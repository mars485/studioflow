"""Independent project work-plan snapshots with relative date offsets."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("project_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False), sa.Column("description", sa.Text()),
        sa.Column("phases", JSONB(), nullable=False), sa.Column("source_project_title", sa.String(255), nullable=False),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_by_name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "name", name="uq_project_templates_name"),
        sa.CheckConstraint("jsonb_typeof(phases) = 'array' AND jsonb_array_length(phases) BETWEEN 1 AND 500", name="ck_project_templates_phases"))
    op.create_index("ix_project_templates_workspace_id", "project_templates", ["workspace_id"])


def downgrade():
    op.drop_table("project_templates")
