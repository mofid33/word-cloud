from __future__ import annotations

import hashlib
import unittest

from src.core.services.analysis.profile_config import load_profile_scoring_config
from src.core.services.candidate.candidate_extraction_service import CandidateExtractionService
from src.core.services.course.course_analysis_service import CourseAnalysisService
from src.core.services.media.media_analysis_service import MediaAnalysisService
from src.core.services.persian_text.persian_text_processor import PersianTextProcessor
from src.core.services.ranking.hybrid_ranking_service import HybridRankingService
from src.core.services.semantic.providers.embedding_provider import EmbeddingProvider
from src.core.services.semantic.providers.provider_metadata import SemanticProviderMetadata
from src.core.services.semantic.providers.reranker_provider import RerankerProvider
from src.core.services.semantic.semantic_analysis_service import SemanticAnalysisService
from src.core.services.soldier_concern.soldier_concern_analysis_service import (
    SoldierConcernAnalysisService,
)
from src.core.services.statistical.statistical_analysis_service import StatisticalAnalysisService
from src.core.services.topic.topic_analysis_service import TopicAnalysisService
from src.core.services.trend.trend_analysis_service import TrendAnalysisService
from src.infrastructure.providers.persian_nlp.persian_nlp_resource_provider import (
    PersianNlpResourceProvider,
)
from src.infrastructure.providers.topic.semantic_agglomerative_topic_model_provider import (
    SemanticAgglomerativeTopicModelProvider,
)
from src.infrastructure.utils.config_reader import ConfigReader


_METADATA = SemanticProviderMetadata(
    provider="phase10-test",
    provider_version="1",
    model_identifier="deterministic-test-provider",
    model_revision="1",
    device="cpu",
    configuration_fingerprint="phase10-test",
)


class _Embedding(EmbeddingProvider):
    @property
    def metadata(self):
        return _METADATA

    async def embed_async(self, texts):
        result = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vector = tuple((value - 127.5) / 127.5 for value in digest[:16])
            result.append(vector)
        return tuple(result)


class _Reranker(RerankerProvider):
    @property
    def metadata(self):
        return _METADATA

    async def rerank_async(self, query, candidates):
        return tuple(
            0.25 + (hashlib.sha256((query + "|" + item).encode("utf-8")).digest()[0] / 510.0)
            for item in candidates
        )


class _OverrideConfig:
    def __init__(self, base, overrides):
        self._base = base
        self._overrides = overrides

    def require(self, key):
        if key in self._overrides:
            return self._overrides[key]
        return self._base.require(key)


class AnalysisProfileTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = ConfigReader(env_type="development")
        resources = PersianNlpResourceProvider(self.config)
        processor = PersianTextProcessor(resources)
        extractor = CandidateExtractionService(self.config)
        statistical = StatisticalAnalysisService(self.config)
        embedding = _Embedding()
        semantic = SemanticAnalysisService(embedding, _Reranker(), self.config)
        ranking = HybridRankingService(embedding, self.config)
        topic_provider = SemanticAgglomerativeTopicModelProvider(
            embedding, self.config
        )
        topics = TopicAnalysisService(topic_provider, self.config)
        trends = TrendAnalysisService(self.config)

        self.course = CourseAnalysisService(
            processor, extractor, statistical, semantic, ranking, topics, self.config
        )
        self.soldier = SoldierConcernAnalysisService(
            processor, extractor, statistical, semantic, ranking, topics, self.config
        )
        self.media = MediaAnalysisService(
            processor, extractor, statistical, semantic, ranking, topics, trends, self.config
        )

    async def test_course_preserves_section_and_chunk_coverage_and_is_deterministic(self):
        documents = [
            {
                "document_id": "course-2",
                "text": "هوش مصنوعی تحلیل داده را تقویت می‌کند",
                "metadata": {"section_id": "s2", "chunk_id": "c2"},
            },
            {
                "document_id": "course-1",
                "text": "هوش مصنوعی و یادگیری ماشین کاربردی هستند",
                "metadata": {"section_id": "s1", "chunk_id": "c1"},
            },
        ]
        first = await self.course.analyze_async(documents)
        second = await self.course.analyze_async(documents)

        self.assertEqual(first, second)
        self.assertTrue(first.profile_result["boundaries"]["section_aware"])
        self.assertTrue(first.profile_result["boundaries"]["chunk_aware"])
        target = next(
            item for item in first.keywords
            if item.canonical_text == "هوش مصنوعی"
        )
        self.assertEqual(target.signals["section_coverage"], 1.0)
        self.assertEqual(target.signals["chunk_coverage"], 1.0)
        self.assertTrue(first.topics)
        self.assertEqual(
            [item["document_id"] for item in first.profile_result["topic_timeline"]],
            ["course-2", "course-1"],
        )
        self.assertEqual(
            first.profile_result["scoring"]["hybrid"][
                "diversity_candidate_pool_size"
            ],
            200,
        )

    async def test_course_rejects_partial_boundary_metadata(self):
        with self.assertRaisesRegex(ValueError, "section_id"):
            await self.course.analyze_async([
                {
                    "document_id": "a",
                    "text": "هوش مصنوعی",
                    "metadata": {"section_id": "s1"},
                },
                {
                    "document_id": "b",
                    "text": "یادگیری ماشین",
                    "metadata": {},
                },
            ])

    async def test_soldier_uses_cross_document_frequency_without_concatenating_documents(self):
        result = await self.soldier.analyze_async([
            {
                "document_id": "concern-b",
                "text": "کمبود اینترنت و کیفیت اینترنت",
                "metadata": {},
            },
            {
                "document_id": "concern-a",
                "text": "کمبود اینترنت مشکل مهمی است",
                "metadata": {},
            },
        ])
        target = next(
            item for item in result.keywords
            if item.canonical_text == "کمبود اینترنت"
        )
        self.assertEqual(target.signals["document_frequency"], 2)
        self.assertEqual(target.signals["document_coverage"], 1.0)
        self.assertTrue(result.profile_result["document_independence"])
        self.assertTrue(result.topics)
        self.assertTrue(
            all(
                document_id.startswith("sha256:")
                for topic in result.topics
                for document_id in topic.document_ids
            )
        )
        self.assertEqual(
            result.profile_result["scoring"]["hybrid"][
                "diversity_candidate_pool_size"
            ],
            50,
        )

    async def test_soldier_result_does_not_retain_raw_document_text(self):
        raw = "عبارت محرمانه بلند برای بررسی عدم نگهداری متن کامل"
        result = await self.soldier.analyze_async([
            {"document_id": "c1", "text": raw, "metadata": {}},
        ])
        self.assertNotIn(raw, repr(result))
        self.assertFalse(result.profile_result["privacy"]["raw_text_persisted"])
        self.assertFalse(result.profile_result["privacy"]["request_override_supported"])

    async def test_media_analyzes_content_and_audience_as_separate_corpora(self):
        result = await self.media.analyze_async([
            {
                "document_id": "p1",
                "text": "اقتصاد دیجیتال و هوش مصنوعی",
                "metadata": {"role": "published_content"},
            },
            {
                "document_id": "a1",
                "text": "کیفیت اینترنت و سرعت اینترنت",
                "metadata": {"role": "audience_feedback"},
            },
        ])
        roles = result.profile_result["roles"]
        self.assertEqual(roles["published_content"]["document_count"], 1)
        self.assertEqual(roles["audience_feedback"]["document_count"], 1)
        self.assertTrue(roles["published_content"]["keywords"])
        self.assertTrue(roles["audience_feedback"]["keywords"])
        self.assertTrue(result.profile_result["role_separation"])
        self.assertEqual(
            roles["published_content"]["hybrid"][
                "diversity_candidate_pool_size"
            ],
            50,
        )
        self.assertEqual(
            roles["audience_feedback"]["hybrid"][
                "diversity_candidate_pool_size"
            ],
            50,
        )
        self.assertIn(
            "normalized_engagement",
            result.profile_result["unsupported_signals"],
        )
        self.assertTrue(result.topics)
        self.assertIn("content_audience_gap", result.profile_result)

    async def test_media_rejects_unknown_role(self):
        with self.assertRaisesRegex(ValueError, "metadata.role"):
            await self.media.analyze_async([
                {
                    "document_id": "m1",
                    "text": "متن رسانه",
                    "metadata": {"role": "unknown"},
                }
            ])

    def test_profile_weight_validation_rejects_bool_and_invalid_sum(self):
        with self.assertRaises(ValueError):
            load_profile_scoring_config(
                _OverrideConfig(
                    self.config,
                    {"analysis_profiles.course.weights.frequency": True},
                ),
                profile_key="course",
                required_signals=(
                    "semantic_relevance",
                    "frequency",
                    "chunk_coverage",
                    "section_coverage",
                    "phrase_quality",
                ),
            )
        with self.assertRaisesRegex(ValueError, "sum to 1.0"):
            load_profile_scoring_config(
                _OverrideConfig(
                    self.config,
                    {"analysis_profiles.media.weights.coverage": 0.10},
                ),
                profile_key="media",
                required_signals=(
                    "mention_share",
                    "semantic_relevance",
                    "coverage",
                ),
            )


if __name__ == "__main__":
    unittest.main()
