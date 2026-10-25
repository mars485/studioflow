from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import workspace_access
from app.core.database import get_db
from app.models import Client, Contact

router = APIRouter(prefix='/workspaces/{workspace_id}/duplicate-candidates', tags=['Duplicate candidates'])


def normalized_text(column):
    return func.lower(func.btrim(func.regexp_replace(func.coalesce(column, ''), r'\s+', ' ', 'g')))


@router.get('')
async def duplicate_candidates(kind: Literal['client', 'contact'], object_id: UUID,
                               workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db),
                               limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    model = Client if kind == 'client' else Contact
    label = model.name if kind == 'client' else func.concat_ws(' ', Contact.last_name, Contact.first_name, Contact.middle_name)
    expressions = {'email': func.lower(func.btrim(func.coalesce(model.email, ''))),
        'phone': func.regexp_replace(func.coalesce(model.phone, ''), '[^0-9]', '', 'g'),
        'name': normalized_text(label)}
    source = (await db.execute(select(model.id, label.label('label'), *(value.label(key) for key, value in expressions.items()))
        .where(model.workspace_id == workspace_id, model.id == object_id))).mappings().first()
    if source is None:
        raise HTTPException(404, 'Клиент не найден')
    predicates = {key: (expression == source[key]) if len(source[key]) >= (7 if key == 'phone' else 3) else literal(False)
                  for key, expression in expressions.items()}
    scope = (model.workspace_id == workspace_id, model.id != object_id, or_(*predicates.values()))
    total = await db.scalar(select(func.count()).select_from(model).where(*scope))
    rows = (await db.execute(select(model.id, label.label('label'), *(value.label(key) for key, value in predicates.items()))
        .where(*scope).order_by(label, model.id).limit(limit).offset(offset))).mappings().all()
    return {'source': {'id': source['id'], 'label': source['label']}, 'total': total,
        'items': [{'id': row['id'], 'label': row['label'], 'reasons': [key for key in predicates if row[key]]} for row in rows]}
