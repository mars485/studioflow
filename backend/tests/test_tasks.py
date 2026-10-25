from uuid import uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError

from app.models import Contact, Project, ProjectStage, Task, TaskStatus, WorkspaceMember

pytestmark = pytest.mark.asyncio


async def test_renamed_deleted_statuses_stay_changed_and_null_patch_is_rejected(crm):
    http, base = crm["http"], crm["base"]
    statuses = (await http.get(base + "/task-statuses")).json()
    path = base + "/task-statuses/" + statuses[0]["id"]
    assert (await http.patch(path, json={"name": "В очереди"})).status_code == 200
    assert (await http.delete(base + "/task-statuses/" + statuses[2]["id"])).status_code == 204
    reloaded = (await http.get(base + "/task-statuses")).json()
    assert len(reloaded) == 3 and reloaded[0]["name"] == "В очереди"
    assert (await http.patch(path, json={"is_final": None})).status_code == 422
    task = (await http.post(base + "/tasks", json={"title": "Работа", "status_id": statuses[0]["id"]})).json()
    assert (await http.patch(path, json={"is_final": True})).status_code == 409
    checklist = base + "/tasks/" + task["id"] + "/checklist"
    item = (await http.post(checklist, json={"text": "Пункт"})).json()
    assert (await http.patch(checklist + "/" + item["id"], json={"is_done": None})).status_code == 422


async def test_parent_deletion_detaches_subtask_without_losing_it(crm):
    http, base = crm["http"], crm["base"]
    parent = (await http.post(base + "/tasks", json={"title": "Родитель"})).json()
    child = (await http.post(base + "/tasks", json={"title": "Подзадача", "parent_task_id": parent["id"]})).json()
    assert (await http.delete(base + "/tasks/" + parent["id"])).status_code == 204
    kept = (await http.get(base + "/tasks/" + child["id"])).json()
    assert kept["parent_task_id"] is None and kept["title"] == "Подзадача"


async def test_database_rejects_cross_workspace_task_links(crm):
    http, base, db = crm["http"], crm["base"], crm["db"]
    task = (await http.post(base + "/tasks", json={"title": "Локальная задача"})).json()
    foreign_id = crm["spaces"][1].id
    contact = Contact(workspace_id=foreign_id, first_name="Чужой контакт")
    stage = ProjectStage(workspace_id=foreign_id, name="Этап")
    status = TaskStatus(workspace_id=foreign_id, name="Сделать", is_final=False)
    db.add_all([contact, stage, status])
    await db.flush()
    project = Project(workspace_id=foreign_id, title="Чужой проект", client_id=crm["clients"][1].id, stage_id=stage.id)
    parent = Task(workspace_id=foreign_id, title="Чужая задача", status_id=status.id)
    db.add_all([project, parent])
    await db.commit()
    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    from uuid import UUID
    for column, value in ((Task.contact_id, contact.id), (Task.project_id, project.id), (Task.parent_task_id, parent.id)):
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(update(Task).where(Task.id == UUID(task["id"])).values({column: value}))


async def change_role(crm, role: str):
    member = await crm["db"].scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm["spaces"][0].id))
    member.role = role
    await crm["db"].commit()


async def test_task_statuses_are_seeded_ordered_and_protected(crm):
    http, base = crm["http"], crm["base"]
    other = f'/api/v1/workspaces/{crm["spaces"][1].id}/task-statuses'
    statuses = (await http.get(base + "/task-statuses")).json()
    assert [item["name"] for item in statuses] == ["Сделать", "В работе", "Ожидает контроля", "Завершено"]
    assert [item["is_final"] for item in statuses] == [False, False, False, True]
    assert (await http.get(base + "/task-statuses")).json() == statuses

    created = await http.post(base + "/task-statuses", json={"name": "  Проверка  "})
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "Проверка" and created.json()["position"] == 4
    assert (await http.post(base + "/task-statuses", json={"name": "Проверка"})).status_code == 409
    assert (await http.post(base + "/task-statuses", json={"name": "  "})).status_code == 422

    ids = [item["id"] for item in (await http.get(base + "/task-statuses")).json()]
    reordered = await http.put(base + "/task-statuses/order", json={"ids": list(reversed(ids))})
    assert reordered.status_code == 200, reordered.text
    assert [item["id"] for item in reordered.json()] == list(reversed(ids))
    assert (await http.put(base + "/task-statuses/order", json={"ids": ids[:2]})).status_code == 422

    task = (await http.post(base + "/tasks", json={"title": "Проверить статус", "status_id": ids[0]})).json()
    assert (await http.delete(base + f"/task-statuses/{ids[0]}")).status_code == 409
    assert (await http.delete(base + f"/task-statuses/{created.json()['id']}")).status_code == 204
    final_ids = [item["id"] for item in (await http.get(base + "/task-statuses")).json() if item["is_final"]]
    assert (await http.patch(base + f"/task-statuses/{final_ids[0]}", json={"is_final": False})).status_code == 409
    assert (await http.get(other)).status_code == 404
    await change_role(crm, "MANAGER")
    assert (await http.post(base + "/task-statuses", json={"name": "Нельзя"})).status_code == 403
    await change_role(crm, "OWNER")
    assert (await http.get(base + "/tasks" + f"/{task['id']}")).json()["status_name"] == "Сделать"


