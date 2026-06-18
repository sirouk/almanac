# ArcLink Ground Truth Brief — Canonical Anchor for Documentation

Authored 2026-05-30 (branch `arclink`) by the lead documentation architect, reconciling the 14
subsystem-truth records under `research/ground-truth/`. Quantitative module, schema, route, and
OpenAPI provenance was refreshed from code and regression tests on 2026-06-17. **This brief is the
single source of coherence** for the downstream documentation rewrite swarm. Where this brief and any
existing doc disagree, this brief wins, because every claim here is grounded in code file citations
from the ground-truth readers. Every doc rewrite MUST cite this brief and stay internally consistent
with it.

Honesty rule that overrides everything: **never claim live proof that does not exist.** Separate
"local-real" from "proof-gated (PG-*)" from "policy/risk-accepted" in every doc, exactly as this
brief does.

---

## 1. Executive Summary — What ArcLink Is Today

ArcLink is a **Sovereign Control Node**: one control plane (the Control Node) that provisions,
governs, bills, and operates many isolated AI agent runtimes called **ArcPods**. A buyer (a
**Captain**) talks to a public bot persona (**Raven**) on Telegram/Discord, pays via Stripe,
and receives one or more ArcPods — each an isolated Docker-Compose stack running a **Hermes Agent**
with a dashboard, Drive/Code/Terminal workspace plugins, a managed-context memory rail, an LLM
router key, and optional Notion/knowledge integration. The human running ArcLink (the **Operator**)
governs the fleet from an admin dashboard, a chat-native **Operator Raven** console, and a single
in-stack **operator Hermes agent**.

What is real **locally** today (no live external secrets needed): the full control-plane schema,
the hosted WSGI API with sessions/CSRF/RBAC/MFA/rate-limits/CIDR gates, the LLM router relay logic,
the Raven turn engine and onboarding state machine, the sovereign provisioning/placement/teardown
loop, the fleet/inventory/enrollment registries, the entitlement state machine and refuel ledger,
the share-grant + Linked-resource + claim-nonce + fleet-folder sharing rails, the Academy program
lifecycle, central deduplicated Academy corpus, PG-HERMES-gated Academy SOUL overlay apply path,
Crew Recipes + SOUL projection, backup scripts and restore-smoke, the diagnostics/health/
evidence harness, the trusted-host broker/helper family, and the cross-surface finish-gate linter.
All of this is unit-tested with fake adapters.

What is **NOT proven** today: any live external transaction. Live Stripe, live Telegram/Discord
delivery, live Chutes inference relay, live Cloudflare/Tailscale ingress apply, live Hermes
browser/workspace proof, live backup/restore recoverability, and the live hosted customer journey
are all **proof-gated (PG-*)** and have not been executed. Several Docker-socket/root services are
**policy/risk-accepted** under GAP-019, narrowed but not tenant-safe.

The mission is source-complete; what remains is operator-authorized live/proof work. Do not let any
doc imply otherwise.

---

## 2. Canonical Vocabulary & Naming (exact terms every doc must use)

These terms are mechanically enforced at the Captain boundary by `python/arclink_surface_contract.py`
(`_CAPTAIN_FORBIDDEN_PATTERNS`). Captain-facing copy MUST capitalize product nouns and MUST NOT use
operator-internal words. The schema/operator canon keeps the technical names.

### Product / Captain-facing canon (capitalize these)
- **Captain** — the customer/buyer. NEVER "user" or "buyer" on Captain surfaces (schema name is
  `arclink_users`).
- **ArcPod** / **Pod** — the customer's provisioned agent runtime. NEVER "deployment" on Captain
  surfaces (schema name is `arclink_deployments`).
- **Agent** / **Hermes Agent** — the AI inside an ArcPod (capitalize). A Captain may have several.
- **Crew** — the set of a Captain's Agents (capitalize).
- **Raven** — the public bot persona that onboards and serves Captains over Telegram/Discord.
  Default display name "Raven" (`ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME`), per-channel/per-user
  renameable via `arclink_public_bot_identity`.
- **Comms** / **Comms Console** — Pod Comms, Agent-to-Agent messaging.
- **ArcPod Fuel** / **ArcPod Refueling** / **Refuel** — inference budget top-ups.
- **Crew Training** / **Crew Recipe** — SOUL-overlay personality/role shaping.
- **Academy** / **Academy Mode** — the per-Agent specialist training experience.
- **ArcLink Wrapped** — the periodic Captain activity report.

### Operator / admin / schema canon (technical names stay)
- **Operator** — the human running ArcLink (admin/deploy surfaces only; reserved word — never use
  for Captains).
- **Operator Raven** — the chat-native operator control console (`arclink_operator_raven.py`).
- **deployment** (`arclink_deployments`), **user** (`arclink_users`), **fleet host**
  (`arclink_fleet_hosts`), **inventory machine** (`arclink_inventory_machines`), **ASU** (the
  standard capacity unit).
- **Sovereign Control Node** / **Control Node** — the control plane itself.

### Voice rules
- **Captain copy = ArcLink lore voice** (Raven persona, nautical/"on the line, Captain" register).
- **Operator copy = precise/auditable voice** (exact action names, proof gates, next actions).
- Blocked/proof-gated copy MUST offer a concrete next action (the gate enforces `_NEXT_ACTION_RE`:
  `Next|Use|Open|Run|Register|Complete|Send|Tap|Choose|Check|Retry|Operator|dashboard|checkout|
  proof|PG-[A-Z-]+`).

---

## 3. Full Current Module Map (every `python/arclink_*.py`, grouped by subsystem)

There are **89** `python/arclink_*.py` files (includes helpers/legacy). The canonical
`docs/arclink/architecture.md` module map mirrors this inventory, and
`tests/test_documentation_truths.py` guards both the count and membership. Every doc must treat the
list below as the authoritative module inventory.

### Control plane core / API / schema
- `arclink_control` — schema (`ensure_schema`), `Config`, env loading, all table DDL, helpers
  (events, notifications, settings, rate limits, IP guards), entitlement/refuel/plan logic,
  managed-memory payload, recall stubs, Notion index/SSOT broker, today-plate.
- `arclink_hosted_api` — WSGI app, `_ROUTES` dispatch (prefix `/api/v1`), CORS, cookies, webhooks,
  OpenAPI generation.
- `arclink_api_auth` — sessions/CSRF/password hashing, rate limiting, login/logout, admin RBAC+MFA,
  provider-state reads, reconciliation API, **all share-grant/claim-nonce/Linked-resource lifecycle**.
- `arclink_dashboard` — `build_operator_snapshot`, `build_scale_operations_snapshot`,
  `control_node_provisioning_readiness` (GAP-030 readiness states), backup write-check read model,
  admin action support matrix (`ARCLINK_ADMIN_ACTION_SUPPORT`).
- `arclink_boundary` — `rowdict`, json-safe helpers, `reject_secret_material`,
  `require_docker_trusted_host_risk_accepted` (GAP-019 gate).
- `arclink_secrets_regex` — redaction (`redact_then_truncate`).
- `arclink_http`, `arclink_rpc_client`, `arclink_ctl` — transport/CLI helpers.
- `arclink_product`, `arclink_product_surface` — **local no-secret WSGI prototype** (NOT production;
  production surface is Next.js `web/` + hosted API).
- `arclink_surface_contract` — the **executable cross-surface finish-gate linter** (GAP-033).

### LLM router / providers
- `arclink_llm_router` — FastAPI ASGI router (`control-llm-router`, port 8090): `/health`,
  `/v1/models`, `/v1/chat/completions`, policy/reservation/relay/settlement, fallback cascade.
- `arclink_llm_model_sync` — hourly `llm-model-sync` job: refreshes the router's allowed `-TEE`
  model catalog from Chutes (last-known-good on failure, Operator-notified).
