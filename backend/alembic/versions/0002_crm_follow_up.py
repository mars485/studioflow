"""Persist CRM details and enforce workspace relationships.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("deals", sa.Column("contact_name", sa.String(255)))
    op.add_column("deals", sa.Column("source", sa.String(100)))
    op.add_column("deals", sa.Column("follow_up_at", sa.DateTime(timezone=True)))
    op.add_column("deals", sa.Column("follow_up_action", sa.String(20)))
    op.add_column("deals", sa.Column("follow_up_comment", sa.Text()))
    op.create_unique_constraint("uq_clients_workspace_id", "clients", ["workspace_id", "id"])
    op.create_unique_constraint("uq_pipelines_workspace_id", "pipelines", ["workspace_id", "id"])
    op.create_unique_constraint("uq_stages_workspace_pipeline_id", "pipeline_stages", ["workspace_id", "pipeline_id", "id"])
    op.create_foreign_key("fk_stages_workspace_pipeline", "pipeline_stages", "pipelines",
                          ["workspace_id", "pipeline_id"], ["workspace_id", "id"], ondelete="CASCADE")
    op.create_foreign_key("fk_deals_workspace_client", "deals", "clients",
                          ["workspace_id", "client_id"], ["workspace_id", "id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_deals_workspace_stage", "deals", "pipeline_stages",
                          ["workspace_id", "pipeline_id", "stage_id"],
                          ["workspace_id", "pipeline_id", "id"], ondelete="RESTRICT")
    op.create_check_constraint("ck_deals_amount", "deals", "amount >= 0")
    op.create_check_constraint("ck_deals_follow_up", "deals",
        "(follow_up_at IS NULL AND follow_up_action IS NULL AND follow_up_comment IS NULL) OR "
        "(follow_up_at IS NOT NULL AND follow_up_action IN ('call', 'message', 'proposal', 'decision') AND follow_up_action IS NOT NULL)")


def downgrade():
    for name in ("ck_deals_follow_up", "ck_deals_amount", "fk_deals_workspace_stage", "fk_deals_workspace_client"):
        op.drop_constraint(name, "deals")
    op.drop_constraint("fk_stages_workspace_pipeline", "pipeline_stages", type_="foreignkey")
    op.drop_constraint("uq_stages_workspace_pipeline_id", "pipeline_stages", type_="unique")
    op.drop_constraint("uq_pipelines_workspace_id", "pipelines", type_="unique")
    op.drop_constraint("uq_clients_workspace_id", "clients", type_="unique")
    for name in ("follow_up_comment", "follow_up_action", "follow_up_at", "source", "contact_name"):
        op.drop_column("deals", name)
