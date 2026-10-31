# Cross-module workflows

Workflows own orchestration between public module service interfaces. Modules do not call another module's private repository, models or API routes. Calls stay in-process and pass the shared Pydantic contracts.

## Integrated boundaries

- `StockSelectionAnalysisWorkflow` checks ownership and a resolved analysis ticker before it asks Module 2 to create an idempotent job. FastAPI exposes this path at `POST /api/v1/analysis/jobs`; the single lifespan worker runs the configured lazy provider.
- `AnalysisDecisionWorkflow` loads an owner-scoped completed result, then delegates freshness, rating interpretation and every risk check to Module 3.
- `DecisionExecutionWorkflow` accepts only persisted approved decisions. Module 4 performs its own persisted-intent validation, idempotency reservation, broker submission and reconciliation.
- `ExecutionPositionWorkflow` reconciles Module 4 state, requires a confirmed fill, reads the current open quantity and average price from an injected broker/paper position reader, and then calls Module 5. It does not infer positions from submitted quantities.
- `PositionExitWorkflow` processes each new persisted monitor trigger once. Module 3 approves or rejects the deterministic exit, and only Module 4 can submit it. The emergency stop/time path has no AI dependency.

The boundary tests use fake analysis, market, account, broker and position readers with temporary SQLite. Only the Stock Selection → AI Analysis workflow is currently exposed through new FastAPI routes. Decision/execution/monitoring route composition waits for trusted production market, account-risk and position providers; callers must not submit those snapshots as client-controlled JSON. No live order path is added here.

Run the boundary tests from `backend/`:

```powershell
python -m pytest tests/integration/test_workflow_boundaries.py -q
```
