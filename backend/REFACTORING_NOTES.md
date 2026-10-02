# Where an order goes

The earlier service layout (`app/services/dhan_service.py`, `app/api/trading_routes.py`, LangGraph) is gone. The desk uses this path:

```text
Desk
  -> FastAPI route in backend/app/api/
  -> pending claim or the intraday handler
  -> TradingGateway
       -> paper ledger, or
       -> DhanHQ SDK for a live order
```

Live quotes, funds, positions, holdings, and orders use the trader token saved on Settings. `backend/app/broker/dhan_gateway.py` is the only module that imports the SDK. `backend/app/broker/dhan_token.py` renews that token before the 24-hour expiry.

NSE public JSON in `backend/app/market/nse_public.py` supplies holidays, constituents, and the rank. It does not price an order.

One process only. See [REPO.md](../REPO.md).
