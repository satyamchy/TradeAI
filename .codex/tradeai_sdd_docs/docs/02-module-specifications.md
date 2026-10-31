# 02 — Module Specifications

## Common rules for all modules

- Expose public service methods from `service.py`.
- Accept and return Pydantic v2 DTOs defined in the module's `schemas.py` or shared contracts.
- Receive the SQLAlchemy `AsyncSession` or repository dependency explicitly; do not create hidden global sessions.
- Raise typed application exceptions; API routes translate them to HTTP errors.
- Persist state changes through repositories owned by the module.
- Do not import private implementation files from another module.
- Do not call the broker except inside Module 4.
- Every module must have isolated unit tests; module-level tests must not require another module, a real LLM call or a live broker.

---

## Module 1 — Stock Selection

### Responsibility

Create a clean, validated list of instruments that should be analyzed. Initially, candidates are entered manually. Automated scanner providers are future additions.

### First-release capabilities

- Accept one or more user-entered symbols.
- Normalize case and whitespace.
- Resolve company/ticker input to a canonical TradeAI instrument.
- Map the TradeAI instrument to the Yahoo Finance ticker needed by TradingAgents (for example, `RELIANCE.NS`) and Dhan's `security_id` needed for broker operations.
- Reject unknown/ambiguous symbols and duplicates.
- Store the batch and each candidate with its source (`MANUAL`).
- Return a candidate ID for downstream analysis.

### Future providers

- `ManualSelectionProvider` — first implementation.
- `TopGainersScanner` — future.
- `TopLosersScanner` — future.
- `MomentumScanner` — future.
- `HighVolumeScanner` — future.

All providers return the same `CandidateBatch` contract.

### Public service interface

- `create_candidates(request) -> CandidateBatch`
- `get_candidate(candidate_id) -> StockCandidate`
- `list_candidates(filters) -> list[StockCandidate]`

### Inputs

- Selection mode (`MANUAL` initially).
- User symbols.
- Exchange/market (NSE initially).
- Optional analysis horizon/timeframe.

### Outputs

- Candidate ID.
- Canonical symbol, exchange and market.
- Analysis ticker (for example Yahoo `.NS` ticker).
- Dhan `security_id` when resolved.
- Selection source and reason.
- Validation status.

### Rules

- Do not assume a Yahoo ticker equals a Dhan symbol or security ID.
- A candidate without a resolved Dhan security ID may be analyzed, but it cannot become an executable order until Module 4 can resolve it.
- Manual input is not a buy recommendation.
- Do not automatically select or execute a trade in this module.

### Acceptance criteria

- Valid manual symbols create candidate rows.
- Invalid and duplicate symbols are reported explicitly.
- Symbol mapping is reproducible and stored with a timestamp/source.
- Module 1 returns the same contract whether a candidate came from a manual list or a future scanner.

---

## Module 2 — AI Analysis

### Responsibility

Produce research for a candidate using a selected analysis provider and return a provider-independent `AnalysisResult`.

### Providers

1. `TradingAgentsProvider` — primary multi-agent research provider. Use the documented `TradingAgentsGraph` and `.propagate()` Python API from a pinned release. Do not edit the package's source.
2. `LegacyLangGraphProvider` — optional adapter around the existing TradeAI stock-analysis graph only if it can provide the same `AnalysisResult` contract. Keep conversational Q&A separate if it does not.
3. Future providers can be registered without changing Module 3.

### Public service interface

- `request_analysis(request) -> AnalysisJobReceipt`
- `run_analysis_job(job_id) -> AnalysisResult` (worker/internal method)
- `get_analysis(analysis_id) -> AnalysisResult | None`
- `list_analyses(filters) -> list[AnalysisSummary]`

### Analysis profiles and TradingAgents capabilities

Module 2 owns an `AnalysisProfile` registry. A profile is a TradeAI configuration object, not a modification to TradingAgents. The initial profile set may include `INTRADAY_RESEARCH`, `SWING_RESEARCH` and `GENERAL_RESEARCH`; do not assume these names are native upstream modes. Each profile records the selected analysts, analysis horizon, quick/deep model identifiers, provider per model tier where supported, `max_debate_rounds`, `max_risk_discuss_rounds`, checkpoint/report preferences and optional provider-specific thinking settings. Validate every setting against the pinned TradingAgents release before passing it to the upstream configuration.

The adapter may use these documented features when supported by the pinned release:

