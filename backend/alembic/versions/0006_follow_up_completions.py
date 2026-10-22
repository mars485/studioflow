"""Record completed follow-ups separately from the next scheduled action."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("follow_up_completions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("completed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("completed_by_name", sa.String(255), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("planned_comment", sa.Text()),
        sa.Column("outcome_comment", sa.Text()),
        sa.Column("completed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_completions_workspace_deal", ondelete="CASCADE"),
        sa.CheckConstraint("action IN ('call', 'message', 'proposal', 'decision')", name="ck_completions_action"),
    )
    op.create_index("ix_follow_up_completions_workspace_id", "follow_up_completions", ["workspace_id"])
    op.create_index("ix_follow_up_completions_deal_id", "follow_up_completions", ["deal_id"])


def downgrade():
    op.drop_table("follow_up_completions")
