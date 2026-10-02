# TradeX

NSE cash desk. A trader picks an index and the loop trades that list. A delivery order or a model suggestion stays on the pending list until that trader presses Execute.

> **Start and sign in**
>
> Backend, from `backend`: `.venv\Scripts\activate` then `python main.py`
>
> Frontend, from `frontend`: `npm run dev`
>
> Desk: http://localhost:5173
>
> The first admin comes from `ADMIN_USERNAME` and `ADMIN_PASSWORD` in `backend/.env`.

Local setup: [docs/PROJECT_SETUP.md](docs/PROJECT_SETUP.md). Production: [REPO.md](REPO.md).

## Project setup

You need Python 3.11 or newer, and Node.js with npm. Two processes run at once: the API on port 8000 and the desk on port 5173.

### 1. Backend

From `backend`:

```text
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

On macOS or Linux, activate with `source .venv/bin/activate` and copy the example with `cp .env.example .env`.

Open `backend/.env` and set these before the first start:

| Name | What to put |
| --- | --- |
| `ADMIN_USERNAME` | Login name for the first admin. Default `admin`. |
| `ADMIN_PASSWORD` | Password for that admin. Required. The account is created only when `tradex.db` has no users. There is no public signup. |
| `SESSION_SECRET` | A long random string. It signs the login cookie. |
| `CREDENTIALS_KEY` | A Fernet key. Traders save a Dhan client id and access token from Settings. Those values are encrypted with this key. |
| `TRADING_MODE` | `paper` until you intend to send orders to the exchange. |

Generate the Fernet key from the activated virtualenv:

```text
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the printed line into `CREDENTIALS_KEY`. Do not commit `.env`.

Optional:

| Name | What to put |
| --- | --- |
| `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN` | Process-level Dhan login for the security master. Each trader still saves their own pair. Live orders refuse to run without that pair. |
| `GROQ_API_KEY` | Suggestions only. The model may return a symbol and a side from the screener list. It cannot place an order. |
| `FRONTEND_ORIGIN` | Browser origin that may send the cookie. Leave `http://localhost:5173` for local development. |
| `PAPER_STARTING_BALANCE_INR` | Starting paper cash. Default `100000`. |

Start the API:

```text
python main.py
```

The first start creates `backend/tradex.db` and, if that file has no users, the admin from `ADMIN_USERNAME` and `ADMIN_PASSWORD`. If the database already has accounts, those two variables are ignored. Delete `tradex.db` and start again to recreate the first admin. The file is gitignored. Relative database and ledger paths are resolved from the `backend` directory.

### 2. Frontend

From `frontend`, in a second terminal:

```text
npm install
npm run dev
```

The client calls `http://localhost:8000` unless `frontend/.env` sets `VITE_API_URL`. Copy `frontend/.env.example` to `frontend/.env` only if the API is somewhere else. Do not append `/api/v1`.

### 3. Open the desk

- Desk: http://localhost:5173
- API: http://localhost:8000
- API reference: http://localhost:8000/docs

Sign in as the admin. Create a trader from Users. An admin does not place orders. The trader signs in, saves Dhan credentials on Settings if they will trade live, and uses Orders.

### Paper and live

`TRADING_MODE=paper` fills orders inside this process. Prices still come from Dhan when a token is configured. `TRADING_MODE=live` sends orders with that trader's saved Dhan token. The mode is fixed when the process starts. Enabling automation does not switch paper to live. Change the variable, then restart `python main.py`.

A Dhan access token expires after 24 hours. While this process is running it renews the saved token before expiry. If the process is stopped until the token is already dead, paste a new one on Settings.

### Checks

From `backend`, with the virtualenv active:

```text
python -m pytest tests -q
```

## Roles

- **admin** creates and disables users, changes the shared limits, and can read another user's event log. An admin does not place orders. Disabling the last admin is refused. Disabling a trader leaves open intraday positions in the exit loop until they are flat.
- **trader** uses their own account: automation, a typed intraday order, Close on an open row, and Execute or Reject on their own pending list.
- **viewer** can read their own desk and their own log. They cannot enable automation, place an order, or approve one.

## What gets traded

The desk index is NIFTY 50, NIFTY BANK, NIFTY NEXT 50, NIFTY FINANCIAL SERVICES, or NIFTY MIDCAP 50. NSE public data supplies the holiday calendar, the constituents, and the rank. A Dhan quote is the price that sizes and marks an order. The built-in NIFTY 50 list is only the fallback when NSE does not answer.

Intraday positions flatten at 15:15 IST, on the stop, or on the target. A live entry also parks a stop-market at Dhan. Delivery positions are closed on the stop or the target, not by the clock. A delivery sell with no shares is rejected.

## Pending orders

`POST /api/v1/suggestions` and `POST /api/v1/orders/delivery` save a row. They do not call Dhan. `POST /api/v1/orders/pending/{id}/execute` claims that row and is the only path from the queue to the broker. A second click is rejected. A typed `POST /api/v1/orders/intraday` places on that click and still passes the risk checks. `POST /api/v1/orders/close` closes one open product row.

The model may return only a symbol and a side from the names just handed to it. Any other reply is dropped.

## Event log

Mutating actions are written to `backend/tradex.db` (gitignored). `GET /api/v1/events` returns the logged-in user's rows. An admin can pass `user_id` to read another account. The Dhan token is never stored in the log.
