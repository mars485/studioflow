from uuid import UUID
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import COOKIE, token_digest
from app.models.entities import AuthSession
from app.core.database import get_db
from app.models import User, WorkspaceMember


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE)
    if not token or len(token) > 256:
        raise HTTPException(401, "Войдите в аккаунт")
    user = await db.scalar(select(User).join(AuthSession, AuthSession.user_id == User.id).where(
        AuthSession.token_hash == token_digest(token),
        AuthSession.expires_at > datetime.now(timezone.utc), User.is_active.is_(True)))
    if user is None:
        raise HTTPException(401, "Сессия завершена. Войдите снова")
    return user


async def workspace_member(
    workspace_id: UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMember:
    member = await db.scalar(select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.user_id == user.id,
    ))
    if member is None:
        raise HTTPException(404, "Workspace not found")
    return member


async def workspace_access(member: WorkspaceMember = Depends(workspace_member)) -> UUID:
    return member.workspace_id


async def workspace_admin(member: WorkspaceMember = Depends(workspace_member)) -> UUID:
    if member.role not in ("OWNER", "ADMIN"):
        raise HTTPException(403, "Требуется роль администратора или владельца")
    return member.workspace_id
