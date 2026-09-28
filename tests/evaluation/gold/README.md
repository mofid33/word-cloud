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
