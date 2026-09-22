import asyncio
import unittest

from fastapi import HTTPException

from src.application.analysis.analysis_controller import AnalysisController
from src.application.analysis.dtos.analysis_dto import AnalysisRequestDto
from src.core.services.analysis.analysis_service import AnalysisService


class AnalysisControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = AnalysisController(AnalysisService())
        self.router = self.controller.api()

    def _endpoint(self):
        for route in self.router.routes:
            if getattr(route, "path", None) == "/validate":
                return route.endpoint
        self.fail("POST /validate route was not discovered")

    def test_validate_endpoint_success(self) -> None:
        payload = AnalysisRequestDto.model_validate(
            {
                "analysis_type": "COURSE",
                "execution_mode": "auto",
                "documents": [
                    {"document_id": "doc-1", "text": "متن فارسی"}
                ],
            }
        )

        response = asyncio.run(self._endpoint()(payload))

        self.assertTrue(response.valid)
        self.assertEqual(response.analysis_type.value, "COURSE")
        self.assertEqual(response.document_count, 1)

    def test_domain_validation_error_maps_to_422(self) -> None:
        payload = AnalysisRequestDto.model_validate(
            {
                "analysis_type": "COURSE",
                "execution_mode": "auto",
                "documents": [
                    {"document_id": "same", "text": "الف"},
                    {"document_id": "same", "text": "ب"},
                ],
            }
        )

        with self.assertRaises(HTTPException) as context:
            asyncio.run(self._endpoint()(payload))

        self.assertEqual(context.exception.status_code, 422)
        self.assertEqual(
            context.exception.detail["code"],
            "duplicate_document_id",
        )


if __name__ == "__main__":
    unittest.main()
