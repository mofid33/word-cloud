# Phase 10 Gold Dataset Infrastructure

این پوشه Contract و ابزار ارزیابی Gold Dataset برای `COURSE`، `SOLDIER_CONCERN` و `MEDIA` را نگه می‌دارد. داده‌ی واقعی Gold به‌صورت خودکار یا از synthetic fixture ساخته نمی‌شود و باید با Human Annotation تهیه و adjudicate شود.

## Dataset package

هر Dataset یک directory مستقل است و شامل این دو فایل می‌شود:

- `manifest.json`
- `cases.jsonl` یا نام JSONL دیگری که در `manifest.json` تعیین شده باشد.

`manifest.json` باید `schema_version=phase10-gold-v1`، شناسه و نسخه‌ی dataset، profile، نسخه‌ی guideline و نام فایل caseها را داشته باشد.

هر خط `cases.jsonl` یک case مستقل با این بخش‌هاست:

- `case_id`: شناسه‌ی opaque و غیرحساس؛
- `split`: فقط `tuning` یا `holdout`؛
- `documents`: ورودی واقعی همان Profile؛
- `annotation`: Human Annotation نهایی و relevance judgmentها.

Machine-readable contract در `phase10_gold_schema.json` است و validator اجرایی در `tests/evaluation/phase10_gold_dataset.py` قرار دارد.

## Relevance grades

برای `phase10-gold-v1`، grade به‌صورت زیر تعریف شده است:

- `3`: keyphrase مرکزی/ضروری برای case؛
- `2`: keyphrase مهم و واضح؛
- `1`: مرتبط ولی فرعی؛
- `0`: judged negative / غیرمرتبط.

این scale برای پشتیبانی از graded `NDCG@10` انتخاب شده است. `Precision@5`، `Precision@10` و `Recall@10` هر grade بزرگ‌تر از صفر را relevant در نظر می‌گیرند.

## Human annotation

Gold label نباید از خروجی مدل به‌صورت خودکار تولید شود. Annotator ابتدا متن را مستقل بررسی می‌کند، سپس relevance judgmentها ثبت می‌شوند. `annotator_count` تعداد annotatorهای انسانی را ثبت می‌کند و evaluator برای split مورد ارزیابی فقط caseهایی را قبول می‌کند که `adjudicated=true` داشته باشند.

Schema حداقل یک annotator را می‌پذیرد؛ برای dataset نهایی Production استفاده از بیش از یک annotator و adjudication اختلاف‌ها توصیه می‌شود، اما تعداد نهایی annotatorها یک تصمیم Evaluation/Project است و در contract به عدد ثابت بزرگ‌تر از یک قفل نشده است.

## Split discipline

`tuning` برای تنظیم وزن‌ها و تصمیم‌های scoring استفاده می‌شود. `holdout` برای ارزیابی نهایی است و نباید در زمان tuning به‌عنوان feedback loop استفاده شود. Runner عمداً فقط یک split را در هر اجرا قبول می‌کند تا این boundary روشن بماند.

## Soldier privacy

Raw text مربوط به `SOLDIER_CONCERN` نباید در repository قرار بگیرد. Loader برای این Profile هر dataset directory داخل repository را رد می‌کند. از یک مسیر private خارج از repository استفاده کنید.

همچنان قواعد اصلی Privacy برقرارند: raw concern text وارد log، metric، trace، Database persistence یا durable queue نمی‌شود. Evaluation output فقط fingerprint، version، count، model/scoring version و metricها را چاپ می‌کند و raw document text را چاپ نمی‌کند.

## Dataset locations

Runner می‌تواند `--dataset-dir` بگیرد یا از متغیرهای زیر استفاده کند:

```text
PHASE10_GOLD_COURSE_DIR
PHASE10_GOLD_SOLDIER_DIR
PHASE10_GOLD_MEDIA_DIR
```

برای Soldier مسیر باید خارج از repository باشد.

## Evaluation commands

Tuning split:

```powershell
python -m tests.evaluation.run_phase10_gold_evaluation --profile COURSE --split tuning
python -m tests.evaluation.run_phase10_gold_evaluation --profile SOLDIER_CONCERN --split tuning
python -m tests.evaluation.run_phase10_gold_evaluation --profile MEDIA --split tuning
```

Holdout split فقط بعد از پایان tuning:

```powershell
python -m tests.evaluation.run_phase10_gold_evaluation --profile COURSE --split holdout
python -m tests.evaluation.run_phase10_gold_evaluation --profile SOLDIER_CONCERN --split holdout
python -m tests.evaluation.run_phase10_gold_evaluation --profile MEDIA --split holdout
```

Evaluator از Profile Service واقعی و DI موجود استفاده می‌کند و metricهای macro-average زیر را گزارش می‌دهد:

- `Precision@5`
- `Precision@10`
- `Recall@10`
- `NDCG@10`

همراه metricها، dataset fingerprint، dataset/guideline version و model/scoring version نیز ثبت می‌شوند تا evaluation reproducible باشد.

## COURSE source manifest v1

