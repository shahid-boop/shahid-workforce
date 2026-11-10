# Security

## Rules

- No API keys, tokens or populated `.env` files in Git.
- `WORKFORCE_API_KEY` enables `X-API-Key` checks; production fails closed
  without it (`RuntimeError` at startup).
- `WORKFORCE_CORS_ORIGINS` is an explicit browser-origin allowlist; the
  default allows only `http://localhost:5173`.
- The dashboard holds the API key **server-side only** (Next.js route
  handlers / server code). Browser code only ever calls `/api/*` proxies.
- Response headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options:
  DENY`, `Referrer-Policy: no-referrer`, `Cross-Origin-Opener-Policy:
  same-origin` via `SecurityHeadersMiddleware`.
- GitHub tool is **read-only** (`read_file`, `repo_info`, `list_issues`) —
  there are no write, delete, merge or deployment actions at all. Path
  traversal (`..`) is rejected, tokens are scrubbed from all tool output and
  error messages via `tools.base.scrub`.
- Terminal tool: fixed argv, never a shell; command allowlist with a blocked
  set (no `rm`, `curl`, `git push`, etc.).
- Filesystem tool is jailed to an explicit root; reads/writes outside it
  raise. Database tool is read-only (SELECT-only parser).
- Desktop/OS automation stays disabled until explicit permission controls and
  audit logging exist.

## Code sandbox (`sandbox/`)

Untrusted agent-generated code runs under `sandbox/policy.py`:

- Docker required by default — a missing engine **refuses to run**
  (`SandboxUnavailableError`); `allow_local=True` is an explicit, logged
  opt-in that cannot isolate.
- Container flags: `--network none`, `--read-only`, `--tmpfs /tmp`,
  `--user 65534:65534`, `--cap-drop ALL`, `--security-opt no-new-privileges`,
  `--pids-limit`, `--memory`, `--memory-swap`, `--cpus`.
- Hard ceilings the policy can never exceed: 4096 MB, 600 s, 8 CPUs, 512 PIDs.
- Source pre-filter rejects subprocess/os.system, network modules, dynamic
  imports, filesystem escapes and private-key material (cheap layer; the
  container is the real boundary).
- Wall-clock timeout enforced by the runner (exit 124 on expiry).

## API surface

- `GET /health` is the only public endpoint; everything else requires
  `X-API-Key` (constant-time comparison, 401 on missing/invalid).
- Input validated with Pydantic models; list limits bounded (1–200);
  unknown status filters rejected with 422.
- Prompt text of agents is never exposed through the API.

## Pending

- User identity / RBAC (API keys are not identity).
- Full compliance-grade audit trail.
- Signed release packaging.
- Rate limiting / per-key quotas.
