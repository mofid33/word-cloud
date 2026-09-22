from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence


class RerankerProvider(ABC):
    @abstractmethod
    async def rerank_async(self, query: str, candidates: Sequence[str]) -> Sequence[float]:
        raise NotImplementedError
