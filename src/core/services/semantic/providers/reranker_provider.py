from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.core.services.semantic.providers.provider_metadata import SemanticProviderMetadata


class RerankerProvider(ABC):
    @property
    @abstractmethod
    def metadata(self) -> SemanticProviderMetadata:
        raise NotImplementedError

    @abstractmethod
    async def rerank_async(self, query: str, candidates: Sequence[str]) -> Sequence[float]:
        raise NotImplementedError
