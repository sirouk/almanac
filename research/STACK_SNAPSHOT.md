# Stack Snapshot

- generated_at: 2026-05-16T00:00:00Z
- project_root: repository root
- primary_stack: Python control plane with Shell/Docker Compose runtime and Next.js dashboard
- deterministic_confidence_score: 086/100
- confidence: high

## Scoring Rule

The deterministic score is repository-evidence based:

- 35 points: dominant Python source and test surface for control-plane logic.
- 20 points: canonical shell/deploy scripts and Docker Compose runtime.
- 15 points: SQLite schema and migration ownership in Python.
- 15 points: Next.js/React dashboard present but secondary to fleet mission.
- 10 points: focused tests exist for the target domain.
- 5 points: penalty retained for live/provisioning behavior that cannot be
  fully proven without operator-authorized hosts/providers.

Score: `35 + 20 + 15 + 15 + 10 - 9 = 86`.

## Project Stack Ranking

| rank | stack hypothesis | score | evidence |
| --- | --- | --- | --- |
| 1 | Python control plane | 35 | `python/` modules own fleet, inventory, action worker, provisioning worker, executor, schema, hosted API, dashboard, tests. |
| 2 | Shell + Docker Compose operations | 20 | `bin/deploy.sh`, `deploy.sh`, `bin/docker-job-loop.sh`, `compose.yaml`, host bootstrap scripts, operational tests. |
| 3 | SQLite-backed state | 15 | `python/arclink_control.py` owns schema, indexes, drift checks, status contracts, and temporary DB tests. |
| 4 | Next.js/React dashboard | 15 | `web/package.json`, Next 15, React 19, TypeScript, Playwright; relevant for operator health surfaces. |
| 5 | External provider adapters | 6 | Hetzner/Linode modules and requests dependency exist, but provisioning is currently partial and live proof is gated. |
| 6 | Hermes runtime integration | 5 | Pinned runtime, skills/plugins/hooks, but this mission must not modify Hermes core. |

## Deterministic Alternatives Ranking

| rank | implementation path | confidence | rationale |
| --- | --- | --- | --- |
| 1 | Extend current Python/Shell/Compose architecture | 86 | Aligns with existing code, tests, deploy surface, and steering constraints. |
| 2 | Add a separate fleet service/daemon with its own API and database | 31 | Could isolate fleet concerns, but violates small-patch/idempotent posture and duplicates control DB state. |
| 3 | Move worker health to a pushed worker agent | 28 | Useful long term, but conflicts with the selected pull-based, low-footprint worker model. |
| 4 | Introduce a new CLI binary for fleet operations | 18 | Technically simple, but conflicts with canonical `bin/deploy.sh control ...` operator surface. |

## Runtime Hypotheses

| hypothesis | confidence | evidence | validation needed |
| --- | --- | --- | --- |
| Fleet placement is Python/SQLite-local and already production-shaped for single-host plus manual multi-host | High | `arclink_fleet.py`, schema, tests for placement, capacity, uniqueness, ASU | Extend tests for region-tier and strategy. |
| Day-2 actions are the multi-host routing weak point | High | `arclink_action_worker.py` builds a single env executor; steering identifies this as load-bearing | Add two-host placement routing regression. |
| Worker enrollment requires new schema/API/CLI surfaces | High | No `arclink_fleet_enrollments` or callback surface found in current source | Add Phase 2 tests and implementation. |
| Periodic inventory probing is absent | High | Current `probe` is operator-triggered; no `arclink_fleet_inventory_worker.py` exists | Add daemon and Compose service. |
| Cloud-provider create/delete is incomplete | High | Current provider CLI path lists servers only | Add fake provider provisioning workflows. |
| Web/dashboard changes are secondary | Medium | Operator scale snapshot exists; fleet health may need dashboard addition | Only touch web if health surface is required by BUILD phase. |

## Alternatives To Keep Explicitly Deferred

- Worker-pushed heartbeat agent.
- TPM/Secure Boot hardware attestation.
- AWS/GCP/Azure/DigitalOcean provisioning.
- Separate probe key distinct from deploy key.
- Captain-visible fleet topology.
- CI-driven live cloud or non-loopback SSH proof.
