from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.core.services.analysis.profile_config import ProfileScoringConfig
from src.core.services.candidate.candidate_extraction_service import CandidateExtractionService
from src.core.services.course.course_analysis_service import CourseAnalysisService
from src.core.services.course.course_document_segmentation_service import CourseDocumentSegmentationService
from src.core.services.persian_text.persian_text_processor import PersianTextProcessor
from src.core.services.ranking.hybrid_ranking_service import HybridRankingService
from src.core.services.semantic.semantic_analysis_service import SemanticAnalysisService
from src.core.services.statistical.statistical_analysis_service import StatisticalAnalysisService
from src.core.services.topic.topic_analysis_service import TopicAnalysisService
from src.infrastructure.providers.persian_nlp.persian_nlp_resource_provider import PersianNlpResourceProvider
from src.infrastructure.providers.topic.semantic_agglomerative_topic_model_provider import (
    SemanticAgglomerativeTopicModelProvider,
)
from src.infrastructure.utils.config_reader import ConfigReader
from tests.evaluation.course_candidate_evaluation import (
    CourseCandidateCase,
    CourseCandidateDataset,
    CourseCandidateDatasetLoader,
    CourseCandidateDocument,
    CourseCandidateEvaluationError,
    CourseCandidateTuningEngine,
    CourseCandidateWeightTuner,
    PreparedCourseCandidateCase,
    REVIEW_SCHEMA_VERSION,
    REVIEW_STATUS,
    _transfer_candidates,
)
from tests.evaluation.phase10_test_support import (
    DeterministicEmbedding,
    DeterministicReranker,
)


def _write_materialized(path: Path) -> dict[str, object]:
    tuning_text = "هوش مصنوعی یادگیری ماشین"
    holdout_text = "پردازش زبان فارسی"
    rows = [
        {
            "source_unit_id": "unit-tuning",
            "case_group_id": "case-tuning",
            "split": "tuning",
            "domain": "test-domain",
            "section_title": "بخش آموزش",
            "character_count": len(tuning_text),
            "text_sha256": hashlib.sha256(
                tuning_text.encode("utf-8")
            ).hexdigest(),
            "permanent_url": "https://example.invalid/tuning",
            "attribution_url": "https://example.invalid/tuning",
            "text": tuning_text,
        },
        {
            "source_unit_id": "unit-holdout",
            "case_group_id": "case-holdout",
            "split": "holdout",
            "domain": "test-domain",
            "section_title": "بخش ارزیابی",
            "character_count": len(holdout_text),
            "text_sha256": hashlib.sha256(
                holdout_text.encode("utf-8")
            ).hexdigest(),
            "permanent_url": "https://example.invalid/holdout",
            "attribution_url": "https://example.invalid/holdout",
            "text": holdout_text,
        },
    ]
    raw = "".join(
        json.dumps(row, ensure_ascii=False) + "\n"
        for row in rows
    ).encode("utf-8")
    path.write_bytes(raw)
    return {
        "schema_version": "phase10-course-materialization-verification-v1",
        "source_manifest_id": "test-course-source",
        "source_manifest_version": "1.0.0",
        "materialized_file_sha256": hashlib.sha256(raw).hexdigest(),
        "source_unit_count": 2,
        "tuning_unit_count": 1,
        "holdout_unit_count": 1,
        "case_count": 2,
        "tuning_case_count": 1,
        "holdout_case_count": 1,
        "verified_on": "2026-09-29",
        "note": "test",
    }


def _write_review(
    path: Path,
    source_sha: str,
) -> dict[str, object]:
    annotation = {
        "grade": 3,
        "evidence_section": "section",
        "origin": "candidate",
        "decision": "APPROVE",
    }
    payload = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "status": REVIEW_STATUS,
        "source_materialized_sha256": source_sha,
        "basis": {},
        "rubric": {},
        "summary": {},
        "cases": [
            {
                "case_id": "case-tuning",
                "split": "tuning",
                "domain": "test-domain",
                "annotations": [
                    {
                        **annotation,
                        "canonical_text": "هوش مصنوعی",
                    }
                ],
            },
            {
                "case_id": "case-holdout",
                "split": "holdout",
                "domain": "test-domain",
                "annotations": [
                    {
                        **annotation,
                        "canonical_text": "پردازش زبان",
                    }
                ],
            },
        ],
    }
    raw = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    path.write_bytes(raw)
    return {
        "schema_version": "phase10-course-model-review-verification-v1",
        "review_status": REVIEW_STATUS,
        "source_materialized_sha256": source_sha,
        "review_file_sha256": hashlib.sha256(raw).hexdigest(),
        "case_count": 2,
        "final_annotation_count": 2,
        "tuning_case_count": 1,
        "holdout_case_count": 1,
        "note": "test",
    }


