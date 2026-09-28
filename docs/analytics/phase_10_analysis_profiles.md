# Phase 10 — Analysis Profiles

Status: IMPLEMENTED_AWAITING_LOCAL_VERIFICATION

## Scope

Phase 10 implements the runtime analysis-profile workflows defined by the frozen project architecture:

- `CourseAnalysisService`
- `SoldierConcernAnalysisService`
- `MediaAnalysisService`
- `AnalysisProcessorService` profile dispatch
- structured profile results and profile-specific scoring configuration

Shared Phase 6–9 engines are reused. Phase 11 topic/trend features, Phase 12 queue/worker runtime, and Phase 13 visualization are not implemented here.

## Phase 9 dependency evidence

Phase 10 is based on the closed Phase 9 baseline on `main`:

- marker: `PHASE_9_COMPLETE_READY_FOR_PHASE_10`
- Hybrid Ranking unit verification: 22/22 PASS
- Phase 9 evaluation verification: 4/4 PASS
- Phase 6→7→8→9 integration: PASS
- full regression at Phase 9 closure: 250/250 PASS
- scoring version: `hybrid-ranking-v2`
- min-max normalization
- exact/canonical/lexical/semantic deduplication
- MMR diversity

The Phase 9 evaluation fixture is regression evidence and is not a Production Gold Dataset.

## COURSE

Workflow:

`documents → PersianTextProcessor → CandidateExtractionService → StatisticalAnalysisService → SemanticAnalysisService → HybridRankingService → StructuredProfileResult`

Behavior:

- document boundaries remain independent;
- caller-provided `section_id` and `chunk_id` metadata are preserved;
- section/chunk metadata must be consistently present when used;
- complete section/chunk boundary universes are passed to Phase 7 statistical coverage;
- no Phase 10 chunker or section parser is invented;
- preprocessing/candidate/statistical/semantic/hybrid work is performed once per required corpus path;
- Course profile statistical scoring uses frequency, optional chunk coverage, optional section coverage, and phrase quality;
- semantic relevance is fused through the existing Hybrid Ranking service;
- deduplication/MMR remain owned by `HybridRankingService`.

Deferred to Phase 11:

- topic clustering/representation;
- Topic Coherence/Diversity;
- topic timeline.

## SOLDIER_CONCERN

Each concern remains an independent document throughout candidate/statistical analysis.

Signals:

- normalized document frequency;
- document coverage;
- semantic relevance;
- Phase-10 concern prevalence represented by document coverage, without pretending Topic Model prevalence exists.

Privacy:

- profile results do not retain the original raw document payload as a raw-text field;
- extracted keyphrases may legitimately contain text fragments from the source document because they are analytical output;
- persistence remains `persist_raw_text=False`;
- repository strips Soldier reference/options/metadata/role;
- persisted Soldier document IDs are hashed;
- repository rejects explicit raw-text persistence;
- Processor failure messages are sanitized;
- request data cannot disable the privacy invariant.

Deferred to Phase 11:

- semantic clustering;
- Topic Extraction;
- Topic Model prevalence;
- representative topic keyphrases;
- Topic-level WordCloud.

## MEDIA

`published_content` and `audience_feedback` are analyzed as separate corpora before any combined top-level result is formed.

Implemented Phase 10 signals:

- mention share;
- semantic relevance;
- document coverage.

Not invented because no frozen metadata contract exists:

- normalized engagement;
- recency.

Deferred to Phase 11:

- topic clustering/representation;
- trend growth/time-series;
- emerging/stable/declining;
- topic-based Content–Audience Gap;
- Topic Coherence/Diversity.

## Scoring configuration

Development and Production contain matching baseline profile configs.

These weights are explicitly evaluation baselines and are **not production-final weights**.

### COURSE

- semantic relevance: 0.35
- frequency: 0.20
- chunk coverage: 0.15
- section coverage: 0.15
- phrase quality: 0.15

### SOLDIER_CONCERN

- document frequency: 0.30
- document coverage: 0.25
- semantic relevance: 0.35
- concern prevalence: 0.10

### MEDIA

- mention share: 0.35
- semantic relevance: 0.40
- coverage: 0.25

Configuration validation rejects booleans, NaN/Inf, out-of-range weights, invalid sums, and missing required values.

## Reproducibility metadata

Structured profile results expose:

- profile;
- ranked keyphrases;
- final/statistical/semantic scores;
- profile component signals;
- frequency/coverage information;
- rank;
- deduplication records;
- MMR score;
- profile scoring version;
- Hybrid Ranking scoring version;
- normalization strategy;
- lexical/semantic dedup thresholds;
- MMR/diversity configuration;
- model identifiers/revisions.

Topics are persisted as an empty collection in Phase 10 rather than faked.

## Processor integration

For resolved `sync` execution:

`AnalysisService → AnalysisProcessorService → Profile Service → Repository`

For `async`, the lifecycle resource remains pending until Phase 12 provides the real queue/worker runtime. Phase 10 does not create a fake queue or worker.

The Processor contains dispatch/lifecycle/persistence orchestration only; profile business logic remains in the three Profile Services.

## Persistence

No database schema change is required. The existing Phase 4 schema already stores:

- ranked keyword persistence fields;
- metrics JSON;
- profile_result JSON;
- model/scoring versions;
- empty topics until Phase 11.

Therefore Phase 10 intentionally has no Alembic migration.

## Tests added

Unit:

- profile workflow/scoring/determinism;
- Course section/chunk boundaries;
- Soldier document frequency/coverage;
- Media role separation;
- input/config validation;
- Processor dispatch/error sanitization;
- Soldier privacy.

Integration:

- DI/discovery resolution for all Phase 10 services;
- environment-gated real Phase 6→7→8→9→10 model paths;
- existing repository/database privacy and atomic persistence tests remain active.

Evaluation:

- independent COURSE/SOLDIER_CONCERN/MEDIA synthetic regression cases;
- Precision@5;
- Precision@10;
- Recall@10;
- NDCG@10;
- deterministic rerun/order regression.

Performance:

- Course orchestration baseline;
- Soldier multi-document baseline;
- Media two-role baseline;
- P50/P95/throughput/Python peak-memory measurement.

## Gold Dataset status

Repository Phase 10 does not contain a verified Production Gold Dataset with human relevance judgments for all three profiles.

The new fixture is explicitly marked:

`PHASE_10_SYNTHETIC_REGRESSION_FIXTURE_NOT_PRODUCTION_GOLD`

It must not be represented as Production Gold evidence, and the baseline profile weights must not be called production-final.

This is the remaining external acceptance dependency for final Phase 10 closure after runtime/local verification.

## Local verification required before closure

Run compile, focused unit/integration/privacy/evaluation/performance tests, real-model integration where configured, DB integration, and full regression.

Only after successful local evidence may this document be changed to CLOSED and the marker changed to:

`PHASE_10_COMPLETE_READY_FOR_PHASE_11`

Current marker:

`PHASE_10_IMPLEMENTED_AWAITING_LOCAL_VERIFICATION`
