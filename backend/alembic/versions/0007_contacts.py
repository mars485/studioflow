"""Add workspace-scoped contacts, company links and optional deal contact."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100)),
        sa.Column("middle_name", sa.String(100)),
        sa.Column("phone", sa.String(50)),
        sa.Column("email", sa.String(320)),
        sa.Column("website", sa.String(255)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("workspace_id", "id", name="uq_contacts_workspace_id"),
    )
    op.create_index("ix_contacts_workspace_id", "contacts", ["workspace_id"])
    op.create_table("contact_clients",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.ForeignKeyConstraint(["workspace_id", "contact_id"], ["contacts.workspace_id", "contacts.id"], name="fk_contact_clients_workspace_contact", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id", "client_id"], ["clients.workspace_id", "clients.id"], name="fk_contact_clients_workspace_client", ondelete="CASCADE"),
    )
    op.create_index("ix_contact_clients_client_id", "contact_clients", ["client_id"])
    op.add_column("deals", sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="RESTRICT")))
    op.create_foreign_key("fk_deals_workspace_contact", "deals", "contacts",
                          ["workspace_id", "contact_id"], ["workspace_id", "id"], ondelete="RESTRICT")


def downgrade():
    op.drop_constraint("fk_deals_workspace_contact", "deals", type_="foreignkey")
    op.drop_column("deals", "contact_id")
    op.drop_table("contact_clients")
    op.drop_table("contacts")
