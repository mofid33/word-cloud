from __future__ import annotations

import json
from pathlib import Path
import unittest

from src.core.services.analysis.profile_result import ProfileKeywordResult
from src.core.services.semantic.providers.embedding_provider import EmbeddingProvider
from src.core.services.semantic.providers.provider_metadata import SemanticProviderMetadata
from src.core.services.topic.topic_analysis_service import (
    TopicAnalysisService,
    TopicDocument,
)
from src.infrastructure.providers.topic.semantic_agglomerative_topic_model_provider import (
    SemanticAgglomerativeTopicModelProvider,
)
from src.infrastructure.utils.config_reader import ConfigReader


_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "phase11_topic_regression.json"
)

_METADATA = SemanticProviderMetadata(
    provider="phase11-evaluation",
    provider_version="1",
    model_identifier="semantic-regression-fixture",
    model_revision="1",
    device="cpu",
    configuration_fingerprint="phase11-evaluation",
)


class _SemanticFixtureEmbedding(EmbeddingProvider):
    @property
    def metadata(self):
        return _METADATA

    async def embed_async(self, texts):
        vectors = []
        for text in texts:
            if "هوش" in text or "یادگیری" in text or "داده" in text:
                vectors.append((1.0, 0.02))
            elif "اینترنت" in text or "شبکه" in text:
                vectors.append((0.02, 1.0))
            else:
                vectors.append((0.7, 0.7))
        return tuple(vectors)


def _keyword(text: str, rank: int) -> ProfileKeywordResult:
    return ProfileKeywordResult(
        text=text,
        canonical_text=text,
        rank=rank,
        final_score=max(0.1, 1.0 - (rank * 0.05)),
        statistical_score=0.8,
        semantic_score=0.9,
        coverage=0.5,
        frequency=1,
        signals={},
    )


class Phase11TopicEvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_semantic_topic_coherence_and_keyphrase_diversity(self):
        fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(fixture["status"], "NOT_PRODUCTION_GOLD")

        config = ConfigReader(env_type="development")
        provider = SemanticAgglomerativeTopicModelProvider(
            _SemanticFixtureEmbedding(),
            config,
        )
        service = TopicAnalysisService(provider, config)
        documents = tuple(
            TopicDocument(
                document_id=item["document_id"],
                text=item["text"],
                order=index,
            )
            for index, item in enumerate(fixture["documents"], start=1)
        )
        keywords = tuple(
            _keyword(text, rank)
            for rank, text in enumerate(
                (
                    "هوش مصنوعی",
                    "یادگیری ماشین",
                    "تحلیل داده",
                    "کیفیت اینترنت",
                    "پایداری شبکه",
                    "سرعت اینترنت",
                ),
                start=1,
            )
        )

        result = await service.analyze_async(
            documents=documents,
            keywords=keywords,
            build_timeline=False,
        )
        self.assertTrue(result.topics)

        semantic_coherence = (
            sum(float(topic.metadata["cohesion"]) for topic in result.topics)
            / len(result.topics)
        )
        representative_terms = [
            keyword.canonical_text
            for topic in result.topics
            for keyword in topic.representative_keyphrases
        ]
        keyphrase_diversity = (
            len(set(representative_terms)) / len(representative_terms)
            if representative_terms
            else 0.0
        )

        expected = {
            item["document_id"]: item["expected_topic"]
            for item in fixture["documents"]
        }
        cluster_purity_values = []
        for topic in result.topics:
            labels = [expected[document_id] for document_id in topic.document_ids]
            dominant = max(set(labels), key=labels.count)
            cluster_purity_values.append(labels.count(dominant) / len(labels))
        cluster_purity = (
            sum(cluster_purity_values) / len(cluster_purity_values)
        )

        evidence = {
            "status": "NOT_PRODUCTION_GOLD",
            "topic_count": len(result.topics),
            "semantic_topic_coherence": semantic_coherence,
            "keyphrase_topic_diversity": keyphrase_diversity,
            "cluster_purity_diagnostic": cluster_purity,
            "provider": result.provider_metadata["provider"],
        }
        print(
            "PHASE11_TOPIC_EVALUATION="
            + json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        )

        self.assertGreaterEqual(
            semantic_coherence,
            fixture["minimum_semantic_topic_coherence"],
        )
        self.assertGreaterEqual(
            keyphrase_diversity,
            fixture["minimum_keyphrase_topic_diversity"],
        )
        self.assertGreater(cluster_purity, 0.0)
        self.assertTrue(
            all(topic.representative_keyphrases for topic in result.topics)
        )


if __name__ == "__main__":
    unittest.main()
