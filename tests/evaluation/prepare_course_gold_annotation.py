from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VERIFICATION = (
    PROJECT_ROOT
    / "tests"
    / "evaluation"
    / "gold"
    / "course_source_materialization_v1.json"
)

PACKAGE_SCHEMA_VERSION = "phase10-course-annotation-package-v1"
ANNOTATION_FILE_SCHEMA_VERSION = "phase10-course-annotation-working-v1"


class CourseAnnotationPackageError(ValueError):
    pass


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CourseAnnotationPackageError(
            f"{label} is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise CourseAnnotationPackageError(f"{label} must be a JSON object")
    return payload


def load_verification(path: Path = DEFAULT_VERIFICATION) -> dict[str, Any]:
    payload = _load_json(path, "COURSE materialization verification")
    if (
        payload.get("schema_version")
        != "phase10-course-materialization-verification-v1"
    ):
        raise CourseAnnotationPackageError(
            "Unsupported COURSE materialization verification schema"
        )
    return payload


def _read_materialized(
    path: Path,
    verification: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    source_bytes = path.read_bytes()
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    if source_sha != verification["materialized_file_sha256"]:
        raise CourseAnnotationPackageError(
            "COURSE materialized corpus SHA-256 does not match verified input"
        )

    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(
        source_bytes.decode("utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CourseAnnotationPackageError(
                f"COURSE materialized line {line_number} is invalid JSON"
            ) from exc
        if not isinstance(row, dict):
            raise CourseAnnotationPackageError(
                f"COURSE materialized line {line_number} must be an object"
            )

        required = {
            "source_unit_id",
            "case_group_id",
            "split",
            "domain",
            "section_title",
            "character_count",
            "text_sha256",
            "permanent_url",
            "attribution_url",
            "text",
        }
        missing = required.difference(row)
        if missing:
            raise CourseAnnotationPackageError(
                "COURSE materialized row is missing required fields"
            )

        source_unit_id = row["source_unit_id"]
        if source_unit_id in seen_ids:
            raise CourseAnnotationPackageError(
                "COURSE materialized source_unit_id values must be unique"
            )
        seen_ids.add(source_unit_id)

        text = row["text"]
        if not isinstance(text, str) or not text.strip():
            raise CourseAnnotationPackageError(
                "COURSE materialized text must be non-empty"
            )
        text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if text_sha != row["text_sha256"]:
            raise CourseAnnotationPackageError(
                "COURSE materialized text SHA-256 mismatch"
            )
        if len(text) != row["character_count"]:
            raise CourseAnnotationPackageError(
                "COURSE materialized character_count mismatch"
            )
        if row["split"] not in {"tuning", "holdout"}:
            raise CourseAnnotationPackageError(
                "COURSE materialized split must be tuning or holdout"
            )
        rows.append(row)

    if len(rows) != verification["source_unit_count"]:
        raise CourseAnnotationPackageError(
            "COURSE materialized source-unit count mismatch"
        )
    if sum(row["split"] == "tuning" for row in rows) != verification["tuning_unit_count"]:
        raise CourseAnnotationPackageError(
            "COURSE materialized tuning-unit count mismatch"
        )
    if sum(row["split"] == "holdout" for row in rows) != verification["holdout_unit_count"]:
        raise CourseAnnotationPackageError(
            "COURSE materialized holdout-unit count mismatch"
        )

    return source_sha, rows


def _group_cases(
    rows: list[dict[str, Any]],
    verification: dict[str, Any],
    source_sha: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["case_group_id"]].append(row)

    cases: list[dict[str, Any]] = []
    for case_id, case_rows in grouped.items():
        splits = {row["split"] for row in case_rows}
        domains = {row["domain"] for row in case_rows}
        if len(splits) != 1:
            raise CourseAnnotationPackageError(
                "COURSE annotation case cannot cross tuning and holdout"
            )
        if len(domains) != 1:
            raise CourseAnnotationPackageError(
                "COURSE annotation case must stay within one domain"
            )

        case_hash_material = "\n".join(
            f"{row['source_unit_id']}:{row['text_sha256']}"
            for row in case_rows
        ).encode("utf-8")
        case_sha = hashlib.sha256(case_hash_material).hexdigest()

        cases.append(
            {
                "case_id": case_id,
                "split": next(iter(splits)),
                "domain": next(iter(domains)),
                "case_sha256": case_sha,
                "documents": [
                    {
                        "document_id": row["source_unit_id"],
                        "section_title": row["section_title"],
                        "character_count": row["character_count"],
                        "text_sha256": row["text_sha256"],
                        "permanent_url": row["permanent_url"],
                        "attribution_url": row["attribution_url"],
                        "text": row["text"],
                    }
                    for row in case_rows
                ],
            }
        )

    if len(cases) != verification["case_count"]:
        raise CourseAnnotationPackageError(
            "COURSE annotation case count mismatch"
        )
    if sum(case["split"] == "tuning" for case in cases) != verification["tuning_case_count"]:
        raise CourseAnnotationPackageError(
            "COURSE annotation tuning-case count mismatch"
        )
    if sum(case["split"] == "holdout" for case in cases) != verification["holdout_case_count"]:
        raise CourseAnnotationPackageError(
            "COURSE annotation holdout-case count mismatch"
        )

    return sorted(
        cases,
        key=lambda case: hashlib.sha256(
            f"{source_sha}:{case['case_id']}".encode("utf-8")
        ).hexdigest(),
    )


def _annotation_rows(
    cases: list[dict[str, Any]],
    annotator_id: str,
) -> list[dict[str, Any]]:
    return [
        {
            "schema_version": ANNOTATION_FILE_SCHEMA_VERSION,
            "case_id": case["case_id"],
            "case_sha256": case["case_sha256"],
            "annotator_id": annotator_id,
            "complete": False,
            "relevance": [],
            "notes": "",
        }
        for case in cases
    ]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _guide(source_sha: str) -> str:
    return f"""# راهنمای Human Annotation — COURSE Gold v1

Source corpus SHA-256:

`{source_sha}`

این package یک working annotation package است و هنوز Production Gold Dataset نیست.

## روش

دو annotator باید مستقل کار کنند. قبل از کامل شدن annotation مستقل، predictionهای مدل، synthetic fixture و annotation نفر دیگر نباید در اختیار annotator قرار گیرد.

برای هر case، همه document/sectionهای آن case خوانده شود و keyphraseهای واقعاً نماینده محتوا ثبت شوند. عنوان section فقط به دلیل heading بودن Gold نیست.

## Relevance grades

- 3: مفهوم مرکزی و ضروری
- 2: مفهوم مهم و واضح
- 1: مرتبط ولی فرعی
- 0: عبارت بررسی‌شده ولی نامناسب/غیرمرتبط

Gradeهای 1 تا 3 در Precision/Recall relevant هستند و NDCG@10 از grade کامل 0..3 استفاده می‌کند.

## Phrase policy

- ترجیحاً 1 تا 3 token واژگانی مطابق Candidate Engine فاز 7.
- یک مفهوم را با چند spelling duplicate ثبت نکنید.
- فارسی، انگلیسی و عبارت mixed فنی مجازند.
- جمله کامل، URL و fragmentهای نحوی Gold keyphrase نیستند.
- کیفیت مقدم بر quota است؛ برای اکثر caseها 8 تا 15 عبارت مثبت هدف مناسبی است، نه الزام سخت.

## Adjudication

بعد از کامل شدن هر دو annotation مستقل، اختلاف‌ها توسط adjudicator حل می‌شوند. فقط نتیجه adjudicated می‌تواند بعداً به contract `phase10-gold-v1` تبدیل شود. Split tuning/holdout عمداً از working annotation rows حذف شده تا بر قضاوت annotator اثر نگذارد.
"""


def prepare_annotation_package(
    materialized_path: Path,
    output_dir: Path,
    *,
    verification_path: Path = DEFAULT_VERIFICATION,
) -> dict[str, Any]:
    verification = load_verification(verification_path)

    output_dir = output_dir.expanduser().resolve()
    project_root = PROJECT_ROOT.resolve()
    if output_dir == project_root or project_root in output_dir.parents:
        raise CourseAnnotationPackageError(
            "COURSE annotation package must be written outside the repository"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    source_sha, rows = _read_materialized(
        materialized_path.expanduser().resolve(),
        verification,
    )
    cases = _group_cases(rows, verification, source_sha)

    package_manifest = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "package_id": "course-wikibooks-fa-human-annotation-v1",
        "source_manifest_id": verification["source_manifest_id"],
        "source_manifest_version": verification["source_manifest_version"],
        "source_materialized_sha256": source_sha,
        "source_unit_count": len(rows),
        "case_count": len(cases),
        "annotation_policy": {
            "independent_annotators": 2,
            "relevance_grades": [0, 1, 2, 3],
            "positive_grades": [1, 2, 3],
            "model_output_visible_during_independent_annotation": False,
            "section_heading_is_automatic_gold": False,
            "adjudication_required": True,
        },
        "case_index": [
            {
                "annotation_order": index,
                "case_id": case["case_id"],
                "split": case["split"],
                "domain": case["domain"],
                "case_sha256": case["case_sha256"],
                "document_count": len(case["documents"]),
            }
            for index, case in enumerate(cases, start=1)
        ],
    }
    (output_dir / "package_manifest.json").write_text(
        json.dumps(package_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    annotator_cases = [
        {
            "annotation_order": index,
            "case_id": case["case_id"],
            "case_sha256": case["case_sha256"],
            "documents": case["documents"],
        }
        for index, case in enumerate(cases, start=1)
    ]
    _write_jsonl(output_dir / "cases.jsonl", annotator_cases)
    _write_jsonl(
        output_dir / "annotator_A.jsonl",
        _annotation_rows(cases, "A"),
    )
    _write_jsonl(
        output_dir / "annotator_B.jsonl",
        _annotation_rows(cases, "B"),
    )
    _write_jsonl(
        output_dir / "adjudication.jsonl",
        _annotation_rows(cases, "ADJUDICATOR"),
    )
    (output_dir / "ANNOTATION_GUIDE_FA.md").write_text(
        _guide(source_sha),
        encoding="utf-8",
    )

    return {
        "source_materialized_sha256": source_sha,
        "source_unit_count": len(rows),
        "case_count": len(cases),
        "tuning_case_count": sum(case["split"] == "tuning" for case in cases),
        "holdout_case_count": sum(case["split"] == "holdout" for case in cases),
        "output_dir": str(output_dir),
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a blinded human-annotation working package from the "
            "verified Phase 10 COURSE materialized corpus."
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--verification",
        type=Path,
        default=DEFAULT_VERIFICATION,
    )
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    report = prepare_annotation_package(
        args.input,
        args.output_dir,
        verification_path=args.verification,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
