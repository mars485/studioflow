from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import ConfigDict, Field, BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import current_user, workspace_access, workspace_admin
from app.api.v1.crm import validate_workspace_member
from app.api.v1.projects import add_event, find_project
from app.api.v1.schemas import Name, Output
from app.core.database import get_db
from app.models import User
from app.models.project_work import ProjectWorkStage

router = APIRouter(prefix="/workspaces/{workspace_id}/projects/{project_id}/work-plan", tags=["Project work plan"])


class WorkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Name
    status: Literal["PLANNED", "ACTIVE", "DONE"] = "PLANNED"
    manager_user_id: UUID | None = None
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def dates(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("Начало этапа не может быть позже окончания")
        return self


class WorkUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Name | None = None
    status: Literal["PLANNED", "ACTIVE", "DONE"] | None = None
    manager_user_id: UUID | None = None
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def required(self):
        if not self.model_fields_set or any(key in self.model_fields_set and getattr(self, key) is None for key in ("title", "status")):
            raise ValueError("Укажите изменения; название и статус не могут быть null")
        return self


class WorkOut(Output):
    id: UUID
    project_id: UUID
    title: str
    position: int
    status: Literal["PLANNED", "ACTIVE", "DONE"]
    manager_user_id: UUID | None
    start_date: date | None
    end_date: date | None


class WorkOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[UUID] = Field(max_length=500)

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.ids)) != len(self.ids):
            raise ValueError("Идентификаторы этапов должны быть уникальны")
        return self


async def editable_project(db, workspace_id, project_id):
    project, _ = await find_project(db, workspace_id, project_id, lock=True)
    if project.status == "ARCHIVED":
        raise HTTPException(409, "План архивного проекта доступен только для чтения")
    return project


async def work_rows(db, workspace_id, project_id):
    return (await db.scalars(select(ProjectWorkStage).where(ProjectWorkStage.workspace_id == workspace_id,
        ProjectWorkStage.project_id == project_id).order_by(ProjectWorkStage.position, ProjectWorkStage.id))).all()


async def find_work(db, workspace_id, project_id, stage_id):
    row = await db.scalar(select(ProjectWorkStage).where(ProjectWorkStage.workspace_id == workspace_id,
        ProjectWorkStage.project_id == project_id, ProjectWorkStage.id == stage_id))
    if row is None:
        raise HTTPException(404, "Этап работ не найден")
    return row


@router.get("", response_model=list[WorkOut])
async def work_plan(project_id: UUID, workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    await find_project(db, workspace_id, project_id)
    return await work_rows(db, workspace_id, project_id)


@router.post("", response_model=WorkOut, status_code=201)
async def create_work(project_id: UUID, data: WorkCreate, workspace_id: UUID = Depends(workspace_access),
                       user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await editable_project(db, workspace_id, project_id)
    rows = await work_rows(db, workspace_id, project_id)
    if len(rows) >= 500:
        raise HTTPException(409, "Не более 500 этапов в проекте")
    if data.manager_user_id is not None:
        await validate_workspace_member(db, workspace_id, data.manager_user_id, "Ответственный должен быть участником студии")
    row = ProjectWorkStage(workspace_id=workspace_id, project_id=project_id,
        position=max((r.position for r in rows), default=-1) + 1, **data.model_dump())
    db.add(row)
    await add_event(db, workspace_id, project_id, user, f"Добавлен этап работ «{row.title}»", "WORK_PLAN")
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/order", response_model=list[WorkOut])
async def reorder_work(project_id: UUID, data: WorkOrder, workspace_id: UUID = Depends(workspace_access),
                        user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await editable_project(db, workspace_id, project_id)
    rows = await work_rows(db, workspace_id, project_id)
    if set(data.ids) != {row.id for row in rows}:
        raise HTTPException(422, "Перечислите все этапы проекта")
    by_id = {row.id: row for row in rows}
    for index, stage_id in enumerate(data.ids):
        by_id[stage_id].position = index
    await add_event(db, workspace_id, project_id, user, "Изменён порядок этапов работ", "WORK_PLAN")
    await db.commit()
    return await work_rows(db, workspace_id, project_id)


@router.patch("/{stage_id}", response_model=WorkOut)
async def update_work(project_id: UUID, stage_id: UUID, data: WorkUpdate, workspace_id: UUID = Depends(workspace_access),
                       user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await editable_project(db, workspace_id, project_id)
    row = await find_work(db, workspace_id, project_id, stage_id)
    changes = data.model_dump(exclude_unset=True)
    start, end = changes.get("start_date", row.start_date), changes.get("end_date", row.end_date)
    if start and end and start > end:
        raise HTTPException(422, "Начало этапа не может быть позже окончания")
    if changes.get("manager_user_id") is not None:
        await validate_workspace_member(db, workspace_id, changes["manager_user_id"], "Ответственный должен быть участником студии")
    for key, value in changes.items():
        setattr(row, key, value)
    await add_event(db, workspace_id, project_id, user, f"Изменён этап работ «{row.title}»", "WORK_PLAN")
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{stage_id}", status_code=204)
async def delete_work(project_id: UUID, stage_id: UUID, workspace_id: UUID = Depends(workspace_admin),
                       user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await editable_project(db, workspace_id, project_id)
    row = await find_work(db, workspace_id, project_id, stage_id)
    await add_event(db, workspace_id, project_id, user, f"Удалён этап работ «{row.title}»", "WORK_PLAN")
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)
