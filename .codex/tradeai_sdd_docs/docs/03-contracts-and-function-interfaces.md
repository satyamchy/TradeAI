# 03 — Contracts and Function Interfaces

## 1. Contract policy

Pydantic v2 models are the public contracts between modules. Do not pass untyped dictionaries, ORM models, SQLAlchemy sessions, LangGraph state objects or Dhan SDK response objects across module boundaries.

The examples below define the intended shape. Exact field types/enums should be implemented and validated in code; fields may be extended with backward-compatible optional values.

## 2. Shared identifiers and enums

```text
CandidateId       = UUID
AnalysisId        = UUID
DecisionId        = UUID
OrderIntentId     = UUID
TradeAIOrderId    = UUID
PositionId        = UUID

SelectionMode     = MANUAL | TOP_GAINERS | TOP_LOSERS | MOMENTUM | HIGH_VOLUME
AnalysisHorizon   = INTRADAY | SWING | RESEARCH
ProviderName      = TRADING_AGENTS | LEGACY_LANGGRAPH | FUTURE_PROVIDER
Direction         = BULLISH | NEUTRAL | BEARISH | REVIEW
DecisionStatus    = BUY_APPROVED | HOLD | REJECTED | SELL_APPROVED | REVIEW_REQUIRED
ExecutionMode     = PAPER | LIVE
OrderSide         = BUY | SELL
OrderType         = MARKET | LIMIT
OrderStatus       = CREATED | SUBMITTED | PENDING | OPEN | PARTIALLY_FILLED | FILLED | REJECTED | CANCELLED | UNKNOWN
PositionStatus    = OPEN | PARTIALLY_CLOSED | CLOSED | DATA_UNAVAILABLE
```

Use timezone-aware UTC timestamps for persisted events. Convert to `Asia/Kolkata` only for exchange-session calculations and user display.

## 3. Instrument contract

```json
{
  "symbol": "RELIANCE",
  "exchange": "NSE",
  "trading_symbol": "RELIANCE",
  "analysis_ticker": "RELIANCE.NS",
  "security_id": "2885",
  "segment": "NSE_EQ",
  "currency": "INR"
}
```

The sample `security_id` is illustrative; the application must resolve it from the current Dhan instrument master and verify the mapping. `analysis_ticker` is the provider-specific symbol; `security_id` is a broker identifier. Never derive one by string manipulation from the other.

## 4. Module 1 contracts

### `CreateCandidatesRequest`

```json
{
  "selection_mode": "MANUAL",
  "exchange": "NSE",
  "symbols": ["RELIANCE", "TCS", "INFY"],
  "horizon": "INTRADAY"
}
```

### `CandidateBatch`

```json
{
  "batch_id": "uuid",
  "status": "COMPLETED",
  "candidates": [
    {
      "candidate_id": "uuid",
      "instrument": {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "analysis_ticker": "RELIANCE.NS",
        "security_id": "resolved-by-instrument-service"
      },
      "selection_mode": "MANUAL",
      "selection_reason": "USER_SELECTED",
      "validation_status": "VALID"
    }
  ],
  "rejected_symbols": [],
  "created_at": "2026-10-31T09:00:00Z"
}
```

Public service: `stock_selection_service.create_candidates(request) -> CandidateBatch`.

## 5. Module 2 contracts

### `AnalysisRequest`

```json
{
  "candidate_id": "uuid",
  "provider": "TRADING_AGENTS",
  "analysis_date": "2026-10-31",
  "horizon": "INTRADAY",
  "analysis_profile_key": "INTRADAY_RESEARCH",
  "analysis_profile_version": "1",
  "selected_analysts": ["market", "news", "social"],
  "model_config": {
    "quick_provider": "groq",
    "quick_model": "configured-quick-model",
    "deep_provider": "openai",
    "deep_model": "configured-deep-model"
  },
  "include_portfolio_context": true,
  "checkpoint_enabled": false,
  "save_html_report": true
}
```

`selected_analysts` must be checked against the installed TradingAgents release's supported names. The example is illustrative, not a guarantee that every value is accepted by every release.

