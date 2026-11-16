# Big Ben AI Pro — Backend

الخادم التشغيلي الحالي `app.py` يخدم الواجهة الخاصة `platform/index.html` ويستقبل TradingView Webhooks ويستخدم PostgreSQL في الإنتاج. ليس هذا ملف إعداد النموذج الأولي الجذري `server.py`.

```bash
python -m pip install -r platform/backend/requirements.txt
python platform/backend/app.py
```

الفحص `GET /healthz`، والواجهة `/dashboard`، والأحداث `POST /v1/tradingview/events`. الواجهة وواجهات API الخاصة محمية بمصادقة Basic؛ اسم المستخدم الافتراضي `bigben` وكلمة المرور في `BIGBEN_DASHBOARD_PASSWORD`. مفتاح Webhook مستقل في `BIGBEN_WEBHOOK_TOKEN` ولا يُحفظ في سجل الأحداث.

خدمة Render البديلة: https://bigben-ai-pro-rebound.onrender.com. مجموعة إعدادات الإنتاج الآمنة `bigben-ai-pro-production` تحتوي المتغيرات الأصلية التسعة بما فيها `DATABASE_URL` وكلمة المرور. لا تصدّر الأسرار إلى Git أو ملفات عامة. راجع `../../docs/RENDER_DEPLOYMENT.md` للحالة المؤكدة وخطوات التحويل.

يستخدم الخادم `PORT`، افتراضياً 10000، على `0.0.0.0`. التخزين المحلي/المؤقت لا يضمن دوام البيانات. لا توجد نقاط لتنفيذ أوامر الوساطة. التحليل الدوري يستخدم الشموع المغلقة ويعرض WAIT أو STALE أو INSUFFICIENT_DATA عند غياب الأدلة. لا يثبت نجاح فحص اتصال واحد تغطية Futures أو تسليم تنبيهات.

اختبارات Backend في `platform/tests`، والبحث في `research/tests`. احتفظ بملفات Pine والأدلة التاريخية؛ عنوان Webhook داخل التنبيهات القائمة لا يتغير تلقائياً بتغيير خدمة Render.
