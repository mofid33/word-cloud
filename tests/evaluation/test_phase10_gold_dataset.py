from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.evaluation.phase10_gold_dataset import (
    GoldDatasetValidationError,
    Phase10GoldDatasetLoader,
    Phase10GoldEvaluator,
    SCHEMA_VERSION,
)


class _ProfileService:
    def __init__(self, profile: str, rankings: list[list[str]]):
        self._profile = profile
        self._rankings = list(rankings)
        self.calls = 0

    async def analyze_async(self, documents):
        ranking = self._rankings[self.calls]
        self.calls += 1
        return SimpleNamespace(
            profile=self._profile,
            keywords=tuple(
                SimpleNamespace(canonical_text=value)
                for value in ranking
            ),
            scoring_version="gold-test-score-v1",
            model_version="gold-test-model-v1",
        )


def _manifest(profile: str) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": f"{profile.lower()}-gold",
        "dataset_version": "1.0.0",
        "profile": profile,
        "guideline_version": "phase10-guideline-v1",
        "cases_file": "cases.jsonl",
    }


def _case(
    case_id: str,
    *,
    split: str,
    profile: str,
    adjudicated: bool = True,
) -> dict[str, object]:
    if profile == "MEDIA":
        metadata = {"role": "published_content"}
    elif profile == "COURSE":
        metadata = {"section_id": "s1", "chunk_id": "c1"}
    else:
        metadata = {}
    return {
        "case_id": case_id,
        "split": split,
        "documents": [
            {
                "document_id": f"doc-{case_id}",
                "text": "متن ارزیابی انسانی خصوصی",
                "metadata": metadata,
            }
        ],
        "annotation": {
            "guideline_version": "phase10-guideline-v1",
            "annotator_count": 2,
            "adjudicated": adjudicated,
            "relevance": [
                {"canonical_text": "هوش مصنوعی", "grade": 3},
                {"canonical_text": "یادگیری ماشین", "grade": 2},
                {"canonical_text": "نویز", "grade": 0},
            ],
        },
    }


def _write_dataset(directory: Path, profile: str, cases: list[dict[str, object]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "manifest.json").write_text(
        json.dumps(_manifest(profile), ensure_ascii=False),
        encoding="utf-8",
    )
    (directory / "cases.jsonl").write_text(
        "\n".join(json.dumps(case, ensure_ascii=False) for case in cases) + "\n",
        encoding="utf-8",
    )


class Phase10GoldDatasetTests(unittest.TestCase):
    def test_machine_readable_schema_version_matches_runtime_validator(self):
        schema_path = Path(__file__).resolve().parent / "gold" / "phase10_gold_schema.json"
        payload = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["$id"], SCHEMA_VERSION)
        self.assertEqual(
            payload["$defs"]["manifest"]["properties"]["schema_version"]["const"],
            SCHEMA_VERSION,
        )

    def test_valid_dataset_requires_tuning_and_holdout_and_has_stable_fingerprint(self):
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "project"
            project.mkdir()
            dataset_dir = Path(root) / "course-gold"
            _write_dataset(
                dataset_dir,
                "COURSE",
                [
                    _case("course-tuning", split="tuning", profile="COURSE"),
                    _case("course-holdout", split="holdout", profile="COURSE"),
                ],
            )
            loader = Phase10GoldDatasetLoader(project)
            first = loader.load(dataset_dir, expected_profile="COURSE")
            second = loader.load(dataset_dir, expected_profile="COURSE")

            self.assertEqual(first.fingerprint, second.fingerprint)
            self.assertTrue(first.fingerprint.startswith("sha256:"))
            self.assertEqual(len(first.cases_for_split("tuning")), 1)
            self.assertEqual(len(first.cases_for_split("holdout")), 1)

    def test_soldier_dataset_is_rejected_when_stored_inside_repository(self):
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "project"
            dataset_dir = project / "private" / "soldier-gold"
            _write_dataset(
                dataset_dir,
                "SOLDIER_CONCERN",
                [
                    _case("soldier-tuning", split="tuning", profile="SOLDIER_CONCERN"),
                    _case("soldier-holdout", split="holdout", profile="SOLDIER_CONCERN"),
                ],
            )
            loader = Phase10GoldDatasetLoader(project)
            with self.assertRaisesRegex(
                GoldDatasetValidationError,
                "outside the repository",
            ):
                loader.load(dataset_dir, expected_profile="SOLDIER_CONCERN")

    def test_soldier_dataset_outside_repository_loads_without_echoing_raw_text(self):
        raw_text = "SOLDIER PRIVATE GOLD RAW TEXT 4f630"
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "project"
            project.mkdir()
            dataset_dir = Path(root) / "external-soldier-gold"
            cases = [
                _case("soldier-tuning", split="tuning", profile="SOLDIER_CONCERN"),
                _case("soldier-holdout", split="holdout", profile="SOLDIER_CONCERN"),
            ]
            cases[0]["documents"][0]["text"] = raw_text
            _write_dataset(dataset_dir, "SOLDIER_CONCERN", cases)
            dataset = Phase10GoldDatasetLoader(project).load(
                dataset_dir,
                expected_profile="SOLDIER_CONCERN",
            )
            self.assertEqual(dataset.cases[0].documents[0].text, raw_text)
            self.assertNotIn(raw_text, dataset.fingerprint)

    def test_duplicate_case_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "project"
            project.mkdir()
            dataset_dir = Path(root) / "media-gold"
            _write_dataset(
                dataset_dir,
                "MEDIA",
                [
                    _case("same", split="tuning", profile="MEDIA"),
                    _case("same", split="holdout", profile="MEDIA"),
                ],
            )
            with self.assertRaisesRegex(GoldDatasetValidationError, "case_id"):
                Phase10GoldDatasetLoader(project).load(
                    dataset_dir,
                    expected_profile="MEDIA",
                )

    def test_course_boundary_metadata_must_be_consistent_within_case(self):
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "project"
            project.mkdir()
            dataset_dir = Path(root) / "course-gold"
            tuning = _case("course-tuning", split="tuning", profile="COURSE")
            tuning["documents"].append(
                {
                    "document_id": "doc-second",
                    "text": "متن دوم",
                    "metadata": {},
                }
            )
            _write_dataset(
                dataset_dir,
                "COURSE",
                [
                    tuning,
                    _case("course-holdout", split="holdout", profile="COURSE"),
                ],
            )
            with self.assertRaisesRegex(GoldDatasetValidationError, "section_id"):
                Phase10GoldDatasetLoader(project).load(
                    dataset_dir,
                    expected_profile="COURSE",
                )

    def test_invalid_case_error_does_not_echo_raw_document_text(self):
        raw_text = "PRIVATE-DOCUMENT-PAYLOAD-93ef"
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "project"
            project.mkdir()
            dataset_dir = Path(root) / "course-gold"
            tuning = _case("course-tuning", split="tuning", profile="COURSE")
            tuning["documents"][0]["text"] = raw_text
            tuning["documents"][0]["metadata"] = []
            _write_dataset(
                dataset_dir,
                "COURSE",
                [
                    tuning,
                    _case("course-holdout", split="holdout", profile="COURSE"),
                ],
            )
            with self.assertRaises(GoldDatasetValidationError) as context:
                Phase10GoldDatasetLoader(project).load(
                    dataset_dir,
                    expected_profile="COURSE",
                )
            self.assertNotIn(raw_text, str(context.exception))


