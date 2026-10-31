import importlib
from pathlib import Path
import sys


MODULES = (
    "stock_selection",
    "ai_analysis",
    "decision_engine",
    "execution",
    "position_monitoring",
)


def test_all_five_public_packages_import_without_external_clients():
    from app.broker import dhan_gateway

    for name in MODULES:
        package = importlib.import_module(f"app.modules.{name}")
        schemas = importlib.import_module(f"app.modules.{name}.schemas")
        service = importlib.import_module(f"app.modules.{name}.service")
        assert package is not None
        assert schemas is not None
        assert service is not None

    assert dhan_gateway._sdk_client.cache_info().currsize == 0
    assert not any(name == "tradingagents" or name.startswith("tradingagents.") for name in sys.modules)


def test_every_module_has_required_scaffold_files():
    modules_root = Path(__file__).resolve().parents[2] / "app" / "modules"
    for name in MODULES:
        package = modules_root / name
        for required in ("__init__.py", "README.md", "schemas.py", "service.py", "tests"):
            assert (package / required).exists(), f"{package / required} is missing"


def test_harness_exposes_the_existing_single_runner_and_database_path_is_shared():
    from pathlib import Path

    from app import db
    from app.harness import get_automation_runner
    from app.shared.database import database_url
    from app.trading.automation_runner import automation_runner

    assert get_automation_runner() is automation_runner
    assert Path(database_url(db._db_path()).database).resolve() == Path(db._db_path()).resolve()
