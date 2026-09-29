from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from tests.evaluation.course_candidate_evaluation import (
    CourseCandidateDataset,
    CourseCandidateEvaluationError,
    CourseCandidateTuningEngine,
    CourseWeightEvaluation,
    PreparedCourseCandidateCase,
    PROJECT_ROOT,
    REVIEW_STATUS,
)
from tests.evaluation.phase10_gold_dataset import (
    Phase10GoldEvaluator,
    RankingMetrics,
)


DEFAULT_TUNING_EVIDENCE = (
    PROJECT_ROOT
    / "tests"
    / "evaluation"
    / "gold"
    / "course_ai_review_tuning_v1.json"
)
TUNING_EVIDENCE_SCHEMA_VERSION = (
    "phase10-course-ai-review-tuning-evidence-v1"
)
TUNING_EVIDENCE_STATUS = (
    "COURSE_AI_REVIEW_TUNING_ENGINEERING_EVIDENCE_NOT_HUMAN_GOLD"
)
HOLDOUT_EVALUATION_STATUS = (
    "COURSE_AI_REVIEW_HOLDOUT_ENGINEERING_EVIDENCE_NOT_HUMAN_GOLD"
)
_REQUIRED_SIGNALS = (
    "semantic_relevance",
    "frequency",
    "chunk_coverage",
    "section_coverage",
    "phrase_quality",
)


@dataclass(frozen=True)
class FrozenCourseTuningEvidence:
    evidence_sha256: str
    source_materialized_sha256: str
    review_sha256: str
    review_status: str
    tuning_case_count: int
    frozen_holdout_case_count: int
    baseline_weights: dict[str, float]
    selected_weights: dict[str, float]
    tuning_model_versions: tuple[str, ...]
    scoring_version: str


@dataclass(frozen=True)
class CourseHoldoutEvaluationResult:
    status: str
    tuning_evidence_sha256: str
    source_materialized_sha256: str
    review_sha256: str
    review_status: str
    tuning_case_count: int
    holdout_case_count: int
    weights_frozen_before_holdout: bool
    weight_search_performed: bool
    baseline: CourseWeightEvaluation
    selected: CourseWeightEvaluation
    model_versions: tuple[str, ...]
    scoring_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "tuning_evidence_sha256": self.tuning_evidence_sha256,
            "source_materialized_sha256": self.source_materialized_sha256,
            "review_sha256": self.review_sha256,
            "review_status": self.review_status,
            "tuning_case_count": self.tuning_case_count,
            "holdout_case_count": self.holdout_case_count,
            "weights_frozen_before_holdout": self.weights_frozen_before_holdout,
            "weight_search_performed": self.weight_search_performed,
            "baseline": self.baseline.to_dict(),
            "selected": self.selected.to_dict(),
            "generalization_delta": {
                "precision_at_5": (
                    self.selected.metrics.precision_at_5
                    - self.baseline.metrics.precision_at_5
                ),
                "precision_at_10": (
                    self.selected.metrics.precision_at_10
                    - self.baseline.metrics.precision_at_10
                ),
                "recall_at_10": (
                    self.selected.metrics.recall_at_10
                    - self.baseline.metrics.recall_at_10
                ),
                "ndcg_at_10": (
                    self.selected.metrics.ndcg_at_10
                    - self.baseline.metrics.ndcg_at_10
                ),
            },
            "model_versions": list(self.model_versions),
            "scoring_version": self.scoring_version,
        }


