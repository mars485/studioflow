import uuid
from datetime import date, datetime
from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.entities import TimestampMixin


class TaskTimeEntry(Base, TimestampMixin):
    __tablename__ = "task_time_entries"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"], name="fk_task_time_task", ondelete="CASCADE"),
        UniqueConstraint("workspace_id", "user_id", "request_key", name="uq_task_time_request"),
        Index("uq_task_time_running", "workspace_id", "user_id", unique=True,
              postgresql_where=text("started_at IS NOT NULL AND ended_at IS NULL")),
        CheckConstraint("seconds >= 0", name="ck_task_time_seconds"),
        CheckConstraint("(started_at IS NULL AND ended_at IS NULL AND seconds > 0) OR "
                        "(started_at IS NOT NULL AND ended_at IS NULL AND seconds = 0) OR "
                        "(started_at IS NOT NULL AND ended_at IS NOT NULL AND ended_at >= started_at)", name="ck_task_time_state"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    author_name: Mapped[str] = mapped_column(String(255))
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    worked_on: Mapped[date] = mapped_column(Date)
    seconds: Mapped[int] = mapped_column(BigInteger, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)
    stop_reason: Mapped[str | None] = mapped_column(String(30))
