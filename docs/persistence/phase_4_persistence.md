# Phase 4 — Database & Persistence

Status: IMPLEMENTED_AWAITING_LOCAL_VERIFICATION
Date: 2026-09-22

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

## Local verification

Phase 4 is not CLOSED until PostgreSQL integration tests pass locally. Use a dedicated database whose name contains `test`; the destructive integration tests reject other database names.

```powershell
$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/word_cloud_test"
python -m pip install -r requirements-dev.txt
python -m compileall -q src tests
python -m unittest discover -s tests/unit/persistence -p "test_*.py" -v
python -m unittest discover -s tests/integration/persistence -p "test_*.py" -v
python -m unittest discover -s tests -p "test_*.py" -v
```

Migration runner:

```powershell
python src/infrastructure/scripts/run_migrations.py --upgrade
python src/infrastructure/scripts/run_migrations.py --downgrade
```
