import unittest

from src.infrastructure.models.analysis_document import AnalysisDocument
from src.infrastructure.models.analysis_keyword import AnalysisKeyword
from src.infrastructure.models.analysis_topic import AnalysisTopic
from src.infrastructure.models.analysis_topic_keyword import AnalysisTopicKeyword
from src.infrastructure.models.word_cloud_analysis import WordCloudAnalysis


class AnalysisModelTests(unittest.TestCase):
    def test_all_phase_four_tables_are_registered(self) -> None:
        self.assertEqual(
            {
                WordCloudAnalysis.__tablename__,
                AnalysisDocument.__tablename__,
                AnalysisKeyword.__tablename__,
                AnalysisTopic.__tablename__,
                AnalysisTopicKeyword.__tablename__,
            },
            {
                "word_cloud_analysis",
                "analysis_document",
                "analysis_keyword",
                "analysis_topic",
                "analysis_topic_keyword",
            },
        )

    def test_analysis_has_required_aggregate_relationships(self) -> None:
        relationships = WordCloudAnalysis.__mapper__.relationships
        self.assertIn("documents", relationships)
        self.assertIn("keywords", relationships)
        self.assertIn("topics", relationships)

    def test_soldier_raw_text_column_is_nullable(self) -> None:
        self.assertTrue(AnalysisDocument.__table__.c.raw_text.nullable)


if __name__ == "__main__":
    unittest.main()
