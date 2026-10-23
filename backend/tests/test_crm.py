from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.security import hash_password
from app.models import Deal, Pipeline, PipelineStage, TaskReminder, User, WorkspaceMember
from app.models.entities import StageType

pytestmark = pytest.mark.asyncio


async def test_my_day_shows_only_active_assigned_work(crm):
    http, base = crm["http"], crm["base"]
    assigned = (await http.post(base + "/deals", json={**crm["payload"],
        "responsible_user_id": str(crm["user"].id)})).json()
    path = base + "/deals/" + assigned["id"]
    assert (await http.put(path + "/follow-up", json={"at": "2026-12-01T10:00:00Z", "action": "call"})).status_code == 200
    assigned_task = (await http.post(path + "/tasks", json={"title": "Позвонить", "assignee_user_id": str(crm["user"].id)})).json()
    await http.post(path + "/tasks", json={"title": "Без исполнителя"})
    other = (await http.post(base + "/deals", json={**crm["payload"], "title": "Не моя сделка"})).json()
    await http.post(base + "/deals/" + other["id"] + "/tasks", json={"title": "Без исполнителя"})
    response = await http.get(base + "/my-day")
    assert response.status_code == 200, response.text
    day = response.json()
    assert [item["task"]["id"] for item in day["tasks"]] == [assigned_task["id"]]
    assert [item["deal_id"] for item in day["follow_ups"]] == [assigned["id"]]
    await http.patch(path + "/tasks/" + assigned_task["id"], json={"status": "DONE"})
    assert (await http.get(base + "/my-day")).json()["tasks"] == []
    crm["next"].stage_type = StageType.WON
    await crm["db"].commit()
    assert (await http.patch(path, json={"stage_id": str(crm["next"].id)})).status_code == 200
    assert (await http.get(base + "/my-day")).json()["follow_ups"] == []
    foreign = f'/api/v1/workspaces/{crm["spaces"][1].id}/my-day'
    assert (await http.get(foreign)).status_code == 404


async def test_task_reminders_are_scoped_due_and_acknowledged(crm):
    http, base = crm["http"], crm["base"]
    deal_id = (await http.post(base + "/deals", json=crm["payload"])).json()["id"]
    task = (await http.post(base + "/deals/" + deal_id + "/tasks", json={
        "title": "Связаться с клиентом", "start_at": "2020-01-01T10:00:00Z",
        "due_at": "2020-01-03T10:00:00Z"})).json()
    path = base + "/deals/" + deal_id + "/tasks/" + task["id"] + "/reminders"
    user_id = str(crm["user"].id)
    assert (await http.post(path, json={"recipient_user_id": user_id, "kind": "DATE"})).status_code == 422
    assert (await http.post(path, json={"recipient_user_id": user_id, "kind": "DUE_OFFSET", "offset_minutes": -1})).status_code == 422
    assert (await http.post(path, json={"recipient_user_id": str(uuid4()), "kind": "DATE", "at": "2020-01-01T09:00:00Z"})).status_code == 422
    date_reminder = await http.post(path, json={"recipient_user_id": user_id,
        "kind": "DATE", "at": "2020-01-01T09:00:00Z"})
    assert date_reminder.status_code == 201, date_reminder.text
    assert date_reminder.json()["trigger_at"] == "2020-01-01T09:00:00Z"
    relative = await http.post(path, json={"recipient_user_id": user_id,
        "kind": "DUE_OFFSET", "offset_minutes": 120})
    assert relative.status_code == 201, relative.text
    assert relative.json()["trigger_at"] == "2020-01-03T08:00:00Z"
    assert len((await http.get(path)).json()) == 2
    due_path = base + "/reminders/due"
    assert {item["id"] for item in (await http.get(due_path)).json()} == {date_reminder.json()["id"], relative.json()["id"]}
    ack = await http.post(base + "/reminders/" + date_reminder.json()["id"] + "/ack")
    assert ack.status_code == 200 and ack.json()["acknowledged_at"] is not None
    assert [item["id"] for item in (await http.get(due_path)).json()] == [relative.json()["id"]]
    task_path = base + "/deals/" + deal_id + "/tasks/" + task["id"]
    assert (await http.patch(task_path, json={"due_at": "2030-01-03T10:00:00Z"})).status_code == 200
    assert (await http.get(due_path)).json() == []
    assert {item["id"]: item["trigger_at"] for item in (await http.get(path)).json()}[relative.json()["id"]] == "2030-01-03T08:00:00Z"
    foreign = f'/api/v1/workspaces/{crm["spaces"][1].id}/deals/{deal_id}/tasks/{task["id"]}/reminders'
    assert (await http.get(foreign)).status_code == 404
    assert (await http.post(foreign, json={"recipient_user_id": user_id, "kind": "DATE", "at": "2020-01-01T09:00:00Z"})).status_code == 404
    assert (await http.get(f'/api/v1/workspaces/{crm["spaces"][1].id}/reminders/due')).status_code == 404
    assert (await http.delete(path + "/" + relative.json()["id"])).status_code == 204
    assert len((await http.get(path)).json()) == 1


