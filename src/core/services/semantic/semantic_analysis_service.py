from __future__ import annotations

import math
from dataclasses import dataclass

from src.core.services.semantic.providers.embedding_provider import EmbeddingProvider
from src.core.services.semantic.providers.provider_metadata import SemanticProviderMetadata
from src.core.services.semantic.providers.reranker_provider import RerankerProvider
from src.core.services.statistical.statistical_analysis_service import StatisticalCandidateResult
from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


@dataclass(frozen=True)
class SemanticCandidateResult:
    text: str
    canonical_text: str
    bi_encoder_similarity: float
    bi_encoder_score: float
    reranker_score: float | None
    semantic_score: float
    reranked: bool
    rank: int


@dataclass(frozen=True)
class SemanticAnalysisResult:
    candidates: tuple[SemanticCandidateResult, ...]
    embedding_metadata: SemanticProviderMetadata
    reranker_metadata: SemanticProviderMetadata
    similarity_metric: str
    semantic_score_strategy: str
    rerank_top_n: int


@inject
class SemanticAnalysisService:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        reranker_provider: RerankerProvider,
        config_reader: ConfigReader,
    ):
        self._embedding_provider = embedding_provider
        self._reranker_provider = reranker_provider
        self._rerank_top_n = self._load_top_n(config_reader)

    async def analyze_async(
        self,
        context: str,
        candidates: tuple[StatisticalCandidateResult, ...],
    ) -> SemanticAnalysisResult:
        if not candidates:
            return SemanticAnalysisResult(
                candidates=(),
                embedding_metadata=self._embedding_provider.metadata,
                reranker_metadata=self._reranker_provider.metadata,
                similarity_metric="cosine",
                semantic_score_strategy="reranker_for_top_n_else_normalized_cosine",
                rerank_top_n=self._rerank_top_n,
            )
        if not isinstance(context, str) or not context.strip():
            raise ValueError("semantic context must be a non-empty string")

        canonical = [item.canonical_text for item in candidates]
        if len(set(canonical)) != len(canonical):
            raise ValueError("semantic candidates must have unique canonical_text values")

        vectors = await self._embedding_provider.embed_async([context, *canonical])
        if len(vectors) != len(canonical) + 1:
            raise ValueError("embedding provider returned an invalid output length")

        query_vector = self._validate_vector(vectors[0], "query")
        candidate_vectors = [
            self._validate_vector(vector, f"candidate[{index}]")
            for index, vector in enumerate(vectors[1:])
        ]
        if any(len(vector) != len(query_vector) for vector in candidate_vectors):
            raise ValueError("embedding provider returned inconsistent vector dimensions")

        preselected: list[tuple[int, float, float]] = []
        for index, vector in enumerate(candidate_vectors):
            similarity = self._cosine_similarity(query_vector, vector)
            normalized = (similarity + 1.0) / 2.0
            preselected.append((index, similarity, normalized))

        preselected.sort(key=lambda item: (-item[2], candidates[item[0]].canonical_text))
        top_count = min(self._rerank_top_n, len(preselected))
        top_indices = [item[0] for item in preselected[:top_count]]

        rerank_scores = await self._reranker_provider.rerank_async(
            context,
            [canonical[index] for index in top_indices],
        )
        if len(rerank_scores) != top_count:
            raise ValueError("reranker provider returned an invalid output length")

        rerank_by_index: dict[int, float] = {}
        for index, score in zip(top_indices, rerank_scores, strict=True):
            rerank_by_index[index] = self._validate_probability(score, "reranker score")

        bi_by_index = {index: (similarity, score) for index, similarity, score in preselected}
        provisional: list[tuple[int, float, float, float | None, float, bool]] = []

        for index in range(len(candidates)):
            similarity, bi_score = bi_by_index[index]
            reranker_score = rerank_by_index.get(index)
            reranked = reranker_score is not None
            semantic_score = reranker_score if reranked else bi_score
            provisional.append(
                (index, similarity, bi_score, reranker_score, semantic_score, reranked)
            )

        provisional.sort(
            key=lambda item: (
                -item[4],
                -item[2],
                candidates[item[0]].canonical_text,
            )
        )

        ranked = tuple(
            SemanticCandidateResult(
                text=candidates[index].text,
                canonical_text=candidates[index].canonical_text,
                bi_encoder_similarity=similarity,
                bi_encoder_score=bi_score,
                reranker_score=reranker_score,
                semantic_score=semantic_score,
                reranked=reranked,
                rank=rank,
            )
            for rank, (
                index,
                similarity,
                bi_score,
                reranker_score,
                semantic_score,
                reranked,
            ) in enumerate(provisional, start=1)
        )

        return SemanticAnalysisResult(
            candidates=ranked,
            embedding_metadata=self._embedding_provider.metadata,
            reranker_metadata=self._reranker_provider.metadata,
            similarity_metric="cosine",
            semantic_score_strategy="reranker_for_top_n_else_normalized_cosine",
            rerank_top_n=self._rerank_top_n,
        )

    @staticmethod
    def _validate_vector(values: object, label: str) -> tuple[float, ...]:
        if not isinstance(values, (list, tuple)) or not values:
            raise ValueError(f"{label} embedding must be a non-empty sequence")
        vector = tuple(float(value) for value in values)
        if any(not math.isfinite(value) for value in vector):
            raise ValueError(f"{label} embedding contains NaN or Inf")
        return vector

    @staticmethod
    def _validate_probability(value: object, label: str) -> float:
        numeric = float(value)
        if not math.isfinite(numeric) or numeric < 0.0 or numeric > 1.0:
            raise ValueError(f"{label} must be finite and within [0, 1]")
        return numeric

    @staticmethod
    def _cosine_similarity(
        left: tuple[float, ...],
        right: tuple[float, ...],
    ) -> float:
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0.0 or right_norm == 0.0:
            raise ValueError("embedding provider returned a zero-norm vector")

        similarity = sum(
            left_value * right_value
            for left_value, right_value in zip(left, right, strict=True)
        ) / (left_norm * right_norm)

        if not math.isfinite(similarity):
            raise ValueError("cosine similarity is not finite")

        return min(max(similarity, -1.0), 1.0)

    @staticmethod
    def _load_top_n(config_reader: ConfigReader) -> int:
        value = config_reader.require("semantic_analysis.rerank_top_n")
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("semantic_analysis.rerank_top_n must be an integer > 0")
        return value
