# Phase 6 — Persian NLP Core

Status: IMPLEMENTED_AWAITING_LOCAL_VERIFICATION

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

## Verification state

Phase 6 includes unit tests, a Persian preprocessing evaluation fixture, DI/resource lifecycle integration coverage and is ready for the repository-wide local regression gate. It must not be marked CLOSED until those commands pass on the user's machine.
