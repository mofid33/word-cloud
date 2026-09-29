# Phase 11 — Topic & Trend

Status: IMPLEMENTED_AWAITING_LOCAL_VERIFICATION
Date: 2026-09-29

## Baseline

Phase 11 starts from main commit `3d5626e458286830e842c885ccfb28416bb945e5`.
Phase 10 remains `IMPLEMENTATION_AND_ENGINEERING_VERIFIED_HUMAN_GOLD_PENDING`.
No Phase 10 Human Gold data or acceptance state is changed by Phase 11.

## Implemented scope

- Typed Topic result/provider contracts.
- Real semantic agglomerative clustering backed by the existing EmbeddingProvider.
- Singleton/load-once lifecycle through DI discovery; no per-request model construction.
- Topic representation, prevalence, coverage and representative keyphrases.
- COURSE topic timeline based on actual request ordering and section/chunk metadata.
- SOLDIER_CONCERN semantic topic clustering while preserving independent-document semantics.
- SOLDIER topic document association persists only SHA-256 document identifiers.
- MEDIA published_content and audience_feedback topic analysis remain separate.
- MEDIA trend uses optional timezone-aware `metadata.published_at`; no synthetic timestamps.
- Deterministic previous/current trend windows and emerging/stable/declining classification.
- Topic-based Content–Audience Gap baseline.
- Atomic AnalysisTopic / AnalysisTopicKeyword persistence through AnalysisProcessorService -> repository.
- Existing Phase 4 schema is reused; no migration is required for Phase 11.
- Fail-fast config validation rejects bool-as-number, NaN, Inf and invalid ranges.
- NOT_PRODUCTION_GOLD topic regression evaluation fixture.
- Algorithm performance baseline and an opt-in real configured embedding benchmark.

## Configuration baselines

These values are engineering/evaluation baselines and are not production-final quality claims:

- `topic_model.similarity_threshold = 0.58`
- `topic_model.maximum_topics = 12`
- `topic_analysis.representative_keyphrases = 5`
- `topic_analysis.media_gap_similarity_threshold = 0.30`
- `trend_analysis.window_days = 7`
- `trend_analysis.minimum_documents_per_window = 2`
- `trend_analysis.growth_threshold = 0.10`
- `trend_analysis.minimum_prevalence = 0.05`

Human Gold evaluation is still required to calibrate/finalize these thresholds and to make production accuracy claims.

## Persistence / migration

The existing tables `analysis_topic` and `analysis_topic_keyword` already contain the required stable columns.
Provider/config/version, document associations and profile-specific Topic metadata are persisted in `analysis_topic.metadata`.
Therefore no Alembic schema change is required for this phase.

## Verification commands

```powershell
git pull origin main
python -m compileall -q src tests
python -m unittest discover -s tests/unit/core/services/topic -p "test_*.py" -v
python -m unittest tests.unit.core.services.profiles.test_analysis_profiles -v
python -m unittest tests.unit.core.services.analysis.test_analysis_processor_service -v
python -m unittest tests.integration.di.test_phase11_topic_discovery -v
python -m unittest tests.evaluation.test_phase11_topic_evaluation -v
python -m unittest tests.evaluation.test_phase11_topic_performance -v
python -m unittest discover -s tests -p "test_*.py" -v
```

PostgreSQL integration:

```powershell
$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/word_cloud_test"
python -m unittest tests.integration.persistence.test_phase11_topic_persistence -v
python -m unittest discover -s tests/integration/persistence -p "test_*.py" -v
```

Real configured model performance:

```powershell
$env:RUN_PHASE11_REAL_MODEL_BENCHMARK = "1"
python -m unittest tests.evaluation.test_phase11_topic_performance.Phase11TopicPerformanceTests.test_real_embedding_topic_performance_baseline -v
```

## Closure gate

Do not change this status to CLOSED until compile, runtime smoke, focused Phase 11 tests, PostgreSQL integration, evaluation/performance evidence and full regression have been executed successfully in an environment with the project dependencies/model cache/database.

The synthetic evaluation fixture is explicitly `NOT_PRODUCTION_GOLD`.
Human Gold remains a production validation dependency.
