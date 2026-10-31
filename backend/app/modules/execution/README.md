# Trade Execution (Module 4)

Owns the broker adapter, paper/Dhan order submission, cancellation, status reconciliation, and fill lifecycle. It accepts only a Module 3 `ApprovedOrderIntent`, validates it again, and does not treat broker acceptance as a confirmed fill.

The existing `TradingGateway` and Dhan SDK client remain the single execution path. Phase 1 adds contracts only; no live execution is enabled.
