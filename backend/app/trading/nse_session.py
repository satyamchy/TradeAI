"""NSE cash-session clock, in Asia/Kolkata.

Owns three questions: is the regular session open, are new entries still
allowed, and must open intraday positions be flattened. This module does
not call the broker.
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# Regular NSE cash session. Entries and exits are both allowed in this window.
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)

# New entries stop here so a position is not opened in the last minutes of the session.
ENTRY_CUTOFF = time(14, 45)

# MIS positions must be flat before the exchange's own square-off. 15:15 leaves a buffer.
SQUARE_OFF = time(15, 15)


def now_ist() -> datetime:
    """Current time in India Standard Time."""
    return datetime.now(IST)


def _moment(moment: datetime | None) -> datetime:
    return moment if moment is not None else now_ist()


def is_nse_cash_session_open(moment: datetime | None = None) -> bool:
    """True from 09:15 to 15:30 IST, Monday to Friday.

    `moment` is a timezone-aware datetime. Naive values are treated as IST.
    """
    current = _as_ist(_moment(moment))
    if current.weekday() >= 5:
        return False
    return SESSION_OPEN <= current.time() <= SESSION_CLOSE


def is_past_entry_cutoff(moment: datetime | None = None) -> bool:
    """True at or after 14:45 IST on a weekday.

    Exits still run after this time. New entries do not.
    """
    current = _as_ist(_moment(moment))
    if current.weekday() >= 5:
        return False
    return current.time() >= ENTRY_CUTOFF


def is_square_off_time(moment: datetime | None = None) -> bool:
    """True at or after 15:15 IST on a weekday, through the session close.

    After the session close this returns False. The runner is asleep then.
    A manual square-off request does not consult this function.
    """
    current = _as_ist(_moment(moment))
    if current.weekday() >= 5:
        return False
    return SQUARE_OFF <= current.time() <= SESSION_CLOSE


def _as_ist(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=IST)
    return moment.astimezone(IST)
