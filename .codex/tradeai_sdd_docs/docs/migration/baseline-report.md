# TradeX Phase 0 Baseline Report

**Captured:** 2026-10-31  
**Scope:** Read-only application/database baseline before the modular refactor. The only persistent artifact created is the SQLite online backup noted below. No application source was changed during baseline capture.

## Repository and environment

- Repository root: `C:\Users\Satyam Kumar\Desktop\TradeX`.
- Backend: one FastAPI application under `backend/app`, launched by `backend/main.py`.
- Frontend: React + Vite under `frontend`; `frontend/node_modules` is present and `frontend/package-lock.json` exists. The package manifest uses `latest` for most direct dependency versions.
- Backend Python: project virtual environment is `backend/myenv`; Python 3.11.5. Relevant installed versions include FastAPI 0.141.1, Pydantic 2.13.5, SQLAlchemy 2.0.54, `dhanhq` 2.2.0, LangGraph 1.2.11, and pytest 9.1.1. The installed environment does not list TradingAgents as a Python package. Alembic is absent. `bcrypt` is declared by `backend/requirements.txt` but is missing from `backend/myenv`.
- `python -m pip check` from `backend/myenv`: **passed** (`No broken requirements found`). This did not detect the absent direct requirement `bcrypt`.
- A system Python 3.11.5 is also installed and has `bcrypt` 5.0.0. It was used only as a fallback for the isolated API smoke test below; project test results are from `backend/myenv`.
- The environment file and database path were not printed. Dhan, LLM, and encryption secrets were not read into this report.

## Baseline checks

| Check | Command / setup | Result |
|---|---|---|
| Full backend suite | `backend/myenv/Scripts/python.exe -m pytest tests -q` from `backend/` | **Blocked during collection.** `tests/test_dhan_token.py` imports `app.auth`, which raises `ModuleNotFoundError: bcrypt`. Pytest stopped before running the suite. |
| Existing regressions excluding token test | `backend/myenv/Scripts/python.exe -m pytest tests/test_pending.py tests/test_intraday_cycle.py -q` | **13 passed, 5 failed.** All five failures are import errors for the same missing `bcrypt` dependency. One Starlette deprecation warning. |
| Dependency consistency | `backend/myenv/Scripts/python.exe -m pip check` | **Passed**, with the caveat above: the declared-but-uninstalled `bcrypt` dependency is not reported by this command. |
| Frontend production build | `npm run build` from `frontend/` | **Passed.** Vite 8.0.16 transformed 84 modules and emitted the production bundle. |
| FastAPI startup and safe routes | `TestClient` using a fresh temporary SQLite path, `TRADING_MODE=paper`, empty Dhan/Groq credentials, no-op NSE holiday loader; system Python fallback | **Passed in fallback environment.** Startup completed. `/openapi.json` exposed 25 paths and 27 operations. Unauthenticated session returned 401; admin and trader login returned 200; admin-only and trader-only checks denied the wrong roles with 403. No broker submission or paid LLM call was made. |
| Representative response contracts | Same isolated API smoke test | **Observed.** Login and user creation return a public `user` object (keys: `id`, `username`, `role`, `disabled`, `dhan_saved`, `automation_state`, `automation_methods`, `trading_index`). Pending orders return `{count, orders}`; automation status returns state/mode/session fields; funds return `{mode, available_balance_inr}`; events return `{count, events}`. |
| Frontend/API connection settings | `frontend/src/api/stockApi.js`, Vite config, API CORS preflight | Frontend base URL defaults to `http://localhost:8000`, sends credentials, and calls `/api/v1/...`. Preflight from `http://localhost:5173` returned 200 with that allowed origin. This was an ASGI/CORS smoke test, not a browser end-to-end test. |
| Existing project-environment startup | Import/startup via `backend/myenv` | **Blocked** by the missing `bcrypt` package. The successful isolated API smoke test used the separately installed system interpreter; this distinction must be closed by installing declared dependencies in the project environment before Phase 1 verification. |

During Phase 1 startup-test setup, the project environment also proved to be missing `itsdangerous`, which Starlette's existing `SessionMiddleware` imports. This package was not listed in the original requirements. It is recorded as a second pre-existing environment/setup gap, not as a refactor regression.

### Existing API routes

