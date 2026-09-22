# Persian Semantic Text Analytics Service — Technical Architecture

Version: 1.0.0
Status: FROZEN
Phase: 2 — Technical Architecture + Runtime Foundation
Based on: Phase 1 — Requirements Freeze

## 1. هدف

فاز ۲ معماری را در سطح Component، Class، File، Dependency، Lifecycle و Sequence Flow فریز می‌کند و هم‌زمان Runtime Foundation واقعی و executable پروژه را پیاده‌سازی می‌کند. این Foundation شامل Host bootstrap، WebService، DI injection/discovery/bootstrap، ConfigReader، VaultService، PsqlDbContext، BaseRepository و Provider contractهای واقعی است.

معماری الزام‌آور بدون تغییر است:

    Host → Application → Core → Infrastructure
    Controller → Service → Repository → PsqlDbContext

Constructor Injection، @inject discovery، Thin Controller، Repository Pattern، BaseRepository، suffix برابر _async برای متدهای async و عدم ایجاد Layer/Interface غیرضروری الزامی است.

## 2. ساختار هدف

Application:

    src/application/web.py
    src/application/analysis/analysis_controller.py
    src/application/analysis/dtos/analysis_dto.py

Core orchestration:

    src/core/services/analysis/analysis_service.py
    src/core/services/analysis/analysis_processor_service.py
    src/core/services/analysis/analysis_execution_policy_service.py
    src/core/services/analysis/providers/analysis_queue_provider.py

Profile services:

    src/core/services/course/course_analysis_service.py
    src/core/services/soldier_concern/soldier_concern_analysis_service.py
    src/core/services/media/media_analysis_service.py

Shared analytics:

    src/core/services/persian_text/persian_text_processor.py
    src/core/services/candidate/candidate_extraction_service.py
    src/core/services/statistical/statistical_analysis_service.py
    src/core/services/semantic/semantic_analysis_service.py
    src/core/services/semantic/providers/embedding_provider.py
    src/core/services/semantic/providers/reranker_provider.py
    src/core/services/ranking/hybrid_ranking_service.py
    src/core/services/topic/topic_analysis_service.py
    src/core/services/topic/providers/topic_model_provider.py
    src/core/services/trend/trend_analysis_service.py
    src/core/services/visualization/wordcloud_service.py

Infrastructure:

    src/infrastructure/context/sql_db/psql_dbcontext.py
    src/infrastructure/context/vault/vault_service.py
    src/infrastructure/utils/config_reader.py
    src/infrastructure/di/inject.py
    src/infrastructure/di/reflection.py
    src/infrastructure/di/bootstrap.py
    src/infrastructure/repositories/base/base_repository.py
    src/infrastructure/repositories/analysis/word_cloud_analysis_repository.py
    src/infrastructure/models/word_cloud_analysis.py
    src/infrastructure/models/analysis_document.py
    src/infrastructure/models/analysis_keyword.py
    src/infrastructure/models/analysis_topic.py
    src/infrastructure/models/analysis_topic_keyword.py
    src/infrastructure/providers/semantic/
    src/infrastructure/providers/queue/
    src/infrastructure/alembic/env.py
    src/infrastructure/scripts/run_migrations.py

## 3. مسئولیت Componentها

AnalysisController فقط HTTP، DTO validation، status/error mapping و response mapping را انجام می‌دهد و فقط به AnalysisService وابسته است. SQLAlchemy، Session، model inference و business workflow در Controller ممنوع است.

AnalysisService workflow سطح بالا را مدیریت می‌کند: ایجاد analysis lifecycle record، resolve کردن execution mode، dispatch مسیر sync/async و retrieval وضعیت/نتیجه. Dependencyهای آن AnalysisExecutionPolicyService، AnalysisProcessorService، WordCloudAnalysisRepository و AnalysisQueueProvider هستند.

AnalysisExecutionPolicyService ruleهای auto/sync/async و thresholdهای Phase 1 را enforce می‌کند و مقادیر را از ConfigReader می‌گیرد. explicit sync بالاتر از threshold مجاز نیست. Privacy transport constraintهای async که به Queue مربوط هستند در Phase 12 enforce می‌شوند و در Phase 2/3 به‌صورت fake پیاده‌سازی نمی‌شوند.

AnalysisProcessorService processing entrypoint مشترک HTTP sync path و Worker است. این Service Profile صحیح را انتخاب می‌کند، lifecycle را به processing/completed/failed transition می‌دهد، failure را sanitize می‌کند و نتیجه را از طریق Repository به‌صورت atomic persist می‌کند. Worker حق bypass کردن آن را ندارد.

CourseAnalysisService section/chunk awareness، COURSE scoring، section coverage و topic timeline را orchestrate می‌کند.

