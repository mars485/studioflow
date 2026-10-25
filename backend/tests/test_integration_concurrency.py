import asyncio
import json
import os
import subprocess
import sys
from uuid import uuid4

import asyncpg
import pytest
from fastapi import HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.v1.integrations import TokenCreate, create_token, incoming_lead, lead_token
from app.core.config import settings
from app.core.security import hash_password
from app.models import Client, Deal, Pipeline, PipelineStage, User, Workspace, WorkspaceMember
from app.models.integrations import IncomingLead, IntegrationToken


@pytest.mark.asyncio
async def test_concurrent_lead_retries_and_quota_use_independent_transactions(monkeypatch):
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('Requires disposable PostgreSQL')
    original = make_url(url)
    name = 'lead_test_' + uuid4().hex
    target = original.set(database=name)
    connection = await asyncpg.connect(original.set(drivername='postgresql').render_as_string(hide_password=False))
    await connection.execute(f'CREATE DATABASE "{name}"')
    engine = create_async_engine(target, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(settings, 'integration_lead_hour_limit', 2)
    try:
        await asyncio.to_thread(subprocess.run, [sys.executable, '-m', 'alembic', 'upgrade', 'head'],
            env={**os.environ, 'DATABASE_URL': target.render_as_string(hide_password=False)}, check=True, capture_output=True)
        async with sessions() as db:
            user = User(email=f'{uuid4()}@example.com', first_name='Owner', password_hash=hash_password('test-password-123'))
            workspace = Workspace(name='Concurrent intake', slug=str(uuid4()))
            db.add_all([user, workspace])
            await db.flush()
            db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role='OWNER'))
            pipeline = Pipeline(workspace_id=workspace.id, name='Intake', is_default=True)
            db.add(pipeline)
            await db.flush()
            db.add(PipelineStage(workspace_id=workspace.id, pipeline_id=pipeline.id, name='New', position=0))
            await db.commit()
            issued = await create_token(TokenCreate(name='Website', pipeline_id=pipeline.id), workspace.id, user, db)
            secret, token_id = issued.token, issued.id

        async def intake(key):
            body = json.dumps({'request_key': str(key), 'title': 'Concurrent lead', 'company_name': 'Company', 'contact_first_name': 'Person'}).encode()
            async def receive():
                return {'type': 'http.request', 'body': body, 'more_body': False}
            request = Request({'type': 'http', 'method': 'POST', 'path': '/api/v1/integrations/leads',
                'headers': [(b'content-type', b'application/json')]}, receive=receive)
            async with sessions() as db:
                try:
                    token = await lead_token(HTTPAuthorizationCredentials(scheme='Bearer', credentials=secret), db)
                    result = await incoming_lead(request, Response(), token, db)
                    return result.deal_id
                except HTTPException as error:
                    return error.status_code

        key = uuid4()
        retries = await asyncio.gather(*(intake(key) for _ in range(6)))
        assert len(set(retries)) == 1 and retries[0] not in (401, 409, 429)
        async with sessions() as db:
            assert await db.scalar(select(func.count()).select_from(Deal)) == 1
            assert await db.scalar(select(func.count()).select_from(Client)) == 1
            assert await db.scalar(select(func.count()).select_from(IncomingLead)) == 1
            assert (await db.get(IntegrationToken, token_id)).hour_count == 1
        competing = await asyncio.gather(intake(uuid4()), intake(uuid4()))
        assert sum(result == 429 for result in competing) == 1
        async with sessions() as db:
            assert await db.scalar(select(func.count()).select_from(Deal)) == 2
            assert (await db.get(IntegrationToken, token_id)).hour_count == 2
    finally:
        await engine.dispose()
        await connection.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await connection.close()
