"""Add workspace project module: stages, projects, members, contacts, events and task links."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

DEFAULT_STAGES = [("Подготовка", 0), ("В работе", 1), ("Сдача", 2), ("Завершён", 3)]


def upgrade():
    op.create_table("project_stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "id", name="uq_project_stages_workspace_id"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_project_stages_workspace_name"),
    )
    op.create_index("ix_project_stages_workspace_id", "project_stages", ["workspace_id"])

    op.create_table("projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("deals.id", ondelete="SET NULL", name="fk_projects_deal")),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manager_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="RUB"),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("status", sa.String(10), nullable=False, server_default="ACTIVE"),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id", "client_id"], ["clients.workspace_id", "clients.id"], name="fk_projects_workspace_client", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id", "stage_id"], ["project_stages.workspace_id", "project_stages.id"], name="fk_projects_workspace_stage", ondelete="RESTRICT"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_projects_workspace_id"),
        sa.CheckConstraint("status IN ('ACTIVE', 'ARCHIVED', 'COMPLETED')", name="ck_projects_status"),
        sa.CheckConstraint("amount >= 0", name="ck_projects_amount"),
        sa.CheckConstraint("start_date IS NULL OR end_date IS NULL OR start_date <= end_date", name="ck_projects_date_order"),
    )
    for column in ("workspace_id", "client_id", "deal_id", "stage_id"):
        op.create_index(f"ix_projects_{column}", "projects", [column])

    op.create_table("project_members",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="MEMBER"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id", "project_id"], ["projects.workspace_id", "projects.id"], name="fk_project_members_workspace_project", ondelete="CASCADE"),
        sa.CheckConstraint("role IN ('LEAD', 'MEMBER')", name="ck_project_members_role"),
    )

    op.create_table("project_contacts",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id", "project_id"], ["projects.workspace_id", "projects.id"], name="fk_project_contacts_workspace_project", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id", "contact_id"], ["contacts.workspace_id", "contacts.id"], name="fk_project_contacts_workspace_contact", ondelete="CASCADE"),
    )

    op.create_table("project_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("author_name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False, server_default="NOTE"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id", "project_id"], ["projects.workspace_id", "projects.id"], name="fk_project_events_workspace_project", ondelete="CASCADE"),
        sa.CheckConstraint("length(trim(body)) > 0", name="ck_project_events_body"),
    )
    op.create_index("ix_project_events_workspace_id", "project_events", ["workspace_id"])
    op.create_index("ix_project_events_project_id", "project_events", ["project_id"])

    values = ", ".join(f"('{name}', {position})" for name, position in DEFAULT_STAGES)
    op.execute(f"INSERT INTO project_stages (id, workspace_id, name, position) "
               f"SELECT gen_random_uuid(), w.id, s.name, s.position FROM workspaces w "
               f"CROSS JOIN (VALUES {values}) AS s(name, position)")

    op.add_column("tasks", sa.Column("project_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key("fk_tasks_project", "tasks", "projects", ["project_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
    op.drop_constraint("fk_tasks_workspace_contact", "tasks", type_="foreignkey")
    op.create_foreign_key("fk_tasks_contact", "tasks", "contacts", ["contact_id"], ["id"], ondelete="SET NULL")


def downgrade():
    op.drop_constraint("fk_tasks_contact", "tasks", type_="foreignkey")
    op.create_foreign_key("fk_tasks_workspace_contact", "tasks", "contacts",
                          ["workspace_id", "contact_id"], ["workspace_id", "id"], ondelete="SET NULL")
    op.drop_index("ix_tasks_project_id", table_name="tasks")
    op.drop_constraint("fk_tasks_project", "tasks", type_="foreignkey")
    op.drop_column("tasks", "project_id")
    op.drop_table("project_events")
    op.drop_table("project_contacts")
    op.drop_table("project_members")
    for column in ("stage_id", "deal_id", "client_id", "workspace_id"):
        op.drop_index(f"ix_projects_{column}", table_name="projects")
    op.drop_table("projects")
    op.drop_index("ix_project_stages_workspace_id", table_name="project_stages")
    op.drop_table("project_stages")
