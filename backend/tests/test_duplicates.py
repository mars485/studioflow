from uuid import uuid4
import pytest
from sqlalchemy import select
from app.models import WorkspaceMember

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize('kind,endpoint,name_field', [('client', 'clients', 'name'), ('contact', 'contacts', 'first_name')])
async def test_duplicate_candidates_normalization_reasons_pages_and_scope(crm, kind, endpoint, name_field):
    http, base = crm['http'], crm['base']
    source_response = await http.post(base + '/' + endpoint, json={name_field: 'Альфа Студия', 'phone': '+7 (900) 123-45-67', 'email': 'Owner@Example.com'})
    assert source_response.status_code == 201
    source = source_response.json()
    other_response = await http.post(base + '/' + endpoint, json={name_field: 'альфа   студия', 'phone': '79001234567', 'email': 'owner@example.com'})
    assert other_response.status_code == 201
    other = other_response.json()
    third = await http.post(base + '/' + endpoint, json={name_field: 'Иное имя', 'phone': '79001234567'})
    assert third.status_code == 201
    params = {'kind': kind, 'object_id': source['id']}
    response = await http.get(base + '/duplicate-candidates', params=params)
    assert response.status_code == 200, response.text
    page = response.json()
    assert page['total'] == 2 and page['source']['id'] == source['id']
    matching = next(row for row in page['items'] if row['id'] == other['id'])
    assert set(matching['reasons']) == {'name', 'phone', 'email'}
    first = (await http.get(base + '/duplicate-candidates', params={**params, 'limit': 1})).json()
    second = (await http.get(base + '/duplicate-candidates', params={**params, 'limit': 1, 'offset': 1})).json()
    assert first['items'] + second['items'] == page['items']
    foreign = base.replace(str(crm['spaces'][0].id), str(crm['spaces'][1].id))
    assert (await http.get(foreign + '/duplicate-candidates', params=params)).status_code == 404
    assert (await http.get(base + '/duplicate-candidates', params={**params, 'object_id': str(uuid4())})).status_code == 404
    member = await crm['db'].scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm['spaces'][0].id))
    member.role = 'MANAGER'; await crm['db'].commit()
    assert (await http.get(base + '/duplicate-candidates', params=params)).json()['total'] == 2
    # Detection is read-only; both identities and their original names remain.
    assert (await http.get(base + '/' + endpoint)).status_code == 200


async def test_duplicate_candidates_ignore_empty_fields_short_names_and_other_types(crm):
    http, base = crm['http'], crm['base']
    source = (await http.post(base + '/clients', json={'name': 'АБ'})).json()
    assert (await http.post(base + '/clients', json={'name': 'АБ'})).status_code == 201
    assert (await http.post(base + '/contacts', json={'first_name': 'АБ'})).status_code == 201
    response = await http.get(base + '/duplicate-candidates', params={'kind': 'client', 'object_id': source['id']})
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 0
    assert (await http.get(base + '/duplicate-candidates', params={'kind': 'deal', 'object_id': source['id']})).status_code == 422
