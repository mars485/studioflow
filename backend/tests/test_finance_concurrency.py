"""Real independent transactions, not the shared-savepoint API fixture."""
import asyncio
import os
import subprocess
import sys
from datetime import date
from decimal import Decimal
from uuid import uuid4

import asyncpg
import pytest
from fastapi import HTTPException
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.v1.finance import add_payment, create_invoice, invoice_out
from app.api.v1.finance_schemas import InvoiceCreate, PaymentCreate
from app.models import Client, Workspace
from app.models.finance import Invoice, Organization


@pytest.mark.asyncio
async def test_concurrent_numbering_payments_and_retry():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires disposable PostgreSQL")
    original = make_url(url)
    name = "finance_test_" + uuid4().hex
    target = original.set(database=name)
    connection = await asyncpg.connect(original.set(drivername="postgresql").render_as_string(hide_password=False))
    await connection.execute(f'CREATE DATABASE "{name}"')
    engine = create_async_engine(target, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await asyncio.to_thread(subprocess.run, [sys.executable, "-m", "alembic", "upgrade", "head"],
            env={**os.environ, "DATABASE_URL": target.render_as_string(hide_password=False)}, check=True, capture_output=True)
        async with sessions() as db:
            workspace = Workspace(name="Concurrent finance", slug=str(uuid4()))
            db.add(workspace)
            await db.flush()
            client = Client(workspace_id=workspace.id, name="Customer")
            organization = Organization(workspace_id=workspace.id, name="Seller")
            db.add_all([client, organization])
            await db.commit()
            workspace_id = workspace.id
            data = InvoiceCreate(client_id=client.id, organization_id=organization.id,
                issued_on=date(2026, 10, 24), amount=Decimal("100.25"), description="Service")

        async def create():
            async with sessions() as db:
                return await create_invoice(data, workspace_id, db)

        created = await asyncio.gather(*(create() for _ in range(8)))
        assert sorted(row["number"] for row in created) == list(range(1, 9))
        invoice_id = created[0]["id"]
        async with sessions() as db:
            invoice = await db.get(Invoice, invoice_id)
            invoice.state = "ISSUED"
            await db.commit()

        async def pay(key, amount):
            async with sessions() as db:
                try:
                    return await add_payment(invoice_id, PaymentCreate(request_key=key,
                        paid_on=date(2026, 10, 24), amount=amount), workspace_id, db)
                except HTTPException as error:
                    return error.status_code

        # Two overlapping payments cannot both spend the same balance.
        results = await asyncio.gather(pay(uuid4(), Decimal("60.00")), pay(uuid4(), Decimal("60.00")))
        assert sum(result == 422 for result in results) == 1
        # Concurrent replay of the same accepted request records only one payment.
        key = uuid4()
        replays = await asyncio.gather(*(pay(key, Decimal("40.25")) for _ in range(4)))
        assert len({row.id for row in replays}) == 1
        async with sessions() as db:
            result = await invoice_out(db, await db.get(Invoice, invoice_id))
            assert result["status"] == "PAID" and result["paid_amount"] == Decimal("100.25")
    finally:
        await engine.dispose()
        await connection.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await connection.close()
