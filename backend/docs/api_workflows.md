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

`GET /account/funds`, `/account/positions`, and `/account/orders` read that trader's book. In live mode they use the Dhan token saved with `PUT /account/dhan-credentials`. A missing token is 400, not a trade on the process account.

The saved access token expires after 24 hours. The running process renews it before expiry.

## Automation

`POST /automation/enable` turns on entries for `intraday_long`, `intraday_short`, or both, and can set the index. `POST /automation/square-off-open-positions` stops new entries and flattens open intraday positions while the NSE cash session is open. Delivery rows are left for their own stop or target.

Shared limits are `GET` and `PATCH /automation/settings`. An admin's patch is stored in SQLite.
