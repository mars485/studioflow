from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import workspace_access
from app.core.database import get_db
from app.models import Client, Contact, Deal, PipelineStage, Project, Task, TaskStatus

router = APIRouter(prefix='/workspaces/{workspace_id}/search', tags=['Search'])


@router.get('')
async def search(q: str = Query(min_length=2, max_length=255), kind: Literal['all', 'deal', 'client', 'contact', 'task', 'project'] = 'all',
                 workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db),
                 limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    term = q.strip()
    if len(term) < 2:
        return {'items': [], 'total': 0}
    pattern = '%' + term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
    def matches(*columns):
        return or_(*(column.ilike(pattern, escape='\\') for column in columns))
    queries = {
        'deal': select(literal('deal').label('kind'), Deal.id.label('id'), Deal.title.label('label'), PipelineStage.name.label('state'))
            .join(PipelineStage, (PipelineStage.workspace_id == Deal.workspace_id) & (PipelineStage.id == Deal.stage_id))
            .where(Deal.workspace_id == workspace_id, matches(Deal.title, Deal.source, Deal.contact_name)),
        'client': select(literal('client').label('kind'), Client.id.label('id'), Client.name.label('label'), literal('Компания').label('state'))
            .where(Client.workspace_id == workspace_id, matches(Client.name, Client.phone, Client.email)),
        'contact': select(literal('contact').label('kind'), Contact.id.label('id'),
            func.concat_ws(' ', Contact.last_name, Contact.first_name, Contact.middle_name).label('label'), literal('Контакт').label('state'))
            .where(Contact.workspace_id == workspace_id, matches(func.concat_ws(' ', Contact.last_name, Contact.first_name, Contact.middle_name), Contact.phone, Contact.email)),
        'task': select(literal('task').label('kind'), Task.id.label('id'), Task.title.label('label'), TaskStatus.name.label('state'))
            .join(TaskStatus, (TaskStatus.workspace_id == Task.workspace_id) & (TaskStatus.id == Task.status_id))
            .where(Task.workspace_id == workspace_id, matches(Task.title, Task.description)),
        'project': select(literal('project').label('kind'), Project.id.label('id'), Project.title.label('label'), Project.status.label('state'))
            .where(Project.workspace_id == workspace_id, matches(Project.title)),
    }
    combined = union_all(*(queries.values() if kind == 'all' else [queries[kind]])).subquery()
    total = await db.scalar(select(func.count()).select_from(combined))
    rows = (await db.execute(select(combined).order_by(combined.c.kind, combined.c.label, combined.c.id).limit(limit).offset(offset))).mappings().all()
    return {'items': [dict(row) for row in rows], 'total': total}
