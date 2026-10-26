from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.api.v1.client_merge_schemas import MergePair

ContactField = Literal['first_name', 'last_name', 'middle_name', 'phone', 'email', 'website', 'notes']


class ContactMergeCreate(MergePair):
    request_key: UUID
    preview_version: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_fields: list[ContactField] = Field(default_factory=list, max_length=7)
    confirmed: Literal[True]

    @model_validator(mode='after')
    def unique_fields(self):
        if len(self.source_fields) != len(set(self.source_fields)):
            raise ValueError('Поля не должны повторяться')
        return self