- Parallel analyst execution.
- Configurable analyst selection.
- Optional Jev/TypeSafe screening of Reddit and StockTwits posts before sentiment analysis (future/optional; requires its provider credential and must be independently evaluated).
- Quick and deep model tiers; the quick tier serves analysts/researchers/debaters/trader, while the deep tier serves research/portfolio managers. The two tiers may use different providers.
- Optional `PortfolioContext` passed to `.propagate()`.
- Saving the report tree and single-page HTML report.
- Persistent decision memory (documented as always on) with its path configured through `TRADINGAGENTS_MEMORY_LOG_PATH`.
- Opt-in LangGraph checkpoint/resume using the supported `checkpoint_enabled` configuration and `TRADINGAGENTS_CACHE_DIR`.
- TradingAgents research backtest API for evaluation of model ratings over a ticker/date grid with its documented historical-date safeguards.

All of these must remain encapsulated inside `TradingAgentsProvider` and Module 2. Module 3 receives only TradeAI's normalized `AnalysisResult`.

### TradingAgents invocation

The current v0.7.1 README and tagged implementation document Python usage through:

- `TradingAgentsGraph(selected_analysts=..., debug=..., config=DEFAULT_CONFIG.copy())` — analyst selection is supplied when constructing the graph, not as a `propagate()` argument.
- `state, rating = graph.propagate(ticker, analysis_date, asset_type="stock", portfolio=...)`.
- `graph.save_reports(state, ticker, save_path=..., html=True)` to save the report tree and one-page HTML report.
- `PortfolioContext.model_validate({...})` from `tradingagents.portfolio` for optional portfolio context.

The v0.7.1 config keys include `llm_provider`, `quick_think_llm`, `deep_think_llm`, `quick_think_provider`, `deep_think_provider`, `max_debate_rounds`, `max_risk_discuss_rounds`, `checkpoint_enabled`, `data_cache_dir`, `memory_log_path` and `results_dir`. Map TradeAI profile fields to these exact upstream names inside the adapter. Use exchange-suffixed Yahoo tickers for supported markets, such as `RELIANCE.NS`. Validate against the installed tagged package before coding; do not copy old examples.

### Inputs

- Candidate ID and analysis ticker.
- Analysis date in ISO `YYYY-MM-DD`.
- Horizon (intraday/swing/research); record it even if the upstream framework does not natively interpret the horizon as a trading interval.
- Provider name and approved provider configuration.
- Selected analyst list when supported by the pinned release.
- Optional portfolio context built from the application's current holdings and cash, with a source timestamp and account snapshot ID.
- Named `AnalysisProfile` and its immutable version.
- Model tier/provider/model IDs, debate limits and report/checkpoint options. These are recorded for repeatability.
- Optional requested report format and analysis tags (such as strategy/timeframe).

### Outputs

- Analysis ID and job status.
- Provider and provider version.
- Raw provider rating preserved exactly.
- Normalized directional view: `BULLISH`, `NEUTRAL`, `BEARISH`, or `REVIEW`.
- Analyst/research sections available from the provider.
- Trader plan and risk/research notes when available.
- Analysis timestamp, data-source notes and errors/warnings.
- A reference to the full raw report/state when safely serializable; do not store Python object reprs as if they were structured facts.

### Rules

- AI output is research only; it cannot place, modify or cancel orders.
- Preserve the upstream rating text; do not silently turn `Overweight` into an unconditional buy or `Underweight` into an unconditional sell.
- `REVIEW`, missing reports, invalid output, exceptions or stale analysis must not be eligible for automatic execution.
- Run blocking `.propagate()` outside the ASGI event loop.
- Limit concurrent runs; record provider failures and retryable status.
- Keep TradingAgents' own memory/checkpoint SQLite files separate from TradeAI's main `tradeai.db`. Configure the documented memory path and checkpoint cache directory under `backend/data/tradingagents/`, isolated by environment. Verify the exact config keys against the installed tag.
- TradingAgents decision memory is supplementary research context. It must never replace TradeAI's broker-confirmed fills, realized P&L or audit history. Be aware that the upstream memory log is documented as always on; isolate test/dev/paper memory paths and do not mix backtest outcomes with live/paper trade records.
- Checkpointing is opt-in. Enable it only after the adapter has stable ticker/date/thread identity and restart/recovery tests.
- Save full/HTML reports as filesystem artifacts and store their relative path, metadata and checksum in the TradeAI database. Avoid storing unbounded HTML blobs in analysis rows. Capture the upstream sanitized run settings when available; never persist API keys or endpoint credentials.
- Portfolio context must come from a fresh TradeAI account snapshot. `positions: []` explicitly means a flat book; missing portfolio context must not be represented as an empty portfolio. If the account snapshot is unavailable or stale, omit portfolio context and mark the analysis warning, or reject the run if the selected profile requires portfolio awareness.
- The existing conversation graph is not automatically an interchangeable stock analysis provider. It must implement the shared provider contract before being registered.

