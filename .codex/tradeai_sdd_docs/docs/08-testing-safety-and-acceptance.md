# 08 — Testing, Safety and Acceptance Specification

## 1. Testing philosophy

Every module must be testable before it is connected to the next module. The default test suite must be deterministic and must not require live LLM calls, paid API keys, live Dhan credentials or a running market session.

Use three distinct levels:

1. **Structure tests:** package imports, FastAPI startup, module registration, schema availability and database initialization.
2. **Module-isolated tests:** unit tests and repository/adapter tests for one module at a time using fakes and a temporary SQLite database.
3. **Integration/E2E tests:** exercise explicit module boundaries and then the complete paper lifecycle.

A passing import test means only that the package is structurally present; it does not mean the module's business functionality is complete.

## 2. Test layout

```text
backend/tests/
├── structure/
├── unit/
│   └── modules/
│       ├── stock_selection/
│       ├── ai_analysis/
│       ├── decision_engine/
│       ├── execution/
│       └── position_monitoring/
├── integration/
│   ├── module_boundaries/
│   └── workflows/
├── regression/
└── end_to_end/
```

Recommended pytest markers: `unit`, `structure`, `integration`, `regression`, `e2e`, `external`, `slow`. Configure the default test run to exclude `external` and `slow` tests.

## 3. Run tests module by module

Run commands from `backend/` on Windows PowerShell or a terminal with the backend environment activated:

```powershell
# Structure and startup
pytest tests/structure -q

# Individual modules
pytest tests/unit/modules/stock_selection -q
pytest tests/unit/modules/ai_analysis -q
pytest tests/unit/modules/decision_engine -q
pytest tests/unit/modules/execution -q
pytest tests/unit/modules/position_monitoring -q

# Regression and cross-module tests
pytest tests/regression -q
pytest tests/integration -q
pytest tests/end_to_end -q

# Default local suite (configure pytest.ini to exclude external/slow)
pytest -q
```

Optional live provider test (requires valid provider credentials/data access and must be invoked intentionally):

```powershell
pytest tests/unit/modules/ai_analysis -m external -q
```

Do not run external tests as part of every normal edit/save cycle. Add equivalent mocked tests so ordinary CI remains deterministic.

## 4. Structure tests

- All five module packages import.
- Public service facades and schemas can be imported without creating broker/LLM clients at import time.
- FastAPI application starts with `TRADING_MODE=PAPER`, `LIVE_TRADING_ENABLED=false` and `HARNESS_AUTO_START=false`.
- SQLite database initializes and migrations run on a temporary database.
- Existing API routes and frontend contract smoke tests continue to pass.
- No duplicate Dhan client, watchdog, scheduler or harness is registered.
- Optional architecture test detects forbidden imports (e.g. Module 3 importing `tradingagents` or Dhan order methods).

## 5. Module-isolated test requirements

### Module 1 — Stock Selection

- Symbol normalization/case/whitespace.
- Invalid, ambiguous and duplicate symbols.
- Mapping of TradeAI symbol, Yahoo analysis ticker and Dhan security ID using a fake instrument-master service.
- Manual candidate batch persistence and retrieval using temporary SQLite.
- Invalid-symbol results do not abort valid symbols in the same batch unless the request explicitly requires all-or-nothing behavior.

### Module 2 — AI Analysis

- Analysis profile validation and version selection.
- Provider registry chooses the requested provider.
- TradingAgents adapter tested with a fake `TradingAgentsGraph`; no live LLM needed.
- Result mapper covers Buy, Overweight, Hold, Underweight, Sell and `REVIEW`/unparseable output.
- Missing/partial report sections and provider exceptions are handled.
- Quick/deep provider and model settings are sanitized and persisted.
- Portfolio mapping distinguishes absent context from an explicit empty holdings list.
- Stale or missing portfolio snapshot is handled according to profile requirements.
- HTML report artifact path/checksum and cleanup rules.
- Decision-memory and checkpoint paths point to temporary test directories; concurrent tests never share those files.
- Job state transitions, retry, cancellation and crash recovery.
- Synchronous `.propagate()` is offloaded from the event loop and concurrency is bounded.

### Module 3 — Decision Engine

