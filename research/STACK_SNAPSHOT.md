# Stack Snapshot

- generated_at: 2026-05-14
- project_root: repository root
- primary_stack: Python control plane with Next.js dashboard and Shell/Compose runtime
- primary_score: 087/100
- confidence: high

## Project Stack Ranking

| rank | stack | score | evidence |
| --- | --- | --- | --- |
| 1 | Python | 087 | 189 Python files, SQLite control-plane schema, hosted API, bots, provisioning, notification delivery, tests |
| 2 | Shell + Docker Compose | 071 | 82 shell scripts, canonical `deploy.sh`, `bin/docker-job-loop.sh`, `compose.yaml`, systemd templates |
| 3 | Next.js / React / TypeScript | 064 | Web package manifest, 17 TSX files, 6 TS files, dashboard/admin/onboarding surfaces, Playwright tests |
| 4 | SQLite | 058 | Embedded control-plane DB schema and migrations in Python; no standalone DB service required for local tests |
| 5 | Node.js tooling | 044 | Web build/test/lint toolchain and marketing/dashboard assets |
| 6 | Hermes plugin runtime | 037 | ArcLink-managed Hermes plugins and hooks, installed by wrapper scripts rather than edited in core |
| 7 | External provider adapters | 025 | Stripe, Chutes, Telegram, Discord, Hetzner, Linode, Notion, Cloudflare, Tailscale boundaries are fake/default-gated |
| 8 | Unknown / other | 000 | No Go, Rust, Java, Ruby, or .NET manifests detected in the active public implementation path |

## Deterministic Confidence Score

Score formula:

```text
primary_score =
  30 points for dominant implementation language evidence
  20 points for matching test suite evidence
  15 points for runtime entrypoint evidence
  15 points for web/dashboard manifest evidence
  10 points for deployment/runtime orchestration evidence
  10 points for docs/spec alignment evidence
```

Applied score:

| Signal | Points | Evidence |
| --- | --- | --- |
| Dominant implementation language | 28/30 | Python owns API, schema, bots, provisioning, notifications, and tests. |
| Test suite | 19/20 | Focused Python tests exist for most ArcLink surfaces; web tests exist. |
| Runtime entrypoints | 14/15 | `deploy.sh`, `bin/arclink-ctl`, hosted API, public bots, job-loop scripts. |
| Web/dashboard manifest | 12/15 | Next.js app with dashboard/admin/onboarding and Playwright tests. |
| Orchestration | 8/10 | Compose and systemd paths exist; live deploy remains operator-gated. |
| Docs/spec alignment | 6/10 | API reference/OpenAPI exist but need Wave 6 reconciliation. |
| Total | 087/100 | High confidence. |

## Top 3 Stack Alternatives

1. Python-first full-stack control plane: score 087.
   Evidence: Python owns business logic, SQLite schema, hosted API, public bots,
   notification delivery, and most tests. This is the correct implementation
   lane for ArcLink Wrapped.

2. Next.js-first product app: score 064.
   Evidence: dashboard and onboarding are Next.js/React, but they consume
   Python hosted API routes rather than owning core behavior.

3. Shell/Compose operations substrate: score 071 as a runtime lane, not the
   primary product logic.
   Evidence: deploy/install/health/job-loop scripts and Compose services own
   runtime orchestration. Wrapped scheduling should use this lane narrowly.

## Alternatives And Rejections

| Alternative | Why it is not primary |
| --- | --- |
| Pure Node.js service | The web app is significant, but control-plane state, API, and tests are Python/SQLite. |
| New queue/scheduler infrastructure | Existing job-loop services are sufficient for Wrapped cadence and retry behavior. |
| Direct Hermes-core implementation | ArcLink operating guide forbids modifying Hermes core for ArcLink behavior. |
| Live-provider implementation path | BUILD is no-secret and local; live providers remain proof-gated. |