- `arclink_chutes` — catalog parse, deployment boundary, usage ingestion, fake key/inference.
- `arclink_chutes_live` — Chutes account/usage/key/OAuth-introspect adapter. **TEST-ONLY, UNWIRED.**
- `arclink_chutes_oauth` — Chutes PKCE OAuth helpers. **TEST-ONLY, UNWIRED, fake exchanger.**
- `arclink_adapters` — Stripe (Fake/Live), Cloudflare, Traefik/Tailscale rendering helpers.
- `arclink_model_providers` — provider preset helpers.

### Captain public bots / onboarding
- `arclink_public_bots` — the Raven turn engine (`handle_arclink_public_bot_turn`): commands,
  routing law, onboarding/checkout copy, channel pairing, selected-agent bridge, Crew Training,
  Academy Mode entry, share approvals/claims, credentials, retire-agent, refuel.
- `arclink_telegram` — Telegram transport + webhook + per-chat command scope + operator interception.
- `arclink_discord` — Discord interaction handler, Ed25519 verify, dedupe, slash/component parsing.
- `arclink_public_bot_commands` — deploy-time command registration + webhook ensure + scope refresh.
- `arclink_onboarding` — the NEW ArcLink public-bot onboarding state machine
  (`arclink_onboarding_sessions`/`_events`).
- `arclink_onboarding_flow`, `arclink_onboarding_completion`, `arclink_onboarding_provider_auth` —
  the OLD Curator/"Almanac" intake flow (Unix-user provisioning, provider OAuth, completion bundle).
  **Still present and active; undocumented in Captain docs.** Two parallel onboarding systems exist.
- `arclink_curator_onboarding`, `arclink_curator_discord_onboarding` — curator-channel onboarding wiring.

### Operator Raven / operator control
- `arclink_operator_raven` — operator command surface (read previews + **real action queueing**).
- `arclink_operator_agent` — the operator's single in-stack Hermes identity + free-form turn bridge.
- `arclink_operator_upgrade_broker` — Docker-mode operator upgrade broker (`operator-upgrade-broker`,
  8917).
- `arclink_operator_upgrade_host_runner` — host-side queue runner for authenticated operator upgrade
  jobs.
- `arclink_action_worker` — admin/operator action-intent consumer (`arclink_action_intents`).
- `arclink_rollout` — rollout model + ArcPod-update rollout planner/materializer/record-only batch.
- `arclink_pin_upgrade_check` — hourly pinned-component upstream upgrade detector.
- `arclink_upgrade_policy` — source-owned dependency and ArcPod rollout policy catalog.

### Academy / Crew / SOUL
- `arclink_academy_programs` — Academy lifecycle (Majors, Trainees, sticky Mode, gallery, adopt,
  curation/apply staging, central corpus, continuing-education).
- `arclink_academy_trainer` — no-network/no-write Academy schemas + fail-closed planning (lanes,
  corpus, gates, review, application-preview boundary).
- `arclink_academy_scheduler` — weekly forward-maintenance job (`control-academy-ce`).
- `arclink_crew_recipes` — Crew Recipes + SOUL overlay + Academy-status overlay + per-Agent artifacts.

### Hermes workspace / dashboard sidecar
- `arclink_dashboard_auth_proxy` — signed-session reverse proxy in front of the Hermes dashboard
  (NOT Basic Auth; HS256 JWT-shaped cookie, mount-prefix rewriting, managed-lifecycle 409 intercept).
- `arclink_nextcloud_access` — provisioning-side `occ` user sync (gated by `ENABLE_NEXTCLOUD`).
- `arclink_headless_hermes_setup` — headless Hermes home setup helper.
- (Plugins live under `plugins/hermes-agent/`, not `python/` — see §7.)

### Public Agent gateway / exec-broker / pod-comms / supervisor family (MISSING from architecture.md)
- `arclink_public_agent_bridge` — short-lived boundary process run INSIDE a Hermes gateway
  container; replays a public Telegram/Discord turn through Hermes' own native gateway pipeline.
- `arclink_public_agent_bridge_root` — root-only Telegram `getMe` cache preload wrapper; it
  launches the actual public Agent bridge as the normal runtime uid.
- `arclink_gateway_exec_broker` — trusted-host broker (8911) owning Docker-exec authority for
  Raven-mediated public-channel Agent replies.
- `arclink_deployment_exec_broker` — trusted-host broker (8912) owning the Docker socket for
  deployment-scoped Compose ops (`compose_up/ps/down`).
- `arclink_agent_supervisor_broker` — trusted-host broker (8913) owning the Docker socket for the
  dashboard network/proxy sidecar lifecycle.
- `arclink_docker_agent_supervisor` — root reconciliation loop (no Docker socket) driving the helper
  family.
- `arclink_agent_process_helper` — root helper (8916) owning the setpriv privilege-drop process
  boundary.
- `arclink_agent_user_helper` — root helper (8915) owning container Unix user/home creation + chown.
- `arclink_pod_comms` — Agent-to-Agent messaging over `arclink_pod_messages`.
- `arclink_rejection_incidents` — shared redacted JSONL incident logger for every broker/helper.
- `arclink_migration_capture_helper` — root helper (8914) for migration capture/materialize.

### Provisioning / fleet / ingress / migration
- `arclink_sovereign_worker` — the Sovereign fleet ArcPod loop (`control-provisioner`): place →
  render → apply → teardown.
- `arclink_enrollment_provisioner` — legacy/starter single-machine onboarding loop + root maintenance
  loop draining `operator_actions`.
- `arclink_provisioning` — provisioning intent render, compose generation, state roots, identity
  projection (`project_arclink_deployment_identity_context`).
- `arclink_fleet` — fleet host registry + placement strategy.
- `arclink_fleet_enrollment` — enrollment-token mint/consume + hash-chained audit.
- `arclink_fleet_inventory_worker` — periodic liveness/capacity/inventory probe worker
  (incl. `docker-local-starter` no-SSH probe).
- `arclink_inventory`, `arclink_inventory_hetzner`, `arclink_inventory_linode` — inventory machines +
  cloud provisioning.
- `arclink_asu` — ASU capacity computation.
- `arclink_ingress` — DNS records + Cloudflare/Traefik/Tailscale ingress.
- `arclink_pod_migration` — the only real capture+materialize+verify+rollback path
  (`reprovision` action).
- `arclink_host_readiness` — no-mutation host preflight checks.
- `arclink_executor` — injectable fail-closed Docker Compose + provider-mutation orchestration
  boundary (Subprocess/Ssh/Brokered/Fake runners).

### Billing / entitlements
- `arclink_entitlements` — Stripe webhook processing + reconciliation drift.
- (entitlement state, refuel ledger, plan pricing, comp, subscription mirror live in
  `arclink_control`; Stripe clients in `arclink_adapters`.)

### Sharing / fleet folder
- `arclink_fleet_share` — fleet shared-folder git-sync engine + control-plane CRUD + CLI.
- (share grants / claim nonces / Linked-resource projection live in `arclink_api_auth`.)

### Backup / lifecycle / wrapped
- `arclink_wrapped` — ArcLink Wrapped scoring/render/cadence/scheduler/delivery.
- (backup scripts are in `bin/`; executor/migration cover the lifecycle.)

### Knowledge / memory / Notion / MCP
- `arclink_memory_synthesizer` — memory synthesis card builder (`memory-synth` job).
- `arclink_org_profile`, `arclink_org_profile_builder` — org-profile validate/apply/doctor + builder.
- `arclink_skill_enablement` — per-agent approved-skill enablement helper for Academy-managed skills.
- `arclink_notion_ssot` — Notion API client + SSOT handshake + no-secret proof harness (PG-NOTION).
- `arclink_notion_webhook` — Notion webhook receiver + verification-token arming.
- `arclink_ssot_batcher` — Notion-event batcher worker.
- `arclink_mcp_server` — ArcLink control-plane MCP server (all agent-facing tools).
- `arclink_resource_map` — shared/managed resource-rail line composition.

