import asyncio
import os
import subprocess
import sys
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from app.core.security import hash_password
from app.models import User, Workspace, WorkspaceMember
from app.models.webhooks import WebhookDelivery, WebhookSubscription
from app.services.webhooks import emit_event, process_delivery


@pytest.mark.asyncio
async def test_outbox_rollback_and_competing_workers_use_independent_transactions():
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('Requires disposable PostgreSQL')
    original = make_url(url)
    name = 'webhook_test_' + uuid4().hex
    target = original.set(database=name)
    connection = await asyncpg.connect(original.set(drivername='postgresql').render_as_string(hide_password=False))
    await connection.execute(f'CREATE DATABASE "{name}"')
    engine = create_async_engine(target, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await asyncio.to_thread(subprocess.run, [sys.executable, '-m', 'alembic', 'upgrade', 'head'],
            env={**os.environ, 'DATABASE_URL': target.render_as_string(hide_password=False)}, check=True, capture_output=True)
        async with sessions() as db:
            user = User(email=f'{uuid4()}@example.com', first_name='Owner', password_hash=hash_password('test-password-123'))
            space = Workspace(name='Outbox', slug=str(uuid4()))
            db.add_all([user, space]); await db.flush()
            db.add(WorkspaceMember(workspace_id=space.id, user_id=user.id, role='OWNER'))
            await db.flush()
            subscription = WebhookSubscription(workspace_id=space.id, created_by_user_id=user.id,
                destination='test', events=['deal.created'])
            db.add(subscription); await db.commit()
            workspace_id = space.id
        async with sessions() as db:
            await emit_event(db, workspace_id, 'deal.created', uuid4())
            await db.flush()
            await db.rollback()
        async with sessions() as db:
            assert (await db.scalars(select(WebhookDelivery))).all() == []
            await emit_event(db, workspace_id, 'deal.created', uuid4())
            await db.commit()
            delivery_id = await db.scalar(select(WebhookDelivery.id))
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def sender(sub, delivery):
            calls.append(delivery.event_id)
            started.set()
            await asyncio.wait_for(release.wait(), 10)
            return 204
        async def work():
            async with sessions() as db:
                return await process_delivery(db, delivery_id, sender=sender)
        first = asyncio.create_task(work())
        try:
            await asyncio.wait_for(started.wait(), 10)
            assert await asyncio.wait_for(work(), 10) is False
        finally:
            release.set()
        assert await asyncio.wait_for(first, 10) is True
        assert len(calls) == 1
        async with sessions() as db:
            row = await db.get(WebhookDelivery, delivery_id)
            assert row.status == 'SENT' and row.attempts == 1
    finally:
        await engine.dispose()
        await connection.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await connection.close()
