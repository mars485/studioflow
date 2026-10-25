import uuid
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class WebhookSubscription(Base):
    __tablename__ = 'webhook_subscriptions'
    __table_args__ = (
        UniqueConstraint('workspace_id', 'id', name='uq_webhook_subscriptions_workspace'),
        UniqueConstraint('workspace_id', 'destination', name='uq_webhook_subscriptions_destination'),
        ForeignKeyConstraint(['workspace_id', 'created_by_user_id'], ['workspace_members.workspace_id', 'workspace_members.user_id'],
            name='fk_webhook_subscriptions_issuer', ondelete='CASCADE'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('workspaces.id', ondelete='CASCADE'), index=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    destination: Mapped[str] = mapped_column(String(100))
    events: Mapped[list] = mapped_column(JSONB)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default='true')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WebhookDelivery(Base):
    __tablename__ = 'webhook_deliveries'
    __table_args__ = (
        ForeignKeyConstraint(['workspace_id', 'subscription_id'], ['webhook_subscriptions.workspace_id', 'webhook_subscriptions.id'],
            name='fk_webhook_deliveries_subscription', ondelete='CASCADE'),
        UniqueConstraint('subscription_id', 'event_id', name='uq_webhook_deliveries_event'),
        CheckConstraint("status IN ('PENDING', 'SENT', 'FAILED', 'CANCELLED')", name='ck_webhook_deliveries_status'),
        CheckConstraint('attempts >= 0', name='ck_webhook_deliveries_attempts'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('workspaces.id', ondelete='CASCADE'), index=True)
    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(10), default='PENDING', server_default='PENDING')
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    last_result: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
