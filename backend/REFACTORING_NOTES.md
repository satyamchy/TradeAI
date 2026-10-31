# Where an order goes

The old service layout (`app/services/dhan_service.py`, `app/api/trading_routes.py`) is gone. The current frontend still uses the guarded compatibility routes while module workflows are introduced. The single FastAPI app also exposes the Module 1 and Module 2 APIs; Modules 3–5 and their workflows have integration coverage but do not replace the public order routes yet.

```text
Desk
  -> FastAPI route in backend/app/api/
  -> compatibility adapter and pending claim or intraday handler
  -> TradingGateway
       -> paper ledger, or
       -> DhanHQ SDK for a live order
```

Module 4 wraps the same `TradingGateway`; it does not create a second broker client, order path, or paper ledger. Cross-module orchestration belongs under `backend/app/workflows/`, and the existing automation runner is exposed through `backend/app/harness/`.

Live quotes, funds, positions, holdings, and orders use the trader token saved on Settings. `backend/app/broker/dhan_gateway.py` is the only module that imports the SDK. `backend/app/broker/dhan_token.py` renews that token before the 24-hour expiry.

NSE public JSON in `backend/app/market/nse_public.py` supplies holidays, constituents, and the rank. It does not price an order.

One process only. See [REPO.md](../REPO.md).
