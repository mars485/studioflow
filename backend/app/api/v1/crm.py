from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import current_user, workspace_access, workspace_admin
from app.api.v1.schemas import (ClientCreate, ClientOut, DealCreate, DealOut,
                                DealUpdate, DealActivityCreate, DealActivityOut, FollowUp,
                                FollowUpComplete, FollowUpCompleteResult, FollowUpCompletionOut, PipelineOut)
from app.core.database import get_db
from app.models import Client, Deal, DealActivity, FollowUpCompletion, Pipeline, PipelineStage, User, Workspace, WorkspaceMember

router = APIRouter(tags=["CRM"])
scoped = APIRouter(prefix="/workspaces/{workspace_id}")


@scoped.get("/pipelines", response_model=list[PipelineOut])
async def pipelines(workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(Pipeline).where(
        Pipeline.workspace_id == workspace_id, Pipeline.is_active.is_(True)
    ).options(selectinload(Pipeline.stages)).order_by(Pipeline.is_default.desc(), Pipeline.id))).all()
    return [PipelineOut(id=p.id, name=p.name, is_default=p.is_default,
                        stages=sorted(p.stages, key=lambda s: s.position)) for p in rows]


@scoped.get("/clients", response_model=list[ClientOut])
async def clients(workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    return (await db.scalars(select(Client).where(Client.workspace_id == workspace_id)
                             .order_by(Client.name, Client.id))).all()


@scoped.post("/clients", response_model=ClientOut, status_code=201)
async def create_client(data: ClientCreate, workspace_id: UUID = Depends(workspace_access),
                        db: AsyncSession = Depends(get_db)):
    row = Client(workspace_id=workspace_id, name=data.name)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def find_deal(db: AsyncSession, workspace_id: UUID, deal_id: UUID) -> Deal:
    row = await db.scalar(select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id))
    if row is None:
        raise HTTPException(404, "Deal not found")
    return row


async def lock_deal(db: AsyncSession, workspace_id: UUID, deal_id: UUID) -> Deal:
    row = await db.scalar(select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Deal not found")
    return row


async def validate_relations(db: AsyncSession, workspace_id: UUID, client_id: UUID,
                             pipeline_id: UUID, stage_id: UUID):
    client = await db.scalar(select(Client.id).where(Client.id == client_id, Client.workspace_id == workspace_id))
    stage = await db.scalar(select(PipelineStage.id).join(Pipeline, Pipeline.id == PipelineStage.pipeline_id).where(
        PipelineStage.id == stage_id, PipelineStage.workspace_id == workspace_id,
        PipelineStage.pipeline_id == pipeline_id, Pipeline.workspace_id == workspace_id,
        Pipeline.is_active.is_(True)))
    if client is None or stage is None:
        raise HTTPException(422, "Client, pipeline and stage must belong to this workspace and stage to the active pipeline")


async def validate_responsible(db: AsyncSession, workspace_id: UUID, responsible_user_id: UUID | None):
    if responsible_user_id is None:
        return
    member = await db.scalar(select(WorkspaceMember.user_id).join(User, User.id == WorkspaceMember.user_id).where(
        WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == responsible_user_id,
        User.is_active.is_(True)).with_for_update(of=WorkspaceMember))
    if member is None:
        raise HTTPException(422, "Ответственный должен быть активным участником студии")


@scoped.get("/deals", response_model=list[DealOut])
async def deals(workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db),
                pipeline_id: UUID | None = None, limit: int = Query(100, ge=1, le=500),
                offset: int = Query(0, ge=0)):
    query = select(Deal).where(Deal.workspace_id == workspace_id)
    if pipeline_id:
        query = query.where(Deal.pipeline_id == pipeline_id)
    return (await db.scalars(query.order_by(Deal.created_at, Deal.id).limit(limit).offset(offset))).all()


