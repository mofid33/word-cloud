from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence


class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed_async(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        raise NotImplementedError
