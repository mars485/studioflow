"""Add personal reminders for deal tasks."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_deal_tasks_workspace_id", "deal_tasks", ["workspace_id", "id"])
    op.create_table("task_reminders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True)),
        sa.Column("offset_minutes", sa.Integer()),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id", "task_id"], ["deal_tasks.workspace_id", "deal_tasks.id"], name="fk_task_reminders_workspace_task", ondelete="CASCADE"),
        sa.CheckConstraint("(kind = 'DATE' AND at IS NOT NULL AND offset_minutes IS NULL) OR (kind IN ('START_OFFSET', 'DUE_OFFSET') AND at IS NULL AND offset_minutes >= 0)", name="ck_task_reminders_trigger"),
    )
    op.create_index("ix_task_reminders_workspace_id", "task_reminders", ["workspace_id"])
    op.create_index("ix_task_reminders_task_id", "task_reminders", ["task_id"])
    op.create_index("ix_task_reminders_recipient_user_id", "task_reminders", ["recipient_user_id"])


def downgrade():
    op.drop_index("ix_task_reminders_recipient_user_id", table_name="task_reminders")
    op.drop_index("ix_task_reminders_task_id", table_name="task_reminders")
    op.drop_index("ix_task_reminders_workspace_id", table_name="task_reminders")
    op.drop_table("task_reminders")
    op.drop_constraint("uq_deal_tasks_workspace_id", "deal_tasks", type_="unique")
