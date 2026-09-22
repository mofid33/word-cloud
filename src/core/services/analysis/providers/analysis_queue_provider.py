from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AnalysisQueueProvider(ABC):
    @abstractmethod
    async def enqueue_async(
        self,
        analysis_id: str,
        payload: dict[str, Any],
    ) -> None:
        raise NotImplementedError
