from datetime import date, datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import current_user, workspace_member
from app.api.v1.crm import find_task, lock_workspace
from app.core.database import get_db
from app.models import Task, User, Workspace, WorkspaceMember
from app.models.task_time import TaskTimeEntry
from app.services.task_time import finish_entry

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["Task time"])


class CommentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("comment")
    @classmethod
    def clean(cls, value):
        return (value.strip() or None) if value is not None else None


class ManualInput(CommentInput):
    request_key: UUID
    worked_on: date
    minutes: int = Field(ge=1, le=525600, strict=True)


class TimerInput(CommentInput):
    request_key: UUID


class TimeUpdate(CommentInput):
    worked_on: date | None = None
    minutes: int | None = Field(default=None, ge=1, le=525600, strict=True)

    @model_validator(mode="after")
    def required(self):
        if not self.model_fields_set or any(k in self.model_fields_set and getattr(self, k) is None for k in ("worked_on", "minutes")):
            raise ValueError("Укажите изменения; дата и минуты обязательны")
        return self


def output(row, title, actor):
    running = row.started_at is not None and row.ended_at is None
    return {"id": row.id, "task_id": row.task_id, "task_title": title, "user_id": row.user_id,
        "author_name": row.author_name, "request_key": row.request_key, "worked_on": row.worked_on,
        "seconds": row.seconds, "started_at": row.started_at, "ended_at": row.ended_at,
        "comment": row.comment, "stop_reason": row.stop_reason, "is_running": running,
        "elapsed_seconds": max(0, int((datetime.now(timezone.utc) - row.started_at).total_seconds())) if running else row.seconds,
        "can_edit": row.user_id == actor.user_id or actor.role in ("OWNER", "ADMIN")}


async def actor_locked(db, workspace_id, user_id):
    await lock_workspace(db, workspace_id)
    actor = await db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.user_id == user_id).execution_options(populate_existing=True))
    if actor is None:
        raise HTTPException(404, "Workspace not found")
    return actor


async def day(db, workspace_id):
    workspace = await db.get(Workspace, workspace_id)
    return workspace.timezone, datetime.now(timezone.utc).astimezone(ZoneInfo(workspace.timezone)).date()


async def entry(db, workspace_id, entry_id):
    result = (await db.execute(select(TaskTimeEntry, Task.title).join(Task,
        (Task.workspace_id == TaskTimeEntry.workspace_id) & (Task.id == TaskTimeEntry.task_id)).where(
        TaskTimeEntry.workspace_id == workspace_id, TaskTimeEntry.id == entry_id).with_for_update(of=TaskTimeEntry))).first()
    if result is None:
        raise HTTPException(404, "Запись времени не найдена")
    return result


def authorize(row, actor):
    if row.user_id != actor.user_id and actor.role not in ("OWNER", "ADMIN"):
        raise HTTPException(403, "Можно изменять только свои записи времени")


