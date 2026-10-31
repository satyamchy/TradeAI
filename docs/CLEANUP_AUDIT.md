# TradeX code cleanup audit

**Audit date:** 2026-11-01  
**Scope:** Root documentation, backend application/runtime, tests and migrations, frontend source/build configuration, and the SDD documentation index.  
**Safety:** The audit did not read secret values or runtime data. The existing database, paper ledgers, log files, environment files, backups, and the untracked `backend/TradingAgents/` checkout are protected. Existing working-tree changes from Phase 3 are retained.

## 1. Safe to delete

No complete file was proven safe to delete. The files that looked like legacy or duplicate implementations are still imported by mounted routes, the scheduler, Alembic, tests, or documentation. Deleting those files would remove live behavior or regression coverage.

The following redundant code fragments are safe to remove after this report is recorded:

| File | Redundancy | Evidence |
|---|---|---|
| `backend/app/modules/execution/__init__.py` | Repeated module docstring and duplicate imports/`__all__` block | The second export block exactly repeats the first. |
| `backend/app/modules/decision_engine/__init__.py` | Repeated module docstring | The second docstring already describes the package. |
| `backend/app/modules/position_monitoring/__init__.py` | Repeated module docstring | The second docstring already describes the package. |

Unused-import candidates were checked against each module's AST and references. The verified import-only names are listed under the cleanup record below.

## 2. Requires consolidation

These are legacy boundaries with active runtime dependants. Keep them until each owning workflow has a replacement route and the frontend has moved to it.

| Files / paths | Current role and evidence | Cleanup decision |
|---|---|---|
| `backend/app/api/{automation,auth,account,events,manual_orders,screener,suggestions,users}.py` | Mounted by `backend/app/api/v1/router.py`. `frontend/src/api/stockApi.js` calls their route families; API regression tests exercise authentication, pending orders, automation, account and events. | Preserve as compatibility adapters. Migrate and retire route-by-route only after frontend and API contract tests move. |
| `backend/app/trading/{automation_runner,intraday_cycle,nifty50,nse_session,pending,risk_limits,screener,suggestions}.py` | Imported by active APIs, the single scheduler, the module-1 screener adapter, broker code, or regression tests. | Consolidate behind module/workflow services incrementally; do not delete now. |
| `backend/app/broker/{dhan_gateway,dhan_token,paper_ledger,trading_gateway}.py` | Active single Dhan/paper execution path, token-renewal tests, and account/order APIs. Module 4 wraps this gateway. | Preserve one broker client and ledger; do not create a parallel execution path. |
| `backend/app/workflows/intraday.py` | Compatibility function imported by both `api/automation.py` and `trading/automation_runner.py`. | Keep until both callers are migrated. |
| `backend/app/{config.py,db.py,auth.py,utils/logger.py}` | Compatibility interfaces imported by active legacy runtime code. `db.init_db()` invokes the Alembic migration authority and its SQLite functions still serve legacy CRUD. | Keep during repository/config/logging transition. No second schema authority was found. |
| `backend/app/modules/{decision_engine,execution,position_monitoring}/` and `backend/app/workflows/{decision,execution,monitoring,exits}.py` | Used by module tests and `backend/tests/integration/test_workflow_boundaries.py`; the workflows are not yet public replacements for the legacy order routes. | Preserve; do not mistake tested service boundaries for a migrated live API. |

## 3. Must be preserved

| Files / paths | Reason |
|---|---|
| `backend/tradex.db`, `backend/data/**`, `backend/paper_ledgers/**`, `backend/logs/**`, root `logs/**`, and all `.env` files | User data, migration backups, paper state, logs, and secrets/runtime configuration. No contents were inspected or changed. |
| `backend/TradingAgents/**` | External dependency checkout; untracked before this cleanup and explicitly out of scope. No source file was read or modified for cleanup. |
| `backend/alembic/**`, `backend/alembic.ini`, `backend/app/shared/migrations.py` | The single Alembic schema-change path and all existing revisions. |
| `backend/requirements.txt`, `backend/requirements-tradingagents.txt`, Python and frontend lock/config files, `.env.example` files | Active runtime/build configuration. No dependency upgrade or speculative configuration change is part of cleanup. |
| `backend/tests/**`, `backend/app/modules/*/tests/**`, `frontend/src/**` | Regression, structural, module-boundary coverage, and the current user-facing application. |
| `README.md`, `REPO.md`, `docs/PROJECT_SETUP.md`, backend/frontend READMEs, baseline and restructuring evidence | Setup, operational, safety, and architecture guidance. Correct stale statements, but keep the docs. |

