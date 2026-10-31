"""Server-controlled, immutable TradeX analysis profile registry."""

from collections.abc import Iterable

from app.modules.ai_analysis.schemas import AnalysisProfile
from app.shared.config import Settings, settings
from app.shared.contracts import AnalysisHorizon


class UnknownAnalysisProfile(ValueError):
    """The caller requested an unregistered profile or version."""


class AnalysisProfileRegistry:
    def __init__(self, profiles: Iterable[AnalysisProfile]):
        items = tuple(profiles)
        by_version = {(profile.key, profile.version): profile for profile in items}
        if not by_version:
            raise ValueError("at least one analysis profile must be registered")
        if len(by_version) != len(items):
            raise ValueError("analysis profile key/version pairs must be unique")
        self._profiles = by_version

    def resolve(self, key: str, version: str) -> AnalysisProfile:
        try:
            return self._profiles[(key, version)]
        except KeyError as exc:
            raise UnknownAnalysisProfile(f"Analysis profile {key!r} version {version!r} is not registered") from exc

    def list_profiles(self) -> tuple[AnalysisProfile, ...]:
        return tuple(self._profiles.values())


def default_profile_registry(config: Settings = settings) -> AnalysisProfileRegistry:
    quick_provider = config.analysis_quick_provider.strip().lower()
    deep_provider = config.analysis_deep_provider.strip().lower()
    quick_model = config.analysis_quick_model.strip() or config.groq_model
    deep_model = config.analysis_deep_model.strip() or config.groq_model
    common = {
        "version": "1",
        "quick_provider": quick_provider,
        "quick_model": quick_model,
        "deep_provider": deep_provider,
        "deep_model": deep_model,
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        "checkpoint_enabled": False,
        "save_html_report": True,
    }
    return AnalysisProfileRegistry(
        [
            AnalysisProfile(
                key="INTRADAY_RESEARCH",
                horizon=AnalysisHorizon.INTRADAY,
                selected_analysts=("market", "social", "news", "fundamentals"),
                **common,
            ),
            AnalysisProfile(
                key="SWING_RESEARCH",
                horizon=AnalysisHorizon.SWING,
                selected_analysts=("market", "social", "news", "fundamentals"),
                **common,
            ),
            AnalysisProfile(
                key="GENERAL_RESEARCH",
                horizon=AnalysisHorizon.RESEARCH,
                selected_analysts=("market", "news", "fundamentals"),
                **common,
            ),
        ]
    )
