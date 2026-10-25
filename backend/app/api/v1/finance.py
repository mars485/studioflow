from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import workspace_admin
from app.api.v1.crm import validate_workspace_member
from app.api.v1.finance_schemas import (ActCreate, ActOut, InvoiceCreate, InvoiceOut, InvoiceTransition,
                                      OrganizationInput, OrganizationOut, PaymentCreate, PaymentOut)
from app.core.database import get_db
from app.models import Client, Deal, Project, Workspace
from app.models.finance import Act, FinanceCounter, Invoice, InvoicePayment, Organization

# Finances are restricted to OWNER/ADMIN, including reads and printable snapshots.
router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["Finance"])


async def find(db, model, workspace_id, object_id, lock=False):
    query = select(model).where(model.workspace_id == workspace_id, model.id == object_id)
    row = await db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise HTTPException(404, "Объект не найден")
    return row


async def next_number(db, workspace_id, kind):
    # Atomic UPSERT locks the counter even for the first concurrent requests.
    return await db.scalar(insert(FinanceCounter).values(workspace_id=workspace_id, kind=kind, value=1)
                           .on_conflict_do_update(index_elements=["workspace_id", "kind"],
                                                  set_={"value": FinanceCounter.value + 1})
                           .returning(FinanceCounter.value))


async def invoice_out(db, row):
    paid = await db.scalar(select(func.coalesce(func.sum(InvoicePayment.amount), 0)).where(
        InvoicePayment.workspace_id == row.workspace_id, InvoicePayment.invoice_id == row.id))
    paid = paid.quantize(Decimal("0.01"))
    result = {column.name: getattr(row, column.name) for column in Invoice.__table__.columns}
    result.update(paid_amount=paid, remaining_amount=row.amount - paid,
                  status=("PAID" if paid == row.amount else "PARTIAL" if paid > 0 else row.state))
    return result


