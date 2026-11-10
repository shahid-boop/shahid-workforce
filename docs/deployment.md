# Deployment

## Targets

- **Full stack**: `infrastructure/docker-compose.yml` — API, worker, Redis and
  dashboard as containers; only the dashboard publishes a port (3000).
- **Database**: SQLite by default; managed PostgreSQL for hosted mode. Schema
  applied with `alembic upgrade head` (never mutated automatically at API
  startup).
- **Queue**: Redis (internal network, not exposed to the host).
- **Dashboard**: standalone Next.js server (`infrastructure/dashboard.Dockerfile`).

## Quick start

```bash
cd infrastructure
cp .env.example .env       # set WORKFORCE_API_KEY to a long random value
docker compose up --build
docker compose ps          # all services healthy
```

Required environment (see `infrastructure/.env.example`):

| Variable | Purpose |
|---|---|
| `WORKFORCE_API_KEY` | Required (`:?` in compose — startup fails without it) |
| `WORKFORCE_ENV=production` | Enables fail-closed boot check |
| `WORKFORCE_DATABASE_URL` | Defaults to SQLite inside the api-data volume |
| `WORKFORCE_CORS_ORIGINS` | Browser origin allowlist |
| `WORKFORCE_API_BASE_URL` | Dashboard → API origin (default `http://api:8000`) |

## Images

- `infrastructure/api.Dockerfile` — one image, two commands: API (default CMD)
  and worker (`python -m services.workers.task_worker`). Runs as non-root
  `appuser`.
- `infrastructure/dashboard.Dockerfile` — multi-stage build, `node` user,
  no API key baked in (runtime env only).

## Health and monitoring

- Health endpoint: `GET /health` (compose healthchecks probe it).
- Prometheus: `infrastructure/monitoring/prometheus.yml`
  (scrapes `api:8000/metrics`, redis exporter).
- Alerts: `infrastructure/monitoring/alerts.yml` — `ApiDown`, `RedisDown`,
  `HighErrorRate` (5xx > 5% for 10 min).
- Structured logging: `infrastructure/logging.json` (JSON to stdout; docker log
  drivers handle shipping).

## Rollback

1. Redeploy the previous image tag.
2. Run `alembic downgrade -1` only when a migration must be reverted.
3. Verify with `GET /health` and the dashboard task board.
