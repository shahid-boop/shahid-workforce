# Dashboard

Next.js (App Router) operator console for the Shahid Workforce platform.

- `app/` - routes, pages and the `/api/*` proxy routes
- `components/` - shared UI components
- `features/` - feature modules (tasks, agents, audit)
- `hooks/` - React hooks
- `lib/` - typed API client (server-side only)
- `public/` - static assets

## How it talks to the API

The browser never talks to `services/api` directly. Pages call the Next.js
route handlers under `app/api/`, which use `lib/api.ts` server-side with the
upstream API key from the environment:

| Env var | Default | Purpose |
| --- | --- | --- |
| `WORKFORCE_API_BASE_URL` | `http://127.0.0.1:8000` | Base URL of `services/api` |
| `WORKFORCE_API_KEY` | _(required)_ | `X-API-Key` sent upstream (fail-closed) |

## Commands

```bash
npm install
npm run dev        # http://localhost:3000
npm run typecheck  # tsc --noEmit
npm run build      # production build (also runs in CI)
```
