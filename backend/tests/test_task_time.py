from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from app.core.security import hash_password
from app.models import User, WorkspaceMember
from app.models.task_time import TaskTimeEntry

pytestmark = pytest.mark.asyncio


async def setup(crm):
    response = await crm['http'].post(crm['base'] + '/tasks', json={'title': 'Учёт времени'})
    assert response.status_code == 201, response.text
    task = response.json()
    return task, crm['base'] + '/tasks/' + task['id']


async def test_manual_time_validation_idempotency_update_and_scope(crm):
    http, base = crm['http'], crm['base']
    task, path = await setup(crm)
    url = path + '/time-entries'
    data = {'request_key': str(uuid4()), 'worked_on': '2020-01-01', 'minutes': 25, 'comment': ' Работа '}
    first = await http.post(url, json=data)
    assert first.status_code == 201, first.text
    row = first.json()
    assert row['seconds'] == 1500 and row['comment'] == 'Работа' and row['can_edit']
    assert (await http.post(url, json=data)).json()['id'] == row['id']
    assert (await http.post(url, json={**data, 'minutes': 30})).status_code == 409
    for changes in ({'minutes': 0}, {'minutes': 1.5}, {'minutes': True}, {'worked_on': '9999-01-01'}):
        assert (await http.post(url, json={**data, 'request_key': str(uuid4()), **changes})).status_code == 422
    entry = base + '/time-entries/' + row['id']
    assert (await http.patch(entry, json={'minutes': 30})).json()['seconds'] == 1800
    assert (await http.patch(entry, json={'minutes': None})).status_code == 422
    page = (await http.get(url + '?limit=1')).json()
    assert page['total_seconds'] == 1800 and len(page['items']) == 1
    foreign = base.replace(str(crm['spaces'][0].id), str(crm['spaces'][1].id))
    assert (await http.get(foreign + '/tasks/' + task['id'] + '/time-entries')).status_code == 404
    assert (await http.patch(entry.replace(base, foreign), json={'minutes': 10})).status_code == 404
    assert (await http.post(entry + '/stop')).status_code == 409
    assert (await http.delete(entry)).status_code == 204
    assert (await http.get(url)).json()['total_seconds'] == 0


async def test_timer_persists_stops_idempotently_and_completion_stops_both_apis(crm):
    http, base, db = crm['http'], crm['base'], crm['db']
    task, path = await setup(crm)
    key = {'request_key': str(uuid4())}
    started = await http.post(path + '/timer', json=key)
    assert started.status_code == 201, started.text
    row = started.json()
    assert (await http.post(path + '/timer', json=key)).json()['id'] == row['id']
    assert (await http.get(base + '/time-timer')).json()['id'] == row['id']
    assert (await http.post(path + '/timer', json={'request_key': str(uuid4())})).status_code == 409
    stored = await db.get(TaskTimeEntry, UUID(row['id']))
    stored.started_at = datetime.now(timezone.utc) - timedelta(seconds=125)
    await db.commit()
    entry = base + '/time-entries/' + row['id']
    assert (await http.delete(entry)).status_code == 409
    stopped = (await http.post(entry + '/stop')).json()
    assert 125 <= stopped['seconds'] < 130 and not stopped['is_running']
    assert (await http.post(entry + '/stop')).json()['seconds'] == stopped['seconds']
    assert (await http.patch(entry, json={'minutes': 4})).status_code == 409
    assert not (await http.post(path + '/timer', json=key)).json()['is_running']
    assert (await http.patch(entry, json={'comment': 'Сохранено'})).status_code == 200
    new = (await http.post(path + '/timer', json={'request_key': str(uuid4())})).json()
    statuses = (await http.get(base + '/task-statuses')).json()
    final = next(s for s in statuses if s['is_final'])
    assert (await http.patch(path, json={'status_id': final['id']})).status_code == 200
    assert (await http.get(base + '/time-timer')).json() is None
    assert (await db.get(TaskTimeEntry, UUID(new['id']))).stop_reason == 'TASK_COMPLETED'
    assert (await http.post(path + '/timer', json={'request_key': str(uuid4())})).status_code == 409
    deal = (await http.post(base + '/deals', json=crm['payload'])).json()
    legacy = base + '/deals/' + deal['id'] + '/tasks'
    linked = (await http.post(legacy, json={'title': 'Совместимый таймер'})).json()
    assert (await http.post(base + '/tasks/' + linked['id'] + '/timer', json={'request_key': str(uuid4())})).status_code == 201
    assert (await http.patch(legacy + '/' + linked['id'], json={'status': 'DONE'})).status_code == 200
    assert (await http.get(base + '/time-timer')).json() is None


async def test_time_permissions_and_membership_revocation_preserve_history(crm):
    http, base, db = crm['http'], crm['base'], crm['db']
    task, path = await setup(crm)
    owner_email = crm['user'].email
    owner_entry = (await http.post(path + '/time-entries', json={'request_key': str(uuid4()), 'worked_on': '2020-01-01', 'minutes': 5})).json()
    user = User(email=f'{uuid4()}@example.com', first_name='Worker', password_hash=hash_password('test-password-123'))
    db.add(user)
    await db.flush()
    member = WorkspaceMember(workspace_id=crm['spaces'][0].id, user_id=user.id, role='MANAGER')
    db.add(member)
    await db.commit()
    assert (await http.post('/api/v1/auth/login', json={'email': user.email, 'password': 'test-password-123'})).status_code == 200
    entry = base + '/time-entries/' + owner_entry['id']
    assert (await http.patch(entry, json={'minutes': 10})).status_code == 403
    assert (await http.delete(entry)).status_code == 403
    timer = (await http.post(path + '/timer', json={'request_key': str(uuid4())})).json()
    assert (await http.post('/api/v1/auth/login', json={'email': owner_email, 'password': 'test-password-123'})).status_code == 200
    assert (await http.delete(base + '/members/' + str(member.id))).status_code == 204
    page = (await http.get(path + '/time-entries')).json()
    stopped = next(r for r in page['items'] if r['id'] == timer['id'])
    assert stopped['stop_reason'] == 'MEMBERSHIP_REVOKED' and stopped['author_name'] == 'Worker' and not stopped['is_running']
    assert (await http.patch(base + '/time-entries/' + timer['id'], json={'comment': 'Проверено администратором'})).status_code == 200
