import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class IntegrationToken(Base):
    __tablename__ = "integration_tokens"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_integration_tokens_workspace_id"),
        UniqueConstraint("token_hash", name="uq_integration_tokens_hash"),
        ForeignKeyConstraint(["workspace_id", "created_by_user_id"], ["workspace_members.workspace_id", "workspace_members.user_id"], name="fk_integration_tokens_issuer", ondelete="CASCADE"),
        ForeignKeyConstraint(["workspace_id", "pipeline_id"], ["pipelines.workspace_id", "pipelines.id"], name="fk_integration_tokens_workspace_pipeline", deferrable=True, initially="DEFERRED"),
        CheckConstraint("hour_count >= 0", name="ck_integration_tokens_hour_count"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    name: Mapped[str] = mapped_column(String(255))
    token_hash: Mapped[str] = mapped_column(String(64))
    hint: Mapped[str] = mapped_column(String(20))
    pipeline_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pipelines.id", ondelete="SET NULL", name="fk_integration_tokens_pipeline"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hour_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hour_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class IncomingLead(Base):
    __tablename__ = "incoming_leads"
    __table_args__ = (
        UniqueConstraint("workspace_id", "request_key", name="uq_incoming_leads_request_key"),
        ForeignKeyConstraint(["workspace_id", "token_id"], ["integration_tokens.workspace_id", "integration_tokens.id"], name="fk_incoming_leads_workspace_token", deferrable=True, initially="DEFERRED"),
        ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_incoming_leads_workspace_deal", deferrable=True, initially="DEFERRED"),
        ForeignKeyConstraint(["workspace_id", "client_id"], ["clients.workspace_id", "clients.id"], name="fk_incoming_leads_workspace_client", deferrable=True, initially="DEFERRED"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    request_digest: Mapped[str] = mapped_column(String(64))
    website_context: Mapped[dict | None] = mapped_column(JSONB)
    token_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("integration_tokens.id", ondelete="SET NULL", name="fk_incoming_leads_token"))
    client_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clients.id", ondelete="SET NULL", name="fk_incoming_leads_client"))
    deal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deals.id", ondelete="SET NULL", name="fk_incoming_leads_deal"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
