from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import current_user, workspace_access, workspace_admin
from app.api.v1.schemas import (ClientCreate, ClientOut, ClientUpdate, ContactCreate, ContactOut, ContactUpdate, DealAttachmentCreate, DealAttachmentOut,
                                DealContactLinkCreate, DealContactLinkOut, DealContactLinkUpdate, DealCreate, DealCustomField, DealCustomFields,
                                DealCustomFieldsOut, DealOut, DealTagCreate, DealTagOut, DealUpdate, DealWatcherCreate, DealWatcherOut,
                                DealActivityCreate, DealActivityOut, DealTaskCreate, DealTaskOut, DealTaskUpdate, DueTaskReminder, FollowUp,
                                FollowUpComplete, FollowUpCompleteResult, FollowUpCompletionOut, MyDayOut, PipelineCreate, PipelineOut, PipelineUpdate,
                                TaskChecklistItemCreate, TaskChecklistItemOut, TaskChecklistItemUpdate, TaskCreate, TaskOut, TaskReminderCreate,
                                TaskReminderOut, TaskStatusCreate, TaskStatusOrder, TaskStatusOut, TaskStatusUpdate, TaskUpdate,
                                StageCreate, StageOrder, StageOut, StageUpdate)
from app.core.database import get_db
from app.models import (Client, Contact, ContactClient, Deal, DealActivity, DealAttachment, DealContact, DealCustomValue, DealTag, DealTagLink, DealWatcher,
                        FollowUpCompletion, Pipeline, PipelineStage, Project, Task, TaskChecklistItem, TaskReminder, TaskStatus, TaskWatcher, User, Workspace,
                        WorkspaceMember)
from app.models.entities import StageType
from app.models.notifications import Notification
from app.services.task_time import stop_timers
from app.services.task_recurrence import repeat_completed_task
from app.services.webhooks import emit_event
from app.services.audit import audit_deal, deal_snapshot

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
        raise HTTPException(409, "Клиента со связанными сделками, проектами или счетами удалить нельзя")
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
                                client_id: UUID, contact_id: UUID | None, deal_id: UUID | None = None) -> Contact | None:
    if contact_id is None:
        return None
    row = await db.scalar(select(Contact).where(Contact.id == contact_id,
        Contact.workspace_id == workspace_id).with_for_update())
    link = await db.scalar(select(ContactClient.contact_id).where(
        ContactClient.workspace_id == workspace_id, ContactClient.contact_id == contact_id,
         ContactClient.client_id == client_id).with_for_update())
    if link is None and deal_id is not None:
        link = await db.scalar(select(DealContact.contact_id).where(DealContact.workspace_id == workspace_id,
            DealContact.deal_id == deal_id, DealContact.contact_id == contact_id))
    if row is None or link is None:
        raise HTTPException(422, "Контакт должен быть связан с компанией этой сделки")
    return row


def contact_label(row: Contact) -> str:
    return " ".join(part for part in (row.last_name, row.first_name, row.middle_name) if part)


async def assign_primary_contact(db: AsyncSession, deal: Deal, contact_id: UUID | None):
    await db.execute(update(DealContact).where(DealContact.workspace_id == deal.workspace_id,
        DealContact.deal_id == deal.id).values(is_primary=False))
    if contact_id is not None:
        await db.execute(pg_insert(DealContact).values(workspace_id=deal.workspace_id, deal_id=deal.id,
            contact_id=contact_id, is_primary=False).on_conflict_do_nothing())
        await db.execute(update(DealContact).where(DealContact.workspace_id == deal.workspace_id,
            DealContact.deal_id == deal.id, DealContact.contact_id == contact_id).values(is_primary=True))
        contact = await db.get(Contact, contact_id)
        deal.contact_name = contact_label(contact)
    else:
        deal.contact_name = None
    deal.contact_id = contact_id


async def replacement_contact(db: AsyncSession, deal: Deal, exclude_id: UUID | None = None) -> UUID | None:
    query = select(DealContact.contact_id).where(DealContact.workspace_id == deal.workspace_id, DealContact.deal_id == deal.id)
    if exclude_id is not None:
        query = query.where(DealContact.contact_id != exclude_id)
    return await db.scalar(query.order_by(DealContact.created_at, DealContact.contact_id).limit(1))


@scoped.get("/deals", response_model=list[DealOut])
async def deals(workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db),
                pipeline_id: UUID | None = None, limit: int = Query(100, ge=1, le=500),
                offset: int = Query(0, ge=0)):
    query = select(Deal).where(Deal.workspace_id == workspace_id)
    if pipeline_id:
        query = query.where(Deal.pipeline_id == pipeline_id)
    return (await db.scalars(query.order_by(Deal.created_at, Deal.id).limit(limit).offset(offset))).all()


@scoped.get("/my-day", response_model=MyDayOut)
async def my_day(workspace_id: UUID = Depends(workspace_access), user: User = Depends(current_user),
                 db: AsyncSession = Depends(get_db)):
    active_deals = (Deal.workspace_id == workspace_id, PipelineStage.workspace_id == workspace_id,
                    PipelineStage.stage_type == StageType.OPEN)
    task_rows = (await db.execute(select(Task, TaskStatus, Deal.title).join(TaskStatus,
        (TaskStatus.workspace_id == Task.workspace_id) & (TaskStatus.id == Task.status_id))
        .join(Deal, (Deal.id == Task.deal_id) & (Deal.workspace_id == Task.workspace_id))
        .join(PipelineStage, PipelineStage.id == Deal.stage_id)
        .where(*active_deals, Task.workspace_id == workspace_id, TaskStatus.is_final.is_(False),
               Task.assignee_user_id == user.id)
        .order_by(Task.due_at, Task.created_at, Task.id))).all()
    follow_rows = (await db.scalars(select(Deal).join(PipelineStage, PipelineStage.id == Deal.stage_id)
        .where(*active_deals, Deal.responsible_user_id == user.id, Deal.follow_up_at.is_not(None))
        .order_by(Deal.follow_up_at, Deal.id))).all()
    return {"tasks": [{"task": legacy_task(task, status), "deal_title": title} for task, status, title in task_rows],
            "follow_ups": [{"deal_id": deal.id, "deal_title": deal.title,
                            "at": deal.follow_up_at, "action": deal.follow_up_action,
                            "comment": deal.follow_up_comment} for deal in follow_rows]}


