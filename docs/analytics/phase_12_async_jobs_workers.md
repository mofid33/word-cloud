# Phase 12 — Async Jobs & Workers

Status: COMPLETE — READY_FOR_PHASE_13
Date: 2026-10-01
Baseline: `611c0f45d6a31e04fdca1af3a21f6288b87a981e`

## مرحله

Phase 12 — Async Jobs & Workers

## هدف

اتصال مسیر واقعی async analysis به Queue و Worker بدون انتقال business logic مربوط به NLP، Ranking، Topic یا Profile به Worker.

## ورودی

- Phase 11 marker: `PHASE_11_COMPLETE_READY_FOR_PHASE_12`
- frozen execution/lifecycle/persistence/privacy contracts
- existing `AnalysisQueueProvider`, `AnalysisService`, `AnalysisProcessorService`
- PostgreSQL persistence foundation

## خروجی پیاده‌سازی‌شده

- PostgreSQL-backed durable queue + Redis non-durable transient payload transport for SOLDIER_CONCERN.
- versioned identifier-only queue job payload.
- enqueue / receive / lease / heartbeat / acknowledgement / requeue / final failure.
- `FOR UPDATE SKIP LOCKED` consumption برای concurrent workers.
- atomic `pending -> processing` claim در Repository.
- retry با exponential backoff و maximum-attempt limit.
- stale-processing recovery و lease heartbeat.
- Worker runtime مستقل با graceful stop و configurable concurrency.
- async COURSE/MEDIA processing input به‌طور موقت در existing `AnalysisDocument.raw_text` نگهداری و پس از success/final failure پاک می‌شود.
- duplicate/completed/failed/unknown delivery رفتار deterministic دارد.
- queue error metadata فقط sanitized error code است.
- queue payload شامل raw text، request object، secret یا model config نیست.

## SOLDIER_CONCERN transient privacy transport

مسیر async برای `SOLDIER_CONCERN` اکنون پیاده‌سازی شده است.

- Raw Text در PostgreSQL persist نمی‌شود.
- Raw Text وارد durable `analysis_queue_job.payload` نمی‌شود.
- PostgreSQL queue فقط identifier/type/version را نگهداری می‌کند.
- Raw processing payload فقط در Redis transient memory نگهداری می‌شود.
- Redis provider قبل از استفاده verify می‌کند که RDB snapshot و AOF هر دو disabled باشند؛ در غیر این صورت fail-closed است.
- payload دارای TTL است و هنگام completion/final failure حذف می‌شود.
- heartbeat و retry TTL را renew می‌کنند.
- اگر transient payload پس از crash/restart موجود نباشد، analysis با error sanitized به `failed` می‌رود.
- Redis URL در Production از environment/Vault boundary resolve می‌شود و در repository commit نمی‌شود.

## Crash / Recovery

- Queue lease expiration باعث redelivery می‌شود.
- `processing` stale قابل reclaim است.
- Worker به‌صورت دوره‌ای `pending + async` analysisهایی را که queue row ندارند reconcile می‌کند.
- بنابراین crash بین commit شدن Analysis و enqueue شدن Queue باعث pending دائمی نمی‌شود.
- enqueue idempotent است و unique `analysis_id` مانع duplicate durable jobs می‌شود.

## Repository Boundary

تمام SQL مربوط به Queue در `AnalysisQueueRepository` قرار دارد.
`PostgresAnalysisQueueProvider` دیگر `PsqlDbContext`، SQLAlchemy query یا SQLAlchemy model را مستقیماً استفاده نمی‌کند.

## Configuration

هر دو environment دارای section یکسان `analysis_queue` هستند:

- backend
- maximum_attempts
- retry_initial_delay_seconds
- retry_max_delay_seconds
- receive_timeout_seconds
- poll_interval_seconds
- visibility_timeout_seconds
- heartbeat_interval_seconds
- processing_stale_seconds
- recovery_interval_seconds
- recovery_batch_size
- concurrency
- transient_payload.backend
- transient_payload.ttl_seconds
- transient_payload.socket_timeout_seconds
- transient_payload.key_prefix

