"""Add workspace-scoped tasks linked to deals."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("deal_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("priority", sa.String(10), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(10), nullable=False, server_default="OPEN"),
        sa.Column("assignee_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("completed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("start_at", sa.DateTime(timezone=True)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_deal_tasks_workspace_deal", ondelete="CASCADE"),
        sa.CheckConstraint("priority IN ('LOW', 'MEDIUM', 'HIGH')", name="ck_deal_tasks_priority"),
        sa.CheckConstraint("status IN ('OPEN', 'DONE')", name="ck_deal_tasks_status"),
        sa.CheckConstraint("start_at IS NULL OR due_at IS NULL OR start_at <= due_at", name="ck_deal_tasks_date_order"),
    )
    op.create_index("ix_deal_tasks_workspace_id", "deal_tasks", ["workspace_id"])
    op.create_index("ix_deal_tasks_deal_id", "deal_tasks", ["deal_id"])


def downgrade():
    op.drop_index("ix_deal_tasks_deal_id", table_name="deal_tasks")
    op.drop_index("ix_deal_tasks_workspace_id", table_name="deal_tasks")
    op.drop_table("deal_tasks")
