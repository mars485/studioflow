"""Add deal card extras: tags, watchers, linked contacts, attachments, custom fields and UTM."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    for column in ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"):
        op.add_column("deals", sa.Column(column, sa.String(255)))
    op.add_column("deals", sa.Column("http_referrer", sa.String(2048)))

    op.drop_constraint("ck_activities_kind", "deal_activities", type_="check")
    op.create_check_constraint("ck_activities_kind", "deal_activities",
                               "kind IN ('NOTE', 'STAGE_CHANGE', 'EVENT', 'MENTION')")

    op.create_table("deal_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "id", name="uq_deal_tags_workspace_id"),
    )
    op.create_index("ix_deal_tags_workspace_id", "deal_tags", ["workspace_id"])
    op.execute("CREATE UNIQUE INDEX uq_deal_tags_workspace_name ON deal_tags (workspace_id, lower(name))")

    op.create_table("deal_tag_links",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_deal_tag_links_workspace_deal", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id", "tag_id"], ["deal_tags.workspace_id", "deal_tags.id"], name="fk_deal_tag_links_workspace_tag", ondelete="CASCADE"),
    )

    op.create_table("deal_watchers",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_deal_watchers_workspace_deal", ondelete="CASCADE"),
    )

    op.create_table("deal_contacts",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_deal_contacts_workspace_deal", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id", "contact_id"], ["contacts.workspace_id", "contacts.id"], name="fk_deal_contacts_workspace_contact", ondelete="CASCADE"),
    )
    op.create_index("uq_deal_contacts_primary", "deal_contacts", ["workspace_id", "deal_id"], unique=True, postgresql_where=sa.text("is_primary"))

    op.create_table("deal_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("uploaded_by_name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_deal_attachments_workspace_deal", ondelete="CASCADE"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_deal_attachments_size"),
    )
    op.create_index("ix_deal_attachments_workspace_id", "deal_attachments", ["workspace_id"])
    op.create_index("ix_deal_attachments_deal_id", "deal_attachments", ["deal_id"])

    op.create_table("deal_custom_values",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("field_key", sa.String(100), primary_key=True),
        sa.Column("field_type", sa.String(10), nullable=False),
        sa.Column("value_text", sa.Text()),
        sa.Column("value_number", sa.Numeric(18, 4)),
        sa.Column("value_date", sa.Date()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_deal_custom_values_workspace_deal", ondelete="CASCADE"),
        sa.CheckConstraint("field_type IN ('TEXT', 'NUMBER', 'DATE')", name="ck_deal_custom_values_type"),
    )


def downgrade():
    op.drop_table("deal_custom_values")
    op.drop_index("ix_deal_attachments_deal_id", table_name="deal_attachments")
    op.drop_index("ix_deal_attachments_workspace_id", table_name="deal_attachments")
    op.drop_table("deal_attachments")
    op.drop_index("uq_deal_contacts_primary", table_name="deal_contacts")
    op.drop_table("deal_contacts")
    op.drop_table("deal_watchers")
    op.drop_table("deal_tag_links")
    op.execute("DROP INDEX uq_deal_tags_workspace_name")
    op.drop_index("ix_deal_tags_workspace_id", table_name="deal_tags")
    op.drop_table("deal_tags")
    op.drop_constraint("ck_activities_kind", "deal_activities", type_="check")
    op.create_check_constraint("ck_activities_kind", "deal_activities", "kind IN ('NOTE', 'STAGE_CHANGE')")
    op.drop_column("deals", "http_referrer")
    for column in ("utm_content", "utm_term", "utm_campaign", "utm_medium", "utm_source"):
        op.drop_column("deals", column)
