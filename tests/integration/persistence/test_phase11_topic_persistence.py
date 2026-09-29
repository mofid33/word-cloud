from __future__ import annotations

import os
import unittest

from sqlalchemy.engine import make_url

from src.core.services.analysis.analysis_processor_service import AnalysisProcessorService
from src.core.services.analysis.profile_result import (
    ProfileKeywordResult,
    ProfileTopicKeywordResult,
    ProfileTopicResult,
    StructuredProfileResult,
)
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


class _Profile:
    async def analyze_async(self, documents):
        keyword = ProfileKeywordResult(
            text="هوش مصنوعی",
            canonical_text="هوش مصنوعی",
            rank=1,
            final_score=0.9,
            statistical_score=0.8,
            semantic_score=0.95,
            coverage=1.0,
            frequency=2,
            signals={},
        )
        topic = ProfileTopicResult(
            topic_id="topic-1",
            label="هوش مصنوعی",
            rank=1,
            prevalence=1.0,
            coverage=1.0,
            representative_keyphrases=(
                ProfileTopicKeywordResult(
                    canonical_text="هوش مصنوعی",
                    text="هوش مصنوعی",
                    rank=1,
                    relevance_score=0.98,
                ),
            ),
            document_ids=("d1",),
            metadata={
                "provider": "phase11-integration",
                "topic_scoring_version": "phase11-topic-baseline-v1",
            },
        )
        return StructuredProfileResult(
            profile="COURSE",
            keywords=(keyword,),
            metrics={"document_count": 1, "topic_count": 1},
            profile_result={"profile": "COURSE"},
            model_version="integration-model",
            scoring_version="integration-scoring",
            topics=(topic,),
        )


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
class Phase11TopicPersistenceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        url = _test_database_url()
        assert url is not None
        self.db_context = PsqlDbContext(_Config(url), _Vault())
        self.repository = WordCloudAnalysisRepository(self.db_context)
        async with self.db_context.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        async with self.db_context.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await self.db_context.dispose_async()

    async def test_processor_persists_topic_and_representative_keyword_atomically(self):
        pending = await self.repository.create_pending_async(
            analysis_type="COURSE",
            execution_mode="sync",
            documents=[
                {
                    "document_id": "d1",
                    "text": "هوش مصنوعی و یادگیری ماشین",
                    "metadata": {"section_id": "s1", "chunk_id": "c1"},
                }
            ],
        )
        profile = _Profile()
        processor = AnalysisProcessorService(
            profile,
            profile,
            profile,
            self.repository,
        )

        await processor.process_async(
            analysis_id=pending.id,
            analysis_type="COURSE",
            documents=[
                {
                    "document_id": "d1",
                    "text": "هوش مصنوعی و یادگیری ماشین",
                    "metadata": {"section_id": "s1", "chunk_id": "c1"},
                }
            ],
        )

        reloaded = await self.repository.get_aggregate_by_id_async(pending.id)
        assert reloaded is not None
        self.assertEqual(reloaded.status, "completed")
        self.assertEqual(len(reloaded.topics), 1)
        self.assertEqual(reloaded.topics[0].label, "هوش مصنوعی")
        self.assertEqual(
            reloaded.topics[0].metadata_json["logical_topic_id"],
            "topic-1",
        )
        self.assertEqual(reloaded.topics[0].metadata_json["document_ids"], ["d1"])
        self.assertEqual(len(reloaded.topics[0].keyword_links), 1)
        link = reloaded.topics[0].keyword_links[0]
        self.assertEqual(link.keyword.canonical_text, "هوش مصنوعی")
        self.assertAlmostEqual(link.relevance_score, 0.98)


if __name__ == "__main__":
    unittest.main()
