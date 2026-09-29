# Phase 12 — Async Jobs & Workers

Status: IMPLEMENTED_AWAITING_LOCAL_VERIFICATION_AND_PRIVACY_TRANSPORT_DECISION
Date: 2026-09-29
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

- PostgreSQL-backed durable queue؛ dependency جدید خارجی اضافه نشده است.
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

## Privacy blocker — SOLDIER_CONCERN

Frozen contract هم‌زمان این دو شرط را دارد:

1. Worker برای تحلیل به raw text نیاز دارد.
2. SOLDIER_CONCERN raw text نه در DB و نه در durable queue payload قابل ذخیره نیست.

در baseline هیچ privacy-safe transient transport contractشده‌ای برای انتقال raw text از HTTP process به Worker وجود ندارد. ساخت storage یا fake ephemeral provider جدید فقط برای سبز کردن Phase ممنوع است.

بنابراین مسیر SOLDIER_CONCERN که به async resolve شود با کد
`soldier_async_transport_unavailable` به‌صورت fail-closed رد می‌شود. هیچ lifecycle row، durable queue payload یا persisted raw text برای این request ساخته نمی‌شود.

به همین دلیل Phase 12 تا زمانی که یک transport privacy-safe واقعی و contractشده تعیین و پیاده‌سازی نشود، `CLOSED` اعلام نمی‌شود.

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
- concurrency

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
- AnalysisService async enqueue + SOLDIER fail-closed.
- worker retry/retry-exhaustion/duplicate completed delivery.
- PostgreSQL enqueue/receive/ack/requeue.
- concurrent queue consumption.
- atomic processing claim.
- processing input cleanup.

## Commands to Run

```powershell
python -m compileall -q src tests
python -m src.infrastructure.scripts.run_migrations --upgrade
$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/word_cloud_test"
python -m unittest tests.unit.core.services.analysis.test_analysis_queue_job -v
python -m unittest tests.unit.infrastructure.providers.test_analysis_queue_settings -v
python -m unittest tests.unit.core.services.analysis.test_analysis_worker_service -v
python -m unittest tests.integration.persistence.test_phase12_async_queue -v
python -m unittest discover -s tests -p "test_*.py" -v
```

## Expected Result

- compile بدون error.
- migration head تا `20260929_0002`.
- Queue integration tests با PostgreSQL PASS.
- فقط یک concurrent claim موفق.
- retry محدود و final failure deterministic.
- duplicate delivery result graph دوم تولید نکند.
- raw text در queue payload وجود نداشته باشد.
- SOLDIER async بدون transport امن fail-closed باشد.
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
- [x] config parity
- [x] Alembic model registration/migration
- [x] unit tests added
- [x] PostgreSQL integration/concurrency tests added
- [ ] local compile/full-regression evidence from target development environment
- [ ] privacy-safe SOLDIER async transport contract + implementation

Phase closure marker remains intentionally unset.
