from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.models import ClientMerge, ContactClient, Deal, DealAudit, IncomingLead, Invoice, WorkspaceMember

pytestmark = pytest.mark.asyncio


async def pair(crm):
    http, base = crm['http'], crm['base']
    source = (await http.post(base + '/clients', json={'name': 'Дубль', 'email': 'duplicate@example.com',
        'phone': '+7 900 111 22 33', 'notes': 'Сохранить в истории'})).json()
    target = (await http.post(base + '/clients', json={'name': 'Основная', 'email': 'primary@example.com'})).json()
    return {'source_id': source['id'], 'target_id': target['id']}


async def payload(crm, ids, **overrides):
    preview = await crm['http'].post(crm['base'] + '/client-merges/preview', json=ids)
    assert preview.status_code == 200, preview.text
    return {**ids, 'preview_version': preview.json()['preview_version'], 'confirmed': True,
        'request_key': str(uuid4()), 'source_fields': ['phone'], **overrides}


async def test_merge_moves_all_company_references_keeps_snapshots_and_receipt(crm):
    http, base, db = crm['http'], crm['base'], crm['db']
    ids = await pair(crm)
    source_id, target_id = ids.values()
    deal = (await http.post(base + '/deals', json={**crm['payload'], 'client_id': source_id})).json()
    contact = (await http.post(base + '/contacts', json={'first_name': 'Мария', 'client_ids': [source_id, target_id]})).json()
    second_contact = (await http.post(base + '/contacts', json={'first_name': 'Иван', 'client_ids': [source_id]})).json()
    project_response = await http.post(base + '/projects', json={'title': 'Проект дубля', 'client_id': source_id})
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    task_response = await http.post(base + '/tasks', json={'title': 'Задача после слияния', 'deal_id': deal['id'], 'project_id': project['id']})
    assert task_response.status_code == 201, task_response.text
    attachment_path = base + '/deals/' + deal['id'] + '/attachments'
    attachment = await http.post(attachment_path + f'/upload?filename=merge.txt&upload_key={uuid4()}', content=b'original attachment bytes')
    assert attachment.status_code == 201, attachment.text
    organization = (await http.post(base + '/organizations', json={'name': 'Продавец'})).json()
    invoice_response = await http.post(base + '/invoices', json={'client_id': source_id, 'organization_id': organization['id'],
        'issued_on': '2026-10-26', 'amount': '1200.25', 'description': 'Услуги', 'deal_id': deal['id'], 'project_id': project['id']})
    assert invoice_response.status_code == 201, invoice_response.text
    invoice = invoice_response.json()
    invoice_path = base + '/invoices/' + invoice['id']
    assert (await http.patch(invoice_path, json={'state': 'ISSUED'})).status_code == 200
    payment_response = await http.post(invoice_path + '/payments', json={'request_key': str(uuid4()),
        'paid_on': '2026-10-26', 'amount': '100.25'})
    assert payment_response.status_code == 201, payment_response.text
    act_response = await http.post(invoice_path + '/acts', json={'issued_on': '2026-10-26'})
    assert act_response.status_code == 201, act_response.text
    signed_act = (await http.post(base + '/acts/' + act_response.json()['id'] + '/sign')).json()
    # A receipt created by the incoming-leads endpoint must also retain its identity/digest.
    lead = IncomingLead(workspace_id=crm['spaces'][0].id, request_key=uuid4(), request_digest='a' * 64,
        client_id=UUID(source_id), deal_id=UUID(deal['id']))
    db.add(lead); await db.commit()
    preview = (await http.post(base + '/client-merges/preview', json=ids)).json()
    assert preview['counts'] == {'deals': {'source': 1, 'target': 0}, 'projects': {'source': 1, 'target': 0},
        'invoices': {'source': 1, 'target': 0}, 'incoming_leads': {'source': 1, 'target': 0}, 'contacts': {'source': 2, 'target': 1}}
    data = await payload(crm, ids)
    response = await http.post(base + '/client-merges', json=data)
    assert response.status_code == 200, response.text
    receipt = response.json()
    assert receipt['snapshot']['source']['notes'] == 'Сохранить в истории'
    assert receipt['snapshot']['target']['phone'] is None and receipt['actor_name'] == 'Tester'
    assert (await http.get(base + '/clients/' + source_id)).status_code == 404
    target = (await http.get(base + '/clients/' + target_id)).json()
    assert target['name'] == 'Основная' and target['email'] == 'primary@example.com' and target['phone'] == '+7 900 111 22 33'
    assert (await http.get(base + '/deals/' + deal['id'])).json()['client_id'] == target_id
    assert (await http.get(base + '/projects/' + project['id'])).json()['client_id'] == target_id
    task = (await http.get(base + '/tasks/' + task_response.json()['id'])).json()
    assert task['deal_id'] == deal['id'] and task['project_id'] == project['id']
    assert (await http.get(attachment_path + '/' + attachment.json()['id'] + '/download')).content == b'original attachment bytes'
    current_invoice = (await http.get(base + '/invoices/' + invoice['id'])).json()
    assert current_invoice['client_id'] == target_id and current_invoice['buyer'] == invoice['buyer']
    assert current_invoice['amount'] == invoice['amount'] and current_invoice['seller'] == invoice['seller']
    assert current_invoice['paid_amount'] == '100.25' and current_invoice['status'] == 'PARTIAL'
    assert (await http.get(invoice_path + '/payments')).json() == [payment_response.json()]
    assert (await http.get(invoice_path + '/acts')).json() == [signed_act]
    for row in (contact, second_contact):
        assert (await http.get(base + '/contacts/' + row['id'])).json()['client_ids'] == [target_id]
    await db.refresh(lead)
    assert str(lead.client_id) == target_id and lead.request_digest == 'a' * 64
    assert await db.scalar(select(func.count()).select_from(ContactClient).where(ContactClient.client_id == UUID(target_id))) == 2
    audit = await db.scalar(select(DealAudit).where(DealAudit.deal_id == UUID(deal['id']), DealAudit.action == 'UPDATED'))
    assert audit.fields == ['client_id']
    # Retry succeeds even though the source no longer exists, with no second receipt/audit.
    replay = await http.post(base + '/client-merges', json=data)
    assert replay.status_code == 200 and replay.json() == receipt
    conflict = await http.post(base + '/client-merges', json={**data, 'source_fields': ['email']})
    assert conflict.status_code == 409
    history = (await http.get(base + '/client-merges', params={'target_id': target_id})).json()
    assert history == [receipt]


