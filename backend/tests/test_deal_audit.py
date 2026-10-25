from uuid import UUID, uuid4
import pytest
from sqlalchemy import select
from app.models import WorkspaceMember
from app.models.audit import DealAudit
from app.services.audit import audit_deal, deal_snapshot
from app.models import Deal, User
from app.core.security import hash_password

pytestmark = pytest.mark.asyncio


async def test_audit_core_changes_noop_delete_filters_and_privacy(crm):
    http, base = crm['http'], crm['base']
    created = await http.post(base + '/deals', json={**crm['payload'], 'title': 'Sensitive title', 'description': 'secret body'})
    assert created.status_code == 201, created.text
    identity = created.json()['id']
    path = base + '/deals/' + identity
    assert (await http.patch(path, json={'title': 'Changed sensitive title'})).status_code == 200
    assert (await http.patch(path, json={'title': 'Changed sensitive title'})).status_code == 200
    assert (await http.patch(path, json={'start_date': '2026-02-01', 'end_date': '2026-01-01'})).status_code == 422
    assert (await http.delete(path)).status_code == 204
    response = await http.get(base + '/deal-audit', params={'deal_id': identity})
    assert response.status_code == 200
    page = response.json()
    assert page['total'] == 3
    assert {row['action'] for row in page['items']} == {'CREATED', 'UPDATED', 'DELETED'}
    changed = next(row for row in page['items'] if row['action'] == 'UPDATED')
    assert changed['fields'] == ['title']
    assert changed['actor_id'] == str(crm['user'].id) and changed['actor_kind'] == 'USER'
    assert 'Sensitive' not in response.text and 'sensitive' not in response.text and 'secret body' not in response.text
    filtered = (await http.get(base + '/deal-audit', params={'action': 'DELETED'})).json()
    assert filtered['total'] == 1 and filtered['items'][0]['deal_id'] == identity
    first = (await http.get(base + '/deal-audit', params={'limit': 1})).json()
    second = (await http.get(base + '/deal-audit', params={'limit': 1, 'offset': 1})).json()
    assert first['items'][0]['id'] != second['items'][0]['id']
    assert (await http.delete(base + '/deal-audit/' + changed['id'])).status_code == 404


async def test_audit_workspace_roles_and_transaction_rollback(crm):
    http, base, db = crm['http'], crm['base'], crm['db']
    workspace_id = crm['spaces'][0].id
    foreign = base.replace(str(workspace_id), str(crm['spaces'][1].id))
    created = (await http.post(base + '/deals', json=crm['payload'])).json()
    deal = await db.get(Deal, UUID(created['id']))
    before = deal_snapshot(deal)
    deal.title = 'Uncommitted title'
    audit_deal(db, deal, 'UPDATED', user=crm['user'], before=before)
    await db.flush()
    await db.rollback()
    assert (await http.get(base + '/deal-audit')).json()['total'] == 1
    assert (await http.get(base + '/deals/' + created['id'])).json()['title'] == created['title']
    assert (await http.get(foreign + '/deal-audit')).status_code == 404
    member = await db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id))
    member.role = 'MANAGER'; await db.commit()
    assert (await http.get(base + '/deal-audit')).status_code == 403
    assert (await db.scalars(select(DealAudit))).all()


async def test_audit_preserves_actor_after_membership_revocation(crm):
    http, base, db = crm['http'], crm['base'], crm['db']
    owner_email = crm['user'].email
    user = User(email=f'audit-{uuid4()}@example.com', first_name='Former manager', password_hash=hash_password('test-password-123'))
    db.add(user); await db.flush()
    member = WorkspaceMember(workspace_id=crm['spaces'][0].id, user_id=user.id, role='MANAGER')
    db.add(member); await db.commit()
    user_id, member_id = user.id, member.id
    assert (await http.post('/api/v1/auth/login', json={'email': user.email, 'password': 'test-password-123'})).status_code == 200
    assert (await http.post(base + '/deals', json=crm['payload'])).status_code == 201
    assert (await http.get(base + '/deal-audit')).status_code == 403
    assert (await http.post('/api/v1/auth/login', json={'email': owner_email, 'password': 'test-password-123'})).status_code == 200
    assert (await http.delete(base + '/members/' + str(member_id))).status_code == 204
    page = (await http.get(base + '/deal-audit')).json()
    assert page['total'] == 1 and page['items'][0]['actor_id'] == str(user_id)
    assert page['items'][0]['actor_name'] == 'Former manager'
