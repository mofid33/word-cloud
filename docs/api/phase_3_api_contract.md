# Phase 3 — API & DTO Contract

Status: IMPLEMENTED_AWAITING_LOCAL_VERIFICATION
Implementation correction: 2026-09-22

## Phase boundary

Phase 3 freezes and implements the HTTP/DTO/validation boundary that can exist without inventing Phase 10 processing or Phase 12 queue behavior.

The executable Phase 3 endpoint is:

`POST /api/v1/analysis/validate`

The final lifecycle routes are frozen for later runtime wiring:

- `POST /api/v1/analysis` — create/execute analysis.
- `GET /api/v1/analysis/{analysis_id}` — retrieve lifecycle/status.
- `GET /api/v1/analysis/{analysis_id}/result` — retrieve structured result.

These routes are intentionally not mounted before their real business behavior exists. Returning placeholder data, creating analyses that can never progress, or introducing fake queue/processor implementations would violate the project Definition of Done.

Ownership after Phase 3:
- Phase 10 wires the real synchronous profile-processing path and structured result mapping.
- Phase 12 wires the real asynchronous queue/worker lifecycle.
- Phase 13 adds visualization/image endpoints.

## Implemented request contract

Request fields:
- `analysis_type`: `COURSE | SOLDIER_CONCERN | MEDIA`
- `documents`: non-empty list
- `execution_mode`: `auto | sync | async`
- `reference`: optional
- `options`: optional

Each document:
- `document_id`: non-blank string
- `text`: non-blank string
- `metadata`: optional object

DTOs live under:

`src/application/analysis/dtos/analysis_dto.py`

Unknown fields are rejected.

## Validation and privacy contract

Core validation enforces:
- unique document IDs;
- MEDIA role = `published_content` or `audience_feedback`;
- document metadata must not repeat the document raw text;
- Phase 1 hard input limits;
- explicit sync thresholds;
- `auto` resolution to `sync` or `async`.

FastAPI/Pydantic schema failures are normalized to a sanitized error envelope and do not echo raw request content.

## HTTP status behavior

For the executable validation endpoint:
- HTTP 200 — valid request.
- HTTP 413 — configured hard input limit exceeded.
- HTTP 422 — DTO, cross-field or execution-policy validation failure.

Stable error envelope:

```json
{
  "detail": {
    "code": "stable_error_code",
    "message": "sanitized message"
  }
}
```

Reserved execution-route behavior is frozen as follows for future wiring:
- create route resolves `auto`; sync completion returns HTTP 200 and async acceptance returns HTTP 202;
- status route returns HTTP 200 for an existing analysis and HTTP 404 for an unknown analysis;
- result route returns HTTP 200 only for a completed result, HTTP 409 when the lifecycle state cannot provide a result, and HTTP 404 for an unknown analysis;
- hard-limit and validation failures retain HTTP 413/422 semantics;
- raw text must never be included in error payloads.

## Tests

Implemented tests cover:
- DTO validation;
- controller discovery;
- controller success/error mapping;
- sanitized schema validation;
- duplicate document IDs;
- MEDIA role validation;
- raw-text repetition in metadata;
- hard limits;
- explicit sync threshold rejection;
- auto sync/async resolution;
- HTTP 413/422 behavior.

## Definition of Done

Phase 3 is implementation-complete when:
- the validation HTTP boundary is executable;
- DTO validation and mapping are real;
- stable HTTP error/status behavior is tested;
- final lifecycle route shapes/status semantics are frozen without fake processing;
- Phase 10/12 runtime work is not implemented prematurely;
- all Phase 3 and regression tests pass locally.

Current verification marker:

`PHASE_3_IMPLEMENTED_AWAITING_LOCAL_VERIFICATION`