@scoped.post("/deals", response_model=DealOut, status_code=201)
async def create_deal(data: DealCreate, workspace_id: UUID = Depends(workspace_access),
                      db: AsyncSession = Depends(get_db)):
    await validate_relations(db, workspace_id, data.client_id, data.pipeline_id, data.stage_id)
    await validate_responsible(db, workspace_id, data.responsible_user_id)
    workspace = await db.get(Workspace, workspace_id)
    row = Deal(workspace_id=workspace_id, currency=workspace.currency, **data.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@scoped.get("/deals/{deal_id}", response_model=DealOut)
async def get_deal(deal_id: UUID, workspace_id: UUID = Depends(workspace_access),
                   db: AsyncSession = Depends(get_db)):
    return await find_deal(db, workspace_id, deal_id)


@scoped.patch("/deals/{deal_id}", response_model=DealOut)
async def update_deal(deal_id: UUID, data: DealUpdate, workspace_id: UUID = Depends(workspace_access),
                      user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    row = await lock_deal(db, workspace_id, deal_id)
    changes = data.model_dump(exclude_unset=True)
    await validate_relations(db, workspace_id, changes.get("client_id", row.client_id),
                             changes.get("pipeline_id", row.pipeline_id), changes.get("stage_id", row.stage_id))
    await validate_responsible(db, workspace_id, changes.get("responsible_user_id", row.responsible_user_id))
    next_stage_id = changes.get("stage_id", row.stage_id)
    if next_stage_id != row.stage_id:
        stages = (await db.scalars(select(PipelineStage).where(
            PipelineStage.workspace_id == workspace_id, PipelineStage.id.in_([row.stage_id, next_stage_id])))).all()
        names = {stage.id: stage.name for stage in stages}
        db.add(DealActivity(workspace_id=workspace_id, deal_id=deal_id, author_user_id=user.id,
                            author_name=" ".join(filter(None, (user.first_name, user.last_name))),
                            kind="STAGE_CHANGE", body=f"Стадия: {names[row.stage_id]} → {names[next_stage_id]}"))
    for name, value in changes.items():
        setattr(row, name, value)
    await db.commit()
    await db.refresh(row)
    return row


@scoped.delete("/deals/{deal_id}", status_code=204)
async def delete_deal(deal_id: UUID, workspace_id: UUID = Depends(workspace_admin),
                      db: AsyncSession = Depends(get_db)):
    await db.delete(await find_deal(db, workspace_id, deal_id))
    await db.commit()
    return Response(status_code=204)


@scoped.put("/deals/{deal_id}/follow-up", response_model=DealOut)
async def save_follow_up(deal_id: UUID, data: FollowUp, workspace_id: UUID = Depends(workspace_access),
                         db: AsyncSession = Depends(get_db)):
    row = await lock_deal(db, workspace_id, deal_id)
    row.follow_up_at, row.follow_up_action, row.follow_up_comment = data.at, data.action, data.comment
    await db.commit()
    await db.refresh(row)
    return row


@scoped.delete("/deals/{deal_id}/follow-up", response_model=DealOut)
async def clear_follow_up(deal_id: UUID, workspace_id: UUID = Depends(workspace_access),
                          db: AsyncSession = Depends(get_db)):
    row = await lock_deal(db, workspace_id, deal_id)
    row.follow_up_at = row.follow_up_action = row.follow_up_comment = None
    await db.commit()
    await db.refresh(row)
    return row


@scoped.get("/deals/{deal_id}/follow-up/completions", response_model=list[FollowUpCompletionOut])
async def follow_up_completions(deal_id: UUID, workspace_id: UUID = Depends(workspace_access),
                                db: AsyncSession = Depends(get_db), limit: int = Query(100, ge=1, le=500),
                                offset: int = Query(0, ge=0)):
    await find_deal(db, workspace_id, deal_id)
    return (await db.scalars(select(FollowUpCompletion).where(
        FollowUpCompletion.workspace_id == workspace_id, FollowUpCompletion.deal_id == deal_id
    ).order_by(FollowUpCompletion.completed_at.desc(), FollowUpCompletion.id.desc()).limit(limit).offset(offset))).all()


@scoped.post("/deals/{deal_id}/follow-up/complete", response_model=FollowUpCompleteResult, status_code=201)
async def complete_follow_up(deal_id: UUID, data: FollowUpComplete,
                             workspace_id: UUID = Depends(workspace_access),
                             user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    row = await lock_deal(db, workspace_id, deal_id)
    if row.follow_up_at is None or row.follow_up_action is None:
        raise HTTPException(409, "У сделки нет назначенного следующего действия")
    completion = FollowUpCompletion(
        workspace_id=workspace_id, deal_id=deal_id, completed_by_user_id=user.id,
        completed_by_name=" ".join(filter(None, (user.first_name, user.last_name))),
        scheduled_at=row.follow_up_at, action=row.follow_up_action,
        planned_comment=row.follow_up_comment, outcome_comment=data.outcome_comment)
    db.add(completion)
    row.follow_up_at = row.follow_up_action = row.follow_up_comment = None
    await db.commit()
    await db.refresh(completion)
    await db.refresh(row)
    return {"completion": completion, "deal": row}


@scoped.get("/deals/{deal_id}/activities", response_model=list[DealActivityOut])
async def deal_activities(deal_id: UUID, workspace_id: UUID = Depends(workspace_access),
                          db: AsyncSession = Depends(get_db), limit: int = Query(100, ge=1, le=500),
                          offset: int = Query(0, ge=0)):
    await find_deal(db, workspace_id, deal_id)
    return (await db.scalars(select(DealActivity).where(
        DealActivity.workspace_id == workspace_id, DealActivity.deal_id == deal_id
    ).order_by(DealActivity.created_at.desc(), DealActivity.id.desc()).limit(limit).offset(offset))).all()


@scoped.post("/deals/{deal_id}/activities", response_model=DealActivityOut, status_code=201)
async def add_deal_activity(deal_id: UUID, data: DealActivityCreate,
                            workspace_id: UUID = Depends(workspace_access),
                            user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await find_deal(db, workspace_id, deal_id)
    row = DealActivity(workspace_id=workspace_id, deal_id=deal_id, author_user_id=user.id,
                       author_name=" ".join(filter(None, (user.first_name, user.last_name))), body=data.body)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


router.include_router(scoped)
