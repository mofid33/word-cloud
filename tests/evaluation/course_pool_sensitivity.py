from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from tests.evaluation.course_candidate_evaluation import (
    CourseCandidateDataset,
    CourseCandidateEvaluationError,
    CourseCandidateTuningEngine,
)
from tests.evaluation.course_ranking_diagnostic import (
    _pre_mmr_fused_ranking,
)


POOL_SIZES = (25, 50, 100, 200, 400)
POOL_SENSITIVITY_STATUS = (
    "COURSE_TUNING_POOL_SENSITIVITY_ENGINEERING_EVIDENCE_NOT_HUMAN_GOLD"
)


@dataclass(frozen=True)
class CoursePoolSensitivityCase:
    case_id: str
    candidate_count: int
    relevant_count: int
    generated_relevant_count: int
    reranked_relevant_count: int
    pool_hits: dict[int, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "candidate_count": self.candidate_count,
            "relevant_count": self.relevant_count,
            "generated_relevant_count": self.generated_relevant_count,
            "candidate_label_coverage": (
                self.generated_relevant_count / self.relevant_count
                if self.relevant_count
                else 1.0
            ),
            "reranked_relevant_count": self.reranked_relevant_count,
            "reranked_relevant_coverage": (
                self.reranked_relevant_count / self.relevant_count
                if self.relevant_count
                else 1.0
            ),
            "pool_hits": {
                str(size): {
                    "relevant_hits": self.pool_hits[size],
                    "recall_all_relevant": (
                        self.pool_hits[size] / self.relevant_count
                        if self.relevant_count
                        else 1.0
                    ),
                    "recall_generated_relevant": (
                        self.pool_hits[size] / self.generated_relevant_count
                        if self.generated_relevant_count
                        else 1.0
                    ),
                }
                for size in POOL_SIZES
            },
        }


@dataclass(frozen=True)
class CoursePoolSensitivityResult:
    status: str
    source_materialized_sha256: str
    review_sha256: str
    review_status: str
    tuning_case_count: int
    frozen_holdout_case_count: int
    holdout_evaluated: bool
    pool_sizes: tuple[int, ...]
    active_weights: dict[str, float]
    cases: tuple[CoursePoolSensitivityCase, ...]

    def to_dict(self) -> dict[str, Any]:
        relevant_count = sum(case.relevant_count for case in self.cases)
        generated_count = sum(
            case.generated_relevant_count
            for case in self.cases
        )
        reranked_count = sum(
            case.reranked_relevant_count
            for case in self.cases
        )
        aggregate_pool_hits = {
            size: sum(
                case.pool_hits[size]
                for case in self.cases
            )
            for size in self.pool_sizes
        }
        return {
            "status": self.status,
            "source_materialized_sha256": self.source_materialized_sha256,
            "review_sha256": self.review_sha256,
            "review_status": self.review_status,
            "tuning_case_count": self.tuning_case_count,
            "frozen_holdout_case_count": self.frozen_holdout_case_count,
            "holdout_evaluated": self.holdout_evaluated,
            "pool_sizes": list(self.pool_sizes),
            "active_weights": dict(self.active_weights),
            "aggregate": {
                "relevant_count": relevant_count,
                "generated_relevant_count": generated_count,
                "candidate_label_coverage": (
                    generated_count / relevant_count
                    if relevant_count
                    else 1.0
                ),
                "reranked_relevant_count": reranked_count,
                "reranked_relevant_coverage": (
                    reranked_count / relevant_count
                    if relevant_count
                    else 1.0
                ),
                "pool_hits": {
                    str(size): {
                        "relevant_hits": aggregate_pool_hits[size],
                        "recall_all_relevant": (
                            aggregate_pool_hits[size] / relevant_count
                            if relevant_count
                            else 1.0
                        ),
                        "recall_generated_relevant": (
                            aggregate_pool_hits[size] / generated_count
                            if generated_count
                            else 1.0
                        ),
                    }
                    for size in self.pool_sizes
                },
            },
            "cases": [
                case.to_dict()
                for case in self.cases
            ],
        }


class CoursePoolSensitivityService:
    def __init__(
        self,
        engine: CourseCandidateTuningEngine,
    ):
        self._engine = engine

    async def analyze_async(
        self,
        dataset: CourseCandidateDataset,
    ) -> CoursePoolSensitivityResult:
        tuning_cases = dataset.cases_for_split("tuning")
        holdout_cases = dataset.cases_for_split("holdout")
        if not tuning_cases:
            raise CourseCandidateEvaluationError(
                "COURSE pool sensitivity requires tuning cases"
            )
        if not holdout_cases:
            raise CourseCandidateEvaluationError(
                "COURSE pool sensitivity requires a frozen holdout boundary"
            )

        weights = dict(self._engine.baseline_config.weights)
        case_results: list[CoursePoolSensitivityCase] = []

        for case in tuning_cases:
            prepared = await self._engine.prepare_case_async(case)
            profile_statistics, _ = (
                await self._engine.rank_prepared_result_async(
                    prepared,
                    weights,
                )
            )
            fused = _pre_mmr_fused_ranking(
                profile_statistics,
                prepared.semantic.candidates,
                weights,
            )
            fused_rank = {
                item["canonical_text"]: item["rank"]
                for item in fused
            }
            semantic_by_id = {
                item.canonical_text: item
                for item in prepared.semantic.candidates
            }
            relevant = {
                text
                for text, grade in case.relevance.items()
                if grade > 0
            }
            generated = relevant.intersection(
                prepared.candidate_ids
            )
            reranked = {
                text
                for text in generated
                if semantic_by_id[text].reranked
            }
            pool_hits = {
                size: sum(
                    fused_rank[text] <= size
                    for text in generated
                )
                for size in POOL_SIZES
            }
            case_results.append(
                CoursePoolSensitivityCase(
                    case_id=case.case_id,
                    candidate_count=len(profile_statistics),
                    relevant_count=len(relevant),
                    generated_relevant_count=len(generated),
                    reranked_relevant_count=len(reranked),
                    pool_hits=pool_hits,
                )
            )

        return CoursePoolSensitivityResult(
            status=POOL_SENSITIVITY_STATUS,
            source_materialized_sha256=dataset.source_materialized_sha256,
            review_sha256=dataset.review_sha256,
            review_status=dataset.review_status,
            tuning_case_count=len(tuning_cases),
            frozen_holdout_case_count=len(holdout_cases),
            holdout_evaluated=False,
            pool_sizes=POOL_SIZES,
            active_weights=weights,
            cases=tuple(case_results),
        )
