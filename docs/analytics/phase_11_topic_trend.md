# Phase 11 — Topic & Trend

Status: IMPLEMENTED_AWAITING_POST_FIX_VERIFICATION
Date: 2026-09-29

## Baseline

Phase 11 starts from main commit `3d5626e458286830e842c885ccfb28416bb945e5`.
Phase 10 remains `IMPLEMENTATION_AND_ENGINEERING_VERIFIED_HUMAN_GOLD_PENDING`.
No Phase 10 Human Gold data or acceptance state is changed by Phase 11.

## Implemented scope

- Typed Topic result/provider contracts.
- Real semantic agglomerative clustering backed by the existing `EmbeddingProvider`.
- Singleton/load-once provider lifecycle through DI discovery; no per-request model construction.
- Topic representation, prevalence, coverage and representative keyphrases.
- Topic representation enrichment reuses an existing clustering result and does not re-run embeddings.
- Representative keyphrases use token-sequence matching rather than unrestricted substring matching.
- COURSE ranking remains canonical/deterministic while Topic Timeline preserves request document sequence.
- COURSE exposes `topic_timeline_contract.ordering = request_document_sequence`.
- SOLDIER_CONCERN preserves independent-document semantics and SHA-256 document associations.
- SOLDIER ranking uses actual cluster-derived `topic_prevalence`; `concern_prevalence` remains diagnostic only.
- MEDIA `published_content` and `audience_feedback` remain separate before gap analysis.
- MEDIA trend uses optional timezone-aware `metadata.published_at`; no synthetic timestamps.
- MEDIA candidate scoring uses configured `trend_growth` and `recency` signals when timestamp evidence is available.
- `normalized_engagement` remains explicitly inactive with zero weight because no engagement metadata contract is frozen.
- Deterministic previous/current trend windows and emerging/stable/declining classification.
- Topic-based Content–Audience Gap.
- Stable logical Topic IDs survive persistence/API round trips while database UUIDs remain internal primary keys.
- MEDIA global keywords are canonical-deduplicated and Topic representatives are restricted to persistable final keywords.
- Duplicate logical Topic/Keyword identifiers are rejected transactionally by the repository.
- Atomic `AnalysisTopic` / `AnalysisTopicKeyword` persistence through `AnalysisProcessorService -> Repository`.
- Existing Phase 4 schema is reused; no migration is required because stable logical Topic IDs fit the existing Topic metadata JSON.
- Fail-fast config validation rejects bool-as-number, NaN, Inf and invalid ranges.
- NOT_PRODUCTION_GOLD topic regression fixture.
- Semantic Topic Coherence uses embedding-cluster cohesion.
- Topic Diversity uses representative-keyphrase diversity; synthetic cluster purity remains diagnostic only.
- Algorithm performance baseline and opt-in real configured embedding benchmark.
- Real-model profile integration tests now assert Phase 11 Topic/Timeline/Trend behavior, not only keyword generation.

## Configuration baselines

These are engineering/evaluation baselines and are not production-final quality claims.

Topic / Trend:

- `topic_model.similarity_threshold = 0.58`
- `topic_model.maximum_topics = 12`
- `topic_analysis.representative_keyphrases = 5`
- `topic_analysis.media_gap_similarity_threshold = 0.30`
- `topic_analysis.scoring_version = phase11-topic-baseline-v2`
- `trend_analysis.window_days = 7`
- `trend_analysis.minimum_documents_per_window = 2`
- `trend_analysis.growth_threshold = 0.10`
- `trend_analysis.minimum_prevalence = 0.05`

SOLDIER_CONCERN:

- `document_frequency = 0.30`
- `document_coverage = 0.25`
- `semantic_relevance = 0.35`
- `topic_prevalence = 0.10`
- scoring version: `phase11-soldier-topic-v1`

MEDIA:

