import unittest

from pydantic import ValidationError

from src.application.analysis.dtos.analysis_dto import (
    AnalysisRequestDto,
    AnalysisStatusResponseDto,
)


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

    def test_status_response_uses_nested_error_contract(self) -> None:
        dto = AnalysisStatusResponseDto.model_validate(
            {
                "analysis_id": "analysis-1",
                "analysis_type": "COURSE",
                "status": "failed",
                "execution_mode": "sync",
                "reference": None,
                "model_version": None,
                "scoring_version": None,
                "created_at": "2026-09-22T12:00:00Z",
                "started_at": None,
                "completed_at": "2026-09-22T12:01:00Z",
                "error": {
                    "code": "analysis_processing_failed",
                    "message": "Analysis processing failed",
                },
            }
        )

        body = dto.model_dump(mode="json")
        self.assertIn("error", body)
        self.assertEqual(
            body["error"]["code"],
            "analysis_processing_failed",
        )
        self.assertNotIn("error_code", body)
        self.assertNotIn("error_message", body)

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
