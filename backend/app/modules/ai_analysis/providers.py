"""Provider interface and lazy, version-verified TradingAgents v0.7.1 adapter."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from app.modules.ai_analysis.schemas import AnalysisProviderOutput, AnalysisProviderRequest
from app.shared.logging import bind_log_context, get_logger, reset_log_context

logger = get_logger(__name__)


class TransientProviderFailure(RuntimeError):
    """A provider/network failure suitable for the job manager's bounded retry."""


class PermanentProviderFailure(RuntimeError):
    """A configuration, validation or malformed-result failure that must not retry."""


class AnalysisProvider(Protocol):
    async def analyze(self, request: AnalysisProviderRequest) -> AnalysisProviderOutput:
        ...


class TradingAgentsProvider:
    """Adapt the tagged TradingAgentsGraph API without importing it at module import."""

    _REQUIRED_CONFIG_KEYS = frozenset(
        {
            "llm_provider",
            "quick_think_llm",
            "deep_think_llm",
            "quick_think_provider",
            "deep_think_provider",
            "max_debate_rounds",
            "max_risk_discuss_rounds",
            "checkpoint_enabled",
            "data_cache_dir",
            "memory_log_path",
            "results_dir",
        }
    )
    expected_version = "0.7.1"

    def __init__(
        self,
        *,
        data_root: str | Path,
        environment: str,
        graph_factory=None,
        default_config: Mapping[str, Any] | None = None,
        provider_version: str | None = None,
        portfolio_factory=None,
    ):
        self._data_root = Path(data_root).expanduser().resolve()
        self._environment = _safe_path_component(environment)
        self._graph_factory = graph_factory
        self._default_config = dict(default_config) if default_config is not None else None
        self._provider_version = provider_version
        self._portfolio_factory = portfolio_factory

    @property
    def version(self) -> str:
        return self._provider_version or self.expected_version

    async def analyze(self, request: AnalysisProviderRequest) -> AnalysisProviderOutput:
        tokens = bind_log_context(module="ai_analysis", analysis_id=str(request.analysis_id))
        try:
            return await asyncio.to_thread(self._analyze_sync, request)
        finally:
            reset_log_context(tokens)

    def _dependencies(self):
        if self._default_config is None:
            try:
                from tradingagents.default_config import DEFAULT_CONFIG
                import tradingagents
            except ImportError as exc:
                raise PermanentProviderFailure(
                    "TradingAgents v0.7.1 is not installed; install backend/requirements-tradingagents.txt"
                ) from exc
            default_config = DEFAULT_CONFIG
            provider_version = tradingagents.__version__
        else:
            default_config = self._default_config
            provider_version = self._provider_version or "unknown"

        graph_factory = self._graph_factory
        if graph_factory is None:
            try:
                from tradingagents.graph.trading_graph import TradingAgentsGraph
            except ImportError as exc:
                raise PermanentProviderFailure("TradingAgentsGraph is unavailable") from exc
            graph_factory = TradingAgentsGraph

        portfolio_factory = self._portfolio_factory
        if portfolio_factory is None:
            try:
                from tradingagents.portfolio import PortfolioContext
            except ImportError as exc:
                raise PermanentProviderFailure("TradingAgents PortfolioContext is unavailable") from exc
            portfolio_factory = PortfolioContext.model_validate
        return default_config, graph_factory, portfolio_factory, provider_version

    def _analyze_sync(self, request: AnalysisProviderRequest) -> AnalysisProviderOutput:
        defaults, graph_factory, portfolio_factory, provider_version = self._dependencies()
        missing = self._REQUIRED_CONFIG_KEYS - set(defaults)
        if missing:
            raise PermanentProviderFailure(
                "Installed TradingAgents config is missing required keys: " + ", ".join(sorted(missing))
            )
        profile = request.profile
        if set(profile.selected_analysts) - {"market", "social", "news", "fundamentals"}:
            raise PermanentProviderFailure("Analysis profile requests analysts unsupported by TradingAgents v0.7.1")

        environment_root = self._data_root / self._environment
        report_root = environment_root / "reports"
        analysis_report_dir = report_root / str(request.analysis_id)
        cache_dir = environment_root / "cache"
        memory_path = environment_root / "memory" / "trading_memory.md"
        for directory in (analysis_report_dir, cache_dir, memory_path.parent):
            directory.mkdir(parents=True, exist_ok=True)

        upstream_config = dict(defaults)
        upstream_config.update(
            {
                "quick_think_provider": profile.quick_provider,
                "quick_think_llm": profile.quick_model,
                "deep_think_provider": profile.deep_provider,
                "deep_think_llm": profile.deep_model,
                "max_debate_rounds": profile.max_debate_rounds,
                "max_risk_discuss_rounds": profile.max_risk_discuss_rounds,
                "checkpoint_enabled": profile.checkpoint_enabled,
                "data_cache_dir": str(cache_dir),
                "memory_log_path": str(memory_path),
                "results_dir": str(report_root),
            }
        )
        portfolio = None
        if request.portfolio is not None:
            portfolio = portfolio_factory(
                {
                    "cash": float(request.portfolio.cash) if request.portfolio.cash is not None else None,
                    "currency": request.portfolio.currency,
                    "positions": [
                        {
                            "ticker": position.ticker,
                            "quantity": float(position.quantity),
                            "average_price": (
                                float(position.average_price) if position.average_price is not None else None
                            ),
                        }
                        for position in request.portfolio.positions
                    ],
                }
            )

        graph = graph_factory(
            selected_analysts=list(profile.selected_analysts),
            debug=False,
            config=upstream_config,
        )
        try:
            state, source_rating = graph.propagate(
                request.instrument.analysis_ticker,
                request.analysis_date.isoformat(),
                asset_type="stock",
                portfolio=portfolio,
            )
        except (TimeoutError, ConnectionError) as exc:
            raise TransientProviderFailure("TradingAgents provider request failed transiently") from exc
        except Exception as exc:
            # Upstream messages can contain request details; do not copy them to
            # jobs, logs, or the API's public failure response.
            logger.warning("TradingAgents run failed (%s)", type(exc).__name__)
            raise PermanentProviderFailure("TradingAgents analysis failed") from exc
        if not isinstance(state, Mapping):
            raise PermanentProviderFailure("TradingAgents returned an invalid state object")

        warnings = list(request.warnings)
        reports = _extract_reports(state)
        if not source_rating or str(source_rating).strip().upper() == "REVIEW":
            warnings.append("UPSTREAM_RATING_REVIEW")
        artifacts = {}
        if profile.save_html_report:
            try:
                graph.save_reports(
                    dict(state),
                    request.instrument.analysis_ticker,
                    save_path=analysis_report_dir,
                    html=True,
                )
                html_path = analysis_report_dir / "complete_report.html"
                if not html_path.is_file():
                    raise PermanentProviderFailure("TradingAgents did not produce the requested HTML report")
                relative_path = html_path.resolve().relative_to(self._data_root)
                checksum = hashlib.sha256(html_path.read_bytes()).hexdigest()
                artifacts = {
                    "html_report_path": relative_path.as_posix(),
                    "report_checksum": f"sha256:{checksum}",
                }
            except PermanentProviderFailure:
                raise
            except (OSError, ValueError) as exc:
                raise PermanentProviderFailure("TradingAgents report artifact could not be saved safely") from exc

        return AnalysisProviderOutput(
            provider_version=provider_version,
            source_rating=(str(source_rating) if source_rating is not None else None),
            reports=reports,
            warnings=warnings,
            report_artifacts=artifacts,
        )


