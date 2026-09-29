from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

from tests.evaluation.course_candidate_evaluation import (
    CourseCandidateDataset,
    CourseCandidateEvaluationError,
    CourseCandidateTuningEngine,
    PreparedCourseCandidateCase,
)
from tests.evaluation.phase10_gold_dataset import (
    Phase10GoldEvaluator,
    RankingMetrics,
)


DIAGNOSTIC_STATUS = (
    "COURSE_TUNING_RANKING_DIAGNOSTIC_ENGINEERING_EVIDENCE_NOT_HUMAN_GOLD"
)


@dataclass(frozen=True)
class CourseGoldPhraseDiagnostic:
    canonical_text: str
    grade: int
    candidate_generated: bool
    statistical_rank: int | None
    profile_statistical_score: float | None
    frequency: int | None
    normalized_frequency: float | None
    section_coverage: float | None
    phrase_quality: float | None
    semantic_rank: int | None
    bi_encoder_score: float | None
    reranker_score: float | None
    semantic_score: float | None
    reranked: bool | None
    pre_mmr_fused_rank: int | None
    normalized_statistical_score: float | None
    normalized_semantic_score: float | None
    fused_score: float | None
    deduplicated: bool
    deduplication_reason: str | None
    deduplicated_into: str | None
    deduplication_similarity: float | None
    final_hybrid_rank: int | None
    mmr_score: float | None
    mmr_rank_delta: int | None
    selection_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_text": self.canonical_text,
            "grade": self.grade,
            "candidate_generated": self.candidate_generated,
            "statistical_rank": self.statistical_rank,
            "profile_statistical_score": self.profile_statistical_score,
            "frequency": self.frequency,
            "normalized_frequency": self.normalized_frequency,
            "section_coverage": self.section_coverage,
            "phrase_quality": self.phrase_quality,
            "semantic_rank": self.semantic_rank,
            "bi_encoder_score": self.bi_encoder_score,
            "reranker_score": self.reranker_score,
            "semantic_score": self.semantic_score,
            "reranked": self.reranked,
            "pre_mmr_fused_rank": self.pre_mmr_fused_rank,
            "normalized_statistical_score": self.normalized_statistical_score,
            "normalized_semantic_score": self.normalized_semantic_score,
            "fused_score": self.fused_score,
            "deduplicated": self.deduplicated,
            "deduplication_reason": self.deduplication_reason,
            "deduplicated_into": self.deduplicated_into,
            "deduplication_similarity": self.deduplication_similarity,
            "final_hybrid_rank": self.final_hybrid_rank,
            "mmr_score": self.mmr_score,
            "mmr_rank_delta": self.mmr_rank_delta,
            "selection_status": self.selection_status,
        }


@dataclass(frozen=True)
class CourseCaseRankingDiagnostic:
    case_id: str
    domain: str
    relevance_count: int
    candidate_count: int
    final_ranked_count: int
    candidate_label_coverage: float
    metrics: RankingMetrics
    failure_stage_counts: dict[str, int]
    phrases: tuple[CourseGoldPhraseDiagnostic, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "domain": self.domain,
            "relevance_count": self.relevance_count,
            "candidate_count": self.candidate_count,
            "final_ranked_count": self.final_ranked_count,
            "candidate_label_coverage": self.candidate_label_coverage,
            "metrics": {
                "precision_at_5": self.metrics.precision_at_5,
                "precision_at_10": self.metrics.precision_at_10,
                "recall_at_10": self.metrics.recall_at_10,
                "ndcg_at_10": self.metrics.ndcg_at_10,
            },
            "failure_stage_counts": dict(self.failure_stage_counts),
            "phrases": [
                phrase.to_dict()
                for phrase in self.phrases
            ],
        }


