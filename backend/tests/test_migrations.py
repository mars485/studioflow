"""Exercise upgrade/downgrade on a separate disposable database, including legacy data."""
import asyncio
import os
import subprocess
import sys
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy.engine import make_url


def test_upgrade_preserves_existing_deal_and_seed_is_idempotent():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires disposable PostgreSQL with CREATE DATABASE permission")
    original = make_url(url)
    name = "migration_test_" + uuid4().hex
    target = original.set(database=name)
    env = {**os.environ, "DATABASE_URL": target.render_as_string(hide_password=False), "DEV_AUTH_ENABLED": "true"}

    async def execute(database_url, sql):
        connection = await asyncpg.connect(database_url.set(drivername="postgresql").render_as_string(hide_password=False))
        try:
            if sql.lstrip().upper().startswith("SELECT"):
                return await connection.fetch(sql)
            await connection.execute(sql)
        finally:
            await connection.close()

    def command(*args):
        subprocess.run([sys.executable, "-m", *args], env=env, check=True, capture_output=True, text=True)

    asyncio.run(execute(original, f'CREATE DATABASE "{name}"'))
    try:
        command("alembic", "upgrade", "0001")
        command("app.seed")
        command("app.seed")
        counts = asyncio.run(execute(target, "SELECT (SELECT count(*) FROM workspaces) AS workspaces, (SELECT count(*) FROM pipeline_stages) AS stages"))[0]
        assert counts["workspaces"] == 1 and counts["stages"] == 4
        client_id, deal_id = uuid4(), uuid4()
        asyncio.run(execute(target, f"""
            INSERT INTO clients (id, workspace_id, type, name)
            SELECT '{client_id}', id, 'COMPANY', 'Existing client' FROM workspaces;
            INSERT INTO deals (id, workspace_id, title, client_id, pipeline_id, stage_id, amount, currency)
            SELECT '{deal_id}', workspace_id, 'Existing deal', '{client_id}', pipeline_id, id, 1234.56, 'RUB'
            FROM pipeline_stages ORDER BY position LIMIT 1;
        """))
        command("alembic", "upgrade", "head")
        command("alembic", "check")
        row = asyncio.run(execute(target, f"SELECT title, amount, follow_up_at FROM deals WHERE id = '{deal_id}'"))[0]
        assert row["title"] == "Existing deal" and str(row["amount"]) == "1234.56"
        assert row["follow_up_at"] is None
        command("alembic", "downgrade", "0001")
        command("alembic", "upgrade", "head")
        assert len(asyncio.run(execute(target, f"SELECT id FROM deals WHERE id = '{deal_id}'"))) == 1
    finally:
        asyncio.run(execute(original, f'DROP DATABASE "{name}" WITH (FORCE)'))
