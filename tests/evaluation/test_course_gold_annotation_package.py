from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tests.evaluation.prepare_course_gold_annotation import (
    ANNOTATION_FILE_SCHEMA_VERSION,
    CourseAnnotationPackageError,
    PACKAGE_SCHEMA_VERSION,
    PROJECT_ROOT,
    prepare_annotation_package,
)


def _write_synthetic_materialized(root: Path) -> tuple[Path, Path]:
    group_sizes = {
        "tuning-a": ("tuning", "fluid", 3),
        "tuning-b": ("tuning", "fluid", 3),
        "tuning-c": ("tuning", "python", 3),
        "tuning-d": ("tuning", "python", 3),
        "tuning-e": ("tuning", "math", 3),
        "tuning-f": ("tuning", "math", 3),
        "tuning-g": ("tuning", "linux", 2),
        "holdout-a": ("holdout", "fluid", 3),
        "holdout-b": ("holdout", "python", 3),
        "holdout-c": ("holdout", "math", 2),
        "holdout-d": ("holdout", "linux", 2),
    }
    rows = []
    counter = 0
    for group_id, (split, domain, size) in group_sizes.items():
        for index in range(size):
            counter += 1
            text = f"متن آموزشی {group_id} بخش {index + 1}"
            text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            rows.append(
                {
                    "source_unit_id": f"unit-{counter:02d}",
                    "case_group_id": group_id,
                    "split": split,
                    "domain": domain,
                    "section_title": f"بخش {index + 1}",
                    "character_count": len(text),
                    "text_sha256": text_sha,
                    "permanent_url": f"https://example.test/{counter}",
                    "attribution_url": f"https://example.test/{counter}",
                    "text": text,
                }
            )

    materialized_path = root / "materialized.jsonl"
    materialized_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
    materialized_sha = hashlib.sha256(
        materialized_path.read_bytes()
    ).hexdigest()

    verification = {
        "schema_version": "phase10-course-materialization-verification-v1",
        "source_manifest_id": "synthetic-source",
        "source_manifest_version": "1.0.0",
        "materialized_file_sha256": materialized_sha,
        "source_unit_count": 30,
        "tuning_unit_count": 20,
        "holdout_unit_count": 10,
        "case_count": 11,
        "tuning_case_count": 7,
        "holdout_case_count": 4,
    }
    verification_path = root / "verification.json"
    verification_path.write_text(
        json.dumps(verification, ensure_ascii=False),
        encoding="utf-8",
    )
    return materialized_path, verification_path


class CourseGoldAnnotationPackageTests(unittest.TestCase):
    def test_package_builder_creates_blinded_working_annotation_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            materialized, verification = _write_synthetic_materialized(root)
            output = root / "annotation-package"

            report = prepare_annotation_package(
                materialized,
                output,
                verification_path=verification,
            )

            self.assertEqual(report["source_unit_count"], 30)
            self.assertEqual(report["case_count"], 11)
            self.assertEqual(report["tuning_case_count"], 7)
            self.assertEqual(report["holdout_case_count"], 4)

            package_manifest = json.loads(
                (output / "package_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                package_manifest["schema_version"],
                PACKAGE_SCHEMA_VERSION,
            )

            case_rows = [
                json.loads(line)
                for line in (output / "cases.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(len(case_rows), 11)
            for row in case_rows:
                self.assertNotIn("split", row)
                self.assertNotIn("domain", row)
                self.assertNotIn("annotation", row)

            annotation_rows = [
                json.loads(line)
                for line in (output / "annotator_A.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(len(annotation_rows), 11)
            for row in annotation_rows:
                self.assertEqual(
                    row["schema_version"],
                    ANNOTATION_FILE_SCHEMA_VERSION,
                )
                self.assertFalse(row["complete"])
                self.assertEqual(row["relevance"], [])
                self.assertNotIn("split", row)
                self.assertNotIn("domain", row)
                self.assertNotIn("adjudicated", row)

    def test_annotation_case_order_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            materialized, verification = _write_synthetic_materialized(root)
            first = root / "first"
            second = root / "second"

            prepare_annotation_package(
                materialized,
                first,
                verification_path=verification,
            )
            prepare_annotation_package(
                materialized,
                second,
                verification_path=verification,
            )

            self.assertEqual(
                (first / "cases.jsonl").read_bytes(),
                (second / "cases.jsonl").read_bytes(),
            )
            self.assertEqual(
                (first / "annotator_A.jsonl").read_bytes(),
                (second / "annotator_A.jsonl").read_bytes(),
            )

    def test_verified_corpus_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            materialized, verification = _write_synthetic_materialized(root)
            payload = json.loads(
                verification.read_text(encoding="utf-8")
            )
            payload["materialized_file_sha256"] = "0" * 64
            verification.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                CourseAnnotationPackageError,
                "SHA-256",
            ):
                prepare_annotation_package(
                    materialized,
                    root / "output",
                    verification_path=verification,
                )

    def test_per_document_text_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            materialized, verification = _write_synthetic_materialized(root)

            rows = [
                json.loads(line)
                for line in materialized.read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            rows[0]["text_sha256"] = "f" * 64
            materialized.write_text(
                "".join(
                    json.dumps(row, ensure_ascii=False, sort_keys=True)
                    + "\n"
                    for row in rows
                ),
                encoding="utf-8",
            )
            payload = json.loads(
                verification.read_text(encoding="utf-8")
            )
            payload["materialized_file_sha256"] = hashlib.sha256(
                materialized.read_bytes()
            ).hexdigest()
            verification.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                CourseAnnotationPackageError,
                "text SHA-256 mismatch",
            ):
                prepare_annotation_package(
                    materialized,
                    root / "output",
                    verification_path=verification,
                )

    def test_case_cannot_cross_tuning_and_holdout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            materialized, verification = _write_synthetic_materialized(root)

            rows = [
                json.loads(line)
                for line in materialized.read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            rows[-1]["case_group_id"] = rows[0]["case_group_id"]
            materialized.write_text(
                "".join(
                    json.dumps(row, ensure_ascii=False, sort_keys=True)
                    + "\n"
                    for row in rows
                ),
                encoding="utf-8",
            )
            payload = json.loads(
                verification.read_text(encoding="utf-8")
            )
            payload["materialized_file_sha256"] = hashlib.sha256(
                materialized.read_bytes()
            ).hexdigest()
            verification.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                CourseAnnotationPackageError,
                "cannot cross tuning and holdout",
            ):
                prepare_annotation_package(
                    materialized,
                    root / "output",
                    verification_path=verification,
                )

    def test_output_inside_repository_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            materialized, verification = _write_synthetic_materialized(root)

            with self.assertRaisesRegex(
                CourseAnnotationPackageError,
                "outside the repository",
            ):
                prepare_annotation_package(
                    materialized,
                    PROJECT_ROOT / "tests" / "evaluation" / "bad-output",
                    verification_path=verification,
                )


if __name__ == "__main__":
    unittest.main()
