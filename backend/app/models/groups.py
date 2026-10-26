import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import TimestampMixin

GROUP_ACTIONS = ('crm.write', 'clients.write', 'tasks.write', 'projects.write', 'finance.write', 'integrations.write')


class EmployeeGroup(Base, TimestampMixin):
    __tablename__ = 'employee_groups'
    __table_args__ = (
        UniqueConstraint('workspace_id', 'id', name='uq_employee_groups_workspace_id'),
        UniqueConstraint('workspace_id', 'name', name='uq_employee_groups_workspace_name'),
        CheckConstraint('version > 0', name='ck_employee_groups_version'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('workspaces.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(1000), default='', server_default='')
    version: Mapped[int] = mapped_column(Integer, default=1, server_default='1')


class EmployeeGroupMember(Base):
    __tablename__ = 'employee_group_members'
    __table_args__ = (
        ForeignKeyConstraint(['workspace_id', 'group_id'], ['employee_groups.workspace_id', 'employee_groups.id'],
            name='fk_employee_group_members_group', ondelete='CASCADE'),
        ForeignKeyConstraint(['workspace_id', 'user_id'], ['workspace_members.workspace_id', 'workspace_members.user_id'],
            name='fk_employee_group_members_membership', ondelete='CASCADE'),
        Index('ix_employee_group_members_user', 'workspace_id', 'user_id'),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)


class EmployeeGroupBlock(Base):
    __tablename__ = 'employee_group_blocks'
    __table_args__ = (
        ForeignKeyConstraint(['workspace_id', 'group_id'], ['employee_groups.workspace_id', 'employee_groups.id'],
            name='fk_employee_group_blocks_group', ondelete='CASCADE'),
        CheckConstraint("action IN ('crm.write','clients.write','tasks.write','projects.write','finance.write','integrations.write')", name='ck_employee_group_blocks_action'),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    action: Mapped[str] = mapped_column(String(30), primary_key=True)


class GroupAudit(Base):
    __tablename__ = 'group_audit'
    __table_args__ = (
        CheckConstraint("action IN ('CREATED','UPDATED','DELETED')", name='ck_group_audit_action'),
        Index('ix_group_audit_workspace_time', 'workspace_id', 'created_at', 'id'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('workspaces.id', ondelete='CASCADE'))
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    actor_name: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(10))
    fields: Mapped[list[str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
