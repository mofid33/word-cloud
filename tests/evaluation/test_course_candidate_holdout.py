from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.evaluation.course_candidate_evaluation import (
    CourseCandidateCase,
    CourseCandidateDataset,
    CourseCandidateDocument,
    CourseCandidateEvaluationError,
    PreparedCourseCandidateCase,
    REVIEW_STATUS,
)
from tests.evaluation.course_candidate_holdout import (
    CourseCandidateHoldoutEvaluator,
    FrozenCourseTuningEvidence,
    HOLDOUT_EVALUATION_STATUS,
    TUNING_EVIDENCE_SCHEMA_VERSION,
    TUNING_EVIDENCE_STATUS,
    load_frozen_course_tuning_evidence,
)


_BASELINE = {
    "semantic_relevance": 0.35,
    "frequency": 0.20,
    "chunk_coverage": 0.15,
    "section_coverage": 0.15,
    "phrase_quality": 0.15,
}
_SELECTED = {
    "semantic_relevance": 0.375,
    "frequency": 0.15,
    "chunk_coverage": 0.15,
    "section_coverage": 0.175,
    "phrase_quality": 0.15,
}


def _frozen_evidence() -> FrozenCourseTuningEvidence:
    return FrozenCourseTuningEvidence(
        evidence_sha256="e" * 64,
        source_materialized_sha256="a" * 64,
        review_sha256="b" * 64,
        review_status=REVIEW_STATUS,
        tuning_case_count=1,
        frozen_holdout_case_count=1,
        baseline_weights=dict(_BASELINE),
        selected_weights=dict(_SELECTED),
        tuning_model_versions=("tuning-model",),
        scoring_version="phase10-course-ai-review-tuning-v1",
    )


def _dataset() -> CourseCandidateDataset:
    return CourseCandidateDataset(
        source_materialized_sha256="a" * 64,
        review_sha256="b" * 64,
        review_status=REVIEW_STATUS,
        cases=(
            CourseCandidateCase(
                case_id="tuning-case",
                split="tuning",
                domain="test",
                documents=(
                    CourseCandidateDocument(
                        document_id="tuning-doc",
                        text="هوش مصنوعی",
                        section_id="tuning-doc",
                    ),
                ),
                relevance={"هوش مصنوعی": 3},
            ),
            CourseCandidateCase(
                case_id="holdout-case",
                split="holdout",
                domain="test",
                documents=(
                    CourseCandidateDocument(
                        document_id="holdout-doc",
                        text="پردازش زبان فارسی",
                        section_id="holdout-doc",
                    ),
                ),
                relevance={
                    "پردازش زبان": 3,
                    "زبان فارسی": 2,
                },
            ),
        ),
    )


class _FakeHoldoutEngine:
    def __init__(self):
        self.prepared_case_ids: list[str] = []
        self.ranked_weights: list[dict[str, float]] = []

    async def prepare_case_async(self, case):
        self.prepared_case_ids.append(case.case_id)
        return PreparedCourseCandidateCase(
            case=case,
            statistics=(),
            semantic=SimpleNamespace(),
            candidate_ids=frozenset(case.relevance),
        )

    async def rank_prepared_async(self, prepared, weights):
        self.ranked_weights.append(dict(weights))
        return tuple(prepared.case.relevance)

    def model_version(self, prepared_cases):
        return ("holdout-test-model",)


