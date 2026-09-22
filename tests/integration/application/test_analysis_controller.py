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


class AnalysisControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        policy = AnalysisExecutionPolicyService(_Config())
        self.repository = _Repository()
        self.controller = AnalysisController(
            AnalysisService(policy, self.repository)
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
