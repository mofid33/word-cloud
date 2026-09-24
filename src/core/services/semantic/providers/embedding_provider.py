from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.core.services.semantic.providers.provider_metadata import SemanticProviderMetadata


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def metadata(self) -> SemanticProviderMetadata:
        raise NotImplementedError

    @abstractmethod
    async def embed_async(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        raise NotImplementedError
