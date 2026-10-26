"""Immutable receipts retain original profiles after an explicit company merge."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ClientMerge(Base):
    __tablename__ = 'client_merges'
    __table_args__ = (
        UniqueConstraint('workspace_id', 'request_key', name='uq_client_merges_request_key'),
        CheckConstraint('source_id <> target_id', name='ck_client_merges_distinct'),
        Index('ix_client_merges_workspace_target', 'workspace_id', 'target_id', 'created_at'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('workspaces.id', ondelete='CASCADE'))
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    request_digest: Mapped[str] = mapped_column(String(64))
    # No object/actor FK: historical snapshots must survive deletion or revoked access.
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    actor_name: Mapped[str] = mapped_column(String(255))
    snapshot: Mapped[dict] = mapped_column(JSONB)
    source_fields: Mapped[list[str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
