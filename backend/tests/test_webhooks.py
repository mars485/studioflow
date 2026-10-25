import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select
from app.core.config import settings
from app.models import WorkspaceMember
from app.models.webhooks import WebhookDelivery
from app.services import webhooks

pytestmark = pytest.mark.asyncio


async def subscribe(crm, monkeypatch):
    monkeypatch.setattr(settings, 'webhook_destinations', {'n8n': 'https://hooks.example.com/events'})
    monkeypatch.setattr(settings, 'webhook_signing_key', 'test-only-signing-key-' * 3)
    response = await crm['http'].post(crm['base'] + '/webhooks', json={'destination': 'n8n', 'events': list(webhooks.EVENTS)})
    assert response.status_code == 201, response.text
    return response.json()


async def test_webhook_events_are_transactional_scoped_and_private(crm, monkeypatch):
    http, base, db = crm['http'], crm['base'], crm['db']
    subscription = await subscribe(crm, monkeypatch)
    listed = (await http.get(base + '/webhooks')).json()
    assert 'signing_secret' not in listed[0] and subscription['signing_secret'] not in json.dumps(listed)
    assert (await http.post(base + '/webhooks', json={'destination': 'n8n', 'events': ['deal.created']})).status_code == 409
    created = await http.post(base + '/deals', json=crm['payload'])
    assert created.status_code == 201
    journal = (await http.get(base + '/webhooks/deliveries/list')).json()
    assert len(journal) == 1 and journal[0]['status'] == 'PENDING' and journal[0]['attempts'] == 0
    row = await db.get(WebhookDelivery, UUID(journal[0]['id']))
    assert row.payload['object_id'] == created.json()['id']
    assert set(row.payload) == {'version', 'event_id', 'type', 'workspace_id', 'occurred_at', 'object_id', 'data'}
    stages = (await http.get(base + '/pipelines')).json()[0]['stages']
    target = next(stage for stage in stages if stage['id'] != created.json()['stage_id'])
    assert (await http.patch(base + '/deals/' + created.json()['id'], json={'stage_id': target['id']})).status_code == 200
    assert len((await http.get(base + '/webhooks/deliveries/list')).json()) == 2
    assert (await http.patch(base + '/deals/' + created.json()['id'], json={'stage_id': target['id']})).status_code == 200
    assert len((await http.get(base + '/webhooks/deliveries/list')).json()) == 2
    foreign = base.replace(str(crm['spaces'][0].id), str(crm['spaces'][1].id))
    assert (await http.get(foreign + '/webhooks')).status_code == 404
    assert (await http.post(foreign + '/webhooks/deliveries/' + journal[0]['id'] + '/retry')).status_code == 404
    member = await db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm['spaces'][0].id))
    member.role = 'MANAGER'; await db.commit()
    assert (await http.get(base + '/webhooks/destinations')).status_code == 403
    assert (await http.get(base + '/webhooks/deliveries/list')).status_code == 403
    assert (await http.patch(base + '/webhooks/' + subscription['id'], json={'enabled': False})).status_code == 403


async def test_worker_retries_failure_success_and_disabled_subscription(crm, monkeypatch):
    http, base, db = crm['http'], crm['base'], crm['db']
    subscription = await subscribe(crm, monkeypatch)
    assert (await http.post(base + '/deals', json=crm['payload'])).status_code == 201
    row = await db.scalar(select(WebhookDelivery))
    calls = []
    async def failure(sub, delivery):
        calls.append(delivery.event_id)
        return 503
    for attempt in range(5):
        row.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
        assert await webhooks.process_delivery(db, row.id, sender=failure)
        assert row.attempts == attempt + 1
        if attempt < 4:
            assert row.status == 'PENDING' and row.next_attempt_at > datetime.now(timezone.utc)
            assert not await webhooks.process_delivery(db, row.id, sender=failure)
    assert row.status == 'FAILED' and row.last_result == 'HTTP_503' and len(calls) == 5
    assert (await http.post(base + '/webhooks/deliveries/' + str(row.id) + '/retry')).status_code == 200
    async def success(sub, delivery):
        return 204
    assert await webhooks.process_delivery(db, row.id, sender=success)
    assert row.status == 'SENT'
    assert not await webhooks.process_delivery(db, row.id, sender=success)
    assert (await http.post(base + '/deals', json=crm['payload'])).status_code == 201
    assert (await http.delete(base + '/webhooks/' + subscription['id'])).status_code == 409
    assert (await http.patch(base + '/webhooks/' + subscription['id'], json={'enabled': False})).status_code == 200
    pending = (await db.scalars(select(WebhookDelivery).where(WebhookDelivery.status == 'PENDING'))).all()
    assert not pending
    assert (await http.delete(base + '/webhooks/' + subscription['id'])).status_code == 204
    assert (await http.get(base + '/webhooks/deliveries/list')).json() == []