async def test_deal_tasks_are_scoped_and_keep_completion_actor(crm):
    http, base = crm["http"], crm["base"]
    deal_id = (await http.post(base + "/deals", json=crm["payload"])).json()["id"]
    path = base + "/deals/" + deal_id + "/tasks"
    payload = {"title": "  Подготовить ТЗ  ", "priority": "HIGH",
        "assignee_user_id": str(crm["user"].id),
        "start_at": "2026-10-23T10:00:00Z", "due_at": "2026-10-24T18:00:00Z"}
    assert (await http.post(path, json={**payload, "due_at": "2026-10-22T18:00:00Z"})).status_code == 422
    assert (await http.post(path, json={**payload, "assignee_user_id": str(uuid4())})).status_code == 422
    created = await http.post(path, json=payload)
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["title"] == "Подготовить ТЗ" and task["status"] == "OPEN"
    assert task["created_by_user_id"] == str(crm["user"].id)
    task_path = path + "/" + task["id"]
    assert (await http.patch(task_path, json={"due_at": "2026-10-22T18:00:00Z"})).status_code == 422
    assert (await http.patch(task_path, json={"assignee_user_id": str(uuid4())})).status_code == 422
    assert (await http.patch(task_path, json={"title": None})).status_code == 422
    completed = await http.patch(task_path, json={"status": "DONE", "description": "Готово"})
    assert completed.status_code == 200, completed.text
    assert completed.json()["completed_by_user_id"] == str(crm["user"].id)
    assert completed.json()["completed_at"] is not None
    assert (await http.get(path)).json()[0]["description"] == "Готово"
    reopened = await http.patch(task_path, json={"status": "OPEN"})
    assert reopened.status_code == 200 and reopened.json()["completed_at"] is None
    other = f'/api/v1/workspaces/{crm["spaces"][1].id}/deals/{deal_id}/tasks'
    assert (await http.get(other)).status_code == 404
    assert (await http.post(other, json=payload)).status_code == 404
    assert (await http.patch(other + "/" + task["id"], json={"status": "DONE"})).status_code == 404
    member = await crm["db"].scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm["spaces"][0].id))
    member.role = "MANAGER"
    await crm["db"].commit()
    assert (await http.patch(task_path, json={"status": "DONE"})).status_code == 200
    assert (await http.delete(task_path)).status_code == 403
    member.role = "OWNER"
    await crm["db"].commit()
    assert (await http.delete(task_path)).status_code == 204
    assert (await http.get(path)).json() == []
    assert (await http.get(base + "/deals/" + deal_id)).status_code == 200


