from __future__ import annotations

import math
from dataclasses import dataclass

from src.infrastructure.utils.config_reader import ConfigReader


@dataclass(frozen=True)
class ProfileScoringConfig:
    scoring_version: str
    maximum_results: int
    diversity_candidate_pool_size: int
    weights: dict[str, float]


def load_profile_scoring_config(
    config_reader: ConfigReader,
    *,
    profile_key: str,
    required_signals: tuple[str, ...],
) -> ProfileScoringConfig:
    prefix = f"analysis_profiles.{profile_key}"
    scoring_version = config_reader.require(f"{prefix}.scoring_version")
    if not isinstance(scoring_version, str) or not scoring_version.strip():
        raise ValueError(f"Configuration '{prefix}.scoring_version' must be a non-empty string")

    maximum_results = config_reader.require(f"{prefix}.maximum_results")
    if (
        isinstance(maximum_results, bool)
        or not isinstance(maximum_results, int)
        or maximum_results <= 0
    ):
        raise ValueError(
            f"Configuration '{prefix}.maximum_results' must be an integer > 0"
        )

    diversity_candidate_pool_size = config_reader.require(
        f"{prefix}.diversity_candidate_pool_size"
    )
    if (
        isinstance(diversity_candidate_pool_size, bool)
        or not isinstance(diversity_candidate_pool_size, int)
        or diversity_candidate_pool_size <= 0
    ):
        raise ValueError(
            f"Configuration '{prefix}.diversity_candidate_pool_size' "
            "must be an integer > 0"
        )
    if diversity_candidate_pool_size < maximum_results:
        raise ValueError(
            f"Configuration '{prefix}.diversity_candidate_pool_size' "
            "must be >= maximum_results"
        )

    weights: dict[str, float] = {}
    for signal in required_signals:
        key = f"{prefix}.weights.{signal}"
        value = config_reader.require(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Configuration '{key}' must be numeric")
        numeric = float(value)
        if not math.isfinite(numeric) or numeric < 0.0 or numeric > 1.0:
            raise ValueError(
                f"Configuration '{key}' must be finite and within [0, 1]"
            )
        weights[signal] = numeric

    total = sum(weights.values())
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(
            f"Configuration '{prefix}.weights' must sum to 1.0"
        )

    return ProfileScoringConfig(
        scoring_version=scoring_version.strip(),
        maximum_results=maximum_results,
        diversity_candidate_pool_size=diversity_candidate_pool_size,
        weights=weights,
    )


def weighted_signal_score(
    values: dict[str, float | None],
    weights: dict[str, float],
) -> tuple[float, dict[str, float]]:
    active = {
        name: float(weights[name])
        for name, value in values.items()
        if value is not None and weights.get(name, 0.0) > 0.0
    }
    total_weight = sum(active.values())
    if total_weight <= 0.0:
        return 0.0, {}

    effective = {
        name: weight / total_weight
        for name, weight in active.items()
    }
    score = sum(
        effective[name] * float(values[name])
        for name in effective
    )
    return min(max(score, 0.0), 1.0), effective