@router.get("/organizations", response_model=list[OrganizationOut])
async def organizations(workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    return (await db.scalars(select(Organization).where(Organization.workspace_id == workspace_id)
                             .order_by(Organization.name, Organization.id))).all()


@router.post("/organizations", response_model=OrganizationOut, status_code=201)
async def create_organization(data: OrganizationInput, workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    row = Organization(workspace_id=workspace_id, **data.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/organizations/{organization_id}", response_model=OrganizationOut)
async def update_organization(organization_id: UUID, data: OrganizationInput, workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    row = await find(db, Organization, workspace_id, organization_id, lock=True)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/invoices", response_model=list[InvoiceOut])
async def invoices(workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db),
                   deal_id: UUID | None = None, project_id: UUID | None = None,
                   limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    query = select(Invoice).where(Invoice.workspace_id == workspace_id)
    for column, value in ((Invoice.deal_id, deal_id), (Invoice.project_id, project_id)):
        if value is not None:
            query = query.where(column == value)
    rows = (await db.scalars(query.order_by(Invoice.number.desc()).limit(limit).offset(offset))).all()
    return [await invoice_out(db, row) for row in rows]


@router.post("/invoices", response_model=InvoiceOut, status_code=201)
async def create_invoice(data: InvoiceCreate, workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    client = await find(db, Client, workspace_id, data.client_id)
    organization = await find(db, Organization, workspace_id, data.organization_id)
    for model, object_id in ((Deal, data.deal_id), (Project, data.project_id)):
        if object_id is not None:
            linked = await find(db, model, workspace_id, object_id, lock=True)
            if linked.client_id != client.id:
                raise HTTPException(422, "Клиент счёта и связанного объекта должен совпадать")
    if data.manager_user_id is not None:
        await validate_workspace_member(db, workspace_id, data.manager_user_id, "Менеджер должен быть участником студии")
    workspace = await db.get(Workspace, workspace_id)
    values = data.model_dump(exclude={"buyer_tax_id", "buyer_address"})
    row = Invoice(workspace_id=workspace_id, number=await next_number(db, workspace_id, "INVOICE"),
                  currency=workspace.currency,
                  seller={key: getattr(organization, key) for key in OrganizationInput.model_fields},
                  buyer={"name": client.name, "tax_id": data.buyer_tax_id, "address": data.buyer_address}, **values)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return await invoice_out(db, row)


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
async def get_invoice(invoice_id: UUID, workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    return await invoice_out(db, await find(db, Invoice, workspace_id, invoice_id))


@router.patch("/invoices/{invoice_id}", response_model=InvoiceOut)
async def transition(invoice_id: UUID, data: InvoiceTransition, workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    row = await find(db, Invoice, workspace_id, invoice_id, lock=True)
    if data.state != row.state:
        if row.state == "CANCELLED" or (data.state == "ISSUED" and row.state != "DRAFT"):
            raise HTTPException(409, "Недопустимый переход статуса")
        if data.state == "CANCELLED":
            paid = (await invoice_out(db, row))["paid_amount"]
            has_act = await db.scalar(select(Act.id).where(Act.workspace_id == workspace_id, Act.invoice_id == row.id).limit(1))
            if paid or has_act:
                raise HTTPException(409, "Нельзя отменить счёт с оплатами или актами")
        row.state = data.state
    await db.commit()
    await db.refresh(row)
    return await invoice_out(db, row)


@router.post("/invoices/{invoice_id}/sent", response_model=InvoiceOut)
async def mark_sent(invoice_id: UUID, workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    row = await find(db, Invoice, workspace_id, invoice_id, lock=True)
    if row.state != "ISSUED":
        raise HTTPException(409, "Сначала выставьте счёт")
    row.sent_at = row.sent_at or datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return await invoice_out(db, row)


@router.get("/invoices/{invoice_id}/payments", response_model=list[PaymentOut])
async def payments(invoice_id: UUID, workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    await find(db, Invoice, workspace_id, invoice_id)
    return (await db.scalars(select(InvoicePayment).where(InvoicePayment.workspace_id == workspace_id,
        InvoicePayment.invoice_id == invoice_id).order_by(InvoicePayment.created_at, InvoicePayment.id))).all()


@router.post("/invoices/{invoice_id}/payments", response_model=PaymentOut, status_code=201)
async def add_payment(invoice_id: UUID, data: PaymentCreate, workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    row = await find(db, Invoice, workspace_id, invoice_id, lock=True)
    existing = await db.scalar(select(InvoicePayment).where(InvoicePayment.workspace_id == workspace_id,
        InvoicePayment.invoice_id == invoice_id, InvoicePayment.request_key == data.request_key))
    if existing is not None:
        if any(getattr(existing, key) != value for key, value in data.model_dump().items()):
            raise HTTPException(409, "Ключ платежа уже использован с другими данными")
        return existing
    if row.state != "ISSUED":
        raise HTTPException(409, "Оплата принимается только по выставленному счёту")
    remaining = (await invoice_out(db, row))["remaining_amount"]
    if data.amount > remaining:
        raise HTTPException(422, "Переплата не допускается")
    payment = InvoicePayment(workspace_id=workspace_id, invoice_id=invoice_id, **data.model_dump())
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return payment


@router.get("/invoices/{invoice_id}/acts", response_model=list[ActOut])
async def acts(invoice_id: UUID, workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    await find(db, Invoice, workspace_id, invoice_id)
    return (await db.scalars(select(Act).where(Act.workspace_id == workspace_id, Act.invoice_id == invoice_id)
                             .order_by(Act.number))).all()


@router.post("/invoices/{invoice_id}/acts", response_model=ActOut, status_code=201)
async def create_act(invoice_id: UUID, data: ActCreate, workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    invoice = await find(db, Invoice, workspace_id, invoice_id, lock=True)
    if invoice.state != "ISSUED":
        raise HTTPException(409, "Акт создаётся по выставленному счёту")
    row = Act(workspace_id=workspace_id, invoice_id=invoice_id, issued_on=data.issued_on,
              number=await next_number(db, workspace_id, "ACT"))
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.post("/acts/{act_id}/sign", response_model=ActOut)
async def sign_act(act_id: UUID, workspace_id: UUID = Depends(workspace_admin), db: AsyncSession = Depends(get_db)):
    row = await find(db, Act, workspace_id, act_id, lock=True)
    row.status = "SIGNED"
    row.signed_at = row.signed_at or datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row
