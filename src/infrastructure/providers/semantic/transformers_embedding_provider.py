from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from threading import RLock
from typing import Any, Sequence

from src.core.services.semantic.providers.embedding_provider import EmbeddingProvider
from src.core.services.semantic.providers.provider_metadata import SemanticProviderMetadata
from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


@inject
class TransformersEmbeddingProvider(EmbeddingProvider):
    __di_singleton__ = True

    def __init__(self, config_reader: ConfigReader):
        self._config = self._load_config(config_reader)
        self._model: Any = None
        self._tokenizer: Any = None
        self._load_lock = RLock()
        self._inference_lock = RLock()

    @property
    def metadata(self) -> SemanticProviderMetadata:
        return SemanticProviderMetadata(
            provider="transformers_embedding",
            provider_version="1",
            model_identifier=self._config["model_identifier"],
            model_revision=self._config["model_revision"],
            device=self._config["device"],
            configuration_fingerprint=self._config["fingerprint"],
        )

    async def embed_async(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        materialized = tuple(texts)
        for text in materialized:
            if not isinstance(text, str) or not text.strip():
                raise ValueError("embedding input must contain non-empty strings")
        if not materialized:
            return ()
        return await asyncio.to_thread(self._embed_sync, materialized)

    def _embed_sync(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self._ensure_loaded()
        results: list[tuple[float, ...]] = []
        batch_size = self._config["batch_size"]
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            with self._inference_lock:
                vectors = self._encode_batch(batch)
            results.extend(tuple(float(value) for value in row) for row in vectors)
        return tuple(results)

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            try:
                import torch
                from transformers import AutoModel, AutoTokenizer
            except ImportError as exc:
                raise RuntimeError("Semantic embedding dependencies are not installed") from exc

            device = self._resolve_device(torch)
            common = {
                "revision": self._config["model_revision"],
                "cache_dir": self._config["cache_dir"],
                "local_files_only": not self._config["allow_remote_downloads"],
                "trust_remote_code": False,
            }
            try:
                tokenizer = AutoTokenizer.from_pretrained(
                    self._config["model_identifier"], **common
                )
                model = AutoModel.from_pretrained(
                    self._config["model_identifier"], **common
                )
                model.to(device)
                model.eval()
            except Exception as exc:
                raise RuntimeError("Failed to load configured embedding model") from exc

            self._tokenizer = tokenizer
            self._model = model

    def _encode_batch(self, texts: tuple[str, ...]) -> list[list[float]]:
        import torch
        import torch.nn.functional as functional

        encoded = self._tokenizer(
            list(texts),
            padding=True,
            truncation=True,
            max_length=self._config["max_length"],
            return_tensors="pt",
        )
        encoded = {
            key: value.to(self._config["device"])
            for key, value in encoded.items()
        }
        with torch.inference_mode():
            output = self._model(**encoded)
            token_embeddings = output.last_hidden_state
            mask = (
                encoded["attention_mask"]
                .unsqueeze(-1)
                .expand(token_embeddings.size())
                .float()
            )
            summed = torch.sum(token_embeddings * mask, dim=1)
            counts = torch.clamp(mask.sum(dim=1), min=1e-9)
            pooled = functional.normalize(summed / counts, p=2, dim=1)
        return pooled.detach().cpu().tolist()

    def _resolve_device(self, torch_module: Any) -> str:
        device = self._config["device"]
        if device == "cpu":
            return "cpu"
        if not torch_module.cuda.is_available():
            raise RuntimeError("CUDA is configured but unavailable")
        index = int(device.split(":", 1)[1])
        if index >= torch_module.cuda.device_count():
            raise RuntimeError("Configured CUDA device index is unavailable")
        return device

    @classmethod
    def _load_config(cls, config_reader: ConfigReader) -> dict[str, Any]:
        model_identifier = cls._required_string(
            config_reader, "semantic.embedding.model_identifier"
        )
        model_revision = config_reader.get("semantic.embedding.model_revision")
        if model_revision is not None and (
            not isinstance(model_revision, str) or not model_revision.strip()
        ):
            raise ValueError("semantic.embedding.model_revision must be a non-empty string")
        batch_size = cls._required_positive_int(
            config_reader, "semantic.embedding.batch_size"
        )
        max_length = cls._required_positive_int(
            config_reader, "semantic.embedding.max_length"
        )
        allow_remote = cls._required_bool(
            config_reader, "models.allow_remote_downloads"
        )
        if cls._required_bool(config_reader, "models.trust_remote_code"):
            raise ValueError("models.trust_remote_code must remain false")

        device_type = cls._required_string(config_reader, "device.type").lower()
        cuda_index = config_reader.require("device.cuda_device_index")
        if isinstance(cuda_index, bool) or not isinstance(cuda_index, int) or cuda_index < 0:
            raise ValueError("device.cuda_device_index must be an integer >= 0")
        if device_type == "cpu":
            device = "cpu"
        elif device_type == "cuda":
            device = f"cuda:{cuda_index}"
        else:
            raise ValueError("device.type must be 'cpu' or 'cuda'")

        payload = {
            "model_identifier": model_identifier,
            "model_revision": model_revision.strip() if isinstance(model_revision, str) else None,
            "batch_size": batch_size,
            "max_length": max_length,
            "device": device,
            "allow_remote_downloads": allow_remote,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return {
            **payload,
            "cache_dir": str(Path(str(config_reader.require("models.cache_dir")))),
            "fingerprint": fingerprint,
        }

    @staticmethod
    def _required_string(config_reader: ConfigReader, key: str) -> str:
        value = config_reader.require(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Configuration '{key}' must be a non-empty string")
        return value.strip()

    @staticmethod
    def _required_positive_int(config_reader: ConfigReader, key: str) -> int:
        value = config_reader.require(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"Configuration '{key}' must be an integer > 0")
        return value

    @staticmethod
    def _required_bool(config_reader: ConfigReader, key: str) -> bool:
        value = config_reader.require(key)
        if not isinstance(value, bool):
            raise ValueError(f"Configuration '{key}' must be a boolean")
        return value
