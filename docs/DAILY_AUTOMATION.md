# الجدولة
workflow .github/workflows/daily-research.yml مضبوط يوميًا 02:17 UTC (06:17 مسقط).
أضيف timeout 20 دقيقة ومجموعة concurrency واحدة وحفظ artifact حتى مع الفشل.
اعتماد البيانات يُمرر فقط لتشغيل schedule أو workflow_dispatch؛ push يتحقق دون استهلاك المفتاح.
نجاح workflow لا يثبت نجاح بحث مرخص؛ راجع status داخل latest.json. awaiting_data_access حالة عائق وليست نتيجة باك تيست.
تشغيلات push ناجحة موجودة، ومنها Actions run 43396238352؛ schedule ببيانات مرخصة لم يُثبت.


## Existing-server research path
The existing Render service starts a bounded worker, refreshes three forex histories with persisted six-hour cooldown, then consumes up to 1000 stored closed M5 candles per symbol. It saves at most one research report per symbol/UTC day. No extra provider calls are made by research. Source and dataset hashes, trades, quality, risk, training/validation/holdout, task logs and the mandatory no-promotion decision are retained. Restart resumes from persisted reports and cooldowns. Missing history (<120 bars) creates no fabricated report. A sleeping/stopped free service cannot guarantee a wall-clock cron; first startup execution and an elapsed timer execution are distinct evidence. The legacy GitHub Barchart workflow remains separate and still needs its own licensed configuration.
