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

- ✅ `services/api` - health + task CRUD with API-key auth (fail-closed)
- ✅ `agents/` - registry, prompt loading, shared agent interface
- ✅ `services/orchestrator` - routing, supervisor, LangGraph task graph
- ✅ `apps/dashboard` - Next.js operator console with `/api` proxy routes
- ⬜ `services/model_router`, `services/workers`, `tools/`, `sandbox/`,
  `database/migrations`, `infrastructure/`, remaining tests and docs

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
