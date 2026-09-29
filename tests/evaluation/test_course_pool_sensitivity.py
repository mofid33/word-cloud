from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.core.services.analysis.profile_config import ProfileScoringConfig
from tests.evaluation.course_candidate_evaluation import (
    CourseCandidateCase,
    CourseCandidateDataset,
    CourseCandidateDocument,
    REVIEW_STATUS,
)
from tests.evaluation.course_pool_sensitivity import (
    CoursePoolSensitivityService,
    POOL_SENSITIVITY_STATUS,
)


_BASELINE = {
    "semantic_relevance": 0.35,
    "frequency": 0.20,
    "chunk_coverage": 0.15,
    "section_coverage": 0.15,
    "phrase_quality": 0.15,
}


class _FakeEngine:
    def __init__(self):
        self.prepared_case_ids: list[str] = []
        self._baseline = ProfileScoringConfig(
            scoring_version="test",
            maximum_results=25,
            diversity_candidate_pool_size=200,
            weights=dict(_BASELINE),
        )

    @property
    def baseline_config(self):
        return self._baseline

    async def prepare_case_async(self, case):
        self.prepared_case_ids.append(case.case_id)
        if case.split != "tuning":
            raise AssertionError("holdout must never be prepared")

        stats = tuple(
            SimpleNamespace(
                canonical_text=f"p{i}",
                statistical_score=float(500 - i),
            )
            for i in range(1, 501)
        )
        semantic = SimpleNamespace(
            candidates=tuple(
                SimpleNamespace(
                    canonical_text=f"p{i}",
                    semantic_score=float(500 - i),
                    reranked=(i <= 25),
                )
                for i in range(1, 501)
            )
        )
        return SimpleNamespace(
            case=case,
            statistics=stats,
            semantic=semantic,
            candidate_ids=frozenset(
                item.canonical_text for item in stats
            ),
        )

    async def rank_prepared_result_async(self, prepared, weights):
        # Pool sensitivity needs profile-scored statistical candidates.
        return prepared.statistics, SimpleNamespace()


class CoursePoolSensitivityTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_pool_sensitivity_uses_tuning_only_and_reports_monotonic_recall(self):
        tuning = CourseCandidateCase(
            case_id="tuning-case",
            split="tuning",
            domain="test",
            documents=(
                CourseCandidateDocument(
                    "doc-t",
                    "متن",
                    "doc-t",
                ),
            ),
            relevance={
                "p10": 3,
                "p60": 2,
                "p150": 2,
                "p350": 1,
                "missing": 1,
            },
        )
        holdout = CourseCandidateCase(
            case_id="holdout-case",
            split="holdout",
            domain="test",
            documents=(
                CourseCandidateDocument(
                    "doc-h",
                    "نباید استفاده شود",
                    "doc-h",
                ),
            ),
            relevance={"p1": 3},
        )
        dataset = CourseCandidateDataset(
            source_materialized_sha256="a" * 64,
            review_sha256="b" * 64,
            review_status=REVIEW_STATUS,
            cases=(tuning, holdout),
        )

        engine = _FakeEngine()
        result = await CoursePoolSensitivityService(
            engine
        ).analyze_async(dataset)
        payload = result.to_dict()

        self.assertEqual(
            result.status,
            POOL_SENSITIVITY_STATUS,
        )
        self.assertEqual(
            engine.prepared_case_ids,
            ["tuning-case"],
        )
        self.assertFalse(result.holdout_evaluated)
        self.assertEqual(result.frozen_holdout_case_count, 1)

        hits = payload["aggregate"]["pool_hits"]
        self.assertEqual(hits["25"]["relevant_hits"], 1)
        self.assertEqual(hits["50"]["relevant_hits"], 1)
        self.assertEqual(hits["100"]["relevant_hits"], 2)
        self.assertEqual(hits["200"]["relevant_hits"], 3)
        self.assertEqual(hits["400"]["relevant_hits"], 4)
        self.assertEqual(
            payload["aggregate"]["generated_relevant_count"],
            4,
        )
        self.assertEqual(
            payload["aggregate"]["reranked_relevant_count"],
            1,
        )

        values = [
            hits[str(size)]["recall_all_relevant"]
            for size in (25, 50, 100, 200, 400)
        ]
        self.assertEqual(values, sorted(values))


if __name__ == "__main__":
    unittest.main()
