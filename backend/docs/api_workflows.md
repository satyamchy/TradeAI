# API workflows

The live reference is FastAPI at `/docs`, generated from the route docstrings. Paths below use the `/api/v1` prefix. See the [root README](../../README.md) for roles and [REPO.md](../../REPO.md) for production.

Every mutating route needs the login cookie. An admin does not place orders.

## Sign in

`POST /auth/login` sets the session cookie. `GET /auth/session` returns the account. Eight failed attempts for one name in a minute return 429.

## Orders

- `POST /orders/intraday` places that click, after the risk checks, at a fresh Dhan quote.
- `POST /orders/delivery` and `POST /suggestions` save a pending row. They do not call Dhan.
- `POST /orders/pending/{id}/execute` claims the row, re-quotes, and is the only path from that queue to the broker. A second click is rejected.
- `POST /orders/close` sells or covers one open product row. A delivery sell with no shares is rejected.
- `DELETE /orders/{order_id}` cancels a working live order. A paper fill is already done.

## Account

`GET /account/funds`, `/account/positions`, and `/account/orders` read that trader's book. Dhan credentials saved with `PUT /account/dhan-credentials` are used by existing account and quote integrations. This app build refuses startup in live mode, so these routes cannot place a live order.

The saved access token expires after 24 hours. The existing renewal service remains unchanged.

## Automation

`POST /automation/enable` turns on entries for `intraday_long`, `intraday_short`, or both, and can set the index. `POST /automation/square-off-open-positions` stops new entries and flattens open intraday positions while the NSE cash session is open. Delivery rows are left for their own stop or target.

Shared limits are `GET` and `PATCH /automation/settings`. An admin's patch is stored in SQLite.

## Module workflow paper trading

The module workflow API is paper-only. Startup refuses `TRADING_MODE=live` or
`LIVE_TRADING_ENABLED=true`; Module 4 also receives `live_execution_allowed=false`.
The API uses the existing per-user `TradingGateway` and paper ledger. It does
not accept prices, capital, positions, decisions, risk limits or order quantity
from the client.

1. `POST /paper/workflows` with `{"symbol":"RELIANCE"}` and an
   `Idempotency-Key` validates a Module 1 candidate and starts the Module 2
   background analysis. Reusing the key for the same symbol returns the same
   workflow; using it for a different symbol returns 409.
2. Poll `GET /paper/workflows/{analysis_id}` or the existing
   `GET /analysis/jobs/{analysis_id}`. When the analysis is `COMPLETED`, call
   `POST /paper/workflows/{analysis_id}/advance`. Module 3 evaluates its
   provider-neutral risk rules. Only a persisted `BUY_APPROVED` intent reaches
   Module 4, which validates it and submits through the paper gateway.
   Repeating this call reuses the persisted decision and idempotent order.
3. Read decisions with `GET /paper/decisions?analysis_id=...`, persisted orders
   with `GET /paper/orders`, and broker-confirmed paper positions with
   `GET /paper/positions`. `POST /paper/orders/{order_id}/reconcile` reconciles
   unknown or working outcomes without blind resubmission.
4. Request a deterministic stop, target or session reassessment with
   `POST /paper/positions/{symbol}/reassess`. Module 5 consumes the confirmed
   paper position, Module 3 must approve any sell intent, and Module 4 submits
   the paper sell. The workflow view reports realized P&L and final P&L after
   the confirmed position closes.

Analysis completion and entry advancement are separate API calls so the
asynchronous job status remains observable before a paper order is created.
Position reassessment is request-driven in this release; the existing harness
and automation runner remain the only scheduler path and do not automatically
advance these new API workflows.