async def test_removing_member_clears_deal_task_assignment(crm):
    db, http, base = crm["db"], crm["http"], crm["base"]
    member_user = User(id=uuid4(), email=f"{uuid4()}@example.com",
                       password_hash=hash_password("test-password-123"), first_name="Коллега")
    db.add(member_user)
    await db.flush()
    member = WorkspaceMember(workspace_id=crm["spaces"][0].id, user_id=member_user.id, role="MANAGER")
    db.add(member)
    await db.commit()
    deal_id = (await http.post(base + "/deals", json=crm["payload"])).json()["id"]
    task_path = base + "/deals/" + deal_id + "/tasks"
    task = (await http.post(task_path, json={"title": "Передать задачу", "assignee_user_id": str(member_user.id)})).json()
    reminder = await http.post(task_path + "/" + task["id"] + "/reminders", json={
        "recipient_user_id": str(member_user.id), "kind": "DATE", "at": "2030-01-01T09:00:00Z"})
    assert reminder.status_code == 201, reminder.text
    assert (await http.delete(base + "/members/" + str(member.id))).status_code == 204
    assert (await http.get(task_path)).json()[0]["assignee_user_id"] is None
    assert (await http.get(task_path)).json()[0]["id"] == task["id"]
    assert await db.scalar(select(TaskReminder).where(TaskReminder.id == reminder.json()["id"])) is None


async def test_deal_dates_validate_order_and_persist(crm):
    http, base = crm["http"], crm["base"]
    invalid = await http.post(base + "/deals", json={**crm["payload"],
        "start_date": "2026-11-02", "end_date": "2026-10-23"})
    assert invalid.status_code == 422
    created = await http.post(base + "/deals", json={**crm["payload"],
        "start_date": "2026-10-23", "end_date": "2026-11-02"})
    assert created.status_code == 201, created.text
    deal_id = created.json()["id"]
    assert created.json()["start_date"] == "2026-10-23"
    assert created.json()["end_date"] == "2026-11-02"
    path = base + "/deals/" + deal_id
    assert (await http.patch(path, json={"start_date": "2026-11-03"})).status_code == 422
    assert (await http.get(path)).json()["start_date"] == "2026-10-23"
    updated = await http.patch(path, json={"end_date": None, "start_date": "2026-11-03"})
    assert updated.status_code == 200 and updated.json()["end_date"] is None
    other = f'/api/v1/workspaces/{crm["spaces"][1].id}/deals/{deal_id}'
    assert (await http.get(other)).status_code == 404
    assert (await http.patch(other, json={"end_date": "2026-11-05"})).status_code == 404


async def test_company_profile_search_deals_and_workspace_access(crm):
    http, base = crm["http"], crm["base"]
    path = base + "/clients"
    created = await http.post(path, json={"name": "  Новая компания  ", "phone": "+7 900 000-00-00",
        "email": "office@example.com", "website": "https://example.com", "notes": "Важный клиент"})
    assert created.status_code == 201, created.text
    company = created.json()
    assert company["name"] == "Новая компания" and company["email"] == "office@example.com"
    assert [row["id"] for row in (await http.get(path + "?search=новая")).json()] == [company["id"]]
    assert (await http.get(path + "/" + company["id"])).json()["notes"] == "Важный клиент"
    assert (await http.patch(path + "/" + company["id"], json={"name": " "})).status_code == 422
    patched = await http.patch(path + "/" + company["id"], json={"phone": None, "notes": "Договор в работе"})
    assert patched.status_code == 200 and patched.json()["phone"] is None
    assert patched.json()["notes"] == "Договор в работе"
    assert (await http.get(path + "/" + company["id"] + "/deals")).json() == []
    disposable = (await http.post(path, json={"name": "Без сделок"})).json()
    assert (await http.delete(path + "/" + disposable["id"])).status_code == 204
    assert (await http.get(path + "/" + disposable["id"])).status_code == 404
    deal = await http.post(base + "/deals", json={**crm["payload"], "client_id": company["id"]})
    assert deal.status_code == 201, deal.text
    assert [row["id"] for row in (await http.get(path + "/" + company["id"] + "/deals")).json()] == [deal.json()["id"]]
    assert (await http.delete(path + "/" + company["id"])).status_code == 409
    assert (await http.get(path + "/" + company["id"])).status_code == 200
    other = f'/api/v1/workspaces/{crm["spaces"][1].id}/clients/{company["id"]}'
    assert (await http.get(other)).status_code == 404
    assert (await http.patch(other, json={"name": "Чужая"})).status_code == 404
    assert (await http.get(other + "/deals")).status_code == 404
    assert (await http.delete(other)).status_code == 404
    member = await crm["db"].scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm["spaces"][0].id))
    member.role = "MANAGER"
    await crm["db"].commit()
    assert (await http.patch(path + "/" + company["id"], json={"website": "example.org"})).status_code == 200
    assert (await http.delete(path + "/" + company["id"])).status_code == 403