The current prefix is `/api/v1`. Routes are grouped as follows:

- Auth: `POST /auth/login`, `POST /auth/logout`, `GET /auth/session`.
- Users: `GET/POST /users`, `PATCH /users/{user_id}`.
- Automation: `GET /automation/status`, `POST /automation/enable`, `POST /automation/disable`, `POST /automation/square-off-open-positions`, `GET /automation/recent-cycles`, `GET /automation/settings`, `PATCH /automation/settings`.
- Account: `GET /account/funds`, `GET /account/positions`, `GET /account/orders`, `PUT /account/dhan-credentials`.
- Screening: `GET /screener/nifty50`.
- Orders: `POST /orders/intraday`, `POST /orders/close`, `POST /orders/delivery`, `GET /orders/pending`, `POST /orders/pending/{pending_id}/execute`, `POST /orders/pending/{pending_id}/reject`, `DELETE /orders/{dhan_order_id}`.
- Suggestions and events: `POST /suggestions`, `GET /events`.

The current frontend uses these routes directly. Existing behavior distinguishes roles: admin manages users/settings, trader actions are denied to admin/viewer, and viewer is read-only. No order route was submitted by the smoke test; the admin intraday attempt was rejected with 403 before broker access.

## SQLite backup and actual schema

Before any schema change, SQLite's online backup API created:

`backend/data/backups/tradex-pre-refactor-20261031.db`

The backup is a database artifact covered by the backend `*.db` ignore rule. The source `backend/tradex.db` was not migrated or modified.

Inspection was performed on the backup in read-only mode. Results:

- SQLite integrity check: `ok`.
- Foreign-key check: no violations; there are no declared foreign keys.
- Actual tables and row counts: `users` (2), `pending_orders` (1), `order_events` (2). Total: 5 rows.
- Actual schema has no CHECK constraints. `users.username` has a UNIQUE constraint backed by SQLite's implicit `sqlite_autoindex_users_1`. No other indexes were present.
- The actual database has no `risk_settings`, `dhan_process_credential`, or `protective_stops` tables, and its three existing tables do not yet have the newer columns added by `app/db.py::_migrate` (`trading_index`, `correlation_id`, `broker_order_id`, `dhan_token_refreshed_at`).
- This is material drift: `app/db.py` currently declares six tables and adds those four columns at startup, whereas the saved database currently contains only three tables. Migration must therefore model a legacy adoption step and a follow-up upgrade, not falsely stamp the live file as already having the six-table current application shape.

## Paper ledger

An aggregate-only structural check parsed `backend/paper_ledgers/*.json` without emitting account values:

- Files: 1; parse failures: 0; structural failures: 0.
- Positions: 1; retained orders: 1.
- Balance was finite and nonnegative; stored position quantity was nonzero; average/last prices were finite and positive; `next_order_id` was a positive integer.
- Basic structural checks: **passed**.
- Full cash/position reconciliation cannot be established from this format: it retains at most 100 orders and has no complete fill/deposit/withdrawal journal. This is a baseline observability limitation, not an inferred ledger failure.

## Dhan authentication/token renewal

`tests/test_dhan_token.py` contains mocked expiry parsing, due-time, renewal-body-shape, and saved-token replacement tests, including a stubbed renewal function. The test file could not be collected in the project environment because `bcrypt` is absent. No Dhan endpoint was called, no real token was renewed, and no credential value was inspected. Separate coverage for encrypted-at-rest failure/rotation and a broader authentication credential lifecycle is not present in the existing tests.

## Baseline disposition

The application’s safe API behavior and frontend build are observable in the fallback smoke setup. The project virtual environment is not yet a valid test/startup environment because a declared dependency is missing. Record the test failures above as pre-refactor failures; do not attribute them to the restructuring. Before Phase 1 acceptance, install/resolve the declared dependency set in the project environment without upgrading TradingAgents or its dependency stack, then rerun the regression suite.

## Phase 1 verification addendum

After preserving the baseline failures above, the Phase 1 environment setup installed only the declared missing `bcrypt` dependency plus the new migration/runtime dependencies Alembic and `itsdangerous`; no TradingAgents package or source was changed. The pre-refactor failures were rerun as part of the Phase 1 suite and passed after dependency resolution. See the [implementation status](../../implementation-status.md) for Phase 1 evidence.
