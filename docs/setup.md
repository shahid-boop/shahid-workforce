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

## LLM API keys (free tier)

Agents call a real model through LiteLLM as soon as **any** provider key
is present; with no key configured they fall back to the template
placeholder, so the stack keeps working before you sign up anywhere.
Set any one of these (all offer free tiers):

```bash
# Google Gemini - free Flash/Flash-Lite tier: https://aistudio.google.com/apikey
export GEMINI_API_KEY=...

# Groq - free tier with per-day rate limits: https://console.groq.com/keys
export GROQ_API_KEY=...

# OpenRouter - free ":free" model ids: https://openrouter.ai/keys
export OPENROUTER_API_KEY=...

# Paid providers work too:
export OPENAI_API_KEY=...        # or ANTHROPIC_API_KEY / MISTRAL_API_KEY
```

Model selection (defaults are free-tier models; override per environment):

```bash
export WORKFORCE_MODEL_PRIMARY=google/gemini-2.5-flash
export WORKFORCE_MODEL_FALLBACKS=groq/llama-3.3-70b-versatile,openrouter/nvidia/nemotron-3.5-lightning:free
```

The chain drops models whose key is missing, rotates on rate limits /
timeouts / 5xx / auth errors, and aborts immediately on request-shape
errors. API keys are passed straight to the provider, never logged and
redacted from any error message.

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
pytest -q                # unit + integration + security + e2e (244+ tests)
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
