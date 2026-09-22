# Phase 1–5 Correction Review

Date: 2026-09-22
Scope: corrections identified during the post-Phase-5 architecture review.

## Reference documents

This correction follows:
- \`Service_Architecture_Guide_FA.md\` for layering, DI, discovery, naming, repository and runtime conventions.
- \`Project_Architecture_and_Phases_FA.md\` for phase scope and Definition of Done.

## Corrections applied

### Phase 2 — DI/discovery

1. Discovery now follows the reference behavior for import failures: one broken discoverable module is skipped and does not stop unrelated provider discovery.
2. Cached modules are inspected for \`@inject\` providers so resetting DI state does not permanently lose registrations when modules remain in \`sys.modules\`.
3. DI reset increments an internal generation. Bootstrap tracks that generation and rescans after a reset instead of incorrectly treating the container as already bootstrapped.
4. Tests cover broken-module isolation and cached-provider restoration.

No manual provider registration or additional DI framework was introduced.

### Phase 3 — API/DTO validation boundary

1. \`AnalysisExecutionPolicyService\` is implemented as a Core service.
2. Phase 1 hard limits are consumed from configuration and enforced.
3. \`auto\` resolves to \`sync\` or \`async\` using both configured sync thresholds.
4. Explicit sync above threshold is rejected.
5. Hard-limit errors map to HTTP 413; request/policy contract errors map to HTTP 422.
6. FastAPI/Pydantic request validation is normalized to a sanitized error response so raw request text is not echoed in validation details.
7. The validation response now exposes both requested and resolved execution modes.
8. The previous false \`PHASE_3_COMPLETE\` marker was removed. Lifecycle create/status/result API behavior remains open rather than being faked.

### Phase 5 — configuration boundary

1. Analysis limits and sync thresholds are now consumed by runtime policy code rather than merely existing in YAML.
2. Documentation now states accurately that the current \`VaultService\` is environment-backed secret resolution, not a concrete external Vault integration.
3. Documentation now distinguishes device configuration from actual GPU model runtime, which belongs to Phase 8.

## Unchanged phases

Phase 1 requirements remain frozen.

Phase 4 persistence implementation is unchanged: models, repository, transaction boundary, privacy guard and migration remain as previously implemented.

## Required local verification

\`\`\`powershell
python -m pip install -r requirements-dev.txt
python -m compileall -q src tests

python -m unittest discover -s tests/unit/foundation -p "test_*.py" -v
python -m unittest discover -s tests/integration/foundation -p "test_*.py" -v

python -m unittest discover -s tests/unit/core/services/analysis -p "test_*.py" -v
python -m unittest discover -s tests/integration/application -p "test_*.py" -v

$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:<YOUR_POSTGRES_PASSWORD>@localhost:5432/word_cloud_test"
python -m unittest tests.integration.persistence.test_analysis_repository tests.integration.persistence.test_migration -v

python -m unittest discover -s tests -p "test_*.py" -v
\`\`\`

## Expected result

- source and tests compile;
- DI/discovery tests pass;
- API/controller/service policy tests pass;
- Phase 4 PostgreSQL integration remains green;
- full regression has zero failures and zero errors.

Phase 3 must remain open until its product-level lifecycle HTTP contract can be implemented without fake processing or queue behavior.
