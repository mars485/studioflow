import asyncio
import os
import subprocess
import sys
from uuid import uuid4

import asyncpg
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.requests import Request

from app.api.v1.groups import GroupInput, GroupUpdate, create_group, update_group
from app.models import EmployeeGroup, User, Workspace, WorkspaceMember
from app.services.group_permissions import enforce_request_blocks


@pytest.mark.asyncio
async def test_group_version_race_and_policy_change_serialize_with_business_write():
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('Requires disposable PostgreSQL')
    original = make_url(url)
    name = 'group_test_' + uuid4().hex
    target = original.set(database=name)
    connection = await asyncpg.connect(original.set(drivername='postgresql').render_as_string(hide_password=False))
    await connection.execute(f'CREATE DATABASE "{name}"')
    engine = create_async_engine(target, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await asyncio.to_thread(subprocess.run, [sys.executable, '-m', 'alembic', 'upgrade', 'head'],
            env={**os.environ, 'DATABASE_URL': target.render_as_string(hide_password=False)}, check=True, capture_output=True)
        async with sessions() as db:
            workspace = Workspace(name='Concurrent groups', slug=str(uuid4()))
            owner = User(email=f'{uuid4()}@example.com', password_hash='not-used', first_name='Owner')
            writer = User(email=f'{uuid4()}@example.com', password_hash='not-used', first_name='Writer')
            db.add_all([workspace, owner, writer]); await db.flush()
            db.add_all([WorkspaceMember(workspace_id=workspace.id, user_id=owner.id, role='OWNER'),
                WorkspaceMember(workspace_id=workspace.id, user_id=writer.id, role='MANAGER')]); await db.commit()
            group = await create_group(GroupInput(name='Group', user_ids=[writer.id]), workspace.id, owner, db)

        async def change(label):
            async with sessions() as db:
                try:
                    return await update_group(group['id'], GroupUpdate(name=label, user_ids=[writer.id], expected_version=1), workspace.id, owner, db)
                except HTTPException as error:
                    return error.status_code

        results = await asyncio.gather(change('First'), change('Second'))
        assert sum(isinstance(row, dict) for row in results) == 1 and 409 in results
        ready = asyncio.Event()

        async def write_after_policy_lock():
            async with sessions() as db:
                member = await db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id,
                    WorkspaceMember.user_id == writer.id))
                request = Request({'type': 'http', 'method': 'POST', 'path': f'/api/v1/workspaces/{workspace.id}/tasks', 'headers': [], 'query_string': b''})
                ready.set()
                try:
                    await enforce_request_blocks(request, member, db)
                    return 200
                except HTTPException as error:
                    return error.status_code

        async with sessions() as db:
            await db.scalar(select(Workspace.id).where(Workspace.id == workspace.id).with_for_update())
            current = await db.get(EmployeeGroup, group['id'])
            pending_write = asyncio.create_task(write_after_policy_lock())
            await ready.wait()
            await update_group(current.id, GroupUpdate(name=current.name, user_ids=[writer.id], blocked_actions=['tasks.write'],
                expected_version=current.version), workspace.id, owner, db)
            assert await pending_write == 403
    finally:
        await engine.dispose()
        await connection.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await connection.close()