- `mention_share = 0.30`
- `semantic_relevance = 0.35`
- `coverage = 0.20`
- `normalized_engagement = 0.00`
- `trend_growth = 0.10`
- `recency = 0.05`
- scoring version: `phase11-media-trend-v1`

Unavailable optional signals are excluded from the effective weighted score and the remaining active signals are renormalized. Human Gold evaluation is still required before production-final thresholds/weights or accuracy claims.

## Persistence / migration

The existing `analysis_topic.metadata` JSON is used for `logical_topic_id`, provider/config/version metadata and document associations. Database `analysis_topic.id` remains an internal UUID primary key.

No relational schema change is required; therefore no Phase 11 Alembic migration is added.

The API returns the stable logical Topic ID when present and falls back to the database ID only for legacy rows that predate the logical-ID metadata.

## Timeline contract

COURSE Topic Timeline represents the sequence of documents supplied in the analysis request. Ranking and clustering remain order-independent/canonical where required for reproducibility. Reversing request documents therefore must not alter ranked keywords or Topics, but it intentionally reverses the Timeline progression.

## Evaluation contract

The Phase 11 synthetic fixture is explicitly `NOT_PRODUCTION_GOLD`.

The automated Topic evaluation records:

- semantic Topic coherence: mean document-to-cluster-centroid cohesion;
- keyphrase Topic diversity: unique representative canonical keyphrases divided by all representative keyphrase slots;
- cluster purity: diagnostic only, not reported as Topic Coherence.

Human Gold/Human Evaluation remains required for production-quality validation.

## Verification commands

```powershell
git pull origin main
git rev-parse HEAD
python -m compileall -q src tests

python -m unittest discover -s tests/unit/core/services/topic -p "test_*.py" -v
python -m unittest tests.unit.core.services.profiles.test_analysis_profiles -v
python -m unittest tests.unit.configuration.test_profile_config -v
python -m unittest tests.unit.core.services.analysis.test_analysis_processor_service -v

python -m unittest tests.integration.di.test_phase11_topic_discovery -v
python -m unittest tests.evaluation.test_phase11_topic_evaluation -v
python -m unittest tests.evaluation.test_phase11_topic_performance -v
```

PostgreSQL integration:

```powershell
$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/word_cloud_test"
python -m unittest tests.integration.persistence.test_phase11_topic_persistence -v
python -m unittest tests.integration.persistence.test_analysis_repository -v
python -m unittest tests.integration.application.test_analysis_lifecycle_api -v
```

Real configured model behavior:

```powershell
$env:RUN_PHASE11_REAL_MODEL_BENCHMARK = "1"
python -m unittest tests.evaluation.test_phase11_topic_performance.Phase11TopicPerformanceTests.test_real_embedding_topic_performance_baseline -v

$env:RUN_PHASE8_MODEL_INTEGRATION = "1"
python -m unittest tests.integration.foundation.test_profile_analysis_pipeline.RealModelProfileIntegrationTests -v
```

Full regression:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

## Previous verification evidence

The pre-audit implementation at `b3b1bc6f45db8d10032445160d19bd3e689c9e8f` had:

- compile PASS;
- focused Topic/Trend tests PASS;
- PostgreSQL integration PASS;
- full regression: 331 tests PASS, 7 environment-gated skips;
- a real configured embedding benchmark PASS.

That evidence is historical and does not close the post-audit code because scoring, Timeline semantics, Topic identity persistence and evaluation behavior have changed.

## Closure gate

Do not mark Phase 11 CLOSED again until the post-audit HEAD passes:

- compile;
- focused Topic/Trend/Profile/config tests;
- PostgreSQL persistence and lifecycle API tests;
- semantic Topic evaluation;
- algorithm performance baseline;
- real configured embedding benchmark;
- real-model COURSE/SOLDIER_CONCERN/MEDIA profile integration;
- full regression with no failures/errors.

Human Gold remains a production accuracy dependency and is not replaced by the synthetic regression fixture.
