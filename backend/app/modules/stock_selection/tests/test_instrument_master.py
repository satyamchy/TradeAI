import pytest

from app.modules.stock_selection.instrument_master import (
    AmbiguousInstrumentError,
    InstrumentMasterError,
    LocalNseInstrumentResolver,
)


def test_local_master_maps_tradeai_yahoo_and_dhan_symbols_separately(tmp_path):
    master = tmp_path / "master.csv"
    master.write_text(
        "SEM_TRADING_SYMBOL,SEM_SMST_SECURITY_ID,SEM_EXM_EXCH_ID,SEM_SEGMENT\n"
        "FOO,1234.0,NSE,E\n"
        "FOO,1234,NSE,E\n"
        "BAR,7654,BSE,E\n",
        encoding="utf-8",
    )

    result = LocalNseInstrumentResolver(master).resolve("FOO", "NSE")

    assert result is not None
    assert result.instrument.symbol == "FOO"
    assert result.instrument.trading_symbol == "FOO"
    assert result.instrument.analysis_ticker == "FOO.NS"
    assert result.instrument.security_id == "1234"
    assert result.instrument.segment == "NSE_EQ"
    assert result.mapping_source == "LOCAL_MASTER:master.csv"
    assert result.resolved_at.tzinfo is not None
    assert LocalNseInstrumentResolver(master).resolve("BAR", "NSE") is None


def test_master_rejects_ambiguous_symbol_mappings(tmp_path):
    master = tmp_path / "master.csv"
    master.write_text(
        "SEM_TRADING_SYMBOL,SEM_SMST_SECURITY_ID,SEM_EXM_EXCH_ID,SEM_SEGMENT\n"
        "FOO,1234,NSE,E\nFOO,5678,NSE,E\n",
        encoding="utf-8",
    )

    with pytest.raises(AmbiguousInstrumentError):
        LocalNseInstrumentResolver(master).resolve("FOO", "NSE")


def test_malformed_master_fails_closed(tmp_path):
    master = tmp_path / "master.csv"
    master.write_text("symbol,id\nFOO,1234\n", encoding="utf-8")

    with pytest.raises(InstrumentMasterError):
        LocalNseInstrumentResolver(master).resolve("FOO", "NSE")


def test_builtin_universe_only_returns_analysis_only_mapping_when_master_is_absent(tmp_path):
    resolver = LocalNseInstrumentResolver(tmp_path / "missing.csv")

    result = resolver.resolve("RELIANCE", "NSE")

    assert result is not None
    assert result.instrument.analysis_ticker == "RELIANCE.NS"
    assert result.instrument.security_id is None
    assert resolver.resolve("UNKNOWN", "NSE") is None
