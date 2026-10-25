import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, ForeignKeyConstraint, Index, Integer, LargeBinary, Numeric, String, Text,
                       UniqueConstraint, func, text)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class StageType(str, enum.Enum):
    OPEN = "OPEN"
    WON = "WON"
    LOST = "LOST"

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class Workspace(Base, TimestampMixin):
    __tablename__ = "workspaces"
    __table_args__ = (UniqueConstraint("slug"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(100), index=True)
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Yekaterinburg")
    currency: Mapped[str] = mapped_column(String(3), default="RUB")

class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),
                      CheckConstraint("role IN ('OWNER', 'ADMIN', 'MANAGER')", name="ck_member_role"))
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20), default="OWNER")

class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

class AuthThrottle(Base):
    __tablename__ = "auth_throttles"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int]
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class Client(Base, TimestampMixin):
    __tablename__ = "clients"
    __table_args__ = (UniqueConstraint("workspace_id", "id", name="uq_clients_workspace_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(20), default="COMPANY")
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(320))
    website: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

class Contact(Base, TimestampMixin):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("workspace_id", "id", name="uq_contacts_workspace_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(320))
    website: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

class ContactClient(Base):
    __tablename__ = "contact_clients"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "contact_id"], ["contacts.workspace_id", "contacts.id"], name="fk_contact_clients_workspace_contact", ondelete="CASCADE"),
        ForeignKeyConstraint(["workspace_id", "client_id"], ["clients.workspace_id", "clients.id"], name="fk_contact_clients_workspace_client", ondelete="CASCADE"),
        Index("ix_contact_clients_client_id", "client_id"),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

class Pipeline(Base, TimestampMixin):
    __tablename__ = "pipelines"
    __table_args__ = (UniqueConstraint("workspace_id", "id", name="uq_pipelines_workspace_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    stages: Mapped[list["PipelineStage"]] = relationship(back_populates="pipeline", cascade="all, delete-orphan", foreign_keys="PipelineStage.pipeline_id")

class PipelineStage(Base):
    __tablename__ = "pipeline_stages"
    __table_args__ = (
        UniqueConstraint("workspace_id", "pipeline_id", "id", name="uq_stages_workspace_pipeline_id"),
        ForeignKeyConstraint(["workspace_id", "pipeline_id"], ["pipelines.workspace_id", "pipelines.id"], name="fk_stages_workspace_pipeline", ondelete="CASCADE"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    pipeline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipelines.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    position: Mapped[int]
    stage_type: Mapped[StageType] = mapped_column(Enum(StageType), default=StageType.OPEN)
    color: Mapped[str | None] = mapped_column(String(20))
    pipeline: Mapped[Pipeline] = relationship(back_populates="stages", foreign_keys=[pipeline_id])

class Deal(Base, TimestampMixin):
    __tablename__ = "deals"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_deals_workspace_id"),
        ForeignKeyConstraint(["workspace_id", "client_id"], ["clients.workspace_id", "clients.id"], name="fk_deals_workspace_client", ondelete="RESTRICT"),
        ForeignKeyConstraint(["workspace_id", "contact_id"], ["contacts.workspace_id", "contacts.id"], name="fk_deals_workspace_contact", ondelete="RESTRICT"),
        ForeignKeyConstraint(["workspace_id", "pipeline_id", "stage_id"], ["pipeline_stages.workspace_id", "pipeline_stages.pipeline_id", "pipeline_stages.id"], name="fk_deals_workspace_stage", ondelete="RESTRICT"),
        CheckConstraint("amount >= 0", name="ck_deals_amount"),
        CheckConstraint("start_date IS NULL OR end_date IS NULL OR start_date <= end_date", name="ck_deals_date_order"),
        CheckConstraint("(follow_up_at IS NULL AND follow_up_action IS NULL AND follow_up_comment IS NULL) OR (follow_up_at IS NOT NULL AND follow_up_action IN ('call', 'message', 'proposal', 'decision') AND follow_up_action IS NOT NULL)", name="ck_deals_follow_up"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="RESTRICT"))
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="RESTRICT"))
    pipeline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipelines.id", ondelete="RESTRICT"))
    stage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_stages.id", ondelete="RESTRICT"))
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    description: Mapped[str | None] = mapped_column(Text)
    contact_name: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str | None] = mapped_column(String(100))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    follow_up_action: Mapped[str | None] = mapped_column(String(20))
    follow_up_comment: Mapped[str | None] = mapped_column(Text)
    utm_source: Mapped[str | None] = mapped_column(String(255))
    utm_medium: Mapped[str | None] = mapped_column(String(255))
    utm_campaign: Mapped[str | None] = mapped_column(String(255))
    utm_term: Mapped[str | None] = mapped_column(String(255))
    utm_content: Mapped[str | None] = mapped_column(String(255))
    http_referrer: Mapped[str | None] = mapped_column(String(2048))


