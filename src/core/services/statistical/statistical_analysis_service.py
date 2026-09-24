from __future__ import annotations

from dataclasses import dataclass

from src.core.services.candidate.candidate_extraction_service import CandidateOccurrence
from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


@dataclass(frozen=True)
class StatisticalOccurrence:
    document_id: str
    segment_index: int
    token_start: int
    token_end: int
    section_id: str | None
    chunk_id: str | None


@dataclass(frozen=True)
class StatisticalCandidateResult:
    text: str
    canonical_text: str
    ngram_size: int
    frequency: int
    relative_frequency: float
    normalized_frequency: float
    document_frequency: int
    document_coverage: float
    section_coverage: float | None
    chunk_coverage: float | None
    phrase_quality: float
    statistical_score: float
    is_protected: bool
    contains_stopword: bool
    pos_tags: tuple[str | None, ...]
    occurrences: tuple[StatisticalOccurrence, ...]


@dataclass(frozen=True)
class StatisticalAnalysisConfig:
    frequency_weight: float
    document_coverage_weight: float
    phrase_quality_weight: float


@dataclass(frozen=True)
class _Aggregate:
    occurrences: list[CandidateOccurrence]


@inject
class StatisticalAnalysisService:
    def __init__(self, config_reader: ConfigReader):
        self._config = self._load_config(config_reader)

    @property
    def config(self) -> StatisticalAnalysisConfig:
        return self._config

    def analyze(
        self,
        occurrences: tuple[CandidateOccurrence, ...],
        *,
        document_ids: tuple[str, ...],
        section_keys: tuple[tuple[str, str], ...] = (),
        chunk_keys: tuple[tuple[str, str], ...] = (),
    ) -> tuple[StatisticalCandidateResult, ...]:
        normalized_document_ids = self._normalize_document_ids(document_ids)
        if not normalized_document_ids:
            if occurrences or section_keys or chunk_keys:
                raise ValueError(
                    "document_ids must include every document represented by the corpus"
                )
            return ()

        allowed_documents = set(normalized_document_ids)
        normalized_section_keys = self._normalize_scope_keys(
            section_keys,
            field_name="section_keys",
            allowed_documents=allowed_documents,
        )
        normalized_chunk_keys = self._normalize_scope_keys(
            chunk_keys,
            field_name="chunk_keys",
            allowed_documents=allowed_documents,
        )
        section_universe = set(normalized_section_keys)
        chunk_universe = set(normalized_chunk_keys)

        for occurrence in occurrences:
            if occurrence.document_id not in allowed_documents:
                raise ValueError(
                    "occurrence document_id is not present in document_ids"
                )
            if occurrence.section_id is not None:
                if not section_universe:
                    raise ValueError(
                        "section_keys are required when occurrences contain section_id"
                    )
                if (occurrence.document_id, occurrence.section_id) not in section_universe:
                    raise ValueError(
                        "occurrence section boundary is not present in section_keys"
                    )
            if occurrence.chunk_id is not None:
                if not chunk_universe:
                    raise ValueError(
                        "chunk_keys are required when occurrences contain chunk_id"
                    )
                if (occurrence.document_id, occurrence.chunk_id) not in chunk_universe:
                    raise ValueError(
                        "occurrence chunk boundary is not present in chunk_keys"
                    )

        if not occurrences:
            return ()

        grouped: dict[str, _Aggregate] = {}
        for occurrence in occurrences:
            grouped.setdefault(
                occurrence.canonical_text,
                _Aggregate(occurrences=[]),
            ).occurrences.append(occurrence)

        maximum_frequency = max(len(item.occurrences) for item in grouped.values())
        total_occurrences = len(occurrences)
        total_documents = len(normalized_document_ids)

        results: list[StatisticalCandidateResult] = []
        for canonical_text, aggregate in grouped.items():
            candidate_occurrences = sorted(
                aggregate.occurrences,
                key=lambda item: (
                    item.document_id,
                    item.segment_index,
                    item.token_start,
                    item.token_end,
                    item.text,
                ),
            )
            frequency = len(candidate_occurrences)
            document_frequency = len(
                {item.document_id for item in candidate_occurrences}
            )
            normalized_frequency = frequency / maximum_frequency
            document_coverage = document_frequency / total_documents
            phrase_quality = min(candidate_occurrences[0].ngram_size / 3.0, 1.0)

            section_hits = {
                (item.document_id, item.section_id)
                for item in candidate_occurrences
                if item.section_id is not None
            }
            chunk_hits = {
                (item.document_id, item.chunk_id)
                for item in candidate_occurrences
                if item.chunk_id is not None
            }
            section_coverage = (
                len(section_hits) / len(section_universe)
                if section_universe
                else None
            )
            chunk_coverage = (
                len(chunk_hits) / len(chunk_universe)
                if chunk_universe
                else None
            )

            score = self._bounded_score(
                self._config.frequency_weight * normalized_frequency
                + self._config.document_coverage_weight * document_coverage
                + self._config.phrase_quality_weight * phrase_quality
            )
            representative_text = min(
                item.text for item in candidate_occurrences
            )
            representative = min(
                candidate_occurrences,
                key=lambda item: (
                    item.text,
                    item.document_id,
                    item.segment_index,
                    item.token_start,
                ),
            )
            results.append(
                StatisticalCandidateResult(
                    text=representative_text,
                    canonical_text=canonical_text,
                    ngram_size=representative.ngram_size,
                    frequency=frequency,
                    relative_frequency=frequency / total_occurrences,
                    normalized_frequency=normalized_frequency,
                    document_frequency=document_frequency,
                    document_coverage=document_coverage,
                    section_coverage=section_coverage,
                    chunk_coverage=chunk_coverage,
                    phrase_quality=phrase_quality,
                    statistical_score=score,
                    is_protected=any(
                        item.is_protected for item in candidate_occurrences
                    ),
                    contains_stopword=any(
                        item.contains_stopword for item in candidate_occurrences
                    ),
                    pos_tags=representative.pos_tags,
                    occurrences=tuple(
                        StatisticalOccurrence(
                            document_id=item.document_id,
                            segment_index=item.segment_index,
                            token_start=item.token_start,
                            token_end=item.token_end,
                            section_id=item.section_id,
                            chunk_id=item.chunk_id,
                        )
                        for item in candidate_occurrences
                    ),
                )
            )

        return tuple(
            sorted(
                results,
                key=lambda item: (
                    -item.statistical_score,
                    -item.frequency,
                    -item.ngram_size,
                    item.canonical_text,
                    item.text,
                ),
            )
        )

    @staticmethod
    def _normalize_document_ids(document_ids: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        seen: set[str] = set()
        for document_id in document_ids:
            if not isinstance(document_id, str) or not document_id.strip():
                raise ValueError("document_ids must contain non-empty strings")
            value = document_id.strip()
            if value in seen:
                raise ValueError("document_ids must be unique")
            seen.add(value)
            normalized.append(value)
        return tuple(normalized)

    @staticmethod
    def _normalize_scope_keys(
        keys: tuple[tuple[str, str], ...],
        *,
        field_name: str,
        allowed_documents: set[str],
    ) -> tuple[tuple[str, str], ...]:
        normalized: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for item in keys:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not isinstance(item[1], str)
                or not item[0].strip()
                or not item[1].strip()
            ):
                raise ValueError(
                    f"{field_name} must contain (document_id, boundary_id) pairs"
                )
            key = (item[0].strip(), item[1].strip())
            if key[0] not in allowed_documents:
                raise ValueError(
                    f"{field_name} contains a document_id not present in document_ids"
                )
            if key in seen:
                raise ValueError(f"{field_name} must contain unique pairs")
            seen.add(key)
            normalized.append(key)
        return tuple(normalized)

    @staticmethod
    def _bounded_score(value: float) -> float:
        return min(max(value, 0.0), 1.0)

    @classmethod
    def _load_config(cls, config_reader: ConfigReader) -> StatisticalAnalysisConfig:
        frequency_weight = cls._required_weight(
            config_reader,
            "statistical_analysis.weights.frequency",
        )
        document_coverage_weight = cls._required_weight(
            config_reader,
            "statistical_analysis.weights.document_coverage",
        )
        phrase_quality_weight = cls._required_weight(
            config_reader,
            "statistical_analysis.weights.phrase_quality",
        )
        total = (
            frequency_weight
            + document_coverage_weight
            + phrase_quality_weight
        )
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                "statistical_analysis component weights must sum to 1.0"
            )
        return StatisticalAnalysisConfig(
            frequency_weight=frequency_weight,
            document_coverage_weight=document_coverage_weight,
            phrase_quality_weight=phrase_quality_weight,
        )

    @staticmethod
    def _required_weight(config_reader: ConfigReader, key: str) -> float:
        value = config_reader.require(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Configuration '{key}' must be numeric")
        numeric = float(value)
        if numeric < 0.0 or numeric > 1.0:
            raise ValueError(
                f"Configuration '{key}' must be between 0.0 and 1.0"
            )
        return numeric