@pytest.mark.parametrize('change', ['profile', 'deal', 'contact'])
async def test_merge_rejects_stale_preview_without_partial_changes(crm, change):
    http, base = crm['http'], crm['base']
    ids = await pair(crm)
    data = await payload(crm, ids)
    if change == 'profile':
        assert (await http.patch(base + '/clients/' + ids['target_id'], json={'notes': 'Параллельная правка'})).status_code == 200
    elif change == 'deal':
        assert (await http.post(base + '/deals', json={**crm['payload'], 'client_id': ids['source_id']})).status_code == 201
    else:
        assert (await http.post(base + '/contacts', json={'first_name': 'Новый контакт', 'client_ids': [ids['source_id']]})).status_code == 201
    response = await http.post(base + '/client-merges', json=data)
    assert response.status_code == 409, response.text
    assert (await http.get(base + '/clients/' + ids['source_id'])).status_code == 200
    assert (await http.get(base + '/clients/' + ids['target_id'])).json()['phone'] is None
    assert (await http.get(base + '/client-merges', params={'target_id': ids['target_id']})).json() == []


async def test_merge_role_scope_validation_and_deleted_objects(crm):
    http, base, db = crm['http'], crm['base'], crm['db']
    ids = await pair(crm)
    data = await payload(crm, ids)
    for values in ({'source_id': ids['source_id'], 'target_id': ids['source_id']}, {**ids, 'source_id': 'not-uuid'}):
        assert (await http.post(base + '/client-merges/preview', json=values)).status_code == 422
    assert (await http.post(base + '/client-merges', json={**data, 'confirmed': False})).status_code == 422
    assert (await http.post(base + '/client-merges', json={**data, 'source_fields': ['type']})).status_code == 422
    assert (await http.post(base + '/client-merges', json={**data, 'source_fields': ['email', 'email']})).status_code == 422
    assert (await http.post(base + '/client-merges/preview', json={**ids, 'source_id': str(crm['clients'][1].id)})).status_code == 404
    foreign = base.replace(str(crm['spaces'][0].id), str(crm['spaces'][1].id))
    assert (await http.post(foreign + '/client-merges', json=data)).status_code == 404
    member = await db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm['spaces'][0].id))
    member.role = 'MANAGER'; await db.commit()
    assert (await http.post(base + '/client-merges/preview', json=ids)).status_code == 403
    assert (await http.post(base + '/client-merges', json=data)).status_code == 403
    assert (await http.get(base + '/client-merges', params={'target_id': ids['target_id']})).status_code == 403
    member.role = 'ADMIN'; await db.commit()
    assert (await http.delete(base + '/clients/' + ids['source_id'])).status_code == 204
    assert (await http.post(base + '/client-merges', json=data)).status_code == 404
    http.cookies.clear()
    assert (await http.post(base + '/client-merges', json=data)).status_code == 401