async def test_contact_company_links_and_deal_contact_are_scoped(crm):
    http, base = crm["http"], crm["base"]
    company_id = str(crm["clients"][0].id)
    second = (await http.post(base + "/clients", json={"name": "Вторая компания"})).json()["id"]
    path = base + "/contacts"
    foreign_id = str(crm["clients"][1].id)
    assert (await http.post(path, json={"first_name": "Мария", "client_ids": [foreign_id]})).status_code == 422
    assert (await http.post(path, json={"first_name": "Мария", "client_ids": [company_id, company_id]})).status_code == 422
    created = await http.post(path, json={"first_name": "Мария", "last_name": "Иванова",
        "phone": "+7 900 000-00-00", "email": "maria@example.com", "client_ids": [company_id, second]})
    assert created.status_code == 201, created.text
    contact = created.json()
    assert set(contact["client_ids"]) == {company_id, second}
    assert [row["id"] for row in (await http.get(path + "?search=Иванова")).json()] == [contact["id"]]
    assert [row["id"] for row in (await http.get(base + "/clients/" + second + "/contacts")).json()] == [contact["id"]]
    assert (await http.get(path + "/" + contact["id"])).json()["email"] == "maria@example.com"
    deal = await http.post(base + "/deals", json={**crm["payload"], "contact_id": contact["id"]})
    assert deal.status_code == 201, deal.text
    assert deal.json()["contact_name"] == "Иванова Мария"
    assert deal.json()["contact_id"] == contact["id"]
    assert [row["id"] for row in (await http.get(path + "/" + contact["id"] + "/deals")).json()] == [deal.json()["id"]]
    assert (await http.patch(path + "/" + contact["id"], json={"client_ids": [second]})).status_code == 409
    assert (await http.delete(path + "/" + contact["id"])).status_code == 409
    other_contact = (await http.post(path, json={"first_name": "Другой", "client_ids": [second]})).json()
    assert (await http.patch(base + "/deals/" + deal.json()["id"], json={"contact_id": other_contact["id"]})).status_code == 422
    assert (await http.delete(path + "/" + other_contact["id"])).status_code == 204
    assert (await http.get(path + "/" + other_contact["id"])).status_code == 404
    other = f'/api/v1/workspaces/{crm["spaces"][1].id}/contacts/{contact["id"]}'
    assert (await http.get(other)).status_code == 404
    assert (await http.patch(other, json={"first_name": "Чужая"})).status_code == 404
    assert (await http.delete(other)).status_code == 404
    member = await crm["db"].scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm["spaces"][0].id))
    member.role = "MANAGER"
    await crm["db"].commit()
    assert (await http.patch(path + "/" + contact["id"], json={"phone": None})).status_code == 200
    assert (await http.delete(path + "/" + contact["id"])).status_code == 403


