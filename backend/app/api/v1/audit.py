from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import workspace_admin
from app.core.database import get_db
from app.models.audit import DealAudit

router = APIRouter(prefix='/workspaces/{workspace_id}/deal-audit', tags=['Deal audit'])


@router.get('')
async def deal_audit(workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db),
                     deal_id: UUID | None = None, action: Literal['CREATED', 'UPDATED', 'DELETED'] | None = None,
                     limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    scope = [DealAudit.workspace_id == workspace_id]
    if deal_id is not None:
        scope.append(DealAudit.deal_id == deal_id)
    if action is not None:
        scope.append(DealAudit.action == action)
    total = await db.scalar(select(func.count()).select_from(DealAudit).where(*scope))
    rows = (await db.scalars(select(DealAudit).where(*scope).order_by(
        DealAudit.created_at.desc(), DealAudit.id.desc()).limit(limit).offset(offset))).all()
    return {'total': total, 'items': [{key: getattr(row, key) for key in (
        'id', 'deal_id', 'actor_id', 'actor_kind', 'actor_name', 'action', 'fields', 'created_at')} for row in rows]}
