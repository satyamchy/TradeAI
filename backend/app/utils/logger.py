import datetime
import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

from app.db.base import AsyncSessionLocal
from app.db.models import EventLog

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "agent.log")


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    # Terminal
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # File
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.propagate = False

    return logger


logger = get_logger("agent_event")


async def log_agent_event(
    agent_name: str,
    message: str,
    ticker: Optional[str] = None,
    status: str = "INFO",
):
    """
    Formats system runs with an active timestamp, target ticker, agent component,
    and statement block. Securely persists metadata inside the database 'event_logs' table
    within an isolated async session block.
    """
    timestamp = datetime.datetime.utcnow()
    ticker_display = ticker if ticker else "N/A"
    
    # Formatted statement block
    formatted_statement = (
        f"[{timestamp.isoformat()} UTC] AGENT: {agent_name} | "
        f"TICKER: {ticker_display} | STATUS: {status} | {message}"
    )

    # Print / File log
    if status.upper() in ("ERROR", "FAILED"):
        logger.error(formatted_statement)
    elif status.upper() == "WARNING":
        logger.warning(formatted_statement)
    else:
        logger.info(formatted_statement)

    # Isolated async session block inside database
    try:
        async with AsyncSessionLocal() as session:
            log_entry = EventLog(
                timestamp=timestamp,
                agent_name=agent_name,
                ticker=ticker,
                status=status,
                message=message,
            )
            session.add(log_entry)
            await session.commit()
    except Exception as exc:
        logger.warning("FAILED_TO_PERSIST_EVENT_LOG | error=%s", exc)
