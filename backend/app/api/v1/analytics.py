from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import workspace_access
from app.core.database import get_db
from app.models import Deal, Pipeline, PipelineStage, Project, Task, TaskStatus, User, Workspace
from app.models.entities import StageType

router = APIRouter(prefix='/workspaces/{workspace_id}/analytics', tags=['Analytics'])


@router.get('')
async def analytics(workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db),
                    pipeline_id: UUID | None = None, from_date: date | None = None, to_date: date | None = None):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(422, 'Начало периода не может быть позже окончания')
    workspace = await db.get(Workspace, workspace_id)
    zone = ZoneInfo(workspace.timezone)
    scope = [Deal.workspace_id == workspace_id]
    if pipeline_id is not None:
        pipeline = await db.scalar(select(Pipeline.id).where(Pipeline.workspace_id == workspace_id, Pipeline.id == pipeline_id))
        if pipeline is None:
            raise HTTPException(404, 'Воронка не найдена')
        scope.append(Deal.pipeline_id == pipeline_id)
    if from_date:
        scope.append(Deal.created_at >= datetime.combine(from_date, time.min, zone).astimezone(timezone.utc))
    if to_date:
        if to_date == date.max:
            raise HTTPException(422, 'Конец периода должен быть раньше 9999-12-31')
        scope.append(Deal.created_at < datetime.combine(to_date + timedelta(days=1), time.min, zone).astimezone(timezone.utc))
    rows = (await db.execute(select(PipelineStage.id, PipelineStage.name, PipelineStage.stage_type,
        PipelineStage.pipeline_id, Pipeline.name, Deal.currency, func.count(Deal.id), func.sum(Deal.amount))
        .select_from(Deal).join(PipelineStage, (PipelineStage.workspace_id == Deal.workspace_id) & (PipelineStage.id == Deal.stage_id))
        .join(Pipeline, (Pipeline.workspace_id == Deal.workspace_id) & (Pipeline.id == Deal.pipeline_id))
        .where(*scope).group_by(PipelineStage.id, PipelineStage.name, PipelineStage.stage_type,
            PipelineStage.pipeline_id, Pipeline.name, PipelineStage.position, Deal.currency)
        .order_by(Pipeline.name, PipelineStage.position, Deal.currency))).all()
    counts = {'OPEN': 0, 'WON': 0, 'LOST': 0}
    stages = []
    for stage_id, name, kind, pipeline, pipeline_name, currency, count, amount in rows:
        counts[kind.value] += count
        stages.append({'stage_id': stage_id, 'name': name, 'stage_type': kind.value, 'pipeline_id': pipeline,
            'pipeline_name': pipeline_name, 'currency': currency, 'count': count, 'amount': str(amount)})
    managers = (await db.execute(select(Deal.responsible_user_id, User.first_name, User.last_name, Deal.currency,
        PipelineStage.stage_type, func.count(Deal.id), func.sum(Deal.amount)).select_from(Deal)
        .join(PipelineStage, (PipelineStage.workspace_id == Deal.workspace_id) & (PipelineStage.id == Deal.stage_id))
        .outerjoin(User, User.id == Deal.responsible_user_id).where(*scope)
        .group_by(Deal.responsible_user_id, User.first_name, User.last_name, Deal.currency, PipelineStage.stage_type)
        .order_by(User.first_name, Deal.responsible_user_id, Deal.currency, PipelineStage.stage_type))).all()
    now = datetime.now(timezone.utc)
    task_scope = (Task.workspace_id == workspace_id, TaskStatus.is_final.is_(False))
    task_query = select(func.count()).select_from(Task).join(TaskStatus,
        (TaskStatus.workspace_id == Task.workspace_id) & (TaskStatus.id == Task.status_id)).where(*task_scope)
    active_tasks = await db.scalar(task_query)
    overdue_tasks = await db.scalar(task_query.where(Task.due_at < now))
    project_rows = (await db.execute(select(Project.status, func.count()).where(Project.workspace_id == workspace_id).group_by(Project.status))).all()
    project_counts = dict(project_rows)
    follow_query = select(func.count()).select_from(Deal).join(PipelineStage,
        (PipelineStage.workspace_id == Deal.workspace_id) & (PipelineStage.id == Deal.stage_id)).where(
        Deal.workspace_id == workspace_id, PipelineStage.stage_type == StageType.OPEN)
    overdue_followups = await db.scalar(follow_query.where(Deal.follow_up_at < now))
    missing_followups = await db.scalar(follow_query.where(Deal.follow_up_at.is_(None)))
    closed = counts['WON'] + counts['LOST']
    return {'generated_at': now, 'timezone': workspace.timezone, 'counts': counts,
        'conversion_percent': round(counts['WON'] / closed * 100, 2) if closed else None,
        'stages': stages, 'managers': [{'user_id': uid, 'name': ' '.join(filter(None, (first, last))) if uid else 'Без ответственного',
            'currency': currency, 'stage_type': kind.value, 'count': count, 'amount': str(amount)}
            for uid, first, last, currency, kind, count, amount in managers],
        'work': {'active_tasks': active_tasks, 'overdue_tasks': overdue_tasks,
            'active_projects': project_counts.get('ACTIVE', 0), 'archived_projects': project_counts.get('ARCHIVED', 0),
            'overdue_followups': overdue_followups, 'missing_followups': missing_followups}}