async def test_workspace_tasks_links_subtasks_checklist_and_watchers(crm):
    http, base = crm["http"], crm["base"]
    other = f'/api/v1/workspaces/{crm["spaces"][1].id}'
    deal = (await http.post(base + "/deals", json=crm["payload"])).json()
    contact = (await http.post(base + "/contacts", json={"first_name": "Анна"})).json()
    payload = {"title": "  Подготовить прототип  ", "priority": "HIGH", "estimate_minutes": 90,
               "deal_id": deal["id"], "contact_id": contact["id"], "assignee_user_id": str(crm["user"].id),
               "start_at": "2026-10-23T10:00:00Z", "due_at": "2026-10-25T18:00:00Z"}
    assert (await http.post(base + "/tasks", json={**payload, "due_at": "2026-10-22T18:00:00Z"})).status_code == 422
    assert (await http.post(base + "/tasks", json={**payload, "estimate_minutes": -1})).status_code == 422
    assert (await http.post(base + "/tasks", json={**payload, "assignee_user_id": str(uuid4())})).status_code == 422
    assert (await http.post(base + "/tasks", json={**payload, "status_id": str(uuid4())})).status_code == 422
    created = await http.post(base + "/tasks", json=payload)
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["title"] == "Подготовить прототип" and task["status_name"] == "Сделать" and task["is_final"] is False
    assert task["deal_id"] == deal["id"] and task["contact_id"] == contact["id"]
    assert task["checklist_done"] == 0 and task["checklist_total"] == 0

    child = await http.post(base + "/tasks", json={"title": "Подзадача", "parent_task_id": task["id"]})
    assert child.status_code == 201, child.text
    grandchild = await http.post(base + "/tasks", json={"title": "Второй уровень", "parent_task_id": child.json()["id"]})
    assert grandchild.status_code == 422
    listed = (await http.get(base + "/tasks?parent_task_id=" + task["id"])).json()
    assert [item["id"] for item in listed] == [child.json()["id"]]

    checklist = base + "/tasks/" + task["id"] + "/checklist"
    first = await http.post(checklist, json={"text": "Собрать требования"})
    second = await http.post(checklist, json={"text": "Согласовать макет"})
    assert first.status_code == 201 and second.json()["position"] == 1
    assert (await http.post(checklist, json={"text": "  "})).status_code == 422
    toggled = await http.patch(checklist + "/" + first.json()["id"], json={"is_done": True})
    assert toggled.status_code == 200 and toggled.json()["is_done"] is True
    assert (await http.get(base + "/tasks/" + task["id"])).json()["checklist_done"] == 1
    assert (await http.get(base + "/tasks/" + task["id"])).json()["checklist_total"] == 2
    assert (await http.delete(checklist + "/" + second.json()["id"])).status_code == 204

    watchers = base + "/tasks/" + task["id"] + "/watchers"
    assert (await http.post(watchers, json={"user_id": str(uuid4())})).status_code == 422
    assert (await http.post(watchers, json={"user_id": str(crm["user"].id)})).status_code == 201
    assert (await http.post(watchers, json={"user_id": str(crm["user"].id)})).status_code == 409
    assert [item["email"] for item in (await http.get(watchers)).json()] == [crm["user"].email]
    assert (await http.delete(watchers + "/" + str(crm["user"].id))).status_code == 204

    statuses = (await http.get(base + "/task-statuses")).json()
    final = next(item for item in statuses if item["is_final"])
    done = await http.patch(base + "/tasks/" + task["id"], json={"status_id": final["id"]})
    assert done.status_code == 200, done.text
    assert done.json()["is_final"] is True and done.json()["completed_at"] is not None
    assert done.json()["completed_by_user_id"] == str(crm["user"].id)
    reopened = await http.patch(base + "/tasks/" + task["id"], json={"status_id": statuses[0]["id"]})
    assert reopened.json()["completed_at"] is None and reopened.json()["completed_by_user_id"] is None
    assert [item["id"] for item in (await http.get(base + "/tasks?include_done=false")).json()] != []
    assert (await http.get(base + "/tasks?deal_id=" + deal["id"])).json()[0]["id"] == task["id"]

    assert (await http.get(other + "/tasks/" + task["id"])).status_code == 404
    assert (await http.patch(other + "/tasks/" + task["id"], json={"title": "Чужая"})).status_code == 404
    await change_role(crm, "MANAGER")
    assert (await http.delete(base + "/tasks/" + child.json()["id"])).status_code == 403
    await change_role(crm, "OWNER")
    assert (await http.delete(base + "/tasks/" + child.json()["id"])).status_code == 204
    assert (await http.get(base + "/deals/" + deal["id"])).status_code == 200


async def test_legacy_deal_task_endpoints_use_workspace_statuses(crm):
    http, base = crm["http"], crm["base"]
    deal = (await http.post(base + "/deals", json=crm["payload"])).json()
    path = base + "/deals/" + deal["id"] + "/tasks"
    created = await http.post(path, json={"title": "Собрать бриф", "priority": "LOW"})
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["status"] == "OPEN" and task["created_by_user_id"] == str(crm["user"].id)
    assert (await http.patch(path + "/" + task["id"], json={"status": "DONE"})).json()["status"] == "DONE"
    new_view = (await http.get(base + "/tasks?deal_id=" + deal["id"])).json()[0]
    assert new_view["is_final"] is True and new_view["status_name"] == "Завершено"
    assert (await http.patch(path + "/" + task["id"], json={"status": "OPEN"})).json()["status"] == "OPEN"
    assert new_view["id"] == task["id"]
    reminder = await http.post(path + "/" + task["id"] + "/reminders",
                               json={"recipient_user_id": str(crm["user"].id), "kind": "DUE_OFFSET", "offset_minutes": 30})
    assert reminder.status_code == 422
    assert (await http.delete(base + "/tasks/" + task["id"])).status_code == 204
    assert (await http.get(path)).json() == []
