from uuid import uuid4

import pytest
from sqlalchemy import select
from app.core.security import hash_password
from app.models import User, WorkspaceMember
from app.models.notifications import Notification

pytestmark = pytest.mark.asyncio


async def test_mentions_require_active_workspace_recipient_and_only_create_one_inbox_entry(crm):
    http, base = crm["http"], crm["base"]
    deal = (await http.post(base + "/deals", json=crm["payload"])).json()
    path = base + "/deals/" + deal["id"] + "/activities"
    assert (await http.post(path, json={"kind": "MENTION", "body": "Без адресата"})).status_code == 422
    assert (await http.post(path, json={"kind": "MENTION", "body": "Чужой", "recipient_user_id": str(uuid4())})).status_code == 422
    assert (await http.post(path, json={"kind": "NOTE", "body": "Не упоминание", "recipient_user_id": str(crm["user"].id)})).status_code == 422
    for kind in ("NOTE", "EVENT"):
        assert (await http.post(path, json={"kind": kind, "body": kind})).status_code == 201
    assert (await http.get(base + "/notifications")).json() == []
    created = await http.post(path, json={"kind": "MENTION", "body": "Ответьте на бриф", "recipient_user_id": str(crm["user"].id)})
    assert created.status_code == 201 and created.json()["recipient_name"] == crm["user"].first_name
    rows = (await http.get(base + "/notifications")).json()
    assert len(rows) == 1 and rows[0]["activity_id"] == created.json()["id"]
    assert rows[0]["body"] == "Ответьте на бриф" and rows[0]["read_at"] is None
    assert (await http.get(base + "/notifications/unread-count")).json() == {"count": 1}
    assert (await http.post(base + "/notifications/" + rows[0]["id"] + "/read")).status_code == 204
    read_at = (await http.get(base + "/notifications")).json()[0]["read_at"]
    assert read_at
    assert (await http.post(base + "/notifications/" + rows[0]["id"] + "/read")).status_code == 204
    assert (await http.get(base + "/notifications")).json()[0]["read_at"] == read_at
    assert (await http.get(base + "/notifications?unread_only=true")).json() == []
    assert (await http.get(base + "/notifications/unread-count")).json() == {"count": 0}


async def test_notifications_are_private_to_recipient_and_revoked_membership_removes_inbox(crm):
    http, base, db = crm["http"], crm["base"], crm["db"]
    user = User(email=f'{uuid4()}@example.com', password_hash=hash_password("test-password-123"), first_name="Recipient")
    db.add(user)
    await db.flush()
    member = WorkspaceMember(workspace_id=crm["spaces"][0].id, user_id=user.id, role="MANAGER")
    db.add(member)
    await db.commit()
    deal = (await http.post(base + "/deals", json=crm["payload"])).json()
    path = base + "/deals/" + deal["id"] + "/activities"
    for _ in range(2):
        assert (await http.post(path, json={"kind": "MENTION", "body": "Личное упоминание", "recipient_user_id": str(user.id)})).status_code == 201
    notification_id = await db.scalar(select(Notification.id).where(Notification.recipient_user_id == user.id))
    assert (await http.get(base + "/notifications")).json() == []
    assert (await http.post(base + f"/notifications/{notification_id}/read")).status_code == 404
    assert (await http.post(base + "/notifications/read-all")).status_code == 204
    assert not (await db.scalar(select(Notification).where(Notification.id == notification_id))).read_at
    assert (await http.post('/api/v1/auth/login', json={"email": user.email, "password": "test-password-123"})).status_code == 200
    assert len((await http.get(base + "/notifications")).json()) == 2
    assert (await http.get(base + "/notifications?limit=1&offset=1")).status_code == 200
    assert len((await http.get(base + "/notifications?limit=1&offset=1")).json()) == 1
    assert (await http.post(base + "/notifications/read-all")).status_code == 204
    assert (await http.get(base + "/notifications/unread-count")).json()["count"] == 0
    await db.delete(member)
    await db.commit()
    assert (await http.get(base + "/notifications")).status_code == 404
    assert await db.scalar(select(Notification.id).where(Notification.recipient_user_id == user.id)) is None
    assert (await http.post('/api/v1/auth/login', json={"email": crm["user"].email, "password": "test-password-123"})).status_code == 200
    assert len((await http.get(path)).json()) == 2  # History survived membership revocation.
    assert (await http.post(path, json={"kind": "MENTION", "body": "Уже удалён", "recipient_user_id": str(user.id)})).status_code == 422


async def test_notification_deal_cascade_and_foreign_workspace(crm):
    http, base, db = crm["http"], crm["base"], crm["db"]
    deal = (await http.post(base + "/deals", json=crm["payload"])).json()
    assert (await http.post(base + "/deals/" + deal["id"] + "/activities", json={"kind": "MENTION", "body": "Запрос", "recipient_user_id": str(crm["user"].id)})).status_code == 201
    notification = (await http.get(base + "/notifications")).json()[0]
    other = f'/api/v1/workspaces/{crm["spaces"][1].id}/notifications'
    for suffix in ("", "/unread-count"):
        assert (await http.get(other + suffix)).status_code == 404
    assert (await http.post(other + "/" + notification["id"] + "/read")).status_code == 404
    assert (await http.post(other + "/read-all")).status_code == 404
    assert (await http.delete(base + "/deals/" + deal["id"])).status_code == 204
    assert (await http.get(base + "/notifications")).json() == []
