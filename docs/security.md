# Security

> Skeleton document — expand before any release.

## Rules

- No API keys, tokens or populated `.env` files in Git.
- `WORKFORCE_API_KEY` enables `X-API-Key` checks; production fails closed
  without it.
- `WORKFORCE_CORS_ORIGINS` is an explicit browser-origin allowlist.
- GitHub tools are allowlisted to this repository and feature branch only;
  `main`/`master`, workflow paths, `.git` and secret paths are blocked.
  There are no delete, merge or deployment routes.
- Desktop/OS automation stays disabled until explicit permission controls and
  audit logging exist.
- The code sandbox runs with no network, read-only root filesystem, non-root
  UID, dropped capabilities and resource limits.

## Pending

- User identity / RBAC (API keys are not identity).
- Full compliance-grade audit trail.
- Signed release packaging.
