from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticProviderMetadata:
    provider: str
    provider_version: str
    model_identifier: str
    model_revision: str | None
    device: str
    configuration_fingerprint: str
