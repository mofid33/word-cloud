# Phase 6 — Persian NLP Core

Status: CORRECTION_IMPLEMENTED_AWAITING_LOCAL_VERIFICATION

## Scope implemented

- deterministic Unicode NFKC normalization;
- Arabic/Persian Yeh and Kaf normalization and Arabic-Indic digit normalization;
- Persian diacritic/tatweel removal;
- conservative ZWNJ and whitespace normalization;
- control/surrogate/symbol noise handling without raw-text logging;
- deterministic Persian/Latin/number tokenization with punctuation segment boundaries;
- configurable conservative plural lemmatization;
- configurable deterministic lexical POS processing;
- versioned general/domain stopwords, protected terms, synonyms and canonical terms;
- explicit candidate and embedding representations.

## Resource conflict precedence

1. Protected terms win over all filtering and rewriting.
2. Explicit canonical mappings are applied before synonym mappings.
3. Synonym targets that resolve to a protected term become protected.
4. General/domain stopword filtering is applied only to the embedding representation; protected spans are never removed.
5. Candidate tokens retain stopwords and segment indices so Phase 7 can perform phrase extraction without preprocessing destroying phrase boundaries.

## Lifecycle and reproducibility

PersianNlpResourceProvider is an immutable singleton Infrastructure provider discovered by the existing DI scanner. It loads the configured versioned JSON resource once. PersianTextProcessor is a normal non-singleton Core service; request processing uses immutable provider data and local variables only. Results expose resource_version for preprocessing reproducibility.

No network access, semantic model, candidate generation, statistical scoring, hybrid ranking, profile workflow, topic/trend, queue/worker or rendering implementation is introduced in this phase.

## Final verification evidence

Verified locally on 2026-09-24 on Windows / Python 3.12:

- `python -m compileall -q src tests`: PASS;
- Phase 6 unit suite: 14 tests, PASS;
- Persian preprocessing evaluation: 1 test, PASS;
- Persian NLP DI/resource lifecycle integration: 1 test, PASS;
- full project regression: 148 tests, PASS;
- failures: 0;
- errors: 0.

The asyncio `Executing <Task ... took ...>` lines emitted during PostgreSQL integration tests are diagnostic slow-callback messages and did not fail the test suite.

The original 148-test verification is retained as the pre-correction baseline.

## Accuracy correction pass

A post-closure audit identified correctness gaps that could affect later candidate and semantic phases. The correction pass:

- preserves internal technical/numeric compounds such as `GPT-4`, `BERT-base`, `v1.2` and `2026/09` as single tokens without creating false sentence boundaries;
- makes plural lemmatization conservative by stripping only explicit ZWNJ plural suffixes, preventing false reductions such as `اژدها -> اژد` and `منتها -> منت`;
- uses `X` for POS values that cannot be classified confidently instead of guessing `NOUN`;
- keeps protected terms unchanged by lemmatization;
- makes embedding stopword removal and lemma usage independently configurable, with conservative defaults that preserve natural normalized text until Phase 8 benchmarking;
- validates NLP boolean configuration strictly;
- rejects chained/cyclic synonym/canonical mappings so mapping precedence remains one-hop and deterministic;
- expands unit/evaluation regression coverage for these cases.

The correction is implemented but must pass local compile, Phase 6 unit/evaluation/integration tests and full project regression before Phase 6 is re-closed.

Current readiness marker:

`PHASE_6_CORRECTION_AWAITING_LOCAL_VERIFICATION`
