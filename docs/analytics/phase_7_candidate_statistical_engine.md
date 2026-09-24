# Phase 7 — Candidate & Statistical Engine

Status: CORRECTION_IMPLEMENTED_AWAITING_LOCAL_VERIFICATION

## مرحله

Phase 7 — Candidate & Statistical Engine

## هدف

پیاده‌سازی واقعی و deterministic استخراج candidateهای 1 تا 3-gram از Candidate Representation فاز 6 و محاسبه signalهای آماری عمومی بدون ورود به Semantic Engine، Hybrid Ranking یا Profile-specific scoring.

## ورودی

- `PersianTextProcessingResult.candidate_tokens` از `PersianTextProcessor`;
- document identity;
- optional section/chunk identity when the caller already has those boundaries;
- Phase 7 configuration from `ConfigReader`.

## خروجی

- immutable `CandidateOccurrence` records;
- immutable `StatisticalCandidateResult` records;
- raw frequency/document-frequency/coverage components;
- bounded statistical score in `[0, 1]` for Phase 7 only.

## Files Created / Modified

### Created

- `src/core/services/candidate/candidate_extraction_service.py`
- `src/core/services/statistical/statistical_analysis_service.py`
- `tests/unit/core/services/candidate/test_candidate_extraction_service.py`
- `tests/unit/core/services/statistical/test_statistical_analysis_service.py`
- `tests/unit/core/services/candidate/__init__.py`
- `tests/unit/core/services/statistical/__init__.py`
- `tests/integration/foundation/test_candidate_statistical_pipeline.py`
- `tests/evaluation/fixtures/candidate_statistical_cases.json`
- `tests/evaluation/test_candidate_statistical_evaluation.py`
- `tests/evaluation/test_candidate_statistical_performance.py`
- `tests/evaluation/test_candidate_statistical_profile_regression.py`

### Modified

- `src/host/res/appsettings.development.yaml`
- `src/host/res/appsettings.yaml`
- `docs/architecture/architecture_contract.json`

No SQLAlchemy model, repository, DTO, controller, API route or Alembic migration is added in Phase 7.

## Candidate extraction behavior

- exact n-gram range is enforced as `1..3`; configuration outside this range fails fast;
- candidates are built only from Phase 6 `candidate_tokens`;
- candidate generation never re-normalizes or re-tokenizes raw text;
- punctuation boundaries are respected through Phase 6 `segment_index`;
- each `CandidateDocument` is extracted independently, so n-grams never cross document/section/chunk processing boundaries;
- protected spans bypass stopword/POS/numeric filtering;
- pure stopword unigrams are rejected by the safe default, with an explicit configurable switch;
- edge-stopword phrase filtering is configurable;
- internal stopwords may remain inside an otherwise valid phrase;
- known function POS values are used conservatively for unigram filtering only;
- `POS=X` is never treated as invalid;
- technical compounds such as `GPT-4`, `BERT-base`, `v1.2`, and `2026/09` remain single tokens because Phase 7 consumes Phase 6 tokens directly;
- pure numeric noise is configurable, while four-digit years and structured numeric compounds may be preserved;
- output ordering is explicit and deterministic.

The current Phase 6 POS processor intentionally returns `X` when lexical POS is not reliable. Therefore Phase 7 does not invent a noun-phrase tagger or aggressively discard `X` candidates. This keeps noun/phrase filtering conservative until reliable POS information exists.

## Internal candidate contract

`CandidateOccurrence` carries:

- document id;
- text;
- canonical text;
- n-gram size;
- segment index;
- token start/end;
- optional section/chunk id;
- protected status;
- stopword metadata;
- POS metadata.

It is a Core dataclass, not a DTO or SQLAlchemy model.

## Statistical analysis behavior

For each canonical candidate:

- `frequency`: total occurrence count;
- `document_frequency`: count of distinct documents containing the candidate;
- `document_coverage`: `document_frequency / total_documents`;
- `relative_frequency`: candidate frequency divided by all candidate occurrences;
- `normalized_frequency`: candidate frequency divided by maximum candidate frequency in the analyzed corpus;
- `section_coverage` and `chunk_coverage`: generic primitives computed against an explicit full corpus boundary universe, including sections/chunks that produce zero surviving candidates;
- `phrase_quality`: bounded statistical length signal based on 1/2/3-gram size;
- source occurrences are retained without raw-text logging.

Repeated occurrences in one document contribute multiple times to `frequency` but only once to `document_frequency`.

## Statistical score

The Phase 7 score is intentionally not a final ranking score.

It is a configurable weighted aggregation of:

- normalized frequency;
- document coverage;
- phrase quality.