### `AnalysisJobReceipt`

```json
{
  "analysis_id": "uuid",
  "candidate_id": "uuid",
  "status": "QUEUED",
  "provider": "TRADING_AGENTS",
  "created_at": "2026-10-31T09:00:00Z"
}
```

### `AnalysisResult`

```json
{
  "analysis_id": "uuid",
  "candidate_id": "uuid",
  "symbol": "RELIANCE",
  "analysis_ticker": "RELIANCE.NS",
  "provider": "TRADING_AGENTS",
  "provider_version": "0.7.1",
  "profile_key": "INTRADAY_RESEARCH",
  "profile_version": "1",
  "quick_model": "configured-quick-model",
  "deep_model": "configured-deep-model",
  "portfolio_snapshot_id": "uuid-or-null",
  "status": "COMPLETED",
  "source_rating": "Overweight",
  "direction": "BULLISH",
  "reports": {
    "market": "...",
    "technical": "...",
    "fundamentals": "...",
    "news": "...",
    "sentiment": "...",
    "bull_bear_research": "...",
    "trader_plan": "...",
    "risk_assessment": "..."
  },
  "warnings": ["PORTFOLIO_CONTEXT_NOT_INCLUDED"],
  "started_at": "2026-10-31T09:00:00Z",
  "completed_at": "2026-10-31T09:03:00Z",
  "report_artifacts": {
    "html_report_path": "reports/ANL-uuid/complete_report.html",
    "report_checksum": "sha256:..."
  }
}
```

The result mapper must preserve `source_rating`. Normalized `direction` is a broad classification only. Module 3 must not infer exact entry price/quantity from this object.

Provider interface:

```python
class AnalysisProvider(Protocol):
    async def analyze(self, request: AnalysisProviderRequest) -> AnalysisResult:
        ...
```

A synchronous third-party provider such as `TradingAgentsGraph.propagate()` must be run off the event loop. The provider adapter owns the mapping from the normalized request to upstream arguments and from upstream state/decision to `AnalysisResult`.

## 6. Module 3 contracts

### `EvaluateTradeRequest`

```json
{
  "analysis_id": "uuid",
  "strategy_key": "intraday_momentum_v1",
  "requested_action": "ENTRY"
}
```

The request intentionally does not accept `current_price`, `available_capital`, `quantity` or `stop_loss` from the frontend. The engine obtains authoritative snapshots and computes these values itself.

### `DecisionResult`

```json
{
  "decision_id": "uuid",
  "analysis_id": "uuid",
  "symbol": "RELIANCE",
  "status": "BUY_APPROVED",
  "strategy_key": "intraday_momentum_v1",
  "strategy_version": "1",
  "reason_codes": ["SIGNAL_VALID", "PRICE_FRESH", "RISK_WITHIN_LIMITS"],
  "explanation": "All configured strategy and risk conditions passed.",
  "market_snapshot_at": "2026-10-31T09:03:00Z",
  "order_intent": {
    "order_intent_id": "uuid",
    "symbol": "RELIANCE",
    "security_id": "resolved-security-id",
    "side": "BUY",
    "quantity": 10,
    "order_type": "LIMIT",
    "limit_price": 1400.0,
    "stop_loss": 1370.0,
    "target": 1460.0,
    "max_risk_amount": 300.0,
    "idempotency_key": "decision-uuid"
  }
}
```

For non-approved statuses, `order_intent` must be `null`.

Public service: `decision_engine.evaluate_entry(request) -> DecisionResult` and `evaluate_exit(request) -> DecisionResult`.

## 7. Module 4 contracts

### `ExecutionRequest`

The frontend does not construct this request. The orchestrator passes the persisted `OrderIntent` ID returned by Module 3.

```json
{
  "order_intent_id": "uuid",
  "execution_mode": "PAPER"
}
```

### `ExecutionResult`

```json
{
  "tradeai_order_id": "uuid",
  "order_intent_id": "uuid",
  "broker": "PAPER",
  "broker_order_id": "PAPER-12345",
  "status": "FILLED",
  "requested_quantity": 10,
  "filled_quantity": 10,
  "remaining_quantity": 0,
  "average_fill_price": 1399.5,
  "submitted_at": "2026-10-31T09:04:00Z",
  "updated_at": "2026-10-31T09:04:01Z"
}
```

