from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from app.api.v1.schemas import Name, Output

PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OrganizationInput(Input):
    name: Name
    tax_id: Annotated[str, StringConstraints(pattern=r"^(\d{10}|\d{12})?$", max_length=12)] = ""
    tax_branch: Annotated[str, StringConstraints(pattern=r"^(\d{9})?$", max_length=9)] = ""
    address: str = Field(default="", max_length=1000)
    bank: str = Field(default="", max_length=255)
    bank_account: str = Field(default="", max_length=34)
    bank_code: str = Field(default="", max_length=11)


class OrganizationOut(OrganizationInput, Output):
    id: UUID


class InvoiceCreate(Input):
    organization_id: UUID
    client_id: UUID
    deal_id: UUID | None = None
    project_id: UUID | None = None
    manager_user_id: UUID | None = None
    issued_on: date
    amount: PositiveMoney
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
    buyer_tax_id: Annotated[str, StringConstraints(pattern=r"^(\d{10}|\d{12})?$", max_length=12)] = ""
    buyer_address: str = Field(default="", max_length=1000)


class InvoiceTransition(Input):
    state: Literal["ISSUED", "CANCELLED"]


class InvoiceOut(Output):
    id: UUID
    number: int
    issued_on: date
    client_id: UUID
    organization_id: UUID
    deal_id: UUID | None
    project_id: UUID | None
    manager_user_id: UUID | None
    amount: Decimal
    currency: str
    description: str
    state: str
    status: Literal["DRAFT", "ISSUED", "PARTIAL", "PAID", "CANCELLED"]
    paid_amount: Decimal
    remaining_amount: Decimal
    sent_at: datetime | None
    seller: dict
    buyer: dict


class PaymentCreate(Input):
    request_key: UUID
    paid_on: date
    amount: PositiveMoney
    method: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)] = "BANK"
    comment: str | None = Field(default=None, max_length=2000)


class PaymentOut(Output):
    id: UUID
    request_key: UUID
    paid_on: date
    amount: Decimal
    method: str
    comment: str | None


class ActCreate(Input):
    issued_on: date


class ActOut(Output):
    id: UUID
    number: int
    invoice_id: UUID
    issued_on: date
    status: str
    signed_at: datetime | None
