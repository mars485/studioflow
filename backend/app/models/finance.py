"""Simple receivables, deliberately not a bookkeeping ledger."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import TimestampMixin


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"
    __table_args__ = (UniqueConstraint("workspace_id", "id", name="uq_organizations_workspace_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    tax_id: Mapped[str] = mapped_column(String(12), default="")
    tax_branch: Mapped[str] = mapped_column(String(9), default="")
    address: Mapped[str] = mapped_column(String(1000), default="")
    bank: Mapped[str] = mapped_column(String(255), default="")
    bank_account: Mapped[str] = mapped_column(String(34), default="")
    bank_code: Mapped[str] = mapped_column(String(11), default="")


class FinanceCounter(Base):
    __tablename__ = "finance_counters"
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(10), primary_key=True)
    value: Mapped[int] = mapped_column(Integer)


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_invoices_workspace_id"),
        UniqueConstraint("workspace_id", "number", name="uq_invoices_workspace_number"),
        ForeignKeyConstraint(["workspace_id", "client_id"], ["clients.workspace_id", "clients.id"], name="fk_invoices_client"),
        ForeignKeyConstraint(["workspace_id", "organization_id"], ["organizations.workspace_id", "organizations.id"], name="fk_invoices_organization"),
        ForeignKeyConstraint(["workspace_id", "deal_id"], ["deals.workspace_id", "deals.id"], name="fk_invoices_workspace_deal", deferrable=True, initially="DEFERRED"),
        ForeignKeyConstraint(["workspace_id", "project_id"], ["projects.workspace_id", "projects.id"], name="fk_invoices_workspace_project", deferrable=True, initially="DEFERRED"),
        CheckConstraint("amount > 0", name="ck_invoices_amount"),
        CheckConstraint("state IN ('DRAFT', 'ISSUED', 'CANCELLED')", name="ck_invoices_state"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    issued_on: Mapped[date] = mapped_column(Date)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    deal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deals.id", ondelete="SET NULL", name="fk_invoices_deal"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL", name="fk_invoices_project"))
    manager_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    description: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(10), default="DRAFT", server_default="DRAFT")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seller: Mapped[dict] = mapped_column(JSONB)
    buyer: Mapped[dict] = mapped_column(JSONB)


class InvoicePayment(Base):
    __tablename__ = "invoice_payments"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "invoice_id"], ["invoices.workspace_id", "invoices.id"], name="fk_payments_invoice", ondelete="CASCADE"),
        CheckConstraint("amount > 0", name="ck_invoice_payments_amount"),
        UniqueConstraint("workspace_id", "invoice_id", "request_key", name="uq_payments_request_key"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    paid_on: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    method: Mapped[str] = mapped_column(String(50))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Act(Base):
    __tablename__ = "acts"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "invoice_id"], ["invoices.workspace_id", "invoices.id"], name="fk_acts_invoice", ondelete="CASCADE"),
        UniqueConstraint("workspace_id", "number", name="uq_acts_workspace_number"),
        CheckConstraint("status IN ('DRAFT', 'SIGNED')", name="ck_acts_status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    number: Mapped[int] = mapped_column(Integer)
    issued_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(10), default="DRAFT", server_default="DRAFT")
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
