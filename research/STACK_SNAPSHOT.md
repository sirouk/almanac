# Stack Snapshot

- generated_at: 2026-05-08
- project_root: repository root
- primary_stack: ArcLink multi-runtime platform
- primary_score: 096/100
- deterministic_confidence_score: 094/100
- confidence: high

## Deterministic Scoring Method

Scores are based only on public repository signals: source counts, manifests,
runtime entrypoints, service definitions, tests, and documented canonical
commands. Private state, live credentials, logs, dependency folders, build
outputs, and machine-specific paths are excluded.

## Ranked Stack Hypotheses

| Rank | Stack hypothesis | Score | Evidence |
| ---: | --- | ---: | --- |
| 1 | ArcLink multi-runtime platform: Bash orchestration, Python control plane, Docker Compose/systemd services, Next.js web, Hermes plugins, qmd/Notion/SSOT rails | 096 | Canonical deploy wrappers, 54 first-party `python/arclink_*.py` modules, 99 Python tests, 82 shell scripts, 29 systemd units, 26 Compose services, 36 web TS/TSX/MJS/JS files, 4 Hermes plugins, 11 skills |
| 2 | Python-centered control and automation system | 088 | Control DB schema, hosted API, onboarding, provisioning, action worker, MCP, Notion/SSOT, memory, Docker supervisor, evidence, diagnostics, and most regression tests are Python |
| 3 | Bash/systemd/Docker operations platform | 082 | `deploy.sh`, `bin/deploy.sh`, Docker wrapper, bootstrap, health, service installers, qmd/PDF/backup jobs, and systemd/Compose topologies own host behavior |
| 4 | Hosted Next.js product surface backed by Python API | 064 | `web/package.json`, Next.js 15, React 19, TypeScript, browser tests, checkout/onboarding/dashboard/admin routes, and Python hosted API/auth modules |
| 5 | Hermes agent extension package | 058 | ArcLink behavior is delivered through Hermes plugins, hooks, generated config, skills, and pinned Hermes runtime docs without editing Hermes core |
| 6 | Documentation-only or static site project | 018 | Many docs exist, but deploy, runtime, API, worker, service, and test surfaces dominate behavior |

## Component Snapshot

| Component | Current role | Primary evidence |
| --- | --- | --- |
| Bash | Host lifecycle, Docker wrapper, bootstrap, health, qmd/PDF/Nextcloud jobs, service installation, validation wrappers | `deploy.sh`, `bin/*.sh`, `test.sh` |
| Python 3 | Control plane, hosted API, auth, onboarding, provisioning, workers, MCP, Notion/SSOT, memory, diagnostics, evidence, plugin APIs | `python/arclink_*.py`, `bin/*.py`, `tests/test_*.py` |
| SQLite | Durable control state for users, deployments, sessions, actions, events, evidence, fleet, rollout, and onboarding | `python/arclink_control.py` |
| Docker Compose | Shared Host Docker and Control Node service topology | `compose.yaml`, `Dockerfile`, `bin/arclink-docker.sh` |
| systemd | Bare-metal Shared Host services and timers | `systemd/user/*`, install scripts |
| Next.js/React/TypeScript | Hosted onboarding, checkout, login, dashboard, admin UI, API client, browser tests | `web/package.json`, `web/src/*`, `web/tests/*` |
| Hermes runtime | Agent gateways, dashboards, skills, hooks, managed context | `config/pins.json`, `plugins/hermes-agent/*`, `hooks/hermes-agent/*`, `skills/*` |
| qmd/Notion/SSOT | Vault/PDF/Notion retrieval and shared-source-of-truth write rails | qmd scripts, Notion/SSOT Python modules, skills |

## Alternatives

| Alternative | Fit | Decision |
| --- | --- | --- |
| Treat the repo as a Node/Next.js app | Too narrow; misses deploy, agent runtime, Docker/systemd, qmd, Notion/SSOT, and onboarding workers | Rejected |
| Treat the repo as a Python service | Useful for control-plane work but misses canonical Bash host orchestration and web/dashboard behavior | Partial only |
| Treat the repo as infrastructure-as-code | Useful for deploy and service review but misses hosted API, onboarding, plugins, and tests | Partial only |
| Treat the repo as a Hermes plugin package | Useful for agent runtime changes but misses product/control and host lifecycle | Partial only |

## BUILD Implication

BUILD should preserve the multi-runtime architecture: use Bash for host and
Docker flows, Python for control/API/worker/knowledge behavior, Next.js for
browser journeys, Compose/systemd for service topology, and ArcLink-owned
Hermes plugins/hooks/skills for agent runtime behavior. Do not patch Hermes
core or private state.