class Phase10GoldEvaluatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_evaluator_uses_only_requested_split_and_fixed_k_denominators(self):
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "project"
            project.mkdir()
            dataset_dir = Path(root) / "course-gold"
            _write_dataset(
                dataset_dir,
                "COURSE",
                [
                    _case("course-tuning", split="tuning", profile="COURSE"),
                    _case("course-holdout", split="holdout", profile="COURSE"),
                ],
            )
            dataset = Phase10GoldDatasetLoader(project).load(
                dataset_dir,
                expected_profile="COURSE",
            )
            service = _ProfileService(
                "COURSE",
                [["هوش مصنوعی", "نویز", "یادگیری ماشین"]],
            )
            result = await Phase10GoldEvaluator().evaluate_async(
                dataset,
                service,
                split="holdout",
            )

            self.assertEqual(service.calls, 1)
            self.assertEqual(result.case_count, 1)
            self.assertEqual(result.metrics.precision_at_5, 0.4)
            self.assertEqual(result.metrics.precision_at_10, 0.2)
            self.assertEqual(result.metrics.recall_at_10, 1.0)
            self.assertGreater(result.metrics.ndcg_at_10, 0.0)
            self.assertLessEqual(result.metrics.ndcg_at_10, 1.0)

    async def test_evaluator_rejects_non_adjudicated_human_annotations(self):
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "project"
            project.mkdir()
            dataset_dir = Path(root) / "media-gold"
            _write_dataset(
                dataset_dir,
                "MEDIA",
                [
                    _case("media-tuning", split="tuning", profile="MEDIA"),
                    _case(
                        "media-holdout",
                        split="holdout",
                        profile="MEDIA",
                        adjudicated=False,
                    ),
                ],
            )
            dataset = Phase10GoldDatasetLoader(project).load(
                dataset_dir,
                expected_profile="MEDIA",
            )
            service = _ProfileService("MEDIA", [["هوش مصنوعی"]])
            with self.assertRaisesRegex(
                GoldDatasetValidationError,
                "adjudicated human annotations",
            ):
                await Phase10GoldEvaluator().evaluate_async(
                    dataset,
                    service,
                    split="holdout",
                )


if __name__ == "__main__":
    unittest.main()
