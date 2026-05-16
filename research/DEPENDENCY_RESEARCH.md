# Dependency Research

## Scope

This document records stack and dependency signals relevant to the ArcLink
Sovereign Fleet enrollment and placement mission. It does not assert live
capability for Stripe, Telegram, Discord, Chutes, Notion, Cloudflare,
Tailscale, real Hetzner/Linode accounts, production deploys, or remote hosts.

## Stack Components

| Component | Evidence | Fleet mission use | Decision |
| --- | --- | --- | --- |
| Python 3 | `python/*.py`, `tests/test_*.py`, `requirements-dev.txt` | Fleet registry, inventory, enrollment helpers, action/provisioning workers, provider clients, hosted API, dashboard snapshots, tests | Primary implementation surface. |
| SQLite | `python/arclink_control.py` schema helpers and drift checks | Additive fleet tables/columns, enrollment tokens, probe history, audit chain, idempotency records | Reuse existing DB helpers and migrations; no new database. |
| Shell | `bin/deploy.sh`, `bin/*.sh`, `test.sh` | Canonical operator CLI, bootstrap script, probe wrapper, job-loop runner | Keep shell thin and test with `bash -n`; use `shellcheck` for new scripts. |
| Docker Compose | `compose.yaml`, `Dockerfile`, `bin/docker-job-loop.sh` | Control Node workers, action/provisioning workers, future inventory probe daemon | Add job-loop service; avoid new scheduler infrastructure. |
| SSH and Docker CLI | Docker image installs `openssh-client`, `rsync`, Docker CLI, compose plugin | Remote worker probe/deploy actions and bootstrap proof | Keep guarded by machine-mode opt-in, allowlists, key validation, and audit logging. |
| Provider APIs | `python/arclink_inventory_hetzner.py`, `python/arclink_inventory_linode.py`, `requests` | Hetzner/Linode create/list/delete/bootstrap orchestration | Use fake provider tests by default; live calls operator-gated. |
| Hosted API | `python/arclink_hosted_api.py`, `python/arclink_api_auth.py`, `python/arclink_http.py` | Enrollment callback and optional fleet health/admin surfaces | Follow existing body caps, auth, CSRF/CIDR, and redaction patterns. |
| Dashboard | `python/arclink_dashboard.py`, `web/` | Operator fleet health summary, no topology leakage to Captains | Reuse current snapshot/API client patterns. |
| Notification outbox | `python/arclink_notification_delivery.py`, control DB helpers | Host unreachable/degraded alerts, token expiry, audit-chain failure, capacity warnings | Reuse existing durable delivery rail. |
| Secret redaction | `python/arclink_evidence.py`, `python/arclink_secrets_regex.py` | Token, key, fingerprint, SSH/provider error redaction | Reuse; do not add a competing regex set. |

## Version Snapshot

| Lane | Public signal | Planning note |
| --- | --- | --- |
| Python validation | `requirements-dev.txt` includes jsonschema, PyYAML, requests, Playwright, pyflakes, ruff | New fleet code should stay standard-library first except existing requests/provider rails. |
| Web app | Next 15, React 19, TypeScript 5, ESLint 9, Playwright | Dashboard changes require web test/lint/build/browser proof when touched. |
| Runtime image | Node 22 Debian slim with Python, Docker CLI, compose plugin, SSH client, rsync, qmd, pinned Hermes runtime | Fleet daemon/bootstrap helpers can run in current image without new base image. |
| Compose jobs | Existing job-loop services for provisioner/action workers and background tasks | Inventory worker should use the same job-loop pattern. |

## Alternatives Compared

| Decision area | Preferred path | Alternatives | Reason |
| --- | --- | --- | --- |
| Database | Additive SQLite schema in `arclink_control.py` | Separate fleet DB or external service | Current control plane is SQLite-backed and tests already use temporary DBs. |
| Worker identity | HMAC enrollment token plus fingerprint attestation | SSH key-only; long-lived static token; client TLS certificates | HMAC token is simpler than cert management and stronger than SSH-only registration. |
| Probe transport | Control-plane pull over SSH to a fixed probe wrapper | Worker-pushed agent; direct arbitrary shell probe | Pull matches current architecture; wrapper narrows command surface. |
| Scheduling | Docker job-loop service | Cron, systemd timer inside container, bespoke daemon supervisor | Job-loop is already observable and used in the repo. |
| Provider abstraction | Extend existing Hetzner/Linode modules with fakeable operations | New provider framework | Existing modules and tests are enough for v1. |
| CLI automation | `deploy.sh control` plus JSON modes | New CLI binary | Canonical operator surface is already `deploy.sh control`. |
| Audit integrity | New per-inventory hash chain plus existing audit log entries | Generic audit log only | Hash chain gives explicit tamper evidence; audit log keeps cross-feature queryability. |

## External Integration Posture

| Integration | Local BUILD posture | Live posture |
| --- | --- | --- |
| SQLite control DB | Temporary DBs and migration tests | No private runtime DB reads. |
| SSH | Fake runners and loopback-only tests unless explicitly authorized | Remote non-loopback SSH is Phase 7/operator-gated. |
| Docker socket | Static and fake-worker tests for intentional access | No Docker install/upgrade/reconfigure in BUILD. |
| Hetzner/Linode | Fake API clients and idempotency tests | Real create/delete/list/probe calls are operator-gated. |
| Notification delivery | Outbox row assertions and fake transports | Live delivery proof remains gated. |
| Web/dashboard | Local unit/browser tests when touched | No production dashboard mutation. |
| Payments/providers/bots/Notion | Not needed for this mission's local BUILD | Blocked unless separately authorized. |

## Dependency Risks

- SSH/Docker behavior is hard to prove without live hosts. Tests must isolate
  command construction, allowlists, key validation, and fallback behavior; live
  proof remains an evidence gate.
- Provider API semantics differ between Hetzner and Linode. Idempotency should
  be implemented at ArcLink's operation layer, not assumed from providers.
- Shell bootstrap scripts can leak tokens through argv if designed poorly.
  Prefer stdin/files or one-time environment at the operator boundary, redact
  output, and never store cleartext tokens after mint.
- The current inventory statuses are `pending|ready|draining|degraded|removed`
  while fleet host statuses are `active|degraded|offline`. New health states
  should be mapped deliberately and documented.
- Web/dashboard fleet detail could leak operator topology to Captains if shared
  response shapes are reused. Keep operator and Captain payloads separate.

## Validation Dependencies

Minimum local validation for early BUILD phases:

```bash
git diff --check
python3 -m py_compile python/arclink_control.py python/arclink_fleet.py python/arclink_inventory.py python/arclink_executor.py python/arclink_sovereign_worker.py python/arclink_action_worker.py
python3 tests/test_arclink_fleet.py
python3 tests/test_arclink_inventory.py
python3 tests/test_arclink_action_worker.py
python3 tests/test_arclink_executor.py
python3 tests/test_arclink_sovereign_worker.py
python3 tests/test_arclink_schema.py
bash -n deploy.sh bin/*.sh test.sh
```

Additional validation as phases land:

```bash
python3 tests/test_arclink_fleet_enrollment.py
python3 tests/test_arclink_fleet_inventory_worker.py
python3 tests/test_arclink_inventory_hetzner.py
python3 tests/test_arclink_inventory_linode.py
python3 tests/test_deploy_regressions.py
```

When web files change:

```bash
cd web
npm test
npm run lint
npm run build
npm run test:browser
```
