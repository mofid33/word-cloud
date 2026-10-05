import unittest

from src.core.services.ranking.hybrid_ranking_service import (
    HybridRankingService,
    _JoinedCandidate,
)
from src.core.services.semantic.semantic_analysis_service import SemanticCandidateResult
from src.core.services.statistical.statistical_analysis_service import (
    StatisticalCandidateResult,
)


def _statistical(canonical_text, *, phrase_quality, frequency, ngram_size):
    return StatisticalCandidateResult(
        text=canonical_text,
        canonical_text=canonical_text,
        ngram_size=ngram_size,
        frequency=frequency,
        relative_frequency=0.1,
        normalized_frequency=frequency / 10.0,
        document_frequency=1,
        document_coverage=1.0,
        section_coverage=0.5,
        chunk_coverage=0.5,
        phrase_quality=phrase_quality,
        statistical_score=0.7,
        is_protected=False,
        contains_stopword=False,
        pos_tags=("NOUN",) * ngram_size,
        occurrences=(),
    )


def _semantic(canonical_text, score):
    return SemanticCandidateResult(
        text=canonical_text,
        canonical_text=canonical_text,
        bi_encoder_similarity=0.7,
        bi_encoder_score=0.85,
        reranker_score=score,
        semantic_score=score,
        reranked=True,
        rank=1,
    )


def _joined(canonical_text, *, phrase_quality, semantic_score, frequency, ngram_size):
    return _JoinedCandidate(
        statistical=_statistical(
            canonical_text,
            phrase_quality=phrase_quality,
            frequency=frequency,
            ngram_size=ngram_size,
        ),
        semantic=_semantic(canonical_text, semantic_score),
        statistical_rank=1,
        normalized_statistical_score=0.8,
        normalized_semantic_score=semantic_score,
        fused_score=0.8,
    )


class DedupRepresentativeQualityTests(unittest.TestCase):
    def test_clean_phrase_beats_higher_semantic_malformed_variant(self):
        clean = _joined(
            "کیفیت داده",
            phrase_quality=2 / 3,
            semantic_score=0.80,
            frequency=5,
            ngram_size=2,
        )
        malformed = _joined(
            "کیفیت داده باید",
            phrase_quality=0.50,
            semantic_score=0.90,
            frequency=1,
            ngram_size=3,
        )

        self.assertTrue(HybridRankingService._prefer_candidate(clean, malformed))
        self.assertFalse(HybridRankingService._prefer_candidate(malformed, clean))


if __name__ == "__main__":
    unittest.main()
