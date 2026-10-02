# Deploy TradeX

One host, one API process, HTTPS in front. The automation loop, the 15:15 IST flatten, and the Dhan token renewal all run inside that process. If it is down, none of those run.

The GitHub remote is [github.com/satyamchy/TradeAI](https://github.com/satyamchy/TradeAI). Local setup is in [docs/PROJECT_SETUP.md](docs/PROJECT_SETUP.md). Do not commit `backend/.env`, `tradex.db`, or `paper_ledgers/`.

## What production mode checks

Set these in `backend/.env` before the process starts. `APP_ENV=production` refuses to boot when any of the first three are wrong.

| Name | Production value |
| --- | --- |
| `APP_ENV` | `production` |
| `APP_DEBUG` | `false` |
| `SESSION_SECRET` | A long random string. The example default is rejected. |
| `CREDENTIALS_KEY` | A Fernet key. Required. |
| `ADMIN_PASSWORD` | Set before the first boot, when `tradex.db` has no users. |
| `TRADING_MODE` | `paper` until a trader's own Dhan token is saved and you intend to send orders. Then `live`, and restart. |
| `FRONTEND_ORIGIN` | The public desk origin, for example `https://desk.example.com`. The login cookie is HTTPS-only in production. |
| `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN` | Process token for the security master. Live orders still use the token saved on Settings. |

`CAPITAL_PER_TRADE_PCT` and `CASH_RESERVE_PCT` are fractions (`0.20`). `TAKE_PROFIT_PCT` and `STOP_LOSS_PCT` are percents (`1.5`). An admin can change the shared limits from Settings. Those edits are stored in SQLite and survive a restart.

Generate the Fernet key on the server:

```text
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Build the desk

`VITE_API_URL` is baked in at build time. Do not append `/api/v1`.

```text
cd frontend
npm ci
# set VITE_API_URL=https://api.example.com in the environment for this command
npm run build
```

Serve the `frontend/dist` directory from the same site named in `FRONTEND_ORIGIN`. The API stays on its own origin. Point the desk's requests at that API origin.

## Run one API process

From `backend`, with the virtualenv active:

```text
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Do not pass `--reload`. Do not run more than one worker. SQLite, the per-user order lock, and the automation loop are local to this process. A second worker will double-send orders.

Put TLS on a reverse proxy. Proxy `/api/` and `/docs` to `127.0.0.1:8000`. Leave the API bound to localhost when the proxy is on the same machine.

A systemd unit is enough:

```text
[Service]
WorkingDirectory=/opt/tradex/backend
EnvironmentFile=/opt/tradex/backend/.env
ExecStart=/opt/tradex/backend/.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
```

`Restart=always` matters. Dhan access tokens expire after 24 hours. This process renews a still-valid token in the last four hours of its life and writes the new ciphertext to `tradex.db`. If the process is stopped through that window, the token is dead and the trader must paste a new one on Settings.

The same process flattens intraday positions from 15:15 IST while the NSE cash session is open. Keep the host clock correct. The session clock is `Asia/Kolkata`, not the server's local zone.

## Before the first live session

1. Boot once in `paper` and sign in as the admin created from `ADMIN_PASSWORD`.
2. Create a trader. An admin cannot place orders.
3. On that trader, save the Dhan client id and a token generated on Dhan Web. Whitelist this host's static IP on that Dhan account first. The steps are in [docs/PROJECT_SETUP.md](docs/PROJECT_SETUP.md). Live orders refuse to run without that pair.
4. Set a small daily-loss cap on Settings.
5. Switch `TRADING_MODE=live` and restart the one API process.
6. Confirm the desk shows a live banner, cash, and positions from that Dhan account.

NSE public data supplies the holiday calendar and the selected index. If the holiday list cannot be loaded, new entries stay off. Exits still run. Order prices come from Dhan quotes, not from NSE.

Dhan's own algo and static-IP rules apply to a live API strategy. Confirm the current Dhan requirements before sending real orders. This repository does not register an algo id for you.

## Backups

Copy `backend/tradex.db` and `backend/paper_ledgers/` while the process is stopped, or use SQLite's online backup. Losing the database loses users, the encrypted Dhan tokens, and the renewal clock. Losing a paper ledger loses that trader's simulated book. Live positions still sit at Dhan.

## What not to do

- Do not commit `.env` or print the Dhan token, `SESSION_SECRET`, or `CREDENTIALS_KEY`.
- Do not point two hosts at one SQLite file.
- Do not turn on `APP_DEBUG` in production. The process will refuse to start.
- Do not expect a token to renew after it has already expired. Paste a new one on Settings.
