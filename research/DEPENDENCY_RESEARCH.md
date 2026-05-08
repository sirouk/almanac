# Dependency Research

## Stack Components

| Component | Evidence | Role | BUILD decision |
| --- | --- | --- | --- |
| Bash | `deploy.sh`, `bin/*.sh`, `test.sh` | Canonical host lifecycle, Docker wrapper, bootstrap, health, qmd/PDF/Nextcloud jobs, service installation | Keep host mutations in scripts; validate with `bash -n` and focused shell/static tests. |
| Python 3 | `python/*.py`, `bin/*.py`, `tests/test_*.py` | Control plane, hosted API, onboarding, provisioning, action worker, MCP, Notion/SSOT, memory, diagnostics, evidence, plugin APIs | Primary behavior-fix language for API, state, worker, onboarding, and knowledge repairs. |
| SQLite | Schema and helpers in `python/arclink_control.py` | Durable state for users, deployments, sessions, actions, health, events, evidence, fleet, rollout, onboarding, and provisioning | Preserve migrations; add focused DB tests for truthful transitions and locking. |
| Docker Compose | `compose.yaml`, `Dockerfile`, `bin/arclink-docker.sh` | Shared Host Docker and hosted/control-node substrate | Preserve completed parity gates; document and reduce remaining trusted-host boundaries. |
| systemd | `systemd/user/*.service`, `systemd/user/*.timer`, install scripts | Bare-metal Shared Host services, timers, and user-agent units | Preserve loopback, path quoting, service env, and health behavior. |
| Next.js | `web/package.json`, `web/src/app/*`, `web/src/lib/api.ts` | Hosted product, onboarding, checkout, login, user dashboard, admin dashboard | Keep existing app; preserve completed auth/session/CSRF and API-shape repairs. |
| React/TypeScript | `web/src/*.tsx`, `web/tests/*`, configs | Web UI and browser validation | Use existing components and tests; avoid introducing another frontend stack. |
| Node.js toolchain | `web/package-lock.json`, `web/package.json`, `config/pins.json` | Next.js build/runtime, Playwright tests, qmd install, live proof/browser checks | Document local Node and Playwright prerequisites; keep web validation explicit. |
| Hermes runtime | `config/pins.json`, Docker/bootstrap installers | Agent runtime, gateways, dashboard host, skills, cron jobs | Do not edit Hermes core; use ArcLink plugins, hooks, generated config, and wrappers. |
| Hermes dashboard plugins | `plugins/hermes-agent/drive`, `plugins/hermes-agent/code`, `plugins/hermes-agent/terminal`, `plugins/hermes-agent/arclink-managed-context` | Agent Drive, Code, Terminal, and managed context | Preserve hardened roots, secret exclusions, terminal boundaries, and installer/Docker defaults. |
| qmd | `bin/qmd-daemon.sh`, `bin/qmd-refresh.sh`, `skills/arclink-qmd-mcp` | Vault, PDF, and shared Notion retrieval | Preserve loopback/default scope and completed freshness guarantees; align remaining docs. |
| Notion API and SSOT | `python/arclink_notion_*`, `python/arclink_ssot_batcher.py`, SSOT skills | Shared Notion indexing and writes through broker rails | Preserve exact-read, destructive-payload, and batch claim/lock gates. |
| PDF ingest and memory synthesis | `bin/pdf-ingest.py`, `python/arclink_memory_synthesizer.py` | Generated markdown sidecars and managed recall hints | Preserve endpoint redaction and content-hash freshness behavior. |
| Nextcloud | Compose service, `bin/nextcloud-*.sh`, access helpers | Shared file service and future share adapter | Preserve truthful enablement/access behavior; keep docs aligned with actual support. |
| Stripe | Hosted API/onboarding/docs/live E2E | Entitlement and checkout | Live flows require explicit operator authorization and credentials. |
| Telegram/Discord | `python/arclink_telegram.py`, `python/arclink_discord.py`, onboarding/public bot modules | Private Curator and public bot onboarding | Test with fakes/mocks unless operator authorizes live bot mutations. |
| Cloudflare/Tailscale | Ingress, provisioning, docs, live proof | Domain and Tailnet routing | Treat as proof-gated external dependencies. |
| Playwright | `web/package.json`, `web/tests/browser`, live proof runner | Browser proof for hosted and workspace surfaces | Document setup and skip conditions; run for touched web/proof surfaces when available. |

