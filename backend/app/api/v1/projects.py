from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import current_user, workspace_access, workspace_admin
from app.api.v1.crm import validate_workspace_member
from app.api.v1.schemas import (ProjectContactOut, ProjectCreate, ProjectEventCreate, ProjectEventOut, ProjectMemberCreate, ProjectMemberOut, ProjectOut,
                                ProjectStageOut, ProjectUpdate)
from app.core.database import get_db
from app.models import (Client, Contact, Deal, DealContact, PipelineStage, Project, ProjectContact, ProjectEvent, ProjectMember, ProjectStage, Task, TaskStatus,
                        User, Workspace, WorkspaceMember)
from app.models.entities import StageType
from app.services.project_templates import apply_template

router = APIRouter(tags=["Projects"])
scoped = APIRouter(prefix="/workspaces/{workspace_id}")

DEFAULT_STAGES = [("Подготовка", 0), ("В работе", 1), ("Сдача", 2), ("Завершён", 3)]


async def ensure_project_stages(db: AsyncSession, workspace_id: UUID) -> list[ProjectStage]:
    await db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    if not await db.scalar(select(ProjectStage.id).where(ProjectStage.workspace_id == workspace_id).limit(1)):
        await db.execute(pg_insert(ProjectStage).values([
            {"id": uuid4(), "workspace_id": workspace_id, "name": name, "position": position}
            for name, position in DEFAULT_STAGES]).on_conflict_do_nothing())
    return (await db.scalars(select(ProjectStage).where(ProjectStage.workspace_id == workspace_id)
                             .order_by(ProjectStage.position, ProjectStage.name))).all()


def stage_out(row: ProjectStage) -> dict:
    return {"id": row.id, "name": row.name, "position": row.position}


def project_out(project: Project, stage: ProjectStage, total: int = 0, done: int = 0, members: int = 0) -> dict:
    return {"id": project.id, "workspace_id": project.workspace_id, "title": project.title,
            "client_id": project.client_id, "deal_id": project.deal_id, "stage_id": stage.id,
            "stage_name": stage.name, "manager_user_id": project.manager_user_id, "amount": project.amount,
            "currency": project.currency, "start_date": project.start_date, "end_date": project.end_date,
            "status": project.status, "archived_at": project.archived_at, "created_at": project.created_at,
            "updated_at": project.updated_at, "tasks_total": total, "tasks_done": done, "members_count": members}


async def project_rows(db: AsyncSession, workspace_id: UUID, *conditions) -> list:
    total = select(func.count()).where(Task.workspace_id == Project.workspace_id,
                                       Task.project_id == Project.id).scalar_subquery()
    done = select(func.count()).where(Task.workspace_id == Project.workspace_id,
                                      Task.project_id == Project.id,
                                      Task.status_id.in_(select(TaskStatus.id).where(
                                          TaskStatus.workspace_id == Project.workspace_id,
                                          TaskStatus.is_final.is_(True)))).scalar_subquery()
    members = select(func.count()).where(ProjectMember.workspace_id == Project.workspace_id,
                                         ProjectMember.project_id == Project.id).scalar_subquery()
    return (await db.execute(select(Project, ProjectStage, total.label("total"), done.label("done"), members.label("members"))
        .join(ProjectStage, (ProjectStage.workspace_id == Project.workspace_id) & (ProjectStage.id == Project.stage_id))
        .where(Project.workspace_id == workspace_id, *conditions)
        .order_by(Project.created_at.desc(), Project.id))).all()


async def find_project(db: AsyncSession, workspace_id: UUID, project_id: UUID, lock: bool = False) -> tuple[Project, ProjectStage]:
    if lock:
        # Same lock order as workspace membership changes, including assignments.
        await db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    query = select(Project, ProjectStage).join(ProjectStage, (ProjectStage.workspace_id == Project.workspace_id) &
        (ProjectStage.id == Project.stage_id)).where(Project.id == project_id, Project.workspace_id == workspace_id)
    row = (await db.execute(query.with_for_update(of=Project) if lock else query)).first()
    if row is None:
        raise HTTPException(404, "Project not found")
    return row[0], row[1]


