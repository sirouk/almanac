# Stack Snapshot

- generated_at: 2026-05-14
- project_root: .
- primary_stack: Python control plane with SQLite, Bash/Compose runtime, and Next.js web surface
- primary_score: 093/100
- confidence: high

## Deterministic Scoring Inputs

Repository-level public signals, excluding private state and generated caches:

| signal | count / evidence |
| --- | --- |
| Python source files | 63 in `python/` |
| Python regression tests | 107 focused `tests/test_*.py` files |
| Shell/runtime scripts | 155 shell files/signals across canonical wrappers and generated/public helper lanes |
| Web source | 17 TSX files and 6 TS files under `web/` |
| Runtime manifests | `requirements-dev.txt`, `compose.yaml`, `Dockerfile`, `deploy.sh`, `test.sh`, `web/package.json` |
| Wave 4-6 targets | Python modules, SQLite tables, MCP/API handlers, public bots, dashboards, notification outbox, Compose job loop |

Scoring rule:

- Python receives the largest weight from control-plane ownership, schema,
  API/auth, MCP, bots, notifications, Chutes/redaction helpers, and tests.
- SQLite is core state but embedded through Python.
- Next.js is required for Captain/Operator surfaces but depends on Python APIs.
- Bash/Compose is operational runtime, especially for the Wave 6 scheduler.
- External services are integration targets, not local BUILD dependencies.

## Project Stack Ranking

| rank | stack | score | evidence |
| --- | --- | --- | --- |
| 1 | Python control plane | 093 | Owns schema, comms/recipe/wrapped modules, API/auth, MCP, bots, notifications, and focused tests. |
| 2 | SQLite state model | 074 | Existing tables for pod messages, crew recipes, wrapped reports, audit/events, rate limits, notifications. |
| 3 | Next.js / React / TypeScript | 061 | Captain dashboard, admin dashboard, API client, browser tests for Comms/Crew Training/Wrapped surfaces. |
| 4 | Bash / Docker Compose | 055 | Canonical wrappers and job-loop service pattern for Wrapped scheduler. |
| 5 | ArcLink/Hermes plugin boundary | 038 | Identity-context and managed-context rails; do not modify Hermes core. |
| 6 | External providers | 018 | Chutes, Telegram, Discord, Stripe, Notion, Cloudflare, Tailscale, Hetzner, Linode remain proof-gated. |

## Ranked Stack Hypotheses

1. **Python-led ArcLink control platform with SQLite state and Next.js dashboards**:
   selected. This matches all Wave 4-6 behavior surfaces.
2. **Next.js product app with Python backend**: true for user-facing work, but
   insufficient as the primary stack because authorization, notifications,
   MCP tools, and report generation live in Python.
3. **Shell/Compose operator system with Python helpers**: true for deploy and
   scheduling, but not primary for brokered comms, recipes, or Wrapped logic.

## Alternatives

| alternative | fit for Waves 4-6 | decision |
| --- | --- | --- |
| Add a separate message broker or queue service | Low | Reject. SQLite plus notification outbox is the existing rail and enough for scoped comms. |
| Add a new LLM/provider SDK for Crew Training | Low | Reject. Reuse Chutes boundary and fake/injectable tests. |
| Build Wrapped as a frontend-only report | Low | Reject. Report inputs and redaction belong server-side. |
| Fold Wrapped into health-watch | Medium | Accept only if an explicit `arclink-wrapped` job service proves unnecessary; default to named job-loop integration. |

## Confidence

Deterministic confidence score: **93/100**.

Confidence is high because repository structure, schema foundations, test
layout, and the Wave 4-6 target surfaces consistently point to Python/SQLite
as the primary implementation stack, with Next.js and Compose as secondary
surfaces. Remaining uncertainty is live delivery/inference proof, which is
explicitly blocked until operator authorization.
