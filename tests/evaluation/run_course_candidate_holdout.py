from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from src.core.services.candidate.candidate_extraction_service import CandidateExtractionService
from src.core.services.persian_text.persian_text_processor import PersianTextProcessor
from src.core.services.ranking.hybrid_ranking_service import HybridRankingService
from src.core.services.semantic.semantic_analysis_service import SemanticAnalysisService
from src.core.services.statistical.statistical_analysis_service import StatisticalAnalysisService
from src.infrastructure.di.bootstrap import bootstrap_di
from src.infrastructure.di.inject import reset_di_state, resolve
from src.infrastructure.utils.config_reader import ConfigReader
from tests.evaluation.course_candidate_evaluation import (
    CourseCandidateDatasetLoader,
    CourseCandidateTuningEngine,
    PROJECT_ROOT,
)
from tests.evaluation.course_candidate_holdout import (
    CourseCandidateHoldoutEvaluator,
    load_frozen_course_tuning_evidence,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the frozen Phase 10 COURSE engineering-tuned weights "
            "on the previously untouched holdout split. No weight search is performed."
        )
    )
    parser.add_argument("--materialized", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


async def _run_async(args: argparse.Namespace) -> dict[str, object]:
    dataset = CourseCandidateDatasetLoader(PROJECT_ROOT).load(
        args.materialized,
        args.review,
    )
    evidence = load_frozen_course_tuning_evidence()

    reset_di_state()
    bootstrap_di()
    engine = CourseCandidateTuningEngine(
        resolve(PersianTextProcessor),
        resolve(CandidateExtractionService),
        resolve(StatisticalAnalysisService),
        resolve(SemanticAnalysisService),
        resolve(HybridRankingService),
        resolve(ConfigReader),
    )
    result = await CourseCandidateHoldoutEvaluator(engine).evaluate_async(
        dataset,
        evidence,
    )
    return result.to_dict()


def main() -> None:
    args = _arguments()
    payload = asyncio.run(_run_async(args))
    serialized = (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    if args.output is not None:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")


if __name__ == "__main__":
    main()
