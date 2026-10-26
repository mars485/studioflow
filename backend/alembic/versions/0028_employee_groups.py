"""Workspace employee groups with deny-only module writes; preserve existing roles."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('employee_groups',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', UUID(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.String(1000), nullable=False, server_default=''),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_employee_groups_workspace_id'),
        sa.UniqueConstraint('workspace_id', 'name', name='uq_employee_groups_workspace_name'),
        sa.CheckConstraint('version > 0', name='ck_employee_groups_version'))
    op.create_index('ix_employee_groups_workspace_id', 'employee_groups', ['workspace_id'])
    op.create_table('employee_group_members',
        sa.Column('workspace_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('group_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), primary_key=True),
        sa.ForeignKeyConstraint(['workspace_id', 'group_id'], ['employee_groups.workspace_id', 'employee_groups.id'], name='fk_employee_group_members_group', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id', 'user_id'], ['workspace_members.workspace_id', 'workspace_members.user_id'], name='fk_employee_group_members_membership', ondelete='CASCADE'))
    op.create_index('ix_employee_group_members_user', 'employee_group_members', ['workspace_id', 'user_id'])
    op.create_table('employee_group_blocks',
        sa.Column('workspace_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('group_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('action', sa.String(30), primary_key=True),
        sa.ForeignKeyConstraint(['workspace_id', 'group_id'], ['employee_groups.workspace_id', 'employee_groups.id'], name='fk_employee_group_blocks_group', ondelete='CASCADE'),
        sa.CheckConstraint("action IN ('crm.write','clients.write','tasks.write','projects.write','finance.write','integrations.write')", name='ck_employee_group_blocks_action'))
    op.create_table('group_audit',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', UUID(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('group_id', UUID(as_uuid=True), nullable=False),
        sa.Column('actor_id', UUID(as_uuid=True), nullable=False),
        sa.Column('actor_name', sa.String(255), nullable=False),
        sa.Column('action', sa.String(10), nullable=False), sa.Column('fields', JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("action IN ('CREATED','UPDATED','DELETED')", name='ck_group_audit_action'))
    op.create_index('ix_group_audit_workspace_time', 'group_audit', ['workspace_id', 'created_at', 'id'])


def downgrade():
    for table in ('group_audit', 'employee_group_blocks', 'employee_group_members', 'employee_groups'):
        op.drop_table(table)
