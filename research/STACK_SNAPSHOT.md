# Stack Snapshot

## Scope

This snapshot uses repository-level manifest and source signals only. It avoids
private state, live service state, local machine paths, timing output, and raw
command output.

## Primary Stack

- primary_stack: Python control plane with Bash operations and Next.js web UI
- primary_score: 091/100
- confidence: high

## Deterministic Confidence Score

Score formula:

- Python control-plane source and tests: 35 points
- Canonical Bash deploy/runtime entrypoints: 20 points
- SQLite schema ownership in Python: 15 points
- Next.js web product surface: 12 points
- Compose/container runtime: 6 points
- ArcLink-owned Hermes plugin/hook layer: 3 points

Observed score: 91/100.

## Project Stack Ranking

| rank | stack | score | evidence |
| --- | --- | --- | --- |
| 1 | Python + SQLite control plane | 091 | `python/` contains control DB, hosted API, auth, onboarding, provisioning, fleet, inventory, bots, dashboard, MCP, memory, and notification modules; `tests/` contains focused Python regression coverage. |
| 2 | Bash operational orchestration | 074 | `deploy.sh`, `bin/deploy.sh`, Docker/control menus, bootstrap, health, qmd, service, and live-proof wrappers are canonical operator entrypoints. |
| 3 | Next.js / React / TypeScript web | 061 | `web/package.json` declares Next.js 15, React 19, TypeScript 5, ESLint, Node tests, and Playwright; `web/src/app` owns onboarding, dashboard, and admin surfaces. |
| 4 | Docker Compose runtime | 047 | `compose.yaml` and `Dockerfile` define Control Node and Shared Host Docker service topology. |
| 5 | Hermes plugin/hook layer | 040 | `plugins/hermes-agent/` and `hooks/hermes-agent/` hold ArcLink-owned managed-context, dashboard plugins, and Telegram start hook integration. |
| 6 | External providers | 025 | Stripe, Chutes, Telegram, Discord, Hetzner, Linode, Notion, Cloudflare, and Tailscale are integration boundaries, not primary local implementation stacks. |

## Stack Hypotheses

| hypothesis | confidence | notes |
| --- | --- | --- |
| ArcLink is primarily a Python/SQLite control platform operated by Bash scripts | 0.95 | Most mission behavior, schema, API, bots, provisioning, fleet, inventory, and tests live in Python; deploy and control inventory are routed through Bash. |
| The web app is a supporting Next.js product/admin console rather than the system spine | 0.88 | The web surface handles onboarding/dashboard/admin UX but calls Python-hosted APIs and mirrors control-plane state. |
| Compose is the runtime substrate for Control Node and Docker validation, not the source of product logic | 0.82 | Compose wires services and environment, while Python modules own behavior. |
| Hermes should remain an external pinned runtime extended by ArcLink plugins/hooks | 0.91 | AGENTS guidance and repo layout route Agent behavior through ArcLink wrappers, plugins, hooks, and generated config. |

## Alternatives Ranking

| alternative | score | why not primary |
| --- | --- | --- |
| Node.js-first app | 061 | Strong web UI, but it does not own schema, provisioning, bots, fleet, migration, notification, or MCP control logic. |
| Compose-first platform | 047 | Important for runtime packaging, but behavior is implemented in Python/Bash. |
| Hermes-core fork | 010 | Explicitly out of scope; ArcLink must use plugins/hooks/wrappers instead of editing Hermes core. |
