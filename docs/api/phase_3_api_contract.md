# Phase 3 — API & DTO Contract

Status: IMPLEMENTED_AWAITING_REVERIFICATION
Correction: 2026-09-22

## Executable routes

Phase 3 now exposes an executable and testable HTTP contract:

- `POST /api/v1/analysis/validate`
- `POST /api/v1/analysis`
- `GET /api/v1/analysis/{analysis_id}`
- `GET /api/v1/analysis/{analysis_id}/result`

The create route performs the Phase 3/4 work that is real today: validation, execution-mode resolution and creation of a real persisted lifecycle resource with status `pending`.

It does not fake Phase 10 processing or Phase 12 queue behavior. Later phases extend the same `AnalysisService.create_async` workflow behind this stable route:
- Phase 10 adds real synchronous processing before the response can become completed.
- Phase 12 adds real asynchronous queue dispatch while retaining the same lifecycle resource.

## Request contract

`AnalysisRequestDto`:
- `analysis_type`: `COURSE | SOLDIER_CONCERN | MEDIA`
- `documents`: non-empty list
- `execution_mode`: `auto | sync | async`
- `reference`: optional
- `options`: optional

Each document:
- `document_id`: non-blank string
- `text`: non-blank string
- `metadata`: optional object

Unknown fields are rejected.

## Validation and privacy

Core validation enforces:
- unique document IDs;
- MEDIA role = `published_content` or `audience_feedback`;
- document metadata must not repeat the document raw text;
- configuration-driven hard input limits;
- explicit sync thresholds;
- `auto` resolution to `sync` or `async`.

FastAPI/Pydantic errors are normalized to a sanitized envelope and raw request text is not echoed.

For `SOLDIER_CONCERN`, persistence applies an additional defense-in-depth boundary: raw text, request metadata, request options, role and free-form `reference` are not persisted; caller-provided document IDs are persisted only as SHA-256 identifiers and persisted failure messages are generic.

## HTTP status contract

Validation:
- 200 — valid request.
- 413 — hard input limit exceeded.
- 422 — DTO/cross-field/execution-policy validation failure.

Create:
- 201 — lifecycle resource created successfully.
- 413/422 — same request validation semantics as the validation endpoint.

Status:
- 200 — analysis exists.
- 404 — analysis does not exist.

Result:
- 200 — completed structured result is available.
- 404 — analysis does not exist.
- 409 — analysis exists but no result is currently available.

Stable error envelope:

```json
{
  "detail": {
    "code": "stable_error_code",
    "message": "sanitized message"
  }
}
```

## Structured result contract

The result response preserves the Phase 1 JSON-first groups:
- `analysis`
- `keywords`
- `topics`
- `metrics`
- `profile_result`

Keyword fields include:
- text
- canonical_text
- rank
- final_score
- statistical_score
- semantic_score
- coverage
- frequency

Topic fields include:
- topic_id
- label
- rank
- prevalence
- coverage
- representative keywords with relevance score

## Tests

Coverage includes:
- DTO validation;
- validation endpoint;
- create endpoint;
- status 404;
- result 409;
- route discovery/OpenAPI;
- stable 413/422/404/409 mapping;
- privacy-safe errors;
- execution-mode resolution.

The final gate must re-run the complete regression and PostgreSQL integration suite after this correction.

Current marker:

`PHASE_3_IMPLEMENTED_AWAITING_REVERIFICATION`
