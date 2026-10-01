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

Copy `.env.production.example` to an untracked local file, replace example credentials, then export/load those variables before running:

```bash
docker compose -f compose.production.yaml up -d --build
```

The `migrate` service runs Alembic once and must complete before API and Worker start. API replicas therefore do not race to run migrations.

Redis in this stack has RDB snapshots and AOF disabled. No volume is mounted for Redis because SOLDIER_CONCERN raw payloads must remain transient.

## Health

- `GET /api/v1/health/live`: process liveness only.
- `GET /api/v1/health/ready`: PostgreSQL + transient Redis readiness. No URLs, credentials, raw text, or exception messages are returned.
- Worker container health executes `python -m src.host.worker_health`.

## Metrics

`GET /api/v1/metrics/` exposes Prometheus text format when enabled. HTTP labels are bounded to method, route template and status. Analysis IDs, document IDs, keywords, topic text and raw input are not metric labels.

## Logging and correlation

Production logs are JSON with timestamp, severity and event name. HTTP logs include request ID, route template, status and duration. Analysis lifecycle events add safe `analysis_id`, profile and execution mode. Raw request bodies, Authorization headers, cookies, DB/Redis credentials and exception messages are not serialized.

HTTP request ID + analysis ID + the existing queue analysis ID provide correlation from request -> analysis -> queue -> worker without changing the queue payload contract.

## Security baseline

Production disables FastAPI docs/OpenAPI, validates allowed hosts, supports explicit CORS origins, enforces configured request body size and request timeout, sanitizes unhandled errors, adds no-sniff/frame/referrer/cache headers, keeps `trust_remote_code=false`, and disables remote model downloads.

Authentication is intentionally not introduced because the project contract does not define an authentication scheme.

## Models

Production config uses `models.allow_remote_downloads=false`. Provision model files into the mounted model cache before analyses requiring semantic models. Embedding/reranker providers remain lazy singletons and are not loaded per request. GPU selection remains configuration-driven.

## Shutdown

API lifespan closes Redis and the SQLAlchemy engine. Worker handles SIGINT/SIGTERM, stops consumers, observes the configured graceful shutdown timeout, cancels only after timeout, closes the queue transport and disposes the DB pool.

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
RUN_PHASE14_RUNTIME_BENCHMARK=1 PHASE14_BASE_URL=http://127.0.0.1:5001 python -m unittest tests.evaluation.test_phase14_runtime_performance -v
```

On PowerShell set the environment variables first. The benchmark records P50/P95 latency and throughput for liveness plus the analysis validation path, and captures one-shot Docker CPU/memory statistics for API and Worker. It does not invent an SLA; the emitted JSON is target-machine baseline evidence to be compared across releases. CPU is the default production image, so VRAM is reported as null.
