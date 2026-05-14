# ArcPod Captain Console Implementation Plan

## Goal

Land the ArcPod Captain Console mission from
`research/RALPHIE_ARCPOD_CAPTAIN_CONSOLE_STEERING.md`: vocabulary canon,
onboarding Agent Name and Agent Title, fleet inventory, 1:1 Pod migration,
pod-to-pod comms, Crew Training, and ArcLink Wrapped.

The prior Sovereign audit plan is historical context only. Current source and
focused tests are ground truth where docs disagree.

## Constraints

- Do not touch `arclink-priv`, live secrets, user Hermes homes, deploy keys, production services, external provider accounts, payment/provider mutations, or Hermes core.
- Do not run live deploys, upgrades, Docker install/upgrade flows, public bot mutations, live Stripe/Chutes/Notion/Cloudflare/Tailscale/Hetzner/Linode proof, or credential-dependent checks without explicit authorization for the named flow.
- Preserve the Sovereign Control Node domain-or-Tailscale ingress intent while this ArcPod/Captain-facing work proceeds; live ingress proof remains explicitly operator-gated.
- Use existing ArcLink Python, Bash, SQLite, Compose, Next/web, Hermes plugin, notification, and MCP structures.
- Preserve dirty worktree changes that are not part of the active patch.
- Keep user-facing vocabulary aligned to ArcPod, Pod, Agent, Captain, Crew, Raven, and Comms. Keep Operator/deployment/user language on backend and admin/operator surfaces.
- Do not use browser/TLS impersonation or registration-control bypass tools.

## Selected Path

Implement the steering document in waves, starting with Wave 0 and Wave 1.

| Path | Strengths | Weaknesses | Decision |
| --- | --- | --- | --- |
| Wave-ordered scoped patches with focused tests | Matches dependency order, keeps risk bounded, and fits existing architecture | Requires multiple coordinated migrations and UI/API/bot updates | Selected. |
| Reuse the old Sovereign audit plan | Already researched | Does not match the current mission | Rejected. |
| One large end-to-end patch | Could reduce intermediate handoffs | High blast radius across schema, web, bots, fleet, migration, MCP, and notifications | Rejected. |
| Docs-only vocabulary update | Fast | Leaves verified UX and runtime gaps unresolved | Rejected. |

## Validation Criteria

BUILD handoff for each wave requires:

- source behavior implemented or explicitly deferred with operator-facing rationale;
- focused tests for schema, API, bot, web, worker, provider, migration, MCP, or notification contracts touched by the wave;
- no private-state reads or live mutations;
- docs updated only after behavior is true or a deferral is recorded;
- completion notes listing skipped live gates and remaining risks.

Terminal completion additionally requires all waves to be complete or explicitly
deferred item-by-item.

## Wave 0 - Vocabulary Canon, Schema Foundations, SOUL Template

Status: locally validated in BUILD on 2026-05-14. Candidate implementation is
present in the current dirty tree and passed the focused source, schema, API,
bot, deploy, shell, and web checks listed below, with the stale
`python/arclink_users.py` compile target omitted because that module does not
exist in this repo.

Tasks:

- [x] Add `docs/arclink/vocabulary.md` as the canonical vocabulary reference and mark it canonical in the docs status index if that index exists.
- [x] Add a short Captain/Crew/ArcPod/Raven/Operator recap to `AGENTS.md`.
- [x] Update Captain-facing docs and copy in the steering targets while preserving Operator/backend terminology.
- [x] Add schema migrations in `python/arclink_control.py`: `arclink_users.agent_title`, `captain_role`, `captain_mission`, `captain_treatment`, `wrapped_frequency`; `arclink_deployments.agent_name`, `agent_title`, `asu_weight`; `arclink_onboarding_sessions.agent_name`, `agent_title`; new inventory, pod messages, pod migrations, crew recipes, and wrapped reports tables.
- [x] Add drift/status checks for the new statuses and identity gaps.
- [x] Extend `templates/SOUL.md.tmpl` with additive optional vars for `$agent_title`, `$crew_preset`, `$crew_capacity`, `$captain_role`, `$captain_mission`, and `$captain_treatment`.
- [x] Preserve existing SOUL orientation and do not rewrite memory/session state.

