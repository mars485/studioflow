from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import literal, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import current_user, workspace_admin
from app.api.v1.client_merge_schemas import ClientMergeCreate, MergePair
from app.api.v1.workspaces import lock_membership
from app.core.database import get_db
from app.models import ClientMerge, User
from app.services.client_merges import apply_merge, merge_snapshot, preview_out, receipt_out

router = APIRouter(prefix='/workspaces/{workspace_id}/client-merges', tags=['Company merges'])


@router.post('/preview')
async def preview(data: MergePair, workspace_id: UUID = Depends(workspace_admin),
                  user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await lock_membership(db, workspace_id, user.id)
    _, _, snapshot = await merge_snapshot(db, workspace_id, data.source_id, data.target_id)
    return preview_out(snapshot)


@router.post('')
async def merge(data: ClientMergeCreate, workspace_id: UUID = Depends(workspace_admin),
                user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    try:
        await lock_membership(db, workspace_id, user.id)
        return await apply_merge(db, workspace_id, user, data)
    except DBAPIError as error:
        await db.rollback()
        # FK races/deadlocks must never leave a half-moved graph.
        if getattr(error.orig, 'sqlstate', None) in ('23503', '23505', '40P01', '40001'):
            raise HTTPException(409, 'Связи изменились параллельно. Обновите предпросмотр и повторите') from None
        raise


@router.get('')
async def history(target_id: UUID, workspace_id: UUID = Depends(workspace_admin),
                  db: AsyncSession = Depends(get_db), limit: int = Query(20, ge=1, le=100),
                  offset: int = Query(0, ge=0)):
    # A → B → C must keep A's original receipt discoverable from C, without rewriting history.
    lineage = select(literal(target_id).label('client_id')).cte('merge_lineage', recursive=True)
    lineage = lineage.union(select(ClientMerge.source_id).join(lineage, ClientMerge.target_id == lineage.c.client_id)
        .where(ClientMerge.workspace_id == workspace_id))
    rows = (await db.scalars(select(ClientMerge).where(ClientMerge.workspace_id == workspace_id,
        ClientMerge.target_id.in_(select(lineage.c.client_id))).order_by(ClientMerge.created_at.desc(), ClientMerge.id.desc())
        .limit(limit).offset(offset))).all()
    return [receipt_out(row) for row in rows]
