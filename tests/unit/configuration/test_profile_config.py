from __future__ import annotations

import math
import unittest

from src.core.services.analysis.profile_config import load_profile_scoring_config
from src.infrastructure.utils.config_reader import ConfigReader


class _OverrideConfig:
    def __init__(self, base, overrides):
        self._base = base
        self._overrides = dict(overrides)

    def require(self, key):
        if key in self._overrides:
            value = self._overrides[key]
            if value is _MISSING:
                raise KeyError(key)
            return value
        return self._base.require(key)


_MISSING = object()


class ProfileConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.development = ConfigReader(env_type="development")
        self.production = ConfigReader(env_type="production")

    def test_development_and_production_profile_baselines_match(self) -> None:
        keys = (
            "analysis_profiles.course.scoring_version",
            "analysis_profiles.course.maximum_results",
            "analysis_profiles.course.diversity_candidate_pool_size",
            "analysis_profiles.course.weights.semantic_relevance",
            "analysis_profiles.course.weights.frequency",
            "analysis_profiles.course.weights.chunk_coverage",
            "analysis_profiles.course.weights.section_coverage",
            "analysis_profiles.course.weights.phrase_quality",
            "analysis_profiles.soldier_concern.scoring_version",
            "analysis_profiles.soldier_concern.maximum_results",
            "analysis_profiles.soldier_concern.diversity_candidate_pool_size",
            "analysis_profiles.soldier_concern.weights.document_frequency",
            "analysis_profiles.soldier_concern.weights.document_coverage",
            "analysis_profiles.soldier_concern.weights.semantic_relevance",
            "analysis_profiles.soldier_concern.weights.topic_prevalence",
            "analysis_profiles.media.scoring_version",
            "analysis_profiles.media.maximum_results",
            "analysis_profiles.media.diversity_candidate_pool_size",
            "analysis_profiles.media.weights.mention_share",
            "analysis_profiles.media.weights.semantic_relevance",
            "analysis_profiles.media.weights.coverage",
        )
        for key in keys:
            self.assertEqual(
                self.development.require(key),
                self.production.require(key),
                key,
            )

    def test_profile_specific_diversity_pools_are_explicit(self) -> None:
        course = load_profile_scoring_config(
            self.development,
            profile_key="course",
            required_signals=(
                "semantic_relevance",
                "frequency",
                "chunk_coverage",
                "section_coverage",
                "phrase_quality",
            ),
        )
        soldier = load_profile_scoring_config(
            self.development,
            profile_key="soldier_concern",
            required_signals=(
                "document_frequency",
                "document_coverage",
                "semantic_relevance",
                "topic_prevalence",
            ),
        )
        media = load_profile_scoring_config(
            self.development,
            profile_key="media",
            required_signals=(
                "mention_share",
                "semantic_relevance",
                "coverage",
                "normalized_engagement",
                "trend_growth",
                "recency",
            ),
        )

        self.assertEqual(course.diversity_candidate_pool_size, 200)
        self.assertEqual(soldier.diversity_candidate_pool_size, 50)
        self.assertEqual(media.diversity_candidate_pool_size, 50)

    def test_profile_pool_cannot_be_smaller_than_maximum_results(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be >= maximum_results"):
            load_profile_scoring_config(
                _OverrideConfig(
                    self.development,
                    {
                        "analysis_profiles.course.diversity_candidate_pool_size": 24,
                    },
                ),
                profile_key="course",
                required_signals=(
                    "semantic_relevance",
                    "frequency",
                    "chunk_coverage",
                    "section_coverage",
                    "phrase_quality",
                ),
            )

    def test_non_finite_profile_weight_is_rejected(self) -> None:
        for invalid in (math.nan, math.inf, -math.inf):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "finite"):
                    load_profile_scoring_config(
                        _OverrideConfig(
                            self.development,
                            {
                                "analysis_profiles.media.weights.coverage": invalid,
                            },
                        ),
                        profile_key="media",
                        required_signals=(
                            "mention_share",
                            "semantic_relevance",
                            "coverage",
                            "normalized_engagement",
                            "trend_growth",
                            "recency",
                        ),
                    )

    def test_boolean_profile_weight_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "numeric"):
            load_profile_scoring_config(
                _OverrideConfig(
                    self.development,
                    {
                        "analysis_profiles.soldier_concern.weights.document_frequency": True,
                    },
                ),
                profile_key="soldier_concern",
                required_signals=(
                    "document_frequency",
                    "document_coverage",
                    "semantic_relevance",
                    "topic_prevalence",
                ),
            )

    def test_missing_required_profile_config_fails_fast(self) -> None:
        with self.assertRaises(KeyError):
            load_profile_scoring_config(
                _OverrideConfig(
                    self.development,
                    {
                        "analysis_profiles.course.weights.frequency": _MISSING,
                    },
                ),
                profile_key="course",
                required_signals=(
                    "semantic_relevance",
                    "frequency",
                    "chunk_coverage",
                    "section_coverage",
                    "phrase_quality",
                ),
            )


if __name__ == "__main__":
    unittest.main()
