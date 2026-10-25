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
        command("alembic", "upgrade", "0010")
        task_id, reminder_id = uuid4(), uuid4()
        asyncio.run(execute(target, f"""
            INSERT INTO deal_tasks (id, workspace_id, deal_id, title, priority, status)
            SELECT '{task_id}', workspace_id, id, 'Existing task', 'HIGH', 'OPEN' FROM deals WHERE id = '{deal_id}';
            INSERT INTO task_reminders (id, workspace_id, task_id, recipient_user_id, kind, at)
            SELECT '{reminder_id}', workspace_id, '{task_id}', user_id, 'DATE', '2026-10-24T10:00:00Z' FROM workspace_members;
        """))
        command("alembic", "upgrade", "0015")
        attachment_id = uuid4()
        old_contact_id, chosen_contact_id = uuid4(), uuid4()
        asyncio.run(execute(target, f"""
            INSERT INTO deal_attachments (id, workspace_id, deal_id, filename, content_type, size_bytes, uploaded_by_name)
            SELECT '{attachment_id}', workspace_id, id, 'legacy.pdf', 'application/pdf', 2048, 'Legacy author'
            FROM deals WHERE id = '{deal_id}';
            INSERT INTO contacts (id, workspace_id, first_name)
            SELECT '{old_contact_id}', workspace_id, 'Old primary' FROM deals WHERE id = '{deal_id}';
            INSERT INTO contacts (id, workspace_id, first_name)
            SELECT '{chosen_contact_id}', workspace_id, 'Explicit primary' FROM deals WHERE id = '{deal_id}';
            UPDATE deals SET contact_id = '{old_contact_id}' WHERE id = '{deal_id}';
            INSERT INTO deal_contacts (workspace_id, deal_id, contact_id, is_primary)
            SELECT workspace_id, id, '{chosen_contact_id}', true FROM deals WHERE id = '{deal_id}';
        """))
        command("alembic", "upgrade", "head")
        command("alembic", "check")
        assert len(asyncio.run(execute(target, "SELECT id FROM deal_audit"))) == 0
        asyncio.run(execute(target, f"""
            INSERT INTO deal_audit (id, workspace_id, deal_id, actor_id, actor_kind, actor_name, action, fields)
            SELECT '{uuid4()}', workspace_id, '{deal_id}', user_id, 'USER', 'Historical actor', 'UPDATED', '["title"]'::jsonb
            FROM workspace_members LIMIT 1;
        """))
        command("alembic", "downgrade", "0024")
        assert len(asyncio.run(execute(target, f"SELECT id FROM deals WHERE id = '{deal_id}'"))) == 1
        command("alembic", "upgrade", "head")
        assert len(asyncio.run(execute(target, "SELECT id FROM deal_audit"))) == 0
        row = asyncio.run(execute(target, f"SELECT title, amount, follow_up_at FROM deals WHERE id = '{deal_id}'"))[0]
        assert row["title"] == "Existing deal" and str(row["amount"]) == "1234.56"
        assert row["follow_up_at"] is None
        legacy = asyncio.run(execute(target, f"SELECT filename, size_bytes, sha256 FROM deal_attachments WHERE id = '{attachment_id}'"))[0]
        assert legacy["filename"] == "legacy.pdf" and legacy["size_bytes"] == 2048 and legacy["sha256"] is None
        reconciled = asyncio.run(execute(target, f"SELECT contact_id, is_primary FROM deal_contacts WHERE deal_id = '{deal_id}'"))
        assert {str(item["contact_id"]) for item in reconciled} == {str(old_contact_id), str(chosen_contact_id)}
        assert [str(item["contact_id"]) for item in reconciled if item["is_primary"]] == [str(chosen_contact_id)]
        assert str(asyncio.run(execute(target, f"SELECT contact_id FROM deals WHERE id = '{deal_id}'"))[0]["contact_id"]) == str(chosen_contact_id)
        migrated = asyncio.run(execute(target, f"SELECT title, priority, deal_id FROM tasks WHERE id = '{task_id}'"))[0]
        assert migrated["title"] == "Existing task" and migrated["priority"] == "HIGH"
        assert str(migrated["deal_id"]) == str(deal_id)
        assert len(asyncio.run(execute(target, f"SELECT id FROM task_reminders WHERE id = '{reminder_id}'"))) == 1
        command("alembic", "downgrade", "0010")
        assert len(asyncio.run(execute(target, f"SELECT id FROM deal_tasks WHERE id = '{task_id}'"))) == 1
        assert len(asyncio.run(execute(target, f"SELECT id FROM task_reminders WHERE id = '{reminder_id}'"))) == 1
        command("alembic", "upgrade", "head")
        command("alembic", "downgrade", "0001")
        command("alembic", "upgrade", "head")
        assert len(asyncio.run(execute(target, f"SELECT id FROM deals WHERE id = '{deal_id}'"))) == 1
    finally:
        asyncio.run(execute(original, f'DROP DATABASE "{name}" WITH (FORCE)'))
