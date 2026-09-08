# Backend API & Architecture Documentation

This document outlines the architecture, end-to-end operational workflows, and API specifications for the StockAI / TradeAI backend service.

---

## 1. High-Level Architecture

```
[ Client / Frontend / Cron Scheduler ]
                 │
                 ▼
         FastAPI App Gateway
                 │
  ┌──────────────┼───────────────────────────┬───────────────────────────┐
  ▼              ▼                           ▼                           ▼
Agentic      Background Watchdog        Trading & Brokerage         Market Analytics
Pipeline      Evaluation Engine          (DhanHQ & Paper)            & Data Feeds
(/api/conv)  (watchdog_service)          (/trading, /trades)         (/data, /stocks)
  │              │                           │                           │
  ▼              ▼                           ▼                           ▼
[LangGraph]  [LangGraph Bg Branch]      [Guardrail Service]        [Technical Calcs]
  │              │                           │                           │
  └──────────────┴─────────────┬─────────────┴───────────────────────────┘
                               ▼
            Database Layer (PostgreSQL / SQLite via asyncpg & aiosqlite)
      Tables: event_logs, active_positions, stock_trade_logs, snapshots
```

---

## 2. API Endpoints & Workflows

### 2.1 Conversational AI Agent (`/api/conversation`)

#### `POST /api/conversation` (also `GET /api/conversation`)
- **Purpose**: Interactive decision support engine that answers natural language trading and investment questions.
- **Scenario**: A trader asks: *"What is the intraday outlook on Reliance and what are its key pivot points?"*
- **Operational Flow**:
  1. **Intake & Validation**: Receives `ChatRequest(query: str, ticker: Optional[str])`.
  2. **Audit Logging**: Emits an `INFO` event to `event_logs` detailing the query and agent component.
  3. **State Initialization**: Assembles `TradingGraphState` with `is_background_run=False`.
  4. **Graph Execution**:
     - `initial_routing` routes to `router_node`.
     - `router_node`: Categorizes query intent and identifies company entities.
     - `company_resolver_node`: Normalizes company names to exchange tickers (e.g. `Reliance` -> `RELIANCE.NS`).
     - `planner_node`: Plans required tool invocations (`stock_analyzer`).
     - `tool_executor_node`: Executes financial tools, computing RSI, MACD, Bollinger Bands, and Pivot Points.
     - `answer_node`: Formulates multi-horizon analysis (Intraday, Short-Term, Long-Term) without hallucinating metrics.
     - `formatter_node`: Structures output into markdown text, citations, and structured JSON.
  5. **Response & Audit**: Logs `SUCCESS` into `event_logs` and returns `ChatResponse`.

---

### 2.2 Background Active Positions Watchdog (`app/services/watchdog_service.py`)

#### `evaluate_active_positions()`
- **Purpose**: Periodic automated evaluation of open trading positions without requiring human interaction.
- **Scenario**: Every 5 minutes during market hours, the watchdog checks whether open trades hit targets, stop-losses, or trend changes.
- **Operational Flow**:
  1. Queries all rows from `active_positions` where `status == "OPEN"`.
  2. Logs the evaluation cycle start to `event_logs`.
  3. Dispatches each position through `trading_compiled_graph.ainvoke` with `is_background_run=True`.
  4. `initial_routing` routes directly to `planner_node` bypassing conversational dialogue.
  5. `planner_node` dispatches `stock_analyzer` for the target ticker.
  6. `tool_executor_node` fetches live prices, calculates pivot levels, updates `active_positions` (price, recommendation, reason, `status="EVALUATED"`), and completes the run.
  7. Logs evaluation outcome to `event_logs`.

---

### 2.3 Stock Analysis & Prediction Snapshots (`/stocks` & `/analysis`)

