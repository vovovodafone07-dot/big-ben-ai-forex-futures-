# Big Ben AI Pro — current status, 14 November 2026

Platform: https://bigben-ai-pro-api.onrender.com/#analyze
Live code: 7212e80a6fb263e6436f6c8581ab58b0c74e152b (PR20).
Render deploy: dep-dbrqi1lbedkc738hsjpg, live at 04:19 Muscat.
The owner chose to keep the service free and subsequently selected design A.

## Current release
- Implemented design A in HTML/CSS: navy right navigation, persisted recipient fields, chart beside reasons and paired full/scalp plans, actual CISD/SMT states and specialist review cards, responsive mobile layout. Generated mockup values are not production data.
- Extensible qualified instrument identifiers, market names, custom watchlist and discovered symbols. Adding a watchlist item does not create a TradingView alert or data license. Analyze filters by symbol before choosing its latest signal.
- Private Telegram Chat ID and international WhatsApp recipient settings; initial settings-load failures cannot silently erase existing recipients. Telegram messages contain both original target and alternative scalp1R with the same entry/stop.
- Official Meta template adapter implemented and tested, DISABLED by default. It needs an existing Business account, approved nine-parameter template, credentials and recipient. No account, keys, template, paid plan or billing was created/enabled. See WHATSAPP_CLOUD_SETUP.md. API acceptance is not delivery.
- New real BUY/SELL events trigger the shared analysis pipeline after webhook acknowledgment. Two concurrent tasks maximum; Gemini retains ten requests/day UTC, a five-minute evidence cache and no hidden retries. Nine deterministic evidence roles are separate from one model request containing four specialist sections. No broker execution or autonomous strategy changes.
- Historical SMT research measures synchronized M5 returns from stored Twelve Data candles, with at least60 return samples. It excludes gaps/open/future bars, identifies its separate historical feed, cannot override Pine and never claims live SMT confirmation.

## Pine and alert snapshots
Existing private script: revision10, title Big Ben AI Pro | Forex & Futures M5 | v6.4.3.
Strategy remains v6.4.1-sync; bridge v6.4.3-multiasset adds CISD/SMT telemetry and a general title. Trading rules and SMT settings are text-identical to the previous release.
All nine existing v10 snapshots saved and checked in the native UI: EURUSD,GBPUSD,USDJPY,NQ,MNQ,ES,MES,YM,6E. No new all-nine v6.4.3 delivery cycle has been verified.
Both original gold alerts remain unchanged; the duplicate MES alert is stopped, not deleted.
All nine delivered the21:40UTC13November cycle on bridge v6.4.2. No claim of a new nine-symbol v6.4.3 cycle during the closed market.

## Verification and limits
PR20 CI passed all six checks:121 backend +37 research tests and11 inline JS blocks, including Windows/Linux and isolated PostgreSQL. HTML container and unique-ID checks passed locally. Render is live; production storage HTTP200. Error-log query since deploy start returned no entries.
Design A was visually checked in native Chrome; actual screenshot: artifacts/design/design-A-live-desktop-2026-11-14.jpg. Mobile visual check remains pending.
Gemini previously returned valid Arabic reviews on MNQ and EURUSD and respected WAIT. A valid EUR/USD Twelve Data price response does not prove continuous live prices or futures licensing.
Official Fed/ECB feeds and BLS calendar have freshness/error metadata; there is no connected numeric consensus feed or invented future result.
The free PostgreSQL database is available and expires11December2026. Free Render can sleep.
Pine-rules RR2.5 research remains distinct from the older proxy RR3 reports. Profitability and bar-by-bar TradingView parity are unverified.
See REMAINING_BLOCKERS.md and evidence/design-a-deployment-2026-11-14.json.

Next release verified locally:122 backend +37 research tests. Corrected the owner’s actual source-qualified watchlist mappings, including COMEX_MINI:MGC1!, CME:MBT1!, CAPITALCOM:NAS100 and CAPITALCOM:SPX500; CFD and crypto remain distinct from futures. Watchlist evidence records13 symbols; this is not proof of alert coverage. Most recent Gemini production attempt returned HTTP503; deterministic analysis continued with WAIT. Four unavailable specialist cards make a failed review explicit.
