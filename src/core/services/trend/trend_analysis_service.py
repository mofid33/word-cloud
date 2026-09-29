from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from src.core.services.analysis.profile_result import ProfileTopicResult
from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


@dataclass(frozen=True)
class TrendDocument:
    document_id: str
    timestamp: datetime


@dataclass(frozen=True)
class TopicTrendResult:
    topic_id: str
    previous_prevalence: float
    current_prevalence: float
    growth: float
    classification: str


@dataclass(frozen=True)
class TrendAnalysisResult:
    available: bool
    reason: str | None
    window_days: int
    comparison_end: datetime | None
    trends: tuple[TopicTrendResult, ...]
    scoring_version: str


@inject
class TrendAnalysisService:
    def __init__(self, config_reader: ConfigReader):
        self._window_days = self._positive_int(
            config_reader.require("trend_analysis.window_days"),
            "trend_analysis.window_days",
        )
        self._minimum_documents = self._positive_int(
            config_reader.require("trend_analysis.minimum_documents_per_window"),
            "trend_analysis.minimum_documents_per_window",
        )
        self._growth_threshold = self._unit_float(
            config_reader.require("trend_analysis.growth_threshold"),
            "trend_analysis.growth_threshold",
            allow_zero=False,
        )
        self._minimum_prevalence = self._unit_float(
            config_reader.require("trend_analysis.minimum_prevalence"),
            "trend_analysis.minimum_prevalence",
            allow_zero=True,
        )
        version = config_reader.require("trend_analysis.scoring_version")
        if not isinstance(version, str) or not version.strip():
            raise ValueError(
                "trend_analysis.scoring_version must be a non-empty string"
            )
        self._scoring_version = version.strip()

    def analyze(
        self,
        *,
        documents: Sequence[TrendDocument],
        topics: Sequence[ProfileTopicResult],
    ) -> TrendAnalysisResult:
        materialized = tuple(documents)
        if not materialized:
            return self._unavailable("no_timestamped_documents")

        self._validate_documents(materialized)
        comparison_end = max(item.timestamp for item in materialized)
        current_start = comparison_end - timedelta(days=self._window_days)
        previous_start = current_start - timedelta(days=self._window_days)

        current = tuple(
            item for item in materialized
            if current_start < item.timestamp <= comparison_end
        )
        previous = tuple(
            item for item in materialized
            if previous_start < item.timestamp <= current_start
        )
        if (
            len(current) < self._minimum_documents
            or len(previous) < self._minimum_documents
        ):
            return TrendAnalysisResult(
                available=False,
                reason="insufficient_documents_per_window",
                window_days=self._window_days,
                comparison_end=comparison_end,
                trends=(),
                scoring_version=self._scoring_version,
            )

        current_ids = {item.document_id for item in current}
        previous_ids = {item.document_id for item in previous}
        trends: list[TopicTrendResult] = []
        for topic in topics:
            topic_ids = set(topic.document_ids)
            previous_prevalence = len(topic_ids & previous_ids) / len(previous_ids)
            current_prevalence = len(topic_ids & current_ids) / len(current_ids)
            if max(previous_prevalence, current_prevalence) < self._minimum_prevalence:
                classification = "stable"
            else:
                growth = current_prevalence - previous_prevalence
                if growth >= self._growth_threshold:
                    classification = "emerging"
                elif growth <= -self._growth_threshold:
                    classification = "declining"
                else:
                    classification = "stable"
            growth = current_prevalence - previous_prevalence
            trends.append(
                TopicTrendResult(
                    topic_id=topic.topic_id,
                    previous_prevalence=previous_prevalence,
                    current_prevalence=current_prevalence,
                    growth=growth,
                    classification=classification,
                )
            )

        trends.sort(
            key=lambda item: (
                -abs(item.growth),
                item.topic_id,
            )
        )
        return TrendAnalysisResult(
            available=True,
            reason=None,
            window_days=self._window_days,
            comparison_end=comparison_end,
            trends=tuple(trends),
            scoring_version=self._scoring_version,
        )

    def _unavailable(self, reason: str) -> TrendAnalysisResult:
        return TrendAnalysisResult(
            available=False,
            reason=reason,
            window_days=self._window_days,
            comparison_end=None,
            trends=(),
            scoring_version=self._scoring_version,
        )

    @staticmethod
    def _validate_documents(documents: Sequence[TrendDocument]) -> None:
        ids: set[str] = set()
        for item in documents:
            if item.document_id in ids:
                raise ValueError("Trend document_id values must be unique")
            if item.timestamp.tzinfo is None or item.timestamp.utcoffset() is None:
                raise ValueError("Trend timestamps must be timezone-aware")
            ids.add(item.document_id)

    @staticmethod
    def _positive_int(value: object, key: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"Configuration '{key}' must be an integer > 0")
        return value

    @staticmethod
    def _unit_float(
        value: object,
        key: str,
        *,
        allow_zero: bool,
    ) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Configuration '{key}' must be numeric")
        number = float(value)
        lower_ok = number >= 0 if allow_zero else number > 0
        if not math.isfinite(number) or not lower_ok or number > 1:
            bound = "[0, 1]" if allow_zero else "(0, 1]"
            raise ValueError(f"Configuration '{key}' must be finite and in {bound}")
        return number
