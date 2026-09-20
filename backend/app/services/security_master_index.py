"""
In-memory fuzzy-searchable index over the Dhan security master.
Built once on startup / on refresh_security_master(), never per-request.
"""

import logging
from dataclasses import dataclass
from typing import Optional

# from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SecurityRecord:
    symbol: str          # e.g. "TCS" (NSE trading symbol, no suffix)
    security_id: str     # Dhan's internal numeric/string ID
    exchange: str        # "NSE" / "BSE"
    segment: str         # "EQUITY" / "INDEX" / "ETF" / "DERIVATIVE" etc.
    display_name: str    # "Tata Consultancy Services Ltd"


class SecurityIndex:
    def __init__(self):
        self._records: list[SecurityRecord] = []
        self._name_to_idx: dict[str, int] = {}

    def is_ready(self) -> bool:
        return len(self._records) > 0

    def build(self, raw_rows: list[dict]) -> int:
        """
        raw_rows: rows from Dhan's get_security_master(), one dict per instrument.
        Adjust the key names below to match your actual Dhan CSV/column schema.
        """
        records: list[SecurityRecord] = []
        for row in raw_rows:
            try:
                # Only index cash-equity/index/ETF instruments for stock lookups —
                # skip derivatives/options rows or you'll match option contracts.
                segment = str(row.get("SEM_SEGMENT", "")).upper()
                if segment not in ("EQUITY", "INDEX", "ETF"):
                    continue

                records.append(SecurityRecord(
                    symbol=str(row["SEM_TRADING_SYMBOL"]).strip().upper(),
                    security_id=str(row["SEM_SMST_SECURITY_ID"]).strip(),
                    exchange=str(row.get("SEM_EXM_EXCH_ID", "NSE")).strip().upper(),
                    segment=segment,
                    display_name=str(row.get("SEM_CUSTOM_SYMBOL") or row["SEM_TRADING_SYMBOL"]).strip(),
                ))
            except KeyError as e:
                logger.debug("Skipping malformed security master row, missing %s", e)
                continue

        self._records = records
        self._name_to_idx = {r.display_name.lower(): i for i, r in enumerate(records)}
        logger.info("SecurityIndex built with %d instruments", len(records))
        return len(records)

    def exact_symbol(self, symbol: str) -> Optional[SecurityRecord]:
        target = symbol.strip().upper()
        for r in self._records:
            if r.symbol == target:
                return r
        return None

    def search(self, query: str, limit: int = 5) -> list[tuple[SecurityRecord, float]]:
        if not self._records:
            return []
        choices = {i: r.display_name for i, r in enumerate(self._records)}
        # also try matching against raw symbol for short queries like "TCS"
        symbol_choices = {i: r.symbol for i, r in enumerate(self._records)}

        name_matches = process.extract(query, choices, scorer=fuzz.WRatio, limit=limit)
        symbol_matches = process.extract(query, symbol_choices, scorer=fuzz.WRatio, limit=limit)

        best: dict[int, float] = {}
        for _, score, idx in name_matches + symbol_matches:
            best[idx] = max(best.get(idx, 0), score)

        ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        return [(self._records[idx], score) for idx, score in ranked]


# Module-level singleton — populated by refresh_security_master()
security_index = SecurityIndex()