async def test_pipeline_lifecycle_preserves_deals_and_workspace_access(crm):
    http, base = crm["http"], crm["base"]
    path = base + "/pipelines"
    assert (await http.post(path, json={"name": " "})).status_code == 422
    created = await http.post(path, json={"name": "  Поддержка  "})
    assert created.status_code == 201, created.text
    second = created.json()
    assert second["name"] == "Поддержка" and second["is_active"] and not second["is_default"]
    assert len(second["stages"]) == 4
    assert [stage["stage_type"] for stage in second["stages"]] == ["OPEN", "OPEN", "WON", "LOST"]
    assert len((await http.get(path)).json()) == 2
    assert (await http.patch(path + "/" + second["id"], json={"name": "Сопровождение"})).json()["name"] == "Сопровождение"
    assert (await http.post(path + "/" + second["id"] + "/default")).json()["is_default"]
    assert (await http.get(path)).json()[0]["id"] == second["id"]
    first_id = str(crm["pipelines"][0].id)
    assert (await http.post(path + "/" + second["id"] + "/deactivate")).json()["is_active"] is False
    assert [item["id"] for item in (await http.get(path)).json()] == [first_id]
    assert (await http.get(path + "?include_inactive=true")).json()[-1]["id"] == second["id"]
    assert (await http.post(path + "/" + second["id"] + "/default")).status_code == 409
    assert (await http.post(path + "/" + second["id"] + "/activate")).json()["is_active"]
    assert (await http.delete(path + "/" + second["id"])).status_code == 204
    assert len((await http.get(path)).json()) == 1
    assert (await http.delete(path + "/" + first_id)).status_code == 409

    used = (await http.post(path, json={"name": "Проекты"})).json()
    deal = await http.post(base + "/deals", json={**crm["payload"],
        "pipeline_id": used["id"], "stage_id": used["stages"][0]["id"]})
    assert deal.status_code == 201, deal.text
    assert (await http.delete(path + "/" + used["id"])).status_code == 409
    assert (await http.post(path + "/" + used["id"] + "/deactivate")).status_code == 200
    assert (await http.get(base + "/deals/" + deal.json()["id"])).json()["pipeline_id"] == used["id"]
    assert (await http.post(path + "/" + used["id"] + "/activate")).status_code == 200

    other = f'/api/v1/workspaces/{crm["spaces"][1].id}/pipelines'
    assert (await http.post(other, json={"name": "Intrusion"})).status_code == 404
    assert (await http.patch(other + "/" + used["id"], json={"name": "Intrusion"})).status_code == 404
    member = await crm["db"].scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm["spaces"][0].id))
    member.role = "MANAGER"
    await crm["db"].commit()
    assert (await http.post(path, json={"name": "Forbidden"})).status_code == 403
    assert (await http.post(path + "/" + used["id"] + "/deactivate")).status_code == 403


async def test_deal_activity_is_persistent_and_workspace_scoped(crm):
    http, base = crm["http"], crm["base"]
    deal = (await http.post(base + "/deals", json=crm["payload"])).json()
    path = base + "/deals/" + deal["id"] + "/activities"
    assert (await http.post(path, json={"body": "  "})).status_code == 422
    created = await http.post(path, json={"body": "  Позвонил клиенту  "})
    assert created.status_code == 201, created.text
    assert created.json()["body"] == "Позвонил клиенту"
    assert created.json()["author_user_id"] == str(crm["user"].id)
    assert [item["id"] for item in (await http.get(path)).json()] == [created.json()["id"]]
    assert (await http.get(path + "?limit=1&offset=1")).json() == []
    other = f'/api/v1/workspaces/{crm["spaces"][1].id}/deals/{deal["id"]}/activities'
    assert (await http.get(other)).status_code == 404
    assert (await http.post(other, json={"body": "Недопустимо"})).status_code == 404
    assert (await http.delete(base + "/deals/" + deal["id"])).status_code == 204
    assert (await http.get(path)).status_code == 404