def normalize_direction(source_rating: str | None) -> str:
    """Map the upstream five-tier rating without collapsing it into an order."""
    if source_rating is None:
        return "REVIEW"
    normalized = source_rating.strip().casefold()
    if normalized in {"buy", "overweight"}:
        return "BULLISH"
    if normalized == "hold":
        return "NEUTRAL"
    if normalized in {"underweight", "sell"}:
        return "BEARISH"
    return "REVIEW"


def _extract_reports(state: Mapping[str, Any]) -> dict[str, str]:
    mapping = {
        "market": "market_report",
        "sentiment": "sentiment_report",
        "news": "news_report",
        "fundamentals": "fundamentals_report",
        "bull_bear_research": "investment_plan",
        "trader_plan": "trader_investment_plan",
        "portfolio_decision": "final_trade_decision",
    }
    reports = {
        output_key: _safe_report_text(state.get(state_key))
        for output_key, state_key in mapping.items()
        if _safe_report_text(state.get(state_key))
    }
    risk = state.get("risk_debate_state")
    if isinstance(risk, Mapping):
        risk_sections = []
        for key in ("aggressive_history", "conservative_history", "neutral_history", "history"):
            section = _safe_report_text(risk.get(key))
            if section and section not in risk_sections:
                risk_sections.append(section)
        if risk_sections:
            reports["risk_assessment"] = "\n\n".join(risk_sections)
    return reports


def _safe_report_text(value: Any) -> str:
    if isinstance(value, str):
        return _redact_report(value.strip())
    if isinstance(value, (list, tuple)):
        return "\n".join(_redact_report(item.strip()) for item in value if isinstance(item, str) and item.strip())
    return ""


def _redact_report(value: str) -> str:
    return re.sub(
        r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+|((?:api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*)[^\s,;]+",
        lambda match: (match.group(1) or match.group(2)) + "[REDACTED]",
        value,
    )


def _safe_path_component(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    if not safe or safe in {".", ".."}:
        raise ValueError("invalid TradingAgents data environment")
    return safe[:64]
