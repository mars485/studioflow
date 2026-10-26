from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update

from app.models import ContactMerge, DealAudit, DealContact, ProjectContact, WorkspaceMember

pytestmark = pytest.mark.asyncio


async def pair(crm):
    http, base = crm['http'], crm['base']
    company = (await http.post(base + '/clients', json={'name': 'Вторая компания контактов'})).json()
    source = (await http.post(base + '/contacts', json={'first_name': 'Анна', 'last_name': 'Исходная',
        'phone': '+7 900 123 45 67', 'email': 'merge@example.com', 'notes': 'Исходное описание контакта',
        'client_ids': [str(crm['clients'][0].id), company['id']]})).json()
    target = (await http.post(base + '/contacts', json={'first_name': 'Мария', 'last_name': 'Основная',
        'email': 'merge@example.com', 'client_ids': [str(crm['clients'][0].id)]})).json()
    return {'source_id': source['id'], 'target_id': target['id']}


async def payload(crm, ids, **overrides):
    preview = await crm['http'].post(crm['base'] + '/contact-merges/preview', json=ids)
    assert preview.status_code == 200, preview.text
    return {**ids, 'preview_version': preview.json()['preview_version'], 'request_key': str(uuid4()),
        'confirmed': True, 'source_fields': ['first_name', 'phone'], **overrides}


async def test_contact_merge_moves_graph_preserves_third_primary_and_history(crm):
    http, base = crm['http'], crm['base']
    ids = await pair(crm)
    source_id, target_id = ids['source_id'], ids['target_id']
    third = (await http.post(base + '/contacts', json={'first_name': 'Третий', 'client_ids': [str(crm['clients'][0].id)]})).json()
    deals = []
    for main in (source_id, target_id, third['id'], source_id):
        response = await http.post(base + '/deals', json={**crm['payload'], 'contact_id': main})
        assert response.status_code == 201, response.text
        deals.append(response.json())
    for index in (0, 1, 2):
        for contact_id in (source_id, target_id):
            if deals[index]['contact_id'] != contact_id:
                assert (await http.post(base + '/deals/' + deals[index]['id'] + '/contacts', json={'contact_id': contact_id})).status_code == 201
    projects = []
    for index in range(2):
        project_response = await http.post(base + '/projects', json={'title': f'Проект {index}', 'client_id': str(crm['clients'][0].id)})
        assert project_response.status_code == 201, project_response.text
        project = project_response.json(); projects.append(project)
        for contact_id in ((source_id, target_id) if index == 0 else (source_id,)):
            crm['db'].add(ProjectContact(workspace_id=crm['spaces'][0].id,
                project_id=UUID(project['id']), contact_id=UUID(contact_id)))
        await crm['db'].commit()
    task_response = await http.post(base + '/tasks', json={'title': 'Задача контакта', 'contact_id': source_id,
        'deal_id': deals[0]['id'], 'project_id': projects[0]['id']})
    assert task_response.status_code == 201, task_response.text
    task = task_response.json()
    data = await payload(crm, ids)
    response = await http.post(base + '/contact-merges', json=data)
    assert response.status_code == 200, response.text
    receipt = response.json()
    assert receipt['snapshot']['source']['notes'] == 'Исходное описание контакта'
    assert receipt['snapshot']['target']['first_name'] == 'Мария'
    assert (await http.get(base + '/contacts/' + source_id)).status_code == 404
    target = (await http.get(base + '/contacts/' + target_id)).json()
    assert target['first_name'] == 'Анна' and target['last_name'] == 'Основная' and target['phone'] == '+7 900 123 45 67'
    assert len(target['client_ids']) == 2
    for index, deal in enumerate(deals):
        saved = (await http.get(base + '/deals/' + deal['id'])).json()
        expected_id = third['id'] if index == 2 else target_id
        assert saved['contact_id'] == expected_id
        assert saved['contact_name'] == ('Третий' if index == 2 else 'Основная Анна')
        assert saved['amount'] == deal['amount']
        links = (await http.get(base + '/deals/' + deal['id'] + '/contacts')).json()
        assert source_id not in [row['contact_id'] for row in links]
        assert [row['contact_id'] for row in links if row['is_primary']] == [expected_id]
        assert sum(row['contact_id'] == target_id for row in links) == 1
    for project in projects:
        assert [row['contact_id'] for row in (await http.get(base + '/projects/' + project['id'] + '/contacts')).json()] == [target_id]
    saved_task = (await http.get(base + '/tasks/' + task['id'])).json()
    assert saved_task['contact_id'] == target_id and saved_task['deal_id'] == task['deal_id'] and saved_task['project_id'] == task['project_id']
    replay = await http.post(base + '/contact-merges', json=data)
    assert replay.status_code == 200 and replay.json() == receipt
    assert (await http.post(base + '/contact-merges', json={**data, 'source_fields': ['email']})).status_code == 409
    assert (await http.get(base + '/contact-merges', params={'target_id': target_id})).json() == [receipt]
    audits = (await crm['db'].scalars(select(DealAudit).where(DealAudit.action == 'UPDATED'))).all()
    assert any(row.deal_id == UUID(deals[0]['id']) and set(row.fields) == {'contact_id', 'contact_name'} for row in audits)
    assert not any(row.deal_id == UUID(deals[2]['id']) for row in audits)


