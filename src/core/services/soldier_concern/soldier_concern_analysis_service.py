from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
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
from src.core.services.topic.topic_analysis_service import (
    TopicAnalysisService,
    TopicDocument,
)
from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


@inject
class SoldierConcernAnalysisService:
    def __init__(
        self,
        persian_text_processor: PersianTextProcessor,
        candidate_extraction_service: CandidateExtractionService,
        statistical_analysis_service: StatisticalAnalysisService,
        semantic_analysis_service: SemanticAnalysisService,
        hybrid_ranking_service: HybridRankingService,
        config_reader: ConfigReader,
        *,
        topic_analysis_service: TopicAnalysisService,
    ):
        self._processor = persian_text_processor
        self._extractor = candidate_extraction_service
        self._statistical = statistical_analysis_service
        self._semantic = semantic_analysis_service
        self._ranking = hybrid_ranking_service
        self._topics = topic_analysis_service
        self._config = load_profile_scoring_config(
            config_reader,
            profile_key="soldier_concern",
            required_signals=(
                "document_frequency",
                "document_coverage",
                "semantic_relevance",
                "concern_prevalence",
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
        processed: list[tuple[dict[str, Any], Any]] = []
        candidate_documents: list[CandidateDocument] = []
        for document in ordered:
            result = self._processor.process(
                document["text"],
                domain="SOLDIER_CONCERN",
            )
            processed.append((document, result))
            candidate_documents.append(
                CandidateDocument(
                    document_id=document["document_id"],
                    processing_result=result,
                )
            )

        occurrences = self._extractor.extract_documents(tuple(candidate_documents))
        document_ids = tuple(document["document_id"] for document in ordered)
        statistics = self._statistical.analyze(
            occurrences,
            document_ids=document_ids,
        )

        maximum_df = max(
            (item.document_frequency for item in statistics),
            default=1,
        )
        profile_statistics = tuple(
            replace(
                item,
                statistical_score=weighted_signal_score(
                    {
                        "document_frequency": item.document_frequency / maximum_df,
                        "document_coverage": item.document_coverage,
                        "concern_prevalence": item.document_coverage,
                    },
                    self._config.weights,
                )[0],
            )
            for item in statistics
        )

        statistical_weight = (
            self._config.weights["document_frequency"]
            + self._config.weights["document_coverage"]
            + self._config.weights["concern_prevalence"]
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
            diversity_candidate_pool_size=(
                self._config.diversity_candidate_pool_size
            ),
        )

        stats_by_id = {item.canonical_text: item for item in profile_statistics}
        semantic_by_id = {item.canonical_text: item for item in semantic.candidates}
        keywords: list[ProfileKeywordResult] = []
        keyword_signals: list[dict[str, Any]] = []
        for ranked in hybrid.candidates:
            stat = stats_by_id[ranked.canonical_text]
            sem = semantic_by_id[ranked.canonical_text]
            signals = {
                "document_frequency": stat.document_frequency,
                "normalized_document_frequency": (
                    stat.document_frequency / maximum_df
                ),
                "document_coverage": stat.document_coverage,
                "concern_prevalence": stat.document_coverage,
                "semantic_relevance": sem.semantic_score,
                "frequency": stat.frequency,
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
                    coverage=stat.document_coverage,
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

        topic_result = await self._topics.analyze_async(
            documents=tuple(
                TopicDocument(
                    document_id="sha256:"
                    + sha256(document["document_id"].encode("utf-8")).hexdigest(),
                    text=result.embedding_text,
                    order=index,
                )
                for index, (document, result) in enumerate(processed, start=1)
            ),
            keywords=tuple(keywords),
            build_timeline=False,
        )

        return StructuredProfileResult(
            profile="SOLDIER_CONCERN",
            keywords=tuple(keywords),
            metrics={
                "document_count": len(ordered),
                "candidate_occurrence_count": len(occurrences),
                "candidate_count": len(statistics),
                "ranked_keyword_count": len(keywords),
            },
            profile_result={
                "profile": "SOLDIER_CONCERN",
                "document_independence": True,
                "privacy": {
                    "raw_text_persisted": False,
                    "raw_document_payload_retained": False,
                    "request_override_supported": False,
                },
                "scoring": {
                    "status": "baseline_requires_production_gold_evaluation",
                    "configured_weights": dict(self._config.weights),
                    "profile_scoring_version": self._config.scoring_version,
                    "hybrid_scoring_version": hybrid.scoring_version,
                    "hybrid": {
                        "normalization_strategy": hybrid.normalization_strategy,
                        "lexical_deduplication_threshold": hybrid.lexical_deduplication_threshold,
                        "semantic_deduplication_threshold": hybrid.semantic_deduplication_threshold,
                        "diversity_strategy": hybrid.diversity_strategy,
                        "mmr_lambda": hybrid.mmr_lambda,
                        "diversity_candidate_pool_size": hybrid.diversity_candidate_pool_size,
                        "maximum_ranked_results": hybrid.maximum_ranked_results,
                        "deterministic_tie_breaking": hybrid.deterministic_tie_breaking,
                    },
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
                "topic_analysis": {
                    "provider": dict(topic_result.provider_metadata),
                    "scoring_version": topic_result.scoring_version,
                    "topic_count": len(topic_result.topics),
                    "document_association": "sha256_document_id_only",
                    "evaluation_status": "baseline_requires_human_gold_validation",
                },
            },
            model_version=(
                self._model_version(semantic)
                + ";topic:"
                + str(topic_result.provider_metadata.get("model_identifier") or "unknown")
            ),
            scoring_version=(
                f"{self._config.scoring_version}+{hybrid.scoring_version}+"
                f"{topic_result.scoring_version}"
            ),
            topics=topic_result.topics,
        )

    @staticmethod
    def _validate_documents(
        documents: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], ...]:
        if not documents:
            raise ValueError(
                "SOLDIER_CONCERN analysis requires at least one document"
            )
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for document in documents:
            document_id = document.get("document_id")
            text = document.get("text")
            metadata = document.get("metadata", {})
            if metadata is None:
                metadata = {}
            if not isinstance(document_id, str) or not document_id.strip():
                raise ValueError(
                    "SOLDIER_CONCERN document_id must be a non-empty string"
                )
            normalized_document_id = document_id.strip()
            if normalized_document_id in seen:
                raise ValueError(
                    "SOLDIER_CONCERN document_id values must be unique"
                )
            if not isinstance(text, str) or not text.strip():
                raise ValueError(
                    "SOLDIER_CONCERN document text must be non-empty"
                )
            if not isinstance(metadata, dict):
                raise ValueError(
                    "SOLDIER_CONCERN metadata must be a mapping"
                )
            seen.add(normalized_document_id)
            normalized.append(
                {
                    "document_id": normalized_document_id,
                    "text": text,
                    "metadata": dict(metadata),
                }
            )
        return tuple(sorted(normalized, key=lambda item: item["document_id"]))

    @staticmethod
    def _model_version(semantic: Any) -> str:
        embedding = semantic.embedding_metadata
        reranker = semantic.reranker_metadata
        return (
            f"embedding:{embedding.model_identifier}@{embedding.model_revision or 'default'};"
            f"reranker:{reranker.model_identifier}@{reranker.model_revision or 'default'}"
        )
