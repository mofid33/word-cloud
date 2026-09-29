from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class TopicModelDocument:
    document_id: str
    text: str


@dataclass(frozen=True)
class TopicModelCluster:
    cluster_id: str
    document_ids: tuple[str, ...]
    cohesion: float


@dataclass(frozen=True)
class TopicModelMetadata:
    provider: str
    provider_version: str
    model_identifier: str
    model_revision: str | None
    configuration_fingerprint: str


@dataclass(frozen=True)
class TopicModelResult:
    clusters: tuple[TopicModelCluster, ...]
    metadata: TopicModelMetadata


class TopicModelProvider(ABC):
    @abstractmethod
    async def analyze_topics_async(
        self,
        documents: Sequence[TopicModelDocument],
    ) -> TopicModelResult:
        raise NotImplementedError
