# قرار مزود بيانات السوق — 2026-11-16

## القرار

لا يتم استبدال Twelve Data في الإنتاج بمزود آخر دون مفتاح API وترخيص بيانات مؤكد. المرشح الموحد الذي يغطي متطلبات المشروع هو **Massive**:

- يعلن عن بث WebSocket للفوركس مع quotes وminute/second aggregates.
- يعلن عن نحو 1,200 زوج عملات ضمن اشتراك العملات.
- يعلن عن بيانات Futures لحظية وتاريخية لأسواق CME وCBOT وNYMEX وCOMEX، مع عقود مستمرة وعمق سوق حسب الخطة.
- يحتاج اشتراكاً وصلاحية بيانات؛ لا يوجد دليل أن التغطية الكاملة اللحظية للفوركس والفيوتشرز مجانية إلى الأبد.

**Databento** هو الخيار الأقوى للفيوتشرز المرخصة وتغطية CME/CBOT/COMEX/NYMEX، لكنه ليس بديلاً موحداً للفوركس الفوري؛ لذلك سيحتاج إلى مصدر FX ثانٍ إذا اختير.

## TradingView والرموز التي أضافها المستخدم

إضافة رمز داخل TradingView لا تمنح الخادم API للوصول إلى قائمة الحساب أو بيانات البورصة. المسار الصحيح هو:

1. TradingView يرسل Alert JSON موثقاً بالـWebhook.
2. الخادم يحفظ `symbol` الوارد في الحدث.
3. `/api/instruments` يضيف الرموز المرصودة إلى الكتالوج، وتعرضها الواجهة ديناميكياً.
4. يمكن للمستخدم إدخال أي رمز TradingView مؤهل بصيغة `EXCHANGE:TICKER`.

هذا موجود في الكود الحالي؛ ظهور XAUUSD في Alerts يثبت أن TradingView أرسل الرمز، لكنه لا يثبت وحده اشتراك بيانات API مستقل.

## ما تم التحقق منه

- TradingView أظهر `Webhook successfully delivered` عدة مرات، مع Heartbeat حديث.
- الإنتاج ما زال يعلن أن Twelve Data نفّذ probe محدوداً لـEUR/USD فقط، وليس continuous feed.
- لا يوجد في بيئة التطوير مفتاح `MASSIVE_API_KEY` أو `DATABENTO_API_KEY`، لذلك لا يمكن تفعيل مزود جديد أو اختبار اتصاله فعلياً.
- لا يتم اختلاق أسعار Futures أو تحويل حالة `realtime_verified` إلى true قبل وصول بيانات حية موثقة.

## خطة التفعيل الآمنة

عند توفير اشتراك مزود مناسب ومفتاحه عبر Render Secrets، يضاف adapter منفصل لمزوّد البيانات، مع:

- `MASSIVE_API_KEY` و`BIGBEN_MARKET_PROVIDER=massive` عند اختيار Massive.
- اشتراك WebSocket منفصل للفوركس والفيوتشرز.
- تحويل رموز TradingView إلى رموز المزود دون اختلاق alias.
- freshness وheartbeat وprovider timestamp وentitlement checks.
- إيقاف التحليل وإظهار WAIT عند غياب البيانات أو انتهاء صلاحية الرمز.
- إبقاء TradingView Webhook مصدراً مستقلاً للإشارات وعدم تفعيل تنفيذ الوساطة.

حتى تنفيذ هذه الخطوات، Twelve Data يبقى مصدراً تاريخياً محدوداً فقط، وTradingView يبقى مصدر الإشارات المرصودة، ولا تُعرض المنصة على أنها بث سوق API كامل.

## المصادر

- [1] https://massive.com/currencies "Massive Currencies data"
- [2] https://massive.com/docs/websocket/forex/overview "Massive Forex WebSocket overview"
- [3] https://massive.com/futures "Massive Futures data"
- [4] https://databento.com/futures "Databento Futures data"
- [5] https://databento.com/docs/api-live "Databento Live API"
- [6] https://www.cmegroup.com/market-data/real-time-futures-and-options-data-api.html "CME Real-Time Futures and Options Data API"
- [7] https://www.tradingview.com/data-coverage/ "TradingView data coverage and exchange fees"
