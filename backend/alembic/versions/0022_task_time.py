"""Persistent per-user task timers and manual time records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("task_time_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("author_name", sa.String(255), nullable=False), sa.Column("request_key", UUID(as_uuid=True), nullable=False),
        sa.Column("worked_on", sa.Date(), nullable=False), sa.Column("seconds", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("comment", sa.Text()), sa.Column("stop_reason", sa.String(30)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"], name="fk_task_time_task", ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "user_id", "request_key", name="uq_task_time_request"),
        sa.CheckConstraint("seconds >= 0", name="ck_task_time_seconds"),
        sa.CheckConstraint("(started_at IS NULL AND ended_at IS NULL AND seconds > 0) OR "
                           "(started_at IS NOT NULL AND ended_at IS NULL AND seconds = 0) OR "
                           "(started_at IS NOT NULL AND ended_at IS NOT NULL AND ended_at >= started_at)", name="ck_task_time_state"))
    for column in ("workspace_id", "task_id"):
        op.create_index(f"ix_task_time_entries_{column}", "task_time_entries", [column])
    op.create_index("uq_task_time_running", "task_time_entries", ["workspace_id", "user_id"], unique=True,
        postgresql_where=sa.text("started_at IS NOT NULL AND ended_at IS NULL"))


def downgrade():
    op.drop_table("task_time_entries")
