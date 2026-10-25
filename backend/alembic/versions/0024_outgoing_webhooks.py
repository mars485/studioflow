"""Transactional webhook deliveries, operator-controlled destinations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('webhook_subscriptions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', UUID(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_by_user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('destination', sa.String(100), nullable=False), sa.Column('events', JSONB(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_webhook_subscriptions_workspace'),
        sa.UniqueConstraint('workspace_id', 'destination', name='uq_webhook_subscriptions_destination'),
        sa.ForeignKeyConstraint(['workspace_id', 'created_by_user_id'], ['workspace_members.workspace_id', 'workspace_members.user_id'],
            name='fk_webhook_subscriptions_issuer', ondelete='CASCADE'))
    op.create_table('webhook_deliveries',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', UUID(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('subscription_id', UUID(as_uuid=True), nullable=False), sa.Column('event_id', UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(30), nullable=False), sa.Column('payload', JSONB(), nullable=False),
        sa.Column('status', sa.String(10), nullable=False, server_default='PENDING'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('last_result', sa.String(40)), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['workspace_id', 'subscription_id'], ['webhook_subscriptions.workspace_id', 'webhook_subscriptions.id'],
            name='fk_webhook_deliveries_subscription', ondelete='CASCADE'),
        sa.UniqueConstraint('subscription_id', 'event_id', name='uq_webhook_deliveries_event'),
        sa.CheckConstraint("status IN ('PENDING', 'SENT', 'FAILED', 'CANCELLED')", name='ck_webhook_deliveries_status'),
        sa.CheckConstraint('attempts >= 0', name='ck_webhook_deliveries_attempts'))
    for table in ('webhook_subscriptions', 'webhook_deliveries'):
        op.create_index(f'ix_{table}_workspace_id', table, ['workspace_id'])
    op.create_index('ix_webhook_deliveries_next_attempt_at', 'webhook_deliveries', ['next_attempt_at'])


def downgrade():
    op.drop_table('webhook_deliveries')
    op.drop_table('webhook_subscriptions')
