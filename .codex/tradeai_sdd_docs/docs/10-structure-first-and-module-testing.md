# 10 — Structure-First Refactor and Module-by-Module Testing Playbook

## 1. Objective

This document operationalizes the agreed delivery method:

- First make the existing TradeAI codebase understandable as five modules.
- Then implement each module and prove it works independently.
- Then connect modules one boundary at a time.
- Finally validate the full paper-trading lifecycle.

The target remains one FastAPI application, one Python environment, direct Python function calls between modules and SQLite as the initial application database.

## 2. Status vocabulary

Track each module using separate statuses:

| Status | Meaning |
|---|---|
| `NOT_STARTED` | No module package/interface exists. |
| `STRUCTURED` | Package, README, DTOs and public service facade exist; no claim of functional completeness. |
| `LEGACY_WRAPPED` | New facade delegates to existing TradeAI implementation and regression tests pass. |
| `INDEPENDENTLY_TESTED` | Module behavior passes its own unit/repository/adapter tests using fakes/test SQLite. |
| `INTEGRATED` | Required adjacent-module boundary tests pass. |
| `E2E_VALIDATED` | Complete paper lifecycle involving the module passes. |

Do not mark a module `INTEGRATED` merely because another module imports it. Do not mark it `E2E_VALIDATED` before end-to-end tests pass.

## 3. Structure-only target

During Phase 1, establish this layout. Exact filenames may be adjusted after inspecting the local repository, but the ownership boundaries should remain:

```text
backend/
├── app/
│   ├── main.py
│   ├── api/
│   │   └── v1/
│   ├── modules/
│   │   ├── stock_selection/
│   │   │   ├── __init__.py
│   │   │   ├── README.md
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   └── providers/
│   │   ├── ai_analysis/
│   │   │   ├── __init__.py
│   │   │   ├── README.md
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── profiles.py
│   │   │   ├── provider_registry.py
│   │   │   ├── result_mapper.py
│   │   │   └── providers/
│   │   ├── decision_engine/
│   │   │   ├── __init__.py
│   │   │   ├── README.md
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   ├── strategies/
│   │   │   └── policies/
│   │   ├── execution/
│   │   │   ├── __init__.py
│   │   │   ├── README.md
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   ├── brokers/
│   │   │   └── order_reconciler.py
│   │   └── position_monitoring/
│   │       ├── __init__.py
│   │       ├── README.md
│   │       ├── schemas.py
│   │       ├── service.py
│   │       └── rules/
│   ├── workflows/
│   ├── shared/
│   │   ├── config/
│   │   ├── database/
│   │   ├── market_data/
│   │   ├── instruments/
│   │   ├── broker_read/      # read-only account/market integrations only
│   │   ├── clock/
│   │   └── logging/
│   ├── jobs/
│   └── harness/              # existing runtime; no duplicate scheduler
├── migrations/
├── data/                     # gitignored
│   └── tradingagents/        # separate upstream memory/checkpoint/report artifacts
├── tests/
│   ├── structure/
│   ├── unit/modules/
│   │   ├── stock_selection/
│   │   ├── ai_analysis/
│   │   ├── decision_engine/
│   │   ├── execution/
│   │   └── position_monitoring/
│   ├── integration/
│   │   ├── module_boundaries/
│   │   └── workflows/
│   ├── regression/
│   └── end_to_end/
├── scripts/
└── pytest.ini
```

### Structure-only rules

- Do not add feature logic during structure work.
- Do not move all legacy files at once.
- First create the destination package and public service/schema; next make a thin adapter that delegates to the legacy file.
- Update callers in small batches and run regression tests after each move.
- Keep compatibility wrappers at old paths temporarily if old imports/routes depend on them.
- Delete old implementations only after a repository-wide import/reference search and all tests pass.
- Do not start the harness, connect to Dhan order endpoints or invoke paid LLMs from import-time code.

## 4. Module ownership and individual test plan

### Module 1 — Stock Selection

**Owns:** manual candidate entry, future scanner providers, candidate validation, symbol normalization and candidate persistence.

**Does not own:** TradingAgents calls, AI analysis, decision/risk, broker order placement.

**Independent dependencies:** instrument resolver interface; temporary SQLite repository.

**Test cases:**

