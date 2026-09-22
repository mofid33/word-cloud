# Phase 3 — API & DTO Contract

Status: FROZEN

This phase implements the HTTP boundary that can be completed without inventing Phase 4 persistence or Phase 12 queue behavior.

## Executable endpoint

`POST /api/v1/analysis/validate`

The endpoint validates the frozen request shape before analysis execution exists.

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

Cross-field rules implemented in Core:
- document IDs are unique within the request.
- MEDIA documents require `metadata.role` equal to `published_content` or `audience_feedback`.

Success:
- HTTP 200
- returns validity plus document and character counts.
- response never echoes raw document text.

Errors:
- malformed DTO/schema: FastAPI/Pydantic HTTP 422.
- cross-field validation failure: HTTP 422 with stable `code` and `message`.

## Deferred execution endpoints

Create/status/result execution endpoints are not faked in Phase 3. They require the real persistence lifecycle from Phase 4 and async dispatch from Phase 12. Their concrete success behavior will be added only when those dependencies are real.

No SQLAlchemy model, Repository, migration, queue implementation, NLP implementation, or in-memory persistence is introduced by Phase 3.
