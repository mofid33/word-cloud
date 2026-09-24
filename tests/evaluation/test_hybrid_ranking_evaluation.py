from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from src.core.services.ranking.hybrid_ranking_service import HybridRankingService
from src.core.services.semantic.providers.embedding_provider import EmbeddingProvider
from src.core.services.semantic.providers.provider_metadata import SemanticProviderMetadata
from src.core.services.semantic.semantic_analysis_service import (
    SemanticAnalysisResult,
    SemanticCandidateResult,
)
from src.core.services.statistical.statistical_analysis_service import (
    StatisticalCandidateResult,
)


_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "hybrid_ranking_cases.json"
_METADATA = SemanticProviderMetadata(
    provider="phase9-evaluation",
    provider_version="1",
    model_identifier="deterministic-public-safe-fixture",
    model_revision="1",
    device="cpu",
    configuration_fingerprint="phase9-evaluation",
)


class _Config:
    def __init__(self, *, threshold: float, mmr_lambda: float):
        self.values = {
            "hybrid_ranking.normalization_strategy": "min_max",
            "hybrid_ranking.baseline_weights.statistical": 0.5,
            "hybrid_ranking.baseline_weights.semantic": 0.5,
            "hybrid_ranking.lexical_deduplication_threshold": threshold,
            "hybrid_ranking.mmr_lambda": mmr_lambda,
            "hybrid_ranking.diversity_candidate_pool_size": 50,
            "hybrid_ranking.maximum_ranked_results": 10,
        }

    def require(self, key):
        return self.values[key]


class _Embedding(EmbeddingProvider):
    def __init__(self, vectors):
        self._vectors = vectors

    @property
    def metadata(self):
        return _METADATA

    async def embed_async(self, texts):
        return tuple(tuple(self._vectors[text]) for text in texts)


def _stat(item) -> StatisticalCandidateResult:
    return StatisticalCandidateResult(
        text=item["canonical_text"],
        canonical_text=item["canonical_text"],
        ngram_size=max(1, min(3, len(item["canonical_text"].split()))),
        frequency=1,
        relative_frequency=0.1,
        normalized_frequency=item["statistical"],
        document_frequency=1,
        document_coverage=1.0,
        section_coverage=None,
        chunk_coverage=None,
        phrase_quality=1.0,
        statistical_score=item["statistical"],
        is_protected=item["canonical_text"] in {"GPT-4", "BERT-base", "v1.2"},
        contains_stopword=False,
        pos_tags=(),
        occurrences=(),
    )


def _semantic(item, rank: int) -> SemanticCandidateResult:
    return SemanticCandidateResult(
        text=item["canonical_text"],
        canonical_text=item["canonical_text"],
        bi_encoder_similarity=0.0,
        bi_encoder_score=item["semantic"],
        reranker_score=item["semantic"],
        semantic_score=item["semantic"],
        reranked=True,
        rank=rank,
    )


def _semantic_result(items) -> SemanticAnalysisResult:
    ordered = sorted(items, key=lambda item: (-item["semantic"], item["canonical_text"]))
    return SemanticAnalysisResult(
        candidates=tuple(_semantic(item, index) for index, item in enumerate(ordered, start=1)),
        embedding_metadata=_METADATA,
        reranker_metadata=_METADATA,
        similarity_metric="cosine",
        semantic_score_strategy="evaluation_fixture",
        rerank_top_n=len(ordered),
    )


def _dcg(ranked, relevance, k):
    value = 0.0
    for index, item in enumerate(ranked[:k], start=1):
        value += (2 ** relevance[item] - 1) / math.log2(index + 1)
    return value


def _metrics(ranked, relevance):
    relevant = {item for item, grade in relevance.items() if grade > 0}
    top5 = ranked[:5]
    top10 = ranked[:10]
    precision5 = sum(item in relevant for item in top5) / max(1, len(top5))
    precision10 = sum(item in relevant for item in top10) / max(1, len(top10))
    recall10 = sum(item in relevant for item in top10) / max(1, len(relevant))
    ideal = [
        item
        for item, _ in sorted(
            relevance.items(),
            key=lambda pair: (-pair[1], pair[0]),
        )
    ]
    ideal_dcg = _dcg(ideal, relevance, 10)
    ndcg10 = _dcg(top10, relevance, 10) / ideal_dcg if ideal_dcg else 1.0
    return {
        "precision_at_5": precision5,
        "precision_at_10": precision10,
        "recall_at_10": recall10,
        "ndcg_at_10": ndcg10,
    }


class HybridRankingEvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_statistical_semantic_hybrid_dedup_and_mmr_baselines(self):
        payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["status"],
            "PHASE_9_REGRESSION_FIXTURE_NOT_PRODUCTION_GOLD",
        )

        evidence = {}
        for case in payload["cases"]:
            items = case["candidates"]
            relevance = {item["canonical_text"]: item["relevance"] for item in items}
            vectors = {item["canonical_text"]: item["vector"] for item in items}
            statistics = tuple(_stat(item) for item in items)
            semantic_result = _semantic_result(items)

            statistical_only = [
                item["canonical_text"]
                for item in sorted(
                    items,
                    key=lambda item: (-item["statistical"], item["canonical_text"]),
                )
            ]
            semantic_only = [
                item["canonical_text"]
                for item in sorted(
                    items,
                    key=lambda item: (-item["semantic"], item["canonical_text"]),
                )
            ]

            hybrid_service = HybridRankingService(
                _Embedding(vectors),
                _Config(threshold=1.0, mmr_lambda=1.0),
            )
            hybrid = await hybrid_service.rank_async(
                statistics,
                semantic_result,
                maximum_results=10,
            )

            dedup_service = HybridRankingService(
                _Embedding(vectors),
                _Config(threshold=0.70, mmr_lambda=1.0),
            )
            hybrid_dedup = await dedup_service.rank_async(
                statistics,
                semantic_result,
                maximum_results=10,
            )

            diversity_service = HybridRankingService(
                _Embedding(vectors),
                _Config(threshold=0.70, mmr_lambda=0.60),
            )
            hybrid_diverse = await diversity_service.rank_async(
                statistics,
                semantic_result,
                maximum_results=10,
            )

            rankings = {
                "statistical_only": statistical_only,
                "semantic_only": semantic_only,
                "hybrid": [item.canonical_text for item in hybrid.candidates],
                "hybrid_dedup": [
                    item.canonical_text for item in hybrid_dedup.candidates
                ],
                "hybrid_dedup_mmr": [
                    item.canonical_text for item in hybrid_diverse.candidates
                ],
            }
            evidence[case["profile"]] = {
                name: _metrics(ranking, relevance)
                for name, ranking in rankings.items()
            }

            repeated = await diversity_service.rank_async(
                tuple(reversed(statistics)),
                semantic_result,
                maximum_results=10,
            )
            self.assertEqual(hybrid_diverse.candidates, repeated.candidates)
            self.assertTrue(
                all(
                    0.0 <= metric["ndcg_at_10"] <= 1.0
                    for metric in evidence[case["profile"]].values()
                )
            )
            self.assertGreaterEqual(
                evidence[case["profile"]]["hybrid_dedup_mmr"]["recall_at_10"],
                0.75,
            )

        print("PHASE9_EVALUATION=" + json.dumps(evidence, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
