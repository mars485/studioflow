from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import workspace_access
from app.api.v1.crm import find_task
from app.core.database import get_db
from app.models.task_recurrence import TaskRecurrence

router = APIRouter(prefix='/workspaces/{workspace_id}/tasks/{task_id}/recurrence', tags=['Task recurrence'])


class RecurrenceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    interval_days: int = Field(ge=1, le=365, strict=True)
    remaining: int = Field(ge=1, le=365, strict=True)
    enabled: bool = True


def output(row):
    return None if row is None else {key: getattr(row, key) for key in (
        'interval_days', 'remaining', 'enabled', 'processed', 'next_task_id', 'stop_reason')}


@router.get('')
async def get_recurrence(task_id: UUID, workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    await find_task(db, workspace_id, task_id)
    row = await db.scalar(select(TaskRecurrence).where(TaskRecurrence.workspace_id == workspace_id, TaskRecurrence.task_id == task_id))
    return output(row)


@router.put('')
async def set_recurrence(task_id: UUID, data: RecurrenceInput, workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    task, status = await find_task(db, workspace_id, task_id, lock=True)
    row = await db.scalar(select(TaskRecurrence).where(TaskRecurrence.workspace_id == workspace_id, TaskRecurrence.task_id == task_id))
    if task.parent_task_id is not None:
        raise HTTPException(409, 'Повторение подзадач не поддерживается')
    if status.is_final or (row is not None and row.processed):
        raise HTTPException(409, 'Настройте повторение на следующей незавершённой задаче')
    if row is None:
        row = TaskRecurrence(workspace_id=workspace_id, task_id=task_id)
        db.add(row)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return output(row)
