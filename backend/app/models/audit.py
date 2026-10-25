import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class DealAudit(Base):
    __tablename__ = 'deal_audit'
    __table_args__ = (
        CheckConstraint("action IN ('CREATED', 'UPDATED', 'DELETED')", name='ck_deal_audit_action'),
        CheckConstraint("actor_kind IN ('USER', 'INTEGRATION')", name='ck_deal_audit_actor'),
        Index('ix_deal_audit_workspace_time', 'workspace_id', 'created_at', 'id'),
        Index('ix_deal_audit_workspace_object', 'workspace_id', 'deal_id'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('workspaces.id', ondelete='CASCADE'))
    # Historical identities deliberately have no FK: deleting the object/actor retains history.
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    actor_kind: Mapped[str] = mapped_column(String(12))
    actor_name: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(10))
    fields: Mapped[list[str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
