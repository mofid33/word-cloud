from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from tests.evaluation.materialize_course_gold_sources import (
    CourseSourceMaterializationError,
    PROJECT_ROOT,
    html_to_visible_text,
    load_manifest,
    materialize,
    normalize_heading,
)


MANIFEST_PATH = (
    Path(__file__).resolve().parent
    / "gold"
    / "course_source_manifest_v1.json"
)


class CourseGoldSourceManifestTests(unittest.TestCase):
    def test_manifest_freezes_30_units_with_20_10_split(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        units = manifest["units"]

        self.assertEqual(len(units), 30)
        self.assertEqual(
            Counter(unit["split"] for unit in units),
            Counter({"tuning": 20, "holdout": 10}),
        )
        self.assertEqual(
            Counter(unit["domain"] for unit in units),
            Counter(
                {
                    "fluid_mechanics": 8,
                    "python_programming": 8,
                    "mathematics_economics": 7,
                    "linux_cli": 7,
                }
            ),
        )

    def test_manifest_units_are_unique_and_revision_pinned(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        units = manifest["units"]

        ids = [unit["source_unit_id"] for unit in units]
        self.assertEqual(len(ids), len(set(ids)))

        for unit in units:
            revision_id = unit["revision_id"]
            self.assertIsInstance(revision_id, int)
            self.assertGreater(revision_id, 0)
            self.assertEqual(
                unit["permanent_url"],
                f"https://fa.wikibooks.org/w/index.php?oldid={revision_id}",
            )
            self.assertEqual(unit["attribution_url"], unit["permanent_url"])
            self.assertGreaterEqual(unit["minimum_materialized_chars"], 200)
            self.assertTrue(unit["license_review_required_before_redistribution"])

    def test_holdout_assignments_are_explicit_and_not_derived_at_runtime(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        holdout_ids = {
            unit["source_unit_id"]
            for unit in manifest["units"]
            if unit["split"] == "holdout"
        }
        self.assertEqual(
            holdout_ids,
            {
                "course-fluid-003",
                "course-fluid-006",
                "course-python-004",
                "course-python-007",
                "course-python-008",
                "course-math-002",
                "course-math-005",
                "course-math-007",
                "course-linux-004",
                "course-linux-007",
            },
        )

    def test_heading_normalization_handles_persian_arabic_variants(self) -> None:
        self.assertEqual(
            normalize_heading("  ماتريس\u200cها: "),
            normalize_heading("ماتریس ها"),
        )
        self.assertEqual(
            normalize_heading("مشاهدهٔ داکیومنت دستورات( --help و man)"),
            normalize_heading("مشاهدهٔ داکیومنت دستورات(--help و man)"),
        )

    def test_html_extractor_keeps_visible_text_and_drops_script_style(self) -> None:
        text = html_to_visible_text(
            "<section><h2>عنوان</h2><p>متن <b>اصلی</b></p>"
            "<script>SECRET_SCRIPT</script><style>SECRET_STYLE</style></section>"
        )
        self.assertIn("عنوان", text)
        self.assertIn("متن اصلی", text)
        self.assertNotIn("SECRET_SCRIPT", text)
        self.assertNotIn("SECRET_STYLE", text)

    def test_materialized_source_text_cannot_be_written_inside_repository(self) -> None:
        with self.assertRaisesRegex(
            CourseSourceMaterializationError,
            "outside the repository",
        ):
            materialize(
                MANIFEST_PATH,
                PROJECT_ROOT / "tests" / "evaluation" / "gold" / "materialized.jsonl",
            )

    def test_materialize_writes_reproducible_report_without_network_in_unit_test(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)

        def fake_materialize(unit):
            text = f"materialized-{unit['source_unit_id']}"
            return {
                "source_unit_id": unit["source_unit_id"],
                "split": unit["split"],
                "domain": unit["domain"],
                "page_title": unit["page_title"],
                "revision_id": unit["revision_id"],
                "section_title": unit["section_title"],
                "permanent_url": unit["permanent_url"],
                "attribution_url": unit["attribution_url"],
                "license_label": "test-license",
                "text_sha256": "0" * 64,
                "character_count": len(text),
                "text": text,
            }

        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "course_sources.jsonl"
            with patch(
                "tests.evaluation.materialize_course_gold_sources.materialize_unit",
                side_effect=fake_materialize,
            ):
                report = materialize(MANIFEST_PATH, output)

            self.assertEqual(report["source_unit_count"], 30)
            self.assertEqual(report["tuning_unit_count"], 20)
            self.assertEqual(report["holdout_unit_count"], 10)
            self.assertEqual(len(report["materialized_file_sha256"]), 64)
            rows = [
                json.loads(line)
                for line in output.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(rows), 30)
            self.assertEqual(
                {row["source_unit_id"] for row in rows},
                {unit["source_unit_id"] for unit in manifest["units"]},
            )


if __name__ == "__main__":
    unittest.main()
