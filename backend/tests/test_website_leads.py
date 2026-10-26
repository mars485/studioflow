import hashlib
import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.api.v1.integrations import LeadInput
from app.core.config import settings
from app.models import Client, Contact, Deal, IncomingLead, IntegrationToken, WorkspaceMember

pytestmark = pytest.mark.asyncio
PATH = '/api/v1/integrations/website-leads'


def payload(**changes):
    return {'request_key': str(uuid4()), 'form_kind': 'audit', 'name': 'Мария', 'contact': '@maria_itg',
        'email': 'Maria@Example.com', 'website': 'https://client.example/', 'message': 'Нужен аудит',
        'source_url': 'https://itgsystem.ru/audit', 'submitted_at': '2026-10-26T12:00:00+03:00',
        'privacy_consent': True, 'audit_email_consent': True, 'policy_version': 'privacy-2026-10',
        'utm_source': 'search', 'utm_campaign': 'audit-autumn', **changes}


async def issue(crm):
    response = await crm['http'].post(crm['base'] + '/integration-tokens', json={'name': 'Website test', 'expires_days': 3})
    assert response.status_code == 201, response.text
    return response.json()


async def test_website_context_profile_and_utm_are_atomic_and_idempotent(crm):
    http, base, db = crm['http'], crm['base'], crm['db']
    token = await issue(crm)
    headers = {'Authorization': 'Bearer ' + token['token']}
    data = payload()
    created = await http.post(PATH, json=data, headers=headers)
    assert created.status_code == 201, created.text
    receipt = created.json(); context = receipt['website_context']
    assert context['contact_text'] == '@maria_itg' and context['submitted_at'] == '2026-10-26T09:00:00Z'
    assert context['privacy_consent'] is True and context['audit_email_consent'] is True
    assert context['client_type'] == 'PERSON' and context['policy_version'] == 'privacy-2026-10'
    client = (await http.get(base + '/clients/' + receipt['client_id'])).json()
    assert client['type'] == 'PERSON' and client['name'] == 'Мария'
    assert client['phone'] is None and client['email'] == 'maria@example.com' and client['website'] == data['website']
    deal = (await http.get(base + '/deals/' + receipt['deal_id'])).json()
    assert deal['title'] == 'Запрос аудита: Мария' and deal['source'] == 'ITG website / audit'
    assert '@maria_itg' in deal['description'] and data['website'] in deal['description']
    assert deal['utm_source'] == 'search' and deal['utm_campaign'] == 'audit-autumn'
    contact = (await http.get(base + '/contacts/' + deal['contact_id'])).json()
    assert contact['phone'] is None and contact['website'] == data['website'] and contact['client_ids'] == [client['id']]
    replay = await http.post(PATH, json={**data, 'email': 'maria@example.com', 'submitted_at': '2026-10-26T09:00:00Z'}, headers=headers)
    assert replay.status_code == 200 and replay.json()['id'] == receipt['id'] and replay.json()['replayed']
    assert (await db.get(IntegrationToken, UUID(token['id']))).hour_count == 1
    assert (await http.post(PATH, json={**data, 'policy_version': 'different'}, headers=headers)).status_code == 409
    journal = (await http.get(base + '/integration-leads')).json()
    assert len(journal) == 1 and journal[0]['website_context'] == context
    assert token['token'] not in str(journal)
    # A mutable CRM profile must not rewrite the original source snapshot.
    assert (await http.patch(base + '/clients/' + client['id'], json={'website': 'https://changed.example/'})).status_code == 200
    assert (await http.delete(base + '/deals/' + deal['id'])).status_code == 204
    deleted_replay = await http.post(PATH, json=data, headers=headers)
    assert deleted_replay.status_code == 200 and deleted_replay.json()['deal_id'] is None
    assert deleted_replay.json()['website_context'] == context
    assert (await http.post(base + '/integration-tokens/' + token['id'] + '/revoke')).status_code == 200
    assert (await http.post(PATH, json=data, headers=headers)).status_code == 401
    assert (await http.get(base + '/integration-leads')).json()[0]['website_context'] == context


@pytest.mark.parametrize('contact,company,expected_phone', [
    ('+7 (900) 111-22-33', 'Компания заявителя', '+7 (900) 111-22-33'),
    ('@contact_name', None, None), ('https://t.me/contact_name', None, None),
    ('123', None, None), (None, None, None),
])
async def test_contact_form_does_not_mislabel_telegram_or_invent_company(crm, contact, company, expected_phone):
    token = await issue(crm)
    data = payload(form_kind='contact', source_url='https://itgsystem.ru/contacts', contact=contact,
        company_name=company, audit_email_consent=False, website=None)
    response = await crm['http'].post(PATH, json=data, headers={'Authorization': 'Bearer ' + token['token']})
    assert response.status_code == 201, response.text
    client = await crm['db'].get(Client, UUID(response.json()['client_id']))
    assert client.type == ('COMPANY' if company else 'PERSON')
    assert client.name == (company or data['name']) and client.phone == expected_phone
    assert response.json()['website_context']['contact_text'] == contact


