import asyncio
import unittest

from src.infrastructure.providers.analysis_queue.redis_analysis_transient_payload_store import (
    RedisAnalysisTransientPayloadStore,
)


class _Config:
    def __init__(self):
        self.values = {
            "analysis_queue.transient_payload.backend": "redis",
            "analysis_queue.transient_payload.ttl_seconds": 3600,
            "analysis_queue.transient_payload.socket_timeout_seconds": 1.0,
            "analysis_queue.transient_payload.key_prefix": "test:payload:",
            "analysis_queue.transient_payload.url": "redis://127.0.0.1:6379/15",
        }

    def require(self, key):
        return self.values[key]

    def get(self, key, default=None):
        return self.values.get(key, default)


class _Vault:
    enabled = False


class _Client:
    def __init__(self, *, save="", appendonly="no"):
        self.save = save
        self.appendonly = appendonly
        self.values = {}
        self.ttls = {}
        self.closed = False

    async def config_get(self, key):
        if key == "save":
            return {"save": self.save}
        if key == "appendonly":
            return {"appendonly": self.appendonly}
        return {}

    async def set(self, key, value, *, ex):
        self.values[key] = value
        self.ttls[key] = ex
        return True

    async def get(self, key):
        return self.values.get(key)

    async def expire(self, key, ttl):
        if key not in self.values:
            return False
        self.ttls[key] = ttl
        return True

    async def delete(self, key):
        self.values.pop(key, None)
        self.ttls.pop(key, None)
        return 1

    async def aclose(self):
        self.closed = True


class RedisAnalysisTransientPayloadStoreTests(unittest.TestCase):
    def test_non_durable_store_round_trip_and_cleanup(self) -> None:
        async def run():
            client = _Client()
            store = RedisAnalysisTransientPayloadStore(
                _Config(),
                _Vault(),
                client,
            )
            documents = [
                {
                    "document_id": "concern-1",
                    "text": "متن محرمانه",
                    "metadata": {"source": "unit"},
                }
            ]

            await store.put_async("analysis-1", documents)
            loaded = await store.get_async("analysis-1")
            self.assertEqual(loaded, documents)
            self.assertTrue(await store.touch_async("analysis-1"))
            await store.delete_async("analysis-1")
            self.assertIsNone(await store.get_async("analysis-1"))
            await store.close_async()
            self.assertTrue(client.closed)

        asyncio.run(run())

    def test_snapshot_or_appendonly_persistence_is_rejected(self) -> None:
        async def assert_rejected(client):
            store = RedisAnalysisTransientPayloadStore(
                _Config(),
                _Vault(),
                client,
            )
            with self.assertRaises(RuntimeError):
                await store.put_async(
                    "analysis-1",
                    [{"document_id": "d", "text": "secret", "metadata": {}}],
                )

        asyncio.run(assert_rejected(_Client(save="3600 1")))
        asyncio.run(assert_rejected(_Client(appendonly="yes")))

    def test_invalid_payload_error_does_not_echo_payload_content(self) -> None:
        async def run():
            client = _Client()
            store = RedisAnalysisTransientPayloadStore(
                _Config(),
                _Vault(),
                client,
            )
            await store.put_async(
                "analysis-1",
                [{"document_id": "d", "text": "SECRET-MARKER", "metadata": {}}],
            )
            key = "test:payload:analysis-1"
            client.values[key] = '{"version":1,"documents":"SECRET-MARKER"}'

            with self.assertRaises(RuntimeError) as context:
                await store.get_async("analysis-1")
            self.assertNotIn("SECRET-MARKER", str(context.exception))

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
