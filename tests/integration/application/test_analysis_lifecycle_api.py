from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from sqlalchemy.engine import make_url

from src.application.analysis.analysis_controller import AnalysisController
from src.core.services.analysis.analysis_execution_policy_service import (
    AnalysisExecutionPolicyService,
)
from src.core.services.analysis.analysis_service import AnalysisService
from src.infrastructure.context.sql_db.psql_dbcontext import Base, PsqlDbContext
from src.infrastructure.repositories.analysis.word_cloud_analysis_repository import (
    WordCloudAnalysisRepository,
)


class _Config:
    def __init__(self, database_url: str):
        self._values = {
            "database.url": database_url,
            "analysis.limits.max_documents_per_analysis": 5000,
            "analysis.limits.max_characters_per_document": 500000,
            "analysis.limits.max_total_characters_per_analysis": 10000000,
            "analysis.sync_threshold.max_documents": 20,
            "analysis.sync_threshold.max_total_characters": 100000,
        }

    def require(self, key: str):
        return self._values[key]


class _Vault:
    enabled = False


def _test_database_url() -> str | None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        return None
    database_name = make_url(url).database or ""
    if "test" not in database_name.lower():
        raise RuntimeError(
            "TEST_DATABASE_URL must point to a database whose name contains 'test'"
        )
    return url


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for lifecycle API integration tests",
)
class AnalysisLifecycleApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        url = _test_database_url()
        assert url is not None
        config = _Config(url)

        with patch.dict(
            os.environ,
            {"DATABASE_URL": url},
            clear=False,
        ):
            self.db_context = PsqlDbContext(config, _Vault())

        self.repository = WordCloudAnalysisRepository(self.db_context)
        policy = AnalysisExecutionPolicyService(config)
        service = AnalysisService(policy, self.repository)
        controller = AnalysisController(service)

        async with self.db_context.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

        app = FastAPI()
        app.include_router(
            controller.api(),
            prefix="/api/v1/analysis",
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        async with self.db_context.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await self.db_context.dispose_async()

    async def test_create_status_and_pending_result_contract(self) -> None:
        create_response = await self.client.post(
            "/api/v1/analysis",
            json={
                "analysis_type": "COURSE",
                "execution_mode": "auto",
                "reference": "course-1",
                "documents": [
                    {
                        "document_id": "doc-1",
                        "text": "متن فارسی",
                    }
                ],
            },
        )

        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        analysis_id = created["analysis_id"]
        self.assertEqual(created["status"], "pending")
        self.assertEqual(created["execution_mode"], "sync")
        self.assertIsNone(created["error"])
        self.assertNotIn("error_code", created)
        self.assertNotIn("error_message", created)

        status_response = await self.client.get(
            f"/api/v1/analysis/{analysis_id}"
        )
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(
            status_response.json()["analysis_id"],
            analysis_id,
        )

        result_response = await self.client.get(
            f"/api/v1/analysis/{analysis_id}/result"
        )
        self.assertEqual(result_response.status_code, 409)
        self.assertEqual(
            result_response.json()["detail"]["code"],
            "analysis_result_not_ready",
        )

    async def test_completed_result_is_returned_as_structured_json(self) -> None:
        create_response = await self.client.post(
            "/api/v1/analysis",
            json={
                "analysis_type": "COURSE",
                "execution_mode": "sync",
                "documents": [
                    {
                        "document_id": "doc-result",
                        "text": "متن فارسی",
                    }
                ],
            },
        )
        self.assertEqual(create_response.status_code, 201)
        analysis_id = create_response.json()["analysis_id"]

        await self.repository.save_result_atomically_async(
            analysis_id=analysis_id,
            keywords=[
                {
                    "keyword_id": "kw-1",
                    "text": "هوش مصنوعی",
                    "canonical_text": "هوش مصنوعی",
                    "rank": 1,
                    "final_score": 0.9,
                    "statistical_score": 0.7,
                    "semantic_score": 0.95,
                    "coverage": 1.0,
                    "frequency": 3,
                }
            ],
            topics=[
                {
                    "topic_id": "topic-1",
                    "label": "فناوری",
                    "rank": 1,
                    "prevalence": 0.8,
                    "coverage": 1.0,
                }
            ],
            topic_keywords=[
                {
                    "topic_id": "topic-1",
                    "keyword_id": "kw-1",
                    "rank": 1,
                    "relevance_score": 0.95,
                }
            ],
            metrics={"document_count": 1},
            profile_result={"kind": "course"},
            model_version="test-model",
            scoring_version="test-scoring",
        )

        result_response = await self.client.get(
            f"/api/v1/analysis/{analysis_id}/result"
        )

        self.assertEqual(result_response.status_code, 200)
        result = result_response.json()
        self.assertEqual(result["analysis"]["status"], "completed")
        self.assertIsNone(result["analysis"]["error"])
        self.assertNotIn("error_code", result["analysis"])
        self.assertNotIn("error_message", result["analysis"])
        self.assertEqual(result["keywords"][0]["rank"], 1)
        self.assertEqual(
            result["topics"][0]["keywords"][0]["text"],
            "هوش مصنوعی",
        )
        self.assertEqual(result["metrics"]["document_count"], 1)
        self.assertEqual(result["profile_result"]["kind"], "course")

    async def test_soldier_create_does_not_persist_free_form_request_fields(
        self,
    ) -> None:
        raw_marker = "PRIVATE-SOLDIER-CONTENT"
        create_response = await self.client.post(
            "/api/v1/analysis",
            json={
                "analysis_type": "SOLDIER_CONCERN",
                "execution_mode": "sync",
                "reference": raw_marker,
                "options": {"private": raw_marker},
                "documents": [
                    {
                        "document_id": raw_marker,
                        "text": "متن حساس",
                        "metadata": {"note": "metadata-sensitive"},
                    }
                ],
            },
        )

        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        self.assertIsNone(created["reference"])

        aggregate = await self.repository.get_aggregate_by_id_async(
            created["analysis_id"]
        )
        assert aggregate is not None
        self.assertIsNone(aggregate.reference)
        self.assertEqual(aggregate.options, {})
        self.assertEqual(aggregate.documents[0].metadata_json, {})
        self.assertTrue(
            aggregate.documents[0].document_id.startswith("sha256:")
        )
        self.assertNotEqual(
            aggregate.documents[0].document_id,
            raw_marker,
        )


if __name__ == "__main__":
    unittest.main()
