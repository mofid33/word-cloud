from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

from src.core.services.analysis.profile_config import (
    ProfileScoringConfig,
    load_profile_scoring_config,
    weighted_signal_score,
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
from src.core.services.semantic.semantic_analysis_service import (
    SemanticAnalysisResult,
    SemanticAnalysisService,
)
from src.core.services.statistical.statistical_analysis_service import (
    StatisticalAnalysisService,
    StatisticalCandidateResult,
)
from src.infrastructure.utils.config_reader import ConfigReader
from tests.evaluation.phase10_gold_dataset import (
    Phase10GoldEvaluator,
    RankingMetrics,
)
from tests.evaluation.prepare_course_gold_annotation import (
    CourseAnnotationPackageError,
    load_verified_course_cases,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REVIEW_VERIFICATION = (
    PROJECT_ROOT
    / "tests"
    / "evaluation"
    / "gold"
    / "course_model_review_v1.json"
)

REVIEW_SCHEMA_VERSION = "phase10-course-model-simulated-human-review-v1"
REVIEW_STATUS = "MODEL_SIMULATED_HUMAN_REVIEW_NOT_ACTUAL_HUMAN_GOLD"
EVALUATION_STATUS = "COURSE_AI_REVIEW_TUNING_ENGINEERING_EVIDENCE_NOT_HUMAN_GOLD"
_REQUIRED_SIGNALS = (
    "semantic_relevance",
    "frequency",
    "chunk_coverage",
    "section_coverage",
    "phrase_quality",
)
_TUNABLE_SIGNALS = (
    "semantic_relevance",
    "frequency",
    "section_coverage",
    "phrase_quality",
)
_FIXED_SIGNAL = "chunk_coverage"


class CourseCandidateEvaluationError(ValueError):
    pass


@dataclass(frozen=True)
class CourseCandidateDocument:
    document_id: str
    text: str
    section_id: str

    def runtime_value(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "text": self.text,
            "metadata": {"section_id": self.section_id},
        }


@dataclass(frozen=True)
class CourseCandidateCase:
    case_id: str
    split: str
    domain: str
    documents: tuple[CourseCandidateDocument, ...]
    relevance: dict[str, int]


@dataclass(frozen=True)
class CourseCandidateDataset:
    source_materialized_sha256: str
    review_sha256: str
    review_status: str
    cases: tuple[CourseCandidateCase, ...]

    def cases_for_split(self, split: str) -> tuple[CourseCandidateCase, ...]:
        if split not in {"tuning", "holdout"}:
            raise ValueError("COURSE candidate split must be tuning or holdout")
        return tuple(case for case in self.cases if case.split == split)


@dataclass(frozen=True)
class PreparedCourseCandidateCase:
    case: CourseCandidateCase
    statistics: tuple[StatisticalCandidateResult, ...]
    semantic: SemanticAnalysisResult
    candidate_ids: frozenset[str]


@dataclass(frozen=True)
class CourseWeightEvaluation:
    weights: dict[str, float]
    metrics: RankingMetrics
    case_metrics: dict[str, RankingMetrics]
    candidate_label_coverage: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "weights": dict(self.weights),
            "metrics": _metrics_dict(self.metrics),
            "case_metrics": {
                case_id: _metrics_dict(metrics)
                for case_id, metrics in sorted(self.case_metrics.items())
            },
            "candidate_label_coverage": self.candidate_label_coverage,
        }


@dataclass(frozen=True)
class CourseTuningResult:
    status: str
    source_materialized_sha256: str
    review_sha256: str
    review_status: str
    tuning_case_count: int
    frozen_holdout_case_count: int
    holdout_evaluated: bool
    baseline: CourseWeightEvaluation
    selected: CourseWeightEvaluation
    evaluated_weight_set_count: int
    search_policy: dict[str, Any]
    model_versions: tuple[str, ...]
    scoring_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_materialized_sha256": self.source_materialized_sha256,
            "review_sha256": self.review_sha256,
            "review_status": self.review_status,
            "tuning_case_count": self.tuning_case_count,
            "frozen_holdout_case_count": self.frozen_holdout_case_count,
            "holdout_evaluated": self.holdout_evaluated,
            "baseline": self.baseline.to_dict(),
            "selected": self.selected.to_dict(),
            "evaluated_weight_set_count": self.evaluated_weight_set_count,
            "search_policy": self.search_policy,
            "model_versions": list(self.model_versions),
            "scoring_version": self.scoring_version,
            "improvement": {
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
        }


class CourseCandidateDatasetLoader:
    def __init__(
        self,
        project_root: Path,
        *,
        source_verification_path: Path | None = None,
        review_verification_path: Path = DEFAULT_REVIEW_VERIFICATION,
    ):
        self._project_root = project_root.resolve()
        self._source_verification_path = source_verification_path
        self._review_verification_path = review_verification_path

    def load(
        self,
        materialized_path: Path,
        review_path: Path,
    ) -> CourseCandidateDataset:
        materialized = materialized_path.expanduser().resolve()
        review = review_path.expanduser().resolve()
        self._require_external_file(materialized, "COURSE materialized corpus")
        self._require_external_file(review, "COURSE model-review candidate")

        try:
            if self._source_verification_path is None:
                source_sha, cases = load_verified_course_cases(materialized)
            else:
                source_sha, cases = load_verified_course_cases(
                    materialized,
                    verification_path=self._source_verification_path,
                )
        except CourseAnnotationPackageError as exc:
            raise CourseCandidateEvaluationError(str(exc)) from exc

        review_verification = self._load_review_verification()
        review_bytes = review.read_bytes()
        review_sha = hashlib.sha256(review_bytes).hexdigest()
        if review_sha != review_verification["review_file_sha256"]:
            raise CourseCandidateEvaluationError(
                "COURSE review SHA-256 does not match verified candidate"
            )
        payload = self._json_object(review_bytes, "COURSE review")
        if payload.get("schema_version") != REVIEW_SCHEMA_VERSION:
            raise CourseCandidateEvaluationError("Unsupported COURSE review schema")
        if payload.get("status") != REVIEW_STATUS:
            raise CourseCandidateEvaluationError(
                "COURSE review status is not the verified model-review status"
            )
        if payload.get("source_materialized_sha256") != source_sha:
            raise CourseCandidateEvaluationError(
                "COURSE review source fingerprint mismatch"
            )

        review_cases = payload.get("cases")
        if not isinstance(review_cases, list):
            raise CourseCandidateEvaluationError(
                "COURSE review cases must be an array"
            )
        if len(review_cases) != review_verification["case_count"]:
            raise CourseCandidateEvaluationError(
                "COURSE review case count mismatch"
            )

        source_by_id = {case["case_id"]: case for case in cases}
        parsed: list[CourseCandidateCase] = []
        seen_case_ids: set[str] = set()
        annotation_count = 0
        for item in review_cases:
            if not isinstance(item, dict):
                raise CourseCandidateEvaluationError(
                    "COURSE review case must be an object"
                )
            if set(item) != {"case_id", "split", "domain", "annotations"}:
                raise CourseCandidateEvaluationError(
                    "COURSE review case fields do not match contract"
                )
            case_id = item["case_id"]
            if not isinstance(case_id, str) or case_id not in source_by_id:
                raise CourseCandidateEvaluationError(
                    "COURSE review case_id does not match source corpus"
                )
            if case_id in seen_case_ids:
                raise CourseCandidateEvaluationError(
                    "COURSE review case_id values must be unique"
                )
            seen_case_ids.add(case_id)
            source_case = source_by_id[case_id]
            if (
                item["split"] != source_case["split"]
                or item["domain"] != source_case["domain"]
            ):
                raise CourseCandidateEvaluationError(
                    "COURSE review split/domain mismatch"
                )

            relevance = self._relevance(item["annotations"])
            annotation_count += len(relevance)
            parsed.append(
                CourseCandidateCase(
                    case_id=case_id,
                    split=item["split"],
                    domain=item["domain"],
                    documents=tuple(
                        CourseCandidateDocument(
                            document_id=document["document_id"],
                            text=document["text"],
                            section_id=document["document_id"],
                        )
                        for document in source_case["documents"]
                    ),
                    relevance=relevance,
                )
            )

        if set(source_by_id) != seen_case_ids:
            raise CourseCandidateEvaluationError(
                "COURSE review does not cover every verified source case"
            )
        if annotation_count != review_verification["final_annotation_count"]:
            raise CourseCandidateEvaluationError(
                "COURSE review annotation count mismatch"
            )
        if (
            sum(case.split == "tuning" for case in parsed)
            != review_verification["tuning_case_count"]
        ):
            raise CourseCandidateEvaluationError(
                "COURSE review tuning-case count mismatch"
            )
        if (
            sum(case.split == "holdout" for case in parsed)
            != review_verification["holdout_case_count"]
        ):
            raise CourseCandidateEvaluationError(
                "COURSE review holdout-case count mismatch"
            )

        return CourseCandidateDataset(
            source_materialized_sha256=source_sha,
            review_sha256=review_sha,
            review_status=payload["status"],
            cases=tuple(sorted(parsed, key=lambda case: case.case_id)),
        )

    def _load_review_verification(self) -> dict[str, Any]:
        payload = self._json_object(
            self._review_verification_path.read_bytes(),
            "COURSE review verification",
        )
        required = {
            "schema_version",
            "review_status",
            "source_materialized_sha256",
            "review_file_sha256",
            "case_count",
            "final_annotation_count",
            "tuning_case_count",
            "holdout_case_count",
            "note",
        }
        if set(payload) != required:
            raise CourseCandidateEvaluationError(
                "COURSE review verification fields do not match contract"
            )
        if (
            payload["schema_version"]
            != "phase10-course-model-review-verification-v1"
        ):
            raise CourseCandidateEvaluationError(
                "Unsupported COURSE review verification schema"
            )
        if payload["review_status"] != REVIEW_STATUS:
            raise CourseCandidateEvaluationError(
                "COURSE review verification status mismatch"
            )
        return payload

    def _require_external_file(self, path: Path, label: str) -> None:
        if not path.is_file():
            raise CourseCandidateEvaluationError(f"{label} does not exist")
        try:
            path.relative_to(self._project_root)
        except ValueError:
            return
        raise CourseCandidateEvaluationError(
            f"{label} must be stored outside the repository"
        )

    @staticmethod
    def _relevance(value: Any) -> dict[str, int]:
        if not isinstance(value, list) or not value:
            raise CourseCandidateEvaluationError(
                "COURSE review annotations must be a non-empty array"
            )
        relevance: dict[str, int] = {}
        for item in value:
            if not isinstance(item, dict):
                raise CourseCandidateEvaluationError(
                    "COURSE review annotation must be an object"
                )
            required = {
                "canonical_text",
                "grade",
                "evidence_section",
                "origin",
                "decision",
            }
            if set(item) != required:
                raise CourseCandidateEvaluationError(
                    "COURSE review annotation fields do not match contract"
                )
            text = item["canonical_text"]
            grade = item["grade"]
            if not isinstance(text, str) or not text.strip():
                raise CourseCandidateEvaluationError(
                    "COURSE review canonical_text must be non-empty"
                )
            text = text.strip()
            if text in relevance:
                raise CourseCandidateEvaluationError(
                    "COURSE review canonical_text values must be unique per case"
                )
            if (
                isinstance(grade, bool)
                or not isinstance(grade, int)
                or grade not in {1, 2, 3}
            ):
                raise CourseCandidateEvaluationError(
                    "COURSE review grade must be 1, 2, or 3"
                )
            relevance[text] = grade
        return relevance

    @staticmethod
    def _json_object(data: bytes, label: str) -> dict[str, Any]:
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CourseCandidateEvaluationError(
                f"{label} is not valid UTF-8 JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise CourseCandidateEvaluationError(
                f"{label} must be a JSON object"
            )
        return payload


class CourseCandidateTuningEngine:
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
        self._baseline = load_profile_scoring_config(
            config_reader,
            profile_key="course",
            required_signals=_REQUIRED_SIGNALS,
        )

    @property
    def baseline_config(self) -> ProfileScoringConfig:
        return self._baseline

    async def prepare_case_async(
        self,
        case: CourseCandidateCase,
    ) -> PreparedCourseCandidateCase:
        ordered = tuple(
            sorted(
                case.documents,
                key=lambda document: document.document_id,
            )
        )
        candidate_documents: list[CandidateDocument] = []
        embedding_texts: list[str] = []
        for document in ordered:
            processed = self._processor.process(
                document.text,
                domain="COURSE",
            )
            if processed.embedding_text:
                embedding_texts.append(processed.embedding_text)
            candidate_documents.append(
                CandidateDocument(
                    document_id=document.document_id,
                    processing_result=processed,
                    section_id=document.section_id,
                    chunk_id=None,
                )
            )

        occurrences = self._extractor.extract_documents(
            tuple(candidate_documents)
        )
        document_ids = tuple(
            document.document_id
            for document in ordered
        )
        section_keys = tuple(
            (document.document_id, document.section_id)
            for document in ordered
        )
        statistics = self._statistical.analyze(
            occurrences,
            document_ids=document_ids,
            section_keys=section_keys,
            chunk_keys=(),
        )
        context = " ".join(embedding_texts)
        semantic = await self._semantic.analyze_async(
            context,
            statistics,
        )
        return PreparedCourseCandidateCase(
            case=case,
            statistics=statistics,
            semantic=semantic,
            candidate_ids=frozenset(
                item.canonical_text
                for item in statistics
            ),
        )

    async def rank_prepared_async(
        self,
        prepared: PreparedCourseCandidateCase,
        weights: dict[str, float],
    ) -> tuple[str, ...]:
        _validate_weights(weights)
        profile_statistics = tuple(
            replace(
                item,
                statistical_score=weighted_signal_score(
                    {
                        "frequency": item.normalized_frequency,
                        "chunk_coverage": None,
                        "section_coverage": item.section_coverage,
                        "phrase_quality": item.phrase_quality,
                    },
                    weights,
                )[0],
            )
            for item in prepared.statistics
        )
        active_statistical_weight = (
            weights["frequency"]
            + weights["section_coverage"]
            + weights["phrase_quality"]
        )
        fusion_total = (
            active_statistical_weight
            + weights["semantic_relevance"]
        )
        if fusion_total <= 0.0:
            raise CourseCandidateEvaluationError(
                "COURSE tuning has no active scoring weight"
            )
        hybrid = await self._ranking.rank_async(
            profile_statistics,
            prepared.semantic,
            weights=FusionWeights(
                statistical=active_statistical_weight / fusion_total,
                semantic=weights["semantic_relevance"] / fusion_total,
            ),
            maximum_results=self._baseline.maximum_results,
        )
        return tuple(
            item.canonical_text
            for item in hybrid.candidates
        )

    def model_version(
        self,
        prepared_cases: Iterable[PreparedCourseCandidateCase],
    ) -> tuple[str, ...]:
        versions: set[str] = set()
        for prepared in prepared_cases:
            embedding = prepared.semantic.embedding_metadata
            reranker = prepared.semantic.reranker_metadata
            versions.add(
                f"embedding:{embedding.model_identifier}@"
                f"{embedding.model_revision or 'default'};"
                f"reranker:{reranker.model_identifier}@"
                f"{reranker.model_revision or 'default'}"
            )
        return tuple(sorted(versions))


class CourseCandidateWeightTuner:
    def __init__(self, engine: CourseCandidateTuningEngine):
        self._engine = engine

    async def tune_async(
        self,
        dataset: CourseCandidateDataset,
    ) -> CourseTuningResult:
        tuning_cases = dataset.cases_for_split("tuning")
        holdout_cases = dataset.cases_for_split("holdout")
        if not tuning_cases:
            raise CourseCandidateEvaluationError(
                "COURSE tuning split is empty"
            )
        if not holdout_cases:
            raise CourseCandidateEvaluationError(
                "COURSE frozen holdout split is empty"
            )

        prepared = tuple(
            [
                await self._engine.prepare_case_async(case)
                for case in tuning_cases
            ]
        )
        baseline_weights = dict(
            self._engine.baseline_config.weights
        )
        baseline = await self._evaluate_weights_async(
            prepared,
            baseline_weights,
        )

        evaluated: dict[
            tuple[tuple[str, float], ...],
            CourseWeightEvaluation,
        ] = {
            _weight_signature(baseline_weights): baseline
        }
        for weights in _transfer_candidates(
            baseline_weights,
            deltas=(0.05, 0.10),
        ):
            signature = _weight_signature(weights)
            if signature not in evaluated:
                evaluated[signature] = (
                    await self._evaluate_weights_async(
                        prepared,
                        weights,
                    )
                )

        first_best = _select_best(
            tuple(evaluated.values()),
            baseline_weights,
        )
        for weights in _transfer_candidates(
            first_best.weights,
            deltas=(0.025,),
        ):
            signature = _weight_signature(weights)
            if signature not in evaluated:
                evaluated[signature] = (
                    await self._evaluate_weights_async(
                        prepared,
                        weights,
                    )
                )

        selected = _select_best(
            tuple(evaluated.values()),
            baseline_weights,
        )
        return CourseTuningResult(
            status=EVALUATION_STATUS,
            source_materialized_sha256=(
                dataset.source_materialized_sha256
            ),
            review_sha256=dataset.review_sha256,
            review_status=dataset.review_status,
            tuning_case_count=len(tuning_cases),
            frozen_holdout_case_count=len(holdout_cases),
            holdout_evaluated=False,
            baseline=baseline,
            selected=selected,
            evaluated_weight_set_count=len(evaluated),
            search_policy={
                "objective_order": [
                    "ndcg_at_10",
                    "recall_at_10",
                    "precision_at_5",
                    "precision_at_10",
                    "minimum_l1_distance_from_baseline",
                    "deterministic_weight_signature",
                ],
                "first_pass_transfer_deltas": [0.05, 0.10],
                "refinement_transfer_delta": 0.025,
                "tunable_signals": list(_TUNABLE_SIGNALS),
                "fixed_signal": _FIXED_SIGNAL,
                "fixed_signal_weight": (
                    baseline_weights[_FIXED_SIGNAL]
                ),
                "holdout_policy": (
                    "holdout is loaded for split-integrity "
                    "verification only and is never prepared or "
                    "ranked by this tuner"
                ),
            },
            model_versions=self._engine.model_version(
                prepared
            ),
            scoring_version=(
                "phase10-course-ai-review-tuning-v1"
            ),
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
            metrics = (
                Phase10GoldEvaluator.ranking_metrics(
                    ranked,
                    prepared.case.relevance,
                )
            )
            case_metrics[
                prepared.case.case_id
            ] = metrics
            relevant = {
                text
                for text, grade
                in prepared.case.relevance.items()
                if grade > 0
            }
            coverage_values.append(
                (
                    len(
                        relevant.intersection(
                            prepared.candidate_ids
                        )
                    )
                    / len(relevant)
                )
                if relevant
                else 1.0
            )

        return CourseWeightEvaluation(
            weights={
                name: float(weights[name])
                for name in _REQUIRED_SIGNALS
            },
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
            candidate_label_coverage=_mean(
                coverage_values
            ),
        )


def _validate_weights(
    weights: dict[str, float],
) -> None:
    if set(weights) != set(_REQUIRED_SIGNALS):
        raise CourseCandidateEvaluationError(
            "COURSE tuning weights do not match required signals"
        )
    for name, value in weights.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
        ):
            raise CourseCandidateEvaluationError(
                f"COURSE tuning weight '{name}' must be numeric"
            )
        numeric = float(value)
        if (
            not math.isfinite(numeric)
            or numeric < 0.0
            or numeric > 1.0
        ):
            raise CourseCandidateEvaluationError(
                f"COURSE tuning weight '{name}' must be within [0, 1]"
            )
    if not math.isclose(
        sum(float(value) for value in weights.values()),
        1.0,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise CourseCandidateEvaluationError(
            "COURSE tuning weights must sum to 1.0"
        )


def _transfer_candidates(
    center: dict[str, float],
    *,
    deltas: tuple[float, ...],
) -> tuple[dict[str, float], ...]:
    _validate_weights(center)
    fixed_weight = float(center[_FIXED_SIGNAL])
    candidates: dict[
        tuple[tuple[str, float], ...],
        dict[str, float],
    ] = {}
    for delta in deltas:
        if (
            not math.isfinite(delta)
            or delta <= 0.0
        ):
            raise CourseCandidateEvaluationError(
                "COURSE tuning transfer delta must be finite and > 0"
            )
        for donor in _TUNABLE_SIGNALS:
            for receiver in _TUNABLE_SIGNALS:
                if donor == receiver:
                    continue
                if (
                    center[donor] + 1e-12 < delta
                    or center[receiver] + delta
                    > 1.0 + 1e-12
                ):
                    continue
                weights = dict(center)
                weights[donor] = round(
                    weights[donor] - delta,
                    12,
                )
                weights[receiver] = round(
                    weights[receiver] + delta,
                    12,
                )
                weights[_FIXED_SIGNAL] = (
                    fixed_weight
                )
                _validate_weights(weights)
                candidates[
                    _weight_signature(weights)
                ] = weights
    return tuple(
        candidates[key]
        for key in sorted(candidates)
    )


def _select_best(
    evaluations: tuple[
        CourseWeightEvaluation,
        ...,
    ],
    baseline_weights: dict[str, float],
) -> CourseWeightEvaluation:
    if not evaluations:
        raise CourseCandidateEvaluationError(
            "COURSE tuning produced no weight evaluations"
        )

    def key(
        item: CourseWeightEvaluation,
    ) -> tuple[Any, ...]:
        distance = sum(
            abs(
                item.weights[name]
                - baseline_weights[name]
            )
            for name in _REQUIRED_SIGNALS
        )
        signature = tuple(
            item.weights[name]
            for name in _REQUIRED_SIGNALS
        )
        return (
            -item.metrics.ndcg_at_10,
            -item.metrics.recall_at_10,
            -item.metrics.precision_at_5,
            -item.metrics.precision_at_10,
            distance,
            signature,
        )

    return sorted(
        evaluations,
        key=key,
    )[0]


def _weight_signature(
    weights: dict[str, float],
) -> tuple[tuple[str, float], ...]:
    return tuple(
        (
            name,
            round(float(weights[name]), 12),
        )
        for name in _REQUIRED_SIGNALS
    )


def _metrics_dict(
    metrics: RankingMetrics,
) -> dict[str, float]:
    return {
        "precision_at_5": metrics.precision_at_5,
        "precision_at_10": metrics.precision_at_10,
        "recall_at_10": metrics.recall_at_10,
        "ndcg_at_10": metrics.ndcg_at_10,
    }


def _mean(
    values: Iterable[float],
) -> float:
    items = tuple(
        float(value)
        for value in values
    )
    if not items:
        raise CourseCandidateEvaluationError(
            "Cannot average an empty COURSE tuning metric sequence"
        )
    return sum(items) / len(items)
