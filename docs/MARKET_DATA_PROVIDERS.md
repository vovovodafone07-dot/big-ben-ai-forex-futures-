# البيانات
Twelve Data موجود في المسار القديم وPro. المالك أكد حسابًا قائمًا ووافق على استخدام مفتاحه الحالي دون شراء.
الخلفية تدعم TWELVE_DATA_API_KEY وTWELVEDATA_API_KEY، بأولوية الاسم الأول. لا تضعهما معًا بقيم مختلفة.
مفتاح مضبوط لا يثبت الصلاحية، ووقت جلب /price ليس وقت سعر البورصة. realtime_verified يبقى false.
Barchart adapter موجود للبحث؛ يحتاج مفتاحًا وخريطة رموز صريحة. لا توحد فوركس وعقود futures بتخمين الاسم.
الرموز المطلوبة EURUSD/GBPUSD/USDJPY/NQ/MNQ/ES/MES/YM/6E لم تُثبت تغطيتها بهذا العمل.
لا توجد مقارنة أسعار اشتراكات جديدة أو توصية بشراء مزود؛ يلزم فحص الوثائق والخطة الفعلية عند توفر الدخول.

المفتاح موجود في Render بحسب فحص الإنتاج. فحص market_probe.py يطلب EUR/USD مرة واحدة فقط عند بدء الخادم، مهلة 8 ثوانٍ ودون إعادة محاولة. لا يطبع السعر أو المفتاح أو رسالة المزود الخام. CONNECTED تعني استجابة سعر صالحة لهذا الطلب، مع realtime_verified=false وfutures_coverage_verified=false دائمًا.


## M5 history adapter
platform/backend/market_history.py requests /time_series with interval=5min, timezone=UTC, order=asc, outputsize=1000, timeout 10 seconds, response cap 2MB. Only three explicitly mapped forex pairs are requested. Metadata must match Physical Currency, exact symbol, UTC and 5min. Current incomplete candle is excluded; malformed, future, duplicate and unordered batches are rejected. Gaps are calendar-unverified and never filled. Persistence is idempotent on provider/symbol/time. Existing bars are retained on conflict. Coverage reads stored bounds even after an unsuccessful refresh.
One server thread runs at startup and every six hours while active, with a persisted six-hour per-symbol cooldown and no retries. The free service may sleep; this is not a guaranteed cron schedule. Futures require licensed contract metadata; they are reported UNKNOWN, provider_tested=false, rather than substituted or marked unavailable without a test. Source: https://twelvedata.com/docs and https://support.twelvedata.com/en/articles/5745849-timezones.


## Verified forex metadata correction
A real public-demo EUR/USD /time_series request returned meta symbol/interval/currency_base/currency_quote/type=Physical Currency and no exchange_timezone. The adapter now permits the omitted optional timezone for forex with an explicit timezone=UTC request (forex defaults to UTC per provider documentation), and still rejects an explicitly conflicting zone. This fixes the observed instrument_metadata_mismatch; actual account history retrieval remains to be retested after deployment.
