# الباك تيست
المحرك الحالي research/daily_agents.py نموذج اختراق مبسط، وليس نفس Pine v6.4.
يدخل من إغلاق إشارة ويقيم الشموع التالية، ويمنع التداخل ويصنف لمس الوقف والهدف في الشمعة نفسها ambiguous_both.
يفصل جزءًا تاريخيًا holdout ويقترح RR للاختبار فقط. ليست walk-forward مكتملة أو إثبات تحسن ربحية.
السبريد والعمولات والانزلاق وقيمة التيك والجلسات وتدوير العقود ليست محاكاة إنتاجية.
candle_quality.py يرفض ترتيبًا معيبًا وفواصل غير M5 وشموعًا غير مغلقة وOHLC غير صالح. يسجل الفجوات دون تعبئة اصطناعية أو ادعاء تقويم بورصة.
لا نتائج ربحية حقيقية منشورة. بيانات الاختبارات موسومة اصطناعية.


## Research report boundaries
The durable nine-role report runs the existing proxy breakout engine with lookback20/RR3/hold48, explicitly separate from live Pine v6.4.1 RR2.5. Trades and ambiguous/unresolved outcomes are persisted. RR candidates1.5/2/3/4 use only first60% training (>=30 resolved trades to select); next20% is validation and final20% is independent of selection. All promotions are rejected until Pine parity, realistic costs, session calendars and walk-forward are validated. Real provider candles do not make a simplified model an exact strategy backtest.

## Chronological walk-forward snapshot —14November2026
research/walk_forward.py evaluates up to4 nonoverlapping chronological test windows using expanding past-only training. RR candidates1.5/2/2.5/3 need at least30 resolved training trades; otherwise baseline2.5 remains. The final20% never selects RR. Continuous replay retains pre-window state and only scores entries inside each window; all assumptions are explicit. Source/engine/runner/dataset hashes are retained.

The dated snapshot used1220 real stored Twelve Data M5 candles for each of EURUSD/GBPUSD/USDJPY from the verified application export, with tick size from stored authenticated TradingView events. Each has4 folds and INSUFFICIENT_EVIDENCE;3 resolved OOS trades and0 resolved final-holdout trades per symbol. No profitability, net return or Pine parity conclusion is supported. Costs are unknown, no parameters are promoted, and no production Pine code is changed. This is a static dated report, not automatic daily walk-forward execution. The authenticated API fails closed when source/engine/runner hashes change.

Reproduce locally without any provider API request:
```powershell
python scripts/run_walk_forward_snapshot.py PATH_TO_VERIFIED_EXPORT.json --output NEW_REPORT.json
```

Next parity acquisition step: use the existing authorized TradingView chart CSV export, which includes chart OHLC and script plots per official documentation (https://www.tradingview.com/support/solutions/43000537255-how-to-export-chart-data/ and https://www.tradingview.com/pine-script-docs/faq/indicators/). Inspect account availability without upgrading or creating alerts. A downloaded CSV is only an input; same-feed alignment and bar-by-bar agreement must be measured separately. No CSV has been acquired in this release yet.
