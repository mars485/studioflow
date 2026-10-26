"""Keep original contact profiles and relationships for explicit merges."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('contact_merges',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', UUID(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('request_key', UUID(as_uuid=True), nullable=False),
        sa.Column('request_digest', sa.String(64), nullable=False),
        sa.Column('source_id', UUID(as_uuid=True), nullable=False),
        sa.Column('target_id', UUID(as_uuid=True), nullable=False),
        sa.Column('actor_id', UUID(as_uuid=True), nullable=False),
        sa.Column('actor_name', sa.String(255), nullable=False),
        sa.Column('snapshot', JSONB(), nullable=False),
        sa.Column('source_fields', JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('workspace_id', 'request_key', name='uq_contact_merges_request_key'),
        sa.CheckConstraint('source_id <> target_id', name='ck_contact_merges_distinct'))
    op.create_index('ix_contact_merges_workspace_target', 'contact_merges', ['workspace_id', 'target_id', 'created_at'])


def downgrade():
    op.drop_table('contact_merges')