SoldierConcernAnalysisService هر concern را Document مستقل نگه می‌دارد و document frequency، document coverage، concern prevalence، cross-document signal و privacy guardها را اعمال می‌کند.

MediaAnalysisService Published Content و Audience Feedback را ابتدا جدا تحلیل می‌کند، سپس MEDIA scoring، trend و Content–Audience Gap را orchestrate می‌کند.

PersianTextProcessor normalization، ZWNJ/whitespace، noise handling، tokenization، linguistic processing و representation جدا برای Candidate و Embedding را مدیریت می‌کند.

CandidateExtractionService مسئول 1 تا 3-gram، noun phrase candidate در صورت linguistic support و filtering configurable است.

StatisticalAnalysisService frequency، document frequency، coverage و statistical score componentها را تولید می‌کند.

SemanticAnalysisService batching، embedding relevance، Top-N reduction و reranking را orchestrate می‌کند و فقط به EmbeddingProvider و RerankerProvider وابسته است.

HybridRankingService normalization، profile-specific fusion، deduplication و diversity را مدیریت می‌کند. Production weightها تا Evaluation نهایی فریز نمی‌شوند.

TopicAnalysisService از TopicModelProvider استفاده می‌کند و topic representation، prevalence، coverage و representative keywords را تولید می‌کند.

TrendAnalysisService trend timestamp-aware و emerging/stable/declining را مدیریت می‌کند.

WordCloudService فقط از Final Ranked Score استفاده می‌کند و Persian RTL/shaping را در Phase 13 پیاده‌سازی خواهد کرد.

## 4. Abstraction Policy

فقط چهار abstraction واقعی فریز می‌شوند:

    EmbeddingProvider
    RerankerProvider
    TopicModelProvider
    AnalysisQueueProvider

سه مورد اول برای model/provider قابل تعویض هستند و مورد Queue برای جدا کردن Core از queue vendor است. برای Serviceها و Repositoryهای عادی Interface جدا ساخته نمی‌شود.

Concrete semantic providerها در src/infrastructure/providers/semantic و concrete queue provider در src/infrastructure/providers/queue قرار می‌گیرند. نام model/vendor تا فاز مربوطه deferred می‌ماند.

## 5. Dependency Graph

    AnalysisController
        ↓
    AnalysisService
        ├─ AnalysisExecutionPolicyService
        ├─ AnalysisProcessorService
        ├─ WordCloudAnalysisRepository
        └─ AnalysisQueueProvider

    AnalysisExecutionPolicyService
        └─ ConfigReader

    AnalysisProcessorService
        ├─ CourseAnalysisService
        ├─ SoldierConcernAnalysisService
        ├─ MediaAnalysisService
        └─ WordCloudAnalysisRepository

هر Profile Service از engineهای مشترک زیر استفاده می‌کند:

    PersianTextProcessor
    CandidateExtractionService
    StatisticalAnalysisService
    SemanticAnalysisService
    HybridRankingService
    TopicAnalysisService

فقط MEDIA به TrendAnalysisService نیاز دارد.

SemanticAnalysisService به EmbeddingProvider و RerankerProvider وابسته است و TopicAnalysisService به TopicModelProvider.

Persistence:

    WordCloudAnalysisRepository → PsqlDbContext → ConfigReader / VaultService

## 6. Persistence و Transaction

Entityهای پایه Phase 1 بدون تغییر هستند:

    WordCloudAnalysis
    AnalysisDocument
    AnalysisKeyword
    AnalysisTopic
    AnalysisTopicKeyword

WordCloudAnalysisRepository از BaseRepository برای CRUD عمومی استفاده می‌کند و query/persistence اختصاصی analysis در همان Repository قرار می‌گیرد.

ذخیره نتیجه کامل باید atomic باشد: یک Repository Session باز می‌شود، root analysis و تمام document/keyword/topic/topic-keyword rowها نوشته یا update می‌شوند و فقط یک commit انجام می‌شود. failure قبل از commit باید rollback شود.

PsqlDbContext singleton است و AsyncEngine و async_sessionmaker را share می‌کند. Global AsyncSession و engine-per-request ممنوع است.

## 7. Singleton Policy

Singletonهای الزامی:

    ConfigReader
    VaultService
    PsqlDbContext

Controller، Service و Repository به‌صورت پیش‌فرض singleton نیستند.

Concrete provider سنگین که model نگه می‌دارد می‌تواند singleton باشد تا model یک بار load شود، اما request-specific mutable state نباید در shared field نگه داشته شود. Queue client نیز در Phase 12 فقط در صورت lifecycle/thread-safety مناسب می‌تواند singleton باشد.

