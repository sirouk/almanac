# Stack Snapshot

- snapshot_date: 2026-05-09
- project_root: repository root
- primary_stack: multi-runtime ArcLink platform
- deterministic_confidence_score: 96/100

## Ranked Stack Hypotheses

| Rank | Hypothesis | Score | Evidence | Decision |
| ---: | --- | ---: | --- | --- |
| 1 | Multi-runtime ArcLink platform: Bash host orchestration, Python control plane/API/bots/MCP, Next.js web, Docker/systemd services, Hermes plugins, qmd, Notion/SSOT, SQLite state | 96 | `deploy.sh`, `bin/*.sh`, `python/*.py`, `tests/test_*.py`, `web/package.json`, `compose.yaml`, `systemd/user/*`, `plugins/hermes-agent/*`, `config/pins.json` | Selected |
| 2 | Python-first backend with a companion Next.js dashboard | 82 | Python owns most product behavior, control state, hosted API, provisioning, bots, MCP, Notion, memory, Chutes, and live proof; web is an important but narrower UI layer | Useful simplification for backend repairs, not sufficient as the whole stack |
| 3 | Next.js web app with backend helpers | 42 | Next.js, React, TypeScript, Tailwind, Node tests, and Playwright exist, but most runtime, deploy, agent, and product behavior lives outside the web tree | Rejected as primary classification |
| 4 | Docker Compose service stack | 38 | Compose and Dockerfile are central for Shared Host Docker and Control Node validation, but bare-metal/systemd remains canonical too | Runtime lane, not the whole project |
| 5 | Unknown or generic library checkout | 0 | Repository contains explicit deploy, service, product, agent, and web surfaces | Rejected |

## Deterministic Scoring Inputs

| Signal | Current public evidence | Weight impact |
| --- | ---: | --- |
| Python behavior files | 172 | Strong backend/control-plane signal |
| Python regression tests | 101 | Strong local validation signal |
| Executable host entrypoints | 81 in `bin/` plus root wrappers | Strong Bash/operator-runtime signal |
| Web TypeScript/JavaScript files | 17 excluding dependency and build output | Strong but not dominant web signal |
| Markdown docs/research files | 103 | Strong operator/research/runbook signal |
| systemd unit/timer/path files | 29 | Strong bare-metal service signal |
| Public JSON/YAML manifests/config | 22 excluding lockfiles and generated build output | Strong Compose/pin/config signal |

The score is capped below 100 because live provider behavior, external account
proof, and several product-policy choices remain intentionally gated.

## Stack Components

| Component | Role in ArcLink |
| --- | --- |
| Bash | Canonical install, upgrade, Docker, health, service, qmd, PDF, backup, and runtime orchestration. |
| Python 3 | Control-plane DB, hosted API, auth, onboarding, provisioning, public bots, action worker, MCP, Notion/SSOT, memory synthesis, Chutes boundaries, fleet, rollout, and evidence/live proof. |
| SQLite | Local control-plane state for users, sessions, deployments, entitlements, events, shares, health, actions, channel links, and provider metadata. |
| Next.js, React, TypeScript, Tailwind | Hosted landing, onboarding, checkout, login, user dashboard, admin dashboard, API client, and browser validation. |
| Docker Compose | Shared Host Docker and Sovereign Control Node runtime lane. |
| systemd | Bare-metal service-user and per-agent timers/services. |
| Hermes runtime | Pinned agent runtime, dashboard host, skills, gateways, and cron behavior. ArcLink extends it through wrappers/plugins/hooks, not core edits. |
| ArcLink Hermes plugins | Managed context, Drive, Code, and Terminal dashboard surfaces with root containment and linked-resource rules. |
| qmd | Retrieval over vault, generated PDF sidecars, and shared Notion markdown. |
| Notion/SSOT | Brokered shared-root membership, scoped reads, webhook/index flow, and write governance. |
| Chutes | Provider lane with fail-closed local credential lifecycle, OAuth/account fallback planning, fake live-adapter coverage, and proof-gated live key/usage/balance behavior. |
| Stripe, Telegram, Discord, Cloudflare, Tailscale | External integrations covered locally by fakes/static tests; live proof requires explicit operator authorization. |

## Alternatives And Tradeoffs

| Path | When viable | Why not primary |
| --- | --- | --- |
| Treat as a Python service | Good for control-plane, hosted API, bots, MCP, Notion, memory, Chutes, and tests | Misses deploy scripts, web, Docker/systemd, Hermes plugins, qmd, and agent runtime behavior. |
| Treat as a Next.js app | Good for website and dashboard UX work | Misses most host, runtime, provisioning, public bot, knowledge, and service behavior. |
| Treat as Docker-only | Good for Control Node and Shared Host Docker validation | Bare-metal Shared Host and per-user systemd lanes remain canonical. |
| Rewrite into one service | Could simplify future architecture | Rejected for this mission because production readiness depends on existing public repo contracts and no Hermes core edits. |

## BUILD Implication

BUILD should repair current surfaces in place: Bash wrappers, Python modules,
Next.js UI, Compose/systemd units, Hermes plugins/hooks/skills, qmd/Notion
rails, and focused tests. Live provider rows remain proof-gated until the
operator authorizes named proof flows.
