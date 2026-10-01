from __future__ import annotations

from asyncio import to_thread
from math import isfinite

from src.core.services.visualization.providers.visualization_renderer import (
    RenderedVisualization,
    VisualizationKeyword,
    VisualizationRenderer,
)
from src.infrastructure.di.inject import inject
from src.infrastructure.providers.visualization.visualization_settings import (
    VisualizationSettings,
)
from src.infrastructure.repositories.analysis.word_cloud_analysis_repository import (
    WordCloudAnalysisRepository,
)


class VisualizationNotFoundError(LookupError):
    code = "analysis_not_found"
    message = "Analysis was not found"


class VisualizationTopicNotFoundError(LookupError):
    code = "analysis_topic_not_found"
    message = "Analysis topic was not found"


class VisualizationUnavailableError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class VisualizationFormatError(ValueError):
    code = "unsupported_visualization_format"
    message = "Visualization format must be png or svg"


@inject
class VisualizationService:
    def __init__(
        self,
        analysis_repository: WordCloudAnalysisRepository,
        renderer: VisualizationRenderer,
        settings: VisualizationSettings,
    ):
        self._analysis_repository = analysis_repository
        self._renderer = renderer
        self._settings = settings

    async def render_async(
        self,
        analysis_id: str,
        output_format: str,
    ) -> RenderedVisualization:
        normalized_format = self._normalize_format(output_format)

        analysis = await self._analysis_repository.get_visualization_source_by_id_async(
            analysis_id
        )
        if analysis is None:
            raise VisualizationNotFoundError()

        self._ensure_renderable_analysis(analysis.status)

        keywords = self._prepare_keywords(analysis.keywords)
        if not keywords:
            raise VisualizationUnavailableError(
                "analysis_visualization_empty",
                "Completed analysis has no visualizable keywords",
            )

        return await self._render_async(normalized_format, keywords)

    async def render_topic_async(
        self,
        analysis_id: str,
        topic_id: str,
        output_format: str,
    ) -> RenderedVisualization:
        normalized_format = self._normalize_format(output_format)
        analysis = await self._analysis_repository.get_topic_visualization_source_by_id_async(
            analysis_id
        )
        if analysis is None:
            raise VisualizationNotFoundError()

        self._ensure_renderable_analysis(analysis.status)

        normalized_topic_id = topic_id.strip()
        topic = next(
            (
                item
                for item in analysis.topics
                if self._logical_topic_id(item) == normalized_topic_id
            ),
            None,
        )
        if topic is None:
            raise VisualizationTopicNotFoundError()

        keywords = self._prepare_topic_keywords(topic.keyword_links)
        if not keywords:
            raise VisualizationUnavailableError(
                "analysis_topic_visualization_empty",
                "Analysis topic has no visualizable keywords",
            )

        return await self._render_async(normalized_format, keywords)

    @staticmethod
    def _normalize_format(output_format: str) -> str:
        normalized_format = output_format.strip().lower()
        if normalized_format not in {"png", "svg"}:
            raise VisualizationFormatError()
        return normalized_format

    @staticmethod
    def _ensure_renderable_analysis(status: str) -> None:
        if status == "failed":
            raise VisualizationUnavailableError(
                "analysis_failed",
                "Analysis failed and has no visualization",
            )
        if status != "completed":
            raise VisualizationUnavailableError(
                "analysis_visualization_not_ready",
                "Analysis visualization is not ready",
            )

    async def _render_async(
        self,
        output_format: str,
        keywords: tuple[VisualizationKeyword, ...],
    ) -> RenderedVisualization:
        if output_format == "png":
            return await to_thread(self._renderer.render_png, keywords)
        return await to_thread(self._renderer.render_svg, keywords)

    @staticmethod
    def _logical_topic_id(topic: object) -> str:
        metadata = getattr(topic, "metadata_json", None)
        if isinstance(metadata, dict):
            value = metadata.get("logical_topic_id")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return str(getattr(topic, "id"))

    def _prepare_topic_keywords(
        self,
        topic_keyword_links: object,
    ) -> tuple[VisualizationKeyword, ...]:
        ordered = sorted(
            topic_keyword_links,
            key=lambda link: (
                int(link.rank),
                str(link.keyword.canonical_text),
                str(link.keyword.text),
            ),
        )[: self._settings.maximum_words]

        result: list[VisualizationKeyword] = []
        seen_texts: set[str] = set()
        for link in ordered:
            text = str(link.keyword.text).strip()
            canonical_text = str(link.keyword.canonical_text).strip()
            score = float(link.relevance_score)
            if not text or not canonical_text or not isfinite(score) or score <= 0.0:
                continue
            if text in seen_texts:
                continue
            seen_texts.add(text)
            result.append(
                VisualizationKeyword(
                    text=text,
                    canonical_text=canonical_text,
                    rank=int(link.rank),
                    weight=score,
                )
            )
        return tuple(result)

    def _prepare_keywords(self, persisted_keywords: object) -> tuple[VisualizationKeyword, ...]:
        ordered = sorted(
            persisted_keywords,
            key=lambda item: (
                int(item.rank),
                str(item.canonical_text),
                str(item.text),
            ),
        )[: self._settings.maximum_words]

        result: list[VisualizationKeyword] = []
        seen_texts: set[str] = set()
        for item in ordered:
            text = str(item.text).strip()
            canonical_text = str(item.canonical_text).strip()
            score = float(item.final_score)
            if not text or not canonical_text or not isfinite(score) or score <= 0.0:
                continue
            if text in seen_texts:
                continue
            seen_texts.add(text)
            result.append(
                VisualizationKeyword(
                    text=text,
                    canonical_text=canonical_text,
                    rank=int(item.rank),
                    weight=score,
                )
            )
        return tuple(result)
