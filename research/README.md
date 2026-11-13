# Big Ben AI — Daily multi-agent research lab

## Implemented
- Dashboard **Strategies → مختبر الكود والوكلاء** has a local-only Pine draft textarea and links to versioned scripts and GitHub Actions. Draft text is not persisted to the server.
- Four deterministic research roles in `research/daily_agents.py`: quality, risk, historical holdout validation, reviewer.
- GitHub Actions `.github/workflows/daily-research.yml` runs daily at 02:17 UTC and via manual dispatch. It uploads a JSON report artifact; it never commits or deploys changes.
- It requires **real** M5 historical OHLC CSV at `research/data/market_m5.csv` with `time,open,high,low,close` columns in chronological order and at least 120 valid candles. Do not commit licensed/private data without permission.
- Without data, report explicitly says `awaiting_real_ohlc_data`; no fabricated trades.

## Critical limitations
- The research breakout algorithm is a **proxy**, not a Pine v6.4 engine or identical implementation of its HTF/SMT/ICT logic.
- CSV bars do not include bid/ask, spread, fees, slippage or tick-level order of SL/TP touches. Same-bar collisions are ambiguous.
- Validation is a single chronological 70/30 holdout; walk-forward, cross-market, and independent Pine signal parity tests are still needed.
- No autonomous LLM learning or code-writing agents have been installed. The roles are deterministic analysis modules.
- No auto-updates to TradingView, live alerts, production Render services, or broker accounts.
- Proposed modifications must pass reproducible out-of-sample testing and human approval.
- A scheduled GitHub Action can be delayed/disabled by GitHub; inspect Actions for the actual run.

## Next development
1. Connect authorized historical data provider for FX/futures symbols and contract rollovers.
2. Implement faithful Pine signal replication and compare signals bar-by-bar.
3. Add walk-forward optimization with fees and cross-market holdout.
4. Store agent proposals and evaluation results in authenticated database; review and approve before publishing a new candidate.
