import asyncio
import hashlib
import hmac
import ipaddress
import json
import socket
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from sqlalchemy import select
from app.core.config import settings
from app.models import User, Workspace, WorkspaceMember
from app.models.webhooks import WebhookDelivery, WebhookSubscription

EVENTS = ('deal.created', 'deal.stage_changed', 'task.completed')


def configured_url(label):
    value = settings.webhook_destinations.get(label, '')
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.port not in (None, 443)
                or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment
                or len(value) > 2048 or any(ord(c) < 33 for c in value)):
            raise ValueError('Invalid destination')
        host = parsed.hostname.encode('idna').decode('ascii')
    except (ValueError, UnicodeError):
        raise ValueError('INVALID_DESTINATION') from None
    return value, host


def signing_secret(subscription_id):
    if len(settings.webhook_signing_key) < 32:
        raise ValueError('SIGNING_NOT_CONFIGURED')
    return hmac.new(settings.webhook_signing_key.encode(), f'studioflow:webhook:v1:{subscription_id}'.encode(), hashlib.sha256).hexdigest()


async def emit_event(db, workspace_id, event_type, object_id, **details):
    subscriptions = (await db.scalars(select(WebhookSubscription).where(
        WebhookSubscription.workspace_id == workspace_id, WebhookSubscription.enabled.is_(True)))).all()
    event_id = uuid4()
    payload = {'version': 1, 'event_id': str(event_id), 'type': event_type, 'workspace_id': str(workspace_id),
        'occurred_at': datetime.now(timezone.utc).isoformat(), 'object_id': str(object_id),
        'data': {key: str(value) if value is not None else None for key, value in details.items()}}
    for subscription in subscriptions:
        if event_type in subscription.events:
            db.add(WebhookDelivery(workspace_id=workspace_id, subscription_id=subscription.id,
                event_id=event_id, event_type=event_type, payload=payload))


async def public_address(host):
    results = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    addresses = sorted({result[4][0] for result in results})
    if not addresses:
        raise ValueError('DNS_EMPTY')
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (not ip.is_global or ip.is_multicast or ip.is_unspecified or (isinstance(ip, ipaddress.IPv6Address)
                and (ip not in ipaddress.ip_network('2000::/3') or ip.sixtofour is not None or ip.teredo is not None))):
            raise ValueError('DESTINATION_NOT_PUBLIC')
    return addresses[0]


async def send_delivery(subscription, delivery, *, transport=None):
    # Entire DNS + connection + headers exchange is bounded; response body is never read.
    async with asyncio.timeout(10):
        value, host = configured_url(subscription.destination)
        secret = signing_secret(subscription.id)
        ip = await public_address(host)
        target = httpx.URL(value).copy_with(host=ip)
        body = json.dumps(delivery.payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
        stamp = str(int(datetime.now(timezone.utc).timestamp()))
        signature = hmac.new(secret.encode(), stamp.encode() + b'.' + body, hashlib.sha256).hexdigest()
        async with httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False, timeout=5) as client:
            request = client.build_request('POST', target, content=body, headers={
                'Host': host, 'Content-Type': 'application/json', 'X-StudioFlow-Event': str(delivery.event_id),
                'X-StudioFlow-Timestamp': stamp, 'X-StudioFlow-Signature': 'sha256=' + signature},
                extensions={'sni_hostname': host})
            response = await client.send(request, stream=True)
            try:
                return response.status_code
            finally:
                await response.aclose()


async def process_delivery(db, delivery_id, *, sender=send_delivery):
    # Workspace first, then delivery: same ordering as subscription/admin writes.
    workspace_id = await db.scalar(select(WebhookDelivery.workspace_id).where(WebhookDelivery.id == delivery_id))
    if workspace_id is None:
        return False
    locked = await db.scalar(select(Workspace.id).where(Workspace.id == workspace_id).with_for_update(skip_locked=True))
    if locked is None:
        return False
    row = await db.scalar(select(WebhookDelivery).where(WebhookDelivery.id == delivery_id,
        WebhookDelivery.workspace_id == workspace_id).with_for_update().execution_options(populate_existing=True))
    now = datetime.now(timezone.utc)
    if row is None or row.status != 'PENDING' or row.next_attempt_at > now:
        return False
    subscription = await db.get(WebhookSubscription, row.subscription_id)
    role = await db.scalar(select(WorkspaceMember.role).join(User, User.id == WorkspaceMember.user_id).where(
        WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == subscription.created_by_user_id,
        User.is_active.is_(True))) if subscription else None
    if not subscription or not subscription.enabled or role not in ('OWNER', 'ADMIN'):
        row.status, row.last_result = 'CANCELLED', 'SUBSCRIPTION_INACTIVE'
        await db.commit()
        return True
    row.attempts += 1
    try:
        status = await sender(subscription, row)
        row.last_result = f'HTTP_{status}'
        if 200 <= status < 300:
            row.status = 'SENT'
    except ValueError as error:
        # Only our bounded validation labels are stored; never URLs, bodies or exception text.
        row.last_result = str(error) if str(error) in ('INVALID_DESTINATION', 'SIGNING_NOT_CONFIGURED', 'DNS_EMPTY', 'DESTINATION_NOT_PUBLIC') else 'CONFIG_ERROR'
    except (httpx.HTTPError, OSError, TimeoutError):
        row.last_result = 'NETWORK_ERROR'
    if row.status != 'SENT':
        if row.attempts >= 5:
            row.status = 'FAILED'
        else:
            row.next_attempt_at = datetime.now(timezone.utc) + timedelta(minutes=2 ** (row.attempts - 1))
    await db.commit()
    return True
