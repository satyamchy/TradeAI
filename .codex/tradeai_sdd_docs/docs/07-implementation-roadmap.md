# 07 — Implementation Roadmap

## Guiding approach

Follow the user's required sequence:

1. **Structure the existing project into five modules first.**
2. **Implement and test each module separately.**
3. **Integrate module boundaries one at a time.**
4. **Run the complete paper-trading lifecycle only after the individual modules and pairwise integrations pass.**

The project remains one FastAPI application. Module communication is direct Python function/service calls. SQLite is the initial application database. TradingAgents is an installed, pinned dependency and must not be modified.

Do not combine directory restructuring, major dependency upgrades, new business behavior and live execution in one change.

---

## Phase 0 — Repository audit and baseline (no refactor yet)

### Tasks

- Create a feature branch and capture current Git status.
- Record the complete backend/frontend folder trees and Python/Node versions.
- Run the existing backend and frontend using the current documented commands.
- Run existing tests and record pass/fail state; do not fix unrelated failures silently.
- Inventory routers, services, models, migrations, schedulers, harness, watchdog and Dhan clients.
- Identify each file's current callers and proposed module owner.
- Back up the development database; identify whether the local `.env` points to SQLite or PostgreSQL.

### Deliverables

- `docs/migration/file-ownership-map.md`.
- Baseline test report.
- Dependency inventory.
- Database backup and current schema inventory.

### Exit gate

A known baseline exists. No source code has been moved yet.

---

## Phase 1 — Create module structure only

**This phase is structural. Do not add new trading behavior or integrate TradingAgents yet.**

### Tasks

- Create packages for `stock_selection`, `ai_analysis`, `decision_engine`, `execution` and `position_monitoring`.
- Create `shared/`, `workflows/`, `jobs/`, `api/v1/` and module-specific test directories.
- Add `__init__.py`, module README files, public schemas and service facades.
- Add typed service interfaces and dependency injection wiring.
- Build a file-ownership map for every existing file.
- Move/wrap existing code one file or one small capability at a time. Prefer a thin facade that delegates to the old implementation first.
- Preserve old routes/imports with temporary compatibility wrappers where required.
- Create a clean SQLite database configuration and migration baseline; do not drop/replace existing data.
- Add structural smoke tests: all five module packages import, service registration works, database initializes, FastAPI starts, existing frontend routes continue to work.

### Deliverables

- Target module folder structure.
- No duplicate Dhan client, scheduler, harness or watchdog.
- Module-specific tests directories and module README/run instructions.
- Passing structure and legacy regression suite, or explicitly documented pre-existing failures.

### Exit gate

One FastAPI app starts; all five modules import; no internal HTTP calls exist; SQLite initializes; existing behavior remains operational. No new end-to-end trading workflow is required yet.

---

## Phase 2 — Module 1: Stock Selection (independent)

### Tasks

- Implement manual symbol input first.
- Normalize and validate symbol formats.
- Resolve canonical TradeAI instrument, analysis ticker and Dhan security ID as separate fields.
- Persist candidate batches and candidates using the module repository.
- Add duplicate/invalid-symbol handling.
- Define scanner provider interface, but defer top-gainer/momentum scanners.

### Test independently

- Normalization/validation unit tests.
- Mapping tests using a fake instrument-master provider.
- SQLite repository CRUD and restart-persistence tests.
- API tests for create/list/detail using TestClient.

### Deliverables

- Working manual candidate module.
- Module 1 README and test report.

### Exit gate

Module 1 can be tested and used without Module 2, TradingAgents, Dhan order placement or the full trading workflow.

---

## Phase 3 — Module 2: AI Analysis (independent)

### Tasks

- Define provider-neutral `AnalysisProvider` and `AnalysisResult` contracts.
- Create versioned `AnalysisProfile` definitions (initially one conservative profile; add intraday/swing variants after validating supported upstream analyst IDs/config keys).
- Upgrade LangGraph/LangChain dependencies only through the compatibility plan in `06-dependencies-and-upgrade.md`.
- Install pinned TradingAgents v0.7.1 without source modifications.
- Implement `TradingAgentsProvider` and a `ResultMapper` using only documented public API.
- Configure quick/deep model IDs and provider tiers through sanitized profiles/configuration.
- Add optional portfolio context built from a timestamped TradeAI portfolio snapshot.
- Save normalized results and upstream full/HTML report artifacts.
- Configure TradingAgents decision-memory and checkpoint paths under `backend/data/tradingagents/`; keep sidecar stores separate from `tradeai.db`.
- Add a persistent analysis-job state machine and bounded worker. Run synchronous `.propagate()` outside the event loop.
- Retain the old LangGraph conversation capability; adapt it as a stock-analysis provider only if it meets the same contract.

### Test independently

- Profile validation tests.
- Fake TradingAgents graph tests (no paid LLM/network).
- Result mapping tests for all five ratings plus `REVIEW`/malformed states.
- Portfolio-context mapping tests (missing vs explicitly empty positions).
- Report metadata/path tests using temporary directories.
- Job lifecycle/retry/recovery tests.
- Optional external smoke test for one NSE ticker with provider credentials.

### Deliverables

- Module 2 can accept an analysis request and return a persisted normalized result without Module 3 or Module 4.
- Reports, model/profile metadata and provider failures are traceable.

### Exit gate

A single-stock TradingAgents analysis works from the TradeAI service interface; default tests do not require real API credentials; existing conversational LangGraph tests pass.

---

## Phase 4 — Module 3: Decision Engine (independent and provider-neutral)

### Tasks

