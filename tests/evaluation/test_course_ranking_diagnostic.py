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
from tests.evaluation.course_ranking_diagnostic import (
    CourseRankingDiagnosticService,
    DIAGNOSTIC_STATUS,
    _pre_mmr_fused_ranking,
)


_BASELINE_WEIGHTS = {
    "semantic_relevance": 0.35,
    "frequency": 0.20,
    "chunk_coverage": 0.15,
    "section_coverage": 0.15,
    "phrase_quality": 0.15,
}


def _stat(
    canonical_text: str,
    statistical_score: float,
    *,
    frequency: int = 1,
    normalized_frequency: float = 1.0,
    section_coverage: float = 1.0,
    phrase_quality: float = 1.0,
):
    return SimpleNamespace(
        canonical_text=canonical_text,
        statistical_score=statistical_score,
        frequency=frequency,
        normalized_frequency=normalized_frequency,
        section_coverage=section_coverage,
        phrase_quality=phrase_quality,
    )


def _sem(
    canonical_text: str,
    semantic_score: float,
    *,
    rank: int,
    bi_encoder_score: float | None = None,
    reranker_score: float | None = None,
    reranked: bool = True,
):
    return SimpleNamespace(
        canonical_text=canonical_text,
        semantic_score=semantic_score,
        rank=rank,
        bi_encoder_score=(
            semantic_score
            if bi_encoder_score is None
            else bi_encoder_score
        ),
        reranker_score=reranker_score,
        reranked=reranked,
    )


class PreMmrFusionTests(unittest.TestCase):
    def test_pre_mmr_fused_ranking_matches_expected_weighting_and_tie_breaking(self):
        stats = (
            _stat("الف", 0.2),
            _stat("ب", 0.8),
            _stat("پ", 0.5),
        )
        sem = (
            _sem("الف", 0.9, rank=1),
            _sem("ب", 0.1, rank=3),
            _sem("پ", 0.5, rank=2),
        )

        ranked = _pre_mmr_fused_ranking(
            stats,
            sem,
            _BASELINE_WEIGHTS,
        )

        self.assertEqual(
            {item["canonical_text"] for item in ranked},
            {"الف", "ب", "پ"},
        )
        self.assertEqual(
            sorted(item["rank"] for item in ranked),
            [1, 2, 3],
        )
        self.assertTrue(
            all(
                0.0 <= item["fused_score"] <= 1.0
                for item in ranked
            )
        )


class _FakeDiagnosticEngine:
    def __init__(self):
        self.prepared_case_ids: list[str] = []
        self._baseline = ProfileScoringConfig(
            scoring_version="baseline-test",
            maximum_results=25,
            weights=dict(_BASELINE_WEIGHTS),
        )

    @property
    def baseline_config(self):
        return self._baseline

    async def prepare_case_async(self, case):
        self.prepared_case_ids.append(case.case_id)
        if case.case_id != "tuning-case":
            raise AssertionError("holdout must never be prepared")
        stats = (
            _stat("هوش مصنوعی", 0.9, frequency=3),
            _stat("یادگیری ماشین", 0.6, frequency=2),
        )
        semantic = SimpleNamespace(
            candidates=(
                _sem(
                    "هوش مصنوعی",
                    0.95,
                    rank=1,
                    bi_encoder_score=0.8,
                    reranker_score=0.95,
                ),
                _sem(
                    "یادگیری ماشین",
                    0.7,
                    rank=2,
                    bi_encoder_score=0.7,
                    reranker_score=0.7,
                ),
            ),
            embedding_metadata=SimpleNamespace(
                model_identifier="embedding-test",
                model_revision="1",
            ),
            reranker_metadata=SimpleNamespace(
                model_identifier="reranker-test",
                model_revision="1",
            ),
        )
        return SimpleNamespace(
            case=case,
            statistics=stats,
            semantic=semantic,
            candidate_ids=frozenset(
                item.canonical_text
                for item in stats
            ),
        )

    async def rank_prepared_result_async(self, prepared, weights):
        self.asserted_weights = dict(weights)
        final = (
            SimpleNamespace(
                canonical_text="هوش مصنوعی",
                rank=1,
                mmr_score=0.9,
            ),
        )
        hybrid = SimpleNamespace(
            candidates=final,
            deduplicated=(
                SimpleNamespace(
                    removed_canonical_text="یادگیری ماشین",
                    kept_canonical_text="هوش مصنوعی",
                    reason="semantic_near_duplicate",
                    similarity=0.97,
                ),
            ),
            diversity_candidate_pool_size=50,
        )
        return prepared.statistics, hybrid

    def model_version(self, prepared_cases):
        return (
            "embedding:embedding-test@1;reranker:reranker-test@1",
        )


class CourseRankingDiagnosticServiceTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_diagnostic_uses_tuning_only_and_explains_selection_stages(self):
        tuning = CourseCandidateCase(
            case_id="tuning-case",
            split="tuning",
            domain="test",
            documents=(
                CourseCandidateDocument(
                    "tuning-doc",
                    "هوش مصنوعی و یادگیری ماشین",
                    "tuning-doc",
                ),
            ),
            relevance={
                "هوش مصنوعی": 3,
                "یادگیری ماشین": 2,
                "عبارت گمشده": 1,
            },
        )
        holdout = CourseCandidateCase(
            case_id="holdout-case",
            split="holdout",
            domain="test",
            documents=(
                CourseCandidateDocument(
                    "holdout-doc",
                    "نباید خوانده شود",
                    "holdout-doc",
                ),
            ),
            relevance={"نگه‌داشت": 3},
        )
        dataset = CourseCandidateDataset(
            source_materialized_sha256="a" * 64,
            review_sha256="b" * 64,
            review_status=REVIEW_STATUS,
            cases=(tuning, holdout),
        )
        engine = _FakeDiagnosticEngine()
        result = await CourseRankingDiagnosticService(
            engine
        ).diagnose_async(dataset)

        self.assertEqual(
            result.status,
            DIAGNOSTIC_STATUS,
        )
        self.assertEqual(
            engine.prepared_case_ids,
            ["tuning-case"],
        )
        self.assertFalse(
            result.holdout_evaluated
        )
        self.assertEqual(
            result.frozen_holdout_case_count,
            1,
        )

        by_phrase = {
            item.canonical_text: item
            for item in result.cases[0].phrases
        }
        self.assertEqual(
            by_phrase["هوش مصنوعی"].selection_status,
            "selected_top_10",
        )
        self.assertEqual(
            by_phrase["یادگیری ماشین"].selection_status,
            "deduplicated:semantic_near_duplicate",
        )
        self.assertEqual(
            by_phrase["عبارت گمشده"].selection_status,
            "not_generated_by_candidate_engine",
        )
        self.assertEqual(
            result.cases[0].candidate_label_coverage,
            2 / 3,
        )


if __name__ == "__main__":
    unittest.main()