### Acceptance criteria

- A manual candidate can be sent to TradingAgents from the single FastAPI app.
- The application remains responsive while analysis is running.
- Each run has a persistent ID and status.
- The result is normalized and persisted.
- Provider errors do not crash the FastAPI application or trading harness.
- A provider can be swapped in a test without changing Module 3.
- Profiles, analyst selection, quick/deep providers/models and portfolio snapshot references are persisted with each run.
- Report artifacts can be found through metadata without parsing local paths from a raw LangGraph state.
- Checkpoint resume and decision-memory isolation have tests or a documented deferred status.

---

## Module 3 — Decision Engine

### Responsibility

Convert research plus real-time/portfolio context into a deterministic, auditable trading decision. This is a TradeAI-owned module and must remain independent of TradingAgents, LangGraph provider internals and broker SDK classes.

### Subcomponents

1. `SignalEvaluator` — interprets normalized analysis and strategy signals.
2. `EntryExitValidator` — checks whether the current market price still meets strategy conditions and whether data is fresh.
3. `PositionSizer` — calculates a permissible quantity from configured risk, entry, stop and exposure limits.
4. `RiskValidator` — checks kill switch, daily loss, maximum order value, portfolio exposure, available margin, position conflicts, duplicate intent and market/session constraints.
5. `OrderIntentGenerator` — creates an approved, immutable order request for Module 4.
6. `StrategyRegistry` — selects intraday/swing strategy implementations.

### Public service interface

- `evaluate_entry(request) -> DecisionResult`
- `evaluate_exit(request) -> DecisionResult`
- `get_decision(decision_id) -> DecisionResult | None`

### Inputs

- Analysis ID and normalized `AnalysisResult` (loaded from persistence, not trusted as arbitrary client JSON).
- Strategy key and version.
- Latest market snapshot from shared market-data service.
- Current account snapshot: available funds/margin, open positions, pending orders and exposure.
- Risk configuration.
- Existing kill-switch state.

### Outputs

- Decision ID.
- `BUY_APPROVED`, `HOLD`, `REJECTED`, `SELL_APPROVED` or `REVIEW_REQUIRED`.
- Reasons and failed checks.
- Calculated quantity only when a trade is approved.
- Entry type/price constraints, stop-loss, target and maximum risk.
- An `OrderIntent` only for approved decisions.

### Mandatory rules

- An AI rating by itself is never sufficient to approve a trade.
- Missing/invalid stop-loss, stale prices, invalid quantity, missing instrument mapping, insufficient available funds, disabled kill switch, duplicate exposure or failed mandatory policy => no order intent.
- Position size must be calculated by deterministic code and limited by all applicable caps.
- For the initial scope, support long-only cash/intraday equity positions. Do not open short positions. A `SELL` may only reduce/close a position already held and must not exceed broker-confirmed open quantity.
- Strategy parameters must be explicit and versioned; do not hide magic numbers in prompts or source constants.
- Decision records must include analysis ID, strategy/version, market snapshot timestamp, risk settings version and explanations.
- Module 3 does not import the TradingAgents package and does not call Dhan order methods.

### Initial position-sizing policy (configurable)

For a long entry:

`risk_per_share = entry_price - stop_loss`

`quantity_by_risk = floor(max_risk_amount / risk_per_share)`

Then limit quantity by available funds, max order value, per-symbol exposure, total portfolio exposure, broker lot/quantity constraints and strategy-specific constraints. Reject if `risk_per_share <= 0` or calculated quantity is zero.

This formula is a software policy template, not an investment recommendation. Actual parameters must be configured and tested.

### Acceptance criteria

- Same inputs and strategy version produce the same decision (excluding explicitly time-dependent market data).
- AI provider changes do not require Module 3 code changes.
- Every approved decision contains a valid `OrderIntent` and all required risk metadata.
- Rejected decisions store exact reasons and produce no order intent.
- Duplicate evaluation cannot create duplicate executable intents.
- SELL quantity cannot exceed confirmed holdings in the initial long-only scope.

---

## Module 4 — Execution

### Responsibility

Translate an approved TradeAI `OrderIntent` into a broker-specific order, submit it through one selected adapter, and reconcile the broker's actual order/fill status.

### Adapters

- `PaperBrokerAdapter` — first execution target.
- `DhanBrokerAdapter` — reuse the existing official DhanHQ SDK integration.
- Other broker adapters are future work.

### Public service interface

