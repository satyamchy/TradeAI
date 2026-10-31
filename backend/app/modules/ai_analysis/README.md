# AI Analysis (Module 2)

Owns provider selection, TradingAgents/legacy LangGraph adapters, execution of analysis, and normalization into the shared `AnalysisResult` contract. It is research only and never calls Module 4 or broker order methods.

## Implemented interface

`AIAnalysisService` exposes `request_analysis`, `run_analysis_job`, `get_analysis`, and `list_analyses`. It accepts an injected candidate lookup, optional authoritative portfolio snapshot provider, provider, profile registry, job manager, and SQLAlchemy result repository. The default provider is lazy: importing this module does not import TradingAgents, create an LLM client, or make a network request.

Requests resolve a server-owned, immutable profile version. The pinned TradingAgents v0.7.1 adapter validates its supported analyst names (`market`, `social`, `news`, `fundamentals`), copies `DEFAULT_CONFIG`, maps quick/deep provider/model and debate settings, and runs blocking `propagate()` in a worker thread. It preserves the raw five-tier rating and maps it to a broad direction, with malformed/missing ratings becoming `REVIEW`.

The adapter keeps the upstream memory log, checkpoint cache, and report artifacts under `TRADINGAGENTS_DATA_DIR/<APP_ENV>-<TRADING_MODE>/`. Checkpointing defaults off. Only a relative HTML report path and SHA-256 checksum are persisted; upstream graph state objects and secrets are not serialized. The existing `AnalysisJobManager` persists idempotent requests/status and runs each handler with bounded retries. The module writes normalized results to the `analysis_runs` table.

The provider pin and candidate core-version pins are in `requirements-tradingagents.txt`. Install with `python -m pip install -r requirements-tradingagents.txt` after the project requirements are installed, then run `python -m pip check`. The project environment initially had LangGraph 1.2.11, LangChain Core 1.6.3, and pandas 3.0.5; the tagged release requires at least 1.2.12, 1.6.5, and 3.0.6 respectively. Provider code tests use fakes and do not require API credentials. No real LLM smoke call is part of the default test suite.

The Module 2 service is not yet connected to the candidate API or FastAPI background worker. That cross-module/API wiring belongs to Phase 3 after all five modules pass their independent tests.

## Tests

Run independently from `backend/`:

```powershell
python -m pytest app/modules/ai_analysis/tests -q
```

Tests use temporary SQLite databases and fake candidate, portfolio, graph, and provider adapters. They make no paid model calls.
