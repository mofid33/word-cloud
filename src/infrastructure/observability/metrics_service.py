from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from src.infrastructure.di.inject import inject


@inject
class MetricsService:
    __di_singleton__ = True

    def __init__(self):
        self._registry = CollectorRegistry()
        self._http_requests = Counter("word_cloud_http_requests_total", "HTTP requests", ("method", "route", "status"), registry=self._registry)
        self._http_duration = Histogram("word_cloud_http_request_duration_seconds", "HTTP request duration", ("method", "route"), registry=self._registry)
        self._readiness = Gauge("word_cloud_readiness", "Readiness state (1 ready, 0 not ready)", registry=self._registry)

    def observe_http(self, *, method: str, route: str, status_code: int, duration_seconds: float) -> None:
        self._http_requests.labels(method=method, route=route, status=str(status_code)).inc()
        self._http_duration.labels(method=method, route=route).observe(duration_seconds)

    def set_readiness(self, ready: bool) -> None:
        self._readiness.set(1 if ready else 0)

    def render(self) -> bytes:
        return generate_latest(self._registry)
