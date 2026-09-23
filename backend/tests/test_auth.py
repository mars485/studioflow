import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import bootstrap
from app.core.config import settings
from app.core.security import COOKIE, hash_password, token_digest, verify_password
from app.models import User, Workspace, WorkspaceMember
from app.api.v1.workspaces import lock_membership, member_to_change
from app.models.entities import AuthSession, AuthThrottle

pytestmark = pytest.mark.asyncio
PASSWORD = "test-password-123"


async def register(http, email=None):
    response = await http.post("/api/v1/auth/register", json={
        "email": email or f"{uuid4()}@example.com", "password": PASSWORD, "first_name": "New user"})
    assert response.status_code == 201, response.text
    return response.json()


async def owner_login(crm):
    response = await crm["http"].post("/api/v1/auth/login", json={"email": crm["user"].email, "password": PASSWORD})
    assert response.status_code == 200


async def test_session_lifecycle(crm):
    http, db = crm["http"], crm["db"]
    old_cookie = http.cookies.get(COOKIE)
    assert (await http.get("/api/v1/auth/me")).json()["id"] == str(crm["user"].id)
    await owner_login(crm)
    cookie = http.cookies.get(COOKIE)
    assert cookie != old_cookie
    assert await db.get(AuthSession, token_digest(old_cookie)) is None
    assert await db.get(AuthSession, token_digest(cookie)) is not None
    response = await http.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert await db.get(AuthSession, token_digest(cookie)) is None
    http.cookies.set(COOKIE, cookie)
    assert (await http.get("/api/v1/auth/me")).status_code == 401
    assert (await http.get(crm["base"] + "/deals")).status_code == 401


async def test_registration_normalization_and_isolation(crm):
    http = crm["http"]
    email = f"New-{uuid4()}@EXAMPLE.COM"
    user = await register(http, email)
    assert user["email"] == email.lower() and "password_hash" not in user
    assert (await http.get("/api/v1/workspaces")).json() == []
    assert (await http.get(crm["base"] + "/deals")).status_code == 404
    duplicate = await http.post("/api/v1/auth/register", json={"email": email.lower(), "password": PASSWORD, "first_name": "Copy"})
    assert duplicate.status_code == 409
    result = await http.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert result.status_code == 200
    cookie = result.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/api" in cookie
    assert result.headers["cache-control"] == "no-store"
    created = await http.post("/api/v1/workspaces", json={"name": " My studio "})
    assert created.status_code == 201
    workspace = created.json()
    assert workspace["role"] == "OWNER" and workspace["name"] == "My studio"
    pipelines = (await http.get(f'/api/v1/workspaces/{workspace["id"]}/pipelines')).json()
    assert len(pipelines) == 1 and len(pipelines[0]["stages"]) == 4


