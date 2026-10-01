from __future__ import annotations

import unittest

import httpx

from src.application.web import WebService


class _Config:
    def get(self, key, default=None):
        return default

    def get_api_prefix(self):
        return "/api/v1"


class _Runtime:
    docs_enabled = False
    allowed_hosts = ("testserver",)
    cors_allowed_origins = ()
    maximum_request_body_bytes = 8
    request_timeout_seconds = 5


class _Metrics:
    def observe_http(self, **_kwargs):
        return None


class _Db:
    async def dispose_async(self):
        return None


class _TransientStore:
    async def close_async(self):
        return None


class _WebServiceWithoutControllers(WebService):
    def discover_controllers(self, package_name: str = "src.application"):
        return []


class ProductionMiddlewareIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_early_413_response_includes_security_headers(self) -> None:
        service = _WebServiceWithoutControllers(
            _Config(),
            _Runtime(),
            _Metrics(),
            _Db(),
            _TransientStore(),
        )
        app = service.create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post("/oversized", content=b"123456789")

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertTrue(response.headers["x-request-id"])


if __name__ == "__main__":
    unittest.main()
