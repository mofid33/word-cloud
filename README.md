# Persian Semantic Text Analytics Service

A production-oriented backend for Persian text analysis. The service produces persisted **structured JSON** as its primary output and derives **PNG/SVG Persian WordCloud visualizations** from final ranked scores.

This project is not a frequency-only WordCloud generator. Its implemented analysis pipeline is:

**Persian Preprocessing → Candidate Extraction → Statistical Analysis → Semantic Ranking → Re-ranking → Deduplication / Diversity → Topic & Trend Analysis → Structured JSON → WordCloud**

> Repository status: Phase 14 is marked <code>COMPLETE — PRODUCTION_READY</code> in the tracked production-readiness record dated 2026-10-04. The current production image is CPU-oriented by default; GPU execution remains configuration-driven and must be benchmarked on the target deployment.

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Analysis Profiles](#analysis-profiles)
- [Architecture](#architecture)
- [Processing Pipeline](#processing-pipeline)
- [Repository Structure](#repository-structure)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Docker Development](#docker-development)
- [Production-like Docker Stack](#production-like-docker-stack)
- [Configuration](#configuration)
- [API Usage](#api-usage)
- [Real Analysis Example](#real-analysis-example)
- [Structured Result](#structured-result)
- [Visualization](#visualization)
- [Sync vs Async](#sync-vs-async)
- [Persistence](#persistence)
- [Privacy & Security](#privacy--security)
- [Observability](#observability)
- [Models & Device Configuration](#models--device-configuration)
- [Testing](#testing)
- [Evaluation](#evaluation)
- [Database Migrations](#database-migrations)
- [CI/CD](#cicd)
- [Performance](#performance)
- [Production Deployment Notes](#production-deployment-notes)
- [Known Limitations](#known-limitations)
- [Project Status](#project-status)
- [Documentation](#documentation)
- [License](#license)

## Overview

Persian Semantic Text Analytics Service accepts Persian documents plus metadata and performs normalization, candidate/keyphrase extraction, statistical scoring, embedding-based semantic analysis, cross-encoder reranking, hybrid score fusion, deduplication/diversification, topic analysis, and profile-specific analysis.

The canonical public result is JSON with these top-level sections:

- <code>analysis</code>
- <code>keywords</code>
- <code>topics</code>
- <code>metrics</code>
- <code>profile_result</code>

WordCloud output is a derived visualization. Overall WordCloud weights use persisted keyword <code>final_score</code>; topic WordCloud weights use persisted topic-keyword <code>relevance_score</code>.

Typical uses include long-course/document analysis, multi-document concern analysis with stricter raw-text privacy, and published-content versus audience-feedback analysis.

## Key Features

- Persian normalization, tokenization, stopword/domain resource handling, ZWNJ and whitespace normalization.
- 1–3 gram candidate extraction with configurable phrase filtering.
- Frequency, document coverage, section/chunk coverage and phrase-quality signals.
- Configurable bi-encoder embeddings and cross-encoder reranking.
- Hybrid statistical/semantic fusion with lexical, canonical and semantic deduplication plus diversity ranking.
- Topic extraction, representative keyphrases, prevalence and coverage.
- COURSE topic timeline.
- MEDIA role-aware topic analysis, trend states and Content–Audience Gap.
- Persisted structured results with model/scoring version metadata.
- Sync and queued async execution.
- PostgreSQL-backed durable queue plus Redis transient transport for SOLDIER_CONCERN raw payloads.
- Persian/RTL WordCloud rendering to PNG and SVG.
- Liveness, dependency readiness and Worker health checks.
- Prometheus metrics, structured JSON logs, request correlation and W3C <code>traceparent</code>.
- Non-root production container, resource ceilings, migration-before-runtime Compose flow.
- GitHub Actions for compile, migrations, unit/integration/evaluation regression and production-like container smoke.
- Provider-neutral release image packaging.

## Analysis Profiles

### COURSE

Designed for long documents, sections, chapters or course material. Documents may include consistent <code>metadata.section_id</code> and/or <code>metadata.chunk_id</code>. If either key is supplied, it must be supplied consistently for all COURSE documents.

Implemented signals include semantic relevance, frequency, chunk coverage, section coverage and phrase quality. The profile produces ranked keyphrases, topics and a request-order topic timeline.

### SOLDIER_CONCERN

Each concern is treated as an independent document; concerns are not merged into one corpus document. The profile uses cross-document signals including document frequency, document coverage, semantic relevance and topic prevalence, with semantic topic clustering and representative keyphrases.

Privacy is enforced in the execution architecture:

- raw concern text is not intentionally written to application logs, metric labels or trace attributes;
- raw concern text is not persisted to the durable analysis database;
- the durable PostgreSQL queue stores an identifier-only analysis job, not the raw SOLDIER payload;
- async SOLDIER raw documents are stored temporarily in Redis with TTL;
- the Redis transport validates at runtime that RDB snapshot persistence is disabled and <code>appendonly=no</code>;
- the production Compose stack mounts no Redis volume;
- the request cannot disable this privacy behavior.

### MEDIA

MEDIA requires every document to declare <code>metadata.role</code> as either <code>published_content</code> or <code>audience_feedback</code>. If <code>metadata.published_at</code> is used within one role corpus, it must be supplied consistently for that role and include an ISO-8601 timezone offset.

The profile analyzes published content and audience feedback as separate corpora before combined analysis. Implemented outputs include topics, mention/coverage signals, semantic relevance, trend information, emerging/stable/declining states where trend data is available, and Content–Audience Gap.

**Scraping and content acquisition are outside this repository's scope.** Input is already-acquired <code>Document + Metadata</code>.

## Architecture

The project follows the repository's lightweight layered architecture:

~~~text
Host → Application → Core → Infrastructure
~~~

The standard persistence call path is:

~~~text
Controller → Service → Repository → PsqlDbContext → PostgreSQL
~~~

~~~mermaid
flowchart TD
    H[Host<br/>bootstrap / API / Worker] --> A[Application<br/>Controllers + DTOs]
    A --> C[Core<br/>Workflow + Analytics Services]
    C --> R[Infrastructure Repositories]
    R --> DB[PsqlDbContext / PostgreSQL]
    C --> P[Replaceable Providers]
    P --> E[Embedding / Reranker / Topic Model]
    C --> Q[AnalysisQueueProvider]
    Q --> PQ[(PostgreSQL durable queue)]
    Q --> TR[(Non-durable Redis<br/>SOLDIER transient payload only)]
~~~

Architecture rules implemented by the codebase:

- constructor dependency injection;
- <code>@inject</code> provider/controller discovery;
- thin Controllers for HTTP/DTO/status/error mapping;
- business/workflow logic in Core services;
- SQLAlchemy persistence/query logic in Repositories;
- shared CRUD through <code>BaseRepository</code>;
- SQLAlchemy models in Infrastructure;
- Alembic migrations with explicit model visibility;
- Config/Vault boundaries for settings and secrets;
- no duplicate Worker business logic: Worker calls the same <code>AnalysisProcessorService</code> used by sync execution.

The project intentionally does not introduce DDD/CQRS/Hexagonal/UseCase layers that are not part of its architecture.

## Processing Pipeline

~~~mermaid
flowchart LR
    D[Persian Documents] --> N[Persian Preprocessing]
    N --> C[1-3 gram Candidates]
    C --> S[Statistical Analysis]
    S --> B[Bi-Encoder Semantic Relevance]
    B --> T[Top-N]
    T --> X[Cross-Encoder Reranker]
    X --> H[Hybrid Ranking]
    H --> DD[Deduplication + Diversity]
    DD --> TP[Topic / Trend Analysis]
    TP --> J[Persisted Structured JSON]
    J --> W[PNG / SVG WordCloud]
~~~

The semantic path is implemented around the intended:

~~~text
Candidates → Bi-Encoder → Top-N → Cross-Encoder → Hybrid Ranking
~~~

Semantic providers are lazy/singleton-style infrastructure providers rather than per-request model loaders.

## Repository Structure

~~~text
.
├── src/
│   ├── host/                       # FastAPI and Worker bootstraps, runtime YAML
│   ├── application/
│   │   ├── analysis/               # Analysis Controller + DTOs
│   │   ├── visualization/          # PNG/SVG HTTP endpoints
│   │   ├── health/                 # live/ready endpoints
│   │   └── metrics/                # Prometheus endpoint
│   ├── core/
│   │   └── services/               # Analysis orchestration + NLP/ranking/topic/profile logic
│   └── infrastructure/
│       ├── context/                # PostgreSQL + Vault boundaries
│       ├── di/                     # @inject, reflection, bootstrap
│       ├── models/                 # SQLAlchemy persistence models
│       ├── repositories/           # BaseRepository + feature repositories
│       ├── providers/              # semantic/topic/queue/visualization/runtime providers
│       ├── observability/          # logging, tracing, Prometheus metrics
│       ├── alembic/                # schema migrations
│       └── scripts/                # migration runner
├── tests/
│   ├── unit/
│   ├── integration/
│   └── evaluation/
├── docs/
│   ├── architecture/
│   ├── requirements/
│   ├── analytics/
│   └── operations/
├── docker/postgres/init/
├── .github/workflows/
├── Dockerfile
├── compose.yaml
├── compose.production.yaml
├── requirements.txt
└── requirements-dev.txt
~~~

## Requirements

### Local Python execution

- Python 3.12 (CI uses 3.12; production image is <code>python:3.12.8-slim-bookworm</code>)
- PostgreSQL 16-compatible server
- Redis 7-compatible server configured as non-durable for transient SOLDIER payloads
- Python build/runtime prerequisites required by the dependencies

### Container execution

- Docker
- Docker Compose v2

The default production image installs CPU PyTorch wheels. GPU is a separate deployment configuration decision; see [Models & Device Configuration](#models--device-configuration).

## Quick Start

### Windows PowerShell

~~~powershell
git clone https://github.com/Amirmahdimtz/Word_Cloud.git
cd Word_Cloud

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

Copy-Item .env.example .env

docker compose up -d postgres redis

python -m src.infrastructure.scripts.run_migrations --upgrade

python -m uvicorn src.host.app:app --host 0.0.0.0 --port 5000
~~~

For async analyses, run the Worker in another activated PowerShell session:

~~~powershell
python -m src.host.worker
~~~

### Linux / macOS

~~~bash
git clone https://github.com/Amirmahdimtz/Word_Cloud.git
cd Word_Cloud

python3.12 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

cp .env.example .env

docker compose up -d postgres redis

python -m src.infrastructure.scripts.run_migrations --upgrade

python -m uvicorn src.host.app:app --host 0.0.0.0 --port 5000
~~~

In another shell for async execution:

~~~bash
source .venv/bin/activate
python -m src.host.worker
~~~

The copied <code>.env</code> file is consumed automatically by Docker Compose. The Python API, Worker and migration runner do not load dotenv files themselves; they read the selected YAML configuration plus actual process environment variables. The checked-in development YAML matches the default local Compose PostgreSQL/Redis settings. If you change runtime URLs for Python processes, export <code>DATABASE_URL</code> and/or <code>TRANSIENT_PAYLOAD_REDIS_URL</code> in the shell before starting migrations, API or Worker.

Development configuration enables FastAPI docs at <code>http://127.0.0.1:5000/docs</code>.

## Docker Development

<code>compose.yaml</code> starts infrastructure dependencies only:

- PostgreSQL 16 Alpine with a named data volume;
- Redis 7 Alpine bound to loopback;
- Redis RDB snapshots disabled;
- Redis AOF disabled;
- Redis has no persistence volume.

~~~bash
docker compose up -d postgres redis
docker compose ps
docker compose logs -f postgres redis
docker compose down
~~~

## Production-like Docker Stack

<code>compose.production.yaml</code> defines:

- PostgreSQL;
- non-durable Redis;
- one-shot Alembic migration service;
- API container;
- Worker container;
- model-cache volume;
- API/Worker CPU, memory and PID ceilings;
- startup dependencies and health checks.

Create an untracked production-like env file from the example and replace example credentials:

~~~bash
cp .env.production.example .env.production.local

docker compose --env-file .env.production.local -f compose.production.yaml up -d --build
docker compose --env-file .env.production.local -f compose.production.yaml ps
docker compose --env-file .env.production.local -f compose.production.yaml logs -f api worker

curl --fail http://127.0.0.1:5000/api/v1/health/live
curl --fail http://127.0.0.1:5000/api/v1/health/ready

docker compose --env-file .env.production.local -f compose.production.yaml down
~~~

The migration container must complete successfully before API and Worker start.

## Configuration

Application configuration is YAML-based. <code>ENV_TYPE=development</code> selects <code>src/host/res/appsettings.development.yaml</code>; every other environment selects <code>src/host/res/appsettings.yaml</code>. Selected production values can be overridden by environment variables.

### Runtime / Compose variables

| Variable | Required | Environment | Description | Example |
|---|---:|---|---|---|
| <code>ENV_TYPE</code> | Yes for explicit deployment | all | Selects development vs non-development config | <code>production</code> |
| <code>DATABASE_URL</code> | Production: yes unless Vault boundary supplies it | runtime | Async SQLAlchemy PostgreSQL URL | <code>postgresql+asyncpg://user:***@postgres:5432/db</code> |
| <code>TRANSIENT_PAYLOAD_REDIS_URL</code> | Production: yes unless Vault boundary supplies it | runtime | Redis URL for transient analysis payloads | <code>redis://redis:6379/0</code> |
| <code>VAULT_DATABASE_URL</code> | Conditional | Vault-enabled runtime | Environment-backed VaultService secret for DB URL | secret value, not committed |
| <code>VAULT_TRANSIENT_PAYLOAD_REDIS_URL</code> | Conditional | Vault-enabled runtime | Environment-backed VaultService secret for transient Redis | secret value, not committed |
| <code>ALLOWED_HOSTS</code> | Optional override | production | Comma-separated TrustedHost values; wildcard rejected outside development | <code>service.example.com,localhost</code> |
| <code>CORS_ALLOWED_ORIGINS</code> | Optional override | production | Comma-separated explicit CORS origins; empty keeps CORS disabled and wildcard is rejected outside development | <code>https://app.example.com</code> |
| <code>LOG_LEVEL</code> | Optional | runtime | Logging level override | <code>INFO</code> |
| <code>POSTGRES_USER</code> | Compose | local/prod-like | PostgreSQL user | <code>postgres</code> |
| <code>POSTGRES_PASSWORD</code> | Prod-like: yes | Compose | PostgreSQL password | use an untracked secret |
| <code>POSTGRES_DB</code> | Compose | local/prod-like | PostgreSQL database | <code>postgres</code> |
| <code>POSTGRES_PORT</code> | Optional | dev Compose | Host PostgreSQL port | <code>5432</code> |
| <code>TRANSIENT_PAYLOAD_PORT</code> | Optional | dev Compose | Host Redis port, bound to 127.0.0.1 | <code>6379</code> |
| <code>API_PORT</code> | Optional | prod-like Compose | Host API port | <code>5000</code> |
| <code>IMAGE_TAG</code> | Optional | prod-like Compose | Image tag used by API/Worker/migrate | <code>local</code> |
| <code>API_CPU_LIMIT</code> | Optional | prod-like Compose | API CPU ceiling | <code>4.0</code> |
| <code>API_MEMORY_LIMIT</code> | Optional | prod-like Compose | API memory ceiling | <code>6g</code> |
| <code>API_PIDS_LIMIT</code> | Optional | prod-like Compose | API PID ceiling | <code>512</code> |
| <code>WORKER_CPU_LIMIT</code> | Optional | prod-like Compose | Worker CPU ceiling | <code>4.0</code> |
| <code>WORKER_MEMORY_LIMIT</code> | Optional | prod-like Compose | Worker memory ceiling | <code>6g</code> |
| <code>WORKER_PIDS_LIMIT</code> | Optional | prod-like Compose | Worker PID ceiling | <code>512</code> |
| <code>WORKER_READINESS_URL</code> | Optional | Worker | Worker health probe API readiness URL | <code>http://api:5000/api/v1/health/ready</code> |
| <code>TEST_DATABASE_URL</code> | Tests only | integration | Integration database URL | local test DB |
| <code>TEST_TRANSIENT_PAYLOAD_REDIS_URL</code> | Tests only | integration | Integration Redis URL | local non-durable Redis |

### Evaluation / benchmark gates

| Variable | Purpose |
|---|---|
| <code>RUN_SEMANTIC_MODEL_BENCHMARK=1</code> | Enables gated real semantic model benchmark suites where implemented |
| <code>RUN_PHASE11_REAL_MODEL_BENCHMARK=1</code> | Enables the real configured embedding/topic performance test |
| <code>RUN_PHASE14_RUNTIME_BENCHMARK=1</code> | Enables the production-like HTTP/container performance baseline |
| <code>PHASE14_BASE_URL</code> | Base URL used by the Phase 14 runtime benchmark |
| <code>PHASE10_GOLD_COURSE_DIR</code> | External/approved COURSE gold data location |
| <code>PHASE10_GOLD_SOLDIER_DIR</code> | Private external SOLDIER gold data location; raw concerns must not be committed |
| <code>PHASE10_GOLD_MEDIA_DIR</code> | External/approved MEDIA gold data location |

Model identifiers, device selection, batch sizes, ranking weights, topic/trend settings and analysis thresholds are currently stored in the YAML runtime configuration rather than environment variables.

## API Usage

Base prefix: <code>/api/v1</code>.

| Method | Path | Purpose |
|---|---|---|
| POST | <code>/api/v1/analysis/validate</code> | Validate input limits/profile contract and resolve <code>auto</code> to sync/async |
| POST | <code>/api/v1/analysis</code> | Create and execute/enqueue an analysis |
| GET | <code>/api/v1/analysis/{analysis_id}</code> | Read lifecycle status |
| GET | <code>/api/v1/analysis/{analysis_id}/result</code> | Read completed persisted structured result |
| GET | <code>/api/v1/visualization/{analysis_id}?format=png|svg</code> | Render overall WordCloud |
| GET | <code>/api/v1/visualization/{analysis_id}/topics/{topic_id}?format=png|svg</code> | Render topic WordCloud |
| GET | <code>/api/v1/health/live</code> | Process liveness |
| GET | <code>/api/v1/health/ready</code> | PostgreSQL + transient Redis readiness |
| GET | <code>/api/v1/metrics/</code> | Prometheus text metrics when enabled |

Production disables FastAPI docs and OpenAPI. Development enables <code>/docs</code> and <code>/openapi.json</code>.

## Real Analysis Example

The request below is valid for the implemented COURSE contract and exercises section/chunk-aware processing:

~~~json
{
  "analysis_type": "COURSE",
  "execution_mode": "auto",
  "reference": "readme-course-example",
  "documents": [
    {
      "document_id": "section-1",
      "text": "یادگیری ماشین به سیستم‌ها کمک می‌کند الگوهای موجود در داده را شناسایی کنند و از داده برای پیش‌بینی استفاده کنند.",
      "metadata": {
        "section_id": "s1",
        "chunk_id": "c1"
      }
    },
    {
      "document_id": "section-2",
      "text": "مدل‌های زبانی و بردارهای معنایی برای سنجش شباهت متن و بازیابی مفاهیم مرتبط استفاده می‌شوند.",
      "metadata": {
        "section_id": "s2",
        "chunk_id": "c2"
      }
    },
    {
      "document_id": "section-3",
      "text": "ارزیابی مدل باید با داده فارسی، معیارهای رتبه‌بندی و آزمون‌های بازگشت انجام شود.",
      "metadata": {
        "section_id": "s3",
        "chunk_id": "c3"
      }
    }
  ],
  "options": {}
}
~~~

Validate it first:

~~~bash
curl -sS -X POST http://127.0.0.1:5000/api/v1/analysis/validate \
  -H "Content-Type: application/json" \
  --data @request.json
~~~

A successful validation has this schema:

~~~json
{
  "valid": true,
  "analysis_type": "COURSE",
  "execution_mode": "auto",
  "resolved_execution_mode": "sync",
  "document_count": 3,
  "total_characters": 318
}
~~~

The exact <code>total_characters</code> value depends on the exact request text. Do not copy that illustrative number as an assertion in tests.

Create the analysis:

~~~bash
curl -sS -X POST http://127.0.0.1:5000/api/v1/analysis \
  -H "Content-Type: application/json" \
  --data @request.json
~~~

The response is an analysis status resource containing:

~~~json
{
  "analysis_id": "generated-uuid",
  "analysis_type": "COURSE",
  "status": "completed",
  "execution_mode": "sync",
  "reference": "readme-course-example",
  "model_version": "configured-provider-version",
  "scoring_version": "configured-scoring-version",
  "created_at": "ISO-8601 timestamp",
  "started_at": "ISO-8601 timestamp",
  "completed_at": "ISO-8601 timestamp",
  "error": null
}
~~~

For <code>auto</code>, the status may instead be <code>pending</code> with <code>execution_mode="async"</code> when the configured sync threshold is exceeded.

Poll async work:

~~~bash
curl -sS http://127.0.0.1:5000/api/v1/analysis/ANALYSIS_ID
~~~

Fetch the final result after status becomes <code>completed</code>:

~~~bash
curl -sS http://127.0.0.1:5000/api/v1/analysis/ANALYSIS_ID/result
~~~

Async lifecycle:

~~~text
POST Analysis → analysis_id → GET Status → GET Result
~~~

## Structured Result

The public result DTO exposes persisted final output. The following is a schema-faithful abbreviated example; values are illustrative:

~~~json
{
  "analysis": {
    "analysis_id": "generated-uuid",
    "analysis_type": "COURSE",
    "status": "completed",
    "execution_mode": "sync",
    "reference": "readme-course-example",
    "model_version": "embedding:...;reranker:...;topic:...",
    "scoring_version": "...",
    "created_at": "2026-10-04T12:00:00Z",
    "started_at": "2026-10-04T12:00:00Z",
    "completed_at": "2026-10-04T12:00:03Z",
    "error": null
  },
  "keywords": [
    {
      "text": "یادگیری ماشین",
      "canonical_text": "یادگیری ماشین",
      "rank": 1,
      "final_score": 0.91,
      "statistical_score": 0.78,
      "semantic_score": 0.94,
      "coverage": 0.67,
      "frequency": 2
    }
  ],
  "topics": [
    {
      "topic_id": "topic-identifier",
      "label": "یادگیری ماشین",
      "rank": 1,
      "prevalence": 0.67,
      "coverage": 0.67,
      "keywords": [
        {
          "text": "یادگیری ماشین",
          "canonical_text": "یادگیری ماشین",
          "rank": 1,
          "relevance_score": 0.93
        }
      ]
    }
  ],
  "metrics": {
    "document_count": 3
  },
  "profile_result": {
    "profile": "COURSE"
  }
}
~~~

The public result does **not** expose the complete internal candidate trace, rejected candidates, raw embedding vectors, or full internal reranking trace. It exposes final persisted keywords/topics plus profile-specific structured metadata.

## Visualization

Overall PNG:

~~~bash
curl --fail \
  "http://127.0.0.1:5000/api/v1/visualization/ANALYSIS_ID?format=png" \
  --output wordcloud.png
~~~

Overall SVG:

~~~bash
curl --fail \
  "http://127.0.0.1:5000/api/v1/visualization/ANALYSIS_ID?format=svg" \
  --output wordcloud.svg
~~~

Topic PNG:

~~~bash
curl --fail \
  "http://127.0.0.1:5000/api/v1/visualization/ANALYSIS_ID/topics/TOPIC_ID?format=png" \
  --output topic-wordcloud.png
~~~

The renderer supports Persian shaping/RTL display using the configured font and shaping libraries. Rendering concurrency, dimensions, maximum words, font and deterministic seed are configuration-driven.

## Sync vs Async

Current configured hard input limits:

- maximum documents per analysis: <code>5000</code>
- maximum characters per document: <code>500000</code>
- maximum total characters per analysis: <code>10000000</code>

Current sync threshold:

- documents ≤ <code>20</code>
- total characters ≤ <code>100000</code>

<code>execution_mode="auto"</code> chooses sync only when **both** sync conditions are satisfied; otherwise it chooses async. Explicit <code>sync</code> above the threshold is rejected.

Async flow:

~~~mermaid
flowchart LR
    API[FastAPI Create Analysis] --> DB[(Pending analysis)]
    DB --> Q[AnalysisQueueProvider]
    Q --> W[Worker]
    W --> P[AnalysisProcessorService]
    P --> PR[Profile/Core Services]
    PR --> R[Repository]
    R --> OUT[(Persisted Result)]
~~~

The durable queue backend is PostgreSQL. For SOLDIER_CONCERN async requests, raw text is carried separately through verified non-durable Redis and is not placed in the durable queue payload.

## Persistence

Primary persisted entities:

- <code>WordCloudAnalysis</code>
- <code>AnalysisDocument</code>
- <code>AnalysisKeyword</code>
- <code>AnalysisTopic</code>
- <code>AnalysisTopicKeyword</code>

The async implementation also has a queue job persistence model.

Persistence supports history, reproducibility, trend processing, model-version tracking and scoring-version tracking. Aggregate result persistence is handled by Repository code against PostgreSQL rather than by Controllers.

## Privacy & Security

Implemented production controls include:

- SOLDIER raw-text durable persistence prohibition.
- Non-durable Redis enforcement for SOLDIER transient async payloads.
- Structured logs containing bounded operational fields rather than request bodies.
- Prometheus labels limited to HTTP method, route template and status.
- No raw text in trace attributes.
- Production FastAPI docs/OpenAPI disabled.
- Request body limit: currently 12,000,000 bytes.
- Request timeout: currently 300 seconds.
- TrustedHost middleware.
- Explicit CORS allow-list support; wildcard origins rejected outside development.
- Security response headers:
  - <code>X-Content-Type-Options: nosniff</code>
  - <code>X-Frame-Options: DENY</code>
  - <code>Referrer-Policy: no-referrer</code>
  - <code>Cache-Control: no-store</code>
- Sanitized generic 500 responses.
- Non-root production process (UID/GID 10001).
- Production model remote downloads disabled.
- <code>models.trust_remote_code=false</code> is enforced by semantic provider configuration.
- No credentials baked into the Docker image.

Authentication is **not** implemented because the current project contract does not define an authentication scheme. Network/deployment-layer access control is therefore an external deployment responsibility.

## Observability

### Logging

Logs are JSON and include fields such as timestamp, severity and event. Correlation fields can include:

- <code>request_id</code>
- <code>trace_id</code>
- <code>span_id</code>
- <code>analysis_id</code>
- profile
- execution mode
- route/status/duration
- sanitized error code

### Tracing

The HTTP middleware accepts W3C <code>traceparent</code>. For a valid incoming header it preserves the trace ID and sampling flags and creates a new server span ID. Invalid/missing input creates a fresh trace context. The response includes <code>traceparent</code>.

The queue contract stays identifier-oriented; <code>analysis_id</code> is the async correlation boundary.

### Metrics

~~~bash
curl -sS http://127.0.0.1:5000/api/v1/metrics/
~~~

Current metrics include HTTP request counters, request-duration histogram and readiness gauge.

### Health

~~~bash
curl -sS http://127.0.0.1:5000/api/v1/health/live
curl -sS http://127.0.0.1:5000/api/v1/health/ready
python -m src.host.worker_health
~~~

Readiness checks PostgreSQL plus transient Redis. Worker health verifies PID 1 plus API readiness and the Worker host exits if its processing loop stops unexpectedly.

## Models & Device Configuration

Current configured semantic models:

- embedding: <code>sentence-transformers/paraphrase-multilingual-mpnet-base-v2</code>
- reranker: <code>BAAI/bge-reranker-v2-m3</code>

Important runtime policy:

- development allows remote model download and uses <code>.cache/models</code>;
- production disables remote downloads and expects models to be provisioned in <code>/var/lib/word-cloud/models</code>;
- <code>trust_remote_code</code> must remain false;
- production defaults to <code>device.type=cpu</code>;
- <code>device.type=cuda</code> with a configured CUDA device index is supported by provider configuration;
- the default Dockerfile installs CPU PyTorch wheels.

This repository does **not** claim a separately verified GPU production image. A GPU deployment should only be used after the selected PyTorch build, model cache, device and semantic/evaluation benchmarks pass on that target.

## Testing

Test layout:

~~~text
tests/
├── unit/
├── integration/
└── evaluation/
~~~

Compile:

~~~bash
python -m compileall -q src tests
~~~

Unit:

~~~bash
python -m unittest discover -s tests/unit -p "test_*.py" -v
~~~

Integration:

~~~bash
python -m unittest discover -s tests/integration -p "test_*.py" -v
~~~

Evaluation/regression:

~~~bash
python -m unittest discover -s tests/evaluation -p "test_*.py" -v
~~~

Equivalent full local regression gate:

~~~bash
python -m compileall -q src tests
python -m unittest discover -s tests/unit -p "test_*.py" -v
python -m unittest discover -s tests/integration -p "test_*.py" -v
python -m unittest discover -s tests/evaluation -p "test_*.py" -v
~~~

Some model/performance suites are intentionally environment-gated. The Phase 14 closure record reports the final target-machine regression on its closure lineage as:

~~~text
Ran 416 tests in 282.906s — OK (skipped=9)
~~~

Those skips are documented as explicit model/benchmark-gated suites.

## Evaluation

The project evaluation contract covers:

- Precision@5
- Precision@10
- Recall@10
- NDCG@10
- Topic Coherence
- Topic Diversity
- Human Evaluation
- P50
- P95
- Throughput
- RAM
- VRAM

Gold data is profile-specific. SOLDIER gold data must remain outside the repository because it contains privacy-sensitive raw concern text.

The configured profile weights and semantic model identifiers are configuration, not an immutable claim that they are universally optimal. Production-quality changes should be evaluated against Persian gold datasets and regression baselines.

## Database Migrations

Apply committed migrations:

~~~bash
python -m src.infrastructure.scripts.run_migrations --upgrade
~~~

Generate a migration:

~~~bash
python -m src.infrastructure.scripts.run_migrations --autogenerate -m "describe schema change"
~~~

Generate and immediately upgrade in local development:

~~~bash
python -m src.infrastructure.scripts.run_migrations --sync -m "describe schema change"
~~~

Downgrade one revision:

~~~bash
python -m src.infrastructure.scripts.run_migrations --downgrade
~~~

Production Compose uses a one-shot <code>migrate</code> service. API and Worker depend on its successful completion, preventing multiple API replicas from racing migrations.

## CI/CD

Tracked workflows:

### CI — <code>.github/workflows/ci.yml</code>

Triggered on pushes to <code>main</code>, pull requests and manual dispatch. It runs:

1. PostgreSQL service + non-durable Redis.
2. Python 3.12 dependency install.
3. compile gate.
4. Alembic upgrade.
5. unit tests.
6. integration tests.
7. evaluation regression.
8. production image build.
9. production-like Compose startup.
10. API readiness/liveness/metrics smoke.
11. API/Worker resource-limit verification.
12. Worker health verification.
13. graceful-stop verification.

### Release — <code>.github/workflows/release.yml</code>

Triggered manually or by tags matching <code>v*</code>. It builds the production image, exports it with <code>docker save</code> as a Docker image tar archive, generates a SHA256 file and uploads both as a GitHub Actions artifact with 14-day retention.

No registry, cloud vendor or Kubernetes destination is assumed.

**CI status note:** this README intentionally does not display a green CI badge. At the time this README was generated, the repository connector returned no combined status contexts for the audited HEAD and its workflow-run lookup is PR-scoped, so a live "passing" claim could not be verified from the available status API. The tracked Phase 14 closure record does document a successful full target-machine regression and production-like verification.

## Performance

Performance tests are treated as baselines, not SLAs.

The Phase 14 production-like runtime benchmark:

~~~bash
RUN_PHASE14_RUNTIME_BENCHMARK=1 \
PHASE14_BASE_URL=http://127.0.0.1:5000 \
python -m unittest tests.evaluation.test_phase14_runtime_performance -v
~~~

PowerShell:

~~~powershell
$env:RUN_PHASE14_RUNTIME_BENCHMARK = "1"
$env:PHASE14_BASE_URL = "http://127.0.0.1:5000"
python -m unittest tests.evaluation.test_phase14_runtime_performance -v
~~~

It records P50/P95 latency and throughput for liveness plus analysis validation, and requires one-shot API/Worker Docker CPU/memory statistics. By default the benchmark resolves the running containers from Docker Compose service labels. If more than one Compose project with <code>api</code>/<code>worker</code> services is running, set <code>PHASE14_COMPOSE_PROJECT</code>, or set explicit <code>PHASE14_API_CONTAINER</code> and <code>PHASE14_WORKER_CONTAINER</code> values. The benchmark fails instead of silently reporting null resource statistics when the target containers cannot be resolved. The CPU production path reports VRAM as null.

## Production Deployment Notes

The repository provides a provider-neutral production image and production-like Compose topology. It does not claim an existing Kubernetes, AWS, Azure or GCP deployment.

Before deploying to a target platform:

- supply secrets through the environment or the existing Vault boundary;
- provision semantic model files because production remote downloads are disabled;
- keep Redis non-durable for SOLDIER transient payload transport;
- run Alembic before API/Worker;
- configure explicit allowed hosts/CORS policy;
- tune CPU/memory/PID limits using target-machine measurements;
- validate GPU model/device combinations separately if GPU is enabled;
- provide deployment-layer authentication/network controls if required by your environment.

## Known Limitations

- The public result API exposes final persisted keywords/topics, not the full internal candidate/rejection/embedding/reranking trace.
- Semantic model selection and profile scoring remain configuration/evaluation-sensitive; the repository does not claim universal Persian benchmark optimality.
- The default production Docker image is CPU-oriented.
- GPU configuration exists, but a standalone GPU production image is not claimed as verified here.
- Web/social/news scraping is outside scope.
- Authentication is not implemented because no authentication contract is defined.
- Production remote model download is disabled, so model provisioning is an operator responsibility.
- The two canonical architecture/reference documents supplied to project maintainers are not currently tracked on <code>main</code> under their canonical filenames; see [Documentation](#documentation).
- Live GitHub Actions "green" status was not independently verifiable through the available repository status connector at README generation time, so no status badge is published.

## Project Status

The current codebase contains implementation for the full 14-phase roadmap:

| Phase | Scope | Current repository state |
|---:|---|---|
| 1 | Requirements Freeze | Implemented / tracked requirements contract |
| 2 | Technical Architecture + Runtime Foundation | Implemented |
| 3 | API & DTO | Implemented |
| 4 | Database & Persistence | Implemented |
| 5 | Configuration & Environments | Implemented |
| 6 | Persian NLP Core | Implemented |
| 7 | Candidate & Statistical Engine | Implemented |
| 8 | Semantic Engine | Implemented |
| 9 | Hybrid Ranking | Implemented |
| 10 | Analysis Profiles | Implemented |
| 11 | Topic & Trend | Implemented |
| 12 | Async Jobs & Workers | Implemented |
| 13 | Visualization | Implemented |
| 14 | Production Readiness | <code>COMPLETE — PRODUCTION_READY</code> per tracked 2026-10-04 closure record |

Phase 14's tracked verification record includes dependency installation, compile, migrations, DB/Redis-backed integration, full regression, Docker build, CPU-only image verification, production-like Compose, API/Worker health, non-root execution, Redis non-durability, docs/OpenAPI disablement, security headers, request-size enforcement, privacy-safe logs/metrics, performance baseline and graceful shutdown.

## Documentation

Tracked repository documentation:

- [Technical Architecture](docs/architecture/technical_architecture.md) — class/component/file architecture and dependency boundaries.
- [Requirements Specification](docs/requirements/requirements_specification.md) — frozen product/runtime requirements.
- [Requirements Contract](docs/requirements/requirements_contract.json) — machine-readable Phase 1 contract.
- [Production Operations](docs/operations/production.md) — production image, Compose, security, observability, health and benchmark operations.
- [Phase 14 Production Readiness](docs/analytics/phase_14_production_readiness.md) — closure/verification record.

The project is also governed by two canonical reference documents supplied to project maintainers:

- <code>Service_Architecture_Guide_FA.md</code> — coding architecture, naming, DI/discovery, Repository/SQLAlchemy, Config/Vault and Alembic rules.
- <code>Project_Architecture_and_Phases_FA.md</code> — product architecture, profile scope, privacy, testing/evaluation, phase scope and Definition of Done.

Those two canonical filenames were not found in the audited <code>main</code> branch, so this README intentionally does not publish broken relative links to them.

## License

No <code>LICENSE</code> file was present in the audited <code>main</code> branch. No license is inferred or assigned by this README.
