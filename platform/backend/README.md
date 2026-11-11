# Big Ben AI Pro — Backend alpha

This is a **development-only** read-only webhook receiver, separate from the existing `server.py`. No broker order endpoints.

Run locally:
```bash
export BIGBEN_WEBHOOK_TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(36))')"
python platform/backend/app.py
```
Health: `GET /healthz`. Webhook: `POST /v1/tradingview/events`.

Required JSON: `{"token":"<secret>","schema":"bigben.v1","event":"BUY","event_id":"unique-event-123","symbol":"EURUSD","time":"2026-11-11T15:00:00Z","entry":1.10,"sl":1.09,"tp":1.13,"rr":3}`.

Security limitations: token in JSON is compatible with TradingView alerts but must be entered in a private alert, never committed to Git. Rotate immediately if exposed. This prototype uses SQLite local storage; Render ephemeral disks are **not suitable** for durable production event storage. No public deployment until authentication, persistent PostgreSQL, rate limiting, replay protection beyond time/id, audit, and load testing are completed. It has no UI or real market-data connection yet.

The older Render service and the original Pine indicator are unchanged.
