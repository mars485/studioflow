"""Restore DB tenant guards while retaining nullable source links on deletion."""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

LINKS = [("tasks", "project_id", "projects", "fk_tasks_workspace_project"),
         ("tasks", "contact_id", "contacts", "fk_tasks_workspace_contact"),
         ("tasks", "parent_task_id", "tasks", "fk_tasks_workspace_parent"),
         ("projects", "deal_id", "deals", "fk_projects_workspace_deal")]


def upgrade():
    # Fail on invalid historical links rather than silently changing user data.
    for table, column, target, name in LINKS:
        op.create_foreign_key(name, table, target, ["workspace_id", column], ["workspace_id", "id"],
                              deferrable=True, initially="DEFERRED")
    op.create_foreign_key("fk_tasks_parent", "tasks", "tasks", ["parent_task_id"], ["id"], ondelete="SET NULL")
    op.create_check_constraint("ck_tasks_not_own_parent", "tasks", "parent_task_id IS NULL OR parent_task_id <> id")


def downgrade():
    op.drop_constraint("ck_tasks_not_own_parent", "tasks", type_="check")
    op.drop_constraint("fk_tasks_parent", "tasks", type_="foreignkey")
    for table, _, _, name in reversed(LINKS):
        op.drop_constraint(name, table, type_="foreignkey")
