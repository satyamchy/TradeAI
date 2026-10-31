# AI Analysis (Module 2)

Owns provider selection, TradingAgents/legacy LangGraph adapters, execution of analysis, and normalization into the shared `AnalysisResult` contract. It is research only and never calls Module 4 or broker order methods.

TradingAgents remains an external dependency. Its source is not changed. Phase 1 adds contracts and job infrastructure only; provider pinning and compatibility work happen during Module 2 implementation.
