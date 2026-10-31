# TradeX Phase 1 File-by-File Restructuring Plan

This plan follows the Phase 0 baseline in [baseline-report.md](baseline-report.md). It is the reviewed migration map for Phase 1; business behavior moves behind typed interfaces incrementally so current routes and the React desk continue to work.

## Target package layout

```text
backend/
  main.py                         # compatibility launcher
  app/
    application.py                # one FastAPI composition root/lifespan
    api/                          # existing route modules; legacy compatibility surface
    api/v1/                       # module-oriented routes and compatibility inclusion
    modules/
      stock_selection/
      ai_analysis/
      decision_engine/
      execution/
      position_monitoring/
    workflows/                    # intraday and cross-module lifecycle coordination
    harness/                      # the single scheduler/automation runner
    jobs/                          # replaceable, in-process analysis-job service
    shared/                        # settings, DTO contracts, DB/session, security, logging
  alembic/                         # sole schema-change authority
  tests/
    structure/ regression/ integration/ e2e/
  docs/migration/
```

Each business module gets `__init__.py`, `README.md`, `schemas.py`, `service.py`, and `tests/`. Importing any module must remain inert: no Dhan, LLM, network, database, or scheduler client is constructed at import time.

## Existing file ownership and treatment

| Existing file(s) | Phase 1 treatment / target owner |
|---|---|
| `backend/main.py` | Keep as the supported compatibility launcher; delegate app creation to `app/application.py`. Preserve `python main.py`. |
| `backend/app/api/auth.py`, `users.py`, `events.py`, `account.py` | Keep as platform-facing route handlers. Move shared config/database/security imports behind `app/shared/` compatibility interfaces, without changing their response contracts. |
| `backend/app/api/automation.py` | Retain current route surface as a compatibility adapter. Later call `harness/` and `workflows/`; keep request validation and role checks at the API boundary. |
| `backend/app/api/screener.py` | Retain current `/screener/nifty50` response and adapt to Module 1 public service once that module is implemented. |
| `backend/app/api/suggestions.py` | Retain as a compatibility route; later delegate job creation to Module 2 via `jobs/` and a workflow. |
| `backend/app/api/manual_orders.py` | Keep the existing manual/pending route contract and guardrails. Gradually delegate to Module 3 and Module 4 public services; do not duplicate order execution. |
| `backend/app/trading/screener.py`, `nifty50.py`, `nse_session.py`, `backend/app/market/nse_public.py` | Existing screen, index, market snapshot, and session-clock implementation stays in place initially. Module 1 wraps it; no provider/network work occurs during import. |
| `backend/app/trading/risk_limits.py` | Retain as the legacy implementation until Module 3 independently replaces/wraps it. Module 3 contracts remain provider-neutral and must not import AI/LangGraph/TradingAgents. |
| `backend/app/broker/trading_gateway.py`, `dhan_gateway.py`, `dhan_token.py` | Preserve as the one execution path and one Dhan client. Module 4 wraps these services; keep SDK calls injected/mockable in tests and preserve existing guardrails. |
| `backend/app/broker/paper_ledger.py` | Preserve the existing paper ledger and path. Do not create a second ledger or silently move account data into new tables. Add stronger reconciliation only in the appropriate later execution phase. |
| `backend/app/trading/intraday_cycle.py` | Move cross-module coordination behind `workflows/` using a thin wrapper first; maintain one implementation/schedule during transition. |
| `backend/app/trading/automation_runner.py` | Scheduling/runner ownership moves behind `harness/`. Keep a single runner instance and avoid starting another watchdog/scheduler. |
| `backend/app/config.py`, `db.py`, `auth.py`, `utils/logger.py` | Become compatibility facades over `app/shared/config`, shared DB/security interfaces, and the common structured logger. Preserve existing import paths until callers migrate. |
| `backend/tests/test_pending.py`, `test_intraday_cycle.py`, `test_dhan_token.py` | Preserve as regression tests; fix only environment/dependency or refactor regressions with explicit test evidence. Add module-local and central structural test directories. |
| `frontend/src/api/stockApi.js` and pages | Leave unchanged during Phase 1. Introduce module-oriented endpoints behind compatibility; update the client only when the replacement contract is implemented and ready. |
| Root/backend READMEs, `REPO.md`, `docs/PROJECT_SETUP.md`, SDD status | Update setup, module ownership, migration/backup safety, live-trading gate, and evidence/status after implementation. |
| `backend/TradingAgents/**` | External dependency; do not edit, reformat, or include in the restructuring. Module 2 may access its public interface behind an adapter in its own later phase. |

## Phase 1A — structure and public contracts

1. Add the five module packages and module-local test folders. Define shared Pydantic contracts and typed service protocols with no runtime client construction or new trading behavior.
2. Add `workflows/`, `harness/`, `jobs/`, `shared/`, and `api/v1/` package boundaries.
3. Make `app/application.py` the sole composition root. Keep legacy route modules mounted during transition and keep `backend/main.py` as a launcher.
4. Add import tests that import each module in a clean process without Dhan/LLM credentials and verify no provider client or scheduler starts.

## Phase 1B — database, jobs, configuration and logging

### Migration adoption strategy

The Phase 0 copy proves the on-disk DB is a three-table legacy core and lacks columns and auxiliary tables currently declared by the legacy initializer. The migration sequence must preserve this distinction:

