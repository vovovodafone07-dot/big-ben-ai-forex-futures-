# الجدولة
workflow .github/workflows/daily-research.yml مضبوط يوميًا 02:17 UTC (06:17 مسقط).
أضيف timeout 20 دقيقة ومجموعة concurrency واحدة وحفظ artifact حتى مع الفشل.
اعتماد البيانات يُمرر فقط لتشغيل schedule أو workflow_dispatch؛ push يتحقق دون استهلاك المفتاح.
نجاح workflow لا يثبت نجاح بحث مرخص؛ راجع status داخل latest.json. awaiting_data_access حالة عائق وليست نتيجة باك تيست.
تشغيلات push ناجحة موجودة، ومنها Actions run 43396238352؛ schedule ببيانات مرخصة لم يُثبت.


## Existing-server research path
The existing Render service starts a bounded worker, refreshes three forex histories with persisted six-hour cooldown, then consumes up to 1000 stored closed M5 candles per symbol. It saves at most one research report per symbol/UTC day. No extra provider calls are made by research. Source and dataset hashes, trades, quality, risk, training/validation/holdout, task logs and the mandatory no-promotion decision are retained. Restart resumes from persisted reports and cooldowns. Missing history (<120 bars) creates no fabricated report. A sleeping/stopped free service cannot guarantee a wall-clock cron; first startup execution and an elapsed timer execution are distinct evidence. The legacy GitHub Barchart workflow remains separate and still needs its own licensed configuration.

## Durable execution evidence —14November
The existing six-hour worker now records each real cycle and individual stage timestamps in job_runs. A database lease prevents overlapping cycles; an expired RUNNING execution becomes INTERRUPTED, not success. COMPLETED means the stage function returned: inspect provider coverage and report references for data availability. A daily Arabic evidence report is inserted once per UTC day, with one Telegram attempt using the existing authorized channel (BIGBEN_DAILY_TELEGRAM_ENABLED=0 disables it). Failed notification acceptance is recorded and not automatically retried. Free-host sleep still prevents a guaranteed wall-clock execution. No external scheduler, paid worker or model call was added.
