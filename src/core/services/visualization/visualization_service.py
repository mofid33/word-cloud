from __future__ import annotations

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
        normalized_format = output_format.strip().lower()
        if normalized_format not in {"png", "svg"}:
            raise VisualizationFormatError()

        analysis = await self._analysis_repository.get_visualization_source_by_id_async(
            analysis_id
        )
        if analysis is None:
            raise VisualizationNotFoundError()

        if analysis.status == "failed":
            raise VisualizationUnavailableError(
                "analysis_failed",
                "Analysis failed and has no visualization",
            )
        if analysis.status != "completed":
            raise VisualizationUnavailableError(
                "analysis_visualization_not_ready",
                "Analysis visualization is not ready",
            )

        keywords = self._prepare_keywords(analysis.keywords)
        if not keywords:
            raise VisualizationUnavailableError(
                "analysis_visualization_empty",
                "Completed analysis has no visualizable keywords",
            )

        if normalized_format == "png":
            return self._renderer.render_png(keywords)
        return self._renderer.render_svg(keywords)

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