@router.get("/tasks/{task_id}/time-entries")
async def time_entries(workspace_id: UUID, task_id: UUID, actor: WorkspaceMember = Depends(workspace_member),
                       db: AsyncSession = Depends(get_db), limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    task, _ = await find_task(db, workspace_id, task_id)
    scope = (TaskTimeEntry.workspace_id == workspace_id, TaskTimeEntry.task_id == task_id)
    rows = (await db.scalars(select(TaskTimeEntry).where(*scope).order_by(
        TaskTimeEntry.worked_on.desc(), TaskTimeEntry.created_at.desc(), TaskTimeEntry.id).limit(limit).offset(offset))).all()
    total = await db.scalar(select(func.coalesce(func.sum(TaskTimeEntry.seconds), 0)).where(*scope))
    zone, today = await day(db, workspace_id)
    return {"items": [output(row, task.title, actor) for row in rows], "total_seconds": total, "timezone": zone, "today": today}


@router.get("/time-timer")
async def current_timer(workspace_id: UUID, actor: WorkspaceMember = Depends(workspace_member), db: AsyncSession = Depends(get_db)):
    result = (await db.execute(select(TaskTimeEntry, Task.title).join(Task,
        (Task.workspace_id == TaskTimeEntry.workspace_id) & (Task.id == TaskTimeEntry.task_id)).where(
        TaskTimeEntry.workspace_id == workspace_id, TaskTimeEntry.user_id == actor.user_id,
        TaskTimeEntry.started_at.is_not(None), TaskTimeEntry.ended_at.is_(None)))).first()
    return output(result[0], result[1], actor) if result else None


async def create(db, workspace_id, task_id, data, user, timer):
    actor = await actor_locked(db, workspace_id, user.id)
    task, status = await find_task(db, workspace_id, task_id, lock=True)
    existing = await db.scalar(select(TaskTimeEntry).where(TaskTimeEntry.workspace_id == workspace_id,
        TaskTimeEntry.user_id == user.id, TaskTimeEntry.request_key == data.request_key))
    if existing:
        matches = existing.task_id == task_id and (existing.started_at is not None) == timer and existing.comment == data.comment
        if not timer:
            matches = matches and existing.worked_on == data.worked_on and existing.seconds == data.minutes * 60
        if not matches:
            raise HTTPException(409, "Ключ операции уже использован с другими данными")
        return output(existing, task.title, actor)
    _, today = await day(db, workspace_id)
    if timer:
        if status.is_final:
            raise HTTPException(409, "Нельзя запустить таймер завершённой задачи")
        running = await db.scalar(select(TaskTimeEntry.id).where(TaskTimeEntry.workspace_id == workspace_id,
            TaskTimeEntry.user_id == user.id, TaskTimeEntry.started_at.is_not(None), TaskTimeEntry.ended_at.is_(None)).limit(1))
        if running:
            raise HTTPException(409, "Сначала остановите активный таймер этой студии")
    elif data.worked_on > today:
        raise HTTPException(422, "Нельзя записать время на будущую дату студии")
    row = TaskTimeEntry(workspace_id=workspace_id, task_id=task_id, user_id=user.id,
        author_name=" ".join(filter(None, (user.first_name, user.last_name))), request_key=data.request_key,
        worked_on=today if timer else data.worked_on, seconds=0 if timer else data.minutes * 60,
        started_at=datetime.now(timezone.utc) if timer else None, comment=data.comment)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return output(row, task.title, actor)


@router.post("/tasks/{task_id}/time-entries", status_code=201)
async def manual_time(workspace_id: UUID, task_id: UUID, data: ManualInput, user: User = Depends(current_user),
                      member: WorkspaceMember = Depends(workspace_member), db: AsyncSession = Depends(get_db)):
    return await create(db, workspace_id, task_id, data, user, False)


@router.post("/tasks/{task_id}/timer", status_code=201)
async def start_timer(workspace_id: UUID, task_id: UUID, data: TimerInput, user: User = Depends(current_user),
                      member: WorkspaceMember = Depends(workspace_member), db: AsyncSession = Depends(get_db)):
    return await create(db, workspace_id, task_id, data, user, True)


@router.post("/time-entries/{entry_id}/stop")
async def stop_timer(workspace_id: UUID, entry_id: UUID, user: User = Depends(current_user),
                     member: WorkspaceMember = Depends(workspace_member), db: AsyncSession = Depends(get_db)):
    actor = await actor_locked(db, workspace_id, user.id)
    row, title = await entry(db, workspace_id, entry_id)
    authorize(row, actor)
    if row.started_at is None:
        raise HTTPException(409, "Ручная запись не является таймером")
    finish_entry(row, "USER")
    await db.commit()
    await db.refresh(row)
    return output(row, title, actor)


@router.patch("/time-entries/{entry_id}")
async def update_time(workspace_id: UUID, entry_id: UUID, data: TimeUpdate, user: User = Depends(current_user),
                      member: WorkspaceMember = Depends(workspace_member), db: AsyncSession = Depends(get_db)):
    actor = await actor_locked(db, workspace_id, user.id)
    row, title = await entry(db, workspace_id, entry_id)
    authorize(row, actor)
    changes = data.model_dump(exclude_unset=True)
    if row.started_at is not None and (row.ended_at is None or {"minutes", "worked_on"} & changes.keys()):
        raise HTTPException(409, "Остановите таймер; его фактические даты и длительность неизменяемы")
    if "worked_on" in changes:
        _, today = await day(db, workspace_id)
        if data.worked_on > today:
            raise HTTPException(422, "Нельзя записать время на будущую дату студии")
        row.worked_on = data.worked_on
    if "minutes" in changes:
        row.seconds = data.minutes * 60
    if "comment" in changes:
        row.comment = data.comment
    await db.commit()
    await db.refresh(row)
    return output(row, title, actor)


@router.delete("/time-entries/{entry_id}", status_code=204)
async def delete_time(workspace_id: UUID, entry_id: UUID, user: User = Depends(current_user),
                      member: WorkspaceMember = Depends(workspace_member), db: AsyncSession = Depends(get_db)):
    actor = await actor_locked(db, workspace_id, user.id)
    row, _ = await entry(db, workspace_id, entry_id)
    authorize(row, actor)
    if row.started_at is not None and row.ended_at is None:
        raise HTTPException(409, "Сначала остановите таймер")
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)