class DealActivity(Base):
    __tablename__ = "deal_activities"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_activities_workspace_id"),
        ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_activities_workspace_deal", ondelete="CASCADE"),
        CheckConstraint("length(trim(body)) > 0", name="ck_activities_body_not_blank"),
        CheckConstraint("kind IN ('NOTE', 'STAGE_CHANGE', 'EVENT', 'MENTION')", name="ck_activities_kind"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    author_name: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="NOTE", server_default="NOTE")
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    recipient_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaskStatus(Base):
    __tablename__ = "task_statuses"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_task_statuses_workspace_id"),
        UniqueConstraint("workspace_id", "name", name="uq_task_statuses_workspace_name"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_tasks_workspace_id"),
        ForeignKeyConstraint(["workspace_id", "status_id"], ["task_statuses.workspace_id", "task_statuses.id"],
                             name="fk_tasks_workspace_status", ondelete="RESTRICT"),
        ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"],
                             name="fk_tasks_workspace_deal", ondelete="CASCADE"),
        ForeignKeyConstraint(["workspace_id", "project_id"], ["projects.workspace_id", "projects.id"],
                             name="fk_tasks_workspace_project", deferrable=True, initially="DEFERRED"),
        ForeignKeyConstraint(["workspace_id", "contact_id"], ["contacts.workspace_id", "contacts.id"],
                             name="fk_tasks_workspace_contact", deferrable=True, initially="DEFERRED"),
        ForeignKeyConstraint(["workspace_id", "parent_task_id"], ["tasks.workspace_id", "tasks.id"],
                             name="fk_tasks_workspace_parent", deferrable=True, initially="DEFERRED"),
        CheckConstraint("parent_task_id IS NULL OR parent_task_id <> id", name="ck_tasks_not_own_parent"),
        CheckConstraint("priority IN ('LOW', 'MEDIUM', 'HIGH')", name="ck_tasks_priority"),
        CheckConstraint("start_at IS NULL OR due_at IS NULL OR start_at <= due_at", name="ck_tasks_date_order"),
        CheckConstraint("estimate_minutes IS NULL OR estimate_minutes >= 0", name="ck_tasks_estimate"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    status_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    priority: Mapped[str] = mapped_column(String(10), default="MEDIUM", server_default="MEDIUM")
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    creator_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimate_minutes: Mapped[int | None] = mapped_column(Integer)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL", name="fk_tasks_project"), index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL", name="fk_tasks_contact"))
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL", name="fk_tasks_parent"), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskChecklistItem(Base):
    __tablename__ = "task_checklist_items"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"],
                             name="fk_task_checklist_workspace_task", ondelete="CASCADE"),
        CheckConstraint("length(trim(text)) > 0", name="ck_task_checklist_text"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    text: Mapped[str] = mapped_column(String(500))
    is_done: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaskWatcher(Base):
    __tablename__ = "task_watchers"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"],
                             name="fk_task_watchers_workspace_task", ondelete="CASCADE"),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectStage(Base):
    __tablename__ = "project_stages"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_project_stages_workspace_id"),
        UniqueConstraint("workspace_id", "name", name="uq_project_stages_workspace_name"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_projects_workspace_id"),
        ForeignKeyConstraint(["workspace_id", "client_id"], ["clients.workspace_id", "clients.id"],
                             name="fk_projects_workspace_client", ondelete="RESTRICT"),
        ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"],
                             name="fk_projects_workspace_deal", deferrable=True, initially="DEFERRED"),
        ForeignKeyConstraint(["workspace_id", "stage_id"], ["project_stages.workspace_id", "project_stages.id"],
                             name="fk_projects_workspace_stage", ondelete="RESTRICT"),
        CheckConstraint("status IN ('ACTIVE', 'ARCHIVED', 'COMPLETED')", name="ck_projects_status"),
        CheckConstraint("amount >= 0", name="ck_projects_amount"),
        CheckConstraint("start_date IS NULL OR end_date IS NULL OR start_date <= end_date", name="ck_projects_date_order"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deals.id", ondelete="SET NULL", name="fk_projects_deal"), index=True)
    stage_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    manager_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE", server_default="ACTIVE")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "project_id"], ["projects.workspace_id", "projects.id"],
                             name="fk_project_members_workspace_project", ondelete="CASCADE"),
        CheckConstraint("role IN ('LEAD', 'MEMBER')", name="ck_project_members_role"),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="MEMBER", server_default="MEMBER")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectContact(Base):
    __tablename__ = "project_contacts"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "project_id"], ["projects.workspace_id", "projects.id"],
                             name="fk_project_contacts_workspace_project", ondelete="CASCADE"),
        ForeignKeyConstraint(["workspace_id", "contact_id"], ["contacts.workspace_id", "contacts.id"],
                             name="fk_project_contacts_workspace_contact", ondelete="CASCADE"),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectEvent(Base):
    __tablename__ = "project_events"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "project_id"], ["projects.workspace_id", "projects.id"],
                             name="fk_project_events_workspace_project", ondelete="CASCADE"),
        CheckConstraint("length(trim(body)) > 0", name="ck_project_events_body"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    author_name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(30), default="NOTE", server_default="NOTE")
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaskReminder(Base):
    __tablename__ = "task_reminders"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"], name="fk_task_reminders_workspace_task", ondelete="CASCADE"),
        CheckConstraint("(kind = 'DATE' AND at IS NOT NULL AND offset_minutes IS NULL) OR (kind IN ('START_OFFSET', 'DUE_OFFSET') AND at IS NULL AND offset_minutes >= 0)", name="ck_task_reminders_trigger"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20))
    at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    offset_minutes: Mapped[int | None]
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FollowUpCompletion(Base):
    __tablename__ = "follow_up_completions"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_completions_workspace_deal", ondelete="CASCADE"),
        CheckConstraint("action IN ('call', 'message', 'proposal', 'decision')", name="ck_completions_action"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    completed_by_name: Mapped[str] = mapped_column(String(255))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    action: Mapped[str] = mapped_column(String(20))
    planned_comment: Mapped[str | None] = mapped_column(Text)
    outcome_comment: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DealTag(Base, TimestampMixin):
    __tablename__ = "deal_tags"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_deal_tags_workspace_id"),
        Index("uq_deal_tags_workspace_name", "workspace_id", func.lower("name"), unique=True),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50))


