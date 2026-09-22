# Phase 4 — Database & Persistence

Status: COMPLETE
Completed: 2026-09-22

## Scope implemented

- SQLAlchemy models: `WordCloudAnalysis`, `AnalysisDocument`, `AnalysisKeyword`, `AnalysisTopic`, `AnalysisTopicKeyword`.
- Aggregate relationships and cascade rules.
- Lifecycle/type/execution constraints and essential indexes.
- `WordCloudAnalysisRepository` reusing `BaseRepository`.
- Pending-analysis persistence and lifecycle updates.
- Raw text is not persisted by default.
- Hard guard forbidding `SOLDIER_CONCERN` raw-text persistence.
- Atomic result-graph persistence in one repository session and one commit.
- Explicit rollback on aggregate write failure.
- Alembic model visibility, migration environment, initial revision and migration runner.
- Model, repository, privacy, transaction rollback and migration tests.

## Transaction boundary

Complete result persistence uses one `AsyncSession` and one commit. Existing result rows are replaced inside the same transaction. Any exception triggers rollback, leaving the previously committed aggregate intact.

## Privacy boundary

`AnalysisDocument.raw_text` is nullable. Repository persistence defaults to `persist_raw_text=False`. For `SOLDIER_CONCERN`, setting it to true raises before any database write.

## Completion evidence

Phase 4 was closed after verification on the local Windows development environment with a dedicated PostgreSQL test database:

- `python -m compileall -q src tests` completed successfully.
- Unit persistence/model tests passed.
- PostgreSQL repository integration tests passed.
- Raw-text default non-persistence test passed.
- `SOLDIER_CONCERN` raw-text persistence rejection test passed.
- Atomic result-graph persistence test passed.
- Transaction rollback test passed.
- Alembic upgrade/downgrade migration test passed against PostgreSQL.
- Phase 4 persistence suite: 5 tests passed.
- Full regression suite: 79 tests passed, 0 failures, 0 errors.
- Existing Phase 1–3 API, DI, startup, architecture, requirements and service tests remained green.

## Local verification commands

Use a dedicated database whose name contains `test`; the destructive integration tests reject other database names.

Use the actual credentials for your local PostgreSQL instance. Do not copy passwords into source control.

```powershell
$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:<YOUR_POSTGRES_PASSWORD>@localhost:5432/word_cloud_test"

python -m pip install -r requirements-dev.txt
python -m compileall -q src tests

python -m unittest discover -s tests/unit/persistence -p "test_*.py" -v

python -m unittest tests.integration.persistence.test_analysis_repository tests.integration.persistence.test_migration -v

python -m unittest discover -s tests -p "test_*.py" -v
```

If the password contains URL-reserved characters such as `@`, `:`, `/`, `#`, or `%`, URL-encode the password before placing it in `TEST_DATABASE_URL`.

Migration runner:

```powershell
python src/infrastructure/scripts/run_migrations.py --upgrade
python src/infrastructure/scripts/run_migrations.py --downgrade
```

PHASE_4_COMPLETE
