import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import current_user, workspace_access, workspace_admin
from app.api.v1.schemas import WorkspaceOut
from app.core.database import get_db
from app.models import Pipeline, PipelineStage, User, Workspace, WorkspaceMember
from app.models.entities import StageType

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])
Role = Literal["OWNER", "ADMIN", "MANAGER"]


class WorkspaceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class MemberRole(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role


class MemberInput(MemberRole):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return value.lower()


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    first_name: str
    role: Role


def workspace_out(workspace, role):
    return WorkspaceOut(id=workspace.id, name=workspace.name, currency=workspace.currency,
                        timezone=workspace.timezone, role=role)


@router.get("", response_model=list[WorkspaceOut])
async def list_workspaces(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Workspace, WorkspaceMember.role).join(WorkspaceMember).where(
        WorkspaceMember.user_id == user.id).order_by(Workspace.name, Workspace.id))).all()
    return [workspace_out(workspace, role) for workspace, role in rows]


@router.post("", response_model=WorkspaceOut, status_code=201)
async def create_workspace(data: WorkspaceInput, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    workspace = Workspace(name=data.name, slug=str(uuid.uuid4()))
    db.add(workspace)
    await db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="OWNER"))
    pipeline = Pipeline(workspace_id=workspace.id, name="Продажи", is_default=True)
    db.add(pipeline)
    await db.flush()
    for position, (name, stage_type) in enumerate([
        ("Новый лид", StageType.OPEN), ("В работе", StageType.OPEN),
        ("Успешно", StageType.WON), ("Отказ", StageType.LOST),
    ]):
        db.add(PipelineStage(workspace_id=workspace.id, pipeline_id=pipeline.id,
                             name=name, position=position, stage_type=stage_type))
    await db.commit()
    return workspace_out(workspace, "OWNER")


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
async def rename_workspace(data: WorkspaceInput, workspace_id: uuid.UUID = Depends(workspace_admin),
                           user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    workspace = await db.get(Workspace, workspace_id)
    workspace.name = data.name
    role = await db.scalar(select(WorkspaceMember.role).where(
        WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user.id))
    await db.commit()
    return workspace_out(workspace, role)


@router.get("/{workspace_id}/members", response_model=list[MemberOut])
async def members(workspace_id: uuid.UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(WorkspaceMember, User).join(User).where(
        WorkspaceMember.workspace_id == workspace_id).order_by(User.first_name, User.id))).all()
    return [MemberOut(id=member.id, user_id=user.id, email=user.email,
                      first_name=user.first_name, role=member.role) for member, user in rows]


async def lock_membership(db, workspace_id, user_id):
    # Serialize membership mutations and recheck authority after acquiring the lock.
    await db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    actor = await db.scalar(select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id)
        .execution_options(populate_existing=True))
    if not actor:
        raise HTTPException(404, "Workspace not found")
    if actor.role not in ("OWNER", "ADMIN"):
        raise HTTPException(403, "Недостаточно прав")
    return actor


def authorize_role(actor, old_role, new_role):
    if actor.role == "ADMIN" and (old_role not in (None, "MANAGER") or new_role not in (None, "MANAGER")):
        raise HTTPException(403, "Администратор может управлять только менеджерами")


async def member_to_change(db, workspace_id, member_id, new_role):
    member = await db.scalar(select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.id == member_id))
    if not member:
        raise HTTPException(404, "Участник не найден")
    if member.role == "OWNER" and new_role != "OWNER":
        owners = await db.scalar(select(func.count()).select_from(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.role == "OWNER"))
        if owners <= 1:
            raise HTTPException(409, "В студии должен остаться хотя бы один владелец")
    return member


@router.post("/{workspace_id}/members", status_code=201, response_model=MemberOut)
async def add_member(data: MemberInput, workspace_id: uuid.UUID = Depends(workspace_admin),
                     user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    actor = await lock_membership(db, workspace_id, user.id)
    authorize_role(actor, None, data.role)
    target = await db.scalar(select(User).where(User.email == data.email, User.is_active.is_(True)))
    if not target:
        raise HTTPException(404, "Пользователь должен сначала зарегистрироваться")
    member = WorkspaceMember(workspace_id=workspace_id, user_id=target.id, role=data.role)
    db.add(member)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Пользователь уже состоит в студии")
    return MemberOut(id=member.id, user_id=target.id, email=target.email, first_name=target.first_name, role=member.role)


@router.patch("/{workspace_id}/members/{member_id}", status_code=204)
async def change_role(member_id: uuid.UUID, data: MemberRole, workspace_id: uuid.UUID = Depends(workspace_admin),
                      user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    actor = await lock_membership(db, workspace_id, user.id)
    member = await member_to_change(db, workspace_id, member_id, data.role)
    authorize_role(actor, member.role, data.role)
    member.role = data.role
    await db.commit()
    return Response(status_code=204)


@router.delete("/{workspace_id}/members/{member_id}", status_code=204)
async def remove_member(member_id: uuid.UUID, workspace_id: uuid.UUID = Depends(workspace_admin),
                        user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    actor = await lock_membership(db, workspace_id, user.id)
    member = await member_to_change(db, workspace_id, member_id, None)
    authorize_role(actor, member.role, None)
    await db.delete(member)
    await db.commit()
    return Response(status_code=204)