### Diagnostics / health / evidence
- `arclink_host_readiness` (above), `arclink_diagnostics` — secret-safe presence-only checks.
- `arclink_live_journey` — 4 journey catalogs (hosted/external/workspace/all).
- `arclink_live_runner` — live-proof orchestration (`bin/arclink-live-proof`), workspace runners.
- `arclink_evidence` — redaction + evidence ledger + `arclink_evidence_runs` DAL (**unwired**).
- `arclink_health_watch` — edge-triggered operator health notifications.
- `arclink_notification_delivery` — notification-outbox delivery worker + Hermes bridge dispatch.

### Misc / helpers
- `arclink_access`, `arclink_agent_access` — access helpers.

---

## 4. Tables — Authoritative Count and Names

Verified by building the live schema and counting DDL in `arclink_control.py`:

- **`arclink_*`-prefixed tables: 45** (NOT 23 — the MEMORY.md "23 tables" figure is **stale by ~2x**
  and must be corrected everywhere it appears).
- **`academy_*` tables: 10** — these are **NOT** `arclink_`-prefixed:
  `academy_programs`, `academy_trainees`, `academy_mode_sessions`,
  `academy_resource_proposals`, `academy_sources`, `academy_corpus_specialists`,
  `academy_specialist_sources`, `academy_source_provenance`,
  `academy_specialist_subscriptions`, and `academy_source_crawl_observations`.
- Total tables in the live schema is 80 (the remainder are legacy/substrate tables such as
  `rate_limits`, `notification_outbox`, `agents`, `agent_identity`, `org_profile_*`,
  `memory_synthesis_cards`, `notion_index_documents`, `settings`, `pin_upgrade_notifications`,
  `operator_actions`).

The 45 `arclink_*` tables (alphabetical):

```
arclink_action_attempts             arclink_events                      arclink_operation_idempotency
arclink_action_intents              arclink_evidence_runs               arclink_pod_messages
arclink_action_operation_links      arclink_fleet_audit_chain           arclink_pod_migrations
arclink_admin_roles                 arclink_fleet_enrollments           arclink_provisioning_jobs
arclink_admin_sessions              arclink_fleet_host_probes           arclink_public_bot_identity
arclink_admin_totp_factors          arclink_fleet_hosts                 arclink_refuel_credits
arclink_admins                      arclink_fleet_share_members         arclink_rollouts
arclink_agent_skill_enablement      arclink_fleet_shares                arclink_service_health
arclink_audit_log                   arclink_inventory_machines          arclink_share_claim_nonces
arclink_channel_pairing_codes       arclink_llm_budget_reservations     arclink_share_grants
arclink_credential_handoffs         arclink_llm_router_keys             arclink_subscriptions
arclink_crew_recipes                arclink_llm_usage_events            arclink_user_sessions
arclink_deployment_placements       arclink_model_catalog               arclink_users
arclink_deployments                 arclink_onboarding_events           arclink_webhook_events
arclink_dns_records                 arclink_onboarding_sessions         arclink_wrapped_reports
```

Two important table facts every doc must respect:
- `arclink_evidence_runs` exists and is fully implemented + tested, but is **UNWIRED** — the live
  runner writes only `evidence/<run_id>.json`; nothing reads the table. Do not claim
  operator-visible evidence/incident state.
- Schema mechanism is a single idempotent `ensure_schema()` with `CREATE TABLE IF NOT EXISTS` plus a
  few `*__new` rebuild migrations. **There is NO version ledger / numbered migrations.** Do not claim
  "reversible, versioned migrations"; it is "create-if-absent + rebuild-when-needed" (idempotent yes,
  reversible/versioned no).

---

## 5. Subsystem-by-Subsystem: REAL TODAY vs PROOF-GATED vs POLICY/RISK-ACCEPTED

For each subsystem: what is genuinely local-real, and what is gated. Be ruthless — no doc may claim
live proof here.

### 5.1 Control core / hosted API / auth
- **REAL:** route dispatch (71 `_ROUTES` entries, 69 unique path suffixes under `/api/v1`; 71
  OpenAPI path objects including the 2 LLM-router paths); session/CSRF
  (double-submit), HMAC-peppered token hashing (`hmac_sha256_v1`, legacy `sha256_legacy` auto-
  rehash); user TTL 24h / admin TTL 1h; PBKDF2-SHA256 passwords (390k iters); admin RBAC single-owner
  + TOTP-MFA gates (login ignores client-asserted MFA); CIDR gate on all admin routes; rate limits
  (login 10/900s, admin_login 5/900s, onboarding_claim 5/900s, webhooks 60/60s); body caps; CORS;
  share-request broker token auth (`X-ArcLink-Share-Request-Broker-Token`); OpenAPI generation.
- **OpenAPI parity is FRESH:** `docs/openapi/arclink-v1.openapi.json` is canonical JSON equivalent to
  the code-generated spec. Keep `test_openapi_spec_matches_static_copy`; regenerate on any `_ROUTES`
  change.
- **PROOF-GATED:** live Stripe webhook delivery (PG-STRIPE), live bot webhooks (PG-BOTS); the
  scale-operations production worker service is a runbook step, not a proven live worker.

### 5.2 Provisioning / fleet / ingress / migration
- **REAL:** sovereign batch loop (place→render→apply→teardown), placement strategies
  (`headroom`/`standard_unit`), idempotency keys, mid-apply entitlement re-check, handoff health gate
  (`ARCLINK_SOVEREIGN_HANDOFF_REQUIRES_HEALTHY_SERVICES`), tailnet port allocator, operator-arcpod
  exclusion; fleet host registry + enrollment + hash-chained audit; `docker-local-starter` no-SSH
  localhost admission; periodic probe worker; ingress for `domain` (Cloudflare CNAME, only `u-` and
  `hermes-` get DNS/Traefik) and `tailscale` (path mode only, no DNS); pod migration capture/
  materialize/verify/rollback; host readiness preflight; GAP-030 readiness states
  (`control_plane_only|pending_ssh|ready_to_provision|blocked_no_worker|blocked_executor`).
- **Provisioning "rollback" is plan-only** (`plan_arclink_provisioning_rollback` writes a plan job,
  no host mutation). Real rollback-with-restore exists ONLY in pod migration.
- **PROOF-GATED:** live remote-fleet apply/worker execution (PG-FLEET / PG-PROVISION), live Cloudflare
  DNS (PG-INGRESS); migration live capture is double-gated
  (`ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE=1` + capture helper).
- **POLICY:** Captain-initiated migration disabled by default (`ARCLINK_CAPTAIN_MIGRATION_ENABLED=0`,
  GAP-017). `set-strategy` CLI is informational only (strategy is read live from env at placement).

### 5.3 LLM router / providers
- **REAL:** router ASGI app + `/health`, `/v1/models`, `/v1/chat/completions`; per-deployment
  `acpod_live_` keys (HMAC-SHA256 + legacy migration); allowlist, model replacements, catalog
  auto-promotion; budget boundary + reservation (prices MAX fallback candidate) + settlement (final
  model); rate limits (key 60 / dep 120 / user 300 per min) + concurrency cap; non-streaming +
  pre-stream fallback cascade with sanitized audit; post-stream no-replay labeling; sanitized usage
  events (**no raw prompts/completions**); fuel-notice refuel nudges to public bots;
  `control-llm-router` compose service is wired and ArcPod default base URL points at it.
- **Compose-vs-code default mismatch (document both):** code default
  `ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS=0`; compose service sets it to **2500**.
- **PROOF-GATED:** live Chutes inference relay (GAP-031 / PG-PROVIDER); fuel-notice bot delivery
  (PG-BOTS).
- **TEST-ONLY, UNWIRED:** `arclink_chutes_live` (account/usage/key/introspect APIs; mutations
  proof-gated) and `arclink_chutes_oauth` (PKCE connect/callback/disconnect, fake exchanger). The
  `per_user_chutes_account_oauth` isolation lane is a **posture/label only** — no live OAuth-backed
  inference path exists.

