"""Simple trading tables used by the public trading APIs."""

from datetime import datetime
from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(50), index=True)
    security_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    side: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[int] = mapped_column(Integer)
    order_type: Mapped[str] = mapped_column(String(20), default="MARKET")
    product_type: Mapped[str] = mapped_column(String(20), default="INTRADAY")
    requested_price: Mapped[float] = mapped_column(Float, default=0.0)
    broker_order_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="PENDING")
    mode: Mapped[str] = mapped_column(String(20), default="PAPER")
    source: Mapped[str] = mapped_column(String(20), default="frontend")
    confirmation_id: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, index=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    symbol: Mapped[str] = mapped_column(String(50), index=True)
    side: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    product_type: Mapped[str] = mapped_column(String(20), default="INTRADAY")
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    security_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    product_type: Mapped[str] = mapped_column(String(20), default="INTRADAY")
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    average_price: Mapped[float] = mapped_column(Float, default=0.0)
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