async def add_event(db: AsyncSession, workspace_id: UUID, project_id: UUID, user: User, body: str, kind: str = "NOTE") -> ProjectEvent:
    row = ProjectEvent(workspace_id=workspace_id, project_id=project_id, author_user_id=user.id,
                       author_name=" ".join(filter(None, (user.first_name, user.last_name))), kind=kind, body=body)
    db.add(row)
    return row


async def validate_stage(db: AsyncSession, workspace_id: UUID, stage_id: UUID | None) -> ProjectStage:
    if stage_id is not None:
        row = await db.scalar(select(ProjectStage).where(ProjectStage.workspace_id == workspace_id,
                                                         ProjectStage.id == stage_id))
        if row is not None:
            return row
        raise HTTPException(422, "Этап проекта должен принадлежать этой студии")
    stages = await ensure_project_stages(db, workspace_id)
    if not stages:
        raise HTTPException(409, "У студии нет этапов проектов")
    return stages[0]


@scoped.get("/project-stages", response_model=list[ProjectStageOut])
async def project_stages(workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    rows = await ensure_project_stages(db, workspace_id)
    await db.commit()
    return [stage_out(row) for row in rows]


@scoped.get("/projects", response_model=list[ProjectOut])
async def projects(workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db),
                   status: str = Query("active", pattern="^(active|archive|all)$"),
                   client_id: UUID | None = None, deal_id: UUID | None = None):
    conditions = []
    if status == "active":
        conditions.append(Project.status == "ACTIVE")
    elif status == "archive":
        conditions.append(Project.status != "ACTIVE")
    if client_id is not None:
        conditions.append(Project.client_id == client_id)
    if deal_id is not None:
        conditions.append(Project.deal_id == deal_id)
    rows = await project_rows(db, workspace_id, *conditions)
    return [project_out(project, stage, total, done, members) for project, stage, total, done, members in rows]


async def deal_for_project(db: AsyncSession, workspace_id: UUID, deal_id: UUID) -> Deal:
    deal = await db.scalar(select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id).with_for_update())
    if deal is None:
        raise HTTPException(422, "Сделка должна принадлежать этой студии")
    stage_type = await db.scalar(select(PipelineStage.stage_type).where(PipelineStage.id == deal.stage_id,
                                                                        PipelineStage.workspace_id == workspace_id))
    if stage_type != StageType.WON:
        raise HTTPException(422, "Проект создаётся только из выигранной сделки")
    return deal