### 5.4 Captain bots / onboarding
- **REAL:** Telegram + Discord transports/webhooks (fake mode without tokens), per-chat command
  scope, operator interception; the Raven turn engine (rate limit → `/raven` rewrite → bare-slash to
  Agent → Raven-owned commands → aboard routing law → pre-launch onboarding); first-contact greeting;
  channel pairing; helm switching; Crew Training workflow; Academy Mode entry; share approve/deny/
  accept/claim; credentials reveal/scrub; retire-agent; refuel/wrapped-frequency/rename; the NEW
  onboarding state machine + direct-checkout tokens; pricing constants (Founders **$149**, Sovereign
  **$199**, Scale **$275**, expansions $99/$79).
- **TWO parallel onboarding systems exist:** the NEW Stripe-checkout Raven path
  (`arclink_public_bots` + `arclink_onboarding`) AND the OLD Curator/"Almanac" host-Unix-user path
  (`arclink_onboarding_flow` + `_completion` + `_provider_auth`). The OLD path is fully present and
  active (Codex device-code + Anthropic Claude-Code PKCE OAuth, Unix-user provisioning, org-profile
  matching) and is **undocumented in Captain docs**.
- **PROOF-GATED:** ALL live Telegram/Discord delivery, command-menu writes, buttons, selected-agent
  bridge (PG-BOTS); per-agent active command scope needs a live gateway container (PG-HERMES);
  `/connect_notion` is preparation-only (PG-NOTION); `/config_backup` records repo only (PG-BACKUP);
  `/upgrade-hermes` routes to managed rails (PG-UPGRADE); academy graduation stages a plan only
  (PG-HERMES); selected-agent bridge delivery is async and streaming is opt-in
  (`ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING=1`, GAP-023).

### 5.5 Operator Raven / action worker / rollout
- **REAL (HEADLINE — fixes a stale claim):** Operator Raven **QUEUES REAL, AUDITED, IDENTITY-GATED
  ACTIONS today.** It is NOT read-only/dry-run. Mutating commands (`pod_repair`, `rollout`,
  `host_upgrade`, `pin_upgrade`) use a three-mode contract: `--dry-run` previews; no-dry-run +
  no-actor fails closed; no-dry-run + operator actor queues a real intent. Read commands: `status`,
  `agents`, `fleet_list`, `worker_probe` (dry-run only), `user_lookup`, `academy_status`,
  `academy_roster`, `upgrade_check`, `action_status`. Operator approval code (constant-time compare)
  required for all mutating commands. Two queues: `arclink_action_intents` (drained by
  `arclink_action_worker`) and `operator_actions` (drained by the enrollment-provisioner root loop).
  The operator gets exactly ONE in-stack Hermes agent (`arclink_operator_agent`, one-agent invariant,
  `control-stack` runtime) with a free-form chat bridge.
- **ArcPod rollout is a substantial local skeleton:** planner (pure dry-run), local materializer
  (typed `arclink_rollouts` rows), record-only fake/local batch executor. NO real per-Pod refresh/
  apply/health exists.
- **PROOF-GATED:** live mutation gated by `ARCLINK_EXECUTOR_ADAPTER` (fake=record-only) + per-action
  gates (PG-PROVISION restart/reprovision, PG-INGRESS dns_repair, PG-UPGRADE/PG-HERMES rollout,
  PG-PROVIDER chutes, PG-STRIPE refund/cancel, PG-BACKUP backup-write-check); academy live writes need
  `ARCLINK_ACADEMY_APPLY_LIVE=1` + PG-HERMES.
- **POLICY/RISK-ACCEPTED:** operator-upgrade-broker live host upgrades require Docker mode +
  `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted` (GAP-019).

### 5.6 Academy / Crew / SOUL
- **REAL:** sticky Academy Mode (idempotent open/close, one open session per trainee), 5 Majors
  (pure data), trainees + per-account quota (50), graduate gallery + redacted card + owner-scoped
  adopt, end-of-mode commit (always `mutation_performed=False`), curation staging (stable-id
  fail-closed contract), `academy_apply` staging (fail-closed gates), resource-proposal rail
  (`academy.propose-resource` MCP tool), weekly continuing-education (no-write); 8 fixture-only source
  lanes; Crew Recipes (4 presets) + deterministic SOUL overlay + Academy-status overlay + SOUL/
  identity projection (local-only, only when local Hermes home exists).
- **No Agent SOUL/skills/qmd/vault write happens anywhere in this subsystem.** Every path returns
  `mutation_performed=False`. Real imparting is the PG-HERMES `bin/install-deployment-hermes-home.sh`
  seam.
- **PROOF-GATED:** live source acquisition per lane (PG-PROVIDER), live LLM-Trainer router synthesis
  (PG-PROVIDER), real Agent writes (PG-HERMES). GAP-034 sub-items A–E landed; remaining work is
  externally-gated/policy.

### 5.7 Hermes workspace plugins / dashboard auth proxy
- **REAL (local code shape complete):** Drive, Code, Terminal plugins with 4 roots (Vault, Workspace,
  **Fleet**, Linked); local-backend file ops with strong path/symlink/sensitive guards; Code
  repo-confined git (read on all roots; mutations blocked on Linked; pull `--ff-only`/push require
  `confirm:true`); Terminal managed-pty/tmux-pty, root-blocked unless `TERMINAL_ALLOW_ROOT=1`,
  SSE+polling; `arclink-managed-context` plugin (hot-injection, recall budget tiers, per-tool recipe
  cards, bootstrap-token injection, notion.query 3/task budget); `arclink-theme`; the signed-session
  dashboard auth proxy (HS256 JWT cookie, NOT Basic Auth; mount-prefix rewriting; managed-lifecycle
  409 intercept).
- **Nextcloud/WebDAV in Drive is effectively dead** (`_dav_request` always 501; backend is always
  local). The standalone `arclink_nextcloud_access` is separate and `ENABLE_NEXTCLOUD`-gated.
- **PROOF-GATED:** live browser proof of Drive/Code/Terminal (PG-HERMES); share-request broker is
  fail-closed/external (PG-BOTS/PG-HERMES for live effect).
- **POLICY/RISK-ACCEPTED:** the dashboard sidecar lifecycle runs through `agent-supervisor-broker`
  (GAP-019-I family residual trusted-host risk).

### 5.8 Public Agent gateway / exec-broker / pod-comms / supervisor (UNDOCUMENTED in architecture.md)
- **REAL:** the public Agent bridge (replays Telegram raw updates through Hermes native handlers;
  Discord via REST shims; durable `ea:` exec-approval mapping on disk; streaming default-on); seven
  trusted-host services with per-service ports/headers/internal networks; all reject raw commands +
  HMAC token + redacted rejection incidents; Pod Comms send+store+list (same-Captain allowed;
  cross-Captain requires accepted `pod_comms` share grant; attachments are projection refs only).
- **Service/port/header/socket map (canonical):**

  | Service | Module | Port | Token env | Header | Docker socket | Root |
  | --- | --- | --- | --- | --- | --- | --- |
  | gateway-exec-broker | arclink_gateway_exec_broker | 8911 | ARCLINK_GATEWAY_EXEC_BROKER_TOKEN | X-ArcLink-Gateway-Exec-Token | yes | no |
  | deployment-exec-broker | arclink_deployment_exec_broker | 8912 | ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN | (executor.*) | yes | no |
  | agent-supervisor-broker | arclink_agent_supervisor_broker | 8913 | ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN | X-ArcLink-Agent-Supervisor-Broker-Token | yes | no |
  | migration-capture-helper | arclink_migration_capture_helper | 8914 | ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN | X-ArcLink-Migration-Capture-Helper-Token | no | yes |
  | agent-user-helper | arclink_agent_user_helper | 8915 | ARCLINK_AGENT_USER_HELPER_TOKEN | X-ArcLink-Agent-User-Helper-Token | no | yes (caps) |
  | agent-process-helper | arclink_agent_process_helper | 8916 | ARCLINK_AGENT_PROCESS_HELPER_TOKEN | X-ArcLink-Agent-Process-Helper-Token | no | yes (setpriv) |
  | operator-upgrade-broker | arclink_operator_upgrade_broker | 8917 | ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN | X-ArcLink-Operator-Upgrade-Broker-Token | no | yes |