async def test_sender_pins_public_ip_preserves_tls_host_and_signs_without_redirects(monkeypatch):
    monkeypatch.setattr(settings, 'webhook_destinations', {'n8n': 'https://hooks.example.com/events'})
    monkeypatch.setattr(settings, 'webhook_signing_key', 'test-signing-key-' * 4)
    async def public(host):
        assert host == 'hooks.example.com'
        return '93.184.216.34'
    monkeypatch.setattr(webhooks, 'public_address', public)
    subscription = SimpleNamespace(id=uuid4(), destination='n8n')
    delivery = SimpleNamespace(event_id=uuid4(), payload={'event_id': 'test', 'version': 1})
    calls = []
    async def transport(request):
        calls.append(request)
        assert request.url.host == '93.184.216.34'
        assert request.headers['host'] == 'hooks.example.com'
        assert request.extensions['sni_hostname'] == 'hooks.example.com'
        stamp = request.headers['X-StudioFlow-Timestamp']
        expected = hmac.new(webhooks.signing_secret(subscription.id).encode(), stamp.encode() + b'.' + request.content, hashlib.sha256).hexdigest()
        assert request.headers['X-StudioFlow-Signature'] == 'sha256=' + expected
        assert 'cookie' not in request.headers and 'authorization' not in request.headers
        return httpx.Response(302, headers={'Location': 'http://127.0.0.1/private'})
    assert await webhooks.send_delivery(subscription, delivery, transport=httpx.MockTransport(transport)) == 302
    assert len(calls) == 1


async def test_destination_validation_and_private_dns_are_rejected(monkeypatch):
    for value in ('http://example.com/x', 'https://user:pass@example.com', 'https://example.com:8443/x',
                  'https://example.com/x?secret=1', 'https://example.com/#x'):
        monkeypatch.setattr(settings, 'webhook_destinations', {'bad': value})
        with pytest.raises(ValueError):
            webhooks.configured_url('bad')
    loop = __import__('asyncio').get_running_loop()
    for address in ('127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', '::ffff:127.0.0.1', '64:ff9b::a00:1', '2002:7f00:1::'):
        async def lookup(*args, **kwargs):
            return [(2, 1, 6, '', (address, 443))]
        monkeypatch.setattr(loop, 'getaddrinfo', lookup)
        with pytest.raises(ValueError, match='DESTINATION_NOT_PUBLIC'):
            await webhooks.public_address('hooks.example.com')


async def test_worker_network_error_is_sanitized_and_downgraded_issuer_cancels(crm, monkeypatch):
    http, base, db = crm['http'], crm['base'], crm['db']
    await subscribe(crm, monkeypatch)
    await http.post(base + '/deals', json=crm['payload'])
    row = await db.scalar(select(WebhookDelivery))
    async def timeout(sub, delivery):
        raise TimeoutError('secret URL or response must not be stored')
    assert await webhooks.process_delivery(db, row.id, sender=timeout)
    assert row.last_result == 'NETWORK_ERROR'
    row.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    member = await db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm['spaces'][0].id))
    member.role = 'MANAGER'
    await db.commit()
    assert await webhooks.process_delivery(db, row.id, sender=timeout)
    assert row.status == 'CANCELLED' and row.attempts == 1
