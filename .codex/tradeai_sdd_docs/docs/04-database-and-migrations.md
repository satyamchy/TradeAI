# 04 — Database and Migration Specification

## 1. Database decision

Use SQLite for the initial development/local deployment and SQLAlchemy 2.x for all application persistence. Use Alembic for schema migrations from the beginning.

Recommended local database location:

`backend/data/tradeai.db`

Example async SQLAlchemy URL (when the backend is started from `backend/`):

`sqlite+aiosqlite:///./data/tradeai.db`

The database path must be configurable through settings and the `data/` directory must be created at startup if absent. Add the database file, WAL files and local test databases to `.gitignore`.

## 2. Existing database safety check

The current TradeAI backend documentation describes PostgreSQL and SQLite support. Before switching the local application to SQLite, inspect the actual `.env`, deployment configuration and database contents. If any existing environment currently uses PostgreSQL, do not simply point it at a new SQLite file or assume the data has moved. Back up the existing database and perform a planned export/import or keep that environment on PostgreSQL until the migration is explicitly completed. The initial SQLite decision applies to the new local development baseline requested for this refactor.

## 3. Portability requirements for future PostgreSQL

Use SQLAlchemy ORM/Core constructs and Alembic migrations. Avoid direct use of SQLite-only SQL in business code.

- Use standard types where possible: integer, numeric/decimal, string, boolean, datetime, JSON via SQLAlchemy's portable JSON type.
- Store money and prices as `Numeric`/`Decimal` in persistence and calculations where practical; do not use binary floating-point for money/risk rounding.
- Use UTC timestamps in storage.
- Use explicit foreign keys and indexes.
- Use unique constraints for idempotency keys and natural identifiers where applicable.
- Keep transaction boundaries short.
- Avoid assumptions about SQLite's case sensitivity, locking or JSON implementation.
- Use application-generated UUIDs or a portable identifier strategy.
- Keep database-specific behavior inside the database setup/repository layer.

Future PostgreSQL URL:

`postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DBNAME`

Moving to PostgreSQL should require a configuration change, reviewed migrations and data migration/verification—not a rewrite of module services.

## 4. Existing entities to inspect and reuse

The current backend README documents these existing entities. Inspect actual SQLAlchemy model files and migrations before adding anything:

| Existing entity/table | Intended ownership |
|---|---|
| `event_logs` | Shared audit/operations logging |
| `active_positions` | Module 5 / execution reconciliation |
| `stock_analysis_snapshots` | Module 2 analysis history |
| `stock_trade_logs` | Module 4 actual order/trade history |
| `trading_guardrail_settings` | Module 3 policy configuration / Module 4 final guardrail |
| `analysis_jobs` | Module 2 job lifecycle; may need a schema extension |
| `job_execution_logs` | Background job execution history |

Do not create duplicate tables if the existing schema already supports the required fields. Prefer additive migrations.

## 5. Additional entities to consider

Add only after checking the current schema:

### `stock_candidates`

- `id` (UUID/string primary key)
- `batch_id`
- `symbol`, `exchange`, `analysis_ticker`, `security_id`
- `selection_mode`, `selection_reason`, `validation_status`
- `created_at`, `updated_at`

### `analysis_runs`

- `id`
- `candidate_id`
- `provider`, `provider_version`, `analysis_date`, `horizon`
- `profile_key`, `profile_version`, `selected_analysts_json`
- `quick_provider`, `quick_model`, `deep_provider`, `deep_model`
- `portfolio_snapshot_id` (nullable FK/reference)
- `checkpoint_enabled` (boolean)
- `status` (`QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`)
- `request_json` (validated/sanitized request)
- `result_json` (normalized result)
- `report_relative_path`, `report_checksum` (nullable artifact metadata)
- `upstream_run_id` / `upstream_thread_id` when supplied and safe to persist
- `error_code`, `error_message` (sanitized)
- `attempt_count`, `started_at`, `completed_at`, `created_at`

### `trade_decisions`

- `id`
- `analysis_id`
- `strategy_key`, `strategy_version`
- `status`, `reason_codes`, `explanation`
- `market_snapshot_at`, `risk_config_version`
- `decision_json` (normalized decision)
- `created_at`

