# TradeAI backend refactor

The backend now uses a simple function-based flow:

```text
Frontend / LangGraph
        |
        v
FastAPI route
        |
        v
Application service
        |
        +---- Dhan service ----> DhanHQ Python SDK
        |
        +---- Trade service ---> SQLAlchemy / DB
```

## Trading flow

`POST /v1/trading/orders` -> `app.api.trading_routes.create_order()` -> `app.services.dhan_service.place_order()` -> guardrails -> Dhan SDK (live) or local journal (paper).

The same `place_order()` function can be called by the LangGraph/harness layer, so the frontend and AI never have separate execution logic.

## Files simplified

- `app/integrations/dhan/client.py`: only Dhan SDK connection, async wrapper, and security-ID lookup.
- `app/services/dhan_service.py`: all Dhan application operations and order orchestration.
- `app/services/trade_service.py`: local trade-journal CRUD and summary.
- `app/api/trading_routes.py`: thin trading endpoints.
- `app/api/trade_routes.py`: thin trade-journal endpoints.

The existing public route paths and compatibility imports from `app.services.dhan_service` are preserved.
