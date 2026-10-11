from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


class AnalysisExecutionPolicyError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AnalysisExecutionDecision:
    requested_execution_mode: str
    resolved_execution_mode: str
    document_count: int
    total_characters: int


@inject
class AnalysisExecutionPolicyService:
    def __init__(self, config_reader: ConfigReader):
        self._config = config_reader

    async def evaluate_async(
        self,
        *,
        execution_mode: str,
        analysis_type: str | None = None,
        documents: list[dict[str, Any]],
    ) -> AnalysisExecutionDecision:
        if execution_mode not in {"auto", "sync", "async"}:
            raise AnalysisExecutionPolicyError(
                "unsupported_execution_mode",
                "execution_mode must be one of: auto, sync, async",
            )
        if (
            analysis_type is not None
            and analysis_type not in {"COURSE", "SOLDIER_CONCERN", "MEDIA"}
        ):
            raise AnalysisExecutionPolicyError(
                "unsupported_analysis_type",
                "analysis_type must be COURSE, SOLDIER_CONCERN, or MEDIA",
            )

        document_count = len(documents)
        if document_count == 0:
            raise AnalysisExecutionPolicyError(
                "documents_required",
                "At least one document is required",
            )

        max_documents = self._positive_int(
            "analysis.limits.max_documents_per_analysis"
        )
        max_characters_per_document = self._positive_int(
            "analysis.limits.max_characters_per_document"
        )
        max_total_characters = self._positive_int(
            "analysis.limits.max_total_characters_per_analysis"
        )
        sync_max_documents = self._positive_int(
            "analysis.sync_threshold.max_documents"
        )
        sync_max_total_characters = self._positive_int(
            "analysis.sync_threshold.max_total_characters"
        )
        sync_max_estimated_candidates = self._positive_int(
            "analysis.sync_threshold.max_estimated_candidates"
        )
        if analysis_type == "COURSE":
            sync_max_total_characters = min(
                sync_max_total_characters,
                self._positive_int(
                    "analysis.sync_threshold.course_max_total_characters"
                ),
            )
            sync_max_estimated_candidates = min(
                sync_max_estimated_candidates,
                self._positive_int(
                    "analysis.sync_threshold.course_max_estimated_candidates"
                ),
            )

        if document_count > max_documents:
            raise AnalysisExecutionPolicyError(
                "max_documents_exceeded",
                f"Analysis contains {document_count} documents; "
                f"maximum allowed is {max_documents}",
            )

        total_characters = 0
        for document in documents:
            text = str(document.get("text", ""))
            character_count = len(text)
            if character_count > max_characters_per_document:
                raise AnalysisExecutionPolicyError(
                    "max_document_characters_exceeded",
                    f"A document contains {character_count} characters; "
                    f"maximum allowed is {max_characters_per_document}",
                )
            total_characters += character_count

        if total_characters > max_total_characters:
            raise AnalysisExecutionPolicyError(
                "max_total_characters_exceeded",
                f"Analysis contains {total_characters} characters; "
                f"maximum allowed is {max_total_characters}",
            )

        estimated_candidate_count = self._estimate_candidate_count(documents)
        fits_sync = (
            document_count <= sync_max_documents
            and total_characters <= sync_max_total_characters
            and estimated_candidate_count <= sync_max_estimated_candidates
        )

        if execution_mode == "sync" and not fits_sync:
            raise AnalysisExecutionPolicyError(
                "sync_threshold_exceeded",
                "Explicit sync execution exceeds the configured sync threshold",
            )

        resolved_execution_mode = execution_mode
        if execution_mode == "auto":
            resolved_execution_mode = "sync" if fits_sync else "async"

        return AnalysisExecutionDecision(
            requested_execution_mode=execution_mode,
            resolved_execution_mode=resolved_execution_mode,
            document_count=document_count,
            total_characters=total_characters,
        )

    def sync_processing_timeout_seconds(self) -> int:
        return self._positive_int(
            "analysis.sync_threshold.processing_timeout_seconds"
        )

    @staticmethod
    def _estimate_candidate_count(
        documents: list[dict[str, Any]],
    ) -> int:
        estimated = 0
        for document in documents:
            token_count = len(str(document.get("text", "")).split())
            estimated += (
                token_count
                + max(token_count - 1, 0)
                + max(token_count - 2, 0)
            )
        return estimated

    def _positive_int(self, key: str) -> int:
        value = self._config.require(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(
                f"Configuration '{key}' must be an integer > 0"
            )
        return value