- Normalize symbol case, whitespace and exchange suffix.
- Reject invalid, unknown and ambiguous inputs.
- Detect duplicates within a batch and against existing candidates according to policy.
- Keep TradeAI symbol, Yahoo analysis ticker and Dhan security ID distinct.
- Persist candidate batch; retrieve it after a new session/database connection.
- Report partial batch validation clearly.

**Command:** `pytest tests/unit/modules/stock_selection -q`.

**Ready when:** manual selection works with a fake instrument master and SQLite, without Module 2.

### Module 2 — AI Analysis

**Owns:** analysis profiles, provider registry, TradingAgents adapter, legacy analysis adapter (if compatible), result mapping, analysis jobs, report artifact metadata and upstream memory/checkpoint configuration.

**Does not own:** trade approval, position sizing, broker orders or actual P&L authority.

**Independent dependencies:** fake provider interface for unit tests; TradingAgents is replaced by a fake graph unless the test is explicitly marked external.

**Analysis profile fields:** profile key/version, horizon, selected analysts, quick model provider/model, deep model provider/model, `max_debate_rounds`/`max_risk_discuss_rounds`, checkpoint option, report option and portfolio-context requirement.

**Test cases:**

- Profile loads and rejects unsupported analyst/config keys before calling upstream code.
- Quick/deep model/provider settings are correctly mapped into a copied `DEFAULT_CONFIG` (never mutate the module global).
- Different profiles produce distinct validated upstream config while preserving safe defaults.
- Fake `TradingAgentsGraph.propagate()` returns a representative state/rating; mapper extracts report sections and preserves original rating.
- All ratings (`Buy`, `Overweight`, `Hold`, `Underweight`, `Sell`) and `REVIEW`/malformed cases map correctly.
- Absent portfolio context differs from an explicit flat portfolio; stale snapshot behavior follows profile rules.
- Report save creates an artifact reference; database stores path/checksum/metadata.
- Memory log/checkpoint paths resolve inside the configured sidecar directory and are isolated for tests.
- Job status transitions and bounded concurrency work; a provider exception produces a failed job, not a FastAPI crash.
- Blocking `.propagate()` is offloaded from the event loop.

**Command:** `pytest tests/unit/modules/ai_analysis -q`.

**Optional external command:** `pytest tests/unit/modules/ai_analysis -m external -q` (requires provider credentials/data).

**Ready when:** module can accept an `AnalysisRequest` and produce a persisted normalized `AnalysisResult` using a fake provider in default tests, plus one successful real provider smoke test before production integration. For NSE historical fundamentals, test and preserve the upstream limitation that non-US Yahoo statements may be withheld for past-dated runs when publication dates cannot be established.

### Module 3 — Decision Engine

**Owns:** strategy registry, signal evaluation, entry/exit validation, position sizing, risk checks and immutable order-intent generation.

**Does not own:** AI provider invocation, Dhan SDK/order submission, broker-specific payload mapping.

**Independent dependencies:** provider-neutral `AnalysisResult`, fake market snapshot provider, fake portfolio/account snapshot provider, fixed clock and strategy config.

**Test cases:**

- Buy/hold/sell/review normalized views produce expected strategy outcomes.
- Stale/missing price, stale analysis, invalid stop-loss and market-closed cases fail closed.
- Position size uses `Decimal`, risk-per-share, max order value, available funds and exposure caps.
- Quantity is zero/negative or less than one => no order intent.
- Kill switch, daily-loss, max exposure, pending order and duplicate decision checks reject correctly.
- Exit quantity cannot exceed broker-confirmed open quantity.
- Same inputs/version produce the same result.
- Static architecture test confirms no import of `tradingagents`, LangGraph providers or Dhan order services.

**Command:** `pytest tests/unit/modules/decision_engine -q`.

**Ready when:** all decision math/policies pass without a real LLM, database-backed broker or Dhan credentials.

### Module 4 — Execution

**Owns:** broker adapter interface, paper broker, Dhan adapter, order submission/status/cancel/reconcile and fill lifecycle.

**Does not own:** selecting stocks or generating/approving signals.

**Independent dependencies:** persisted test `OrderIntent`, fake broker API, test SQLite.

**Test cases:**

- Only approved, non-expired, persisted intents can be submitted.
- Paper order transitions through expected states.
- Repeated idempotency key does not duplicate the order.
- Timeout means unknown until broker status reconciliation; no blind retry.
- Partial fills update filled/remaining quantity correctly.
- Rejected/cancelled orders do not create open positions.
- Dhan payload mapping uses correct security ID, exchange segment, product and quantity.
- Broker response is normalized into `ExecutionResult`.

