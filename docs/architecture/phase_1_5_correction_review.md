# Phase 1–5 Correction Review

Date: 2026-09-22
Verification status: PASSED

## Reference documents

This correction follows:
- `Service_Architecture_Guide_FA.md` for layering, DI, discovery, naming, repository and runtime conventions.
- `Project_Architecture_and_Phases_FA.md` for phase scope and Definition of Done.

## Corrections applied

### Phase 2 — DI/discovery

1. Discovery follows the reference behavior for import failures: one broken discoverable module is skipped and does not stop unrelated provider discovery.
2. Cached modules are inspected for `@inject` providers so resetting DI state does not permanently lose registrations when modules remain in `sys.modules`.
3. DI reset increments an internal generation. Bootstrap tracks that generation and rescans after a reset instead of incorrectly treating the container as already bootstrapped.
4. Tests cover broken-module isolation and cached-provider restoration.

No manual provider registration or additional DI framework was introduced.

### Phase 3 — API/DTO validation boundary

1. `AnalysisExecutionPolicyService` is implemented as a Core service.
2. Phase 1 hard limits are consumed from configuration and enforced.
3. `auto` resolves to `sync` or `async` using both configured sync thresholds.
4. Explicit sync above threshold is rejected.
5. Hard-limit errors map to HTTP 413; request/policy contract errors map to HTTP 422.
6. FastAPI/Pydantic request validation is normalized to a sanitized error response so raw request text is not echoed in validation details.
7. The validation response exposes both requested and resolved execution modes.
8. The previous false `PHASE_3_COMPLETE` marker was removed. Lifecycle create/status/result API behavior remains open rather than being faked.

### Phase 5 — configuration boundary

1. Analysis limits and sync thresholds are consumed by runtime policy code rather than merely existing in YAML.
2. Documentation states accurately that the current `VaultService` is environment-backed secret resolution, not a concrete external Vault integration.
3. Documentation distinguishes device configuration from actual GPU model runtime, which belongs to Phase 8.

## Unchanged phases

Phase 1 requirements remain frozen.

Phase 4 persistence implementation is unchanged: models, repository, transaction boundary, privacy guard and migration remain as previously implemented.

## Local verification evidence

The correction set was verified on the local Windows development environment on 2026-09-22.

Results:
- PostgreSQL container: healthy.
- Dedicated test database: available.
- Persistence + Alembic integration suite: 5 tests passed.
- Full regression suite: 104 tests passed.
- Failures: 0.
- Errors: 0.

This confirms the Phase 2 correction, Phase 4 persistence behavior, and Phase 5 corrected runtime configuration are green together.

## Current phase status after correction

- Phase 1 — CLOSED.
- Phase 2 — CLOSED and reverified.
- Phase 3 — OPEN/PARTIAL; validation and execution-policy HTTP boundary are implemented, but product-level create/status/result lifecycle API remains open.
- Phase 4 — CLOSED and reverified.
- Phase 5 — CLOSED and reverified.

Phase 3 must remain open until its product-level lifecycle HTTP contract can be implemented without fake processing or queue behavior.
