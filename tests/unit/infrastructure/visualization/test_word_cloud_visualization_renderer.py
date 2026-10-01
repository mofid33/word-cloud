from __future__ import annotations

from io import BytesIO
import unittest
import xml.etree.ElementTree as ET

from PIL import Image

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
        "visualization.width": 800,
        "visualization.height": 450,
        "visualization.maximum_words": 20,
        "visualization.background": "#FFFFFF",
        "visualization.font_family": "DejaVu Sans",
        "visualization.font_path": "@matplotlib/DejaVuSans.ttf",
        "visualization.random_seed": 17,
    }

    def require(self, key):
        return self.values[key]


class WordCloudVisualizationRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.renderer = WordCloudVisualizationRenderer(VisualizationSettings(_Config()))
        cls.keywords = (
            VisualizationKeyword("یادگیری ماشین", "یادگیری ماشین", 1, 1.0),
            VisualizationKeyword("نیم\u200cفاصله", "نیم\u200cفاصله", 2, 0.8),
            VisualizationKeyword("Python فارسی ۱۴۰۵", "Python فارسی ۱۴۰۵", 3, 0.6),
        )

    def test_persian_and_rtl_text_is_shaped(self) -> None:
        shaped = self.renderer.shape_text("یادگیری ماشین")
        self.assertNotEqual(shaped, "یادگیری ماشین")
        self.assertTrue(any("\uFB50" <= char <= "\uFEFF" for char in shaped))

        zwnj = self.renderer.shape_text("نیم\u200cفاصله")
        self.assertTrue(zwnj)
        mixed = self.renderer.shape_text("Python فارسی ۱۴۰۵")
        self.assertIn("Python", mixed)
        self.assertIn("۱۴۰۵", mixed)

    def test_png_is_valid_non_empty_and_deterministic(self) -> None:
        first = self.renderer.render_png(self.keywords)
        second = self.renderer.render_png(self.keywords)
        self.assertEqual(first.media_type, "image/png")
        self.assertTrue(first.content.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(first.content, second.content)

        with Image.open(BytesIO(first.content)) as image:
            self.assertEqual(image.size, (800, 450))
            extrema = image.convert("L").getextrema()
            self.assertNotEqual(extrema[0], extrema[1])

    def test_svg_is_valid_safe_and_deterministic(self) -> None:
        hostile = self.keywords + (
            VisualizationKeyword('<script>alert("x") & test</script>', "hostile", 4, 0.4),
        )
        first = self.renderer.render_svg(hostile)
        second = self.renderer.render_svg(hostile)
        self.assertEqual(first.media_type, "image/svg+xml")
        self.assertEqual(first.content, second.content)
        root = ET.fromstring(first.content)
        self.assertTrue(root.tag.endswith("svg"))

        text = first.content.decode("utf-8")
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;script&gt;", text)
        logical_values = [
            element.attrib.get("data-logical-text")
            for element in root.iter()
            if element.tag.endswith("text")
        ]
        self.assertIn("یادگیری ماشین", logical_values)
        self.assertIn("نیم\u200cفاصله", logical_values)

    def test_numbers_and_punctuation_render_without_error(self) -> None:
        items = (
            VisualizationKeyword("نسخه 3.14", "نسخه 3.14", 1, 1.0),
            VisualizationKeyword("هوش مصنوعی؛ ایران", "هوش مصنوعی؛ ایران", 2, 0.8),
        )
        self.assertGreater(len(self.renderer.render_png(items).content), 100)
        self.assertGreater(len(self.renderer.render_svg(items).content), 100)


if __name__ == "__main__":
    unittest.main()
