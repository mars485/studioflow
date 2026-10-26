from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import current_user, workspace_admin, workspace_member
from app.api.v1.workspaces import lock_membership
from app.core.database import get_db
from app.models import EmployeeGroup, EmployeeGroupBlock, EmployeeGroupMember, GroupAudit, User, WorkspaceMember
from app.models.groups import GROUP_ACTIONS
from app.services.group_permissions import blocked_actions

router = APIRouter(prefix='/workspaces/{workspace_id}', tags=['Employee groups'])
GroupAction = Literal['crm.write', 'clients.write', 'tasks.write', 'projects.write', 'finance.write', 'integrations.write']


class GroupInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    description: str = Field(default='', max_length=1000)
    user_ids: list[UUID] = Field(default_factory=list, max_length=500)
    blocked_actions: list[GroupAction] = Field(default_factory=list, max_length=6)

    @model_validator(mode='after')
    def unique_entries(self):
        if len(self.user_ids) != len(set(self.user_ids)) or len(self.blocked_actions) != len(set(self.blocked_actions)):
            raise ValueError('Участники и ограничения не должны повторяться')
        return self


class GroupUpdate(GroupInput):
    expected_version: int = Field(ge=1)


async def owner_locked(db, workspace_id, user):
    member = await lock_membership(db, workspace_id, user.id)
    if member.role != 'OWNER':
        raise HTTPException(403, 'Только владелец управляет группами и ограничениями доступа')


async def group_out(db, row):
    members = (await db.scalars(select(EmployeeGroupMember.user_id).where(
        EmployeeGroupMember.workspace_id == row.workspace_id, EmployeeGroupMember.group_id == row.id)
        .order_by(EmployeeGroupMember.user_id))).all()
    blocked = (await db.scalars(select(EmployeeGroupBlock.action).where(EmployeeGroupBlock.workspace_id == row.workspace_id,
        EmployeeGroupBlock.group_id == row.id).order_by(EmployeeGroupBlock.action))).all()
    return {'id': row.id, 'name': row.name, 'description': row.description, 'version': row.version,
        'user_ids': members, 'blocked_actions': blocked}


async def group_row(db, workspace_id, group_id):
    row = await db.scalar(select(EmployeeGroup).where(EmployeeGroup.workspace_id == workspace_id,
        EmployeeGroup.id == group_id).with_for_update().execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404, 'Группа не найдена')
    return row


async def validate_members(db, workspace_id, data):
    members = (await db.scalars(select(WorkspaceMember.user_id).where(WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.user_id.in_(data.user_ids)))).all()
    if set(members) != set(data.user_ids):
        raise HTTPException(422, 'Все участники группы должны состоять в этой студии')


async def set_links(db, workspace_id, group_id, data):
    await validate_members(db, workspace_id, data)
    for model in (EmployeeGroupMember, EmployeeGroupBlock):
        await db.execute(delete(model).where(model.workspace_id == workspace_id, model.group_id == group_id))
    db.add_all(EmployeeGroupMember(workspace_id=workspace_id, group_id=group_id, user_id=user_id) for user_id in data.user_ids)
    db.add_all(EmployeeGroupBlock(workspace_id=workspace_id, group_id=group_id, action=action) for action in data.blocked_actions)


def audit(db, row, user, action, fields):
    db.add(GroupAudit(workspace_id=row.workspace_id, group_id=row.id, actor_id=user.id,
        actor_name=' '.join(filter(None, (user.first_name, user.last_name)))[:255], action=action, fields=sorted(fields)))


async def commit(db):
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, 'Название группы уже используется или состав студии изменился') from None


@router.get('/group-permissions')
async def my_permissions(member: WorkspaceMember = Depends(workspace_member), db: AsyncSession = Depends(get_db)):
    blocked = set() if member.role == 'OWNER' else await blocked_actions(db, member.workspace_id, member.user_id)
    return {'role': member.role, 'owner_exempt': member.role == 'OWNER', 'blocked_actions': sorted(blocked),
        'supported_actions': GROUP_ACTIONS, 'mode': 'deny_only_writes'}


@router.get('/groups')
async def groups(workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(EmployeeGroup).where(EmployeeGroup.workspace_id == workspace_id)
        .order_by(EmployeeGroup.name, EmployeeGroup.id))).all()
    return [await group_out(db, row) for row in rows]


@router.get('/groups/audit')
async def group_audit(workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db),
                       limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    rows = (await db.scalars(select(GroupAudit).where(GroupAudit.workspace_id == workspace_id)
        .order_by(GroupAudit.created_at.desc(), GroupAudit.id.desc()).limit(limit).offset(offset))).all()
    return [{'id': row.id, 'group_id': row.group_id, 'actor_id': row.actor_id, 'actor_name': row.actor_name,
        'action': row.action, 'fields': row.fields, 'created_at': row.created_at} for row in rows]


@router.post('/groups', status_code=201)
async def create_group(data: GroupInput, workspace_id: UUID = Depends(workspace_admin),
                        user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await owner_locked(db, workspace_id, user)
    if await db.scalar(select(func.count()).select_from(EmployeeGroup).where(EmployeeGroup.workspace_id == workspace_id)) >= 200:
        raise HTTPException(409, 'В студии допускается не более 200 групп')
    if await db.scalar(select(EmployeeGroup.id).where(EmployeeGroup.workspace_id == workspace_id, EmployeeGroup.name == data.name)):
        raise HTTPException(409, 'Название группы уже используется')
    await validate_members(db, workspace_id, data)
    row = EmployeeGroup(workspace_id=workspace_id, name=data.name, description=data.description)
    db.add(row); await db.flush()
    await set_links(db, workspace_id, row.id, data)
    audit(db, row, user, 'CREATED', ['name', 'description', 'user_ids', 'blocked_actions'])
    await commit(db)
    return await group_out(db, row)


@router.put('/groups/{group_id}')
async def update_group(group_id: UUID, data: GroupUpdate, workspace_id: UUID = Depends(workspace_admin),
                        user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await owner_locked(db, workspace_id, user)
    row = await group_row(db, workspace_id, group_id)
    if row.version != data.expected_version:
        raise HTTPException(409, 'Группа изменена. Обновите список и откройте форму заново')
    if await db.scalar(select(EmployeeGroup.id).where(EmployeeGroup.workspace_id == workspace_id,
        EmployeeGroup.name == data.name, EmployeeGroup.id != group_id)):
        raise HTTPException(409, 'Название группы уже используется')
    before = await group_out(db, row)
    after = {**data.model_dump(exclude={'expected_version'}), 'user_ids': sorted(data.user_ids), 'blocked_actions': sorted(data.blocked_actions)}
    fields = [key for key, value in after.items() if before[key] != value]
    if not fields:
        return before
    await set_links(db, workspace_id, row.id, data)
    row.name, row.description, row.version = data.name, data.description, row.version + 1
    audit(db, row, user, 'UPDATED', fields)
    await commit(db)
    return await group_out(db, row)


@router.delete('/groups/{group_id}', status_code=204)
async def delete_group(group_id: UUID, expected_version: int = Query(ge=1), workspace_id: UUID = Depends(workspace_admin),
                        user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await owner_locked(db, workspace_id, user)
    row = await group_row(db, workspace_id, group_id)
    if row.version != expected_version:
        raise HTTPException(409, 'Группа изменена. Обновите список перед удалением')
    audit(db, row, user, 'DELETED', [])
    await db.delete(row)
    await commit(db)
    return Response(status_code=204)
