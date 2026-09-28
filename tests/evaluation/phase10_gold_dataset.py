from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "phase10-gold-v1"
SUPPORTED_PROFILES = ("COURSE", "SOLDIER_CONCERN", "MEDIA")
SUPPORTED_SPLITS = ("tuning", "holdout")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


class GoldDatasetValidationError(ValueError):
    pass


@dataclass(frozen=True)
class GoldDocument:
    document_id: str
    text: str
    metadata: dict[str, Any]

    def runtime_value(self) -> dict[str, Any]:
        return {"document_id": self.document_id, "text": self.text, "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class GoldCase:
    case_id: str
    split: str
    documents: tuple[GoldDocument, ...]
    guideline_version: str
    annotator_count: int
    adjudicated: bool
    relevance: dict[str, int]


@dataclass(frozen=True)
class GoldDataset:
    dataset_id: str
    dataset_version: str
    profile: str
    guideline_version: str
    fingerprint: str
    cases: tuple[GoldCase, ...]

    def cases_for_split(self, split: str) -> tuple[GoldCase, ...]:
        if split not in SUPPORTED_SPLITS:
            raise ValueError("Gold evaluation split must be tuning or holdout")
        return tuple(case for case in self.cases if case.split == split)


@dataclass(frozen=True)
class RankingMetrics:
    precision_at_5: float
    precision_at_10: float
    recall_at_10: float
    ndcg_at_10: float


@dataclass(frozen=True)
class GoldEvaluationResult:
    profile: str
    split: str
    dataset_id: str
    dataset_version: str
    dataset_fingerprint: str
    guideline_version: str
    case_count: int
    metrics: RankingMetrics
    scoring_versions: tuple[str, ...]
    model_versions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "split": self.split,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "dataset_fingerprint": self.dataset_fingerprint,
            "guideline_version": self.guideline_version,
            "case_count": self.case_count,
            "metrics": {
                "precision_at_5": self.metrics.precision_at_5,
                "precision_at_10": self.metrics.precision_at_10,
                "recall_at_10": self.metrics.recall_at_10,
                "ndcg_at_10": self.metrics.ndcg_at_10,
            },
            "scoring_versions": list(self.scoring_versions),
            "model_versions": list(self.model_versions),
        }


