"""Operator-run bounded batch; intentionally never started by the API."""
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.webhooks import WebhookDelivery
from app.services.webhooks import process_delivery


async def main():
    async with SessionLocal() as db:
        ids = (await db.scalars(select(WebhookDelivery.id).where(WebhookDelivery.status == 'PENDING',
            WebhookDelivery.next_attempt_at <= datetime.now(timezone.utc)).order_by(WebhookDelivery.next_attempt_at).limit(20))).all()
    for delivery_id in ids:
        async with SessionLocal() as db:
            await process_delivery(db, delivery_id)


if __name__ == '__main__':
    asyncio.run(main())
