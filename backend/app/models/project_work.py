import uuid
from datetime import date
from sqlalchemy import CheckConstraint, Date, ForeignKey, ForeignKeyConstraint, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.entities import TimestampMixin


class ProjectWorkStage(Base, TimestampMixin):
    __tablename__ = "project_work_stages"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "project_id"], ["projects.workspace_id", "projects.id"], name="fk_work_stages_project", ondelete="CASCADE"),
        CheckConstraint("status IN ('PLANNED', 'ACTIVE', 'DONE')", name="ck_work_stages_status"),
        CheckConstraint("position >= 0", name="ck_work_stages_position"),
        CheckConstraint("start_date IS NULL OR end_date IS NULL OR start_date <= end_date", name="ck_work_stages_dates"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    title: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(10), default="PLANNED", server_default="PLANNED")
    manager_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
