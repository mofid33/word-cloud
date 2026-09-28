from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProfileKeywordResult:
    text: str
    canonical_text: str
    rank: int
    final_score: float
    statistical_score: float
    semantic_score: float
    coverage: float
    frequency: int
    signals: dict[str, float | int | str | bool | None]


@dataclass(frozen=True)
class StructuredProfileResult:
    profile: str
    keywords: tuple[ProfileKeywordResult, ...]
    metrics: dict[str, Any]
    profile_result: dict[str, Any]
    model_version: str
    scoring_version: str
