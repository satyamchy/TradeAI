# TradeAI — Spec-Driven Development Pack

**Document status:** Draft v1.1  
**Updated:** 31 October 2026  
**Architecture decision:** One FastAPI application, five business modules, in-process Python function calls, one primary SQLite database initially, PostgreSQL-compatible persistence later.

This pack is the working specification for restructuring and developing TradeAI. It describes the intended architecture, interfaces, testing rules and phased delivery. It does **not** claim that proposed folders, functions or database tables already exist.

## 1. Agreed development approach

Development is deliberately split into three major stages:

1. **Structure first:** Audit the current repository, create the five module packages, shared infrastructure and module-specific test folders. Move or wrap existing code incrementally. Do not add new trading behavior during this stage.
2. **Build and test modules separately:** Implement each module behind a public service interface. Test its validation, business logic and persistence in isolation using SQLite test databases and fakes/mocks for external systems.
3. **Integrate one workflow at a time:** Connect Module 1 → Module 2, then Module 2 → Module 3, Module 3 → Module 4, and Module 4 → Module 5. Every connection gets integration tests before the next one is added.

Do not attempt a large rewrite or build all five modules in one pass.

## 2. Product direction

TradeAI is a modular trading application with five core modules:

1. **Stock Selection** — manual candidate input first; scanners later.
2. **AI Analysis** — provider-independent interface with TradingAgents as an external package and the existing TradeAI LangGraph capability as an optional provider. Add analysis profiles, configurable quick/deep models, portfolio context, report storage, and controlled use of TradingAgents memory/checkpoint capabilities.
3. **Decision Engine** — TradeAI-owned strategy, entry/exit validation, position sizing and risk controls. It must not depend on a particular AI provider.
4. **Execution** — paper execution first, then the existing Dhan integration behind a broker interface.
5. **Position Monitoring** — monitor confirmed positions, apply deterministic stop/target/time rules, and request reassessment when needed.

Future supporting capabilities include a backtesting/evaluation module, portfolio allocation, analytics/feedback, notifications, additional scanners and additional AI/broker providers.

## 3. Non-negotiable architecture decisions

- One FastAPI application; no separate analysis microservice.
- One Python runtime/process initially. Modules communicate through direct Python service/function calls with typed Pydantic DTOs.
- REST/WebSocket is for the React frontend and external clients only. No internal module-to-module HTTP.
- A workflow/orchestration layer coordinates multi-module processes and prevents circular dependencies.
- SQLite is the initial application database. Use SQLAlchemy 2.x and Alembic so PostgreSQL can be introduced later without rewriting business logic.
- Keep TradingAgents as an installed, pinned third-party package. Do not edit/fork its source, internal agents, prompts, graph or package files.
- Module 2 adapts TradingAgents into TradeAI's normalized `AnalysisResult` contract. Module 3 must not import TradingAgents or provider-specific types.
- TradingAgents' own memory and checkpoint SQLite files are separate sidecar stores; they are not the source of truth for TradeAI orders, fills or P&L.
- Paper mode is the default. Live trading is disabled by default.
- AI analysis is research only. Only a persisted, risk-approved `OrderIntent` from Module 3 may be submitted by Module 4.

## 4. Documents in this pack

