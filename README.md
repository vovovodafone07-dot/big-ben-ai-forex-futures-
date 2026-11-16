# Big Ben AI Pro — تحليل الفوركس والفيوتشرز

المنصة الحالية هي `platform/index.html` مع خادم `platform/backend/app.py`. تعرض الأدلة والتحليلات وتستقبل أحداث TradingView وتدعم Telegram، دون تنفيذ أوامر وساطة أو تغيير الاستراتيجية تلقائياً. التصميم الحالي Midnight/Neon عربي RTL؛ لا تستخدم أرقام أداء أو مستويات صفقات غير مستمدة من بيانات فعلية.

## الخدمة البديلة — 16 نوفمبر 2026

الرابط: https://bigben-ai-pro-rebound.onrender.com/dashboard

خدمة Render: `bigben-ai-pro-rebound`، المعرف `srv-dbt68qe1egvs73fhqbg0`، الفرع `main`، المنطقة Frankfurt، الخطة Free. نُسخت متغيرات الخدمة السابقة التسعة بالقيم الأصلية عبر مجموعة Render الآمنة `bigben-ai-pro-production`، بما فيها كلمة مرور المنصة ومفتاح Webhook واتصال قاعدة البيانات. لا توجد قيم سرية في هذا المستودع.

نشر الإعدادات `dep-dbt6dkt6e07s73biikf0` نجح على commit `0c25909e58cf39fc57ac1621802f2db6ca3b07e0`. فحص `/healthz` و`/healthz/storage` أعاد 200 مع PostgreSQL. `/dashboard` والمسارات الخاصة تعيد 401 بدون المصادقة، بدلاً من خطأ عدم تهيئة المنصة 503. هذا لا يعادل اختبار دخول مصادق أو تسليم تنبيه فعلي جديد.

الخدمة السابقة `bigben-ai-pro-api` محفوظة مؤقتاً حتى اكتمال قطع التحويل والتحقق وتأكيد الحذف النهائي. عنوانها الصحيح `bigben-ai-pro-api.onrender.com` يستجيب 200؛ العنوان المختلف `big-ben-ai-pro-api.onrender.com` يعيد 404 ولا يخص هذه الخدمة. لا تحذف قاعدة PostgreSQL المشتركة أو مجموعة البيئة عند حذف خدمة الويب.

## تشغيل التطبيق الحالي محلياً

يتطلب Python 3.10+ وNode لفحص JavaScript. أدخل الأسرار عبر بيئة خاصة، لا في أوامر محفوظة أو HTML أو Git.

```bash
python -m pip install -r platform/backend/requirements.txt
python platform/backend/app.py
```

الخادم يستمع إلى `0.0.0.0` والمنفذ `PORT`، افتراضياً 10000. نقطة الفحص `/healthz`، والواجهة `/dashboard`، واستقبال TradingView `POST /v1/tradingview/events`.

تحتاج الواجهة كلمة مرور `BIGBEN_DASHBOARD_PASSWORD` بطول 20 حرفاً على الأقل؛ اسم المستخدم الافتراضي `bigben`. يستخدم الإنتاج `DATABASE_URL`، بينما SQLite المحلي/المؤقت ليس بديلاً عن قاعدة دائمة. إعدادات التكاملات ومجموعة البيئة ومسار التحويل موثقة في [دليل Render](docs/RENDER_DEPLOYMENT.md).

## الحالة والقيود

الوكلاء التسعة والمراقب يعملون في وضع `live_analysis`، مع بقاء تنفيذ الوساطة معطلاً. نجاح فحص Twelve Data لطلب EUR/USD واحد لا يثبت بيانات لحظية متصلة أو ترخيص جميع عقود Futures. الرسائل والإعدادات المنقولة لا تثبت تسليم Telegram جديد. إعدادات WhatsApp الخمسة غير موجودة في الخدمة السابقة وتبقى غير مهيأة.

تغيير عنوان المستودع أو مجموعة البيئة لا يغير تلقائياً وجهة Webhook داخل تنبيهات TradingView. يجب نقل وجهة التنبيهات القائمة والتحقق من حدث حديث قبل حذف مستقبلها السابق؛ لا تنشئ تنبيهات مكررة ولا تعدل Pine لهذا الغرض. خطة Render المجانية قد تدخل الخمول، ولا تضمن تشغيل 24/7. تاريخ انتهاء PostgreSQL السابق الموثق 11 ديسمبر 2026 يحتاج إعادة تحقق، ولم يتغير بنقل خدمة الويب.

## الاختبارات

```bash
python -m unittest discover -s platform/tests -v
python -m unittest discover -s research/tests -v
python scripts/check_frontend.py
python -m compileall -q platform/backend platform/agent research
```

[الحالة الحالية](docs/CURRENT_PROJECT_STATUS.md) · [العوائق](docs/REMAINING_BLOCKERS.md) · [التقدم التاريخي](docs/IMPLEMENTATION_PROGRESS.md) · [حفظ البيانات](docs/DATA_PRESERVATION.md) · [TradingView](docs/TRADINGVIEW_INTEGRATION.md).

## النموذج الأولي التاريخي

الزوج الجذري `server.py` و`index.html` ليس مسار التشغيل الحالي، ولا يطابق عقد API الخاص بالمنصة. ليسا نسختين متطابقتين. حُفظا لتجنب كسر أي نشر قديم غير مفحوص؛ لا تستخدم تعليمات النموذج الأولي لنشر الخدمة البديلة. ملفات Pine والأدلة وتقارير الاختبارات المؤرخة ليست ملفات مكررة، وتبقى محفوظة لتتبع المصدر والرجوع.
