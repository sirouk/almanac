# Stack Snapshot

- generated_at: 2026-05-01
- project_root: repository root
- primary_stack: Python + Bash + Docker Compose
- deterministic_confidence_score: 92/100
- confidence: high

## Deterministic Scoring Inputs

This snapshot is based on repository-visible files and manifests only, excluding
private state and git metadata.

| Signal | Count | Weight | Contribution |
| --- | ---: | ---: | ---: |
| Python source files | 128 | 35 | 35 |
| Python dev manifest | 1 | 10 | 10 |
| Shell scripts | 79 | 18 | 18 |
| Dockerfile | 1 | 8 | 8 |
| Compose file | 1 | 8 | 8 |
| systemd user units | 29 | 6 | 6 |
| YAML/JSON config manifests | 13 | 5 | 5 |
| Node package manifest | 0 | 0 | 0 |
| TypeScript/JavaScript app files | 0 | 0 | 0 |
| Total |  |  | 90 |

The final score is 92 rather than 90 because repository docs, tests, and pins
consistently describe Python/Bash/Docker Compose as the active runtime stack.

## Ranked Stack Hypotheses

| Rank | Stack Hypothesis | Score | Evidence | Decision |
| --- | --- | ---: | --- | --- |
| 1 | Python control plane with Bash operations on Docker Compose | 92 | `python/`, `tests/`, `requirements-dev.txt`, `bin/`, `compose.yaml`, `Dockerfile` | Selected ArcLink MVP stack. |
| 2 | Almanac/Hermes/qmd platform extension | 86 | Hermes runtime pins, qmd pin, Hermes hooks/plugins/skills, MCP services, memory and vault workers | Preserve as product substrate, not a separate rewrite. |
| 3 | Baremetal Linux/systemd operator stack | 72 | `systemd/user/`, deploy scripts, health scripts, AGENTS operational guide | Keep as compatibility and repair lane. |
| 4 | Future Next.js/Tailwind dashboard app | 34 | Product goals and docs prefer it, Node 22 is available, but no package manifest or app exists | Defer until backend/executor/auth contracts are ready. |
| 5 | Kubernetes/Nomad scheduler stack | 8 | Mentioned only as a later scaling alternative; no manifests | Reject for MVP. |

## Alternatives

| Alternative | Viability | Why It Is Not Primary Now |
| --- | --- | --- |
| Separate SaaS web/API shell around Almanac | Medium later | It would duplicate billing, audit, health, and provisioning semantics before the ArcLink backend contract is stable. |
| Immediate Postgres-first SaaS state | Medium later | SQLite helpers and tests are the existing development loop; keep schema portable and migrate after contracts settle. |
| Kubernetes/Nomad | Low for MVP | Docker Compose and per-node supervision are enough until multi-host scheduling pressure is measured. |
| Server-rendered Python dashboard | Medium fallback | It could be quick, but product goals call for responsive user/admin dashboards; Next.js/Tailwind is a better later frontend once APIs exist. |

## Architecture Confidence Notes

- Python is the dominant implementation language for control-plane, ArcLink,
  onboarding, Notion, memory, health, dashboard read-model, and executor code.
- Bash remains central for deploy, Docker orchestration, service repair, qmd,
  vault, PDF, backup, and host lifecycle work.
- Docker Compose is the preferred ArcLink provisioning substrate; baremetal
  systemd remains compatibility and operator-repair infrastructure.
- Node is present as runtime/tooling support for qmd/Hermes web build and a
  future dashboard, but there is no current JavaScript application.
