from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnalysisType(str, Enum):
    COURSE = "COURSE"
    SOLDIER_CONCERN = "SOLDIER_CONCERN"
    MEDIA = "MEDIA"


class ExecutionMode(str, Enum):
    AUTO = "auto"
    SYNC = "sync"
    ASYNC = "async"


class AnalysisDocumentDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("document_id", "text")
    @classmethod
    def reject_blank_strings(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class AnalysisRequestDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_type: AnalysisType
    documents: list[AnalysisDocumentDto] = Field(min_length=1)
    execution_mode: ExecutionMode
    reference: str | None = Field(default=None, max_length=500)
    options: dict[str, Any] = Field(default_factory=dict)


class AnalysisValidationResponseDto(BaseModel):
    valid: bool = True
    analysis_type: AnalysisType
    execution_mode: ExecutionMode
    resolved_execution_mode: ExecutionMode
    document_count: int = Field(ge=1)
    total_characters: int = Field(ge=1)


class ApiErrorDto(BaseModel):
    code: str
    message: str


class ApiErrorEnvelopeDto(BaseModel):
    detail: ApiErrorDto
