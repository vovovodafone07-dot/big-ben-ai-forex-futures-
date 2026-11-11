# Big Ben Hybrid M5 v6.0 — development copy

This file is a **new independent copy**. It does not replace v5.3, the original BBB indicator, or existing TradingView alerts.

## What is implemented
- M5 close-only entry, breakout first-cross with ATR buffer and candle body filter, optional breakout-and-retest on a later bar, RR-adjustable **single** TP and stop based on recent swing, cooldown, directional guard on closed M15/H1/H4 candles.
- Lightweight **algorithmic proxies**, not verified full institutional implementations: ICT/SMC swing BOS, 3-candle FVG, liquidity sweep; CRT previous-candle raid and reclaim; CISD previous opposite candle open cross; Turtle Soup lookback sweep and reclaim; QM approximate structure shift; SMT optional cross-symbol extreme divergence.
- Evidence vote threshold, BUY/SELL box labels, risk/reward boxes, Entry/SL/TP, TradingView alertconditions, optional webhook JSON to existing read-only receiver. Webhook is **off by default**. No broker execution.

## Limitations / validation
- These pattern definitions are simplified and **not** a faithful reproduction of a specific BBB video or discretionary ICT/SMC/CRT/SMT/CISD/QM methodology. The exact reference video rules must be compared candle-by-candle before claiming parity.
- Not compiled in TradingView, not backtested or forward-tested, and no win-rate claim. Code should be compiled and reviewed in Pine Editor first.
- SMT comparison defaults to ES1! as an example and is **off**; for Forex, select a meaningful correlated or inversely correlated instrument and review polarity. Symbol availability depends on TradingView plan/data.
- One candle can touch stop and target; without lower timeframe data, exit order is unknown. Current indicator only tracks whether either was hit; it is **not** a backtest engine.
- Use a standard candle chart for actual OHLC values; synthetic Heikin Ashi differs and should be tested separately.
- TradingView alerts are snapshot-based: create a **new** alert for this separate indicator if desired; do not delete existing alerts.
- For app notifications, create BUY and SELL alertconditions and enable Notify in app. For webhooks, enable the private token and use Any alert() function call; never paste secrets in GitHub/chat.

## Connection status
GitHub and Render connected; Render free PostgreSQL available but **not wired to API**. External TradingView/market data/Telegram/WhatsApp/Cloudflare account authorization and credentials remain unavailable through current tools. Do not claim those integrations are active.
