# مزامنة Pine مع المنصة

## المنفذ فعليًا
- أحدث أساس موجود كان v6.4 Review؛ حُفظ كما هو في المستودع كمرجع.
- أُنشئ Big_Ben_AI_Hybrid_M5_v6_4_1_Synced.pine من ذلك الأساس.
- تحديث الملف الخاص القديم في TradingView، المحفوظ باسم Big Ben AI Hybrid M5 v6.1 Pro Webhook، إلى مراجعة 8؛ عنوان المؤشر الجديد v6.4.1 Synced Bridge.
- نجح التجميع والإضافة إلى الشارت. أبقيت نسخة الشارت v6.3 مخفية كمرجع دون حذفها، والنسخة الجديدة مرئية.
- أعيد استخدام اعتماد الجسر القائم من الذاكرة في إعداد النسخة الجديدة، دون طباعة قيمته أو حفظه في الكود.

## التوافق
RR الافتراضي 2.5 وminEvidence=1، مطابقان لإعدادات الشارت المرصودة. فلاتر HA وATR الجديدة opt-in ومعطلة افتراضيًا. إصلاح SMT الموجود في v6.4 متاح عند تمكين SMT؛ لا يُدعى تطابقه مع v6.3 عند تغيير هذا الخيار.
أُضيف strategy_version/timeframe/tick_size إلى كل من BUY/SELL وHEARTBEAT، مع إبقاء bigben.v1 وevent_id والتوكن والهدف الأصلي.
أُخفي عرض input التوكن في status line/data window باستخدام display.none؛ يظل مرئيًا لصاحب الحساب في إعداداته، فلا تشارك صورها.

## مطابقة المصدر
current_strategy.json يحدد ملف المصدر وبصمة SHA-256 وعنوانه ونسخته. /api/pine/current يقرأ المصدر نفسه ويتحقق من البصمة، ويرفض الخطأ بـ503 بدل عرض نسخة خاطئة. تجري تسوية نهايات الأسطر عبر read_text لدعم Windows وLinux.
السكالب يعرض strategy_version من الحدث؛ غيابها يوسم unreported ولا تُنسب إشارة قديمة للنسخة الجديدة.

## الاختبار والحالة
64 اختبار خلفية محليًا PASS بعد إضافة اختبارات سجل المصدر وHTTP والبيانات الجديدة. فحص JavaScript يراجع النسخة الحالية. لا باك تيست مطابق أو إثبات ربحية.
اختبار الجسر السابق أثبت v6.3؛ اختبار v6.4.1 الحي يحتاج تحديث نسخة التنبيه المحفوظة. توقف التحكم بـEscape بعد حفظ الكود سابقًا، والمالك طلب الآن الاستكمال دون لمس النافذة. لا تعتبر التنبيه القديم محدثًا بمجرد حفظ المصدر.

## النشر المؤكد
دُمج PR #7 إلى commit ce5e2d0bd52edc4ffc7487a90c4e6a8e5600710a. نشر dep-dbrkpretlv9c73au4rdg أصبح live، ونجح فحص PostgreSQL بعده. CI run 43475682638 نجح على Windows وLinux وPostgreSQL؛ 64 اختبار خلفية و15 بحث، و6 كتل JavaScript.

## مسودة تحديث تنبيه قائم
أُعد تعديل تنبيه MES الأقدم بدل إنشاء تنبيه جديد: المصدر v6.4.1، اسم Big Ben Pro | MES M5 | v6.4.1، Any alert() function call، M5، Webhook فقط، رابط Render نفسه، وجدول 24/7. زر Save لم يُضغط بعد؛ يوجد طلب تأكيد وقت التفعيل لتحديثه وإيقاف نسخة MES المكررة مع إبقاء الذهب.


## Final verified cutover — 2026-11-13 18:00 UTC
This section supersedes earlier pending-cutover or confirmation notes. PR #7 is merged and deploy dep-dbrkpretlv9c73au4rdg is live at ce5e2d0bd52edc4ffc7487a90c4e6a8e5600710a. The existing MES alert now uses v6.4.1-sync revision 8; the duplicate legacy MES alert is stopped manually, not deleted. Both original gold alerts remain active and unchanged. TradingView confirmed delivery of the 18:00 UTC v6.4.1-sync heartbeat; Render accepted it at 18:00:13.032726795Z with 202 and no duplicate observed in the check window. CI: 64 backend +15 research tests, Windows/Linux, isolated PostgreSQL; frontend JS checks passed. Live BUY/SELL and Telegram delivery remain unverified. See evidence/pine-v6-4-1-delivery-2026-11-13.json.