async def test_bad_credentials_expiry_and_disabled_user(crm):
    http, db = crm["http"], crm["db"]
    for email, password in ((crm["user"].email, "wrong-password-123"), ("missing@example.com", PASSWORD)):
        response = await http.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert response.status_code == 401
    await db.execute(update(AuthSession).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    await db.commit()
    assert (await http.get("/api/v1/auth/me")).status_code == 401
    await owner_login(crm)
    crm["user"].is_active = False
    await db.commit()
    assert (await http.get("/api/v1/auth/me")).status_code == 401
    assert (await http.post("/api/v1/auth/login", json={"email": crm["user"].email, "password": PASSWORD})).status_code == 401


async def test_csrf_and_throttle(crm):
    http, db = crm["http"], crm["db"]
    for headers in ({"X-StudioFlow-Request": ""}, {"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"}):
        assert (await http.post("/api/v1/auth/logout", headers=headers)).status_code == 403
    assert (await http.get("/api/v1/auth/me")).status_code == 200
    assert (await http.post("/api/v1/workspaces", json={"name": "Allowed"}, headers={"Origin": "http://localhost:5173"})).status_code == 201
    await db.execute(update(AuthThrottle).values(attempts=100))
    await db.commit()
    response = await http.post("/api/v1/auth/login", json={"email": crm["user"].email, "password": PASSWORD})
    assert response.status_code == 429 and response.headers["retry-after"] == "900"


async def test_roles_revocation_and_last_owner(crm):
    http, base = crm["http"], crm["base"]
    user = await register(http)
    await owner_login(crm)
    member = await http.post(base + "/members", json={"email": user["email"], "role": "MANAGER"})
    assert member.status_code == 201
    member_id = member.json()["id"]
    assert (await http.post(base + "/members", json={"email": user["email"], "role": "MANAGER"})).status_code == 409
    members = (await http.get(base + "/members")).json()
    owner_id = next(m["id"] for m in members if m["role"] == "OWNER")
    assert (await http.delete(base + "/members/" + owner_id)).status_code == 409
    assert (await http.patch(base + "/members/" + owner_id, json={"role": "ADMIN"})).status_code == 409
    await http.post("/api/v1/auth/login", json={"email": user["email"], "password": PASSWORD})
    deal = await http.post(base + "/deals", json=crm["payload"])
    assert deal.status_code == 201
    path = base + "/deals/" + deal.json()["id"]
    assert (await http.patch(path, json={"title": "Manager edit"})).status_code == 200
    assert (await http.delete(path)).status_code == 403
    assert (await http.patch(base, json={"name": "Intrusion"})).status_code == 403
    assert (await http.post(base + "/members", json={"email": "any@example.com", "role": "OWNER"})).status_code == 403
    await owner_login(crm)
    assert (await http.patch(base + "/members/" + member_id, json={"role": "ADMIN"})).status_code == 204
    await http.post("/api/v1/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert (await http.delete(path)).status_code == 204
    assert (await http.patch(base, json={"name": "Renamed"})).status_code == 200
    assert (await http.patch(base + "/members/" + member_id, json={"role": "OWNER"})).status_code == 403
    assert (await http.post(base + "/members", json={"email": "any@example.com", "role": "ADMIN"})).status_code == 403
    await owner_login(crm)
    assert (await http.delete(base + "/members/" + member_id)).status_code == 204
    await http.post("/api/v1/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert (await http.get(base + "/deals")).status_code == 404
    assert (await http.get(base + "/members")).status_code == 404


async def test_bootstrap_preserves_user_and_membership(crm, monkeypatch):
    db, user = crm["db"], crm["user"]
    original_id = user.id
    user.email, user.password_hash = "local@studioflow.invalid", "!disabled"
    await db.commit()

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(bootstrap, "SessionLocal", session)
    monkeypatch.setattr(settings, "dev_user_id", str(original_id))
    await bootstrap.activate("Owner@example.com", "Owner", PASSWORD)
    assert user.id == original_id and user.email == "owner@example.com"
    assert verify_password(PASSWORD, user.password_hash)
    assert await db.scalar(select(WorkspaceMember).where(WorkspaceMember.user_id == original_id))
    with pytest.raises(ValueError):
        await bootstrap.activate("other@example.com", "Other", PASSWORD)
    assert (await crm["http"].post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})).status_code == 200


async def test_password_validation_and_hashing(crm):
    assert hash_password(PASSWORD) != hash_password(PASSWORD)
    assert not verify_password(PASSWORD, "!disabled")
    for data in ({"email": "bad", "password": PASSWORD}, {"email": "ok@example.com", "password": "short"}):
        assert (await crm["http"].post("/api/v1/auth/register", json={**data, "first_name": "Test"})).status_code == 422


async def test_concurrent_owner_demotions_keep_one_owner(crm):
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"], poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    workspace_id = uuid4()
    user_ids, member_ids = [uuid4(), uuid4()], [uuid4(), uuid4()]
    try:
        async with sessions() as db:
            db.add(Workspace(id=workspace_id, name="Concurrent owners", slug=str(uuid4())))
            db.add_all([User(id=id, email=f"{id}@example.com", first_name="Owner", password_hash="!disabled") for id in user_ids])
            await db.flush()
            db.add_all([WorkspaceMember(id=m, workspace_id=workspace_id, user_id=u, role="OWNER") for m, u in zip(member_ids, user_ids)])
            await db.commit()

        async def demote(index):
            async with sessions() as db:
                try:
                    await lock_membership(db, workspace_id, user_ids[index])
                    member = await member_to_change(db, workspace_id, member_ids[index], "MANAGER")
                    member.role = "MANAGER"
                    await db.commit()
                    return 204
                except HTTPException as error:
                    await db.rollback()
                    return error.status_code

        assert sorted(await asyncio.gather(demote(0), demote(1))) == [204, 409]
        async with sessions() as db:
            roles = (await db.scalars(select(WorkspaceMember.role).where(WorkspaceMember.workspace_id == workspace_id))).all()
            assert roles.count("OWNER") == 1
    finally:
        async with sessions() as db:
            await db.execute(delete(Workspace).where(Workspace.id == workspace_id))
            await db.execute(delete(User).where(User.id.in_(user_ids)))
            await db.commit()
        await engine.dispose()
