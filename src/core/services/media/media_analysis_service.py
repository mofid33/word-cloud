from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime
from typing import Any

from src.core.services.analysis.profile_config import (
    ProfileScoringConfig,
    load_profile_scoring_config,
    weighted_signal_score,
)
from src.core.services.analysis.profile_result import (
    ProfileKeywordResult,
    ProfileTopicResult,
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
from src.core.services.trend.trend_analysis_service import (
    TrendAnalysisService,
    TrendDocument,
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
        *,
        topic_analysis_service: TopicAnalysisService,
        trend_analysis_service: TrendAnalysisService,
    ):
        self._processor = persian_text_processor
        self._extractor = candidate_extraction_service
        self._statistical = statistical_analysis_service
        self._semantic = semantic_analysis_service
        self._ranking = hybrid_ranking_service
        self._topics = topic_analysis_service
        self._trends = trend_analysis_service
        self._config = load_profile_scoring_config(
            config_reader,
            profile_key="media",
            required_signals=(
                "mention_share",
                "semantic_relevance",
                "coverage",
                "normalized_engagement",
                "trend_growth",
                "recency",
            ),
        )
        self._gap_threshold = self._unit_interval(
            config_reader.require("topic_analysis.media_gap_similarity_threshold"),
            "topic_analysis.media_gap_similarity_threshold",
        )

    @property
    def config(self) -> ProfileScoringConfig:
        return self._config

    async def analyze_async(
        self,
        documents: list[dict[str, Any]],
    ) -> StructuredProfileResult:
        ordered = self._validate_documents(documents)
        role_documents_by_name: dict[str, tuple[dict[str, Any], ...]] = {}
        role_results: dict[str, dict[str, Any]] = {}
        combined: list[tuple[str, ProfileKeywordResult]] = []
        model_versions: list[str] = []
        topic_versions: list[str] = []
        trend_versions: list[str] = []
        total_occurrences = 0
        total_candidates = 0

        for role in self._ROLES:
            role_documents = tuple(
                document
                for document in ordered
                if document["metadata"]["role"] == role
            )
            role_documents_by_name[role] = role_documents
            if not role_documents:
                continue

            role_result = await self._analyze_role_async(role, role_documents)
            role_results[role] = role_result
            total_occurrences += role_result["candidate_occurrence_count"]
            total_candidates += role_result["candidate_count"]
            model_versions.append(role_result["model_version"])
            combined.extend(
                (role, keyword)
                for keyword in role_result["keywords"]
            )
            topic_versions.append(role_result["topic_result"].scoring_version)
            trend_versions.append(role_result["trend_result"].scoring_version)
            topic_model_identifier = role_result[
                "topic_result"
            ].provider_metadata.get("model_identifier")
            if topic_model_identifier:
                model_versions.append(f"topic:{topic_model_identifier}")

        combined.sort(
            key=lambda pair: (
                -pair[1].final_score,
                -pair[1].semantic_score,
                pair[1].canonical_text,
                pair[0],
            )
        )
        unique_combined: list[tuple[str, ProfileKeywordResult]] = []
        seen_canonical: set[str] = set()
        for role, keyword in combined:
            if keyword.canonical_text in seen_canonical:
                continue
            seen_canonical.add(keyword.canonical_text)
            unique_combined.append((role, keyword))

        selected = unique_combined[: self._config.maximum_results]
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

        role_payloads: dict[str, dict[str, Any]] = {}
        role_topics: dict[str, tuple[ProfileTopicResult, ...]] = {}
        all_topics: list[ProfileTopicResult] = []
        for role in self._ROLES:
            role_documents = role_documents_by_name[role]
            role_result = role_results.get(role)
            if role_result is None:
                role_payloads[role] = {
                    "document_count": 0,
                    "keywords": [],
                    "topics": [],
                    "trend": {
                        "available": False,
                        "reason": "no_documents",
                        "trends": [],
                    },
                    "deduplication": [],
                }
                role_topics[role] = ()
                continue

            enriched_topic_result = self._topics.enrich_result(
                result=role_result["topic_result"],
                documents=role_result["topic_documents"],
                keywords=keywords,
            )
            prefixed_topics: list[ProfileTopicResult] = []
            for topic in enriched_topic_result.topics:
                prefixed = replace(
                    topic,
                    topic_id=f"{role}:{topic.topic_id}",
                    rank=len(all_topics) + 1,
                    metadata={**topic.metadata, "role": role},
                )
                prefixed_topics.append(prefixed)
                all_topics.append(prefixed)
            role_topics[role] = tuple(prefixed_topics)

            trend_result = role_result["trend_result"]
            role_payloads[role] = {
                "document_count": len(role_documents),
                "keywords": [
                    {
                        "canonical_text": keyword.canonical_text,
                        "rank": keyword.rank,
                        "final_score": keyword.final_score,
                        "signals": keyword.signals,
                    }
                    for keyword in role_result["keywords"]
                ],
                "topics": [
                    self._topic_payload(topic) for topic in prefixed_topics
                ],
                "trend": {
                    "available": trend_result.available,
                    "reason": trend_result.reason,
                    "window_days": trend_result.window_days,
                    "comparison_end": (
                        trend_result.comparison_end.isoformat()
                        if trend_result.comparison_end is not None
                        else None
                    ),
                    "scoring_version": trend_result.scoring_version,
                    "trends": [
                        {
                            "topic_id": f"{role}:{item.topic_id}",
                            "previous_prevalence": item.previous_prevalence,
                            "current_prevalence": item.current_prevalence,
                            "growth": item.growth,
                            "classification": item.classification,
                        }
                        for item in trend_result.trends
                    ],
                },
                "deduplication": role_result["deduplication"],
                "hybrid": role_result["hybrid"],
            }

        gaps = self._content_audience_gap(
            role_topics.get("published_content", ()),
            role_topics.get("audience_feedback", ()),
        )
        unique_model_versions = sorted(set(model_versions))
        scoring_parts = [
            self._config.scoring_version,
            HybridRankingService.SCORING_VERSION,
            *sorted(set(topic_versions)),
            *sorted(set(trend_versions)),
        ]
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
                "topic_count": len(all_topics),
                "content_audience_gap_count": len(gaps),
            },
            profile_result={
                "profile": "MEDIA",
                "role_separation": True,
                "roles": role_payloads,
                "content_audience_gap": {
                    "similarity_threshold": self._gap_threshold,
                    "items": gaps,
                },
                "scoring": {
                    "status": "baseline_requires_production_gold_evaluation",
                    "configured_weights": dict(self._config.weights),
                    "profile_scoring_version": self._config.scoring_version,
                    "hybrid_scoring_version": HybridRankingService.SCORING_VERSION,
                    "topic_scoring_versions": sorted(set(topic_versions)),
                    "trend_scoring_versions": sorted(set(trend_versions)),
                },
                "unsupported_signals": {
                    "normalized_engagement": (
                        "no engagement metadata contract is frozen; "
                        "weight remains zero until a contract is defined"
                    ),
                },
                "trend_contract": {
                    "timestamp_field": "metadata.published_at",
                    "timezone_required": True,
                    "missing_timestamp_behavior": "trend_unavailable_no_synthetic_time",
                    "trend_growth_strategy": "positive_topic_growth_weighted_by_candidate_documents",
                    "recency_strategy": "linear_within_current_trend_window",
                },
            },
            model_version="|".join(unique_model_versions) or "semantic-providers:no-role-data",
            scoring_version="+".join(scoring_parts),
            topics=tuple(all_topics),
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
        topic_documents = tuple(
            TopicDocument(
                document_id=document["document_id"],
                text=result.embedding_text,
                order=index,
                timestamp=self._optional_timestamp(
                    (document.get("metadata") or {}).get("published_at")
                ),
            )
            for index, (document, result) in enumerate(processed, start=1)
        )
        topic_result = await self._topics.analyze_async(
            documents=topic_documents,
            keywords=(),
            build_timeline=False,
        )
        timestamped = self._trend_documents(documents)
        trend_result = self._trends.analyze(
            documents=timestamped,
            topics=topic_result.topics,
        )

        signal_values: dict[str, dict[str, float | None]] = {}
        profile_statistics_list = []
        for item in statistics:
            values = {
                "mention_share": item.relative_frequency,
                "coverage": item.document_coverage,
                "normalized_engagement": None,
                "trend_growth": self._candidate_trend_growth(
                    item,
                    topic_result.topics,
                    trend_result,
                ),
                "recency": self._candidate_recency(
                    item,
                    timestamped,
                    trend_result.window_days,
                ),
            }
            signal_values[item.canonical_text] = values
            profile_statistics_list.append(
                replace(
                    item,
                    statistical_score=weighted_signal_score(
                        values,
                        self._config.weights,
                    )[0],
                )
            )
        profile_statistics = tuple(profile_statistics_list)

        active_statistical_signals = {
            "mention_share": True,
            "coverage": True,
            "normalized_engagement": False,
            "trend_growth": trend_result.available,
            "recency": bool(timestamped),
        }
        statistical_weight = sum(
            self._config.weights[name]
            for name, enabled in active_statistical_signals.items()
            if enabled
        )
        semantic_weight = self._config.weights["semantic_relevance"]
        fusion_total = statistical_weight + semantic_weight
        fusion_weights = FusionWeights(
            statistical=statistical_weight / fusion_total,
            semantic=semantic_weight / fusion_total,
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
        for ranked in hybrid.candidates:
            stat = stats_by_id[ranked.canonical_text]
            sem = semantic_by_id[ranked.canonical_text]
            values = signal_values[ranked.canonical_text]
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
                        "normalized_engagement": values["normalized_engagement"],
                        "trend_growth": values["trend_growth"],
                        "recency": values["recency"],
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
            "topic_result": topic_result,
            "topic_documents": topic_documents,
            "trend_result": trend_result,
            "deduplication": [
                {
                    "removed_canonical_text": item.removed_canonical_text,
                    "kept_canonical_text": item.kept_canonical_text,
                    "reason": item.reason,
                    "similarity": item.similarity,
                }
                for item in hybrid.deduplicated
            ],
            "hybrid": {
                "normalization_strategy": hybrid.normalization_strategy,
                "lexical_deduplication_threshold": hybrid.lexical_deduplication_threshold,
                "semantic_deduplication_threshold": hybrid.semantic_deduplication_threshold,
                "diversity_strategy": hybrid.diversity_strategy,
                "mmr_lambda": hybrid.mmr_lambda,
                "diversity_candidate_pool_size": hybrid.diversity_candidate_pool_size,
                "maximum_ranked_results": hybrid.maximum_ranked_results,
                "deterministic_tie_breaking": hybrid.deterministic_tie_breaking,
                "weights": {
                    "statistical": fusion_weights.statistical,
                    "semantic": fusion_weights.semantic,
                },
            },
        }

    @staticmethod
    def _candidate_trend_growth(
        candidate: Any,
        topics: tuple[ProfileTopicResult, ...],
        trend_result: Any,
    ) -> float | None:
        if not trend_result.available:
            return None
        candidate_documents = {
            occurrence.document_id
            for occurrence in candidate.occurrences
        }
        if not candidate_documents:
            return 0.0

        growth_by_topic = {
            item.topic_id: max(0.0, float(item.growth))
            for item in trend_result.trends
        }
        value = 0.0
        for topic in topics:
            hits = len(candidate_documents.intersection(topic.document_ids))
            if hits:
                value += (
                    hits
                    / len(candidate_documents)
                    * growth_by_topic.get(topic.topic_id, 0.0)
                )
        return min(max(value, 0.0), 1.0)

    @staticmethod
    def _candidate_recency(
        candidate: Any,
        documents: tuple[TrendDocument, ...],
        window_days: int,
    ) -> float | None:
        if not documents:
            return None
        timestamps = {
            item.document_id: item.timestamp
            for item in documents
        }
        comparison_end = max(timestamps.values())
        window_seconds = float(window_days * 24 * 60 * 60)
        candidate_documents = {
            occurrence.document_id
            for occurrence in candidate.occurrences
        }
        scores = []
        for document_id in candidate_documents:
            timestamp = timestamps.get(document_id)
            if timestamp is None:
                continue
            age_seconds = max(
                0.0,
                (comparison_end - timestamp).total_seconds(),
            )
            scores.append(
                max(0.0, 1.0 - (age_seconds / window_seconds))
            )
        if not scores:
            return None
        return sum(scores) / len(scores)

    def _content_audience_gap(
        self,
        content_topics: tuple[ProfileTopicResult, ...],
        audience_topics: tuple[ProfileTopicResult, ...],
    ) -> list[dict[str, Any]]:
        gaps: list[dict[str, Any]] = []
        for audience in audience_topics:
            best_topic: ProfileTopicResult | None = None
            best_similarity = 0.0
            audience_terms = {
                item.canonical_text
                for item in audience.representative_keyphrases
            }
            for content in content_topics:
                content_terms = {
                    item.canonical_text
                    for item in content.representative_keyphrases
                }
                union = audience_terms | content_terms
                similarity = (
                    len(audience_terms & content_terms) / len(union)
                    if union
                    else 0.0
                )
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_topic = content
            if best_similarity < self._gap_threshold:
                gaps.append(
                    {
                        "audience_topic_id": audience.topic_id,
                        "audience_label": audience.label,
                        "best_content_topic_id": (
                            best_topic.topic_id if best_topic is not None else None
                        ),
                        "similarity": best_similarity,
                        "gap_score": 1.0 - best_similarity,
                    }
                )
        gaps.sort(key=lambda item: (-item["gap_score"], item["audience_topic_id"]))
        return gaps

    @staticmethod
    def _topic_payload(topic: ProfileTopicResult) -> dict[str, Any]:
        return {
            "topic_id": topic.topic_id,
            "label": topic.label,
            "rank": topic.rank,
            "prevalence": topic.prevalence,
            "coverage": topic.coverage,
            "representative_keyphrases": [
                {
                    "canonical_text": item.canonical_text,
                    "text": item.text,
                    "rank": item.rank,
                    "relevance_score": item.relevance_score,
                }
                for item in topic.representative_keyphrases
            ],
        }

    @classmethod
    def _trend_documents(
        cls,
        documents: tuple[dict[str, Any], ...],
    ) -> tuple[TrendDocument, ...]:
        values: list[TrendDocument] = []
        for document in documents:
            raw = (document.get("metadata") or {}).get("published_at")
            if raw is None:
                return ()
            timestamp = cls._optional_timestamp(raw)
            if timestamp is None:
                return ()
            values.append(
                TrendDocument(
                    document_id=document["document_id"],
                    timestamp=timestamp,
                )
            )
        return tuple(values)

    @staticmethod
    def _optional_timestamp(value: object) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("MEDIA metadata.published_at must be an ISO-8601 string")
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(
                "MEDIA metadata.published_at must be a valid ISO-8601 timestamp"
            ) from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(
                "MEDIA metadata.published_at must include a timezone offset"
            )
        return parsed

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
            metadata = document.get("metadata", {})
            if metadata is None:
                metadata = {}
            if not isinstance(document_id, str) or not document_id.strip():
                raise ValueError("MEDIA document_id must be a non-empty string")
            normalized_document_id = document_id.strip()
            if normalized_document_id in seen:
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
            if "published_at" in metadata:
                cls._optional_timestamp(metadata["published_at"])
            seen.add(normalized_document_id)
            normalized.append(
                {
                    "document_id": normalized_document_id,
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
    def _unit_interval(value: object, key: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Configuration '{key}' must be numeric")
        number = float(value)
        if not math.isfinite(number) or number < 0 or number > 1:
            raise ValueError(f"Configuration '{key}' must be finite and in [0, 1]")
        return number

    @staticmethod
    def _model_version(semantic: Any) -> str:
        embedding = semantic.embedding_metadata
        reranker = semantic.reranker_metadata
        return (
            f"embedding:{embedding.model_identifier}@{embedding.model_revision or 'default'};"
            f"reranker:{reranker.model_identifier}@{reranker.model_revision or 'default'}"
        )
