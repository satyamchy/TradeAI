# TradeX API

FastAPI on port 8000. How to run it, the three roles, and paper versus live are in the [root README](../README.md). Production is in [REPO.md](../REPO.md).

The app is composed in `app/application.py`; `main.py` remains the compatibility launcher. The five business packages are under `app/modules/`. Existing route handlers remain mounted as API compatibility adapters. Shared settings, database/session utilities, security, and structured logging are under `app/shared/`. Cross-module coordination belongs under `app/workflows/`; the existing single automation runner is exposed through `app/harness/`.

SQLite schema changes are managed only by Alembic. The configured `DATABASE_PATH` remains `tradex.db` by default. Startup backs up and adopts a recognized legacy database before applying revisions; an unknown or incomplete legacy schema fails closed. Legacy CRUD functions remain temporarily available through the same file. Revisions 004–008 add only module-owned candidate, analysis, decision/intent, execution lifecycle and monitoring-trigger tables. All five module services have independent fake-based tests, and workflows I1–I5 have integration tests against temporary SQLite.

AI Analysis includes the lazy pinned TradingAgents v0.7.1 adapter, a single in-process FastAPI worker, and normalized result persistence. `POST /api/v1/analysis/jobs` accepts a typed `AnalysisRequest` with an `Idempotency-Key`; `GET /api/v1/analysis/jobs/{analysis_id}` returns status and `GET /api/v1/analysis/results/{analysis_id}` returns the owner-scoped normalized result. The default provider constructs no external client until a submitted job is run. No real LLM smoke call has been made. Execution accepts persisted approved-intent IDs, reserves idempotency before broker calls, and reconciles fills through an adapter wrapping the existing single `TradingGateway`. Live trading remains gated off. Position Monitoring returns deduplicated exit candidates; the workflow routes new triggers through Module 3 and then Module 4, and never submits directly.

I2–I5 are composed as injectable workflows and verified using fake market, account and broker services. They are not yet connected to new public order routes or a real-data end-to-end lifecycle. Keep the existing guarded legacy routes and frontend behavior while those providers are reviewed. No Dhan call, live order or paid model call was used by the structural/integration tests.

Live order placement requires `APP_ENV=production`, `TRADING_MODE=live`, and `LIVE_TRADING_ENABLED=true`. The safety gate defaults to false. Keep it false throughout structural tests, integration work, and paper trading.

Route behavior and status codes are the docstrings on the handlers. FastAPI publishes them at `/docs`.

Run one process. Do not add uvicorn workers. SQLite, the order lock, and the automation loop live in this process.

From this directory, with the virtualenv active:

```text
python main.py
python -m pytest tests -q
```
