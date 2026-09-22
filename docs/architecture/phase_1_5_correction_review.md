# Phase 1–5 Finalization Review

Date: 2026-09-22
Status: IMPLEMENTED_AWAITING_LOCAL_VERIFICATION

## References

This finalization pass follows:
- `Service_Architecture_Guide_FA.md` for layering, constructor DI, discovery, controller conventions, repository boundaries, Config/Vault and Alembic.
- `Project_Architecture_and_Phases_FA.md` for phase scope, privacy, tests and Definition of Done.

## Phase 1

No runtime changes were required. Requirements, profiles, limits, persistence/privacy rules, evaluation requirements and deferred decisions remain frozen.

Implementation status: COMPLETE.

## Phase 2

Final corrections:
- provider discovery excludes `di` and `sso` in addition to the existing excluded folders;
- WebService instantiates discovered controllers directly, allowing dependency-free controllers without `@inject` while decorated controllers still receive constructor injection;
- the architecture contract records `AnalysisExecutionPolicyService -> ConfigReader`;
- tests cover the optional-`@inject` controller rule and discovery exclusions.

Implementation status: COMPLETE, awaiting regression re-verification after this correction set.

## Phase 3

The executable request-validation HTTP boundary is implemented and tested. Final lifecycle route shapes/status semantics are frozen without mounting fake processing routes. Raw-text duplication inside document metadata is rejected with a sanitized stable error.

Execution wiring remains correctly owned by Phase 10 (real profile processing) and Phase 12 (real queue/worker lifecycle), not by Phase 3.

Implementation status: COMPLETE, awaiting regression re-verification after this correction set.

## Phase 4

Final corrections:
- SOLDIER request metadata/options cannot be persisted as a privacy bypass;
- PostgreSQL constraint behavior is tested;
- FK cascade behavior is tested;
- destructive repository tests are pinned to `TEST_DATABASE_URL`.

Implementation status: COMPLETE, awaiting PostgreSQL and full-regression re-verification after this correction set.

## Phase 5

Final corrections:
- runtime, Alembic and migration runner share one database secret-resolution policy;
- Vault-enabled migration execution now resolves the same secret as application runtime;
- development dependency typo `httpx2` was corrected to `httpx`.

Implementation status: COMPLETE, awaiting full-regression re-verification after this correction set.

## Required final gate before Phase 6

```powershell
python -m pip install -r requirements-dev.txt
python -m compileall -q src tests

python -m unittest discover -s tests/unit/foundation -p "test_*.py" -v
python -m unittest discover -s tests/integration/foundation -p "test_*.py" -v

python -m unittest discover -s tests/unit/application -p "test_*.py" -v
python -m unittest discover -s tests/unit/core/services/analysis -p "test_*.py" -v
python -m unittest discover -s tests/integration/application -p "test_*.py" -v

python -m unittest discover -s tests/unit/configuration -p "test_*.py" -v
python -m unittest discover -s tests/integration/configuration -p "test_*.py" -v

$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:<YOUR_POSTGRES_PASSWORD>@localhost:5432/word_cloud_test"
python -m unittest discover -s tests/unit/persistence -p "test_*.py" -v
python -m unittest tests.integration.persistence.test_analysis_repository tests.integration.persistence.test_migration -v

python -m unittest discover -s tests -p "test_*.py" -v
```

Expected:
- compile succeeds;
- all focused suites pass;
- PostgreSQL integration/migration tests pass;
- full regression reports zero failures and zero errors.

Only after this gate passes should the repository be marked ready to start Phase 6.