@pytest.mark.parametrize('changes', [
    {'privacy_consent': False}, {'privacy_consent': 'on'}, {'privacy_consent': 1},
    {'audit_email_consent': False}, {'audit_email_consent': 'true'}, {'email': None}, {'website': None},
    {'submitted_at': '2026-10-26T12:00:00'}, {'submitted_at': 1793000000}, {'submitted_at': '1793000000'},
    {'request_key': 'invalid'}, {'form_kind': 'unknown'},
    {'source_url': 'https://evil.example/audit'}, {'source_url': 'https://itgsystem.ru/audit?token=DO_NOT_ECHO'},
    {'source_url': 'https://user:DO_NOT_ECHO@itgsystem.ru/audit'}, {'website': 'javascript:DO_NOT_ECHO'},
    {'website': 'https://user:DO_NOT_ECHO@client.example/'}, {'message': 'x' * 8001},
    {'workspace_id': str(uuid4())}, {'authorization': 'DO_NOT_ECHO'},
    {'form_kind': 'contact', 'contact': None, 'email': None},
])
async def test_invalid_website_envelope_is_rejected_without_echoing_sensitive_input(crm, changes):
    token = await issue(crm)
    response = await crm['http'].post(PATH, json=payload(**changes), headers={'Authorization': 'Bearer ' + token['token']})
    assert response.status_code == 422, response.text
    assert 'DO_NOT_ECHO' not in response.text
    assert (await crm['http'].get(crm['base'] + '/deals')).json() == []
    assert (await crm['http'].get(crm['base'] + '/integration-leads')).json() == []


async def test_website_intake_keeps_legacy_hash_and_rejects_cross_contract_uuid_reuse(crm):
    http, db = crm['http'], crm['db']
    token = await issue(crm); headers = {'Authorization': 'Bearer ' + token['token']}
    data = {'request_key': str(uuid4()), 'title': 'Legacy', 'company_name': 'Legacy company'}
    created = await http.post('/api/v1/integrations/leads', json=data, headers=headers)
    assert created.status_code == 201 and created.json()['website_context'] is None
    normalized = LeadInput(**data).model_dump(mode='json'); normalized['amount'] = '0.00'
    old_digest = hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    stored = await db.get(IncomingLead, UUID(created.json()['id']))
    assert stored.request_digest == old_digest
    assert (await http.post('/api/v1/integrations/leads', json=data, headers=headers)).status_code == 200
    assert (await http.post(PATH, json=payload(request_key=data['request_key']), headers=headers)).status_code == 409


async def test_website_intake_auth_limits_scope_and_quota(crm, monkeypatch):
    http, base, db = crm['http'], crm['base'], crm['db']
    token = await issue(crm); headers = {'Authorization': 'Bearer ' + token['token']}
    assert (await http.post(PATH, json=payload())).status_code == 401
    assert (await http.post(PATH, json=payload(), headers={'Authorization': 'Bearer wrong'})).status_code == 401
    assert (await http.post(PATH, content=b'{}', headers=headers)).status_code == 415
    assert (await http.post(PATH, json=payload(), headers={**headers, 'Origin': 'https://evil.example'})).status_code == 403
    assert (await http.post(PATH, content=b'x' * (64 * 1024 + 1), headers={**headers, 'Content-Type': 'application/json'})).status_code == 413
    member = await db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm['spaces'][0].id))
    member.role = 'MANAGER'; await db.commit()
    assert (await http.post(PATH, json=payload(), headers=headers)).status_code == 401
    assert (await http.get(base + '/integration-leads')).status_code == 403
    member.role = 'OWNER'; await db.commit()
    foreign = base.replace(str(crm['spaces'][0].id), str(crm['spaces'][1].id))
    assert (await http.get(foreign + '/integration-leads')).status_code == 404
    monkeypatch.setattr(settings, 'integration_lead_hour_limit', 1)
    data = payload()
    assert (await http.post(PATH, json=data, headers=headers)).status_code == 201
    assert (await http.post(PATH, json=data, headers=headers)).status_code == 200
    assert (await http.post(PATH, json=payload(), headers=headers)).status_code == 429
    assert len((await http.get(base + '/deals')).json()) == 1


async def test_website_intake_rolls_back_all_profile_and_context_writes(crm, monkeypatch):
    import app.api.v1.integrations as integrations

    token = await issue(crm)
    workspace_id = crm['spaces'][0].id
    async def fail(*_args, **_kwargs):
        raise RuntimeError('Injected website intake failure')
    monkeypatch.setattr(integrations, 'emit_event', fail)
    with pytest.raises(RuntimeError, match='Injected website intake failure'):
        await crm['http'].post(PATH, json=payload(), headers={'Authorization': 'Bearer ' + token['token']})
    await crm['db'].rollback()
    for model in (Deal, Contact, IncomingLead):
        assert await crm['db'].scalar(select(func.count()).select_from(model)) == 0
    assert await crm['db'].scalar(select(func.count()).select_from(Client).where(Client.workspace_id == workspace_id)) == 1