The configured baseline uses neutral equal weighting and must not be interpreted as Production profile weighting. Profile-specific scoring remains owned by later phases and final weights remain subject to evaluation/Gold Dataset tuning.

The score is bounded to `[0, 1]`, while all raw components remain available to later phases.

## Configuration

Development and production config now include:

- `candidate_extraction.minimum_ngram = 1`
- `candidate_extraction.maximum_ngram = 3`
- maximum phrase characters;
- pure numeric filtering;
- four-digit year preservation;
- stopword unigram filtering;
- edge stopword filtering;
- conservative function-POS unigram filtering;
- Phase 7 statistical component weights.

Configuration validation is fail-fast.

## Tests Added

### Unit

Candidate extraction coverage includes:

- unigram/bigram/trigram;
- no 4-gram;
- punctuation boundary;
- document boundary;
- Persian/Latin/mixed text;
- technical compound tokens;
- numeric noise vs meaningful numeric forms;
- protected unigram/multi-token phrase;
- stopword unigram;
- edge/internal stopword behavior;
- `POS=X`;
- configurable filtering;
- deterministic ordering;
- empty/single/noisy inputs;
- invalid config.

Statistical coverage includes:

- frequency;
- document frequency;
- document coverage;
- repeated occurrence in one document;
- cross-document occurrence;
- relative/normalized frequency;
- bounded statistical score;
- section/chunk generic coverage;
- explicit corpus boundary validation;
- filtered-empty section/chunk denominator correctness;
- inconsistent scope metadata rejection;
- source occurrence tracking;
- deterministic ranking;
- empty input;
- invalid document ids;
- invalid weight configuration.

### Integration

`PersianTextProcessor -> CandidateExtractionService -> StatisticalAnalysisService` is exercised through the real DI discovery/bootstrap path.

### Evaluation

A small Persian multi-document fixture checks expected educational phrases, protected phrases, mixed technical terms and known noise exclusions. Additional profile-aware corpus regressions cover COURSE, SOLDIER_CONCERN and MEDIA while keeping profile workflow/scoring out of Phase 7.

### Performance baseline

A controlled 100-document corpus verifies bounded candidate growth (`<= 3 * token_count`), measures runtime, and supports an optional environment-specific time gate through `PHASE7_PERF_MAX_SECONDS`.

## Local verification correction pass

The first local verification run showed two Candidate unit failures while the statistical, DI integration, evaluation and performance suites passed.

Root causes and corrections:

- configurability test: stopword-unigram rejection was unconditional even though the test exercised fully configurable filtering. The safe default remains enabled, but `candidate_extraction.filter_stopword_unigrams` now controls that rule explicitly;
- mixed Persian/Latin test: the test expected raw `NLP` after Phase 6, but Phase 6 canonicalizes `NLP` to `پردازش زبان طبیعی`. The test now asserts the real Phase 6 representation instead of bypassing or undoing preprocessing;
- global discovery: `python -m unittest discover -s tests` reported 158 passing tests but omitted the new candidate/statistical unit directories because they lacked package markers. Test-only `__init__.py` files were added so the global regression gate includes all Phase 7 unit tests.

## Final verification evidence

Verified locally on 2026-09-24 on Windows / Python 3.12:

- `python -m compileall -q src tests`: PASS;
- Candidate extraction unit suite: 18 tests, PASS;
- Statistical analysis unit suite: 11 tests, PASS;
- Phase 6 → Phase 7 DI integration: 1 test, PASS;
- Persian candidate/statistical evaluation: 1 test, PASS;
- controlled performance baseline: 1 test, PASS;
- full project regression: 187 tests, PASS;
- failures: 0;
- errors: 0.

The full regression now includes the Phase 7 Candidate and Statistical unit packages, confirming that the earlier unittest discovery gap is fixed.

The Windows asyncio `Executing <Task ... took ...>` / `Executing <Handle ... took ...>` lines observed during PostgreSQL integration tests are diagnostic slow-callback messages; they did not fail the suite.

That verification is retained as the pre-audit baseline. The coverage/profile/performance corrections require a new local compile, focused test run and full regression before Phase 7 can be re-closed.

## Coverage correctness correction

A post-closure audit identified that section/chunk coverage denominators were previously derived from surviving candidate occurrences. That could overestimate coverage when a real section or chunk produced no candidates after filtering.

The correction changes the statistical contract so that callers provide the complete generic corpus boundary universe through:

- `document_ids`;
- optional `section_keys = ((document_id, section_id), ...)`;
- optional `chunk_keys = ((document_id, chunk_id), ...)`.

Rules are fail-fast and deterministic:

