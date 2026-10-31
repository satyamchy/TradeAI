# Trade Execution (Module 4)

Owns the broker adapter, paper/Dhan order submission, cancellation, status reconciliation, and fill lifecycle. It accepts only a Module 3 `ApprovedOrderIntent`, validates it again, and does not treat broker acceptance as a confirmed fill.

`ExecutionService` accepts an intent ID and execution mode, loads only a still-approved intent through an injected public lookup, validates its expiry and mandatory fields, and reserves the idempotency key in SQLite before calling a broker adapter. The reservation is retained as `UNKNOWN` if a submission outcome is uncertain; repeating the request returns the existing order and does not blindly submit again. Reconciliation updates fill quantity, remaining quantity, status, rejection reason and append-only event history.

`ExistingTradingGatewayAdapter` wraps an injected instance of the application's existing `TradingGateway`. It does not construct a Dhan client or paper ledger. The existing gateway remains the single broker path and enforces its own live safety checks. Current adapter supports NSE equity market orders only; unsupported exchange or order types fail closed. Live execution is additionally blocked unless the shared application settings explicitly allow it.

Tests use temporary SQLite and fake broker/intent services. They cover approved persisted intents, idempotency, unknown outcomes, partial fills, rejection, reconciliation and adapter payload mapping without network, Dhan credentials or live orders.
