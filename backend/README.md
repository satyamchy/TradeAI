# TradeX API

FastAPI on port 8000. How to run it, the three roles, and paper versus live are in the [root README](../README.md). Production is in [REPO.md](../REPO.md).

The app is composed in `app/application.py`; `main.py` remains the compatibility launcher. The five business packages are under `app/modules/`. Existing route handlers remain mounted as API compatibility adapters while module services are implemented incrementally. Shared settings, database/session utilities, security, and structured logging are under `app/shared/`. Cross-module coordination belongs under `app/workflows/`; the existing single automation runner is exposed through `app/harness/`.

SQLite schema changes are managed only by Alembic. The configured `DATABASE_PATH` remains `tradex.db` by default. Startup backs up and adopts a recognized legacy database before applying revisions; an unknown or incomplete legacy schema fails closed. Legacy CRUD functions remain temporarily available through the same file. The new `analysis_jobs` table is additive and does not imply that AI provider execution is implemented yet.

Live order placement requires `APP_ENV=production`, `TRADING_MODE=live`, and `LIVE_TRADING_ENABLED=true`. The safety gate defaults to false. Keep it false throughout structural tests, integration work, and paper trading.

Route behavior and status codes are the docstrings on the handlers. FastAPI publishes them at `/docs`.

Run one process. Do not add uvicorn workers. SQLite, the order lock, and the automation loop live in this process.

From this directory, with the virtualenv active:

```text
python main.py
python -m pytest tests -q
```
