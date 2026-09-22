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
        raw_text_marker = "TOP-SECRET-RAW-TEXT"
        response = self.client.post(
            "/api/v1/analysis/validate",
            json={
                "analysis_type": "COURSE",
                "execution_mode": "auto",
                "documents": [
                    {
                        "document_id": "doc-1",
                        "text": {"raw": raw_text_marker},
                    },
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
        self.assertNotIn(raw_text_marker, response.text)

    def test_raw_text_embedded_in_metadata_returns_sanitized_422(self) -> None:
        raw_text = "SENSITIVE-SOLDIER-CONTENT"
        response = self.client.post(
            "/api/v1/analysis/validate",
            json={
                "analysis_type": "SOLDIER_CONCERN",
                "execution_mode": "sync",
                "documents": [
                    {
                        "document_id": "concern-1",
                        "text": raw_text,
                        "metadata": {
                            "nested": {
                                "copy": f"prefix {raw_text} suffix"
                            }
                        },
                    }
                ],
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"]["code"],
            "raw_text_repeated_in_metadata",
        )
        self.assertNotIn(raw_text, response.text)

    def test_user_controlled_document_id_is_not_echoed_in_limit_error(self) -> None:
        secret_id = "TOP-SECRET-DOCUMENT-ID"
        response = self.client.post(
            "/api/v1/analysis/validate",
            json={
                "analysis_type": "COURSE",
                "execution_mode": "async",
                "documents": [
                    {
                        "document_id": secret_id,
                        "text": "x" * 500001,
                    }
                ],
            },
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(
            response.json()["detail"]["code"],
            "max_document_characters_exceeded",
        )
        self.assertNotIn(secret_id, response.text)

    def test_lifecycle_routes_are_mounted_in_openapi(self) -> None:
        paths = self.client.app.openapi()["paths"]

        self.assertIn("/api/v1/analysis", paths)
        self.assertIn("post", paths["/api/v1/analysis"])
        self.assertIn("/api/v1/analysis/{analysis_id}", paths)
        self.assertIn("get", paths["/api/v1/analysis/{analysis_id}"])
        self.assertIn("/api/v1/analysis/{analysis_id}/result", paths)
        self.assertIn(
            "get",
            paths["/api/v1/analysis/{analysis_id}/result"],
        )

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