برای `COURSE`، انتخاب منبع اولیه قبل از Human Annotation به‌صورت reproducible freeze شده است:

- manifest: `tests/evaluation/gold/course_source_manifest_v1.json`;
- source: Persian Wikibooks;
- تعداد source unit: 30؛
- `tuning`: 20 unit در 7 case group؛
- `holdout`: 10 unit در 4 case group؛
- domainها: `fluid_mechanics`، `python_programming`، `mathematics_economics` و `linux_cli`؛
- توزیع domainها: 8 Fluid، 8 Python، 7 Math/Economics و 7 Linux؛
- هر unit با `case_group_id`، `revision_id` و permanent URL ثابت شده است؛
- هیچ `page_title + revision_id` یا `case_group_id` بین tuning و holdout مشترک نیست؛
- هر چهار domain در هر دو split حضور دارند؛
- تخصیص holdout قبل از annotation و weight tuning freeze شده و در runtime دوباره random نمی‌شود.

این manifest هنوز Gold label نیست. عنوان section یا heading منبع به‌صورت خودکار relevance label محسوب نمی‌شود.

### Materialization

Materializer فقط revision و section ثبت‌شده در manifest را از MediaWiki API دریافت می‌کند:

```powershell
python -m tests.evaluation.materialize_course_gold_sources --output "E:\WordCloudGold\course_sources_v1.course_gold_materialized.jsonl"
```

Output باید خارج از repository باشد. Script اگر output داخل repository باشد fail-fast می‌کند. `.gitignore` نیز به‌عنوان defense-in-depth فایل‌های `*.course_gold_materialized.jsonl` را نادیده می‌گیرد.

Materialized row شامل provenance، revision، permanent attribution URL، SHA-256 متن و متن همان section است. Materializer:

- live page را به‌جای revision ثابت استفاده نمی‌کند؛
- section heading را در همان revision resolve می‌کند؛
- برای headingهای تکراری، manifest می‌تواند `section_level` صریح داشته باشد تا ambiguity بدون fuzzy selection رفع شود؛
- section map هر revision را در همان اجرا cache می‌کند تا درخواست تکراری حذف شود؛
- درخواست‌ها را serial/throttled ارسال می‌کند و `maxlag` را برای MediaWiki API فعال می‌کند؛
- برای HTTP `429` و `503` مقدار `Retry-After` را رعایت می‌کند و در نبود آن exponential backoff دارد؛
- User-Agent شامل نام client و URL repository است؛
- revision mismatch را رد می‌کند؛
- section مبهم/گم‌شده را رد می‌کند؛
- source unit کوتاه‌تر از minimum تعریف‌شده را رد می‌کند؛
- raw materialized text را داخل repository ذخیره نمی‌کند.

بعد از materialization باید source units توسط انسان annotation شوند و خروجی نهایی به contract `phase10-gold-v1` تبدیل شود. Model output یا عنوان صفحه/section نباید به‌صورت خودکار Gold label تولید کند.

### Attribution and licensing provenance

برای هر source unit، `permanent_url` و `attribution_url` در manifest ثبت شده است. قبل از انتشار یا توزیع corpus materialized باید attribution و شرایط بازنشر منبع رعایت شوند. Repository فقط provenance manifest و tooling را version-control می‌کند؛ corpus materialized به‌صورت پیش‌فرض داخل GitHub قرار نمی‌گیرد.

## COURSE Human Annotation Package

پس از materialization موفق، fingerprint تأییدشده در فایل زیر ثبت می‌شود:

`tests/evaluation/gold/course_source_materialization_v1.json`

برای ساخت working annotation package:

```powershell
python -m tests.evaluation.prepare_course_gold_annotation `
  --input "E:\WordCloudGold\course_sources_v1.course_gold_materialized.jsonl" `
  --output-dir "E:\WordCloudGold\course_annotation_package_v1"
```

Builder فقط corpusای را می‌پذیرد که SHA-256 آن با verification metadata یکسان باشد. علاوه بر fingerprint کل corpus، SHA-256 تک‌تک textها، تعداد 30 source unit، split واحدها و 11 case group نیز validate می‌شوند.

Working package شامل:

- `package_manifest.json`: provenance، fingerprint، case index و split mapping برای pipeline؛
- `cases.jsonl`: متن‌های 11 case برای annotator، بدون نمایش tuning/holdout؛
- `annotator_A.jsonl` و `annotator_B.jsonl`: annotation مستقل اولیه با `complete=false` و relevance خالی؛
- `adjudication.jsonl`: working file برای مرحله adjudication؛
- `ANNOTATION_GUIDE_FA.md`: guideline انسانی.

این فایل‌ها عمداً contract `phase10-gold-v1` نیستند و field `adjudicated=true` تولید نمی‌کنند. Gold نهایی فقط پس از annotation انسانی مستقل و adjudication ساخته می‌شود.

Package باید خارج از repository نوشته شود. Model output، synthetic fixture و annotation نفر دیگر در annotation مستقل نباید به annotator نمایش داده شود.

