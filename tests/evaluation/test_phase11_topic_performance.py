from __future__ import annotations

import json
import os
import statistics
import time
import tracemalloc
import unittest

from src.core.services.semantic.providers.embedding_provider import EmbeddingProvider
from src.core.services.semantic.providers.provider_metadata import SemanticProviderMetadata
from src.core.services.topic.providers.topic_model_provider import TopicModelDocument
from src.infrastructure.providers.semantic.transformers_embedding_provider import (
    TransformersEmbeddingProvider,
)
from src.infrastructure.providers.topic.semantic_agglomerative_topic_model_provider import (
    SemanticAgglomerativeTopicModelProvider,
)
from src.infrastructure.utils.config_reader import ConfigReader


_METADATA = SemanticProviderMetadata(
    provider="phase11-performance-fixture",
    provider_version="1",
    model_identifier="deterministic-scaling-fixture",
    model_revision="1",
    device="cpu",
    configuration_fingerprint="phase11-performance",
)


class _ScalingEmbedding(EmbeddingProvider):
    @property
    def metadata(self):
        return _METADATA

    async def embed_async(self, texts):
        vectors = []
        for index, text in enumerate(texts):
            if "هوش" in text:
                vectors.append((1.0, 0.02, (index % 7) / 100.0))
            else:
                vectors.append((0.02, 1.0, (index % 7) / 100.0))
        return tuple(vectors)


class Phase11TopicPerformanceTests(unittest.IsolatedAsyncioTestCase):
    async def _measure(self, provider, documents, iterations=3):
        durations = []
        tracemalloc.start()
        try:
            for _ in range(iterations):
                started = time.perf_counter()
                result = await provider.analyze_topics_async(documents)
                durations.append(time.perf_counter() - started)
                self.assertTrue(result.clusters)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        ordered = sorted(durations)
        p50 = statistics.median(ordered)
        p95_index = max(
            0,
            min(len(ordered) - 1, round(0.95 * (len(ordered) - 1))),
        )
        return {
            "iterations": iterations,
            "document_count": len(documents),
            "p50_seconds": p50,
            "p95_seconds": ordered[p95_index],
            "documents_per_second": (
                len(documents) * iterations / sum(durations)
            ),
            "peak_python_bytes": peak,
        }

    async def test_topic_algorithm_scaling_baseline_not_production_model(self):
        config = ConfigReader(env_type="development")
        provider = SemanticAgglomerativeTopicModelProvider(
            _ScalingEmbedding(),
            config,
        )
        evidence = []
        for size in (25, 100):
            documents = tuple(
                TopicModelDocument(
                    f"d-{index:04d}",
                    (
                        "هوش مصنوعی یادگیری ماشین"
                        if index % 2 == 0
                        else "کیفیت اینترنت شبکه ارتباط"
                    ),
                )
                for index in range(size)
            )
            item = await self._measure(provider, documents)
            item["status"] = "NOT_PRODUCTION_MODEL_PERFORMANCE"
            evidence.append(item)

        print(
            "PHASE11_TOPIC_ALGORITHM_PERFORMANCE="
            + json.dumps(evidence, sort_keys=True)
        )
        self.assertEqual([item["document_count"] for item in evidence], [25, 100])

    @unittest.skipUnless(
        os.getenv("RUN_PHASE11_REAL_MODEL_BENCHMARK") == "1",
        "Set RUN_PHASE11_REAL_MODEL_BENCHMARK=1 to run the real embedding benchmark",
    )
    async def test_real_embedding_topic_performance_baseline(self):
        config = ConfigReader(env_type="development")
        embedding = TransformersEmbeddingProvider(config)
        provider = SemanticAgglomerativeTopicModelProvider(embedding, config)
        documents = tuple(
            TopicModelDocument(
                f"real-{index:03d}",
                (
                    "هوش مصنوعی و یادگیری ماشین برای تحلیل داده"
                    if index % 2 == 0
                    else "کیفیت اینترنت و پایداری شبکه و ارتباط"
                ),
            )
            for index in range(20)
        )
        evidence = await self._measure(provider, documents, iterations=2)
        evidence["status"] = "REAL_CONFIGURED_EMBEDDING_PROVIDER"
        evidence["model_identifier"] = embedding.metadata.model_identifier
        print(
            "PHASE11_REAL_MODEL_PERFORMANCE="
            + json.dumps(evidence, sort_keys=True)
        )


if __name__ == "__main__":
    unittest.main()