def load_frozen_course_tuning_evidence(
    path: Path = DEFAULT_TUNING_EVIDENCE,
) -> FrozenCourseTuningEvidence:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CourseCandidateEvaluationError(
            "COURSE frozen tuning evidence is missing"
        ) from exc

    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CourseCandidateEvaluationError(
            "COURSE frozen tuning evidence is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise CourseCandidateEvaluationError(
            "COURSE frozen tuning evidence must be a JSON object"
        )

    required = {
        "schema_version",
        "status",
        "source_materialized_sha256",
        "review_sha256",
        "review_status",
        "tuning_case_count",
        "frozen_holdout_case_count",
        "holdout_evaluated",
        "evaluated_weight_set_count",
        "candidate_label_coverage",
        "baseline",
        "selected",
        "improvement",
        "model_versions",
        "scoring_version",
        "selection_policy",
        "verified_on",
        "note",
    }
    if set(payload) != required:
        raise CourseCandidateEvaluationError(
            "COURSE frozen tuning evidence fields do not match contract"
        )
    if payload["schema_version"] != TUNING_EVIDENCE_SCHEMA_VERSION:
        raise CourseCandidateEvaluationError(
            "Unsupported COURSE frozen tuning evidence schema"
        )
    if payload["status"] != TUNING_EVIDENCE_STATUS:
        raise CourseCandidateEvaluationError(
            "COURSE frozen tuning evidence status mismatch"
        )
    if payload["review_status"] != REVIEW_STATUS:
        raise CourseCandidateEvaluationError(
            "COURSE frozen tuning review status mismatch"
        )
    if payload["holdout_evaluated"] is not False:
        raise CourseCandidateEvaluationError(
            "COURSE tuning evidence must be frozen before holdout evaluation"
        )
    selection_policy = payload["selection_policy"]
    if not isinstance(selection_policy, dict):
        raise CourseCandidateEvaluationError(
            "COURSE tuning selection_policy must be an object"
        )
    if selection_policy.get("production_config_updated") is not False:
        raise CourseCandidateEvaluationError(
            "COURSE production config must remain unchanged before holdout"
        )

    tuning_case_count = _positive_int(
        payload["tuning_case_count"],
        "tuning_case_count",
    )
    holdout_case_count = _positive_int(
        payload["frozen_holdout_case_count"],
        "frozen_holdout_case_count",
    )
    baseline_weights = _weights_from_result(
        payload["baseline"],
        "baseline",
    )
    selected_weights = _weights_from_result(
        payload["selected"],
        "selected",
    )
    model_versions = payload["model_versions"]
    if (
        not isinstance(model_versions, list)
        or not model_versions
        or any(
            not isinstance(item, str) or not item.strip()
            for item in model_versions
        )
    ):
        raise CourseCandidateEvaluationError(
            "COURSE tuning model_versions must be non-empty strings"
        )
    scoring_version = payload["scoring_version"]
    if not isinstance(scoring_version, str) or not scoring_version.strip():
        raise CourseCandidateEvaluationError(
            "COURSE tuning scoring_version must be non-empty"
        )

    return FrozenCourseTuningEvidence(
        evidence_sha256=hashlib.sha256(data).hexdigest(),
        source_materialized_sha256=_sha256_text(
            payload["source_materialized_sha256"],
            "source_materialized_sha256",
        ),
        review_sha256=_sha256_text(
            payload["review_sha256"],
            "review_sha256",
        ),
        review_status=payload["review_status"],
        tuning_case_count=tuning_case_count,
        frozen_holdout_case_count=holdout_case_count,
        baseline_weights=baseline_weights,
        selected_weights=selected_weights,
        tuning_model_versions=tuple(sorted(model_versions)),
        scoring_version=scoring_version.strip(),
    )


