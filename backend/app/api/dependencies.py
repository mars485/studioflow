from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models import User, WorkspaceMember


async def current_user(db: AsyncSession = Depends(get_db)) -> User:
    # Temporary local identity. Never accept a user ID from request headers.
    if not settings.dev_auth_enabled:
        raise HTTPException(401, "Authentication is not configured")
    user = await db.get(User, UUID(settings.dev_user_id))
    if not user or not user.is_active:
        raise HTTPException(401, "Local development user is unavailable; run app.seed")
    return user


async def workspace_access(
    workspace_id: UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> UUID:
    member = await db.scalar(select(WorkspaceMember.id).where(
        WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.user_id == user.id,
    ))
    if member is None:
        raise HTTPException(404, "Workspace not found")
    return workspace_id
