from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app.core.config import settings
from app.core.security import hash_password, token_digest
from app.main import app
from app.models import PipelineStage, User, WorkspaceMember
from app.models.entities import StageType
from app.models.integrations import IncomingLead, IntegrationToken

pytestmark = pytest.mark.asyncio


async def issue(crm):
    response = await crm["http"].post(crm["base"] + "/integration-tokens", json={"name": "ITG website", "pipeline_id": str(crm["pipelines"][0].id), "expires_days": 30})
    assert response.status_code == 201, response.text
    return response.json()


def payload(**changes):
    return {"request_key": str(uuid4()), "title": "Заявка с сайта", "company_name": "Компания с сайта", "contact_first_name": "Мария",
            "email": "Client@Example.com", "phone": "+7 900 000-00-00", "message": "Нужен сайт", "amount": "1500.25", "source": "ITG", **changes}


async def test_server_token_creates_lead_atomically_and_replays_without_copies(crm):
    http, base, db = crm["http"], crm["base"], crm["db"]
    token = await issue(crm)
    stored = await db.get(IntegrationToken, UUID(token["id"]))
    assert stored.token_hash == token_digest(token["token"]) and stored.token_hash != token["token"]
    listed = await http.get(base + "/integration-tokens")
    assert token["token"] not in listed.text and 'token_hash' not in listed.text
    headers = {"Authorization": "Bearer " + token["token"], "X-StudioFlow-Request": "1"}
    data = payload()
    # A real integration has no browser session, and cannot use the token for CRM reads.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as server:
        assert (await server.get(base + "/deals")).status_code == 401
        created = await server.post('/api/v1/integrations/leads', json=data)
        assert created.status_code == 201, created.text
        receipt = created.json()
        replay = await server.post('/api/v1/integrations/leads', json={**data, "email": "client@example.com"})
        assert replay.status_code == 200 and replay.json()["replayed"] and replay.json()["id"] == receipt["id"]
        assert (await server.post('/api/v1/integrations/leads', json={**data, "title": "Другая заявка"})).status_code == 409
    deals = (await http.get(base + "/deals")).json()
    assert len(deals) == 1 and deals[0]["source"] == "ITG" and deals[0]["amount"] == "1500.25"
    assert deals[0]["responsible_user_id"] == str(crm["user"].id)
    assert len((await http.get(base + "/clients")).json()) == 2
    links = (await http.get(base + "/deals/" + receipt["deal_id"] + "/contacts")).json()
    assert len(links) == 1 and links[0]["is_primary"] and links[0]["email"] == "client@example.com"
    assert len((await http.get(base + "/integration-leads")).json()) == 1
    audit = (await http.get(base + '/deal-audit')).json()
    assert audit['total'] == 1 and audit['items'][0]['actor_kind'] == 'INTEGRATION'
    assert audit['items'][0]['actor_id'] == token['id'] and token['token'] not in str(audit)
    assert (await http.delete(base + "/deals/" + receipt["deal_id"])).status_code == 204
    deleted = await http.post('/api/v1/integrations/leads', json=data, headers=headers)
    assert deleted.status_code == 200 and deleted.json()["deal_id"] is None
    assert (await http.get(base + "/deals")).json() == []


async def test_lead_token_expiry_revoke_roles_and_foreign_configuration(crm):
    http, base, db = crm["http"], crm["base"], crm["db"]
    token = await issue(crm)
    headers = {"Authorization": "Bearer " + token["token"]}
    assert (await http.post('/api/v1/integrations/leads', json=payload())).status_code == 401
    assert (await http.post('/api/v1/integrations/leads', json=payload(), headers={"Authorization": "Bearer wrong"})).status_code == 401
    assert (await http.post(base + "/integration-tokens", json={"name": "Foreign", "pipeline_id": str(crm["pipelines"][1].id)})).status_code == 422
    assert (await http.post(base + "/integration-tokens", json={"name": "Bad expiry", "expires_days": 366})).status_code == 422
    member = await db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm["spaces"][0].id))
    member.role = "MANAGER"
    await db.commit()
    assert (await http.get(base + "/integration-tokens")).status_code == 403
    assert (await http.get(base + "/integration-leads")).status_code == 403
    assert (await http.post(base + "/integration-tokens", json={"name": "Denied"})).status_code == 403
    assert (await http.post(base + "/integration-tokens/" + token["id"] + "/revoke")).status_code == 403
    assert (await http.post('/api/v1/integrations/leads', json=payload(), headers=headers)).status_code == 401
    member.role = "OWNER"
    await db.commit()
    stored = await db.get(IntegrationToken, UUID(token["id"]))
    stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.commit()
    assert (await http.post('/api/v1/integrations/leads', json=payload(), headers=headers)).status_code == 401
    other = await issue(crm)
    assert (await http.post(base + "/integration-tokens/" + other["id"] + "/revoke")).status_code == 200
    assert (await http.post('/api/v1/integrations/leads', json=payload(), headers={"Authorization": "Bearer " + other["token"]})).status_code == 401
    foreign = f'/api/v1/workspaces/{crm["spaces"][1].id}'
    assert (await http.get(foreign + "/integration-tokens")).status_code == 404
    assert (await http.post(foreign + "/integration-tokens/" + token["id"] + "/revoke")).status_code == 404


