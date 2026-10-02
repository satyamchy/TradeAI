"""NSE's public JSON, cached on disk.

This module reads the holiday calendar, index constituents, and the index
snapshot used to rank names. It does not size or place orders. A price that
an order uses comes from Dhan.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import httpx

from app.trading.nifty50 import INDEX_CHOICES, NIFTY50_SYMBOLS, canonical_index
from app.trading.nse_session import now_ist, set_holidays
from app.utils.logger import get_logger

logger = get_logger(__name__)
_MEMO: dict[str, tuple[float, object]] = {}
_MEMO_SECONDS = 120.0


def _memo_get(key: str):
    hit = _MEMO.get(key)
    if hit and time.time() - hit[0] < _MEMO_SECONDS:
        return hit[1]
    return None


def _memo_put(key: str, value: object) -> None:
    _MEMO[key] = (time.time(), value)

_HOME = "https://www.nseindia.com"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def _cache_dir() -> Path:
    path = Path(__file__).resolve().parents[2] / "data" / "nse"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_cache(name: str) -> dict | list | None:
    file = _cache_dir() / name
    if not file.exists():
        return None
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(name: str, payload: dict | list) -> None:
    file = _cache_dir() / name
    file.write_text(json.dumps(payload), encoding="utf-8")


async def _get_json(path: str) -> dict | list:
    async with httpx.AsyncClient(timeout=20, headers=_HEADERS, follow_redirects=True) as client:
        await client.get(_HOME)
        response = await client.get(_HOME + path)
        response.raise_for_status()
        return response.json()


async def load_holidays() -> set[str]:
    """CM holiday dates as YYYY-MM-DD. A failed load blocks new entries."""
    try:
        payload = await _get_json("/api/holiday-master")
        dates = _holiday_dates(payload)
        if not dates:
            raise ValueError("NSE holiday list was empty")
        _write_cache("holidays.json", {"dates": sorted(dates)})
        set_holidays(dates, "loaded")
        return dates
    except Exception as exc:
        cached = _read_cache("holidays.json")
        if isinstance(cached, dict) and cached.get("dates"):
            dates = set(cached["dates"])
            set_holidays(dates, "loaded")
            logger.warning("NSE holiday fetch failed, using the cache: %s", exc)
            return dates
        set_holidays(set(), "failed")
        logger.warning("NSE holiday list is unavailable, new entries are blocked: %s", exc)
        return set()


def _holiday_dates(payload: dict | list) -> set[str]:
    rows: list = []
    if isinstance(payload, dict):
        cm = payload.get("CM") or payload.get("cm") or []
        if isinstance(cm, list):
            rows = cm
        elif isinstance(cm, dict):
            rows = list(cm.values())
    elif isinstance(payload, list):
        rows = payload
    dates: set[str] = set()
    for row in rows:
        if isinstance(row, str):
            parsed = _parse_date(row)
        elif isinstance(row, dict):
            parsed = _parse_date(
                str(row.get("tradingDate") or row.get("trading_date") or row.get("date") or "")
            )
        else:
            parsed = None
        if parsed:
            dates.add(parsed)
    return dates


def _parse_date(text: str) -> str | None:
    raw = text.strip()
    if not raw:
        return None
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


async def constituents(index_name: str) -> list[str]:
    """Trading symbols in one selectable index. NIFTY 50 falls back to the built-in list."""
    index_name = canonical_index(index_name)
    remembered = _memo_get(f"names:{index_name}")
    if remembered is not None:
        return list(remembered)
    query = INDEX_CHOICES[index_name]
    cache_name = f"constituents-{index_name.replace(' ', '_')}.json"
    try:
        payload = await _get_json("/api/equity-stockIndices?index=" + query.replace(" ", "%20"))
        symbols = _symbols_from_snapshot(payload, index_name)
        if symbols:
            _write_cache(cache_name, {"symbols": symbols})
            _memo_put(f"names:{index_name}", symbols)
            return symbols
        raise ValueError("empty constituent list")
    except Exception as exc:
        cached = _read_cache(cache_name)
        if isinstance(cached, dict) and cached.get("symbols"):
            logger.warning("NSE constituents failed for %s, using cache: %s", index_name, exc)
            _memo_put(f"names:{index_name}", list(cached["symbols"]))
            return list(cached["symbols"])
        if index_name == "NIFTY 50":
            logger.warning("NSE constituents failed, using the built-in NIFTY 50 list: %s", exc)
            _memo_put(f"names:{index_name}", list(NIFTY50_SYMBOLS))
            return list(NIFTY50_SYMBOLS)
        logger.warning("NSE constituents failed for %s and there is no fallback: %s", index_name, exc)
        return []


async def snapshot(index_name: str) -> list[dict]:
    """One row per constituent: symbol, ltp, and percent change. Not an order price."""
    index_name = canonical_index(index_name)
    remembered = _memo_get(f"snap:{index_name}")
    if remembered is not None:
        return list(remembered)
    query = INDEX_CHOICES[index_name]
    try:
        payload = await _get_json("/api/equity-stockIndices?index=" + query.replace(" ", "%20"))
    except Exception as exc:
        logger.warning("NSE snapshot failed for %s: %s", index_name, exc)
        symbols = await constituents(index_name)
        return [{"symbol": symbol, "ltp": 0.0, "percent_change": 0.0} for symbol in symbols]
    rows = []
    for item in _data_rows(payload):
        symbol = str(item.get("symbol") or "").upper().strip()
        if not symbol or symbol == index_name.upper() or " " in symbol:
            continue
        last = float(item.get("lastPrice") or item.get("last") or 0)
        change = float(item.get("pChange") or item.get("percentChange") or 0)
        rows.append({"symbol": symbol, "ltp": last, "percent_change": change})
    if rows:
        _write_cache(
            f"constituents-{index_name.replace(' ', '_')}.json",
            {"symbols": [row["symbol"] for row in rows]},
        )
        _memo_put(f"snap:{index_name}", rows)
        _memo_put(f"names:{index_name}", [row["symbol"] for row in rows])
    return rows


def _symbols_from_snapshot(payload: dict | list, index_name: str) -> list[str]:
    symbols = []
    for item in _data_rows(payload):
        symbol = str(item.get("symbol") or "").upper().strip()
        if symbol and symbol != index_name.upper() and " " not in symbol:
            symbols.append(symbol)
    return symbols


def _data_rows(payload: dict | list) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
    return []


def cache_is_from_today() -> bool:
    """True when a holiday cache file was written today. Informational."""
    file = _cache_dir() / "holidays.json"
    if not file.exists():
        return False
    written = datetime.fromtimestamp(file.stat().st_mtime, tz=now_ist().tzinfo)
    return written.date() == now_ist().date()
