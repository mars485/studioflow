from uuid import UUID, uuid4

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import func, select

from app.api.dependencies import workspace_access, workspace_admin, workspace_member
from app.core.security import hash_password
from app.main import app
from app.models import EmployeeGroup, EmployeeGroupMember, GroupAudit, User, WorkspaceMember
from app.services.group_permissions import required_actions

pytestmark = pytest.mark.asyncio


async def add_member(crm, role='MANAGER', workspace_id=None):
    user = User(email=f'{uuid4()}@example.com', password_hash=hash_password('groups-password-123'), first_name='Group user')
    crm['db'].add(user); await crm['db'].flush()
    member = WorkspaceMember(workspace_id=workspace_id or crm['spaces'][0].id, user_id=user.id, role=role)
    crm['db'].add(member); await crm['db'].commit()
    return user, member


async def login(crm, user=None):
    user = user or crm['user']
    password = 'test-password-123' if user.id == crm['user'].id else 'groups-password-123'
    result = await crm['http'].post('/api/v1/auth/login', json={'email': user.email, 'password': password})
    assert result.status_code == 200, result.text


async def create(crm, **changes):
    response = await crm['http'].post(crm['base'] + '/groups', json={'name': 'Группа', **changes})
    assert response.status_code == 201, response.text
    return response.json()


async def test_groups_crud_versions_noop_and_transactional_audit(crm):
    http, base = crm['http'], crm['base']
    user, _ = await add_member(crm)
    group = await create(crm, description='Private description not copied to audit', user_ids=[str(user.id)], blocked_actions=['tasks.write'])
    assert group['version'] == 1 and group['user_ids'] == [str(user.id)]
    assert (await http.get(base + '/groups')).json() == [group]
    data = {key: group[key] for key in ('name', 'description', 'user_ids', 'blocked_actions')}
    unchanged = await http.put(base + '/groups/' + group['id'], json={**data, 'expected_version': 1})
    assert unchanged.status_code == 200 and unchanged.json()['version'] == 1
    changed = await http.put(base + '/groups/' + group['id'], json={**data, 'name': 'Переименованная', 'expected_version': 1})
    assert changed.status_code == 200 and changed.json()['version'] == 2
    assert (await http.put(base + '/groups/' + group['id'], json={**data, 'expected_version': 1})).status_code == 409
    assert (await http.delete(base + '/groups/' + group['id'], params={'expected_version': 1})).status_code == 409
    assert (await http.delete(base + '/groups/' + group['id'], params={'expected_version': 2})).status_code == 204
    assert (await http.get(base + '/groups')).json() == []
    audit = (await http.get(base + '/groups/audit')).json()
    assert len(audit) == 3 and {row['action'] for row in audit} == {'CREATED', 'UPDATED', 'DELETED'}
    assert all(row['group_id'] == group['id'] for row in audit)
    assert next(row['fields'] for row in audit if row['action'] == 'UPDATED') == ['name']
    assert 'Private description' not in str(audit) and user.email not in str(audit)
    assert len((await http.get(base + '/groups/audit', params={'limit': 1, 'offset': 1})).json()) == 1