class Phase10GoldDatasetLoader:
    _MANIFEST_FIELDS = {
        "schema_version", "dataset_id", "dataset_version", "profile", "guideline_version", "cases_file"
    }
    _CASE_FIELDS = {"case_id", "split", "documents", "annotation"}
    _DOCUMENT_FIELDS = {"document_id", "text", "metadata"}
    _ANNOTATION_FIELDS = {"guideline_version", "annotator_count", "adjudicated", "relevance"}
    _RELEVANCE_FIELDS = {"canonical_text", "grade"}

    def __init__(self, project_root: Path):
        self._project_root = project_root.resolve()

    def load(self, dataset_dir: Path, *, expected_profile: str) -> GoldDataset:
        if expected_profile not in SUPPORTED_PROFILES:
            raise GoldDatasetValidationError("Unsupported Gold Dataset profile")
        directory = dataset_dir.expanduser().resolve()
        if expected_profile == "SOLDIER_CONCERN" and self._inside_project(directory):
            raise GoldDatasetValidationError("SOLDIER_CONCERN Gold Dataset must be stored outside the repository")
        if not directory.is_dir():
            raise GoldDatasetValidationError("Gold Dataset directory does not exist")

        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            raise GoldDatasetValidationError("Gold Dataset manifest.json is missing")
        manifest_bytes = manifest_path.read_bytes()
        manifest = self._json_object(manifest_bytes, "manifest")
        self._exact_fields(manifest, self._MANIFEST_FIELDS, "manifest")
        if manifest["schema_version"] != SCHEMA_VERSION:
            raise GoldDatasetValidationError("Unsupported Gold Dataset schema_version")
        if manifest["profile"] != expected_profile:
            raise GoldDatasetValidationError("Gold Dataset profile does not match requested profile")

        dataset_id = self._identifier(manifest["dataset_id"], "dataset_id")
        dataset_version = self._identifier(manifest["dataset_version"], "dataset_version")
        guideline_version = self._identifier(manifest["guideline_version"], "guideline_version")
        cases_file = self._text(manifest["cases_file"], "cases_file")
        if Path(cases_file).name != cases_file or not cases_file.endswith(".jsonl"):
            raise GoldDatasetValidationError("Gold Dataset cases_file must be a local .jsonl filename")

        cases_path = (directory / cases_file).resolve()
        if cases_path.parent != directory or not cases_path.is_file():
            raise GoldDatasetValidationError("Gold Dataset cases file is missing or outside dataset directory")
        cases_bytes = cases_path.read_bytes()
        cases = self._load_cases(cases_bytes, expected_profile, guideline_version)
        if not cases:
            raise GoldDatasetValidationError("Gold Dataset must contain at least one case")
        if {case.split for case in cases} != set(SUPPORTED_SPLITS):
            raise GoldDatasetValidationError("Gold Dataset must contain both tuning and holdout splits")

        digest = hashlib.sha256(manifest_bytes + b"\0" + cases_bytes).hexdigest()
        return GoldDataset(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            profile=expected_profile,
            guideline_version=guideline_version,
            fingerprint=f"sha256:{digest}",
            cases=cases,
        )

    def _inside_project(self, path: Path) -> bool:
        try:
            path.relative_to(self._project_root)
            return True
        except ValueError:
            return False

    def _load_cases(self, data: bytes, profile: str, guideline_version: str) -> tuple[GoldCase, ...]:
        try:
            lines = data.decode("utf-8").splitlines()
        except UnicodeDecodeError as exc:
            raise GoldDatasetValidationError("Gold Dataset cases file must be UTF-8") from exc
        cases: list[GoldCase] = []
        seen: set[str] = set()
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise GoldDatasetValidationError(f"Gold Dataset case line {line_number} is invalid JSON") from exc
            case = self._case(payload, profile, guideline_version, line_number)
            if case.case_id in seen:
                raise GoldDatasetValidationError("Gold Dataset case_id values must be unique")
            seen.add(case.case_id)
            cases.append(case)
        return tuple(cases)

    def _case(self, payload: Any, profile: str, guideline_version: str, line_number: int) -> GoldCase:
        if not isinstance(payload, dict):
            raise GoldDatasetValidationError(f"Gold Dataset case line {line_number} must be an object")
        self._exact_fields(payload, self._CASE_FIELDS, f"case line {line_number}")
        case_id = self._identifier(payload["case_id"], "case_id")
        split = payload["split"]
        if split not in SUPPORTED_SPLITS:
            raise GoldDatasetValidationError("Gold Dataset case split must be tuning or holdout")
        documents = self._documents(payload["documents"], profile)
        annotation = payload["annotation"]
        if not isinstance(annotation, dict):
            raise GoldDatasetValidationError("Gold Dataset annotation must be an object")
        self._exact_fields(annotation, self._ANNOTATION_FIELDS, "annotation")
        case_guideline = self._identifier(annotation["guideline_version"], "guideline_version")
        if case_guideline != guideline_version:
            raise GoldDatasetValidationError("Gold Dataset case guideline_version must match manifest")
        annotator_count = annotation["annotator_count"]
        if isinstance(annotator_count, bool) or not isinstance(annotator_count, int) or annotator_count <= 0:
            raise GoldDatasetValidationError("Gold Dataset annotator_count must be an integer > 0")
        if not isinstance(annotation["adjudicated"], bool):
            raise GoldDatasetValidationError("Gold Dataset adjudicated must be boolean")
        relevance = self._relevance(annotation["relevance"])
        return GoldCase(
            case_id=case_id,
            split=split,
            documents=documents,
            guideline_version=case_guideline,
            annotator_count=annotator_count,
            adjudicated=annotation["adjudicated"],
            relevance=relevance,
        )

    def _documents(self, value: Any, profile: str) -> tuple[GoldDocument, ...]:
        if not isinstance(value, list) or not value:
            raise GoldDatasetValidationError("Gold Dataset case documents must be a non-empty array")
        documents: list[GoldDocument] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                raise GoldDatasetValidationError("Gold Dataset document must be an object")
            self._exact_fields(item, self._DOCUMENT_FIELDS, "document")
            document_id = self._identifier(item["document_id"], "document_id")
            if document_id in seen:
                raise GoldDatasetValidationError("Gold Dataset document_id values must be unique per case")
            seen.add(document_id)
            text = self._text(item["text"], "text")
            metadata = item["metadata"]
            if not isinstance(metadata, dict):
                raise GoldDatasetValidationError("Gold Dataset document metadata must be an object")
            self._profile_metadata(profile, metadata)
            documents.append(GoldDocument(document_id, text, dict(metadata)))
        if profile == "COURSE":
            self._course_boundaries(documents)
        return tuple(documents)

    @staticmethod
    def _profile_metadata(profile: str, metadata: dict[str, Any]) -> None:
        if profile == "SOLDIER_CONCERN":
            if metadata:
                raise GoldDatasetValidationError("SOLDIER_CONCERN Gold Dataset document metadata must be empty")
            return
        if profile == "MEDIA" and metadata.get("role") not in {"published_content", "audience_feedback"}:
            raise GoldDatasetValidationError("MEDIA Gold Dataset metadata.role is invalid")
        for key in ("section_id", "chunk_id"):
            if key in metadata and (not isinstance(metadata[key], str) or not metadata[key].strip()):
                raise GoldDatasetValidationError(f"Gold Dataset metadata.{key} must be a non-empty string")

    @staticmethod
    def _course_boundaries(documents: list[GoldDocument]) -> None:
        for key in ("section_id", "chunk_id"):
            present = [key in document.metadata for document in documents]
            if any(present) and not all(present):
                raise GoldDatasetValidationError(f"COURSE Gold Dataset {key} must be present consistently within a case")

    def _relevance(self, value: Any) -> dict[str, int]:
        if not isinstance(value, list) or not value:
            raise GoldDatasetValidationError("Gold Dataset relevance must be a non-empty array")
        result: dict[str, int] = {}
        for item in value:
            if not isinstance(item, dict):
                raise GoldDatasetValidationError("Gold Dataset relevance item must be an object")
            self._exact_fields(item, self._RELEVANCE_FIELDS, "relevance item")
            text = self._text(item["canonical_text"], "canonical_text")
            if text in result:
                raise GoldDatasetValidationError("Gold Dataset relevance canonical_text values must be unique")
            grade = item["grade"]
            if isinstance(grade, bool) or not isinstance(grade, int) or not 0 <= grade <= 3:
                raise GoldDatasetValidationError("Gold Dataset relevance grade must be an integer within [0, 3]")
            result[text] = grade
        return result

    @staticmethod
    def _json_object(data: bytes, label: str) -> dict[str, Any]:
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GoldDatasetValidationError(f"Gold Dataset {label} is not valid UTF-8 JSON") from exc
        if not isinstance(value, dict):
            raise GoldDatasetValidationError(f"Gold Dataset {label} must be a JSON object")
        return value

    @staticmethod
    def _exact_fields(value: dict[str, Any], expected: set[str], label: str) -> None:
        if set(value) != expected:
            raise GoldDatasetValidationError(f"Gold Dataset {label} fields do not match schema")

    @staticmethod
    def _identifier(value: Any, name: str) -> str:
        if not isinstance(value, str) or not _ID_RE.fullmatch(value):
            raise GoldDatasetValidationError(f"Gold Dataset {name} must be an opaque ASCII identifier")
        return value

    @staticmethod
    def _text(value: Any, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise GoldDatasetValidationError(f"Gold Dataset {name} must be a non-empty string")
        return value.strip()


class Phase10GoldEvaluator:
    async def evaluate_async(self, dataset: GoldDataset, service: Any, *, split: str) -> GoldEvaluationResult:
        cases = dataset.cases_for_split(split)
        if not cases:
            raise GoldDatasetValidationError("Requested Gold Dataset split is empty")
        if any(not case.adjudicated for case in cases):
            raise GoldDatasetValidationError("Gold evaluation requires adjudicated human annotations")

        metrics: list[RankingMetrics] = []
        scoring_versions: set[str] = set()
        model_versions: set[str] = set()
        for case in cases:
            result = await service.analyze_async([document.runtime_value() for document in case.documents])
            if result.profile != dataset.profile:
                raise RuntimeError("Profile service returned a mismatched profile")
            ranked = [item.canonical_text for item in result.keywords]
            metrics.append(self.ranking_metrics(ranked, case.relevance))
            scoring_versions.add(str(result.scoring_version))
            model_versions.add(str(result.model_version))

        return GoldEvaluationResult(
            profile=dataset.profile,
            split=split,
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.dataset_version,
            dataset_fingerprint=dataset.fingerprint,
            guideline_version=dataset.guideline_version,
            case_count=len(cases),
            metrics=RankingMetrics(
                precision_at_5=self._mean(item.precision_at_5 for item in metrics),
                precision_at_10=self._mean(item.precision_at_10 for item in metrics),
                recall_at_10=self._mean(item.recall_at_10 for item in metrics),
                ndcg_at_10=self._mean(item.ndcg_at_10 for item in metrics),
            ),
            scoring_versions=tuple(sorted(scoring_versions)),
            model_versions=tuple(sorted(model_versions)),
        )

    @classmethod
    def ranking_metrics(cls, ranked: list[str], relevance: dict[str, int]) -> RankingMetrics:
        relevant = {item for item, grade in relevance.items() if grade > 0}
        return RankingMetrics(
            precision_at_5=sum(item in relevant for item in ranked[:5]) / 5,
            precision_at_10=sum(item in relevant for item in ranked[:10]) / 10,
            recall_at_10=(sum(item in relevant for item in ranked[:10]) / len(relevant) if relevant else 1.0),
            ndcg_at_10=cls._ndcg(ranked, relevance, 10),
        )

    @classmethod
    def _ndcg(cls, ranked: list[str], relevance: dict[str, int], k: int) -> float:
        ideal = [item for item, _ in sorted(relevance.items(), key=lambda pair: (-pair[1], pair[0]))]
        denominator = cls._dcg(ideal, relevance, k)
        return cls._dcg(ranked, relevance, k) / denominator if denominator else 1.0

    @staticmethod
    def _dcg(ranked: list[str], relevance: dict[str, int], k: int) -> float:
        return sum((2 ** relevance.get(item, 0) - 1) / math.log2(index + 1) for index, item in enumerate(ranked[:k], 1))

    @staticmethod
    def _mean(values: Iterable[float]) -> float:
        items = tuple(float(value) for value in values)
        if not items:
            raise ValueError("Cannot average an empty metric sequence")
        return sum(items) / len(items)
