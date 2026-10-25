"""Limited integration tokens and idempotent inbound CRM lead receipts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("integration_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("hint", sa.String(20), nullable=False),
        sa.Column("pipeline_id", UUID(as_uuid=True), sa.ForeignKey("pipelines.id", ondelete="SET NULL", name="fk_integration_tokens_pipeline")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)), sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("hour_started_at", sa.DateTime(timezone=True)),
        sa.Column("hour_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "id", name="uq_integration_tokens_workspace_id"),
        sa.UniqueConstraint("token_hash", name="uq_integration_tokens_hash"),
        sa.ForeignKeyConstraint(["workspace_id", "created_by_user_id"], ["workspace_members.workspace_id", "workspace_members.user_id"], name="fk_integration_tokens_issuer", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id", "pipeline_id"], ["pipelines.workspace_id", "pipelines.id"], name="fk_integration_tokens_workspace_pipeline", deferrable=True, initially="DEFERRED"),
        sa.CheckConstraint("hour_count >= 0", name="ck_integration_tokens_hour_count"))
    op.create_table("incoming_leads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_key", UUID(as_uuid=True), nullable=False), sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("token_id", UUID(as_uuid=True), sa.ForeignKey("integration_tokens.id", ondelete="SET NULL", name="fk_incoming_leads_token")),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="SET NULL", name="fk_incoming_leads_client")),
        sa.Column("deal_id", UUID(as_uuid=True), sa.ForeignKey("deals.id", ondelete="SET NULL", name="fk_incoming_leads_deal")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "request_key", name="uq_incoming_leads_request_key"),
        sa.ForeignKeyConstraint(["workspace_id", "token_id"], ["integration_tokens.workspace_id", "integration_tokens.id"], name="fk_incoming_leads_workspace_token", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_incoming_leads_workspace_deal", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["workspace_id", "client_id"], ["clients.workspace_id", "clients.id"], name="fk_incoming_leads_workspace_client", deferrable=True, initially="DEFERRED"))
    for table in ("integration_tokens", "incoming_leads"):
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])


def downgrade():
    op.drop_table("incoming_leads")
    op.drop_table("integration_tokens")