## 8. Sync Flow

    HTTP Request
      → AnalysisController
      → AnalysisService
      → AnalysisExecutionPolicyService
      → WordCloudAnalysisRepository: create pending
      → AnalysisProcessorService
      → Profile Service
      → Shared Analytics Services
      → WordCloudAnalysisRepository: atomic result write
      → HTTP Response

Lifecycle:

    pending → processing → completed
                         ↘ failed

## 9. Async Flow

    HTTP Request
      → AnalysisController
      → AnalysisService
      → AnalysisExecutionPolicyService
      → WordCloudAnalysisRepository: create pending
      → AnalysisQueueProvider: enqueue
      → Accepted Response

    Worker
      → AnalysisProcessorService
      → Profile Service
      → Shared Analytics Services
      → WordCloudAnalysisRepository: atomic result write

Worker business logic مستقل ندارد و Profile Service را مستقیم فراخوانی نمی‌کند.

Queue technology، worker runtime و retry/backoff در Phase 12 انتخاب می‌شوند.

## 10. Privacy Boundary

Raw Text برای هیچ Profileای وارد application log، exception message، metric label یا tracing attribute نمی‌شود.

برای SOLDIER_CONCERN علاوه بر آن:

    DB persistence of raw text = forbidden
    durable queue payload with raw text = forbidden
    disk spool with raw text = forbidden

Raw Text فقط در memory و transient processing path مجاز است. Async Soldier path باید non-durable باشد. اگر transient payload به‌علت crash از بین برود، analysis در صورت امکان failed می‌شود و client باید request را دوباره submit کند. این trade-off از privacy contract Phase 1 ناشی می‌شود و Phase 12 باید آن را enforce کند.

## 11. Layer Boundaries

Application مالک HTTP، DTO، validation و mapping است و نباید SQLAlchemy Session/query یا model inference detail بداند.

Core مالک workflow، profile rule، NLP/semantic/ranking/topic/trend orchestration و provider contractهای واقعی است. Core نباید APIRouter، HTTPException، status code، queue vendor یا نام model نهایی Production را بشناسد.

Infrastructure مالک SQLAlchemy model، Repository query/persistence، engine/session factory، Config/Vault، DI discovery، Alembic و concrete external providerها است.

## 12. Phase Ownership

Phase 3 exact API routes، DTOها، validation و HTTP error contract را فریز می‌کند.

Phase 4 schema، relation، Repository implementation، migration و indexها را پیاده‌سازی می‌کند.

Phase 5 configuration و environmentها را نهایی می‌کند.

Phase 6 PersianTextProcessor، Phase 7 Candidate/Statistical، Phase 8 Semantic Providers، Phase 9 Hybrid Ranking، Phase 10 Profile workflows، Phase 11 Topic/Trend، Phase 12 Queue/Worker، Phase 13 Visualization و Phase 14 Production Readiness را پیاده‌سازی می‌کنند.

## 13. Deferred Decisions

Phase 2 عمداً این موارد را حدسی فریز نمی‌کند: exact embedding/reranker/topic model، final profile weights، MMR lambda، semantic dedup threshold، production latency SLO، worker/queue technology، GPU model، DB indexes، API routes و HTTP error codes.

## 14. Definition of Done

فاز ۲ فقط زمانی کامل است که علاوه بر Component Catalog، class/file map، dependency graph، sync/async sequence، singleton policy، transaction boundary، Core/Infrastructure boundary، worker reuse rule، Soldier privacy boundary و Phase ownership، Runtime Foundation نیز واقعاً وجود داشته باشد و قابل اجرا باشد.

Runtime Foundation پیاده‌سازی‌شده در این فاز:
- src/host/app.py
- src/application/web.py
- src/infrastructure/di/inject.py
- src/infrastructure/di/reflection.py
- src/infrastructure/di/bootstrap.py
- src/infrastructure/utils/config_reader.py
- src/infrastructure/context/vault/vault_service.py
- src/infrastructure/context/sql_db/psql_dbcontext.py
- src/infrastructure/repositories/base/base_repository.py
- EmbeddingProvider
- RerankerProvider
- TopicModelProvider
- AnalysisQueueProvider

معیار بسته‌شدن:
- src و tests compile شوند.
- Constructor DI و singleton policy با تست واقعی کار کنند.
- DI discovery ماژول‌ها را واقعاً import و register کند.
- WebService controller discovery را بر اساس convention اجرا کند.
- application foundation در یک process تازه boot شود.
- هیچ Analysis API، DB schema نهایی، concrete semantic provider یا queue implementation متعلق به Phaseهای بعدی به‌صورت fake ساخته نشده باشد.


Status after successful compile, unit, integration and startup smoke verification:

PHASE_2_COMPLETE
