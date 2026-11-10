# Shahid Assistant AI

Windows 11 desktop AI assistant with a multi-agent AI workforce.

## Repository structure

```
Shahid-Assistant-AI/
├── apps/dashboard/       # Dashboard web app (routes, components, features, hooks, lib)
├── services/
│   ├── api/              # FastAPI service (routes, middleware, auth)
│   ├── orchestrator/     # Task supervisor, LangGraph, routing, state
│   ├── model_router/     # Provider routing, fallback, budgets
│   └── workers/          # Task worker and scheduler
├── agents/               # Agent registry, base agent, prompts/, configs/agents.yaml
├── tools/                # github, filesystem, terminal, browser, database, testing
├── sandbox/              # Dockerfile and execution policies
├── database/             # migrations, models, repositories
├── infrastructure/       # docker, deployment, monitoring, redis
├── tests/                # unit, integration, security, e2e
├── docs/                 # architecture, agents, setup, security, deployment
└── .github/workflows/    # CI
```

## Status

Incremental build-out (each step ships with tests and a green CI):

- ✅ `services/api` - health + task CRUD + agent roster with API-key auth (fail-closed)
- ✅ `agents/` - registry, prompt loading, shared agent interface
- ✅ `services/orchestrator` - routing, supervisor, LangGraph task graph
- ✅ `apps/dashboard` - Next.js console: task board, task detail/progress, agents page, `/api` proxy routes
- ✅ `services/model_router` - 6 providers, budgets, fallback with billing preflight
- ✅ `services/workers` - scheduler (memory + Redis) and task worker with retries
- ✅ `tools/` - filesystem (jailed), terminal, database, github, testing, browser
- ✅ `sandbox/` - hardened Docker execution policy with local opt-in
- ✅ `database/migrations` - Alembic pipeline with ORM drift tests
- ✅ `infrastructure/` - compose stack (api/worker/redis/dashboard), monitoring, logging
- ✅ `tests/` - security regressions (auth, headers, jail, scrub) + e2e full flow (API→worker→orchestrator)
- ✅ `docs/` - architecture, setup, security, deployment, agents (with regression tests)

No feature is considered working until its tests pass in CI.

## Requirements

- Python 3.12+
- Node.js 22+
- Docker (for the code sandbox)
- Redis + PostgreSQL (for queued tasks and hosted persistence)

## Setup

See [docs/setup.md](docs/setup.md).

## Security

See [docs/security.md](docs/security.md). Never commit secrets or populated
`.env` files.
