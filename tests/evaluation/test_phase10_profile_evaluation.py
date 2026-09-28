from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from tests.evaluation.phase10_test_support import build_profile_services


_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "phase10_profile_regression_cases.json"
)


def _precision_at_k(ranked, relevance, k):
    relevant = {item for item, grade in relevance.items() if grade > 0}
    return sum(item in relevant for item in ranked[:k]) / k


def _recall_at_k(ranked, relevance, k):
    relevant = {item for item, grade in relevance.items() if grade > 0}
    if not relevant:
        return 1.0
    return sum(item in relevant for item in ranked[:k]) / len(relevant)


def _dcg(ranked, relevance, k):
    total = 0.0
    for index, item in enumerate(ranked[:k], start=1):
        grade = relevance.get(item, 0)
        total += (2 ** grade - 1) / math.log2(index + 1)
    return total


def _ndcg_at_10(ranked, relevance):
    ideal = [
        item
        for item, _ in sorted(
            relevance.items(),
            key=lambda pair: (-pair[1], pair[0]),
        )
    ]
    denominator = _dcg(ideal, relevance, 10)
    return _dcg(ranked, relevance, 10) / denominator if denominator else 1.0


class Phase10ProfileEvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.services = build_profile_services()
        self.payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_is_explicitly_not_production_gold(self):
        self.assertEqual(
            self.payload["status"],
            "PHASE_10_SYNTHETIC_REGRESSION_FIXTURE_NOT_PRODUCTION_GOLD",
        )
        self.assertEqual(
            {case["profile"] for case in self.payload["cases"]},
            {"COURSE", "SOLDIER_CONCERN", "MEDIA"},
        )

    async def test_profile_ranking_metrics_are_computed_and_deterministic(self):
        evidence = {}
        for case in self.payload["cases"]:
            service = self.services[case["profile"]]
            first = await service.analyze_async(case["documents"])
            second = await service.analyze_async(list(reversed(case["documents"])))
            self.assertEqual(first, second)

            ranked = [item.canonical_text for item in first.keywords]
            relevance = case["relevance"]
            metrics = {
                "precision_at_5": _precision_at_k(ranked, relevance, 5),
                "precision_at_10": _precision_at_k(ranked, relevance, 10),
                "recall_at_10": _recall_at_k(ranked, relevance, 10),
                "ndcg_at_10": _ndcg_at_10(ranked, relevance),
            }
            for value in metrics.values():
                self.assertTrue(math.isfinite(value))
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)

            evidence[f'{case["profile"]}:{case["name"]}'] = metrics

        print(
            "PHASE10_SYNTHETIC_EVALUATION="
            + json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        )

    async def test_profile_specific_product_behaviors(self):
        cases = {case["profile"]: case for case in self.payload["cases"]}

        course = await self.services["COURSE"].analyze_async(
            cases["COURSE"]["documents"]
        )
        course_term = next(
            item for item in course.keywords
            if item.canonical_text == "هوش مصنوعی"
        )
        self.assertEqual(course_term.signals["section_coverage"], 1.0)
        self.assertEqual(course_term.signals["chunk_coverage"], 1.0)

        soldier = await self.services["SOLDIER_CONCERN"].analyze_async(
            cases["SOLDIER_CONCERN"]["documents"]
        )
        soldier_term = next(
            item for item in soldier.keywords
            if item.canonical_text == "کیفیت اینترنت"
        )
        self.assertEqual(soldier_term.signals["document_frequency"], 3)
        self.assertEqual(soldier_term.signals["document_coverage"], 1.0)

        media = await self.services["MEDIA"].analyze_async(
            cases["MEDIA"]["documents"]
        )
        self.assertTrue(media.profile_result["role_separation"])
        self.assertEqual(
            media.profile_result["roles"]["published_content"]["document_count"],
            2,
        )
        self.assertEqual(
            media.profile_result["roles"]["audience_feedback"]["document_count"],
            2,
        )


if __name__ == "__main__":
    unittest.main()
