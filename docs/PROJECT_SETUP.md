# TradeX project setup

Python 3.11 or newer, and Node.js with npm. Two processes: the API on port 8000 and the desk on port 5173.

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
