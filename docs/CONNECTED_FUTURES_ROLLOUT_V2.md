# Connected-symbols and futures rollout (Arabic-first, no broker orders)

## New module
`platform/backend/connected_symbols_v2.py` is an additive, fail-closed **core**, not a deployed API or real futures feed.
`platform/tests/test_connected_symbols_v2.py` contains deterministic unit tests.

## Required integration into the existing service

1. Do not replace `connected_market.py` by a static 8-contract watchlist. Build database rows
   from the actual enabled symbol registry and verified matching-provider feed attestations.
   Set `enabled`, `provider_verified`, `licensed`, `venue_verified`,
   `contract_verified`, `verified_contract`, `last_closed_m5` from verifiable
   evidence only, never from the request body.
2. For Futures, subscribe to and verify actual expiry-specific OHLC (e.g., NQZ26)
   and keep the continuous symbol for chart display only. CFDs are not substitutes.
   The module does not fetch quotes or prove the provider's entitlement.
3. Add authenticated GET /v1/connected-symbols that returns `verified_connected(records)`
   plus explicit Arabic reasons for excluded configured instruments on a separate diagnostic endpoint.
   Replace free-text picker on the existing Analyze screen with a `select` populated from
   that endpoint. On selection, request existing native instant analysis, cancel stale
   response rendering, and display the actual selected contract.
4. Before trade-only Telegram publishing, call `can_send_trade` after rechecking
   the venue's session status (including exchange holiday / maintenance windows),
   a matching-provider *live* quote heartbeat, exact expiry, and M5 closure.
   A recently stored candle alone must not be treated as proof of market open.
5. Reuse `instant_telegram.py` for persistence and delivery; the existing
   `native_telegram_alerts` table is the actual durable dedup mechanism.
   Integrate `setup_fingerprint` only after migration / backwards-compatibility
   review. Do not introduce a second independent trade alert sender.
6. Route `READY` trade-only messages into the trade destination; technical/newsy
   analysis into separate destinations/threads. Persist stable event IDs and delivery
   state before sending; webhook retries must not fan out duplicates.
7. Reuse `native_trade_journal.py` for post-entry bar-by-bar tracking. Do not claim
   broker fills. Explicitly record ambiguous same-bar TP/SL collisions. Notify once
   per transition. Never synthesize a completed target when candle evidence is missing.
8. Reuse `arabic_event_engine.py`; never label a news direction 'confirmed' without
   the released actual, verified consensus, and live price confirmation.
   Before news, only conditional scenarios belong in the analysis/news channel.
9. For market-open wake-up, store per-instrument last observed state transactionally,
   emit OPENED only on a verified CLOSED -> OPEN transition, and dedupe the transition
   using a session ID and date. Do not emit 'open' from a scheduled clock alone.
10. A dedicated background worker cannot be guaranteed continuously on free Render,
    which sleeps. Prefer supervised always-on hosting or a separate permitted
    scheduler/webhook service, and communicate the limitation.

## Acceptance tests before deployment
- A real source-qualified NQZ26 and MGC expiry appear in the picker; unlicensed
  futures never show as connected/trade-ready.
- NQ1! / ES1! show as non-tradable reference, not a false expiry.
- During closure/stale feed, ZERO trade messages; at verified open, one session message.
- 100 simultaneous retries of the same setup produce at most one trade message,
  relying on a database unique key and an outbox with delivery reconciliation.
- Same symbol with distinct structural zone/entry generates a new message.
- TP1, TP2, TP3 and SL management messages use separate category routing; no
  pretend fills when the bar touches SL and TP concurrently.
- Arabic-only end-user templates; explicit Arabic reasons in place of WAIT.
- News does not invent consensus, released results or a directional certainty.
- No code path can place a broker order; no Pine revision unless separately approved.

## Commands
```bash
python -m unittest discover -s platform/tests -v
python -m unittest discover -s research/tests -v
python scripts/check_frontend.py
python -m compileall -q platform/backend platform/agent research
```

## Deployment safety
Keep `main`, the production Render service, PostgreSQL and existing TradingView
alerts unchanged until tests and authenticated production checks pass. Merging
this branch alone **does not** activate the new functions: endpoint, UI,
provider, market-open worker and Telegram wiring remain to be implemented.
