"""Local, client-free NSE instrument resolution for manual candidates."""

from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from app.modules.stock_selection.schemas import InstrumentResolution
from app.shared.contracts import Instrument
from app.trading.nifty50 import NIFTY50_SYMBOLS


class InstrumentMasterError(RuntimeError):
    """The configured local instrument master cannot be safely interpreted."""


class AmbiguousInstrumentError(RuntimeError):
    """More than one broker instrument matches the requested NSE symbol."""


class InstrumentResolver(Protocol):
    """Resolve a canonical symbol without constructing a broker/provider client."""

    def resolve(self, symbol: str, exchange: str) -> InstrumentResolution | None:
        """Return a canonical mapping, or None when the symbol is unknown."""
        ...


class LocalNseInstrumentResolver:
    """Resolve from a local Dhan compact CSV, with the legacy NIFTY 50 fallback.

    The resolver performs no network calls. When a master is configured, it is
    authoritative for unknown symbols; the built-in fallback is used only when
    no file is configured/present. Fallback candidates have no Dhan ID and are
    therefore marked analysis-only by the service.
    """

    _REQUIRED_FIELDS = {
        "SEM_TRADING_SYMBOL",
        "SEM_SMST_SECURITY_ID",
        "SEM_EXM_EXCH_ID",
        "SEM_SEGMENT",
    }

    def __init__(self, master_path: str | Path | None = None):
        self._master_path = Path(master_path).expanduser() if master_path else None

    def resolve(self, symbol: str, exchange: str) -> InstrumentResolution | None:
        if exchange.upper() != "NSE":
            return None
        if self._master_path is not None and self._master_path.exists():
            return self._resolve_from_csv(symbol)
        if symbol not in NIFTY50_SYMBOLS:
            return None
        instrument = Instrument(
            symbol=symbol,
            exchange="NSE",
            trading_symbol=symbol,
            analysis_ticker=f"{symbol}.NS",
            security_id=None,
            segment="NSE_EQ",
            currency="INR",
        )
        return InstrumentResolution(
            instrument=instrument,
            mapping_source="LEGACY_NIFTY50_FALLBACK",
            resolved_at=_utc_now(),
        )

    def _resolve_from_csv(self, symbol: str) -> InstrumentResolution | None:
        assert self._master_path is not None
        try:
            with self._master_path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                fields = set(reader.fieldnames or [])
                missing = self._REQUIRED_FIELDS - fields
                if missing:
                    raise InstrumentMasterError(
                        "Instrument master is missing required columns: " + ", ".join(sorted(missing))
                    )
                matches: dict[tuple[str, str | None], None] = {}
                for row in reader:
                    if (row.get("SEM_EXM_EXCH_ID") or "").strip().upper() != "NSE":
                        continue
                    if (row.get("SEM_SEGMENT") or "").strip().upper() != "E":
                        continue
                    trading_symbol = (row.get("SEM_TRADING_SYMBOL") or "").strip().upper()
                    if trading_symbol != symbol:
                        continue
                    raw_id = (row.get("SEM_SMST_SECURITY_ID") or "").strip()
                    security_id = _normalize_security_id(raw_id)
                    matches[(trading_symbol, security_id)] = None
        except InstrumentMasterError:
            raise
        except (OSError, UnicodeError, csv.Error) as exc:
            raise InstrumentMasterError("Instrument master could not be read") from exc

        if not matches:
            return None
        if len(matches) > 1:
            raise AmbiguousInstrumentError(f"Multiple NSE equity mappings found for {symbol}")

        trading_symbol, security_id = next(iter(matches))
        instrument = Instrument(
            symbol=symbol,
            exchange="NSE",
            trading_symbol=trading_symbol,
            analysis_ticker=f"{trading_symbol}.NS",
            security_id=security_id,
            segment="NSE_EQ",
            currency="INR",
        )
        return InstrumentResolution(
            instrument=instrument,
            mapping_source=f"LOCAL_MASTER:{self._master_path.name}",
            resolved_at=_utc_now(),
        )


def _normalize_security_id(value: str) -> str | None:
    normalized = value.strip()
    if re.fullmatch(r"\d+\.0+", normalized):
        normalized = normalized.split(".", 1)[0]
    return normalized if re.fullmatch(r"\d+", normalized) else None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
