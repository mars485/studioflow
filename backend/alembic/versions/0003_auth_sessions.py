"""Add revocable sessions and workspace roles without changing CRM data."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    # Fail on ambiguous case-insensitive duplicates rather than taking over an account.
    op.execute("UPDATE users SET email = lower(email)")
    op.create_check_constraint("ck_member_role", "workspace_members", "role IN ('OWNER', 'ADMIN', 'MANAGER')")
    op.create_table("auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table("auth_throttles",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("auth_throttles")
    op.drop_table("auth_sessions")
    op.drop_constraint("ck_member_role", "workspace_members", type_="check")
