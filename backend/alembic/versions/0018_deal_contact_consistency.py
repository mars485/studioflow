"""Reconcile primary contact representations without removing any contacts or links."""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        INSERT INTO deal_contacts (workspace_id, deal_id, contact_id, is_primary)
        SELECT workspace_id, id, contact_id, false FROM deals WHERE contact_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        UPDATE deals d SET contact_id = chosen.contact_id
        FROM (
            SELECT DISTINCT ON (dc.workspace_id, dc.deal_id) dc.workspace_id, dc.deal_id, dc.contact_id
            FROM deal_contacts dc JOIN deals old ON old.workspace_id = dc.workspace_id AND old.id = dc.deal_id
            ORDER BY dc.workspace_id, dc.deal_id, dc.is_primary DESC,
                     (dc.contact_id = old.contact_id) DESC NULLS LAST, dc.created_at, dc.contact_id
        ) chosen WHERE d.workspace_id = chosen.workspace_id AND d.id = chosen.deal_id
    """)
    op.execute("UPDATE deal_contacts SET is_primary = false WHERE is_primary")
    op.execute("""
        UPDATE deal_contacts dc SET is_primary = true FROM deals d
        WHERE dc.workspace_id = d.workspace_id AND dc.deal_id = d.id AND dc.contact_id = d.contact_id
    """)
    op.execute("""
        UPDATE deals d SET contact_name = concat_ws(' ', c.last_name, c.first_name, c.middle_name)
        FROM contacts c WHERE c.workspace_id = d.workspace_id AND c.id = d.contact_id
    """)


def downgrade():
    # Keep reconciled user data; no schema changes to undo.
    pass
