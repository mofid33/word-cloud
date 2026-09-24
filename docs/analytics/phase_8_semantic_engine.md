# Phase 8 — Semantic Engine

Status: PHASE_8_IMPLEMENTED_AWAITING_LOCAL_VERIFICATION

## مرحله

Phase 8 — Semantic Engine

## هدف

پیاده‌سازی واقعی مسیر:

Candidates → Bi-Encoder → Top-N → Cross-Encoder → Semantic Result

بدون ورود به Hybrid Ranking، MMR، profile-specific scoring، Topic Analysis، Queue/Worker یا Visualization.

## Files Created / Modified

### Created

- src/core/services/semantic/providers/provider_metadata.py
- src/core/services/semantic/semantic_analysis_service.py
- src/infrastructure/providers/semantic/transformers_embedding_provider.py
- src/infrastructure/providers/semantic/transformers_reranker_provider.py
- tests/unit/core/services/semantic/__init__.py
- tests/unit/core/services/semantic/test_semantic_analysis_service.py
- tests/unit/infrastructure/providers/__init__.py
- tests/unit/infrastructure/providers/test_semantic_provider_config.py
- tests/integration/foundation/test_semantic_pipeline.py
- tests/evaluation/fixtures/semantic_cases.json
- tests/evaluation/test_semantic_benchmark.py

### Modified

- src/core/services/semantic/providers/embedding_provider.py
- src/core/services/semantic/providers/reranker_provider.py
- src/host/res/appsettings.development.yaml
- src/host/res/appsettings.yaml
- requirements.txt
- docs/architecture/architecture_contract.json

No DTO, Controller, Repository, SQLAlchemy model or Alembic migration was added because Phase 8 does not require new HTTP or persistence schema.

## Semantic Result Contract

SemanticAnalysisResult and SemanticCandidateResult are immutable Core dataclasses.

Each candidate exposes:

- text
- canonical_text
- raw cosine bi_encoder_similarity in [-1, 1]
- normalized bi_encoder_score in [0, 1]
- reranker_score in [0, 1] when reranked, otherwise None
- semantic_score
- reranked flag
- deterministic rank

Result metadata includes:

- embedding provider/model identifier
- embedding revision
- reranker provider/model identifier
- reranker revision
- provider version
- configured device
- configuration fingerprint
- similarity metric
- score strategy
- rerank_top_n

## Score semantics

Bi-encoder similarity is cosine similarity.

bi_encoder_score = (cosine + 1) / 2

For Phase 8:

- Top-N reranked candidate: semantic_score = reranker_score
- candidate outside Top-N: semantic_score = bi_encoder_score

This intentionally avoids inventing an unbenchmarked weighted blend. Statistical + semantic fusion belongs to Phase 9.

Tie-breaking is deterministic through semantic score, then bi-encoder score, then canonical_text.

NaN, Inf, zero-norm vectors, inconsistent embedding dimensions, invalid provider output lengths and reranker scores outside [0,1] fail fast.

## Model lifecycle

Both concrete providers are Infrastructure providers with @inject and __di_singleton__ = True.

Behavior:

- lazy load once
- double-checked loading lock
- no request-specific mutable state retained
- inference lock protects shared tokenizer/model execution
- repeated calls reuse the same model instance
- raw user text is not logged
- provider errors do not echo input text

## CPU / GPU

One codebase is used for CPU and CUDA.

Configuration:

- device.type = cpu | cuda
- device.cuda_device_index
- model cache
- allow_remote_downloads
- trust_remote_code
- model identifier/revision
- embedding/reranker batch sizes
- max sequence lengths
- rerank_top_n

Silent CUDA → CPU fallback is not implemented. Configured CUDA that is unavailable fails explicitly.

Production config has models.allow_remote_downloads = false.

models.trust_remote_code = true is rejected by both semantic providers.

## Batching

Embedding and reranking split inputs by their configured batch size, preserve output ordering, and handle empty batches without loading heavy models.

Long input is handled by tokenizer truncation with configuration-driven max_length.

## Model Selection Evidence

Current configured models are benchmark candidates only:

- embedding candidate: sentence-transformers/paraphrase-multilingual-mpnet-base-v2
- reranker candidate: BAAI/bge-reranker-v2-m3

They are not declared final production models.