class DealTagLink(Base):
    __tablename__ = "deal_tag_links"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_deal_tag_links_workspace_deal", ondelete="CASCADE"),
        ForeignKeyConstraint(["workspace_id", "tag_id"], ["deal_tags.workspace_id", "deal_tags.id"], name="fk_deal_tag_links_workspace_tag", ondelete="CASCADE"),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tag_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DealWatcher(Base):
    __tablename__ = "deal_watchers"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_deal_watchers_workspace_deal", ondelete="CASCADE"),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DealContact(Base):
    __tablename__ = "deal_contacts"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_deal_contacts_workspace_deal", ondelete="CASCADE"),
        ForeignKeyConstraint(["workspace_id", "contact_id"], ["contacts.workspace_id", "contacts.id"], name="fk_deal_contacts_workspace_contact", ondelete="CASCADE"),
        Index("uq_deal_contacts_primary", "workspace_id", "deal_id", unique=True, postgresql_where=text("is_primary")),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DealAttachment(Base):
    __tablename__ = "deal_attachments"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_deal_attachments_workspace_deal", ondelete="CASCADE"),
        CheckConstraint("size_bytes >= 0", name="ck_deal_attachments_size"),
        UniqueConstraint("workspace_id", "id", name="uq_deal_attachments_workspace_id"),
        UniqueConstraint("workspace_id", "upload_key", name="uq_deal_attachments_upload_key"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64))
    upload_key: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    uploaded_by_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def has_content(self) -> bool:
        return self.sha256 is not None


class DealAttachmentContent(Base):
    __tablename__ = "deal_attachment_contents"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "attachment_id"], ["deal_attachments.workspace_id", "deal_attachments.id"],
                             name="fk_attachment_contents_attachment", ondelete="CASCADE"),
    )
    attachment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class DealCustomValue(Base):
    __tablename__ = "deal_custom_values"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_deal_custom_values_workspace_deal", ondelete="CASCADE"),
        CheckConstraint("field_type IN ('TEXT', 'NUMBER', 'DATE')", name="ck_deal_custom_values_type"),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    field_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    field_type: Mapped[str] = mapped_column(String(10))
    value_text: Mapped[str | None] = mapped_column(Text)
    value_number: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    value_date: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