Validation floor:

```bash
python3 -m py_compile python/arclink_control.py python/arclink_onboarding.py python/arclink_public_bots.py
python3 tests/test_arclink_schema.py
python3 tests/test_arclink_control_db.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_arclink_public_bots.py
cd web && npm test && npm run lint
```

## Wave 1 - Onboarding Agent Name And Agent Title

Status: locally validated in BUILD on 2026-05-14. Candidate implementation is
present in the current dirty tree and passed the focused API, onboarding, bot,
provisioning, web, and browser checks listed below.

Tasks:

- [x] Rework `web/src/app/onboarding/page.tsx` so the form captures Captain Name, Email, required Agent Name, and required Agent Title; persist identity fields in resume state; send `agent_name` and `agent_title` to the backend.
- [x] Update `python/arclink_onboarding.py` to validate, store, and propagate `agent_name` and `agent_title` from session answer through checkout metadata, entitlement/provisioning, and deployment identity rows.
- [x] For Scale multi-Pod sessions, document and implement the initial naming rule for Pods 2 and 3.
- [x] Update provisioning/SOUL materialization so `$agent_label` and `$agent_title` use the captured identity.
- [x] Extend `python/arclink_public_bots.py` with Captain-name copy plus `prompt_agent_name` and `prompt_agent_title` before package selection.
- [x] Add Telegram/Discord slash command support for `/agent-name`, `/agent-title`, `/agent-identity`, `/rename-agent`, and `/retitle-agent`.
- [x] Add authenticated dashboard/API rename and retitle support with CSRF, audit event, deployment row update, and managed-context identity refresh. API, dashboard, bot commands, audit, deployment row updates, and local identity projection are implemented. Remote fleet projection remains proof-gated until the Wave 2/3 worker transport path lands; the current helper skips rather than creating local lookalike paths when a Pod's Hermes home is not present on the control node.

Validation floor:

```bash
python3 tests/test_arclink_onboarding.py
python3 tests/test_arclink_public_bots.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_arclink_telegram.py
python3 tests/test_arclink_discord.py
cd web && npm test && npm run lint
```

Browser proof should assert required Agent Name and Agent Title inputs, resume
preservation, and mocked Stripe metadata carrying `arclink_agent_name` and
`arclink_agent_title`.

## Wave 2 - Fleet Inventory And ASU Placement

Status: locally validated in BUILD on 2026-05-14. Candidate implementation is
present in the current dirty tree and passed the focused fleet, ASU, provider,
deploy, shell, web, and browser checks listed below.

Tasks:

- [x] Add `./deploy.sh control inventory` menu and argv aliases for list, probe, add manual, add Hetzner, add Linode, drain, remove, and set-strategy.
- [x] Implement manual registration using the existing fleet SSH key guidance and fakeable probe commands.
- [x] Add `python/arclink_inventory_hetzner.py` and `python/arclink_inventory_linode.py` with fail-closed missing-token behavior, safe redaction, list/provision/probe/remove methods, and fake HTTP tests.
- [x] Add `python/arclink_asu.py` with pure ASU computation and load helpers.
- [x] Extend `python/arclink_fleet.py` with `ARCLINK_FLEET_PLACEMENT_STRATEGY=headroom|standard_unit`; keep `headroom` default.
- [x] Surface inventory and ASU load in the Operator dashboard and audit inventory events.
- [x] Document provider env vars and fail-closed behavior in the control-node runbook.

Implementation note: provider-backed `add hetzner` / `add linode` now fail
closed without tokens and expose safe list/provision/remove/probe adapter
methods with fake HTTP coverage. The deploy CLI lists provider inventory when
credentials are present; destructive cloud creation/removal remains explicit
inside the provider adapters and should stay operator-gated for live proof.

Validation floor:

