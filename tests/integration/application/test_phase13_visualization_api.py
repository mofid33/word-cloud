from __future__ import annotations

import os
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import httpx
from fastapi import FastAPI
from sqlalchemy.engine import make_url

from src.application.visualization.visualization_controller import (
    VisualizationController,
)
from src.core.services.visualization.visualization_service import VisualizationService
from src.infrastructure.context.sql_db.psql_dbcontext import Base, PsqlDbContext
from src.infrastructure.providers.visualization.visualization_settings import (
    VisualizationSettings,
)
from src.infrastructure.providers.visualization.word_cloud_visualization_renderer import (
    WordCloudVisualizationRenderer,
)
from src.infrastructure.repositories.analysis.word_cloud_analysis_repository import (
    WordCloudAnalysisRepository,
)


class _Config:
    def __init__(self, database_url: str):
        self.values = {
            "database.url": database_url,
            "visualization.width": 800,
            "visualization.height": 450,
            "visualization.maximum_words": 20,
            "visualization.background": "#FFFFFF",
            "visualization.font_family": "DejaVu Sans",
            "visualization.font_path": "@matplotlib/DejaVuSans.ttf",
            "visualization.random_seed": 17,
        }

    def require(self, key):
        return self.values[key]

    def get(self, key, default=None):
        return self.values.get(key, default)


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
    "TEST_DATABASE_URL is required for Phase 13 visualization integration tests",
)
class Phase13VisualizationApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        url = _test_database_url()
        assert url is not None
        config = _Config(url)
        with patch.dict(os.environ, {"DATABASE_URL": url}, clear=False):
            self.db_context = PsqlDbContext(config, _Vault())

        self.repository = WordCloudAnalysisRepository(self.db_context)
        settings = VisualizationSettings(config)
        renderer = WordCloudVisualizationRenderer(settings)
        service = VisualizationService(self.repository, renderer, settings)
        controller = VisualizationController(service)

        async with self.db_context.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

        app = FastAPI()
        app.include_router(controller.api(), prefix="/api/v1/visualization")
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        async with self.db_context.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await self.db_context.dispose_async()

    async def _create_analysis(self, *, analysis_type="COURSE", marker="safe input"):
        return await self.repository.create_pending_async(
            analysis_type=analysis_type,
            execution_mode="sync",
            documents=[
                {"document_id": "doc-1", "text": marker, "metadata": {}}
            ],
        )

    async def _complete(self, analysis_id: str, keyword: str = "یادگیری ماشین"):
        return await self.repository.save_result_atomically_async(
            analysis_id=analysis_id,
            keywords=[
                {
                    "keyword_id": "kw-1",
                    "text": keyword,
                    "canonical_text": keyword,
                    "rank": 1,
                    "final_score": 0.9,
                    "statistical_score": 0.8,
                    "semantic_score": 0.95,
                    "coverage": 1.0,
                    "frequency": 3,
                },
                {
                    "keyword_id": "kw-2",
                    "text": "پردازش زبان فارسی",
                    "canonical_text": "پردازش زبان فارسی",
                    "rank": 2,
                    "final_score": 0.7,
                    "statistical_score": 0.7,
                    "semantic_score": 0.8,
                    "coverage": 0.8,
                    "frequency": 2,
                },
            ],
            topics=[],
            topic_keywords=[],
            metrics={"document_count": 1},
            profile_result={"kind": "test"},
            model_version="phase13-test-model",
            scoring_version="phase13-test-scoring",
        )

    async def test_completed_analysis_returns_real_png_and_svg(self) -> None:
        analysis = await self._create_analysis()
        await self._complete(analysis.id)

        png = await self.client.get(f"/api/v1/visualization/{analysis.id}?format=png")
        self.assertEqual(png.status_code, 200)
        self.assertTrue(png.headers["content-type"].startswith("image/png"))
        self.assertTrue(png.content.startswith(b"\x89PNG\r\n\x1a\n"))

        svg = await self.client.get(f"/api/v1/visualization/{analysis.id}?format=svg")
        self.assertEqual(svg.status_code, 200)
        self.assertTrue(svg.headers["content-type"].startswith("image/svg+xml"))
        root = ET.fromstring(svg.content)
        self.assertTrue(root.tag.endswith("svg"))
        self.assertIn("یادگیری ماشین", svg.text)

    async def test_unknown_pending_processing_failed_and_invalid_format_contract(self) -> None:
        unknown = await self.client.get("/api/v1/visualization/missing?format=png")
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(unknown.json()["detail"]["code"], "analysis_not_found")

        pending_analysis = await self._create_analysis()
        pending = await self.client.get(
            f"/api/v1/visualization/{pending_analysis.id}?format=png"
        )
        self.assertEqual(pending.status_code, 409)
        self.assertEqual(
            pending.json()["detail"]["code"],
            "analysis_visualization_not_ready",
        )

        processing_analysis = await self._create_analysis()
        await self.repository.mark_processing_async(processing_analysis.id)
        processing = await self.client.get(
            f"/api/v1/visualization/{processing_analysis.id}?format=svg"
        )
        self.assertEqual(processing.status_code, 409)

        failed_analysis = await self._create_analysis()
        await self.repository.mark_failed_async(
            failed_analysis.id,
            error_code="processing_error",
            error_message="sanitized failure",
        )
        failed = await self.client.get(
            f"/api/v1/visualization/{failed_analysis.id}?format=png"
        )
        self.assertEqual(failed.status_code, 409)
        self.assertEqual(failed.json()["detail"]["code"], "analysis_failed")
        self.assertNotIn("sanitized failure", failed.text)

        invalid = await self.client.get(
            f"/api/v1/visualization/{pending_analysis.id}?format=pdf"
        )
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(
            invalid.json()["detail"]["code"],
            "unsupported_visualization_format",
        )

    async def test_soldier_raw_marker_never_enters_visualization(self) -> None:
        raw_marker = "PRIVATE-SOLDIER-RAW-MARKER-987654321"
        analysis = await self._create_analysis(
            analysis_type="SOLDIER_CONCERN",
            marker=raw_marker,
        )
        await self._complete(analysis.id, keyword="دغدغه معیشتی")

        aggregate = await self.repository.get_aggregate_by_id_async(analysis.id)
        assert aggregate is not None
        self.assertIsNone(aggregate.documents[0].raw_text)

        svg = await self.client.get(f"/api/v1/visualization/{analysis.id}?format=svg")
        png = await self.client.get(f"/api/v1/visualization/{analysis.id}?format=png")
        self.assertEqual(svg.status_code, 200)
        self.assertEqual(png.status_code, 200)
        self.assertNotIn(raw_marker, svg.text)
        self.assertNotIn(raw_marker.encode("utf-8"), png.content)


if __name__ == "__main__":
    unittest.main()
