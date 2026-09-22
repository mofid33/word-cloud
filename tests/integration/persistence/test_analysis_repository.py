from __future__ import annotations

import os
import unittest

from sqlalchemy import text
from sqlalchemy.engine import make_url

from src.infrastructure.context.sql_db.psql_dbcontext import Base, PsqlDbContext
from src.infrastructure.models.analysis_document import AnalysisDocument
from src.infrastructure.models.analysis_keyword import AnalysisKeyword
from src.infrastructure.models.analysis_topic import AnalysisTopic
from src.infrastructure.models.analysis_topic_keyword import AnalysisTopicKeyword
from src.infrastructure.models.word_cloud_analysis import WordCloudAnalysis
from src.infrastructure.repositories.analysis.word_cloud_analysis_repository import (
    WordCloudAnalysisRepository,
)


class _Config:
    def __init__(self, url: str):
        self._url = url

    def require(self, key: str) -> str:
        if key != "database.url":
            raise KeyError(key)
        return self._url


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
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class AnalysisRepositoryIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        url = _test_database_url()
        assert url is not None
        self.db_context = PsqlDbContext(_Config(url), _Vault())
        self.repository = WordCloudAnalysisRepository(self.db_context)

        async with self.db_context.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self) -> None:
        async with self.db_context.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await self.db_context.dispose_async()

    async def test_create_pending_does_not_persist_raw_text_by_default(self) -> None:
        analysis = await self.repository.create_pending_async(
            analysis_type="COURSE",
            execution_mode="sync",
            documents=[
                {
                    "document_id": "doc-1",
                    "text": "متن محرمانه",
                    "metadata": {"section": "1"},
                }
            ],
        )

        self.assertEqual(analysis.status, "pending")
        self.assertEqual(len(analysis.documents), 1)
        self.assertIsNone(analysis.documents[0].raw_text)
        self.assertEqual(analysis.documents[0].metadata_json["section"], "1")

    async def test_soldier_raw_text_persistence_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "forbidden"):
            await self.repository.create_pending_async(
                analysis_type="SOLDIER_CONCERN",
                execution_mode="sync",
                documents=[
                    {
                        "document_id": "concern-1",
                        "text": "raw soldier concern",
                        "metadata": {},
                    }
                ],
                persist_raw_text=True,
            )

    async def test_result_graph_is_persisted_atomically(self) -> None:
        pending = await self.repository.create_pending_async(
            analysis_type="MEDIA",
            execution_mode="sync",
            documents=[
                {
                    "document_id": "content-1",
                    "text": "content",
                    "metadata": {"role": "published_content"},
                }
            ],
        )

        completed = await self.repository.save_result_atomically_async(
            analysis_id=pending.id,
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
                    "metadata": {},
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
            profile_result={"kind": "media"},
            model_version="test-model",
            scoring_version="test-scoring",
        )

        self.assertEqual(completed.status, "completed")
        self.assertEqual(len(completed.keywords), 1)
        self.assertEqual(len(completed.topics), 1)
        self.assertEqual(len(completed.topics[0].keyword_links), 1)
        self.assertEqual(completed.metrics["document_count"], 1)

    async def test_failed_result_write_rolls_back_entire_graph(self) -> None:
        pending = await self.repository.create_pending_async(
            analysis_type="COURSE",
            execution_mode="sync",
            documents=[
                {"document_id": "doc-1", "text": "content", "metadata": {}}
            ],
        )

        with self.assertRaisesRegex(ValueError, "Unknown keyword_id"):
            await self.repository.save_result_atomically_async(
                analysis_id=pending.id,
                keywords=[
                    {
                        "keyword_id": "kw-1",
                        "text": "کلیدواژه",
                        "canonical_text": "کلیدواژه",
                        "rank": 1,
                        "final_score": 0.8,
                        "statistical_score": 0.8,
                        "semantic_score": 0.8,
                        "coverage": 1.0,
                        "frequency": 1,
                    }
                ],
                topics=[
                    {
                        "topic_id": "topic-1",
                        "label": "موضوع",
                        "rank": 1,
                        "prevalence": 1.0,
                        "coverage": 1.0,
                    }
                ],
                topic_keywords=[
                    {
                        "topic_id": "topic-1",
                        "keyword_id": "missing-keyword",
                        "rank": 1,
                        "relevance_score": 1.0,
                    }
                ],
                metrics={},
                profile_result={},
                model_version="test-model",
                scoring_version="test-scoring",
            )

        reloaded = await self.repository.get_aggregate_by_id_async(pending.id)
        assert reloaded is not None
        self.assertEqual(reloaded.status, "pending")
        self.assertEqual(reloaded.keywords, [])
        self.assertEqual(reloaded.topics, [])

        async with self.db_context.session() as session:
            count = await session.scalar(
                text(
                    "SELECT COUNT(*) FROM analysis_keyword "
                    "WHERE analysis_id = :analysis_id"
                ),
                {"analysis_id": pending.id},
            )
            self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
