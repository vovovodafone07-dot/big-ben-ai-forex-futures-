# Big Ben AI — market data acceptance and no-fabrication contract

**Preferred licensed historical feed:** Barchart OnDemand (getHistory, type=minutes, interval=5).
Official docs: https://www.barchart.com/ondemand/api/getHistory
Instrument metadata: https://www.barchart.com/ondemand/api/getInstrumentDefinition

## Coverage gate — no untested guarantees
Markets to verify using the subscriber's API entitlement before marking as supported:
- FX spot: EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, USD/CHF and requested crosses
- CME equity futures: NQ / MNQ, ES / MES, YM / MYM
- CME FX futures: 6E and additional user watchlist contracts
- Optional crypto and metal instruments, only if contract/API coverage is confirmed

Barchart's product supports **Forex** and **Futures** as asset categories; this is NOT evidence of an authorized entitlement to every exchange/contract.
Provider-specific identifiers must be read from instrument metadata, never guessed from TradingView `tickerid`.

## Data pipeline
- `research/barchart_adapter.py` reads licensed M5 OHLC bars. Rejects malformed, out-of-order, truncated, unavailable or stale data.
- `research/run_provider_research.py` runs quality, risk, holdout validation, reviewer and parameter-hypothesis agents per tested symbol.
- Scheduled GitHub Action: `.github/workflows/daily-research.yml`, 02:17 UTC, manual trigger also available.
- GitHub Actions secret: `BARCHART_API_KEY`; GitHub Actions variable: `BIGBEN_BARCHART_SYMBOL_MAP`. Example **only after authoritative instrument lookup**: `{"EURUSD":"^EURUSD"}`.
- The protected dashboard endpoint `/api/data-sources` reports **configuration only**, not market entitlement.
- Output is an artifact `bigben-daily-research` containing aggregate JSON. Reports with missing access explicitly say `awaiting_data_access`.

## Compliance, safety and limits
No API key is stored in Pine, frontend HTML, or repository files. No broker order API.
Do not modify existing TradingView alerts or the running Pine indicator.
Barchart free trial and commercial feeds have specific permissions and may involve licensing/fees; user approval required before any paid subscription.
Research backtest is a labelled **breakout proxy**, not full Pine v6.4 signal parity. No real-time multi-market signal generator is claimed.
Never treat a result as valid before verifying true OHLC history, timestamp/session consistency, contract rolls, fees, slippage and sufficient out-of-sample trades.
Daily job produces hypotheses and review reports. It does **not** self-train an LLM, push strategy changes, or update TradingView automatically.

## Acceptance checklist
1. Provider credentials authorized and loaded in GitHub Actions, never in chat.
2. Explicit provider symbol mapping and exchange entitlement confirmed for every requested instrument.
3. Minimum 120 fresh, valid consecutive-or-session-gapped M5 bars; sufficient sample for meaningful holdout.
4. Distinguish success, partial coverage, failure and missing data in report.
5. Pine per-bar signal parity, walk-forward tests and human review required before shipping any candidate.
