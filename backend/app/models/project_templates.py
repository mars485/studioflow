import uuid
from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.entities import TimestampMixin


class ProjectTemplate(Base, TimestampMixin):
    __tablename__ = "project_templates"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_project_templates_name"),
        CheckConstraint("jsonb_typeof(phases) = 'array' AND jsonb_array_length(phases) BETWEEN 1 AND 500", name="ck_project_templates_phases"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    phases: Mapped[list] = mapped_column(JSONB)
    source_project_title: Mapped[str] = mapped_column(String(255))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_by_name: Mapped[str] = mapped_column(String(255))
