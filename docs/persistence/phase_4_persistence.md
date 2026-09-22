# Phase 4 — Database & Persistence

Status: IMPLEMENTED_AWAITING_REVERIFICATION
Correction: 2026-09-22

## Scope implemented

- SQLAlchemy models: `WordCloudAnalysis`, `AnalysisDocument`, `AnalysisKeyword`, `AnalysisTopic`, `AnalysisTopicKeyword`.
- Aggregate relationships and cascade rules.
- Lifecycle/type/execution constraints and essential indexes.
- `WordCloudAnalysisRepository` reusing `BaseRepository`.
- Pending-analysis persistence and lifecycle updates.
- Raw text is not persisted by default.
- Hard guard forbidding `SOLDIER_CONCERN` raw-text persistence.
- Defense-in-depth SOLDIER persistence policy: request metadata and request options are not persisted.
- Atomic result-graph persistence in one repository session and one commit.
- Explicit rollback on aggregate write failure.
- Alembic model visibility, migration environment, initial revision and migration runner.
- Database constraint and cascade behavior covered by PostgreSQL integration tests.

## Transaction boundary

Complete result persistence uses one `AsyncSession` and one commit. Existing result rows are replaced inside the same transaction. Any exception triggers rollback, leaving the previously committed aggregate intact.

## Privacy boundary

For all profiles, `AnalysisDocument.raw_text` is nullable and repository persistence defaults to `persist_raw_text=False`.

For `SOLDIER_CONCERN`:
- `persist_raw_text=True` is rejected before any database write;
- request document metadata is persisted as an empty object;
- request analysis options are persisted as an empty object;
- free-form request reference is persisted as NULL;
- caller-provided document IDs are persisted only as SHA-256 identifiers;
- document role is not persisted;
- failure messages are reduced to a generic persisted message;
- only identifiers, lifecycle metadata and later derived analytics may be persisted.

This prevents free-form request fields, document identifiers and failure messages from being used as a bypass around the raw-text persistence prohibition.

## Database integrity coverage

PostgreSQL integration tests now verify:
- invalid constrained values are rejected;
- duplicate document IDs within an analysis are rejected;
- keyword coverage constraints are enforced;
- deleting an analysis cascades to document/keyword/topic/topic-keyword rows;
- result graph writes are atomic;
- failed aggregate writes rollback;
- migration upgrade/downgrade works against PostgreSQL.

The integration test setup pins `DATABASE_URL` to `TEST_DATABASE_URL` while constructing the test DbContext so a pre-existing developer `DATABASE_URL` cannot redirect destructive tests to another database. The existing database-name safety check still requires `test` in the database name.

## Local verification

```powershell
$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:<YOUR_POSTGRES_PASSWORD>@localhost:5432/word_cloud_test"

python -m unittest discover -s tests/unit/persistence -p "test_*.py" -v
python -m unittest tests.integration.persistence.test_analysis_repository tests.integration.persistence.test_migration -v
python -m unittest discover -s tests -p "test_*.py" -v
```

## Final verification evidence

Verified locally on 2026-09-22:
- PostgreSQL persistence behavior passed inside the final regression.
- Constraint, cascade, privacy, atomic-write and rollback tests passed.
- Alembic upgrade/downgrade test passed.
- Full regression suite: 113 tests passed.
- Failures: 0.
- Errors: 0.

The privacy correction above requires PostgreSQL and full-regression re-verification before Phase 4 is re-closed.

Current verification marker:

`PHASE_4_IMPLEMENTED_AWAITING_REVERIFICATION`
