from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Sequence

from src.core.services.semantic.providers.embedding_provider import EmbeddingProvider
from src.core.services.topic.providers.topic_model_provider import (
    TopicModelCluster,
    TopicModelDocument,
    TopicModelMetadata,
    TopicModelProvider,
    TopicModelResult,
)
from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


@dataclass
class _WorkingCluster:
    document_ids: list[str]
    vectors: list[tuple[float, ...]]
    vector_sum: tuple[float, ...]
    centroid: tuple[float, ...]


@inject
class SemanticAgglomerativeTopicModelProvider(TopicModelProvider):
    __di_singleton__ = True

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        config_reader: ConfigReader,
    ):
        self._embedding_provider = embedding_provider
        self._config = self._load_config(config_reader)

    async def analyze_topics_async(
        self,
        documents: Sequence[TopicModelDocument],
    ) -> TopicModelResult:
        materialized = tuple(documents)
        if not materialized:
            return TopicModelResult(clusters=(), metadata=self._metadata())

        ids: set[str] = set()
        for item in materialized:
            if not isinstance(item.document_id, str) or not item.document_id.strip():
                raise ValueError("topic document_id must be a non-empty string")
            if item.document_id in ids:
                raise ValueError("topic document_id values must be unique")
            if not isinstance(item.text, str) or not item.text.strip():
                raise ValueError("topic document text must be non-empty")
            ids.add(item.document_id)

        ordered = tuple(sorted(materialized, key=lambda item: item.document_id))
        raw_vectors = await self._embedding_provider.embed_async(
            tuple(item.text for item in ordered)
        )
        if len(raw_vectors) != len(ordered):
            raise RuntimeError("Topic embedding provider returned an invalid vector count")

        vectors: list[tuple[float, ...]] = []
        dimension: int | None = None
        for raw in raw_vectors:
            vector = tuple(float(value) for value in raw)
            if not vector:
                raise RuntimeError("Topic embedding provider returned an empty vector")
            if any(not math.isfinite(value) for value in vector):
                raise RuntimeError("Topic embedding provider returned a non-finite vector")
            if dimension is None:
                dimension = len(vector)
            elif len(vector) != dimension:
                raise RuntimeError("Topic embedding provider returned inconsistent dimensions")
            vectors.append(self._normalize(vector))

        clusters = [
            _WorkingCluster(
                document_ids=[item.document_id],
                vectors=[vector],
                vector_sum=vector,
                centroid=vector,
            )
            for item, vector in zip(ordered, vectors, strict=True)
        ]
        threshold = self._config["similarity_threshold"]
        maximum_topics = self._config["maximum_topics"]

        while len(clusters) > 1:
            best_pair: tuple[int, int] | None = None
            best_similarity = -1.0
            for left in range(len(clusters) - 1):
                for right in range(left + 1, len(clusters)):
                    similarity = self._cluster_similarity(clusters[left], clusters[right])
                    tie_key = (
                        tuple(clusters[left].document_ids),
                        tuple(clusters[right].document_ids),
                    )
                    if (
                        similarity > best_similarity
                        or (
                            math.isclose(similarity, best_similarity, abs_tol=1e-12)
                            and best_pair is not None
                            and tie_key
                            < (
                                tuple(clusters[best_pair[0]].document_ids),
                                tuple(clusters[best_pair[1]].document_ids),
                            )
                        )
                    ):
                        best_similarity = similarity
                        best_pair = (left, right)

            force_merge = len(clusters) > maximum_topics
            if best_pair is None or (not force_merge and best_similarity < threshold):
                break

            left, right = best_pair
            merged_sum = tuple(
                left_value + right_value
                for left_value, right_value in zip(
                    clusters[left].vector_sum,
                    clusters[right].vector_sum,
                    strict=True,
                )
            )
            merged = _WorkingCluster(
                document_ids=sorted(
                    clusters[left].document_ids + clusters[right].document_ids
                ),
                vectors=clusters[left].vectors + clusters[right].vectors,
                vector_sum=merged_sum,
                centroid=self._normalize(merged_sum),
            )
            clusters = [
                cluster
                for index, cluster in enumerate(clusters)
                if index not in {left, right}
            ]
            clusters.append(merged)
            clusters.sort(key=lambda cluster: tuple(cluster.document_ids))

        ranked = sorted(
            clusters,
            key=lambda cluster: (-len(cluster.document_ids), tuple(cluster.document_ids)),
        )
        result_clusters = tuple(
            TopicModelCluster(
                cluster_id=f"topic-{index}",
                document_ids=tuple(cluster.document_ids),
                cohesion=self._cohesion(cluster),
            )
            for index, cluster in enumerate(ranked, start=1)
        )
        return TopicModelResult(
            clusters=result_clusters,
            metadata=self._metadata(),
        )

    def _metadata(self) -> TopicModelMetadata:
        embedding = self._embedding_provider.metadata
        return TopicModelMetadata(
            provider="semantic_agglomerative",
            provider_version="1",
            model_identifier=embedding.model_identifier,
            model_revision=embedding.model_revision,
            configuration_fingerprint=self._config["fingerprint"],
        )

    @staticmethod
    def _normalize(vector: tuple[float, ...]) -> tuple[float, ...]:
        norm = math.sqrt(sum(value * value for value in vector))
        if norm <= 0:
            raise RuntimeError("Topic embedding provider returned a zero vector")
        return tuple(value / norm for value in vector)

    @classmethod
    def _cluster_similarity(
        cls,
        left: _WorkingCluster,
        right: _WorkingCluster,
    ) -> float:
        return cls._cosine(left.centroid, right.centroid)

    @classmethod
    def _cohesion(cls, cluster: _WorkingCluster) -> float:
        if len(cluster.vectors) <= 1:
            return 1.0
        values = [
            cls._cosine(vector, cluster.centroid)
            for vector in cluster.vectors
        ]
        return max(0.0, min(1.0, sum(values) / len(values)))

    @staticmethod
    def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
        return max(
            -1.0,
            min(1.0, sum(a * b for a, b in zip(left, right, strict=True))),
        )

    @classmethod
    def _load_config(cls, config_reader: ConfigReader) -> dict[str, object]:
        threshold = cls._finite_float(
            config_reader.require("topic_model.similarity_threshold"),
            "topic_model.similarity_threshold",
        )
        if threshold < -1.0 or threshold > 1.0:
            raise ValueError("topic_model.similarity_threshold must be between -1 and 1")

        maximum_topics = config_reader.require("topic_model.maximum_topics")
        if (
            isinstance(maximum_topics, bool)
            or not isinstance(maximum_topics, int)
            or maximum_topics <= 0
        ):
            raise ValueError("topic_model.maximum_topics must be an integer > 0")

        payload = {
            "algorithm": "semantic_agglomerative_v1",
            "similarity_threshold": threshold,
            "maximum_topics": maximum_topics,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return {**payload, "fingerprint": fingerprint}

    @staticmethod
    def _finite_float(value: object, key: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Configuration '{key}' must be numeric")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"Configuration '{key}' must be finite")
        return result
