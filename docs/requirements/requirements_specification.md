# Persian Semantic Text Analytics Service
## Requirements Specification

Version: 1.0.0
Status: FROZEN
Phase: 1 — Requirements Freeze

---

## 1. Purpose

این پروژه یک WordCloud Generator ساده نیست.

محصول نهایی یک:

Persian Semantic Text Analytics Service

است که WordCloud فقط یکی از Visualizationهای خروجی آن محسوب می‌شود.

Pipeline سطح بالا:

Persian Preprocessing
→ Candidate / Keyphrase Extraction
→ Statistical Analysis
→ Semantic Analysis
→ Re-ranking / Score Fusion
→ Deduplication / Diversity
→ Topic / Trend Analysis
→ Structured JSON
→ WordCloud Visualization

Structured JSON خروجی اصلی سیستم است.

PNG و SVG فقط Visualization روی نتیجه نهایی تحلیل هستند.

---

## 2. Supported Analysis Profiles

سیستم در نسخه فعلی سه Analysis Profile اصلی دارد:

1. COURSE
2. SOLDIER_CONCERN
3. MEDIA

Scoring، workflow و interpretation این Profileها یکسان نیست.

استفاده از یک scoring formula ثابت برای هر سه Profile ممنوع است.

---

# 3. Architecture Constraints

تمام مراحل بعدی باید معماری زیر را حفظ کنند:

Host
→ Application
→ Core
→ Infrastructure

جریان استاندارد Featureهای HTTP:

HTTP Request
→ Controller
→ Service
→ Repository
→ PsqlDbContext
→ PostgreSQL

قواعد معماری الزام‌آور:

- Dependencyها با Constructor Injection دریافت می‌شوند.
- Service با @inject تعریف می‌شود.
- Repository با @inject تعریف می‌شود.
- Infrastructure Provider وابسته با @inject تعریف می‌شود.
- Controller دارای dependency با @inject تعریف می‌شود.
- Controller فقط HTTP concernها را مدیریت می‌کند.
- Business workflow در Core/services قرار می‌گیرد.
- SQLAlchemy query و persistence فقط در Repository قرار می‌گیرد.
- CRUD عمومی باید BaseRepository را reuse کند.
- SQLAlchemy Modelها در src/infrastructure/models قرار می‌گیرند.
- DTOها در src/application/{feature}/dtos قرار می‌گیرند.
- async methodها suffix برابر _async دارند.
- Interface فقط برای abstraction واقعی یا چند implementation ایجاد می‌شود.
- DDD، CQRS، Hexagonal Architecture و UseCase Layer بدون درخواست صریح اضافه نمی‌شوند.
- Provider registration دستی در صورتی که discovery قابل استفاده باشد انجام نمی‌شود.
- هر Model جدید باید برای Alembic metadata قابل مشاهده باشد.
- هر تغییر schema باید Migration داشته باشد.

---

# 4. Input Contract

هر Analysis شامل موارد زیر است:

- analysis_type
- reference اختیاری
- documents
- options اختیاری
- execution_mode

analysis_type یکی از موارد زیر است:

- COURSE
- SOLDIER_CONCERN
- MEDIA

execution_mode یکی از موارد زیر است:

- auto
- sync
- async

---

## 4.1 Document Contract

هر Document حداقل دارای موارد زیر است:

- document_id
- text

و می‌تواند Metadata اختیاری داشته باشد.

Metadata باید برای use-caseهای مختلف قابل توسعه باشد بدون اینکه Raw Text در Metadata تکرار شود.

---

## 4.2 Input Hard Limits

Hard limits اولیه سیستم:

- Maximum documents per analysis: 5000
- Maximum characters per document: 500000
- Maximum total characters per analysis: 10000000

این limitها configuration-driven خواهند بود و hard-code نهایی داخل Service ممنوع است.

هدف این limitها:

- جلوگیری از مصرف کنترل‌نشده RAM
- جلوگیری از request abuse
- کنترل execution time
- امکان اجرای سیستم روی Laptop
- قابل پیش‌بینی بودن Queue workload در Production

