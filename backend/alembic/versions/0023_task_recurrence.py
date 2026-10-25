"""Bounded completion-based task recurrence, no background scheduler."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("task_recurrences",
        sa.Column("task_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False), sa.Column("remaining", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("next_task_id", UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="SET NULL", name="fk_task_recurrence_next_id")),
        sa.Column("stop_reason", sa.String(30)),
        sa.ForeignKeyConstraint(["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"], name="fk_task_recurrence_task", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id", "next_task_id"], ["tasks.workspace_id", "tasks.id"], name="fk_task_recurrence_next", deferrable=True, initially="DEFERRED"),
        sa.CheckConstraint("interval_days BETWEEN 1 AND 365", name="ck_task_recurrence_interval"),
        sa.CheckConstraint("remaining BETWEEN 1 AND 365", name="ck_task_recurrence_remaining"))
    op.create_index("ix_task_recurrences_workspace_id", "task_recurrences", ["workspace_id"])


def downgrade():
    op.drop_table("task_recurrences")
