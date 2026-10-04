from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import redis.asyncio as redis_asyncio

from src.infrastructure.context.vault.vault_service import VaultService
from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


@inject
class RedisAnalysisTransientPayloadStore:
    __di_singleton__ = True

    def __init__(
        self,
        config_reader: ConfigReader,
        vault_service: VaultService,
        client: Any = None,
    ):
        backend = str(
            config_reader.require("analysis_queue.transient_payload.backend")
        ).strip().lower()
        if backend != "redis":
            raise ValueError(
                "analysis_queue.transient_payload.backend must be 'redis'"
            )

        ttl = config_reader.require("analysis_queue.transient_payload.ttl_seconds")
        if isinstance(ttl, bool) or not isinstance(ttl, int) or ttl < 60:
            raise ValueError(
                "analysis_queue.transient_payload.ttl_seconds must be an integer >= 60"
            )
        self._ttl_seconds = ttl

        timeout = config_reader.require(
            "analysis_queue.transient_payload.socket_timeout_seconds"
        )
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or float(timeout) <= 0
        ):
            raise ValueError(
                "analysis_queue.transient_payload.socket_timeout_seconds must be positive"
            )
        self._socket_timeout_seconds = float(timeout)

        self._key_prefix = str(
            config_reader.require("analysis_queue.transient_payload.key_prefix")
        ).strip()
        if not self._key_prefix:
            raise ValueError(
                "analysis_queue.transient_payload.key_prefix must be non-empty"
            )

        url = self._resolve_url(config_reader, vault_service)
        if not (url.startswith("redis://") or url.startswith("rediss://")):
            raise ValueError("Transient payload URL must use redis:// or rediss://")

        self._client = client or redis_asyncio.from_url(
            url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=self._socket_timeout_seconds,
            socket_connect_timeout=self._socket_timeout_seconds,
        )
        self._validated_non_durable = False
        self._validation_lock = asyncio.Lock()

    async def put_async(
        self,
        analysis_id: str,
        documents: list[dict[str, Any]],
    ) -> None:
        self._validate_analysis_id(analysis_id)
        await self._ensure_non_durable_async()
        payload = json.dumps(
            {
                "version": 1,
                "documents": documents,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        await self._client.set(
            self._key(analysis_id),
            payload,
            ex=self._ttl_seconds,
        )

    async def get_async(
        self,
        analysis_id: str,
    ) -> list[dict[str, Any]] | None:
        self._validate_analysis_id(analysis_id)
        await self._ensure_non_durable_async()
        payload = await self._client.get(self._key(analysis_id))
        if payload is None:
            return None
        try:
            decoded = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Transient analysis payload is invalid") from exc
        if (
            not isinstance(decoded, dict)
            or decoded.get("version") != 1
            or set(decoded) != {"version", "documents"}
            or not isinstance(decoded["documents"], list)
        ):
            raise RuntimeError("Transient analysis payload is invalid")

        documents: list[dict[str, Any]] = []
        for document in decoded["documents"]:
            if (
                not isinstance(document, dict)
                or "document_id" not in document
                or "text" not in document
            ):
                raise RuntimeError("Transient analysis payload is invalid")
            documents.append(
                {
                    "document_id": str(document["document_id"]),
                    "text": str(document["text"]),
                    "metadata": dict(document.get("metadata") or {}),
                }
            )
        return documents

    async def touch_async(self, analysis_id: str) -> bool:
        self._validate_analysis_id(analysis_id)
        await self._ensure_non_durable_async()
        return bool(
            await self._client.expire(
                self._key(analysis_id),
                self._ttl_seconds,
            )
        )

    async def delete_async(self, analysis_id: str) -> None:
        self._validate_analysis_id(analysis_id)
        await self._ensure_non_durable_async()
        await self._client.delete(self._key(analysis_id))

    async def ping_async(self) -> bool:
        await self._ensure_non_durable_async()
        return bool(await self._client.ping())

    async def close_async(self) -> None:
        close = getattr(self._client, "aclose", None)
        if close is not None:
            await close()

    async def _ensure_non_durable_async(self) -> None:
        if self._validated_non_durable:
            return
        async with self._validation_lock:
            if self._validated_non_durable:
                return

            save_config = None
            append_config = None
            for attempt in range(2):
                try:
                    save_config = await self._client.config_get("save")
                    append_config = await self._client.config_get("appendonly")
                    break
                except Exception as exc:
                    if attempt == 1:
                        raise RuntimeError(
                            "Unable to verify transient Redis persistence policy"
                        ) from exc
                    await asyncio.sleep(0.05)

            assert save_config is not None
            assert append_config is not None
            save_value = str(save_config.get("save", "")).strip()
            append_value = str(
                append_config.get("appendonly", "")
            ).strip().lower()
            if save_value:
                raise RuntimeError(
                    "Transient Redis snapshot persistence must be disabled"
                )
            if append_value != "no":
                raise RuntimeError(
                    "Transient Redis append-only persistence must be disabled"
                )
            self._validated_non_durable = True

    def _key(self, analysis_id: str) -> str:
        return f"{self._key_prefix}{analysis_id}"

    @staticmethod
    def _validate_analysis_id(analysis_id: str) -> None:
        if (
            not isinstance(analysis_id, str)
            or not analysis_id.strip()
            or analysis_id != analysis_id.strip()
            or len(analysis_id) > 64
        ):
            raise ValueError("analysis_id is invalid")

    @staticmethod
    def _resolve_url(
        config_reader: ConfigReader,
        vault_service: VaultService,
    ) -> str:
        if vault_service.enabled:
            value = vault_service.get_secret("transient_payload_redis_url")
        else:
            value = os.getenv("TRANSIENT_PAYLOAD_REDIS_URL")
            if not value:
                configured = config_reader.get(
                    "analysis_queue.transient_payload.url"
                )
                if configured is None:
                    raise KeyError(
                        "Transient payload Redis URL is not configured"
                    )
                value = str(configured)

        url = str(value).strip()
        if not url:
            raise ValueError("Transient payload Redis URL must be non-empty")
        return url
