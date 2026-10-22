from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models import Deal, Pipeline, PipelineStage, User, WorkspaceMember

pytestmark = pytest.mark.asyncio


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
