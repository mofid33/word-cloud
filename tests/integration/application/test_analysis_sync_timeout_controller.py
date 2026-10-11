import asyncio
import unittest

from fastapi import HTTPException

from src.application.analysis.analysis_controller import AnalysisController
from src.application.analysis.dtos.analysis_dto import AnalysisRequestDto
from src.core.services.analysis.analysis_service import AnalysisSyncTimeoutError


class _TimeoutAnalysisService:
    async def create_async(self, **_kwargs):
        raise AnalysisSyncTimeoutError()


class AnalysisSyncTimeoutControllerTests(unittest.TestCase):
    def test_create_maps_sync_timeout_to_504(self) -> None:
        router = AnalysisController(_TimeoutAnalysisService()).api()
        endpoint = next(
            route.endpoint
            for route in router.routes
            if getattr(route, "path", None) == ""
            and "POST" in (getattr(route, "methods", None) or set())
        )
        payload = AnalysisRequestDto.model_validate(
            {
                "analysis_type": "COURSE",
                "execution_mode": "sync",
                "documents": [
                    {"document_id": "doc-1", "text": "متن"},
                ],
            }
        )

        with self.assertRaises(HTTPException) as context:
            asyncio.run(endpoint(payload))

        self.assertEqual(context.exception.status_code, 504)
        self.assertEqual(
            context.exception.detail["code"],
            "analysis_sync_timeout",
        )


if __name__ == "__main__":
    unittest.main()
