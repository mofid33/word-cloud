# Phase 10 — Analysis Profiles

Status: IMPLEMENTED_GOLD_INFRA_VERIFIED_AWAITING_HUMAN_GOLD_DATASETS

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

## Local verification evidence

Local verification was executed on Windows / Python 3.12 against the repository head after the Soldier privacy regression correction.

Verified evidence:

- `python -m compileall -q src tests`: PASS;
- PostgreSQL persistence integration: 9/9 PASS;
- lifecycle API integration: 5/5 PASS;
- Soldier privacy regression: 3/3 PASS;
- Phase 10 DI/discovery: PASS;
- Phase 6→7→8→9→10 real-model COURSE integration: PASS;
- Phase 6→7→8→9→10 real-model SOLDIER_CONCERN integration: PASS;
- Phase 6→7→8→9→10 real-model MEDIA integration: PASS;
- full regression: 277 tests executed, PASS with 1 expected skipped benchmark;
- no FAIL and no ERROR.

The skipped test is the separately gated Phase 8 semantic benchmark requiring `RUN_PHASE8_BENCHMARK=1`. It is not a Phase 10 implementation failure.

Phase 10 synthetic evaluation evidence:

- COURSE: NDCG@10 = 0.7646065393046344, Precision@5 = 0.2, Precision@10 = 0.2, Recall@10 = 0.6666666666666666;
- SOLDIER_CONCERN: NDCG@10 = 0.7309292742059024, Precision@5 = 0.4, Precision@10 = 0.2, Recall@10 = 1.0;
- MEDIA: NDCG@10 = 0.5349710957202363, Precision@5 = 0.2, Precision@10 = 0.2, Recall@10 = 0.6666666666666666.

These values are regression evidence only. They are not Production Gold quality claims.

Phase 10 orchestration performance evidence with the deterministic fixture provider:

- COURSE: P50 = 1.023873 s, P95 = 1.103443 s, throughput = 12.1063 documents/s, peak Python memory = 329660 bytes;
- SOLDIER_CONCERN: P50 = 1.011361 s, P95 = 1.011634 s, throughput = 51.2447 documents/s, peak Python memory = 530487 bytes;
- MEDIA: P50 = 0.720427 s, P95 = 0.835789 s, throughput = 52.7173 documents/s, peak Python memory = 242207 bytes.

These performance numbers measure orchestration using the deterministic fixture provider and must not be represented as production model latency.

## Gold Dataset evaluation infrastructure

The Phase 10 Gold Dataset infrastructure is implemented on `main` and awaits local verification before its evidence is added to the regression baseline.

Implemented files:

- `tests/evaluation/phase10_gold_dataset.py`: strict loader, profile-aware validation, privacy-safe Soldier path enforcement, dataset fingerprinting, and ranking metrics;
- `tests/evaluation/run_phase10_gold_evaluation.py`: real-DI evaluation runner for COURSE, SOLDIER_CONCERN, and MEDIA;
- `tests/evaluation/gold/phase10_gold_schema.json`: machine-readable `phase10-gold-v1` contract;
- `tests/evaluation/gold/README.md`: annotation, relevance grading, split discipline, privacy, and execution guidance;
- `tests/evaluation/test_phase10_gold_dataset.py`: validation, privacy, split isolation, fixed-k metric, and adjudication tests.

Gold Dataset contract decisions:

- each dataset contains both `tuning` and `holdout` cases;
- runner evaluates exactly one split per execution;
- human annotations use graded relevance `0..3` so NDCG@10 remains graded;
- Precision@5, Precision@10, and Recall@10 treat grades greater than zero as relevant;
- evaluation requires `adjudicated=true`;
- the schema records `annotator_count` but does not hard-code a minimum greater than one;
- dataset/guideline versions and a SHA-256 dataset fingerprint are included in evaluation output;
- Soldier Gold raw text must live outside the repository; the loader rejects repository-local Soldier datasets;
- Gold data is not generated from synthetic fixtures or model output.

This infrastructure does not create Production Gold labels by itself. Real human-adjudicated COURSE, SOLDIER_CONCERN, and MEDIA datasets are still required.

Gold infrastructure local verification evidence:

- `python -m unittest tests.evaluation.test_phase10_gold_dataset -v`: 9/9 PASS;
- `python -m compileall -q src tests`: PASS;
- full regression after Gold infrastructure addition: 286 tests executed, PASS with 1 expected skipped benchmark;
- no FAIL and no ERROR.

The expected skip remains the separately gated Phase 8 semantic benchmark requiring `RUN_PHASE8_BENCHMARK=1`.



## COURSE Gold source selection

The first COURSE source pool is now frozen before human annotation and scoring-weight tuning:

- source manifest: `tests/evaluation/gold/course_source_manifest_v1.json`;
- 30 revision-pinned Persian Wikibooks source units grouped into 11 COURSE cases;
- 20 tuning units in 7 case groups and 10 pre-frozen holdout units in 4 case groups;
- four domains: fluid mechanics, Python programming, mathematics/economics, and Linux CLI, represented in both splits;
- tuning and holdout are disjoint by both case group and page/revision identity to prevent source leakage;
- each unit records case group, page title, revision id, exact section title, permanent URL, attribution URL, and minimum materialized length; ambiguous repeated headings can additionally pin `section_level`;
- materializer: `tests/evaluation/materialize_course_gold_sources.py`;
- source text must be materialized outside the repository;
- section headings are provenance/selection metadata and are not automatically treated as Gold keyphrases.