async def test_stage_change_is_recorded_once_with_author_and_stage_names(crm):
    http, base = crm["http"], crm["base"]
    deal = (await http.post(base + "/deals", json=crm["payload"])).json()
    path = base + "/deals/" + deal["id"]
    changed = await http.patch(path, json={"stage_id": str(crm["next"].id)})
    assert changed.status_code == 200, changed.text
    assert (await http.patch(path, json={"stage_id": str(crm["next"].id)})).status_code == 200
    assert (await http.patch(path, json={"title": "New title"})).status_code == 200
    activities = (await http.get(path + "/activities")).json()
    assert len(activities) == 1
    assert activities[0]["kind"] == "STAGE_CHANGE"
    assert activities[0]["body"] == "Стадия: Stage 0 → Next"
    assert activities[0]["author_user_id"] == str(crm["user"].id)


async def test_completed_follow_up_is_archived_once_and_workspace_scoped(crm):
    http, base = crm["http"], crm["base"]
    deal = (await http.post(base + "/deals", json=crm["payload"])).json()
    path = base + "/deals/" + deal["id"] + "/follow-up"
    assert (await http.post(path + "/complete", json={})).status_code == 409
    scheduled = {"at": "2026-12-01T16:30:00+05:00", "action": "call", "comment": "Обсудить бюджет"}
    assert (await http.put(path, json=scheduled)).status_code == 200
    finished = await http.post(path + "/complete", json={"outcome_comment": "Договорились о встрече"})
    assert finished.status_code == 201, finished.text
    result = finished.json()
    assert result["deal"]["follow_up_at"] is None
    assert result["completion"]["scheduled_at"] == "2026-12-01T11:30:00Z"
    assert result["completion"]["action"] == "call"
    assert result["completion"]["planned_comment"] == "Обсудить бюджет"
    assert result["completion"]["outcome_comment"] == "Договорились о встрече"
    assert result["completion"]["completed_by_user_id"] == str(crm["user"].id)
    assert (await http.post(path + "/complete", json={})).status_code == 409
    assert len((await http.get(path + "/completions")).json()) == 1
    other = f'/api/v1/workspaces/{crm["spaces"][1].id}/deals/{deal["id"]}/follow-up'
    assert (await http.get(other + "/completions")).status_code == 404
    assert (await http.post(other + "/complete", json={})).status_code == 404
    assert (await http.delete(base + "/deals/" + deal["id"])).status_code == 204


async def test_responsible_must_be_workspace_member_and_is_cleared_on_removal(crm):
    http, base = crm["http"], crm["base"]
    stranger = User(id=uuid4(), email=f"{uuid4()}@example.com", password_hash="unused", first_name="Other")
    crm["db"].add(stranger)
    await crm["db"].commit()
    assert (await http.post(base + "/deals", json={**crm["payload"], "responsible_user_id": str(stranger.id)})).status_code == 422
    member = WorkspaceMember(workspace_id=crm["spaces"][0].id, user_id=stranger.id, role="MANAGER")
    crm["db"].add(member)
    await crm["db"].commit()
    created = await http.post(base + "/deals", json={**crm["payload"], "responsible_user_id": str(stranger.id)})
    assert created.status_code == 201, created.text
    path = base + "/deals/" + created.json()["id"]
    assert created.json()["responsible_user_id"] == str(stranger.id)
    assert (await http.patch(path, json={"responsible_user_id": str(uuid4())})).status_code == 422
    assert (await http.get(path)).json()["responsible_user_id"] == str(stranger.id)
    assert (await http.delete(base + "/members/" + str(member.id))).status_code == 204
    assert (await http.get(path)).json()["responsible_user_id"] is None


