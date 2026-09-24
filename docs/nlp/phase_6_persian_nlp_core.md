# Phase 6 — Persian NLP Core

Status: CLOSED

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

Phase 6 satisfies its Definition of Done and is CLOSED.

Current readiness marker:

`PHASE_6_COMPLETE_READY_FOR_PHASE_7`
