import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, ValidationError, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import current_user, workspace_admin
from app.api.v1.crm import assign_primary_contact, lock_workspace
from app.api.v1.schemas import Money, Name, Output
from app.core.config import settings
from app.core.database import get_db
from app.core.http import read_limited_body
from app.core.security import token_digest
from app.models import Client, Contact, ContactClient, Deal, DealActivity, Pipeline, PipelineStage, User, Workspace, WorkspaceMember
from app.models.entities import StageType
from app.models.integrations import IncomingLead, IntegrationToken
from app.services.webhooks import emit_event
from app.services.audit import audit_deal

router = APIRouter(tags=["Incoming leads"])
bearer = HTTPBearer(auto_error=False)


class TokenCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    pipeline_id: UUID | None = None
    expires_days: int = Field(default=90, ge=1, le=365)


class TokenOut(Output):
    id: UUID
    name: str
    hint: str
    pipeline_id: UUID | None
    expires_at: datetime
    revoked_at: datetime | None
    created_at: datetime
    last_used_at: datetime | None
    scope: Literal["leads:create"] = "leads:create"


class TokenSecret(TokenOut):
    token: str


class LeadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: UUID
    title: Name
    company_name: Name
    contact_first_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] | None = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = None
    email: EmailStr | None = None
    message: Annotated[str, StringConstraints(strip_whitespace=True, max_length=10000)] | None = None
    source: Name = "Website"
    amount: Money = Decimal("0")

    @field_validator("email")
    @classmethod
    def email_lower(cls, value):
        return value.lower() if value else None


class LeadOut(Output):
    id: UUID
    request_key: UUID
    client_id: UUID | None
    deal_id: UUID | None
    created_at: datetime
    replayed: bool = False


async def admin_locked(db, workspace_id, user_id):
    await lock_workspace(db, workspace_id)
    role = await db.scalar(select(WorkspaceMember.role).join(User, User.id == WorkspaceMember.user_id).where(
        WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id, User.is_active.is_(True)))
    if role is None:
        raise HTTPException(404, "Workspace not found")
    if role not in ("OWNER", "ADMIN"):
        raise HTTPException(403, "Требуется роль владельца или администратора")


@router.get("/workspaces/{workspace_id}/integration-tokens", response_model=list[TokenOut])
async def tokens(workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db),
                 limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    return (await db.scalars(select(IntegrationToken).where(IntegrationToken.workspace_id == workspace_id)
        .order_by(IntegrationToken.created_at.desc(), IntegrationToken.id).limit(limit).offset(offset))).all()


