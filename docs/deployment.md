# Deployment

> Skeleton document — no deployment is configured yet.

## Planned targets

- **API + worker**: container via `docker-compose.yml` or a hosted container
  platform.
- **Database**: managed PostgreSQL; schema applied with
  `alembic upgrade head` (never mutated automatically at API startup).
- **Queue**: managed Redis.
- **Dashboard**: static build or Node server.

## Required environment

See `.env.example`. Hosted provisioning (database, Redis, secrets) is owned by
the deployment operator and is not performed by this repository.

## Health and rollback

- Health endpoint: `GET /health`
- Monitoring location: `infrastructure/monitoring/` (TODO)
- Rollback: redeploy the previous image; run `alembic downgrade -1` only when
  a migration must be reverted.
