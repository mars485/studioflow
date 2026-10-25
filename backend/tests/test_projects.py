from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import WorkspaceMember

pytestmark = pytest.mark.asyncio


async def test_project_copies_primary_contact_from_legacy_deal_form(crm):
    http, base = crm["http"], crm["base"]
    stage = await won_stage(crm)
    contact = (await http.post(base + "/contacts", json={"first_name": "Мария", "client_ids": [str(crm["clients"][0].id)]})).json()
    deal = (await http.post(base + "/deals", json={**crm["payload"], "stage_id": stage["id"], "contact_id": contact["id"]})).json()
    project = await http.post(base + "/projects", json={"deal_id": deal["id"]})
    assert project.status_code == 201, project.text
    contacts = (await http.get(base + "/projects/" + project.json()["id"] + "/contacts")).json()
    assert [row["contact_id"] for row in contacts] == [contact["id"]]


async def change_role(crm, role: str):
    member = await crm["db"].scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm["spaces"][0].id))
    member.role = role
    await crm["db"].commit()


async def won_stage(crm):
    http, base = crm["http"], crm["base"]
    response = await http.post(f'{base}/pipelines/{crm["pipelines"][0].id}/stages',
                               json={"name": "Выиграна", "stage_type": "WON"})
    assert response.status_code == 201, response.text
    return response.json()


async def test_project_from_won_deal_copies_client_contacts_and_amount(crm):
    http, base = crm["http"], crm["base"]
    stage = await won_stage(crm)
    open_deal = (await http.post(base + "/deals", json=crm["payload"])).json()
    assert (await http.post(base + "/projects", json={"deal_id": open_deal["id"]})).status_code == 422

    contact = (await http.post(base + "/contacts", json={"first_name": "Анна",
                                                        "client_ids": [str(crm["clients"][0].id)]})).json()
    deal = (await http.post(base + "/deals", json={**crm["payload"], "stage_id": stage["id"]})).json()
    assert (await http.post(base + "/deals/" + deal["id"] + "/contacts",
                           json={"contact_id": contact["id"]})).status_code == 201

    created = await http.post(base + "/projects", json={"deal_id": deal["id"]})
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["client_id"] == str(crm["clients"][0].id)
    assert project["deal_id"] == deal["id"]
    assert project["amount"] == "65000.25"
    assert project["stage_name"] == "Подготовка" and project["status"] == "ACTIVE"
    contacts = (await http.get(base + f"/projects/{project['id']}/contacts")).json()
    assert [item["contact_id"] for item in contacts] == [contact["id"]]
    events = (await http.get(base + f"/projects/{project['id']}/events")).json()
    assert any("сделки" in item["body"] for item in events)

    assert (await http.post(base + "/projects", json={"deal_id": deal["id"]})).status_code == 409
    forced = await http.post(base + "/projects", json={"deal_id": deal["id"], "force": True})
    assert forced.status_code == 201, forced.text
    assert len((await http.get(base + "/projects?deal_id=" + deal["id"])).json()) == 2
    assert (await http.get(base + "/deals/" + deal["id"])).status_code == 200