مقادیر نهایی Production می‌توانند بعد از Performance Benchmark تنظیم شوند.

---

# 5. Sync / Async Execution Policy

سیستم باید هر دو execution mode را پشتیبانی کند.

## 5.1 Sync

Sync processing برای workload سبک استفاده می‌شود.

Threshold اولیه:

- حداکثر 20 Document
- حداکثر 100000 Character مجموع

هر دو شرط باید برقرار باشند.

---

## 5.2 Async

Corpusهای بزرگ باید Async پردازش شوند.

معماری هدف:

FastAPI
→ Create Analysis
→ Queue
→ Worker
→ Core Services
→ Repository
→ Persist Result

Worker نباید Business Logic مستقل داشته باشد.

Worker فقط Core Service موجود را invoke می‌کند.

---

## 5.3 Auto

در execution_mode=auto:

اگر:

document_count <= 20
AND
total_characters <= 100000

باشد، تحلیل می‌تواند Sync اجرا شود.

در غیر این صورت Async انتخاب می‌شود.

---

## 5.4 Explicit Sync

اگر Client صریحاً execution_mode=sync درخواست کند ولی workload از Sync Threshold بیشتر باشد، درخواست Sync نباید به‌صورت کنترل‌نشده اجرا شود.

نحوه HTTP mapping این وضعیت در Phase 3 — API & DTO مشخص می‌شود.

---

# 6. Persian NLP Requirements

Preprocessing فارسی باید حداقل موارد زیر را پوشش دهد:

- Unicode normalization
- Arabic/Persian character normalization
- Persian Yeh normalization
- Persian Kaf normalization
- ZWNJ normalization
- whitespace normalization
- noise handling
- tokenization
- configurable lemmatization
- configurable POS processing
- general stopwords
- domain stopwords
- protected terms
- synonym terms
- canonical terms

---

## 6.1 Separate Representations

سیستم باید representation مناسب Candidate Extraction را از representation مناسب Embedding جدا نگه دارد.

Candidate representation نباید به دلیل preprocessing بیش از حد، phrase structure مورد نیاز extraction را از بین ببرد.

Embedding representation می‌تواند normalization متفاوتی داشته باشد.

---

# 7. Candidate Extraction Requirements

Candidate Extraction باید حداقل از:

- unigram
- bigram
- trigram

پشتیبانی کند.

بنابراین ngram_range برابر:

1 تا 3

است.

در صورت وجود linguistic information قابل اعتماد، noun phrase candidateها باید قابل استفاده باشند.

Candidate filtering باید configurable باشد.

---

# 8. Semantic Architecture Requirements

Semantic Engine نباید به یک مدل خاص hard-code شود.

Abstractionهای واقعی مورد نیاز:

- EmbeddingProvider
- RerankerProvider
- TopicModelProvider

این Interfaceها مجاز هستند چون implementation مدل باید قابل تعویض باشد.

مدل نهایی فقط بعد از Benchmark روی داده واقعی فارسی انتخاب می‌شود.

هیچ Model Name خاصی در Phase 1 به‌عنوان مدل Production فریز نمی‌شود.

---

## 8.1 Preferred Semantic Pipeline

مسیر ترجیحی:

Candidates
→ Bi-Encoder
→ Top-N Candidates
→ Cross-Encoder
→ Hybrid Ranking

Cross-Encoder باید فقط روی Candidateهای محدودشده اجرا شود تا latency و resource consumption کنترل شود.

---

## 8.2 Model Lifecycle

مدل‌های سنگین نباید per-request load شوند.

Providerهایی که Model سنگین نگه می‌دارند می‌توانند Singleton باشند.

Singleton بودن باید بر اساس lifecycle واقعی Provider باشد.

---

# 9. Hybrid Ranking Requirements

Final Keyphrase Ranking باید بتواند موارد زیر را ترکیب کند:

- statistical score
- semantic relevance
- profile-specific signals
- phrase quality
- coverage
- normalization
- reranker score

Score Fusion باید configurable باشد.

