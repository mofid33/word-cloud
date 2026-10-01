from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar


class AnalysisQueueError(RuntimeError):
    pass


class AnalysisQueueInvalidMessageError(AnalysisQueueError):
    def __init__(self, analysis_id: str | None = None):
        super().__init__("Analysis queue message is invalid")
        self.analysis_id = analysis_id


@dataclass(frozen=True)
class AnalysisQueueJob:
    version: int
    analysis_id: str
    analysis_type: str

    CURRENT_VERSION: ClassVar[int] = 1
    _ANALYSIS_TYPES: ClassVar[frozenset[str]] = frozenset(
        {"COURSE", "SOLDIER_CONCERN", "MEDIA"}
    )

    @classmethod
    def create(cls, *, analysis_id: str, analysis_type: str) -> "AnalysisQueueJob":
        return cls(
            version=cls.CURRENT_VERSION,
            analysis_id=analysis_id,
            analysis_type=analysis_type,
        ).validated()

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AnalysisQueueJob":
        if not isinstance(payload, dict):
            raise ValueError("Queue payload must be an object")
        if set(payload) != {"version", "analysis_id", "analysis_type"}:
            raise ValueError("Queue payload fields are invalid")
        return cls(
            version=payload["version"],
            analysis_id=payload["analysis_id"],
            analysis_type=payload["analysis_type"],
        ).validated()

    def validated(self) -> "AnalysisQueueJob":
        if isinstance(self.version, bool) or not isinstance(self.version, int):
            raise ValueError("Queue payload version must be an integer")
        if self.version != self.CURRENT_VERSION:
            raise ValueError("Queue payload version is unsupported")
        if (
            not isinstance(self.analysis_id, str)
            or not self.analysis_id.strip()
            or self.analysis_id != self.analysis_id.strip()
            or len(self.analysis_id) > 64
        ):
            raise ValueError("Queue payload analysis_id is invalid")
        if self.analysis_type not in self._ANALYSIS_TYPES:
            raise ValueError("Queue payload analysis_type is invalid")
        return self

    def to_payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "analysis_id": self.analysis_id,
            "analysis_type": self.analysis_type,
        }


@dataclass(frozen=True)
class AnalysisQueueMessage:
    job: AnalysisQueueJob
    receipt: str
    attempt: int


class AnalysisQueueProvider(ABC):
    @abstractmethod
    async def enqueue_async(
        self,
        analysis_id: str,
        payload: dict[str, Any],
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def receive_async(
        self,
        *,
        timeout_seconds: float,
    ) -> AnalysisQueueMessage | None:
        raise NotImplementedError

    @abstractmethod
    async def acknowledge_async(self, message: AnalysisQueueMessage) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def requeue_async(
        self,
        message: AnalysisQueueMessage,
        *,
        delay_seconds: float,
        error_code: str,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def fail_async(
        self,
        message: AnalysisQueueMessage,
        *,
        error_code: str,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def extend_lease_async(self, message: AnalysisQueueMessage) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def recover_orphaned_async(self, *, limit: int) -> int:
        raise NotImplementedError

    @abstractmethod
    async def put_transient_payload_async(
        self,
        analysis_id: str,
        documents: list[dict[str, Any]],
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_transient_payload_async(
        self,
        analysis_id: str,
    ) -> list[dict[str, Any]] | None:
        raise NotImplementedError

    @abstractmethod
    async def touch_transient_payload_async(self, analysis_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def delete_transient_payload_async(self, analysis_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def close_async(self) -> None:
        raise NotImplementedError