Final production model selection remains deferred until reproducible Persian benchmark evidence is collected on representative CPU/GPU hardware and compared with additional candidate models.

## Benchmark Results

No benchmark numbers are fabricated from the GitHub implementation environment.

The repository now contains an executable benchmark gate:

RUN_PHASE8_BENCHMARK=1

It uses public-safe synthetic fixtures for:

- COURSE
- SOLDIER_CONCERN
- MEDIA

The current fixture is an evaluation smoke dataset and is not represented as the final frozen Gold Dataset. Therefore Precision@5/10, Recall@10 and NDCG@10 are not falsely reported without sufficient annotation.

The benchmark records semantic relevance behavior, elapsed time and Python peak allocated memory. GPU memory evidence must be captured on a CUDA-capable verification machine.

## Tests Added

### Unit

- Top-N reranking
- deterministic fallback for non-reranked candidates
- empty candidates
- duplicate canonical candidates
- invalid provider output length
- NaN reranker output
- CPU metadata
- stable configuration fingerprint
- trust_remote_code rejection
- invalid device
- embedding batching and ordering
- reranker batching and ordering
- empty batch without model load

### Integration

Phase 6 → Phase 7 → Phase 8 through real DI/discovery and concrete providers.

The real-model integration test is intentionally environment-gated through RUN_PHASE8_MODEL_INTEGRATION=1 because it requires configured model artifacts and hardware/runtime dependencies.

### Evaluation / Performance

Phase 8 benchmark fixture and executable benchmark test added for COURSE, SOLDIER_CONCERN and MEDIA.

## Commands to Run

```powershell
python -m pip install -r requirements.txt
python -m compileall -q src tests

python -m unittest discover -s tests/unit/core/services/semantic -p "test_*.py" -v
python -m unittest tests.unit.infrastructure.providers.test_semantic_provider_config -v

$env:RUN_PHASE8_MODEL_INTEGRATION="1"
python -m unittest tests.integration.foundation.test_semantic_pipeline -v

$env:RUN_PHASE8_BENCHMARK="1"
python -m unittest tests.evaluation.test_semantic_benchmark -v

python -m unittest discover -s tests -p "test_*.py" -v
```

For production-like verification, pre-populate the configured model cache because appsettings.yaml disables remote model downloads.

## Expected Result

- compile passes
- semantic unit tests pass
- provider config/batching/lifecycle tests pass
- real DI resolves SemanticAnalysisService, EmbeddingProvider and RerankerProvider
- model is not loaded per request
- CPU path works
- configured invalid CUDA fails explicitly
- Phase 6 → Phase 7 → Phase 8 integration works
- benchmark emits relevance/performance evidence
- full Phase 1–7 regression remains green

## Acceptance Checklist

- [x] PHASE_7_COMPLETE_READY_FOR_PHASE_8 verified before implementation.
- [x] Existing provider contracts inspected and minimally extended.
- [x] Real EmbeddingProvider concrete implementation added.
- [x] Real RerankerProvider concrete implementation added.
- [x] Heavy providers are singleton.
- [x] Lazy load-once lifecycle implemented.
- [x] Real batching implemented.
- [x] CPU configuration implemented.
- [x] CUDA configuration implemented without silent fallback.
- [x] Production remote download policy is controlled.
- [x] trust_remote_code is not enabled.
- [x] Semantic result contract is immutable.
- [x] Reproducibility metadata is included.
- [x] Semantic score semantics are explicit.
- [x] No Hybrid Ranking/Profile/Topic/Queue/Visualization scope leaked into Phase 8.
- [x] Unit coverage added.
- [x] Real-provider DI integration test added.
- [x] Persian profile benchmark fixture/test added.
- [x] Raw text logging/persistence was not introduced.
- [ ] Local dependency install verified.
- [ ] Local compile verified.
- [ ] Real-model integration executed.
- [ ] Persian benchmark evidence captured on target hardware.
- [ ] GPU RAM/VRAM evidence captured when CUDA hardware is available.
- [ ] Full regression Phase 1–7 executed after Phase 8 dependency installation.
- [ ] Final model selection justified by benchmark, or explicitly remains deferred after benchmark comparison.

Current marker:

PHASE_8_IMPLEMENTED_AWAITING_LOCAL_VERIFICATION
