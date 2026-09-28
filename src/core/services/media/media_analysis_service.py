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
class MediaAnalysisService:
    _ROLES = ("published_content", "audience_feedback")

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
            profile_key="media",
            required_signals=(
                "mention_share",
                "semantic_relevance",
                "coverage",
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
        role_payloads: dict[str, dict[str, Any]] = {}
        combined: list[tuple[str, ProfileKeywordResult]] = []
        model_versions: list[str] = []
        total_occurrences = 0
        total_candidates = 0

        for role in self._ROLES:
            role_documents = tuple(
                document
                for document in ordered
                if document["metadata"]["role"] == role
            )
            if not role_documents:
                role_payloads[role] = {
                    "document_count": 0,
                    "keywords": [],
                    "deduplication": [],
                }
                continue

            role_result = await self._analyze_role_async(role, role_documents)
            total_occurrences += role_result["candidate_occurrence_count"]
            total_candidates += role_result["candidate_count"]
            model_versions.append(role_result["model_version"])
            role_keywords = role_result["keywords"]
            combined.extend((role, keyword) for keyword in role_keywords)
            role_payloads[role] = {
                "document_count": len(role_documents),
                "keywords": [
                    {
                        "canonical_text": keyword.canonical_text,
                        "rank": keyword.rank,
                        "final_score": keyword.final_score,
                        "signals": keyword.signals,
                    }
                    for keyword in role_keywords
                ],
                "deduplication": role_result["deduplication"],
            }

        combined.sort(
            key=lambda pair: (
                -pair[1].final_score,
                -pair[1].semantic_score,
                pair[1].canonical_text,
                pair[0],
            )
        )
        selected = combined[: self._config.maximum_results]
        keywords = tuple(
            ProfileKeywordResult(
                text=keyword.text,
                canonical_text=keyword.canonical_text,
                rank=index,
                final_score=keyword.final_score,
                statistical_score=keyword.statistical_score,
                semantic_score=keyword.semantic_score,
                coverage=keyword.coverage,
                frequency=keyword.frequency,
                signals={**keyword.signals, "role": role},
            )
            for index, (role, keyword) in enumerate(selected, start=1)
        )

        unique_model_versions = sorted(set(model_versions))
        return StructuredProfileResult(
            profile="MEDIA",
            keywords=keywords,
            metrics={
                "document_count": len(ordered),
                "published_content_document_count": sum(
                    document["metadata"]["role"] == "published_content"
                    for document in ordered
                ),
                "audience_feedback_document_count": sum(
                    document["metadata"]["role"] == "audience_feedback"
                    for document in ordered
                ),
                "candidate_occurrence_count": total_occurrences,
                "candidate_count": total_candidates,
                "ranked_keyword_count": len(keywords),
            },
            profile_result={
                "profile": "MEDIA",
                "role_separation": True,
                "roles": role_payloads,
                "scoring": {
                    "status": "baseline_requires_production_gold_evaluation",
                    "configured_weights": dict(self._config.weights),
                    "profile_scoring_version": self._config.scoring_version,
                },
                "unsupported_phase_10_signals": {
                    "normalized_engagement": (
                        "no engagement metadata contract is frozen"
                    ),
                    "recency": "no timestamp metadata contract is frozen",
                },
                "deferred_to_phase_11": [
                    "topic_clustering",
                    "topic_representation",
                    "trend_growth",
                    "trend_time_series",
                    "emerging_stable_declining",
                    "topic_based_content_audience_gap",
                    "topic_coherence",
                    "topic_diversity",
                ],
            },
            model_version="|".join(unique_model_versions) or "semantic-providers:no-role-data",
            scoring_version=(
                f"{self._config.scoring_version}+"
                f"{HybridRankingService.SCORING_VERSION}"
            ),
        )

    async def _analyze_role_async(
        self,
        role: str,
        documents: tuple[dict[str, Any], ...],
    ) -> dict[str, Any]:
        processed: list[tuple[dict[str, Any], Any]] = []
        candidate_documents: list[CandidateDocument] = []
        for document in documents:
            result = self._processor.process(document["text"], domain="MEDIA")
            processed.append((document, result))
            candidate_documents.append(
                CandidateDocument(
                    document_id=document["document_id"],
                    processing_result=result,
                )
            )

        occurrences = self._extractor.extract_documents(tuple(candidate_documents))
        statistics = self._statistical.analyze(
            occurrences,
            document_ids=tuple(document["document_id"] for document in documents),
        )
        profile_statistics = tuple(
            replace(
                item,
                statistical_score=weighted_signal_score(
                    {
                        "mention_share": item.relative_frequency,
                        "coverage": item.document_coverage,
                    },
                    self._config.weights,
                )[0],
            )
            for item in statistics
        )

        statistical_weight = (
            self._config.weights["mention_share"]
            + self._config.weights["coverage"]
        )
        semantic_weight = self._config.weights["semantic_relevance"]
        fusion_weights = FusionWeights(
            statistical=statistical_weight,
            semantic=semantic_weight,
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
        for ranked in hybrid.candidates:
            stat = stats_by_id[ranked.canonical_text]
            sem = semantic_by_id[ranked.canonical_text]
            keywords.append(
                ProfileKeywordResult(
                    text=ranked.text,
                    canonical_text=ranked.canonical_text,
                    rank=ranked.rank,
                    final_score=ranked.fused_score,
                    statistical_score=ranked.statistical_score,
                    semantic_score=ranked.semantic_score,
                    coverage=stat.document_coverage,
                    frequency=stat.frequency,
                    signals={
                        "role": role,
                        "mention_share": stat.relative_frequency,
                        "coverage": stat.document_coverage,
                        "semantic_relevance": sem.semantic_score,
                        "frequency": stat.frequency,
                        "mmr_score": ranked.mmr_score,
                    },
                )
            )

        return {
            "keywords": tuple(keywords),
            "candidate_occurrence_count": len(occurrences),
            "candidate_count": len(statistics),
            "model_version": self._model_version(semantic),
            "deduplication": [
                {
                    "removed_canonical_text": item.removed_canonical_text,
                    "kept_canonical_text": item.kept_canonical_text,
                    "reason": item.reason,
                    "similarity": item.similarity,
                }
                for item in hybrid.deduplicated
            ],
        }

    @classmethod
    def _validate_documents(
        cls,
        documents: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], ...]:
        if not documents:
            raise ValueError("MEDIA analysis requires at least one document")
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for document in documents:
            document_id = document.get("document_id")
            text = document.get("text")
            metadata = document.get("metadata") or {}
            if not isinstance(document_id, str) or not document_id.strip():
                raise ValueError("MEDIA document_id must be a non-empty string")
            if document_id in seen:
                raise ValueError("MEDIA document_id values must be unique")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("MEDIA document text must be non-empty")
            if not isinstance(metadata, dict):
                raise ValueError("MEDIA metadata must be a mapping")
            role = metadata.get("role")
            if role not in cls._ROLES:
                raise ValueError(
                    "MEDIA metadata.role must be published_content or audience_feedback"
                )
            seen.add(document_id)
            normalized.append(
                {
                    "document_id": document_id.strip(),
                    "text": text,
                    "metadata": dict(metadata),
                }
            )
        return tuple(
            sorted(
                normalized,
                key=lambda item: (
                    item["metadata"]["role"],
                    item["document_id"],
                ),
            )
        )

    @staticmethod
    def _model_version(semantic: Any) -> str:
        embedding = semantic.embedding_metadata
        reranker = semantic.reranker_metadata
        return (
            f"embedding:{embedding.model_identifier}@{embedding.model_revision or 'default'};"
            f"reranker:{reranker.model_identifier}@{reranker.model_revision or 'default'}"
        )
