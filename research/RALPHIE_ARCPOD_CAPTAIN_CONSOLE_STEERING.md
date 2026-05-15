# Ralphie Steering: ArcPod Captain Console, Fleet Inventory, Crew Training, ArcLink Wrapped

## Current Mission

Land seven interlocking ArcLink product surfaces:

1. **Onboarding agent-name + agent-title input** on web, Telegram, and Discord public bots so a buyer can actually name and title their Agent during onboarding. Existing surface promises "Name The Agent" but only collects the buyer's display name. Fix the broken UX.
2. **Vocabulary migration**: introduce **ArcPod / Pod**, **Captain**, **Agent**, **Crew**, and keep **Raven** as the guide / Console Curator and **Operator** as the ArcLink platform owner term (operator/admin/management surfaces only).
3. **Pod-fleet inventory management** in `./deploy.sh control`: support local single-machine, manual remote-machine lists with paste-the-key onboarding, and cloud-provider API integration for Hetzner Cloud and Linode. Probe each registered machine for connectivity and hardware. Compute an **ArcPod Standard Unit** (ASU) per machine and use it in fair placement.
4. **1:1 Pod migration tool** so an Operator can upgrade a Captain's Pod to better hardware (or move it between machines) without losing vault, memory, sessions, configs, secrets, DNS, or fleet placement. The current `reprovision` admin action is `pending_not_implemented`; this mission wires it for real.
5. **Pod-to-pod comms + Comms Console**: agents in a Captain's Crew can send messages and share files between Pods. The Captain sees a unified Comms Console; the Operator sees a cross-Captain Comms Console for audit/management.
6. **Crew Training**: a character-creation-style flow (Fallout / Elder Scrolls / Cyberpunk feel) that captures the Captain's role and mission, asks how the Crew should treat them, then applies an LLM-driven Crew Recipe — a Crew preset (Space risk-takers, Corpos, Scrapers, Military) crossed with a Crew capacity (sales, marketing, development, life coaching, companionship). Outputs an additive SOUL overlay applied to every Pod in the Crew without wiping memories or sessions. Re-runnable any time.
7. **ArcLink Wrapped**: a periodic Captain-facing insights report (daily by default, configurable to weekly or monthly minimum). Reads Pod sessions, memory deltas, and event ledger; scores novel/non-standard insights; delivers to the Captain's home channel and dashboard.

Ralphie should treat code and focused regression tests as truth when docs disagree. Update docs after behavior is in place.

## Landing Status (2026-05-14)

This steering file remains the original mission spec. The implementation record
is now source, tests, and `research/BUILD_COMPLETION_NOTES.md`. The task
checkboxes below are preserved as the original build map; this landing section
is the authoritative closeout status for the six ArcPod Captain Console waves.

| Wave | Scope | Status |
| --- | --- | --- |
| 0 | Vocabulary canon, schema foundations, SOUL overlay variables, drift checks | Landed in `b32e1da` |
| 1 | Agent Name and Agent Title onboarding on web / Telegram / Discord, post-onboarding rename/retitle, identity projection | Landed in `b32e1da` |
| 2 | Fleet inventory, manual / Hetzner / Linode inventory providers, ArcPod Standard Unit, ASU-aware placement | Landed in `b32e1da` |
| 3 | 1:1 Pod migration and executable `reprovision` admin action | Landed in `aec064e` |
| 4 | Pod-to-Pod Comms, share-grant-gated cross-Captain comms, MCP tools, Captain/Operator Comms Console | Landed in `faf33dc` |
| 5 | Crew Training, Crew Recipes, deterministic fallback generation, `/train-crew`, `/whats-changed`, additive SOUL overlay | Landed in `5fd4aff` |
| 6 | ArcLink Wrapped report generation, scheduler, delivery, dashboard history, admin aggregate view, `/wrapped-frequency` | Complete in the final Wave 6 worktree; ready for final commit |

Closeout notes:

- The original onboarding defect is closed: the web `Name The Agent` step now
  accepts Agent Name and Agent Title, public bots prompt and command both
  fields, and identity flows through onboarding, Stripe metadata, deployments,
  provisioning, and managed-context projection.
- The Wave-0 schema is no longer orphan scaffolding: inventory, Comms,
  migration, Crew Training, and Wrapped each read/write their owning tables.
- Live provider and host proof remains operator-gated. No production deploy,
  upgrade, remote SSH migration, live Stripe/Chutes/Cloudflare/Tailscale,
  Telegram/Discord mutation, Notion proof, or live Wrapped delivery was run.

## Operating Guardrails

- Read `AGENTS.md` before changing deploy, onboarding, service, runtime, or knowledge code.
- Do not read `arclink-priv/`, user homes, secret files, live token files, deploy keys, or private runtime state unless a focused fix requires a specific non-secret path and the operator explicitly authorizes it.
- Do not print, log, commit, or quote secrets. Avoid argv/env exposure of bootstrap tokens, API keys, bot tokens, OAuth data, deploy keys, and `.env` contents. Use `arclink_secrets_regex.redact_then_truncate` for any operator-facing error text.
- Do not edit Hermes core. Use ArcLink wrappers, plugins, hooks, generated config, services, or docs.
- Do not run `./deploy.sh upgrade`, `./deploy.sh install`, live Stripe, live Cloudflare, live Tailscale, live Hetzner, live Linode, live Telegram, live Discord, or host-mutating production flows unless the operator explicitly asks during this mission.
- Prefer narrow, tested fixes over broad rewrites. Add regression tests for every boundary, journey, or feature gap that can be tested locally.
- Never convert an unverified external/tool/data claim into product truth. If a fact cannot be verified locally without secrets or live credentials, mark it as proof-gated or ask a concrete operator question instead of inventing a confident answer.
- Keep `ralphie.sh` changes separate from ArcLink product changes if commits are later requested.
- When the audit verification file `research/RALPHIE_SOVEREIGN_AUDIT_VERIFICATION_20260511.md` and the closure file `research/BUILD_COMPLETION_NOTES.md` disagree with current source, prefer current source. Both files are now historical.
- Open trust-boundary residuals tracked in `research/RALPHIE_SOVEREIGN_AUDIT_VERIFICATION_20260511.md` (curator single-step approval, `additional_agent_price_id` plan-blindness, secret cleanup on teardown, Cloudflare token in env, idempotency-surface split, control upgrade no git fetch, 5×Docker-sock-RW services) are out of scope for this mission unless a wave below specifically intersects them. Note interactions in completion notes but do not widen scope.

