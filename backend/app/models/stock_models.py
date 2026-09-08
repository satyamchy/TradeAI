import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON, Boolean
from app.database import Base


class StockAnalysisSnapshot(Base):
    __tablename__ = "stock_analysis_snapshots"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ticker = Column(String(50), index=True, nullable=False)
    symbol = Column(String(50), index=True, nullable=False)
    name = Column(String(100), nullable=True)
    analysis_date = Column(String(10), index=True, nullable=False) # YYYY-MM-DD
    initial_price = Column(Float, nullable=False, default=0.0)
    target_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    currency = Column(String(10), default="INR")
    overall_sentiment = Column(String(30), default="Neutral") # Bullish, Bearish, Neutral
    intraday_bias = Column(String(30), default="Neutral")
    recommendation = Column(String(30), default="HOLD") # BUY, SELL, HOLD
    technical_score = Column(Float, nullable=True, default=50.0)
    macro_score = Column(Float, nullable=True, default=50.0)
    ai_reasoning = Column(Text, nullable=True)
    structured_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class StockTradeLog(Base):
    __tablename__ = "stock_trade_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    trade_date = Column(String(10), index=True, nullable=False) # YYYY-MM-DD
    trade_time = Column(String(8), nullable=True) # HH:MM:SS
    symbol = Column(String(50), index=True, nullable=False) # e.g. RELIANCE.NS, GOLDBEES.NS
    trade_type = Column(String(10), nullable=False) # BUY / SELL
    product_type = Column(String(15), default="INTRADAY") # INTRADAY (MIS) / DELIVERY (CNC)
    asset_category = Column(String(20), default="STOCK") # STOCK / GOLD / SILVER
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=True)
    target_price = Column(Float, nullable=True)
    brokerage = Column(Float, default=0.0)
    realized_pnl = Column(Float, default=0.0)
    dhan_order_id = Column(String(100), nullable=True)
    status = Column(String(30), default="EXECUTED") # EXECUTED, OPEN, SQUARED_OFF, CANCELLED
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class TradingGuardrailSettings(Base):
    __tablename__ = "trading_guardrail_settings"

    id = Column(Integer, primary_key=True, default=1)
    is_trading_enabled = Column(Boolean, default=False)
    paper_trading_mode = Column(Boolean, default=True)
    max_order_value_inr = Column(Float, default=100000.0)
    max_daily_loss_inr = Column(Float, default=25000.0)
    auto_intraday_exit_time = Column(String(5), default="15:15") # 15:15 IST
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)


class GlobalMacroNews(Base):
    __tablename__ = "global_macro_news"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    source = Column(String(100), nullable=True)
    region = Column(String(50), default="Global") # Global, US, India, Asia
    sentiment = Column(String(20), default="Neutral") # Positive, Negative, Neutral
    impact_score = Column(Float, default=0.0) # -10 to +10
    summary = Column(Text, nullable=True)
    published_at = Column(DateTime, default=datetime.datetime.utcnow)


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(100), nullable=False)
    job_type = Column(String(20), default="CRON") # NORMAL / CRON
    tickers = Column(String(255), nullable=False) # comma-separated symbols
    cron_expression = Column(String(50), default="15 9 * * 1-5") # e.g. 9:15 AM Mon-Fri
    market_hours_only = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class JobExecutionLog(Base):
    __tablename__ = "job_execution_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    job_id = Column(Integer, index=True, nullable=False)
    status = Column(String(20), default="SUCCESS") # SUCCESS / FAILED / IN_PROGRESS
    message = Column(Text, nullable=True)
    executed_at = Column(DateTime, default=datetime.datetime.utcnow)