## 8. Module 5 contracts

### `PositionEvaluation`

```json
{
  "position_id": "uuid",
  "symbol": "RELIANCE",
  "status": "OPEN",
  "action": "REASSESS",
  "current_price": 1440.0,
  "unrealized_pnl": 405.0,
  "trigger_reason": "TARGET_APPROACHING",
  "market_data_at": "2026-10-31T09:10:00Z"
}
```

Possible actions: `HOLD`, `REASSESS`, `EXIT_CANDIDATE`, `DATA_UNAVAILABLE`.

The monitor produces a request/decision candidate. It does not return an executable broker order.

## 9. Error contract

Use a common application error format:

```json
{
  "error": {
    "code": "STALE_MARKET_DATA",
    "message": "A fresh market snapshot is not available.",
    "retryable": true,
    "correlation_id": "uuid"
  }
}
```

Do not expose API keys, access tokens, stack traces, provider secrets, raw account credentials or sensitive broker payloads in errors.

## 10. Contract versioning

- Add `schema_version` to persisted/exported objects where future changes may be breaking.
- Prefer additive optional fields.
- If an incompatible contract change is required, create a new schema version and migration plan.
- Persist provider name/version and strategy name/version with every result/decision.


## 11. Analysis profile and portfolio-context interfaces

```python
class AnalysisProfile(BaseModel):
    key: str
    version: str
    horizon: AnalysisHorizon
    selected_analysts: list[str]
    quick_provider: str
    quick_model: str
    deep_provider: str
    deep_model: str
    max_debate_rounds: int
    max_risk_discuss_rounds: int
    checkpoint_enabled: bool = False
    save_html_report: bool = True

class PortfolioSnapshotReference(BaseModel):
    snapshot_id: UUID
    captured_at: datetime
    currency: str
    cash: Decimal
    positions: list[PortfolioPosition]
```

The profile is resolved and validated by Module 2. Never accept arbitrary upstream configuration dictionaries from the frontend. The portfolio snapshot is created by TradeAI from broker-confirmed/account data; Module 2 maps it to the upstream `PortfolioContext` type. An explicit empty positions list means the snapshot is flat. If no valid snapshot exists, do not fabricate one.

## 12. Module isolation and test contracts

Each module's public service methods must be callable with typed DTOs and injected dependencies. Unit tests should use an in-memory or temporary SQLite database and fake market/broker/AI adapters. A module's unit tests must not invoke another module's private implementation. Cross-module orchestration is tested separately under `tests/integration/workflows/`.


### TradingAgents adapter mapping (v0.7.1)

The adapter is responsible for mapping the TradeAI profile into the upstream call. The following is the intended shape; imports/config keys must be verified against the pinned release during implementation:

```python
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.portfolio import PortfolioContext

upstream_config = DEFAULT_CONFIG.copy()
upstream_config.update({
    "quick_think_llm": profile.quick_model,
    "deep_think_llm": profile.deep_model,
    "quick_think_provider": profile.quick_provider,
    "deep_think_provider": profile.deep_provider,
    "max_debate_rounds": profile.max_debate_rounds,
    "max_risk_discuss_rounds": profile.max_risk_discuss_rounds,
    "checkpoint_enabled": profile.checkpoint_enabled,
})

graph = TradingAgentsGraph(
    selected_analysts=profile.selected_analysts,
    debug=False,
    config=upstream_config,
)
state, upstream_rating = graph.propagate(
    analysis_ticker, analysis_date, asset_type="stock", portfolio=portfolio_context
)
report_dir = graph.save_reports(state, analysis_ticker, save_path=report_path, html=True)
```

`portfolio_context` is either a validated upstream `PortfolioContext` built from an authoritative TradeAI account snapshot or `None`. `selected_analysts` is passed to the graph constructor in v0.7.1. The adapter must never mutate imported `DEFAULT_CONFIG` itself; always pass a per-run copy.
