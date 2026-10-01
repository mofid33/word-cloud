from __future__ import annotations

from io import BytesIO
from unicodedata import normalize
from xml.sax.saxutils import escape, quoteattr

import arabic_reshaper
from bidi.algorithm import get_display
from wordcloud import WordCloud

from src.core.services.visualization.providers.visualization_renderer import (
    RenderedVisualization,
    VisualizationKeyword,
    VisualizationRenderer,
)
from src.infrastructure.di.inject import inject
from src.infrastructure.providers.visualization.visualization_settings import (
    VisualizationSettings,
)


@inject
class WordCloudVisualizationRenderer(VisualizationRenderer):
    def __init__(self, settings: VisualizationSettings):
        self._settings = settings

    def render_png(
        self,
        keywords: tuple[VisualizationKeyword, ...],
    ) -> RenderedVisualization:
        cloud, _ = self._build_cloud(keywords)
        image = cloud.to_image()
        output = BytesIO()
        image.save(
            output,
            format="PNG",
            optimize=False,
            compress_level=9,
        )
        return RenderedVisualization(
            content=output.getvalue(),
            media_type="image/png",
        )

    def render_svg(
        self,
        keywords: tuple[VisualizationKeyword, ...],
    ) -> RenderedVisualization:
        cloud, logical_by_visual = self._build_cloud(keywords)
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{self._settings.width}" height="{self._settings.height}" '
                f'viewBox="0 0 {self._settings.width} {self._settings.height}">'
            ),
            (
                f'<rect width="100%" height="100%" fill='
                f'{quoteattr(self._settings.background)}/>'
            ),
        ]

        for layout_item in cloud.layout_:
            (visual_text, _normalized_frequency), font_size, position, orientation, color = (
                layout_item
            )
            if orientation is not None:
                raise RuntimeError("Vertical word orientation is disabled for Persian rendering")
            logical_text = logical_by_visual.get(visual_text, visual_text)
            y, x = position
            lines.append(
                "<text "
                f'x="{int(x)}" y="{int(y)}" '
                f'font-size="{int(font_size)}" '
                f'font-family={quoteattr(self._settings.font_family + ", sans-serif")} '
                'direction="ltr" unicode-bidi="bidi-override" '
                'dominant-baseline="text-before-edge" '
                f'fill={quoteattr(str(color))} '
                f'data-logical-text={quoteattr(logical_text)}>'
                f'{escape(visual_text)}</text>'
            )

        lines.append("</svg>")
        return RenderedVisualization(
            content=("\n".join(lines) + "\n").encode("utf-8"),
            media_type="image/svg+xml",
        )

    def _build_cloud(
        self,
        keywords: tuple[VisualizationKeyword, ...],
    ) -> tuple[WordCloud, dict[str, str]]:
        frequencies: dict[str, float] = {}
        logical_by_visual: dict[str, str] = {}
        for keyword in keywords:
            visual_text = self.shape_text(keyword.text)
            existing = frequencies.get(visual_text)
            if existing is None or keyword.weight > existing:
                frequencies[visual_text] = keyword.weight
                logical_by_visual[visual_text] = keyword.text

        if not frequencies:
            raise ValueError("At least one positive visualization keyword is required")

        cloud = WordCloud(
            width=self._settings.width,
            height=self._settings.height,
            background_color=self._settings.background,
            max_words=self._settings.maximum_words,
            font_path=str(self._settings.font_path),
            random_state=self._settings.random_seed,
            prefer_horizontal=1.0,
            collocations=False,
            relative_scaling=0.5,
        )
        cloud.generate_from_frequencies(frequencies)
        return cloud, logical_by_visual

    @staticmethod
    def shape_text(text: str) -> str:
        logical = normalize("NFC", text)
        reshaped = arabic_reshaper.reshape(logical)
        return get_display(reshaped)
