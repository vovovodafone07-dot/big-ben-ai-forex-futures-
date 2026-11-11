# Big Ben AI Pro — integration access checklist (approved 2026-11-11)

## Authorized scope
GitHub, Render, TradingView, market data, economic news/calendar, Telegram, WhatsApp, Cloudflare, security/storage, tests. Free-only. No deletions of legacy services, no paid resources, **never execute trades**.

## Current verified state
- New API and redesigned private preview deployed to Render Free: https://bigben-ai-pro-api.onrender.com/dashboard
- Pine v5.3 development bridge in `platform/indicator/`, not compiled in TradingView.
- PostgreSQL 18 Free created: `dpg-dbq9afmgekts73eqe0c0-a`, status creating at creation; **expires 2026-12-11**. Do not claim durable long-term history on an expiring free database.
- Existing service and original indicator preserved.

## External authorizations required
1. **TradingView:** user signs into their account, opens Pine Editor, compiles v5.3, and creates alert `Any alert() function call` on each intended chart/symbol (M5). Configure webhook URL `https://bigben-ai-pro-api.onrender.com/v1/tradingview/events`. Secret is managed in Render and must be entered only into private Pine input; do not paste in chat. TradingView account plan must support webhook alerts.
2. **Market data:** user creates/authorizes a free API account (existing Twelve Data key can be set as `TWELVE_DATA_API_KEY` in Render Environment). Verify Forex and *actual supported futures contract symbols* and free-plan limits before enabling. NQ and 6E generic tickers previously failed; no unsupported-symbol fallback masquerading as live prices.
3. **Economic news:** choose a provider with an explicit legal free API/license; set API key in Render Environment, not Git. Distinguish delayed/limited feeds.
4. **Telegram:** user creates bot via BotFather and sets `TELEGRAM_BOT_TOKEN` and destination `TELEGRAM_CHAT_ID` in Render Environment. Test on a private chat first. No unsolicited messages.
5. **WhatsApp:** requires official WhatsApp Business Cloud API registration, a verified sender, a user opt-in and template approval as applicable; free tier eligibility and charges must be confirmed before activating. No bypass via unofficial web automation.
6. **Cloudflare:** user authorizes zone/worker access if domain routing is desired. Do not alter legacy Worker DNS or delete existing routes. Existing Render HTTPS works without Cloudflare.
7. **Postgres:** once ready, securely connect using an internal URL and install a PostgreSQL client dependency in Render build. Do not put DB URL in repository or chat. Plan migration from expiring free DB.
8. **Security:** rotate the dashboard password already exposed in chat, keep `BIGBEN_WEBHOOK_TOKEN` private, restrict CORS, use least privilege and audit events.

## Delivery criteria
- No fake live status, win rates, market prices, news, or AI progress.
- Verify real end-to-end TradingView webhook (BUY/SELL, Entry/SL/TP/RR) and idempotency.
- Verify historical events persist through service restart with Postgres, before claiming storage durable.
- Verify per-provider rate limits, timestamps, timezone, instrument mapping and license.
- No real broker connections or order endpoints.
