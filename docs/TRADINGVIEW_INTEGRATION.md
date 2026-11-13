# TradingView
المصدر محفوظ في tradingview/ مع backup v6.3 وReview v6.4. لا تغيير على Pine ضمن تحديث السكالب.
الواجهة تستقبل المستوى الأصلي؛ السكالب حساب خلفي مستقل في العرض والتنبيه فقط.
رابط الاستقبال الحالي https://bigben-ai-pro-api.onrender.com/v1/tradingview/events.
Any alert() function call هو النوع التاريخي. لا تعِد إنشاء التنبيه دون سبب مثبت؛ تنبيهات TradingView تحفظ نسخة الكود عند الإنشاء.
Heartbeat لا يخلق صفقة. لا توجد API مدعومة مفترضة لنشر Pine أو إدارة التنبيهات.
التحقق المتبقي: جلسة حساب مدعومة، سجل تنبيه فعلي، مطابقة event_id في التخزين، ومعرفة الرمز ووقت المصدر.

## فحص الحساب في 13 نوفمبر 2026
استُعيد الوصول إلى جلسة TradingView المسجلة. شارت MES1! على 5 دقائق يعرض Big Ben AI Hybrid M5 v6.3. توجد تنبيهات BUY وSELL نشطة على XAUUSD في القائمة الظاهرة. لم تُعدّل الاستراتيجية أو هذه التنبيهات.
تم تجهيز مسودة MES M5 باسم Big Ben Pro | MES M5 | JSON Bridge، Any alert() function call، Webhook فقط، على الرابط الحالي. الحفظ معلق على تأكيد المالك عند خطوة Create طبقًا لمهارة التحكم بالمتصفح. ظهر تحذير TradingView لاحتمال repaint لحسابات المؤشر الحالي؛ لم يُتجاهل أو يُصلح بتغيير الاستراتيجية.
ملاحظة خصوصية: إعداد توكن المؤشر يظهر ضمن بيانات العرض واسم التنبيه الافتراضي. استُخدم اسم جسر مخصص بلا إعدادات، وتُحجب سلاسل الاعتماد من المخرجات. لا تحفظ قيمته في التوثيق.

## تحقق حي — 13 نوفمبر 2026، 21:00 مسقط
وافق المالك على حفظ تنبيه MES M5 بشرط Any alert() function call إلى Webhook الحالي فقط. ظهر التنبيه Active، وأكد سجل TradingView حدث HEARTBEAT للرمز CME_MINI:MES1! عند 17:00 UTC، وقبله Render عند 17:00:30.116 UTC برمز 202. وصلت نسخة مطابقة برمز 200 وduplicate=True، دون إنشاء حدث آخر.
أثناء استعادة المسودة أُنشئت نسخة إضافية؛ يوجد حاليًا تنبيهان مطابقان نشطان. أُرسل طلب تأكيد لإيقاف الأحدث فقط، دون حذف أو تغيير تنبيهي الذهب، وما زال الرد معلقًا. لا توقف أي نسخة قبل وصول التأكيد. لم تتغير استراتيجية Pine؛ لم يُثبت تسليم BUY/SELL أو Telegram حي بهذا الاختبار.
الدليل دون توكن: docs/evidence/tradingview-mes-delivery-2026-11-13.json.


## Final verified cutover — 2026-11-13 18:00 UTC
This section supersedes earlier pending-cutover or confirmation notes. PR #7 is merged and deploy dep-dbrkpretlv9c73au4rdg is live at ce5e2d0bd52edc4ffc7487a90c4e6a8e5600710a. The existing MES alert now uses v6.4.1-sync revision 8; the duplicate legacy MES alert is stopped manually, not deleted. Both original gold alerts remain active and unchanged. TradingView confirmed delivery of the 18:00 UTC v6.4.1-sync heartbeat; Render accepted it at 18:00:13.032726795Z with 202 and no duplicate observed in the check window. CI: 64 backend +15 research tests, Windows/Linux, isolated PostgreSQL; frontend JS checks passed. Live BUY/SELL and Telegram delivery remain unverified. See evidence/pine-v6-4-1-delivery-2026-11-13.json.


## Nine-symbol production cutover — 2026-11-13 19:15 UTC
All nine requested symbols have active v6.4.1 revision8 M5 alerts (RR2.5, Any alert(), current Webhook only). TradingView confirmed delivery for all nine in the same19:15 bar and Render recorded nine202/nonduplicate requests. See evidence/expanded-alerts-2026-11-13.json. Gold alerts are unchanged, legacy duplicate MES is stopped, and the original MES chart/layout was restored and saved. No real BUY/SELL or live trade Telegram delivery occurred during this verification.
The live analysis page displayed all nine source closes/biases, but the embedded NQ widget was denied. Official widget data FAQ states that such symbols cannot be shown in widgets and a user subscription does not change widget permissions: https://www.tradingview.com/widget-docs/faq/data/. Pending UI correction uses an explicitly labeled forex default and direct futures chart links while keeping actual webhook analysis independent.