#### `POST /api/v1/stocks/analyze`
- **Purpose**: Generates quantitative and AI-interpreted stock analysis reports for selected stocks or top intraday movers.
- **Scenario**: Trader clicks "Analyze Top Movers" on the dashboard.
- **Operational Flow**:
  1. Resolves tickers from request or queries top gainers/losers via `market_data_service`.
  2. Computes technical indicators (RSI, SMA, EMA, MACD, Pivot Points, Support/Resistance).
  3. Generates grounded AI recommendation (`BUY`, `HOLD`, `AVOID`).
  4. Saves analysis record into `stock_analysis_snapshots`.
  5. Returns structured analysis response list.

#### `GET /v1/analysis/today` & `GET /v1/analysis/prediction`
- **Purpose**: Retrieves historical and current day AI analysis snapshots for performance tracking and model back-testing.
- **Scenario**: Checking what the system predicted yesterday for a stock against its actual closing performance.

---

### 2.4 Live Market Data & Risk Monitoring (`/data` & `/market`)

#### `GET /v1/market/status` & `GET /v1/market/indices`
- **Purpose**: Provides live IST market session status (Open / Closed / Pre-Market) and benchmark indices (`NIFTY 50`, `BANKNIFTY`, `SENSEX`, Gold, Silver).

#### `GET /v1/data/interval-data/{ticker}`
- **Purpose**: Fetches 15-minute candlestick chart data along with calculated VWAP, RSI, and MACD indicators.
- **Scenario**: Frontend displays interactive candlestick charts for a requested ticker.

#### `GET /v1/data/position-monitor`
- **Purpose**: Live portfolio risk tracker with unrealized P&L calculation and intraday auto-squareoff detection.
- **Scenario**: Checks open trades against the clock. If the current time is 15:15 IST or later, sets `needs_auto_squareoff = True` and recommendation to `FORCE_EXIT`.

---

### 2.5 Trading Execution & Guardrails (`/trading` & `/trades`)

#### `POST /v1/trading/orders`
- **Purpose**: Submits buy/sell orders via DhanHQ broker integration or paper trading engine with mandatory safety checks.
- **Scenario**: Placing a trade for 25 shares of `TCS.NS`.
- **Operational Flow**:
  1. Validates trade against guardrails (`validate_trade_execution`):
     - Verifies Master Kill-Switch is enabled (`is_trading_enabled`).
     - Ensures total order value does not exceed `max_order_value_inr`.
  2. If valid, routes order to DhanHQ API (if credentials configured) or paper simulator.
  3. Stores trade record in `stock_trade_logs`.

#### `POST /v1/trading/square-off/{trade_id}`
- **Purpose**: Closes open intraday or delivery trades, calculating realized net P&L and broker commissions.

#### `GET /v1/trading/guardrails/status` & `POST /v1/trading/guardrails/toggle`
- **Purpose**: Real-time inspection and toggle of the Master Kill-Switch to halt automated trading system-wide.

---

### 2.6 Scheduled Batch Jobs (`/jobs`)

#### `GET /v1/jobs` & `POST /v1/jobs` & `POST /v1/jobs/{job_id}/run`
- **Purpose**: Schedules recurring cron-based stock evaluation jobs and allows manual out-of-band triggering.
- **Scenario**: Setting up a job to analyze a custom watchlist (`"RELIANCE.NS,TCS.NS,INFY.NS"`) at 9:15 AM every weekday.

---

## 3. Database Schema Overview

| Table Name | Entity Model | Responsibility |
| :--- | :--- | :--- |
| `event_logs` | `EventLog` (`AgentLog`) | Auditing agent runs, components, timestamps, tickers, statuses, and statements. |
| `active_positions` | `ActivePosition` | Live position tracking with targets, stop-losses, and evaluations. |
| `stock_analysis_snapshots` | `StockAnalysisSnapshot` | Daily AI analysis records, scores, and technical metrics. |
| `stock_trade_logs` | `StockTradeLog` | Realized/unrealized trade logs, broker order IDs, P&L. |
| `trading_guardrail_settings` | `TradingGuardrailSettings` | Kill-switch toggle, max order limits, auto-squareoff times. |
| `analysis_jobs` | `AnalysisJob` | Scheduled cron analysis configurations. |
| `job_execution_logs` | `JobExecutionLog` | Execution records and outcomes of scheduled jobs. |
