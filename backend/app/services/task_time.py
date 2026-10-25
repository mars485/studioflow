from datetime import datetime, timezone
from sqlalchemy import select
from app.models.task_time import TaskTimeEntry


def finish_entry(row: TaskTimeEntry, reason: str, now: datetime | None = None):
    if row.started_at is None or row.ended_at is not None:
        return
    end = max(now or datetime.now(timezone.utc), row.started_at)
    row.ended_at = end
    row.seconds = max(0, int((end - row.started_at).total_seconds()))
    row.stop_reason = reason


async def stop_timers(db, workspace_id, *, task_id=None, user_id=None, reason):
    query = select(TaskTimeEntry).where(TaskTimeEntry.workspace_id == workspace_id,
        TaskTimeEntry.started_at.is_not(None), TaskTimeEntry.ended_at.is_(None))
    if task_id is not None:
        query = query.where(TaskTimeEntry.task_id == task_id)
    if user_id is not None:
        query = query.where(TaskTimeEntry.user_id == user_id)
    rows = (await db.scalars(query.with_for_update())).all()
    now = datetime.now(timezone.utc)
    for row in rows:
        finish_entry(row, reason, now)
