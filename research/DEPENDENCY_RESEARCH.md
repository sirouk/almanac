# Dependency Research

## Scope

This document records public dependency and runtime signals relevant to the
Sovereign audit remediation. It does not assert live account capability for
Stripe, Telegram, Discord, Chutes, Notion, Cloudflare, Tailscale, Docker host
mutation, or production deploy flows.

## Stack Components

| Component | Evidence | Mission relevance | Decision |
| --- | --- | --- | --- |
| Python 3.11+ | `python/*.py`, `tests/test_*.py`, `requirements-dev.txt`, `config/pins.json` | Control DB, hosted API, auth, workers, provisioning, entitlements, evidence, dashboard, bots, Notion, memory, live proof | Primary repair surface. |
| SQLite | `python/arclink_control.py` and its callers | Sessions, CSRF, rate limits, jobs, deployments, entitlements, evidence, drift, migrations | Use existing `connect_db`, migrations, transactions, constraints, and DB tests. |
| Bash | `deploy.sh`, `bin/*.sh`, `test.sh`, `ralphie.sh` | Canonical host lifecycle, Docker wrappers, health, qmd/PDF/runtime jobs | Keep scripts canonical; run syntax checks when touched. |
| Docker Compose | `Dockerfile`, `compose.yaml`, Docker tests | Container privilege, socket scope, service topology, Control Node runtime | Use static/fake tests locally; no live Docker mutation without authorization. |
| WSGI/hosted API runtime | `python/arclink_hosted_api.py`, hosted API tests | Body limits, CORS/preflight behavior, CIDR checks, route auth, and SQLite connection scope | Prefer server-side middleware/helper fixes and either document single-thread SQLite use or move to per-request connections. |
| Next.js / React / TypeScript | `web/package.json`, `web/src/*` | Product/admin/onboarding response-shape and UX fixes | Touch only with matching backend contract tests. |
| Hermes runtime/plugins | `config/pins.json`, `plugins/hermes-agent`, `hooks/hermes-agent` | Agent runtime integration | Use ArcLink wrappers/plugins/hooks; do not edit Hermes core. |
| qmd | `config/pins.json`, qmd scripts | Vault/Notion/PDF retrieval MCP | Preserve pin and loopback bindings. |
| Stripe / Chutes / DNS / bots / Notion | Provider adapters and live proof files | Later side-effect correctness and live proof | Local fake clients only unless explicitly authorized. |

## Version Snapshot

| Lane | Public signal | Planning note |
| --- | --- | --- |
| Python | `config/pins.json`: preferred `3.12`, `3.11`; minimum `3.11` | New code should remain Python 3.11 compatible. |
| Node | `config/pins.json`: Node major `22`; `Dockerfile` uses Node 22 base image | Preserve current runtime line. |
| Next.js | `web/package.json`: `next` `^15.3.2` | App Router web lane. |
| React | `web/package.json`: `react` and `react-dom` `^19.1.0` | Preserve current UI assumptions. |
| TypeScript | `web/package.json`: `typescript` `^5.8.0` | Needed for web/API client changes. |
| Playwright | `web/package.json`: `@playwright/test` `^1.59.1`; Python dev requirements also include Playwright | Browser proof only when web behavior changes or release validation is requested. |
| qmd | `config/pins.json`: `@tobilu/qmd` `2.1.0` | Keep retrieval semantics stable. |
| Hermes | pinned `hermes-agent` runtime/docs commit | Do not drift docs/runtime or edit core. |
| Service images | Nextcloud 31, Postgres 16, Redis 7, Traefik v3 | Preserve Compose compatibility. |
| Python dev validation | `requirements-dev.txt` lists jsonschema, discord.py, PyNaCl, PyYAML, requests, Playwright, pyflakes, and ruff | Use for local no-secret tests and lint. |

## Alternatives Compared

| Decision area | Preferred path | Alternatives | Reason |
| --- | --- | --- | --- |
| Wave 1 trust-boundary work | Patch existing Python/API/bot/auth/container surfaces with focused tests | New gateway service; proxy-only fixes | Existing code owns the boundaries and already has tests. |
| Secret detection | Shared `python/arclink_secrets_regex.py` imported by all redaction call sites | Fragmented per-module regexes | Centralization closes several audit IDs and prevents redaction order drift. |
| Session token hashing | HMAC-SHA256 with server-side pepper and migration-compatible reads | Plain SHA-256; password-hash library | HMAC preserves the current token lookup model while adding a server secret. |
| Body/CIDR/CORS enforcement | Hosted API middleware/helpers | Rely only on ingress | Server must enforce its own documented env contract. |
| Hosted API SQLite connection scope | Per-request connections if threaded serving is supported; otherwise explicit single-thread contract plus health-route guard | Shared app connection without documentation | `ME-5` and `LOW-3` require the runtime contract to be explicit and tested. |
| Docker socket hardening | Non-root image plus explicit socket-bound services | Remove all socket access; root containers | Some services intentionally need Docker; scope and document that boundary. |
| Executor workspace boundaries | Keep shell mode bounded and document or allowlist broader SSH/machine mode | Treat all executor modes as equivalent | `ME-15` is a corrected PARTIAL item; behavior must match an explicit permission model. |
| Live provider proof | Fake/injected clients until authorized | Run live provider mutations during BUILD | No-secret plan constraints block live mutation. |

## External Integration Posture

| Integration | Local-test posture | Live-proof posture |
| --- | --- | --- |
| SQLite control DB | Temporary DBs and migration tests | No private runtime DB reads. |
| Stripe/Chutes | Fake/injected clients, idempotency checks, adapter tests | Blocked until named authorization. |
| Telegram/Discord | Local signature/webhook tests | Webhook registration, command sync, and delivery blocked until authorized. |
| Docker/Cloudflare/Tailscale | Static Compose checks, fake runners, local command shims | Host/network mutation blocked until authorized. |
| Notion | Local/mock tests for cache and error handling | Workspace mutation blocked until authorized. |

## Dependency Risks

- The dirty worktree may contain partial fixes; tests must prove behavior.
- Wave 1 touches shared request/auth/secret helpers, so a small patch can have
  broad blast radius.
- Container hardening must preserve services that legitimately need Docker
  socket access.
- Web/API response changes require fixture and browser test alignment.
- Live proof remains outside local BUILD and must be reported separately from
  local validation.

## Validation Dependencies

Minimum Wave 1 validation after relevant edits:

```bash
git diff --check
python3 -m py_compile python/arclink_hosted_api.py python/arclink_api_auth.py python/arclink_telegram.py python/arclink_discord.py python/arclink_secrets_regex.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_telegram.py
python3 tests/test_arclink_discord.py
python3 tests/test_arclink_secrets_regex.py
python3 tests/test_arclink_docker.py
python3 tests/test_loopback_service_hardening.py
```

If shell files change:

```bash
bash -n deploy.sh bin/*.sh test.sh ralphie.sh
```

If web files change:

```bash
cd web
npm test
npm run lint
npm run build
```
