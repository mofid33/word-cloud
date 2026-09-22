import unittest

from pydantic import ValidationError

from src.application.analysis.dtos.analysis_dto import AnalysisRequestDto


class AnalysisDtoTests(unittest.TestCase):
    def test_valid_course_request(self) -> None:
        dto = AnalysisRequestDto.model_validate(
            {
                "analysis_type": "COURSE",
                "execution_mode": "auto",
                "documents": [
                    {"document_id": "doc-1", "text": "متن فارسی"}
                ],
            }
        )
        self.assertEqual(dto.analysis_type.value, "COURSE")
        self.assertEqual(dto.execution_mode.value, "auto")
        self.assertEqual(len(dto.documents), 1)

    def test_rejects_unknown_analysis_type(self) -> None:
        with self.assertRaises(ValidationError):
            AnalysisRequestDto.model_validate(
                {
                    "analysis_type": "UNKNOWN",
                    "execution_mode": "auto",
                    "documents": [
                        {"document_id": "doc-1", "text": "متن"}
                    ],
                }
            )

    def test_rejects_empty_documents(self) -> None:
        with self.assertRaises(ValidationError):
            AnalysisRequestDto.model_validate(
                {
                    "analysis_type": "COURSE",
                    "execution_mode": "auto",
                    "documents": [],
                }
            )

    def test_rejects_blank_document_text(self) -> None:
        with self.assertRaises(ValidationError):
            AnalysisRequestDto.model_validate(
                {
                    "analysis_type": "COURSE",
                    "execution_mode": "auto",
                    "documents": [
                        {"document_id": "doc-1", "text": "   "}
                    ],
                }
            )

    def test_rejects_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            AnalysisRequestDto.model_validate(
                {
                    "analysis_type": "COURSE",
                    "execution_mode": "auto",
                    "documents": [
                        {"document_id": "doc-1", "text": "متن"}
                    ],
                    "unexpected": True,
                }
            )


if __name__ == "__main__":
    unittest.main()
