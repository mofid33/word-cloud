from __future__ import annotations

from dataclasses import replace
from typing import Any

from src.core.services.analysis.profile_config import (
    ProfileScoringConfig,
    load_profile_scoring_config,
    weighted_signal_score,
)
from src.core.services.analysis.profile_result import (
    ProfileKeywordResult,
    StructuredProfileResult,
)
from src.core.services.candidate.candidate_extraction_service import (
    CandidateDocument,
    CandidateExtractionService,
)
from src.core.services.persian_text.persian_text_processor import PersianTextProcessor
from src.core.services.ranking.hybrid_ranking_service import (
    FusionWeights,
    HybridRankingService,
)
from src.core.services.semantic.semantic_analysis_service import SemanticAnalysisService
from src.core.services.statistical.statistical_analysis_service import (
    StatisticalAnalysisService,
)
from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


@inject
class CourseAnalysisService:
    def __init__(
        self,
        persian_text_processor: PersianTextProcessor,
        candidate_extraction_service: CandidateExtractionService,
        statistical_analysis_service: StatisticalAnalysisService,
        semantic_analysis_service: SemanticAnalysisService,
        hybrid_ranking_service: HybridRankingService,
        config_reader: ConfigReader,
    ):
        self._processor = persian_text_processor
        self._extractor = candidate_extraction_service
        self._statistical = statistical_analysis_service
        self._semantic = semantic_analysis_service
        self._ranking = hybrid_ranking_service
        self._config = load_profile_scoring_config(
            config_reader,
            profile_key="course",
            required_signals=(
                "semantic_relevance",
                "frequency",
                "chunk_coverage",
                "section_coverage",
                "phrase_quality",
            ),
        )

    @property
    def config(self) -> ProfileScoringConfig:
        return self._config

    async def analyze_async(
        self,
        documents: list[dict[str, Any]],
    ) -> StructuredProfileResult:
        ordered = self._validate_documents(documents)
        section_enabled = self._scope_enabled(ordered, "section_id")
        chunk_enabled = self._scope_enabled(ordered, "chunk_id")

        processed: list[tuple[dict[str, Any], Any]] = []
        candidate_documents: list[CandidateDocument] = []
        for document in ordered:
            result = self._processor.process(document["text"], domain="COURSE")
            processed.append((document, result))
            metadata = document.get("metadata") or {}
            candidate_documents.append(
                CandidateDocument(
                    document_id=document["document_id"],
                    processing_result=result,
                    section_id=metadata.get("section_id") if section_enabled else None,
                    chunk_id=metadata.get("chunk_id") if chunk_enabled else None,
                )
            )

        occurrences = self._extractor.extract_documents(tuple(candidate_documents))
        document_ids = tuple(document["document_id"] for document in ordered)
        section_keys = (
            tuple(
                (document["document_id"], document["metadata"]["section_id"])
                for document in ordered
            )
            if section_enabled
            else ()
        )
        chunk_keys = (
            tuple(
                (document["document_id"], document["metadata"]["chunk_id"])
                for document in ordered
            )
            if chunk_enabled
            else ()
        )
        statistics = self._statistical.analyze(
            occurrences,
            document_ids=document_ids,
            section_keys=section_keys,
            chunk_keys=chunk_keys,
        )

        available_statistical_signals = {
            "frequency": True,
            "chunk_coverage": chunk_enabled,
            "section_coverage": section_enabled,
            "phrase_quality": True,
        }
        active_statistical_weight = sum(
            self._config.weights[name]
            for name, enabled in available_statistical_signals.items()
            if enabled
        )
        semantic_weight = self._config.weights["semantic_relevance"]
        fusion_total = active_statistical_weight + semantic_weight
        fusion_weights = FusionWeights(
            statistical=active_statistical_weight / fusion_total,
            semantic=semantic_weight / fusion_total,
        )

        profile_statistics = tuple(
            replace(
                item,
                statistical_score=weighted_signal_score(
                    {
                        "frequency": item.normalized_frequency,
                        "chunk_coverage": item.chunk_coverage if chunk_enabled else None,
                        "section_coverage": item.section_coverage if section_enabled else None,
                        "phrase_quality": item.phrase_quality,
                    },
                    self._config.weights,
                )[0],
            )
            for item in statistics
        )
        context = " ".join(
            result.embedding_text
            for _, result in processed
            if result.embedding_text
        )
        semantic = await self._semantic.analyze_async(context, profile_statistics)
        hybrid = await self._ranking.rank_async(
            profile_statistics,
            semantic,
            weights=fusion_weights,
            maximum_results=self._config.maximum_results,
        )

        stats_by_id = {item.canonical_text: item for item in profile_statistics}
        semantic_by_id = {item.canonical_text: item for item in semantic.candidates}
        keywords: list[ProfileKeywordResult] = []
        keyword_signals: list[dict[str, Any]] = []
        for ranked in hybrid.candidates:
            stat = stats_by_id[ranked.canonical_text]
            sem = semantic_by_id[ranked.canonical_text]
            coverage = (
                stat.section_coverage
                if section_enabled
                else stat.chunk_coverage
                if chunk_enabled
                else stat.document_coverage
            )
            signals = {
                "semantic_relevance": sem.semantic_score,
                "frequency": stat.frequency,
                "normalized_frequency": stat.normalized_frequency,
                "chunk_coverage": stat.chunk_coverage,
                "section_coverage": stat.section_coverage,
                "document_coverage": stat.document_coverage,
                "phrase_quality": stat.phrase_quality,
                "mmr_score": ranked.mmr_score,
            }
            keywords.append(
                ProfileKeywordResult(
                    text=ranked.text,
                    canonical_text=ranked.canonical_text,
                    rank=ranked.rank,
                    final_score=ranked.fused_score,
                    statistical_score=ranked.statistical_score,
                    semantic_score=ranked.semantic_score,
                    coverage=float(coverage or 0.0),
                    frequency=stat.frequency,
                    signals=signals,
                )
            )
            keyword_signals.append(
                {
                    "canonical_text": ranked.canonical_text,
                    "rank": ranked.rank,
                    "signals": signals,
                }
            )

        model_version = self._model_version(semantic)
        return StructuredProfileResult(
            profile="COURSE",
            keywords=tuple(keywords),
            metrics={
                "document_count": len(ordered),
                "candidate_occurrence_count": len(occurrences),
                "candidate_count": len(statistics),
                "ranked_keyword_count": len(keywords),
                "section_boundary_count": len(section_keys),
                "chunk_boundary_count": len(chunk_keys),
            },
            profile_result={
                "profile": "COURSE",
                "scoring": {
                    "status": "baseline_requires_production_gold_evaluation",
                    "configured_weights": dict(self._config.weights),
                    "effective_hybrid_weights": {
                        "statistical": fusion_weights.statistical,
                        "semantic": fusion_weights.semantic,
                    },
                    "profile_scoring_version": self._config.scoring_version,
                    "hybrid_scoring_version": hybrid.scoring_version,
                },
                "keywords": keyword_signals,
                "deduplication": [
                    {
                        "removed_canonical_text": item.removed_canonical_text,
                        "kept_canonical_text": item.kept_canonical_text,
                        "reason": item.reason,
                        "similarity": item.similarity,
                    }
                    for item in hybrid.deduplicated
                ],
                "boundaries": {
                    "section_aware": section_enabled,
                    "chunk_aware": chunk_enabled,
                },
                "deferred_to_phase_11": [
                    "topic_clustering",
                    "topic_representation",
                    "topic_coherence",
                    "topic_diversity",
                    "topic_timeline",
                ],
            },
            model_version=model_version,
            scoring_version=f"{self._config.scoring_version}+{hybrid.scoring_version}",
        )

    @staticmethod
    def _validate_documents(
        documents: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], ...]:
        if not documents:
            raise ValueError("COURSE analysis requires at least one document")
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for document in documents:
            document_id = document.get("document_id")
            text = document.get("text")
            metadata = document.get("metadata") or {}
            if not isinstance(document_id, str) or not document_id.strip():
                raise ValueError("COURSE document_id must be a non-empty string")
            if document_id in seen:
                raise ValueError("COURSE document_id values must be unique")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("COURSE document text must be non-empty")
            if not isinstance(metadata, dict):
                raise ValueError("COURSE metadata must be a mapping")
            seen.add(document_id)
            normalized.append(
                {
                    "document_id": document_id.strip(),
                    "text": text,
                    "metadata": dict(metadata),
                }
            )
        return tuple(sorted(normalized, key=lambda item: item["document_id"]))

    @staticmethod
    def _scope_enabled(
        documents: tuple[dict[str, Any], ...],
        key: str,
    ) -> bool:
        values = [(document.get("metadata") or {}).get(key) for document in documents]
        present = [value is not None for value in values]
        if any(present) and not all(present):
            raise ValueError(f"COURSE {key} must be supplied consistently for all documents")
        if not any(present):
            return False
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError(f"COURSE {key} values must be non-empty strings")
        return True

    @staticmethod
    def _model_version(semantic: Any) -> str:
        embedding = semantic.embedding_metadata
        reranker = semantic.reranker_metadata
        return (
            f"embedding:{embedding.model_identifier}@{embedding.model_revision or 'default'};"
            f"reranker:{reranker.model_identifier}@{reranker.model_revision or 'default'}"
        )