وزن‌های Production نباید صرفاً حدسی و hard-coded باشند.

وزن‌ها ابتدا configurable هستند و سپس با Gold Dataset و Evaluation تنظیم می‌شوند.

---

## 9.1 Deduplication

سیستم باید بتواند duplicateهای زیر را حذف یا merge کند:

- exact duplicates
- normalized lexical duplicates
- canonical-term duplicates
- high-semantic-similarity duplicates

---

## 9.2 Diversity

Ranking نهایی نباید فقط مجموعه‌ای از عبارت‌های تقریباً مترادف باشد.

یک diversity mechanism مانند MMR یا روش equivalent باید در Phase 9 ارزیابی شود.

انتخاب الگوریتم نهایی در Phase 9 انجام می‌شود.

---

# 10. COURSE Profile

COURSE برای تحلیل:

- course text
- session
- section
- chapter
- long document

است.

---

## 10.1 COURSE Requirements

سیستم باید پشتیبانی کند از:

- Persian normalization
- long-document analysis
- chunk-aware processing
- section-aware processing
- 1 تا 3 gram keyphrases
- statistical ranking
- semantic ranking
- hybrid ranking
- topic extraction
- section coverage
- topic timeline
- ranked keyphrases
- structured JSON
- WordCloud

---

## 10.2 COURSE Scoring Signals

COURSE scoring باید حداقل بتواند این signalها را استفاده کند:

- semantic relevance
- frequency
- chunk coverage
- section coverage
- phrase quality

وزن نهایی در این مرحله فریز نمی‌شود.

---

## 10.3 COURSE Goal

هدف:

فهم سریع موضوعات اصلی دوره،
اهمیت Keyphraseها،
پوشش موضوع در Sectionها،
و روند حرکت Topicها در طول محتوا.

---

# 11. SOLDIER_CONCERN Profile

در SOLDIER_CONCERN هر دل‌نوشته یک Document مستقل است.

ادغام تمام دل‌نوشته‌ها به یک Document واحد ممنوع است.

---

## 11.1 SOLDIER_CONCERN Requirements

سیستم باید پشتیبانی کند از:

- multi-document corpus analysis
- document frequency
- document coverage
- concern prevalence
- semantic clustering
- topic extraction
- representative keyphrases
- overall word cloud
- topic-level word cloud

---

## 11.2 SOLDIER_CONCERN Scoring Signals

حداقل signalها:

- document frequency
- document coverage
- semantic relevance
- topic prevalence

تکرار یک دغدغه در چند Document مستقل یک signal مثبت است.

صرف تکرار زیاد یک عبارت داخل یک Document نباید به اندازه تکرار آن دغدغه بین افراد مختلف ارزش داشته باشد.

---

## 11.3 SOLDIER_CONCERN Privacy

این Profile privacy-sensitive است.

الزامات:

- Raw Text نباید در application log ثبت شود.
- Raw Text نباید در exception message قرار گیرد.
- Raw Text نباید در metrics label قرار گیرد.
- Raw Text نباید در tracing attribute قرار گیرد.
- Raw Text SOLDIER_CONCERN در persistence ذخیره نمی‌شود.
- فقط metadata، derived analytics و identifiers مورد نیاز ذخیره می‌شوند.
- Debug logging نباید privacy requirement را دور بزند.

این policy قابل غیرفعال‌شدن توسط request نیست.

---

# 12. MEDIA Profile

MEDIA باید Published Content و Audience Feedback را ابتدا جداگانه تحلیل کند.

ترکیب زودهنگام این دو corpus ممنوع است.

Document باید role داشته باشد.

Roleهای اولیه:

- published_content
- audience_feedback

---

## 12.1 MEDIA Requirements

سیستم باید پشتیبانی کند از:

- content topic analysis
- audience topic analysis
- mention prevalence
- coverage
- semantic relevance
- engagement normalization
- topic trend
- emerging topics
- stable topics
- declining topics
- content-audience gap
- structured JSON
- word cloud

---

## 12.2 MEDIA Scoring Signals

حداقل signalها:

