from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import literal, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import current_user, workspace_admin
from app.api.v1.client_merge_schemas import MergePair
from app.api.v1.contact_merge_schemas import ContactMergeCreate
from app.api.v1.workspaces import lock_membership
from app.core.database import get_db
from app.models import ContactMerge, User
from app.services.client_merges import preview_out, receipt_out
from app.services.contact_merges import apply_merge, merge_snapshot

router = APIRouter(prefix='/workspaces/{workspace_id}/contact-merges', tags=['Contact merges'])


@router.post('/preview')
async def preview(data: MergePair, workspace_id: UUID = Depends(workspace_admin),
                  user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await lock_membership(db, workspace_id, user.id)
    _, _, _, snapshot = await merge_snapshot(db, workspace_id, data.source_id, data.target_id)
    return preview_out(snapshot)


@router.post('')
async def merge(data: ContactMergeCreate, workspace_id: UUID = Depends(workspace_admin),
                user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    try:
        await lock_membership(db, workspace_id, user.id)
        return await apply_merge(db, workspace_id, user, data)
    except DBAPIError as error:
        await db.rollback()
        if getattr(error.orig, 'sqlstate', None) in ('23503', '23505', '40P01', '40001'):
            raise HTTPException(409, 'Связи изменились параллельно. Обновите предпросмотр и повторите') from None
        raise


@router.get('')
async def history(target_id: UUID, workspace_id: UUID = Depends(workspace_admin),
                  db: AsyncSession = Depends(get_db), limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    lineage = select(literal(target_id).label('contact_id')).cte('contact_merge_lineage', recursive=True)
    lineage = lineage.union(select(ContactMerge.source_id).join(lineage, ContactMerge.target_id == lineage.c.contact_id)
        .where(ContactMerge.workspace_id == workspace_id))
    rows = (await db.scalars(select(ContactMerge).where(ContactMerge.workspace_id == workspace_id,
        ContactMerge.target_id.in_(select(lineage.c.contact_id))).order_by(ContactMerge.created_at.desc(), ContactMerge.id.desc())
        .limit(limit).offset(offset))).all()
    return [receipt_out(row) for row in rows]