@scoped.post("/deals", response_model=DealOut, status_code=201)
async def create_deal(data: DealCreate, workspace_id: UUID = Depends(workspace_access),
                      db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await validate_relations(db, workspace_id, data.client_id, data.pipeline_id, data.stage_id)
    contact = await validate_deal_contact(db, workspace_id, data.client_id, data.contact_id)
    await validate_responsible(db, workspace_id, data.responsible_user_id)
    workspace = await db.get(Workspace, workspace_id)
    values = data.model_dump()
    if contact:
        values["contact_name"] = contact_label(contact)
    row = Deal(workspace_id=workspace_id, currency=workspace.currency, **values)
    db.add(row)
    await db.flush()
    if contact is not None:
        await assign_primary_contact(db, row, contact.id)
    await emit_event(db, workspace_id, 'deal.created', row.id)
    audit_deal(db, row, 'CREATED', user=user)
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
    before = deal_snapshot(row)
    changes = data.model_dump(exclude_unset=True)
    start_date = changes.get("start_date", row.start_date)
    end_date = changes.get("end_date", row.end_date)
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, "Дата начала не может быть позже даты окончания")
    await validate_relations(db, workspace_id, changes.get("client_id", row.client_id),
                             changes.get("pipeline_id", row.pipeline_id), changes.get("stage_id", row.stage_id))
    contact = await validate_deal_contact(db, workspace_id, changes.get("client_id", row.client_id),
                                          changes.get("contact_id", row.contact_id), deal_id)
    if "contact_id" in changes:
        changes["contact_name"] = contact_label(contact) if contact else None
    await validate_responsible(db, workspace_id, changes.get("responsible_user_id", row.responsible_user_id))
    next_stage_id = changes.get("stage_id", row.stage_id)
    if next_stage_id != row.stage_id:
        await emit_event(db, workspace_id, 'deal.stage_changed', row.id, old_stage_id=row.stage_id, stage_id=next_stage_id)
        stages = (await db.scalars(select(PipelineStage).where(
            PipelineStage.workspace_id == workspace_id, PipelineStage.id.in_([row.stage_id, next_stage_id])))).all()
        names = {stage.id: stage.name for stage in stages}
        db.add(DealActivity(workspace_id=workspace_id, deal_id=deal_id, author_user_id=user.id,
                            author_name=" ".join(filter(None, (user.first_name, user.last_name))),
                            kind="STAGE_CHANGE", body=f"Стадия: {names[row.stage_id]} → {names[next_stage_id]}"))
    for name, value in changes.items():
        setattr(row, name, value)
    if "contact_id" in changes:
        primary_id = changes["contact_id"]
        if primary_id is None:
            await db.execute(delete(DealContact).where(DealContact.workspace_id == workspace_id,
                DealContact.deal_id == deal_id, DealContact.is_primary.is_(True)))
            primary_id = await replacement_contact(db, row)
        await assign_primary_contact(db, row, primary_id)
    audit_deal(db, row, 'UPDATED', user=user, before=before)
    await db.commit()
    await db.refresh(row)
    return row


