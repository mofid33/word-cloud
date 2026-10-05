import unittest

from src.core.services.candidate.candidate_extraction_service import CandidateOccurrence
from src.core.services.statistical.statistical_analysis_service import (
    StatisticalAnalysisService,
)


class _Config:
    def __init__(self):
        self.values = {
            "statistical_analysis.weights.frequency": 0.3333333333333333,
            "statistical_analysis.weights.document_coverage": 0.3333333333333333,
            "statistical_analysis.weights.phrase_quality": 0.3333333333333334,
        }

    def require(self, key):
        return self.values[key]


def _occurrence(text, canonical, size, pos_tags):
    return CandidateOccurrence(
        document_id="doc-1",
        text=text,
        canonical_text=canonical,
        ngram_size=size,
        segment_index=0,
        token_start=0,
        token_end=size,
        section_id=None,
        chunk_id=None,
        is_protected=False,
        contains_stopword=False,
        stopword_count=0,
        pos_tags=pos_tags,
    )


class PhraseQualityRegressionTests(unittest.TestCase):
    def test_clean_noun_phrase_scores_above_auxiliary_ended_fragment(self):
        service = StatisticalAnalysisService(_Config())
        results = service.analyze(
            (
                _occurrence(
                    "کیفیت داده",
                    "کیفیت داده",
                    2,
                    ("NOUN", "NOUN"),
                ),
                _occurrence(
                    "کیفیت داده باید",
                    "کیفیت داده باید",
                    3,
                    ("NOUN", "NOUN", "AUX"),
                ),
            ),
            document_ids=("doc-1",),
        )
        by_text = {item.canonical_text: item for item in results}
        self.assertGreater(
            by_text["کیفیت داده"].phrase_quality,
            by_text["کیفیت داده باید"].phrase_quality,
        )

    def test_repeated_token_phrase_is_penalized(self):
        service = StatisticalAnalysisService(_Config())
        results = service.analyze(
            (
                _occurrence(
                    "کیفیت داده",
                    "کیفیت داده",
                    2,
                    ("NOUN", "NOUN"),
                ),
                _occurrence(
                    "داده کیفیت داده",
                    "داده کیفیت داده",
                    3,
                    ("NOUN", "NOUN", "NOUN"),
                ),
            ),
            document_ids=("doc-1",),
        )
        by_text = {item.canonical_text: item for item in results}
        self.assertGreater(
            by_text["کیفیت داده"].phrase_quality,
            by_text["داده کیفیت داده"].phrase_quality,
        )


if __name__ == "__main__":
    unittest.main()
