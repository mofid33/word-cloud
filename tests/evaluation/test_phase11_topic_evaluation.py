from __future__ import annotations

import json
from pathlib import Path
import unittest

from src.core.services.semantic.providers.embedding_provider import EmbeddingProvider
from src.core.services.semantic.providers.provider_metadata import SemanticProviderMetadata
from src.core.services.topic.providers.topic_model_provider import TopicModelDocument
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


class Phase11TopicEvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_topic_coherence_and_diversity_regression(self):
        fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(fixture["status"], "NOT_PRODUCTION_GOLD")

        provider = SemanticAgglomerativeTopicModelProvider(
            _SemanticFixtureEmbedding(),
            ConfigReader(env_type="development"),
        )
        documents = tuple(
            TopicModelDocument(item["document_id"], item["text"])
            for item in fixture["documents"]
        )
        result = await provider.analyze_topics_async(documents)

        expected = {
            item["document_id"]: item["expected_topic"]
            for item in fixture["documents"]
        }
        coherence_scores = []
        represented_expected_topics = set()
        for cluster in result.clusters:
            labels = [expected[document_id] for document_id in cluster.document_ids]
            dominant = max(set(labels), key=labels.count)
            coherence_scores.append(labels.count(dominant) / len(labels))
            represented_expected_topics.add(dominant)

        coherence = sum(coherence_scores) / len(coherence_scores)
        diversity = len(represented_expected_topics) / 2
        evidence = {
            "status": "NOT_PRODUCTION_GOLD",
            "topic_count": len(result.clusters),
            "topic_coherence_proxy": coherence,
            "topic_diversity": diversity,
            "provider": result.metadata.provider,
        }
        print("PHASE11_TOPIC_EVALUATION=" + json.dumps(evidence, ensure_ascii=False, sort_keys=True))

        self.assertGreaterEqual(
            coherence,
            fixture["minimum_coherence_proxy"],
        )
        self.assertGreaterEqual(
            diversity,
            fixture["minimum_topic_diversity"],
        )


if __name__ == "__main__":
    unittest.main()