## Vocabulary Reference (Load-bearing)

This vocabulary is **the user-facing canon**. Apply it consistently across web pages, bot copy, dashboard labels, Notion guides, Raven copy, completion bundles, audit reasons (where surfaced to a Captain), error messages (where surfaced to a Captain), and docs. Operator-facing surfaces (admin dashboard sections, internal logs, audit reasons stored in DB, completion notes, research files, code module names, `arclink_sovereign_worker.py`, SQL table names, env-var names) keep their existing technical vocabulary.

| Term | Means | Where to use | Where NOT to use |
|---|---|---|---|
| **Raven** | The guide to ArcLink and the Curator of the Console. The public bot persona, the onboarding voice, the dashboard guide voice. | All Captain-facing copy, web hero/onboarding/dashboard, public bot replies, completion bundles, Wrapped emails. | Internal admin/operator screens. |
| **ArcPod** | A single Captain's provisioned deployment. Renames "Sovereign Pod" / "deployment" in Captain-facing copy. | All Captain-facing copy. | Module/file/table names (e.g. `arclink_deployments`, `arclink_sovereign_worker.py`) — keep as-is. |
| **Pod** | Short for ArcPod. Acceptable in fluent copy after the first occurrence of "ArcPod" in a given surface. | Captain-facing copy. | Operator screens (use "deployment" or "ArcPod" with operator context). |
| **Agent** | The Hermes-powered occupant of one ArcPod. One Agent per Pod. | Everywhere. (Already correct.) | n/a |
| **Captain** | A user who owns one or more ArcPods (their Crew). All paying users — Founders / Sovereign / Scale — are Captains. | Public bot copy, web pages, dashboard greetings, completion bundles, Wrapped reports, share-grant copy. | Backend audit reasons (use `user_id`), admin operator screens. |
| **Crew** | The inventory of Agents managed by one Captain. Scale plan = Crew of three Agents on three ArcPods. Sovereign / Founders = Crew of one. Agentic Expansion grows the Crew. | Captain-facing copy (already partially in place — `Show My Crew`, etc.). | n/a |
| **Operator** | The owner of the ArcLink platform — runs `./deploy.sh control install`, sees the admin dashboard, manages the fleet, registers cloud providers. | Operator/admin surfaces only — admin dashboard, deploy.sh menus, AGENTS.md, internal logs, completion notes. | Captain-facing copy. Never replace with "Captain" or vice versa. |
| **Comms** | Inter-Pod messaging within a Captain's Crew and (in the Operator view) across all Crews. | Captain dashboard "Comms" tab, agent tooling, audit. | n/a |
| **Comms Console** | The Captain's unified view of all Crew comms; and the Operator's view of all cross-Captain Crew comms. | Captain dashboard + admin dashboard. | n/a |
| **Crew Training** | The character-creation flow. | Captain dashboard + public-bot `/train-crew` command + web `/train-crew`. | n/a |
| **Crew Recipe** | The combined `preset × capacity × role × mission` definition that drives the SOUL overlay. | Captain-facing copy. Internally call this `crew_recipe` on the data side. | n/a |
| **ArcLink Wrapped** | The novelty-scored insights report. | Captain-facing copy. Internally `arclink_wrapped` module. | n/a |

Tone: keep Raven's existing maritime / orbital frontier voice from `docs/arclink/CREATIVE_BRIEF.md` and `docs/arclink/raven-public-bot.md`. Captain greetings continue the existing pattern ("Captain &lt;name&gt;, payment cleared..."). Do not invent new metaphors.

## Mission Success Criteria

