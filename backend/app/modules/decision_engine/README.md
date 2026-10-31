# Decision & Risk Engine (Module 3)

Owns provider-neutral strategies, position sizing, risk checks, and approved order-intent generation. Only this module may create an `ApprovedOrderIntent`. It must not import TradingAgents, LangChain/LangGraph providers, or broker order services.

`DecisionEngineService` consumes injected public analysis/candidate lookup interfaces, market and account snapshots, a versioned `StrategyPolicy`, and a repository. Entry evaluation is long-only, deterministic and fails closed for stale/missing data, unresolved security IDs, kill-switch/loss/exposure limits, duplicate positions, pending orders, and market closure. It sizes with `Decimal` using risk-per-share, available funds, order-value, symbol-exposure and portfolio-exposure caps.

Only this module creates `ApprovedOrderIntent` values. The service persists each result and approved intent with a stable decision fingerprint and idempotency key. Exit evaluation is deterministic and does not read or invoke AI; it checks the requested quantity against the injected account snapshot's confirmed open quantity. It returns a sell intent candidate for Module 4 and never submits an order.

The module has no TradingAgents, LangChain/LangGraph or broker SDK imports. External services and time are injected. Its isolated tests use a temporary SQLite database and fake public interfaces. Strategy numbers are explicit input configuration, not recommendations; production integration must supply reviewed values.
