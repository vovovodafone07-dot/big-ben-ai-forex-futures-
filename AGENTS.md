# Big Ben AI Pro continuation
Read docs/CURRENT_PROJECT_STATUS.md, docs/IMPLEMENTATION_PROGRESS.md and docs/REMAINING_BLOCKERS.md before editing.
Repository: vovovodafone07-dot/big-ben-ai-forex-futures-.
Continuation branch: feature/autonomous-continuation-2026-11-13, based on f64490ca543d6576efb27420987383726a7136eb.
Preserve all Pine files and existing TradingView alerts. The owner explicitly requires the original strategy to remain unchanged.
The dashboard scalp option is hypothetical arithmetic at 1R by default, not a new Pine strategy or independent signal. Keep both options in one Telegram message.
Never show configured credentials as verified data access, stale events as current opportunities, or closing-price observations as fills.
Never log tokens, provider responses that might echo credentials, or database URLs.
Run python -m unittest discover -s platform/tests -v and python -m unittest discover -s research/tests -v.
Run python scripts/check_frontend.py with Node available. CI additionally validates PostgreSQL migration on an isolated database.
Update progress, status and blockers after every meaningful milestone. Do not claim completion of all acceptance criteria.
Production account connections require supported access. Do not bypass browser policy or database IP restrictions.

Owner subsequently requested updating the existing TradingView source and retesting. v6.4.1-sync was saved/compiled in the existing private script (revision 8), preserving observed RR 2.5/evidence 1 and disabling the new optional filters by default. Read docs/PINE_VERSION_SYNC.md. Updating source does not update alert snapshots; inspect existing alerts before any cutover and do not create duplicates.

Latest continuation (2026-11-14): PR13–17 are merged. Live code aff712ef7a926f0169338a6215d7b105c5cd60e5 / Render dep-dbrotfpsrm7s73eobuh0. All nine existing M5 alert snapshots use revision 9 / bridge v6.4.2-telemetry, with strategy v6.4.1-sync unchanged; all nine delivered the21:40UTC cycle. Do not recreate them. Gemini production review succeeded with four specialist sections; see docs/evidence/gemini-review-verified-2026-11-14.json. Current CI43519184758 passes102 backend +37 research tests and8 JS blocks on Windows/Linux and isolated PostgreSQL. Local node.exe is currently missing; CI supplies Node22. Browser control recovered after the owner freed2.94GiB, a kernel reset and Chrome activation. Read canonical status/blockers for actual remaining limits. No pending cutover or general approval exists. Preserve the distinction between Pine-rules RR2.5 research and the older proxy RR3 reports.

Current continuation supersedes older deployment notes above: PR20 is live at7212e80a6fb263e6436f6c8581ab58b0c74e152b / dep-dbrqi1lbedkc738hsjpg. Owner chose design A and free hosting.121 backend +37 research tests and11JS blocks passed CI. The compiled private Pine is revision10/v6.4.3; only EURUSD/GBPUSD/6E snapshot saves are verified so far, six existing alerts remain. Official WhatsApp template adapter is implemented but disabled/unconfigured; no extra costs approved. Historical SMT research cannot override Pine. Read the rewritten canonical status/blockers before continuing.

Latest cutover supersedes six-pending note: all nine existing alerts were saved at revision10/v6.4.3. See revision10-alert-cutover evidence; new all-nine delivery remains unverified. Source-qualified owner watchlist has13 symbols; never infer alert coverage from membership. Latest Gemini request503, deterministic analysis remains available.

PR22 workspace release: head0f82f604db46e34094917626c7d00ff432ac5d96, merge0b5de4a1a2da9a7e12c718fc6c9091bb13f8d1e4, deploydep-dbs6ckafngtc73brk87g.129 backend +37 research tests,12JS and all six CI checks passed. Additive workspace/operations migrations support private drafts/notes and leased real-cycle reports. Default daily Telegram attempt uses existing authorized destination once/day; disableBIGBEN_DAILY_TELEGRAM_ENABLED=0. Verify production before claiming this release completed. Pine unchanged.

Owner deferred the nine new TradingView alerts; do not create them or ask again until resumed. Meta Business was inspected and requires owner login; auth must remain user-operated. Data preservation release adds bounded authenticated application snapshot and offline restore only to a NEW local SQLite file. No HTTP restore, secret export, database renewal or migration is implied. See DATA_PRESERVATION.md.

Owner has now deferred WhatsApp too: do not automate Meta setup, request login, or resume new alerts unless explicitly requested. Production application export4129rows/17tables is restored and row-compared successfully; raw backup files stay outside Git. Dated walk-forward reports are research-only and insufficient; never treat them as a strategy promotion or continuous scheduled validation.

Latest live PR24:1d95a1e826c8d2f120c353b3705effee8a25672d /dep-dbsb8jqfngtc73c8gdk0.178 tests and14JS/7CI checks passed. Dated walk-forward3forex reports are INSUFFICIENT_EVIDENCE, hash-guarded and not auto-refreshed; production Pine unchanged. Export/restore17tables4129rows verified. Next: native report UI and supported same-feed TradingView CSV export, without new alerts or purchases.
