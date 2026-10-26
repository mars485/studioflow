from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ClientField = Literal['name', 'phone', 'email', 'website', 'notes']


class MergePair(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_id: UUID
    target_id: UUID

    @model_validator(mode='after')
    def distinct(self):
        if self.source_id == self.target_id:
            raise ValueError('Выберите две разные компании')
        return self


class ClientMergeCreate(MergePair):
    request_key: UUID
    preview_version: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_fields: list[ClientField] = Field(default_factory=list, max_length=5)
    confirmed: Literal[True]

    @model_validator(mode='after')
    def unique_fields(self):
        if len(self.source_fields) != len(set(self.source_fields)):
            raise ValueError('Поля не должны повторяться')
        return self
