import unittest

from fastapi.testclient import TestClient

from src.application.web import WebService
from src.infrastructure.di.bootstrap import bootstrap_di
from src.infrastructure.di.inject import resolve


class AnalysisApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        bootstrap_di()
        cls.client = TestClient(resolve(WebService).create_app())

    def test_validate_request_returns_200(self) -> None:
        response = self.client.post(
            "/api/v1/analysis/validate",
            json={
                "analysis_type": "COURSE",
                "execution_mode": "auto",
                "documents": [
                    {"document_id": "doc-1", "text": "متن فارسی"}
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["valid"])
        self.assertEqual(body["execution_mode"], "auto")
        self.assertEqual(body["resolved_execution_mode"], "sync")
        self.assertEqual(body["document_count"], 1)
        self.assertNotIn("documents", body)
        self.assertNotIn("text", body)

    def test_schema_error_returns_sanitized_422_contract(self) -> None:
        raw_text = "   "
        response = self.client.post(
            "/api/v1/analysis/validate",
            json={
                "analysis_type": "COURSE",
                "execution_mode": "auto",
                "documents": [
                    {"document_id": "doc-1", "text": raw_text},
                ],
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json(),
            {
                "detail": {
                    "code": "request_validation_error",
                    "message": "Request payload validation failed",
                }
            },
        )
        self.assertNotIn(raw_text, response.text)

    def test_cross_field_error_returns_stable_code(self) -> None:
        response = self.client.post(
            "/api/v1/analysis/validate",
            json={
                "analysis_type": "COURSE",
                "execution_mode": "auto",
                "documents": [
                    {"document_id": "same", "text": "الف"},
                    {"document_id": "same", "text": "ب"},
                ],
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"]["code"],
            "duplicate_document_id",
        )


if __name__ == "__main__":
    unittest.main()
