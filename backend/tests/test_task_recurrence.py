from datetime import datetime, timedelta
from uuid import uuid4
import pytest

pytestmark = pytest.mark.asyncio


async def setup(crm):
    http, base = crm['http'], crm['base']
    task = (await http.post(base + '/tasks', json={'title': 'Регулярный отчёт', 'start_at': '2026-01-01T10:00:00Z',
        'due_at': '2026-01-01T12:00:00Z', 'assignee_user_id': str(crm['user'].id)})).json()
    statuses = (await http.get(base + '/task-statuses')).json()
    return task, base + '/tasks/' + task['id'], next(s['id'] for s in statuses if s['is_final'])


async def test_repeat_copies_once_and_bounds_chain(crm):
    http, base = crm['http'], crm['base']
    task, path, final = await setup(crm)
    assert (await http.get(path + '/recurrence')).json() is None
    assert (await http.post(path + '/checklist', json={'text': 'Проверить отчёт'})).status_code == 201
    item = (await http.get(path + '/checklist')).json()[0]
    assert (await http.patch(path + '/checklist/' + item['id'], json={'is_done': True})).status_code == 200
    assert (await http.put(path + '/recurrence', json={'interval_days': 7, 'remaining': 2})).status_code == 200
    completed = await http.patch(path, json={'status_id': final, 'description': 'Новое описание при завершении'})
    assert completed.status_code == 200, completed.text
    rule = (await http.get(path + '/recurrence')).json()
    next_id = rule['next_task_id']
    assert rule['processed'] and next_id
    next_path = base + '/tasks/' + next_id
    successor = (await http.get(next_path)).json()
    assert successor['description'] == 'Новое описание при завершении'
    start = datetime.fromisoformat(successor['start_at'])
    completed_at = datetime.fromisoformat(completed.json()['completed_at'])
    assert start - completed_at == timedelta(days=7)
    assert datetime.fromisoformat(successor['due_at']) - start == timedelta(hours=2)
    assert successor['assignee_user_id'] == str(crm['user'].id) and not successor['is_final']
    copied = (await http.get(next_path + '/checklist')).json()
    assert len(copied) == 1 and not copied[0]['is_done'] and copied[0]['id'] != item['id']
    assert (await http.get(next_path + '/recurrence')).json()['remaining'] == 1
    assert (await http.patch(path, json={'status_id': final})).status_code == 200
    assert (await http.patch(path, json={'status_id': task['status_id']})).status_code == 200
    assert (await http.patch(path, json={'status_id': final})).status_code == 200
    assert len((await http.get(base + '/tasks')).json()) == 2
    assert (await http.patch(next_path, json={'status_id': final})).status_code == 200
    last_id = (await http.get(next_path + '/recurrence')).json()['next_task_id']
    last_path = base + '/tasks/' + last_id
    assert (await http.get(last_path + '/recurrence')).json() is None
    assert (await http.patch(last_path, json={'status_id': final})).status_code == 200
    assert len((await http.get(base + '/tasks')).json()) == 3


async def test_recurrence_validation_disabled_child_and_workspace(crm):
    http, base = crm['http'], crm['base']
    task, path, final = await setup(crm)
    for invalid in ({'interval_days': 0, 'remaining': 1}, {'interval_days': 1, 'remaining': 366}, {'interval_days': True, 'remaining': 1}):
        assert (await http.put(path + '/recurrence', json=invalid)).status_code == 422
    rule = {'interval_days': 1, 'remaining': 1, 'enabled': False}
    assert (await http.put(path + '/recurrence', json=rule)).status_code == 200
    foreign = path.replace(str(crm['spaces'][0].id), str(crm['spaces'][1].id))
    assert (await http.get(foreign + '/recurrence')).status_code == 404
    assert (await http.put(foreign + '/recurrence', json=rule)).status_code == 404
    child = (await http.post(base + '/tasks', json={'title': 'Подзадача', 'parent_task_id': task['id']})).json()
    assert (await http.put(base + '/tasks/' + child['id'] + '/recurrence', json=rule)).status_code == 409
    assert (await http.patch(path, json={'status_id': final})).status_code == 200
    assert not (await http.get(path + '/recurrence')).json()['processed']
    assert (await http.put(path + '/recurrence', json={**rule, 'enabled': True})).status_code == 409


async def test_legacy_completion_repeats_and_archived_project_stops_chain(crm):
    http, base = crm['http'], crm['base']
    deal = (await http.post(base + '/deals', json=crm['payload'])).json()
    path = base + '/deals/' + deal['id'] + '/tasks'
    task = (await http.post(path, json={'title': 'Совместимое повторение'})).json()
    recurrence = base + '/tasks/' + task['id'] + '/recurrence'
    assert (await http.put(recurrence, json={'interval_days': 1, 'remaining': 1})).status_code == 200
    assert (await http.patch(path + '/' + task['id'], json={'status': 'DONE'})).status_code == 200
    assert (await http.get(recurrence)).json()['next_task_id']
    project = (await http.post(base + '/projects', json={'title': 'Архив', 'client_id': str(crm['clients'][0].id)})).json()
    task, general, final = await setup(crm)
    assert (await http.patch(general, json={'project_id': project['id']})).status_code == 200
    assert (await http.put(general + '/recurrence', json={'interval_days': 1, 'remaining': 1})).status_code == 200
    assert (await http.patch(base + '/projects/' + project['id'], json={'status': 'ARCHIVED'})).status_code == 200
    assert (await http.patch(general, json={'status_id': final})).status_code == 200
    stopped = (await http.get(general + '/recurrence')).json()
    assert stopped['stop_reason'] == 'PROJECT_ARCHIVED' and stopped['next_task_id'] is None
