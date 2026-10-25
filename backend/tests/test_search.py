import pytest
from sqlalchemy import select
from app.models import WorkspaceMember

pytestmark = pytest.mark.asyncio


async def test_search_multiple_entities_stable_pages_and_tenant_scope(crm):
    http, base = crm['http'], crm['base']
    company = (await http.post(base + '/clients', json={'name': 'Needle company'})).json()
    contact = (await http.post(base + '/contacts', json={'first_name': 'Needle contact'})).json()
    deal = (await http.post(base + '/deals', json={**crm['payload'], 'title': 'Needle deal'})).json()
    task = (await http.post(base + '/tasks', json={'title': 'Needle task'})).json()
    project = (await http.post(base + '/projects', json={'title': 'Needle project', 'client_id': company['id']})).json()
    result = await http.get(base + '/search', params={'q': 'needle'})
    assert result.status_code == 200, result.text
    data = result.json()
    assert data['total'] == 5
    expected = {('client', company['id']), ('contact', contact['id']), ('deal', deal['id']), ('task', task['id']), ('project', project['id'])}
    assert {(row['kind'], row['id']) for row in data['items']} == expected
    first = (await http.get(base + '/search', params={'q': 'needle', 'limit': 2})).json()
    second = (await http.get(base + '/search', params={'q': 'needle', 'limit': 2, 'offset': 2})).json()
    assert first['items'] + second['items'] == data['items'][:4]
    filtered = (await http.get(base + '/search', params={'q': 'needle', 'kind': 'task'})).json()
    assert filtered['total'] == 1 and filtered['items'][0]['id'] == task['id']
    foreign = base.replace(str(crm['spaces'][0].id), str(crm['spaces'][1].id))
    assert (await http.get(foreign + '/search', params={'q': 'needle'})).status_code == 404
    member = await crm['db'].scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm['spaces'][0].id))
    member.role = 'MANAGER'; await crm['db'].commit()
    assert (await http.get(base + '/search', params={'q': 'needle'})).json()['total'] == 5
    crm['db'].add(WorkspaceMember(workspace_id=crm['spaces'][1].id, user_id=crm['user'].id, role='MANAGER'))
    await crm['db'].commit()
    other_company = await http.post(foreign + '/clients', json={'name': 'Needle other workspace'})
    assert other_company.status_code == 201
    assert (await http.get(foreign + '/search', params={'q': 'needle'})).json()['total'] == 1
    assert (await http.get(base + '/search', params={'q': 'needle'})).json()['total'] == 5


async def test_search_wildcards_are_literal_and_does_not_return_description(crm):
    http, base = crm['http'], crm['base']
    title = 'literal %_\\ marker'
    task = (await http.post(base + '/tasks', json={'title': title, 'description': 'private body searched but not returned'})).json()
    for term in ('%_', '_\\'):
        result = await http.get(base + '/search', params={'q': term})
        assert result.status_code == 200, result.text
        assert result.json()['total'] == 1 and result.json()['items'][0]['id'] == task['id']
    description = (await http.get(base + '/search', params={'q': 'private body'})).json()
    assert description['total'] == 1 and 'private body' not in str(description['items'])
    assert (await http.get(base + '/search', params={'q': 'x'})).status_code == 422
    assert (await http.get(base + '/search', params={'q': '  '})).json()['total'] == 0
    assert (await http.get(base + '/search', params={'q': 'ok', 'kind': 'finance'})).status_code == 422
