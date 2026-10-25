import csv
import io
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import workspace_admin
from app.core.database import get_db
from app.models import Client, Contact, Deal, Pipeline, PipelineStage

router = APIRouter(prefix='/workspaces/{workspace_id}/exports', tags=['CSV exports'])


def safe_cell(value):
    text = '' if value is None else str(value)
    stripped = text.lstrip(' \t\r\n\ufeff')
    if (stripped and stripped[0] in '=+-@') or (text and text[0] in '\t\r\n'):
        return "'" + text
    return text


@router.get('/{entity}.csv')
async def export_csv(entity: Literal['deals', 'clients', 'contacts'], pipeline_id: UUID | None = None,
                     workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    if entity == 'deals':
        query = select(Deal.id, Deal.title, Client.name, Pipeline.name, PipelineStage.name, Deal.amount, Deal.currency,
            Deal.source, Deal.responsible_user_id, Deal.start_date, Deal.end_date, Deal.follow_up_at, Deal.created_at)
        query = query.join(Client, (Client.workspace_id == Deal.workspace_id) & (Client.id == Deal.client_id))
        query = query.join(Pipeline, (Pipeline.workspace_id == Deal.workspace_id) & (Pipeline.id == Deal.pipeline_id))
        query = query.join(PipelineStage, (PipelineStage.workspace_id == Deal.workspace_id) & (PipelineStage.id == Deal.stage_id))
        query = query.where(Deal.workspace_id == workspace_id).order_by(Deal.created_at, Deal.id)
        if pipeline_id is not None:
            if await db.scalar(select(Pipeline.id).where(Pipeline.workspace_id == workspace_id, Pipeline.id == pipeline_id)) is None:
                raise HTTPException(404, 'Воронка не найдена')
            query = query.where(Deal.pipeline_id == pipeline_id)
        headers = ['id', 'title', 'client', 'pipeline', 'stage', 'amount', 'currency', 'source', 'responsible_user_id',
            'start_date', 'end_date', 'follow_up_at', 'created_at']
    elif entity == 'clients':
        query = select(Client.id, Client.name, Client.phone, Client.email, Client.website, Client.notes).where(
            Client.workspace_id == workspace_id).order_by(Client.name, Client.id)
        headers = ['id', 'name', 'phone', 'email', 'website', 'notes']
    else:
        query = select(Contact.id, Contact.last_name, Contact.first_name, Contact.middle_name, Contact.phone,
            Contact.email, Contact.website, Contact.notes).where(Contact.workspace_id == workspace_id).order_by(Contact.id)
        headers = ['id', 'last_name', 'first_name', 'middle_name', 'phone', 'email', 'website', 'notes']
    rows = (await db.execute(query.limit(5001))).all()
    if len(rows) > 5000:
        raise HTTPException(413, 'Выгрузка ограничена 5000 строками; для сделок выберите отдельную воронку')
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer, delimiter=';', quoting=csv.QUOTE_ALL)
    writer.writerow(headers)
    writer.writerows([safe_cell(value) for value in row] for row in rows)
    return Response(content=('\ufeff' + buffer.getvalue()).encode('utf-8'), media_type='text/csv; charset=utf-8', headers={
        'Content-Disposition': f'attachment; filename="studioflow-{entity}.csv"',
        'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})
