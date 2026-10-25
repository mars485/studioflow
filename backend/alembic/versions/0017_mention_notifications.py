"""Addressed mentions and membership-scoped internal inbox."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("deal_activities", sa.Column("recipient_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")))
    op.add_column("deal_activities", sa.Column("recipient_name", sa.String(255)))
    op.create_unique_constraint("uq_activities_workspace_id", "deal_activities", ["workspace_id", "id"])
    op.create_table("notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("activity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id", "recipient_user_id"], ["workspace_members.workspace_id", "workspace_members.user_id"], name="fk_notifications_recipient", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id", "activity_id"], ["deal_activities.workspace_id", "deal_activities.id"], name="fk_notifications_activity", ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "recipient_user_id", "activity_id", name="uq_notifications_activity_recipient"))
    op.create_index("ix_notifications_workspace_id", "notifications", ["workspace_id"])
    op.create_index("ix_notifications_recipient_user_id", "notifications", ["recipient_user_id"])


def downgrade():
    op.drop_table("notifications")
    op.drop_constraint("uq_activities_workspace_id", "deal_activities", type_="unique")
    op.drop_column("deal_activities", "recipient_name")
    op.drop_column("deal_activities", "recipient_user_id")
