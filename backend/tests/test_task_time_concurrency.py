import asyncio
import os
import subprocess
import sys
from uuid import uuid4

import asyncpg
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from app.api.v1.task_time import TimerInput, create
from app.api.v1.crm import update_task
from app.api.v1.schemas import TaskUpdate
from app.core.security import hash_password
from app.models import Task, TaskStatus, User, Workspace, WorkspaceMember
from app.models.task_time import TaskTimeEntry
from app.models.task_recurrence import TaskRecurrence


@pytest.mark.asyncio
async def test_independent_timer_starts_serialize_and_retries_do_not_duplicate():
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('Requires disposable PostgreSQL')
    original = make_url(url)
    name = 'time_test_' + uuid4().hex
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
            space = Workspace(name='Timers', slug=str(uuid4()))
            db.add_all([user, space]); await db.flush()
            db.add(WorkspaceMember(workspace_id=space.id, user_id=user.id, role='OWNER'))
            status = TaskStatus(workspace_id=space.id, name='Open', position=0, is_final=False)
            db.add(status); await db.flush()
            task = Task(workspace_id=space.id, status_id=status.id, title='Concurrent work')
            db.add(task); await db.commit()
            user_id, workspace_id, task_id = user.id, space.id, task.id

        async def start(key):
            async with sessions() as db:
                user = await db.get(User, user_id)
                try:
                    return (await create(db, workspace_id, task_id, TimerInput(request_key=key), user, True))['id']
                except HTTPException as error:
                    return error.status_code

        key = uuid4()
        results = await asyncio.wait_for(asyncio.gather(*(start(key) for _ in range(6))), 15)
        assert len(set(results)) == 1 and results[0] != 409
        competing = await asyncio.wait_for(asyncio.gather(start(uuid4()), start(uuid4())), 15)
        assert competing == [409, 409]
        async with sessions() as db:
            assert await db.scalar(select(func.count()).select_from(TaskTimeEntry)) == 1
            final = TaskStatus(workspace_id=workspace_id, name='Done', position=1, is_final=True)
            db.add(final)
            db.add(TaskRecurrence(workspace_id=workspace_id, task_id=task_id, interval_days=7, remaining=1))
            await db.commit()
            final_id = final.id

        async def complete():
            async with sessions() as db:
                user = await db.get(User, user_id)
                await update_task(task_id, TaskUpdate(status_id=final_id), workspace_id, user, db)

        await asyncio.wait_for(asyncio.gather(*(complete() for _ in range(5))), 15)
        async with sessions() as db:
            assert await db.scalar(select(func.count()).select_from(Task)) == 2
            rule = await db.get(TaskRecurrence, task_id)
            assert rule.processed and rule.next_task_id is not None
            time = await db.scalar(select(TaskTimeEntry))
            assert time.ended_at is not None and time.stop_reason == 'TASK_COMPLETED'
    finally:
        await engine.dispose()
        await connection.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await connection.close()
