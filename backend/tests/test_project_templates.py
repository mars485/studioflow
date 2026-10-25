from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.main import app
from app.models import WorkspaceMember

pytestmark = pytest.mark.asyncio


async def source_template(crm):
    http, base = crm["http"], crm["base"]
    project = (await http.post(base + "/projects", json={"title": "Источник", "client_id": str(crm["clients"][0].id)})).json()
    path = base + "/projects/" + project["id"] + "/work-plan"
    first = await http.post(path, json={"title": "Дизайн", "status": "DONE", "manager_user_id": str(crm["user"].id), "start_date": "2026-11-01", "end_date": "2026-11-03"})
    assert first.status_code == 201
    assert (await http.post(path, json={"title": "Разработка", "start_date": "2026-11-04", "end_date": "2026-11-10"})).status_code == 201
    response = await http.post(base + "/projects/" + project["id"] + "/template", json={"name": "Сайт студии", "description": "Типовой план"})
    assert response.status_code == 201, response.text
    return project, response.json(), path


async def test_project_template_snapshot_relative_dates_and_independent_copy(crm):
    http, base = crm["http"], crm["base"]
    source, template, source_path = await source_template(crm)
    assert template["phases"] == [{"title": "Дизайн", "start_offset": 0, "end_offset": 2}, {"title": "Разработка", "start_offset": 3, "end_offset": 9}]
    created = await http.post(base + "/projects", json={"title": "Новый проект", "client_id": str(crm["clients"][0].id),
        "template_id": template["id"], "start_date": "2027-01-15"})
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["end_date"] == "2027-01-24"
    path = base + "/projects/" + project["id"] + "/work-plan"
    rows = (await http.get(path)).json()
    assert [row["title"] for row in rows] == ["Дизайн", "Разработка"]
    assert [(row["start_date"], row["end_date"]) for row in rows] == [("2027-01-15", "2027-01-17"), ("2027-01-18", "2027-01-24")]
    assert all(row["status"] == "PLANNED" and row["manager_user_id"] is None for row in rows)
    assert {row["id"] for row in rows}.isdisjoint({row["id"] for row in (await http.get(source_path)).json()})
    assert (await http.patch(base + "/project-templates/" + template["id"], json={"name": "Переименован"})).status_code == 200
    assert (await http.delete(base + "/project-templates/" + template["id"])).status_code == 204
    assert (await http.get(path)).json() == rows
    assert (await http.get(source_path)).json()[0]["status"] == "DONE"


async def test_templates_roles_names_and_scope(crm):
    http, base, db = crm["http"], crm["base"], crm["db"]
    project, template, _ = await source_template(crm)
    path = base + "/projects/" + project["id"] + "/template"
    assert (await http.post(path, json={"name": template["name"]})).status_code == 409
    # A failed name transaction expires fixture identities; subsequent requests use stored IDs.
    template_path = base + "/project-templates/" + template["id"]
    assert (await http.patch(template_path, json={"name": None})).status_code == 422
    spaces = (await http.get('/api/v1/workspaces')).json()
    own_id = spaces[0]["id"]
    member = await db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == UUID(own_id)))
    member.role = "MANAGER"
    await db.commit()
    assert (await http.get(base + "/project-templates")).status_code == 200
    assert (await http.post(path, json={"name": "Новый"})).status_code == 403
    assert (await http.patch(template_path, json={"name": "Нельзя"})).status_code == 403
    assert (await http.delete(template_path)).status_code == 403
    assert (await http.get(f'/api/v1/workspaces/{uuid4()}/project-templates')).status_code == 404


async def test_invalid_template_application_rolls_back_the_whole_project(crm):
    http, base, db = crm["http"], crm["base"], crm["db"]
    client_id = str(crm["clients"][0].id)
    _, template, _ = await source_template(crm)
    await db.commit()
    original_override = app.dependency_overrides[get_db]

    async def request_session():
        # Mirror the production per-request session/rollback, retaining disposable DB isolation.
        async with AsyncSession(bind=db.bind, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
            yield session

    app.dependency_overrides[get_db] = request_session
    try:
        before = (await http.get(base + "/projects?status=all")).json()
        payload = {"title": "Не должен сохраниться", "client_id": client_id, "template_id": template["id"], "start_date": "2027-01-15"}
        assert (await http.post(base + "/projects", json={**payload, "template_id": str(uuid4())})).status_code == 404
        assert (await http.post(base + "/projects", json={**payload, "start_date": "9999-12-31"})).status_code == 422
        assert (await http.post(base + "/projects", json={**payload, "end_date": "2027-01-16"})).status_code == 422
        assert (await http.post(base + "/projects", json={**payload, "start_date": None})).status_code == 422
        after = (await http.get(base + "/projects?status=all")).json()
        assert {row["id"] for row in after} == {row["id"] for row in before}
    finally:
        app.dependency_overrides[get_db] = original_override