- **PROOF-GATED:** real bridge delivery needs a live gateway container + bot token + Hermes runtime
  (PG-BOTS / PG-HERMES); Discord bridge is NOT native parity (text/slash + REST shims only); Pod Comms
  cross-Pod **delivery** and operator redaction are unwired (`mark_pod_message_delivered`/
  `redact_pod_message` have no production callers).
- **POLICY/RISK-ACCEPTED:** the WHOLE family is Docker-mode + trusted-host gated
  (`ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted`). Each socket broker still holds a writeable
  Docker socket; each root helper still runs as root — **GAP-019 is OPEN, acknowledged-only, not
  tenant-safe.**

### 5.9 Billing / entitlements
- **REAL:** entitlement state machine (`none|paid|comp|past_due|cancelled`); the provisioning gate is
  `arclink_deployment_can_provision` (true only for `paid`/`comp`), enforced at both gate-advance and
  intent-build; Stripe webhook processing (signature verify, idempotent replay via
  `arclink_webhook_events`, 7 mutating event types, email identity merge, subscription mirror);
  refuel-credit ledger (FIFO, `fair_credit_local_ledger`); refuel checkout (mode=payment,
  account-match gating); subscription inference allowance (plan-share split, idempotent per invoice);
  plan pricing (`ARCLINK_PLAN_RETAIL_CENTS`); two distinct drift systems (Stripe reconciliation vs
  schema drift); targeted comp (account- or deployment-scoped); renewal lifecycle policy.
- **CRITICAL honesty nuance:** refuel/allowance is **LOCAL BUDGET ACCOUNTING ONLY** — it stamps
  `local_budget_accounting_only_until_live_chutes_proof` and never moves a real Chutes balance. The
  webhook returns a synthetic `entitlement_state="refuel_paid"` marker, NOT a stored state.
- **PROOF-GATED:** live Stripe checkout/portal/webhook (PG-STRIPE); live Chutes provider-balance
  application (PG-PROVIDER). Webhook is fail-closed: unset `STRIPE_WEBHOOK_SECRET` → 503 (Stripe
  retries).

### 5.10 Sharing / Linked resources / fleet folder
- **REAL:** share-grant lifecycle (`pending_owner_approval→approved→accepted`, +denied/revoked/
  expired, 7-day TTL); same-account auto-accept; Linked-resource projection
  (`living_symlink` for drive/code, `ssot_inherited_subtree` for notion); `.arclink-linked-resources.json`
  manifest; no-reshare enforced in three places; ephemeral claim-nonce (`asn_`, 12h, hashed-only);
  share-request broker (`/user/share-grants/broker`, deployment-scoped token, OFF by default);
  notification rails (Raven approve/deny/accept buttons use `/raven` namespace); the **fleet shared
  folder** (2026-05-29) — real git-sync engine (bare hub per Captain at `/arcdata/captains/<user>/
  fleet-shared.git`, per-agent working copy, multi-writer rebase, conflict-surfacing not clobber,
  quarantine-and-reclone), surfaced as the writable **Fleet** root in Drive/Code.
- **PROOF-GATED:** live bot delivery of approval/recipient prompts (PG-BOTS); browser share affordance
  (GAP-014); remote git hub transport (ssh/https, infra-gated).
- **CORRECTION (this brief was stale here):** the `fleet-share-reconcile` control-node compose job
  **does exist** — it was added in commit `7ccb2b3` (`compose.yaml`, runs `reconcile --all` ~every
  120s via `reconcile_all_fleet_shares()`, a DB-only membership-convergence pass). The two-tier model
  is correct: the per-agent `fleet-share-sync` job runs the in-pod git sync; the control-node
  `fleet-share-reconcile` job runs DB membership convergence. Docs were aligned to the code, not to
  this brief's earlier wrong claim.

### 5.11 Backup / restore / executor / wrapped / lifecycle
- **REAL:** the executor is fail-closed by default (`live_enabled=False`, `adapter_name="disabled"`),
  with Subprocess/Ssh/Brokered/Fake runners; lifecycle actions `stop|restart|inspect|teardown`
  (volumes preserved unless `metadata.teardown.remove_volumes is True`); `rollback_apply` enforces
  `preserve_state_roots` (but **has no production caller** — pod migration uses teardown for
  rollback); two backup scripts (`backup-to-github.sh` for control/priv, `backup-agent-home.sh` for
  Hermes home) with two-phase pending→verify→activate, public-repo refusal, curated secret-excluding
  snapshot, separate per-user deploy keys; restore-smoke (artifact shape only, refuses remote
  sources); ArcLink Wrapped (signal-gated eligibility, operator/terminal exclusion, persistent-
  failure operator notice at 3, quiet-hours delivery).
- **Teardown lives in the SOVEREIGN worker, not the action worker.** The action worker only supports
  `restart` among lifecycle ops. Volume-delete is gated by `metadata.teardown.remove_volumes`, NOT a
  `destructive: true` flag.
- **PROOF-GATED:** per-agent backup activation (PG-BACKUP, GAP-013 — chat/dashboard reach only
  `pending_key_setup`; unattended write check is `failed_closed`); restore recoverability (PG-BACKUP,
  GAP-020); live Docker/Cloudflare/Chutes/Stripe execution.

### 5.12 Knowledge / memory / Notion / MCP / skills
- **REAL:** memory synthesis (full-content-hash freshness, deterministic local fallback when no LLM
  config, prompt-injection hardening); recall stubs into managed context; org-profile validate/apply/
  doctor + SOUL overlay + identity state + unmatched-agent baseline; Notion indexed knowledge rail
  (`notion-shared` qmd collection) + SSOT broker + operator-armed webhook token install + sub-second
  batcher; MCP server (loopback, bootstrap-token auth, full tool set incl. `knowledge.*`, `vault.*`,
  `notion.*`, `ssot.*`, `pod_comms.*`, `shares.request`, `academy.propose-resource`); 12 installed
  skills; docs→vault sync.
- **PROOF-GATED:** live external Notion mutation (PG-NOTION; code default `proof_mode="fake"`); live
  agent/workspace knowledge proof (PG-HERMES).

### 5.13 Diagnostics / health / evidence / notifications
- **REAL:** host readiness (no-mutation, secret presence excluded from `ready`); presence-only
  provider diagnostics (`live=True` is a stub); 4 journey catalogs; live runner (dry-run default,
  statuses `blocked_missing_credentials|blocked_no_registered_runner|dry_run_ready|live_executed`);
  evidence redaction + ledger; **WORKSPACE journey ships executable no-secret runners** (`deploy.sh
  control upgrade/health` + Playwright Drive/Code/Terminal with sanitized screenshots); health-watch
  (edge-triggered operator notify, deploy-window suppression); notification-delivery worker (6
  target_kinds: operator, curator, user-agent, public-bot-user, captain-wrapped, public-agent-turn);
  redacted rejection-incident JSONL logs.
- **KEY HONESTY GAPS:** the **external** journey has **NO executable runners** — `--journey external
  --live` returns `blocked_no_registered_runner` (it is a catalog, not a proof). `arclink_evidence_runs`
  persistence is **unwired** — there is NO shared operator-visible incident/evidence read model.
- **PROOF-GATED:** the whole live journey is gated by `ARCLINK_E2E_LIVE`; no live customer journey has
  been proven (PG-PROD). Workspace runners are the only executable proof vehicle (PG-HERMES).

### 5.14 Surface contract / vocabulary / brand / product surface
- **REAL:** the executable finish gate (`arclink_surface_contract.py` — secret/traceback refusal,
  Captain-vocabulary lint, blocked-copy "next action" rule, audience/channel/state taxonomy) with a
  passing cross-surface test that exercises real local surfaces; the local product-surface prototype
  (FakeStripe, loopback) applies the brand palette (Jet `#080808`, Carbon `#0F0F0E`, Soft `#E7E6E6`,
  Signal Orange `#FB5005`, Electric Blue `#2075FE`, Neon Green `#1AC153`).
