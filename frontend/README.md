# PAIOS Frontend

React + Vite frontend for the PAIOS Chat Core. It includes login/register, guest exploration mode, conversation sidebar, three interaction modes, markdown rendering, sources, tool calls, composer, model selector, and run details.

## Install Later

```bash
cd frontend
npm install
```

## Run Later

```bash
npm run dev
```

## Configure Later

Set this when the backend URL changes:

```env
VITE_API_URL=http://localhost:8000/v1
```

## Structure

- `src/api`: Axios client and API wrappers.
- `src/pages`: route-level screens.
- `src/components/sidebar`: conversation navigation.
- `src/components/mode`: top chat mode selector.
- `src/components/chat`: chat area, composer, messages, sources, tools.
- `src/components/run-details`: model run metadata display.
- `src/hooks`: auth lifecycle logic.
- `src/store`: Zustand stores prepared for later expansion.
- `src/routes`: route guards.
