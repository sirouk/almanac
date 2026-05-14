# Research Summary

<confidence>95</confidence>

## Scope

This PLAN pass inspected the public ArcLink repository structure, runtime
stack, existing Ralphie artifacts, current ArcPod Captain Console steering, and
nearby source files for onboarding, schema, fleet, bots, dashboard, Compose,
Hermes plugin integration, and tests.

No private state, secrets, user Hermes homes, deploy keys, production services,
provider consoles, payment flows, or Hermes core files were inspected.

## Active Mission

The active BUILD backlog is:

`research/RALPHIE_ARCPOD_CAPTAIN_CONSOLE_STEERING.md`

Historical Sovereign audit files remain background context only. The open
trust-boundary residuals in the audit verification file are out of scope unless
an ArcPod Captain Console wave directly intersects them.

## Source Findings

ArcLink is a Python-led control platform with Bash operational orchestration,
SQLite control state, Docker Compose runtime lanes, ArcLink-owned Hermes
plugins/hooks, and a Next.js product/admin surface.

| Signal | Evidence |
| --- | --- |
| Python control plane | `python/` contains hosted API, auth, control DB, onboarding, provisioning, fleet, action worker, executor, public bots, dashboard, MCP, Notion, memory, and notification modules. |
| SQLite schema spine | `python/arclink_control.py` owns `ensure_schema` and most control tables. The current dirty tree includes Wave 0 foundations: `agent_title`, per-deployment identity fields, onboarding identity fields, inventory, pod messages, pod migrations, crew recipes, Wrapped reports, indexes, and drift/status checks. |
| Operational shell | `deploy.sh`, `bin/deploy.sh`, `bin/arclink-docker.sh`, and many `bin/*.sh` wrappers are canonical host/container entrypoints. |
| Container runtime | `compose.yaml` defines Shared Host Docker and Control Node services with app, API, web, worker, gateway, qmd, Notion, Nextcloud, Postgres, Redis, and Traefik lanes. |
| Web surface | `web/package.json` uses Next.js 15, React 19, TypeScript 5, Tailwind, ESLint, Node tests, and Playwright. |
| Current onboarding identity state | The current dirty tree includes Wave 1 surfaces: web Agent Name/Agent Title inputs and resume state, backend validation/storage/metadata propagation, public bot identity commands, hosted API rename/retitle route, dashboard form, SOUL title substitution, and focused tests. |
| Fleet baseline | `python/arclink_fleet.py`, deployment placement tables, `python/arclink_inventory.py`, `python/arclink_asu.py`, Hetzner/Linode provider modules, deploy inventory help, runbook notes, and focused ASU/provider/fleet tests are present in the current dirty tree. BUILD must validate before closing Wave 2 because no tests were run during this PLAN pass. |
| Migration baseline | The schema foundation for pod migrations exists in the current dirty tree. A real `python/arclink_pod_migration.py` module and full `reprovision` wiring did not surface. |
| Comms/training/wrapped gaps | Schema foundations for pod messages, crew recipes, and Wrapped reports exist. Runtime modules and product surfaces for `arclink_pod_comms.py`, Crew Training, and `arclink_wrapped.py` did not surface. |

## Selected Build Order

Use the steering document's wave order:

| Wave | Scope | Rationale |
| --- | --- | --- |
| 0 | Vocabulary canon, schema foundations, SOUL template additions | Current dirty tree appears to contain the implementation; BUILD should validate before considering it closed. |
| 1 | Onboarding Agent Name and Agent Title across web, Telegram, Discord, dashboard rename/retitle | Current dirty tree appears to contain the implementation; BUILD should validate and fix any regressions before continuing. |
| 2 | Fleet inventory, provider modules, ASU, fair placement | Current dirty tree appears to contain a candidate implementation; BUILD should validate it before moving to migration. |
| 3 | 1:1 Pod migration via real `reprovision`/migration action | Depends on inventory/placement model. |
| 4 | Pod-to-pod comms, MCP tools, Captain and Operator Comms Console | Depends on deployment identity and share-grant boundaries. |
| 5 | Crew Training and Crew Recipe SOUL overlays | Depends on identity, schema, comms history, and managed context overlay path. |
| 6 | ArcLink Wrapped scheduler, reports, delivery, dashboard history | Consumes outputs from earlier waves. |

## Implementation Path Comparison

| Path | Strengths | Weaknesses | Decision |
| --- | --- | --- | --- |
| Wave-ordered scoped implementation from the ArcPod steering | Matches coupling order, preserves existing architecture, supports focused tests, and avoids live/private operations | Requires several migrations and coordinated web/bot/API updates | Selected. |
| Start only with the old Sovereign audit Wave 1 | Security-focused and already researched | Conflicts with the user-provided current mission and would ignore ArcPod deliverables | Rejected for this PLAN. |
| Big-bang implementation of all seven surfaces | Minimizes intermediate docs churn | High regression risk across schema, web, bots, provider, migration, MCP, and notifications | Rejected. |
| Documentation-only vocabulary pass | Low code risk | Does not fix onboarding, schema, inventory, migration, comms, training, or Wrapped behavior | Rejected. |
| Live provider/deploy proof during BUILD | Strong end-to-end confidence | Blocked by no-secret/no-live-mutation posture | Requires explicit operator authorization. |

## Assumptions

- Current source and focused tests are ground truth when historical docs disagree.
- The untracked ArcPod steering file is intended project context and should be preserved.
- Existing dirty-tree changes are user-owned or prior generated work and must not be reverted.
- BUILD may modify public ArcLink code, tests, docs, web files, templates, and Compose/deploy wrappers only when tied to the ArcPod mission.
- Live Stripe, Chutes, Hetzner, Linode, Cloudflare, Tailscale, Telegram, Discord, Notion, Docker host mutation, production deploys, and private-state reads remain blocked unless explicitly authorized.

## Risks

- Schema work touches shared `ensure_schema` and drift checks; tests must cover existing DB compatibility.
- Vocabulary migration can accidentally rename backend/operator terms that should stay technical; user-facing and operator-facing surfaces need separate assertions.
- Onboarding data must flow through web, bots, Stripe metadata, entitlements, provisioning intent, deployment rows, and managed-context identity without secret leakage.
- Provider inventory modules must fail closed without credentials and must not perform live cloud mutations in tests.
- Pod migration is high-risk because it touches state capture, secrets, DNS, placement, rollback, and idempotency.
- Live correctness remains unproved until the operator authorizes named live proof.

## Verdict

PLAN is ready for no-secret BUILD handoff. First validate the existing Wave 0,
Wave 1, and Wave 2 dirty-tree implementation against the focused test floors,
repair any regressions, then move to Wave 3 migration. Do not route to terminal
done while any wave checklist item remains unresolved or explicitly deferred
with operator-facing rationale.