### `order_intents`

- `id`, `decision_id`
- `symbol`, `security_id`, `side`, `quantity`, `order_type`
- `limit_price`, `stop_loss`, `target`, `max_risk_amount`
- `idempotency_key` (unique)
- `status`, `created_at`, `expires_at`

### `position_events` (optional if not represented by current logs)

- `id`, `position_id`, `event_type`, `event_time`, `payload_json`
- Used for fills, stop/target triggers, reassessment requests, partial exits and closure.

## 6. Relationship outline

```mermaid
erDiagram
    STOCK_CANDIDATES ||--o{ ANALYSIS_RUNS : analyzed_by
    ANALYSIS_RUNS ||--o{ TRADE_DECISIONS : evaluated_into
    TRADE_DECISIONS ||--o| ORDER_INTENTS : may_create
    ORDER_INTENTS ||--o{ STOCK_TRADE_LOGS : executed_as
    STOCK_TRADE_LOGS ||--o| ACTIVE_POSITIONS : may_open_or_update
    ACTIVE_POSITIONS ||--o{ POSITION_EVENTS : records
```

Adjust names/relationships after inspecting actual models. One analysis may produce multiple decisions for different strategies; one decision should create at most one active order intent for a given decision/action unless an explicit retry/replace workflow is implemented.

## 7. SQLite runtime settings

- Enable foreign-key enforcement on every connection (`PRAGMA foreign_keys=ON`).
- Use WAL mode for local concurrency where supported.
- Set a reasonable busy timeout.
- Keep write transactions short; do not hold a transaction open while calling an LLM or broker.
- Do not write large raw provider objects repeatedly; persist normalized reports and, when required, a sanitized raw payload/report artifact path.
- Start with one application worker/process. SQLite is not the target for horizontally scaled concurrent writers.
- Store TradingAgents' own checkpoint/memory databases separately from `tradeai.db`.

## 8. Migrations

1. Inspect current model definitions and existing database files.
2. Establish an Alembic baseline without dropping user data.
3. Add tables/columns incrementally.
4. Test migrations against a new empty SQLite database and a copy of the existing development database.
5. Add rollback guidance for each migration; do not promise lossless rollback for destructive data transformations without a backup.
6. Before PostgreSQL migration, create a data export/import plan, run migrations on a staging database and compare row counts, identifiers, money fields, timestamps and foreign keys.

## 9. Acceptance criteria

- Fresh SQLite database initializes through migrations.
- Existing development data remains intact after additive migrations.
- All modules use SQLAlchemy repositories; no module hardcodes SQLite file operations.
- Foreign keys, idempotency and required indexes are enforced.
- A database URL can be switched to PostgreSQL in test configuration without changing service contracts.


## 10. TradingAgents sidecar persistence

The application uses one primary SQLite database at `backend/data/tradeai.db`. TradingAgents may create its own persistent decision-memory log and per-ticker LangGraph checkpoint SQLite files. Keep these in a separate directory, for example:

```text
backend/data/
├── tradeai.db
└── tradingagents/
    ├── memory/
    │   └── trading_memory.md
    ├── cache/
    │   └── checkpoints/
    └── reports/
```

Configure documented upstream path settings (including `TRADINGAGENTS_MEMORY_LOG_PATH` and `TRADINGAGENTS_CACHE_DIR`) rather than changing TradingAgents internals. Keep test, development and paper/live environments isolated. These sidecar stores are not the authoritative record of broker orders, actual fills, open positions or realized P&L; those remain in TradeAI's main database.

Do not point concurrent test runs at the same TradingAgents memory/checkpoint files. Use a temporary directory per test run.

## 11. Module-specific database testing

- Repository tests use a fresh temporary SQLite database per test or test class.
- Use the same SQLAlchemy models and Alembic migrations as the application; do not create an unrelated simplified test schema.
- Include tests for insert/read/update, uniqueness/idempotency, foreign keys and restart persistence.
- Keep LLM/broker calls outside database transactions.
- Add a test for SQLite lock/busy behavior and verify that the configured timeout/error policy is understandable.
