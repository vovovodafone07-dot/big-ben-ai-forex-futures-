# تشغيل Big Ben عبر TradingView — Forex وFutures

## الحقيقة التشغيلية

Big Ben يستقبل من TradingView إشارات Pine وHeartbeat فقط. هذا المسار يعطي إشارات حية للرموز التي أنشأت لها Alerts، لكنه ليس WebSocket عاماً لكل Watchlist. لكي تُراقب Forex وFutures، يجب إنشاء Alert لكل رسم/رمز مطلوب أو ربط مزود Market Data مستقل يدعم البث.

تنفيذ الوساطة يبقى معطلاً دائماً؛ المنصة تحليل وتنبيهات فقط.

## 1. إنشاء رمز Webhook جديد

ولّد رمزاً عشوائياً محلياً، من دون إرساله للمحادثة:

```bash
python3 /home/ubuntu/skills/bigben-live-tradingview-workflow/scripts/generate_webhook_token.py
```

انسخ الناتج إلى مدير أسرار مؤقت، ولا تحفظه في Git. بما أن الكود الحالي يقبل رمزاً واحداً، يجب تنفيذ التحديث في Render ثم تحديث TradingView Alerts مباشرة.

## 2. تحديث Render

في Render افتح الخدمة `bigben-ai-pro-rebound` ثم **Environment**. حدّث المتغير:

```text
BIGBEN_WEBHOOK_TOKEN=<الرمز الجديد>
```

احفظ التعديل ثم نفّذ Deploy/Restart. لا تضف الرمز إلى `render.yaml` أو GitHub. لا تعتبر حفظ المتغير دليلاً على عمل Webhook؛ تحقق من `/healthz/integrations` ومن حدث حقيقي.

## 3. تحديث TradingView

لكل رمز، افتح الرسم، ثبّت نسخة Pine الحالية، ثم أنشئ Alert على المؤشر واختر **Any alert() function call**. فعّل Webhook URL:

```text
https://bigben-ai-pro-rebound.onrender.com/v1/tradingview/events
```

اترك Message الذي يبنيه Pine؛ لا تلصق نصاً يدوياً. يجب أن تحتوي الحمولة على `token`, `schema`, `event`, `event_id`, `symbol`, `time`، وتفاصيل Entry/SL/TP عند BUY/SELL.

كرّر الإعداد للرموز المطلوبة، مثل `OANDA:EURUSD`, `FOREXCOM:XAUUSD`, `CME_MINI:MNQ1!`, `CME_MINI:NQ1!`, و`CME_MINI:ES1!` بحسب الرموز التي تملك عليها تغطية TradingView.

## 4. اختبار آمن

أرسل Heartbeat حقيقياً من TradingView وانتظر إغلاق الشمعة. في TradingView يجب ظهور `Webhook successfully delivered`. بعد ذلك افحص `/api/integrations` داخل لوحة المنصة، وتحقق من:

- `heartbeat_recent=true`
- `last_heartbeat` يحتوي الرمز والوقت
- `recent_event_verified=true`
- `live_feed_verified` يبقى `false` ما لم يوجد مزود بث مستمر مثبت

لا ترسل BUY/SELL اصطناعياً إلى الإنتاج؛ قد يحفظه الخادم ويرسل Telegram. الصفقة لا تظهر إلا من BUY/SELL حقيقي حديث وبمستويات صالحة.

## 5. Agent Mode

Agent Mode للمنصة يتطلب في Render:

```text
BIGBEN_SIGNAL_ANALYSIS_ENABLED=1
BIGBEN_AGENT_WATCHDOG_ENABLED=1
broker_execution=disabled
```

الوكلاء التسعة يعملون عند وصول BUY/SELL حديث. Heartbeat يثبت النبض فقط ولا يولّد صفقة. التعلم evidence-only ولا يعدّل Pine تلقائياً.

## 6. مزود Market Data مستقل

Twelve Data الحالي لا يثبت بث Futures كاملاً. Massive هو المرشح الموحد بعد توفير اشتراك ومفتاح وترخيص؛ Databento/CME خيارات قوية للفيوتشرز وقد تتطلب مصدر Forex منفصلاً. لا تضبط `BIGBEN_MARKET_PROVIDER` قبل إضافة adapter واختباره، ولا تغيّر `live_feed_verified` يدوياً.

عند جاهزية مفتاح المزود، أضفه في Render كـSecret مثل `MASSIVE_API_KEY`، ثم اختبر provider timestamp وstream reconnect وentitlement ورمز Forex ورمز Futures قبل الإعلان عن Live.
