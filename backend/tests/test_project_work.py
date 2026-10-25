from uuid import UUID, uuid4
import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import Project, ProjectMember, User, WorkspaceMember
from app.models.project_work import ProjectWorkStage

pytestmark = pytest.mark.asyncio


async def create_project(crm):
    response = await crm["http"].post(crm["base"] + "/projects", json={"title": "Рабочий план", "client_id": str(crm["clients"][0].id)})
    assert response.status_code == 201, response.text
    project = response.json()
    return project, crm["base"] + "/projects/" + project["id"] + "/work-plan"


async def test_project_work_crud_dates_order_events_and_cascade(crm):
    http = crm["http"]
    project, path = await create_project(crm)
    first = await http.post(path, json={"title": "Дизайн", "manager_user_id": str(crm["user"].id), "start_date": "2026-11-01", "end_date": "2026-11-05"})
    assert first.status_code == 201 and first.json()["position"] == 0
    second = await http.post(path, json={"title": "Разработка"})
    assert second.status_code == 201 and second.json()["position"] == 1
    ids = [second.json()["id"], first.json()["id"]]
    reordered = await http.put(path + "/order", json={"ids": ids})
    assert reordered.status_code == 200 and [row["id"] for row in reordered.json()] == ids
    assert (await http.put(path + "/order", json={"ids": [ids[0], ids[0]]})).status_code == 422
    assert (await http.put(path + "/order", json={"ids": [ids[0]]})).status_code == 422
    assert (await http.patch(path + "/" + ids[1], json={"end_date": "2026-10-01"})).status_code == 422
    assert (await http.patch(path + "/" + ids[1], json={"title": None})).status_code == 422
    assert (await http.patch(path + "/" + ids[1], json={"status": "DONE"})).json()["status"] == "DONE"
    assert (await http.post(path, json={"title": "Чужой", "manager_user_id": str(uuid4())})).status_code == 422
    assert (await http.get(path)).json()[1]["status"] == "DONE"
    assert (await http.delete(path + "/" + ids[0])).status_code == 204
    events = (await http.get(crm["base"] + "/projects/" + project["id"] + "/events")).json()
    assert any(event["kind"] == "WORK_PLAN" and "Дизайн" in event["body"] for event in events)
    assert (await http.delete(crm["base"] + "/projects/" + project["id"])).status_code == 204
    assert await crm["db"].get(ProjectWorkStage, UUID(ids[1])) is None


async def test_project_work_archive_manager_and_workspace_isolation(crm):
    http, db = crm["http"], crm["db"]
    project, path = await create_project(crm)
    other_project, other_path = await create_project(crm)
    stage = (await http.post(path, json={"title": "План"})).json()
    assert (await http.patch(other_path + "/" + stage["id"], json={"title": "Нельзя"})).status_code == 404
    assert (await http.delete(other_path + "/" + stage["id"])).status_code == 404
    foreign = path.replace(str(crm["spaces"][0].id), str(crm["spaces"][1].id))
    for method, suffix, data in (("GET", "", None), ("POST", "", {"title": "X"}), ("PUT", "/order", {"ids": []}),
                                  ("PATCH", "/" + stage["id"], {"title": "X"}), ("DELETE", "/" + stage["id"], None)):
        assert (await http.request(method, foreign + suffix, json=data)).status_code == 404
    member = await db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm["spaces"][0].id))
    member.role = "MANAGER"
    await db.commit()
    assert (await http.delete(path + "/" + stage["id"])).status_code == 403
    assert (await http.patch(path + "/" + stage["id"], json={"status": "ACTIVE"})).status_code == 200
    assert (await http.patch(crm["base"] + "/projects/" + project["id"], json={"status": "ARCHIVED"})).status_code == 200
    assert (await http.get(path)).status_code == 200
    assert (await http.post(path, json={"title": "X"})).status_code == 409
    assert (await http.patch(path + "/" + stage["id"], json={"status": "DONE"})).status_code == 409
    assert (await http.put(path + "/order", json={"ids": [stage["id"]]})).status_code == 409


async def test_workspace_member_revocation_clears_project_and_work_assignments(crm):
    http, db = crm["http"], crm["db"]
    user = User(email=f'{uuid4()}@example.com', password_hash=hash_password("test-password-123"), first_name="Manager")
    db.add(user)
    await db.flush()
    member = WorkspaceMember(workspace_id=crm["spaces"][0].id, user_id=user.id, role="MANAGER")
    db.add(member)
    await db.commit()
    response = await http.post(crm["base"] + "/projects", json={"title": "Проект менеджера", "client_id": str(crm["clients"][0].id), "manager_user_id": str(user.id)})
    assert response.status_code == 201
    project_id = response.json()["id"]
    path = crm["base"] + "/projects/" + project_id + "/work-plan"
    work = await http.post(path, json={"title": "Работа", "manager_user_id": str(user.id)})
    assert work.status_code == 201
    assert (await http.delete(crm["base"] + "/members/" + str(member.id))).status_code == 204
    assert (await http.get(crm["base"] + "/projects/" + project_id)).json()["manager_user_id"] is None
    assert (await http.get(path)).json()[0]["manager_user_id"] is None
    assert (await http.get(crm["base"] + "/projects/" + project_id + "/members")).json() == []