1. `legacy_core` baseline: describe/create only the three actual core tables (`users`, `pending_orders`, `order_events`) with their observed defaults and unique username constraint.
2. `legacy_runtime` upgrade: idempotently add the four current application columns if absent and create only the three runtime tables already required by existing features (`risk_settings`, `dhan_process_credential`, `protective_stops`). On a fresh DB the baseline creates core, then this revision creates the current application shape.
3. `analysis_jobs` upgrade: add only the requested analysis job table and its idempotency index/constraint.

For an existing database with no Alembic marker, first require a recognized legacy core signature, create a second backup, rehearse the revision path against a working copy, compare schema and row counts, then stamp only `legacy_core` and upgrade to head. If the DB already contains some or all runtime objects, the runtime revision checks presence and alters only missing parts. An unknown schema fails closed. Never run migrations against the real file before the copy upgrade and preservation checks pass.

Alembic is the only schema author. Remove `_SCHEMA` and `_migrate` from runtime initialization only after the copy rehearsals pass; `db.init_db()` becomes a compatibility entry point that delegates to Alembic. Keep existing `sqlite3` CRUD functions during repository migration, all bound to the same configured `DATABASE_PATH`. New SQLAlchemy 2.x repository code receives its engine/session factory through dependency injection. Test both empty initialization and adoption/upgrade copies; compare existing row counts and constraints after upgrading.

### Jobs/config/logging

- Implement a replaceable job service in `app/jobs/` with `analysis_id`, `PENDING/RUNNING/COMPLETED/FAILED`, idempotency-key reuse, sanitized failure/result references, attempt tracking, and two total attempts for transient failures. The second attempt retains the ID. Keep the repository/session injected and persist in SQLite.
- Provide a single in-process worker interface with concurrency one. Wire its lifecycle only when Module 2 provides a handler; do not add Celery/Redis or launch a second scheduler.
- Centralize settings and structured logging under `shared/`. Include request/module/analysis/decision IDs when available, redact credentials, and add `LIVE_TRADING_ENABLED=false` as a separate hard gate in addition to `TRADING_MODE`.
- Do not add candidate, decision, order-intent, or position tables in Phase 1.

## Phase 1C — structural/regression validation

- Add independent import/startup tests and module-local test scaffolds. Use fake external adapters and temporary SQLite files.
- Test fresh Alembic initialization and existing-core adoption on a database copy. Verify old records, defaults, unique username constraint, and foreign-key/integrity checks remain sound.
- Rerun all existing tests from the project environment once declared dependencies are installed. Do not hide baseline failures or count baseline-only failures as regressions.
- Verify existing frontend API contracts remain mounted and no order/LLM side effect is possible in structural tests.
- Update implementation status with exact command output; scaffolded modules are `STRUCTURED`, not independently tested/implemented merely because imports pass.

## Release gates and ownership order

Phase 1 must meet the acceptance criteria in the approved plan before module implementation begins. Later implementation order is Stock Selection → AI Analysis → Decision Engine → Execution → Position Monitoring. Integrate one tested boundary at a time. Only Module 3 may emit approved order intent; Module 4 validates and idempotently submits; broker acceptance is not a fill; emergency stop/time exits remain deterministic and independent of AI. Keep live execution disabled through the paper lifecycle and all failure/recovery checks.

## Phase 1 implementation and verification record

**Status: COMPLETE (structure and shared infrastructure only).** The five module packages and their typed contracts/public protocols exist. Existing API routes remain mounted through `app/api/v1/router.py`; the React source was left unchanged. `app/application.py` is the composition root and `backend/main.py` remains a launcher.

- Alembic revisions `001_legacy_core` → `002_legacy_runtime` → `003_analysis_jobs` were tested against a fresh temporary SQLite database and a copy of the captured actual database. The actual-copy rehearsal created its own pre-migration backup, reached head, returned `integrity_check=ok` and zero foreign-key violations, and preserved the 2 users, 1 pending order, and 2 event rows. The working `backend/tradex.db` remains untouched at its original path/schema.
- Legacy CRUD still uses `sqlite3` during incremental migration; SQLAlchemy job persistence uses the same configured SQLite file. `db.init_db()` delegates schema changes to Alembic. No candidate/decision/intent/position tables were introduced.
- `analysis_jobs` supports per-user idempotency, status retrieval, PENDING/RUNNING/COMPLETED/FAILED, sanitized request/error fields, result references, transient-only retry (two total attempts), abandoned-job recovery, and an injected single-worker interface. The API returns an `analysis_id`; jobs remain pending until Module 2 supplies a handler.
- Shared settings include development/production validation and the fail-closed live gate. Structured logs retain the rotating log file and carry request/entity context with credential redaction. The existing automation runner and Dhan gateway remain the single runtime instances/paths.
- Verification: `python -m pytest tests -q` passed (36 tests); module-local commands passed individually (Stock Selection 1, AI Analysis 1, Decision Engine 2, Execution 1, Position Monitoring 1); `python -m pip check` passed; `python -m compileall -q app alembic tests` passed; `npm run build` passed. An HTTP smoke test served the Vite page and verified credentialed CORS, login, and session against a temporary paper-mode FastAPI database. No live broker order or paid LLM call was made.
- The baseline project environment lacked `bcrypt` and `itsdangerous`; those gaps are recorded in the baseline report and the dependency declarations are now explicit. TradingAgents was neither installed nor upgraded in this phase, and `backend/TradingAgents/**` was not edited.

All five modules remain `STRUCTURED`; their business behavior and module completion gates are pending. The current analysis route persists jobs without running provider analysis until Module 2 is implemented.