- mention share
- semantic relevance
- coverage
- normalized engagement
- trend growth
- recency

وزن نهایی در Phase 1 فریز نمی‌شود.

---

## 12.3 MEDIA Boundary

Scraping مسئولیت این Service نیست.

ورودی Service:

Document + Metadata

است.

جمع‌آوری داده از شبکه اجتماعی، سایت خبری یا Platform خارجی خارج از scope این Service است.

---

# 13. Topic Analysis Requirements

Topic Analysis باید حداقل موارد زیر را تولید کند:

- topic identifier
- topic label/representation
- prevalence
- representative keywords
- document coverage

بسته به Profile می‌تواند شامل:

- section coverage
- timeline
- trend
- representative documents

باشد.

TopicModelProvider باید قابل تعویض باشد.

---

# 14. Trend Analysis Requirements

Trend در ابتدا برای MEDIA الزام اصلی دارد.

Topic trend باید بتواند وضعیت Topic را به یکی از حالت‌های مفهومی زیر map کند:

- emerging
- stable
- declining

محاسبه trend باید timestamp-aware باشد.

روش و threshold دقیق trend در Phase 11 و بر اساس داده واقعی تعیین می‌شود.

---

# 15. Structured Output Requirements

JSON خروجی اصلی Analysis است.

خروجی باید حداقل شامل گروه‌های اطلاعاتی زیر باشد:

- analysis
- keywords
- topics
- metrics
- profile_result

Analysis metadata باید حداقل امکان نگهداری موارد زیر را داشته باشد:

- analysis_id
- analysis_type
- status
- reference
- model_version
- scoring_version
- created_at
- started_at
- completed_at
- error information

---

## 15.1 Keyword Output

هر Ranked Keyword باید بتواند حداقل موارد زیر را ارائه کند:

- text
- canonical_text
- rank
- final_score
- statistical_score
- semantic_score
- coverage
- frequency

Profile-specific score componentها می‌توانند اضافه شوند.

---

## 15.2 Topic Output

هر Topic باید بتواند حداقل موارد زیر را ارائه کند:

- topic_id
- label
- prevalence
- coverage
- keywords

MEDIA می‌تواند علاوه بر آن داشته باشد:

- trend
- trend_score

COURSE می‌تواند علاوه بر آن داشته باشد:

- section_coverage
- timeline

---

# 16. Visualization Requirements

WordCloud خروجی ثانویه است.

WordCloud فقط باید از Final Ranked Score استفاده کند.

Raw term frequency نباید مستقیماً به‌عنوان وزن نهایی WordCloud استفاده شود مگر Profile scoring صریحاً چنین تصمیمی گرفته باشد.

Visualization باید:

- Persian text را پشتیبانی کند
- RTL را پشتیبانی کند
- Persian shaping را درست نمایش دهد
- PNG output داشته باشد
- SVG output داشته باشد

Visualization implementation در Phase 13 انجام می‌شود.

---

# 17. Persistence Requirements

Persistence بخشی از معماری نهایی سیستم است.

دلایل:

- History
- Reproducibility
- Trend Analysis
- Model Version Tracking
- Scoring Version Tracking
- Debugging
- Evaluation comparison

Entityهای پایه:

- WordCloudAnalysis
- AnalysisDocument
- AnalysisKeyword
- AnalysisTopic
- AnalysisTopicKeyword

در صورت نیاز Phase 11 می‌تواند Trend Entity اضافه کند.

---

## 17.1 WordCloudAnalysis Data

Analysis باید حداقل قابلیت نگهداری موارد زیر را داشته باشد:

- id
- type
- status
- reference
- model_version
- scoring_version
- metrics
- error information
- creation timestamp
- start timestamp
- completion timestamp

---

## 17.2 AnalysisDocument

AnalysisDocument برای metadata و derived information استفاده می‌شود.

Raw Text به‌صورت پیش‌فرض persist نمی‌شود.

برای SOLDIER_CONCERN ذخیره Raw Text ممنوع است.

---

# 18. Privacy Requirements

