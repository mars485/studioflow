from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import current_user, workspace_access, workspace_admin
from app.api.v1.schemas import (ClientCreate, ClientOut, ClientUpdate, ContactCreate, ContactOut, ContactUpdate, DealCreate, DealOut,
                                DealUpdate, DealActivityCreate, DealActivityOut, FollowUp,
                                FollowUpComplete, FollowUpCompleteResult, FollowUpCompletionOut, PipelineCreate, PipelineOut, PipelineUpdate,
                                StageCreate, StageOrder, StageOut, StageUpdate)
from app.core.database import get_db
from app.models import Client, Contact, ContactClient, Deal, DealActivity, FollowUpCompletion, Pipeline, PipelineStage, User, Workspace, WorkspaceMember
from app.models.entities import StageType

router = APIRouter(tags=["CRM"])
scoped = APIRouter(prefix="/workspaces/{workspace_id}")


@scoped.get("/pipelines", response_model=list[PipelineOut])
async def pipelines(include_inactive: bool = False, workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    query = select(Pipeline).where(Pipeline.workspace_id == workspace_id)
    if not include_inactive:
        query = query.where(Pipeline.is_active.is_(True))
    rows = (await db.scalars(query.options(selectinload(Pipeline.stages))
                             .order_by(Pipeline.is_default.desc(), Pipeline.id))).all()
    return [PipelineOut(id=p.id, name=p.name, is_default=p.is_default,
                        is_active=p.is_active, stages=sorted(p.stages, key=lambda s: s.position)) for p in rows]


async def lock_workspace(db: AsyncSession, workspace_id: UUID):
    await db.scalar(select(Workspace.id).where(Workspace.id == workspace_id).with_for_update())


@scoped.post("/pipelines", response_model=PipelineOut, status_code=201)
async def create_pipeline(data: PipelineCreate, workspace_id: UUID = Depends(workspace_admin),
                          db: AsyncSession = Depends(get_db)):
    await lock_workspace(db, workspace_id)
    has_default = await db.scalar(select(Pipeline.id).where(Pipeline.workspace_id == workspace_id,
                                                            Pipeline.is_default.is_(True)).limit(1))
    row = Pipeline(workspace_id=workspace_id, name=data.name, is_default=has_default is None, is_active=True)
    db.add(row)
    await db.flush()
    for position, (name, stage_type) in enumerate([
        ("Новый лид", StageType.OPEN), ("В работе", StageType.OPEN),
        ("Успешно", StageType.WON), ("Отказ", StageType.LOST),
    ]):
        db.add(PipelineStage(workspace_id=workspace_id, pipeline_id=row.id, name=name,
                             position=position, stage_type=stage_type))
    await db.commit()
    return await db.scalar(select(Pipeline).where(Pipeline.id == row.id).options(selectinload(Pipeline.stages)))


@scoped.patch("/pipelines/{pipeline_id}", response_model=PipelineOut)
async def update_pipeline(pipeline_id: UUID, data: PipelineUpdate,
                          workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    row = await lock_pipeline(db, workspace_id, pipeline_id)
    row.name = data.name
    await db.commit()
    return await db.scalar(select(Pipeline).where(Pipeline.id == pipeline_id).options(selectinload(Pipeline.stages)))


@scoped.post("/pipelines/{pipeline_id}/activate", response_model=PipelineOut)
async def activate_pipeline(pipeline_id: UUID, workspace_id: UUID = Depends(workspace_admin),
                            db: AsyncSession = Depends(get_db)):
    await lock_workspace(db, workspace_id)
    row = await lock_pipeline(db, workspace_id, pipeline_id)
    row.is_active = True
    await db.commit()
    return await db.scalar(select(Pipeline).where(Pipeline.id == pipeline_id).options(selectinload(Pipeline.stages)))


@scoped.post("/pipelines/{pipeline_id}/default", response_model=PipelineOut)
async def make_default_pipeline(pipeline_id: UUID, workspace_id: UUID = Depends(workspace_admin),
                                db: AsyncSession = Depends(get_db)):
    await lock_workspace(db, workspace_id)
    row = await lock_pipeline(db, workspace_id, pipeline_id)
    if not row.is_active:
        raise HTTPException(409, "Только активную воронку можно сделать основной")
    rows = (await db.scalars(select(Pipeline).where(Pipeline.workspace_id == workspace_id))).all()
    for pipeline in rows:
        pipeline.is_default = pipeline.id == pipeline_id
    await db.commit()
    return await db.scalar(select(Pipeline).where(Pipeline.id == pipeline_id).options(selectinload(Pipeline.stages)))


@scoped.post("/pipelines/{pipeline_id}/deactivate", response_model=PipelineOut)
async def deactivate_pipeline(pipeline_id: UUID, workspace_id: UUID = Depends(workspace_admin),
                              db: AsyncSession = Depends(get_db)):
    await lock_workspace(db, workspace_id)
    row = await lock_pipeline(db, workspace_id, pipeline_id)
    replacement = await db.scalar(select(Pipeline).where(Pipeline.workspace_id == workspace_id,
        Pipeline.id != pipeline_id, Pipeline.is_active.is_(True)).order_by(Pipeline.id).limit(1))
    if replacement is None:
        raise HTTPException(409, "Нельзя отключить единственную активную воронку")
    row.is_active = False
    if row.is_default:
        row.is_default = False
        replacement.is_default = True
    await db.commit()
    return await db.scalar(select(Pipeline).where(Pipeline.id == pipeline_id).options(selectinload(Pipeline.stages)))


@scoped.delete("/pipelines/{pipeline_id}", status_code=204)
async def delete_pipeline(pipeline_id: UUID, workspace_id: UUID = Depends(workspace_admin),
                          db: AsyncSession = Depends(get_db)):
    await lock_workspace(db, workspace_id)
    row = await lock_pipeline(db, workspace_id, pipeline_id)
    (await db.scalars(select(PipelineStage).where(PipelineStage.workspace_id == workspace_id,
        PipelineStage.pipeline_id == pipeline_id).with_for_update())).all()
    if await db.scalar(select(Deal.id).where(Deal.workspace_id == workspace_id,
                                              Deal.pipeline_id == pipeline_id).limit(1)):
        raise HTTPException(409, "Воронку со сделками можно только отключить")
    if row.is_active:
        replacement = await db.scalar(select(Pipeline).where(Pipeline.workspace_id == workspace_id,
            Pipeline.id != pipeline_id, Pipeline.is_active.is_(True)).order_by(Pipeline.id).limit(1))
        if replacement is None:
            raise HTTPException(409, "Нельзя удалить единственную активную воронку")
        if row.is_default:
            replacement.is_default = True
    await db.refresh(row, attribute_names=["stages"])
    await db.delete(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Воронку со сделками можно только отключить")
    return Response(status_code=204)


async def lock_pipeline(db: AsyncSession, workspace_id: UUID, pipeline_id: UUID) -> Pipeline:
    row = await db.scalar(select(Pipeline).where(Pipeline.id == pipeline_id,
                                                  Pipeline.workspace_id == workspace_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Pipeline not found")
    return row


@scoped.post("/pipelines/{pipeline_id}/stages", response_model=StageOut, status_code=201)
async def create_stage(pipeline_id: UUID, data: StageCreate,
                       workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    await lock_pipeline(db, workspace_id, pipeline_id)
    position = (await db.scalar(select(func.coalesce(func.max(PipelineStage.position), -1)).where(
        PipelineStage.workspace_id == workspace_id, PipelineStage.pipeline_id == pipeline_id))) + 1
    row = PipelineStage(workspace_id=workspace_id, pipeline_id=pipeline_id, name=data.name,
                        position=position, stage_type=StageType(data.stage_type), color=data.color)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@scoped.patch("/pipelines/{pipeline_id}/stages/{stage_id}", response_model=StageOut)
async def update_stage(pipeline_id: UUID, stage_id: UUID, data: StageUpdate,
                       workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    await lock_pipeline(db, workspace_id, pipeline_id)
    row = await db.scalar(select(PipelineStage).where(PipelineStage.id == stage_id,
        PipelineStage.workspace_id == workspace_id, PipelineStage.pipeline_id == pipeline_id))
    if row is None:
        raise HTTPException(404, "Stage not found")
    for name, value in data.model_dump(exclude_unset=True).items():
        setattr(row, name, StageType(value) if name == "stage_type" else value)
    await db.commit()
    await db.refresh(row)
    return row


@scoped.put("/pipelines/{pipeline_id}/stages/order", response_model=list[StageOut])
async def reorder_stages(pipeline_id: UUID, data: StageOrder,
                         workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    await lock_pipeline(db, workspace_id, pipeline_id)
    rows = (await db.scalars(select(PipelineStage).where(PipelineStage.workspace_id == workspace_id,
        PipelineStage.pipeline_id == pipeline_id))).all()
    if len(data.ids) != len(rows) or len(set(data.ids)) != len(rows) or set(data.ids) != {row.id for row in rows}:
        raise HTTPException(422, "Order must contain every stage of this pipeline exactly once")
    by_id = {row.id: row for row in rows}
    for position, stage_id in enumerate(data.ids):
        by_id[stage_id].position = position
    await db.commit()
    return [by_id[stage_id] for stage_id in data.ids]


@scoped.delete("/pipelines/{pipeline_id}/stages/{stage_id}", status_code=204)
async def delete_stage(pipeline_id: UUID, stage_id: UUID,
                       workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    await lock_pipeline(db, workspace_id, pipeline_id)
    rows = (await db.scalars(select(PipelineStage).where(PipelineStage.workspace_id == workspace_id,
        PipelineStage.pipeline_id == pipeline_id).order_by(PipelineStage.position, PipelineStage.id))).all()
    row = next((stage for stage in rows if stage.id == stage_id), None)
    if row is None:
        raise HTTPException(404, "Stage not found")
    if len(rows) <= 2:
        raise HTTPException(409, "В воронке должно остаться не менее двух этапов")
    if await db.scalar(select(Deal.id).where(Deal.workspace_id == workspace_id,
                                              Deal.stage_id == stage_id).limit(1)):
        raise HTTPException(409, "Нельзя удалить этап со сделками")
    await db.delete(row)
    for position, stage in enumerate(stage for stage in rows if stage.id != stage_id):
        stage.position = position
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Нельзя удалить этап со сделками")
    return Response(status_code=204)


@scoped.get("/clients", response_model=list[ClientOut])
async def clients(search: str | None = Query(None, max_length=255),
                  workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    query = select(Client).where(Client.workspace_id == workspace_id)
    if search and search.strip():
        pattern = f"%{search.strip().replace('%', r'\%').replace('_', r'\_')}%"
        query = query.where(Client.name.ilike(pattern, escape="\\"))
    return (await db.scalars(query
                             .order_by(Client.name, Client.id))).all()


@scoped.post("/clients", response_model=ClientOut, status_code=201)
async def create_client(data: ClientCreate, workspace_id: UUID = Depends(workspace_access),
                        db: AsyncSession = Depends(get_db)):
    row = Client(workspace_id=workspace_id, **data.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@scoped.get("/clients/{client_id}", response_model=ClientOut)
async def get_client(client_id: UUID, workspace_id: UUID = Depends(workspace_access),
                     db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(Client).where(Client.id == client_id, Client.workspace_id == workspace_id))
    if row is None:
        raise HTTPException(404, "Client not found")
    return row


@scoped.patch("/clients/{client_id}", response_model=ClientOut)
async def update_client(client_id: UUID, data: ClientUpdate,
                        workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(Client).where(Client.id == client_id,
        Client.workspace_id == workspace_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Client not found")
    for name, value in data.model_dump(exclude_unset=True).items():
        setattr(row, name, value)
    await db.commit()
    await db.refresh(row)
    return row


@scoped.get("/clients/{client_id}/deals", response_model=list[DealOut])
async def client_deals(client_id: UUID, workspace_id: UUID = Depends(workspace_access),
                       db: AsyncSession = Depends(get_db)):
    if not await db.scalar(select(Client.id).where(Client.id == client_id, Client.workspace_id == workspace_id)):
        raise HTTPException(404, "Client not found")
    return (await db.scalars(select(Deal).where(Deal.workspace_id == workspace_id,
        Deal.client_id == client_id).order_by(Deal.created_at.desc(), Deal.id.desc()))).all()


@scoped.delete("/clients/{client_id}", status_code=204)
async def delete_client(client_id: UUID, workspace_id: UUID = Depends(workspace_admin),
                        db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(Client).where(Client.id == client_id,
        Client.workspace_id == workspace_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Client not found")
    if await db.scalar(select(Deal.id).where(Deal.workspace_id == workspace_id,
                                              Deal.client_id == client_id).limit(1)):
        raise HTTPException(409, "Клиента со сделками удалить нельзя")
    await db.delete(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Клиента со сделками удалить нельзя")
    return Response(status_code=204)


async def contact_output(db: AsyncSession, row: Contact) -> ContactOut:
    ids = (await db.scalars(select(ContactClient.client_id).where(
        ContactClient.workspace_id == row.workspace_id, ContactClient.contact_id == row.id)
        .order_by(ContactClient.client_id))).all()
    return ContactOut.model_validate({**{key: getattr(row, key) for key in (
        "id", "workspace_id", "first_name", "last_name", "middle_name", "phone", "email",
        "website", "notes", "created_at", "updated_at")}, "client_ids": ids})


async def validate_contact_clients(db: AsyncSession, workspace_id: UUID, client_ids: list[UUID]):
    if not client_ids:
        return
    existing = (await db.scalars(select(Client.id).where(Client.workspace_id == workspace_id,
        Client.id.in_(client_ids)).with_for_update())).all()
    if len(existing) != len(client_ids):
        raise HTTPException(422, "Все компании контакта должны принадлежать этой студии")


@scoped.get("/contacts", response_model=list[ContactOut])
async def contacts(search: str | None = Query(None, max_length=255),
                   workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    query = select(Contact).where(Contact.workspace_id == workspace_id)
    if search and search.strip():
        pattern = f"%{search.strip().replace('%', r'\%').replace('_', r'\_')}%"
        query = query.where(or_(Contact.first_name.ilike(pattern, escape="\\"),
            Contact.last_name.ilike(pattern, escape="\\"), Contact.phone.ilike(pattern, escape="\\"),
            Contact.email.ilike(pattern, escape="\\")))
    rows = (await db.scalars(query.order_by(Contact.last_name, Contact.first_name, Contact.id))).all()
    return [await contact_output(db, row) for row in rows]


@scoped.post("/contacts", response_model=ContactOut, status_code=201)
async def create_contact(data: ContactCreate, workspace_id: UUID = Depends(workspace_access),
                         db: AsyncSession = Depends(get_db)):
    await validate_contact_clients(db, workspace_id, data.client_ids)
    row = Contact(workspace_id=workspace_id, **data.model_dump(exclude={"client_ids"}))
    db.add(row)
    await db.flush()
    db.add_all(ContactClient(workspace_id=workspace_id, contact_id=row.id, client_id=client_id)
               for client_id in data.client_ids)
    await db.commit()
    await db.refresh(row)
    return await contact_output(db, row)


@scoped.get("/contacts/{contact_id}", response_model=ContactOut)
async def get_contact(contact_id: UUID, workspace_id: UUID = Depends(workspace_access),
                      db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id))
    if row is None:
        raise HTTPException(404, "Contact not found")
    return await contact_output(db, row)


@scoped.get("/contacts/{contact_id}/deals", response_model=list[DealOut])
async def contact_deals(contact_id: UUID, workspace_id: UUID = Depends(workspace_access),
                        db: AsyncSession = Depends(get_db)):
    if not await db.scalar(select(Contact.id).where(Contact.id == contact_id,
        Contact.workspace_id == workspace_id)):
        raise HTTPException(404, "Contact not found")
    return (await db.scalars(select(Deal).where(Deal.workspace_id == workspace_id,
        Deal.contact_id == contact_id).order_by(Deal.created_at.desc(), Deal.id.desc()))).all()


@scoped.patch("/contacts/{contact_id}", response_model=ContactOut)
async def update_contact(contact_id: UUID, data: ContactUpdate,
                         workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(Contact).where(Contact.id == contact_id,
        Contact.workspace_id == workspace_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Contact not found")
    changes = data.model_dump(exclude_unset=True)
    if "client_ids" in changes:
        client_ids = changes.pop("client_ids")
        if client_ids is None:
            raise HTTPException(422, "Company links cannot be null")
        await validate_contact_clients(db, workspace_id, client_ids)
        (await db.scalars(select(ContactClient).where(ContactClient.workspace_id == workspace_id,
            ContactClient.contact_id == contact_id).with_for_update())).all()
        used = (await db.scalars(select(Deal.client_id).where(Deal.workspace_id == workspace_id,
            Deal.contact_id == contact_id).distinct())).all()
        if not set(used).issubset(set(client_ids)):
            raise HTTPException(409, "Нельзя отвязать компанию, пока контакт указан в её сделке")
        await db.execute(delete(ContactClient).where(ContactClient.workspace_id == workspace_id,
            ContactClient.contact_id == contact_id))
        db.add_all(ContactClient(workspace_id=workspace_id, contact_id=contact_id, client_id=client_id)
                   for client_id in client_ids)
    for name, value in changes.items():
        setattr(row, name, value)
    await db.commit()
    await db.refresh(row)
    return await contact_output(db, row)


@scoped.delete("/contacts/{contact_id}", status_code=204)
async def delete_contact(contact_id: UUID, workspace_id: UUID = Depends(workspace_admin),
                         db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(Contact).where(Contact.id == contact_id,
        Contact.workspace_id == workspace_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Contact not found")
    if await db.scalar(select(Deal.id).where(Deal.workspace_id == workspace_id,
        Deal.contact_id == contact_id).limit(1)):
        raise HTTPException(409, "Контакт используется в сделках")
    await db.delete(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Контакт используется в сделках")
    return Response(status_code=204)


@scoped.get("/clients/{client_id}/contacts", response_model=list[ContactOut])
async def client_contacts(client_id: UUID, workspace_id: UUID = Depends(workspace_access),
                          db: AsyncSession = Depends(get_db)):
    if not await db.scalar(select(Client.id).where(Client.id == client_id, Client.workspace_id == workspace_id)):
        raise HTTPException(404, "Client not found")
    rows = (await db.scalars(select(Contact).join(ContactClient,
        (ContactClient.contact_id == Contact.id) & (ContactClient.workspace_id == workspace_id))
        .where(ContactClient.client_id == client_id, Contact.workspace_id == workspace_id)
        .order_by(Contact.last_name, Contact.first_name, Contact.id))).all()
    return [await contact_output(db, row) for row in rows]


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
    client = await db.scalar(select(Client.id).where(Client.id == client_id,
        Client.workspace_id == workspace_id).with_for_update())
    stage = await db.scalar(select(PipelineStage.id).join(Pipeline, Pipeline.id == PipelineStage.pipeline_id).where(
        PipelineStage.id == stage_id, PipelineStage.workspace_id == workspace_id,
        PipelineStage.pipeline_id == pipeline_id, Pipeline.workspace_id == workspace_id,
        Pipeline.is_active.is_(True)).with_for_update(of=PipelineStage))
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


async def validate_deal_contact(db: AsyncSession, workspace_id: UUID,
                                client_id: UUID, contact_id: UUID | None) -> Contact | None:
    if contact_id is None:
        return None
    row = await db.scalar(select(Contact).where(Contact.id == contact_id,
        Contact.workspace_id == workspace_id).with_for_update())
    link = await db.scalar(select(ContactClient.contact_id).where(
        ContactClient.workspace_id == workspace_id, ContactClient.contact_id == contact_id,
        ContactClient.client_id == client_id).with_for_update())
    if row is None or link is None:
        raise HTTPException(422, "Контакт должен быть связан с компанией этой сделки")
    return row


def contact_label(row: Contact) -> str:
    return " ".join(part for part in (row.last_name, row.first_name, row.middle_name) if part)


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
    contact = await validate_deal_contact(db, workspace_id, data.client_id, data.contact_id)
    await validate_responsible(db, workspace_id, data.responsible_user_id)
    workspace = await db.get(Workspace, workspace_id)
    values = data.model_dump()
    if contact:
        values["contact_name"] = contact_label(contact)
    row = Deal(workspace_id=workspace_id, currency=workspace.currency, **values)
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
    start_date = changes.get("start_date", row.start_date)
    end_date = changes.get("end_date", row.end_date)
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, "Дата начала не может быть позже даты окончания")
    await validate_relations(db, workspace_id, changes.get("client_id", row.client_id),
                             changes.get("pipeline_id", row.pipeline_id), changes.get("stage_id", row.stage_id))
    contact = await validate_deal_contact(db, workspace_id, changes.get("client_id", row.client_id),
                                          changes.get("contact_id", row.contact_id))
    if "contact_id" in changes:
        changes["contact_name"] = contact_label(contact) if contact else None
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