- **The finish gate proves only LOCAL copy quality** — it does NOT prove how Telegram/Discord/browser/
  CLI actually render. That is GAP-033's open gates: PG-PROD, PG-BOTS, PG-HERMES.

---

## 6. Authoritative GAP-* Ledger (current true status — every doc must cite this)

`GAPS.md` defines GAP-001..GAP-034 with no open `### GAP-008` header; `GAP-008` appears only in
locally closed references. Product matrix SSOT: **101 real / 0 partial /
0 gap / 15 proof-gated / 5 policy-question (121 rows)**, guarded by
`tests/test_documentation_truths.py`. The two header-level "closed locally" callouts are GAP-011
(docs align) and GAP-025 (suite green).

### The specifically-requested gaps
- **GAP-013** (Raven backup prep stops before key setup): **PARTIAL, ux-gap/ops-gap, PG-BACKUP.**
  Public `/config_backup` records repo only; dashboard projects `pending_key_setup`, can stage a key
  via CSRF route (public key only); unattended write check is `failed_closed`; the
  `configure-agent-backup.sh --verify` lane does real read + dry-run-write checks for the Hermes-home
  lane. Live GitHub write/activation/restore remain open.
- **GAP-014** (browser share requests need live broker/adapter proof): **PARTIAL, policy-question.**
  Local broker contract + hosted route + token-hash auth + provisioning secret wiring all real,
  OFF by default. Open: production browser proof + native-broker-vs-Nextcloud-adapter decision.
- **GAP-015** (share approval can silently wait without a linked public channel): **PROOF-GATED
  (PG-BOTS).** Inbox + retry-notification + no-channel recovery hints + single-row local queueing all
  real; only live Telegram/Discord delivery + callback proof remains.
- **GAP-016** (Linked copy/duplicate policy aligned): **REAL / closed locally.** Code and GAPS.md now
  cite `accepted_linked_resources_writable_in_place_without_reshare_or_git_mutation` (+ destination
  roots `["vault","workspace"]`). Docs must keep using the current string.
- **GAP-019** (Docker socket/root services, P0 trusted-host): **OPEN — acknowledged residual risk
  only.** Largest row (sub-items A..BD). Command path narrowed via seven brokers/helpers (raw-command
  rejection, HMAC tokens, internal networks, trusted Docker-binary pins, path/symlink validation,
  redacted rejection incidents), but each socket broker still owns a writeable Docker socket and each
  root helper still runs as root → **not tenant-safe.** Gated behind
  `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted` (GAP-019-AL). Many sub-items landed; see §5.8.
- **GAP-029** (Operator Raven not full-service control plane): **PARTIALLY CLOSED — read-only/dry-run
  framing is STALE.** Raven now queues real, audited, identity-gated, approval-code-gated mutations
  (`pod_repair`, `rollout`, `host_upgrade`, `pin_upgrade`) plus a broad read surface and an outer
  operator-Hermes free-form bridge. Residue: breadth (fleet drain/admit/rotate, billing refuel from
  chat), unified policy, and authorized live proof. Any doc calling Operator Raven "read-only/dry-run"
  is WRONG and must be corrected.
- **GAP-030** (sovereign worker / Control Node provisioning readiness live proof): **PROOF-GATED
  (PG-FLEET/PG-PROVISION).** Local/admin readiness surfacing implemented + tested
  (`control_node_provisioning_readiness` + admin/Raven/web panels); only authorized live worker proof
  remains.
- **GAP-031** (LLM router fallback cascade live proof): **PROOF-GATED (PG-PROVIDER).** GAP-031-A
  landed (sanitized fallback audit, pre-stream fallback, no-replay-after-stream, fallback-aware
  reservation pricing, final-model settlement pricing). Only authorized live overload proof remains.
- **GAP-032** (Control Node rolling Hermes/ArcPod updates): **OPEN, product-gap, proof-gated**, with a
  substantial local skeleton (planner + local materializer + record-only batch executor, all queueable
  through Operator Raven + action worker). Missing: real per-Pod refresh/apply + live multi-Pod health
  proof (PG-UPGRADE/PG-HERMES). The runbooks still list rollout as "pending/disabled" — STALE; rollout
  is now `wired`/queueable in `ARCLINK_ADMIN_ACTION_SUPPORT`.
- **GAP-033** (cross-surface experience finish gate): **quality-gap, proof-gated — NOT CLOSED.**
  GAP-033-A landed (`arclink_surface_contract.py` + test). Remains open ONLY for authorized PG-PROD/
  PG-BOTS/PG-HERMES browser/chat/workspace proof. Do not let any doc claim it closed.
- **GAP-034** (Academy Trainer corpus + continuing education): **PARTIAL — sub-items A–E landed
  locally** (`arclink_academy_trainer.py`, no-write/no-network). Remaining is externally-gated:
  live source acquisition (PG-PROVIDER), live Trainer synthesis (PG-PROVIDER), real Agent writes
  (PG-HERMES), source-governance policy. Belongs to the prior completed mission, not the active DoD.

### Other gaps the readers surfaced (must not be resurrected as open)
- **REAL / closed locally:** GAP-009 (session-only browser tokens), GAP-010 (web preferred-channel
  copy), GAP-011 (foundation docs align), GAP-012 (matrix guarded), GAP-016 (Linked policy), GAP-025
  (suite green).
- **Proof-gated:** GAP-001 (PG-PROD), GAP-002 (PG-STRIPE), GAP-003 (PG-BOTS), GAP-004
  (PG-PROVISION/PG-INGRESS), GAP-005 (PG-HERMES), GAP-007 (PG-NOTION), GAP-018 (admin action side
  effects), GAP-020 (PG-BACKUP), GAP-021 (cloud fleet), GAP-022 (live Crew/SOUL generation), GAP-023
  (selected-agent streaming opt-in), GAP-026 (PG-UPGRADE), GAP-028 (PG-SHARED-HOST).
- **Policy-question:** GAP-006 (provider self-service policy), GAP-017
  (`ARCLINK_CAPTAIN_MIGRATION_ENABLED=0`), GAP-024 (provider changes visible not self-service),
  GAP-027 (Discord Curator operator-action authority).

### Proof-gate identifiers (the vocabulary docs must use)
`PG-PROD`, `PG-STRIPE`, `PG-BOTS`, `PG-PROVIDER`, `PG-PROVISION`, `PG-INGRESS`, `PG-FLEET`,
`PG-HERMES`, `PG-UPGRADE`, `PG-BACKUP`, `PG-NOTION`, `PG-CLOUDFLARE`, `PG-TAILSCALE`,
`PG-SHARED-HOST`. Keep proof-gate language in copy — blocked surfaces must name the gate.

### Stale gap status to flag in docs
- Any doc citing Operator Raven as "read-only/dry-run" (GAP-029) — STALE (it queues real actions).
- Any runbook listing `rollout` as "pending/disabled" (GAP-032) — STALE (now wired/queueable).
- GAPS.md GAP-016 policy string — must stay aligned with `python/arclink_mcp_server.py`.
- MEMORY.md "23 arclink_* tables" — STALE (45).
- (Earlier brief claim that operations-runbook.md's `fleet-share-reconcile` job "does not exist" was
  itself STALE — the job exists as of commit `7ccb2b3`; docs were aligned to the code.)

---

## 7. Undocumented / Newer-Than-Docs Subsystems Needing NEW Canonical Doc Coverage

These have NO adequate canonical home and need new (or heavily expanded) docs:

1. **Public Agent Gateway + trusted-host broker/helper family** (§5.8) — entirely absent from
   `architecture.md`. Needs: a "Public Agent Gateway" section (bridge process, native-handler replay,
   per-turn `docker exec` via `gateway-exec-broker`), and a "Trusted-Host Brokers & Helpers" section
   with the service/port/header/socket table and the GAP-019 trust-boundary invariants
   (cross-link operations-runbook.md GAP-019 entries, the authoritative source).
2. **Fleet shared folder** (§5.10, 2026-05-29) — absent from data-safety.md and the symphony Sharing
   section. Needs a data-safety note (multi-writer git, conflict-surfacing-not-clobber, hub durability
   boundary, hashed nonces) and recognition as a Drive/Code **Fleet** root.
