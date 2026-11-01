# Production Provider Composition and Paper E2E

**Updated:** 2026-11-01  
**Status:** Paper lifecycle integrated and verified. Live execution remains disabled.

## Provider composition

FastAPI's single composition root now creates an owner-scoped paper workflow factory using the existing session factory, repositories, and per-user `TradingGateway`. No additional broker client, SQLite store, schema mechanism, scheduler, or watchdog was introduced.

| Boundary | Production adapter | Trust and safety behavior |
| --- | --- | --- |
| Market data | `TradingGatewayMarketDataProvider` | Uses the existing gateway for current quotes and candles. Decision snapshots include market-session and entry-cutoff state; missing quotes fail closed. |
| Account risk | `TradingGatewayAccountRiskProvider` | Reads paper cash and positions, marks exposure/P&L with current quotes, loads saved risk limits from the existing SQLite settings row, and includes outstanding execution symbols. Paper cash is the available margin because the ledger does not provide leverage. |
| Confirmed positions | `TradingGatewayConfirmedPositionProvider` | Returns only matching positive open positions read from the user's paper ledger. Module 5 does not infer a position from an order submission. |
| Broker execution | `ExistingTradingGatewayAdapter` | Wraps the existing `TradingGateway`; paper ledger rejections are persisted as rejections, and tagged paper fills can be reconciled after a lost response or service restart. |

The five module services are composed per user. Module 3 owns entry and exit approval. Module 4 receives only persisted approved intents and independently validates, reserves idempotency, submits, and reconciles. Module 5 evaluates confirmed positions and persists deduplicated triggers.

## Public paper workflow

The owner-scoped API is mounted under `/api/v1/paper`:

- `POST /workflows` selects one local NSE instrument and starts an idempotent background analysis.
- `GET /workflows/{analysis_id}` reports analysis, decision, order, confirmed position, and lifecycle P&L.
- `POST /workflows/{analysis_id}/advance` waits for completed analysis, delegates all trade/risk approval to Module 3, then asks Module 4 to submit an idempotent paper BUY.
- `GET /decisions`, `GET /orders`, and `GET /positions` expose owner-scoped decisions, persisted execution states, and confirmed paper positions.
- `POST /orders/{order_id}/reconcile` recovers an uncertain/working broker outcome without blind resubmission.
- `POST /positions/{symbol}/reassess` runs deterministic stop, target, and session evaluation. A sell is sent only after a Module 3 approval and Module 4 validation.

The frontend's existing routes remain mounted and its source was left unchanged. Analysis advancement and position reassessment are request-driven in this release; the existing scheduler was not duplicated or connected to the new APIs.

## Test evidence

The end-to-end tests use real SQLAlchemy repositories, temporary SQLite, the existing `TradingGateway` and `PaperLedger`, a mocked analysis provider, and deterministic market data. They make no Dhan order call or paid LLM call. Coverage includes:

- A complete public API lifecycle: selection, analysis, risk-approved BUY, confirmed position, monitor trigger, Module 3-approved SELL, and final realized P&L.
- Sequential and concurrent duplicate requests, proving one analysis job, decision, and paper order.
- Stale prices and insufficient paper capital rejected before execution.
- Partial fills, rejected orders, and an accepted paper fill recovered after rebuilding the workflow service over the same database and ledger.
- Provider adapter tests for quote/candle normalization, saved risk limits, exposure and P&L, pending symbols, and owner-scoped confirmed positions.

Validation from `backend/`:

- `python -m pytest tests -q` — **60 passed**, one Starlette deprecation warning.
- Module-local suite — **61 passed**.
- `python -m compileall -q app tests alembic` — passed.
- `npm run build` from `frontend/` — passed; Vite built 84 modules.
- `python -m pip check` — failed on pre-existing global LangChain/LangGraph and TensorFlow dependency conflicts. No package upgrades were made to resolve them.

The global Python 3.11 environment does not include Alembic, so migration-backed tests were run with the existing pinned Alembic requirement installed into a temporary workspace-local test dependency directory. No project requirements file or TradingAgents source was changed.

## Remaining limits

- This application build refuses startup unless `TRADING_MODE=paper` and `LIVE_TRADING_ENABLED=false`. No live order path is enabled.
- The current frontend has not been migrated to the new paper workflow endpoints; the APIs are available and the legacy frontend surface remains intact.
- Workflow advancement and position reassessment are explicit API actions. Periodic monitoring through the existing harness is future integration work.
- The existing Dhan quote adapter captures retrieval time, while its legacy candle method omits exchange bar timestamps. Candle-series `observed_at` is therefore the fetch time; it is not a bar timestamp. Production stale-quote behavior should be revisited if the broker API exposes source timestamps.
- `pip check` remains red until the separate global environment's LangChain/LangGraph and TensorFlow package set is reconciled in the planned dependency-upgrade phase.