Validation مقادیر bool-as-number، NaN/Inf و rangeهای ناسازگار را fail-fast می‌کند.

## Worker entrypoint

```powershell
python -m src.host.worker
```

Worker فقط orchestration انجام می‌دهد و processing را به
`AnalysisProcessorService.process_claimed_async()` می‌سپارد.

## Migration

Migration جدید:

`20260929_0002_add_analysis_queue.py`

Table:

`analysis_queue_job`

Queue schema فقط orchestration metadata را نگهداری می‌کند.

## تست‌های اضافه‌شده

- queue job validation/privacy serialization.
- queue configuration validation.
- AnalysisService async enqueue + SOLDIER transient transport.
- worker retry/retry-exhaustion/duplicate completed delivery.
- PostgreSQL enqueue/receive/ack/requeue.
- concurrent queue consumption.
- atomic processing claim.
- processing input cleanup.
- orphan dispatch reconciliation after API crash.
- expired lease + stale-processing recovery.
- real Redis SOLDIER async privacy/integration test.
- repository boundary test preventing SQLAlchemy query usage inside Queue Provider.

## Commands to Run

```powershell
python -m pip install -r requirements.txt
python -m compileall -q src tests
docker compose up -d postgres redis
python -m src.infrastructure.scripts.run_migrations --upgrade
$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/word_cloud_test"
$env:TEST_TRANSIENT_PAYLOAD_REDIS_URL = "redis://127.0.0.1:6379/0"
python -m unittest tests.unit.core.services.analysis.test_analysis_queue_job -v
python -m unittest tests.unit.infrastructure.providers.test_analysis_queue_settings -v
python -m unittest tests.unit.core.services.analysis.test_analysis_worker_service -v
python -m unittest tests.integration.persistence.test_phase12_async_queue -v
python -m unittest tests.integration.persistence.test_phase12_soldier_async -v
python -m unittest discover -s tests -p "test_*.py" -v
```

## Expected Result

- compile بدون error.
- migration head تا `20260929_0002`.
- Queue integration tests با PostgreSQL PASS.
- فقط یک concurrent claim موفق.
- retry محدود و final failure deterministic.
- duplicate delivery result graph دوم تولید نکند.
- raw text در durable queue payload وجود نداشته باشد.
- SOLDIER async با Redis non-durable واقعی completed شود.
- Redis دارای RDB/AOF روشن توسط runtime رد شود.
- orphan pending analysis recover شود.
- expired lease + stale processing recover شود.
- Phaseهای 1 تا 11 regression نشکنند.

## Acceptance Checklist

- [x] concrete Queue Provider
- [x] Worker runtime
- [x] status lifecycle orchestration
- [x] retry/backoff
- [x] queue lease/heartbeat
- [x] atomic processing claim
- [x] duplicate-delivery protection
- [x] queue payload privacy boundary
- [x] privacy-safe SOLDIER async transient transport
- [x] Redis non-durability enforcement
- [x] orphan dispatch reconciliation
- [x] lease/stale-processing recovery
- [x] Queue SQL moved to Repository
- [x] config parity
- [x] Alembic model registration/migration
- [x] unit tests added
- [x] PostgreSQL integration/concurrency tests added
- [x] local compile/full-regression evidence after final Phase 12 fixes
- [x] real Redis + PostgreSQL Soldier async integration evidence from target development environment

## Verification Evidence

Local verification received on 2026-10-01:

- PostgreSQL container healthy on the development host.
- Redis non-durable transient container healthy.
- `python -m compileall -q src tests` completed without errors.
- Alembic upgrade completed successfully.
- Phase 12 PostgreSQL queue integration tests passed, including concurrent delivery, orphan recovery, lease expiry and stale-processing recovery.
- Phase 12 SOLDIER_CONCERN Redis/PostgreSQL integration tests passed, including durable-payload privacy and orphan-dispatch recovery.
- Full regression suite: `Ran 364 tests ... OK (skipped=7)`; skips are explicit environment/model-gated tests.

PHASE_12_COMPLETE_READY_FOR_PHASE_13