@dataclass(frozen=True)
class CourseRankingDiagnosticResult:
    status: str
    source_materialized_sha256: str
    review_sha256: str
    review_status: str
    tuning_case_count: int
    frozen_holdout_case_count: int
    holdout_evaluated: bool
    active_weights: dict[str, float]
    aggregate_metrics: RankingMetrics
    candidate_label_coverage: float
    failure_stage_counts: dict[str, int]
    model_versions: tuple[str, ...]
    cases: tuple[CourseCaseRankingDiagnostic, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_materialized_sha256": self.source_materialized_sha256,
            "review_sha256": self.review_sha256,
            "review_status": self.review_status,
            "tuning_case_count": self.tuning_case_count,
            "frozen_holdout_case_count": self.frozen_holdout_case_count,
            "holdout_evaluated": self.holdout_evaluated,
            "active_weights": dict(self.active_weights),
            "aggregate_metrics": {
                "precision_at_5": self.aggregate_metrics.precision_at_5,
                "precision_at_10": self.aggregate_metrics.precision_at_10,
                "recall_at_10": self.aggregate_metrics.recall_at_10,
                "ndcg_at_10": self.aggregate_metrics.ndcg_at_10,
            },
            "candidate_label_coverage": self.candidate_label_coverage,
            "failure_stage_counts": dict(self.failure_stage_counts),
            "model_versions": list(self.model_versions),
            "cases": [
                case.to_dict()
                for case in self.cases
            ],
        }


class CourseRankingDiagnosticService:
    def __init__(
        self,
        engine: CourseCandidateTuningEngine,
    ):
        self._engine = engine

    async def diagnose_async(
        self,
        dataset: CourseCandidateDataset,
    ) -> CourseRankingDiagnosticResult:
        tuning_cases = dataset.cases_for_split("tuning")
        holdout_cases = dataset.cases_for_split("holdout")
        if not tuning_cases:
            raise CourseCandidateEvaluationError(
                "COURSE ranking diagnostic requires tuning cases"
            )
        if not holdout_cases:
            raise CourseCandidateEvaluationError(
                "COURSE ranking diagnostic requires a frozen holdout boundary"
            )

        weights = dict(
            self._engine.baseline_config.weights
        )
        case_results: list[CourseCaseRankingDiagnostic] = []
        prepared_cases: list[PreparedCourseCandidateCase] = []

        for case in tuning_cases:
            prepared = await self._engine.prepare_case_async(case)
            prepared_cases.append(prepared)
            profile_statistics, hybrid = (
                await self._engine.rank_prepared_result_async(
                    prepared,
                    weights,
                )
            )
            case_results.append(
                _diagnose_case(
                    prepared,
                    profile_statistics,
                    hybrid,
                    weights,
                )
            )

        aggregate_metrics = RankingMetrics(
            precision_at_5=_mean(
                case.metrics.precision_at_5
                for case in case_results
            ),
            precision_at_10=_mean(
                case.metrics.precision_at_10
                for case in case_results
            ),
            recall_at_10=_mean(
                case.metrics.recall_at_10
                for case in case_results
            ),
            ndcg_at_10=_mean(
                case.metrics.ndcg_at_10
                for case in case_results
            ),
        )
        aggregate_failures: Counter[str] = Counter()
        for case in case_results:
            aggregate_failures.update(
                case.failure_stage_counts
            )

        return CourseRankingDiagnosticResult(
            status=DIAGNOSTIC_STATUS,
            source_materialized_sha256=dataset.source_materialized_sha256,
            review_sha256=dataset.review_sha256,
            review_status=dataset.review_status,
            tuning_case_count=len(tuning_cases),
            frozen_holdout_case_count=len(holdout_cases),
            holdout_evaluated=False,
            active_weights=weights,
            aggregate_metrics=aggregate_metrics,
            candidate_label_coverage=_mean(
                case.candidate_label_coverage
                for case in case_results
            ),
            failure_stage_counts=dict(
                sorted(aggregate_failures.items())
            ),
            model_versions=self._engine.model_version(
                prepared_cases
            ),
            cases=tuple(case_results),
        )


