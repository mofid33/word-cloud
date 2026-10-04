# Production Operations

This document describes the Phase 14 provider-neutral production runtime.

## Build

```bash
docker build -t word-cloud:local .
```

The default production image is CPU-oriented because the production baseline config uses `device.type=cpu`. PyTorch is installed first from the official CPU wheel index, preventing pip from resolving the CUDA-heavy PyPI distribution for this image. Dependency downloads use bounded retry/resume settings for large wheels.

For an approved GPU deployment, override `TORCH_INDEX_URL` and `TORCH_SPEC` at build time only after the target PyTorch/device combination has passed the project's semantic benchmark and regression gates.

The image runs as UID/GID 10001, does not bake secrets, disables the server banner, writes model cache under `/var/lib/word-cloud/models`, and records the exact resolved Python dependency set at `/opt/word-cloud/resolved-dependencies.txt`.

## Required runtime environment

Production uses `ENV_TYPE=production`. Supply secrets through the deployment environment or the existing Vault boundary:

- `DATABASE_URL`
- `TRANSIENT_PAYLOAD_REDIS_URL`

Optional production overrides:

- `ALLOWED_HOSTS` comma-separated, explicit hosts only
- `CORS_ALLOWED_ORIGINS` comma-separated origins
- `LOG_LEVEL`

Do not commit populated production env files.

## Production-like local stack

Copy `.env.production.example` to an untracked local file, replace example credentials, then pass that file explicitly to Compose:

```bash
cp .env.production.example .env.production.local
docker compose --env-file .env.production.local -f compose.production.yaml up -d --build
```

The production Compose API service passes `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, and `LOG_LEVEL` into the application runtime. An empty `CORS_ALLOWED_ORIGINS` keeps CORS disabled.

The `migrate` service runs Alembic once and must complete before API and Worker start. API replicas therefore do not race to run migrations.

Redis in this stack has RDB snapshots and AOF disabled. No volume is mounted for Redis because SOLDIER_CONCERN raw payloads must remain transient.

## Health

- `GET /api/v1/health/live`: process liveness only.
- `GET /api/v1/health/ready`: PostgreSQL + transient Redis readiness. No URLs, credentials, raw text, or exception messages are returned.
- Worker container health executes `python -m src.host.worker_health`. The probe is constant-time and checks that the Worker process (PID 1) is alive and that the API readiness endpoint is healthy. PostgreSQL + transient Redis readiness therefore remains centralized in the API health service instead of re-importing SQLAlchemy/Redis and rebuilding DI inside every Worker probe. The Worker host also exits if its processing task stops unexpectedly, so a live PID cannot mask a dead Worker loop.

## Metrics

`GET /api/v1/metrics/` exposes Prometheus text format when enabled. HTTP labels are bounded to method, route template and status. Analysis IDs, document IDs, keywords, topic text and raw input are not metric labels.

## Logging, tracing and correlation

Production logs are JSON with timestamp, severity and event name. HTTP logs include request ID, W3C trace ID/span ID, route template, status and duration. Analysis lifecycle events add safe `analysis_id`, profile and execution mode. Raw request bodies, Authorization headers, cookies, DB/Redis credentials and exception messages are not serialized.

HTTP middleware accepts a valid W3C `traceparent`, preserves its trace ID and sampling flags, creates a new server span ID, returns the resulting `traceparent` response header, and creates a fresh trace context when the incoming header is absent or invalid. The async queue intentionally keeps its identifier-only durable payload contract; `analysis_id` is the correlation boundary from HTTP analysis creation through queue and Worker.

## Security baseline

Production disables FastAPI docs/OpenAPI, validates allowed hosts, supports explicit CORS origins, enforces configured request body size and request timeout, sanitizes unhandled errors, adds no-sniff/frame/referrer/cache headers, keeps `trust_remote_code=false`, and disables remote model downloads.

Authentication is intentionally not introduced because the project contract does not define an authentication scheme.

## Resource limits

Production Compose applies explicit, overridable ceilings to both API and Worker containers:

- CPU: `API_CPU_LIMIT` / `WORKER_CPU_LIMIT` (default `4.0`);
- memory: `API_MEMORY_LIMIT` / `WORKER_MEMORY_LIMIT` (default `6g`);
- PID count: `API_PIDS_LIMIT` / `WORKER_PIDS_LIMIT` (default `512`).

These are ceilings, not reservations. Tune them only after target-machine measurement and semantic-model memory verification. CI inspects the created containers and fails if CPU, memory or PID limits are absent.

## Models

Production config uses `models.allow_remote_downloads=false`. Provision model files into the mounted model cache before analyses requiring semantic models. Embedding/reranker providers remain lazy singletons and are not loaded per request. GPU selection remains configuration-driven.

## Shutdown

API lifespan closes Redis and the SQLAlchemy engine. Worker handles SIGINT/SIGTERM, stops consumers, observes the configured 30-second internal graceful shutdown timeout, cancels consumers only after that timeout, closes the queue transport even on cancellation, and disposes the DB pool. Production Compose grants API and Worker a 60-second external stop grace period so application cleanup has bounded headroom after the internal timeout. CI requires both containers to finish with exit code 0 and without OOM termination; a successful container stop command alone is not considered graceful-shutdown evidence.

## Release

The release workflow builds one production image, exports it as a tar artifact, and publishes a SHA256 file. No cloud/Kubernetes destination is assumed. The exported image is the immutable deployment artifact; its embedded `resolved-dependencies.txt` captures the exact installed Python dependency set.

## Troubleshooting

- readiness 503 with `postgres=false`: verify DB URL, migration completion and network reachability.
- readiness 503 with `redis_transient=false`: verify Redis URL and that both snapshot persistence and AOF are disabled.
- production startup fails before serving: check required configuration/secrets and host/security settings.
- semantic analysis fails with local model load error: provision the configured model/revision into the model cache or explicitly change the deployment policy; production remote download is disabled by design.
- Docker dependency install fails on PyTorch: confirm outbound access to the configured PyTorch wheel index. The default image intentionally uses the official CPU wheel index; do not switch to a CUDA wheel index unless that deployment target has been benchmarked and approved.

## Target-machine performance baseline

With the production-like stack healthy, run the Phase 14 HTTP benchmark from the project virtual environment:

```bash
RUN_PHASE14_RUNTIME_BENCHMARK=1 PHASE14_BASE_URL=http://127.0.0.1:5000 python -m unittest tests.evaluation.test_phase14_runtime_performance -v
```

On PowerShell set the environment variables first. The benchmark records P50/P95 latency and throughput for liveness plus the analysis validation path, and requires one-shot Docker CPU/memory statistics for both API and Worker. By default it discovers the running Compose containers through Docker Compose service labels. If multiple Compose projects with the same service names are running, set `PHASE14_COMPOSE_PROJECT` or explicit `PHASE14_API_CONTAINER` / `PHASE14_WORKER_CONTAINER` values. The test fails instead of silently emitting null resource statistics when the containers cannot be resolved. It does not invent an SLA; the emitted JSON is target-machine baseline evidence to be compared across releases. CPU is the default production image, so VRAM is reported as null.
