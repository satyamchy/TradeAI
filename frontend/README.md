# TradeX desk

Vite and React. The desk talks to the FastAPI process. There is no signup page.

## Run locally

```text
npm install
npm run dev
```

Open http://localhost:5173. The client calls `http://localhost:8000` unless `VITE_API_URL` is set. Copy `frontend/.env.example` to `frontend/.env` only when the API is somewhere else. Do not append `/api/v1`.

## Production build

```text
VITE_API_URL=https://api.example.com npm run build
```

Serve `dist/` from the origin set as `FRONTEND_ORIGIN` on the API. See [REPO.md](../REPO.md).

## Screens

- `src/pages/DeskPage.jsx` shows cash, positions, the selected index, and Close.
- `src/pages/OrdersPage.jsx` is the pending list, the blotter, and manual orders.
- `src/pages/SettingsPage.jsx` saves the Dhan token and the shared limits.
- `src/api/stockApi.js` is the HTTP client. The session cookie is sent with each request.
