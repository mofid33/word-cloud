# Phase 5 — Configuration & Environments

Status: COMPLETE
Completed: 2026-09-22
Correction reverified: 2026-09-22

## Scope implemented

- Separate development and production runtime configuration.
- PostgreSQL pool settings.
- Model lifecycle/configuration settings without freezing a production NLP model.
- CPU device configuration plus a configuration boundary for future GPU-capable providers.
- Configurable batch settings.
- Frozen Phase 1 analysis limits and sync thresholds represented in runtime configuration.
- Runtime database secret resolution:
  - environment-backed Vault boundary when `vault.enabled=true`;
  - `DATABASE_URL` environment override otherwise;
  - development YAML fallback for local execution.
- Production YAML contains no database credential.
- Local PostgreSQL dependency through `compose.yaml`.
- Automatic local test database creation for `word_cloud_test`.
- Example environment file without real secrets.
- Unit tests for environment selection, settings, secret resolution and local Compose.
- Integration test for application startup using development configuration.
- Runtime consumption of analysis limits and sync thresholds through `AnalysisExecutionPolicyService`.

## Configuration policy

`ENV_TYPE=development` selects `appsettings.development.yaml`.
Any other environment value selects `appsettings.yaml`, preserving the architecture convention established by the project.

Production database credentials are not stored in `appsettings.yaml`. Supply `DATABASE_URL` at runtime, or enable the current secret boundary and supply `VAULT_DATABASE_URL`.

## Vault boundary clarification

`VaultService` in the current Phase 5 implementation is a secret-resolution boundary backed by environment variables. It is not a concrete HashiCorp Vault client and must not be represented as a completed external Vault integration.

A concrete external secret backend can be introduced later only when the deployment architecture requires it and without changing Core business logic.

## Device/GPU clarification

Phase 5 provides device configuration only. The presence of:

```yaml
device:
  type: "cpu"
  cuda_device_index: 0
```

does not prove GPU runtime support by itself. Actual CPU/GPU model execution belongs to the concrete semantic providers and benchmark work in Phase 8.

NLP model names remain intentionally unfrozen. Model/provider selection belongs to the Persian benchmark work in Phase 8.

## Runtime policy integration

The configured values under:

```text
analysis.limits.*
analysis.sync_threshold.*
```

are consumed by `AnalysisExecutionPolicyService`.

The service enforces:
- maximum documents per analysis;
- maximum characters per document;
- maximum total characters;
- explicit sync thresholds;
- `auto` resolution to `sync` or `async`.

These values are not duplicated as production constants in business logic.

## Completion evidence

The corrected Phase 5 implementation was reverified on the local Windows development environment on 2026-09-22.

Verified results:
- PostgreSQL container healthy.
- Dedicated `word_cloud_test` database available.
- PostgreSQL repository and Alembic migration integration suite: 5 tests passed.
- Full project regression suite: 104 tests passed.
- Failures: 0.
- Errors: 0.
- DI/discovery corrections remained green.
- API/controller/execution-policy tests remained green.
- Phase 4 persistence and migration behavior remained green.

## Local verification commands

```powershell
python -m pip install -r requirements-dev.txt
python -m compileall -q src tests
python -m unittest discover -s tests/unit/configuration -p "test_*.py" -v
python -m unittest discover -s tests/unit/core/services/analysis -p "test_*.py" -v
python -m unittest discover -s tests/integration/configuration -p "test_*.py" -v
python -m unittest discover -s tests/integration/application -p "test_*.py" -v
python -m unittest tests.integration.persistence.test_analysis_repository tests.integration.persistence.test_migration -v
python -m unittest discover -s tests -p "test_*.py" -v
```

Do not commit real passwords or production connection strings.

PHASE_5_COMPLETE
