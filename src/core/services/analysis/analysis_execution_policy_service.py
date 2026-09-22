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
        documents: list[dict[str, Any]],
    ) -> AnalysisExecutionDecision:
        if execution_mode not in {"auto", "sync", "async"}:
            raise AnalysisExecutionPolicyError(
                "unsupported_execution_mode",
                "execution_mode must be one of: auto, sync, async",
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
                document_id = str(document.get("document_id", "unknown"))
                raise AnalysisExecutionPolicyError(
                    "max_document_characters_exceeded",
                    f"Document '{document_id}' contains {character_count} characters; "
                    f"maximum allowed is {max_characters_per_document}",
                )
            total_characters += character_count

        if total_characters > max_total_characters:
            raise AnalysisExecutionPolicyError(
                "max_total_characters_exceeded",
                f"Analysis contains {total_characters} characters; "
                f"maximum allowed is {max_total_characters}",
            )

        fits_sync = (
            document_count <= sync_max_documents
            and total_characters <= sync_max_total_characters
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

    def _positive_int(self, key: str) -> int:
        value = int(self._config.require(key))
        if value <= 0:
            raise ValueError(f"Configuration value must be positive: {key}")
        return value