## Alternatives Compared

| Decision area | Preferred path | Alternative | Reason |
| --- | --- | --- | --- |
| Security repairs | Fix inside ArcLink wrappers/plugins/Python modules with focused tests | Rely on private state conventions or manual operator discipline | Public code must fail closed and remain testable without secrets. |
| Onboarding recovery | Make failure/denial/skip/retry/cancel state durable and user-visible | Leave failures only in operator logs or ephemeral chat context | Users need recoverable journeys and operators need auditable state. |
| Credential delivery | Route generated credentials only through documented credential channels or remove them from operator notifications | Continue sending generated passwords to generic operator notification channels | Credential exposure is a policy and security boundary, not a convenience detail. |
| Knowledge freshness | Use content hashes and DB claim/lock semantics | Depend on timestamps, sizes, or serial job assumptions | Same-size rewrites and concurrent batchers can produce stale or duplicate output. |
| qmd exposure | Loopback by default with deliberate opt-in for wider bind | Default public bind | Retrieval MCP should not be exposed accidentally. |
| Notion exact reads | Scope to configured shared/indexed roots or privileged audited operations | Allow any integration-accessible page/database | Agent-facing tools must match shared knowledge boundaries. |
| Generated cleanup | Resolve and contain DB-stored paths before unlink/move | Trust stored paths | Corrupt or malicious rows must not delete outside generated roots. |
| Docs | Behavior-first updates with a doc status map | Rewrite docs ahead of repairs | Prevents polished docs from covering broken behavior. |
| Stack ownership | Preserve the multi-runtime ArcLink topology | Collapse into Python-only, Node-only, or plugin-only work | The repo has first-class Bash, Python, Compose/systemd, web, and Hermes plugin surfaces. |

## Source Composition Signals

Counts exclude private state, dependency folders, build output, logs, bytecode
caches, and completion artifacts.

| Source kind | Count | Planning implication |
| --- | ---: | --- |
| Python first-party `arclink_*.py` modules | 54 | Primary control-plane, API, worker, onboarding, plugin API, and knowledge modules. |
| Python tests | 99 | Broad focused regression coverage exists and should be rerun or extended for remaining documentation/validation tasks. |
| Shell scripts | 82 | Host lifecycle, Docker, health, bootstrap, and service orchestration are first-class behavior. |
| systemd service/timer/path units | 29 | Bare-metal services and recurring jobs are core behavior. |
| Web TS/TSX/MJS/JS source, tests, and config | 36 | Hosted product web surface and browser validation are active. |
| Hermes plugins | 4 | Drive, Code, Terminal, and managed-context agent plugins. |
| Skills | 11 | Vault, qmd, Notion, SSOT, resources, upgrade, first-contact, and PDF export. |
| `arclink_*` control DB tables | 24 | Durable state spans users, deployments, sessions, actions, events, health, fleet, rollout, evidence, and onboarding. |

## Dependency Risks

- `requirements-dev.txt` includes local validation helpers but not every
  dependency implied by heavier live or browser proof.
- Web validation depends on Node dependencies and installed Playwright browsers.
- Live Stripe E2E requires explicit credentials and the Stripe runtime package.
- Docker mode mounts private state and the Docker socket into trusted services;
  the security model must remain documented and reduced where practical.
- qmd, Hermes, Nextcloud, Postgres, Redis, uv, nvm/Node, and Tailscale are
  pinned or configured components whose upgrade paths must preserve private
  config and release-state truth.
- External proof dependencies are not safe to run automatically in PLAN.
- Private manifests and generated DB paths can influence destructive
  operations; BUILD must preserve path-component validation before reset,
  unlink, or move actions.

## Validation Dependencies

Use the narrowest relevant checks during BUILD:

```bash
git diff --check
bash -n deploy.sh bin/*.sh test.sh
python3 -m py_compile <touched python files>
python3 tests/<nearest focused test>.py
```

For web changes:

```bash
cd web
npm test
npm run lint
npm run test:browser
```

Credential-gated live proof, Docker install/upgrade, public bot mutation,
production payment, and live host deploy/upgrade flows require explicit
operator authorization during BUILD.
