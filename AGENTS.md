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

Current continuation: nine requested TradingView symbols are active on M5/v6.4.1 with9 confirmed deliveries at2026-11-13T19:15Z. Do not recreate them. Read evidence/expanded-alerts-2026-11-13.json. Render has2997 real closed forex candles and3 persisted nine-role proxy reports (27 tasks). Preserve the distinction between proxy RR3 and live Pine RR2.5. Do not treat widget embed denial as webhook outage. Current code ff1cb75686d03b70062224a6efabfe61ea5b2222, with a fresh-analysis/chart fix in progress.
