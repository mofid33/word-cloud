from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.core.services.analysis.analysis_execution_policy_service import (
    AnalysisExecutionPolicyService,
)
from src.infrastructure.di.inject import inject


class AnalysisRequestValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AnalysisValidationResult:
    analysis_type: str
    execution_mode: str
    resolved_execution_mode: str
    document_count: int
    total_characters: int


@inject
class AnalysisService:
    def __init__(
        self,
        execution_policy_service: AnalysisExecutionPolicyService,
    ):
        self._execution_policy_service = execution_policy_service

    async def validate_async(
        self,
        *,
        analysis_type: str,
        execution_mode: str,
        documents: list[dict[str, Any]],
    ) -> AnalysisValidationResult:
        if analysis_type not in {"COURSE", "SOLDIER_CONCERN", "MEDIA"}:
            raise AnalysisRequestValidationError(
                "unsupported_analysis_type",
                "analysis_type must be COURSE, SOLDIER_CONCERN, or MEDIA",
            )

        document_ids = [str(document["document_id"]) for document in documents]
        if len(set(document_ids)) != len(document_ids):
            raise AnalysisRequestValidationError(
                "duplicate_document_id",
                "document_id values must be unique within an analysis request",
            )

        if analysis_type == "MEDIA":
            allowed_roles = {"published_content", "audience_feedback"}
            for document in documents:
                metadata = document.get("metadata") or {}
                role = metadata.get("role")
                if role not in allowed_roles:
                    raise AnalysisRequestValidationError(
                        "media_document_role_required",
                        "MEDIA documents require metadata.role equal to "
                        "'published_content' or 'audience_feedback'",
                    )

        decision = await self._execution_policy_service.evaluate_async(
            execution_mode=execution_mode,
            documents=documents,
        )

        return AnalysisValidationResult(
            analysis_type=analysis_type,
            execution_mode=decision.requested_execution_mode,
            resolved_execution_mode=decision.resolved_execution_mode,
            document_count=decision.document_count,
            total_characters=decision.total_characters,
        )