async def test_groups_deny_union_preserve_reads_and_role_ceiling(crm):
    http, base = crm['http'], crm['base']
    user, _ = await add_member(crm)
    group = await create(crm, user_ids=[str(user.id), str(crm['user'].id)], blocked_actions=['crm.write'])
    second = await create(crm, name='Вторая', user_ids=[str(user.id)], blocked_actions=['tasks.write'])
    # A group cannot lock the owner out of recovery or existing business writes.
    assert (await http.post(base + '/deals', json=crm['payload'])).status_code == 201
    assert (await http.get(base + '/group-permissions')).json()['blocked_actions'] == []
    await login(crm, user)
    permissions = (await http.get(base + '/group-permissions')).json()
    assert permissions['blocked_actions'] == ['crm.write', 'tasks.write'] and not permissions['owner_exempt']
    assert (await http.get(base + '/deals')).status_code == 200
    assert (await http.post(base + '/deals', json=crm['payload'])).status_code == 403
    assert (await http.post(base + '/tasks', json={'title': 'Запрещено'})).status_code == 403
    assert (await http.post(base + '/clients', json={'name': 'Разрешённый клиент'})).status_code == 201
    assert (await http.post(base + '/invoices', json={})).status_code == 403
    assert (await http.get(base + '/groups')).status_code == 403
    assert (await http.get(base + '/groups/audit')).status_code == 403
    await login(crm)
    values = {key: group[key] for key in ('name', 'description', 'user_ids', 'blocked_actions')}
    assert (await http.put(base + '/groups/' + group['id'], json={**values, 'blocked_actions': [], 'expected_version': 1})).status_code == 200
    await login(crm, user)
    assert (await http.post(base + '/deals', json=crm['payload'])).status_code == 201
    assert (await http.post(base + '/tasks', json={'title': 'Вторая группа всё ещё запрещает'})).status_code == 403
    await login(crm)
    assert (await http.delete(base + '/groups/' + second['id'], params={'expected_version': 1})).status_code == 204
    await login(crm, user)
    assert (await http.post(base + '/tasks', json={'title': 'Снова разрешено'})).status_code == 201


async def test_group_limits_scope_validation_admin_cannot_change_policy_and_revocation(crm):
    http, base, db = crm['http'], crm['base'], crm['db']
    user, member = await add_member(crm, 'ADMIN')
    restricted_manager, restricted_membership = await add_member(crm)
    foreign, _ = await add_member(crm, workspace_id=crm['spaces'][1].id)
    assert (await http.post(base + '/groups', json={'name': 'Чужой', 'user_ids': [str(foreign.id)]})).status_code == 422
    assert (await http.post(base + '/groups', json={'name': 'Дубли', 'user_ids': [str(user.id)] * 2})).status_code == 422
    assert (await http.post(base + '/groups', json={'name': 'Эскалация', 'blocked_actions': ['finance.read']})).status_code == 422
    group = await create(crm, user_ids=[str(user.id), str(restricted_manager.id)], blocked_actions=['finance.write'])
    assert (await http.post(base + '/groups', json={'name': group['name']})).status_code == 409
    await login(crm, user)
    assert (await http.delete(base + '/members/' + str(restricted_membership.id))).status_code == 403
    assert (await http.get(base + '/groups')).status_code == 200
    assert (await http.post(base + '/groups', json={'name': 'Обход ограничений'})).status_code == 403
    data = {key: group[key] for key in ('name', 'description', 'user_ids', 'blocked_actions')}
    assert (await http.put(base + '/groups/' + group['id'], json={**data, 'blocked_actions': [], 'expected_version': 1})).status_code == 403
    assert (await http.delete(base + '/groups/' + group['id'], params={'expected_version': 1})).status_code == 403
    assert (await http.post(base + '/organizations', json={'name': 'Запрещённая'})).status_code == 403
    assert (await http.get(base + '/organizations')).status_code == 200
    await login(crm)
    other_base = base.replace(str(crm['spaces'][0].id), str(crm['spaces'][1].id))
    assert (await http.put(other_base + '/groups/' + group['id'], json={**data, 'expected_version': 1})).status_code == 404
    assert (await http.delete(base + '/members/' + str(member.id))).status_code == 204
    assert await db.scalar(select(func.count()).select_from(EmployeeGroupMember).where(EmployeeGroupMember.user_id == user.id)) == 0
    await login(crm, user)
    assert (await http.get(base + '/group-permissions')).status_code == 404


