---
name: tradex
description: >-
  Set up, configure, and change the TradeX NSE desk. Use when the user asks
  how to run TradeX, which environment variables or API keys are required,
  how paper and live trading differ, how to deploy, or where auth, orders,
  Dhan, or Groq settings live.
---

# TradeX

NSE cash desk. The trader picks an index (NIFTY 50, NIFTY BANK, NIFTY NEXT 50, NIFTY FINANCIAL SERVICES, or NIFTY MIDCAP 50). Backend is FastAPI on port 8000. Frontend is Vite on port 5173. State is SQLite plus per-user paper ledger JSON. There is no Redis, no migration tool, and no public signup.

## Setup

Follow [docs/PROJECT_SETUP.md](../../../docs/PROJECT_SETUP.md) for a local run. Follow [REPO.md](../../../REPO.md) for a production host. Copy `backend/.env.example` to `backend/.env`. Do not commit `.env`. Do not print secret values from `.env`.

Keys the process actually reads are the fields on `Settings` in `backend/app/config.py`. These names are ignored if present: `DATABASE_URL`, `DHAN_APP_ID`, `DHAN_APP_SECRET`, `DHAN_PIN`, `DHAN_TOTP_SECRET`.

Before the first start, set `ADMIN_PASSWORD`, replace `SESSION_SECRET`, and set `CREDENTIALS_KEY` if traders will save Dhan tokens. Leave `TRADING_MODE=paper` unless the user explicitly wants orders sent to Dhan. `APP_ENV=production` refuses the default session secret, a missing `CREDENTIALS_KEY`, and `APP_DEBUG=true`.

Relative `DATABASE_PATH` and `PAPER_LEDGER_DIR` are resolved from the `backend` directory, not from the shell's current directory.

## Run

From `backend`, with the virtualenv active: `python main.py`.

From `frontend`: `npm run dev`.

Desk: http://localhost:5173. API reference: http://localhost:8000/docs.

Checks, from `backend`: `python -m pytest tests -q`.

## Rules that are easy to get wrong

- `TRADING_MODE` is fixed for the life of the process. Changing it requires a restart. Enabling automation does not switch paper to live.
- An admin does not place orders. Only a trader can. A delivery request and a model suggestion stay pending until that trader calls execute. A typed intraday order is sent on that request. One pending row can be claimed once.
- Live funds, quotes, positions, holdings, and orders use the trader's own Dhan pair from Settings. The process-level `DHAN_CLIENT_ID` and `DHAN_ACCESS_TOKEN` are a fallback for the security master only. A live order is refused when that trader has no saved token.
- A Dhan access token expires after 24 hours. While the process is running, `backend/app/broker/dhan_token.py` renews it before expiry and stores the new ciphertext. A stopped process cannot renew a dead token.
- Order prices come from the Dhan quote. NSE public JSON supplies the holiday calendar, the index constituents, and the rank. yfinance is not on the order path.
- Intraday positions are flattened at 15:15 IST, on the stop, or on the target. Delivery positions are closed on the stop or the target, not by the clock. A live entry parks a stop-market at Dhan.
- `GROQ_API_KEY` is suggestions only. The model may return a symbol and a side from the screener list. Quantity and price come from the risk limits and a fresh quote. The model cannot place an order.
- The first admin is created only when `tradex.db` has no users. If accounts already exist, `ADMIN_USERNAME` and `ADMIN_PASSWORD` are ignored.
- Run one API process. SQLite, the paper ledger lock, and the automation loop are in that process.

## Where to change things

| Area | Location |
| --- | --- |
| Settings | `backend/app/config.py`, `backend/.env` |
| Routes | `backend/app/api/` |
| Orders and pending queue | `backend/app/api/manual_orders.py`, `backend/app/trading/pending.py` |
| Paper vs live | `backend/app/broker/trading_gateway.py` |
| Dhan quotes, holdings, order status | `backend/app/broker/dhan_gateway.py` |
| Token renewal | `backend/app/broker/dhan_token.py` |
| NSE holidays and index lists | `backend/app/market/nse_public.py` |
| Risk limits | `backend/app/trading/risk_limits.py` |
| Suggestions | `backend/app/trading/suggestions.py` |
| Frontend API client | `frontend/src/api/stockApi.js` |
| Production deploy | `REPO.md` |
