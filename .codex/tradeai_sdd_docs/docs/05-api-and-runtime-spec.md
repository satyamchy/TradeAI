# 05 — API and Runtime Specification

## 1. API principle

HTTP is for the React frontend and external clients only. Internal module communication uses Python calls.

FastAPI routers must:

1. Validate the HTTP request.
2. Resolve the database/session and authenticated user context.
3. Call an application/workflow service.
4. Return a Pydantic response model.

Routers must not instantiate TradingAgents, calculate position size, read/write ORM entities directly, or call Dhan order methods.

## 2. Proposed frontend-facing API

These are proposed versioned routes. Preserve existing routes during refactoring and either delegate them to the new services or introduce these routes additively. Do not break current frontend calls without a coordinated frontend update.

| Method | Route | Module | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/candidates` | 1 | Create manual candidate batch |
| `GET` | `/api/v1/candidates` | 1 | List candidates |
| `GET` | `/api/v1/candidates/{candidate_id}` | 1 | Candidate detail |
| `POST` | `/api/v1/analysis-runs` | 2 | Queue analysis for one/more candidates |
| `GET` | `/api/v1/analysis-runs/{analysis_id}` | 2 | Read job status/result |
| `GET` | `/api/v1/analysis-runs` | 2 | List recent analyses |
| `POST` | `/api/v1/decisions/evaluate` | 3 | Evaluate an analysis against a named strategy |
| `GET` | `/api/v1/decisions/{decision_id}` | 3 | Read decision and reasons |
| `POST` | `/api/v1/executions` | 4 | Execute a persisted approved intent (paper by default) |
| `GET` | `/api/v1/executions/{order_id}` | 4 | Read broker/paper order status |
| `GET` | `/api/v1/positions` | 5 | List open/closed positions |
| `POST` | `/api/v1/positions/{position_id}/reassess` | 5 | Request fresh analysis |
| `POST` | `/api/v1/positions/{position_id}/exit-evaluation` | 5/3 | Request a rules-based exit evaluation |
| `GET` | `/api/v1/system/health` | Shared | App/database/provider health without exposing secrets |

Existing TradeAI endpoints documented in the backend README include conversational analysis, stock analysis, analysis history, market data, `/v1/trading/orders`, square-off, guardrail status/toggle, jobs and harness status/start/stop. Preserve them while migrating internals. Confirm exact prefixes and route names in the local source before changing them.

## 3. Internal function-call workflow

A single orchestration function should coordinate the end-to-end process. The exact class/function names may vary, but the boundaries must remain stable.

```python
async def analyze_candidates_and_evaluate(batch_id: UUID, strategy_key: str):
    candidates = await stock_selection_service.get_batch(batch_id)

    results = []
    for candidate in candidates:
        job = await ai_analysis_service.request_analysis(
            AnalysisRequest(candidate_id=candidate.id, provider="TRADING_AGENTS")
        )
        # The analysis worker completes the job asynchronously.
        results.append(job)
    return results
```

After analysis completion:

```python
async def evaluate_completed_analysis(analysis_id: UUID, strategy_key: str):
    decision = await decision_engine.evaluate_entry(
        EvaluateTradeRequest(analysis_id=analysis_id, strategy_key=strategy_key)
    )
    if decision.order_intent is None:
        return decision
    # Automatic execution is allowed only when paper/live settings and policy permit it.
    return decision