3. **Pod Comms** (Agent-to-Agent messaging) — absent from architecture.md as a messaging subsystem
   (only appears as a share-grant kind). Needs module-map row, isolation model, routes
   (`/user/comms`, `/admin/comms`), MCP tools (`pod_comms.*`), and the unwired-delivery caveat.
4. **Operator Raven real-action layer + operator single Hermes agent + free-form bridge** (§5.5) —
   under-documented; the symphony/runbooks lag the code.
5. **The OLD Curator/"Almanac" onboarding system** (§5.4) — entirely undocumented in Captain docs;
   needs reconciliation against the NEW Raven path.
6. **The executable finish gate** (`arclink_surface_contract.py`) — `professional-finish-gate.md` is
   prose-only and never names it.
7. **`arclink_evidence_runs` unwired state** — every diagnostics/evidence doc must state evidence is
   currently file-only (`evidence/<run_id>.json`), NOT persisted/operator-visible.
8. **DOC_STATUS omissions** — `brand-system.md`, `professional-finish-gate.md`, and
   `sovereign-control-node-symphony.md` were previously unclassified; the current
   documentation alignment classifies them in `docs/DOC_STATUS.md`.

---

## 8. Per-Doc Drift Table

Severity legend: **heavy** (materially wrong/missing core), **light** (small corrections),
**fresh** (accurate, keep), **new-doc-needed** (subsystem has no adequate home).

| Doc | Severity | Corrections needed |
| --- | --- | --- |
| `README.md` | light | Verify top-line product framing matches §1/§2 canon (Sovereign Control Node, Captain/ArcPod/Raven). Ensure no "23 tables" or "read-only Operator Raven" residue. |
| `AGENTS.md` | light | Align contributor-facing architecture summary with the §3 module map; add the public Agent gateway/broker family and Operator Raven real-action note if referenced. |
| `docs/API_REFERENCE.md` | light | Add 10 missing live routes: `GET /adapter-mode`; onboarding `status`/`claim-session`/`cancel`; all 6 Academy routes. Align rate-limit scope labels (`onboarding:{channel}`→`onboarding_claim`). Note refuel webhook returns synthetic `refuel_paid` marker. Otherwise accurate (auth, CORS, body caps, prices, broker token). |
| `docs/DOC_STATUS.md` | aligned | Classifies the previously missing docs (`brand-system.md`, `professional-finish-gate.md`, `sovereign-control-node-symphony.md`) and points `architecture.md` route truth to API/OpenAPI instead of treating its high-level family table as the route catalog. |
| `docs/arclink/architecture.md` | aligned | Module map now includes the public-Agent-gateway/broker/helper/pod-comms family, operator_raven/agent, operator-upgrade host runner, upgrade policy, Academy, skill enablement, memory_synthesizer, fleet_share, pod_migration, notification_delivery, and current 45 `arclink_*` + 10 `academy_*` count. Route truth is delegated to API_REFERENCE/OpenAPI. |
| `docs/arclink/sovereign-control-node-symphony.md` | aligned / aspirational | Corrects GAP-029 real-action Operator Raven wording, marks migration versioning as target shape, adds fleet shared folder, notes OAuth/live-Chutes adapters as present-but-unwired, names the broker/helper split, and keeps Academy weekly maintenance no-write while documenting PG-HERMES Academy SOUL apply. |
| `docs/arclink/sovereign-control-node.md` | light-to-heavy | Ingress §6 lists DNS for FOUR hosts (`u-/files-/code-/hermes-`); code only creates DNS/Traefik for `u-` and `hermes-` (`ARCLINK_HOST_ROLES`). Files/Code are dashboard plugin routes, not subdomains — concrete contradiction, fix. Add Operator Raven/operator-agent subsection. Add handoff health gate, tailnet port allocator, operator-arcpod exclusion, mid-apply entitlement re-check. |
| `docs/arclink/control-node-production-runbook.md` | heavy | Action matrix lists `rollout` (and suspend/unsuspend/force-resynth/bot-key-rotation) as "disabled/pending" — `rollout` is now wired/queueable (`arcpod_update_rollout`, PG-UPGRADE/PG-HERMES). Add Operator Raven real-action surface, operator approval code, operator single Hermes agent, free-form bridge. Pod-migration section is accurate. |
| `docs/arclink/operations-runbook.md` | light | Add the `rollout` action-readiness row. State ALL Operator Raven mutating commands require the approval code. Add the two-queue distinction (`arclink_action_intents` vs `operator_actions`). Add operator single Hermes agent + bridge. **Fix:** document BOTH the per-agent `fleet-share-sync` (in-pod git) and the control-node `fleet-share-reconcile` (DB membership convergence) jobs — both exist in `compose.yaml`. GAP-019 entries are the authoritative trust-boundary source — keep. |
| `docs/arclink/llm-router.md` | light | Config table default wrong: `ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS` is `0` in code, `2500` in compose — state both. Add `arclink_chutes_live` + `arclink_chutes_oauth` coverage marked TEST-ONLY/unwired; add `per_user_chutes_account_oauth` + `account_oauth_required` as proof-gated/unwired. Add `streaming_fallback` taxonomy. |
| `docs/arclink/fleet-cli.md` | light | `set-strategy` only prints (no persistence; strategy is env-driven at placement). `inventory rotate-key`/`fleet-key --rotate` live in `deploy.sh`, not the Python CLI. |
| `docs/arclink/fleet-operator-runbook.md` | fresh | Add the `docker-local-starter` no-SSH localhost admission path. Otherwise matches code. |
| `docs/arclink/ingress-plan.md` | fresh | Strongest ingress doc; matches `ARCLINK_HOST_ROLES`. One-line note that `files-`/`code-` hostnames are computed but not provisioned as subdomains. |
| `docs/arclink/raven-public-bot.md` | light | Operator command list incomplete/off (use real `ARCLINK_OPERATOR_TELEGRAM_COMMANDS`: operator_status, agents, fleet_list, worker_probe, user_lookup, pod_repair, upgrade_check, upgrade, pin_upgrade, rollout, action_status, academy_status). Add `/share-accept`/nonce-claim, retire-agent, refuel, academy, crew-training, wrapped-frequency, rename/retitle pointers. Pricing line is correct. |
| `docs/arclink/first-day-user-guide.md` | heavy | Describes the OLD Curator flow as the only path. Reconcile the two onboarding systems (Stripe-checkout Raven vs Curator host-Unix). Use "Raven" not "Curator" for the public persona. Add credentials handoff, `/agents`, Crew Training, Academy, channel pairing. Backup/Notion sections match GAP-013/PG-NOTION — keep. |
| `docs/arclink/CREATIVE_BRIEF.md` | light-to-heavy (copy drift) | Sample Raven copy drifted from live strings (header "`{raven} on the line, Captain.`", default prompt buttons "Founders Offer $149/mo" + "3X Scale Plan $275/mo"). Acknowledge Academy Mode and Crew Training as shipped surfaces. Pricing table/feature grid match code — keep. Keep the proof-gated implementation-status note. |
| `docs/arclink/academy-trainer.md` | aligned | Covers the shipped `/academy` sticky-mode in-chat flow, central corpus/resource proposals, quota/retention, proof-gated live Trainer synthesis, no-write weekly CE, and the PG-HERMES authorized Academy SOUL apply path. Keep vault/qmd/skill writes described as staged/planned rather than implemented. |
| `docs/arclink/operator-stripe-webhook.md` | light | Add: unset `STRIPE_WEBHOOK_SECRET` → 503 fail-closed; idempotency/replay semantics; refuel `checkout.session.completed` (mode=payment) + subscription invoices replenish fuel; email-driven user merge. Required 7-event list matches. |
| `docs/arclink/data-safety.md` | light-to-heavy | Teardown safeguards #1/#4 wrong: teardown runs via the SOVEREIGN worker (action worker only does `restart`); volume-delete gate is `metadata.teardown.remove_volumes`, not `destructive:true`. Add Fleet shared folder + claim-nonce + share-request broker (missing). Add entitlement/refuel/Stripe data-safety story (currently absent). Volume layout + GAP-019 inventory are accurate. |
| `docs/arclink/backup-restore.md` | heavy | State-root path wrong (`/srv/arclink/...` → `/arcdata/deployments/{id}` with `config/vault/state/nextcloud/published/`). Volume name wrong (`arclink-{id}_postgres_data`). Add the two backup scripts + two-phase `configure-agent-backup.sh` pending→verify→activate + per-user key separation + public-repo refusal + curated secret-excluding snapshot. Add `deployment-exec-broker` for the Docker lifecycle. Restore-smoke section is current. |
| `docs/arclink/wrapped.md` | light | Add eligibility signal gate (`_has_wrapped_signal`), operator/terminal exclusions, persistent-failure operator notice at 3 (`tui-only`, no narrative), `delivery_channel='unavailable'` outcome. Routes/formula/runtime accurate. |
| `docs/arclink/notion-human-guide.md` | light | Add `knowledge.search-and-fetch` unified rail; `ssot.preflight/pending/approve/deny`; operator-armed webhook token flow + sub-second batcher pipeline; data-source-aware Notion API (`2026-03-11`). |
| `docs/org-profile.md` | light-to-moderate | Add unmatched-agent baseline slice (`org_member_unmatched`, "do not infer identity from roster"); `policies` + `agent_lineage` schema sections (privacy visibility gating, seed-source sha256); note `[managed:today-plate]` exists. |
| `docs/managed-memory-stubs-example.md` | fresh | Matches `_build_recall_stubs` / `_memory_synthesis_card_lines`. Example JSON omits some payload keys (self-flagged as fictionalized subset) — fine. |
| `docs/docker.md` | light | Verify it names all current high-authority compose services (the 7 in §5.8) and `control-llm-router`, `control-provisioner`, `control-academy-ce`, `arclink-wrapped`, `notification-delivery`, `health-watch`, `fleet-share-sync`, `managed-context-install`. Confirm against `config/docker-authority-inventory.json`. |
| `docs/arclink/alert-candidates.md` | heavy | Describes an external pager pipeline but never the in-product rail: health-watch edge-triggered operator notifications → `notification_outbox` → operator channel, deploy-window suppression, `arclink_service_health`. Add these; mark poll-based Stripe/provisioning alerts aspirational (no in-repo emitter). |
| `docs/arclink/live-e2e-secrets-needed.md` | fresh | Add a warning that the **external** journey rows have NO executable runners (`--journey external --live` returns `blocked_no_registered_runner`); only `workspace` ships runners. |
| `docs/arclink/live-e2e-evidence-template.md` | light | Add the Tailscale ingress alternative (`tailscale_ingress_health_check`) for step 6; add the ledger `status` field for blocked-while-live runs; note evidence is currently file-only (not persisted to `arclink_evidence_runs`). |
| `docs/arclink/local-validation.md` | fresh | Optionally list `python3 -m arclink_host_readiness` / `arclink_diagnostics` dry-run commands. |
| `docs/arclink/foundation.md` | light | Accurate but generic; don't imply evidence is operator-visible (it isn't). |
| `docs/arclink/foundation-runbook.md` | light | Accurate; same evidence-persistence caveat. |
| `docs/arclink/brand-system.md` | light | Palette/typography/voice match the product-surface CSS. Add to DOC_STATUS. Note shipped copy uses "Your AI workforce. Deployed." not the documented "Built once. Runs forever." |
| `docs/arclink/professional-finish-gate.md` | heavy (missing executable gate) | Prose-only; add a section naming `python/arclink_surface_contract.py` + `tests/test_arclink_surface_contract.py`, the audience/channel/state taxonomy, the Captain-vocabulary lint, secret/traceback refusal, and the blocked-copy "next action" rule. Add to DOC_STATUS. |
| `docs/arclink/vocabulary.md` | fresh | Matches the gate. Optionally name `arclink_surface_contract.py` as the mechanical enforcer. |
| `docs/arclink/document-phase-status.md` | heavy (historical log) | Stale at 2026-05-16; never records GAP-029/033/034 slices; embedded matrix totals stale. Treat as historical; if updated, append a 2026-05-27+ note. |
| `docs/arclink/CHANGELOG.md` | heavy (historical) | Stops at Foundation (2026-05-05); no surface gate, Operator Raven, Academy, LLM router, fleet, Wrapped. If refreshed, add the cross-surface finish gate + GAP-029/032/033/034 slices. |
| `plugins/hermes-agent/README.md` | light | "default to `$HOME`" is now `$HERMES_HOME/workspace`. Add `arclink-managed-context` to the bullet list. |
| `plugins/hermes-agent/drive/README.md` | light | "Workspace defaults to `$HOME`" → `$HERMES_HOME/workspace`. Add the **Fleet** root. Writable-Linked/no-reshare/`.drive-trash` accurate. |
| `plugins/hermes-agent/code/README.md` | light | Same Workspace-root fix. Add the **Fleet** root. Add that `pull`/`push` require `confirm:true` and pull is `--ff-only`. |
| `plugins/hermes-agent/terminal/README.md` | fresh→light | Version drift (plugin.yaml 0.2.0 vs status 0.3.0). `+SSH` is correctly described as a local machine shell (not remote dial-out). |
| `plugins/hermes-agent/arclink-managed-context/README.md` | fresh | Accurate. Could add `pre_tool_call` token-injection + `notion.query` 3/10min budget block + per-turn recipe cards. |
| `docs/openapi/arclink-v1.openapi.json` | fresh | Canonical JSON equivalent to the code-generated spec. Keep `test_openapi_spec_matches_static_copy`; regenerate on any `_ROUTES` change. |
| `FUTURE_SHARED_ARCLINK.md` | heavy (intended north-star) | Add a banner clarifying what IS built (single-control-plane share grants + Linked + claim-nonce broker + git fleet folder) vs the unbuilt keypair/mesh/cross-sovereign-node layer. Its scope strings don't match the real resource_kind/resource_root/access_mode model. |

