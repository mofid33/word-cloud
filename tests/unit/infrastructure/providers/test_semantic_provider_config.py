from __future__ import annotations

import asyncio
import unittest

from src.infrastructure.providers.semantic.transformers_embedding_provider import (
    TransformersEmbeddingProvider,
)
from src.infrastructure.providers.semantic.transformers_reranker_provider import (
    TransformersRerankerProvider,
)


class _Config:
    def __init__(self, overrides=None):
        self.values = {
            "semantic.embedding.model_identifier": "embedding-model",
            "semantic.embedding.model_revision": None,
            "semantic.embedding.batch_size": 2,
            "semantic.embedding.max_length": 128,
            "semantic.reranker.model_identifier": "reranker-model",
            "semantic.reranker.model_revision": None,
            "semantic.reranker.batch_size": 2,
            "semantic.reranker.max_length": 128,
            "models.allow_remote_downloads": False,
            "models.trust_remote_code": False,
            "models.cache_dir": ".cache/models",
            "device.type": "cpu",
            "device.cuda_device_index": 0,
            "batch.max_size": 4,
        }
        self.values.update(overrides or {})

    def require(self, key):
        if key not in self.values:
            raise KeyError(key)
        return self.values[key]

    def get(self, key, default=None):
        return self.values.get(key, default)


class _UnavailableCuda:
    @staticmethod
    def is_available():
        return False

    @staticmethod
    def device_count():
        return 0


class _TorchWithoutCuda:
    cuda = _UnavailableCuda()


class SemanticProviderConfigTests(unittest.IsolatedAsyncioTestCase):
    def test_cpu_metadata_and_fingerprint_are_stable(self):
        first = TransformersEmbeddingProvider(_Config())
        second = TransformersEmbeddingProvider(_Config())
        self.assertEqual(first.metadata.device, "cpu")
        self.assertEqual(
            first.metadata.configuration_fingerprint,
            second.metadata.configuration_fingerprint,
        )

    def test_resolved_model_revision_is_exposed_in_metadata(self):
        provider = TransformersEmbeddingProvider(_Config())
        provider._resolved_revision = "commit-sha"
        self.assertEqual(provider.metadata.model_revision, "commit-sha")

    def test_trust_remote_code_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "trust_remote_code"):
            TransformersRerankerProvider(_Config({"models.trust_remote_code": True}))

    def test_invalid_device_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "device.type"):
            TransformersEmbeddingProvider(_Config({"device.type": "mps"}))

    def test_configured_cuda_unavailable_fails_explicitly(self):
        provider = TransformersEmbeddingProvider(_Config({"device.type": "cuda"}))
        with self.assertRaisesRegex(RuntimeError, "CUDA is configured but unavailable"):
            provider._resolve_device(_TorchWithoutCuda())

    def test_embedding_batch_size_cannot_exceed_global_max(self):
        with self.assertRaisesRegex(ValueError, "batch.max_size"):
            TransformersEmbeddingProvider(
                _Config({"semantic.embedding.batch_size": 5})
            )

    def test_reranker_batch_size_cannot_exceed_global_max(self):
        with self.assertRaisesRegex(ValueError, "batch.max_size"):
            TransformersRerankerProvider(
                _Config({"semantic.reranker.batch_size": 5})
            )

    def test_embedding_batches_preserve_order(self):
        provider = TransformersEmbeddingProvider(_Config())
        provider._ensure_loaded = lambda: None
        calls = []

        def encode(batch):
            calls.append(tuple(batch))
            return [[float(int(item))] for item in batch]

        provider._encode_batch = encode
        result = provider._embed_sync(("1", "2", "3", "4", "5"))
        self.assertEqual(calls, [("1", "2"), ("3", "4"), ("5",)])
        self.assertEqual(result, ((1.0,), (2.0,), (3.0,), (4.0,), (5.0,)))

    def test_reranker_batches_preserve_order(self):
        provider = TransformersRerankerProvider(_Config())
        provider._ensure_loaded = lambda: None
        calls = []

        def score(query, batch):
            calls.append(tuple(batch))
            return [float(int(item)) / 10 for item in batch]

        provider._score_batch = score
        result = provider._rerank_sync("q", ("1", "2", "3", "4", "5"))
        self.assertEqual(calls, [("1", "2"), ("3", "4"), ("5",)])
        self.assertEqual(result, (0.1, 0.2, 0.3, 0.4, 0.5))

    async def test_empty_batches_do_not_load_models(self):
        embedding = TransformersEmbeddingProvider(_Config())
        reranker = TransformersRerankerProvider(_Config())
        self.assertEqual(await embedding.embed_async(()), ())
        self.assertEqual(await reranker.rerank_async("query", ()), ())
        self.assertIsNone(embedding._model)
        self.assertIsNone(reranker._model)

    async def test_repeated_and_concurrent_embedding_calls_are_stable(self):
        provider = TransformersEmbeddingProvider(_Config())
        sentinel_model = object()
        provider._model = sentinel_model
        provider._tokenizer = object()
        provider._encode_batch = lambda batch: [
            [float(int(item)), 1.0] for item in batch
        ]

        calls = [
            provider.embed_async(("1", "2", "3"))
            for _ in range(8)
        ]
        results = await asyncio.gather(*calls)

        self.assertTrue(all(result == results[0] for result in results))
        self.assertIs(provider._model, sentinel_model)

    async def test_repeated_and_concurrent_reranker_calls_are_stable(self):
        provider = TransformersRerankerProvider(_Config())
        sentinel_model = object()
        provider._model = sentinel_model
        provider._tokenizer = object()
        provider._score_batch = lambda query, batch: [
            float(int(item)) / 10 for item in batch
        ]

        calls = [
            provider.rerank_async("query", ("1", "2", "3"))
            for _ in range(8)
        ]
        results = await asyncio.gather(*calls)

        self.assertTrue(all(result == results[0] for result in results))
        self.assertIs(provider._model, sentinel_model)


if __name__ == "__main__":
    unittest.main()
