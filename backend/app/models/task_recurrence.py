import uuid
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class TaskRecurrence(Base):
    __tablename__ = "task_recurrences"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"], name="fk_task_recurrence_task", ondelete="CASCADE"),
        ForeignKeyConstraint(["workspace_id", "next_task_id"], ["tasks.workspace_id", "tasks.id"], name="fk_task_recurrence_next", deferrable=True, initially="DEFERRED"),
        CheckConstraint("interval_days BETWEEN 1 AND 365", name="ck_task_recurrence_interval"),
        CheckConstraint("remaining BETWEEN 1 AND 365", name="ck_task_recurrence_remaining"),
    )
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    interval_days: Mapped[int] = mapped_column(Integer)
    remaining: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    processed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    next_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL", name="fk_task_recurrence_next_id"))
    stop_reason: Mapped[str | None] = mapped_column(String(30))
