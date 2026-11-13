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
