from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any


class TopicModelProvider(ABC):
    @abstractmethod
    async def analyze_topics_async(
        self,
        documents: Sequence[str],
    ) -> Sequence[dict[str, Any]]:
        raise NotImplementedError
