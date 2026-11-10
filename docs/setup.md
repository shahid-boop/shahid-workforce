# Setup

## Requirements

- Python 3.12+
- Node.js 22+ (npm)
- Docker (for the code sandbox; optional for local development)
- Redis (for queued/worker mode; optional — an in-memory scheduler is used in tests)

## Local development

```bash
# Python environment
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -e ".[dev]"

# Dashboard
cd apps/dashboard
npm ci
npm run dev          # http://localhost:3000
```

## Running the API

```bash
# Windows (PowerShell)
$env:WORKFORCE_API_KEY = "local-dev-key"
$env:WORKFORCE_DATABASE_URL = "sqlite:///./workforce.db"
python -m uvicorn services.api.main:app --host 127.0.0.1 --port 8000
```

```bash
# macOS/Linux
export WORKFORCE_API_KEY=local-dev-key
export WORKFORCE_DATABASE_URL=sqlite:///./workforce.db
python -m uvicorn services.api.main:app --host 127.0.0.1 --port 8000
```

- Health check: `GET http://127.0.0.1:8000/health`
- Interactive docs: `http://127.0.0.1:8000/docs`
- All task/agent endpoints require the `X-API-Key` header.

The dashboard needs the API origin and key **server-side only**:

```bash
cd apps/dashboard
export WORKFORCE_API_KEY=local-dev-key
export WORKFORCE_API_BASE_URL=http://127.0.0.1:8000
npm run dev
```

## Database migrations

```bash
export WORKFORCE_DATABASE_URL=sqlite:///./workforce.db   # or ALEMBIC_DATABASE_URL
alembic upgrade head          # apply
alembic downgrade -1          # roll back one revision
```

Migrations are never applied automatically at API startup.

## Full stack (containers)

```bash
cd infrastructure
cp .env.example .env          # set WORKFORCE_API_KEY
docker compose up --build
# dashboard on :3000, API internal, redis internal
```

## Tests

```bash
pytest -q                # unit + integration + security + e2e (219+ tests)
ruff check .             # lint
mypy .                   # type check (runs in CI)
cd apps/dashboard
npm run typecheck        # tsc --noEmit
npm run build            # production build
```

## Notes

- On machines that block compiled executables (AppLocker), run tools via
  `python -m pytest`, `python -m uvicorn`, and use `npm.cmd` on Windows.
- langgraph-dependent tests skip automatically when langgraph is unavailable.
