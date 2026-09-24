from __future__ import annotations

import json
import math
import os
import time
import tracemalloc
import unittest
from pathlib import Path

import psutil

from src.core.services.semantic.providers.embedding_provider import EmbeddingProvider
from src.core.services.semantic.providers.reranker_provider import RerankerProvider
from src.infrastructure.di.bootstrap import bootstrap_di
from src.infrastructure.di.inject import reset_di_state, resolve


@unittest.skipUnless(
    os.getenv("RUN_PHASE8_BENCHMARK") == "1",
    "set RUN_PHASE8_BENCHMARK=1 to execute model benchmark",
)
class SemanticBenchmarkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        reset_di_state()
        bootstrap_di()
        self.embedding = resolve(EmbeddingProvider)
        self.reranker = resolve(RerankerProvider)
        fixture = Path(__file__).parent / "fixtures" / "semantic_cases.json"
        self.cases = json.loads(fixture.read_text(encoding="utf-8"))["cases"]

    @staticmethod
    def _cosine(left, right):
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        return dot / (left_norm * right_norm)

    async def _embedding_batch_baseline(self, texts, batch_size):
        original = self.embedding._config["batch_size"]
        self.embedding._config["batch_size"] = batch_size
        try:
            started = time.perf_counter()
            result = await self.embedding.embed_async(texts)
            elapsed = time.perf_counter() - started
        finally:
            self.embedding._config["batch_size"] = original
        return {
            "batch_size": batch_size,
            "items": len(result),
            "elapsed_seconds": elapsed,
            "throughput_items_per_second": len(result) / elapsed,
        }

    async def _reranker_batch_baseline(self, query, candidates, batch_size):
        original = self.reranker._config["batch_size"]
        self.reranker._config["batch_size"] = batch_size
        try:
            started = time.perf_counter()
            result = await self.reranker.rerank_async(query, candidates)
            elapsed = time.perf_counter() - started
        finally:
            self.reranker._config["batch_size"] = original
        return {
            "batch_size": batch_size,
            "items": len(result),
            "elapsed_seconds": elapsed,
            "throughput_pairs_per_second": len(result) / elapsed,
        }

    async def test_profile_semantic_relevance_and_performance_baseline(self):
        process = psutil.Process()
        rss_before = process.memory_info().rss
        tracemalloc.start()

        evaluation_started = time.perf_counter()
        correct = 0
        total = 0
        profile_results = []

        for case in self.cases:
            candidates = case["relevant"] + case["irrelevant"]
            vectors = await self.embedding.embed_async([case["context"], *candidates])
            query = vectors[0]
            bi_scores = [
                self._cosine(query, vector)
                for vector in vectors[1:]
            ]
            rerank_scores = await self.reranker.rerank_async(
                case["context"],
                candidates,
            )
            ranked = [
                candidate
                for _, _, candidate in sorted(
                    zip(rerank_scores, bi_scores, candidates, strict=True),
                    key=lambda item: (-item[0], -item[1], item[2]),
                )
            ]
            relevant = set(case["relevant"])
            cutoff = len(relevant)
            case_correct = sum(item in relevant for item in ranked[:cutoff])
            correct += case_correct
            total += cutoff
            profile_results.append(
                {
                    "profile": case["profile"],
                    "coverage": case["coverage"],
                    "precision_at_relevant_cutoff": case_correct / cutoff,
                }
            )

        evaluation_elapsed = time.perf_counter() - evaluation_started

        embedding_inputs = tuple(
            case["context"] for case in self.cases
        )
        reranker_query = self.cases[0]["context"]
        reranker_candidates = tuple(
            case["relevant"][0] for case in self.cases
        )

        embedding_batch_sizes = sorted(
            {
                1,
                min(
                    self.embedding._config["batch_size"],
                    len(embedding_inputs),
                ),
            }
        )
        reranker_batch_sizes = sorted(
            {
                1,
                min(
                    self.reranker._config["batch_size"],
                    len(reranker_candidates),
                ),
            }
        )

        embedding_batch_results = [
            await self._embedding_batch_baseline(
                embedding_inputs,
                batch_size,
            )
            for batch_size in embedding_batch_sizes
        ]
        reranker_batch_results = [
            await self._reranker_batch_baseline(
                reranker_query,
                reranker_candidates,
                batch_size,
            )
            for batch_size in reranker_batch_sizes
        ]

        _, python_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rss_after = process.memory_info().rss

        gpu_evidence = None
        device = self.embedding.metadata.device
        if device.startswith("cuda"):
            import torch

            cuda_index = int(device.split(":", 1)[1])
            gpu_evidence = {
                "device": device,
                "allocated_bytes": torch.cuda.memory_allocated(cuda_index),
                "reserved_bytes": torch.cuda.memory_reserved(cuda_index),
                "peak_allocated_bytes": torch.cuda.max_memory_allocated(cuda_index),
            }

        precision = correct / total
        evidence = {
            "precision_at_relevant_cutoff": precision,
            "evaluation_elapsed_seconds": evaluation_elapsed,
            "process_rss_before_bytes": rss_before,
            "process_rss_after_bytes": rss_after,
            "process_rss_delta_bytes": rss_after - rss_before,
            "python_peak_bytes": python_peak,
            "embedding_batch_results": embedding_batch_results,
            "reranker_batch_results": reranker_batch_results,
            "gpu": gpu_evidence,
            "profile_results": profile_results,
            "embedding_metadata": {
                "model_identifier": self.embedding.metadata.model_identifier,
                "model_revision": self.embedding.metadata.model_revision,
                "device": self.embedding.metadata.device,
            },
            "reranker_metadata": {
                "model_identifier": self.reranker.metadata.model_identifier,
                "model_revision": self.reranker.metadata.model_revision,
                "device": self.reranker.metadata.device,
            },
        }
        print(
            "PHASE8_BENCHMARK "
            + json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        )

        self.assertGreaterEqual(precision, 0.0)
        self.assertLessEqual(precision, 1.0)
        self.assertGreater(evaluation_elapsed, 0.0)
        self.assertGreater(rss_after, 0)
        for item in embedding_batch_results:
            self.assertGreater(item["elapsed_seconds"], 0.0)
            self.assertGreater(item["throughput_items_per_second"], 0.0)
        for item in reranker_batch_results:
            self.assertGreater(item["elapsed_seconds"], 0.0)
            self.assertGreater(item["throughput_pairs_per_second"], 0.0)


if __name__ == "__main__":
    unittest.main()