## 4. Requires further investigation

| Files / paths | Open question | Decision for this cleanup |
|---|---|---|
| `.codex/tradeai_sdd_docs/implementation-status.md` and `.codex/tradeai_sdd_docs/docs/implementation-status.md` | Two status boards exist: the root README links to the current board while the SDD index still names the planning/template board. Neither is a runtime dependency, but the SDD tree is read-only in this workspace. | Preserve both; do not remove or edit the read-only SDD copy. Reconcile the canonical status link in a docs-authorized change. |
| `frontend/package.json` and `frontend/package-lock.json` | The manifest uses `latest` ranges while the lockfile captures concrete versions. The production build uses the lockfile; changing dependency policy needs a separate compatibility review. | Preserve both and do not upgrade packages during code cleanup. |
| `backend/AI_Stock_Trading_Roadmap.md`, `backend/REFACTORING_NOTES.md`, and `docs/PROJECT_SETUP.md` | These include product history and current Dhan/ledger operating guidance alongside architecture notes. No authoritative reference proves their content is fully superseded. | Retain and update only claims contradicted by the current implementation. |

## API and runtime findings

- Every current frontend API call remains mounted through the compatibility router. Removing those routes would break frontend behavior.
- Regression tests directly depend on `/api/v1/auth`, `/api/v1/orders`, `/api/v1/account`, `/api/v1/automation`, and `/api/v1/events` behavior.
- Module 2 analysis jobs and Module 1 stock-selection endpoints are composed into FastAPI. Modules 3–5 and their workflows have fake-backed module/integration coverage, but do not yet replace the legacy public execution APIs.
- `backend/app/application.py` owns the single FastAPI app and one analysis worker; `backend/app/harness/` returns the existing automation runner. No duplicate scheduler, Dhan gateway, SQLite CRUD store, or schema authority was identified.
- Alembic revisions and module model imports are live schema dependencies. No migration or table file is safe to remove.
- The AST import audit found redundant imports in production and test files. Only names with no code use or public re-export were selected; type-checking-only imports and package exports are retained.

## Cleanup record

No complete files were deleted. The audit found active callers or required data/schema/test ownership for every file candidate.

| Modified file | Reason |
|---|---|
| `docs/CLEANUP_AUDIT.md` | Added this evidence-based cleanup report and recorded the final changes and verification results. |
| `README.md` | Removed the stale claim that the analysis worker was not connected; it now reflects the current in-process worker and lazy provider. |
| `backend/REFACTORING_NOTES.md` | Clarified that compatibility routes remain active, described current module/workflow status, and documented that Module 4 wraps the existing gateway. |
| `backend/app/modules/execution/__init__.py` | Removed a repeated docstring and duplicate imports/exports. |
| `backend/app/modules/decision_engine/__init__.py` | Removed the repeated package docstring. |
| `backend/app/modules/position_monitoring/__init__.py` | Removed the repeated package docstring. |
| `backend/app/modules/ai_analysis/providers.py` | Removed unused `json` and `UUID` imports. |
| `backend/app/modules/execution/schemas.py` | Removed unused `model_validator` import. |
| `backend/app/modules/execution/service.py` | Removed unused `hashlib` and `Decimal` imports. Other pre-existing Phase 3 changes in this file are retained. |
| `backend/app/modules/position_monitoring/service.py` | Removed unused `UUID` import. |
| `backend/app/modules/stock_selection/instrument_master.py` | Removed unused `defaultdict` import. |
| `backend/app/modules/stock_selection/service.py` | Removed unused `Instrument` import. |
| `backend/app/modules/ai_analysis/tests/conftest.py` | Removed unused `AnalysisHorizon` and `ProviderName` imports. |
| `backend/app/modules/ai_analysis/tests/test_provider.py` | Removed unused `PortfolioPosition` import. |
| `backend/app/modules/ai_analysis/tests/test_service.py` | Removed unused `AnalysisJobManager` and `SqlAlchemyAnalysisRunRepository` imports. |
| `backend/app/modules/decision_engine/tests/test_service.py` | Removed unused `AccountRiskSnapshot` import. |
| `backend/app/modules/execution/tests/test_gateway_adapter.py` | Removed an unused local `execution_request` import. |
| `backend/app/modules/execution/tests/test_service.py` | Removed unused `ExecutionService` import. |
| `backend/tests/test_pending.py` | Removed unused `pytest` import. |