@scoped.delete("/deals/{deal_id}", status_code=204)
async def delete_deal(deal_id: UUID, workspace_id: UUID = Depends(workspace_admin),
                      db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    row = await lock_deal(db, workspace_id, deal_id)
    audit_deal(db, row, 'DELETED', user=user)
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


DEFAULT_STATUSES = [("Сделать", 0, False), ("В работе", 1, False), ("Ожидает контроля", 2, False), ("Завершено", 3, True)]


async def ensure_task_statuses(db: AsyncSession, workspace_id: UUID) -> list[TaskStatus]:
    # Serialize first initialization; renamed/deleted defaults must not reappear.
    await db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    if not await db.scalar(select(TaskStatus.id).where(TaskStatus.workspace_id == workspace_id).limit(1)):
        await db.execute(pg_insert(TaskStatus).values([
            {"id": uuid4(), "workspace_id": workspace_id, "name": name, "position": position, "is_final": final}
            for name, position, final in DEFAULT_STATUSES]).on_conflict_do_nothing())
    return (await db.scalars(select(TaskStatus).where(TaskStatus.workspace_id == workspace_id)
                             .order_by(TaskStatus.position, TaskStatus.name))).all()


async def default_open_status(db: AsyncSession, workspace_id: UUID) -> TaskStatus:
    for status in await ensure_task_statuses(db, workspace_id):
        if not status.is_final:
            return status
    raise HTTPException(409, "В рабочем процессе нет незавершённого статуса")


async def final_task_status(db: AsyncSession, workspace_id: UUID) -> TaskStatus:
    for status in await ensure_task_statuses(db, workspace_id):
        if status.is_final:
            return status
    raise HTTPException(409, "В рабочем процессе нет завершающего статуса")


def apply_task_status(task: Task, status: TaskStatus, user: User):
    task.status_id = status.id
    if status.is_final:
        if task.completed_at is None:
            task.completed_at = datetime.now(timezone.utc)
            task.completed_by_user_id = user.id
    else:
        task.completed_at = None
        task.completed_by_user_id = None


def task_out(task: Task, status: TaskStatus, done: int = 0, total: int = 0) -> dict:
    return {"id": task.id, "workspace_id": task.workspace_id, "title": task.title, "description": task.description,
            "status_id": status.id, "status_name": status.name, "is_final": status.is_final,
            "priority": task.priority, "assignee_user_id": task.assignee_user_id,
            "creator_user_id": task.creator_user_id, "completed_by_user_id": task.completed_by_user_id,
            "start_at": task.start_at, "due_at": task.due_at, "estimate_minutes": task.estimate_minutes,
            "deal_id": task.deal_id, "project_id": task.project_id, "contact_id": task.contact_id,
            "parent_task_id": task.parent_task_id,
            "completed_at": task.completed_at, "created_at": task.created_at, "updated_at": task.updated_at,
            "checklist_done": done, "checklist_total": total}


def legacy_task(task: Task, status: TaskStatus) -> dict:
    return {"id": task.id, "workspace_id": task.workspace_id, "deal_id": task.deal_id, "title": task.title,
            "description": task.description, "priority": task.priority,
            "status": "DONE" if status.is_final else "OPEN", "assignee_user_id": task.assignee_user_id,
            "created_by_user_id": task.creator_user_id, "completed_by_user_id": task.completed_by_user_id,
            "start_at": task.start_at, "due_at": task.due_at, "created_at": task.created_at,
            "updated_at": task.updated_at, "completed_at": task.completed_at}


async def task_rows(db: AsyncSession, workspace_id: UUID, *conditions, limit: int | None = None, offset: int = 0) -> list:
    done = select(func.count()).where(TaskChecklistItem.workspace_id == Task.workspace_id,
                                      TaskChecklistItem.task_id == Task.id,
                                      TaskChecklistItem.is_done.is_(True)).scalar_subquery()
    total = select(func.count()).where(TaskChecklistItem.workspace_id == Task.workspace_id,
                                       TaskChecklistItem.task_id == Task.id).scalar_subquery()
    return (await db.execute(select(Task, TaskStatus, done.label("done"), total.label("total"))
        .join(TaskStatus, (TaskStatus.workspace_id == Task.workspace_id) & (TaskStatus.id == Task.status_id))
        .where(Task.workspace_id == workspace_id, *conditions)
        .order_by(TaskStatus.is_final, TaskStatus.position, Task.due_at, Task.created_at, Task.id)
        .limit(limit).offset(offset))).all()


@scoped.get("/deals/{deal_id}/tasks", response_model=list[DealTaskOut])
async def deal_tasks(deal_id: UUID, workspace_id: UUID = Depends(workspace_access),
                     db: AsyncSession = Depends(get_db)):
    await find_deal(db, workspace_id, deal_id)
    return [legacy_task(task, status) for task, status, _, _ in await task_rows(db, workspace_id, Task.deal_id == deal_id)]


@scoped.post("/deals/{deal_id}/tasks", response_model=DealTaskOut, status_code=201)
async def create_deal_task(deal_id: UUID, data: DealTaskCreate,
                           workspace_id: UUID = Depends(workspace_access), user: User = Depends(current_user),
                           db: AsyncSession = Depends(get_db)):
    await find_deal(db, workspace_id, deal_id)
    await validate_responsible(db, workspace_id, data.assignee_user_id)
    status = await default_open_status(db, workspace_id)
    row = Task(workspace_id=workspace_id, deal_id=deal_id, status_id=status.id, creator_user_id=user.id,
               **data.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return legacy_task(row, status)


async def find_deal_task(db: AsyncSession, workspace_id: UUID, deal_id: UUID, task_id: UUID,
                         lock: bool = False) -> tuple[Task, TaskStatus]:
    if lock:
        await lock_workspace(db, workspace_id)
    query = select(Task, TaskStatus).join(TaskStatus, (TaskStatus.workspace_id == Task.workspace_id) &
        (TaskStatus.id == Task.status_id)).where(Task.id == task_id, Task.workspace_id == workspace_id,
        Task.deal_id == deal_id)
    result = (await db.execute(query.with_for_update(of=Task) if lock else query)).first()
    if result is None:
        raise HTTPException(404, "Task not found")
    return result[0], result[1]


@scoped.patch("/deals/{deal_id}/tasks/{task_id}", response_model=DealTaskOut)
async def update_deal_task(deal_id: UUID, task_id: UUID, data: DealTaskUpdate,
                           workspace_id: UUID = Depends(workspace_access), user: User = Depends(current_user),
                           db: AsyncSession = Depends(get_db)):
    row, status = await find_deal_task(db, workspace_id, deal_id, task_id, lock=True)
    completed_now = False
    changes = data.model_dump(exclude_unset=True)
    start_at = changes.get("start_at", row.start_at)
    due_at = changes.get("due_at", row.due_at)
    if start_at and due_at and start_at > due_at:
        raise HTTPException(422, "Дата начала задачи не может быть позже крайнего срока")
    if "assignee_user_id" in changes:
        await validate_responsible(db, workspace_id, changes["assignee_user_id"])
    if "status" in changes:
        wanted = changes.pop("status")
        target = await final_task_status(db, workspace_id) if wanted == "DONE" else await default_open_status(db, workspace_id)
        if target.id != row.status_id:
            apply_task_status(row, target, user)
            completed_now = target.is_final
            status = target
    for name, value in changes.items():
        setattr(row, name, value)
    if completed_now:
        await stop_timers(db, workspace_id, task_id=row.id, reason="TASK_COMPLETED")
        await repeat_completed_task(db, row, user)
        await emit_event(db, workspace_id, 'task.completed', row.id)
    await db.commit()
    await db.refresh(row)
    return legacy_task(row, status)


@scoped.delete("/deals/{deal_id}/tasks/{task_id}", status_code=204)
async def delete_deal_task(deal_id: UUID, task_id: UUID,
                           workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    row, _ = await find_deal_task(db, workspace_id, deal_id, task_id)
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


def reminder_trigger(row: TaskReminder, task: Task) -> datetime | None:
    if row.kind == "DATE":
        return row.at
    base = task.start_at if row.kind == "START_OFFSET" else task.due_at
    return base - timedelta(minutes=row.offset_minutes) if base is not None else None


def reminder_output(row: TaskReminder, task: Task) -> dict:
    return {"id": row.id, "workspace_id": row.workspace_id, "task_id": row.task_id,
            "recipient_user_id": row.recipient_user_id, "created_by_user_id": row.created_by_user_id,
            "kind": row.kind, "at": row.at, "offset_minutes": row.offset_minutes,
            "trigger_at": reminder_trigger(row, task), "acknowledged_at": row.acknowledged_at,
            "created_at": row.created_at}


@scoped.get("/deals/{deal_id}/tasks/{task_id}/reminders", response_model=list[TaskReminderOut])
async def task_reminders(deal_id: UUID, task_id: UUID, workspace_id: UUID = Depends(workspace_access),
                         db: AsyncSession = Depends(get_db)):
    task, _ = await find_deal_task(db, workspace_id, deal_id, task_id)
    rows = (await db.scalars(select(TaskReminder).where(TaskReminder.workspace_id == workspace_id,
        TaskReminder.task_id == task_id).order_by(TaskReminder.created_at, TaskReminder.id))).all()
    return [reminder_output(row, task) for row in rows]


@scoped.post("/deals/{deal_id}/tasks/{task_id}/reminders", response_model=TaskReminderOut, status_code=201)
async def create_task_reminder(deal_id: UUID, task_id: UUID, data: TaskReminderCreate,
                               workspace_id: UUID = Depends(workspace_access), user: User = Depends(current_user),
                               db: AsyncSession = Depends(get_db)):
    task, status = await find_deal_task(db, workspace_id, deal_id, task_id, lock=True)
    if status.is_final:
        raise HTTPException(409, "Завершённой задаче нельзя назначить напоминание")
    await validate_responsible(db, workspace_id, data.recipient_user_id)
    if (data.kind == "START_OFFSET" and task.start_at is None) or (data.kind == "DUE_OFFSET" and task.due_at is None):
        raise HTTPException(422, "Для относительного напоминания укажите соответствующий срок задачи")
    row = TaskReminder(workspace_id=workspace_id, task_id=task_id, created_by_user_id=user.id,
                       **data.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return reminder_output(row, task)


@scoped.delete("/deals/{deal_id}/tasks/{task_id}/reminders/{reminder_id}", status_code=204)
async def delete_task_reminder(deal_id: UUID, task_id: UUID, reminder_id: UUID,
                               workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    await find_deal_task(db, workspace_id, deal_id, task_id)
    row = await db.scalar(select(TaskReminder).where(TaskReminder.id == reminder_id,
        TaskReminder.workspace_id == workspace_id, TaskReminder.task_id == task_id))
    if row is None:
        raise HTTPException(404, "Reminder not found")
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)



@scoped.get("/reminders/due", response_model=list[DueTaskReminder])
async def due_task_reminders(workspace_id: UUID = Depends(workspace_access),
                             user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(TaskReminder, Task, Deal.title, Deal.id)
        .join(Task, (Task.id == TaskReminder.task_id) & (Task.workspace_id == TaskReminder.workspace_id))
        .join(TaskStatus, (TaskStatus.workspace_id == Task.workspace_id) & (TaskStatus.id == Task.status_id))
        .join(Deal, (Deal.id == Task.deal_id) & (Deal.workspace_id == Task.workspace_id))
        .join(PipelineStage, PipelineStage.id == Deal.stage_id)
        .where(TaskReminder.workspace_id == workspace_id, TaskReminder.recipient_user_id == user.id,
               TaskReminder.acknowledged_at.is_(None), TaskStatus.is_final.is_(False),
               Deal.workspace_id == workspace_id, PipelineStage.workspace_id == workspace_id,
               PipelineStage.stage_type == StageType.OPEN))).all()
    now = datetime.now(timezone.utc)
    result = []
    for reminder, task, deal_title, deal_id in rows:
        trigger = reminder_trigger(reminder, task)
        if trigger is not None and trigger <= now:
            result.append({**reminder_output(reminder, task), "deal_id": deal_id,
                           "deal_title": deal_title, "task_title": task.title})
    return sorted(result, key=lambda item: (item["trigger_at"], str(item["id"])))


@scoped.post("/reminders/{reminder_id}/ack", response_model=TaskReminderOut)
async def acknowledge_task_reminder(reminder_id: UUID, workspace_id: UUID = Depends(workspace_access),
                                    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(TaskReminder).where(TaskReminder.id == reminder_id,
        TaskReminder.workspace_id == workspace_id, TaskReminder.recipient_user_id == user.id).with_for_update())
    if row is None:
        raise HTTPException(404, "Reminder not found")
    task = await db.scalar(select(Task).where(Task.id == row.task_id,
        Task.workspace_id == workspace_id))
    if task is None:
        raise HTTPException(404, "Task not found")
    if row.acknowledged_at is None:
        row.acknowledged_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(row)
    return reminder_output(row, task)


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
    recipient_name = None
    if data.recipient_user_id is not None:
        await db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
        await validate_workspace_member(db, workspace_id, data.recipient_user_id, "Адресат должен быть активным участником студии")
        recipient = await db.get(User, data.recipient_user_id)
        recipient_name = " ".join(filter(None, (recipient.first_name, recipient.last_name)))
    await find_deal(db, workspace_id, deal_id)
    row = DealActivity(workspace_id=workspace_id, deal_id=deal_id, author_user_id=user.id,
                       author_name=" ".join(filter(None, (user.first_name, user.last_name))), body=data.body,
                       kind=data.kind, recipient_user_id=data.recipient_user_id, recipient_name=recipient_name)
    db.add(row)
    await db.flush()
    if data.recipient_user_id is not None:
        db.add(Notification(workspace_id=workspace_id, recipient_user_id=data.recipient_user_id, activity_id=row.id))
    await db.commit()
    await db.refresh(row)
    return row


async def validate_workspace_member(db: AsyncSession, workspace_id: UUID, user_id: UUID, message: str):
    member = await db.scalar(select(WorkspaceMember.user_id).join(User, User.id == WorkspaceMember.user_id).where(
        WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id,
        User.is_active.is_(True)))
    if member is None:
        raise HTTPException(422, message)


@scoped.get("/tags", response_model=list[DealTagOut])
async def workspace_tags(workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    return (await db.scalars(select(DealTag).where(DealTag.workspace_id == workspace_id)
                             .order_by(func.lower(DealTag.name)))).all()


@scoped.get("/deals/{deal_id}/tags", response_model=list[DealTagOut])
async def deal_tags(deal_id: UUID, workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    await find_deal(db, workspace_id, deal_id)
    return (await db.scalars(select(DealTag).join(DealTagLink, (DealTagLink.workspace_id == DealTag.workspace_id) &
        (DealTagLink.tag_id == DealTag.id)).where(DealTagLink.workspace_id == workspace_id,
        DealTagLink.deal_id == deal_id).order_by(func.lower(DealTag.name)))).all()


@scoped.post("/deals/{deal_id}/tags", response_model=DealTagOut, status_code=201)
async def add_deal_tag(deal_id: UUID, data: DealTagCreate, workspace_id: UUID = Depends(workspace_access),
                       db: AsyncSession = Depends(get_db)):
    await lock_deal(db, workspace_id, deal_id)
    await db.execute(pg_insert(DealTag).values(id=uuid4(), workspace_id=workspace_id, name=data.name)
                     .on_conflict_do_nothing())
    tag = await db.scalar(select(DealTag).where(DealTag.workspace_id == workspace_id,
                                                func.lower(DealTag.name) == data.name.lower()))
    if tag is None:
        raise HTTPException(409, "Не удалось создать тег, повторите попытку")
    link = await db.get(DealTagLink, {"workspace_id": workspace_id, "deal_id": deal_id, "tag_id": tag.id})
    if link is None:
        db.add(DealTagLink(workspace_id=workspace_id, deal_id=deal_id, tag_id=tag.id))
    await db.commit()
    await db.refresh(tag)
    return tag


@scoped.delete("/deals/{deal_id}/tags/{tag_id}", status_code=204)
async def remove_deal_tag(deal_id: UUID, tag_id: UUID, workspace_id: UUID = Depends(workspace_access),
                          db: AsyncSession = Depends(get_db)):
    await find_deal(db, workspace_id, deal_id)
    link = await db.get(DealTagLink, {"workspace_id": workspace_id, "deal_id": deal_id, "tag_id": tag_id})
    if link is None:
        raise HTTPException(404, "Тег не привязан к сделке")
    await db.delete(link)
    await db.commit()
    return Response(status_code=204)


@scoped.get("/deals/{deal_id}/watchers", response_model=list[DealWatcherOut])
async def deal_watchers(deal_id: UUID, workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    await find_deal(db, workspace_id, deal_id)
    rows = (await db.execute(select(DealWatcher, User).join(User, User.id == DealWatcher.user_id).where(
        DealWatcher.workspace_id == workspace_id, DealWatcher.deal_id == deal_id)
        .order_by(User.first_name, User.email))).all()
    return [DealWatcherOut(user_id=user.id, first_name=user.first_name, last_name=user.last_name, email=user.email)
            for _, user in rows]


@scoped.post("/deals/{deal_id}/watchers", response_model=DealWatcherOut, status_code=201)
async def add_deal_watcher(deal_id: UUID, data: DealWatcherCreate, workspace_id: UUID = Depends(workspace_access),
                           db: AsyncSession = Depends(get_db)):
    await lock_deal(db, workspace_id, deal_id)
    await validate_workspace_member(db, workspace_id, data.user_id, "Наблюдателем может стать только активный участник студии")
    if await db.get(DealWatcher, {"workspace_id": workspace_id, "deal_id": deal_id, "user_id": data.user_id}) is not None:
        raise HTTPException(409, "Участник уже наблюдает за сделкой")
    db.add(DealWatcher(workspace_id=workspace_id, deal_id=deal_id, user_id=data.user_id))
    await db.commit()
    user = await db.get(User, data.user_id)
    return DealWatcherOut(user_id=user.id, first_name=user.first_name, last_name=user.last_name, email=user.email)


@scoped.delete("/deals/{deal_id}/watchers/{user_id}", status_code=204)
async def remove_deal_watcher(deal_id: UUID, user_id: UUID, workspace_id: UUID = Depends(workspace_access),
                              db: AsyncSession = Depends(get_db)):
    await find_deal(db, workspace_id, deal_id)
    row = await db.get(DealWatcher, {"workspace_id": workspace_id, "deal_id": deal_id, "user_id": user_id})
    if row is None:
        raise HTTPException(404, "Наблюдатель не найден")
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


def contact_link(row: DealContact, contact: Contact) -> DealContactLinkOut:
    return DealContactLinkOut(contact_id=contact.id, is_primary=row.is_primary, first_name=contact.first_name,
                              last_name=contact.last_name, middle_name=contact.middle_name,
                              phone=contact.phone, email=contact.email)


@scoped.get("/deals/{deal_id}/contacts", response_model=list[DealContactLinkOut])
async def deal_contacts(deal_id: UUID, workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    await find_deal(db, workspace_id, deal_id)
    rows = (await db.execute(select(DealContact, Contact).join(Contact, (Contact.workspace_id == DealContact.workspace_id) &
        (Contact.id == DealContact.contact_id)).where(DealContact.workspace_id == workspace_id,
        DealContact.deal_id == deal_id).order_by(DealContact.is_primary.desc(), Contact.first_name))).all()
    return [contact_link(link, contact) for link, contact in rows]


@scoped.post("/deals/{deal_id}/contacts", response_model=DealContactLinkOut, status_code=201)
async def add_deal_contact(deal_id: UUID, data: DealContactLinkCreate, workspace_id: UUID = Depends(workspace_access),
                           db: AsyncSession = Depends(get_db)):
    deal = await lock_deal(db, workspace_id, deal_id)
    contact = await db.scalar(select(Contact).where(Contact.workspace_id == workspace_id, Contact.id == data.contact_id))
    if contact is None:
        raise HTTPException(422, "Контакт должен принадлежать этой студии")
    existing = await db.get(DealContact, {"workspace_id": workspace_id, "deal_id": deal_id, "contact_id": data.contact_id})
    if existing is not None:
        raise HTTPException(409, "Контакт уже связан со сделкой")
    row = DealContact(workspace_id=workspace_id, deal_id=deal_id, contact_id=data.contact_id, is_primary=False)
    db.add(row)
    await db.flush()
    if data.is_primary or deal.contact_id is None:
        await assign_primary_contact(db, deal, data.contact_id)
    await db.commit()
    await db.refresh(row)
    return contact_link(row, contact)


@scoped.patch("/deals/{deal_id}/contacts/{contact_id}", response_model=DealContactLinkOut)
async def set_primary_deal_contact(deal_id: UUID, contact_id: UUID, data: DealContactLinkUpdate,
                                   workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    deal = await lock_deal(db, workspace_id, deal_id)
    row = await db.get(DealContact, {"workspace_id": workspace_id, "deal_id": deal_id, "contact_id": contact_id})
    if row is None:
        raise HTTPException(404, "Контакт не связан со сделкой")
    contact = await db.scalar(select(Contact).where(Contact.workspace_id == workspace_id, Contact.id == contact_id))
    if data.is_primary:
        await assign_primary_contact(db, deal, contact_id)
    elif row.is_primary:
        replacement = await replacement_contact(db, deal, contact_id)
        if replacement is None:
            raise HTTPException(409, "Единственный контакт должен остаться основным; отвяжите контакт для удаления связи")
        await assign_primary_contact(db, deal, replacement)
    await db.commit()
    await db.refresh(row)
    return contact_link(row, contact)


@scoped.delete("/deals/{deal_id}/contacts/{contact_id}", status_code=204)
async def remove_deal_contact(deal_id: UUID, contact_id: UUID, workspace_id: UUID = Depends(workspace_access),
                              db: AsyncSession = Depends(get_db)):
    deal = await lock_deal(db, workspace_id, deal_id)
    row = await db.get(DealContact, {"workspace_id": workspace_id, "deal_id": deal_id, "contact_id": contact_id})
    if row is None:
        raise HTTPException(404, "Контакт не связан со сделкой")
    was_primary = row.is_primary
    await db.delete(row)
    await db.flush()
    if was_primary:
        await assign_primary_contact(db, deal, await replacement_contact(db, deal))
    await db.commit()
    return Response(status_code=204)


@scoped.get("/deals/{deal_id}/attachments", response_model=list[DealAttachmentOut])
async def deal_attachments(deal_id: UUID, workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    await find_deal(db, workspace_id, deal_id)
    return (await db.scalars(select(DealAttachment).where(DealAttachment.workspace_id == workspace_id,
                                                          DealAttachment.deal_id == deal_id)
                             .order_by(DealAttachment.created_at.desc()))).all()


@scoped.post("/deals/{deal_id}/attachments", response_model=DealAttachmentOut, status_code=201)
async def add_deal_attachment(deal_id: UUID, data: DealAttachmentCreate, workspace_id: UUID = Depends(workspace_access),
                              user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await find_deal(db, workspace_id, deal_id)
    row = DealAttachment(workspace_id=workspace_id, deal_id=deal_id, filename=data.filename,
                         content_type=data.content_type, size_bytes=data.size_bytes, uploaded_by_user_id=user.id,
                         uploaded_by_name=" ".join(filter(None, (user.first_name, user.last_name))))
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@scoped.delete("/deals/{deal_id}/attachments/{attachment_id}", status_code=204)
async def remove_deal_attachment(deal_id: UUID, attachment_id: UUID, workspace_id: UUID = Depends(workspace_access),
                                 db: AsyncSession = Depends(get_db)):
    await find_deal(db, workspace_id, deal_id)
    row = await db.scalar(select(DealAttachment).where(DealAttachment.workspace_id == workspace_id,
                                                       DealAttachment.deal_id == deal_id,
                                                       DealAttachment.id == attachment_id))
    if row is None:
        raise HTTPException(404, "Вложение не найдено")
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


def parse_custom_field(field: DealCustomField) -> dict:
    if field.type == "NUMBER":
        try:
            number = Decimal(field.value.strip().replace(",", "."))
        except (InvalidOperation, AttributeError):
            raise HTTPException(422, f"Поле «{field.key}» должно быть числом")
        return {"field_type": "NUMBER", "value_number": number, "value_text": None, "value_date": None}
    if field.type == "DATE":
        try:
            day = date.fromisoformat(field.value.strip())
        except ValueError:
            raise HTTPException(422, f"Поле «{field.key}» должно быть датой в формате ГГГГ-ММ-ДД")
        return {"field_type": "DATE", "value_date": day, "value_text": None, "value_number": None}
    return {"field_type": "TEXT", "value_text": field.value, "value_number": None, "value_date": None}


def custom_field_out(row: DealCustomValue) -> DealCustomField:
    if row.field_type == "NUMBER":
        value = "" if row.value_number is None else format(row.value_number.normalize(), "f")
    elif row.field_type == "DATE":
        value = "" if row.value_date is None else row.value_date.isoformat()
    else:
        value = row.value_text or ""
    return DealCustomField(key=row.field_key, type=row.field_type, value=value)


@scoped.get("/deals/{deal_id}/custom-fields", response_model=DealCustomFieldsOut)
async def deal_custom_fields(deal_id: UUID, workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    await find_deal(db, workspace_id, deal_id)
    rows = (await db.scalars(select(DealCustomValue).where(DealCustomValue.workspace_id == workspace_id,
                                                           DealCustomValue.deal_id == deal_id))).all()
    return {"values": [custom_field_out(row) for row in sorted(rows, key=lambda item: item.field_key.casefold())]}


@scoped.put("/deals/{deal_id}/custom-fields", response_model=DealCustomFieldsOut)
async def save_deal_custom_fields(deal_id: UUID, data: DealCustomFields, workspace_id: UUID = Depends(workspace_access),
                                  db: AsyncSession = Depends(get_db)):
    await lock_deal(db, workspace_id, deal_id)
    parsed = [(field, parse_custom_field(field)) for field in data.values]
    await db.execute(delete(DealCustomValue).where(DealCustomValue.workspace_id == workspace_id,
                                                   DealCustomValue.deal_id == deal_id))
    for field, columns in parsed:
        db.add(DealCustomValue(workspace_id=workspace_id, deal_id=deal_id, field_key=field.key, **columns))
    await db.commit()
    rows = (await db.scalars(select(DealCustomValue).where(DealCustomValue.workspace_id == workspace_id,
                                                           DealCustomValue.deal_id == deal_id))).all()
    return {"values": [custom_field_out(row) for row in sorted(rows, key=lambda item: item.field_key.casefold())]}


def status_out(row: TaskStatus) -> dict:
    return {"id": row.id, "name": row.name, "position": row.position, "is_final": row.is_final}


@scoped.get("/task-statuses", response_model=list[TaskStatusOut])
async def task_statuses(workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    rows = await ensure_task_statuses(db, workspace_id)
    await db.commit()
    return [status_out(row) for row in rows]


@scoped.post("/task-statuses", response_model=TaskStatusOut, status_code=201)
async def create_task_status(data: TaskStatusCreate, workspace_id: UUID = Depends(workspace_admin),
                             db: AsyncSession = Depends(get_db)):
    await ensure_task_statuses(db, workspace_id)
    if await db.scalar(select(TaskStatus.id).where(TaskStatus.workspace_id == workspace_id,
                                                   TaskStatus.name == data.name)):
        raise HTTPException(409, "Статус с таким названием уже есть")
    position = (await db.scalar(select(func.coalesce(func.max(TaskStatus.position), -1))
                                .where(TaskStatus.workspace_id == workspace_id))) + 1
    row = TaskStatus(workspace_id=workspace_id, name=data.name, position=position, is_final=data.is_final)
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Статус с таким названием уже есть")
    await db.refresh(row)
    return status_out(row)


async def lock_task_status(db: AsyncSession, workspace_id: UUID, status_id: UUID) -> TaskStatus:
    await db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    row = await db.scalar(select(TaskStatus).where(TaskStatus.id == status_id,
                                                   TaskStatus.workspace_id == workspace_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Status not found")
    return row


async def final_status_count(db: AsyncSession, workspace_id: UUID) -> int:
    return await db.scalar(select(func.count()).where(TaskStatus.workspace_id == workspace_id,
                                                      TaskStatus.is_final.is_(True)))


@scoped.patch("/task-statuses/{status_id}", response_model=TaskStatusOut)
async def update_task_status(status_id: UUID, data: TaskStatusUpdate, workspace_id: UUID = Depends(workspace_admin),
                             db: AsyncSession = Depends(get_db)):
    row = await lock_task_status(db, workspace_id, status_id)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes:
        duplicate = await db.scalar(select(TaskStatus.id).where(TaskStatus.workspace_id == workspace_id,
                                                                TaskStatus.name == changes["name"],
                                                                TaskStatus.id != status_id))
        if duplicate:
            raise HTTPException(409, "Статус с таким названием уже есть")
    if changes.get("is_final") is False and row.is_final and await final_status_count(db, workspace_id) <= 1:
        raise HTTPException(409, "В рабочем процессе должен остаться завершающий статус")
    if "is_final" in changes and changes["is_final"] != row.is_final and await db.scalar(
            select(Task.id).where(Task.workspace_id == workspace_id, Task.status_id == status_id).limit(1)):
        raise HTTPException(409, "Нельзя менять признак завершения статуса с задачами; сначала перенесите задачи")
    for name, value in changes.items():
        setattr(row, name, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Статус с таким названием уже есть")
    await db.refresh(row)
    return status_out(row)


@scoped.put("/task-statuses/order", response_model=list[TaskStatusOut])
async def reorder_task_statuses(data: TaskStatusOrder, workspace_id: UUID = Depends(workspace_admin),
                                db: AsyncSession = Depends(get_db)):
    await db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    rows = (await db.scalars(select(TaskStatus).where(TaskStatus.workspace_id == workspace_id)
                             .with_for_update())).all()
    if set(data.ids) != {row.id for row in rows}:
        raise HTTPException(422, "Нужно перечислить все статусы студии")
    by_id = {row.id: row for row in rows}
    for position, status_id in enumerate(data.ids):
        by_id[status_id].position = position
    await db.commit()
    return [status_out(row) for row in await ensure_task_statuses(db, workspace_id)]


@scoped.delete("/task-statuses/{status_id}", status_code=204)
async def delete_task_status(status_id: UUID, workspace_id: UUID = Depends(workspace_admin),
                             db: AsyncSession = Depends(get_db)):
    row = await lock_task_status(db, workspace_id, status_id)
    if await db.scalar(select(Task.id).where(Task.workspace_id == workspace_id,
                                             Task.status_id == status_id).limit(1)):
        raise HTTPException(409, "Статус с задачами удалить нельзя")
    if row.is_final and await final_status_count(db, workspace_id) <= 1:
        raise HTTPException(409, "В рабочем процессе должен остаться завершающий статус")
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


async def find_task(db: AsyncSession, workspace_id: UUID, task_id: UUID, lock: bool = False) -> tuple[Task, TaskStatus]:
    if lock:
        await lock_workspace(db, workspace_id)
    query = select(Task, TaskStatus).join(TaskStatus, (TaskStatus.workspace_id == Task.workspace_id) &
        (TaskStatus.id == Task.status_id)).where(Task.id == task_id, Task.workspace_id == workspace_id)
    result = (await db.execute(query.with_for_update(of=Task) if lock else query)).first()
    if result is None:
        raise HTTPException(404, "Task not found")
    return result[0], result[1]


async def checklist_counts(db: AsyncSession, task: Task) -> tuple[int, int]:
    total = await db.scalar(select(func.count()).where(TaskChecklistItem.workspace_id == task.workspace_id,
                                                       TaskChecklistItem.task_id == task.id))
    done = await db.scalar(select(func.count()).where(TaskChecklistItem.workspace_id == task.workspace_id,
                                                      TaskChecklistItem.task_id == task.id,
                                                      TaskChecklistItem.is_done.is_(True)))
    return done or 0, total or 0


async def validate_task_status(db: AsyncSession, workspace_id: UUID, status_id: UUID) -> TaskStatus:
    row = await db.scalar(select(TaskStatus).where(TaskStatus.id == status_id,
                                                   TaskStatus.workspace_id == workspace_id))
    if row is None:
        raise HTTPException(422, "Статус должен принадлежать этой студии")
    return row


async def validate_task_links(db: AsyncSession, workspace_id: UUID, deal_id: UUID | None, project_id: UUID | None,
                              contact_id: UUID | None, parent_task_id: UUID | None, task_id: UUID | None = None):
    if deal_id is not None:
        await find_deal(db, workspace_id, deal_id)
    if project_id is not None:
        project = await db.scalar(select(Project).where(Project.workspace_id == workspace_id,
                                                       Project.id == project_id))
        if project is None:
            raise HTTPException(422, "Проект должен принадлежать этой студии")
        if project.status == "ARCHIVED":
            raise HTTPException(422, "Нельзя добавить задачу в архивный проект")
    if contact_id is not None:
        contact = await db.scalar(select(Contact.id).where(Contact.workspace_id == workspace_id,
                                                           Contact.id == contact_id))
        if contact is None:
            raise HTTPException(422, "Контакт должен принадлежать этой студии")
    if parent_task_id is not None:
        if parent_task_id == task_id:
            raise HTTPException(422, "Задача не может быть родителем самой себе")
        parent = await db.scalar(select(Task).where(Task.workspace_id == workspace_id, Task.id == parent_task_id))
        if parent is None:
            raise HTTPException(422, "Родительская задача не найдена в этой студии")
        if parent.parent_task_id is not None:
            raise HTTPException(422, "Подзадачи допускаются только на одном уровне вложенности")


@scoped.get("/tasks", response_model=list[TaskOut])
async def workspace_tasks(workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db),
                          deal_id: UUID | None = None, project_id: UUID | None = None, contact_id: UUID | None = None,
                          status_id: UUID | None = None, assignee_user_id: UUID | None = None, parent_task_id: UUID | None = None,
                          include_done: bool = True, limit: int = Query(200, ge=1, le=500),
                          offset: int = Query(0, ge=0)):
    conditions = []
    for column, value in ((Task.deal_id, deal_id), (Task.project_id, project_id), (Task.contact_id, contact_id),
                          (Task.status_id, status_id), (Task.assignee_user_id, assignee_user_id),
                          (Task.parent_task_id, parent_task_id)):
        if value is not None:
            conditions.append(column == value)
    if not include_done:
        conditions.append(TaskStatus.is_final.is_(False))
    rows = await task_rows(db, workspace_id, *conditions, limit=limit, offset=offset)
    return [task_out(task, status, done, total) for task, status, done, total in rows]


@scoped.post("/tasks", response_model=TaskOut, status_code=201)
async def create_task(data: TaskCreate, workspace_id: UUID = Depends(workspace_access),
                      user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await validate_responsible(db, workspace_id, data.assignee_user_id)
    await validate_task_links(db, workspace_id, data.deal_id, data.project_id, data.contact_id, data.parent_task_id)
    status = await validate_task_status(db, workspace_id, data.status_id) if data.status_id else await default_open_status(db, workspace_id)
    values = data.model_dump(exclude={"status_id"})
    row = Task(workspace_id=workspace_id, status_id=status.id, creator_user_id=user.id, **values)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return task_out(row, status)


@scoped.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: UUID, workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    task, status = await find_task(db, workspace_id, task_id)
    done, total = await checklist_counts(db, task)
    return task_out(task, status, done, total)


@scoped.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(task_id: UUID, data: TaskUpdate, workspace_id: UUID = Depends(workspace_access),
                      user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    task, status = await find_task(db, workspace_id, task_id, lock=True)
    changes = data.model_dump(exclude_unset=True)
    completed_now = False
    start_at = changes.get("start_at", task.start_at)
    due_at = changes.get("due_at", task.due_at)
    if start_at and due_at and start_at > due_at:
        raise HTTPException(422, "Дата начала задачи не может быть позже крайнего срока")
    if "assignee_user_id" in changes:
        await validate_responsible(db, workspace_id, changes["assignee_user_id"])
    if {"deal_id", "project_id", "contact_id", "parent_task_id"} & changes.keys():
        await validate_task_links(db, workspace_id, changes.get("deal_id", task.deal_id),
                                  changes.get("project_id", task.project_id),
                                  changes.get("contact_id", task.contact_id),
                                  changes.get("parent_task_id", task.parent_task_id), task_id)
    if changes.get("status_id") is not None:
        target = await validate_task_status(db, workspace_id, changes["status_id"])
        if target.id != task.status_id:
            apply_task_status(task, target, user)
            completed_now = target.is_final
            status = target
        changes.pop("status_id")
    if "parent_task_id" in changes and changes["parent_task_id"] is not None:
        children = await db.scalar(select(Task.id).where(Task.workspace_id == workspace_id,
                                                         Task.parent_task_id == task_id).limit(1))
        if children:
            raise HTTPException(422, "У задачи с подзадачами нельзя менять родителя")
    for name, value in changes.items():
        setattr(task, name, value)
    if completed_now:
        await stop_timers(db, workspace_id, task_id=task.id, reason="TASK_COMPLETED")
        await repeat_completed_task(db, task, user)
        await emit_event(db, workspace_id, 'task.completed', task.id)
    await db.commit()
    await db.refresh(task)
    done, total = await checklist_counts(db, task)
    return task_out(task, status, done, total)


@scoped.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: UUID, workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    task, _ = await find_task(db, workspace_id, task_id)
    await db.delete(task)
    await db.commit()
    return Response(status_code=204)


@scoped.get("/tasks/{task_id}/checklist", response_model=list[TaskChecklistItemOut])
async def task_checklist(task_id: UUID, workspace_id: UUID = Depends(workspace_access),
                         db: AsyncSession = Depends(get_db)):
    await find_task(db, workspace_id, task_id)
    return (await db.scalars(select(TaskChecklistItem).where(TaskChecklistItem.workspace_id == workspace_id,
                                                             TaskChecklistItem.task_id == task_id)
                             .order_by(TaskChecklistItem.position, TaskChecklistItem.created_at))).all()


@scoped.post("/tasks/{task_id}/checklist", response_model=TaskChecklistItemOut, status_code=201)
async def add_checklist_item(task_id: UUID, data: TaskChecklistItemCreate,
                             workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    await find_task(db, workspace_id, task_id)
    position = (await db.scalar(select(func.coalesce(func.max(TaskChecklistItem.position), -1))
                                .where(TaskChecklistItem.workspace_id == workspace_id,
                                       TaskChecklistItem.task_id == task_id))) + 1
    row = TaskChecklistItem(workspace_id=workspace_id, task_id=task_id, text=data.text, position=position)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def find_checklist_item(db: AsyncSession, workspace_id: UUID, task_id: UUID, item_id: UUID) -> TaskChecklistItem:
    row = await db.scalar(select(TaskChecklistItem).where(TaskChecklistItem.id == item_id,
                                                          TaskChecklistItem.workspace_id == workspace_id,
                                                          TaskChecklistItem.task_id == task_id))
    if row is None:
        raise HTTPException(404, "Checklist item not found")
    return row


@scoped.patch("/tasks/{task_id}/checklist/{item_id}", response_model=TaskChecklistItemOut)
async def update_checklist_item(task_id: UUID, item_id: UUID, data: TaskChecklistItemUpdate,
                                workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    await find_task(db, workspace_id, task_id)
    row = await find_checklist_item(db, workspace_id, task_id, item_id)
    for name, value in data.model_dump(exclude_unset=True).items():
        setattr(row, name, value)
    await db.commit()
    await db.refresh(row)
    return row


@scoped.delete("/tasks/{task_id}/checklist/{item_id}", status_code=204)
async def delete_checklist_item(task_id: UUID, item_id: UUID, workspace_id: UUID = Depends(workspace_access),
                                db: AsyncSession = Depends(get_db)):
    await find_task(db, workspace_id, task_id)
    await db.delete(await find_checklist_item(db, workspace_id, task_id, item_id))
    await db.commit()
    return Response(status_code=204)


@scoped.get("/tasks/{task_id}/watchers", response_model=list[DealWatcherOut])
async def task_watchers(task_id: UUID, workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    await find_task(db, workspace_id, task_id)
    rows = (await db.execute(select(TaskWatcher, User).join(User, User.id == TaskWatcher.user_id).where(
        TaskWatcher.workspace_id == workspace_id, TaskWatcher.task_id == task_id)
        .order_by(User.first_name, User.email))).all()
    return [DealWatcherOut(user_id=user.id, first_name=user.first_name, last_name=user.last_name, email=user.email)
            for _, user in rows]


@scoped.post("/tasks/{task_id}/watchers", response_model=DealWatcherOut, status_code=201)
async def add_task_watcher(task_id: UUID, data: DealWatcherCreate, workspace_id: UUID = Depends(workspace_access),
                           db: AsyncSession = Depends(get_db)):
    await find_task(db, workspace_id, task_id, lock=True)
    await validate_workspace_member(db, workspace_id, data.user_id, "Наблюдателем может стать только активный участник студии")
    if await db.get(TaskWatcher, {"workspace_id": workspace_id, "task_id": task_id, "user_id": data.user_id}) is not None:
        raise HTTPException(409, "Участник уже наблюдает за задачей")
    db.add(TaskWatcher(workspace_id=workspace_id, task_id=task_id, user_id=data.user_id))
    await db.commit()
    user = await db.get(User, data.user_id)
    return DealWatcherOut(user_id=user.id, first_name=user.first_name, last_name=user.last_name, email=user.email)


@scoped.delete("/tasks/{task_id}/watchers/{user_id}", status_code=204)
async def remove_task_watcher(task_id: UUID, user_id: UUID, workspace_id: UUID = Depends(workspace_access),
                              db: AsyncSession = Depends(get_db)):
    await find_task(db, workspace_id, task_id)
    row = await db.get(TaskWatcher, {"workspace_id": workspace_id, "task_id": task_id, "user_id": user_id})
    if row is None:
        raise HTTPException(404, "Наблюдатель не найден")
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


router.include_router(scoped)
