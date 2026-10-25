from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import current_user, workspace_access
from app.core.database import get_db
from app.models import Deal, DealActivity, User
from app.models.notifications import Notification

router = APIRouter(prefix="/workspaces/{workspace_id}/notifications", tags=["Notifications"])


class NotificationOut(BaseModel):
    id: UUID
    workspace_id: UUID
    activity_id: UUID
    deal_id: UUID
    deal_title: str
    body: str
    author_name: str
    read_at: datetime | None
    created_at: datetime


@router.get("", response_model=list[NotificationOut])
async def notifications(workspace_id: UUID = Depends(workspace_access), user: User = Depends(current_user),
                        db: AsyncSession = Depends(get_db), unread_only: bool = False,
                        limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    query = select(Notification, DealActivity, Deal).join(DealActivity,
        (DealActivity.workspace_id == Notification.workspace_id) & (DealActivity.id == Notification.activity_id))
    query = query.join(Deal, (Deal.workspace_id == DealActivity.workspace_id) & (Deal.id == DealActivity.deal_id)).where(
        Notification.workspace_id == workspace_id, Notification.recipient_user_id == user.id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    rows = (await db.execute(query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).offset(offset))).all()
    return [NotificationOut(id=n.id, workspace_id=n.workspace_id, activity_id=a.id, deal_id=d.id,
        deal_title=d.title, body=a.body, author_name=a.author_name, read_at=n.read_at, created_at=n.created_at) for n, a, d in rows]


@router.get("/unread-count")
async def unread_count(workspace_id: UUID = Depends(workspace_access), user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    count = await db.scalar(select(func.count()).where(Notification.workspace_id == workspace_id,
        Notification.recipient_user_id == user.id, Notification.read_at.is_(None)))
    return {"count": count}


@router.post("/read-all", status_code=204)
async def read_all(workspace_id: UUID = Depends(workspace_access), user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(update(Notification).where(Notification.workspace_id == workspace_id,
        Notification.recipient_user_id == user.id, Notification.read_at.is_(None)).values(read_at=datetime.now(timezone.utc)))
    await db.commit()
    return Response(status_code=204)


@router.post("/{notification_id}/read", status_code=204)
async def read_notification(notification_id: UUID, workspace_id: UUID = Depends(workspace_access),
                            user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(Notification).where(Notification.id == notification_id,
        Notification.workspace_id == workspace_id, Notification.recipient_user_id == user.id).with_for_update())
    if row is None:
        raise HTTPException(404, "Уведомление не найдено")
    row.read_at = row.read_at or datetime.now(timezone.utc)
    await db.commit()
    return Response(status_code=204)
