# Phase 9 — Hybrid Ranking

Status: IMPLEMENTED_AWAITING_LOCAL_VERIFICATION

## مرحله

Phase 9 — Hybrid Ranking

## هدف

پیاده‌سازی Hybrid Ranking عمومی و reusable روی خروجی واقعی Phase 7 و Phase 8، شامل:

- deterministic score normalization;
- configurable statistical/semantic fusion;
- exact/canonical/lexical deduplication;
- embedding-based MMR diversity;
- reproducibility metadata;
- bounded diversity pool;
- fail-fast configuration and identity validation.

Phase 9 وارد Profile workflowهای Phase 10 نمی‌شود.

## ورودی

- `tuple[StatisticalCandidateResult, ...]` از `StatisticalAnalysisService`;
- `SemanticAnalysisResult` از `SemanticAnalysisService`;
- Phase 9 configuration from `ConfigReader`;
- existing `EmbeddingProvider` for bounded MMR similarity.

Candidate join identity is `canonical_text`. Statistical and semantic candidate sets must match exactly. Missing, empty or duplicate identities fail fast. Raw source text is not used as a ranking identifier.

## خروجی

`HybridRankingResult` شامل:

- raw statistical score;
- raw semantic score;
- normalized statistical score;
- normalized semantic score;
- fused score;
- MMR score;
- statistical/semantic/final ranks;
- deduplication records;
- scoring version;
- normalization strategy;
- configured/overridden fusion weights;
- lexical dedup threshold;
- MMR configuration;
- embedding provider metadata inherited from Phase 8;
- deterministic tie-breaking metadata.

Current scoring version:

`hybrid-ranking-v1`

## Files Created / Modified

### Created

- `src/core/services/ranking/hybrid_ranking_service.py`
- `tests/unit/core/services/ranking/__init__.py`
- `tests/unit/core/services/ranking/test_hybrid_ranking_service.py`
- `tests/integration/foundation/test_hybrid_ranking_pipeline.py`
- `tests/evaluation/fixtures/hybrid_ranking_cases.json`
- `tests/evaluation/test_hybrid_ranking_evaluation.py`
- `tests/evaluation/test_hybrid_ranking_performance.py`
- `docs/analytics/phase_9_hybrid_ranking.md`

### Modified

- `src/host/res/appsettings.yaml`
- `src/host/res/appsettings.development.yaml`
- `docs/architecture/architecture_contract.json`

No Controller, DTO, SQLAlchemy model, Repository, migration, Queue/Worker, Topic/Trend or Visualization implementation is added.

## Normalization

Safe baseline strategy:

`min_max`

Rules:

- deterministic;
- finite input required;
- NaN/Inf rejected;
- empty input supported;
- constant/single-value input maps to `1.0` for every item;
- output bounded to `[0, 1]`.

The method is configurable by named strategy, but only the implemented `min_max` strategy is currently accepted; unsupported names fail fast rather than silently changing production behavior.

## Fusion

Baseline configuration:

- statistical weight: `0.5`;
- semantic weight: `0.5`.

These are Phase 9 benchmark defaults only and are not production-final profile weights.

`rank_async(..., weights=FusionWeights(...))` allows Phase 10 to supply profile-specific evaluated weights without duplicating ranking logic.

Weights:

- must be numeric, finite and within `[0,1]`;
- booleans are rejected;
- must sum to `1.0`.

Raw signal scores remain in the ranked result.

## Deduplication

Implemented deterministic stages:

1. exact representative text;
2. canonical identity after NFKC/casefold/whitespace normalization;
3. lexical near-duplicate comparison using deterministic sequence ratio.

Protected terms bypass lexical near-duplicate removal so technically important/protected phrases are not deleted by a generic fuzzy threshold.

The baseline lexical threshold is configurable:

`0.92`

### Semantic deduplication decision

The architecture contract explicitly keeps the exact semantic deduplication threshold deferred. Phase 9 therefore does **not** invent a production-final semantic removal threshold.

Semantic similarity is used for real MMR diversity. A future semantic-dedup threshold can only be frozen when stronger Gold Dataset/evaluation evidence justifies it.

This is intentional scope control, not a placeholder implementation.

## Diversity / MMR

MMR is implemented with the existing Phase 8 `EmbeddingProvider`.

