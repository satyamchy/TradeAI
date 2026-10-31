import pytest

from app.modules.ai_analysis.profiles import AnalysisProfileRegistry, UnknownAnalysisProfile
from app.modules.ai_analysis.schemas import AnalysisProfile
from app.shared.contracts import AnalysisHorizon


def test_default_profiles_are_versioned_and_use_only_tagged_analysts():
    from app.modules.ai_analysis.profiles import default_profile_registry

    profile = default_profile_registry().resolve("INTRADAY_RESEARCH", "1")

    assert profile.horizon is AnalysisHorizon.INTRADAY
    assert profile.selected_analysts == ("market", "social", "news", "fundamentals")
    assert profile.quick_provider == "groq"
    assert profile.checkpoint_enabled is False


def test_registry_rejects_unknown_profile_and_unsupported_upstream_analyst():
    profile = AnalysisProfile(
        key="TEST",
        version="1",
        horizon=AnalysisHorizon.RESEARCH,
        selected_analysts=("market",),
        quick_provider="groq",
        quick_model="test-quick",
        deep_provider="groq",
        deep_model="test-deep",
    )
    registry = AnalysisProfileRegistry((item for item in [profile]))

    with pytest.raises(UnknownAnalysisProfile):
        registry.resolve("TEST", "2")
    with pytest.raises(ValueError, match="unsupported TradingAgents analyst"):
        AnalysisProfile(
            key="BAD",
            version="1",
            horizon=AnalysisHorizon.RESEARCH,
            selected_analysts=("technical",),
            quick_provider="groq",
            quick_model="test-quick",
            deep_provider="groq",
            deep_model="test-deep",
        )
