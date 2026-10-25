from datetime import timedelta
from typing import Annotated
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, ValidationError, model_validator
from sqlalchemy import select
from app.models.project_templates import ProjectTemplate
from app.models.project_work import ProjectWorkStage


class PhaseBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    start_offset: int | None = Field(default=None, ge=0, le=3650)
    end_offset: int | None = Field(default=None, ge=0, le=3650)

    @model_validator(mode="after")
    def dates(self):
        if self.start_offset is not None and self.end_offset is not None and self.start_offset > self.end_offset:
            raise ValueError("Неверный порядок смещений")
        return self


Blueprints = TypeAdapter(Annotated[list[PhaseBlueprint], Field(min_length=1, max_length=500)])


def snapshot_plan(rows):
    dates = [value for row in rows for value in (row.start_date, row.end_date) if value is not None]
    base = min(dates) if dates else None
    try:
        result = Blueprints.validate_python([{"title": row.title,
            "start_offset": (row.start_date - base).days if row.start_date else None,
            "end_offset": (row.end_date - base).days if row.end_date else None} for row in rows])
    except ValidationError:
        raise HTTPException(422, "Шаблон требует 1–500 этапов и смещения дат не более 10 лет")
    return [row.model_dump() for row in result]


async def apply_template(db, workspace_id, project, template_id):
    template = await db.scalar(select(ProjectTemplate).where(ProjectTemplate.workspace_id == workspace_id, ProjectTemplate.id == template_id))
    if template is None:
        raise HTTPException(404, "Шаблон проекта не найден")
    if project.start_date is None:
        raise HTTPException(422, "Укажите дату начала проекта по шаблону")
    try:
        phases = Blueprints.validate_python(template.phases)
    except ValidationError:
        raise HTTPException(409, "Шаблон содержит некорректный план")
    latest = None
    for position, phase in enumerate(phases):
        try:
            start = project.start_date + timedelta(days=phase.start_offset) if phase.start_offset is not None else None
            end = project.start_date + timedelta(days=phase.end_offset) if phase.end_offset is not None else None
        except OverflowError:
            raise HTTPException(422, "Даты плана выходят за допустимый диапазон")
        endpoint = end or start
        if endpoint is not None:
            latest = max(latest, endpoint) if latest else endpoint
        db.add(ProjectWorkStage(workspace_id=workspace_id, project_id=project.id, title=phase.title,
            position=position, start_date=start, end_date=end, status="PLANNED"))
    if latest and project.end_date and latest > project.end_date:
        raise HTTPException(422, "Конец проекта не может быть раньше конца плана по шаблону")
    if latest and project.end_date is None:
        project.end_date = latest
    return template.name
