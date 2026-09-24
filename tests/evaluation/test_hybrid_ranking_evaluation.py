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
from src.infrastructure.utils.config_reader import ConfigReader


_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "hybrid_ranking_cases.json"
_METADATA = SemanticProviderMetadata(
    provider="phase9-evaluation",
    provider_version="1",
    model_identifier="deterministic-public-safe-fixture",
    model_revision="1",
    device="cpu",
    configuration_fingerprint="phase9-evaluation",
)


class _OverrideConfig:
    def __init__(self, base: ConfigReader, overrides: dict[str, object]):
        self._base = base
        self._overrides = dict(overrides)

    def require(self, key):
        if key in self._overrides:
            return self._overrides[key]
        return self._base.require(key)


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
        candidates=tuple(
            _semantic(item, index)
            for index, item in enumerate(ordered, start=1)
        ),
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


def _precision_at_k(ranked, relevance, k):
    relevant = {item for item, grade in relevance.items() if grade > 0}
    hits = sum(item in relevant for item in ranked[:k])
    return hits / k


def _metrics(ranked, relevance):
    relevant = {item for item, grade in relevance.items() if grade > 0}
    ideal = [
        item
        for item, _ in sorted(
            relevance.items(),
            key=lambda pair: (-pair[1], pair[0]),
        )
    ]
    ideal_dcg = _dcg(ideal, relevance, 10)
    return {
        "precision_at_5": _precision_at_k(ranked, relevance, 5),
        "precision_at_10": _precision_at_k(ranked, relevance, 10),
        "recall_at_10": (
            sum(item in relevant for item in ranked[:10]) / len(relevant)
            if relevant
            else 1.0
        ),
        "ndcg_at_10": (
            _dcg(ranked, relevance, 10) / ideal_dcg
            if ideal_dcg
            else 1.0
        ),
    }


def _cosine(left, right):
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return sum(
        left_value * right_value
        for left_value, right_value in zip(left, right, strict=True)
    ) / (left_norm * right_norm)


class HybridRankingEvaluationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.production_config = ConfigReader(env_type="production")
        self.development_config = ConfigReader(env_type="development")

    def test_metrics_use_fixed_k_denominators(self):
        relevance = {
            "relevant": 3,
            "noise": 0,
        }
        metric = _metrics(["relevant", "noise"], relevance)

        self.assertEqual(metric["precision_at_5"], 0.2)
        self.assertEqual(metric["precision_at_10"], 0.1)
        self.assertEqual(metric["recall_at_10"], 1.0)

    def test_fixture_covers_required_phase_9_evaluation_boundaries(self):
        payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["status"],
            "PHASE_9_REGRESSION_FIXTURE_NOT_PRODUCTION_GOLD",
        )

        cases = payload["cases"]
        self.assertTrue(all(len(case["candidates"]) >= 10 for case in cases))
        self.assertEqual(
            {case["profile"] for case in cases},
            {"COURSE", "SOLDIER_CONCERN", "MEDIA"},
        )
        self.assertTrue(
            {"persian_only", "mixed", "latin_only"}.issubset(
                {case["coverage"] for case in cases}
            )
        )

        all_terms = {
            item["canonical_text"]
            for case in cases
            for item in case["candidates"]
        }
        self.assertTrue({"GPT-4", "BERT-base", "v1.2"}.issubset(all_terms))
        self.assertTrue(any(case["near_duplicate_pairs"] for case in cases))
        self.assertTrue(any(case["high_similarity_pairs"] for case in cases))

        threshold = self.production_config.require(
            "hybrid_ranking.lexical_deduplication_threshold"
        )
        semantic_threshold = self.production_config.require(
            "hybrid_ranking.semantic_deduplication_threshold"
        )
        for case in cases:
            for left, right in case["near_duplicate_pairs"]:
                similarity = HybridRankingService._lexical_similarity(left, right)
                self.assertGreaterEqual(similarity, threshold)

            vectors = {
                item["canonical_text"]: item["vector"]
                for item in case["candidates"]
            }
            declared_semantic_pairs = {
                frozenset((left, right))
                for left, right in case["high_similarity_pairs"]
            }
            for left, right in case["high_similarity_pairs"]:
                self.assertGreaterEqual(
                    _cosine(vectors[left], vectors[right]),
                    semantic_threshold,
                )

            candidate_names = list(vectors)
            for left_index, left in enumerate(candidate_names):
                for right in candidate_names[left_index + 1:]:
                    pair = frozenset((left, right))
                    similarity = _cosine(vectors[left], vectors[right])
                    if pair in declared_semantic_pairs:
                        self.assertGreaterEqual(
                            similarity,
                            semantic_threshold,
                        )
                    else:
                        self.assertLess(
                            similarity,
                            semantic_threshold,
                            msg=(
                                f"undeclared semantic duplicate in {case['name']}: "
                                f"{left!r} vs {right!r} = {similarity}"
                            ),
                        )

    def test_production_and_development_hybrid_baselines_match(self):
        keys = (
            "hybrid_ranking.normalization_strategy",
            "hybrid_ranking.baseline_weights.statistical",
            "hybrid_ranking.baseline_weights.semantic",
            "hybrid_ranking.lexical_deduplication_threshold",
            "hybrid_ranking.semantic_deduplication_threshold",
            "hybrid_ranking.mmr_lambda",
            "hybrid_ranking.diversity_candidate_pool_size",
            "hybrid_ranking.maximum_ranked_results",
        )
        for key in keys:
            self.assertEqual(
                self.production_config.require(key),
                self.development_config.require(key),
            )

        self.assertEqual(
            self.production_config.require(
                "hybrid_ranking.lexical_deduplication_threshold"
            ),
            0.92,
        )
        self.assertEqual(
            self.production_config.require(
                "hybrid_ranking.semantic_deduplication_threshold"
            ),
            0.95,
        )
        self.assertEqual(
            self.production_config.require("hybrid_ranking.mmr_lambda"),
            0.7,
        )

    async def test_statistical_semantic_hybrid_dedup_and_mmr_baselines(self):
        payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        evidence = {}

        production_threshold = self.production_config.require(
            "hybrid_ranking.lexical_deduplication_threshold"
        )
        production_semantic_threshold = self.production_config.require(
            "hybrid_ranking.semantic_deduplication_threshold"
        )
        production_lambda = self.production_config.require(
            "hybrid_ranking.mmr_lambda"
        )

        for case in payload["cases"]:
            items = case["candidates"]
            relevance = {
                item["canonical_text"]: item["relevance"]
                for item in items
            }
            vectors = {
                item["canonical_text"]: item["vector"]
                for item in items
            }
            statistics = tuple(_stat(item) for item in items)
            semantic_result = _semantic_result(items)

            statistical_only = [
                item["canonical_text"]
                for item in sorted(
                    items,
                    key=lambda item: (
                        -item["statistical"],
                        item["canonical_text"],
                    ),
                )
            ]
            semantic_only = [
                item["canonical_text"]
                for item in sorted(
                    items,
                    key=lambda item: (
                        -item["semantic"],
                        item["canonical_text"],
                    ),
                )
            ]

            hybrid_service = HybridRankingService(
                _Embedding(vectors),
                _OverrideConfig(
                    self.production_config,
                    {
                        "hybrid_ranking.lexical_deduplication_threshold": 1.0,
                        "hybrid_ranking.semantic_deduplication_threshold": 1.0,
                        "hybrid_ranking.mmr_lambda": 1.0,
                    },
                ),
            )
            hybrid = await hybrid_service.rank_async(
                statistics,
                semantic_result,
                maximum_results=10,
            )

            dedup_service = HybridRankingService(
                _Embedding(vectors),
                _OverrideConfig(
                    self.production_config,
                    {
                        "hybrid_ranking.mmr_lambda": 1.0,
                    },
                ),
            )
            hybrid_dedup = await dedup_service.rank_async(
                statistics,
                semantic_result,
                maximum_results=10,
            )

            production_service = HybridRankingService(
                _Embedding(vectors),
                self.production_config,
            )
            production_hybrid = await production_service.rank_async(
                statistics,
                semantic_result,
                maximum_results=10,
            )

            rankings = {
                "statistical_only": statistical_only,
                "semantic_only": semantic_only,
                "hybrid": [
                    item.canonical_text
                    for item in hybrid.candidates
                ],
                "hybrid_dedup": [
                    item.canonical_text
                    for item in hybrid_dedup.candidates
                ],
                "hybrid_dedup_mmr": [
                    item.canonical_text
                    for item in production_hybrid.candidates
                ],
            }
            case_key = f'{case["profile"]}:{case["coverage"]}:{case["name"]}'
            evidence[case_key] = {
                name: _metrics(ranking, relevance)
                for name, ranking in rankings.items()
            }

            self.assertEqual(len(production_hybrid.candidates), 10)
            self.assertEqual(
                production_hybrid.lexical_deduplication_threshold,
                production_threshold,
            )
            self.assertEqual(
                production_hybrid.semantic_deduplication_threshold,
                production_semantic_threshold,
            )
            self.assertEqual(
                production_hybrid.mmr_lambda,
                production_lambda,
            )
            if case["high_similarity_pairs"]:
                self.assertTrue(
                    any(
                        item.reason == "semantic_near_duplicate"
                        for item in production_hybrid.deduplicated
                    )
                )

            repeated = await production_service.rank_async(
                tuple(reversed(statistics)),
                semantic_result,
                maximum_results=10,
            )
            self.assertEqual(
                production_hybrid.candidates,
                repeated.candidates,
            )

            for metric in evidence[case_key].values():
                self.assertTrue(0.0 <= metric["precision_at_5"] <= 1.0)
                self.assertTrue(0.0 <= metric["precision_at_10"] <= 1.0)
                self.assertTrue(0.0 <= metric["recall_at_10"] <= 1.0)
                self.assertTrue(0.0 <= metric["ndcg_at_10"] <= 1.0)

            self.assertGreaterEqual(
                evidence[case_key]["hybrid_dedup_mmr"]["recall_at_10"],
                0.70,
            )

        print(
            "PHASE9_EVALUATION="
            + json.dumps(
                {
                    "baseline_config": {
                        "lexical_deduplication_threshold": production_threshold,
                        "semantic_deduplication_threshold": (
                            production_semantic_threshold
                        ),
                        "mmr_lambda": production_lambda,
                        "statistical_weight": self.production_config.require(
                            "hybrid_ranking.baseline_weights.statistical"
                        ),
                        "semantic_weight": self.production_config.require(
                            "hybrid_ranking.baseline_weights.semantic"
                        ),
                    },
                    "cases": evidence,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