@scoped.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(data: ProjectCreate, workspace_id: UUID = Depends(workspace_access),
                         user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    stage = await validate_stage(db, workspace_id, data.stage_id)
    values: dict = {"start_date": data.start_date, "end_date": data.end_date}
    deal: Deal | None = None
    if data.deal_id is not None:
        deal = await deal_for_project(db, workspace_id, data.deal_id)
        existing = await db.scalar(select(Project.id).where(Project.workspace_id == workspace_id,
                                                             Project.deal_id == data.deal_id))
        if existing is not None and not data.force:
            raise HTTPException(409, "Проект из этой сделки уже создан")
    client_id = data.client_id or (deal.client_id if deal else None)
    if client_id is None:
        raise HTTPException(422, "Укажите клиента проекта")
    client = await db.scalar(select(Client.id).where(Client.workspace_id == workspace_id, Client.id == client_id))
    if client is None:
        raise HTTPException(422, "Клиент должен принадлежать этой студии")
    manager_id = data.manager_user_id if data.manager_user_id is not None else (deal.responsible_user_id if deal else None)
    if manager_id is not None:
        await validate_workspace_member(db, workspace_id, manager_id, "Менеджер проекта должен быть активным участником студии")
    workspace = await db.get(Workspace, workspace_id)
    if deal is not None:
        values.update({"title": data.title or deal.title, "client_id": client_id, "deal_id": deal.id,
                       "manager_user_id": manager_id, "amount": data.amount if data.amount is not None else deal.amount})
        row = Project(workspace_id=workspace_id, stage_id=stage.id, currency=deal.currency, **values)
    else:
        row = Project(workspace_id=workspace_id, title=data.title, client_id=client_id, stage_id=stage.id,
                      manager_user_id=manager_id, amount=data.amount if data.amount is not None else Decimal("0"),
                      currency=workspace.currency, **values)
    db.add(row)
    await db.flush()
    if data.template_id is not None:
        template_name = await apply_template(db, workspace_id, row, data.template_id)
        await add_event(db, workspace_id, row.id, user, f"Применён шаблон «{template_name}»", "TEMPLATE")
    if deal is not None:
        contact_ids = set((await db.scalars(select(DealContact.contact_id).where(
            DealContact.workspace_id == workspace_id, DealContact.deal_id == deal.id))).all())
        if deal.contact_id is not None:
            contact_ids.add(deal.contact_id)
        for contact_id in contact_ids:
            db.add(ProjectContact(workspace_id=workspace_id, project_id=row.id, contact_id=contact_id))
        await add_event(db, workspace_id, row.id, user, f"Проект создан из сделки «{deal.title}»", "CREATED")
    else:
        await add_event(db, workspace_id, row.id, user, "Проект создан", "CREATED")
    if manager_id is not None:
        db.add(ProjectMember(workspace_id=workspace_id, project_id=row.id, user_id=manager_id, role="LEAD"))
    await db.commit()
    await db.refresh(row)
    return project_out(row, stage)


@scoped.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: UUID, workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    project, stage = await find_project(db, workspace_id, project_id)
    rows = await project_rows(db, workspace_id, Project.id == project_id)
    _, _, total, done, members = rows[0]
    return project_out(project, stage, total, done, members)


@scoped.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(project_id: UUID, data: ProjectUpdate, workspace_id: UUID = Depends(workspace_access),
                         user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    project, stage = await find_project(db, workspace_id, project_id, lock=True)
    changes = data.model_dump(exclude_unset=True)
    start_date = changes.get("start_date", project.start_date)
    end_date = changes.get("end_date", project.end_date)
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, "Дата начала не может быть позже даты окончания")
    if "manager_user_id" in changes and changes["manager_user_id"] is not None:
        await validate_workspace_member(db, workspace_id, changes["manager_user_id"],
                                        "Менеджер проекта должен быть активным участником студии")
    if changes.get("stage_id") is not None:
        stage = await validate_stage(db, workspace_id, changes["stage_id"])
        changes.pop("stage_id")
        project.stage_id = stage.id
    if "status" in changes:
        project.status = changes.pop("status")
        project.archived_at = datetime.now(timezone.utc) if project.status == "ARCHIVED" else None
        await add_event(db, workspace_id, project_id, user,
                        "Проект в архиве" if project.status == "ARCHIVED" else "Статус проекта изменён", "STATUS")
    for name, value in changes.items():
        setattr(project, name, value)
    await db.commit()
    await db.refresh(project)
    rows = await project_rows(db, workspace_id, Project.id == project_id)
    _, _, total, done, members = rows[0]
    return project_out(project, stage, total, done, members)


@scoped.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: UUID, workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    project, _ = await find_project(db, workspace_id, project_id)
    await db.delete(project)
    await db.commit()
    return Response(status_code=204)


@scoped.get("/projects/{project_id}/members", response_model=list[ProjectMemberOut])
async def project_members(project_id: UUID, workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    await find_project(db, workspace_id, project_id)
    rows = (await db.execute(select(ProjectMember, User).join(User, User.id == ProjectMember.user_id).where(
        ProjectMember.workspace_id == workspace_id, ProjectMember.project_id == project_id)
        .order_by(ProjectMember.role, User.first_name))).all()
    return [ProjectMemberOut(user_id=user.id, first_name=user.first_name, last_name=user.last_name,
                             email=user.email, role=member.role) for member, user in rows]


@scoped.post("/projects/{project_id}/members", response_model=ProjectMemberOut, status_code=201)
async def add_project_member(project_id: UUID, data: ProjectMemberCreate, workspace_id: UUID = Depends(workspace_access),
                             user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await find_project(db, workspace_id, project_id, lock=True)
    await validate_workspace_member(db, workspace_id, data.user_id, "Участник проекта должен быть активным участником студии")
    if await db.get(ProjectMember, {"workspace_id": workspace_id, "project_id": project_id, "user_id": data.user_id}):
        raise HTTPException(409, "Участник уже добавлен в проект")
    db.add(ProjectMember(workspace_id=workspace_id, project_id=project_id, user_id=data.user_id, role=data.role))
    member = await db.get(User, data.user_id)
    await add_event(db, workspace_id, project_id, user,
                    f"В команду добавлен {member.first_name}", "MEMBER")
    await db.commit()
    return ProjectMemberOut(user_id=member.id, first_name=member.first_name, last_name=member.last_name,
                            email=member.email, role=data.role)


@scoped.delete("/projects/{project_id}/members/{member_user_id}", status_code=204)
async def remove_project_member(project_id: UUID, member_user_id: UUID, workspace_id: UUID = Depends(workspace_access),
                                user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await find_project(db, workspace_id, project_id)
    row = await db.get(ProjectMember, {"workspace_id": workspace_id, "project_id": project_id, "user_id": member_user_id})
    if row is None:
        raise HTTPException(404, "Участник проекта не найден")
    await db.delete(row)
    member = await db.get(User, member_user_id)
    await add_event(db, workspace_id, project_id, user,
                    f"Из команды удалён {member.first_name}" if member else "Участник удалён из проекта", "MEMBER")
    await db.commit()
    return Response(status_code=204)


@scoped.get("/projects/{project_id}/contacts", response_model=list[ProjectContactOut])
async def project_contacts(project_id: UUID, workspace_id: UUID = Depends(workspace_access), db: AsyncSession = Depends(get_db)):
    await find_project(db, workspace_id, project_id)
    rows = (await db.execute(select(ProjectContact, Contact).join(Contact, (Contact.workspace_id == ProjectContact.workspace_id) &
        (Contact.id == ProjectContact.contact_id)).where(ProjectContact.workspace_id == workspace_id,
        ProjectContact.project_id == project_id).order_by(Contact.first_name))).all()
    return [ProjectContactOut(contact_id=contact.id, first_name=contact.first_name, last_name=contact.last_name,
                              middle_name=contact.middle_name, phone=contact.phone, email=contact.email)
            for _, contact in rows]


@scoped.get("/projects/{project_id}/events", response_model=list[ProjectEventOut])
async def project_events(project_id: UUID, workspace_id: UUID = Depends(workspace_access),
                         db: AsyncSession = Depends(get_db), limit: int = Query(100, ge=1, le=500)):
    await find_project(db, workspace_id, project_id)
    return (await db.scalars(select(ProjectEvent).where(ProjectEvent.workspace_id == workspace_id,
                                                        ProjectEvent.project_id == project_id)
                             .order_by(ProjectEvent.created_at.desc(), ProjectEvent.id.desc()).limit(limit))).all()


@scoped.post("/projects/{project_id}/events", response_model=ProjectEventOut, status_code=201)
async def add_project_event(project_id: UUID, data: ProjectEventCreate, workspace_id: UUID = Depends(workspace_access),
                            user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await find_project(db, workspace_id, project_id)
    event = await add_event(db, workspace_id, project_id, user, data.body)
    await db.commit()
    await db.refresh(event)
    return event


router.include_router(scoped)
