"""Minimal transactional audit of core deal mutations; no historical backfill."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = '0025'
down_revision = '0024'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('deal_audit',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', UUID(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('deal_id', UUID(as_uuid=True), nullable=False),
        sa.Column('actor_id', UUID(as_uuid=True), nullable=False),
        sa.Column('actor_kind', sa.String(12), nullable=False), sa.Column('actor_name', sa.String(255), nullable=False),
        sa.Column('action', sa.String(10), nullable=False), sa.Column('fields', JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("action IN ('CREATED', 'UPDATED', 'DELETED')", name='ck_deal_audit_action'),
        sa.CheckConstraint("actor_kind IN ('USER', 'INTEGRATION')", name='ck_deal_audit_actor'))
    op.create_index('ix_deal_audit_workspace_time', 'deal_audit', ['workspace_id', 'created_at', 'id'])
    op.create_index('ix_deal_audit_workspace_object', 'deal_audit', ['workspace_id', 'deal_id'])


def downgrade():
    op.drop_table('deal_audit')
