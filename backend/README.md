# TradeX API

FastAPI runs on port 8000. Setup instructions are in the [root README](../README.md); deployment notes are in [REPO.md](../REPO.md).

The single composition root is `app/application.py`; `main.py` remains the compatibility launcher. Five business packages live under `app/modules/`. Shared database/session, settings, security, market data and logging interfaces live under `app/shared/` or the existing `app/market/`. Cross-module coordination belongs under `app/workflows/`. The existing automation runner remains the single scheduler.

SQLite schema changes are managed by Alembic. The configured database path remains `tradex.db` by default, and legacy CRUD interfaces continue to use the same file. Existing compatibility routes stay mounted for the React frontend.

AI Analysis uses the lazy pinned TradingAgents v0.7.1 adapter, one in-process FastAPI worker, and normalized result persistence. `POST /api/v1/analysis/jobs` accepts a typed request and an `Idempotency-Key`; owner-scoped GET routes return job status and results. Automated tests use fake analysis output and make no paid LLM calls.

The public paper lifecycle APIs are under `/api/v1/paper`: start and poll a workflow, advance completed analysis through Module 3 risk approval and paper BUY, view decisions/orders/confirmed positions, reconcile an uncertain order, and request position reassessment through Module 5 and Module 3 before paper SELL. The client cannot submit market prices, capital, positions, risk limits, decisions or order quantities. The existing `TradingGateway` and `PaperLedger` remain the single execution path.

This build is locked to `TRADING_MODE=paper` and `LIVE_TRADING_ENABLED=false`; FastAPI refuses startup if live mode or the live gate is enabled. Position reassessment is request-driven; the existing scheduler is not duplicated or connected to the new API workflow. The frontend remains compatible through its current routes.

End-to-end and failure-recovery evidence is in `tests/end_to_end/README.md`. Route behavior and status codes are documented in handler docstrings and FastAPI's `/docs` page.

Run one process from this directory:

```powershell
python main.py
python -m pytest tests -q
```
