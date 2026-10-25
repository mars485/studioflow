"""Ordered execution stages separate from the project's lifecycle stage."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("project_work_stages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="PLANNED"),
        sa.Column("manager_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("start_date", sa.Date()), sa.Column("end_date", sa.Date()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id", "project_id"], ["projects.workspace_id", "projects.id"], name="fk_work_stages_project", ondelete="CASCADE"),
        sa.CheckConstraint("status IN ('PLANNED', 'ACTIVE', 'DONE')", name="ck_work_stages_status"),
        sa.CheckConstraint("position >= 0", name="ck_work_stages_position"),
        sa.CheckConstraint("start_date IS NULL OR end_date IS NULL OR start_date <= end_date", name="ck_work_stages_dates"))
    for column in ("workspace_id", "project_id"):
        op.create_index(f"ix_project_work_stages_{column}", "project_work_stages", [column])


def downgrade():
    op.drop_table("project_work_stages")