async def test_projects_members_tasks_archive_and_isolation(crm):
    http, base = crm["http"], crm["base"]
    project = (await http.post(base + "/projects", json={"title": "Новый сайт",
                                                        "client_id": str(crm["clients"][0].id)})).json()
    assert project["tasks_total"] == 0 and project["members_count"] == 0

    members = base + f"/projects/{project['id']}/members"
    assert (await http.post(members, json={"user_id": str(uuid4())})).status_code == 422
    added = await http.post(members, json={"user_id": str(crm["user"].id), "role": "LEAD"})
    assert added.status_code == 201 and added.json()["role"] == "LEAD"
    assert (await http.post(members, json={"user_id": str(crm["user"].id)})).status_code == 409
    assert [item["user_id"] for item in (await http.get(members)).json()] == [str(crm["user"].id)]

    task = await http.post(base + "/tasks", json={"title": "Смета проекта", "project_id": project["id"]})
    assert task.status_code == 201, task.text
    assert task.json()["project_id"] == project["id"]
    detail = (await http.get(base + f"/projects/{project['id']}")).json()
    assert detail["tasks_total"] == 1 and detail["tasks_done"] == 0
    final = [item for item in (await http.get(base + "/task-statuses")).json() if item["is_final"]][0]
    assert (await http.patch(base + "/tasks/" + task.json()["id"], json={"status_id": final["id"]})).status_code == 200
    assert (await http.get(base + f"/projects/{project['id']}")).json()["tasks_done"] == 1

    archived = await http.patch(base + f"/projects/{project['id']}", json={"status": "ARCHIVED"})
    assert archived.status_code == 200 and archived.json()["archived_at"] is not None
    assert (await http.post(base + "/tasks", json={"title": "Поздно", "project_id": project["id"]})).status_code == 422
    assert (await http.patch(base + "/tasks/" + task.json()["id"], json={"title": "Правка"})).status_code == 200

    assert (await http.get(base + "/projects")).json() == []
    assert [item["id"] for item in (await http.get(base + "/projects?status=archive")).json()] == [project["id"]]
    assert [item["id"] for item in (await http.get(base + "/projects?status=all")).json()] == [project["id"]]
    conflict = await http.patch(base + f"/projects/{project['id']}", json={"status": "COMPLETED"})
    assert conflict.status_code == 200 and conflict.json()["archived_at"] is None

    note = await http.post(base + f"/projects/{project['id']}/events", json={"body": "  Созвон с клиентом  "})
    assert note.status_code == 201 and note.json()["body"] == "Созвон с клиентом"
    assert (await http.post(base + f"/projects/{project['id']}/events", json={"body": "  "})).status_code == 422

    other = f'/api/v1/workspaces/{crm["spaces"][1].id}'
    assert (await http.get(other + "/projects/" + project["id"])).status_code == 404
    assert (await http.get(other + "/projects")).status_code == 404
    assert (await http.get(other + "/project-stages")).status_code == 404

    await change_role(crm, "MANAGER")
    assert (await http.delete(base + "/projects/" + project["id"])).status_code == 403
    await change_role(crm, "OWNER")
    assert (await http.delete(base + "/projects/" + project["id"])).status_code == 204
    kept = await http.get(base + "/tasks/" + task.json()["id"])
    assert kept.status_code == 200 and kept.json()["project_id"] is None


async def test_project_validation_stages_and_client_filter(crm):
    http, base = crm["http"], crm["base"]
    stages = (await http.get(base + "/project-stages")).json()
    assert [item["name"] for item in stages] == ["Подготовка", "В работе", "Сдача", "Завершён"]
    assert (await http.get(base + "/project-stages")).json() == stages

    client_id = str(crm["clients"][0].id)
    assert (await http.post(base + "/projects", json={"title": "Без клиента"})).status_code == 422
    assert (await http.post(base + "/projects", json={"title": "Плохие даты", "client_id": client_id,
                                                      "start_date": "2026-11-10", "end_date": "2026-11-01"})).status_code == 422
    assert (await http.post(base + "/projects", json={"title": "Плохой этап", "client_id": client_id,
                                                      "stage_id": str(uuid4())})).status_code == 422
    assert (await http.post(base + "/projects", json={"title": "Отрицательная сумма", "client_id": client_id,
                                                      "amount": "-5"})).status_code == 422

    first = (await http.post(base + "/projects", json={"title": "Первый", "client_id": client_id,
                                                       "stage_id": stages[2]["id"], "amount": "1000"})).json()
    assert first["stage_name"] == "Сдача" and first["amount"] == "1000.00"
    second = (await http.post(base + "/projects", json={"title": "Второй", "client_id": client_id})).json()
    listed = (await http.get(base + "/projects?client_id=" + client_id)).json()
    assert {item["id"] for item in listed} == {first["id"], second["id"]} and len(listed) == 2

    updated = await http.patch(base + f"/projects/{first['id']}", json={"title": "Первый этап",
                                                                        "stage_id": stages[1]["id"],
                                                                        "start_date": "2026-11-01"})
    assert updated.status_code == 200 and updated.json()["stage_name"] == "В работе"
    assert (await http.patch(base + f"/projects/{first['id']}", json={"title": None})).status_code == 422
    assert (await http.patch(base + f"/projects/{first['id']}", json={})).status_code == 422
