"""Retain structured source/consent context without inventing historical consent."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('incoming_leads', sa.Column('website_context', JSONB(), nullable=True))


def downgrade():
    op.drop_column('incoming_leads', 'website_context')
