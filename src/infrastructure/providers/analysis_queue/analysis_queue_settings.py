from __future__ import annotations

import math
from dataclasses import dataclass

from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


@inject
@dataclass(frozen=True, init=False)
class AnalysisQueueSettings:
    __di_singleton__ = True

    backend: str
    maximum_attempts: int
    retry_initial_delay_seconds: float
    retry_max_delay_seconds: float
    receive_timeout_seconds: float
    poll_interval_seconds: float
    visibility_timeout_seconds: float
    heartbeat_interval_seconds: float
    processing_stale_seconds: float
    concurrency: int

    def __init__(self, config_reader: ConfigReader):
        object.__setattr__(
            self,
            "backend",
            self._string(config_reader, "analysis_queue.backend"),
        )
        object.__setattr__(
            self,
            "maximum_attempts",
            self._integer(config_reader, "analysis_queue.maximum_attempts", minimum=1),
        )
        object.__setattr__(
            self,
            "retry_initial_delay_seconds",
            self._number(
                config_reader,
                "analysis_queue.retry_initial_delay_seconds",
                minimum=0.0,
            ),
        )
        object.__setattr__(
            self,
            "retry_max_delay_seconds",
            self._number(
                config_reader,
                "analysis_queue.retry_max_delay_seconds",
                minimum=0.0,
            ),
        )
        object.__setattr__(
            self,
            "receive_timeout_seconds",
            self._number(
                config_reader,
                "analysis_queue.receive_timeout_seconds",
                minimum=0.001,
            ),
        )
        object.__setattr__(
            self,
            "poll_interval_seconds",
            self._number(
                config_reader,
                "analysis_queue.poll_interval_seconds",
                minimum=0.001,
            ),
        )
        object.__setattr__(
            self,
            "visibility_timeout_seconds",
            self._number(
                config_reader,
                "analysis_queue.visibility_timeout_seconds",
                minimum=1.0,
            ),
        )
        object.__setattr__(
            self,
            "heartbeat_interval_seconds",
            self._number(
                config_reader,
                "analysis_queue.heartbeat_interval_seconds",
                minimum=0.001,
            ),
        )
        object.__setattr__(
            self,
            "processing_stale_seconds",
            self._number(
                config_reader,
                "analysis_queue.processing_stale_seconds",
                minimum=1.0,
            ),
        )
        object.__setattr__(
            self,
            "concurrency",
            self._integer(config_reader, "analysis_queue.concurrency", minimum=1),
        )

        if self.backend != "postgres":
            raise ValueError("analysis_queue.backend must be 'postgres'")
        if self.retry_max_delay_seconds < self.retry_initial_delay_seconds:
            raise ValueError(
                "analysis_queue.retry_max_delay_seconds must be >= retry_initial_delay_seconds"
            )
        if self.poll_interval_seconds > self.receive_timeout_seconds:
            raise ValueError(
                "analysis_queue.poll_interval_seconds must be <= receive_timeout_seconds"
            )
        if self.heartbeat_interval_seconds >= self.visibility_timeout_seconds:
            raise ValueError(
                "analysis_queue.heartbeat_interval_seconds must be < visibility_timeout_seconds"
            )
        if self.processing_stale_seconds < self.visibility_timeout_seconds:
            raise ValueError(
                "analysis_queue.processing_stale_seconds must be >= visibility_timeout_seconds"
            )

    @staticmethod
    def _string(config_reader: ConfigReader, key: str) -> str:
        value = config_reader.require(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a non-empty string")
        return value.strip().lower()

    @staticmethod
    def _integer(
        config_reader: ConfigReader,
        key: str,
        *,
        minimum: int,
    ) -> int:
        value = config_reader.require(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{key} must be an integer")
        if value < minimum:
            raise ValueError(f"{key} is below the minimum")
        return value

    @staticmethod
    def _number(
        config_reader: ConfigReader,
        key: str,
        *,
        minimum: float,
    ) -> float:
        value = config_reader.require(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be a finite number")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{key} must be a finite number")
        if number < minimum:
            raise ValueError(f"{key} is below the minimum")
        return number
