# أدوار البحث الفعلية
research/daily_agents.py يحوي quality وrisk وvalidation وhypotheses وreviewer.
هي حسابات حتمية، ولا تستدعي نموذجًا مدفوعًا ولا تمثل استقلال مصادر البيانات.
research/run_provider_research.py يجلب التاريخ المرخص عند ضبط الاعتمادات ثم يشغل المراجعات.
platform/agent/reliability_agent.py يراقب واجهات خاصة. لا يعني وجوده نجاح جدولة حية.
الأدوار التسعة المطلوبة وسجل task ID وحالات واستئناف وأرشيف دائم كامل لم تنفذ بعد؛ لا تصف ذلك بأنه مكتمل.


## Durable deterministic roles
research/orchestrator.py executes market data validation, proxy backtesting, signal quality, risk diagnostics, bounded RR experiments, a disjoint final holdout, Pine source integrity reporting, feed-age monitoring, and coordination. Each task has ID, input dataset hash, status, output, timestamps, logs, sanitized error and artifact reference. PostgreSQL/SQLite store reports and all nine tasks atomically; repeated run IDs are idempotent. A task failure is recorded and the coordinator still reports failures. No paid AI API or automatic strategy mutation is used. The optimization uses 60% training, 20% validation and a final 20% holdout; final holdout never selects parameters. This is not evidence of Pine parity or profitability.

## Current execution boundaries
The durable orchestrator has nine deterministic evidence roles; Analyze optionally asks one Gemini model for four specialist sections. Production reviews succeeded previously; latest pre-release attempt returned503. The new operations ledger records actual worker attempts and daily report references. Private lab drafts are stored and diffed against an immutable baseline, never executed or automatically promoted. Compilation, market licensing, Pine parity and independent validation remain necessary before a strategy change can be claimed.