No second model, provider lifecycle or parallel embedding pipeline is introduced.

Because Phase 8 does not expose candidate vectors in `SemanticAnalysisResult`, Phase 9 batch-embeds only the bounded diversity candidate pool. The existing provider is singleton and reuses its loaded model.

Baseline configuration:

- `mmr_lambda = 0.7`;
- `diversity_candidate_pool_size = 50`;
- `maximum_ranked_results = 25`.

The exact production MMR lambda remains deferred pending Gold Dataset evidence.

Pairwise similarity uses normalized cosine similarity. The bounded pool prevents MMR pairwise work from growing with the full candidate corpus after preselection.

## Determinism

Deterministic behavior is enforced through:

- canonical identity validation;
- order-independent joins;
- explicit finite normalization;
- explicit fused-score tie-breaking;
- canonical lexical final tie-breaking;
- deterministic dedup traversal over fused order;
- deterministic MMR selection;
- immutable result dataclasses.

Unit coverage includes repeated execution, reversed input ordering and concurrent execution.

## Configuration

Development and production config both include:

```yaml
hybrid_ranking:
  normalization_strategy: "min_max"
  baseline_weights:
    statistical: 0.5
    semantic: 0.5
  lexical_deduplication_threshold: 0.92
  mmr_lambda: 0.7
  diversity_candidate_pool_size: 50
  maximum_ranked_results: 25
```

Validation is fail-fast for:

- unsupported normalization strategy;
- boolean/non-numeric weights;
- NaN/Inf;
- out-of-range weights;
- weight sums not equal to 1;
- invalid lexical threshold;
- invalid MMR lambda;
- non-positive pool/result sizes;
- diversity pool smaller than configured maximum results.

## Tests Added

### Unit

Coverage includes:

- empty candidates;
- one candidate;
- min-max normalization;
- all-equal scores;
- fusion;
- candidate identity mismatch;
- duplicate identity;
- NaN/Inf rejection;
- exact text dedup;
- canonical dedup;
- lexical near-duplicate dedup;
- protected-term preservation;
- MMR diversity;
- Phase 10 weight override;
- repeated execution;
- different input ordering;
- concurrent execution;
- invalid config;
- invalid runtime weights;
- invalid Top-N.

Persian, Latin and technical terms such as `GPT-4` and `BERT-base` are represented in tests/evaluation.

### Integration

`tests/integration/foundation/test_hybrid_ranking_pipeline.py` provides:

- non-model-gated DI/discovery verification for `HybridRankingService` and the real discovered `EmbeddingProvider`;
- environment-gated real-model pipeline:

`Phase 6 -> Phase 7 -> Phase 8 -> Phase 9`

using the concrete Phase 8 providers discovered by the runtime container.

The heavy-model test uses the existing `RUN_PHASE8_MODEL_INTEGRATION=1` gate because Phase 9 intentionally reuses the same model artifacts/lifecycle.

### Evaluation / Regression

The Phase 9 fixture is explicitly marked:

`PHASE_9_REGRESSION_FIXTURE_NOT_PRODUCTION_GOLD`

It contains COURSE, SOLDIER_CONCERN and MEDIA cases, Persian, Latin/technical terms, duplicates/near-duplicates and semantically similar vectors.

The evaluation compares:

- statistical-only;
- semantic-only;
- hybrid;
- hybrid + dedup;
- hybrid + dedup + MMR.

It computes real:

- Precision@5;
- Precision@10;
- Recall@10;
- NDCG@10.

These metrics are regression evidence for the public-safe fixture only and must not be represented as production Gold Dataset quality.

Final profile weights, semantic dedup threshold and exact production MMR lambda remain deferred.

### Performance

The performance baseline exercises candidate counts:

- 100;
- 500;
- 1000.

It records:

- elapsed ranking time;
- Python peak tracked memory;
- fixed ranked result count;
- bounded MMR pool size.

No universal production latency SLO is invented.

An optional environment gate is available:

`PHASE9_PERF_MAX_SECONDS_1000`

Phase 8 already owns heavy-model latency/RAM/VRAM evidence; Phase 9 performance isolates ranking/MMR overhead so model inference cost is not misattributed to ranking logic.

## Privacy

Phase 9 adds no:

