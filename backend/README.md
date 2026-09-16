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
  ┌──────────────┼───────────────────────────┬───────────────────────────┬───────────────────────────┐
  ▼              ▼                           ▼                           ▼                           ▼
Agentic      Background Watchdog        Trading & Brokerage         Market Analytics          Trading Harness
Pipeline      Evaluation Engine          (DhanHQ & Paper)            & Data Feeds              (/harness)
(/api/conv)  (watchdog_service)          (/trading, /trades)         (/data, /stocks)          app/harness/
  │              │                           │                           │                           │
  ▼              ▼                           ▼                           ▼                           ▼
[LangGraph]  [LangGraph Bg Branch]  [Guardrail Service → dhan_service]  [Technical Calcs]   [Strategies + Feed +
  │              │                     │             (dhanhq SDK)           │                Watchdog Sched.]
  │              │                     ▼                                    │                        │
  │              │              [dhan_client.py — shared DhanContext / dhanhq client] ◄───────────────┘
  │              │                           │                                                        │
  └──────────────┴─────────────┬─────────────┴────────────────────────────────────────────────────────┘
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

---

## 4. DhanHQ SDK Integration

All Dhan connectivity goes through the official `dhanhq` Python SDK
(https://github.com/dhan-oss/DhanHQ-py), not hand-rolled REST calls. This
replaced an earlier version of `dhan_service.py` that built `access-token`
headers manually and called `httpx.AsyncClient` against raw
`api.dhan.co/v2/...` URLs.

| File | Owns |
| :--- | :--- |
| `app/services/dhan_client.py` | The **shared connection**: one `DhanContext` + one `dhanhq` client per process (both `@lru_cache`d), thin async wrappers around the SDK's blocking calls (`get_holdings_raw`, `place_order_raw`, `get_fund_limits_raw`, ...), and the trading-symbol → `security_id` lookup (`resolve_security_id`) that Dhan's order/feed APIs actually require. Every DhanAPIError raised anywhere in the app originates here. |
| `app/services/dhan_service.py` | The **app-specific rules** on top of that connection: guardrail validation, paper-vs-live branching, and persisting every order into `stock_trade_logs` regardless of whether it was a paper or live fill. |
| `app/harness/connection_manager.py` | The **live price feed** (`MarketFeed` websocket) — a separate, persistent connection from the request/response REST calls above, since continuously polling REST for "current price" doesn't scale and gets rate-limited. |

Why the SDK instead of raw REST:
- One authenticated context reused everywhere, instead of rebuilding headers per call site.
- Consistent, SDK-parsed responses instead of guessing at response key casing (`totalQty` vs `total_qty` vs `quantity`).
- Access to the live `MarketFeed` websocket for streaming prices — the right way to "continuously fetch current price," instead of polling a REST endpoint in a loop.
- `get_fund_limits()` gives available margin directly — this is what powers the margin check before a strategy's BUY intent is executed (see §5).

**Setup**: add `DHAN_CLIENT_ID` and `DHAN_ACCESS_TOKEN` to `backend/.env` (already read by `app/config.py`; `dhan_service.py`'s old direct `os.getenv` calls for these are gone — `dhan_client.py` is now the only place that reads them). `dhanhq` is already pinned in `requirements.txt`.

**Known gap to fill in before going live**: `dhan_client.refresh_security_master()` pulls Dhan's compact instrument list to build the symbol → `security_id` cache, and reads columns named `SEM_TRADING_SYMBOL` / `SEM_SMST_SECURITY_ID` — verify those against one real response from your account before relying on it, since Dhan's instrument-master schema isn't guaranteed to stay identical. Same caveat applies to the tick field names read in `connection_manager.py`'s `_ingest_tick()`.

---

## 5. Backend Trading Harness (`app/harness/`)

A "backend harness," for a trading bot, is the layer that turns several
independent trading logics and one broker connection into a single running
system. Concretely, it's the piece that:

- **Runs the main loop** — fetch price → run strategy logic → decide → execute → log.
- **Manages the broker connection lifecycle** — auth, and reconnects when the websocket drops.
- **Coordinates independent strategies** so they don't step on each other (e.g. two strategies both trying to buy the same stock).
- **Handles scheduling** — market hours, and background evaluation cycles.
- **Centralizes logging/error handling** so one broken strategy doesn't crash the whole bot.

This app already had two of these pieces before this change
(`watchdog_service.py` for background evaluation, `guardrail_service.py` for
centralized trade validation) — `app/harness/` is what ties them, the Dhan
SDK connection, and any number of strategies together into the one system
described above, rather than each strategy managing its own broker calls.

| Responsibility above | File | Class |
| :--- | :--- | :--- |
| Main loop | `app/harness/runner.py` | `TradingHarness._tick_loop()` / `_run_one_cycle()` |
| Broker connection lifecycle | `app/harness/connection_manager.py` | `DhanFeedManager` |
| Strategy coordination | `app/harness/strategy_coordinator.py` | `StrategyCoordinator` |
| Scheduling | `app/harness/scheduler.py` | `is_market_open()`, `WatchdogScheduler` |
| Centralized logging / error isolation | `app/harness/runner.py` | `TradingHarness._run_strategy_safely()`, `_execute_intent()` |

**How a tick flows through the harness:**

```
DhanFeedManager (background thread, MarketFeed websocket)
        │  latest tick per security_id
        ▼
TradingHarness._tick_loop()  ── gated by is_market_open() ──▶ skip if market closed
        │  every HARNESS_TICK_INTERVAL_SECONDS
        ▼
_run_one_cycle()
        │  fetches available_margin via dhan_service.get_margin_snapshot()
        │  builds `context = {available_margin, open_positions, market_open}`
        ▼
for each registered strategy → _run_strategy_safely(strategy, context)
        │  try/except around the ENTIRE strategy call —
        │  one strategy's bug/exception is logged and skipped,
        │  every other strategy still runs this tick and every future tick
        ▼
strategy.evaluate(price, context) → OrderIntent | None
        ▼ (if an intent came back)
_execute_intent()
        │  acquires StrategyCoordinator.lock_for(symbol)  ← prevents two
        │  strategies both buying the same symbol in the same tick
        ▼
dhan_service.place_order()  ← same guardrails / paper-live branching /
                                trade-log persistence as manual orders
                                placed through POST /trading/orders
```

Meanwhile, `WatchdogScheduler` runs `watchdog_service.evaluate_active_positions()`
on its own independent cadence (`HARNESS_WATCHDOG_INTERVAL_SECONDS`,
default 300s) — checking stop-loss/target on positions the harness (or a
human) already opened, separate from the faster per-tick entry loop above.

**Control & debugging** — `app/api/harness_routes.py`:

| Endpoint | Purpose |
| :--- | :--- |
| `GET /v1/harness/status` | Single snapshot: is it running, is the feed connected, which strategies are registered, open positions, tick count, last error. Check this first when a strategy doesn't seem to be trading. |
| `POST /v1/harness/start` | Connects the feed for all registered strategies, starts the watchdog scheduler, starts the tick loop. |
| `POST /v1/harness/stop` | Cleanly closes the feed, stops the watchdog scheduler, exits the tick loop. Does **not** touch existing orders/positions — the harness and the Master Kill-Switch (`/trading/guardrails`) are two independent off-switches. |

Configuration (in `app/config.py` / `.env`):

| Setting | Default | Meaning |
| :--- | :--- | :--- |
| `HARNESS_TICK_INTERVAL_SECONDS` | `5` | How often the main loop checks prices and runs strategies. |
| `HARNESS_WATCHDOG_INTERVAL_SECONDS` | `300` | How often open positions are re-checked for stop-loss/target/auto-squareoff. |
| `HARNESS_AUTO_START` | `false` | If `true`, the harness starts automatically on app startup (`main.py`'s `on_startup`) instead of requiring `POST /v1/harness/start`. Leave `false` until you've registered real strategies. |

---

## 6. Adding a New Strategy (Trading Logic)

This is the extension point the harness exists for — a new trading idea
should never require touching `dhan_service.py`, `runner.py`, or any route.

1. **Write the strategy** as a `BaseStrategy` subclass with one method,
   `evaluate(price, context) -> OrderIntent | None`. See
   `app/harness/example_strategies.py::ThresholdBuyStrategy` for the shape.
   Put your real signal logic here — technical indicators
   (`app/services/technical_analysis_service.py` already has RSI/MACD/pivot
   calculations), an LLM call, a model prediction, whatever the logic needs.
   The strategy never calls Dhan directly; it only returns intent.

2. **Resolve the symbol's `security_id`** once (needed for both the feed
   subscription and order placement):
   ```python
   from app.services.dhan_client import resolve_security_id
   security_id = await resolve_security_id("RELIANCE.NS")
   ```

3. **Register it** with the shared harness instance — e.g. in a small
   `app/harness/bootstrap.py` you call from `main.py`'s startup, or from a
   route/script for ad-hoc registration:
   ```python
   from app.harness import harness
   from app.harness.example_strategies import ThresholdBuyStrategy

   harness.register_strategy(
       ThresholdBuyStrategy(
           name="reliance_dip_buy",
           symbol="RELIANCE.NS",
           security_id=security_id,
           buy_below=1350.0,
           quantity=5,
       )
   )
   ```

4. **Start (or restart) the harness** — `POST /v1/harness/start`, or let
   `HARNESS_AUTO_START` do it. Registering after the harness is already
   running also works: `register_strategy()` subscribes the new symbol onto
   the live feed immediately, no restart required.

That's the whole extension surface. Multiple strategies can watch the same
symbol (the `StrategyCoordinator` lock keeps their orders from colliding)
or different symbols entirely — the loop, feed, and logging are shared
infrastructure that every strategy gets for free.

---

## 7. Debugging Guide

Where to look, in order, when something isn't behaving:

1. **`GET /v1/harness/status`** — is the harness running, is the feed
   connected, is the market considered open, which strategies are
   registered, what's the last recorded error. This answers "is the
   automated loop even running" before you look at anything else.

2. **`logs/agent.log`** (rotating, 5MB × 3 backups, also mirrored to
   stdout) — every harness event (`TradingHarness` logger name), strategy
   error, feed reconnect attempt, and watchdog cycle is written here via
   `app.utils.logger.get_agent_logger(...)`. Filter by agent name:
   ```bash
   grep "TradingHarness" backend/logs/agent.log | tail -50
   grep "DhanFeedManager" backend/logs/agent.log | tail -50
   ```

3. **`event_logs` table** — the same events as above, persisted to the DB
   (`GET`-able via any DB browser, or add a quick route if you want one over
   HTTP) with `agent_name`, `ticker`, `status`, `message`, `timestamp`
   columns — useful for querying "everything that happened for RELIANCE.NS
   today" instead of grepping a flat file.

4. **`stock_trade_logs` table** (`GET /v1/trades/`) — every order the
   harness (or a manual `POST /v1/trading/orders` call) actually placed,
   whether paper or live, with the `notes` column showing which strategy
   triggered it (`[strategy_name] reason...`) — this is how you trace an
   order back to the logic that fired it.

5. **DhanAPIError messages** — every SDK-level failure (auth, bad
   `security_id`, insufficient margin, network error, or Dhan's own
   `{"status": "failure", ...}` payloads) is normalized to this one
   exception type in `dhan_client.py`, so the error message itself tells
   you which SDK call failed and why — you don't need to guess which layer
   raised it.

Common failure modes and where they come from:

| Symptom | Likely cause | Where to look |
| :--- | :--- | :--- |
| `feed_connected: false` in `/harness/status` | Bad/expired `DHAN_ACCESS_TOKEN`, or Dhan-side outage | `DhanFeedManager._run_loop()` reconnect logs (`grep DhanFeedManager`) |
| Strategy never fires despite the "right" price | `resolve_security_id()` returned `None` — feed never subscribed | Check `refresh_security_master()` column names still match Dhan's schema (§4) |
| Order placed as `DHAN_PAPER_...` when you expected live | `paper_trading_mode` guardrail is still `true` | `GET /v1/trading/guardrails/status`, then `POST /v1/trading/guardrails/toggle` |
| Two strategies both bought the same stock | Shouldn't happen — check `StrategyCoordinator.lock_for()` is being awaited around `_execute_intent()`, not bypassed by a custom call into `dhan_service.place_order()` from outside the harness | `app/harness/runner.py` |
| One strategy's exception silently "stopped everything" | It shouldn't — `_run_strategy_safely()` wraps every strategy individually; if the whole loop stopped, the error was in `_run_one_cycle()`'s own code (e.g. the margin-check call), not in a strategy | `_tick_loop()`'s own try/except, `last_error` in `/harness/status` |

Extending debuggability further: since every new strategy is just a
`BaseStrategy` subclass with no other wiring, you can unit-test
`evaluate()` directly with a plain price + hand-built `context` dict,
without needing a live Dhan connection, the feed, or the event loop at all.


app/
│
├── api/
│   ├── trading_routes.py
│   ├── market_routes.py
│   └── ai_routes.py
│
├── services/
│   ├── trading_service.py
│   ├── market_service.py
│   └── ai_service.py
│
├── integrations/
│   └── dhan/
│       ├── client.py
│       ├── orders.py
│       ├── portfolio.py
│       └── instruments.py
│
├── guardrails/
│   └── trading_guardrails.py
│
├── db/
│   ├── base.py
│   └── models.py
│
└── schemas/
    ├── trading.py
    └── ai.py