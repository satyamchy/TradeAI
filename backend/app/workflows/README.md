# Cross-module workflows

Workflows own orchestration between public module service interfaces. Modules do not call another module's private repositories, models or API routes. Calls stay in-process and pass typed Pydantic contracts.

## Integrated boundaries

- `StockSelectionAnalysisWorkflow` checks ownership and a resolved analysis ticker before it asks Module 2 to create an idempotent analysis job. FastAPI exposes it at `POST /api/v1/analysis/jobs`; the single lifespan worker runs the configured lazy provider.
- `AnalysisDecisionWorkflow` loads an owner-scoped completed result, returns an existing decision for the same analysis and strategy when one exists, and otherwise delegates freshness, rating interpretation and risk checks to Module 3.
- `DecisionExecutionWorkflow` accepts only persisted approved decisions. Module 4 validates the persisted intent, reserves its idempotency key, submits through the injected broker adapter and reconciles status without blind retries.
- `ExecutionPositionWorkflow` reconciles Module 4 state, requires a confirmed fill, reads the current open quantity and average price from the injected paper position provider, and then calls Module 5. It does not infer positions from submitted quantities.
- `PositionExitWorkflow` processes each new persisted monitor trigger once. Module 3 approves or rejects the deterministic exit; only Module 4 can submit it. The exit path has no AI dependency.
- `PaperTradingServiceFactory` composes owner-scoped trusted providers from the existing `TradingGateway` and shared repositories in the FastAPI application. The app refuses to start outside paper mode or when the live gate is enabled.

## Public paper workflow

The owner-scoped routes under `/api/v1/paper` start and inspect a workflow, advance a completed analysis through risk approval and paper BUY, list decisions/orders/confirmed positions, reconcile an uncertain order, and request deterministic position reassessment. Reassessment routes any stop, target or session trigger through Module 3 before Module 4 paper SELL. Request data never supplies the price, account, holdings, risk limits, decision or quantity.

Analysis and entry advancement are separate calls so a client can observe asynchronous analysis status before a paper order can be created. Position reassessment is request-driven in this release; the existing automation runner remains the single scheduler and does not automatically advance API workflows.

The end-to-end suite uses real SQLAlchemy repositories and temporary SQLite, the existing `TradingGateway`/`PaperLedger`, fake normalized analysis output and deterministic market data. It covers BUY/SELL lifecycle P&L, duplicate requests, stale prices, insufficient capital, partial fills, rejected orders and restart reconciliation. No Dhan orders or paid LLM calls are made.

Run from `backend/`:

```powershell
python -m pytest tests/integration tests/end_to_end -q
```