async def test_stage_management_preserves_deals_and_workspace_rights(crm):
    http, base = crm["http"], crm["base"]
    path = base + "/pipelines/" + str(crm["pipelines"][0].id) + "/stages"
    created = await http.post(path, json={"name": "Review", "color": "#1166AA"})
    assert created.status_code == 201, created.text
    stage_id = created.json()["id"]
    assert created.json()["position"] == 3
    edited = await http.patch(path + "/" + stage_id, json={"name": "Approval", "stage_type": "WON"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] == "Approval" and edited.json()["stage_type"] == "WON"
    assert (await http.patch(path + "/" + stage_id, json={"name": " "})).status_code == 422
    order = [stage_id, str(crm["stages"][0].id), str(crm["next"].id)]
    assert (await http.put(path + "/order", json={"ids": order[:2]})).status_code == 422
    reordered = await http.put(path + "/order", json={"ids": order})
    assert reordered.status_code == 200, reordered.text
    assert [stage["id"] for stage in (await http.get(base + "/pipelines")).json()[0]["stages"]] == order
    assert (await http.delete(path + "/" + stage_id)).status_code == 204
    assert (await http.delete(path + "/" + str(crm["next"].id))).status_code == 409
    occupied = (await http.post(path, json={"name": "Occupied"})).json()
    deal = await http.post(base + "/deals", json={**crm["payload"], "stage_id": occupied["id"]})
    assert deal.status_code == 201, deal.text
    assert (await http.delete(path + "/" + occupied["id"])).status_code == 409
    assert (await http.get(base + "/deals/" + deal.json()["id"])).json()["stage_id"] == occupied["id"]
    other = f'/api/v1/workspaces/{crm["spaces"][1].id}/pipelines/{crm["pipelines"][0].id}/stages'
    assert (await http.post(other, json={"name": "Intrusion"})).status_code == 404
    member = await crm["db"].scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm["spaces"][0].id))
    member.role = "MANAGER"
    await crm["db"].commit()
    assert (await http.post(path, json={"name": "Forbidden"})).status_code == 403


async def test_crud_and_follow_up_persist(crm):
    http, base = crm["http"], crm["base"]
    assert len((await http.get("/api/v1/workspaces")).json()) == 1
    assert len((await http.get(base + "/pipelines")).json()[0]["stages"]) == 2
    client = await http.post(base + "/clients", json={"name": "Новый клиент"})
    assert client.status_code == 201
    assert len((await http.get(base + "/clients")).json()) == 2
    response = await http.post(base + "/deals", json=crm["payload"])
    assert response.status_code == 201, response.text
    deal = response.json()
    assert deal["amount"] == "65000.25"
    path = base + "/deals/" + deal["id"]
    updated = await http.patch(path, json={"title": "Updated", "amount": "0.99", "stage_id": str(crm["next"].id), "contact_name": None})
    assert updated.status_code == 200, updated.text
    assert updated.json()["stage_id"] == str(crm["next"].id)
    follow = {"at": "2026-12-01T16:30:00+05:00", "action": "proposal", "comment": "Отправить КП"}
    assert (await http.put(path + "/follow-up", json=follow)).status_code == 200
    crm["db"].expire_all()
    persisted = (await http.get(path)).json()
    assert persisted["follow_up_at"] == "2026-12-01T11:30:00Z"
    assert persisted["follow_up_action"] == "proposal"
    assert persisted["follow_up_comment"] == "Отправить КП"
    assert persisted["amount"] == "0.99" and persisted["title"] == "Updated"
    assert persisted["contact_name"] is None
    assert len((await http.get(base + "/deals?limit=1")).json()) == 1
    assert (await http.get(base + "/deals?offset=1")).json() == []
    assert (await http.get(base + f"/deals?pipeline_id={uuid4()}")).json() == []
    cleared = await http.delete(path + "/follow-up")
    assert cleared.json()["follow_up_at"] is None
    assert cleared.json()["follow_up_action"] is None
    assert cleared.json()["follow_up_comment"] is None
    assert (await http.delete(path)).status_code == 204
    assert (await http.get(path)).status_code == 404
    assert (await http.get(base + "/deals")).json() == []