---

## 9. Cross-Cutting Honesty Rules (apply to every doc)

1. **No secrets, ever.** No live tokens/keys/passwords/PEM material, no operator identity, no raw
   prompts/completions in any doc or example. Examples must use placeholders.
2. **Separate local-real from proof-gated.** Every capability claim must say whether it is local-real,
   PROOF-GATED (name the PG-* gate), or POLICY/RISK-ACCEPTED. Never imply a live transaction has been
   proven. The phrases to reach for: "implemented and tested locally", "proof-gated behind PG-X",
   "risk-accepted under GAP-019".
3. **Keep proof-gate language in copy.** Blocked/proof-gated surfaces must name the gate and offer a
   concrete next action (the surface-contract gate enforces this).
4. **Voice split.** Captain copy = ArcLink lore voice (Raven persona). Operator copy = precise/
   auditable voice (exact action names, gates, next actions). Never use "user/buyer/deployment" on
   Captain surfaces; never use Captain lore on operator/audit surfaces.
5. **Cite the canonical names.** Use the §2 vocabulary, the §3 module names, the §4 table names, and
   the §6 GAP/PG identifiers verbatim. Do not invent synonyms.
6. **Two-system honesty.** Where two systems coexist (NEW Raven vs OLD Curator onboarding; the
   fake-default vs live adapter; the local product-surface prototype vs the Next.js production app),
   name both and say which is the production/Captain path.
7. **Don't resurrect closed gaps** (GAP-009/010/011/012/016/025 are real/closed-locally) and **don't
   claim closure of open ones** (GAP-033 is NOT closed; GAP-019 is acknowledged-only; live journeys
   are unproven).
8. **Cross-link, don't duplicate.** For the trust boundary, point to operations-runbook.md's GAP-019
   entries (authoritative). For the route catalog, point to API_REFERENCE/OpenAPI. For gap taxonomy,
   point to GAPS.md; for product claims, the product/coverage matrix.
