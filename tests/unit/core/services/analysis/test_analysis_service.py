import asyncio
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace

from src.core.services.analysis.analysis_execution_policy_service import (
    AnalysisExecutionPolicyError,
    AnalysisExecutionPolicyService,
)
from src.core.services.analysis.analysis_service import (
    AnalysisNotFoundError,
    AnalysisRequestValidationError,
    AnalysisResultUnavailableError,
    AnalysisService,
)


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
        self.last_create = None

    async def create_pending_async(self, **kwargs):
        self.last_create = kwargs
        now = datetime.now(UTC)
        self.analysis = SimpleNamespace(
            id="analysis-1",
            analysis_type=kwargs["analysis_type"],
            status="pending",
            execution_mode=kwargs["execution_mode"],
            reference=(
                None
                if kwargs["analysis_type"] == "SOLDIER_CONCERN"
                else kwargs.get("reference")
            ),
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


class AnalysisServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        policy = AnalysisExecutionPolicyService(_Config())
        self.repository = _Repository()
        self.service = AnalysisService(policy, self.repository)

    def test_rejects_duplicate_document_ids(self) -> None:
        async def run() -> None:
            with self.assertRaises(AnalysisRequestValidationError) as context:
                await self.service.validate_async(
                    analysis_type="COURSE",
                    execution_mode="auto",
                    documents=[
                        {"document_id": "same", "text": "الف", "metadata": {}},
                        {"document_id": "same", "text": "ب", "metadata": {}},
                    ],
                )
            self.assertEqual(context.exception.code, "duplicate_document_id")

        asyncio.run(run())

    def test_media_requires_supported_document_role(self) -> None:
        async def run() -> None:
            with self.assertRaises(AnalysisRequestValidationError) as context:
                await self.service.validate_async(
                    analysis_type="MEDIA",
                    execution_mode="auto",
                    documents=[
                        {
                            "document_id": "doc-1",
                            "text": "متن",
                            "metadata": {},
                        }
                    ],
                )
            self.assertEqual(
                context.exception.code,
                "media_document_role_required",
            )

        asyncio.run(run())

    def test_returns_request_metrics_without_retaining_raw_text(self) -> None:
        async def run() -> None:
            result = await self.service.validate_async(
                analysis_type="SOLDIER_CONCERN",
                execution_mode="sync",
                documents=[
                    {"document_id": "a", "text": "abc", "metadata": {}},
                    {"document_id": "b", "text": "12345", "metadata": {}},
                ],
            )
            self.assertEqual(result.document_count, 2)
            self.assertEqual(result.total_characters, 8)
            self.assertEqual(result.resolved_execution_mode, "sync")
            self.assertFalse(hasattr(result, "documents"))
            self.assertFalse(hasattr(result, "text"))

        asyncio.run(run())

    def test_auto_mode_is_resolved_by_execution_policy(self) -> None:
        result = asyncio.run(
            self.service.validate_async(
                analysis_type="COURSE",
                execution_mode="auto",
                documents=[
                    {"document_id": "a", "text": "abc", "metadata": {}},
                ],
            )
        )

        self.assertEqual(result.execution_mode, "auto")
        self.assertEqual(result.resolved_execution_mode, "sync")

    def test_rejects_raw_text_embedded_inside_metadata_value(self) -> None:
        raw_text = "متن محرمانه"
        with self.assertRaises(AnalysisRequestValidationError) as context:
            asyncio.run(
                self.service.validate_async(
                    analysis_type="SOLDIER_CONCERN",
                    execution_mode="sync",
                    documents=[
                        {
                            "document_id": "concern-1",
                            "text": raw_text,
                            "metadata": {
                                "nested": {
                                    "copy": f"prefix {raw_text} suffix"
                                }
                            },
                        }
                    ],
                )
            )

        self.assertEqual(
            context.exception.code,
            "raw_text_repeated_in_metadata",
        )
        self.assertNotIn(raw_text, context.exception.message)

    def test_rejects_raw_text_embedded_inside_metadata_key(self) -> None:
        raw_text = "PRIVATE-CONTENT"
        with self.assertRaises(AnalysisRequestValidationError) as context:
            asyncio.run(
                self.service.validate_async(
                    analysis_type="SOLDIER_CONCERN",
                    execution_mode="sync",
                    documents=[
                        {
                            "document_id": "concern-1",
                            "text": raw_text,
                            "metadata": {
                                f"prefix-{raw_text}-suffix": "safe"
                            },
                        }
                    ],
                )
            )

        self.assertEqual(
            context.exception.code,
            "raw_text_repeated_in_metadata",
        )
        self.assertNotIn(raw_text, context.exception.message)

    def test_execution_policy_error_is_not_swallowed(self) -> None:
        with self.assertRaises(AnalysisExecutionPolicyError) as context:
            asyncio.run(
                self.service.validate_async(
                    analysis_type="COURSE",
                    execution_mode="async",
                    documents=[
                        {
                            "document_id": "long",
                            "text": "x" * 11,
                            "metadata": {},
                        },
                    ],
                )
            )

        self.assertEqual(
            context.exception.code,
            "max_document_characters_exceeded",
        )

    def test_create_persists_real_pending_resource_with_resolved_mode(self) -> None:
        result = asyncio.run(
            self.service.create_async(
                analysis_type="COURSE",
                execution_mode="auto",
                documents=[
                    {"document_id": "a", "text": "abc", "metadata": {}},
                ],
                reference="course-1",
                options={"language": "fa"},
            )
        )

        self.assertEqual(result.analysis_id, "analysis-1")
        self.assertEqual(result.status, "pending")
        self.assertEqual(result.execution_mode, "sync")
        self.assertEqual(
            self.repository.last_create["execution_mode"],
            "sync",
        )
        self.assertFalse(
            self.repository.last_create["persist_raw_text"]
        )

    def test_completed_result_maps_structured_json_groups(self) -> None:
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

        result = asyncio.run(
            self.service.get_result_async("analysis-1")
        )

        self.assertEqual(result.analysis.status, "completed")
        self.assertIsNone(result.analysis.error)
        self.assertEqual(result.keywords[0].rank, 1)
        self.assertEqual(result.topics[0].keywords[0].text, "هوش مصنوعی")
        self.assertEqual(result.metrics["document_count"], 1)
        self.assertEqual(result.profile_result["kind"], "course")

    def test_get_status_unknown_analysis_error_is_sanitized(self) -> None:
        raw_marker = "TOP-SECRET-AS-ANALYSIS-ID"
        with self.assertRaises(AnalysisNotFoundError) as context:
            asyncio.run(self.service.get_status_async(raw_marker))

        self.assertEqual(
            context.exception.code,
            "analysis_not_found",
        )
        self.assertNotIn(raw_marker, str(context.exception))
        self.assertNotIn(raw_marker, context.exception.message)
        self.assertFalse(hasattr(context.exception, "analysis_id"))

    def test_result_is_conflict_until_analysis_is_completed(self) -> None:
        asyncio.run(
            self.service.create_async(
                analysis_type="COURSE",
                execution_mode="sync",
                documents=[
                    {"document_id": "a", "text": "abc", "metadata": {}},
                ],
            )
        )

        with self.assertRaises(AnalysisResultUnavailableError) as context:
            asyncio.run(self.service.get_result_async("analysis-1"))

        self.assertEqual(
            context.exception.code,
            "analysis_result_not_ready",
        )


if __name__ == "__main__":
    unittest.main()
