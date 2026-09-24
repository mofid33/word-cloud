from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, Sequence

from src.core.services.semantic.providers.embedding_provider import EmbeddingProvider
from src.core.services.semantic.providers.provider_metadata import SemanticProviderMetadata
from src.core.services.semantic.semantic_analysis_service import (
    SemanticAnalysisResult,
    SemanticCandidateResult,
)
from src.core.services.statistical.statistical_analysis_service import (
    StatisticalCandidateResult,
)
from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class FusionWeights:
    statistical: float
    semantic: float


@dataclass(frozen=True)
class HybridRankingConfig:
    normalization_strategy: str
    baseline_weights: FusionWeights
    lexical_deduplication_threshold: float
    mmr_lambda: float
    diversity_candidate_pool_size: int
    maximum_ranked_results: int


@dataclass(frozen=True)
class DeduplicationRecord:
    removed_canonical_text: str
    kept_canonical_text: str
    reason: str
    similarity: float


@dataclass(frozen=True)
class HybridRankedCandidate:
    text: str
    canonical_text: str
    statistical_score: float
    semantic_score: float
    normalized_statistical_score: float
    normalized_semantic_score: float
    fused_score: float
    mmr_score: float
    statistical_rank: int
    semantic_rank: int
    rank: int
    is_protected: bool


@dataclass(frozen=True)
class HybridRankingResult:
    candidates: tuple[HybridRankedCandidate, ...]
    deduplicated: tuple[DeduplicationRecord, ...]
    scoring_version: str
    normalization_strategy: str
    weights: FusionWeights
    deduplication_strategy: str
    lexical_deduplication_threshold: float
    diversity_strategy: str
    mmr_lambda: float
    diversity_candidate_pool_size: int
    maximum_ranked_results: int
    embedding_metadata: SemanticProviderMetadata
    semantic_score_strategy: str
    deterministic_tie_breaking: str


@dataclass(frozen=True)
class _JoinedCandidate:
    statistical: StatisticalCandidateResult
    semantic: SemanticCandidateResult
    statistical_rank: int
    normalized_statistical_score: float
    normalized_semantic_score: float
    fused_score: float


