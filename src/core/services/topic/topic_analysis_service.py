from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Sequence

from src.core.services.analysis.profile_result import (
    ProfileKeywordResult,
    ProfileTopicKeywordResult,
    ProfileTopicResult,
)
from src.core.services.topic.providers.topic_model_provider import (
    TopicModelDocument,
    TopicModelProvider,
)
from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


@dataclass(frozen=True)
class TopicDocument:
    document_id: str
    text: str
    order: int
    section_id: str | None = None
    chunk_id: str | None = None
    timestamp: datetime | None = None


@dataclass(frozen=True)
class TopicTimelinePoint:
    position: int
    document_id: str
    section_id: str | None
    chunk_id: str | None
    topic_ids: tuple[str, ...]


@dataclass(frozen=True)
class TopicAnalysisResult:
    topics: tuple[ProfileTopicResult, ...]
    timeline: tuple[TopicTimelinePoint, ...]
    provider_metadata: dict[str, str | None]
    scoring_version: str


@inject
class TopicAnalysisService:
    def __init__(
        self,
        topic_model_provider: TopicModelProvider,
        config_reader: ConfigReader,
    ):
        self._provider = topic_model_provider
        self._representative_count = self._positive_int(
            config_reader.require("topic_analysis.representative_keyphrases"),
            "topic_analysis.representative_keyphrases",
        )
        version = config_reader.require("topic_analysis.scoring_version")
        if not isinstance(version, str) or not version.strip():
            raise ValueError(
                "topic_analysis.scoring_version must be a non-empty string"
            )
        self._scoring_version = version.strip()

    async def analyze_async(
        self,
        *,
        documents: Sequence[TopicDocument],
        keywords: Sequence[ProfileKeywordResult],
        build_timeline: bool = False,
    ) -> TopicAnalysisResult:
        materialized = tuple(documents)
        if not materialized:
            return TopicAnalysisResult(
                topics=(),
                timeline=(),
                provider_metadata={},
                scoring_version=self._scoring_version,
            )
        self._validate_documents(materialized)

        model_result = await self._provider.analyze_topics_async(
            tuple(
                TopicModelDocument(document_id=item.document_id, text=item.text)
                for item in materialized
            )
        )
        by_id = {item.document_id: item for item in materialized}
        all_ids = set(by_id)
        covered_ids: set[str] = set()
        total_sections = {
            item.section_id for item in materialized if item.section_id is not None
        }
        total_chunks = {
            item.chunk_id for item in materialized if item.chunk_id is not None
        }

        topics: list[ProfileTopicResult] = []
        for rank, cluster in enumerate(model_result.clusters, start=1):
            member_ids = tuple(cluster.document_ids)
            member_set = set(member_ids)
            if not member_ids or not member_set.issubset(all_ids):
                raise RuntimeError("Topic model provider returned invalid document membership")
            if covered_ids & member_set:
                raise RuntimeError("Topic model provider returned overlapping clusters")
            covered_ids.update(member_set)

            members = tuple(by_id[document_id] for document_id in member_ids)
            topic_id = cluster.cluster_id
            prevalence = len(member_ids) / len(materialized)
            coverage = self._coverage(
                members,
                total_documents=len(materialized),
                total_sections=total_sections,
                total_chunks=total_chunks,
            )
            metadata: dict[str, Any] = {
                "cohesion": cluster.cohesion,
                "provider": model_result.metadata.provider,
                "provider_version": model_result.metadata.provider_version,
                "model_identifier": model_result.metadata.model_identifier,
                "model_revision": model_result.metadata.model_revision,
                "configuration_fingerprint": (
                    model_result.metadata.configuration_fingerprint
                ),
                "topic_scoring_version": self._scoring_version,
            }
            topics.append(
                ProfileTopicResult(
                    topic_id=topic_id,
                    label=f"Topic {rank}",
                    rank=rank,
                    prevalence=prevalence,
                    coverage=coverage,
                    representative_keyphrases=(),
                    document_ids=member_ids,
                    metadata=metadata,
                )
            )

        if covered_ids != all_ids:
            raise RuntimeError("Topic model provider left documents unassigned")

        timeline: tuple[TopicTimelinePoint, ...] = ()
        if build_timeline:
            membership = {
                document_id: topic.topic_id
                for topic in topics
                for document_id in topic.document_ids
            }
            timeline = tuple(
                TopicTimelinePoint(
                    position=index,
                    document_id=item.document_id,
                    section_id=item.section_id,
                    chunk_id=item.chunk_id,
                    topic_ids=(membership[item.document_id],),
                )
                for index, item in enumerate(
                    sorted(materialized, key=lambda value: value.order),
                    start=1,
                )
            )

        result = TopicAnalysisResult(
            topics=tuple(topics),
            timeline=timeline,
            provider_metadata={
                "provider": model_result.metadata.provider,
                "provider_version": model_result.metadata.provider_version,
                "model_identifier": model_result.metadata.model_identifier,
                "model_revision": model_result.metadata.model_revision,
                "configuration_fingerprint": (
                    model_result.metadata.configuration_fingerprint
                ),
            },
            scoring_version=self._scoring_version,
        )
        if not keywords:
            return result
        return self.enrich_result(
            result=result,
            documents=materialized,
            keywords=keywords,
        )

    def enrich_result(
        self,
        *,
        result: TopicAnalysisResult,
        documents: Sequence[TopicDocument],
        keywords: Sequence[ProfileKeywordResult],
    ) -> TopicAnalysisResult:
        materialized = tuple(documents)
        self._validate_documents(materialized)
        by_id = {item.document_id: item for item in materialized}
        expected_ids = set(by_id)
        covered_ids = {
            document_id
            for topic in result.topics
            for document_id in topic.document_ids
        }
        if covered_ids != expected_ids:
            raise ValueError(
                "Topic result document membership does not match enrichment documents"
            )

        enriched: list[ProfileTopicResult] = []
        for topic in result.topics:
            members = tuple(
                by_id[document_id]
                for document_id in topic.document_ids
            )
            representative = self._representative_keyphrases(
                members,
                keywords,
            )
            enriched.append(
                replace(
                    topic,
                    label=(
                        representative[0].text
                        if representative
                        else topic.label
                    ),
                    representative_keyphrases=representative,
                )
            )
        return replace(result, topics=tuple(enriched))

    def _representative_keyphrases(
        self,
        documents: Sequence[TopicDocument],
        keywords: Sequence[ProfileKeywordResult],
    ) -> tuple[ProfileTopicKeywordResult, ...]:
        if not documents or not keywords:
            return ()

        ranked: list[tuple[float, ProfileKeywordResult]] = []
        document_texts = tuple(self._normalized_text(item.text) for item in documents)
        for keyword in keywords:
            phrase = self._normalized_text(
                keyword.canonical_text or keyword.text
            )
            if not phrase:
                continue
            tokens = tuple(token for token in phrase.split() if token)
            hits = 0
            for text in document_texts:
                if phrase in text or (
                    tokens and all(token in text for token in tokens)
                ):
                    hits += 1
            if hits == 0:
                continue
            member_coverage = hits / len(document_texts)
            final_score = self._unit_float(keyword.final_score)
            relevance = 0.65 * member_coverage + 0.35 * final_score
            ranked.append((relevance, keyword))

        ranked.sort(
            key=lambda pair: (
                -pair[0],
                pair[1].rank,
                pair[1].canonical_text,
            )
        )
        return tuple(
            ProfileTopicKeywordResult(
                canonical_text=keyword.canonical_text,
                text=keyword.text,
                rank=index,
                relevance_score=relevance,
            )
            for index, (relevance, keyword) in enumerate(
                ranked[: self._representative_count],
                start=1,
            )
        )

    @staticmethod
    def _coverage(
        documents: Sequence[TopicDocument],
        *,
        total_documents: int,
        total_sections: set[str],
        total_chunks: set[str],
    ) -> float:
        if total_sections:
            topic_sections = {
                item.section_id
                for item in documents
                if item.section_id is not None
            }
            return len(topic_sections) / len(total_sections)
        if total_chunks:
            topic_chunks = {
                item.chunk_id
                for item in documents
                if item.chunk_id is not None
            }
            return len(topic_chunks) / len(total_chunks)
        return len(documents) / total_documents

    @staticmethod
    def _validate_documents(documents: Sequence[TopicDocument]) -> None:
        ids: set[str] = set()
        orders: set[int] = set()
        for item in documents:
            if not item.document_id or not item.document_id.strip():
                raise ValueError("Topic document_id must be non-empty")
            if item.document_id in ids:
                raise ValueError("Topic document_id values must be unique")
            if not item.text or not item.text.strip():
                raise ValueError("Topic document text must be non-empty")
            if isinstance(item.order, bool) or not isinstance(item.order, int):
                raise ValueError("Topic document order must be an integer")
            if item.order in orders:
                raise ValueError("Topic document order values must be unique")
            ids.add(item.document_id)
            orders.add(item.order)

    @staticmethod
    def _normalized_text(value: str) -> str:
        return " ".join(value.casefold().split())

    @staticmethod
    def _unit_float(value: float) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise RuntimeError("Keyword score must be finite")
        return max(0.0, min(1.0, number))

    @staticmethod
    def _positive_int(value: object, key: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"Configuration '{key}' must be an integer > 0")
        return value
