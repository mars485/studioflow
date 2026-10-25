from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

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
    type: str
    name: str
    phone: str | None
    email: str | None
    website: str | None
    notes: str | None


class ClientCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = None
    email: EmailStr | None = None
    website: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    notes: str | None = Field(default=None, max_length=10000)


class ClientUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name | None = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = None
    email: EmailStr | None = None
    website: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    notes: str | None = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set or ("name" in self.model_fields_set and self.name is None):
            raise ValueError("Specify at least one field; name cannot be null")
        return self


ContactName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
OptionalContactName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None


class ContactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_name: ContactName
    last_name: OptionalContactName = None
    middle_name: OptionalContactName = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = None
    email: EmailStr | None = None
    website: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    notes: str | None = Field(default=None, max_length=10000)
    client_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_clients(self):
        if len(self.client_ids) != len(set(self.client_ids)):
            raise ValueError("Company links must be unique")
        return self


class ContactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_name: ContactName | None = None
    last_name: OptionalContactName = None
    middle_name: OptionalContactName = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = None
    email: EmailStr | None = None
    website: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    notes: str | None = Field(default=None, max_length=10000)
    client_ids: list[UUID] | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set or ("first_name" in self.model_fields_set and self.first_name is None):
            raise ValueError("Specify at least one field; first_name cannot be null")
        if self.client_ids is not None and len(self.client_ids) != len(set(self.client_ids)):
            raise ValueError("Company links must be unique")
        return self


class ContactOut(Output):
    id: UUID
    workspace_id: UUID
    first_name: str
    last_name: str | None
    middle_name: str | None
    phone: str | None
    email: str | None
    website: str | None
    notes: str | None
    client_ids: list[UUID]
    created_at: datetime
    updated_at: datetime


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
    is_active: bool
    stages: list[StageOut]


class PipelineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name


class PipelineUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name


class DealCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Name
    client_id: UUID
    contact_id: UUID | None = None
    pipeline_id: UUID
    stage_id: UUID
    responsible_user_id: UUID | None = None
    amount: Money = Decimal("0")
    contact_name: str | None = Field(default=None, max_length=255)
    source: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=10000)
    start_date: date | None = None
    end_date: date | None = None
    utm_source: str | None = Field(default=None, max_length=255)
    utm_medium: str | None = Field(default=None, max_length=255)
    utm_campaign: str | None = Field(default=None, max_length=255)
    utm_term: str | None = Field(default=None, max_length=255)
    utm_content: str | None = Field(default=None, max_length=255)
    http_referrer: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def check_dates(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("Дата начала не может быть позже даты окончания")
        return self


class DealUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Name | None = None
    client_id: UUID | None = None
    contact_id: UUID | None = None
    pipeline_id: UUID | None = None
    stage_id: UUID | None = None
    responsible_user_id: UUID | None = None
    amount: Money | None = None
    contact_name: str | None = Field(default=None, max_length=255)
    source: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=10000)
    start_date: date | None = None
    end_date: date | None = None
    utm_source: str | None = Field(default=None, max_length=255)
    utm_medium: str | None = Field(default=None, max_length=255)
    utm_campaign: str | None = Field(default=None, max_length=255)
    utm_term: str | None = Field(default=None, max_length=255)
    utm_content: str | None = Field(default=None, max_length=255)
    http_referrer: str | None = Field(default=None, max_length=2048)

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
    kind: Literal["NOTE", "EVENT", "MENTION"] = "NOTE"
    recipient_user_id: UUID | None = None

    @model_validator(mode="after")
    def validate_recipient(self):
        if (self.kind == "MENTION") != (self.recipient_user_id is not None):
            raise ValueError("Выберите адресата для упоминания; комментарии и события не имеют адресата")
        return self


class DealActivityOut(Output):
    id: UUID
    deal_id: UUID
    author_user_id: UUID | None
    author_name: str
    recipient_user_id: UUID | None
    recipient_name: str | None
    body: str
    kind: Literal["NOTE", "STAGE_CHANGE", "EVENT", "MENTION"]
    created_at: datetime


class DealTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Name
    description: str | None = Field(default=None, max_length=10000)
    priority: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    assignee_user_id: UUID | None = None
    start_at: AwareDatetime | None = None
    due_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.start_at and self.due_at and self.start_at > self.due_at:
            raise ValueError("Дата начала задачи не может быть позже крайнего срока")
        return self


class DealTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Name | None = None
    description: str | None = Field(default=None, max_length=10000)
    priority: Literal["LOW", "MEDIUM", "HIGH"] | None = None
    status: Literal["OPEN", "DONE"] | None = None
    assignee_user_id: UUID | None = None
    start_at: AwareDatetime | None = None
    due_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def reject_null_required(self):
        for name in ("title", "priority", "status"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class DealTaskOut(Output):
    id: UUID
    workspace_id: UUID
    deal_id: UUID
    title: str
    description: str | None
    priority: Literal["LOW", "MEDIUM", "HIGH"]
    status: Literal["OPEN", "DONE"]
    assignee_user_id: UUID | None
    created_by_user_id: UUID | None
    completed_by_user_id: UUID | None
    start_at: datetime | None
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class MyDayTask(BaseModel):
    task: DealTaskOut
    deal_title: str


class MyDayFollowUp(BaseModel):
    deal_id: UUID
    deal_title: str
    at: datetime
    action: Action
    comment: str | None


class MyDayOut(BaseModel):
    tasks: list[MyDayTask]
    follow_ups: list[MyDayFollowUp]


class TaskReminderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipient_user_id: UUID
    kind: Literal["DATE", "START_OFFSET", "DUE_OFFSET"]
    at: AwareDatetime | None = None
    offset_minutes: int | None = Field(default=None, ge=0, le=525600)

    @model_validator(mode="after")
    def check_trigger(self):
        if self.kind == "DATE" and (self.at is None or self.offset_minutes is not None):
            raise ValueError("Для напоминания по дате укажите дату и время")
        if self.kind != "DATE" and (self.at is not None or self.offset_minutes is None):
            raise ValueError("Для напоминания до срока укажите интервал в минутах")
        return self


class TaskReminderOut(Output):
    id: UUID
    workspace_id: UUID
    task_id: UUID
    recipient_user_id: UUID
    created_by_user_id: UUID | None
    kind: Literal["DATE", "START_OFFSET", "DUE_OFFSET"]
    at: datetime | None
    offset_minutes: int | None
    trigger_at: datetime | None
    acknowledged_at: datetime | None
    created_at: datetime


class DueTaskReminder(TaskReminderOut):
    deal_id: UUID
    deal_title: str
    task_title: str


class DealOut(Output):
    id: UUID
    workspace_id: UUID
    title: str
    client_id: UUID
    contact_id: UUID | None
    pipeline_id: UUID
    stage_id: UUID
    responsible_user_id: UUID | None
    amount: Decimal
    currency: str
    contact_name: str | None
    source: str | None
    description: str | None
    start_date: date | None
    end_date: date | None
    utm_source: str | None
    utm_medium: str | None
    utm_campaign: str | None
    utm_term: str | None
    utm_content: str | None
    http_referrer: str | None
    follow_up_at: datetime | None
    follow_up_action: Action | None
    follow_up_comment: str | None
    created_at: datetime
    updated_at: datetime


class FollowUpCompleteResult(Output):
    completion: FollowUpCompletionOut
    deal: DealOut


TagName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class DealTagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: TagName


class DealTagOut(Output):
    id: UUID
    name: str
    created_at: datetime


class DealWatcherCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID


class DealWatcherOut(BaseModel):
    user_id: UUID
    first_name: str
    last_name: str | None
    email: str


class DealContactLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contact_id: UUID
    is_primary: bool = False


class DealContactLinkUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_primary: bool


class DealContactLinkOut(BaseModel):
    contact_id: UUID
    is_primary: bool
    first_name: str
    last_name: str | None
    middle_name: str | None
    phone: str | None
    email: str | None


class DealAttachmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    content_type: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] = "application/octet-stream"
    size_bytes: int = Field(default=0, ge=0, le=1000000000)


class DealAttachmentOut(Output):
    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    has_content: bool
    sha256: str | None
    uploaded_by_user_id: UUID | None
    uploaded_by_name: str
    created_at: datetime


FieldType = Literal["TEXT", "NUMBER", "DATE"]


class DealCustomField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    type: FieldType
    value: str = Field(default="", max_length=10000)


class DealCustomFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: list[DealCustomField] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_keys(self):
        keys = [item.key.casefold() for item in self.values]
        if len(keys) != len(set(keys)):
            raise ValueError("Ключи пользовательских полей должны быть уникальны")
        return self


class DealCustomFieldsOut(BaseModel):
    values: list[DealCustomField]


class TaskStatusOut(Output):
    id: UUID
    name: str
    position: int
    is_final: bool


class TaskStatusCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    is_final: bool = False


class TaskStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)] | None = None
    is_final: bool | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Укажите хотя бы одно поле статуса; название не может быть пустым")
        return self


class TaskStatusOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[UUID] = Field(min_length=2)


TaskPriority = Literal["LOW", "MEDIUM", "HIGH"]


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Name
    description: str | None = Field(default=None, max_length=10000)
    status_id: UUID | None = None
    priority: TaskPriority = "MEDIUM"
    assignee_user_id: UUID | None = None
    start_at: AwareDatetime | None = None
    due_at: AwareDatetime | None = None
    estimate_minutes: int | None = Field(default=None, ge=0, le=525600)
    deal_id: UUID | None = None
    project_id: UUID | None = None
    contact_id: UUID | None = None
    parent_task_id: UUID | None = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.start_at and self.due_at and self.start_at > self.due_at:
            raise ValueError("Дата начала задачи не может быть позже крайнего срока")
        return self


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Name | None = None
    description: str | None = Field(default=None, max_length=10000)
    status_id: UUID | None = None
    priority: TaskPriority | None = None
    assignee_user_id: UUID | None = None
    start_at: AwareDatetime | None = None
    due_at: AwareDatetime | None = None
    estimate_minutes: int | None = Field(default=None, ge=0, le=525600)
    deal_id: UUID | None = None
    project_id: UUID | None = None
    contact_id: UUID | None = None
    parent_task_id: UUID | None = None

    @model_validator(mode="after")
    def reject_null_required(self):
        for name in ("title", "status_id", "priority"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        if self.start_at and self.due_at and self.start_at > self.due_at:
            raise ValueError("Дата начала задачи не может быть позже крайнего срока")
        return self


class TaskOut(Output):
    id: UUID
    workspace_id: UUID
    title: str
    description: str | None
    status_id: UUID
    status_name: str
    is_final: bool
    priority: TaskPriority
    assignee_user_id: UUID | None
    creator_user_id: UUID | None
    completed_by_user_id: UUID | None
    start_at: datetime | None
    due_at: datetime | None
    estimate_minutes: int | None
    deal_id: UUID | None
    project_id: UUID | None
    contact_id: UUID | None
    parent_task_id: UUID | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    checklist_done: int = 0
    checklist_total: int = 0


class TaskChecklistItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class TaskChecklistItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)] | None = None
    is_done: bool | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Укажите текст пункта или отметку выполнения")
        return self


class TaskChecklistItemOut(Output):
    id: UUID
    task_id: UUID
    text: str
    is_done: bool
    position: int
    created_at: datetime


class ProjectStageOut(Output):
    id: UUID
    name: str
    position: int


class ProjectOut(Output):
    id: UUID
    workspace_id: UUID
    title: str
    client_id: UUID
    deal_id: UUID | None
    stage_id: UUID
    stage_name: str
    manager_user_id: UUID | None
    amount: Decimal
    currency: str
    start_date: date | None
    end_date: date | None
    status: Literal["ACTIVE", "ARCHIVED", "COMPLETED"]
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    tasks_total: int = 0
    tasks_done: int = 0
    members_count: int = 0


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Name | None = None
    client_id: UUID | None = None
    deal_id: UUID | None = None
    stage_id: UUID | None = None
    manager_user_id: UUID | None = None
    amount: Money | None = None
    start_date: date | None = None
    end_date: date | None = None
    force: bool = False
    template_id: UUID | None = None

    @model_validator(mode="after")
    def require_source(self):
        if self.deal_id is None and (self.title is None or self.client_id is None):
            raise ValueError("Укажите сделку или название и клиента")
        if self.template_id is not None and self.start_date is None:
            raise ValueError("Укажите дату начала проекта по шаблону")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("Дата начала не может быть позже даты окончания")
        return self


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Name | None = None
    stage_id: UUID | None = None
    manager_user_id: UUID | None = None
    amount: Money | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: Literal["ACTIVE", "ARCHIVED", "COMPLETED"] | None = None

    @model_validator(mode="after")
    def require_change(self):
        for name in ("title", "stage_id", "amount", "status"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле проекта")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("Дата начала не может быть позже даты окончания")
        return self


class ProjectMemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    role: Literal["LEAD", "MEMBER"] = "MEMBER"


class ProjectMemberOut(BaseModel):
    user_id: UUID
    first_name: str
    last_name: str | None
    email: str
    role: Literal["LEAD", "MEMBER"]


class ProjectContactOut(BaseModel):
    contact_id: UUID
    first_name: str
    last_name: str | None
    middle_name: str | None
    phone: str | None
    email: str | None


class ProjectEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]


class ProjectEventOut(Output):
    id: UUID
    kind: str
    body: str
    author_name: str
    created_at: datetime