```

The examples are illustrative. A route must not wait synchronously for a long TradingAgents run. The API returns a job receipt; the client polls or receives a WebSocket event when the result is ready.

## 4. Analysis job lifecycle

Persist job state using the existing `analysis_jobs` where possible or the new `analysis_runs` entity:

`QUEUED → RUNNING → COMPLETED`

Error states:

- `FAILED_RETRYABLE`
- `FAILED_FINAL`
- `CANCELLED`

Required fields: job ID, candidate ID, provider, attempt count, created/started/completed timestamps, sanitized error code/message and result reference.

### Worker rules

- An in-process worker is started/stopped through FastAPI lifespan.
- The worker claims a queued job inside a short DB transaction, marks it `RUNNING`, releases the transaction, then invokes the provider.
- The LLM/provider call must not run inside an open database transaction.
- On completion, persist result/status in a short transaction.
- On failure, apply bounded retries with backoff for retryable provider/network errors; do not retry invalid symbols or invalid configuration.
- On startup, recover jobs left `RUNNING` after an unclean shutdown according to retry limits.
- The first implementation runs one analysis job at a time. Add configurable concurrency only after tests show that TradingAgents graph state, provider quotas and SQLite persistence remain safe.
- Do not let the existing 5-second trading harness tick enqueue the same analysis repeatedly.

## 5. Error and status conventions

Use HTTP status codes consistently:

- `201` — candidate or decision resource created.
- `202` — analysis queued.
- `200` — read/evaluation completed.
- `400` — malformed request.
- `404` — resource not found.
- `409` — duplicate/conflicting state or idempotency conflict.
- `422` — semantic validation failure.
- `429` — configured provider/rate/concurrency limit.
- `503` — required external provider/broker unavailable.

Use the shared error schema from `03-contracts-and-function-interfaces.md`.

## 6. WebSocket/events

WebSocket is optional for the first milestone. Polling `GET /analysis-runs/{id}` is sufficient.

When added, WebSocket events are read-only status updates such as:

- `analysis.queued`
- `analysis.started`
- `analysis.completed`
- `analysis.failed`
- `order.updated`
- `position.updated`

The socket must not become an alternate route for creating or executing orders.

## 7. App lifecycle

On startup:

1. Load settings and validate required configuration.
2. Initialize DB engine/session factory.
3. Apply/verify migrations as a deployment step (do not run destructive schema creation on every startup).
4. Initialize shared Dhan client lazily or only when credentials are configured.
5. Register analysis providers.
6. Recover pending jobs.
7. Start the job worker and existing harness/watchdog only when explicitly enabled.

On shutdown:

1. Stop accepting new background work.
2. Allow in-flight jobs a bounded graceful shutdown period or mark them recoverable.
3. Stop the harness/watchdog cleanly.
4. Close market-feed connections.
5. Dispose DB engine and executors.

## 8. Frontend compatibility

Keep React + Vite. The frontend should use the public FastAPI endpoints only. It should not import Python module contracts or communicate with TradingAgents directly.

The dashboard should display candidate status, analysis status, provider/rating/reports, decision status/reasons, order status/fills and position status. Do not show an order as filled merely because an execution request was submitted.


## 9. Module-local test execution and development endpoints

The five modules are not separate HTTP services and do not each need a separate FastAPI app. During development, test a module by running its pytest directory. The single app may expose one `/api/v1/system/health/modules` diagnostic endpoint for module registration/configuration checks, but it must not pretend that a provider or broker is healthy merely because its Python package imported.

Recommended local commands (run from `backend/`):

```powershell
pytest tests/structure -q
pytest tests/unit/modules/stock_selection -q
pytest tests/unit/modules/ai_analysis -q
pytest tests/unit/modules/decision_engine -q
pytest tests/unit/modules/execution -q
pytest tests/unit/modules/position_monitoring -q
pytest tests/integration -q
pytest tests/regression -q
pytest tests/end_to_end -q
```

The default test suite must not require real LLM API keys or a live Dhan account. Provider/broker smoke tests are explicitly marked `external` and run only on demand.

## 10. Runtime sequencing

1. FastAPI lifespan initializes settings, logging, database engine/session factory and migrations/health checks.
2. Register module services and adapters using dependency injection.
3. Start only the existing required runtime workers/harness components when explicitly enabled by configuration.
4. Use a bounded analysis-job worker for synchronous TradingAgents graph work; avoid blocking the ASGI event loop.
5. On shutdown, stop accepting new jobs, finish/cancel according to policy, close provider/broker clients and dispose database connections.

The structure-only milestone must not automatically start the trading harness or contact Dhan order endpoints. Default flags remain `TRADING_MODE=PAPER`, `LIVE_TRADING_ENABLED=false`, `HARNESS_AUTO_START=false`.