- if occurrences carry `section_id`, `section_keys` are required;
- if occurrences carry `chunk_id`, `chunk_keys` are required;
- every boundary key must reference a known document;
- every scoped occurrence must belong to the supplied universe;
- when a section/chunk universe is supplied, occurrences must carry the corresponding scope metadata;
- sections/chunks with zero surviving candidates remain in the denominator.

This remains a generic Phase 7 statistical primitive and does not introduce COURSE/SOLDIER/MEDIA workflow logic.

## Profile-aware regression correction

The Phase 7 test suite now includes representative corpus regressions for all three product profiles without implementing Phase 10 profile services:

- COURSE: verifies that a filtered-empty section/chunk still contributes to the coverage denominator;
- SOLDIER_CONCERN: verifies that repeated occurrences inside one concern increase frequency but contribute only once to document frequency, while cross-document repetition increases document coverage;
- MEDIA: verifies that published-content and audience-feedback corpora can be analyzed independently without cross-role candidate mixing.

## Performance baseline correction

The controlled corpus still measures runtime and enforces bounded candidate growth. The previous unconditional 15-second assertion was hardware-dependent and was removed.

Runtime is printed as baseline evidence. A time gate is optional through `PHASE7_PERF_MAX_SECONDS`; when supplied by CI or a known environment it must be positive and the measured runtime must remain below it. This avoids inventing a universal production latency SLO before that SLO is frozen.

## Privacy

Phase 7 adds no logging of raw text or candidate text, no persistence, no metrics labels, no trace attributes and no durable queue payload.

The implementation does not weaken the `SOLDIER_CONCERN` privacy contract.

## Complexity

For `N` Phase 6 candidate tokens, extraction considers at most three spans per token. Candidate generation is therefore bounded by `O(N)` for fixed maximum n-gram size 3, excluding deterministic result sorting.

Document frequency uses sets/maps and does not count repeated occurrences in one document more than once.

## Scope exclusions preserved

Phase 7 does not implement:

- embeddings;
- bi-encoder/cross-encoder;
- reranker;
- semantic benchmark;
- hybrid fusion;
- MMR/diversity;
- semantic deduplication;
- profile workflows/final scoring;
- topic/trend;
- queue/worker;
- visualization.

## Commands to Run

```powershell
python -m compileall -q src tests

python -m unittest discover -s tests/unit/core/services/candidate -p "test_*.py" -v
python -m unittest discover -s tests/unit/core/services/statistical -p "test_*.py" -v

python -m unittest tests.integration.foundation.test_candidate_statistical_pipeline -v

python -m unittest tests.evaluation.test_candidate_statistical_evaluation -v
python -m unittest tests.evaluation.test_candidate_statistical_profile_regression -v
python -m unittest tests.evaluation.test_candidate_statistical_performance -v

python -m unittest discover -s tests -p "test_*.py" -v
```

## Expected Result

- compile succeeds;
- all Phase 7 unit tests pass;
- DI integration resolves `PersianTextProcessor`, `CandidateExtractionService`, and `StatisticalAnalysisService`;
- evaluation fixture passes;
- controlled performance baseline passes;
- all pre-existing regression tests remain green.

## Acceptance Checklist

- [x] Phase 6 readiness marker verified before implementation.
- [x] 1–3 gram candidate extraction implemented from Phase 6 representation.
- [x] punctuation/document boundaries preserved.
- [x] protected terms and phrase-aware stopword rules implemented.
- [x] technical/mixed tokens preserved without re-tokenization.
- [x] conservative POS behavior implemented; `X` is not rejected.
- [x] frequency/DF/document coverage implemented.
- [x] generic section/chunk coverage primitives implemented when metadata is supplied.
- [x] immutable Core candidate/statistical contracts implemented.
- [x] bounded configurable Phase 7 statistical aggregation implemented.
- [x] deterministic tie-breaking implemented.
- [x] fail-fast config validation implemented.
- [x] Unit tests added.
- [x] Integration/DI test added.
- [x] Persian evaluation fixture/test added.
- [x] Performance baseline added.
- [x] No Phase 8+ implementation introduced.
- [x] No new persistence schema or migration introduced.
- [x] No raw-text operational logging introduced.
- [x] Original local compile/test/regression evidence captured (187 tests).
- [x] Coverage denominator correctness fix implemented.
- [x] COURSE/SOLDIER_CONCERN/MEDIA profile-aware regression tests added.
- [x] Hardware-dependent fixed performance threshold removed.
- [ ] Post-correction local compile/test/regression evidence captured.

Current readiness marker:

`PHASE_7_CORRECTION_AWAITING_LOCAL_VERIFICATION`
