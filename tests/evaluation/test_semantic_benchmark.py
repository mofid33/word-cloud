from __future__ import annotations

import json
import math
import os
import time
import tracemalloc
import unittest
from pathlib import Path

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

    async def test_profile_semantic_relevance_and_performance_baseline(self):
        tracemalloc.start()
        started = time.perf_counter()
        correct = 0
        total = 0

        for case in self.cases:
            candidates = case["relevant"] + case["irrelevant"]
            vectors = await self.embedding.embed_async([case["context"], *candidates])
            query = vectors[0]

            def cosine(left, right):
                dot = sum(a * b for a, b in zip(left, right, strict=True))
                left_norm = math.sqrt(sum(value * value for value in left))
                right_norm = math.sqrt(sum(value * value for value in right))
                return dot / (left_norm * right_norm)

            bi_scores = [cosine(query, vector) for vector in vectors[1:]]
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
            correct += sum(item in relevant for item in ranked[:cutoff])
            total += cutoff

        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        precision = correct / total
        print(
            f"PHASE8_BENCHMARK precision_at_relevant_cutoff={precision:.4f} "
            f"elapsed_seconds={elapsed:.3f} python_peak_bytes={peak}"
        )
        self.assertGreaterEqual(precision, 0.0)
        self.assertLessEqual(precision, 1.0)


if __name__ == "__main__":
    unittest.main()
