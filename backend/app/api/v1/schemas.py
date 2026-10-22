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
    color: str | None


class StageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    stage_type: Literal["OPEN", "WON", "LOST"] = "OPEN"
    color: Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")] | None = None


class StageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] | None = None
    stage_type: Literal["OPEN", "WON", "LOST"] | None = None
    color: Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")] | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in ("name", "stage_type") if key in self.model_fields_set):
            raise ValueError("Specify at least one stage field; name and type cannot be null")
        return self


class StageOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[UUID] = Field(min_length=2)


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
    responsible_user_id: UUID | None = None
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
    responsible_user_id: UUID | None = None
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


class FollowUpComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome_comment: str | None = Field(default=None, max_length=10000)


class FollowUpCompletionOut(Output):
    id: UUID
    deal_id: UUID
    completed_by_user_id: UUID | None
    completed_by_name: str
    scheduled_at: datetime
    action: Action
    planned_comment: str | None
    outcome_comment: str | None
    completed_at: datetime


class DealActivityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]


class DealActivityOut(Output):
    id: UUID
    deal_id: UUID
    author_user_id: UUID | None
    author_name: str
    body: str
    kind: Literal["NOTE", "STAGE_CHANGE"]
    created_at: datetime


class DealOut(Output):
    id: UUID
    workspace_id: UUID
    title: str
    client_id: UUID
    pipeline_id: UUID
    stage_id: UUID
    responsible_user_id: UUID | None
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


class FollowUpCompleteResult(Output):
    completion: FollowUpCompletionOut
    deal: DealOut
