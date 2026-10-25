from datetime import datetime, timezone
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import current_user, workspace_admin
from app.api.v1.integrations import admin_locked
from app.core.config import settings
from app.core.database import get_db
from app.models import User
from app.models.webhooks import WebhookDelivery, WebhookSubscription
from app.services.webhooks import configured_url, signing_secret

router = APIRouter(prefix='/workspaces/{workspace_id}/webhooks', tags=['Outgoing webhooks'])


class SubscriptionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    destination: str = Field(min_length=1, max_length=100)
    events: list[Literal['deal.created', 'deal.stage_changed', 'task.completed']] = Field(min_length=1, max_length=3)


class SubscriptionUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool


def output(row):
    return {key: getattr(row, key) for key in ('id', 'destination', 'events', 'enabled', 'created_at')}


@router.get('/destinations')
async def destinations(workspace_id: UUID = Depends(workspace_admin)):
    labels = []
    if len(settings.webhook_signing_key) >= 32:
        for label in settings.webhook_destinations:
            try:
                configured_url(label)
                if 1 <= len(label) <= 100:
                    labels.append(label)
            except ValueError:
                pass
    return {'destinations': sorted(labels), 'worker_required': True}


@router.get('')
async def subscriptions(workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(WebhookSubscription).where(WebhookSubscription.workspace_id == workspace_id)
        .order_by(WebhookSubscription.created_at, WebhookSubscription.id))).all()
    return [output(row) for row in rows]


@router.post('', status_code=201)
async def subscribe(data: SubscriptionInput, workspace_id: UUID = Depends(workspace_admin),
                    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await admin_locked(db, workspace_id, user.id)
    try:
        configured_url(data.destination)
        signing_secret(UUID(int=0))
    except ValueError:
        raise HTTPException(409, 'Оператор должен настроить разрешённый HTTPS-адрес и ключ подписей')
    exists = await db.scalar(select(WebhookSubscription.id).where(WebhookSubscription.workspace_id == workspace_id,
        WebhookSubscription.destination == data.destination))
    if exists:
        raise HTTPException(409, 'Подписка на это назначение уже существует')
    count = await db.scalar(select(func.count()).where(WebhookSubscription.workspace_id == workspace_id))
    if count >= 20:
        raise HTTPException(409, 'Не более 20 подписок на студию')
    row = WebhookSubscription(workspace_id=workspace_id, created_by_user_id=user.id,
        destination=data.destination, events=sorted(set(data.events)))
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {**output(row), 'signing_secret': signing_secret(row.id)}


@router.patch('/{subscription_id}')
async def change_subscription(subscription_id: UUID, data: SubscriptionUpdate, workspace_id: UUID = Depends(workspace_admin),
                              user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await admin_locked(db, workspace_id, user.id)
    row = await db.scalar(select(WebhookSubscription).where(WebhookSubscription.workspace_id == workspace_id,
        WebhookSubscription.id == subscription_id).with_for_update())
    if row is None:
        raise HTTPException(404, 'Подписка не найдена')
    row.enabled = data.enabled
    if not data.enabled:
        await db.execute(update(WebhookDelivery).where(WebhookDelivery.workspace_id == workspace_id,
            WebhookDelivery.subscription_id == row.id, WebhookDelivery.status == 'PENDING')
            .values(status='CANCELLED', last_result='SUBSCRIPTION_INACTIVE'))
    await db.commit()
    return output(row)


@router.get('/deliveries/list')
async def deliveries(workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db),
                     limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    rows = (await db.scalars(select(WebhookDelivery).where(WebhookDelivery.workspace_id == workspace_id)
        .order_by(WebhookDelivery.created_at.desc(), WebhookDelivery.id).limit(limit).offset(offset))).all()
    return [{key: getattr(row, key) for key in ('id', 'subscription_id', 'event_id', 'event_type', 'status', 'attempts', 'last_result', 'next_attempt_at', 'created_at')} for row in rows]


@router.delete('/{subscription_id}', status_code=204)
async def delete_subscription(subscription_id: UUID, workspace_id: UUID = Depends(workspace_admin),
                              user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await admin_locked(db, workspace_id, user.id)
    row = await db.scalar(select(WebhookSubscription).where(WebhookSubscription.workspace_id == workspace_id,
        WebhookSubscription.id == subscription_id).with_for_update())
    if row is None:
        raise HTTPException(404, 'Подписка не найдена')
    if row.enabled:
        raise HTTPException(409, 'Перед удалением отключите подписку')
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


@router.post('/deliveries/{delivery_id}/retry')
async def retry_delivery(delivery_id: UUID, workspace_id: UUID = Depends(workspace_admin),
                         user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await admin_locked(db, workspace_id, user.id)
    row = await db.scalar(select(WebhookDelivery).where(WebhookDelivery.workspace_id == workspace_id,
        WebhookDelivery.id == delivery_id).with_for_update())
    if row is None:
        raise HTTPException(404, 'Доставка не найдена')
    subscription = await db.get(WebhookSubscription, row.subscription_id)
    if row.status != 'FAILED' or not subscription.enabled:
        raise HTTPException(409, 'Повтор разрешён только для FAILED активной подписки')
    row.status, row.attempts, row.last_result = 'PENDING', 0, None
    row.next_attempt_at = datetime.now(timezone.utc)
    await db.commit()
    return {'queued': True}