Raw Text برای هیچ Profileای نباید در log ثبت شود.

Log مجاز است شامل:

- analysis_id
- document_id
- analysis_type
- status
- duration
- counts
- model version
- scoring version
- sanitized error code

باشد.

Log نباید شامل:

- full document text
- raw excerpt
- private user content
- full soldier concern content

باشد.

---

# 19. Reproducibility Requirements

هر نتیجه persist شده باید به اندازه کافی metadata داشته باشد که مشخص شود با چه configuration و model generation ایجاد شده است.

حداقل:

- model_version
- scoring_version
- analysis_type
- processing timestamps
- relevant analysis metrics

در مراحل بعد در صورت نیاز موارد زیر اضافه می‌شوند:

- preprocessing_version
- provider_version
- configuration fingerprint

---

# 20. Configuration Requirements

موارد زیر باید configuration-driven باشند:

- input limits
- sync thresholds
- model selection
- device
- batch sizes
- Top-N reranking
- profile scoring weights
- stopword resources
- domain stopwords
- protected terms
- canonical terms
- deduplication thresholds
- diversity configuration

مقادیر Production نباید در Business Logic پراکنده شوند.

---

# 21. Local and Production Requirements

یک Codebase واحد باید هم روی Laptop و هم Production اجرا شود.

Laptop mode باید CPU-ready باشد.

Production باید بتواند GPU configuration را در صورت وجود فعال کند.

Business Logic نباید برای CPU و GPU دو implementation جداگانه داشته باشد.

تفاوت محیط باید عمدتاً از Configuration و Provider configuration مدیریت شود.

---

# 22. Evaluation Requirements

Evaluation بخشی از Definition of Done سیستم است.

سه Gold Dataset مستقل لازم است:

- COURSE Gold Dataset
- SOLDIER_CONCERN Gold Dataset
- MEDIA Gold Dataset

---

## 22.1 Required Ranking Metrics

حداقل metrics:

- Precision@5
- Precision@10
- Recall@10
- NDCG@10

---

## 22.2 Topic Metrics

حداقل:

- Topic Coherence
- Topic Diversity

---

## 22.3 Human Evaluation

Evaluation انسانی باید حداقل relevance و usefulness خروجی را برای هر Profile بررسی کند.

روش scoring انسانی در Evaluation Phase نهایی می‌شود.

---

## 22.4 Performance Metrics

Benchmark باید حداقل اندازه‌گیری کند:

- P50 latency
- P95 latency
- throughput
- peak RAM
- peak VRAM when GPU is enabled

---

# 23. Evaluation Policy

هیچ مدل Semantic یا Weight Set صرفاً بر اساس حدس به‌عنوان Production Final انتخاب نمی‌شود.

Model Selection باید بر اساس Benchmark فارسی و داده واقعی پروژه باشد.

Scoring Weights ابتدا configurable هستند.

Final weights باید توسط Evaluation پشتیبانی شوند.

---

## 23.1 Regression Gate

پس از ایجاد accepted baseline:

Regression بیشتر از 3 درصد به‌صورت relative در:

- Precision@10
یا
- NDCG@10

باید Release را block کند مگر اینکه justification مستند و explicit approval وجود داشته باشد.

این مقدار یک initial engineering guardrail است و در صورت وجود شواهد Evaluation قابل بازنگری است.

---

# 24. Testing Requirements

ساختار تست نهایی:

tests/
├── unit/
├── integration/
└── evaluation/

بسته به Phase باید شامل موارد مناسب زیر باشد:

- Unit Test
- Integration Test
- API Test
- Repository Test
- Database Test
- DI Test
- Discovery Test
- NLP Evaluation
- Regression Test
- Performance Test

Unit Test به‌تنهایی برای NLP Definition of Done محسوب نمی‌شود.

---

# 25. Error Requirements

سیستم باید errorها را بدون leak کردن Raw Text ثبت و مدیریت کند.

Analysis failure باید قابل persist شدن باشد.

حداقل وضعیت‌های lifecycle که در طراحی بعدی باید پشتیبانی شوند:

