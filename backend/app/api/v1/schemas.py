from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Action = Literal["call", "message", "proposal", "decision"]


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class WorkspaceOut(Output):
    role: Literal["OWNER", "ADMIN", "MANAGER"]
    id: UUID
    name: str
    currency: str
    timezone: str


class ClientOut(Output):
    id: UUID
    name: str


class ClientCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name


class StageOut(Output):
    id: UUID
    pipeline_id: UUID
    name: str
    position: int
    stage_type: str


class PipelineOut(Output):
    id: UUID
    name: str
    is_default: bool
    stages: list[StageOut]


class DealCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Name
    client_id: UUID
    pipeline_id: UUID
    stage_id: UUID
    amount: Money = Decimal("0")
    contact_name: str | None = Field(default=None, max_length=255)
    source: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=10000)


class DealUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Name | None = None
    client_id: UUID | None = None
    pipeline_id: UUID | None = None
    stage_id: UUID | None = None
    amount: Money | None = None
    contact_name: str | None = Field(default=None, max_length=255)
    source: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        for name in ("title", "client_id", "pipeline_id", "stage_id", "amount"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class FollowUp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    at: AwareDatetime
    action: Action
    comment: str | None = Field(default=None, max_length=10000)


class DealOut(Output):
    id: UUID
    workspace_id: UUID
    title: str
    client_id: UUID
    pipeline_id: UUID
    stage_id: UUID
    amount: Decimal
    currency: str
    contact_name: str | None
    source: str | None
    description: str | None
    follow_up_at: datetime | None
    follow_up_action: Action | None
    follow_up_comment: str | None
    created_at: datetime
    updated_at: datetime