The AST-based unused-import scan was rerun after cleanup. Its only remaining finding is `AutomationRunner` in `backend/app/harness/__init__.py`, intentionally imported under `TYPE_CHECKING` for a quoted return annotation and therefore retained.

**Validation results:**

- `python -m compileall -q app tests alembic` — passed.
- `npm run build` in `frontend/` — passed; Vite transformed 84 modules.
- `python -m pytest tests/structure/test_module_imports.py -q` — 3 passed.
- `python -m pytest tests/structure/test_live_safety_gate.py -q` — 1 passed.
- `python -m pytest tests/structure/test_logging.py -q` — 1 passed.
- `python -m pytest tests -q` — blocked during collection in three migration-dependent test modules because the available system Python has no installed Alembic package. The backend's `alembic/` directory is then imported as a namespace package, which does not provide `alembic.command`.
- The module-local suites and the full structure/integration command are likewise blocked at collection by the missing Alembic dependency. In the subset run that did collect, 9 tests passed and one Dhan token renewal test failed only when `db.init_db()` attempted to import Alembic.
- `python -m pip check` — failed in the only available global Python 3.11 environment. Reported conflicts: LangChain 0.3 packages require `langchain-core<0.4` and `langsmith<0.2`, while the environment has core 1.6.3 and langsmith 0.12.5; `langchain-classic` requires text-splitters 1.1.2+ while 0.3.8 is installed; `langgraph-checkpoint-sqlite` requires checkpoint `<3` while 4.2.0 is installed; and `ml-dtypes`/TensorFlow constraints disagree with installed NumPy 1.26.4, ml-dtypes 0.6.0 and protobuf 6.33.6. These are conflicts in the global environment, not cleanup changes. There is no project virtual environment in this checkout, and no packages were installed or upgraded as part of a code-only cleanup.
- `git diff --check` — passed (Git emitted line-ending notices for existing CRLF/LF files).
- The AST unused-import audit has no remaining actionable findings; the only remaining finding is the intentional `TYPE_CHECKING` import documented above.

The frontend build and tests that do not need Alembic used fakes or local code paths. No live Dhan request, order, paid LLM call, database migration, or TradingAgents source change was performed. The original SQLite database, ledger files, logs, credentials, and backups were preserved.

## Pre-existing working-tree changes retained

These changes were present before this cleanup and were not reverted. Where a file also appears in the modified-file table, only the explicitly described cleanup edit is attributable to this task.

| Files | Reason retained |
|---|---|
| `.codex/tradeai_sdd_docs/implementation-status.md` | Existing Phase 3 status and evidence; read-only under the workspace permissions. |
| `backend/README.md`, `backend/app/api/v1/analysis_jobs.py`, `backend/app/application.py`, `backend/app/jobs/schemas.py`, `backend/app/modules/ai_analysis/README.md`, `backend/app/modules/ai_analysis/tests/test_service.py`, `backend/app/modules/execution/service.py`, `backend/app/workflows/__init__.py`, `backend/tests/integration/README.md`, `backend/tests/structure/test_application_startup.py` | Existing Phase 3 docs, app composition, job API, workflow and regression-test work. This cleanup preserved it. |
| `backend/app/workflows/README.md`, `backend/app/workflows/{analysis,decision,execution,exits,monitoring,schemas}.py`, `backend/tests/integration/test_workflow_boundaries.py` | Existing untracked Phase 3 workflow implementation and integration coverage. These are part of the current architecture and were retained. |
| `backend/TradingAgents/**` | Existing untracked external checkout, explicitly outside cleanup scope; untouched. |