@pytest.mark.parametrize('change', ['profile', 'company', 'task', 'primary'])
async def test_contact_merge_rejects_stale_preview(crm, change):
    http, base = crm['http'], crm['base']
    ids = await pair(crm)
    deal = (await http.post(base + '/deals', json={**crm['payload'], 'contact_id': ids['source_id']})).json()
    assert (await http.post(base + '/deals/' + deal['id'] + '/contacts', json={'contact_id': ids['target_id']})).status_code == 201
    data = await payload(crm, ids)
    if change == 'profile':
        assert (await http.patch(base + '/contacts/' + ids['target_id'], json={'first_name': 'Изменено'})).status_code == 200
    elif change == 'company':
        company = (await http.post(base + '/clients', json={'name': 'Новая связь'})).json()
        assert (await http.patch(base + '/contacts/' + ids['target_id'], json={'client_ids': [company['id']]})).status_code == 200
    elif change == 'task':
        assert (await http.post(base + '/tasks', json={'title': 'Новая задача', 'contact_id': ids['source_id']})).status_code == 201
    else:
        assert (await http.patch(base + '/deals/' + deal['id'] + '/contacts/' + ids['target_id'], json={'is_primary': True})).status_code == 200
    assert (await http.post(base + '/contact-merges', json=data)).status_code == 409
    assert (await http.get(base + '/contacts/' + ids['source_id'])).status_code == 200
    assert (await http.get(base + '/contact-merges', params={'target_id': ids['target_id']})).json() == []


async def test_contact_merge_scope_roles_validation_and_inconsistent_primary(crm):
    http, base, db = crm['http'], crm['base'], crm['db']
    ids = await pair(crm); data = await payload(crm, ids)
    assert (await http.post(base + '/contact-merges/preview', json={**ids, 'target_id': ids['source_id']})).status_code == 422
    assert (await http.post(base + '/contact-merges', json={**data, 'source_fields': ['name']})).status_code == 422
    assert (await http.post(base + '/contact-merges', json={**data, 'source_fields': ['phone', 'phone']})).status_code == 422
    assert (await http.post(base + '/contact-merges', json={**data, 'confirmed': False})).status_code == 422
    assert (await http.post(base + '/contact-merges/preview', json={**ids, 'source_id': str(crm['clients'][0].id)})).status_code == 404
    foreign = base.replace(str(crm['spaces'][0].id), str(crm['spaces'][1].id))
    assert (await http.post(foreign + '/contact-merges', json=data)).status_code == 404
    member = await db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm['spaces'][0].id))
    member.role = 'MANAGER'; await db.commit()
    assert (await http.post(base + '/contact-merges/preview', json=ids)).status_code == 403
    assert (await http.post(base + '/contact-merges', json=data)).status_code == 403
    assert (await http.get(base + '/contact-merges', params={'target_id': ids['target_id']})).status_code == 403
    member.role = 'ADMIN'; await db.commit()
    deal = (await http.post(base + '/deals', json={**crm['payload'], 'contact_id': ids['source_id']})).json()
    await db.execute(update(DealContact).where(DealContact.deal_id == UUID(deal['id'])).values(is_primary=False)); await db.commit()
    assert (await http.post(base + '/contact-merges/preview', json=ids)).status_code == 409
    assert (await http.post(base + '/contact-merges', json=data)).status_code == 409
    http.cookies.clear()
    assert (await http.post(base + '/contact-merges', json=data)).status_code == 401


async def test_contact_merge_rollback_and_chain_history(crm, monkeypatch):
    http, base, db = crm['http'], crm['base'], crm['db']
    ids = await pair(crm)
    task = (await http.post(base + '/tasks', json={'title': 'Не потерять задачу', 'contact_id': ids['source_id']})).json()
    data = await payload(crm, ids)
    original_delete = db.delete

    async def fail(_row):
        raise RuntimeError('Injected contact merge failure')

    monkeypatch.setattr(db, 'delete', fail)
    with pytest.raises(RuntimeError, match='Injected contact merge failure'):
        await http.post(base + '/contact-merges', json=data)
    await db.rollback(); monkeypatch.setattr(db, 'delete', original_delete)
    assert (await http.get(base + '/tasks/' + task['id'])).json()['contact_id'] == ids['source_id']
    assert await db.scalar(select(func.count()).select_from(ContactMerge)) == 0
    first = await http.post(base + '/contact-merges', json=data)
    assert first.status_code == 200, first.text
    third = (await http.post(base + '/contacts', json={'first_name': 'Итоговый'})).json()
    next_ids = {'source_id': ids['target_id'], 'target_id': third['id']}
    second = await http.post(base + '/contact-merges', json=await payload(crm, next_ids, source_fields=['first_name', 'notes']))
    assert second.status_code == 200, second.text
    rows = (await http.get(base + '/contact-merges', params={'target_id': third['id']})).json()
    assert {row['id'] for row in rows} == {first.json()['id'], second.json()['id']}
    assert (await http.get(base + '/contact-merges', params={'target_id': third['id'], 'limit': 1, 'offset': 1})).json() == rows[1:]
    assert (await http.get(base + '/tasks/' + task['id'])).json()['contact_id'] == third['id']
