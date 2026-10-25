"""Workspace invoices, immutable party snapshots, payments and acts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def workspace():
    return sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)


def identity():
    return sa.Column("id", UUID(as_uuid=True), primary_key=True)


def upgrade():
    op.create_table("organizations", identity(), workspace(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("tax_id", sa.String(12), nullable=False),
        sa.Column("tax_branch", sa.String(9), nullable=False),
        sa.Column("address", sa.String(1000), nullable=False),
        sa.Column("bank", sa.String(255), nullable=False),
        sa.Column("bank_account", sa.String(34), nullable=False),
        sa.Column("bank_code", sa.String(11), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "id", name="uq_organizations_workspace_id"))
    op.create_table("finance_counters",
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("kind", sa.String(10), primary_key=True), sa.Column("value", sa.Integer(), nullable=False))
    op.create_table("invoices", identity(), workspace(),
        sa.Column("number", sa.Integer(), nullable=False), sa.Column("issued_on", sa.Date(), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("deal_id", UUID(as_uuid=True), sa.ForeignKey("deals.id", ondelete="SET NULL", name="fk_invoices_deal")),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL", name="fk_invoices_project")),
        sa.Column("manager_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False), sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("state", sa.String(10), nullable=False, server_default="DRAFT"),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("seller", JSONB(), nullable=False), sa.Column("buyer", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "id", name="uq_invoices_workspace_id"),
        sa.UniqueConstraint("workspace_id", "number", name="uq_invoices_workspace_number"),
        sa.ForeignKeyConstraint(["workspace_id", "client_id"], ["clients.workspace_id", "clients.id"], name="fk_invoices_client"),
        sa.ForeignKeyConstraint(["workspace_id", "organization_id"], ["organizations.workspace_id", "organizations.id"], name="fk_invoices_organization"),
        sa.ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_invoices_workspace_deal", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["workspace_id", "project_id"], ["projects.workspace_id", "projects.id"], name="fk_invoices_workspace_project", deferrable=True, initially="DEFERRED"),
        sa.CheckConstraint("amount > 0", name="ck_invoices_amount"),
        sa.CheckConstraint("state IN ('DRAFT', 'ISSUED', 'CANCELLED')", name="ck_invoices_state"))
    op.create_table("invoice_payments", identity(), workspace(),
        sa.Column("invoice_id", UUID(as_uuid=True), nullable=False),
        sa.Column("request_key", UUID(as_uuid=True), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False), sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("method", sa.String(50), nullable=False), sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id", "invoice_id"], ["invoices.workspace_id", "invoices.id"], name="fk_payments_invoice", ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "invoice_id", "request_key", name="uq_payments_request_key"),
        sa.CheckConstraint("amount > 0", name="ck_invoice_payments_amount"))
    op.create_table("acts", identity(), workspace(),
        sa.Column("invoice_id", UUID(as_uuid=True), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False), sa.Column("issued_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="DRAFT"),
        sa.Column("signed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["workspace_id", "invoice_id"], ["invoices.workspace_id", "invoices.id"], name="fk_acts_invoice", ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "number", name="uq_acts_workspace_number"),
        sa.CheckConstraint("status IN ('DRAFT', 'SIGNED')", name="ck_acts_status"))
    for table in ("organizations", "invoices", "invoice_payments", "acts"):
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])


def downgrade():
    for table in ("acts", "invoice_payments", "invoices", "finance_counters", "organizations"):
        op.drop_table(table)
