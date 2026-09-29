from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_EVIDENCE = (
    _PROJECT_ROOT
    / "tests"
    / "evaluation"
    / "gold"
    / "course_ai_review_holdout_v1.json"
)
_CONFIGS = (
    _PROJECT_ROOT / "src" / "host" / "res" / "appsettings.yaml",
    _PROJECT_ROOT / "src" / "host" / "res" / "appsettings.development.yaml",
)


class CourseHoldoutEvidenceRegressionTests(unittest.TestCase):
    def test_rejected_tuning_weights_are_not_promoted_to_runtime_config(self):
        evidence = json.loads(_EVIDENCE.read_text(encoding="utf-8"))
        self.assertFalse(
            evidence["decision"]["selected_tuning_weights_accepted"]
        )
        self.assertFalse(
            evidence["decision"]["production_config_updated"]
        )
        self.assertTrue(
            evidence["decision"]["baseline_config_remains_active"]
        )

        baseline = evidence["baseline"]["weights"]
        rejected = evidence["selected"]["weights"]

        for config_path in _CONFIGS:
            config = yaml.safe_load(
                config_path.read_text(encoding="utf-8")
            )
            configured = config["analysis_profiles"]["course"]["weights"]

            self.assertEqual(configured, baseline)
            self.assertNotEqual(configured, rejected)

    def test_holdout_regression_is_recorded_for_all_ranking_metrics_except_p5(self):
        evidence = json.loads(_EVIDENCE.read_text(encoding="utf-8"))
        delta = evidence["generalization_delta"]

        self.assertEqual(delta["precision_at_5"], 0.0)
        self.assertLess(delta["precision_at_10"], 0.0)
        self.assertLess(delta["recall_at_10"], 0.0)
        self.assertLess(delta["ndcg_at_10"], 0.0)
        self.assertTrue(
            evidence["decision"][
                "holdout_is_spent_for_future_model_selection"
            ]
        )


if __name__ == "__main__":
    unittest.main()
