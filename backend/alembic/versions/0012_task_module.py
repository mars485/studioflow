"""Move deal tasks into a workspace task module with statuses, checklists and watchers."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

DEFAULTS = [
    ("Сделать", 0, False),
    ("В работе", 1, False),
    ("Ожидает контроля", 2, False),
    ("Завершено", 3, True),
]


def upgrade():
    op.create_table("task_statuses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "id", name="uq_task_statuses_workspace_id"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_task_statuses_workspace_name"),
    )
    op.create_index("ix_task_statuses_workspace_id", "task_statuses", ["workspace_id"])
    values = ", ".join(f"('{name}', {position}, {'true' if final else 'false'})" for name, position, final in DEFAULTS)
    op.execute(f"INSERT INTO task_statuses (id, workspace_id, name, position, is_final) "
               f"SELECT gen_random_uuid(), w.id, s.name, s.position, s.is_final FROM workspaces w "
               f"CROSS JOIN (VALUES {values}) AS s(name, position, is_final)")

    op.create_table("tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False, server_default="MEDIUM"),
        sa.Column("assignee_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("creator_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("completed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("start_at", sa.DateTime(timezone=True)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("estimate_minutes", sa.Integer()),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True)),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True)),
        sa.Column("parent_task_id", postgresql.UUID(as_uuid=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id", "status_id"], ["task_statuses.workspace_id", "task_statuses.id"], name="fk_tasks_workspace_status", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_tasks_workspace_deal", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id", "contact_id"], ["contacts.workspace_id", "contacts.id"], name="fk_tasks_workspace_contact", ondelete="SET NULL"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_tasks_workspace_id"),
        sa.CheckConstraint("priority IN ('LOW', 'MEDIUM', 'HIGH')", name="ck_tasks_priority"),
        sa.CheckConstraint("start_at IS NULL OR due_at IS NULL OR start_at <= due_at", name="ck_tasks_date_order"),
        sa.CheckConstraint("estimate_minutes IS NULL OR estimate_minutes >= 0", name="ck_tasks_estimate"),
    )
    for column in ("workspace_id", "status_id", "deal_id", "parent_task_id"):
        op.create_index(f"ix_tasks_{column}", "tasks", [column])

    op.create_table("task_checklist_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.String(500), nullable=False),
        sa.Column("is_done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"], name="fk_task_checklist_workspace_task", ondelete="CASCADE"),
        sa.CheckConstraint("length(trim(text)) > 0", name="ck_task_checklist_text"),
    )
    op.create_index("ix_task_checklist_items_workspace_id", "task_checklist_items", ["workspace_id"])
    op.create_index("ix_task_checklist_items_task_id", "task_checklist_items", ["task_id"])

    op.create_table("task_watchers",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"], name="fk_task_watchers_workspace_task", ondelete="CASCADE"),
    )

    op.execute("""
        INSERT INTO tasks (id, workspace_id, title, description, status_id, priority, assignee_user_id,
                           creator_user_id, completed_by_user_id, start_at, due_at, created_at, updated_at,
                           completed_at, deal_id)
        SELECT dt.id, dt.workspace_id, dt.title, dt.description,
               (SELECT ts.id FROM task_statuses ts
                 WHERE ts.workspace_id = dt.workspace_id AND ts.is_final = (dt.status = 'DONE')
                 ORDER BY ts.position LIMIT 1),
               dt.priority, dt.assignee_user_id, dt.created_by_user_id, dt.completed_by_user_id,
               dt.start_at, dt.due_at, dt.created_at, dt.updated_at, dt.completed_at, dt.deal_id
        FROM deal_tasks dt
    """)

    op.drop_constraint("fk_task_reminders_workspace_task", "task_reminders", type_="foreignkey")
    op.create_foreign_key("fk_task_reminders_workspace_task", "task_reminders", "tasks",
                          ["workspace_id", "task_id"], ["workspace_id", "id"], ondelete="CASCADE")
    op.drop_table("deal_tasks")


def downgrade():
    op.create_table("deal_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("priority", sa.String(10), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(10), nullable=False, server_default="OPEN"),
        sa.Column("assignee_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("completed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("start_at", sa.DateTime(timezone=True)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_deal_tasks_workspace_deal", ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_deal_tasks_workspace_id"),
        sa.CheckConstraint("priority IN ('LOW', 'MEDIUM', 'HIGH')", name="ck_deal_tasks_priority"),
        sa.CheckConstraint("status IN ('OPEN', 'DONE')", name="ck_deal_tasks_status"),
        sa.CheckConstraint("start_at IS NULL OR due_at IS NULL OR start_at <= due_at", name="ck_deal_tasks_date_order"),
    )
    op.create_index("ix_deal_tasks_workspace_id", "deal_tasks", ["workspace_id"])
    op.create_index("ix_deal_tasks_deal_id", "deal_tasks", ["deal_id"])

    op.execute("""
        INSERT INTO deal_tasks (id, workspace_id, deal_id, title, description, priority, status,
                                assignee_user_id, created_by_user_id, completed_by_user_id,
                                start_at, due_at, created_at, updated_at, completed_at)
        SELECT t.id, t.workspace_id, t.deal_id, t.title, t.description, t.priority,
               CASE WHEN ts.is_final THEN 'DONE' ELSE 'OPEN' END,
               t.assignee_user_id, t.creator_user_id, t.completed_by_user_id,
               t.start_at, t.due_at, t.created_at, t.updated_at, t.completed_at
        FROM tasks t JOIN task_statuses ts ON ts.id = t.status_id
        WHERE t.deal_id IS NOT NULL
    """)

    op.drop_constraint("fk_task_reminders_workspace_task", "task_reminders", type_="foreignkey")
    op.create_foreign_key("fk_task_reminders_workspace_task", "task_reminders", "deal_tasks",
                          ["workspace_id", "task_id"], ["workspace_id", "id"], ondelete="CASCADE")
    op.drop_table("task_watchers")
    op.drop_index("ix_task_checklist_items_task_id", table_name="task_checklist_items")
    op.drop_index("ix_task_checklist_items_workspace_id", table_name="task_checklist_items")
    op.drop_table("task_checklist_items")
    for column in ("parent_task_id", "deal_id", "status_id", "workspace_id"):
        op.drop_index(f"ix_tasks_{column}", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_task_statuses_workspace_id", table_name="task_statuses")
    op.drop_table("task_statuses")