- pending
- processing
- completed
- failed

در صورت Async processing وضعیت retry نیز می‌تواند در Queue infrastructure وجود داشته باشد، اما business status contract نباید به Queue implementation خاص hard-code شود.

---

# 26. Out of Scope

موارد زیر در scope این Service نیستند:

- Web Scraping
- Social Media Scraping
- News Crawling
- Content Acquisition Pipeline
- Training a foundation language model
- Generic chatbot functionality

این Service Document + Metadata دریافت می‌کند و Semantic Text Analytics انجام می‌دهد.

---

# 27. Phase Acceptance Criteria

## COURSE

Phaseهای مربوط به COURSE زمانی قابل قبول هستند که:

- Persian normalization اعمال شده باشد.
- Long document قابل پردازش باشد.
- Section information حفظ شود.
- Keyphrases رتبه‌بندی شوند.
- Semantic و statistical signals ترکیب شوند.
- Section coverage قابل تولید باشد.
- Topic extraction وجود داشته باشد.
- Topic timeline قابل تولید باشد.
- JSON structured output وجود داشته باشد.
- Evaluation روی COURSE Gold Dataset اجرا شود.

---

## SOLDIER_CONCERN

قابل قبول است وقتی:

- هر concern یک Document مستقل باقی بماند.
- document frequency محاسبه شود.
- document coverage محاسبه شود.
- repeated concern across documents signal مثبت باشد.
- topic prevalence محاسبه شود.
- representative keyphrases تولید شوند.
- Raw Text در log ظاهر نشود.
- Raw Text concern در DB persist نشود.
- Evaluation روی SOLDIER_CONCERN Gold Dataset اجرا شود.

---

## MEDIA

قابل قبول است وقتی:

- Published Content جدا تحلیل شود.
- Audience Feedback جدا تحلیل شود.
- Content Topics تولید شوند.
- Audience Topics تولید شوند.
- normalized engagement قابل استفاده باشد.
- trend قابل محاسبه باشد.
- emerging/stable/declining topics قابل تشخیص باشند.
- Content–Audience Gap قابل محاسبه باشد.
- Evaluation روی MEDIA Gold Dataset اجرا شود.

---

# 28. Phase 1 Decisions

موارد زیر در Phase 1 فریز شده‌اند:

- سه Profile اصلی
- JSON-first architecture
- WordCloud به‌عنوان Visualization
- Persistence requirement
- Privacy-first handling
- Async requirement برای corpus بزرگ
- Separate scoring profile
- Replaceable semantic providers
- 1 تا 3 gram candidates
- Gold Dataset requirement
- Required evaluation metrics
- No guessed final model
- No guessed final scoring weights
- Laptop + Production from one codebase

---

# 29. Decisions Deferred Intentionally

موارد زیر عمداً در Phase 1 فریز نمی‌شوند:

- exact embedding model
- exact reranker model
- exact topic model
- final profile weights
- exact MMR lambda
- exact semantic deduplication threshold
- exact production latency SLO
- exact worker technology
- exact queue technology
- exact GPU model
- exact database indexes
- exact API routes
- exact HTTP error codes

این موارد در Phaseهای رسمی مربوط به خودشان تعیین می‌شوند.

---

# 30. Definition of Done — Phase 1

Phase 1 فقط زمانی Done است که:

- Requirements Specification وجود داشته باشد.
- Machine-readable Requirements Contract وجود داشته باشد.
- سه Profile تعریف شده باشند.
- Input limits تعریف شده باشند.
- Sync/Async policy تعریف شده باشد.
- Persistence policy تعریف شده باشد.
- Privacy policy تعریف شده باشد.
- Evaluation requirements تعریف شده باشند.
- Architecture constraints ثبت شده باشند.
- Deferred decisions مشخص شده باشند.
- Contract tests پاس شوند.
- هیچ runtime implementation زودهنگام اضافه نشده باشد.
- هیچ TODO یا placeholder در Phase 1 باقی نمانده باشد.

Status after successful contract tests:

PHASE_1_COMPLETE