class CourseCandidateDatasetTests(unittest.TestCase):
    def test_verified_external_candidate_loads_and_preserves_frozen_split(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            project = root_path / "project"
            project.mkdir()
            external = root_path / "external"
            external.mkdir()

            materialized = external / "materialized.jsonl"
            source_verification = _write_materialized(materialized)
            source_verification_path = (
                root_path / "source-verification.json"
            )
            source_verification_path.write_text(
                json.dumps(source_verification),
                encoding="utf-8",
            )

            review = external / "review.json"
            review_verification = _write_review(
                review,
                source_verification[
                    "materialized_file_sha256"
                ],
            )
            review_verification_path = (
                root_path / "review-verification.json"
            )
            review_verification_path.write_text(
                json.dumps(review_verification),
                encoding="utf-8",
            )

            dataset = CourseCandidateDatasetLoader(
                project,
                source_verification_path=source_verification_path,
                review_verification_path=review_verification_path,
            ).load(
                materialized,
                review,
            )

            self.assertEqual(
                len(dataset.cases_for_split("tuning")),
                1,
            )
            self.assertEqual(
                len(dataset.cases_for_split("holdout")),
                1,
            )
            self.assertEqual(
                dataset.review_status,
                REVIEW_STATUS,
            )
            self.assertEqual(
                dataset.cases_for_split("tuning")[
                    0
                ].documents[0].section_id,
                "unit-tuning",
            )

    def test_review_hash_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            project = root_path / "project"
            project.mkdir()
            external = root_path / "external"
            external.mkdir()

            materialized = external / "materialized.jsonl"
            source_verification = _write_materialized(
                materialized
            )
            source_verification_path = (
                root_path / "source-verification.json"
            )
            source_verification_path.write_text(
                json.dumps(source_verification),
                encoding="utf-8",
            )

            review = external / "review.json"
            review_verification = _write_review(
                review,
                source_verification[
                    "materialized_file_sha256"
                ],
            )
            review_verification_path = (
                root_path / "review-verification.json"
            )
            review_verification_path.write_text(
                json.dumps(review_verification),
                encoding="utf-8",
            )
            review.write_text(
                review.read_text(encoding="utf-8")
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                CourseCandidateEvaluationError,
                "SHA-256",
            ):
                CourseCandidateDatasetLoader(
                    project,
                    source_verification_path=(
                        source_verification_path
                    ),
                    review_verification_path=(
                        review_verification_path
                    ),
                ).load(
                    materialized,
                    review,
                )

    def test_materialized_file_inside_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            project = root_path / "project"
            project.mkdir()

            materialized = project / "materialized.jsonl"
            source_verification = _write_materialized(
                materialized
            )
            source_verification_path = (
                root_path / "source-verification.json"
            )
            source_verification_path.write_text(
                json.dumps(source_verification),
                encoding="utf-8",
            )
            review = root_path / "review.json"
            review_verification = _write_review(
                review,
                source_verification[
                    "materialized_file_sha256"
                ],
            )
            review_verification_path = (
                root_path / "review-verification.json"
            )
            review_verification_path.write_text(
                json.dumps(review_verification),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                CourseCandidateEvaluationError,
                "outside the repository",
            ):
                CourseCandidateDatasetLoader(
                    project,
                    source_verification_path=(
                        source_verification_path
                    ),
                    review_verification_path=(
                        review_verification_path
                    ),
                ).load(
                    materialized,
                    review,
                )


class CourseWeightSearchTests(unittest.TestCase):
    def test_transfer_search_keeps_chunk_weight_fixed_and_simplex_valid(self):
        baseline = {
            "semantic_relevance": 0.35,
            "frequency": 0.20,
            "chunk_coverage": 0.15,
            "section_coverage": 0.15,
            "phrase_quality": 0.15,
        }
        candidates = _transfer_candidates(
            baseline,
            deltas=(0.05, 0.10),
        )
        self.assertGreater(
            len(candidates),
            0,
        )
        for weights in candidates:
            self.assertAlmostEqual(
                sum(weights.values()),
                1.0,
            )
            self.assertEqual(
                weights["chunk_coverage"],
                baseline["chunk_coverage"],
            )


class _FakeEngine:
    def __init__(self):
        self.prepared_case_ids: list[str] = []
        self._baseline = ProfileScoringConfig(
            scoring_version="test",
            maximum_results=25,
            diversity_candidate_pool_size=200,
            weights={
                "semantic_relevance": 0.35,
                "frequency": 0.20,
                "chunk_coverage": 0.15,
                "section_coverage": 0.15,
                "phrase_quality": 0.15,
            },
        )

    @property
    def baseline_config(self):
        return self._baseline

    async def prepare_case_async(self, case):
        self.prepared_case_ids.append(
            case.case_id
        )
        return PreparedCourseCandidateCase(
            case=case,
            statistics=(),
            semantic=SimpleNamespace(),
            candidate_ids=frozenset(
                case.relevance
            ),
        )

    async def rank_prepared_async(
        self,
        prepared,
        weights,
    ):
        return tuple(
            prepared.case.relevance
        )

    def model_version(
        self,
        prepared_cases,
    ):
        return ("test-model",)


class CourseCandidateWeightTunerTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_tuner_never_prepares_or_ranks_holdout(self):
        tuning = CourseCandidateCase(
            case_id="tuning-case",
            split="tuning",
            domain="test",
            documents=(
                CourseCandidateDocument(
                    "doc-t",
                    "هوش مصنوعی",
                    "doc-t",
                ),
            ),
            relevance={"هوش مصنوعی": 3},
        )
        holdout = CourseCandidateCase(
            case_id="holdout-case",
            split="holdout",
            domain="test",
            documents=(
                CourseCandidateDocument(
                    "doc-h",
                    "پردازش زبان",
                    "doc-h",
                ),
            ),
            relevance={"پردازش زبان": 3},
        )
        dataset = CourseCandidateDataset(
            source_materialized_sha256="source",
            review_sha256="review",
            review_status=REVIEW_STATUS,
            cases=(tuning, holdout),
        )
        engine = _FakeEngine()
        result = await CourseCandidateWeightTuner(
            engine
        ).tune_async(dataset)

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
        self.assertEqual(
            result.selected.weights,
            result.baseline.weights,
        )


class CourseCandidateTuningEngineParityTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_baseline_prepared_ranking_matches_real_course_service(self):
        config = ConfigReader(
            env_type="development"
        )
        resource_provider = (
            PersianNlpResourceProvider(config)
        )
        processor = PersianTextProcessor(
            resource_provider
        )
        extractor = CandidateExtractionService(
            config
        )
        statistical = StatisticalAnalysisService(
            config
        )
        embedding = DeterministicEmbedding()
        semantic = SemanticAnalysisService(
            embedding,
            DeterministicReranker(),
            config,
        )
        ranking = HybridRankingService(
            embedding,
            config,
        )
        course_segmentation = CourseDocumentSegmentationService(
            config
        )
        topics = TopicAnalysisService(
            SemanticAgglomerativeTopicModelProvider(
                embedding,
                config,
            ),
            config,
        )
        service = CourseAnalysisService(
            processor,
            extractor,
            statistical,
            semantic,
            ranking,
            course_segmentation,
            config,
            topic_analysis_service=topics,
        )
        engine = CourseCandidateTuningEngine(
            processor,
            extractor,
            statistical,
            semantic,
            ranking,
            config,
        )
        case = CourseCandidateCase(
            case_id="parity",
            split="tuning",
            domain="test",
            documents=(
                CourseCandidateDocument(
                    "section-1",
                    (
                        "هوش مصنوعی و یادگیری ماشین "
                        "در آموزش کاربرد دارند."
                    ),
                    "section-1",
                ),
                CourseCandidateDocument(
                    "section-2",
                    (
                        "یادگیری ماشین یکی از روش های "
                        "هوش مصنوعی است."
                    ),
                    "section-2",
                ),
            ),
            relevance={"هوش مصنوعی": 3},
        )

        prepared = (
            await engine.prepare_case_async(
                case
            )
        )
        engine_ranked = (
            await engine.rank_prepared_async(
                prepared,
                dict(
                    engine.baseline_config.weights
                ),
            )
        )
        service_result = (
            await service.analyze_async(
                [
                    document.runtime_value()
                    for document
                    in case.documents
                ]
            )
        )
        service_ranked = tuple(
            item.canonical_text
            for item in service_result.keywords
        )

        self.assertEqual(
            engine_ranked,
            service_ranked,
        )


if __name__ == "__main__":
    unittest.main()
