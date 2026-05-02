# Stack Snapshot

- generated_at: 2026-05-02
- project_root: .
- primary_stack: Docker-first Python control plane with Next.js web UI
- deterministic_confidence_score: 94/100
- confidence: high

## Deterministic Scoring Method

Scores are based on repository-local signals only: manifests, source-file
counts, runtime entrypoints, test coverage, deployment files, and documented
architecture commitments. A stack receives higher confidence when it has
multiple independent signals and lower confidence when it appears only as a
future option or support dependency.

## Ranked Stack Hypotheses

| Rank | Stack hypothesis | Score | Evidence | Decision |
| --- | --- | ---: | --- | --- |
| 1 | Docker-first Python/Bash control plane with SQLite state and Hermes/qmd services | 94 | `compose.yaml`, `Dockerfile`, `deploy.sh`, `bin/`, `python/`, `requirements-dev.txt`, 25 `arclink*.py` modules, 27 ArcLink test files | Primary ArcLink implementation path. |
| 2 | Next.js 15 + Tailwind 4 dashboard shell consuming the Python hosted API | 82 | `web/package.json`, `web/src/app`, `web/src/lib/api.ts`, web smoke tests, Playwright product checks | Production dashboard path, not the source of business truth. |
| 3 | Docker Compose plus Traefik/Cloudflare as the MVP deployment fabric | 78 | `compose.yaml`, `python/arclink_executor.py`, `python/arclink_ingress.py`, `docs/arclink/ingress-plan.md` | Chosen before Kubernetes or Nomad. |
| 4 | SQLite-first commercial state with a later Postgres path | 74 | `python/almanac_control.py`, `arclink_*` tables, schema tests, Postgres already present for Nextcloud | Keep SQLite now; migrate after contracts stabilize. |
| 5 | Provider-adapter architecture for Stripe, Cloudflare, Chutes, Telegram, and Discord | 72 | `python/arclink_adapters.py`, `python/arclink_chutes.py`, `python/arclink_telegram.py`, `python/arclink_discord.py`, live-gated tests | Keep fake-by-default adapters and secret-gated live proof. |
| 6 | Kubernetes/Nomad scheduler path | 18 | Mentioned only as future scaling option; no manifests | Defer until real scale requires it. |
| 7 | Separate SaaS shell around Almanac | 16 | Viable product option, but current code has additive ArcLink modules inside the existing control plane | Defer to avoid duplicating state semantics. |

## Current Stack Components

| Component | Role in ArcLink | Status |
| --- | --- | --- |
| Python | Hosted API, auth, onboarding, entitlements, provisioning, executor, dashboards read models, diagnostics, fleet, rollout, live proof | Primary and active. |
| Bash | Deploy, host bootstrap, health, Docker orchestration, jobs | Preserve as operational substrate. |
| Docker Compose | Shared Almanac runtime and ArcLink per-deployment executor target | Primary MVP runtime. |
| SQLite | Control-plane and commercial state via `arclink_*` tables | Primary database for tests and MVP. |
| Postgres | Nextcloud database today; future ArcLink state candidate | Secondary. |
| Redis | Nextcloud cache today; future jobs/pubsub/rate-limit candidate | Secondary. |
| Hermes | Agent runtime, skills, gateways, dashboards, cron behavior | Preserve and surface as product value. |
| qmd | Retrieval/indexing MCP for vault, PDF, and Notion content | Preserve. |
| Nextcloud | Per-user file/vault UI target | Preserve with isolation safeguards. |
| code-server | Browser IDE target | Preserve with host-per-service routing. |
| Chutes | Primary inference provider | Chutes-first, live proof still credential-blocked. |
| Stripe | Checkout, subscription, entitlement, reconciliation | Fake boundary complete; live proof credential-blocked. |
| Cloudflare/Traefik | DNS, tunnel/access strategy, host routing | Fake/planning boundary complete; live proof credential-blocked. |
| Telegram/Discord | Public onboarding and agent chat lanes | Shared state machine and fake/live adapter split complete. |
| Next.js/Tailwind | User/admin web dashboards | Active production UI path. |

## Alternatives Compared

| Path | Benefits | Costs | Verdict |
| --- | --- | --- | --- |
| Evolve Almanac in place with ArcLink modules | Preserves proven Hermes/qmd/memory/deploy machinery and existing tests. | Requires compatibility discipline during rebrand. | Selected. |
| Wrap Almanac with a separate SaaS shell | Cleaner isolation later. | Duplicates provisioning, auth, entitlement, and health semantics too early. | Defer. |
| Rewrite onto Kubernetes/Nomad | Stronger multi-host scheduling eventually. | Premature operational complexity for MVP. | Reject for now. |

## Confidence Notes

The primary-stack confidence is high because source layout, tests, Compose
runtime, docs, and implementation plan all point to the same architecture. The
remaining uncertainty is external rather than structural: live Stripe,
Cloudflare, Chutes, Telegram, Discord, and production-host proof cannot be
validated until credentials and accounts are available.
