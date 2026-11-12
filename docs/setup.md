# Setup

## Requirements

- Python 3.12+
- Node.js 22+ (npm)
- Docker (for the code sandbox; optional for local development)
- Redis (for queued/worker mode; optional — an in-memory scheduler is used in tests)

## One-click start (Windows)

### Packaged EXE (end users)

Download `ShahidWorkforce-win64.zip` from the repository's Releases
page, extract it anywhere and run `ShahidWorkforce\ShahidWorkforce.exe`:

- one process serves the dashboard **and** the API on
  `http://127.0.0.1:8756` (browser opens automatically);
- first launch generates an API key in
  `%LOCALAPPDATA%\ShahidWorkforce\config.json` and creates the SQLite
  database in the same folder — both persist between launches;
- tasks execute inline (`WORKFORCE_AUTO_RUN=1`); no Redis/Python/Node;
- provider keys are added from the Settings page as usual. An explicit
  `WORKFORCE_*` environment variable overrides any derived setting;
- stop the app by closing its console window.

Build it yourself (from source, Node + Python required):

```bash
cd apps/dashboard
npm ci
npm run build:static          # stop `npm run dev` first on Windows
cd ..\..
pip install pyinstaller
pyinstaller packaging/ShahidWorkforce.spec --distpath dist --workpath build --noconfirm
dist\ShahidWorkforce\ShahidWorkforce.exe
```

CI runs the same build, smoke-tests it (health + dashboard + key
injection) and attaches the zip to the GitHub Release
(`.github/workflows/release.yml`, manual dispatch or `v*` tag).

### From source

Double-click **`start-dev.bat`** in the repo root. It:

1. creates `.venv` / installs dependencies on first run;
2. applies database migrations (`alembic upgrade head`);
3. starts the API on `http://127.0.0.1:8000` (this window) and the
   dashboard in a second window (`http://localhost:3000`);
4. opens the dashboard in your default browser.

All required `WORKFORCE_*` variables are set by the script, including
`WORKFORCE_AUTO_RUN=1` (see below). Close the windows to stop the servers.

## Task auto-run (development)

When `Settings.auto_run` is on, `POST /tasks` executes the task **inline,
right after the response** — no Redis, no worker process. The dev default
is on (`WORKFORCE_ENV != "production"`), so a freshly started server runs
tasks end-to-end with the real LLM chain (or the template fallback when no
provider key exists).

- `WORKFORCE_AUTO_RUN=0` forces queued mode (tasks wait for
  `python -m services.workers.task_worker` + Redis).
- Production defaults to queued mode; set `WORKFORCE_AUTO_RUN=1` to
  override.

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
export WORKFORCE_MODEL_PRIMARY=google/gemini-3.6-flash
export WORKFORCE_MODEL_FALLBACKS=google/gemini-3.5-flash-lite,groq/llama-3.3-70b-versatile,openrouter/nvidia/nemotron-3.5-lightning:free
```

The chain drops models whose key is missing, rotates on rate limits /
timeouts / 5xx / auth errors, and aborts immediately on request-shape
errors. API keys are passed straight to the provider, never logged and
redacted from any error message.

### Adding keys from the dashboard

The same keys can be managed **manually** at **http://localhost:3000/settings**
(no terminal needed): paste a key per provider (Gemini, Groq, OpenRouter,
Ollama, OpenAI, Anthropic, Mistral), hit Save, Remove to revoke. Keys are
stored in the `provider_credentials` table of the configured database and
resolved in this order:

1. environment variable (`GEMINI_API_KEY`, `GROQ_API_KEY`, ...) - always wins;
2. key saved on the Settings page.

Ollama needs no key: save its base URL (default `http://localhost:11434`)
and the provider becomes available; set `OLLAMA_BASE_URL` for an
environment-only setup. New keys take effect for the next task without a
restart.

## Packaged (static) mode

`npm run build:static` exports the dashboard as pure static HTML in
`apps/dashboard/out/` (temporarily moving the `app/api` proxies aside —
stop `npm run dev` first on Windows). Point the API at it and it serves
the whole UI itself:

```bash
export WORKFORCE_DASHBOARD_DIR=apps/dashboard/out
python -m uvicorn services.api.main:app --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000/ - no Node.js process required
```

The API then also answers `/api/*` itself (the dashboard's fetch paths),
returning the same JSON with the browser-facing `{"error": ...}` shape,
and injects `window.__WF_KEY` into every served HTML page so `apiFetch`
can authenticate. This is the basis of the Windows EXE build.

## Android (Termux)

The packaged static mode also runs on a phone — no PC, no Node.js:

```bash
# Termux (install from F-Droid), then:
pkg update -y && pkg upgrade -y
pkg install python git curl unzip     # + `clang rust` only if pip must compile

git clone https://github.com/shahid-boop/shahid-workforce.git
cd shahid-workforce
python -m venv .venv && source .venv/bin/activate
pip install -e .

# Prebuilt dashboard from the release zip (Next.js' SWC binary does not
# run on Termux's bionic libc, so do not build it locally):
curl -L -o /tmp/wf.zip \
  https://github.com/shahid-boop/shahid-workforce/releases/download/v0.1.0/ShahidWorkforce-win64.zip
unzip -q /tmp/wf.zip -d /tmp/wf
cp -r /tmp/wf/ShahidWorkforce/_internal/dashboard apps/dashboard/out

export WORKFORCE_DASHBOARD_DIR="$PWD/apps/dashboard/out"
termux-wake-lock                       # keep the server alive when idle
python -m uvicorn services.api.main:app --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000/ in the phone browser
```

Dev mode needs no API key (auth stays open until a key is configured),
the SQLite schema is created at startup and tasks auto-run inline. Add
real LLM keys from the Settings page. The Windows EXE, `start-dev.bat`
and the Docker sandbox do not run inside Termux.

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