- Strategy signal rules using normalized provider-neutral `AnalysisResult`.
- Entry/exit validation with current/stale/missing market snapshots.
- Position-size calculations using `Decimal`, floor/rounding and boundaries.
- Insufficient capital/margin, max order value, max exposure, daily loss, market-session and kill-switch checks.
- Existing/pending position conflicts and duplicate intent prevention.
- `REVIEW`, failed, incomplete or expired analysis cannot auto-approve.
- Module 3 imports neither TradingAgents, LangChain/LangGraph providers nor Dhan order-placement interfaces.
- Same inputs, strategy version and risk config produce the same result.

### Module 4 — Execution

- Paper adapter state machine.
- Mocked Dhan SDK requests/responses.
- Approved persisted intent required; arbitrary frontend order data rejected.
- Idempotency on repeated calls.
- Unknown broker status after timeout is reconciled before retry.
- Partial fills, rejects, cancel, average fill price and remaining quantity.
- Position updates come from confirmed fills, not order submission.

### Module 5 — Position Monitoring

- Synthetic market snapshots and fake clock.
- Stop-loss, target, time/session exit and feed staleness.
- Partial exits and remaining quantity.
- Reassessment cooldown/deduplication.
- Mandatory stop/time controls do not wait for AI provider.
- Monitor creates requests/evaluations only; it never submits broker orders.

## 6. Integration tests

Test each boundary separately:

1. Module 1 → Module 2: candidate mapping and analysis job creation.
2. Module 2 → Module 3: normalized analysis is accepted; invalid/REVIEW/stale analysis is rejected or sent to review.
3. Module 3 → Module 4: approved persisted intent executes in paper mode exactly once.
4. Module 4 → Module 5: confirmed fills create correct open position quantities.
5. Module 5 → Module 2/3: reassessment/exit is deduplicated and routed through the decision engine.

Then run the whole lifecycle in `tests/end_to_end/`.

## 7. Mandatory negative scenarios

- Invalid/ambiguous ticker or unresolved broker security ID.
- TradingAgents unavailable, malformed response, rate limit or timeout.
- Analysis rating is `REVIEW`, missing or stale.
- No/freshness-failed market price; market closed.
- Stale or missing portfolio/account snapshot.
- Invalid stop, zero/negative per-share risk or zero calculated quantity.
- Insufficient funds/margin, exposure cap exceeded or kill switch active.
- Duplicate candidate, analysis, decision or order request.
- Broker timeout after submission, partial fill, reject or cancel.
- Market-feed disconnect while a position is open.
- Restart with queued/running analysis and open positions.
- SQLite `database is locked`/busy conditions.
- TradingAgents memory/checkpoint directory unavailable or corrupted.

## 8. Safety invariants

1. Module 2 never places orders.
2. Module 3 never calls broker order methods.
3. Module 4 executes only persisted approved `OrderIntent` records.
4. Module 5 never bypasses Module 3/4 to sell.
5. Live trading is off by default; paper mode is the default.
6. Every broker submission has an idempotency key and decision/intent reference.
7. Submitted order is not equivalent to filled order.
8. Position size and holdings use confirmed fills.
9. AI output/memory cannot override mandatory risk limits or kill switch.
10. Stale/unavailable market/account data cannot approve a new entry.
11. Hard stop-loss and mandatory session exit logic is deterministic and not dependent on an LLM.
12. Secrets/access tokens are never written to logs or database error fields.
13. New entries fail closed when critical market/broker/account data is unavailable.
14. TradingAgents memory is not authoritative for TradeAI realized P&L or Dhan execution history.

## 9. Observability and performance

Every workflow should carry a correlation ID and persistent identifiers:

`candidate_id → analysis_id → decision_id → order_intent_id → order_id/broker_order_id → position_id → exit_decision_id`.

Log module, operation, correlation/entity IDs, timestamps/duration, status, sanitized error code, profile/provider/model/strategy versions and market-data timestamp/source. Never log credentials, full authorization headers or sensitive account payloads.

Measure AI queue time, provider run time, model/provider usage where available, retry/failure rates and report storage. Limit concurrent graph runs. The FastAPI event loop must stay responsive. The existing harness tick must not start repeated AI runs, and the position monitor must not poll an LLM on every price tick.

## 10. Definition of module completion

A module is complete only when:

- Its public service interface and DTOs are documented.
- Its module-isolated unit/repository/adapter tests pass.
- Failure cases are covered.
- It does not make forbidden cross-module/private imports.
- It can run with fakes and a temporary SQLite database.
- Its logs and errors are useful and sanitized.
- Its acceptance checklist is checked off.

Integration completion is a separate gate and requires boundary tests. End-to-end completion is a further separate gate.