```bash
python3 tests/test_arclink_fleet.py
python3 tests/test_arclink_asu.py
python3 tests/test_arclink_inventory_hetzner.py
python3 tests/test_arclink_inventory_linode.py
python3 tests/test_deploy_regressions.py
bash -n deploy.sh bin/*.sh test.sh
```

## Wave 3 - 1:1 Pod Migration

Status: next implementation wave after Waves 0 through 2 validate cleanly or
receive explicit project-specific deferrals.

Tasks:

- [ ] Add `python/arclink_pod_migration.py` with migration planning, capture, target materialization, health verification, rollback, audit, and idempotent replay.
- [ ] Add `arclink_pod_migrations` schema, status checks, source/target placement links, file digests, and rollback metadata.
- [ ] Wire admin `reprovision` to real migration/redeploy-in-place behavior and remove `pending_not_implemented` for the wired path.
- [ ] Preserve state capture boundaries for vault, memory, sessions, configs, secrets, DNS rows, placement, bots, and Hermes home.
- [ ] Gate Captain-initiated migration behind an explicit disabled-by-default flag until policy is decided.
- [ ] Add migration garbage collection for successful source-state retention.

Validation floor:

```bash
python3 tests/test_arclink_pod_migration.py
python3 tests/test_arclink_action_worker.py
python3 tests/test_arclink_sovereign_worker.py
python3 tests/test_arclink_executor.py
```

## Wave 4 - Pod Comms And Comms Console

Tasks:

- [ ] Add `python/arclink_pod_comms.py` for queued text and attachment-ref messages with same-Captain Crew scope by default.
- [ ] Extend share grants with `pod_comms` for cross-Captain comms.
- [ ] Add sender rate limiting, audit events, and notification outbox delivery.
- [ ] Register MCP tools for list/fetch/send/share-file under caller-scoped deployment authorization.
- [ ] Add Captain Comms Console and Operator Comms Console views and API routes.

Validation floor:

```bash
python3 tests/test_arclink_pod_comms.py
python3 tests/test_arclink_mcp_server.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_dashboard.py
cd web && npm test && npm run lint
```

## Wave 5 - Crew Training

Tasks:

- [ ] Add dashboard and public-bot Crew Training flow for Captain role, mission, treatment, preset, capacity, review, regenerate, and confirm.
- [ ] Add `templates/CREW_RECIPE.md.tmpl` and provider-backed recipe generation with deterministic fallback when live credentials are absent.
- [ ] Reject unsafe recipe output using existing unsafe-output/redaction boundaries.
- [ ] Write one active `arclink_crew_recipes` row per Captain, archive previous active recipes, and audit operator-on-behalf changes.
- [ ] Apply the Crew Recipe as an additive managed-context/SOUL overlay to each Pod in the Captain's Crew without touching memories or sessions.
- [ ] Add `/train-crew` and `/whats-changed` bot flows.

Validation floor:

```bash
python3 tests/test_arclink_crew_recipes.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_public_bots.py
cd web && npm test && npm run lint
```

## Wave 6 - ArcLink Wrapped

Tasks:

- [ ] Add `python/arclink_wrapped.py` to generate reports from events, audit, comms, session counts, vault/memory deltas, and memory synthesis cards.
- [ ] Produce at least five non-standard statistics per report with a documented novelty score formula.
- [ ] Add daily/weekly/monthly frequency preference with daily default and no more-frequent-than-daily behavior.
- [ ] Add scheduler service or job-loop integration and default config values.
- [ ] Deliver reports through `notification_outbox` and render history in the Captain dashboard; show only aggregate status/score in Operator views.
- [ ] Redact secrets before report rendering.

Validation floor:

```bash
python3 tests/test_arclink_wrapped.py
python3 tests/test_arclink_notification_delivery.py
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_hosted_api.py
cd web && npm test && npm run lint
```

## Build Notes Required At Completion

Final BUILD notes must include files changed by wave, migrations added,
environment defaults added, validation run, skipped live gates, unresolved
risks, and any explicit deferrals. Live infrastructure remains unproven unless
the operator separately authorizes named live proof.
