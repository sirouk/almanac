# Stack Snapshot

- snapshot_date: 2026-05-01
- primary_stack_hypothesis: Python control plane with Bash operations and Docker Compose runtime
- deterministic_confidence_score: 92/100
- confidence_band: high

## Scoring Rule

The score is deterministic from repository signals available in the checkout:

| Signal | Weight | Evidence | Awarded |
| --- | ---: | --- | ---: |
| Primary source directory | 25 | `python/` contains ArcLink and Almanac control-plane modules | 25 |
| Test surface for primary language | 20 | `tests/` contains focused Python regression tests | 20 |
| Dependency manifest | 10 | `requirements-dev.txt` exists for local validation tooling | 10 |
| Runtime orchestration | 15 | `compose.yaml` and `Dockerfile` define the Docker-first runtime | 15 |
| Operational scripts | 10 | `bin/` and `deploy.sh` drive install, upgrade, Docker, health, and repair | 10 |
| Stack pins | 10 | `config/pins.json` pins Hermes, qmd, Node, Python, Nextcloud, Postgres, Redis, and code-server | 10 |
| Frontend production manifest | 5 | no `package.json` or app directory for production dashboard yet | 0 |
| Cross-language adjustment | 5 | Node exists as runtime/tooling but not as app source today | 2 |

Total: 92/100.

## Ranked Stack Hypotheses

| Rank | Hypothesis | Score | Evidence | Interpretation |
| ---: | --- | ---: | --- | --- |
| 1 | Python + Bash + Docker Compose control plane | 92 | `python/`, `tests/`, `bin/`, `deploy.sh`, `compose.yaml`, `Dockerfile`, `config/pins.json` | The existing system is a Python control plane wrapped by Bash operations and run primarily through Docker Compose. This is the BUILD path. |
| 2 | Python service with future Next.js/Tailwind dashboard | 78 | ArcLink dashboard goals, Node 22 pin, no production frontend manifest yet | Likely target architecture after API/auth contracts harden, but not the current implementation stack. |
| 3 | Dockerized Almanac/Hermes appliance | 74 | Compose services, Hermes/qmd/runtime pins, user-agent supervisor | Accurate for the inherited Almanac substrate; incomplete for the SaaS/commercial ArcLink layer. |
| 4 | Node-first SaaS app | 22 | Node is pinned and available in the image | Node supports qmd/Hermes web build and future dashboard work, but the repo currently lacks production Node app manifests. |
| 5 | Kubernetes/Nomad platform | 8 | no scheduler manifests | Viable later for fleet scale, but not supported by current repo artifacts. |

## Current Runtime Stack

| Layer | Current choice | ArcLink implication |
| --- | --- | --- |
| Control plane | Python modules over SQLite helpers | Continue adding ArcLink contracts here first. |
| Operations | Bash scripts and canonical `deploy.sh` flows | Preserve for install, upgrade, health, Docker, and repair. |
| Runtime packaging | Dockerfile plus Docker Compose | Use for MVP single-user deployment units. |
| Data | SQLite for control plane, Postgres for Nextcloud, Redis for Nextcloud cache | Keep SQLite-first with Postgres migration path; Redis can later support jobs/pubsub/rate limits. |
| Agent runtime | Hermes with skills, hooks, plugins, gateways, cron | Preserve and expose as product value. |
| Retrieval | qmd MCP plus vault/PDF/Notion indexing | Preserve in every deployment plan. |
| Files/code | Nextcloud and code-server | Route by host-per-service, not path prefixes. |
| Inference | Chutes-first OpenAI-compatible lane; Codex/Claude remain supported | Keep per-deployment secret references and fake manager until live Chutes lifecycle is verified. |
| Billing/provisioning | Stripe/Cloudflare/Traefik/Chutes fakeable adapters | Keep live mutation behind explicit E2E gates. |
| Dashboard | Python WSGI prototype and dashboard read models | Treat as a no-secret contract probe; production Next.js/Tailwind comes later. |

## Alternatives

| Alternative | When to reconsider | Reason not selected now |
| --- | --- | --- |
| Immediate Next.js/Tailwind app | After API/auth, RBAC, audit, and admin-action contracts are hosted-ready | Frontend-first work would risk duplicating billing/provisioning logic before backend contracts stabilize. |
| Postgres-first ArcLink state | When multi-process hosted API load or migration tooling requires it | SQLite keeps local no-secret tests fast and matches current helpers. |
| Redis queue first | When job volume requires worker fanout | Durable DB idempotency is more important for payment/provisioning correctness right now. |
| Kubernetes/Nomad | When Docker Compose placement and rollout limits are proven constraints | Scheduler complexity is premature for the MVP. |
| Separate SaaS shell around Almanac | After the ArcLink backend contract is stable | A separate shell now would duplicate state, audit, health, and provisioning semantics. |
