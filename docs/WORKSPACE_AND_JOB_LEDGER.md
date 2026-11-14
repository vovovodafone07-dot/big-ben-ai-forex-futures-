# Private research workspace and operations ledger

Authenticated GET/POST /api/workspace/drafts stores Pine drafts with rationale, source hash and immutable baseline. It never executes Pine or approves a release. GET/POST /api/workspace/notes persists symbol-scoped plain-text notes. Inputs are bounded; JSON POSTs reject cross-origin requests. UI renders user content as text.

GET /api/operations reads actual worker runs and daily Arabic reports. Expired leases record interrupted executions. Reports reference existing research datasets rather than duplicating every trade. An existing authorized Telegram channel is attempted once per UTC day, no retries or duplicated startup reports. A provider acknowledgment is not proof of reading or trade delivery. Disable via BIGBEN_DAILY_TELEGRAM_ENABLED=0.

Migrations are additive and exercised in SQLite tests and isolated PostgreSQL CI. Rollback: redeploy prior app commit; leave additive tables intact so notes, drafts and audit evidence are preserved. Existing Pine source and alert snapshots do not change.
