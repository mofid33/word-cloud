# Phase 5 — Configuration & Environments

Status: IMPLEMENTED_AWAITING_LOCAL_VERIFICATION
Date: 2026-09-22

## Scope implemented

- Separate development and production runtime configuration.
- PostgreSQL pool settings.
- Model lifecycle/configuration settings without freezing a production NLP model.
- CPU device configuration with a future GPU-selectable boundary.
- Configurable batch settings.
- Frozen Phase 1 analysis limits and sync thresholds represented in runtime configuration.
- Runtime database secret resolution:
  - Vault secret when `vault.enabled=true`.
  - `DATABASE_URL` environment override otherwise.
  - Development YAML fallback for local execution.
- Production YAML contains no database credential.
- Local PostgreSQL dependency through `compose.yaml`.
- Automatic local test database creation for `word_cloud_test`.
- Example environment file without real secrets.
- Unit tests for environment selection, settings, secret resolution and local Compose.
- Integration test for application startup using development configuration.

## Configuration policy

`ENV_TYPE=development` selects `appsettings.development.yaml`.
Any other environment value selects `appsettings.yaml`, preserving the architecture convention already established by the project.

Production database credentials are not stored in `appsettings.yaml`. Supply `DATABASE_URL` at runtime, or enable the Vault boundary and supply the configured database secret.

NLP model names remain intentionally unfrozen. Model/provider selection belongs to the Persian benchmark work in Phase 8.

## Local verification

Phase 5 must not be marked COMPLETE until the following commands pass on the local development machine.

```powershell
python -m pip install -r requirements-dev.txt
python -m compileall -q src tests
python -m unittest discover -s tests/unit/configuration -p "test_*.py" -v
python -m unittest discover -s tests/integration/configuration -p "test_*.py" -v
python -m unittest discover -s tests -p "test_*.py" -v
```

Local PostgreSQL dependency:

```powershell
docker compose up -d postgres
docker compose ps
```

Optional runtime DB override:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://postgres:<YOUR_POSTGRES_PASSWORD>@localhost:5432/postgres"
```

Do not commit real passwords or production connection strings.