- Define strategy interface and versioned strategy configuration.
- Build signal evaluation using normalized `AnalysisResult` only.
- Implement fresh-price validation and market-session checks.
- Implement deterministic entry/exit validation.
- Implement Decimal-based position sizing.
- Implement risk rules for capital, max order value, per-symbol/portfolio exposure, daily loss, open/pending orders, duplicate intents and kill switch.
- Persist decisions, reason codes and immutable order intents.
- Implement one initial strategy only; keep other strategy types disabled until independently tested.

### Test independently

- Pure unit tests with fixed inputs and deterministic expected outputs.
- Boundary/rounding tests for sizing.
- Stale-price, missing-data and market-closed tests.
- Risk cap, insufficient margin, kill-switch, duplicate and conflicting-position tests.
- Assert Module 3 imports neither `tradingagents` nor Dhan order-placement modules.

### Deliverables

- Module 3 returns `BUY_APPROVED`, `SELL_APPROVED`, `HOLD`, `REJECTED` or `REVIEW_REQUIRED` with reason codes.
- It creates an `OrderIntent` only for approved decisions.

### Exit gate

Decision results are deterministic for the same snapshots, strategy version and risk configuration. Module 3 is fully testable with fake market/account providers and no AI or broker credentials.

---

## Phase 5 — Module 4: Execution (independent)

### Tasks

- Define broker-neutral adapter interface.
- Implement/test paper broker first.
- Wrap the existing Dhan SDK/client; do not create a second Dhan connection owner.
- Accept only persisted approved `OrderIntent` IDs.
- Add idempotency, broker status reconciliation, timeout recovery and partial fills.
- Re-check mandatory guardrails immediately before submission.

### Test independently

- Paper order state-transition tests.
- Mocked Dhan SDK adapter tests.
- Duplicate submission/idempotency tests.
- Timeout/unknown status reconciliation tests.
- Partial fill, rejection, cancel and fill-price tests.
- Verify positions update from confirmed fills only.

### Deliverables

- Module 4 can execute a test-approved intent in paper mode and return a normalized execution result.

### Exit gate

No duplicate orders; partial fills and failures are reconciled; no live order is sent by default.

---

## Phase 6 — Module 5: Position Monitoring (independent)

### Tasks

- Build monitor logic over an injected position repository, market snapshot provider and clock.
- Reuse the existing watchdog/harness scheduler rather than create another scheduler.
- Monitor only confirmed open quantity.
- Implement deterministic stop-loss, target, session/time and stale-feed behavior.
- Add deduplicated reassessment requests to Module 2 and exit-evaluation requests to Module 3.

### Test independently

- Synthetic price/time tests for stop, target and time exit.
- Partial position and remaining-quantity tests.
- Stale/disconnected feed tests.
- Reassessment cooldown/deduplication tests.
- Assert hard stop/session rules do not call an LLM.

### Deliverables

- Module 5 can evaluate synthetic open positions without Dhan live feed or TradingAgents.

### Exit gate

All monitor rules pass in isolation; it produces requests/evaluations only and never sends broker orders.

---

## Phase 7 — Incremental module integration

Do not integrate all modules at once. Implement and test each boundary in this order:

| Integration | Flow | Required integration test |
|---|---|---|
| I1 | Module 1 → Module 2 | Valid candidate creates an analysis job with the right provider ticker/profile. |
| I2 | Module 2 → Module 3 | Completed normalized analysis can be evaluated; `REVIEW`/failed/stale analysis cannot auto-approve. |
| I3 | Module 3 → Module 4 | Only a persisted approved `OrderIntent` can be paper-executed exactly once. |
| I4 | Module 4 → Module 5 | Confirmed paper fills create/update the monitored position quantity correctly. |
| I5 | Module 5 → Module 2 and Module 3 | Reassessment and exit evaluation are deduplicated; approved exit is routed through Module 4. |

For each integration: define the DTO contract, implement the orchestrator function, add happy-path and failure-path tests, run the module unit suites, then merge the integration change.

### Exit gate

Each pairwise integration passes before the next is started.

---

## Phase 8 — End-to-end paper trading and operational hardening

### Tasks

- Run the complete lifecycle: manual candidate → AI analysis → decision → approved intent → paper order → confirmed paper fill → position monitoring → exit decision → paper sell → closed position.
- Test app restart with queued/running analysis jobs and open positions.
- Test provider timeout, broker timeout, partial fills, SQLite lock/busy errors and market-feed disconnects.
- Measure analysis time, queue delay, token/cost usage where available, error rates and duplicate prevention.
- Use leakage-safe historical evaluation with realistic fees/slippage. Keep TradingAgents research backtests distinct from TradeAI strategy/order backtests.
- Run paper trading across different market conditions before any live-trading review.

### Deliverables

- End-to-end test report.
- Paper-trading and backtest report.
- Operational runbook.
- Live-trading readiness checklist.

### Exit gate

All critical safety, execution reconciliation and recovery tests pass. Live trading remains a separate explicit authorization and is not automatically enabled by test completion.

---

## Future phases

1. Automated top-gainer/top-loser/momentum scanners in Module 1.
2. Additional analysis providers and validated profiles in Module 2.
3. Additional strategies and portfolio allocation in Module 3.
4. Additional broker adapters in Module 4.
5. **Module 6 — Backtesting & Evaluation:** upstream TradingAgents rating backtests plus TradeAI full-strategy simulation.
6. **Module 7 — Performance Analytics & Feedback:** actual fill/P&L analytics and reviewed research feedback; no automatic unreviewed risk-rule adaptation.
7. Notifications and reporting enhancements.
8. PostgreSQL migration when data volume/concurrency/deployment requires it.
9. External worker queue only when the single-process job worker is insufficient.
