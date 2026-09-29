from __future__ import annotations

from datetime import datetime, timezone
import unittest

from src.core.services.analysis.profile_result import (
    ProfileKeywordResult,
    ProfileTopicResult,
)
from src.core.services.semantic.providers.embedding_provider import EmbeddingProvider
from src.core.services.semantic.providers.provider_metadata import SemanticProviderMetadata
from src.core.services.topic.topic_analysis_service import (
    TopicAnalysisService,
    TopicDocument,
)
from src.core.services.trend.trend_analysis_service import (
    TrendAnalysisService,
    TrendDocument,
)
from src.infrastructure.providers.topic.semantic_agglomerative_topic_model_provider import (
    SemanticAgglomerativeTopicModelProvider,
)
from src.infrastructure.utils.config_reader import ConfigReader


_METADATA = SemanticProviderMetadata(
    provider="phase11-unit",
    provider_version="1",
    model_identifier="phase11-deterministic-embedding",
    model_revision="1",
    device="cpu",
    configuration_fingerprint="phase11-unit",
)


class _Embedding(EmbeddingProvider):
    @property
    def metadata(self):
        return _METADATA

    async def embed_async(self, texts):
        result = []
        for text in texts:
            if "هوش" in text or "یادگیری" in text:
                result.append((1.0, 0.05))
            elif "اینترنت" in text or "شبکه" in text:
                result.append((0.05, 1.0))
            else:
                result.append((0.7, 0.7))
        return tuple(result)


class _InvalidEmbedding(EmbeddingProvider):
    @property
    def metadata(self):
        return _METADATA

    async def embed_async(self, texts):
        return tuple((float("nan"), 1.0) for _ in texts)


class _OverrideConfig:
    def __init__(self, base, overrides):
        self._base = base
        self._overrides = overrides

    def require(self, key):
        if key in self._overrides:
            return self._overrides[key]
        return self._base.require(key)