| File | Purpose |
|---|---|
| `docs/00-product-spec.md` | Product goals, scope, workflows and success criteria |
| `docs/01-architecture-spec.md` | Single-app architecture, target folder structure and migration rules |
| `docs/02-module-specifications.md` | Requirements and acceptance criteria for all five modules and future modules |
| `docs/03-contracts-and-function-interfaces.md` | Typed contracts and public Python service interfaces |
| `docs/04-database-and-migrations.md` | SQLite schema, ownership, sidecar stores and PostgreSQL portability |
| `docs/05-api-and-runtime-spec.md` | Frontend APIs, module calls, background analysis and runtime lifecycle |
| `docs/06-dependencies-and-upgrade.md` | LangGraph/LangChain/TradingAgents compatibility and safe upgrade sequence |
| `docs/07-implementation-roadmap.md` | Structure-first, module-by-module and integration phases |
| `docs/08-testing-safety-and-acceptance.md` | Isolated module tests, integration tests, safety and acceptance gates |
| `docs/09-ai-coding-agent-rules.md` | Rules for Cursor/AI-assisted implementation |
| `docs/10-structure-first-and-module-testing.md` | Detailed structure-first playbook and how to test each module separately |
| `docs/implementation-status.md` | Initial phase/module status board; update during development |
| `docs/migration/baseline-report.md` | Captured pre-refactor environment, tests, route smoke, actual SQLite schema, and paper-ledger baseline |
| `docs/migration/restructuring-plan.md` | Phase 1 file ownership map, migration adoption sequence, and verification evidence |
| `docs/templates/module-spec-template.md` | Template for future module specifications |
| `docs/templates/module-readme-template.md` | Required README format for each module package |
| `docs/templates/file-ownership-map-template.md` | Inventory template for the structure-first file migration |
| `docs/templates/pytest.ini.example` | Suggested pytest markers/defaults for isolated module testing |

## 5. Existing TradeAI capabilities to preserve

The current backend README documents these capabilities. Confirm exact source paths and behavior against the local checkout before moving files:

- Existing LangGraph conversation workflow.
- Stock analysis endpoint and analysis snapshots.
- Technical indicators and market-data services.
- DhanHQ client/order service, paper/live branching and guardrails.
- Active-position watchdog and auto-square-off checks.
- Trading harness, live feed manager, scheduler and strategy coordinator.
- Existing entities such as `event_logs`, `active_positions`, `stock_analysis_snapshots`, `stock_trade_logs`, `trading_guardrail_settings`, `analysis_jobs` and `job_execution_logs`.

**Migration rule:** create the module structure first, then move or wrap existing code in small steps. Keep old routes/imports working through temporary compatibility wrappers until tests pass. Do not delete existing functionality during the structure-only phase.

## 6. Dependency baseline verified on 31 October 2026

| Package | Candidate baseline | Notes |
|---|---:|---|
| Python | `>=3.11` | TradingAgents v0.7.1 requires Python 3.11 or later. |
| TradingAgents | `v0.7.1` | Latest release shown in the project release page on 31 Oct 2026; pin the tag/release, not `main`. |
| LangGraph | `1.2.19` | Candidate latest PyPI release observed 30 Oct 2026; TradingAgents v0.7.1 requires `>=1.2.12`. |
| LangChain Core | `1.7.3` | Candidate latest PyPI release observed 29 Oct 2026; TradingAgents v0.7.1 requires `>=1.6.5`. |
| LangChain Groq | `1.1.3` | Candidate latest PyPI release observed 10 Jun 2026; verify its resolved compatibility with Core 1.x. |

These are candidate pins, not a claim that the complete existing TradeAI requirements already resolve. Upgrade in a clean environment, run `pip check`, run legacy regression tests, then lock the complete resolved dependency set. Do not use an unconstrained `latest` install in the application environment.

## 7. First milestone

**Structure-only milestone:** one FastAPI app starts; all five module packages import; module-specific test folders exist; SQLite initializes; current frontend/API behavior still works; tests establish a green structural baseline. TradingAgents is not yet connected to the live workflow in this milestone.

**First functional vertical slice after structure:** manual candidate → analysis profile → TradingAgents analysis → normalized result/report → SQLite persistence → frontend display. No order placement.

## 8. Source references

- TradeAI: https://github.com/satyamchy/TradeAI
- TradeAI backend README: https://github.com/satyamchy/TradeAI/blob/main/backend/README.md
- TradeAI requirements: https://github.com/satyamchy/TradeAI/blob/main/backend/requirements.txt
- TradingAgents README: https://github.com/TauricResearch/TradingAgents
- TradingAgents v0.7.1 release: https://github.com/TauricResearch/TradingAgents/releases/tag/v0.7.1
- TradingAgents v0.7.1 package metadata: https://github.com/TauricResearch/TradingAgents/blob/v0.7.1/pyproject.toml
- LangGraph PyPI: https://pypi.org/project/langgraph/
- LangChain Core PyPI: https://pypi.org/project/langchain-core/