def _diagnose_case(
    prepared: PreparedCourseCandidateCase,
    profile_statistics: tuple[Any, ...],
    hybrid: Any,
    weights: dict[str, float],
) -> CourseCaseRankingDiagnostic:
    statistics_by_id = {
        item.canonical_text: item
        for item in profile_statistics
    }
    semantic_by_id = {
        item.canonical_text: item
        for item in prepared.semantic.candidates
    }
    if set(statistics_by_id) != set(semantic_by_id):
        raise CourseCandidateEvaluationError(
            "COURSE diagnostic statistical/semantic candidate identities differ"
        )

    statistical_rank = {
        item.canonical_text: rank
        for rank, item in enumerate(
            sorted(
                profile_statistics,
                key=lambda item: (
                    -item.statistical_score,
                    item.canonical_text,
                ),
            ),
            start=1,
        )
    }

    fused = _pre_mmr_fused_ranking(
        profile_statistics,
        prepared.semantic.candidates,
        weights,
    )
    fused_by_id = {
        item["canonical_text"]: item
        for item in fused
    }
    final_by_id = {
        item.canonical_text: item
        for item in hybrid.candidates
    }
    dedup_by_removed = {
        item.removed_canonical_text: item
        for item in hybrid.deduplicated
    }

    ranked = [
        item.canonical_text
        for item in hybrid.candidates
    ]
    metrics = Phase10GoldEvaluator.ranking_metrics(
        ranked,
        prepared.case.relevance,
    )

    phrases: list[CourseGoldPhraseDiagnostic] = []
    stage_counts: Counter[str] = Counter()
    relevant = {
        text
        for text, grade in prepared.case.relevance.items()
        if grade > 0
    }
    candidate_hits = 0

    for canonical_text, grade in sorted(
        prepared.case.relevance.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        stat = statistics_by_id.get(canonical_text)
        sem = semantic_by_id.get(canonical_text)
        pre_mmr = fused_by_id.get(canonical_text)
        final = final_by_id.get(canonical_text)
        dedup = dedup_by_removed.get(canonical_text)

        if stat is None:
            status = "not_generated_by_candidate_engine"
            stage_counts[status] += 1
            phrases.append(
                CourseGoldPhraseDiagnostic(
                    canonical_text=canonical_text,
                    grade=grade,
                    candidate_generated=False,
                    statistical_rank=None,
                    profile_statistical_score=None,
                    frequency=None,
                    normalized_frequency=None,
                    section_coverage=None,
                    phrase_quality=None,
                    semantic_rank=None,
                    bi_encoder_score=None,
                    reranker_score=None,
                    semantic_score=None,
                    reranked=None,
                    pre_mmr_fused_rank=None,
                    normalized_statistical_score=None,
                    normalized_semantic_score=None,
                    fused_score=None,
                    deduplicated=False,
                    deduplication_reason=None,
                    deduplicated_into=None,
                    deduplication_similarity=None,
                    final_hybrid_rank=None,
                    mmr_score=None,
                    mmr_rank_delta=None,
                    selection_status=status,
                )
            )
            continue

        candidate_hits += 1
        if sem is None or pre_mmr is None:
            raise CourseCandidateEvaluationError(
                "COURSE diagnostic candidate is missing semantic/fused state"
            )

        if final is not None:
            delta = final.rank - pre_mmr["rank"]
            if final.rank <= 10:
                status = "selected_top_10"
            else:
                status = "selected_outside_top_10"
        elif dedup is not None:
            delta = None
            status = f"deduplicated:{dedup.reason}"
        elif pre_mmr["rank"] > hybrid.diversity_candidate_pool_size:
            delta = None
            status = "outside_diversity_candidate_pool"
        else:
            delta = None
            status = "mmr_or_top_k_cutoff"

        stage_counts[status] += 1
        phrases.append(
            CourseGoldPhraseDiagnostic(
                canonical_text=canonical_text,
                grade=grade,
                candidate_generated=True,
                statistical_rank=statistical_rank[canonical_text],
                profile_statistical_score=stat.statistical_score,
                frequency=stat.frequency,
                normalized_frequency=stat.normalized_frequency,
                section_coverage=stat.section_coverage,
                phrase_quality=stat.phrase_quality,
                semantic_rank=sem.rank,
                bi_encoder_score=sem.bi_encoder_score,
                reranker_score=sem.reranker_score,
                semantic_score=sem.semantic_score,
                reranked=sem.reranked,
                pre_mmr_fused_rank=pre_mmr["rank"],
                normalized_statistical_score=pre_mmr[
                    "normalized_statistical_score"
                ],
                normalized_semantic_score=pre_mmr[
                    "normalized_semantic_score"
                ],
                fused_score=pre_mmr["fused_score"],
                deduplicated=dedup is not None,
                deduplication_reason=(
                    dedup.reason
                    if dedup is not None
                    else None
                ),
                deduplicated_into=(
                    dedup.kept_canonical_text
                    if dedup is not None
                    else None
                ),
                deduplication_similarity=(
                    dedup.similarity
                    if dedup is not None
                    else None
                ),
                final_hybrid_rank=(
                    final.rank
                    if final is not None
                    else None
                ),
                mmr_score=(
                    final.mmr_score
                    if final is not None
                    else None
                ),
                mmr_rank_delta=delta,
                selection_status=status,
            )
        )

    return CourseCaseRankingDiagnostic(
        case_id=prepared.case.case_id,
        domain=prepared.case.domain,
        relevance_count=len(relevant),
        candidate_count=len(profile_statistics),
        final_ranked_count=len(hybrid.candidates),
        candidate_label_coverage=(
            candidate_hits / len(relevant)
            if relevant
            else 1.0
        ),
        metrics=metrics,
        failure_stage_counts=dict(
            sorted(stage_counts.items())
        ),
        phrases=tuple(phrases),
    )


def _pre_mmr_fused_ranking(
    statistics: tuple[Any, ...],
    semantic: tuple[Any, ...],
    weights: dict[str, float],
) -> tuple[dict[str, Any], ...]:
    statistical_by_id = {
        item.canonical_text: item
        for item in statistics
    }
    semantic_by_id = {
        item.canonical_text: item
        for item in semantic
    }
    if set(statistical_by_id) != set(semantic_by_id):
        raise CourseCandidateEvaluationError(
            "COURSE diagnostic cannot fuse mismatched candidate sets"
        )

    identities = tuple(sorted(statistical_by_id))
    statistical_values = tuple(
        float(
            statistical_by_id[identity].statistical_score
        )
        for identity in identities
    )
    semantic_values = tuple(
        float(
            semantic_by_id[identity].semantic_score
        )
        for identity in identities
    )
    normalized_statistical = _min_max(
        statistical_values
    )
    normalized_semantic = _min_max(
        semantic_values
    )

    statistical_weight = (
        weights["frequency"]
        + weights["section_coverage"]
        + weights["phrase_quality"]
    )
    semantic_weight = weights["semantic_relevance"]
    total = statistical_weight + semantic_weight
    if total <= 0.0:
        raise CourseCandidateEvaluationError(
            "COURSE diagnostic active fusion weight is zero"
        )
    statistical_weight /= total
    semantic_weight /= total

    rows = []
    for index, identity in enumerate(identities):
        fused_score = (
            statistical_weight
            * normalized_statistical[index]
            + semantic_weight
            * normalized_semantic[index]
        )
        rows.append(
            {
                "canonical_text": identity,
                "normalized_statistical_score": normalized_statistical[index],
                "normalized_semantic_score": normalized_semantic[index],
                "fused_score": min(
                    max(fused_score, 0.0),
                    1.0,
                ),
            }
        )

    ordered = sorted(
        rows,
        key=lambda item: (
            -item["fused_score"],
            -item["normalized_semantic_score"],
            -item["normalized_statistical_score"],
            item["canonical_text"],
        ),
    )
    return tuple(
        {
            **item,
            "rank": rank,
        }
        for rank, item in enumerate(
            ordered,
            start=1,
        )
    )


def _min_max(
    values: tuple[float, ...],
) -> tuple[float, ...]:
    if not values:
        return ()
    finite = tuple(float(value) for value in values)
    if any(
        not math.isfinite(value)
        for value in finite
    ):
        raise CourseCandidateEvaluationError(
            "COURSE diagnostic score contains NaN or Inf"
        )
    minimum = min(finite)
    maximum = max(finite)
    if maximum == minimum:
        return tuple(
            1.0
            for _ in finite
        )
    span = maximum - minimum
    return tuple(
        (value - minimum) / span
        for value in finite
    )


def _mean(
    values: Iterable[float],
) -> float:
    items = tuple(
        float(value)
        for value in values
    )
    if not items:
        raise CourseCandidateEvaluationError(
            "Cannot average an empty COURSE diagnostic sequence"
        )
    return sum(items) / len(items)
