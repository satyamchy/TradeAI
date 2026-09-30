# TradeX

NSE desk for the NIFTY 50. The rules loop trades intraday only. A delivery order or a model suggestion stays on the pending list until that trader presses Execute.

## Run

From `backend`:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python main.py
```

From `frontend`:

```
npm install
npm run dev
```

The desk is at http://localhost:5173. The API is at http://localhost:8000. OpenAPI, built from the route docstrings, is at http://localhost:8000/docs.

## Environment

Set these in `backend/.env`.

| Name | Meaning |
| --- | --- |
| `TRADING_MODE` | `paper` or `live`. Paper is the default and never sends an order to the exchange. Live is fixed when the process starts. Enabling automation does not change it. |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | The first admin, created only when the user table is empty. There is no public signup. |
| `SESSION_SECRET` | Signs the login cookie. |
| `CREDENTIALS_KEY` | Fernet key. Dhan client id and access token are encrypted with it. A hash cannot be sent to Dhan, so these are not hashed. |
| `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN` | Optional process-level login for market data. Each trader saves their own pair on the settings screen. |
| `GROQ_API_KEY` | Used only to pick a symbol and a side from the screener list. Quantity and price are computed here. |
| `FRONTEND_ORIGIN` | Browser origin allowed to send the cookie. Default `http://localhost:5173`. |

Generate a key with:

```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Roles

- **admin** creates and disables users, changes the shared limits, and can read another user's event log. An admin does not place orders on someone else's Dhan account.
- **trader** uses their own account: automation, a typed intraday order, and Execute or Reject on their own pending list.
- **viewer** can read their own desk and their own log. They cannot enable automation, place an order, or approve one.

## Pending orders

`POST /api/v1/suggestions` and `POST /api/v1/orders/delivery` save a row. They do not call Dhan. `POST /api/v1/orders/pending/{id}/execute` is the only path from that queue to the broker, and only the trader who owns the row can press it. A typed `POST /api/v1/orders/intraday` places on that click, because that click is the person, and it still passes the risk checks.

The model may return only a symbol and a side from the names just handed to it. Any other reply is dropped.

## Event log

Mutating actions are written to `backend/tradex.db` (gitignored). `GET /api/v1/events` returns the logged-in user's rows. An admin can pass `user_id` to read another account. The Dhan token is never stored in the log.
