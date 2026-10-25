import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "recipient_user_id"], ["workspace_members.workspace_id", "workspace_members.user_id"],
                             name="fk_notifications_recipient", ondelete="CASCADE"),
        ForeignKeyConstraint(["workspace_id", "activity_id"], ["deal_activities.workspace_id", "deal_activities.id"],
                             name="fk_notifications_activity", ondelete="CASCADE"),
        UniqueConstraint("workspace_id", "recipient_user_id", "activity_id", name="uq_notifications_activity_recipient"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    activity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
