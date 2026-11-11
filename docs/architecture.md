# Architecture

## Overview

Shahid Workforce has three layers:

1. **Dashboard** (`apps/dashboard/`) — Next.js 15 operator console: task board,
   task detail with live progress, agent roster. It talks to the API only
   through its own `/api/*` proxy routes, so the `X-API-Key` never reaches the
   browser.
2. **Services** (`services/`) — FastAPI API (`services/api`), orchestrator
   (`services/orchestrator`, LangGraph supervisor + routing), model router
   (`services/model_router`, 7 providers with budgets/fallback), background
   workers (`services/workers`, scheduler + task worker with retries).
3. **Agents & tools** (`agents/`, `tools/`, `sandbox/`) — 15 specialist roles
   loaded from `agents/configs/agents.yaml`, allowlisted tools (filesystem,
   terminal, database, github, testing, browser) and the hardened Docker
   sandbox used to execute untrusted code.

Supporting pieces: `database/` (SQLAlchemy models + Alembic migrations),
`infrastructure/` (compose stack, monitoring, logging), `tests/` (unit,
integration, security, e2e), `docs/`.

## Data flow

```
Dashboard -> API -> Orchestrator (plan) -> Workers (execute) -> Tools/Sandbox
                \-> Model Router (primary/fallback/budget)
                \-> Database (tasks) + Redis (queue)
```

1. A task is created via `POST /tasks` (status `pending`).
2. The orchestrator routes the task to specialist agents, appending the
   mandatory `code_reviewer` and `qa_engineer` gates at the end of every plan.
3. **Development (`Settings.auto_run`, the default when `WORKFORCE_ENV` is
   not `production`):** the API executes the task inline right after the
   response via a FastAPI background task - no Redis or worker needed.
   **Production / `WORKFORCE_AUTO_RUN=0`:** the worker claims queued jobs,
   executes steps through the model router (budget preflight, fallback
   rotation) and tool registry, and writes status transitions back to the
   database.
4. The dashboard polls `/api/tasks/{id}` for live progress.

## Key decisions

- Sequential specialist execution with prior outputs as reviewable context.
- Mandatory independent code-review and QA gates appended to every plan.
- Estimate-based per-task spend ceiling with preflight pricing checks.
- Restricted, ephemeral Docker sandbox: no network, read-only root, non-root,
  dropped capabilities, memory/CPU/PID limits, execution timeout. Missing
  Docker refuses to run (explicit `allow_local=True` opt-in only).
- Fail-closed API key auth; production refuses to boot without
  `WORKFORCE_API_KEY`.
- Migrations are explicit (`alembic upgrade head`), never automatic.
- One CI workflow with two jobs: `python` (ruff, mypy, pytest) and
  `dashboard` (typecheck + Next.js build).
