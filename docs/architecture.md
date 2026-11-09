# Architecture

> Skeleton document — expand as components are implemented.

## Overview

Shahid Assistant AI has three layers:

1. **Dashboard** (`apps/dashboard/`) — web UI for creating tasks, watching agent
   progress, reviewing outputs and inspecting the audit trail.
2. **Services** (`services/`) — FastAPI API, orchestrator (LangGraph),
   model router (LiteLLM) and background workers (Redis + RQ).
3. **Agents & tools** (`agents/`, `tools/`) — 15 specialist roles with
   role-specific prompts, plus allowlisted tools (GitHub, filesystem, terminal,
   browser, database, testing) executed through `sandbox/`.

## Data flow

```
Dashboard -> API -> Orchestrator (plan) -> Workers (execute) -> Tools/Sandbox
                \-> Model Router (primary/fallback/budget)
                \-> Database (tasks, audit events) + Redis (queue)
```

## Key decisions

- Sequential specialist execution with prior outputs as reviewable context.
- Mandatory independent code-review and QA gates appended to every plan.
- Estimate-based per-task spend ceiling with preflight pricing checks.
- Restricted, ephemeral Docker sandbox: no network, read-only root, non-root,
  dropped capabilities, memory/CPU/PID limits, execution timeout.