@router.post("/workspaces/{workspace_id}/integration-tokens", response_model=TokenSecret, status_code=201)
async def create_token(data: TokenCreate, workspace_id: UUID = Depends(workspace_admin),
                        user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await admin_locked(db, workspace_id, user.id)
    now = datetime.now(timezone.utc)
    count = await db.scalar(select(func.count()).where(IntegrationToken.workspace_id == workspace_id,
        IntegrationToken.revoked_at.is_(None), IntegrationToken.expires_at > now))
    if count >= 20:
        raise HTTPException(409, "Не более 20 активных интеграционных токенов")
    query = select(Pipeline).where(Pipeline.workspace_id == workspace_id, Pipeline.is_active.is_(True))
    if data.pipeline_id is not None:
        query = query.where(Pipeline.id == data.pipeline_id)
    pipeline = await db.scalar(query.order_by(Pipeline.is_default.desc(), Pipeline.id).limit(1))
    if pipeline is None:
        raise HTTPException(422, "Выберите активную воронку этой студии")
    secret = "sf_lead_" + secrets.token_urlsafe(32)
    row = IntegrationToken(workspace_id=workspace_id, name=data.name, pipeline_id=pipeline.id,
        created_by_user_id=user.id, token_hash=token_digest(secret), hint="…" + secret[-6:], expires_at=now + timedelta(days=data.expires_days))
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return TokenSecret(**TokenOut.model_validate(row).model_dump(), token=secret)


@router.post("/workspaces/{workspace_id}/integration-tokens/{token_id}/revoke", response_model=TokenOut)
async def revoke_token(token_id: UUID, workspace_id: UUID = Depends(workspace_admin),
                        user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await admin_locked(db, workspace_id, user.id)
    row = await db.scalar(select(IntegrationToken).where(IntegrationToken.workspace_id == workspace_id, IntegrationToken.id == token_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Токен не найден")
    row.revoked_at = row.revoked_at or datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


async def lead_token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: AsyncSession = Depends(get_db)) -> IntegrationToken:
    invalid = HTTPException(401, "Интеграционный токен недействителен", headers={"WWW-Authenticate": "Bearer"})
    if credentials is None or not credentials.credentials.startswith("sf_lead_") or len(credentials.credentials) > 128:
        raise invalid
    digest = token_digest(credentials.credentials)
    workspace_id = await db.scalar(select(IntegrationToken.workspace_id).where(IntegrationToken.token_hash == digest))
    if workspace_id is None:
        raise invalid
    await lock_workspace(db, workspace_id)
    row = await db.scalar(select(IntegrationToken).join(WorkspaceMember,
        (WorkspaceMember.workspace_id == IntegrationToken.workspace_id) & (WorkspaceMember.user_id == IntegrationToken.created_by_user_id))
        .join(User, User.id == WorkspaceMember.user_id).where(IntegrationToken.token_hash == digest,
            IntegrationToken.revoked_at.is_(None), IntegrationToken.expires_at > datetime.now(timezone.utc),
            User.is_active.is_(True), WorkspaceMember.role.in_(["OWNER", "ADMIN"]))
        .with_for_update(of=IntegrationToken).execution_options(populate_existing=True))
    if row is None:
        raise invalid
    return row


@router.post("/integrations/leads", response_model=LeadOut, status_code=201,
    openapi_extra={"requestBody": {"required": True, "content": {"application/json": {"schema": LeadInput.model_json_schema()}}}})
async def incoming_lead(request: Request, response: Response, token: IntegrationToken = Depends(lead_token), db: AsyncSession = Depends(get_db)):
    if request.headers.get("content-type", "").split(';', 1)[0].lower() != "application/json":
        raise HTTPException(415, "Требуется application/json")
    raw = await read_limited_body(request, 64 * 1024)
    try:
        data = LeadInput.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(422, "Некорректная заявка: проверьте обязательные поля, UUID, email, сумму и длины строк")
    normalized = data.model_dump(mode="json")
    normalized["amount"] = str(data.amount.quantize(Decimal("0.01")))
    digest = hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    receipt = await db.scalar(select(IncomingLead).where(IncomingLead.workspace_id == token.workspace_id, IncomingLead.request_key == data.request_key))
    if receipt is not None:
        if receipt.request_digest != digest:
            raise HTTPException(409, "Ключ заявки уже использован с другими данными")
        response.status_code = 200
        return LeadOut.model_validate(receipt).model_copy(update={"replayed": True})
    pipeline = await db.scalar(select(Pipeline).where(Pipeline.workspace_id == token.workspace_id,
        Pipeline.id == token.pipeline_id, Pipeline.is_active.is_(True)).with_for_update())
    if pipeline is None:
        raise HTTPException(409, "Настроенная воронка недоступна; создайте новый токен для активной воронки")
    stage = await db.scalar(select(PipelineStage).where(PipelineStage.workspace_id == token.workspace_id,
        PipelineStage.pipeline_id == pipeline.id, PipelineStage.stage_type == StageType.OPEN)
        .order_by(PipelineStage.position, PipelineStage.id).limit(1).with_for_update())
    if stage is None:
        raise HTTPException(409, "В воронке нет открытого этапа")
    now = datetime.now(timezone.utc)
    if token.hour_started_at is None or now >= token.hour_started_at + timedelta(hours=1):
        token.hour_started_at, token.hour_count = now, 0
    if token.hour_count >= settings.integration_lead_hour_limit:
        raise HTTPException(429, "Превышен часовой лимит заявок токена", headers={"Retry-After": "3600"})
    client = Client(workspace_id=token.workspace_id, name=data.company_name, phone=data.phone, email=data.email)
    db.add(client)
    await db.flush()
    contact = None
    if data.contact_first_name:
        contact = Contact(workspace_id=token.workspace_id, first_name=data.contact_first_name, phone=data.phone, email=data.email)
        db.add(contact)
        await db.flush()
        db.add(ContactClient(workspace_id=token.workspace_id, contact_id=contact.id, client_id=client.id))
    workspace = await db.get(Workspace, token.workspace_id)
    deal = Deal(workspace_id=token.workspace_id, title=data.title, client_id=client.id, pipeline_id=pipeline.id,
        stage_id=stage.id, amount=data.amount, currency=workspace.currency, source=data.source, description=data.message,
        responsible_user_id=token.created_by_user_id)
    db.add(deal)
    await db.flush()
    if contact:
        await assign_primary_contact(db, deal, contact.id)
    await emit_event(db, token.workspace_id, 'deal.created', deal.id)
    audit_deal(db, deal, 'CREATED', token=token)
    db.add(DealActivity(workspace_id=token.workspace_id, deal_id=deal.id, author_user_id=token.created_by_user_id,
        author_name=("Интеграция: " + token.name)[:255], kind="EVENT", body="Принята входящая заявка с источником «" + data.source + "»"))
    receipt = IncomingLead(workspace_id=token.workspace_id, request_key=data.request_key, request_digest=digest,
        token_id=token.id, client_id=client.id, deal_id=deal.id)
    db.add(receipt)
    token.hour_count += 1
    token.last_used_at = now
    await db.commit()
    await db.refresh(receipt)
    return receipt


@router.get("/workspaces/{workspace_id}/integration-leads")
async def lead_journal(workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db),
                       limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    rows = (await db.execute(select(IncomingLead, Deal.title).outerjoin(Deal,
        (Deal.workspace_id == IncomingLead.workspace_id) & (Deal.id == IncomingLead.deal_id))
        .where(IncomingLead.workspace_id == workspace_id).order_by(IncomingLead.created_at.desc(), IncomingLead.id.desc())
        .limit(limit).offset(offset))).all()
    return [{**LeadOut.model_validate(row).model_dump(), "deal_title": title} for row, title in rows]