async def test_merge_transaction_rolls_back_after_reference_changes(crm, monkeypatch):
    http, base, db = crm['http'], crm['base'], crm['db']
    ids = await pair(crm)
    deal = (await http.post(base + '/deals', json={**crm['payload'], 'client_id': ids['source_id']})).json()
    data = await payload(crm, ids)
    original_delete = db.delete

    async def fail_delete(row):
        raise RuntimeError('Injected failure before deleting source')

    monkeypatch.setattr(db, 'delete', fail_delete)
    with pytest.raises(RuntimeError, match='Injected failure'):
        await http.post(base + '/client-merges', json=data)
    await db.rollback()
    monkeypatch.setattr(db, 'delete', original_delete)
    assert (await http.get(base + '/clients/' + ids['source_id'])).status_code == 200
    assert (await http.get(base + '/deals/' + deal['id'])).json()['client_id'] == ids['source_id']
    assert (await http.get(base + '/clients/' + ids['target_id'])).json()['phone'] is None
    assert await db.scalar(select(func.count()).select_from(ClientMerge)) == 0


async def test_merge_chain_retains_prior_history_pagination_and_scope(crm):
    http, base, db = crm['http'], crm['base'], crm['db']
    ids = await pair(crm)
    first = (await http.post(base + '/client-merges', json=await payload(crm, ids))).json()
    third = (await http.post(base + '/clients', json={'name': 'Итоговая компания', 'website': 'https://example.com'})).json()
    second_pair = {'source_id': ids['target_id'], 'target_id': third['id']}
    data = await payload(crm, second_pair, source_fields=['name', 'website'])
    second = (await http.post(base + '/client-merges', json=data)).json()
    assert (await http.get(base + '/clients/' + third['id'])).json()['website'] is None
    history = (await http.get(base + '/client-merges', params={'target_id': third['id']})).json()
    assert {row['id'] for row in history} == {first['id'], second['id']}
    assert next(row for row in history if row['id'] == first['id'])['target_id'] == ids['target_id']
    page = (await http.get(base + '/client-merges', params={'target_id': third['id'], 'limit': 1, 'offset': 1})).json()
    assert page == history[1:]
    db.add(WorkspaceMember(workspace_id=crm['spaces'][1].id, user_id=crm['user'].id, role='OWNER'))
    await db.commit()
    foreign = base.replace(str(crm['spaces'][0].id), str(crm['spaces'][1].id))
    assert (await http.get(foreign + '/client-merges', params={'target_id': third['id']})).json() == []
