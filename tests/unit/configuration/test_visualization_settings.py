from __future__ import annotations

import unittest

from src.infrastructure.providers.visualization.visualization_settings import (
    VisualizationSettings,
)


class _Config:
    def __init__(self, **overrides):
        self.values = {
            "visualization.width": 1200,
            "visualization.height": 675,
            "visualization.maximum_words": 100,
            "visualization.maximum_concurrent_renders": 2,
            "visualization.background": "#FFFFFF",
            "visualization.font_family": "DejaVu Sans",
            "visualization.font_path": "@matplotlib/DejaVuSans.ttf",
            "visualization.random_seed": 42,
        }
        self.values.update(overrides)

    def require(self, key):
        if key not in self.values:
            raise KeyError(key)
        return self.values[key]


class VisualizationSettingsTests(unittest.TestCase):
    def test_valid_portable_font_configuration(self) -> None:
        settings = VisualizationSettings(_Config())
        self.assertEqual(settings.width, 1200)
        self.assertEqual(settings.height, 675)
        self.assertEqual(settings.maximum_words, 100)
        self.assertTrue(settings.font_path.is_file())

    def test_invalid_dimensions_are_rejected(self) -> None:
        for key, value in (
            ("visualization.width", 0),
            ("visualization.height", 5000),
            ("visualization.width", True),
            ("visualization.height", 512.5),
        ):
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    VisualizationSettings(_Config(**{key: value}))

    def test_invalid_word_limit_is_rejected(self) -> None:
        for value in (0, -1, 501, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    VisualizationSettings(
                        _Config(**{"visualization.maximum_words": value})
                    )

    def test_invalid_seed_is_rejected(self) -> None:
        for value in (-1, 2**32, True, 1.5):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    VisualizationSettings(
                        _Config(**{"visualization.random_seed": value})
                    )

    def test_missing_or_invalid_font_fails_fast(self) -> None:
        with self.assertRaises(FileNotFoundError):
            VisualizationSettings(
                _Config(**{"visualization.font_path": "missing-font.ttf"})
            )
        with self.assertRaises(ValueError):
            VisualizationSettings(
                _Config(**{"visualization.font_path": "@matplotlib/../font.ttf"})
            )


if __name__ == "__main__":
    unittest.main()
