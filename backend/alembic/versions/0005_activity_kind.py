"""Distinguish deal notes from automatic stage changes."""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("deal_activities", sa.Column("kind", sa.String(20), server_default="NOTE", nullable=False))
    op.create_check_constraint("ck_activities_kind", "deal_activities", "kind IN ('NOTE', 'STAGE_CHANGE')")


def downgrade():
    op.drop_constraint("ck_activities_kind", "deal_activities", type_="check")
    op.drop_column("deal_activities", "kind")