- Web `/onboarding` collects **Agent Name** and **Agent Title** as separate required inputs in addition to the existing Captain display name and email. The H2 promise ("Name The Agent") matches a field that actually accepts the agent name. Subsequent screens render the agent name back to the Captain as confirmation. The captured agent name + title flow through `open_arclink_onboarding_checkout` → Stripe metadata → entitlement → provisioning intent → `arclink_users.agent_name` and the new `arclink_users.agent_title` column (or wherever the title belongs per Wave 0 schema design).
- Public Telegram and Discord bots gain a dedicated `prompt_agent_name` and `prompt_agent_title` pair (or one combined `Name your Agent + Title` flow) before the package selection step. The existing `prompt_name` (which captures the **Captain's** display name) is preserved with renamed copy that says "Captain name" not "Display Name."
- Captains can rename and re-title their Agent at any time through both the dashboard and the public bot (`/rename-agent <name>` and `/retitle-agent <title>` or a unified `/agent-identity`).
- The user-facing surfaces consistently say **ArcPod / Pod / Captain / Crew / Raven** per the Vocabulary Reference. The Operator surfaces continue to say "deployment / user / operator." Both vocabularies render correctly side-by-side where a single page bridges them (admin dashboard Captain detail panel).
- `./deploy.sh control` gains an **inventory** submenu that lists every machine known to the fleet, shows ArcPod Standard Unit (ASU) capacity and current load, can add machines via Hetzner API / Linode API / manual public-key paste, can probe a machine for connectivity + hardware, and can drain/cordon/remove a machine.
- Hetzner and Linode integrations live behind explicit operator opt-in env vars (`HETZNER_API_TOKEN`, `LINODE_API_TOKEN`). Without those, the API panels say "configure provider to enable." Manual-machine mode continues to work without any cloud credentials.
- Pod placement uses ASU-fair selection rather than raw capacity_slots (existing model) when the operator opts in via `ARCLINK_FLEET_PLACEMENT_STRATEGY=standard_unit`. The legacy headroom-deterministic path remains as default fallback so existing placements do not break.
- A Captain (or Operator on the Captain's behalf) can run a Pod migration: select source Pod, select target machine (or "redeploy in place"), confirm. The migration captures vault, memory, sessions, configs, secrets, DNS, placement, Hermes home; re-applies on target; restores; verifies health; emits audit events. The `reprovision` admin action is wired to call this. Migration is idempotent and rollback-safe per the existing `arclink_operation_idempotency` contract.
- Agents in a Captain's Crew can exchange comms (text + file references) through a brokered pod-to-pod surface. The Comms Console renders the inventory on both Captain and Operator dashboards. Comms cross-Captain require explicit Captain-to-Captain share-grants (extends existing `arclink_share_grants`).
- A Captain can run **Crew Training** through the dashboard or the public bot. The flow walks a character-creation set of choices, captures the Captain's role + mission + how-to-be-treated, picks a Crew preset and capacity, applies a Crew Recipe as an additive SOUL overlay across every Agent in the Crew without dropping memories or sessions. Re-running Crew Training updates the recipe; old recipes are archived for the audit trail.
- **ArcLink Wrapped** generates a Captain-facing insights report on a daily/weekly/monthly cadence (per-Captain choice; minimum 1 week — anything more frequent than daily is rejected; "daily" is the default). Wrapped scores at least five novel non-standard statistics per period (examples below). Delivery rides the existing `notification_outbox` rail to the Captain's home channel and shows in the dashboard. Operator-side scheduler service joins compose under existing `docker-job-loop.sh` patterns.
- Every wave has focused regression coverage. Live infra remains operator-gated; nothing in this mission requires live deploys, payments, or provider mutation to land.

## Phase Strategy

Ralphie should not try to land all seven surfaces in one giant patch. Use waves. Each wave runs the existing loop:

1. Confirm current behavior in code and tests.
2. For each hole, write the possibility set: at least three distinct plausible fixes when three exist, plus the unknowns that would change the choice.
3. Add or update focused regression coverage where practical.
4. Implement the fix without widening scope.
5. Run the narrow validation floor.
6. Update the closest docs only after behavior exists.

Waves are ordered to minimize coupling: vocabulary + schema first so later waves can rely on canon vocabulary; onboarding fix next so the broken UX is closed quickly; inventory and migration follow because they share fleet/placement code; comms before training because training writes to comms history; Wrapped last because it consumes outputs of every prior wave.

## Wave 0: Vocabulary Canon + Schema Foundations

### Vocabulary canon

- [ ] Add `docs/arclink/vocabulary.md` as the canonical reference. Mark it Canonical in `docs/DOC_STATUS.md`.
- [ ] Add a one-paragraph "Captain / Crew / ArcPod / Raven / Operator" recap to `AGENTS.md` so future Ralphie iterations have it at first read.
- [ ] Update `docs/arclink/CREATIVE_BRIEF.md`, `docs/arclink/raven-public-bot.md`, `docs/arclink/first-day-user-guide.md`, `docs/arclink/sovereign-control-node.md`, `docs/arclink/notion-human-guide.md` to use the canon. Where these docs describe Operator/admin flows, retain "Operator." Where they describe paying-user flows, switch to "Captain." Mark "ArcPod" / "Pod" on first mention.
- [ ] **Do not rename**: `python/arclink_sovereign_worker.py`, `python/arclink_control.py` table names, env-var names, audit-event names, journey-step names, OpenAPI route names. These are technical/operator surface.

### Captain-facing copy migration

- [ ] Replace "Sovereign Pod" / "Sovereign deployment" / "deployment is live" in user-facing strings inside `python/arclink_public_bots.py`, `python/arclink_onboarding_completion.py`, `python/arclink_onboarding_flow.py`, `python/arclink_dashboard_auth_proxy.py` HTML, and `web/src/app/**` with "ArcPod" / "Pod" / "Pod is live". When the string is a label inside a server-rendered response, change the label only — leave underlying field names, JSON keys, and DB columns alone.
- [ ] Audit Raven completion-bundle copy and `_queue_paid_ping` / `_queue_vessel_online_notifications` / `_queue_billing_noncurrent_ping` text for old "deployment" language.
- [ ] Captain greeting pattern: "Captain &lt;name&gt;, ..." for paid pings and Wrapped notifications. Existing pattern in `_queue_paid_ping` already uses this — preserve.

### Schema additions

Apply via `ensure_schema` migrations in `python/arclink_control.py` and matching `arclink_drift_checks` entries:

- [ ] `arclink_users.agent_title TEXT NOT NULL DEFAULT ''` — the Title used in Captain-facing copy ("Bob, the know-it-all"). Per-Captain, applied to each Agent in the Captain's Crew unless the per-deployment row overrides. Backfill empty.
- [ ] `arclink_deployments.agent_name TEXT NOT NULL DEFAULT ''` and `arclink_deployments.agent_title TEXT NOT NULL DEFAULT ''` — per-Pod name and title. Per-Pod field wins over per-Captain default. Backfill from `agents.agent_name` where available, else from the existing random readable prefix as a placeholder pending rename.
- [ ] `arclink_users.captain_role TEXT NOT NULL DEFAULT ''`, `arclink_users.captain_mission TEXT NOT NULL DEFAULT ''`, `arclink_users.captain_treatment TEXT NOT NULL DEFAULT ''` — Crew Training inputs about how the Crew should treat the Captain. Used by Wave 5.
- [ ] `arclink_crew_recipes` new table: `(recipe_id, user_id, preset, capacity, role, mission, treatment, soul_overlay_json, applied_at, archived_at, status ∈ {active, archived, superseded})` with unique partial index on `(user_id) WHERE status='active'`.
- [ ] `arclink_pod_messages` new table: comms outbox `(message_id, sender_deployment_id, recipient_deployment_id, sender_user_id, recipient_user_id, body, attachments_json, status ∈ {queued, delivered, failed, redacted}, created_at, delivered_at, audit_id)`. Recipient may be same Captain (within-crew) or different Captain (cross-Captain, only when an active share-grant exists).
- [ ] `arclink_inventory_machines` new table: `(machine_id, provider ∈ {local, manual, hetzner, linode}, provider_resource_id, hostname, ssh_host, ssh_user, region, status ∈ {pending, ready, draining, degraded, removed}, asu_capacity REAL, asu_consumed REAL, hardware_summary_json, connectivity_summary_json, registered_at, last_probed_at)`. Joins `arclink_fleet_hosts.host_id` via a `machine_host_link` column or by FK.
- [ ] `arclink_wrapped_reports` new table: `(report_id, user_id, period ∈ {daily, weekly, monthly}, period_start, period_end, status ∈ {pending, generated, delivered, failed}, ledger_json, novelty_score REAL, delivery_channel, created_at, delivered_at)`.
- [ ] Drift checks: `agent_title_unknown_user`, `pod_message_status_invalid`, `inventory_machine_status_invalid`, `wrapped_report_status_invalid`, `crew_recipe_status_invalid`.

### SOUL template additions (additive only)

- [ ] Extend `templates/SOUL.md.tmpl` with new optional sections wrapped in `{{#if $crew_recipe_active}} ... {{/if}}`-style guards (use the existing `$var` substitution conventions):
  - `$agent_title` — woven into the introduction (e.g. "I'm $agent_label, $agent_title").
  - `$crew_preset` — adjusts tone ladder: Space risk-takers / Corpos / Scrapers / Military.
  - `$crew_capacity` — adjusts mission ladder: sales / marketing / development / life coaching / companionship.
  - `$captain_role`, `$captain_mission`, `$captain_treatment` — adjusts how the agent addresses and treats the Captain.
- [ ] Preserve the existing SOUL body verbatim above the new overlay so existing Agents do not lose orientation. Crew Training writes the overlay to `soul_overlay_json`; the runtime composes Final SOUL = base SOUL + overlay every refresh.
- [ ] Do not rewrite memories. Crew Training MUST NOT touch `state/arclink-vault-reconciler.json` or any prior conversation context. The SOUL change is the only persona-shifting write.

### Validation floor (Wave 0)

```bash
python3 -m py_compile python/arclink_control.py python/arclink_users.py python/arclink_public_bots.py python/arclink_onboarding.py
python3 tests/test_arclink_schema.py
python3 tests/test_arclink_control_db.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_arclink_public_bots.py
cd web && npm test && npm run lint
```

## Wave 1: Onboarding Agent Name + Title

### Web onboarding

- [ ] In `web/src/app/onboarding/page.tsx`: the existing `step === "questions"` form currently has only a "Display Name" (Captain) input and an Email input. Rework:
  - Rename existing field to "Captain Name" (label and placeholder). The form already has `name` state — keep it but rename to `captainName` for clarity.
  - Add a required "Agent Name" input bound to new `agentName` state. Placeholder: "Bob" / "Vane" / "Atlas". Max 40 chars. Required.
  - Add a required "Agent Title" input bound to new `agentTitle` state. Placeholder: "the know-it-all" / "the marketing guy" / "your right hand". Max 80 chars. Required.
  - Reorder H2 to match the field set ("Name Your Agent" or keep "Name The Agent" with subheading).
  - Persist `agentName` and `agentTitle` into `ResumeState` localStorage so refresh / Stripe cancel preserves them.
  - Send `agent_name` and `agent_title` in the `api.answerOnboarding(...)` body. Backend will route them.
- [ ] In `python/arclink_onboarding.py`: `answer_arclink_onboarding_session` and `_handle_public_onboarding_answer` accept `agent_name` and `agent_title`, validate (non-blank, ≤40 chars name, ≤80 chars title, reject `_reject_secret_material` patterns), and persist to `arclink_onboarding_sessions.agent_name`/`agent_title` columns (add them to the table).
- [ ] When `prepare_arclink_onboarding_deployment` mints the deployment row, copy `agent_name`/`agent_title` from the onboarding session onto `arclink_deployments.agent_name`/`agent_title`. For Scale-plan multi-Pod sessions, use the same agent name + title for Pod #1 and append " (Ensign)" / " (Chief)" / " (Bosun)" or similar to Pod #2 and Pod #3, or prompt for one set per Pod in a future revision (out of scope for this wave — document the choice).
- [ ] When `_apply_deployment` materializes the SOUL during provisioning, substitute `$agent_label = agent_name`, `$agent_title = agent_title`.

### Telegram + Discord public bot

- [ ] In `python/arclink_public_bots.py`: extend the question ladder. After `/start` greeting and the existing Captain-name capture (rename from "display name" to "Captain name" in copy), add `prompt_agent_name` then `prompt_agent_title` before `prompt_package`.
- [ ] Add slash commands: `/agent-name <name>` and `/agent-title <title>`, plus a combined `/agent-identity <name>, <title>`. Each rejects bot-token-shaped strings via `_reject_secret_material` and re-emits the package prompt when the captain has answered both.
- [ ] Keep the menu compact: a tap button "Name your Agent" walks the Captain through the same two-step input.
- [ ] On Discord, register the corresponding application commands in `arclink_discord.py` and `python/arclink_public_bot_commands.py`.
- [ ] For existing onboarding sessions in `collecting` / `checkout_open` / `paid` / `provisioning_ready` without agent_name set, accept inbound `/agent-name` and `/agent-title` post hoc as long as the Pod is not yet `first_contacted`. After first contact, route to dashboard rename surface.

### Post-onboarding rename / retitle

- [ ] In `python/arclink_api_auth.py`: add `user_rename_agent_api(conn, session_id, deployment_id, agent_name, agent_title)` and `user_retitle_agent_api` (or one merged `user_update_agent_identity_api`). Cookie + CSRF. Records audit `agent_identity_renamed:<deployment_id>` with `{old_name, new_name, old_title, new_title}`. Updates `arclink_deployments.agent_name`/`agent_title`, then queues a worker action so the new SOUL substitution lands on the next refresh.
- [ ] Add the matching hosted-API route `POST /api/v1/user/agent-identity` and Captain-dashboard form.
- [ ] Public bot: `/rename-agent <name>` and `/retitle-agent <title>` on Telegram + Discord. Validation per Wave 0 schema. Same audit.
- [ ] Worker pickup: when an Agent's name/title changes, write the substitution to `$HERMES_HOME/state/arclink-identity-context.json` so the `arclink-managed-context` plugin re-injects on the next turn. Do not restart the gateway.

### Validation floor (Wave 1)

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

Web browser tests in `web/tests/browser/product-checks.spec.ts` must assert: the onboarding form contains "Agent Name" and "Agent Title" required inputs; the value typed in those inputs is preserved across resume; the Stripe metadata payload (mocked) carries `arclink_agent_name` and `arclink_agent_title`.

## Wave 2: Fleet Inventory Management

### deploy.sh inventory submenu

- [ ] Add a new top-level entry to the `./deploy.sh control` menu: **Inventory** (item 13 or similar; renumber Stop/Teardown/Exit as needed). Subcommands:
  - `control inventory list` — render the full machine table with provider, hostname, status, ASU capacity, ASU consumed, last probe timestamp.
  - `control inventory probe <machine-id|hostname>` — re-run the connectivity + hardware probe.
  - `control inventory add manual` — interactive ritual: ask for hostname, SSH host, SSH user, region, tags. Print the ArcLink Operator public key for the operator to install on the remote `authorized_keys` (re-uses `print_control_fleet_ssh_key_guidance`). Smoke-test ssh → docker --version → df → free → nproc, write row.
  - `control inventory add hetzner` — guarded by `HETZNER_API_TOKEN`. Lists existing Hetzner servers via Cloud API and lets the operator pick one or provision a new one (server type + image + location). Captures the public key automatically into the project key. Records resource id.
  - `control inventory add linode` — same shape, guarded by `LINODE_API_TOKEN`. Linode Instances API.
  - `control inventory drain <machine-id>` — `arclink_fleet.drain_host` flips the row, no new placements pick this host, existing Pods are not affected. Marks for operator-initiated migration.
  - `control inventory remove <machine-id>` — refuses if active placements exist; offers migrate-first guidance.
- [ ] All command shortcuts get exposed at the deploy.sh argv layer (`control-inventory`, `control-inventory-list`, etc.).
- [ ] If `HETZNER_API_TOKEN` / `LINODE_API_TOKEN` are missing, the cloud subcommands print "Configure $token to enable" and return non-zero. Document in `docs/arclink/control-node-production-runbook.md`.

### Provider modules

- [ ] `python/arclink_inventory_hetzner.py` — Hetzner Cloud API v1 wrapper. Endpoints used:
  - `GET /servers` — list
  - `GET /server_types` — for ASU computation
  - `POST /servers` — provision (optional, behind `--provision` flag)
  - `GET /servers/{id}` — refresh
  - `DELETE /servers/{id}` — only via explicit `inventory remove --destroy`
  - `POST /ssh_keys` — register the project key once
  - Authenticate with `HETZNER_API_TOKEN`. Treat blank as misconfigured (raises). Cache responses for 60s within a session. Redact any token in error messages via `redact_then_truncate`.
- [ ] `python/arclink_inventory_linode.py` — Linode API v4 wrapper. Endpoints:
  - `GET /linode/instances` — list
  - `GET /linode/types` — for ASU
  - `POST /linode/instances` — provision (optional)
  - `GET /linode/instances/{id}` — refresh
  - `DELETE /linode/instances/{id}` — explicit destroy only
  - `POST /profile/sshkeys` — register the project key once
  - Authenticate via `LINODE_API_TOKEN`.
- [ ] Both modules must be fail-closed: blank token → `InventoryProviderError("$provider token missing")`. Failed HTTP → safe-error.
- [ ] Both modules expose a `probe(machine)` method that runs `ssh -i $fleet_key BatchMode=yes StrictHostKeyChecking=accept-new $user@$host -- 'nproc; cat /proc/meminfo | head -3; df -BG / /var/lib/docker; docker --version; docker compose version'` and parses the result into `hardware_summary_json`.

### ArcPod Standard Unit (ASU)

The ASU is the unit by which we measure how many Pods a machine can host. Define:

```
ASU = min(
  floor(vCPU_cores / ARCLINK_ASU_VCPU_PER_POD),         # default 1
  floor(RAM_GiB    / ARCLINK_ASU_RAM_PER_POD),          # default 4
  floor(DISK_GiB   / ARCLINK_ASU_DISK_PER_POD)          # default 30
)
```

Env knobs persisted in docker.env. Defaults shipped: 1 vCPU + 4 GiB RAM + 30 GiB disk per Pod. The probe captures actual numbers; the ASU is computed at probe time and persisted on `arclink_inventory_machines.asu_capacity`.

- [ ] Add `python/arclink_asu.py` that exposes `compute_asu(hardware_summary, env)` and `current_load(machine_id, conn)` (counts active placements). Pure function, no I/O.
- [ ] Add unit tests covering edge cases: 0 vCPU (raises), tiny disk (returns 0 ASU = unusable), oversized machine, missing field.

### Placement strategy

- [ ] `python/arclink_fleet.py`: add `ARCLINK_FLEET_PLACEMENT_STRATEGY` env-driven branch in `_filter_placement_candidates` and `place_deployment`:
  - `headroom` (default, existing) — sort by `(-headroom, hostname)`.
  - `standard_unit` (new) — sort by `(-asu_available, hostname)` where `asu_available = asu_capacity - asu_consumed`. Reject hosts with `asu_available < 1`.
- [ ] The Inventory submenu surfaces both numbers. Operator can switch via `./deploy.sh control inventory set-strategy standard_unit`.
- [ ] Documentation: explain that `standard_unit` is "fair" — every Captain's Pod consumes 1 ASU regardless of plan tier. If a future plan adds heavier Pods, extend ASU consumption per-deployment via `arclink_deployments.asu_weight` (out of scope for this wave; record as forward-looking).

### Operator dashboard

- [ ] Extend `arclink_dashboard.build_scale_operations_snapshot` with an `inventory` section: machines + ASU table. The admin web page renders it as a tab.
- [ ] Audit events `inventory_machine_registered`, `inventory_machine_probed`, `inventory_machine_drained`, `inventory_machine_removed` flow into the existing audit table.

### Validation floor (Wave 2)

```bash
python3 tests/test_arclink_fleet.py
python3 tests/test_arclink_asu.py                # new
python3 tests/test_arclink_inventory_hetzner.py   # new — fake provider
python3 tests/test_arclink_inventory_linode.py    # new — fake provider
python3 tests/test_deploy_regressions.py
bash -n bin/*.sh deploy.sh
```

Live Hetzner / Linode calls remain operator-gated. Tests stub the HTTP layer.

## Wave 3: 1:1 Pod Migration

### Migration captures

A migration must capture every piece of Captain state that lives in a Pod:

1. **Vault** — the per-Captain `arclink-priv/vault` slice for the Captain's user (or per-Pod `vault/` under the state root) — `rsync -a --info=progress2` to a staging area.
2. **Memory** — `state/memory/` and `state/arclink-vault-reconciler.json` and any qmd index state.
3. **Sessions** — Hermes session files under `state/hermes-home/sessions/` (per-Captain user; do not cross uid).
4. **Configs** — `.env` files, plugin configs under `state/hermes-home/{config.yaml,skills,plugins,cron}`.
5. **Secrets** — `<secret_store_dir>/<deployment_id>/` and per-Captain dashboard password file. These never traverse outside the Operator's `arclink-priv` tree.
6. **DNS** — `arclink_dns_records` rows for the source deployment.
7. **Placement** — `arclink_deployment_placements` row.
8. **Bots** — `TELEGRAM_BOT_TOKEN` / `DISCORD_BOT_TOKEN` env values; `discord_home_channel_id`; `telegram_home_channel`.
9. **Hermes home** — full `state/hermes-home/` tree (excluding `secrets/` which is handled separately).

### Migration steps

1. Operator (or Captain via dashboard, gated by Wave 3 CSRF) calls `POST /api/v1/admin/actions` with `action_type=reprovision` and metadata `{target_machine_id, reason, dry_run?}` (or the user-facing `POST /api/v1/user/pod-migrate`).
2. Dispatcher routes to `python/arclink_pod_migration.py:migrate_pod(conn, executor, deployment_id, target_machine_id, ...)`.
3. The migration creates a Migration row in `arclink_pod_migrations` (new table) with status `planned`.
4. **Drain source**: stop the Hermes gateway service (`systemctl stop arclink-user-agent-gateway.service` via `runuser` or container exec). Mark deployment `migrating`.
5. **Capture**: rsync the state tree from source machine to operator staging area `<state_root_base>/.migrations/<migration_id>/`. For local executor this is a local rsync; for SSH executor, an rsync over SSH using the fleet key. Capture digest of every file for integrity verification.
6. **Plan target**: render the new provisioning intent with the new placement, new state root.
7. **Materialize**: push the staged state to the target via rsync (or local move). Apply Compose on target.
8. **Verify**: run health probes (the same `ARCLINK_SOVEREIGN_HANDOFF_REQUIRES_HEALTHY_SERVICES` gate from existing apply); verify Captain can reach the new dashboard URL; verify the Hermes session continuity by checking the session manifest hashes.
9. **Update DNS**: re-point CNAMEs (domain mode) or update Traefik labels (Tailscale mode); rely on existing ingress reconciliation.
10. **Mark done**: source placement → `removed`, target placement → `active`; deployment row updated with new state_roots; migration row → `succeeded`. Source's Hermes home is preserved on the source machine for 7 days for rollback, then garbage-collected by a new `migration-gc` periodic job.
11. **Audit**: `pod_migration_started`, `pod_migration_completed`, with both the source and target placements referenced.

### Idempotency and rollback

- [ ] Migration ID `mig_<token_hex(12)>`; idempotency-key for executor operations: `arclink:migration:<migration_id>`. Re-running the same migration_id returns the previous result.
- [ ] If verification fails: re-point source placement to `active`, restart source's Hermes gateway, mark migration `failed`. Emit `pod_migration_rolled_back`.
- [ ] Migration GC: garbage-collect successful migrations' source state after `ARCLINK_MIGRATION_GC_DAYS` (default 7).

### Hooks

- [ ] Wire the admin-action `reprovision` to call `migrate_pod` with `target_machine_id=current` for "redeploy in place" semantics.
- [ ] Surface "Upgrade hardware" button in the Captain dashboard that calls `/api/v1/user/pod-migrate` with `target_machine_id=<choice>` only when the Captain has the Operator-granted ability (controlled by a new env / plan flag — for now gate by `ARCLINK_CAPTAIN_MIGRATION_ENABLED=0` default off, document as Operator-only feature).
- [ ] Remove `pending_not_implemented` for `reprovision` and add `reprovision` (or new `migrate`) to `ARCLINK_EXECUTABLE_ADMIN_ACTION_TYPES`.

### Validation floor (Wave 3)

```bash
python3 tests/test_arclink_pod_migration.py    # new
python3 tests/test_arclink_action_worker.py
python3 tests/test_arclink_sovereign_worker.py
python3 tests/test_arclink_executor.py
```

Tests must cover: capture roundtrip, target apply, verification success, verification failure → rollback, idempotent replay.

## Wave 4: Pod-to-Pod Comms + Comms Console

### Pod comms primitive

- [ ] `python/arclink_pod_comms.py`: `send_pod_message(conn, sender_deployment_id, recipient_deployment_id, body, attachments=None, allow_cross_captain=False)` enqueues a row in `arclink_pod_messages` and a notification in the notification outbox. The recipient agent reads its inbox via a new MCP tool `pod_inbox.list` / `pod_inbox.fetch`.
- [ ] Cross-Captain comms require an active `arclink_share_grants` row with `resource_kind='pod_comms'` (extend existing share-grant resource_kinds). The CSRF/cookie share-grant flow already exists; add `pod_comms` to `RESOURCE_KINDS_ALLOWED`.
- [ ] Attachments use the existing share-grant projection model — never carry raw files in the message body.
- [ ] Rate limit: 60 messages per minute per sender, scope `pod_comms:<sender_deployment_id>`.
- [ ] Audit: `pod_message_sent`, `pod_message_delivered`, `pod_message_redacted`.

### MCP tools for agents

- [ ] Register on `arclink-mcp` (per the existing pattern in `python/arclink_mcp_server.py`):
  - `pod_comms.list` — paginated inbox/outbox view. Caller-scoped (the agent only sees its own deployment's traffic).
  - `pod_comms.send` — body + optional attachment refs; refuses send to a non-Crew deployment without a share-grant.
  - `pod_comms.share-file` — extends an active share-grant to a comms attachment.

### Comms Console (Captain dashboard)

- [ ] `web/src/app/dashboard/page.tsx`: new "Comms" tab. Lists comms across the Captain's Crew. Filter by sender/recipient/period. Read-only initial cut.
- [ ] `web/src/app/admin/page.tsx`: new "Comms" admin tab. Same data, cross-Captain, with Captain identity exposed.
- [ ] API: `GET /api/v1/user/comms` (Captain-scoped) and `GET /api/v1/admin/comms` (CIDR-gated; all Captains).

### Validation floor (Wave 4)

```bash
python3 tests/test_arclink_pod_comms.py        # new
python3 tests/test_arclink_mcp_server.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_dashboard.py
cd web && npm test && npm run lint
```

## Wave 5: Crew Training (Character Creation Style)

### Flow

1. The Captain opens **Crew Training** from the dashboard or `/train-crew` in the bot.
2. Question 1: **Your role** (free-form; suggestions: "founder building a startup," "marketing director," "household coordinator," "creative writer," "field engineer"). Persists to `arclink_users.captain_role`.
3. Question 2: **Your mission** (free-form; "what should your Crew help you ship in the next 12 weeks"). Persists to `arclink_users.captain_mission`.
4. Question 3: **How should your Crew treat you?** (radio: "Like a Captain — formal, ready to take orders" / "Like a peer — casual, give pushback" / "Like a coach — supportive, ask great questions" / "Custom — describe in one line"). Persists to `arclink_users.captain_treatment`.
5. Question 4: **Pick a Crew preset** (radio with character-art card):
   - **Frontier (Space risk-takers)** — bold, opportunistic, willing to improvise. Maritime/orbital voice. Suits ambiguous, fast-moving work.
   - **Concourse (Corpos)** — proper, process-aware, formal. Suits compliance-heavy or regulated work.
   - **Salvage (Scrapers)** — resourceful, frugal, makes the most of available data. Suits bootstrapped or constraint-driven work.
   - **Vanguard (Military)** — directive, regimented, mission-first. Suits operations work where order matters.
6. Question 5: **Pick a Crew capacity** (radio): Sales / Marketing / Development / Life Coaching / Companionship. The selected capacity informs the SOUL overlay tone and the recommended skill set.
7. Question 6: **Review the Crew Recipe** — Raven generates a one-paragraph recipe via the configured LLM provider (Chutes by default) summarizing role + mission + treatment + preset + capacity + per-Pod count. The Captain confirms or asks to regenerate.
8. On confirm: a new `arclink_crew_recipes` row is written `status='active'`, previous active row archived. The recipe's `soul_overlay_json` is computed (templated below). Every Pod in the Captain's Crew gets the overlay applied to `state/arclink-identity-context.json` on the next refresh.

### LLM-driven recipe

The recipe generator must use the existing provider boundary:

- Default model: the Captain's per-Captain Chutes credential (existing per-deployment Chutes lifecycle). Falls back to `ARCLINK_CREW_RECIPE_FALLBACK_MODEL` if unset.
- Prompt template: `templates/CREW_RECIPE.md.tmpl` (new). Inputs: role, mission, treatment, preset, capacity, pod_count. Output: one paragraph natural-language recipe + a JSON soul-overlay block.
- Reject any model output that contains URLs, shell commands, jailbreak patterns (re-use `arclink_memory_synthesizer._card_has_unsafe_output` if convenient). Regenerate up to 2 times before falling back to a deterministic preset-only overlay.
- Crew Training runs entirely in dry-run mode if no Chutes credential is configured for the Captain — the dashboard shows "Live recipe generation requires Chutes credentials. Using preset-only overlay." with truthful copy.

### SOUL overlay schema

```json
{
  "agent_label": "Bob",
  "agent_title": "the know-it-all",
  "crew_preset": "Frontier",
  "crew_capacity": "Development",
  "captain_role": "founder shipping a small SaaS",
  "captain_mission": "land 50 paying customers by Q3",
  "captain_treatment": "peer",
  "applied_at": "2026-05-13T10:00:00Z"
}
```

The `arclink-managed-context` plugin reads this overlay on the next `pre_llm_call` and weaves it into the rendered SOUL via the new `$crew_*` and `$captain_*` substitution vars. Memory is untouched. Sessions continue.

### Re-running

- [ ] Captain can re-run Crew Training at any time. The previous recipe is archived, not deleted. A `/whats-changed` Raven command shows the current vs prior recipe.
- [ ] Operator can re-run training on a Captain's behalf via admin dashboard (audited).

### Validation floor (Wave 5)

```bash
python3 tests/test_arclink_crew_recipes.py     # new
python3 tests/test_arclink_provisioning.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_public_bots.py
cd web && npm test && npm run lint
```

Browser test: walk the Crew Training questionnaire end-to-end, assert the resulting recipe persists, assert the agent identity context file picks up the change without restarting Hermes.

## Wave 6: ArcLink Wrapped

### Periodic insights pipeline

- [ ] `python/arclink_wrapped.py`: `generate_wrapped_report(conn, user_id, period, period_start, period_end)`. Reads:
  - `arclink_events` for Captain's deployments
  - `arclink_audit_log` entries scoped to the Captain
  - `arclink_pod_messages` for comms volume / interesting recipients
  - Hermes session counts (via local job-status scanner on the agent's home — read-only, no uid crossing)
  - `state/arclink-vault-reconciler.json` delta digest (per-Pod)
  - `memory_synthesis_cards` for new cards in the window
- [ ] Compute novelty score: a weighted sum of (number of net-new cards) × (avg recipe drift) × (interaction breadth) × (rare-event count). Document the formula in `docs/arclink/arclink-wrapped.md`.
- [ ] Emit at least five **non-standard statistics** per period. Examples (Ralphie can choose its own set; the bar is "interesting, not obvious"):
  - "Your most replayed memory card was '<title>' — opened N times this <period>."
  - "Crew sentiment shifted from <X> to <Y> mid-<period>."
  - "Hermes spent <N> minutes researching <topic>, the most of any single thread."
  - "Crew composed <N> Notion writes and <M> SSOT approvals, a <delta>% change from prior <period>."
  - "Longest agent silence: <duration> on <date>."
  - "Most-asked question this <period>: '<paraphrased>'."
  - "Rarest event observed: <event_type> (first time in <window>)."
- [ ] Render the report as both plain text (for chat delivery) and Markdown (for web display).

### Scheduler

- [ ] New compose service `arclink-wrapped` (or fold into existing `health-watch`-style cadence). Cron expression: daily at `ARCLINK_WRAPPED_DAILY_HOUR_UTC` (default 02:00 UTC) for daily; weekly Monday for weekly; monthly first of month for monthly.
- [ ] Per-Captain frequency preference stored on `arclink_users.wrapped_frequency ∈ {daily, weekly, monthly}` (default `daily`). Captain changes via dashboard or `/wrapped-frequency <weekly|monthly|daily>` bot command. Reject anything more frequent than daily.
- [ ] Failed reports retry on next cycle. Persistent failures emit operator notification.

### Delivery

- [ ] Captain receives the report on their Hermes home channel (Telegram or Discord) via `notification_outbox`, `target_kind='captain-wrapped'`. Discord uses an embed with the five non-standard stats as fields. Telegram uses Markdown with section breaks.
- [ ] Captain dashboard "Wrapped" tab shows the history with toggle daily/weekly/monthly.
- [ ] Reports never include secrets; same redaction pipeline as `arclink_evidence.redact_value`.
- [ ] Out-of-quiet-hours rule: respects the existing `org_quiet_hours` from the Captain's SOUL inputs.

### Validation floor (Wave 6)

```bash
python3 tests/test_arclink_wrapped.py            # new
python3 tests/test_arclink_notification_delivery.py
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_hosted_api.py
cd web && npm test && npm run lint
```

## Journey Map (Updated for new vocabulary)

### Captain Public Web Purchase Journey

Visitor lands at arclink.online, chooses a plan, opens onboarding. Provides Captain Name, Agent Name, Agent Title, Email. Checks out via Stripe. Raven reports back when payment clears and provisioning starts. Captain receives "Captain &lt;name&gt;, your ArcPod is live" with the dashboard URL. Logs into the dashboard, sees the Crew tab listing one Agent (or three on Scale), opens the Pod, talks to the Agent in their home channel. Optionally runs Crew Training. Receives ArcLink Wrapped on the configured cadence.

### Captain Public Bot Purchase Journey

Captain DMs Raven. Names themselves, names their Agent, picks Agent Title, picks Plan. Stripe link. Pays. Raven pings paid status. Provisioning runs. Raven hands off to the new Agent. Captain talks to the Agent on the same channel from there forward. Slash commands `/agent-name`, `/agent-title`, `/rename-agent`, `/retitle-agent` for post-onboarding updates. `/train-crew` opens the questionnaire. `/wrapped <weekly|monthly>` adjusts cadence.

### Operator Inventory Journey

Operator runs `./deploy.sh control install`. After install, opens `./deploy.sh control inventory` to register fleet machines. For each machine: chooses manual (paste-key) or Hetzner / Linode (via API). Probes hardware. Sees ASU capacity per machine. Toggles placement strategy to `standard_unit`. Watches the admin Comms Console for cross-Captain activity. Initiates Pod migrations when a Captain upgrades hardware.

### Operator Crew Training (admin-on-Captain's-behalf)

Operator has the option (audit-gated) to run Crew Training on a Captain's behalf — e.g. during enterprise onboarding. Surfaces in the admin dashboard. Same flow; the audit records `crew_recipe_applied_by_operator`.

### Operator ArcLink Wrapped (Operator view)

Operator sees aggregate Wrapped statistics per Captain in the admin dashboard for fleet-management context. No Captain's private narrative is exposed; only the periodic novelty score, delivery status, and frequency are surfaced operator-side.

## Schema Migrations (Summary)

Apply in `ensure_schema`. Add a `wave_0` revision marker if you want, but the existing `_migrate_*` helpers are fine.

```
arclink_users
  + agent_title TEXT NOT NULL DEFAULT ''
  + captain_role TEXT NOT NULL DEFAULT ''
  + captain_mission TEXT NOT NULL DEFAULT ''
  + captain_treatment TEXT NOT NULL DEFAULT ''
  + wrapped_frequency TEXT NOT NULL DEFAULT 'daily'

arclink_deployments
  + agent_name TEXT NOT NULL DEFAULT ''
  + agent_title TEXT NOT NULL DEFAULT ''
  + asu_weight REAL NOT NULL DEFAULT 1.0  -- forward-looking; weight=1 today

arclink_onboarding_sessions
  + agent_name TEXT NOT NULL DEFAULT ''
  + agent_title TEXT NOT NULL DEFAULT ''

arclink_inventory_machines (new)
arclink_pod_messages (new)
arclink_pod_migrations (new)
arclink_crew_recipes (new)
arclink_wrapped_reports (new)
```

All new tables include drift checks. All status enums get `*_status_invalid` probes.

## Final Handoff Expectations

Ralphie's final report must include:

- Files changed, grouped by wave.
- Schema migrations applied and tested.
- New env vars and their defaults, written into `bin/docker-entrypoint.sh write_default_docker_config` and `bin/deploy.sh write_docker_runtime_config`.
- Captain-facing copy migration verified via `web/tests/browser/product-checks.spec.ts` (browser) and `tests/test_arclink_public_bots.py` (bot strings).
- Operator-facing surfaces verified to still say "Operator" / "deployment" / etc.
- Vocabulary canon doc `docs/arclink/vocabulary.md` written.
- Open trust-boundary residuals NOT addressed by this mission are listed in completion notes with a one-line rationale for why they remain.
- Live infra remains unproven. Note any per-wave live-proof prerequisites in completion notes.

## Backlog Tracking

When ralphie's PLAN phase produces `IMPLEMENTATION_PLAN.md`, it should mirror this steering's waves and check off items as it builds. Do not leave a wave half-complete and move on to the next — finish the validation floor first, then transition.

If a wave hits a hard blocker that requires operator policy (e.g. "should the additional-agent price-id alias be fixed as part of Crew naming, or kept as a separate residual?"), record the blocker in `consensus/build_gate.md`, hand off, and proceed to the next wave's reading work in parallel.
