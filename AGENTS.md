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
