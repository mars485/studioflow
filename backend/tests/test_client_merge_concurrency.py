"""Profile merge concurrency uses independent committed transactions and a disposable DB."""
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

from app.api.v1.client_merge_schemas import ClientMergeCreate, MergePair
from app.api.v1.client_merges import merge, preview
from app.api.v1.contact_merge_schemas import ContactMergeCreate
from app.api.v1.contact_merges import merge as merge_contact, preview as preview_contact
from app.models import Client, ClientMerge, Contact, ContactMerge, Deal, DealContact, Pipeline, PipelineStage, User, Workspace, WorkspaceMember


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['client', 'contact'])
async def test_concurrent_merge_replays_and_membership_recheck(kind):
    model, receipt_model, schema, run_merge, run_preview, name_field = (
        (Client, ClientMerge, ClientMergeCreate, merge, preview, 'name') if kind == 'client' else
        (Contact, ContactMerge, ContactMergeCreate, merge_contact, preview_contact, 'first_name'))
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('Requires disposable PostgreSQL')
    original = make_url(url)
    name = 'client_merge_test_' + uuid4().hex
    target = original.set(database=name)
    connection = await asyncpg.connect(original.set(drivername='postgresql').render_as_string(hide_password=False))
    await connection.execute(f'CREATE DATABASE "{name}"')
    engine = create_async_engine(target, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await asyncio.to_thread(subprocess.run, [sys.executable, '-m', 'alembic', 'upgrade', 'head'],
            env={**os.environ, 'DATABASE_URL': target.render_as_string(hide_password=False)}, check=True, capture_output=True)
        async with sessions() as db:
            workspace = Workspace(name='Merge concurrency', slug=str(uuid4()))
            user = User(email=f'{uuid4()}@example.com', password_hash='unused-in-direct-route-test', first_name='Actor')
            db.add_all([workspace, user]); await db.flush()
            member = WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role='OWNER')
            source = model(workspace_id=workspace.id, **{name_field: 'Source'}, phone='123456789')
            destination = model(workspace_id=workspace.id, **{name_field: 'Destination'})
            db.add_all([member, source, destination]); await db.commit()
            workspace_id = workspace.id
            ids = MergePair(source_id=source.id, target_id=destination.id)
            if kind == 'contact':
                company = Client(workspace_id=workspace.id, name='Contact graph company')
                pipeline = Pipeline(workspace_id=workspace.id, name='Contact graph pipeline')
                db.add_all([company, pipeline]); await db.flush()
                stage = PipelineStage(workspace_id=workspace.id, pipeline_id=pipeline.id, name='Open', position=0)
                db.add(stage); await db.flush()
                deal = Deal(workspace_id=workspace.id, title='Concurrent contact graph', client_id=company.id,
                    pipeline_id=pipeline.id, stage_id=stage.id, contact_id=source.id, contact_name='Source')
                db.add(deal); await db.flush()
                db.add_all([DealContact(workspace_id=workspace.id, deal_id=deal.id, contact_id=source.id, is_primary=True),
                    DealContact(workspace_id=workspace.id, deal_id=deal.id, contact_id=destination.id, is_primary=False)])
                await db.commit()
        async with sessions() as db:
            state = await run_preview(ids, workspace_id, user, db)
        data = schema(**ids.model_dump(), preview_version=state['preview_version'], request_key=uuid4(),
            confirmed=True, source_fields=['phone'])

        async def run(values):
            async with sessions() as db:
                try:
                    return await run_merge(values, workspace_id, user, db)
                except HTTPException as error:
                    return error.status_code

        results = await asyncio.gather(*(run(data) for _ in range(4)))
        assert all(isinstance(row, dict) for row in results), results
        assert len({row['id'] for row in results}) == 1
        async with sessions() as db:
            assert await db.scalar(select(func.count()).select_from(receipt_model)) == 1
            assert await db.get(model, source.id) is None
            assert (await db.get(model, destination.id)).phone == '123456789'
            if kind == 'contact':
                assert (await db.get(Deal, deal.id)).contact_id == destination.id
                links = (await db.scalars(select(DealContact).where(DealContact.deal_id == deal.id))).all()
                assert len(links) == 1 and links[0].contact_id == destination.id and links[0].is_primary
        # Another operation cannot reuse a completed request key with a different choice.
        assert await run(data.model_copy(update={'source_fields': ['email']})) == 409

        async with sessions() as db:
            new_source = model(workspace_id=workspace_id, **{name_field: 'Fresh source'})
            db.add(new_source); await db.commit()
        async with sessions() as db:
            fresh_pair = MergePair(source_id=new_source.id, target_id=destination.id)
            fresh = await run_preview(fresh_pair, workspace_id, user, db)
        fresh_data = schema(**fresh_pair.model_dump(), preview_version=fresh['preview_version'], request_key=uuid4(),
            confirmed=True)
        competing = fresh_data.model_copy(update={'request_key': uuid4()})
        results = await asyncio.gather(run(fresh_data), run(competing))
        assert sum(isinstance(row, dict) for row in results) == 1 and 404 in results

        # A stale ORM membership loaded before revocation is not authorization to merge.
        async with sessions() as stale_db:
            stale_member = await stale_db.get(WorkspaceMember, member.id)
            assert stale_member.role == 'OWNER'
            async with sessions() as db:
                current = await db.get(WorkspaceMember, member.id)
                current.role = 'MANAGER'; await db.commit()
            with pytest.raises(HTTPException) as denied:
                await run_merge(data, workspace_id, user, stale_db)
            assert denied.value.status_code == 403
    finally:
        await engine.dispose()
        await connection.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await connection.close()