- `execute_order(intent_id, mode) -> ExecutionResult`
- `get_order_status(order_id) -> ExecutionResult`
- `cancel_order(order_id) -> ExecutionResult` (only where supported and authorized)
- `reconcile_orders() -> ReconciliationSummary`

### Inputs

- Persisted approved `OrderIntent` ID.
- Execution mode (`PAPER` or `LIVE`).
- Broker/instrument mapping and required Dhan identifiers.
- Idempotency key.

### Outputs

- TradeAI order ID and broker order ID.
- Broker status.
- Requested quantity, filled quantity and remaining quantity.
- Average fill price, timestamps and rejection reason.
- Updated position only from confirmed fills, never merely from submitted quantity.

### Rules

- Module 4 accepts a persisted approved intent, not an arbitrary buy/sell payload from the frontend.
- Re-run mandatory execution guardrails immediately before submission.
- Enforce idempotency to prevent duplicate submission after timeout/retry.
- Treat timeout as unknown broker status until reconciled; do not blindly resubmit.
- Handle partial fills and rejected/cancelled orders.
- Keep the existing Dhan SDK client as the only Dhan connection owner.
- `PAPER` is default. `LIVE` requires explicit configuration, a live-trading master switch and all required account/broker checks.
- MCP is not required for the first implementation. The direct Dhan SDK remains the primary order path; an MCP adapter may be added later behind the same interface if needed.

### Acceptance criteria

- An approved paper intent produces a broker-neutral execution record.
- Repeated execution calls with the same idempotency key do not create a second order.
- Partial fills update only the actually filled quantity.
- A broker rejection is persisted and visible.
- An API timeout triggers status reconciliation rather than duplicate submission.

---

## Module 5 — Position Monitoring

### Responsibility

Monitor positions created from confirmed fills and produce hold/reassessment/exit requests. It is not an order-placement module.

### Subcomponents

- Stop-loss rule.
- Target rule.
- Time/session and auto-square-off rule.
- Data freshness/market-feed health rule.
- Optional AI reassessment trigger.

### Public service interface

- `evaluate_open_positions() -> list[PositionEvaluation]`
- `request_reassessment(position_id, reason) -> AnalysisJobReceipt`
- `create_exit_request(position_id, reason) -> ExitEvaluationRequest`

### Inputs

- Broker-confirmed or paper-confirmed position quantity.
- Average fill price and open quantity.
- Latest market data and timestamp.
- Strategy's stop/target/time rules.
- Market session status.

### Outputs

- `HOLD`, `REASSESS`, `EXIT_CANDIDATE`, `DATA_UNAVAILABLE`.
- Unrealized P&L and rule-trigger details.
- Reassessment/exit request ID.

### Rules

- Only monitor confirmed filled quantity; distinguish order pending from open position.
- Hard stop-loss and mandatory square-off checks are deterministic and must not wait for an LLM.
- AI reassessment may provide context but does not directly place a sell order.
- Every exit candidate must pass Module 3's exit policy and Module 4's execution guardrails.
- Avoid repeated reassessment for the same unchanged trigger; apply cooldown/deduplication.
- On feed disconnection or stale price, mark data unavailable and follow a configured fail-safe policy; do not assume the last price is current.

### Acceptance criteria

- Open paper positions are monitored on the configured cadence.
- Stop/target/time triggers produce a deduplicated exit request.
- AI reassessment is triggered only by configured conditions.
- No module other than Module 4 sends an order to a broker.

---

## Future modules (not in first implementation)

| Future module | Planned responsibility | Integration point |
|---|---|---|
| Backtesting & Evaluation | Evaluate TradingAgents research ratings over ticker/date grids and separately replay TradeAI strategies with fills, fees, slippage and no look-ahead | Use TradingAgents backtest API only for AI-decision research; build a TradeAI simulator for full strategy lifecycle. |
| Portfolio Allocation | Allocate capital across approved strategies and symbols | Module 3, before position sizing. |
| Performance Analytics & Feedback | Win rate, expectancy, drawdown, exposure, slippage and provider/strategy comparisons; create reviewed feedback summaries from actual TradeAI trade outcomes | Read-only analytics over persisted decisions, orders, positions and confirmed fills; never auto-change production risk rules. |
| Portfolio Allocation | Allocate capital across approved strategies and symbols, subject to portfolio-level limits | Module 3, before position sizing. |
| Notifications | UI/Telegram/email alerts for analysis completion, approvals, fills, rejections and exits | Event/notification interface; must not change trading decisions. |
| Automated Scanner | Top gainers/losers, volume and momentum selection | Module 1 provider interface. |
| Additional AI providers | Alternative research models/frameworks | Module 2 provider interface. |
| Additional brokers | Other broker APIs | Module 4 broker adapter interface. |
