# Remaining work and verification limits —14November2026

## Account/browser work
1. All nine existing snapshots were saved at revision10/v6.4.3. Verify actual new market delivery; preserve gold alerts and the stopped MES duplicate.
2. Actual desktop design A screenshot was captured. Complete the mobile visual check. Previous browser URL-confidence enforcement stopped tab changes. Use only supported native browser control and stop if enforcement stops the turn.
3. Compare the owner's TradingView watchlist with actual alert coverage. Qualified symbol support is open, but a symbol in a watchlist is not an active webhook alert or a data subscription. Do not silently substitute CFDs for futures or purchase subscriptions.
4. WhatsApp Cloud API adapter is implemented, tested and disabled by default. Actual connection needs an existing Business account/sender, approved compatible template, secret credentials and recipient. Configure only through supported account access; do not create charges under broad authorization. Manual sharing works independently. Provider acceptance is not device delivery; a delivery callback is not implemented.

## Real-data acceptance
- Verify automatic specialists and Telegram paired-plan delivery with a NEW real signal; do not fabricate a trade to test the pipeline. Earlier Telegram connection test succeeded, but full real-signal delivery was not proven.
- Independent futures history/realtime coverage, licensing, contract rolls and calendars remain unverified. A Twelve Data EUR/USD probe and stored forex candles have a narrower scope.
- Historical paired-return SMT research is implemented for available matching stored data. It is a separate-feed historical observation, not current Pine SMT confirmation. Candidates for other markets need synchronized data and measured validation; preserve the existing Pine SMT setting.
- Pine-rules RR2.5 replay is implemented with rejection logs, but bar-by-bar parity, realistic costs/fills, sessions/rolls, large out-of-sample validation and the unavailable reference video remain unresolved. Older proxy RR3 reports are separate.
- Learning is an evidence review with bounded model commentary, not verified training or autonomous strategy promotion. Proposed changes need measured independent validation.
- Official Fed/ECB news and BLS calendar are connected with freshness/error status. No numeric consensus feed is connected. Future news scenarios are conditional.

## Operational choices
- Owner explicitly chose free Render; sleep and non-guaranteed schedules are accepted constraints, not pending upgrade approval.
- Free PostgreSQL expires11December2026. Arrange preservation/migration before expiry without opening the external IP allowlist or introducing unapproved costs.
- Some TradingView alert expiries were observed on9December2026. Review renewal before expiry.
- Gemini uses the existing free-tier project with10 request reservations/day UTC, five-minute cache and no automatic retries. Deterministic analysis continues without a model response.
- Never print secrets, provider error bodies, webhook tokens or database URLs. Keep source/alert snapshot versions separate. No broker execution.

Workspace release in progress: draft storage/diff/export and per-symbol notes are implemented; candidate compilation, experiments, independent validation and release workflow remain unverified. Daily worker execution ledger and reports are implemented; production run and notification proof still required. No claim that a startup cycle proves a full elapsed six-hour cycle.

Owner decision: nine additional TradingView alerts are deferred. Meta Business currently requires owner login; this is a concrete authentication dependency for WhatsApp, not a generic missing permission. New application-data export/restore support is being tested; actual export and a hosting migration remain separate.

Owner deferred WhatsApp as well as the nine new alerts. Do not continue Meta setup or request sign-in again unless explicitly resumed; continue independent verification/research.

Production application snapshot download and new-local-database restore are verified, including all17 tables/4129rows; this does not renew/migrate Render PostgreSQL or create recurring offsite backups. Walk-forward protocol has run on the available three forex histories, but sample sizes are insufficient; larger licensed histories, costs and same-feed Pine parity remain required. WhatsApp and additional alerts remain explicitly deferred.

## Focused audit — 16 November 2026

The live service is healthy in `live-analysis-alerts-only`; broker execution remains disabled. A separate endpoint audit confirmed that the private APIs and `/api/events.csv` require Basic Auth, while the TradingView webhook requires its independent token. The remaining blockers are evidence and operations, not an observed private-route exposure: continuous realtime data, licensed Futures coverage and rolls, same-feed Pine parity, larger cost-aware out-of-sample research, repeated production worker/notification proof, physical mobile/Safari validation, and recurring offsite backup. The Futures coverage inventory now includes every contract in `backend/instruments.py`, but each remains `UNKNOWN` until a licensed provider test proves access. The prioritized record is `docs/READINESS_AUDIT_2026-11-16.md`.
