from datetime import timedelta
from sqlalchemy import select
from app.models import Project, Task, TaskChecklistItem, TaskStatus, WorkspaceMember
from app.models.task_recurrence import TaskRecurrence


async def repeat_completed_task(db, task, user):
    # Caller holds workspace then task lock, in the same completion transaction.
    rule = await db.scalar(select(TaskRecurrence).where(TaskRecurrence.workspace_id == task.workspace_id,
        TaskRecurrence.task_id == task.id).with_for_update())
    if rule is None or not rule.enabled or rule.processed:
        return
    rule.processed = True
    if task.parent_task_id is not None:
        rule.stop_reason = 'CHILD_TASK'
        return
    if task.project_id is not None:
        project = await db.get(Project, task.project_id)
        if project is None or project.status == 'ARCHIVED':
            rule.stop_reason = 'PROJECT_ARCHIVED'
            return
    status = await db.scalar(select(TaskStatus).where(TaskStatus.workspace_id == task.workspace_id,
        TaskStatus.is_final.is_(False)).order_by(TaskStatus.position, TaskStatus.id).limit(1))
    if status is None:
        rule.stop_reason = 'NO_OPEN_STATUS'
        return
    assignee = task.assignee_user_id
    if assignee is not None and await db.scalar(select(WorkspaceMember.id).where(
        WorkspaceMember.workspace_id == task.workspace_id, WorkspaceMember.user_id == assignee)) is None:
        assignee = None
    start = task.completed_at + timedelta(days=rule.interval_days)
    span = max(task.due_at - (task.start_at or task.completed_at), timedelta()) if task.due_at else None
    successor = Task(workspace_id=task.workspace_id, title=task.title, description=task.description,
        priority=task.priority, status_id=status.id, creator_user_id=user.id, assignee_user_id=assignee,
        start_at=start, due_at=start + span if span is not None else None, estimate_minutes=task.estimate_minutes,
        deal_id=task.deal_id, project_id=task.project_id, contact_id=task.contact_id)
    db.add(successor)
    await db.flush()
    rule.next_task_id = successor.id
    items = (await db.scalars(select(TaskChecklistItem).where(TaskChecklistItem.workspace_id == task.workspace_id,
        TaskChecklistItem.task_id == task.id).order_by(TaskChecklistItem.position, TaskChecklistItem.id))).all()
    for item in items:
        db.add(TaskChecklistItem(workspace_id=task.workspace_id, task_id=successor.id, text=item.text,
            position=item.position, is_done=False))
    if rule.remaining > 1:
        db.add(TaskRecurrence(workspace_id=task.workspace_id, task_id=successor.id,
            interval_days=rule.interval_days, remaining=rule.remaining - 1))
