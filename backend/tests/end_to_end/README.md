# End-to-end tests

`test_paper_lifecycle.py` exercises the owner-scoped public paper APIs with the
real SQLAlchemy repositories and temporary SQLite/database files, the existing
`TradingGateway`/`PaperLedger`, a fake analysis provider, and a deterministic
market fixture. It covers idempotent workflow creation and advancement, a full
BUY/monitor/SELL lifecycle and realized P&L, stale quotes, insufficient cash,
partial fills, broker rejection, and an accepted paper fill recovered after a
service restart. It makes no Dhan order or paid LLM call.

Run from `backend/` with `python -m pytest tests/end_to_end -q`.
