# Production Provider Composition and Paper E2E — Gap Report

**Audit date:** 2026-11-01  
**Implementation status at audit:** No implementation changes made for this milestone yet.

## Follow-up outcome

The audit gaps have since been addressed by the paper-only provider composition and public workflow APIs documented in [PRODUCTION_PROVIDER_E2E_REPORT.md](PRODUCTION_PROVIDER_E2E_REPORT.md). Provider and lifecycle tests now use the existing gateway/paper ledger and persisted SQLite repositories. Live startup is refused. The remaining limits are request-driven monitoring, an unchanged frontend that does not yet call the new workflow routes, unavailable source timestamps in the legacy Dhan candle adapter, and pre-existing global `pip check` conflicts.

## Current state

- FastAPI composes Stock Selection, AI Analysis, the analysis job manager/worker, and the Stock Selection → AI Analysis workflow. `TradingAgentsProvider` is lazy and injectable.
- I1–I5 workflows and module services already exist. Workflow integration tests use fake market, account, position and broker providers with temporary SQLite.
- Existing trusted sources are available: the single `TradingGateway` supplies quotes, account funds, open positions, orders, order polling and the existing paper ledger; the screener supplies candle history; NSE session helpers supply market-open state; SQLite stores shared risk settings. Module 4 already has an adapter over `TradingGateway`.
- These market/account/position/broker adapters are not composed into Module 3–5 services in `app/application.py`. No public API starts and tracks the whole paper lifecycle, retrieves module decisions or reassesses confirmed positions.
- The end-to-end test directory is still a placeholder. Existing workflow integration tests do not execute a complete persisted paper buy, confirmed position, monitor-triggered sell and realized P&L lifecycle.

## Gaps to close

1. **Trusted provider adapters:** Add injected implementations for market snapshots/candles, account risk snapshots, confirmed positions, and paper broker operations. Reuse `TradingGateway`, `paper_ledger`, screener/session helpers and existing repositories; never construct another Dhan client. A paper workflow must fail closed unless the configured execution mode is paper and live execution remains disabled.
2. **Composition:** `create_app()` currently wires only Modules 1 and 2. Add the Module 3 decision service, Module 4 execution service, Module 5 monitoring service, and I2–I5 workflow objects through the existing lifespan/session factory.
3. **Public API:** Current module endpoints cover candidates and analysis jobs/results only. Add owner-scoped paper workflow start/status, decision/order/position views and reassessment routes; retain the existing frontend routes as compatibility APIs.
4. **Lifecycle persistence/status:** Existing candidate, analysis, decision/intent, execution and trigger tables can hold lifecycle evidence. The API needs an owner-scoped aggregate view and idempotent transitions that derive state from those records and confirmed paper-ledger positions.
5. **End-to-end evidence:** Add a paper lifecycle suite that uses real app/module services, temporary SQLite and a temporary paper ledger, a fake analysis provider, and deterministic market fixtures. Cover duplicate requests, insufficient capital, stale price, rejection, partial fills, restart/reconciliation and final realized P&L.
6. **Validation environment:** The only available interpreter is global Python 3.11; it lacks Alembic, so migration-dependent tests cannot collect. `pip check` reports unrelated global dependency conflicts. There is no project virtual environment in the checkout.

## Safe implementation sequence

1. Define thin, typed adapters over existing market, account, position and paper gateway functions; unit-test each with temporary storage/fakes.
2. Compose Modules 3–5 and workflows I2–I5 in the single FastAPI lifespan, with paper mode enforced at both API and Module 4 boundaries.
3. Add owner-scoped public workflow APIs and aggregate lifecycle status without replacing current routes.
4. Add full end-to-end paper tests, run regression/module/structure suites, frontend build, dependency check and compile check; update implementation status with the resulting evidence and remaining gaps.

No legacy API, data file, paper ledger, migration, or TradingAgents source should be removed or modified as part of these steps.
