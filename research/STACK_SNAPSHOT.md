# Stack Snapshot

- generated_at: 2026-05-01
- project_root: .
- primary_stack: Python + Bash + Docker Compose
- confidence: high (92/100)

## Ranked Stack Hypotheses

| Rank | Stack | Score | Evidence | Role |
| --- | --- | --- | --- | --- |
| 1 | Python 3.11+ | 95 | 44 modules under python/, 86 test files, requirements-dev.txt, almanac_control.py (15k lines), 14 arclink_* modules (~8300 lines) | Control plane, API, adapters, all business logic |
| 2 | Bash | 85 | 78 bin/ scripts, deploy.sh, init.sh, systemd units, Docker entrypoints | Ops automation, service lifecycle, cron jobs |
| 3 | Docker Compose | 90 | compose.yaml (16 services, 4 profiles), Dockerfile, .dockerignore | Runtime orchestration, service isolation |
| 4 | SQLite | 80 | Default DB in almanac_control.py, 18 arclink_* tables | Primary data store (Postgres path available) |
| 5 | PostgreSQL 16 | 70 | compose.yaml postgres service, config/almanac.env.example | Production-ready DB alternative |
| 6 | Redis 7 | 65 | compose.yaml redis service, Nextcloud cache, job pubsub | Cache, session, job coordination |
| 7 | Node.js / Next.js 15 | 10 | Planned (no package.json yet); IMPLEMENTATION_PLAN Task 2 | Future dashboard UI |
| 8 | Tailwind CSS | 10 | Planned alongside Next.js | Future dashboard styling |

## Deterministic Confidence Score

**Overall: 92/100**

Scoring breakdown:
- Manifest signals (requirements-dev.txt, compose.yaml, Dockerfile): +30
- Source file count (135+ Python, 78 Bash, 14 ArcLink modules): +25
- Test coverage (86 test files, 15 ArcLink-specific): +15
- Architecture documentation alignment (all research artifacts agree): +12
- Runtime evidence (16 Docker services, systemd units, cron patterns): +10
- Deductions: No package.json for planned Next.js (-5), no live E2E proof yet (-5)

## Implementation Path Comparison

### Path A: Evolve Docker/Python Almanac Control Plane (Selected)

- **Benefits:** Preserves Hermes/qmd/memory/vault/health; additive arclink_* modules already written; 86 passing tests; no rewrite risk
- **Costs:** Legacy Almanac naming persists; monolith grows until dashboard extraction
- **Confidence:** High - 14 ArcLink modules and 96 tests already landed

### Path B: Clean-Room Rewrite

- **Benefits:** Fresh naming, modern structure from day one
- **Costs:** Loses proven Hermes/qmd/memory/Nextcloud/code-server integration; rewrites 15k lines of almanac_control.py; months of regression risk
- **Confidence:** Low - no evidence this is viable within project timeline

**Verdict:** Path A is the only defensible choice given existing investment.

## Alternatives Considered

| Component | Current Choice | Alternative | Why Current Wins |
| --- | --- | --- | --- |
| Primary language | Python | Go/Rust | Existing 15k-line control plane; team expertise |
| Orchestration | Docker Compose | Kubernetes | Docker-first per project constraints; K8s premature |
| Database | SQLite-first | Postgres-only | Zero-config dev; Postgres path preserved for scale |
| Ingress | Traefik + Cloudflare | Nginx + manual DNS | Traefik labels integrate with Docker Compose natively |
| Inference | Chutes.ai | Direct model hosting | Chutes-first is a project requirement; BYOK supported |
| Dashboard | Next.js 15 + Tailwind | Python templates | Modern SPA expected for SaaS product surface |
| Bots | Telegram + Discord SDKs | Slack/custom | Telegram + Discord per project goals |

## Key Signals

- No `.csproj`, `go.mod`, `Cargo.toml`, `Gemfile`, or `package.json` in repo root
- Python is unambiguously the primary runtime language
- Bash is the primary ops/glue language
- Docker Compose is the sole orchestration layer
- Next.js is planned but not yet present in the codebase
