# TradeX project setup

Python 3.11 or newer, and Node.js with npm. Two processes: the API on port 8000 and the desk on port 5173. DhanHQ account, token, and static IP setup is in [DhanHQ](#dhanhq) below.

## 1. Backend

From `backend`:

```text
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

On macOS or Linux, activate with `source .venv/bin/activate` and copy with `cp .env.example .env`.

Generate a Fernet key from the activated virtualenv and paste it into `CREDENTIALS_KEY`:

```text
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Replace `SESSION_SECRET` with a long random string. Set `ADMIN_PASSWORD`. Leave `TRADING_MODE=paper`.

Start the API:

```text
python main.py
```

The first start creates `backend/tradex.db`. If that file has no users, it creates the admin from `ADMIN_USERNAME` and `ADMIN_PASSWORD`. If accounts already exist, those two variables are ignored. Delete `tradex.db` and start again to recreate the first admin. Do not commit `.env` or `tradex.db`.

## 2. Frontend

From `frontend`:

```text
npm install
npm run dev
```

Open http://localhost:5173. The API reference is http://localhost:8000/docs.

Copy `frontend/.env.example` to `frontend/.env` only when the API is not on `http://localhost:8000`.

## 3. Checks

From `backend`, with the virtualenv active:

```text
python -m pytest tests -q
```

## Backend keys

`backend/app/config.py` loads these names from the environment and from `backend/.env`. Unknown names are ignored.

### Required before first start

| Name | Required | What to put |
| --- | --- | --- |
| `ADMIN_PASSWORD` | Yes, for the first admin | Password for `ADMIN_USERNAME`. Used only when `tradex.db` has no users. |
| `SESSION_SECRET` | Yes | Long random string. Signs the login cookie. The example default is for local development only. |
| `CREDENTIALS_KEY` | Yes, before saving Dhan tokens | Fernet key. Traders' Dhan client id and access token are encrypted with it. Empty means saving credentials fails. |

### Mode and login

| Name | Default | What to put |
| --- | --- | --- |
| `TRADING_MODE` | `paper` | `paper` fills inside this process. `live` sends orders through that trader's saved Dhan token. Restart after changing it. |
| `ADMIN_USERNAME` | `admin` | Login name for the first admin. |
| `APP_NAME` | `TradeX` | Process name. |
| `APP_ENV` | `development` | `production` refuses the default session secret, a missing `CREDENTIALS_KEY`, and `APP_DEBUG=true`. See [REPO.md](../REPO.md). |
| `APP_DEBUG` | `true` | `true` turns on reload. Production must set `false`. |

### Network and storage

| Name | Default | What to put |
| --- | --- | --- |
| `BACKEND_HOST` | `0.0.0.0` | API bind address. |
| `BACKEND_PORT` | `8000` | API port. |
| `API_VERSION_PREFIX` | `/api/v1` | Prefix for every route. |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | Browser origin allowed to send the login cookie. |
| `DATABASE_PATH` | `tradex.db` | SQLite file, created on startup. A relative path is resolved from the `backend` directory. |
| `PAPER_STARTING_BALANCE_INR` | `100000` | Starting paper cash, in INR. |
| `PAPER_LEDGER_PATH` | `paper_ledger.json` | Fallback paper ledger path. Per-user ledgers live under `PAPER_LEDGER_DIR`. |
| `PAPER_LEDGER_DIR` | `paper_ledgers` | One JSON ledger per user id. A relative path is resolved from the `backend` directory. |

### Market data, broker, and suggestions

| Name | Required | What to put |
| --- | --- | --- |
| `DHAN_CLIENT_ID` | For the security master when a trader token is absent | Process-level Dhan client id. Not a substitute for a trader's saved pair. |
| `DHAN_ACCESS_TOKEN` | Same as above | Process-level access token. It expires after 24 hours. The running process renews it, and renews each trader's saved token, before expiry. |
| `GROQ_API_KEY` | For suggestions only | Groq key. The model cannot place an order. |
| `GROQ_MODEL` | No | Default `llama-3.3-70b-versatile`. |

Order prices come from a Dhan quote. NSE public JSON supplies the holiday calendar, the index constituents, and the rank. Live order placement uses the token that trader saved on Settings. A missing trader token is refused. It is not filled from the process account.

### Risk limits (startup defaults)

An admin can change these from Settings. The change is stored in SQLite and reloaded on the next start. The values below are the defaults used until that happens.

| Name | Default |
| --- | --- |
| `MAX_POSITIONS` | `4` |
| `CAPITAL_PER_TRADE_PCT` | `0.20` |
| `CASH_RESERVE_PCT` | `0.10` |
| `TAKE_PROFIT_PCT` | `1.5` |
| `STOP_LOSS_PCT` | `1.0` |
| `MAX_DAILY_LOSS_INR` | `2000` |
| `CYCLE_INTERVAL_SECONDS` | `180` |
| `SCREENER_LIMIT` | `6` |

`CAPITAL_PER_TRADE_PCT` and `CASH_RESERVE_PCT` are fractions from 0 to 1. `TAKE_PROFIT_PCT` and `STOP_LOSS_PCT` are percents: `1.5` means 1.5 percent.

## Frontend key

| Name | Default | What to put |
| --- | --- | --- |
| `VITE_API_URL` | `http://localhost:8000` | API origin only. Do not append `/api/v1`. The client adds that prefix. |

## Names that are not read

Setting these does nothing. The code does not load them:

- `DATABASE_URL`
- `DHAN_APP_ID`
- `DHAN_APP_SECRET`
- `DHAN_PIN`
- `DHAN_TOTP_SECRET`

Use `DATABASE_PATH`, `DHAN_CLIENT_ID`, and `DHAN_ACCESS_TOKEN` instead.

## Roles

- **admin** creates and disables users and changes shared limits. An admin does not place orders.
- **trader** enables automation, types an intraday order, and executes or rejects their own pending list.
- **viewer** can read their own desk and log. They cannot enable automation, place an order, or approve one.

Sign in as the admin, create a trader from Users, then use that trader for orders.

## DhanHQ

TradeX uses [DhanHQ v2](https://dhanhq.co/docs/v2/authentication/). It needs two values from a Dhan account: the client id, and an access token generated on Dhan Web. That is the only login this process implements. An API key, API secret, PIN, or TOTP is not read. `DHAN_APP_ID`, `DHAN_APP_SECRET`, `DHAN_PIN`, and `DHAN_TOTP_SECRET` do nothing.

A token from the API-key consent flow cannot be renewed by this process. Generate the token on Dhan Web so [RenewToken](https://dhanhq.co/docs/v2/authentication/) applies.

### 1. On Dhan Web

1. Sign in at [web.dhan.co](https://web.dhan.co).
2. Open My Profile, then Access DhanHQ APIs. Dhan's support pages call the same screen Get Trading & Data APIs.
3. Copy the client id shown there. That is `dhanClientId`. It is not the UCC.
4. Generate an access token. Leave the postback URL empty. This desk polls order status. It does not receive postbacks. The token is valid for 24 hours.
5. Whitelist the public IP of the machine that will run `python main.py`. On that same page, add the IP and save. Dhan requires a static IP for placing, modifying, and cancelling orders. Quotes, funds, and order status do not. A home connection whose address changes will fail at the order, not at login. Each Dhan account needs its own IP, and Dhan will not let you change a saved IP for 7 days.

Trading APIs are included with a Dhan account. The 15-minute candles used to refine a rank are a Data API, which Dhan bills separately. With no candle data, the rank stays on the NSE percent-change snapshot. Order prices still come from a quote.

### 2. Two places the token can sit

Set `CREDENTIALS_KEY` before either save. The desk encrypts a trader token with that key. An empty key makes the Settings save fail.

| Where | Who | What it is allowed to do |
| --- | --- | --- |
| `DHAN_CLIENT_ID` and `DHAN_ACCESS_TOKEN` in `backend/.env` | The process | Download the security master when a trader has not saved a token yet. Restart after you change these. |
| Settings, Client id and Access token | That trader | Live funds, quotes, positions, holdings, and orders. A live order with no saved pair is refused. It is not sent on the process token. |

An admin has no Dhan form. Sign in as the trader, open Settings, paste the client id and the access token, and save. Saving again replaces the pair. The token is not shown back and is not written to the event log.

Paper mode still fills inside this process. With a token saved, those fills are priced from Dhan quotes. Live mode sends the order to that trader's Dhan account. `TRADING_MODE` changes only after a restart.

### 3. After it is saved

Leave the API process running. It calls RenewToken while the current token is still valid: in the last four hours of a token that carries an expiry, or 20 hours after a save when it does not. Dhan invalidates the old token when the new one is issued. The new value is stored encrypted.

Renewal does not run when the process is stopped, and it cannot revive a token that has already expired. Paste a new web token on Settings in that case.

Confirm the pair before `TRADING_MODE=live`. On the trader's desk, funds and positions should be that Dhan account's. A 400 on those calls means the pair was not saved. A 502 means Dhan rejected the call.

Orders this desk sends are NSE equity, product `INTRADAY` or `CNC`, as a market order. A live fill also parks a stop-market at Dhan. The static IP whitelist is what lets those order calls through.