- raw text logging;
- raw text trace attributes;
- raw text metrics labels;
- raw text persistence;
- durable queue payload.

Error messages report structural counts/field names, not user content.

The SOLDIER_CONCERN privacy boundary remains unchanged.

## Reproducibility

Result metadata exposes:

- scoring version;
- normalization strategy;
- weights;
- dedup strategy;
- lexical threshold;
- diversity strategy;
- MMR lambda;
- pool size;
- maximum results;
- Phase 8 embedding metadata;
- Phase 8 semantic score strategy;
- deterministic tie-breaking description.

Persistence of this metadata remains owned by later profile/persistence orchestration and is not prematurely added to the DB schema in Phase 9.

## Evaluation / Benchmark Results

Repository implementation and test artifacts are committed.

Final execution evidence is intentionally pending the required local verification step. No unexecuted test is reported as PASS.

The previous verified baseline entering Phase 9 was Phase 8 full regression: 221/221 tests PASS.

## Commands to Run

```powershell
python -m compileall -q src tests

python -m unittest discover -s tests/unit/core/services/ranking -p "test_*.py" -v

python -m unittest tests.integration.foundation.test_hybrid_ranking_pipeline.HybridRankingDiscoveryIntegrationTests -v

$env:RUN_PHASE8_MODEL_INTEGRATION="1"
python -m unittest tests.integration.foundation.test_hybrid_ranking_pipeline.HybridRankingPipelineIntegrationTests -v

python -m unittest tests.evaluation.test_hybrid_ranking_evaluation -v
python -m unittest tests.evaluation.test_hybrid_ranking_performance -v

python -m unittest discover -s tests -p "test_*.py" -v
```

If production config is being verified offline, pre-populate the configured model cache as required by Phase 8 before running the real-model integration.

## Expected Result

- compile succeeds;
- all Phase 9 unit tests pass;
- DI resolves `HybridRankingService` automatically;
- discovered `EmbeddingProvider` instance is reused;
- Phase 6→7→8→9 integration passes with configured real models;
- evaluation prints baseline metric evidence for all three fixture profiles;
- performance prints scaling/memory evidence;
- all Phase 1–8 regression tests remain green;
- no Phase 10 implementation is introduced.

## Acceptance Checklist

- [x] Phase 8 marker `PHASE_8_COMPLETE_READY_FOR_PHASE_9` verified on main before implementation.
- [x] HybridRankingService implemented in Core.
- [x] Constructor DI and `@inject` used.
- [x] Existing EmbeddingProvider reused for MMR.
- [x] No manual provider registration added.
- [x] Real Phase 7 StatisticalCandidateResult consumed.
- [x] Real Phase 8 SemanticAnalysisResult consumed.
- [x] canonical_text identity join implemented.
- [x] mismatch/duplicate identity fail-fast behavior implemented.
- [x] deterministic bounded normalization implemented.
- [x] configurable fusion implemented.
- [x] raw and normalized signals retained.
- [x] exact/canonical/lexical dedup implemented.
- [x] protected terms guarded from fuzzy lexical deletion.
- [x] real MMR implemented.
- [x] diversity pool bounded/configurable.
- [x] heavy model lifecycle is reused rather than duplicated.
- [x] configuration validation implemented.
- [x] reproducibility metadata implemented.
- [x] Unit tests added.
- [x] real-DI non-model integration added.
- [x] environment-gated Phase 6→7→8→9 real-model integration added.
- [x] evaluation fixture/baselines/metrics added.
- [x] performance baseline added.
- [x] architecture contract aligned with runtime dependencies.
- [x] no Phase 10 profile service implemented.
- [x] no DB/API/Queue/Topic/Trend/Visualization scope pulled forward.
- [x] final profile weights remain deferred.
- [x] semantic dedup production threshold remains deferred.
- [x] exact production MMR lambda remains deferred.
- [ ] local compile evidence received.
- [ ] local focused Phase 9 tests verified.
- [ ] local real-model Phase 6→7→8→9 integration verified.
- [ ] local evaluation evidence reviewed.
- [ ] local performance evidence reviewed.
- [ ] local full regression Phase 1–9 reviewed.

Current marker:

`PHASE_9_IMPLEMENTED_AWAITING_LOCAL_VERIFICATION`
