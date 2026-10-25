"""Add workspace-scoped deal notes with immutable author label."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_deals_workspace_id", "deals", ["workspace_id", "id"])
    op.create_table("deal_activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("author_name", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_activities_workspace_deal", ondelete="CASCADE"),
        sa.CheckConstraint("length(trim(body)) > 0", name="ck_activities_body_not_blank"),
    )
    op.create_index("ix_deal_activities_workspace_id", "deal_activities", ["workspace_id"])
    op.create_index("ix_deal_activities_deal_id", "deal_activities", ["deal_id"])


def downgrade():
    op.drop_table("deal_activities")
    op.drop_constraint("uq_deals_workspace_id", "deals", type_="unique")
