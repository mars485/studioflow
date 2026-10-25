from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import current_user, workspace_access, workspace_admin
from app.api.v1.projects import add_event, find_project
from app.api.v1.project_work import work_rows
from app.api.v1.schemas import Name, Output
from app.core.database import get_db
from app.models import User
from app.models.project_templates import ProjectTemplate
from app.services.project_templates import PhaseBlueprint, snapshot_plan

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["Project templates"])


class TemplateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    description: str | None = Field(default=None, max_length=10000)


class TemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name | None = None
    description: str | None = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def fields(self):
        if not self.model_fields_set or ("name" in self.model_fields_set and self.name is None):
            raise ValueError("Укажите изменения; название не может быть null")
        return self


class TemplateOut(Output):
    id: UUID
    name: str
    description: str | None
    phases: list[PhaseBlueprint]
    source_project_title: str
    created_by_name: str
    created_at: datetime


@router.get("/project-templates", response_model=list[TemplateOut])
async def templates(workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    return (await db.scalars(select(ProjectTemplate).where(ProjectTemplate.workspace_id == workspace_id)
                             .order_by(ProjectTemplate.name, ProjectTemplate.id))).all()


@router.post("/projects/{project_id}/template", response_model=TemplateOut, status_code=201)
async def save_template(project_id: UUID, data: TemplateInput, workspace_id: UUID = Depends(workspace_admin),
                         user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    project, _ = await find_project(db, workspace_id, project_id, lock=True)
    count = await db.scalar(select(func.count()).where(ProjectTemplate.workspace_id == workspace_id))
    if count >= 200:
        raise HTTPException(409, "Не более 200 шаблонов в студии")
    row = ProjectTemplate(workspace_id=workspace_id, **data.model_dump(), source_project_title=project.title,
        phases=snapshot_plan(await work_rows(db, workspace_id, project_id)), created_by_user_id=user.id,
        created_by_name=" ".join(filter(None, (user.first_name, user.last_name))))
    db.add(row)
    await add_event(db, workspace_id, project_id, user, f"План сохранён как шаблон «{data.name}»", "TEMPLATE")
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Шаблон с таким названием уже есть")
    await db.refresh(row)
    return row


async def find_template(db, workspace_id, template_id):
    row = await db.scalar(select(ProjectTemplate).where(ProjectTemplate.workspace_id == workspace_id,
        ProjectTemplate.id == template_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Шаблон проекта не найден")
    return row


@router.patch("/project-templates/{template_id}", response_model=TemplateOut)
async def update_template(template_id: UUID, data: TemplateUpdate, workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    row = await find_template(db, workspace_id, template_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Шаблон с таким названием уже есть")
    await db.refresh(row)
    return row


@router.delete("/project-templates/{template_id}", status_code=204)
async def delete_template(template_id: UUID, workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    await db.delete(await find_template(db, workspace_id, template_id))
    await db.commit()
    return Response(status_code=204)