@inject
class HybridRankingService:
    SCORING_VERSION = "hybrid-ranking-v1"

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        config_reader: ConfigReader,
    ):
        self._embedding_provider = embedding_provider
        self._config = self._load_config(config_reader)

    @property
    def config(self) -> HybridRankingConfig:
        return self._config

    async def rank_async(
        self,
        statistical_candidates: tuple[StatisticalCandidateResult, ...],
        semantic_result: SemanticAnalysisResult,
        *,
        weights: FusionWeights | None = None,
        maximum_results: int | None = None,
    ) -> HybridRankingResult:
        selected_weights = self._validate_weights(
            weights or self._config.baseline_weights
        )
        selected_maximum = self._validate_maximum_results(maximum_results)

        if not statistical_candidates and not semantic_result.candidates:
            return self._build_result(
                candidates=(),
                deduplicated=(),
                weights=selected_weights,
                maximum_results=selected_maximum,
                semantic_result=semantic_result,
            )

        joined = self._join_candidates(
            statistical_candidates,
            semantic_result.candidates,
            selected_weights,
        )
        deduplicated, removed = self._deduplicate(joined)
        ranked = await self._apply_mmr_async(
            deduplicated,
            maximum_results=selected_maximum,
        )

        return self._build_result(
            candidates=ranked,
            deduplicated=removed,
            weights=selected_weights,
            maximum_results=selected_maximum,
            semantic_result=semantic_result,
        )

    def _join_candidates(
        self,
        statistical_candidates: tuple[StatisticalCandidateResult, ...],
        semantic_candidates: tuple[SemanticCandidateResult, ...],
        weights: FusionWeights,
    ) -> tuple[_JoinedCandidate, ...]:
        statistical_by_id = self._unique_statistical_candidates(statistical_candidates)
        semantic_by_id = self._unique_semantic_candidates(semantic_candidates)

        statistical_ids = set(statistical_by_id)
        semantic_ids = set(semantic_by_id)
        if statistical_ids != semantic_ids:
            missing_semantic = len(statistical_ids - semantic_ids)
            missing_statistical = len(semantic_ids - statistical_ids)
            raise ValueError(
                "statistical and semantic candidate identities do not match "
                f"(missing_semantic={missing_semantic}, "
                f"missing_statistical={missing_statistical})"
            )

        ordered_ids = tuple(sorted(statistical_ids))
        statistical_scores = tuple(
            self._finite_score(
                statistical_by_id[identity].statistical_score,
                "statistical_score",
            )
            for identity in ordered_ids
        )
        semantic_scores = tuple(
            self._finite_score(
                semantic_by_id[identity].semantic_score,
                "semantic_score",
            )
            for identity in ordered_ids
        )
        normalized_statistical = self._normalize(statistical_scores)
        normalized_semantic = self._normalize(semantic_scores)

        statistical_order = sorted(
            ordered_ids,
            key=lambda identity: (
                -statistical_by_id[identity].statistical_score,
                identity,
            ),
        )
        statistical_rank = {
            identity: rank
            for rank, identity in enumerate(statistical_order, start=1)
        }

        joined = tuple(
            _JoinedCandidate(
                statistical=statistical_by_id[identity],
                semantic=semantic_by_id[identity],
                statistical_rank=statistical_rank[identity],
                normalized_statistical_score=normalized_statistical[index],
                normalized_semantic_score=normalized_semantic[index],
                fused_score=self._bounded_score(
                    weights.statistical * normalized_statistical[index]
                    + weights.semantic * normalized_semantic[index]
                ),
            )
            for index, identity in enumerate(ordered_ids)
        )
        return tuple(
            sorted(
                joined,
                key=lambda item: (
                    -item.fused_score,
                    -item.normalized_semantic_score,
                    -item.normalized_statistical_score,
                    item.statistical.canonical_text,
                ),
            )
        )

    def _deduplicate(
        self,
        candidates: tuple[_JoinedCandidate, ...],
    ) -> tuple[tuple[_JoinedCandidate, ...], tuple[DeduplicationRecord, ...]]:
        kept: list[_JoinedCandidate] = []
        removed: list[DeduplicationRecord] = []

        for candidate in candidates:
            duplicate = self._find_duplicate(candidate, kept)
            if duplicate is None:
                kept.append(candidate)
                continue
            kept_candidate, reason, similarity = duplicate
            removed.append(
                DeduplicationRecord(
                    removed_canonical_text=candidate.statistical.canonical_text,
                    kept_canonical_text=kept_candidate.statistical.canonical_text,
                    reason=reason,
                    similarity=similarity,
                )
            )

        return tuple(kept), tuple(removed)

    def _find_duplicate(
        self,
        candidate: _JoinedCandidate,
        kept: Sequence[_JoinedCandidate],
    ) -> tuple[_JoinedCandidate, str, float] | None:
        text_key = self._exact_text_key(candidate.statistical.text)
        canonical_key = self._identity_key(candidate.statistical.canonical_text)

        for existing in kept:
            if text_key == self._exact_text_key(existing.statistical.text):
                return existing, "exact_text", 1.0
            if canonical_key == self._identity_key(existing.statistical.canonical_text):
                return existing, "canonical", 1.0

        if candidate.statistical.is_protected:
            return None

        for existing in kept:
            if existing.statistical.is_protected:
                continue
            similarity = self._lexical_similarity(
                candidate.statistical.canonical_text,
                existing.statistical.canonical_text,
            )
            if similarity >= self._config.lexical_deduplication_threshold:
                return existing, "lexical_near_duplicate", similarity
        return None

    async def _apply_mmr_async(
        self,
        candidates: tuple[_JoinedCandidate, ...],
        *,
        maximum_results: int,
    ) -> tuple[HybridRankedCandidate, ...]:
        if not candidates:
            return ()

        pool_size = min(
            len(candidates),
            self._config.diversity_candidate_pool_size,
        )
        pool = tuple(candidates[:pool_size])
        target_count = min(maximum_results, len(pool))

        if target_count == 1:
            candidate = pool[0]
            return (self._to_ranked(candidate, mmr_score=candidate.fused_score, rank=1),)

        vectors_raw = await self._embedding_provider.embed_async(
            tuple(item.statistical.canonical_text for item in pool)
        )
        if len(vectors_raw) != len(pool):
            raise ValueError("embedding provider returned an invalid diversity output length")
        vectors = tuple(
            self._validate_vector(vector, f"diversity candidate[{index}]")
            for index, vector in enumerate(vectors_raw)
        )
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1:
            raise ValueError("embedding provider returned inconsistent diversity dimensions")

        remaining = list(range(len(pool)))
        selected: list[int] = []
        mmr_by_index: dict[int, float] = {}

        while remaining and len(selected) < target_count:
            best_index: int | None = None
            best_key: tuple[float, float, str] | None = None
            best_mmr = 0.0

            for index in remaining:
                if not selected:
                    diversity_similarity = 0.0
                else:
                    diversity_similarity = max(
                        self._normalized_cosine(vectors[index], vectors[chosen])
                        for chosen in selected
                    )

                mmr_score = (
                    self._config.mmr_lambda * pool[index].fused_score
                    - (1.0 - self._config.mmr_lambda) * diversity_similarity
                )
                key = (
                    mmr_score,
                    pool[index].fused_score,
                    self._reverse_lexical_key(pool[index].statistical.canonical_text),
                )
                if best_key is None or key > best_key:
                    best_key = key
                    best_index = index
                    best_mmr = mmr_score

            assert best_index is not None
            selected.append(best_index)
            remaining.remove(best_index)
            mmr_by_index[best_index] = best_mmr

        return tuple(
            self._to_ranked(
                pool[index],
                mmr_score=mmr_by_index[index],
                rank=rank,
            )
            for rank, index in enumerate(selected, start=1)
        )

    @staticmethod
    def _reverse_lexical_key(value: str) -> str:
        return "".join(chr(0x10FFFF - ord(char)) for char in value)

    @staticmethod
    def _to_ranked(
        candidate: _JoinedCandidate,
        *,
        mmr_score: float,
        rank: int,
    ) -> HybridRankedCandidate:
        return HybridRankedCandidate(
            text=candidate.statistical.text,
            canonical_text=candidate.statistical.canonical_text,
            statistical_score=candidate.statistical.statistical_score,
            semantic_score=candidate.semantic.semantic_score,
            normalized_statistical_score=candidate.normalized_statistical_score,
            normalized_semantic_score=candidate.normalized_semantic_score,
            fused_score=candidate.fused_score,
            mmr_score=mmr_score,
            statistical_rank=candidate.statistical_rank,
            semantic_rank=candidate.semantic.rank,
            rank=rank,
            is_protected=candidate.statistical.is_protected,
        )

    def _build_result(
        self,
        *,
        candidates: tuple[HybridRankedCandidate, ...],
        deduplicated: tuple[DeduplicationRecord, ...],
        weights: FusionWeights,
        maximum_results: int,
        semantic_result: SemanticAnalysisResult,
    ) -> HybridRankingResult:
        return HybridRankingResult(
            candidates=candidates,
            deduplicated=deduplicated,
            scoring_version=self.SCORING_VERSION,
            normalization_strategy=self._config.normalization_strategy,
            weights=weights,
            deduplication_strategy="exact_text+canonical+lexical_sequence_ratio",
            lexical_deduplication_threshold=self._config.lexical_deduplication_threshold,
            diversity_strategy="mmr_cosine",
            mmr_lambda=self._config.mmr_lambda,
            diversity_candidate_pool_size=self._config.diversity_candidate_pool_size,
            maximum_ranked_results=maximum_results,
            embedding_metadata=semantic_result.embedding_metadata,
            semantic_score_strategy=semantic_result.semantic_score_strategy,
            deterministic_tie_breaking=(
                "fused_score, semantic_score, statistical_score, canonical_text"
            ),
        )

    def _normalize(self, values: tuple[float, ...]) -> tuple[float, ...]:
        if self._config.normalization_strategy != "min_max":
            raise ValueError("unsupported hybrid ranking normalization strategy")
        if not values:
            return ()
        finite = tuple(self._finite_score(value, "normalization score") for value in values)
        minimum = min(finite)
        maximum = max(finite)
        if maximum == minimum:
            return tuple(1.0 for _ in finite)
        span = maximum - minimum
        return tuple((value - minimum) / span for value in finite)

    @classmethod
    def _unique_statistical_candidates(
        cls,
        candidates: Iterable[StatisticalCandidateResult],
    ) -> dict[str, StatisticalCandidateResult]:
        result: dict[str, StatisticalCandidateResult] = {}
        for candidate in candidates:
            identity = cls._required_identity(candidate.canonical_text)
            if identity in result:
                raise ValueError("statistical candidates contain duplicate canonical_text")
            result[identity] = candidate
        return result

    @classmethod
    def _unique_semantic_candidates(
        cls,
        candidates: Iterable[SemanticCandidateResult],
    ) -> dict[str, SemanticCandidateResult]:
        result: dict[str, SemanticCandidateResult] = {}
        for candidate in candidates:
            identity = cls._required_identity(candidate.canonical_text)
            if identity in result:
                raise ValueError("semantic candidates contain duplicate canonical_text")
            result[identity] = candidate
        return result

    @staticmethod
    def _required_identity(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("candidate canonical_text must be a non-empty string")
        return value.strip()

    @staticmethod
    def _exact_text_key(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value)
        return _SPACE_RE.sub(" ", normalized).strip()

    @staticmethod
    def _identity_key(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        return _SPACE_RE.sub(" ", normalized).strip()

    @classmethod
    def _lexical_similarity(cls, left: str, right: str) -> float:
        left_key = cls._identity_key(left)
        right_key = cls._identity_key(right)
        if not left_key or not right_key:
            return 0.0
        return SequenceMatcher(a=left_key, b=right_key, autojunk=False).ratio()

    @staticmethod
    def _finite_score(value: object, label: str) -> float:
        if isinstance(value, bool):
            raise ValueError(f"{label} must be numeric, not boolean")
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} must be numeric") from exc
        if not math.isfinite(numeric):
            raise ValueError(f"{label} must be finite")
        return numeric

    @staticmethod
    def _bounded_score(value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("hybrid score must be finite")
        return min(max(value, 0.0), 1.0)

    @classmethod
    def _validate_vector(
        cls,
        values: object,
        label: str,
    ) -> tuple[float, ...]:
        if not isinstance(values, (list, tuple)) or not values:
            raise ValueError(f"{label} embedding must be a non-empty sequence")
        vector = tuple(cls._finite_score(value, label) for value in values)
        if math.sqrt(sum(value * value for value in vector)) == 0.0:
            raise ValueError(f"{label} embedding must have non-zero norm")
        return vector

    @classmethod
    def _normalized_cosine(
        cls,
        left: tuple[float, ...],
        right: tuple[float, ...],
    ) -> float:
        if len(left) != len(right):
            raise ValueError("diversity embeddings must have consistent dimensions")
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0.0 or right_norm == 0.0:
            raise ValueError("diversity embedding must have non-zero norm")
        cosine = sum(
            left_value * right_value
            for left_value, right_value in zip(left, right, strict=True)
        ) / (left_norm * right_norm)
        if not math.isfinite(cosine):
            raise ValueError("diversity cosine similarity must be finite")
        cosine = min(max(cosine, -1.0), 1.0)
        return (cosine + 1.0) / 2.0

    def _validate_maximum_results(self, value: int | None) -> int:
        if value is None:
            return self._config.maximum_ranked_results
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("maximum_results must be an integer > 0")
        if value > self._config.diversity_candidate_pool_size:
            raise ValueError(
                "maximum_results must be <= diversity_candidate_pool_size"
            )
        return value

    @classmethod
    def _validate_weights(cls, weights: FusionWeights) -> FusionWeights:
        statistical = cls._finite_unit_interval(
            weights.statistical,
            "statistical fusion weight",
        )
        semantic = cls._finite_unit_interval(
            weights.semantic,
            "semantic fusion weight",
        )
        if not math.isclose(statistical + semantic, 1.0, abs_tol=1e-9):
            raise ValueError("hybrid ranking fusion weights must sum to 1")
        return FusionWeights(statistical=statistical, semantic=semantic)

    @classmethod
    def _load_config(cls, config_reader: ConfigReader) -> HybridRankingConfig:
        strategy = config_reader.require("hybrid_ranking.normalization_strategy")
        if not isinstance(strategy, str) or strategy.strip().lower() != "min_max":
            raise ValueError(
                "hybrid_ranking.normalization_strategy must be 'min_max'"
            )

        baseline_weights = cls._validate_weights(
            FusionWeights(
                statistical=cls._required_float(
                    config_reader,
                    "hybrid_ranking.baseline_weights.statistical",
                    minimum=0.0,
                    maximum=1.0,
                ),
                semantic=cls._required_float(
                    config_reader,
                    "hybrid_ranking.baseline_weights.semantic",
                    minimum=0.0,
                    maximum=1.0,
                ),
            )
        )
        threshold = cls._required_float(
            config_reader,
            "hybrid_ranking.lexical_deduplication_threshold",
            minimum=0.0,
            maximum=1.0,
        )
        mmr_lambda = cls._required_float(
            config_reader,
            "hybrid_ranking.mmr_lambda",
            minimum=0.0,
            maximum=1.0,
        )
        pool_size = cls._required_positive_int(
            config_reader,
            "hybrid_ranking.diversity_candidate_pool_size",
        )
        maximum_results = cls._required_positive_int(
            config_reader,
            "hybrid_ranking.maximum_ranked_results",
        )
        if pool_size < maximum_results:
            raise ValueError(
                "hybrid_ranking.diversity_candidate_pool_size must be "
                ">= hybrid_ranking.maximum_ranked_results"
            )

        return HybridRankingConfig(
            normalization_strategy="min_max",
            baseline_weights=baseline_weights,
            lexical_deduplication_threshold=threshold,
            mmr_lambda=mmr_lambda,
            diversity_candidate_pool_size=pool_size,
            maximum_ranked_results=maximum_results,
        )

    @staticmethod
    def _required_positive_int(config_reader: ConfigReader, key: str) -> int:
        value = config_reader.require(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"Configuration '{key}' must be an integer > 0")
        return value

    @classmethod
    def _required_float(
        cls,
        config_reader: ConfigReader,
        key: str,
        *,
        minimum: float,
        maximum: float,
    ) -> float:
        value = config_reader.require(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Configuration '{key}' must be numeric")
        numeric = float(value)
        if (
            not math.isfinite(numeric)
            or numeric < minimum
            or numeric > maximum
        ):
            raise ValueError(
                f"Configuration '{key}' must be finite and within "
                f"[{minimum}, {maximum}]"
            )
        return numeric

    @classmethod
    def _finite_unit_interval(cls, value: object, label: str) -> float:
        numeric = cls._finite_score(value, label)
        if numeric < 0.0 or numeric > 1.0:
            raise ValueError(f"{label} must be within [0, 1]")
        return numeric
