"""Add optional deal start and end dates."""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("deals", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("deals", sa.Column("end_date", sa.Date(), nullable=True))
    op.create_check_constraint("ck_deals_date_order", "deals",
        "start_date IS NULL OR end_date IS NULL OR start_date <= end_date")


def downgrade():
    op.drop_constraint("ck_deals_date_order", "deals", type_="check")
    op.drop_column("deals", "end_date")
    op.drop_column("deals", "start_date")
