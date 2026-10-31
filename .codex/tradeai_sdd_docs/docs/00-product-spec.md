# 00 — Product Specification

## 1. Purpose

Build TradeAI into a maintainable, modular trading application that can accept a stock candidate, research it using configurable AI providers, make a deterministic strategy/risk decision, submit an approved order through a broker adapter, and monitor the resulting position.

The initial target is a **working and testable paper-trading lifecycle**, not a claim of profitable trading.

## 2. Product goals

1. Make the full stock-to-position workflow traceable from one dashboard.
2. Separate research opinions from executable trading decisions.
3. Keep broker execution behind a single controlled interface.
4. Allow AI providers and trading strategies to be replaced without rewriting unrelated modules.
5. Keep the initial system simple to run locally: one FastAPI application, in-process calls, SQLite database.
6. Preserve working TradeAI features and migrate them behind module interfaces incrementally.
7. Make future PostgreSQL adoption possible through SQLAlchemy and database migrations.
8. Allow every module to be tested independently before it is connected to another module.
9. Capture the AI analysis profile, model/provider configuration, portfolio context, source timestamps and TradingAgents version for reproducibility.
10. Keep actual broker fills and TradeAI P&L authoritative; third-party AI memory is supplementary research context.

## 3. Initial user workflow

### Workflow A — Manual candidate analysis

1. User enters one or more NSE symbols in the React frontend.
2. Module 1 validates symbols and maps each symbol to TradeAI's canonical instrument representation.
3. The application creates an analysis job for each candidate or a batch parent job.
4. Module 2 invokes the configured analysis provider. The first provider is TradingAgents; the existing LangGraph-based stock analysis may be retained as another provider if it can meet the common contract.
5. The result is normalized into a provider-independent `AnalysisResult` and persisted.
6. The frontend displays reports, rating, provider, timestamp and failure/status information.

### Workflow B — Evaluate a potential entry

1. The user or an explicitly enabled strategy requests a decision for a completed analysis.
2. Module 3 obtains a fresh market snapshot, available funds/margin and current positions from shared services; it does not trust prices or capital supplied by the frontend.
3. The selected strategy evaluates entry conditions.
4. Position sizing and risk policies run.
5. Module 3 returns `BUY_APPROVED`, `HOLD`, `REJECTED` or `REVIEW_REQUIRED` and, only when approved, a validated `OrderIntent`.
6. In the initial release, the order is sent to the paper execution adapter. Live execution is disabled by default.

### Workflow C — Manage an open position

1. Module 5 reads broker-confirmed/paper-confirmed open positions and current prices.
2. Deterministic checks evaluate stop-loss, target, time-based square-off and stale-data conditions.
3. When a reassessment is needed, Module 5 requests an analysis through Module 2.
4. Module 3 evaluates the potential hold/exit action and risk.
5. Module 4 executes an approved exit intent.
6. Actual fills and remaining quantity are reconciled before the position is marked closed or reduced.

## 4. Scope — first release

### In scope

- One FastAPI application.
- Five business modules with direct service calls.
- Manual stock selection for NSE equity candidates.
- Symbol/instrument mapping and validation.
- TradingAgents v0.7.1 integration as an analysis provider without modifying its source.
- Analysis profiles that configure supported analyst selection, quick/deep model tiers and debate settings.
- Optional portfolio context built from a timestamped TradeAI account/position snapshot.
- Save normalized analysis results and a reference to the upstream HTML/full report where available.
- Configure TradingAgents memory and checkpoint directories independently from the TradeAI main database.
- Retention of existing TradeAI LangGraph capabilities behind an adapter where appropriate.
- SQLite persistence through SQLAlchemy 2.x.
- Existing Dhan client/service reuse and paper execution.
- Independent decision/risk engine with configurable initial strategies.
- Position monitoring and deterministic exit triggers.
- React + Vite frontend remains in place.
- Module-isolated tests, integration tests and operational logs for each module.

### Out of scope for first release

- Automatic discovery across the full NSE universe.
- Unattended live trading.
- Short selling, options, futures, leverage or portfolio margin strategies.
- Multiple brokers.
- Microservices, inter-module HTTP, Kafka, Redis or distributed workers.
- Rewriting TradingAgents internals or modifying its prompts/agents/graph.
- Replacing the existing frontend framework.
- Claiming that AI ratings or backtest outcomes guarantee future returns.

## 5. Actors and permissions

| Actor | Allowed actions |
|---|---|
| User | Add candidates, inspect research, request a decision, enable/disable paper or live mode, inspect positions and logs. |
| Module 1 | Create validated candidates; it cannot place orders. |
| Module 2 | Produce research and normalized analysis; it cannot approve or execute orders. |
| Module 3 | Approve/reject a trade and produce an order intent; it cannot call a broker directly. |
| Module 4 | Validate and submit an already-approved order intent; it cannot originate trading signals. |
| Module 5 | Monitor positions and create reassessment/exit requests; it cannot bypass Module 3 or Module 4. |

## 6. Success criteria

The first end-to-end acceptance target is:

- A user can enter a valid stock manually.
- The application creates a persistent analysis job.
- TradingAgents completes analysis without blocking the FastAPI event loop.
- TradeAI stores and displays a normalized result.
- Re-running or retrying an analysis is traceable and does not silently overwrite previous runs.
- A decision can be evaluated in paper mode using fresh market/portfolio snapshots.
- An approved paper order is recorded, simulated fills update the position, and Module 5 can monitor it.
- Every rejection, error, provider response, decision and order has a traceable ID.

Profitability is not a functional acceptance criterion. Strategy performance must be established separately using leakage-safe backtesting and paper/live-market evaluation.


## 7. Explicit development sequence

The project must be delivered in this order:

1. **Repository audit and baseline:** record the current tree, behavior and test status.
2. **Structure-only refactor:** establish packages, module contracts, shared infrastructure and module test directories. Keep business behavior unchanged.
3. **Independent module implementation:** build and test each module with fakes/test databases before connecting it to other modules.
4. **Incremental integration:** connect one module boundary at a time and add integration tests.
5. **End-to-end paper lifecycle:** validate all five modules together.

A module is not considered complete merely because its folder exists or its imports work. Structural readiness and functional acceptance are separate gates.
