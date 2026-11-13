# البنية الفعلية
TradingView Pine -> HTTPS /v1/tradingview/events -> تحقق توكن ومخطط -> events في PostgreSQL أو SQLite تطويري.
الخلفية platform/backend/app.py تخدم الواجهة platform/index.html وواجهات خاصة بمصادقة Basic خلف HTTPS.
analysis.py يصف Heartbeat. scalping.py يحسب بديلًا حسابيًا من مستويات الإشارة. كلاهما لا ينفذ أوامر.
Telegram يرسل الرسالة بعد الرد على TradingView. العامل الحالي خيط daemon؛ ضمان تسليم دائم وإعادة محاولة محفوظة ما زالا عملًا متبقيًا.
research/ منفصل عن الإنتاج؛ محرك اختراق مبسط ومراجعة حتمية ومزود Barchart مرخص عند ضبطه.
الهجرة الإضافية migrations.py تحفظ received_at مع فهارس وسجل schema_migrations. لا حذف ولا إعادة كتابة للتاريخ.
