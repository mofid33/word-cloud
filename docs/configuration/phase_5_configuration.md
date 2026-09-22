# Phase 5 — Configuration & Environments

Status: IMPLEMENTED
Original completion: 2026-09-22
Correction review: 2026-09-22

## Scope implemented

- Separate development and production runtime configuration.
- PostgreSQL pool settings.
- Model lifecycle/configuration settings without freezing a production NLP model.
- CPU device configuration plus a configuration boundary for future GPU-capable providers.
- Configurable batch settings.
- Frozen Phase 1 analysis limits and sync thresholds represented in runtime configuration.
- Runtime database secret resolution:
  - environment-backed Vault boundary when \`vault.enabled=true\`;
  - \`DATABASE_URL\` environment override otherwise;
  - development YAML fallback for local execution.
- Production YAML contains no database credential.
- Local PostgreSQL dependency through \`compose.yaml\`.
- Automatic local test database creation for \`word_cloud_test\`.
- Example environment file without real secrets.
- Unit tests for environment selection, settings, secret resolution and local Compose.
- Integration test for application startup using development configuration.
- Runtime consumption of analysis limits and sync thresholds through \`AnalysisExecutionPolicyService\`.

## Configuration policy

\`ENV_TYPE=development\` selects \`appsettings.development.yaml\`.
Any other environment value selects \`appsettings.yaml\`, preserving the architecture convention established by the project.

Production database credentials are not stored in \`appsettings.yaml\`. Supply \`DATABASE_URL\` at runtime, or enable the current secret boundary and supply \`VAULT_DATABASE_URL\`.

## Vault boundary clarification

\`VaultService\` in the current Phase 5 implementation is a secret-resolution boundary backed by environment variables. It is not a concrete HashiCorp Vault client and must not be represented as a completed external Vault integration.

A concrete external secret backend can be introduced later only when the deployment architecture requires it and without changing Core business logic.

## Device/GPU clarification

Phase 5 provides device configuration only. The presence of:

\`\`\`yaml
device:
  type: "cpu"
  cuda_device_index: 0
\`\`\`

does not prove GPU runtime support by itself. Actual CPU/GPU model execution belongs to the concrete semantic providers and benchmark work in Phase 8.

NLP model names remain intentionally unfrozen. Model/provider selection belongs to the Persian benchmark work in Phase 8.

## Runtime policy integration

The configured values under:

\`\`\`text
analysis.limits.*
analysis.sync_threshold.*
\`\`\`

are now consumed by \`AnalysisExecutionPolicyService\`.

The service enforces:
- maximum documents per analysis;
- maximum characters per document;
- maximum total characters;
- explicit sync thresholds;
- \`auto\` resolution to \`sync\` or \`async\`.

These values are not duplicated as production constants in business logic.

## Historical completion evidence

Before this correction, Phase 5 had been locally verified on the Windows development environment with compile, configuration tests, development startup, PostgreSQL integration and the then-current regression suite.

Because this correction changes runtime consumption of Phase 5 settings, the current revision must be reverified locally before treating the historical completion evidence as evidence for the corrected commit.

## Commands to reverify

\`\`\`powershell
python -m pip install -r requirements-dev.txt
python -m compileall -q src tests
python -m unittest discover -s tests/unit/configuration -p "test_*.py" -v
python -m unittest discover -s tests/unit/core/services/analysis -p "test_*.py" -v
python -m unittest discover -s tests/integration/configuration -p "test_*.py" -v
python -m unittest discover -s tests/integration/application -p "test_*.py" -v
python -m unittest discover -s tests -p "test_*.py" -v
\`\`\`

Local PostgreSQL dependency:

\`\`\`powershell
docker compose up -d postgres
docker compose ps
\`\`\`

Optional runtime DB override:

\`\`\`powershell
$env:DATABASE_URL = "postgresql+asyncpg://postgres:<YOUR_POSTGRES_PASSWORD>@localhost:5432/postgres"
\`\`\`

Do not commit real passwords or production connection strings.

Current verification marker:

\`PHASE_5_REVERIFY_AFTER_CORRECTION\`
