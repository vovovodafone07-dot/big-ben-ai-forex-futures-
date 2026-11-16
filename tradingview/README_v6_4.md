# Big Ben AI v6.4 — Installation and safety

- Backup: `tradingview/Big_Ben_AI_Hybrid_M5_v6_3_backup.pine`
- Review candidate: `tradingview/Big_Ben_AI_Hybrid_M5_v6_4_Review.pine`

## TradingView
1. Open a supported Forex or Futures symbol, switch to **5 minutes (M5)**.
2. Pine Editor → New indicator → paste **v6.4** → Save as a **new** script → Add to chart.
3. Resolve any Pine compilation errors before configuring alerts; this version has **not been compiled on TradingView**.
4. Default settings: RR 3, Both directions, Breakout + Retest, Balanced M15/H1/H4, two evidence votes. SMT and Heikin Ashi confirmation are optional.
5. If using the bridge, enter the secret webhook token **only in TradingView indicator settings**; never commit it or share it in chat.
6. For a manually authorized alert migration, use **Any alert() function call** with webhook `https://bigben-ai-pro-rebound.onrender.com/v1/tradingview/events`. Do not create duplicates automatically; verify one fresh event on the new endpoint before retiring the old receiver. Enable mobile app notifications if wanted.
7. Check `/healthz/integrations` and `/healthz/storage` on the Render service, then verify actual HEARTBEAT and BUY/SELL delivery.

## Limitations
- Analysis and alerts only; no real orders.
- M5 entries only, higher timeframes provide directional context.
- Some ICT/SMC/CRT/SMT checks are proxies, not full discretionary models.
- The backend learning audit does not automatically train a model or edit Pine.
- No verified TradingView compilation or historical out-of-sample win rate yet.
- Existing v6.3 and current alerts remain untouched.
