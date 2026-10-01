from __future__ import annotations

import os
from statistics import median
from time import perf_counter
import unittest

from src.core.services.visualization.providers.visualization_renderer import (
    VisualizationKeyword,
)
from src.infrastructure.providers.visualization.visualization_settings import (
    VisualizationSettings,
)
from src.infrastructure.providers.visualization.word_cloud_visualization_renderer import (
    WordCloudVisualizationRenderer,
)


class _Config:
    values = {
        "visualization.width": 1200,
        "visualization.height": 675,
        "visualization.maximum_words": 100,
        "visualization.background": "#FFFFFF",
        "visualization.font_family": "DejaVu Sans",
        "visualization.font_path": "@matplotlib/DejaVuSans.ttf",
        "visualization.random_seed": 42,
    }

    def require(self, key):
        return self.values[key]


@unittest.skipUnless(
    os.getenv("RUN_PHASE13_RENDER_BENCHMARK") == "1",
    "Set RUN_PHASE13_RENDER_BENCHMARK=1 to run the rendering performance baseline",
)
class Phase13VisualizationPerformanceTests(unittest.TestCase):
    def test_rendering_latency_and_output_size_baseline(self) -> None:
        renderer = WordCloudVisualizationRenderer(VisualizationSettings(_Config()))
        keywords = tuple(
            VisualizationKeyword(
                text=f"کلیدواژه فارسی {index}",
                canonical_text=f"کلیدواژه فارسی {index}",
                rank=index + 1,
                weight=1.0 / (index + 1),
            )
            for index in range(100)
        )

        png_times = []
        svg_times = []
        png = None
        svg = None
        for _ in range(5):
            started = perf_counter()
            png = renderer.render_png(keywords)
            png_times.append(perf_counter() - started)

            started = perf_counter()
            svg = renderer.render_svg(keywords)
            svg_times.append(perf_counter() - started)

        assert png is not None and svg is not None
        print(
            "PHASE13_RENDER_BASELINE "
            f"png_p50_ms={median(png_times) * 1000:.2f} "
            f"svg_p50_ms={median(svg_times) * 1000:.2f} "
            f"png_bytes={len(png.content)} "
            f"svg_bytes={len(svg.content)} "
            f"maximum_words={len(keywords)}"
        )
        self.assertLess(len(png.content), 10 * 1024 * 1024)
        self.assertLess(len(svg.content), 5 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
