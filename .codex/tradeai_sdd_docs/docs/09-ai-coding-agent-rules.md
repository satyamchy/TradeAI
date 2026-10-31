# 09 — Instructions for AI Coding Agents (Cursor / Copilot / ChatGPT)

Use this file as the implementation contract when asking an AI coding agent to modify TradeAI.

## 1. Before making changes

1. Read `README.md` and all relevant specification documents.
2. Inspect the actual local repository tree; do not infer file paths from this specification.
3. Read the existing implementation and tests for the area being changed.
4. Identify the current behavior and preserve it unless a spec explicitly replaces it.
5. State which requirements and acceptance criteria the requested task addresses.

## 2. Required development order

Follow the roadmap exactly:

1. Audit and baseline.
2. Create module structure only.
3. Test structural imports/startup and ensure legacy behavior still works.
4. Implement one module at a time and test it in isolation.
5. Integrate one module boundary at a time with dedicated tests.
6. Run the full paper lifecycle only after all module and boundary tests pass.

Do not skip ahead because a folder or stub has been created. Ask for/confirm the active phase if the task request is ambiguous.

## 3. Scope discipline

- Implement only the requested phase/task.
- Do not build all five modules in one large rewrite.
- Do not rename/delete routes, tables or services without an explicit migration plan.
- Do not replace React + Vite with Next.js.
- Do not create microservices or internal HTTP calls between modules.
- Do not create a second Dhan client, scheduler, watchdog or trading loop.
- Do not modify/fork TradingAgents source code.
- Do not place broker calls inside Module 2 or Module 3.
- Do not expose a route that lets the frontend submit arbitrary live broker orders outside existing guardrails.

## 4. Required implementation style

- Python type hints for public functions.
- Pydantic v2 request/response DTOs for module boundaries.
- SQLAlchemy 2.x models/repositories and Alembic migrations.
- Async service functions for I/O; offload blocking SDK/LLM calls from the event loop.
- Dependency injection for DB sessions, providers and services.
- Structured errors and logs with correlation IDs.
- Decimal-safe handling for monetary/risk calculations.
- Tests for happy path and failure path.

## 5. Module dependency direction

Allowed dependency direction:

`API → Workflow → Module public service → Shared services/repositories`.

Modules may call another module's **public service interface** only when the workflow requires it. Prefer the workflow orchestrator for multi-module sequences. A module must not import another module's repository/private file. Keep Module 3 independent of all AI-provider packages.

## 6. Completion response for each coding task

Before considering a task complete, report:

- Files added/changed.
- Spec requirements implemented.
- Existing behavior preserved or intentionally changed.
- Tests run and their results.
- Migration steps, if any.
- Known limitations and next task.

Do not claim tests passed unless they were actually executed. If a test cannot run, state why.

## 7. Definition of done

A task is done only when:

- It meets the relevant spec.
- It includes or updates tests.
- It passes relevant tests and lint/type checks that are available.
- It does not bypass risk/execution boundaries.
- It has no hard-coded secrets or untracked local DB artifacts.
- Its config/documentation is updated.


## 8. Structure-phase guardrails

During the structure-only phase:

- Do not add TradingAgents calls, new trading strategies, new scanner algorithms or new order behavior.
- Do not upgrade major dependencies in the same pull request as moving modules.
- Create package folders, `__init__.py`, module README, DTOs and thin service facades.
- Use adapters/wrappers to preserve existing working implementations until they can be moved safely.
- Keep temporary compatibility imports where required and document their removal condition.
- Make no destructive database changes.
- Do not mark a module functionally complete based on an import-only test.

## 9. Testing rules

- Provide a module-specific test command in each module README.
- Unit tests must not require a network, paid LLM key or live broker. Use fakes/mocks.
- Repository tests use temporary SQLite databases.
- Real TradingAgents/Dhan tests must be marked `external` or `slow` and run only when explicitly requested.
- Run the module's isolated tests after every change, then the regression suite, then affected integration tests.
- Report exact commands and pass/fail counts. Do not claim a module is working if only its folder/import test passes.
