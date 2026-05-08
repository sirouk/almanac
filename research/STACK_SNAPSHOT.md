# Stack Snapshot

- snapshot_date: 2026-05-08
- project_root: .
- primary_stack: ArcLink multi-runtime platform
- primary_score: 096/100
- confidence: high

## Deterministic Scoring Inputs

| Signal | Score contribution | Evidence |
| --- | ---: | --- |
| Python control plane and tests | 30 | 168 tracked Python files and 99 tracked Python regression tests cover control DB, hosted API, auth, bots, provisioning, qmd/MCP, Notion/SSOT, memory, diagnostics, and plugin APIs. |
| Bash host lifecycle | 20 | 86 tracked shell/script entrypoints cover deploy, Docker, bootstrap, health, service installation, qmd/PDF jobs, backup, and upgrades. |
| Next.js web app | 18 | `web/package.json`, App Router pages, React/TypeScript components, Node tests, and Playwright browser tests cover onboarding, checkout, login, user dashboard, and admin dashboard. |
| Docker and systemd runtime | 14 | `compose.yaml`, `Dockerfile`, and 29 tracked systemd units/timers/paths define Shared Host Docker, Control Node, and bare-metal service lanes. |
| Hermes, qmd, plugins, hooks, and skills | 9 | `config/pins.json`, ArcLink Hermes plugins, hooks, skills, qmd wrappers, and managed-context tests define the agent runtime without Hermes core edits. |
| Public config/docs alignment | 5 | Public JSON/YAML manifests, OpenAPI, env examples, runbooks, and Ralphie research artifacts describe the same multi-lane stack. |

Total: 96/100. Confidence is capped below 100 because live external services
and host-mutating proof are intentionally gated.

## Project Stack Ranking

| Rank | Stack hypothesis | Score | Evidence | Decision |
| --- | --- | ---: | --- | --- |
| 1 | ArcLink multi-runtime platform: Bash + Python + Next.js + Docker/systemd + Hermes/qmd | 96 | Strong source, manifest, service, and test evidence across all lanes | Primary |
| 2 | Python control-plane platform with Bash host orchestration and a Next.js frontend | 83 | Python and Bash own most behavior, with web as a substantial UI layer | Useful shorthand, but it underweights Docker/systemd and Hermes plugins |
| 3 | Next.js application with Python API backend | 42 | Web app exists and is product-facing | Rejected as primary because host lifecycle, agent runtime, qmd, Notion, and bots are core product behavior |
| 4 | Python service collection only | 35 | Python modules are broad | Rejected because deploy scripts, web, Docker, systemd, and Hermes plugin surfaces are load-bearing |
| 5 | Node.js app | 18 | Next.js, React, TypeScript, and Playwright are present | Rejected as primary; Node is one runtime lane, not the whole project |
| 6 | Unknown or generic library | 0 | Repository has explicit manifests, entrypoints, and runbooks | Rejected |

## Ranked Implementation Alternatives

| Rank | Path | Fit | Tradeoff |
| --- | --- | --- | --- |
| 1 | Repair existing ArcLink Bash, Python, web, plugin, Compose, and systemd surfaces | Best fit | Preserves the current operator, hosted, agent, qmd, Notion, and dashboard contracts. |
| 2 | Fail closed or label unavailable where proof or policy is missing | Required companion path | Keeps no-secret BUILD safe, but leaves external rows proof-gated until authorized. |
| 3 | Add a new ArcLink browser broker for Drive/Code sharing | Conditional | Could make browser right-click sharing real without Nextcloud, but it is additional product scope and needs operator priority. |
| 4 | Depend on Nextcloud/WebDAV/OCS as the only sharing backend | Conditional | Fits deployments with Nextcloud enabled, but cannot be the only path for deployments without a safe live shared root. |
| 5 | Rewrite as a single hosted web application first | Poor fit | Would not repair Shared Host, Docker, public bots, Hermes plugins, qmd, Notion/SSOT, or runtime services. |
| 6 | Documentation-only repair | Poor fit | Violates the mission requirement to fix behavior before docs unless a row is explicitly proof-gated or policy-gated. |

## Stack Assumptions For BUILD

- Use public repo wrappers, generated config, plugins, hooks, service units,
  hosted API, public bots, web dashboards, and tests.
- Do not edit Hermes core.
- Treat live Stripe, Telegram, Discord, Chutes, Notion, Cloudflare, Tailscale,
  Docker install/upgrade, and host deploy/upgrade proof as explicit
  authorization gates.
- Keep Shared Host, Shared Host Docker, and Sovereign Control Node boundaries
  distinct while aligning docs, defaults, health checks, and tests.
