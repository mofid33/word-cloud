from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from src.core.services.course.course_analysis_service import CourseAnalysisService
from src.core.services.media.media_analysis_service import MediaAnalysisService
from src.core.services.soldier_concern.soldier_concern_analysis_service import (
    SoldierConcernAnalysisService,
)
from src.infrastructure.di.bootstrap import bootstrap_di
from src.infrastructure.di.inject import reset_di_state, resolve
from tests.evaluation.phase10_gold_dataset import (
    Phase10GoldDatasetLoader,
    Phase10GoldEvaluator,
    SUPPORTED_PROFILES,
    SUPPORTED_SPLITS,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DATASET_ENV = {
    "COURSE": "PHASE10_GOLD_COURSE_DIR",
    "SOLDIER_CONCERN": "PHASE10_GOLD_SOLDIER_DIR",
    "MEDIA": "PHASE10_GOLD_MEDIA_DIR",
}
_SERVICE_TYPES = {
    "COURSE": CourseAnalysisService,
    "SOLDIER_CONCERN": SoldierConcernAnalysisService,
    "MEDIA": MediaAnalysisService,
}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate a Phase 10 profile against an adjudicated Gold Dataset."
    )
    parser.add_argument("--profile", choices=SUPPORTED_PROFILES, required=True)
    parser.add_argument("--split", choices=SUPPORTED_SPLITS, required=True)
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="Dataset directory. When omitted, the profile-specific environment variable is used.",
    )
    return parser.parse_args()


def _dataset_dir(profile: str, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    variable = _DATASET_ENV[profile]
    value = os.getenv(variable)
    if not value:
        raise RuntimeError(f"Required Gold Dataset location is missing: {variable}")
    return Path(value)


async def _run_async(args: argparse.Namespace) -> dict[str, object]:
    loader = Phase10GoldDatasetLoader(PROJECT_ROOT)
    dataset = loader.load(
        _dataset_dir(args.profile, args.dataset_dir),
        expected_profile=args.profile,
    )

    reset_di_state()
    bootstrap_di()
    service = resolve(_SERVICE_TYPES[args.profile])
    result = await Phase10GoldEvaluator().evaluate_async(
        dataset,
        service,
        split=args.split,
    )
    return result.to_dict()


def main() -> None:
    args = _arguments()
    payload = asyncio.run(_run_async(args))
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
