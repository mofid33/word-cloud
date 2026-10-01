from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import ImageColor, ImageFont

from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


@inject
class VisualizationSettings:
    __di_singleton__ = True

    def __init__(self, config_reader: ConfigReader):
        self.width = self._require_int(
            config_reader,
            "visualization.width",
            minimum=256,
            maximum=4096,
        )
        self.height = self._require_int(
            config_reader,
            "visualization.height",
            minimum=256,
            maximum=4096,
        )
        self.maximum_words = self._require_int(
            config_reader,
            "visualization.maximum_words",
            minimum=1,
            maximum=500,
        )
        self.random_seed = self._require_int(
            config_reader,
            "visualization.random_seed",
            minimum=0,
            maximum=2**32 - 1,
        )

        background = config_reader.require("visualization.background")
        if not isinstance(background, str) or not background.strip():
            raise ValueError("visualization.background must be a non-empty color string")
        try:
            ImageColor.getrgb(background.strip())
        except ValueError as exc:
            raise ValueError("visualization.background must be a valid color") from exc
        self.background = background.strip()

        font_family = config_reader.require("visualization.font_family")
        if not isinstance(font_family, str) or not font_family.strip():
            raise ValueError("visualization.font_family must be a non-empty string")
        self.font_family = font_family.strip()

        font_value = config_reader.require("visualization.font_path")
        if not isinstance(font_value, str) or not font_value.strip():
            raise ValueError("visualization.font_path must be a non-empty string")
        self.font_path = self._resolve_font_path(font_value.strip())
        if not self.font_path.is_file():
            raise FileNotFoundError(
                f"Visualization font file not found: {self.font_path}"
            )
        try:
            with self.font_path.open("rb"):
                pass
            ImageFont.truetype(str(self.font_path), size=32)
        except (OSError, ValueError) as exc:
            raise ValueError(
                f"Visualization font is unreadable or invalid: {self.font_path}"
            ) from exc

    @staticmethod
    def _require_int(
        config_reader: ConfigReader,
        key: str,
        *,
        minimum: int,
        maximum: int,
    ) -> int:
        value: Any = config_reader.require(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{key} must be an integer")
        if value < minimum or value > maximum:
            raise ValueError(
                f"{key} must be between {minimum} and {maximum}"
            )
        return value

    @staticmethod
    def _resolve_font_path(value: str) -> Path:
        matplotlib_prefix = "@matplotlib/"
        if value.startswith(matplotlib_prefix):
            filename = value[len(matplotlib_prefix) :]
            if not filename or Path(filename).name != filename:
                raise ValueError(
                    "visualization.font_path matplotlib token must contain only a filename"
                )
            from matplotlib import get_data_path

            return (Path(get_data_path()) / "fonts" / "ttf" / filename).resolve()

        path = Path(value).expanduser()
        if path.is_absolute():
            return path.resolve()
        project_root = Path(__file__).resolve().parents[4]
        return (project_root / path).resolve()