**Command:** `pytest tests/unit/modules/execution -q`.

**Ready when:** paper adapter tests pass and Dhan adapter passes mocked request/response tests; no live order is required.

### Module 5 — Position Monitoring

**Owns:** open-position evaluation, stop/target/time rules, data-health rules, reassessment/exit request generation and deduplication.

**Does not own:** AI execution, trade approval or broker order placement.

**Independent dependencies:** synthetic confirmed positions, fake market feed and controllable clock.

**Test cases:**

- Stop, target and time/session exits trigger at exact expected boundaries.
- Partial fills/partial exits affect only confirmed open quantity.
- Stale/missing feed returns data-unavailable/fail-safe outcome.
- Same unchanged trigger does not create repeated reassessment/exit requests.
- Hard stop/time controls run without calling AI.
- Monitor returns an exit candidate; it never submits an order.

**Command:** `pytest tests/unit/modules/position_monitoring -q`.

**Ready when:** all rules pass using synthetic data and no live Dhan feed.

## 5. How to integrate after modules pass independently

Use one workflow/orchestration function per business flow. Keep module-to-module calls in-process and typed.

1. **I1: Stock Selection → AI Analysis.** Test the instrument's `analysis_ticker`, profile selection, job creation and duplicate handling.
2. **I2: AI Analysis → Decision Engine.** Test normalized report loading, source rating preservation, data freshness and `REVIEW` rejection.
3. **I3: Decision Engine → Execution.** Test approved intent persistence, idempotency, paper execution and failure reconciliation.
4. **I4: Execution → Position Monitoring.** Test only confirmed fills create/update open quantities.
5. **I5: Position Monitoring → AI Analysis/Decision Engine.** Test reassessment and exit request deduplication; exit decisions must pass Module 3 and Module 4.

For each integration, add one happy-path test, at least one failure-path test and a persisted lifecycle test. Do not start the next boundary until the current boundary's tests pass.

## 6. Standard test fixtures

Provide reusable pytest fixtures in `tests/conftest.py` or module-local `conftest.py`:

- `test_db`: fresh temporary SQLite database per test.
- `db_session`: isolated SQLAlchemy session/transaction.
- `fake_clock`: controllable UTC/Kolkata-aware clock.
- `fake_instrument_resolver`: maps a small set of known NSE symbols.
- `fake_market_data`: returns controlled current/historical prices and timestamps.
- `fake_portfolio`: returns controlled cash, holdings, pending orders and margin.
- `fake_analysis_provider`: returns a normalized `AnalysisResult` for Module 3 tests.
- `fake_tradingagents_graph`: emulates `.propagate()`/`save_reports()` for Module 2 tests.
- `fake_broker`: returns submit, partial fill, reject, timeout and reconcile outcomes.

Fixtures must not share a real SQLite file across tests. Use temporary paths. Use `monkeypatch` to redirect TradingAgents memory/checkpoint paths during tests.

## 7. Local development loop

For every code change:

1. Run the relevant module test command.
2. Run `pytest tests/structure -q` if package wiring or imports changed.
3. Run `pytest tests/regression -q` if existing code or compatibility wrappers changed.
4. Run affected integration tests only after module tests pass.
5. Run the complete default test suite before merging a phase.

Use exact test output to update each module's status table. Do not mark tests passed unless they were run.

## 8. Module status board

Maintain this table in `docs/implementation-status.md` once coding begins:

| Module | Structure | Independent tests | Integration | E2E | Notes |
|---|---|---|---|---|---|
| Stock Selection | NOT_STARTED | NOT_STARTED | NOT_STARTED | NOT_STARTED | Manual only first |
| AI Analysis | NOT_STARTED | NOT_STARTED | NOT_STARTED | NOT_STARTED | TradingAgents provider |
| Decision Engine | NOT_STARTED | NOT_STARTED | NOT_STARTED | NOT_STARTED | Provider-neutral |
| Execution | NOT_STARTED | NOT_STARTED | NOT_STARTED | NOT_STARTED | Paper first |
| Position Monitoring | NOT_STARTED | NOT_STARTED | NOT_STARTED | NOT_STARTED | Synthetic data first |