class FrozenCourseTuningEvidenceTests(unittest.TestCase):
    def test_loader_requires_pre_holdout_frozen_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "evidence.json"
            payload = {
                "schema_version": TUNING_EVIDENCE_SCHEMA_VERSION,
                "status": TUNING_EVIDENCE_STATUS,
                "source_materialized_sha256": "a" * 64,
                "review_sha256": "b" * 64,
                "review_status": REVIEW_STATUS,
                "tuning_case_count": 7,
                "frozen_holdout_case_count": 4,
                "holdout_evaluated": False,
                "evaluated_weight_set_count": 37,
                "candidate_label_coverage": 0.91,
                "baseline": {
                    "weights": _BASELINE,
                    "metrics": {
                        "precision_at_5": 0.1,
                        "precision_at_10": 0.1,
                        "recall_at_10": 0.1,
                        "ndcg_at_10": 0.1,
                    },
                },
                "selected": {
                    "weights": _SELECTED,
                    "metrics": {
                        "precision_at_5": 0.1,
                        "precision_at_10": 0.12,
                        "recall_at_10": 0.11,
                        "ndcg_at_10": 0.2,
                    },
                },
                "improvement": {
                    "precision_at_5": 0.0,
                    "precision_at_10": 0.02,
                    "recall_at_10": 0.01,
                    "ndcg_at_10": 0.1,
                },
                "model_versions": ["model"],
                "scoring_version": "score",
                "selection_policy": {
                    "production_config_updated": False,
                },
                "verified_on": "2026-09-29",
                "note": "test",
            }
            raw = (
                json.dumps(payload, ensure_ascii=False)
                + "\n"
            ).encode("utf-8")
            path.write_bytes(raw)

            evidence = load_frozen_course_tuning_evidence(path)

            self.assertEqual(
                evidence.evidence_sha256,
                hashlib.sha256(raw).hexdigest(),
            )
            self.assertEqual(
                evidence.selected_weights,
                _SELECTED,
            )

    def test_loader_rejects_evidence_that_already_used_holdout(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "evidence.json"
            payload = {
                "schema_version": TUNING_EVIDENCE_SCHEMA_VERSION,
                "status": TUNING_EVIDENCE_STATUS,
                "source_materialized_sha256": "a" * 64,
                "review_sha256": "b" * 64,
                "review_status": REVIEW_STATUS,
                "tuning_case_count": 7,
                "frozen_holdout_case_count": 4,
                "holdout_evaluated": True,
                "evaluated_weight_set_count": 37,
                "candidate_label_coverage": 0.91,
                "baseline": {
                    "weights": _BASELINE,
                    "metrics": {},
                },
                "selected": {
                    "weights": _SELECTED,
                    "metrics": {},
                },
                "improvement": {},
                "model_versions": ["model"],
                "scoring_version": "score",
                "selection_policy": {
                    "production_config_updated": False,
                },
                "verified_on": "2026-09-29",
                "note": "test",
            }
            path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                CourseCandidateEvaluationError,
                "before holdout",
            ):
                load_frozen_course_tuning_evidence(path)


class CourseCandidateHoldoutEvaluatorTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_holdout_evaluator_never_prepares_tuning_or_searches_weights(self):
        engine = _FakeHoldoutEngine()
        result = await CourseCandidateHoldoutEvaluator(
            engine
        ).evaluate_async(
            _dataset(),
            _frozen_evidence(),
        )

        self.assertEqual(
            result.status,
            HOLDOUT_EVALUATION_STATUS,
        )
        self.assertEqual(
            engine.prepared_case_ids,
            ["holdout-case"],
        )
        self.assertEqual(
            engine.ranked_weights,
            [_BASELINE, _SELECTED],
        )
        self.assertTrue(
            result.weights_frozen_before_holdout
        )
        self.assertFalse(
            result.weight_search_performed
        )
        self.assertEqual(
            result.holdout_case_count,
            1,
        )

    async def test_holdout_evaluator_rejects_fingerprint_drift(self):
        dataset = _dataset()
        drifted = CourseCandidateDataset(
            source_materialized_sha256="c" * 64,
            review_sha256=dataset.review_sha256,
            review_status=dataset.review_status,
            cases=dataset.cases,
        )
        with self.assertRaisesRegex(
            CourseCandidateEvaluationError,
            "source fingerprint",
        ):
            await CourseCandidateHoldoutEvaluator(
                _FakeHoldoutEngine()
            ).evaluate_async(
                drifted,
                _frozen_evidence(),
            )


if __name__ == "__main__":
    unittest.main()