class Phase11TopicTrendTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = ConfigReader(env_type="development")

    async def test_semantic_provider_clusters_documents_deterministically(self):
        provider = SemanticAgglomerativeTopicModelProvider(
            _Embedding(),
            self.config,
        )
        from src.core.services.topic.providers.topic_model_provider import (
            TopicModelDocument,
        )

        documents = (
            TopicModelDocument("d3", "کیفیت اینترنت"),
            TopicModelDocument("d1", "هوش مصنوعی"),
            TopicModelDocument("d2", "یادگیری ماشین"),
        )
        first = await provider.analyze_topics_async(documents)
        second = await provider.analyze_topics_async(tuple(reversed(documents)))

        self.assertEqual(first, second)
        self.assertEqual(len(first.clusters), 2)
        memberships = {frozenset(item.document_ids) for item in first.clusters}
        self.assertIn(frozenset({"d1", "d2"}), memberships)
        self.assertIn(frozenset({"d3"}), memberships)
        self.assertEqual(first.metadata.provider, "semantic_agglomerative")

    async def test_provider_rejects_non_finite_model_output(self):
        provider = SemanticAgglomerativeTopicModelProvider(
            _InvalidEmbedding(),
            self.config,
        )
        from src.core.services.topic.providers.topic_model_provider import (
            TopicModelDocument,
        )

        with self.assertRaisesRegex(RuntimeError, "non-finite"):
            await provider.analyze_topics_async(
                (TopicModelDocument("d1", "هوش مصنوعی"),)
            )

    async def test_topic_analysis_builds_representation_prevalence_coverage_and_timeline(self):
        provider = SemanticAgglomerativeTopicModelProvider(
            _Embedding(),
            self.config,
        )
        service = TopicAnalysisService(provider, self.config)
        keywords = (
            ProfileKeywordResult(
                text="هوش مصنوعی",
                canonical_text="هوش مصنوعی",
                rank=1,
                final_score=0.9,
                statistical_score=0.8,
                semantic_score=0.9,
                coverage=2 / 3,
                frequency=2,
                signals={},
            ),
            ProfileKeywordResult(
                text="کیفیت اینترنت",
                canonical_text="کیفیت اینترنت",
                rank=2,
                final_score=0.8,
                statistical_score=0.7,
                semantic_score=0.8,
                coverage=1 / 3,
                frequency=1,
                signals={},
            ),
        )
        result = await service.analyze_async(
            documents=(
                TopicDocument("d1", "هوش مصنوعی", 1, section_id="s1"),
                TopicDocument("d2", "یادگیری هوش مصنوعی", 2, section_id="s1"),
                TopicDocument("d3", "کیفیت اینترنت شبکه", 3, section_id="s2"),
            ),
            keywords=keywords,
            build_timeline=True,
        )

        self.assertEqual(len(result.topics), 2)
        self.assertEqual(len(result.timeline), 3)
        self.assertEqual(
            [point.document_id for point in result.timeline],
            ["d1", "d2", "d3"],
        )
        ai_topic = next(
            item
            for item in result.topics
            if set(item.document_ids) == {"d1", "d2"}
        )
        self.assertAlmostEqual(ai_topic.prevalence, 2 / 3)
        self.assertAlmostEqual(ai_topic.coverage, 0.5)
        self.assertEqual(
            ai_topic.representative_keyphrases[0].canonical_text,
            "هوش مصنوعی",
        )

    async def test_soldier_style_ids_do_not_require_raw_text_in_results(self):
        provider = SemanticAgglomerativeTopicModelProvider(
            _Embedding(),
            self.config,
        )
        service = TopicAnalysisService(provider, self.config)
        raw = "متن محرمانه سرباز درباره کیفیت اینترنت"
        result = await service.analyze_async(
            documents=(
                TopicDocument("sha256:abc", raw, 1),
                TopicDocument("sha256:def", "اینترنت شبکه", 2),
            ),
            keywords=(
                ProfileKeywordResult(
                    text="اینترنت",
                    canonical_text="اینترنت",
                    rank=1,
                    final_score=0.8,
                    statistical_score=0.7,
                    semantic_score=0.8,
                    coverage=1.0,
                    frequency=2,
                    signals={},
                ),
            ),
        )
        self.assertNotIn(raw, repr(result))
        self.assertTrue(
            all(
                document_id.startswith("sha256:")
                for topic in result.topics
                for document_id in topic.document_ids
            )
        )

    async def test_trend_classifies_emerging_and_declining(self):
        service = TrendAnalysisService(self.config)
        documents = (
            TrendDocument("p1", datetime(2026, 9, 16, tzinfo=timezone.utc)),
            TrendDocument("p2", datetime(2026, 9, 18, tzinfo=timezone.utc)),
            TrendDocument("c1", datetime(2026, 9, 24, tzinfo=timezone.utc)),
            TrendDocument("c2", datetime(2026, 9, 28, tzinfo=timezone.utc)),
        )
        topics = (
            ProfileTopicResult(
                topic_id="emerging",
                label="هوش مصنوعی",
                rank=1,
                prevalence=0.75,
                coverage=0.75,
                representative_keyphrases=(),
                document_ids=("p1", "c1", "c2"),
            ),
            ProfileTopicResult(
                topic_id="declining",
                label="موضوع قدیمی",
                rank=2,
                prevalence=0.25,
                coverage=0.25,
                representative_keyphrases=(),
                document_ids=("p2",),
            ),
        )
        result = service.analyze(documents=documents, topics=topics)
        by_id = {item.topic_id: item for item in result.trends}

        self.assertTrue(result.available)
        self.assertEqual(by_id["emerging"].classification, "emerging")
        self.assertEqual(by_id["declining"].classification, "declining")
        self.assertGreater(by_id["emerging"].growth, 0)
        self.assertLess(by_id["declining"].growth, 0)


    async def test_phase11_config_validation_rejects_bool_nan_inf_and_range_errors(self):
        bad_topic_values = (True, float("nan"), float("inf"), 1.1)
        for value in bad_topic_values:
            with self.subTest(topic_similarity=value):
                with self.assertRaises(ValueError):
                    SemanticAgglomerativeTopicModelProvider(
                        _Embedding(),
                        _OverrideConfig(
                            self.config,
                            {"topic_model.similarity_threshold": value},
                        ),
                    )

        with self.assertRaises(ValueError):
            SemanticAgglomerativeTopicModelProvider(
                _Embedding(),
                _OverrideConfig(
                    self.config,
                    {"topic_model.maximum_topics": True},
                ),
            )

        for key, value in (
            ("trend_analysis.growth_threshold", True),
            ("trend_analysis.growth_threshold", float("nan")),
            ("trend_analysis.growth_threshold", float("inf")),
            ("trend_analysis.growth_threshold", 1.1),
            ("trend_analysis.minimum_prevalence", -0.1),
            ("trend_analysis.window_days", True),
            ("trend_analysis.minimum_documents_per_window", 0),
        ):
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    TrendAnalysisService(
                        _OverrideConfig(self.config, {key: value})
                    )

    async def test_trend_is_unavailable_without_minimum_evidence(self):
        service = TrendAnalysisService(self.config)
        result = service.analyze(
            documents=(
                TrendDocument(
                    "only",
                    datetime(2026, 9, 28, tzinfo=timezone.utc),
                ),
            ),
            topics=(),
        )
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "insufficient_documents_per_window")


if __name__ == "__main__":
    unittest.main()
