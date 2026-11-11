# Big Ben AI v5.2 — Audit and integration plan

Source: user-supplied `Big Ben AI | TradingView Only v5.2`. Original is preserved outside this development branch.

## Verified by static review (not TradingView compilation or backtest)
- M5-only signals: `timeframe.period == "5"`.
- BUY/SELL trigger on breakout candle close, without retest.
- HTF trend uses previous closed M15/H1/H4 bars. D1 is displayed but not used in signal filter.
- `Balanced` bypasses `minStopATR` and `maxStopATR` checks entirely.
- `cooldownBars=0` permits another signal on the exit bar if a qualifying breakout occurs; this must be specified and tested.
- Entry assumed at signal close; SL/TP tracking begins the next bar; SL wins ties when both levels touched.
- `showClosedLevels` does not keep every historical trade: a new entry deletes the prior set of level objects.
- No webhook/JSON integration, external news, ML, or broker execution.
- No CISD/Turtle Soup/QM/SMT implementation in this version.
- Uploaded text is Markdown-formatted with bold markers and HTML spaces, not directly paste-ready Pine code.

## Build order
1. Normalize user source to compilable Pine in a separate versioned file, preserve original.
2. Add stable JSON `alert()` payloads (schema version, symbol, timeframe, event ID, timestamp, side, entry, SL, TP, RR, reasons). Never embed API secrets in Pine.
3. Build authenticated read-only webhook ingestion, strict schema validation, idempotency, replay protection and structured logs. Fix existing 400 rejects by testing actual TradingView payloads.
4. Add durable storage for symbols, signals, outcomes, evidence, economic calendar events, alert channels, and model versions.
5. Integrate licensed live market feeds for supported futures contracts and forex pairs; verify symbol mapping and timestamp freshness.
6. Add news ingestion and event reminders; evaluate economic surprises alongside price reaction, with explicit data provenance.
7. Add Telegram and WhatsApp Business messaging with opt-in, secure credential storage, delivery status and retries.
8. Introduce deterministic CISD/Turtle Soup/QM/SMT detectors as separately testable modules; avoid requiring every detector to agree.
9. Train an offline model on properly labeled outcomes with chronological holdouts; publish only after walk-forward evaluation and approval.
10. Add private authentication, least privilege, rate limits, monitoring, backup/recovery, and load testing before production deployment.

## Important constraints
- Pine Script cannot directly consume an external AI model's live decision.
- TradingView watchlist synchronization and alert creation need separate feasibility verification; do not promise official APIs where none are confirmed.
- Never execute real trades or enable broker order routing.
- Do not deploy publicly or spend money without explicit authorization.
