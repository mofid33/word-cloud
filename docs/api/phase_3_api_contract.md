# Phase 3 — API & DTO Contract

Status: FROZEN
Implementation Status: PARTIAL
Correction: 2026-09-22

Phase 3 owns the HTTP contract, request/response DTOs, validation, error/status behavior and DTO mapping. Runtime behavior from later phases must not be faked merely to close this phase.

## Implemented executable endpoint

\`POST /api/v1/analysis/validate\`

Request fields:
- \`analysis_type\`: \`COURSE | SOLDIER_CONCERN | MEDIA\`
- \`documents\`: non-empty list
- \`execution_mode\`: \`auto | sync | async\`
- \`reference\`: optional
- \`options\`: optional

Each document:
- \`document_id\`: non-blank string
- \`text\`: non-blank string
- \`metadata\`: optional object

## Implemented validation behavior

DTO/schema validation:
- unknown fields are rejected.
- blank \`document_id\` and \`text\` values are rejected.
- malformed request payloads return sanitized HTTP 422 without echoing raw input.

Cross-field validation in Core:
- document IDs must be unique within one request.
- \`MEDIA\` documents require \`metadata.role\` equal to \`published_content\` or \`audience_feedback\`.

Execution policy validation in Core:
- Phase 1 hard limits are read from runtime configuration and enforced.
- \`auto\` resolves to \`sync\` only when both configured sync thresholds fit; otherwise it resolves to \`async\`.
- explicit \`sync\` above the configured sync threshold is rejected.
- hard-limit violations map to HTTP 413.
- contract/policy validation violations map to HTTP 422.

Success response:
- HTTP 200.
- returns \`analysis_type\`, requested \`execution_mode\`, \`resolved_execution_mode\`, document count and total character count.
- never echoes document text.

Stable application error envelope:

\`\`\`json
{
  "detail": {
    "code": "stable_error_code",
    "message": "sanitized message"
  }
}
\`\`\`

Pydantic/FastAPI request validation is normalized to:

\`\`\`json
{
  "detail": {
    "code": "request_validation_error",
    "message": "Request payload validation failed"
  }
}
\`\`\`

## Execution endpoints still open

The earlier repository state incorrectly marked Phase 3 complete while only the validation endpoint was implemented.

The Analysis lifecycle contract still requires executable HTTP behavior for the product-level operations designed in the architecture:
- create analysis;
- retrieve analysis status;
- retrieve structured analysis result.

Those endpoints must not be closed with in-memory persistence, placeholder processing, fake queue providers, or temporary business behavior.

Phase 4 now provides real persistence, but synchronous analysis completion still depends on the real analytics processing pipeline and asynchronous dispatch still belongs to Phase 12. Until the final route/status behavior can be implemented without violating those boundaries, Phase 3 remains open.

## Verification after this correction

The correction adds/changes tests for:
- configuration-driven execution policy;
- hard input limits;
- auto sync/async resolution;
- explicit sync threshold rejection;
- HTTP 413/422 mapping;
- sanitized schema-validation errors;
- existing DTO/controller/API behavior.

Run:

\`\`\`powershell
python -m compileall -q src tests
python -m unittest discover -s tests/unit/core/services/analysis -p "test_*.py" -v
python -m unittest discover -s tests/integration/application -p "test_*.py" -v
python -m unittest discover -s tests -p "test_*.py" -v
\`\`\`

Current closure marker:

\`PHASE_3_OPEN\`