async def test_group_restrictions_cover_nested_tasks_merges_and_tokens(crm):
    http, base = crm['http'], crm['base']
    admin, _ = await add_member(crm, 'ADMIN')
    deal = (await http.post(base + '/deals', json=crm['payload'])).json()
    task = (await http.post(base + '/tasks', json={'title': 'Timer guard'})).json()
    source = (await http.post(base + '/contacts', json={'first_name': 'Source'})).json()
    target = (await http.post(base + '/contacts', json={'first_name': 'Target'})).json()
    other_client = (await http.post(base + '/clients', json={'name': 'Source company'})).json()
    contact_pair = {'source_id': source['id'], 'target_id': target['id']}
    contact_preview = (await http.post(base + '/contact-merges/preview', json=contact_pair)).json()
    client_pair = {'source_id': other_client['id'], 'target_id': str(crm['clients'][0].id)}
    client_preview = (await http.post(base + '/client-merges/preview', json=client_pair)).json()
    await login(crm, admin)
    token_response = await http.post(base + '/integration-tokens', json={'name': 'Test issuer', 'pipeline_id': str(crm['pipelines'][0].id)})
    assert token_response.status_code == 201, token_response.text
    token = token_response.json()
    await login(crm)
    await create(crm, user_ids=[str(admin.id)], blocked_actions=['tasks.write', 'finance.write', 'integrations.write'])
    await login(crm, admin)
    assert (await http.post(base + '/deals/' + deal['id'] + '/tasks', json={'title': 'Nested blocked'})).status_code == 403
    assert (await http.post(base + '/tasks/' + task['id'] + '/time-entries', json={'request_key': str(uuid4()), 'worked_on': '2026-10-26', 'minutes': 5})).status_code == 403
    assert (await http.post(base + '/tasks/' + task['id'] + '/timer', json={'request_key': str(uuid4())})).status_code == 403
    for route, pair, state in (('contact-merges', contact_pair, contact_preview), ('client-merges', client_pair, client_preview)):
        assert (await http.post(base + '/' + route + '/preview', json=pair)).status_code == 200
        response = await http.post(base + '/' + route, json={**pair, 'preview_version': state['preview_version'], 'request_key': str(uuid4()), 'confirmed': True})
        assert response.status_code == 403, response.text
    data = {'request_key': str(uuid4()), 'title': 'Blocked incoming', 'company_name': 'Blocked buyer'}
    assert (await http.post('/api/v1/integrations/leads', json=data, headers={'Authorization': 'Bearer ' + token['token']})).status_code == 403
    assert (await http.post('/api/v1/integrations/website-leads', json={}, headers={'Authorization': 'Bearer ' + token['token']})).status_code == 403


async def test_group_mutation_and_audit_rollback(crm, monkeypatch):
    http, base, db = crm['http'], crm['base'], crm['db']
    original_commit = db.commit

    async def fail():
        raise RuntimeError('Injected group transaction failure')

    monkeypatch.setattr(db, 'commit', fail)
    with pytest.raises(RuntimeError, match='Injected group transaction failure'):
        await http.post(base + '/groups', json={'name': 'Not committed'})
    await db.rollback(); monkeypatch.setattr(db, 'commit', original_commit)
    assert await db.scalar(select(func.count()).select_from(EmployeeGroup)) == 0
    assert await db.scalar(select(func.count()).select_from(GroupAudit)) == 0


async def test_every_mutating_workspace_route_has_explicit_group_classification():
    prefix = '/api/v1/workspaces/{workspace_id}'
    checked = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith(prefix) or not (route.methods - {'GET', 'HEAD', 'OPTIONS'}):
            continue
        relative = route.path[len(prefix):]
        assert required_actions(relative) is not None, route.path
        assert any(dependency.call in (workspace_access, workspace_admin, workspace_member) for dependency in route.dependant.dependencies), route.path
        checked.append(route.path)
    assert len(checked) >= 80
    assert required_actions('/future-unknown/preview') is None
    assert required_actions('/deals/id/tasks/task-id/reminders') == {'crm.write', 'tasks.write'}