async def test_lead_limits_validation_quota_and_pipeline_without_open_stage(crm, monkeypatch):
    http, base = crm["http"], crm["base"]
    token = await issue(crm)
    headers = {"Authorization": "Bearer " + token["token"]}
    for data in (payload(workspace_id=str(uuid4())), payload(amount="-1"), payload(email="bad"), payload(request_key="bad"), payload(amount="NaN")):
        assert (await http.post('/api/v1/integrations/leads', json=data, headers=headers)).status_code == 422
    async def stream():
        yield b'x' * (40 * 1024)
        yield b'x' * (40 * 1024)
    assert (await http.post('/api/v1/integrations/leads', content=stream(), headers={**headers, "Content-Type": "application/json"})).status_code == 413
    assert (await http.post('/api/v1/integrations/leads', content=b'{}', headers=headers)).status_code == 415
    assert (await http.post('/api/v1/integrations/leads', json=payload(), headers={**headers, "Origin": "https://evil.example"})).status_code == 403
    assert (await http.get(base + "/deals")).json() == []
    monkeypatch.setattr(settings, "integration_lead_hour_limit", 1)
    first = payload()
    assert (await http.post('/api/v1/integrations/leads', json=first, headers=headers)).status_code == 201
    assert (await http.post('/api/v1/integrations/leads', json=first, headers=headers)).status_code == 200
    assert (await http.post('/api/v1/integrations/leads', json=payload(), headers=headers)).status_code == 429
    assert len((await http.get(base + "/deals")).json()) == 1
    await crm["db"].execute(update(PipelineStage).where(PipelineStage.pipeline_id == crm["pipelines"][0].id).values(stage_type=StageType.WON))
    await crm["db"].commit()
    assert (await http.post('/api/v1/integrations/leads', json=payload(), headers=headers)).status_code == 409


async def test_membership_revocation_removes_issuer_tokens_but_keeps_receipt(crm):
    http, base, db = crm["http"], crm["base"], crm["db"]
    token = await issue(crm)
    headers = {"Authorization": "Bearer " + token["token"]}
    created = await http.post('/api/v1/integrations/leads', json=payload(), headers=headers)
    assert created.status_code == 201
    issuer = await db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm["spaces"][0].id))
    issuer_id = str(issuer.id)
    owner = User(email=f'{uuid4()}@example.com', first_name="Other owner", password_hash=hash_password("test-password-123"))
    db.add(owner)
    await db.flush()
    db.add(WorkspaceMember(workspace_id=crm["spaces"][0].id, user_id=owner.id, role="OWNER"))
    await db.commit()
    assert (await http.post('/api/v1/auth/login', json={"email": owner.email, "password": "test-password-123"})).status_code == 200
    assert (await http.delete(base + "/members/" + issuer_id)).status_code == 204
    assert (await http.post('/api/v1/integrations/leads', json=payload(), headers=headers)).status_code == 401
    journal = (await http.get(base + "/integration-leads")).json()
    assert len(journal) == 1 and journal[0]["deal_id"] == created.json()["deal_id"]
    receipt = await db.scalar(select(IncomingLead).where(IncomingLead.id == UUID(created.json()["id"])).execution_options(populate_existing=True))
    assert receipt.token_id is None
