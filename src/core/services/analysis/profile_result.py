from __future__ import annotations

from dataclasses import dataclass, field
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
class ProfileTopicKeywordResult:
    canonical_text: str
    text: str
    rank: int
    relevance_score: float


@dataclass(frozen=True)
class ProfileTopicResult:
    topic_id: str
    label: str
    rank: int
    prevalence: float
    coverage: float
    representative_keyphrases: tuple[ProfileTopicKeywordResult, ...]
    document_ids: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StructuredProfileResult:
    profile: str
    keywords: tuple[ProfileKeywordResult, ...]
    metrics: dict[str, Any]
    profile_result: dict[str, Any]
    model_version: str
    scoring_version: str
    topics: tuple[ProfileTopicResult, ...] = ()
