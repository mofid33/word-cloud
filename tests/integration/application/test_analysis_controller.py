import asyncio
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import HTTPException

from src.application.analysis.analysis_controller import AnalysisController
from src.application.analysis.dtos.analysis_dto import AnalysisRequestDto
from src.core.services.analysis.analysis_execution_policy_service import (
    AnalysisExecutionPolicyService,
)
from src.core.services.analysis.analysis_service import AnalysisService


class _Config:
    def __init__(self):
        self._values = {
            "analysis.limits.max_documents_per_analysis": 5,
            "analysis.limits.max_characters_per_document": 10,
            "analysis.limits.max_total_characters_per_analysis": 20,
            "analysis.sync_threshold.max_documents": 2,
            "analysis.sync_threshold.max_total_characters": 8,
        }

    def require(self, key: str) -> int:
        return self._values[key]


class _Repository:
    def __init__(self):
        self.analysis = None

    async def create_pending_async(self, **kwargs):
        now = datetime.now(UTC)
        self.analysis = SimpleNamespace(
            id="analysis-1",
            analysis_type=kwargs["analysis_type"],
            status="pending",
            execution_mode=kwargs["execution_mode"],
            reference=kwargs.get("reference"),
            model_version=None,
            scoring_version=None,
            created_at=now,
            started_at=None,
            completed_at=None,
            error_code=None,
            error_message=None,
            keywords=[],
            topics=[],
            metrics={},
            profile_result={},
        )
        return self.analysis

    async def get_aggregate_by_id_async(self, analysis_id: str):
        if self.analysis is None or self.analysis.id != analysis_id:
            return None
        return self.analysis


class _NoopProcessor:
    async def process_async(self, **kwargs):
        return None


class AnalysisControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        policy = AnalysisExecutionPolicyService(_Config())
        self.repository = _Repository()
        self.controller = AnalysisController(
            AnalysisService(policy, _NoopProcessor(), self.repository)
        )
        self.router = self.controller.api()

    def _endpoint(self, path: str, method: str):
        for route in self.router.routes:
            if (
                getattr(route, "path", None) == path
                and method in (getattr(route, "methods", None) or set())
            ):
                return route.endpoint
        self.fail(f"{method} {path} route was not discovered")

    def test_validate_endpoint_success(self) -> None:
        payload = AnalysisRequestDto.model_validate(
            {
                "analysis_type": "COURSE",
                "execution_mode": "auto",
                "documents": [
                    {"document_id": "doc-1", "text": "متن"}
                ],
            }
        )

        response = asyncio.run(
            self._endpoint("/validate", "POST")(payload)
        )

        self.assertTrue(response.valid)
        self.assertEqual(response.analysis_type.value, "COURSE")
        self.assertEqual(response.execution_mode.value, "auto")
        self.assertEqual(response.resolved_execution_mode.value, "sync")
        self.assertEqual(response.document_count, 1)

    def test_domain_validation_error_maps_to_422(self) -> None:
        payload = AnalysisRequestDto.model_validate(
            {
                "analysis_type": "COURSE",
                "execution_mode": "auto",
                "documents": [
                    {"document_id": "same", "text": "الف"},
                    {"document_id": "same", "text": "ب"},
                ],
            }
        )

        with self.assertRaises(HTTPException) as context:
            asyncio.run(
                self._endpoint("/validate", "POST")(payload)
            )

        self.assertEqual(context.exception.status_code, 422)
        self.assertEqual(
            context.exception.detail["code"],
            "duplicate_document_id",
        )

    def test_hard_input_limit_maps_to_413_without_echoing_raw_text(self) -> None:
        raw_text = "sensitive-text"
        payload = AnalysisRequestDto.model_validate(
            {
                "analysis_type": "SOLDIER_CONCERN",
                "execution_mode": "async",
                "documents": [
                    {"document_id": "concern-1", "text": raw_text},
                ],
            }
        )

        with self.assertRaises(HTTPException) as context:
            asyncio.run(
                self._endpoint("/validate", "POST")(payload)
            )

        self.assertEqual(context.exception.status_code, 413)
        self.assertEqual(
            context.exception.detail["code"],
            "max_document_characters_exceeded",
        )
        self.assertNotIn(
            raw_text,
            context.exception.detail["message"],
        )

    def test_explicit_sync_over_threshold_maps_to_422(self) -> None:
        payload = AnalysisRequestDto.model_validate(
            {
                "analysis_type": "COURSE",
                "execution_mode": "sync",
                "documents": [
                    {"document_id": "a", "text": "12345"},
                    {"document_id": "b", "text": "6789"},
                ],
            }
        )

        with self.assertRaises(HTTPException) as context:
            asyncio.run(
                self._endpoint("/validate", "POST")(payload)
            )

        self.assertEqual(context.exception.status_code, 422)
        self.assertEqual(
            context.exception.detail["code"],
            "sync_threshold_exceeded",
        )

    def test_create_endpoint_returns_persisted_pending_resource(self) -> None:
        payload = AnalysisRequestDto.model_validate(
            {
                "analysis_type": "COURSE",
                "execution_mode": "auto",
                "reference": "course-1",
                "documents": [
                    {"document_id": "doc-1", "text": "متن"},
                ],
            }
        )

        response = asyncio.run(
            self._endpoint("", "POST")(payload)
        )

        self.assertEqual(response.analysis_id, "analysis-1")
        self.assertEqual(response.status.value, "pending")
        self.assertEqual(response.execution_mode.value, "sync")

    def test_completed_result_maps_to_response_dto(self) -> None:
        now = datetime.now(UTC)
        keyword = SimpleNamespace(
            text="هوش مصنوعی",
            canonical_text="هوش مصنوعی",
            rank=1,
            final_score=0.9,
            statistical_score=0.7,
            semantic_score=0.95,
            coverage=1.0,
            frequency=3,
        )
        link = SimpleNamespace(
            keyword=keyword,
            rank=1,
            relevance_score=0.95,
        )
        topic = SimpleNamespace(
            id="topic-1",
            label="فناوری",
            rank=1,
            prevalence=0.8,
            coverage=1.0,
            keyword_links=[link],
        )
        self.repository.analysis = SimpleNamespace(
            id="analysis-1",
            analysis_type="COURSE",
            status="completed",
            execution_mode="sync",
            reference="course-1",
            model_version="model-v1",
            scoring_version="score-v1",
            created_at=now,
            started_at=now,
            completed_at=now,
            error_code=None,
            error_message=None,
            keywords=[keyword],
            topics=[topic],
            metrics={"document_count": 1},
            profile_result={"kind": "course"},
        )

        response = asyncio.run(
            self._endpoint("/{analysis_id}/result", "GET")(
                "analysis-1"
            )
        )

        self.assertEqual(response.analysis.status.value, "completed")
        self.assertIsNone(response.analysis.error)
        self.assertEqual(response.keywords[0].rank, 1)
        self.assertEqual(
            response.topics[0].keywords[0].text,
            "هوش مصنوعی",
        )
        self.assertEqual(response.metrics["document_count"], 1)

    def test_failed_status_maps_internal_error_to_nested_error_contract(self) -> None:
        now = datetime.now(UTC)
        self.repository.analysis = SimpleNamespace(
            id="analysis-1",
            analysis_type="COURSE",
            status="failed",
            execution_mode="sync",
            reference=None,
            model_version=None,
            scoring_version=None,
            created_at=now,
            started_at=now,
            completed_at=now,
            error_code="analysis_processing_failed",
            error_message="Analysis processing failed",
            keywords=[],
            topics=[],
            metrics={},
            profile_result={},
        )

        response = asyncio.run(
            self._endpoint("/{analysis_id}", "GET")("analysis-1")
        )

        self.assertEqual(response.status.value, "failed")
        self.assertIsNotNone(response.error)
        self.assertEqual(
            response.error.code,
            "analysis_processing_failed",
        )
        body = response.model_dump(mode="json")
        self.assertNotIn("error_code", body)
        self.assertNotIn("error_message", body)

    def test_status_not_found_maps_to_404(self) -> None:
        with self.assertRaises(HTTPException) as context:
            asyncio.run(
                self._endpoint("/{analysis_id}", "GET")("missing")
            )

        self.assertEqual(context.exception.status_code, 404)
        self.assertEqual(
            context.exception.detail["code"],
            "analysis_not_found",
        )

    def test_pending_result_maps_to_409(self) -> None:
        payload = AnalysisRequestDto.model_validate(
            {
                "analysis_type": "COURSE",
                "execution_mode": "sync",
                "documents": [
                    {"document_id": "doc-1", "text": "متن"},
                ],
            }
        )
        asyncio.run(self._endpoint("", "POST")(payload))

        with self.assertRaises(HTTPException) as context:
            asyncio.run(
                self._endpoint("/{analysis_id}/result", "GET")(
                    "analysis-1"
                )
            )

        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(
            context.exception.detail["code"],
            "analysis_result_not_ready",
        )


if __name__ == "__main__":
    unittest.main()
