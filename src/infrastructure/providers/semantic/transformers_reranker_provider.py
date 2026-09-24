from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from threading import RLock
from typing import Any, Sequence

from src.core.services.semantic.providers.provider_metadata import SemanticProviderMetadata
from src.core.services.semantic.providers.reranker_provider import RerankerProvider
from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


@inject
class TransformersRerankerProvider(RerankerProvider):
    __di_singleton__ = True

    def __init__(self, config_reader: ConfigReader):
        self._config = self._load_config(config_reader)
        self._model: Any = None
        self._tokenizer: Any = None
        self._resolved_revision: str | None = None
        self._load_lock = RLock()
        self._inference_lock = RLock()

    @property
    def metadata(self) -> SemanticProviderMetadata:
        return SemanticProviderMetadata(
            provider="transformers_reranker",
            provider_version="1",
            model_identifier=self._config["model_identifier"],
            model_revision=self._resolved_revision or self._config["model_revision"],
            device=self._config["device"],
            configuration_fingerprint=self._config["fingerprint"],
        )

    async def rerank_async(self, query: str, candidates: Sequence[str]) -> Sequence[float]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("reranker query must be a non-empty string")
        materialized = tuple(candidates)
        for candidate in materialized:
            if not isinstance(candidate, str) or not candidate.strip():
                raise ValueError("reranker candidates must be non-empty strings")
        if not materialized:
            return ()
        return await asyncio.to_thread(self._rerank_sync, query, materialized)

    def _rerank_sync(
        self,
        query: str,
        candidates: tuple[str, ...],
    ) -> tuple[float, ...]:
        self._ensure_loaded()
        results: list[float] = []
        batch_size = self._config["batch_size"]
        for start in range(0, len(candidates), batch_size):
            batch = candidates[start:start + batch_size]
            with self._inference_lock:
                scores = self._score_batch(query, batch)
            results.extend(float(score) for score in scores)
        return tuple(results)

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            try:
                import torch
                from transformers import AutoModelForSequenceClassification, AutoTokenizer
            except ImportError as exc:
                raise RuntimeError("Semantic reranker dependencies are not installed") from exc

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
                model = AutoModelForSequenceClassification.from_pretrained(
                    self._config["model_identifier"], **common
                )
                model.to(device)
                model.eval()
            except Exception as exc:
                raise RuntimeError("Failed to load configured reranker model") from exc

            resolved_revision = getattr(
                getattr(model, "config", None),
                "_commit_hash",
                None,
            )
            if not resolved_revision:
                resolved_revision = getattr(
                    tokenizer,
                    "init_kwargs",
                    {},
                ).get("_commit_hash")

            self._tokenizer = tokenizer
            self._model = model
            self._resolved_revision = resolved_revision or self._config["model_revision"]

    def _score_batch(
        self,
        query: str,
        candidates: tuple[str, ...],
    ) -> list[float]:
        import torch

        encoded = self._tokenizer(
            [query] * len(candidates),
            list(candidates),
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
            logits = self._model(**encoded).logits
            if logits.ndim == 1:
                probabilities = torch.sigmoid(logits)
            elif logits.shape[-1] == 1:
                probabilities = torch.sigmoid(logits[:, 0])
            else:
                probabilities = torch.softmax(logits, dim=-1)[:, -1]
        return probabilities.detach().cpu().tolist()

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
            config_reader, "semantic.reranker.model_identifier"
        )
        model_revision = config_reader.get("semantic.reranker.model_revision")
        if model_revision is not None and (
            not isinstance(model_revision, str) or not model_revision.strip()
        ):
            raise ValueError("semantic.reranker.model_revision must be a non-empty string")
        batch_size = cls._required_positive_int(
            config_reader, "semantic.reranker.batch_size"
        )
        max_length = cls._required_positive_int(
            config_reader, "semantic.reranker.max_length"
        )
        max_batch_size = cls._required_positive_int(
            config_reader, "batch.max_size"
        )
        if batch_size > max_batch_size:
            raise ValueError(
                "semantic.reranker.batch_size must be <= batch.max_size"
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
            "max_batch_size": max_batch_size,
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