The source pool is therefore reproducible, but Phase 10 is still waiting for human relevance annotations/adjudication. Source selection alone does not satisfy the Production Gold Dataset closure gate.

Local materialization evidence:

- source manifest: `course-wikibooks-fa-v1`;
- manifest version: `1.0.0`;
- materialized source units: 30/30;
- tuning units: 20;
- holdout units: 10;
- materialized file SHA-256: `ea6fc2af90570db504cce5e31f594410d4505917aa15289e699c8e59d7f98d78`;
- focused COURSE source-manifest tests: 14/14 PASS;
- `python -m compileall -q src tests`: PASS;
- no source unit was silently skipped.

The materialized corpus remains outside the repository. The fingerprint above is the reproducibility reference for the input corpus that will be used to build the human annotation package.

Human annotation package tooling local verification evidence:

- `python -m unittest tests.evaluation.test_course_gold_annotation_package -v`: 6/6 PASS;
- deterministic case ordering: PASS;
- tuning/holdout case-boundary protection: PASS;
- repository-local output rejection: PASS;
- blinded annotation package generation: PASS;
- per-document SHA-256 integrity validation: PASS;
- verified corpus SHA-256 validation: PASS;
- `python -m compileall -q src tests`: PASS.

The COURSE annotation package infrastructure is therefore verified. The remaining COURSE dependency is actual independent human annotation and adjudication; no annotation workbook is considered Gold merely because the package builder generated it.

COURSE human-annotation preparation is now implemented:

- verification metadata: `tests/evaluation/gold/course_source_materialization_v1.json`;
- package builder: `tests/evaluation/prepare_course_gold_annotation.py`;
- package-builder regression tests: `tests/evaluation/test_course_gold_annotation_package.py`;
- working annotation package keeps split mapping out of annotator-facing case rows;
- two independent working annotation files are generated;
- working files cannot claim `adjudicated=true` and are not `phase10-gold-v1`;
- builder rejects corpus fingerprint drift, per-document text-hash drift, invalid grouping, and repository-local output.

COURSE sub-status: source selection/materialization and annotation tooling are ready; human annotations and adjudication are still pending.

## COURSE AI-reviewed engineering tuning path

A separate non-Gold evaluation/tuning path is implemented to support engineering analysis of the model-simulated review without weakening the Human Gold contract.

Status marker for the external review candidate:

`MODEL_SIMULATED_HUMAN_REVIEW_NOT_ACTUAL_HUMAN_GOLD`

Implemented files:

- `tests/evaluation/gold/course_model_review_v1.json`: metadata-only fingerprint/count verification for the external review candidate;
- `tests/evaluation/course_candidate_evaluation.py`: strict external-file loader, review/source fingerprint checks, section-aware tuning preparation, Phase-10 metric reuse and deterministic weight search;
- `tests/evaluation/run_course_candidate_tuning.py`: real-DI tuning runner;
- `tests/evaluation/test_course_candidate_evaluation.py`: split-isolation, fingerprint drift, weight-simplex and baseline-parity regression tests.

Safety/evaluation boundaries:

- the existing `Phase10GoldEvaluator` still rejects non-adjudicated/non-human Gold data;
- raw COURSE materialized text and the model-review labels remain outside the repository;
- source corpus SHA-256 remains `ea6fc2af90570db504cce5e31f594410d4505917aa15289e699c8e59d7f98d78`;
- external model-review JSON SHA-256 is frozen as `9db3195b527c246c5d0c236433eb7761d0a7da218fe4732cdfe94c307c6e8e2b`;
- the candidate contains 11 cases and 117 positive relevance labels;
- the tuner prepares and ranks only the 7 tuning cases;
- the 4 holdout cases are loaded only for split-integrity/count verification and are never passed to preprocessing, semantic analysis, Hybrid Ranking or weight selection;
- `chunk_coverage` remains fixed because the selected corpus provides section boundaries but no independent chunk-boundary ground truth;
- semantic analysis is prepared once per tuning case, while candidate weight configurations reuse the prepared semantic result and execute the real Hybrid Ranking path;
- ranking metrics reuse the same `Phase10GoldEvaluator.ranking_metrics` implementation;
- candidate-label coverage is reported separately to expose keyphrases that never enter the Phase 7 candidate universe.

Search policy:

1. baseline COURSE weights;
2. deterministic pairwise transfer search with deltas 0.05 and 0.10 across semantic relevance, frequency, section coverage and phrase quality;
3. one refinement pass around the first-pass winner with delta 0.025;
4. deterministic selection priority: NDCG@10, Recall@10, Precision@5, Precision@10, minimum L1 distance from baseline, deterministic weight signature.

This path is engineering evidence only. Its selected weights must not be called production-final and it does not satisfy the Human Gold closure gate.

Local verification of this new tuning path is still required after pulling the implementation. Phase 10 status therefore remains unchanged.

## Remaining closure dependency

Runtime/local verification is complete.

The remaining Phase 10 closure dependency is a verified Production Gold Dataset and Human Evaluation for COURSE, SOLDIER_CONCERN, and MEDIA, followed by profile-weight evaluation/tuning against that data.

Until that evidence exists:

- baseline profile weights remain provisional;
- synthetic fixture metrics remain regression-only;
- Phase 10 must not be marked CLOSED;
- Phase 11 entry approval must not be issued.

After accepted Gold Dataset evaluation, this document may be changed to CLOSED and the marker changed to:

`PHASE_10_COMPLETE_READY_FOR_PHASE_11`

Current marker:

`PHASE_10_IMPLEMENTED_GOLD_INFRA_VERIFIED_AWAITING_HUMAN_GOLD_DATASETS`
