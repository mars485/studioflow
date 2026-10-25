"""Keep legacy metadata; persist real attachment bytes transactionally."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("deal_attachments", sa.Column("sha256", sa.String(64)))
    op.add_column("deal_attachments", sa.Column("upload_key", UUID(as_uuid=True)))
    op.create_unique_constraint("uq_deal_attachments_workspace_id", "deal_attachments", ["workspace_id", "id"])
    op.create_unique_constraint("uq_deal_attachments_upload_key", "deal_attachments", ["workspace_id", "upload_key"])
    op.create_table("deal_attachment_contents",
        sa.Column("attachment_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id", "attachment_id"], ["deal_attachments.workspace_id", "deal_attachments.id"],
                                name="fk_attachment_contents_attachment", ondelete="CASCADE"))
    op.create_index("ix_deal_attachment_contents_workspace_id", "deal_attachment_contents", ["workspace_id"])


def downgrade():
    # Binary contents cannot be represented by the old metadata-only application.
    op.drop_table("deal_attachment_contents")
    op.drop_constraint("uq_deal_attachments_upload_key", "deal_attachments", type_="unique")
    op.drop_constraint("uq_deal_attachments_workspace_id", "deal_attachments", type_="unique")
    op.drop_column("deal_attachments", "upload_key")
    op.drop_column("deal_attachments", "sha256")
