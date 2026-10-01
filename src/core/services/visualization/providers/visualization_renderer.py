from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class VisualizationKeyword:
    text: str
    canonical_text: str
    rank: int
    weight: float


@dataclass(frozen=True)
class RenderedVisualization:
    content: bytes
    media_type: str


class VisualizationRenderer(ABC):
    @abstractmethod
    def render_png(
        self,
        keywords: tuple[VisualizationKeyword, ...],
    ) -> RenderedVisualization:
        raise NotImplementedError

    @abstractmethod
    def render_svg(
        self,
        keywords: tuple[VisualizationKeyword, ...],
    ) -> RenderedVisualization:
        raise NotImplementedError