async def test_workspace_isolation_and_relationships(crm):
    http, base = crm["http"], crm["base"]
    other = f'/api/v1/workspaces/{crm["spaces"][1].id}'
    for resource in ("deals", "clients", "pipelines"):
        assert (await http.get(other + "/" + resource)).status_code == 404
    assert (await http.post(other + "/deals", json=crm["payload"])).status_code == 404
    for field, value in (("client_id", crm["clients"][1].id), ("stage_id", crm["stages"][1].id), ("pipeline_id", crm["pipelines"][1].id)):
        assert (await http.post(base + "/deals", json={**crm["payload"], field: str(value)})).status_code == 422
    # Even a user with membership in both spaces cannot address a deal through the wrong space.
    crm["db"].add(WorkspaceMember(workspace_id=crm["spaces"][1].id, user_id=crm["user"].id))
    await crm["db"].commit()
    deal = (await http.post(base + "/deals", json=crm["payload"])).json()
    path = other + "/deals/" + deal["id"]
    assert (await http.get(path)).status_code == 404
    assert (await http.patch(path, json={"title": "Intrusion"})).status_code == 404
    assert (await http.delete(path)).status_code == 404
    assert (await http.put(path + "/follow-up", json={"at": "2026-12-01T10:00:00Z", "action": "call"})).status_code == 404
    assert (await http.delete(path + "/follow-up")).status_code == 404
    assert (await http.get(other + "/deals")).json() == []
    assert (await http.patch(base + "/deals/" + deal["id"], json={"client_id": str(crm["clients"][1].id)})).status_code == 422
    # A stage from another pipeline in the SAME workspace is also invalid.
    pipeline = Pipeline(id=uuid4(), workspace_id=crm["spaces"][0].id, name="Other")
    crm["db"].add(pipeline)
    await crm["db"].flush()
    stage = PipelineStage(id=uuid4(), workspace_id=pipeline.workspace_id, pipeline_id=pipeline.id, name="Other", position=0)
    crm["db"].add(stage)
    await crm["db"].commit()
    assert (await http.patch(base + "/deals/" + deal["id"], json={"stage_id": str(stage.id)})).status_code == 422


@pytest.mark.parametrize("patch", [{"title": " "}, {"title": None}, {"amount": "-1"}, {"amount": "1.001"},
                                    {"amount": "1000000000000"}, {"client_id": None}, {"workspace_id": str(uuid4())}])
async def test_invalid_update(crm, patch):
    deal = (await crm["http"].post(crm["base"] + "/deals", json=crm["payload"])).json()
    response = await crm["http"].patch(crm["base"] + "/deals/" + deal["id"], json=patch)
    assert response.status_code == 422


@pytest.mark.parametrize("follow", [{"at": "2026-12-01T10:00:00", "action": "call"},
                                      {"at": "invalid", "action": "call"},
                                      {"at": "2026-12-01T10:00:00Z", "action": "invalid"}])
async def test_invalid_follow_up(crm, follow):
    deal = (await crm["http"].post(crm["base"] + "/deals", json=crm["payload"])).json()
    assert (await crm["http"].put(crm["base"] + "/deals/" + deal["id"] + "/follow-up", json=follow)).status_code == 422


async def test_dev_auth_never_bypasses_session(crm, monkeypatch):
    crm["http"].cookies.clear()
    monkeypatch.setattr(settings, "dev_auth_enabled", True)
    assert (await crm["http"].get("/api/v1/workspaces")).status_code == 401


async def test_database_rejects_cross_workspace_client(crm):
    db = crm["db"]
    payload = crm["payload"].copy()
    from uuid import UUID
    for key in ("client_id", "pipeline_id", "stage_id"):
        payload[key] = UUID(payload[key])
    payload["client_id"] = crm["clients"][1].id
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(Deal(workspace_id=crm["spaces"][0].id, **payload))
            await db.flush()
    assert (await db.scalars(select(Deal))).all() == []
