# Phase 5 — Configuration & Environments

Status: COMPLETE
Correction: 2026-09-22

## Scope implemented

- Separate development and production runtime configuration.
- PostgreSQL pool settings.
- Model lifecycle/configuration settings without freezing a production NLP model.
- CPU device configuration plus a configuration boundary for future GPU-capable providers.
- Configurable batch settings.
- Frozen Phase 1 analysis limits and sync thresholds represented in runtime configuration.
- Runtime database secret resolution.
- Alembic and migration-runner database resolution reuse the same runtime secret policy.
- Production YAML contains no database credential.
- Local PostgreSQL dependency through `compose.yaml`.
- Automatic local test database creation for `word_cloud_test`.
- Example environment file without real secrets.
- Unit tests for environment selection, settings, secret resolution and local Compose.
- Integration test for application startup using development configuration.
- Runtime consumption of analysis limits and sync thresholds through `AnalysisExecutionPolicyService`.

## Configuration policy

`ENV_TYPE=development` selects `appsettings.development.yaml`.
Any other environment value selects `appsettings.yaml`.

Database URL resolution is now a single policy exposed by `PsqlDbContext.resolve_database_url`:

1. when `vault.enabled=true`, resolve `VAULT_DATABASE_URL` through `VaultService`;
2. otherwise use `DATABASE_URL` when present;
3. otherwise fall back to `database.url` from configuration.

Application runtime, Alembic and `run_migrations.py` use this same policy.

## Vault boundary

The current `VaultService` is an environment-backed secret-resolution boundary. It is not a concrete HashiCorp Vault client. A concrete external secret backend may be introduced later only if deployment architecture requires it.

## Device/GPU boundary

Phase 5 configures device selection but does not claim a working CUDA model provider. Actual CPU/GPU model execution belongs to Phase 8.

NLP model names remain intentionally unfrozen until Persian benchmark/evaluation.

## Development dependency correction

`requirements-dev.txt` uses the real `httpx` package required by FastAPI/TestClient:

```text
httpx>=0.27,<1.0
```

The previous `httpx2` entry was removed.

## Local verification

```powershell
python -m pip install -r requirements-dev.txt
python -m compileall -q src tests
python -m unittest discover -s tests/unit/configuration -p "test_*.py" -v
python -m unittest discover -s tests/integration/configuration -p "test_*.py" -v
python -m unittest discover -s tests -p "test_*.py" -v
```

## Final verification evidence

Verified locally on 2026-09-22:
- development startup/configuration tests passed;
- runtime/Vault/database URL resolution tests passed;
- Foundation integration suite: 7 tests passed;
- full regression suite: 113 tests passed;
- failures: 0;
- errors: 0;
- source and tests compiled successfully.

Current verification marker:

`PHASE_5_COMPLETE`
