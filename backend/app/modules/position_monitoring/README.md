# Position Monitoring (Module 5)

Owns deterministic evaluation of supplied broker- or paper-confirmed open quantities against configured stop, target, session square-off and market-data freshness rules. Stop and target comparisons trigger at their exact price boundary. Session square-off remains a trigger even when a quote is unavailable, so time exits do not depend on AI analysis.

`PositionMonitoringService` returns `HOLD`, `EXIT_CANDIDATE` or `DATA_UNAVAILABLE`; it never creates an order or calls Module 3/4. It reports the confirmed quantity to close, and persists a unique trigger per position, reason and rules version so the same unchanged trigger is surfaced once. Scheduling and market/position snapshot acquisition remain outside this module.

Tests use synthetic snapshots, a fixed clock and temporary SQLite. No Dhan, AI, scheduler or network client is initialized.