class CourseCandidateHoldoutEvaluator:
    def __init__(
        self,
        engine: CourseCandidateTuningEngine,
    ):
        self._engine = engine

    async def evaluate_async(
        self,
        dataset: CourseCandidateDataset,
        evidence: FrozenCourseTuningEvidence,
    ) -> CourseHoldoutEvaluationResult:
        self._validate_dataset(dataset, evidence)
        holdout_cases = dataset.cases_for_split("holdout")
        if not holdout_cases:
            raise CourseCandidateEvaluationError(
                "COURSE holdout split is empty"
            )

        prepared = tuple(
            [
                await self._engine.prepare_case_async(case)
                for case in holdout_cases
            ]
        )
        baseline = await self._evaluate_weights_async(
            prepared,
            evidence.baseline_weights,
        )
        selected = await self._evaluate_weights_async(
            prepared,
            evidence.selected_weights,
        )
        return CourseHoldoutEvaluationResult(
            status=HOLDOUT_EVALUATION_STATUS,
            tuning_evidence_sha256=evidence.evidence_sha256,
            source_materialized_sha256=dataset.source_materialized_sha256,
            review_sha256=dataset.review_sha256,
            review_status=dataset.review_status,
            tuning_case_count=evidence.tuning_case_count,
            holdout_case_count=len(holdout_cases),
            weights_frozen_before_holdout=True,
            weight_search_performed=False,
            baseline=baseline,
            selected=selected,
            model_versions=self._engine.model_version(prepared),
            scoring_version=(
                "phase10-course-ai-review-holdout-v1"
            ),
        )

    @staticmethod
    def _validate_dataset(
        dataset: CourseCandidateDataset,
        evidence: FrozenCourseTuningEvidence,
    ) -> None:
        if (
            dataset.source_materialized_sha256
            != evidence.source_materialized_sha256
        ):
            raise CourseCandidateEvaluationError(
                "COURSE holdout source fingerprint does not match frozen tuning evidence"
            )
        if dataset.review_sha256 != evidence.review_sha256:
            raise CourseCandidateEvaluationError(
                "COURSE holdout review fingerprint does not match frozen tuning evidence"
            )
        if dataset.review_status != evidence.review_status:
            raise CourseCandidateEvaluationError(
                "COURSE holdout review status does not match frozen tuning evidence"
            )
        if (
            len(dataset.cases_for_split("tuning"))
            != evidence.tuning_case_count
        ):
            raise CourseCandidateEvaluationError(
                "COURSE tuning-case count changed after weight freeze"
            )
        if (
            len(dataset.cases_for_split("holdout"))
            != evidence.frozen_holdout_case_count
        ):
            raise CourseCandidateEvaluationError(
                "COURSE holdout-case count changed after weight freeze"
            )

    async def _evaluate_weights_async(
        self,
        prepared_cases: tuple[
            PreparedCourseCandidateCase,
            ...,
        ],
        weights: dict[str, float],
    ) -> CourseWeightEvaluation:
        case_metrics: dict[str, RankingMetrics] = {}
        coverage_values: list[float] = []
        for prepared in prepared_cases:
            ranked = list(
                await self._engine.rank_prepared_async(
                    prepared,
                    weights,
                )
            )
            metrics = Phase10GoldEvaluator.ranking_metrics(
                ranked,
                prepared.case.relevance,
            )
            case_metrics[prepared.case.case_id] = metrics
            relevant = {
                text
                for text, grade in prepared.case.relevance.items()
                if grade > 0
            }
            coverage_values.append(
                (
                    len(relevant.intersection(prepared.candidate_ids))
                    / len(relevant)
                )
                if relevant
                else 1.0
            )

        return CourseWeightEvaluation(
            weights=dict(weights),
            metrics=RankingMetrics(
                precision_at_5=_mean(
                    item.precision_at_5
                    for item in case_metrics.values()
                ),
                precision_at_10=_mean(
                    item.precision_at_10
                    for item in case_metrics.values()
                ),
                recall_at_10=_mean(
                    item.recall_at_10
                    for item in case_metrics.values()
                ),
                ndcg_at_10=_mean(
                    item.ndcg_at_10
                    for item in case_metrics.values()
                ),
            ),
            case_metrics=case_metrics,
            candidate_label_coverage=_mean(coverage_values),
        )


def _weights_from_result(
    value: Any,
    label: str,
) -> dict[str, float]:
    if not isinstance(value, dict):
        raise CourseCandidateEvaluationError(
            f"COURSE tuning {label} must be an object"
        )
    if set(value) != {"weights", "metrics"}:
        raise CourseCandidateEvaluationError(
            f"COURSE tuning {label} fields do not match contract"
        )
    weights = value["weights"]
    if not isinstance(weights, dict) or set(weights) != set(_REQUIRED_SIGNALS):
        raise CourseCandidateEvaluationError(
            f"COURSE tuning {label}.weights do not match required signals"
        )
    normalized: dict[str, float] = {}
    for name in _REQUIRED_SIGNALS:
        raw = weights[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise CourseCandidateEvaluationError(
                f"COURSE tuning weight '{name}' must be numeric"
            )
        numeric = float(raw)
        if not math.isfinite(numeric) or numeric < 0.0 or numeric > 1.0:
            raise CourseCandidateEvaluationError(
                f"COURSE tuning weight '{name}' must be within [0, 1]"
            )
        normalized[name] = numeric
    if not math.isclose(
        sum(normalized.values()),
        1.0,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise CourseCandidateEvaluationError(
            "COURSE frozen tuning weights must sum to 1.0"
        )
    metrics = value["metrics"]
    if not isinstance(metrics, dict):
        raise CourseCandidateEvaluationError(
            f"COURSE tuning {label}.metrics must be an object"
        )
    return normalized


def _positive_int(
    value: Any,
    name: str,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CourseCandidateEvaluationError(
            f"COURSE tuning {name} must be an integer > 0"
        )
    return value


def _sha256_text(
    value: Any,
    name: str,
) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CourseCandidateEvaluationError(
            f"COURSE tuning {name} must be a lowercase SHA-256 hex digest"
        )
    return value


def _mean(values: Iterable[float]) -> float:
    items = tuple(float(value) for value in values)
    if not items:
        raise CourseCandidateEvaluationError(
            "Cannot average an empty COURSE holdout metric sequence"
        )
    return sum(items) / len(items)
