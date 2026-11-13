# الباك تيست
المحرك الحالي research/daily_agents.py نموذج اختراق مبسط، وليس نفس Pine v6.4.
يدخل من إغلاق إشارة ويقيم الشموع التالية، ويمنع التداخل ويصنف لمس الوقف والهدف في الشمعة نفسها ambiguous_both.
يفصل جزءًا تاريخيًا holdout ويقترح RR للاختبار فقط. ليست walk-forward مكتملة أو إثبات تحسن ربحية.
السبريد والعمولات والانزلاق وقيمة التيك والجلسات وتدوير العقود ليست محاكاة إنتاجية.
candle_quality.py يرفض ترتيبًا معيبًا وفواصل غير M5 وشموعًا غير مغلقة وOHLC غير صالح. يسجل الفجوات دون تعبئة اصطناعية أو ادعاء تقويم بورصة.
لا نتائج ربحية حقيقية منشورة. بيانات الاختبارات موسومة اصطناعية.


## Research report boundaries
The durable nine-role report runs the existing proxy breakout engine with lookback20/RR3/hold48, explicitly separate from live Pine v6.4.1 RR2.5. Trades and ambiguous/unresolved outcomes are persisted. RR candidates1.5/2/3/4 use only first60% training (>=30 resolved trades to select); next20% is validation and final20% is independent of selection. All promotions are rejected until Pine parity, realistic costs, session calendars and walk-forward are validated. Real provider candles do not make a simplified model an exact strategy backtest.
