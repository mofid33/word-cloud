from __future__ import annotations

from datetime import datetime
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


class AnalysisStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


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


class AnalysisErrorResponseDto(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    message: str


class AnalysisStatusResponseDto(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    analysis_id: str
    analysis_type: AnalysisType
    status: AnalysisStatus
    execution_mode: ExecutionMode
    reference: str | None
    model_version: str | None
    scoring_version: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error: AnalysisErrorResponseDto | None


class AnalysisKeywordResponseDto(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    text: str
    canonical_text: str
    rank: int = Field(gt=0)
    final_score: float
    statistical_score: float
    semantic_score: float
    coverage: float = Field(ge=0, le=1)
    frequency: int = Field(ge=0)


class AnalysisTopicKeywordResponseDto(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    text: str
    canonical_text: str
    rank: int = Field(gt=0)
    relevance_score: float


class AnalysisTopicResponseDto(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    topic_id: str
    label: str
    rank: int = Field(gt=0)
    prevalence: float = Field(ge=0, le=1)
    coverage: float = Field(ge=0, le=1)
    keywords: list[AnalysisTopicKeywordResponseDto]


class AnalysisResultResponseDto(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    analysis: AnalysisStatusResponseDto
    keywords: list[AnalysisKeywordResponseDto]
    topics: list[AnalysisTopicResponseDto]
    metrics: dict[str, Any]
    profile_result: dict[str, Any]


class ApiErrorDto(BaseModel):
    code: str
    message: str


class ApiErrorEnvelopeDto(BaseModel):
    detail: ApiErrorDto
