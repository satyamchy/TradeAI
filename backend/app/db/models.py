import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from app.db.base import Base


class ActivePosition(Base):
    __tablename__ = "active_positions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ticker = Column(String(50), index=True, nullable=False)
    symbol = Column(String(50), nullable=True)
    current_price = Column(Float, nullable=True)
    target_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    recommendation = Column(String(30), default="HOLD")
    status = Column(String(30), default="OPEN", index=True)  # OPEN, CLOSED, EVALUATED
    evaluation_reason = Column(Text, nullable=True)
    last_evaluated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class EventLog(Base):
    __tablename__ = "event_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    agent_name = Column(String(100), index=True, nullable=False)
    ticker = Column(String(50), index=True, nullable=True)
    status = Column(String(50), nullable=False, default="INFO")
    message = Column(Text, nullable=False)


# Alias AgentLog to EventLog for full backward compatibility
AgentLog = EventLog
