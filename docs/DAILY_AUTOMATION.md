# الجدولة
workflow .github/workflows/daily-research.yml مضبوط يوميًا 02:17 UTC (06:17 مسقط).
أضيف timeout 20 دقيقة ومجموعة concurrency واحدة وحفظ artifact حتى مع الفشل.
اعتماد البيانات يُمرر فقط لتشغيل schedule أو workflow_dispatch؛ push يتحقق دون استهلاك المفتاح.
نجاح workflow لا يثبت نجاح بحث مرخص؛ راجع status داخل latest.json. awaiting_data_access حالة عائق وليست نتيجة باك تيست.
تشغيلات push ناجحة موجودة، ومنها Actions run 43396238352؛ schedule ببيانات مرخصة لم يُثبت.
