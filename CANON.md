# CANON.md — ArcLink Project Canon (Federated Ground-Truth Dissection)

> **What this is.** The single authoritative, code-proven map of the **entire ArcLink
> project end-to-end** — every subsystem, every surface, every seam — built by a
> two-model **Federation** (Claude Opus 4.8 `xhigh` + GPT-5.5 via Codex CLI). It is the
> whole-project successor to `DISSECT.md` (which proved one vertical: the operator-upgrade
> pipeline). The method, format, and severity discipline are inherited from `DISSECT.md`.
>
> **Binding method (enforced in every audit prompt).** *Prove, do not guess.* Comments,
> docstrings, names, and prior docs are **claims, not evidence** — only executed code paths
> are evidence. Every load-bearing claim cites `path:line`. Where code and comment/doc/name
> disagree, **the code wins and the drift is called out**. No human-language intent is
> accepted as proof. Disagreement is preserved, not averaged away.

---

## Federation provenance (audit trail)

| Stage | Engine | Status |
|---|---|---|
| Decomposition (this doc's piece index + file→piece coverage map) | Claude Opus 4.8 `xhigh` | **LANDED** |
| Coverage cartography (every tracked file mapped to exactly one piece; orphans/double-claims proven) | 1× cartographer `xhigh` | **LANDED** |
| Independent audit — round 1 (per-piece, code-cited, traced to the boundary) | 32× Claude Opus 4.8 `xhigh` | **LANDED** (32/32) |
| Adversarial verification (per-piece skeptic refutes every load-bearing claim vs code) | 32× Claude Opus 4.8 `xhigh` skeptic | **LANDED** (32/32) |
| Synthesis (consolidated matrix + seam graph + unified risk register) | 1× synthesizer `xhigh` | **LANDED** (this doc) |
| **Codex (GPT-5.5) independent overlay + ratification** | 32× GPT-5.5 `xhigh` via Codex CLI | **LANDED** (32/32; brief: [`research/canon/CODEX_OVERLAY_BRIEF.md`](research/canon/CODEX_OVERLAY_BRIEF.md)) |
| **Federation reconciliation (Claude adjudicator, code-decided)** | 32× Claude Opus 4.8 `xhigh` adjudicator | **LANDED** (32/32; [`research/canon/reconciled/`](research/canon/reconciled/)) |

**Honesty note on provenance.** CANON is now a **two-model-signed document** wherever a
piece is **BOTH-MODEL-AGREED**. Each of the 32 pieces went through the full Federation: a
Claude independent audit, a Claude adversarial verification, an *independent* Codex (GPT-5.5)
overlay + ratification, and finally a code-decided **reconciliation** in which a Claude
adjudicator re-decided every dispute against the actual code (not by averaging). The result is
recorded per piece at [`research/canon/reconciled/CANON-NN-*.reconciled.md`](research/canon/reconciled/).
**26 / 32 pieces are BOTH-MODEL-AGREED**; the remaining **6 carry explicit STANDING
DISAGREEMENTS** — points where the two models genuinely cannot be settled from repo code alone
(live-EPERM behaviour, external pinned binaries, host-conditional CI, threat-model severity
calls). Those are enumerated, not averaged away, in the new **Federation sign-off** section at
the end of this doc. Where reconciliation overturned a Claude-half claim, the **code-grounded
finding is carried forward** and the loser is flagged.

---

## The project, end-to-end (value spine + cross-cutting layers)

ArcLink is the public half of a live **Sovereign Control Node** system: a Chutes-first
self-serve SaaS that provisions Hermes-powered **ArcPods** for paying **Captains**, with a
Python control plane, Bash deploy/ops, Docker-Compose-first topology, SQLite-first state, a
public Agent Gateway, chat-bot onboarding, billing, Academy, fleet, and an operator control
plane. The Federation decomposes the whole into **32 pieces**: a Captain-facing **value
spine** (CANON-01 … CANON-23) and **cross-cutting infrastructure** (CANON-24 … CANON-32).
Boundaries between pieces are *discovered in code* (producer output == consumer input,
verified at both ends), not asserted.

### Piece index (the locked decomposition)

> Each piece's deep, code-cited record lives at `research/canon/sections/CANON-NN-*.md`;
> its adversarial verdict at `research/canon/verify/CANON-NN-*.verify.md`. This master doc
> holds the index, the coverage proof, the cross-piece seam graph, the unified risk
> register, the drift ledger, the disagreement register, and the per-piece index table.

**Value spine**

| Piece | Title | Primary files |
|---|---|---|
| CANON-01 | Control Plane & Schema | `arclink_control.py`, `arclink_boundary.py` |
| CANON-02 | Hosted API & Transport | `arclink_hosted_api.py`, `arclink_api_auth.py`, `arclink_http.py`, `arclink_rpc_client.py`, `arclink_adapters.py` |
| CANON-03 | Web App & Product Surface | `web/**`, `arclink_product.py`, `arclink_product_surface.py`, `arclink_surface_contract.py` |
| CANON-04 | Onboarding & Provider Auth | `arclink_onboarding.py`, `arclink_onboarding_flow.py`, `arclink_onboarding_completion.py`, `arclink_onboarding_provider_auth.py` |
| CANON-05 | Public Bots (Telegram/Discord) | `arclink_public_bots.py`, `arclink_public_bot_commands.py`, `arclink_telegram.py`, `arclink_discord.py` |
| CANON-06 | Curator Onboarding | `arclink_curator_onboarding.py`, `arclink_curator_discord_onboarding.py` (+ `bin/curator-*.sh`, `bin/bootstrap-curator.sh`) |
| CANON-07 | Billing & Entitlements | `arclink_entitlements.py` (+ Stripe seam in `arclink_adapters.py`) |
| CANON-08 | Provisioning & Enrollment | `arclink_provisioning.py`, `arclink_enrollment_provisioner.py`, `arclink_fleet_enrollment.py`, `arclink_host_readiness.py`, `arclink_sovereign_worker.py`, `arclink_access.py`, `arclink_agent_access.py` |
| CANON-09 | Ingress & DNS | `arclink_ingress.py` |
| CANON-10 | Cloud Inventory & Capacity | `arclink_inventory.py`, `arclink_inventory_hetzner.py`, `arclink_inventory_linode.py`, `arclink_resource_map.py`, `arclink_asu.py` |
| CANON-11 | Executor | `arclink_executor.py` |
| CANON-12 | Public Agent Gateway & Brokers | `arclink_gateway_exec_broker.py`, `arclink_agent_supervisor_broker.py`, `arclink_deployment_exec_broker.py`, `arclink_docker_agent_supervisor.py`, `arclink_pod_comms.py`, `arclink_public_agent_bridge.py`, `arclink_agent_user_helper.py`, `arclink_agent_process_helper.py`, `arclink_migration_capture_helper.py`, `arclink_rejection_incidents.py` |
| CANON-13 | Pod Migration | `arclink_pod_migration.py` |
| CANON-14 | Operator & Admin Control | `arclink_ctl.py`, `arclink_operator_raven.py`, `arclink_operator_agent.py`, `arclink_action_worker.py`, `arclink_rollout.py` |
| CANON-15 | Operator Upgrade Pipeline | `arclink_operator_upgrade_broker.py`, `arclink_operator_upgrade_host_runner.py`, `arclink_upgrade_policy.py`, `arclink_pin_upgrade_check.py` (reconciles with `DISSECT.md`) |
| CANON-16 | LLM Router & Providers | `arclink_llm_router.py`, `arclink_model_providers.py`, `arclink_chutes.py`, `arclink_chutes_oauth.py`, `arclink_chutes_live.py` |
| CANON-17 | Academy / Crew / SOUL | `arclink_academy_programs.py`, `arclink_academy_scheduler.py`, `arclink_academy_trainer.py`, `arclink_crew_recipes.py` |
| CANON-18 | Knowledge / Memory / Notion / MCP | `arclink_memory_synthesizer.py`, `arclink_notion_ssot.py`, `arclink_notion_webhook.py`, `arclink_mcp_server.py`, `arclink_ssot_batcher.py` |
| CANON-19 | Hermes Workspace & Dashboard | `arclink_dashboard.py`, `arclink_dashboard_auth_proxy.py`, `arclink_nextcloud_access.py`, `arclink_headless_hermes_setup.py`, `arclink_skill_enablement.py` |
| CANON-20 | Sharing & Fleet Folder | `arclink_fleet.py`, `arclink_fleet_inventory_worker.py`, `arclink_fleet_share.py` |
| CANON-21 | Org Profile | `arclink_org_profile.py`, `arclink_org_profile_builder.py` |
| CANON-22 | Backup / Restore / Lifecycle / Wrapped | `arclink_wrapped.py` (+ backup/restore `bin/*.sh`) |
| CANON-23 | Diagnostics / Health / Evidence / Notifications / Live Proof | `arclink_diagnostics.py`, `arclink_health_watch.py`, `arclink_evidence.py`, `arclink_notification_delivery.py`, `arclink_live_runner.py`, `arclink_live_journey.py`, `arclink_secrets_regex.py` |

**Cross-cutting infrastructure**

| Piece | Title | Primary surface |
|---|---|---|
| CANON-24 | Deployment & Install Lane | `deploy.sh`, `init.sh`, `ralphie.sh`, `Dockerfile`, `bin/install-*.sh`, `bin/bootstrap-*.sh`, `bin/docker-entrypoint.sh`, `bin/component-upgrade.sh`, `bin/common.sh`, `bin/lib/*` |
| CANON-25 | Container Topology (Compose) | `compose.yaml`, `compose/nextcloud-compose.yml`, `bin/docker-*.sh`, `bin/arclink-docker.sh`, `bin/nextcloud-*.sh`, `.dockerignore` |
| CANON-26 | Systemd Services & Timers | `systemd/**`, `bin/install-system-services.sh`, `bin/install-user-services.sh`, `bin/install-agent-user-services.sh`, `bin/install-agent-cron-jobs.sh` |
| CANON-27 | Config & Environment | `config/**`, `.env.live(.example)`, `bin/model-providers.sh`, env precedence (`ARCLINK_*` / `ALMANAC_*`) |
| CANON-28 | CI, Smoke & Quality Gates | `.github/workflows/install-smoke.yml`, `bin/ci-*.sh`, `bin/*-smoke.sh`, `test.sh`, `pytest.ini`, `requirements-dev.txt`, `PROMPT_*.md` |
| CANON-29 | Test Corpus | `tests/**` (128 tracked `test_*.py` files), `tests/fixtures`, e2e fake/live gates, `web` playwright tests |
| CANON-30 | Hermes Plugins & Bridges | `plugins/hermes-agent/**`, `hooks/hermes-agent/**`, `bin/install-arclink-plugins.sh`, `bin/install-hermes-workspace-plugins.sh` |
| CANON-31 | Operational & Knowledge-Pipeline Scripts, Skills & Templates | `skills/**`, `templates/**`, remaining `bin/*.sh` + `bin/*.py` ops scripts (qmd/pdf/notion/vault/tailscale/memory-synth/quarto/sync) |
| CANON-32 | Documentation Corpus & Federation Provenance | `AGENTS.md`, `CANON.md`, `DISSECT.md`, `README.md`, `docs/**`, `research/**` including `research/canon/**` sections/verify/codex/reconciled/fixes, `USER_JOURNEY.md`, `GAPS.md`, `mission_status.md`, `IMPLEMENTATION_PLAN.md`, root meta files |

---

## 1. Coverage proof (file → piece)

**Headline: 766 / 766 current workspace corpus files assigned (100%).** The refreshed corpus
is the union of tracked files (`git ls-files`) and active untracked, non-ignored files
(`git ls-files --others --exclude-standard`). Every row is mapped to exactly one of the 32
pieces. Full mapping:
[`research/canon/COVERAGE_MATRIX.md`](research/canon/COVERAGE_MATRIX.md) (762 tracked rows +
4 active untracked rows, zero duplicate rows, zero unassigned rows; per-piece counts sum to
766).

> **Refresh note.** The original CANON baseline matrix covered 614 tracked product/repo files.
> After CANON itself landed, the repository gained tracked canon, DISSECT, overlay,
> verification, reconciliation, and repair artifacts. Those artifacts are now explicitly
> assigned to **CANON-32** instead of sitting outside the map. Active untracked repair outputs
> are included so this matrix reflects the current repair workspace, not only the last commit.

**Orphans (1).** `bin/arclink-dashboard-placeholder.sh` matches no explicit rule list; it was
swept into CANON-31 by the `bin/` "everything-else → CANON-31" default. Flagged for Codex —
it is covered but not *deliberately* placed.

**Double-claims (4, all resolved to a single assignment):**

| File | Declared by | Resolved to | Rationale |
|---|---|---|---|
| `python/arclink_adapters.py` | CANON-02, CANON-07 | **CANON-07** | Stripe/billing adapter is primary role; transport covered by http/rpc in CANON-02 |
| `bin/arclink-restore-smoke.sh` | CANON-22, CANON-28 | **CANON-22** | restore-smoke is a backup/restore artifact; runs in CI only transitively via CANON-29 |
| `bin/arclink-wrapped.sh` | CANON-22, CANON-31 | **CANON-31** | explicit `bin/` everything-else list |
| `bin/curator-refresh.sh` | CANON-06, CANON-31 | **CANON-31** | explicit `bin/` rule |

**Ignored local/operator scratch is still outside the matrix.** `.env.live.example` and
`analyze_vuln.md` are present locally but ignored by `.gitignore`, so
`--exclude-standard` omits them. They remain operator/scratch artifacts, not public corpus
rows. `DISSECT.md` is now tracked and assigned to CANON-32.

**Deviation noted.** `hooks/hermes-agent/**` (the `arclink-telegram-start` bridge) is assigned
to **CANON-30** (Hermes Plugins & Bridges), not CANON-32, because it is clearly Hermes plugin
bridge *code*, overriding the `hooks/ → CANON-32` default.

---

## 2. Cross-piece seam graph

Directed producer→consumer contracts, **discovered in code and verified at both ends** unless
flagged. Grouped by producer. `BEV` = both-ends-verified per the per-piece audit. Seams where
`BEV=no` **or** where the adversarial verifier found a mismatch are pulled out into
**SEAM RISKS** at the end of this section.

### Producer: CANON-01 (Control Plane & Schema)
- `CANON-01 --[append_arclink_event(conn,*,subject_kind,subject_id,event_type,metadata,...)→str]--> CANON-02` (BEV: yes; `arclink_control.py:3870` → `arclink_api_auth.py:2189`)
- `CANON-01 --[is_ip_in_cidrs / is_loopback_ip CIDR predicates]--> CANON-02` (BEV: **no** — consumer was handoff; later confirmed at `arclink_hosted_api.py:644-648`; producer `arclink_control.py:7604,7611`)
- `CANON-01 --[require_docker_trusted_host_risk_accepted / require_trusted_docker_binary fail-closed guards]--> CANON-12` (BEV: yes; `arclink_boundary.py:85,107` → `arclink_gateway_exec_broker.py:24-25`)
- `CANON-01 --[rowdict(sqlite3.Row)→dict passthrough]--> CANON-14/19/23 (many)` (BEV: yes; `arclink_boundary.py:76`; **evidence figure wrong** — 6 modules import `rowdict`, not 26; see Drift Ledger)
- `CANON-01 --[queue_notification(conn,*,target_kind,target_id,channel_kind,message,extra)→int]--> CANON-14/23` (BEV: yes; `arclink_control.py:8055` → schema `:745`; delivery `:9910`)

### Producer: CANON-02 (Hosted API & Transport)
- `CANON-02 --[_backend_client_allowed(ip,cidrs) CIDR gate]--> CANON-01 predicates` (BEV: **no** — producer hands a *spoofable* IP string (x-real-ip/XFF, 127.0.0.1 fallback) to the predicate; `arclink_hosted_api.py:646`)
- `CANON-02 --[raw_body + Stripe-Signature → process_stripe_webhook → StripeWebhookResult]--> CANON-07` (BEV: yes — verifier upgraded from "partial"; `arclink_hosted_api.py:906` ↔ `arclink_entitlements.py:508-515,157-161`)
- `CANON-02 --[public onboarding body keys channel/channel_identity/email/plan_id/model_id/session_id]--> CANON-04` (BEV: yes; `arclink_api_auth.py:40`)
- `CANON-02 --[non-HttpOnly arclink_{kind}_csrf cookie + X-ArcLink-CSRF-Token double-submit]--> CANON-03` (BEV: yes; `arclink_hosted_api.py:463` ↔ `web/src/lib/api.ts:31`)
- `CANON-02 ↔ CANON-18` MCP Streamable-HTTP (initialize/tools-call, mcp-session-id, structuredContent) (BEV: yes; `arclink_rpc_client.py:71`)
- `CANON-02 <--[X-ArcLink-Share-Request-Broker-Token verified against deployments.metadata_json.share_request_broker.token_hash]-- CANON-12` (BEV: **no** — broker producer mints raw token in CANON-12; `arclink_api_auth.py:2477`)

### Producer: CANON-03 (Web App)
- `CANON-03 --[all 50 api.ts paths POST/GET under /api/v1]--> CANON-02 _ROUTES` (BEV: yes; `web/src/lib/api.ts:43` → `arclink_hosted_api.py:3754`)
- `CANON-03 --[product_surface direct SQL column reads]--> CANON-01 ensure_schema` (BEV: verifier upgraded to yes; columns exist; `arclink_product_surface.py:414` → `arclink_control.py:1309+`)

### Producer: CANON-04 (Onboarding)
- `CANON-04 --[open_arclink_onboarding_checkout → create_checkout_session → {id,url}]--> CANON-07` (BEV: yes; `arclink_onboarding.py:664` ↔ `arclink_adapters.py:42,54,128`)
- `CANON-04 <--[sync_arclink_onboarding_after_entitlement(session_id,...) on checkout.session.completed]-- CANON-07` (BEV: **no/unsafe-path** — shape matches but consumer raises on terminal/missing session and triggers a premature commit; `arclink_onboarding.py:807` ↔ `arclink_entitlements.py:744`)
- `CANON-04 --[reserve deployments at entitlement_required; advance_arclink_entitlement_gate]--> CANON-01` (BEV: yes; `arclink_onboarding.py:614-635,811`)
- `CANON-04 <--[record_arclink_onboarding_first_agent_contact(session_id,channel,identity)]-- CANON-08` (BEV: yes; **no terminal guard** — can resurrect expired session; `arclink_onboarding.py:880`)
- `CANON-04 <--[process_onboarding_message(cfg, IncomingMessage, *, validate_bot_token)]-- CANON-06` (BEV: yes; `arclink_onboarding_flow.py:1761` ↔ `arclink_curator_onboarding.py:685`)

### Producer: CANON-05 (Public Bots)
- `CANON-05 --[notification_outbox 'public-agent-turn' row {deployment_id,prefix,user_id,agent_label,...}]--> CANON-12/23` (BEV: yes; **but `display_name` and `telegram_update_json_list` are consumer-only keys**; `arclink_public_bots.py:3919-3959` ↔ `arclink_notification_delivery.py:650-690`)
- `CANON-05 ↔ CANON-04` onboarding session create/resume/answer/checkout (BEV: yes; `arclink_public_bots.py:61`)
- `CANON-05 ↔ CANON-02` Telegram webhook secret + direct-checkout token (BEV: yes; `arclink_telegram.py:832`/`arclink_public_bots.py:1455` ↔ `arclink_hosted_api.py:2900,799`)
- `CANON-05 --[dispatch_operator_raven_command(...)]--> CANON-14` (BEV: **no** — owner not re-read line-by-line; verifier later confirmed fail-closed; `arclink_telegram.py:1305`)

### Producer: CANON-06 (Curator Onboarding)
- `CANON-06 ↔ CANON-04` IncomingMessage↔OutboundMessage + completion helpers (BEV: yes; `arclink_curator_onboarding.py:1098`)
- `CANON-06 --[operator_telegram_sender_allowed(...) shared GAP-029 gate]--> CANON-05` (BEV: yes; `arclink_curator_onboarding.py:240` ↔ `arclink_telegram.py:1144`)
- `CANON-06 ↔ CANON-14` dispatch_operator_raven_command → {message,buttons} (BEV: yes; `arclink_curator_onboarding.py:359` ↔ `arclink_operator_raven.py:349`)
- `CANON-06 --[arclink_ctl internal curator-refresh / register-curator --channels-json]--> CANON-14/31` (BEV: **no** — consumer body not opened; `bin/curator-refresh.sh:10`)

### Producer: CANON-07 (Billing & Entitlements)
- `CANON-07 --[set/upsert entitlement, advance gates, mirror subscription, grant refuel — all commit=False under webhook BEGIN]--> CANON-01` (BEV: yes-with-exception — `upsert_arclink_subscription_mirror` can receive status='none' which is **not** a valid subscription status → raises; `arclink_entitlements.py:713-762` → `arclink_control.py:4710`)
- `CANON-07 --[ReconciliationDrift{kind,user_id,detail}]--> CANON-02` (BEV: yes; `arclink_entitlements.py:30-33` → `arclink_api_auth.py:4853`)
- `CANON-07 --[sync_arclink_onboarding_after_entitlement(commit=False)]--> CANON-04` (BEV: **no** — see CANON-04 seam risk; premature commit breaks webhook atomicity; `arclink_entitlements.py:742-750`)
- `CANON-07 ↔ Stripe (self-signed HMAC, only LAST v1= parsed)` (BEV: yes; `arclink_adapters.py:149-176`)
- `CANON-07 --[refuel application mutates LOCAL chutes.monthly_budget_cents only]--> CANON-16/01` (BEV: **no** — provider-balance move is proof-gated PG-PROVIDER; `arclink_control.py:4601-4604`)

### Producer: CANON-08 (Provisioning & Enrollment)
- `CANON-08 --[HMAC-signed POST /v1/operator-upgrade, 4 headers, signed string f'{ts}\n{nonce}\n{body_hash}']--> CANON-15` (BEV: yes, byte-verified; `arclink_enrollment_provisioner.py:316-349` ↔ `arclink_operator_upgrade_broker.py:707-716`)
- `CANON-08 <--[get_pin_upgrade_action_payload → install_items]-- CANON-01` (BEV: yes; `arclink_control.py:9550-9576` → `arclink_enrollment_provisioner.py:458`)
- `CANON-08 <--[fleet enrollment callback: Bearer + JSON body → consume_fleet_enrollment]-- CANON-02` (BEV: yes; `arclink_hosted_api.py:2035-2050` → `arclink_fleet_enrollment.py:536-600`)
- `CANON-08 --[intent dict (compose+dns) → DockerComposeApplyRequest / CloudflareDnsApplyRequest]--> CANON-11` (BEV: yes; `arclink_sovereign_worker.py:1210-1243` ↔ `arclink_provisioning.py:1701-1782`)
- `CANON-08 <--[desired_arclink_ingress_records / arclink_access_urls feed intent]-- CANON-09` (BEV: yes; `arclink_provisioning.py:1487-1502` ↔ `arclink_ingress.py:46`)
- `CANON-08 <--[operator_actions.request_source=='operator-raven' confirmed-source gate]-- CANON-14` (BEV: **no** — gate strength depends on who writes request_source; `arclink_control.py:765` ↔ `arclink_enrollment_provisioner.py:2292-2297`)

### Producer: CANON-09 (Ingress & DNS)
- `CANON-09 --[desired_arclink_ingress_records(...) → dict[role,DnsRecord]]--> CANON-08` (BEV: yes; `arclink_ingress.py:46`)
- `CANON-09 <--[_persist_dns_from_intent → persist_arclink_dns_records]-- CANON-08` (BEV: yes; proxied silently dropped; `arclink_sovereign_worker.py:1982`)
- `CANON-09 --[arclink_dns_records_for_teardown → CloudflareDnsTeardownRequest.records]--> CANON-11` (BEV: yes; `arclink_ingress.py:182` → `arclink_executor.py:2583`)
- `CANON-09 <--[provider_record_id backfill via _mark_dns_provisioned]-- CANON-08/11` (BEV: yes; ingress reads but never writes it; `arclink_ingress.py:174`)

### Producer: CANON-10 (Cloud Inventory & Capacity)
- `CANON-10 --[asu_capacity/asu_consumed columns + machine_host_link FK]--> CANON-08/20` (BEV: yes; `arclink_inventory.py:479-486` → `arclink_fleet.py:316-337`)
- `CANON-10 <--[register_inventory_machine(...) keyword subset]-- CANON-08` (BEV: yes; `arclink_fleet_enrollment.py:651-668` → `arclink_inventory.py:142-161`)
- `CANON-10 ↔ CANON-01` operation idempotency reserve/replay/complete/fail (BEV: yes; `arclink_inventory.py:746-767` ↔ `arclink_control.py:3329`)
- `CANON-10 --[list_inventory_machines row dicts]--> CANON-19` (BEV: yes; `arclink_inventory.py:317-322` → `arclink_dashboard.py:604-617`)
- `CANON-10 --[shared_tailnet_host / shared_resource_lines / managed_resource_ref string builders]--> CANON-04/01` (BEV: yes; `arclink_resource_map.py:8,23,93`)

### Producer: CANON-11 (Executor)
- `CANON-11 <--[intent Mapping wrapped in DockerComposeApplyRequest; teardown remove_volumes=False]-- CANON-08` (BEV: yes; `arclink_sovereign_worker.py:1237` → `arclink_executor.py:890`)
- `CANON-11 --[POST broker_url/v1/docker-compose, X-ArcLink-Deployment-Exec-Broker-Token]--> CANON-12` (BEV: yes; `arclink_executor.py:796` ↔ `arclink_deployment_exec_broker.py:117`)
- `CANON-11 <--[docker_compose_apply / lifecycle teardown for rollback]-- CANON-13` (BEV: yes; `arclink_pod_migration.py:1147` → `arclink_executor.py:949`)
- `CANON-11 <--[restart/rotate_chutes_key/refund|cancel/dns_repair → executor requests]-- CANON-14` (BEV: yes; `arclink_action_worker.py:848` → `arclink_executor.py:1196`)
- `CANON-11 --[reserve/complete/fail_arclink_operation_idempotency]--> CANON-01` (BEV: yes; reachable ONLY when operation_conn injected — **never in production**; `arclink_executor.py:2701`)
- `CANON-11 <--[fleet_host_ssh_endpoint/user; redact_then_truncate]-- CANON-20/23` (BEV: yes; `arclink_executor.py:21`)

### Producer: CANON-12 (Public Agent Gateway & Brokers)
- `CANON-12 <--[gateway-exec POST {deployment_id,prefix,project_name,payload,timeout} + X-ArcLink-Gateway-Exec-Token]-- CANON-23` (BEV: yes; `arclink_notification_delivery.py:674-685` → `arclink_gateway_exec_broker.py:177`)
- `CANON-12 <--[deployment-exec POST]-- CANON-11` (BEV: yes; `arclink_executor.py:796` → `arclink_deployment_exec_broker.py:120`)
- `CANON-12 <--[migration POST]-- CANON-13` (BEV: yes; `arclink_pod_migration.py:469-479` → `arclink_migration_capture_helper.py:115`)
- `CANON-12 (internal)` agent-supervisor / agent-user / agent-process broker POSTs from docker_agent_supervisor (BEV: yes; env double-filtered both ends; `arclink_agent_process_helper.py:385`)
- `CANON-12 --[bridge stdin JSON {platform,bot_token,chat_id,user_id,text}]--> public_agent_bridge` (BEV: yes — tokens via stdin not argv; `arclink_public_agent_bridge.py:375`)
- `CANON-12 --[pod_comms queue_notification(channel_kind='pod-message')]--> CANON-23` (BEV: **no** — delivery-worker read of pod-message not traced; `arclink_pod_comms.py:308`)
- `CANON-12 <--[arclink_share_grants column reads]-- CANON-20` (BEV: yes; `arclink_pod_comms.py:92-110` → `arclink_control.py:1052-1069`)

### Producer: CANON-13 (Pod Migration)
- `CANON-13 --[HTTP POST /v1/migration-capture + X-ArcLink-Migration-Capture-Helper-Token]--> CANON-12` (BEV: yes; helper imports this module's own copy/materialize fns; `arclink_pod_migration.py:497-531`)
- `CANON-13 <--[render_arclink_state_roots / intent state_roots + secret_refs.llm_router_api_key]-- CANON-08` (BEV: yes; **secret_refs.llm_router_api_key conditionally absent in direct_chutes mode**; `arclink_provisioning.py:657-665` ↔ `arclink_pod_migration.py:736`)
- `CANON-13 --[DockerComposeLifecycle/Apply requests]--> CANON-11` (BEV: yes; `arclink_pod_migration.py:583-589`)
- `CANON-13 <--[reprovision action → migrate_pod(...); result['status']]-- CANON-14` (BEV: yes; **worker also accepts status=='planned' when dry_run**; `arclink_action_worker.py:1157-1180`)
- `CANON-13 ↔ CANON-01` idempotency + service health + audit + arclink_pod_migrations schema (BEV: yes; `arclink_pod_migration.py:1006-1015`)

### Producer: CANON-14 (Operator & Admin Control)
- `CANON-14 <--[Telegram approval-code + dispatch_operator_raven_command(actor_id,idempotency_key)]-- CANON-05` (BEV: yes; **approval code enforced by transport, not Raven**; `arclink_telegram.py:1305-1337` → `arclink_operator_raven.py:301`)
- `CANON-14 --[queue_arclink_admin_action → arclink_action_intents status='queued']--> CANON-19/08` (BEV: yes; `arclink_operator_raven.py:1126-1135` → `arclink_dashboard.py:2376` → `arclink_action_worker.py:460`)
- `CANON-14 --[request_operator_action(action_kind∈{upgrade,pin-upgrade}, request_source='operator-raven')]--> CANON-08/15` (BEV: yes; `arclink_operator_raven.py:1307-1314` → `arclink_control.py:8294`)
- `CANON-14 <--[fleet_capacity_summary; admin_action_execution_readiness gates pod_repair/rollout]-- CANON-20/19` (BEV: yes; `arclink_operator_raven.py:467-468` → `arclink_fleet.py:356`)
- `CANON-14 --[executor request builders, .live/.status/.action reads]--> CANON-11` (BEV: yes; `arclink_action_worker.py:32-42`)
- `CANON-14 --[rollout → plan/materialize/execute_arcpod_update_rollout_batch (record_only)]--> CANON-13` (BEV: yes; `arclink_action_worker.py:1169` → `arclink_rollout.py:844`)
- `CANON-14 --[enqueue_operator_agent_turn → notification 'public-agent-turn' extra.operator_turn]--> CANON-12/23` (BEV: **no** — consumer read of operator_turn/source_kind not opened here; `arclink_operator_agent.py:271-278`)

### Producer: CANON-15 (Operator Upgrade Pipeline)
- `CANON-15 --[register_pin_upgrade_action(items, install_items, notify_limit)]--> CANON-01` (BEV: yes; `arclink_pin_upgrade_check.py:710-715` → `arclink_control.py:9502-9534`)
- `CANON-15 --[upgrade_policy.py read-only: PIN_UPGRADE_COMPONENTS + policy display]--> CANON-14` (BEV: yes; never crosses into broker path; `arclink_upgrade_policy.py:9-17` → `arclink_operator_raven.py:35`)
- `CANON-15 <--[provisioner HMAC pre-image over raw bytes]-- CANON-08` (BEV: yes; `arclink_enrollment_provisioner.py:310-330` → `arclink_operator_upgrade_broker.py:707-714`)
- `CANON-15 <--[provisioner _pin_upgrade_apply_flag replicates 6-kind map but NOT the 7-component allowlist]-- CANON-08` (BEV: yes; broker/runner are the enforcing boundary; `arclink_operator_upgrade_broker.py:267`)
- `CANON-15 (internal) broker → host runner` schema-v1 pending/results JSON (BEV: yes; `arclink_operator_upgrade_broker.py:316-360` → `arclink_operator_upgrade_host_runner.py:279-330`)
- `CANON-15 --[runner execs component-upgrade.sh ... --skip-upgrade]--> CANON-24/31` (BEV: yes; single marker per item; `arclink_operator_upgrade_host_runner.py:248-259` → `bin/component-upgrade.sh:46`)

### Producer: CANON-16 (LLM Router & Providers)
- `CANON-16 <--[acpod_live_ raw key + hmac-sha256$ hash row]-- CANON-08` (BEV: yes; `arclink_sovereign_worker.py:163` → `arclink_control.py:6782`)
- `CANON-16 --[OpenAI chat-completions wire with central Bearer key]--> Chutes (external)` (BEV: **no** — never exercised live; only httpx.MockTransport; GAP-031 open; `arclink_llm_router.py:1213`)
- `CANON-16 --[provider-state reads arclink_llm_router_keys + arclink_llm_usage_events]--> CANON-02` (BEV: yes; **CONTRACT #3 misnames a read column**; `arclink_api_auth.py:4601` ↔ `arclink_control.py:1261`)
- `CANON-16 --[fuel-notice notification_outbox 'public-bot-user' + Refuel button]--> CANON-05/23` (BEV: **no**; `arclink_llm_router.py:1024`)
- `CANON-16 <--[config/model-providers.yaml merged over defaults]-- CANON-27` (BEV: yes; `config/model-providers.yaml:2` → `arclink_model_providers.py:60`)
- `CANON-16 --[provider_default_model/recommended_models]--> CANON-04/19` (BEV: yes; resolved at module import — not per-request; `arclink_model_providers.py:85`)

### Producer: CANON-17 (Academy / Crew / SOUL)
- `CANON-17 ↔ CANON-01` 10 academy_* tables + arclink_crew_recipes (BEV: yes; `arclink_control.py:1476-1709`)
- `CANON-17 --[academy_apply staged payload {writes_enabled, academy_soul_section, vault/qmd/skill intents,...}]--> CANON-14` (BEV: yes; **marker convention-matched, not field-read**; `arclink_academy_programs.py:2958-2996` → `arclink_action_worker.py:2077-2156`)
- `CANON-17 <--[MCP academy.propose-resource → record_academy_resource_proposal]-- CANON-18` (BEV: yes; **unhandled IntegrityError TOCTOU on the consumer**; `arclink_mcp_server.py:2162` → `arclink_academy_programs.py:683`)
- `CANON-17 --[render/merge_academy_overlay: BEGIN/END marker block only]--> CANON-19` (BEV: yes; `arclink_org_profile.py:1713-1761`)
- `CANON-17 --[project_arclink_deployment_identity_context(source=crew/academy_training)]--> CANON-08` (BEV: yes; `arclink_crew_recipes.py:895` → `arclink_provisioning.py:274-283`)
- `CANON-17 <--[public bots /academy → enroll/open/get/end_academy_mode]-- CANON-05` (BEV: yes; `arclink_public_bots.py:5816-6542`)
- `CANON-17 --[RouterAcademyTrainerClient → /chat/completions]--> CANON-16` (BEV: **no** — router endpoint not cross-read; `arclink_academy_programs.py:2175-2212`)
- `CANON-17 <--[control-academy-ce → scheduler --once --json weekly]-- CANON-25` (BEV: yes; `compose.yaml:777-803`)

### Producer: CANON-18 (Knowledge / Memory / Notion / MCP)
- `CANON-18 --[systemctl --user start arclink-ssot-batcher.service]--> CANON-26` (BEV: yes; `arclink_notion_webhook.py:42-49`)
- `CANON-18 --[process_pending_notion_events / consume_notion_reindex_queue]--> CANON-01` (BEV: yes; `arclink_ssot_batcher.py:13-14` → `arclink_control.py:19206`)
- `CANON-18 --[notion_verify_signature HMAC-SHA256 compare_digest]--> CANON-01` (BEV: yes; `arclink_notion_webhook.py:348` → `arclink_control.py:12135`)
- `CANON-18 <--[ctl arm/reset/mark/get verification-token; handshake/preflight]-- CANON-14` (BEV: yes; `arclink_notion_webhook.py:109` → `arclink_ctl.py:26-29`)
- `CANON-18 --[MCP ssot.write → enqueue_ssot_write; _normalize_ssot_write_result]--> CANON-01` (BEV: **no** in record — verifier CONFIRMED broker is fail-closed on destructive ops at `arclink_control.py:17105-17112`; **normalizer reads applied/queued/approval_required, NOT the record's claimed final_state/target_id/url/id**)
- `CANON-18 --[_mcp_tool_call(qmd 'query'|'get', MCP 2025-03-26)]--> CANON-31/external qmd` (BEV: **no** — qmd external; protocol-version comment stale vs pinned 2.5.3)

### Producer: CANON-19 (Hermes Workspace & Dashboard)
- `CANON-19 --[read_arclink_user/admin_dashboard → JSON]--> CANON-02` (BEV: yes; `arclink_dashboard.py:1797` → `arclink_api_auth.py:1181`)
- `CANON-19 --[queue_arclink_admin_action]--> CANON-14` (BEV: yes; UNIQUE-index hardened; `arclink_dashboard.py:2376` → `arclink_action_worker.py:461`)
- `CANON-19 <--[run_readiness/run_diagnostics .to_dict() + build_journey steps]-- CANON-23` (BEV: **no** — but verifier found required_env divergence: dashboard ignores `CLOUDFLARE_API_TOKEN_REF`; `arclink_dashboard.py:537-550`)
- `CANON-19 <--[arclink-web-access.json keys incl. SSO secret/subject]-- CANON-08` (BEV: **REFUTED** — record said SSO path is dead; producer chain IS wired in Docker mode → live cross-deployment SSO; `arclink_dashboard_auth_proxy.py:173-193`)
- `CANON-19 <--[headless setup argv]-- CANON-08` (BEV: yes; **`--agent-title` never actually sent**; `arclink_enrollment_provisioner.py:1404-1432`)
- `CANON-19 <--[arclink-academy-approved-skills.json applier]-- CANON-17/31` (BEV: **no**; `arclink_skill_enablement.py:189-217`)
- `CANON-19 --[evaluate_chutes_deployment_boundary().to_public()]--> CANON-16 (read)` (BEV: **no**; `arclink_dashboard.py:1743-1763`)

### Producer: CANON-20 (Sharing & Fleet Folder)
- `CANON-20 <--[docker-job-loop.sh execs fleet_share.py reconcile/sync-local]-- CANON-24/25` (BEV: yes; `compose.yaml:1091` → `arclink_fleet_share.py:863`)
- `CANON-20 <--[ensure_fleet_share / ensure_hub_repo; place_deployment/remove_placement]-- CANON-08` (BEV: yes; `arclink_sovereign_worker.py:913-916` → `arclink_fleet_share.py:384`)
- `CANON-20 <--[register_fleet_host(...); process_due_hosts]-- CANON-10` (BEV: yes; `arclink_inventory.py:174` → `arclink_fleet.py:158`)
- `CANON-20 --[ssh arclink-fleet-probe-wrapper <kind> → JSON]--> CANON-31/24` (BEV: yes; **consumer reads top-level capacity_slots/observed_load the wrapper never emits — producer-subset+fallback, not key-by-key**; `arclink_fleet_inventory_worker.py:184` ↔ `bin/arclink-fleet-probe-wrapper:53-71`)
- `CANON-20 --[compute_asu / current_load]--> CANON-10` (BEV: yes; `arclink_fleet_inventory_worker.py:367-368` → `arclink_asu.py:42`)
- `CANON-20 --[append_audit/event/queue_notification]--> CANON-01` (BEV: yes; `arclink_fleet_inventory_worker.py:263-270`)
- `CANON-20 --[ARCLINK_FLEET_SHARED_ROOT=/fleet-shared]--> CANON-19/03/30` (BEV: **no** — Drive/Code plugin read is CANON-30; `arclink_provisioning.py:1342-1344`)

### Producer: CANON-21 (Org Profile)
- `CANON-21 --[settings('org_profile_revision', checksum)]--> CANON-01` (BEV: yes; org_profile_* tables write-only/unread; `arclink_org_profile.py:2046`)
- `CANON-21 ↔ CANON-04/08` agent_identity.org_profile_person_id (BEV: yes; `arclink_org_profile.py:2065`)
- `CANON-21 --[managed-context payload keys → materialize_agent_context]--> CANON-19/01` (BEV: yes; `arclink_org_profile.py:1586` → `arclink_control.py:17760-17764`)
- `CANON-21 --[render_soul_for_identity → SOUL + identity dict]--> CANON-19` (BEV: yes; `arclink_org_profile.py:1884` → `arclink_headless_hermes_setup.py:353`)
- `CANON-21 --[merge_academy_overlay marker block]--> CANON-17` (BEV: **no** — academy capsule body owned by CANON-17; `arclink_org_profile.py:1745`)
- `CANON-21 --[builder shells arclink-ctl org-profile apply --file ... --yes]--> CANON-14/31` (BEV: yes; `arclink_org_profile_builder.py:623` → `arclink_ctl.py:238-250`)

### Producer: CANON-22 (Backup / Restore / Wrapped)
- `CANON-22 --[notification_outbox 'captain-wrapped' + extra_json{report_id,...}]--> CANON-23` (BEV: yes; **no claim/lease → double-send risk**; `arclink_wrapped.py:921-936` ↔ `arclink_notification_delivery.py:1803-1825`)
- `CANON-22 --[persistent-failure operator notice (tui-only, attempt>=3)]--> CANON-23` (BEV: yes; `arclink_wrapped.py:988-1010`)
- `CANON-22 <--[arclink-github-backup.service ExecStart backup-to-github.sh]-- CANON-26` (BEV: yes; `systemd/user/arclink-github-backup.service:6`)
- `CANON-22 <--[install-agent-cron-jobs.sh → backup-agent-home.sh hermes_home (4h cron)]-- CANON-26` (BEV: yes; `bin/install-agent-cron-jobs.sh:45`)
- `CANON-22 <--[docker-job-loop.sh arclink-wrapped 300 ./bin/arclink-wrapped.sh --json]-- CANON-25/08` (BEV: yes; `python/arclink_provisioning.py:1315`)
- `CANON-22 ↔ CANON-01` schema + CHECK + utc_now_iso (BEV: yes; `arclink_control.py:1738-1750`)
- `CANON-22 <--[redact_value/contains_secret_material]-- CANON-23` (BEV: yes; `arclink_wrapped.py:38-39`)
- `CANON-22 --[restore-smoke routes NO restore through executor (asserted absence)]--> CANON-11` (BEV: yes; `bin/arclink-restore-smoke.sh:7-11`)

### Producer: CANON-23 (Diagnostics / Health / Evidence / Notifications / Live Proof)
- `CANON-23 <--[run_readiness().to_dict()]-- CANON-08` (BEV: yes; `arclink_live_runner.py:670` ↔ `arclink_host_readiness.py:57-61`)
- `CANON-23 ↔ CANON-01` queue_notification / fetch_undelivered / store_evidence_run / status domain (BEV: yes; `arclink_health_watch.py:248`)
- `CANON-23 --[run_readiness/run_diagnostics/build_journey]--> CANON-19` (BEV: yes; `arclink_dashboard.py:537-562`)
- `CANON-23 --[run_public_agent_turns_once → summary]--> CANON-02` (BEV: yes; `arclink_hosted_api.py:130` → `arclink_notification_delivery.py:1652`)
- `CANON-23 <--[load_router_config; create_app(upstream_transport=MockTransport)]-- CANON-16` (BEV: yes; `arclink_live_runner.py:579-617`)
- `CANON-23 --[POST /v1/public-agent-bridge + X-ArcLink-Gateway-Exec-Token; stdin payload]--> CANON-12` (BEV: **no** — broker route not re-read; **and detached path writes bot_token to a 0600 job file**; `arclink_notification_delivery.py:334-389`)
- `CANON-23 --[telegram_send_message/discord_send_message return shapes]--> CANON-05/adapters` (BEV: record said **no**; verifier CONFIRMED both ends hold; `arclink_notification_delivery.py:1335,1380`)

### Producer: CANON-24 (Deployment & Install Lane)
- `CANON-24 <--[host-runner execs component-upgrade.sh; status marker re-parsed]-- CANON-15` (BEV: yes; `arclink_operator_upgrade_host_runner.py:276` ↔ `bin/component-upgrade.sh:680-695`)
- `CANON-24 (internal) component-upgrade.sh → deploy.sh upgrade` (BEV: yes; `bin/component-upgrade.sh:497-538`)
- `CANON-24 <--[Dockerfile reads config/pins.json components]-- CANON-27` (BEV: yes; `Dockerfile:74-86`)
- `CANON-24 --[install-system/user-services.sh + DEFER_START=1]--> CANON-26` (BEV: **no** — services not re-read here; `bin/deploy.sh:5534`)
- `CANON-24 --[init.sh bootstrap.handshake / activate-agent agents.register]--> CANON-02/04` (BEV: **no**; **divergent payload shapes auto_provision vs source_ip**; `bin/init.sh:444-484`)
- `CANON-24 --[docker-entrypoint writes docker.env keys]--> CANON-25` (BEV: **no**; `bin/docker-entrypoint.sh:391-592`)
- `CANON-24 --[ensure_llm_router_key / ensure_agent_mcp_bootstrap_token]--> CANON-01` (BEV: **no**; `bin/install-operator-hermes-home.sh:86-94`)

### Producer: CANON-25 (Container Topology / Compose)
- `CANON-25 --[operator-upgrade-broker typed-JSON queue (no docker.sock)]--> CANON-15` (BEV: yes; `compose.yaml:862` ↔ `arclink_operator_upgrade_broker.py:277`)
- `CANON-25 --[gateway-exec-broker 0.0.0.0:8911 + docker.sock]--> CANON-12` (BEV: yes; `compose.yaml:1008` ↔ `arclink_gateway_exec_broker.py:33`)
- `CANON-25 --[control-api 127.0.0.1:8900]--> CANON-02` (BEV: yes; `compose.yaml:73,550`)
- `CANON-25 --[all 7 brokers require_docker_trusted_host_risk_accepted at startup]--> CANON-01` (BEV: yes; `compose.yaml:654` ↔ `arclink_boundary.py:80-97`)
- `CANON-25 --[docker-job-loop.sh status JSON]--> CANON-23/19` (BEV: **no** — **key-name drift job/returncode vs job_name/exit_code, survives only via or-fallback**; `bin/docker-job-loop.sh:81-90` ↔ `bin/docker-health.sh:250`)
- `CANON-25 <--[arclink-docker.sh compose() driven by ./deploy.sh control]-- CANON-24` (BEV: **no**; `bin/arclink-docker.sh:6-7`)
- `CANON-25 <--[image/tag pins + traefik config]-- CANON-27` (BEV: **no**; `compose.yaml:261`)

### Producer: CANON-26 (Systemd Services & Timers)
- `CANON-26 --[oneshot exec bin/memory-synth.sh]--> CANON-18` (BEV: yes; `systemd/.../arclink-memory-synth.service:6`)
- `CANON-26 --[notification-delivery 5s, health-watch 15m oneshots]--> CANON-23` (BEV: yes; `systemd/.../arclink-notification-delivery.timer:5-6`)
- `CANON-26 --[enrollment-provision.sh [--claims-only]]--> CANON-08` (BEV: yes; `bin/install-system-services.sh:87`)
- `CANON-26 --[dashboard-proxy unit 5 flags]--> CANON-19` (BEV: yes; `bin/install-agent-user-services.sh:434`)
- `CANON-26 <--[common.sh gating helpers]-- CANON-24` (BEV: yes; `bin/install-user-services.sh:12`)
- `CANON-26 --[qmd/quarto/pdf/docs-sync/vault-watch exec CLI/scripts]--> CANON-31` (BEV: yes; `systemd/.../arclink-qmd-update.service:6`)
- `CANON-26 --[curator onboarding/refresh/gateway exec]--> CANON-06` (BEV: yes; `systemd/.../arclink-curator-onboarding.service:7`)
- `CANON-26 --[user-agent-backup.service → backup-agent-home.sh; github-backup]--> CANON-22` (BEV: **no**; `bin/install-agent-user-services.sh:333`)
- `CANON-26 <--[per-agent dashboard ports from arclink-web-access.json]-- CANON-19` (BEV: **no** — **hard subscript fails OPEN on malformed JSON**; `bin/install-agent-user-services.sh:286-289`)
- `CANON-26 --[per-agent gateway unit HERMES_BIN gateway run --replace]--> CANON-30` (BEV: **no**; `bin/install-agent-user-services.sh:383`)

### Producer: CANON-27 (Config & Environment)
- `CANON-27 --[config/pins.json components]--> CANON-15` (BEV: yes; **pins.json has 13 components, MANAGED_COMPONENTS=8 → subset not equality**; `config/pins.json:7-11` → `arclink_pin_upgrade_check.py:99-100`)
- `CANON-27 --[pins.sh pins_get/pins_resolve_inherited_ref stdout]--> CANON-24` (BEV: yes; `bin/pins.sh:40` → `bin/common.sh:553`)
- `CANON-27 --[model-providers.yaml preset→target]--> CANON-16` (BEV: yes; `config/model-providers.yaml:3` → `arclink_model_providers.py:60`)
- `CANON-27 --[docker-authority-inventory.json compose_boundary structured fields]--> CANON-12/25` (BEV: yes for the **5 compose-derived fields only**; prose not validated; `config/docker-authority-inventory.json:2228-2247`)
- `CANON-27 --[traefik-control.yaml routers/services]--> CANON-25` (BEV: **no** in record — verifier CONFIRMED all 4 upstreams are defined compose services; `config/traefik-control.yaml:1-43`)
- `CANON-27 --[team-resources.example.tsv pipe-delimited]--> CANON-31` (BEV: yes; `config/team-resources.example.tsv:1` → `bin/clone-team-resources.sh:54`)
- `CANON-27 --[academy-source-lanes.example.json (DECORATIVE per record; ACTUALLY a drift-guarded test fixture)]--> CANON-17` (BEV: yes; refuted as decorative; `tests/test_arclink_academy_trainer.py:256-287`)
- `CANON-27 ↔ CANON-03` env precedence (ARCLINK_ wins; **ALMANAC_* aliases are vapor — zero in source**) (BEV: yes; `arclink_product.py:12,42-66`)

### Producer: CANON-28 (CI, Smoke & Quality Gates)
- `CANON-28 --[python-regressions runs each tests/test_*.py via python3 (NOT pytest)]--> CANON-29` (BEV: **no** — standalone-executable convention; **10 orphan tests never run**; `.github/workflows/install-smoke.yml:33,40`)
- `CANON-28 --[web-regressions lint && test && build]--> CANON-03` (BEV: yes; `.github/workflows/install-smoke.yml:64-67`)
- `CANON-28 --[deploy.sh --apply-install/--apply-remove with ARCLINK_INSTALL_ANSWERS_FILE]--> CANON-24` (BEV: yes; `bin/ci-install-smoke.sh:2503` ↔ `bin/deploy.sh:24,757,768`)
- `CANON-28 <--[JSONL telemetry session_id + tool_token_injected]-- CANON-30` (BEV: yes; `plugins/.../arclink-managed-context/__init__.py:1888-1890` → `bin/live-agent-tool-smoke.sh:163`)
- `CANON-28 <--[pdf-ingest status.json key set]-- CANON-31` (BEV: yes; `bin/pdf-ingest.py:604-621` ↔ `bin/ci-preflight.sh:261-265`)
- `CANON-28 <--[arclink-restore-smoke.sh CLI + JSON shape]-- CANON-29` (BEV: yes — verifier upgraded from PARTIAL to FULL; `bin/arclink-restore-smoke.sh:258-265` ↔ `tests/test_backup_git_regressions.py:14`)

### Producer: CANON-29 (Test Corpus)
- `CANON-29 <--[ensure_schema(conn) + helper INSERTs]-- CANON-01` (BEV: **no** — helper side verified, DDL not column-diffed; `tests/arclink_test_helpers.py:35`)
- `CANON-29 ↔ CANON-02` route_arclink_hosted_api(...) → (status,payload,headers) (BEV: yes; `tests/test_arclink_e2e_fake.py:45-51`)
- `CANON-29 <--[render_traefik_dynamic_labels deep-equals golden JSON]-- CANON-09` (BEV: yes; `tests/test_arclink_ingress.py:72-75`)
- `CANON-29 <--[sign_stripe_webhook accepted by route]-- CANON-07` (BEV: yes; `tests/arclink_test_helpers.py:111`)
- `CANON-29 --[each test_*.py runnable as python3 <file> (__main__ convention)]--> CANON-28` (BEV: yes mechanism; **coverage promise breached by 10 orphans**; `.github/workflows/install-smoke.yml:38-40`)
- `CANON-29 --[web .mjs via node --test; playwright]--> CANON-03` (BEV: yes; `web/tests/test_api_client.mjs:3-5`)

### Producer: CANON-30 (Hermes Plugins & Bridges)
- `CANON-30 --[Drive/Code POST /user/share-grants/broker + share-request-broker-token]--> CANON-02` (BEV: yes — broker-token hmac auth confirmed; `plugins/.../drive/.../plugin_api.py:919-988` ↔ `arclink_api_auth.py:3525-3531`)
- `CANON-30 --[managed-context _pre_tool_call sets args['token'] for MCP tools]--> CANON-18` (BEV: record said **yes**; **REFUTED — `_TOKEN_TOOL_NAMES` is NOT a superset; pod_comms.*/agents.register cross the seam with token='' → validate_token fails**; `plugins/.../arclink-managed-context/__init__.py:1869-1879` ↔ `arclink_mcp_server.py:1094,1989`)
- `CANON-30 <--[arclink-crew reads crew_dashboards from arclink-web-access.json]-- CANON-08/19` (BEV: yes; real producer is `arclink_provisioning.py:842-855` via env hop, not the cited sovereign-worker line)
- `CANON-30 --[register(ctx) hooks + _pre_llm_call → {'context':str}]--> Hermes runtime (external)` (BEV: **no**)
- `CANON-30 <--[installers argv <repo> <hermes-home> [plugin...]]-- CANON-24/06/28` (BEV: yes; `bin/init.sh:296`)
- `CANON-30 --[installer mutates config.yaml; sync execs external skills_sync.py]--> Hermes runtime (external)` (BEV: **no**)

### Producer: CANON-31 (Ops Scripts, Skills & Templates)
- `CANON-31 <--[14 systemd units exec wrapper scripts no-args]-- CANON-26` (BEV: yes; `systemd/user/arclink-vault-watch.service`)
- `CANON-31 --[skill helpers + run-first-contact.sh call MCP tools via arclink_rpc_client.py]--> CANON-18` (BEV: yes mechanism; **only 5 of 14 tools are script-invoked; the other 9 are SKILL.md prose**; `arclink_mcp_server.py:2005`)
- `CANON-31 --[run-first-contact.sh → write_managed_memory_stubs(payload)]--> CANON-01` (BEV: yes; **validation only on local-file branch, not the MCP-fetch branch**; `run-first-contact.sh:307-311` → `arclink_control.py:18450`)
- `CANON-31 --[vault-repo-sync.sh / curator-refresh.sh exec arclink_ctl internal subparsers]--> CANON-14` (BEV: yes; `bin/vault-repo-sync.sh:10` → `arclink_ctl.py:268`)
- `CANON-31 <--[arclink_notion_webhook kicks arclink-ssot-batcher.service]-- CANON-18` (BEV: yes; **adjacent function bodies actually live in arclink_control (CANON-01), not the exec'd module**; `arclink_ssot_batcher.sh:13`)
- `CANON-31 --[upsert-hermes-mcps.sh mutates mcp_servers via hermes_cli.config]--> Hermes runtime (external)` (BEV: **no**)
- `CANON-31 ↔ CANON-17` arclink-academy SKILL.md → academy.search-graduates/propose-resource (BEV: yes; `skills/arclink-academy/SKILL.md:28-30` → `arclink_mcp_server.py:2137`)

### Producer: CANON-32 (Documentation Corpus & Provenance)
- `CANON-32 <--[table inventory GTB §4 + architecture.md (44+9) vs code DDL (45+10)]-- CANON-01` (BEV: yes — **doc stale**; `ARCLINK_GROUND_TRUTH_BRIEF.md:251`)
- `CANON-32 <--[GTB §2 vocab + _NEXT_ACTION_RE]-- CANON-03` (BEV: yes; alternation-equal, not byte-identical; `ARCLINK_GROUND_TRUTH_BRIEF.md:81-83` ↔ `arclink_surface_contract.py:41-43`)
- `CANON-32 ↔ CANON-02` committed OpenAPI (71 paths) vs build_arclink_openapi_spec() (BEV: yes content; **byte-parity unguarded and non-reproducible**; `docs/openapi/arclink-v1.openapi.json` ↔ `arclink_hosted_api.py:3689`)
- `CANON-32 <--[GAP-016 copy_duplicate_policy string]-- CANON-07/20` (BEV: yes — **GAPS.md quotes stale value**; `GAPS.md:746` vs `arclink_mcp_server.py:120`)
- `CANON-32 --[DISSECT.md scoped to operator-upgrade pipeline only]--> CANON-15` (BEV: yes; `DISSECT.md:1`)

### SEAM RISKS (BEV=no or verifier-found mismatch)

| # | Seam | Issue | Cite |
|---|---|---|---|
| S1 | CANON-07 → CANON-04 (entitlement sync) | **Premature `conn.commit()` mid-webhook** via `expire_stale_arclink_onboarding_sessions(commit=True)`; entitlement write commits before event marked processed → paying user entitled while webhook loops failed/retry. Breaks the single-transaction invariant. **HIGH** | `arclink_entitlements.py:744` → `arclink_onboarding.py:807,324-325` |
| S2 | CANON-30 → CANON-18 (token injection) | **`_TOKEN_TOOL_NAMES` not a superset**: `pod_comms.*`/`agents.register` advertise an agent-filled token but never receive one → `validate_token` fails. **HIGH live break.** | `arclink-managed-context/__init__.py:276-302` vs `arclink_mcp_server.py:1094,1989` |
| S3 | CANON-19 ← CANON-08 (SSO keys) | Record said SSO path dead; **producer chain IS wired in Docker → live per-user cross-deployment SSO cookie**. Trust-boundary surface. | `bin/install-deployment-hermes-home.sh:169-170`; `arclink_dashboard_auth_proxy.py:735` |
| S4 | CANON-25 → CANON-23/19 (job status) | **Key-name drift** `job`/`returncode` (producer) vs `job_name`/`exit_code` (consumer); works only via or-fallback; brittle to any strict consumer. | `bin/docker-job-loop.sh:82` vs `bin/docker-health.sh:250` |
| S5 | CANON-26 ← CANON-19 (per-agent ports) | Hard dict subscript on `arclink-web-access.json` **fails OPEN** (renders empty-port units, half-enabled). | `bin/install-agent-user-services.sh:286-294` |
| S6 | CANON-20 → CANON-31/24 (probe wrapper) | Consumer reads top-level `capacity_slots`/`observed_load` the wrapper never emits — producer-subset + `.get()` fallback, **not** "key-by-key". | `arclink_fleet_inventory_worker.py:352` vs `bin/arclink-fleet-probe-wrapper:53-71` |
| S7 | CANON-13 ← CANON-08 (secret_refs) | `secret_refs.llm_router_api_key` conditionally absent in `direct_chutes` mode → migration silently skips router-key ensure (null-safe). | `arclink_provisioning.py:657-665` vs `arclink_pod_migration.py:736` |
| S8 | CANON-23 → CANON-12 (bridge) | Detached delivery path writes **bot_token to a 0600 job file** (contradicts "stdin-only" verdict). | `arclink_notification_delivery.py:973-1001` |
| S9 | CANON-12 → CANON-23 (pod-message / notification) | Two non-atomic transactions: message committed, then `queue_notification` commits separately; crash between leaves message with no notification. | `arclink_pod_comms.py:306,308`; `arclink_control.py:8071` |
| S10 | CANON-24 → CANON-02/04 (handshake) | Divergent producer argument shapes (`auto_provision` vs `source_ip`) to the same `bootstrap.handshake` MCP tool. | `init.sh:267` vs `bin/init.sh:453` |
| S11 | CANON-24 ↔ CANON-24 (operator breadcrumb) | Producer writes `ARCLINK_OPERATOR_DEPLOYED_CONFIG_FILE/_REPO_DIR`; consumer reads `_CONFIG/_REPO` → config discovery is dead, falls to hardcoded default. | `bin/deploy.sh:2856,2858` vs `bin/component-upgrade.sh:515` |
| S12 | CANON-31 → CANON-18 (skill→MCP) | Record claims 14 tools both-ends-verified; only 5 are executed code, 9 are SKILL.md prose. | `skills/**/scripts/*.sh` vs `skills/**/SKILL.md` |

---

## 3. Unified risk register (severity-ranked, code-cited)

> Merged from every piece's `risks` + every verifier `newGaps`, deduplicated, HIGH first.
> Each row: piece · severity · description · `path:line`. A risk and its verifier upgrade
> are collapsed to a single row at the higher severity.

**Counts (Claude-half register): HIGH = 14 · MEDIUM = 48 · LOW = 41 · INFO = 23.** (INFO items
are listed compactly at the end; full INFO detail lives in the per-piece records.)

**Counts after Federation reconciliation:** the rows below carry `[Federation: was X]`
annotations wherever reconciliation re-levelled a severity against code, and the new
**Federation-added (Codex-found, code-confirmed)** subsection appends every Codex finding that
re-verified true (none rejected at the conclusion level). **Federation totals incl. the
Codex-added subsection: HIGH = 16 · MEDIUM ≈ 70 · LOW ≈ 60 · INFO ≈ 28.** Per-piece exact
severities are authoritative in [`research/canon/reconciled/`](research/canon/reconciled/).

### HIGH (14)

| Piece | Risk | Cite |
|---|---|---|
| CANON-04 | Terminal/expired onboarding session at `checkout.session.completed` forces the **entire Stripe webhook to roll back and re-raise (replayable-forever)**; a paying customer whose completed event lands >24h after session creation wedges their own webhook permanently. | `arclink_onboarding.py:336-341,807`; `arclink_entitlements.py:799-809` |
| CANON-07 | **Atomicity break**: onboarding-sync path triggers a premature `conn.commit()` inside the webhook BEGIN; entitlement write + gate advance commit BEFORE the event is marked processed → user entitled (paid) while webhook loops failed/retry. | `arclink_entitlements.py:744`; `arclink_onboarding.py:271,324-325` |
| CANON-10 | **`parse_probe_output` `continue` on `/dev/`/`overlay`/`Filesystem` skips every real `df -BG` device line** → `disk_gib` always 0 on real probe output → `asu_capacity` collapses to 0 → probed host **can never receive placements** under standard_unit. Untested (all tests inject dict). *[Federation: was LOW in the original record; raised to HIGH — executed `compute_asu(...)==0`, gate `arclink_fleet.py:143,701`.]* | `arclink_inventory.py:404,410-416`; `arclink_asu.py:61` |
| CANON-11 | Durable cross-process idempotency for live Chutes/Stripe is **inert in production** (`operation_conn` never injected); retried refund/cancel after a restart could **double-execute against the provider**. | `arclink_executor.py:852` |
| CANON-12 | **Bot token persisted to disk** on the detached gateway-exec delivery path (0600 job file), contradicting the stdin-only secret-handling verdict. *[Federation: record framed stdin-only as a STRENGTH; reconciled to a HIGH defect.]* | `arclink_notification_delivery.py:973-1001` |
| CANON-12 | agent-process-helper drops **ALL Linux caps** (`cap_drop: ALL`, no cap_add, no-new-privileges) yet privilege-drops via `setpriv --reuid/--regid` (needs CAP_SETUID/SETGID) → **likely EPERM, breaks every agent process**. *[Federation: HIGH pending live proof — STANDING DISAGREEMENT; both models read the compose/code mismatch, neither can execute the kernel EPERM from a read-only audit.]* | `compose.yaml:911-918` vs `arclink_agent_process_helper.py:444-457` |
| CANON-13 | **No mutual exclusion for concurrent migrations** of the same deployment: reserve treats only TERMINAL statuses as replay, so a concurrent 'running' row returns replay=False and two `migrate_pod` calls both stop source + capture concurrently. *[Federation: latent today behind a single serial worker loop; distinct reprovision actions use distinct keys so idempotency gives zero protection — `arclink_action_worker.py:1154-1157`.]* | `arclink_pod_migration.py:1006-1017` |
| CANON-17 | Live crawler + live LLM-router Trainer ship **default-ON in compose**, contradicting fake-adapter-default convention; weekly outbound fetches + live inference run unless explicitly disabled. | `arclink_academy_scheduler.py:625`; `compose.yaml:97` |
| CANON-17 | **DNS-rebinding/TOCTOU**: `_url_allowed_for_live_crawl` resolves+validates host, then `_default_fetch_url` reconnects separately → host public at check, private at fetch reaches internal services. | `arclink_academy_scheduler.py:195-204,222` |
| CANON-15 | **Single poison/dangling-symlink pending file permanently wedges the host-runner drain** (no try/except around the loop; re-globbed every ~5s, blocks all upgrades). Trusted-host boundary. | `arclink_operator_upgrade_host_runner.py:412,367-376` |
| CANON-22 | Operator-queued pin bumps **auto-commit+push `config/pins.json` to the live production branch** (host-runner passes only `--skip-upgrade`, not `--skip-push`). | `bin/component-upgrade.sh:658-662` |
| CANON-22 | **Generate-then-enqueue-throw → unbounded duplicate `generated` reports** every 300s tick: a 'failed' row shadows the 'generated' row in the due query and bypasses the signal gate. | `arclink_wrapped.py:1043-1056,1079-1094` |
| CANON-26 | **Silent FAIL-OPEN on bad/renamed `arclink-web-access.json`**: `eval "$(python3 ...)"` swallows JSONDecodeError/KeyError; installer renders + enables dashboard/proxy units with EMPTY ports then aborts mid-restart → half-enabled broken units. | `bin/install-agent-user-services.sh:276-294,416,434` |
| CANON-29 | **10 orphaned regression tests** (not 3) are unreachable from their file's `__main__` and **never run in CI**, incl. two GAP-019 broker fail-closed boundary proofs (proven by AST + raise-injection). | `tests/test_arclink_docker.py:4854,2953`; `tests/test_arclink_executor.py:1550,1586` (+5 more) |
| CANON-13 | **Production verification is effectively non-verifying** (raised MEDIUM→HIGH): the default verifier reads deployment-keyed `arclink_service_health` that apply never seeds, ignores `checked_at`/target host, and the prod action-worker injects no verifier → a migration is marked succeeded on **empty AND stale source health**. *[Federation: was MEDIUM (verifier); raised to HIGH for the no-injected-verifier prod path.]* | `arclink_action_worker.py:1169-1178`; `arclink_pod_migration.py:563-572`; `arclink_control.py:1230` |
| CANON-04 | **"Public store cannot hold provider keys" is FALSE** (raised INFO/strength→HIGH gap): the exec-verified value regex lets Anthropic `sk-ant-`, OpenAI `sk-`/`sk-proj-`, Chutes `cpk_`, and AWS `AKIA` keys through into persisted free-text hint fields. *[Federation: record asserted secret-hostility as a strength; reconciled to a HIGH partial-protection gap.]* | `arclink_onboarding.py:116-126` |

### MEDIUM (48)

| Piece | Risk | Cite |
|---|---|---|
| CANON-01 | `Config.from_env` int() casts unguarded → non-numeric env override raises unhandled `ValueError` at load, hard-failing every config consumer. | `arclink_control.py:492-546` |
| CANON-01 | Secret material can reach event/notification rows: `append_arclink_event.metadata` and `queue_notification.extra` do NOT call `reject_secret_material`. | `arclink_control.py:3886,8069` |
| CANON-01 | Config-file value silent truncation to first shlex token → `ARCLINK_BACKEND_ALLOWED_CIDRS` allowlist silently narrowed/mangled. | `arclink_control.py:330-331` |
| CANON-01 | `connect_db` runs `expire_stale_ssot_pending_writes` UPDATE+commit on **every** open → connection-open is a write/lock-contention path the OUTPUT CONTRACT omits. | `arclink_control.py:589-591` |
| CANON-02 | `_remote_ip_from_headers` falls back to attacker-influenceable `x-real-ip` when remote_addr empty → CIDR-gate spoof if a proxy drops REMOTE_ADDR. | `arclink_hosted_api.py:635` |
| CANON-02 | Dev session-hash **pepper used when `ARCLINK_BASE_DOMAIN` unset/blank** → prod deploy forgetting it runs with a publicly-known pepper → forgeable session/CSRF given DB read. | `arclink_api_auth.py:281` |
| CANON-02 | **Broker proof tokens accept legacy plain SHA-256** and are NOT rotated on re-auth; public broker route has no session/CIDR → stolen DB hash forgeable indefinitely. | `arclink_api_auth.py:248-257,2477` |
| CANON-03 | `product_surface` blanket `except Exception` collapses all errors (incl. schema drift) into a generic 400, masking real failures. | `arclink_product_surface.py:762` |
| CANON-03 | Web client renders server-supplied `checkout_url`/access URLs as `<a href>` with no client-side scheme allowlist (open-redirect/`javascript:` surface). | `web/src/app/checkout/success/page.tsx:269` |
| CANON-03 | Non-UTF-8 POST body escapes the `product_surface` catch-all → unhandled traceback-leaking 500 (bypasses surface_contract linter). | `arclink_product_surface.py:789` |
| CANON-03 | Admin CIDR allowlist depends on an **unproven Next-proxy XFF-forwarding assumption** (loopback-trusted proxy could neuter the allowlist). | `web/next.config.ts:3,10-11` vs `arclink_hosted_api.py:624-648` |
| CANON-04 | NEW onboarding has **no terminal 'completed' transition**; sessions stop at first_contacted → any consumer treating 'completed' as success never sees it. | `arclink_onboarding.py:880` |
| CANON-04 | Secret rejection enforced only at entry points, not at the DB write (`_update_session` metadata/hint UPDATEs unscanned). *[Federation: was MEDIUM; downgraded to LOW/INFO — the record's concrete bypass cite `api_auth.py:1093` IS scanned via `json_dumps_safe`→`reject_secret_material`; no reachable external exploit (`arclink_api_auth.py:1092-1095`; `arclink_boundary.py:65-73`).]* | `arclink_onboarding.py:344-383` |
| CANON-04 | OLD path makes **live outbound OAuth HTTP to OpenAI/Anthropic** driven by user input during onboarding; abuse controls live elsewhere. | `arclink_onboarding_provider_auth.py:300,326,408` |
| CANON-04 | OLD `_completion.py` emits **plaintext shared password into chat text**; scrub-on-ack is best-effort. | `arclink_onboarding_completion.py:411-432` |
| CANON-04 | `sync_arclink_onboarding_after_entitlement` returning False is a **silent no-op** (webhook ignores return) → session stalls at checkout_open with no error/retry. | `arclink_onboarding.py:808-810` |
| CANON-04 | `record_arclink_onboarding_first_agent_contact` has **no terminal guard** → resurrects expired/terminal session, re-occupying the (channel,identity) slot. | `arclink_onboarding.py:880-902` |
| CANON-04 | Free-text hint fields **escape the secret filter** (Anthropic `sk-ant-`/OpenAI/Chutes `cpk_`/AWS keys persist) — refutes "store cannot hold provider keys". | `arclink_onboarding.py:116-126` |
| CANON-05 | Operator Telegram interception **bypasses per-identity rate limit**; operators can issue mutating actions under only the coarse webhook limit. | `arclink_telegram.py:1471` vs `arclink_public_bots.py:7144` |
| CANON-05 | Telegram authn is a **single shared secret** (no per-update signature like Discord Ed25519); leaked secret allows forged updates. | `arclink_hosted_api.py:2889,2900` |
| CANON-05 | A **Discord interaction failing AFTER reservation poisons its own retry** and is permanently dropped (PK dedupe + 200 deferred ack, no followup). Proven. | `arclink_discord.py:271-283`; `arclink_hosted_api.py:3047-3049` |
| CANON-06 | settings-table **unbounded growth**: every Discord message id persisted forever as `curator_discord_onboarding_seen_message:<id>` with no sweeper/TTL. | `arclink_curator_discord_onboarding.py:194-204` |
| CANON-06 | Dead/misleading **Dismiss** writes `arclink_upgrade_last_dismissed_sha` (nothing reads it) yet tells operator the notice is dismissed; real key is `_last_notified_sha`. | `arclink_curator_onboarding.py:975-977` |
| CANON-07 | Refuel-checkout credit grant lacks `(source_kind,source_id)` idempotency guard / UNIQUE constraint (mitigated to MEDIUM by single-transaction design). | `arclink_entitlements.py:598-615` |
| CANON-07 | Subscription/invoice branch **trusts metadata `arclink_user_id` with NO account-ownership assertion**; gated only by HMAC → secret leak/misconfig writes entitlement to arbitrary user. | `arclink_entitlements.py:724-740` |
| CANON-07 | `verify_stripe_webhook` keeps only the **LAST `v1=` signature** → fails during webhook-secret rotation (multi-v1) → 400/retry availability dip. | `arclink_adapters.py:159-163,171` |
| CANON-07 | Subscription-mirror crash on **status='none'** (not a valid subscription status) → webhook rollback → permanent Stripe retry. | `arclink_entitlements.py:62,413` → `arclink_control.py:4710` |
| CANON-08 | Non-Docker pin-upgrade path has **no component allowlist** (kind-only validation); allowlist enforced only by the Docker broker. | `arclink_enrollment_provisioner.py:429-448` |
| CANON-08 | `verify_fleet_audit_chain` **accepts UNKEYED sha256 legacy entries** → a DB-write attacker can re-forge an entire inventory chain undetected (refutes "cryptographically sound / P0 on tamper"). | `arclink_fleet_enrollment.py:469-472,884-902` |
| CANON-09 | Dead/divergent DNS API surface (`provision/reconcile/teardown_arclink_dns`) implements a protocol production never uses; test-green false confidence. *[Federation: MEDIUM as a doc-trust hazard, operationally LOW (pure dead code, zero production callers).]* | `arclink_ingress.py:114,192,207` |
| CANON-09 | Bulk status clobber: `_mark_dns_status` UPDATEs ALL rows for a deployment to one status; teardown after partial apply marks never-provisioned rows 'torn_down'. | `arclink_ingress.py:145` |
| CANON-09 | Torn-down DNS rows never deleted → global UNIQUE index stays loaded → any `(hostname,record_type)` collision (prefix reuse) raises **unhandled IntegrityError** crashing persist. *[Federation: was MEDIUM; downgraded to LOW — reachability gated by CANON-08's never-released UNIQUE prefix reservation, so this is a DB-bypass/corruption scenario not a normal redeploy (`arclink_control.py:1947-1948,3614-3615`).]* | `arclink_ingress.py:78,146`; `arclink_control.py:2077-2078` |
| CANON-10 | Hetzner memory/disk **un-normalized vs Linode** (raw MB vs MB→GiB) → can mis-size `compute_asu`; untested. | `arclink_inventory_hetzner.py:115-117` |
| CANON-10 | SSH probe **`StrictHostKeyChecking=accept-new` (TOFU)** → MITM at first probe unless known-hosts pre-seeded. | `arclink_inventory.py:440` |
| CANON-10 | **Orphaned billable cloud VM**: post-provision exception (e.g. `reject_secret_material` on tags) only fails idempotency + re-raises, never `remove_server`. | `arclink_inventory.py:770,833-842` |
| CANON-11 | Live SSH/local executor is **root-equivalent** on the worker (GAP-019); containment rests on path/allowlist + shlex.quote. | `arclink_executor.py:2384` |
| CANON-11 | `ALLOW_LIFECYCLE_PATH_OVERRIDES` relaxes the `project==arclink-{id}` invariant for teardown. | `arclink_executor.py:1879` |
| CANON-11 | Compose/dns/lifecycle live mutations have **NO ArcLink-side idempotency at all** (only chutes/stripe attempt it, and that is dead). | `arclink_executor.py:890-947` |
| CANON-11 | Live Cloudflare DNS upsert is a **find-then-create TOCTOU** (per-record GET then POST-if-absent, no lock/idempotency key) → duplicate records. | `arclink_executor.py:2538-2569` |
| CANON-11 | `SshDockerComposeRunner.write/read_text_file` **fail-open on containment** (empty `allowed_root` skips the check) → arbitrary remote-host file read/write primitive. | `arclink_executor.py:702-708,663-669` |
| CANON-12 | Brokers bind **0.0.0.0 in production** while docstrings imply loopback; security rests on compose `internal:true` isolation. (Verifier: gateway-exec-broker-net already carries operator Hermes containers → live, not hypothetical.) | `compose.yaml:390-391,1008` |
| CANON-12 | agent-process-helper `_require_env` passes through arbitrary uppercase env keys not on its block/unapproved lists. | `arclink_agent_process_helper.py:337` |
| CANON-12 | agent-process-helper **leaks a log FD per started process** → FD exhaustion over reconciliation. | `arclink_agent_process_helper.py:843,846-852` |
| CANON-13 | `_default_verifier` **fail-open on empty health** → migration marked succeeded without target ever registering service health. | `arclink_pod_migration.py:563-572` |
| CANON-13 | `garbage_collect_pod_migrations` **rmtree's stored capture_dir with only `.exists()`** — no `.migrations` guard, no root guard, no re-validate (rollback path has all three). | `arclink_pod_migration.py:1254-1258` |
| CANON-13 | Symlinks in source state silently unlinked from capture → migrated pods **lose symlinks** (quiet data-fidelity loss). | `arclink_pod_migration.py:441-448` |
| CANON-14 | `recover_stale_actions` **always re-queues with no failed-path/retry cap** → an action whose executor hangs is recovered forever; unbounded `arclink_action_attempts` growth. | `arclink_action_worker.py:2247,2262` |
| CANON-14 | Dismissed pin upgrades **remain queueable** (`active_only=True` filters only `applied_at IS NULL`, ignores `silenced`). | `arclink_operator_raven.py:1281-1290` |
| CANON-15 | Queue-root agreement is **deploy-enforced, not code-enforced** (broker containment-checks, runner only `is_absolute()`; different env fallbacks) → config drift silently times out every request. | `arclink_operator_upgrade_host_runner.py:87-92` |
| CANON-15 | **Nonce replay**: TOCTOU window between `_nonce_seen` and `_record_nonce` + non-persistent store wiped on restart → captured request replays once after broker restart. | `arclink_operator_upgrade_broker.py:665-683` |
| CANON-15 | **Stale/ghost re-execution after a broker timeout**: runner never checks `created_at`/`timeout_seconds` staleness → a request the broker abandoned still executes later (compounds with nonce replay → double-upgrade). | `arclink_operator_upgrade_host_runner.py:279-330` |
| CANON-16 | **Budget fail-open** `budget_policy=observe_only_unlimited` disables the reservation gate (remaining_cents=10¹²); if settable on a non-operator deployment, inference is uncapped. | `arclink_llm_router.py:1149`; `arclink_chutes.py:767-772` |
| CANON-16 | **Model allowlist escape**: allowlist checked only on the literal request string; resolved upstream/auto-promoted/fallback model forwarded unchecked (auto-promote default-on, upstream-catalog-influenced). | `arclink_llm_router.py:1084` vs `:1452,1465` |
| CANON-16 | Reservation is **advisory not atomic** (read then INSERT, no lock) → concurrent requests both pass (TOCTOU). | `arclink_llm_router.py:834,1129,1149` |
| CANON-16 | **Unbounded in-memory body buffering DoS**: `await request.body()` buffers entire body before the 1 MiB cap check (chunked/Content-Length-absent). | `arclink_llm_router.py:489-494` |
| CANON-17 | `record_academy_resource_proposal` is a **SELECT-then-INSERT TOCTOU with NO IntegrityError handler** → concurrent agent turns on the same URL crash the loser. | `arclink_academy_programs.py:755-760,791-824` |
| CANON-17 | `academy_apply` live private filesystem writes (SOUL/vault/state) gated by env+adapter; broader blast radius than "SOUL+receipt only". *[Federation: CANON-14's variant of this risk down-ranked MEDIUM→LOW — it IS executor-adapter gated + 3 more gates (`arclink_academy_programs.py:2864,2938-2940`), the record's "one env var" mechanism is wrong. The blast-radius MEDIUM here stands.]* | `arclink_action_worker.py:2089-2206` |
| CANON-18 | Event drain depends entirely on the 1-min systemd timer if the webhook kick fails (`_spawn_batcher_now` swallows all exceptions). | `arclink_notion_webhook.py:56-59` |
| CANON-18 | `run_notion_ssot_no_secret_proof` in `authorized_live` does **live Notion reads with the real token** even when `allow_live_mutation=False`. | `arclink_notion_ssot.py:1101,1120` |
| CANON-18 | **Loopback "enforcement" is not a defense** under the intended Tailscale Funnel deployment (funnel proxies to 127.0.0.1 → `backend_client_allowed` true for all). HMAC is the real gate. | `bin/tailscale-notion-webhook-funnel.sh:175`; `arclink_control.py:7628-7632` |
| CANON-19 | Auth-proxy `_token_secret` **falls back to `sha256(realm\0user\0password)`** when session_secret blank → forgeable tokens for legacy/hand-written access files. | `arclink_dashboard_auth_proxy.py:90-98` |
| CANON-19 | `request_arclink_backup_deploy_key` runs ssh-keygen and **persists a private ed25519 key** under key_staging_dir on a user-session-gated API call; no rotation/cleanup. | `arclink_dashboard.py:1090-1112` |
| CANON-19 | `build_scale_operations_snapshot` reads `os.environ` directly despite accepting conn → **process env leaks into an admin read model**. | `arclink_dashboard.py:705,748` |
| CANON-19 | Two sibling modules mutate the **same `config.yaml` with incompatible strategies and no shared lock** (full YAML re-dump vs byte-preserving line surgery). | `arclink_headless_hermes_setup.py:565` vs `arclink_skill_enablement.py:118` |
| CANON-20 | Fleet hub is a **single bare repo with no replication/backup**; `ensure_hub_repo` returns True for remote refs without verifying reachability. | `arclink_fleet_share.py:188-208` |
| CANON-20 | `_assert_safe_git_arg` validates only leading `-`/control chars, **NOT URL scheme/host** → env-controlled hub URL could redirect sync to a hostile repo. | `arclink_fleet_share.py:123-136,738` |
| CANON-20 | `_apply_capacity_or_inventory` calls `compute_asu` **un-guarded** → malformed/degraded probe (vcpu_cores:0 from `getconf||nproc||0`) raises and aborts the probe pass. | `arclink_fleet_inventory_worker.py:367,427` |
| CANON-20 | `.corrupt` quarantine **silently orphans un-pushed local Fleet-folder edits** (re-clone never re-merges/GCs the quarantined dir). | `arclink_fleet_share.py:251-263,143-152` |
| CANON-21 | Write-only SQLite mirror: 5 `org_profile_*` tables no reader consumes; full DELETE+INSERT per apply, drifts from `applied.json`. | `arclink_org_profile.py:1961` |
| CANON-21 | **No concurrency control on apply** (DELETE→INSERT→commit + multi-file fan-out, no lock); concurrent apply / mid-write read observes inconsistent revision vs slices. | `arclink_org_profile.py:2093` |
| CANON-21 | Allowlist/best-effort secret scanner: high-entropy secret in a benign-named field passes → persisted to `applied.json` + SQLite. | `arclink_org_profile.py:233` |
| CANON-21 | Dead `clear_materialized_agent_context` → an agent that stops matching keeps a **stale org-profile SOUL overlay** (apply only deletes the JSON slice). *[Federation: LOW→MEDIUM, mechanism NARROWED — stale overlay occurs only on full profile teardown or build failure, not ordinary unmatch (baseline overlay overwrites: `arclink_org_profile.py:1577-1585,1705-1707`; empty-skip `arclink_control.py:18600`).]* | `arclink_org_profile.py:1807,2122-2124` |
| CANON-21 | Post-commit DB/file divergence: SQLite committed, then file writes; a post-commit write failure leaves committed revision while `applied.json` (authoritative read) is stale/missing. | `arclink_org_profile.py:2053` vs `:2107-2145` |
| CANON-22 | GitHub visibility check maps **HTTP 404 → 'non-public-or-missing' and PROCEEDS** with backup (both agent-home AND control-plane lanes) → wrong/unauthorized repo not blocked. | `bin/backup-agent-home.sh:88-90`; `common.sh:1390-1397` |
| CANON-22 | No backoff on failed-report retry: re-queues every 'failed' period each 300s tick → failure-row churn for a permanently-failing Captain. | `arclink_wrapped.py:1091-1094` |
| CANON-22 | Wrapped eligibility gate **ignores `session_counter`** (Hermes turns) → a Captain whose only activity is Hermes turns never gets a 'missing' report. | `arclink_wrapped.py:365-401` |
| CANON-23 | **No retry backoff**: `mark_notification_error` leaves `next_attempt_at` untouched → persistently-failing non-leased row re-attempts every 5s, hammering external APIs. | `arclink_control.py:9403-9408` |
| CANON-23 | Evidence ledger DB layer (`store_evidence_run`/`arclink_evidence_runs`) is **built but unwired**; `run_live_proof` only writes local JSON → operator-visible evidence state is not real. | `arclink_live_runner.py:743-748`; `arclink_evidence.py:278-376` |
| CANON-23 | **Two divergent redaction engines**: evidence `_SECRET_PATTERNS` covers far fewer families than shared `PLAINTEXT_SECRET_RE` → a secret family in a journey detail can survive into `evidence/<run_id>.json` (reproduced via the `error` field). | `arclink_evidence.py:26-31` vs `arclink_secrets_regex.py:25-44` |
| CANON-23 | `run_live_proof` Phase 4 **mutates global `os.environ`** (update/restore) because evaluate_journey reads os.environ → not thread-safe. | `arclink_live_runner.py:705-711` |
| CANON-24 | Doc drift: `AGENTS.md` describes `run_root_upgrade` for `./deploy.sh upgrade`, but live command runs the Dockerized `run_control_install_flow` (Docker rebuild). | `bin/deploy.sh:13012-13016` vs `AGENTS.md:182-195` |
| CANON-24 | Placeholder/personal-fork upstream URLs in entry scripts (`github.com/example/arclink.git`, personal fork) → bootstrap relying on defaults clones wrong repo. | `init.sh:13-14`; `bin/bootstrap-userland.sh:17` |
| CANON-24 | `docker-entrypoint` **fails open**: unwritable config dir → only warns and continues → pod can start with change-me/empty secrets. | `bin/docker-entrypoint.sh:655-660` |
| CANON-24 | Mis-keyed operator breadcrumb makes config discovery dead code (S11) → falls through to hardcoded `/home/arclink/...` config. | `bin/deploy.sh:2856` vs `bin/component-upgrade.sh:515` |
| CANON-25 | Three services mount **`/var/run/docker.sock` writable** (deployment-exec/agent-supervisor/gateway-exec brokers) → each host-root-equivalent on compromise (GAP-019). | `compose.yaml:666,832,1017` |
| CANON-25 | Four services run **user 0:0** (migration-capture/operator-upgrade-broker+DAC_OVERRIDE/agent-user-helper/agent-process-helper) + writable binds → high authority even without socket. | `compose.yaml:679,847,885,918` |
| CANON-25 | **Redaction regex leading `\b` anchor fails** to match `ARCLINK_*_TOKEN`/`_SECRET` names → those tokens **leak unredacted** into job status `output_tail`. | `bin/docker-job-loop.sh:44,72,88` |
| CANON-25 | agent-process-helper (root, binds 0.0.0.0:8916) is on **non-internal `agent-process-helper-egress-net`** → contradicts the blanket `internal:true` containment claim. | `compose.yaml:918,942-944,1177` |
| CANON-25 | operator-upgrade-broker mounts the **live host repo writable as root** (no `:ro`), unlike its read-only siblings. | `compose.yaml:869` |
| CANON-25 | `docker-job-loop.sh` never propagates child exit codes → a perpetually failing job never trips `restart: unless-stopped`. | `bin/docker-job-loop.sh:141-144` |
| CANON-26 | Unit-directive injection: positional `AGENT_ID`/`ACTIVATION_TRIGGER_PATH`/`HERMES_HOME` interpolate RAW into Description/WorkingDirectory/Path/ExecStart; the lone guard covers only Environment= lines and is inert in heredoc `$(...)`. Mitigated only by upstream slugging. | `bin/install-agent-user-services.sh:47-51,298,345-348,380` |
| CANON-27 | Env-file `ARCLINK_HERMES_AGENT_REF` could **override pins.json with an OLDER Hermes commit** (verifier: actually pins.json wins via `__pins_get_or_default`; downgrade contested). *[Federation: RESOLVED — MEDIUM→INFO; precedence is inverted, pins.json wins in the happy path, env fallback only on degraded jq/pins-missing path (`bin/common.sh:545-552`).]* | `config/arclink.env.example:120` vs `config/pins.json:11` |
| CANON-27 | `pins_set/pins_set_raw` are **FAIL-OPEN**: jq exit status never checked before the unconditional `mv` → a jq failure clobbers `config/pins.json` (the single source of truth) with empty/truncated content. | `bin/pins.sh:81-85,95-99` |
| CANON-28 | **No Python style/lint gate in CI**: ruff/pyflakes pinned but never invoked; only py_compile on 3 modules runs. | `requirements-dev.txt:12-13`; `bin/ci-preflight.sh:197-203` |
| CANON-28 | python-regressions quality fully delegated to CANON-29: a `tests/test_*.py` lacking a `__main__` runner runs to no-op exit 0, silently passing. | `.github/workflows/install-smoke.yml:40` |
| CANON-28 | install-smoke **mutates the REAL host** (creates users, installs stack), depends on passwordless sudo, ≤90m; teardown failures swallowed by `--apply-remove || true`. | `bin/ci-install-smoke.sh:39-42,2503` |
| CANON-29 | `test_arclink_executor.py` / `test_deploy_regressions.py` are **not hermetic** (write to hardcoded `/arcdata`, shell out to systemd-analyze/git) → FAIL on read-only/minimal host. | `tests/test_arclink_executor.py:41`; `tests/test_deploy_regressions.py:2941` |
| CANON-30 | Code `_run_git` 400 detail echoes **raw git stderr (absolute repo path)** to the client, unredacted. | `plugins/.../code/.../plugin_api.py:1127-1128` |
| CANON-31 | Misnamed `tailscale-nextcloud-serve.sh` **tears down** (no longer serves); still invoked by `deploy.sh` gated on `ENABLE_TAILSCALE_SERVE==1` → publish-named flag drives teardown. | `bin/tailscale-nextcloud-serve.sh:235-240`; `bin/deploy.sh:5571,5713` |
| CANON-31 | `QMD_EMBED_PROVIDER=endpoint` (and aliases) **silently falls back to local embeddings** with only a stderr warning. | `bin/qmd-refresh.sh:71-79` |
| CANON-31 | `vault-watch` **fail-open on unreadable manifest** → corrupt manifest triggers unnecessary PDF reconciliation churn on every directory delete. | `bin/vault-watch.sh:78-81` |
| CANON-31 | `qmd-daemon.sh` waits only on `qmd_pid`, never the backgrounded Python TCP forwarder → forwarder death leaves unit 'active' with the container port silently unreachable. | `bin/qmd-daemon.sh:75,83` |
| CANON-32 | Canonical-labeled module/table map is **stale and unguarded** (architecture.md 84/44/9 vs code 87/45/10; DOC_STATUS brands it Canonical; no count test). | `docs/arclink/architecture.md:18,280`; `docs/DOC_STATUS.md:26` |
| CANON-32 | GTB instructs maintainers to "keep the OpenAPI parity test" but a **byte-diff parity test does not exist** (a *canonical-JSON* parity test does). *[Federation: was MEDIUM; downgraded to LOW — a real parity test exists and PASSES via canonical sort_keys equality (`tests/test_arclink_hosted_api.py:5496-5507`, in runner `:6375`); the spec cannot silently drift in content. Only the literal "byte-identical" wording in 3 docs is wrong.]* | `ARCLINK_GROUND_TRUTH_BRIEF.md:295` vs `arclink_hosted_api.py:3689` |

### LOW (41) — by piece (compact)

- **CANON-01:** `config_env_value` re-reads/re-parses the config file every call (mild TOCTOU, no cache) `:340`; silent missing-config-file no-op `:248-249`; `journal_mode` PRAGMA failure swallowed `:576-577`; parser ignores `export ` prefix → silent no-op `:324-325`.
- **CANON-02:** legacy `sha256_legacy` session/CSRF hashes still verified+auto-rehashed (stolen plain-SHA usable until re-auth) `:295`; fresh `connect_db` per request under high QPS `:4319`; `enforce_secure_transport` scheme-blind (`file://`/`ftp://` pass) `arclink_http.py:59,117`; rate-limit TOCTOU `arclink_api_auth.py:408`; `/auth/login` admin-enable footgun on empty REMOTE_ADDR `:4031-4038`.
- **CANON-03:** SW pre-caches auth-gated `/dashboard`,`/admin` shells `web/public/sw.js:6`; `NEXT_PUBLIC_ARCLINK_API_URL` baked into client bundle `web/src/lib/api.ts:1`; admin page mishandles 403 CIDR-denial (only 401 handled) `web/src/app/admin/page.tsx:162-164`.
- **CANON-04:** `expire_stale_*` UPDATEs on the read path `:337`; `_active_session_row` IN(?) placeholder/value-order looks like a bug (harmless) `:237-249`; dry-run-then-live with same migration_id hard-errors.
- **CANON-05:** silent lossy truncation of replies >4000 chars `:224`; per-agent command scope swallows exceptions to stale static fallback `arclink_public_bot_commands.py:172`; process-local unbounded command-scope cache `:50`; webhook IP rate-limit bucket shared across all Telegram traffic; Telegram entities not re-clamped on truncation `:1520-1524`.
- **CANON-06:** operator DM allowed without allowlist on Discord `:182-188`; failure-write fragility can hot-loop on poison update `:1182-1210`; `notify_operator_worker_failure` fire-and-forget swallows send exceptions `:217-220`; Discord claim-before-process permanently drops a message on handler exception `:190-204`; `_send_replies` swallows all user-reply send errors after state advanced `:385-441`.
- **CANON-07:** 'received'-status redelivery returns replayed=True with empty user_id → 200 stops retries `:544-552`; error→404 drift (KeyError) on missing onboarding session `:331-332`.
- **CANON-08:** UnicodeDecodeError escapes returncode-2 contract, strands 'running' row until reaper `:335`; plaintext http carries broker bearer token (GAP-019) `:322`; broker URL no scheme/host allowlist `:289-290`; `_docker_mode` truthy-set divergence `{1,true,yes}` vs `{...,on}` `:764`; agent_access chown swallow `arclink_agent_access.py:69-75`.
- **CANON-09:** provider_record_id depends on out-of-piece writer `:174`; retry masks deterministic failures `:228`; executor teardown over-reports never-deleted hostnames as removed `arclink_executor.py:2588-2589`.
- **CANON-10:** fragile `df -BG` parse (already HIGH); compute_asu returns 0 on RAM/disk=0 without error `arclink_asu.py:59-61`; current_load returns stale `asu_consumed` for unlinked rows `:72-74`; hostname-collision capacity clobber `arclink_fleet.py:189-234`; float→int load truncation.
- **CANON-11:** brokered runner always sends remove_volumes/include_all `:802`; SSH TOFU default `:529`; `_cleanup_materialized_secret_root` symlinked-ROOT case incomplete `:2131-2150`; lifecycle project-override blast radius narrower than stated.
- **CANON-12:** same-Captain pod_comms sends bypass the share-grant gate `:131`; broker returns raw subprocess failure tail to caller `:307`; `record_rejection_incident` silently no-ops on OSError/unsafe path `:138`; chown -R TOCTOU `arclink_agent_user_helper.py:129-148`; pod_comms grant user-pair-scoped (authorizes all deployment pairs) `:77-78`.
- **CANON-13:** success-path metadata_json write bypasses secret rejection `:903`; rollback best-effort swallows exceptions `:610-654`; dry-run-then-live same migration_id hard-errors `:1005`; docker `result.status` captured but never compared `:1155-1156`.
- **CANON-14:** button-nonce consume not transactionally guarded vs double-tap `:1388-1394`; ctl channel reconfigure persists bot tokens to env file `:2376-2627`; `_redact_text` only redacts `key=value` lines (misses `:`/bare) `:2415-2423`.
- **CANON-15:** hermes-docs-only install_items rejected by broker `:643-646`; malformed POLL_SECONDS aborts request `:341`; unguarded pins.json read `:99-100`; constants triplicated across trust boundary `:23-42`; unbounded growth of results/ and processed/ queue dirs `:377,391-394`.
- **CANON-16:** `verify_llm_router_key` UPDATE+commit on every auth `arclink_control.py:6810`; `mark_missing_unavailable` can reroute live traffic on a transient bad fetch `:6603`.
- **CANON-17:** `subscribe_trainee_to_specialist` bare `except: pass` `:451-454`; crawl 'failed'/'blocked' never feed observed_sources `:690`; unbounded crawl when `CRAWL_LIMIT=0` `:638-644`; robots 4xx/5xx fail-OPEN `:288-293`; live-trainer failure silently downgraded with no Captain signal `:2294-2299`.
- **CANON-18:** webhook `/health` GET answered before loopback auth check `:304-307`; dead env `ARCLINK_MEMORY_SYNTH_MAX_CONTENT_HASH_BYTES` (REFUTED — it IS read; setting 0 disables the cap) `memory_synthesizer.py:329`; qmd protocol comment stale vs pin 2.5.3 `:71-75`; MCP source_ip spoof/TOCTOU (env-gated) `:1847-1856`.
- **CANON-19:** SW/SSO/login-throttle process-local `:66`; admin list exposes `stripe_customer_id` `:2179`; `_deployment_urls` builds https from unvalidated operator env `:797-819`; silent SSO secret generation by default `bin/arclink-docker.sh:1696-1698`.
- **CANON-20:** no advisory lock on fleet-share sync `:309-363`; `.corrupt[-N]` dirs never GC'd `:143-152`; `remove_fleet_share_member` silent no-op on empty id `:531-533`; non-atomic probe transaction (queue_notification internal commit) `arclink_control.py:8071`; `register_fleet_host` unhandled IntegrityError TOCTOU `arclink_fleet.py:189`.
- **CANON-21:** `cpk_` placeholder bypasses secret scan `:216`; silent stale-slice deletion `:2123`; fan-out scoped to role='user'∧active only `:2069`; dict-key secret blindness `:221-230`.
- **CANON-22:** tar member validation only for `*.tar`/`.tgz`, not git-archive/dir-snapshot `:104-114`; `reconcile_backup_git_remote_branch` duplicated verbatim across two scripts `:101-142`; TOFU host-key via ssh-keyscan unchecked `common.sh:1450-1456`.
- **CANON-23:** detached public-agent-turn lease ~2h locks the turn on transient error `:943-946`; dashboard/runner disagree on `required_env` (`CLOUDFLARE_API_TOKEN_REF`) `dashboard.py:548`.
- **CANON-24:** `${CONTROL_DEPLOY_ARGS[@]:-}` spurious empty element under set -u `:11599`; `printf "$TARGET_USER"` format-string `:199`; DB-password repair persists literal `change-me` once init marker exists `docker-entrypoint.sh:323-341`; TOFU host-key trust both backup lanes `common.sh:1450-1456`.
- **CANON-25:** `arclink-docker.sh compose()` docker-only (podman fails closed) `:123`; placeholder-secret detection only warns `docker-health.sh:474-476`; standalone nextcloud redis no healthcheck `nextcloud-compose.yml:11`; asymmetric queue-path validation `broker:284` vs `host_runner:90`; health() swallows tailnet/refresh failures `:747-749`.
- **CANON-26:** `start_system_service_if_idle` TOCTOU double-start `:110-119`; restart batch lacks per-unit `|| true` under set -e `:109-120`; enable block unguarded under set -e `:49-59`.
- **CANON-27:** inventory stale 'writeable Docker socket' prose `:205`; egress-network prose false `:316`; ALMANAC alias claim vapor `env.example:4`; `pins_set` no lock `:79-85`; `pins_validate` omits release-asset coverage `:131-137`; mktemp non-atomic across filesystems `:80,94`; documented `pins_get ... extras.0` broken (jq array-index) `:39`.
- **CANON-28:** dead `master` branch trigger `:5-8`; preflight skips (not fails) when systemd-analyze/inotifywait absent `:208-211`; preflight pdf-ingest backend assert env-coupled (docling precedence) `:250,262`; restore-smoke tar symlink screening absent `:104-114`.
- **CANON-29:** `pytest.ini` dead/misleading (CI runs files directly) `pytest.ini:1-8`; live E2E correctly fail-safe (INFO).
- **CANON-30:** terminal `_clean_ssh_target`/`_SSH_TARGET_RE` dead code (ssh mode = local shell) `terminal/.../plugin_api.py:62,459-462`; drive sensitive-path denylist + strict=False resolve (TOCTOU-adjacent) `drive/.../plugin_api.py:589-609`; crew links silently dropped on empty/non-https URL `:41`; bootstrap-token momentary argv exposure `skills/.../curate-vaults.sh:67-72`; drive `_resolve_local` skips sensitive guard for empty relative_path (root) `:1189-1190`.
- **CANON-31:** bootstrap-token-on-argv exposure window `curate-vaults.sh:67-72`; qmd embed timeout swallowed as success `:105-108`; `pdf-ingest.py` hard-crashes on unset env `:21-24`; non-atomic CONFIG_FILE rewrite `qmd-refresh.sh:57`.
- **CANON-32:** stale GAP-016 string in GAPS.md `:746`; ~~untracked DISSECT.md/analyze_vuln.md invisible to hygiene tests~~ *[Federation: REFUTED→INFO — untracked-but-unignored files ARE scanned (`DISSECT.md` appears in `git ls-files --cached --others --exclude-standard`); only `.gitignore`-matched `*_vuln.md` is excluded by design (`tests/test_public_repo_hygiene.py:18-23`; `.gitignore:22-24`)]*; third undocumented module `arclink_upgrade_policy` absent from the canonical map; `test_arclink_schema.py` subset assertion cannot catch a count drift `:41-78`.

### INFO (23, compact)

GAP-019 fail-closed gate is by-design (CANON-01 `boundary.py:82`). Telegram/Discord webhook
handlers return 200 on transport-send exception (CANON-02 `:2966`). Discord global vs
guild-scoped command registration (CANON-05 `:167`). Single-instance token interlock is the
only Telegram-409 guard (CANON-06 `curator-gateway.sh:27-31`). Live Stripe + Chutes
provider-balance are proof-gated PG-STRIPE/PG-PROVIDER (CANON-07/16). Readiness ready-roll-up
excludes secret presence by design + tautological `check_ingress_strategy` always ok=True
(CANON-08 `host_readiness.py:154-161,183`). `persist_arclink_dns_records` empty-records commit
(CANON-09). set-strategy CLI is a DB no-op (CANON-10 `:1287-1291`). All fake idempotency state
is per-instance (CANON-11 `:860`). public_agent_bridge reports delivered on
absence-of-exception (CANON-12 `:799`). Helper request timeout clamped (CANON-13 `:494`).
Host-upgrade dedupe ignores request_source (CANON-14 `control.py:8200-8216`).
schema_version/returncode laxity inside trusted boundary (CANON-15 `host_runner:282`). Fuel
notices swallow exceptions by design (CANON-16 `:1068`). Fixture-fallback graduate
(CANON-17 `:2681`). MCP returns JSON-RPC errors on HTTP 200 with error-status header
(CANON-18 `:1718-1721`). SSO cookie/dead-code framing (CANON-19, refuted). `paused`/`pending`
statuses are dead (CANON-20 `control.py:1098,1111`). Dual `default_profile_path` (CANON-21
`builder.py:45`). force-with-lease single-writer assumption (CANON-22 `:136-141`). External
journey is catalog-only + `run_diagnostics(live=)` dead param (CANON-23 `:200-213`). Self-reexec
mktemp stable copy (CANON-24 `:11-20`). Both nextcloud topologies default host port 18080 →
collision (CANON-25). `HOME=/root` hardcoded in system units (CANON-26 `:58`).
`.env.live.example` untracked + decorative version fields (CANON-27). `master` trigger /
tailscale-serve not in CI gate (CANON-28). `notion-page-pdf-export` + `arclink-upgrade-orchestrator`
skills not in default install (CANON-30/31). GTB date 2026-05-30 < code date (CANON-32).

### Federation-added (Codex-found, code-confirmed)

> Every `codexFindingsConfirmed` item from the reconciliation manifests — findings the *Codex
> (GPT-5.5) independent overlay* raised that the Claude adjudicator then **re-verified true in
> code**. Zero were rejected at the conclusion level. Grouped by severity, with piece id +
> cite. These are additive to the Claude-half register above.

**HIGH (5)**

| Piece | Risk | Cite |
|---|---|---|
| CANON-05 | **`/credentials` reveals the dashboard password into a public (non-DM/non-ephemeral) channel** — raw secret + Copy button, no chat-type/`flags:64` guard; the first reveal in a group channel IS the leak ("revealed once then removed" only affects future responses). | `arclink_public_bots.py:3705-3750,7608-7622`; `arclink_discord.py:469-471`; `arclink_hosted_api.py:2980-2984` |
| CANON-11 | **Live Chutes/Stripe admin actions are NOT production-wired** — the non-fake path raises before any provider mutation because no production ctor injects the clients (only `self.x=` at `:857`; factory at `:142` omits them); the sovereign getattr-guard is always None on non-fake. (Re-scopes the Claude HIGH from current double-execute to latent.) | `arclink_executor.py:1204-1205,1327-1328,857,142`; `arclink_sovereign_worker.py:1392,1514` |
| CANON-13 | **Default verifier trusts STALE pre-migration health** (not just empty) — `arclink_service_health` is keyed `(deployment_id,service_name)` only, the verifier ignores `checked_at`/target host, and the prod caller injects no verifier → source-pod healthy rows survive into target verification. | `arclink_control.py:1230`; `arclink_pod_migration.py:563-572`; `arclink_action_worker.py:1169-1178` |
| CANON-26 | **SSH-key newline injection** — both the bash and Python validators admit an internal newline after a no-comment first key; the whole multiline value is appended, producing a second **UNRESTRICTED `authorized_keys` line** that bypasses `from=`/no-forwarding options (both regexes executed and confirmed). | `bin/install-agent-ssh-key.sh:54-56,73-74,115`; `python/arclink_onboarding_flow.py:76-77,955-956` |
| CANON-30 | **Token-injection seam misses `ssot.approve`/`ssot.deny` (not just `pod_comms.*`)** — `_TOKEN_TOOL_NAMES` is not a superset of token-requiring agent-advertised tools; the schema-following agent omits the token and the server `validate_token("")` fails closed = a live break. | `arclink-managed-context/__init__.py:276-302,1843`; `arclink_mcp_server.py:464-479,2614-2644,1094`; tools/list `:1787-1796` |

**MEDIUM (≈22)**

| Piece | Risk | Cite |
|---|---|---|
| CANON-01 | Org-profile apply creates **5 `org_profile_*` tables on the same `connect_db` connection** (control DB reaches 85 after apply) — `ensure_schema` is primary but NOT the sole control-DB schema authority. | `arclink_ctl.py:2090`; `arclink_org_profile.py:1910-1957` |
| CANON-01 | Raw `notification_outbox`/`arclink_events` INSERTs bypass `queue_notification`/`append_arclink_event` and use plain JSON encoders, widening the secret-leak surface (helper contracts are not exclusive). | `arclink_llm_router.py:1024-1041,1043-1051`; `arclink_wrapped.py:921-932`; `arclink_chutes.py:917-925` |
| CANON-05 | **Reusable direct-checkout URL token** re-arms `browser_claim_proof_hash` on every redirect; the claim API turns that proof into a full authenticated session → anyone holding the URL can re-claim an account session. | `arclink_hosted_api.py:799-807,835-843`; `arclink_api_auth.py:4996-5004` |
| CANON-06 | **Configured operator approval code is NOT enforced on direct Discord approve/deny/SSOT paths** — only Operator-Raven commands check it; direct slash/text/`arclink:ssot|upgrade|pin-upgrade` component buttons mutate after channel-id + allowlist only. Telegram-vs-Discord asymmetry. | `arclink_curator_discord_onboarding.py:206-253,539-556,600-619,973-993` (code rail only `:310-323`) |
| CANON-07 | **No payment verification** — `arclink_entitlements` never reads `payment_status`/`amount_total`/`amount_paid`; `checkout.session.completed` maps unconditionally to `paid`; a signed event with `payment_status` unpaid grants before settlement. | `arclink_entitlements.py:399-403,575-616` |
| CANON-08 | **Fleet enrollment consume is not transaction-clean** — `register_inventory_machine`/`register_fleet_host` commit before the single-use token guard, so a lost race or post-register failure leaves a committed orphan inventory machine + degraded fleet-host row (overturns the verifier's "no orphan inventory row"). | `arclink_fleet_enrollment.py:651-698`; `arclink_inventory.py:173-182,262`; `arclink_fleet.py:238-248` |
| CANON-09 | **`dns_repair` can apply DNS to Cloudflare with NO control-DB tracking** — the explicit-DNS and no-rows branches apply via executor then return with no persist/status/`provider_record_id` backfill; teardown reads only `arclink_dns_records` → teardown blind spot. | `arclink_action_worker.py:168-179,209-231,858-880`; `arclink_ingress.py:171-189` |
| CANON-11 | `cloudflare_access_apply` is a **no-op returning `live=True,status=applied`** with no Cloudflare/subprocess call and no production import. | `arclink_executor.py:1183-1194` |
| CANON-11 | Local/broker compose apply **creates arbitrary absolute bind-source directories from intent** (`volume_root_mode=all` skips containment when `allowed_root` is None). | `arclink_executor.py:2162-2165,1981,2182,2189` |
| CANON-12 | Pod-message notification extra metadata (`message_id`/`sender`/`recipient`/`agent_name`/`attachments`) is queued into `extra_json` but **never read at agent consumption** — `consume_agent_notifications` SELECTs no `extra_json`. | `arclink_pod_comms.py:308-321` vs `arclink_control.py:9871-9882` |
| CANON-13 | Existing **planned migration rows bypass target availability re-check** — `plan_pod_migration` returns the existing row before the active&&!drain check; `migrate_pod` applies without re-validating. | `arclink_pod_migration.py:324-344,1136-1147` |
| CANON-13 | Materialize **overlays the target root with `dirs_exist_ok=True` and never clears stale files** → a prior partial/failed target root can contaminate the migrated pod. | `arclink_pod_migration.py:462-466` |
| CANON-13 | **Success not atomic with idempotency completion** — `_mark_success` + `upsert_arclink_service_health` commit mid-success before `complete_arclink_operation_idempotency` commits separately; a crash leaves migration succeeded with idempotency `running`. | `arclink_pod_migration.py:954,1188-1196`; `arclink_control.py:4695,3393` |
| CANON-14 | **`operator_actions` is not an atomic queue** — SELECT-then-INSERT enqueue, non-unique index, drain UPDATEs `status='running'` with no `status='pending'` guard → concurrent request/drain can duplicate or double-run host/pin upgrades. | `arclink_control.py:8273-8308,8581-8591,1860-1862,760-772`; `arclink_enrollment_provisioner.py:2330-2342` |
| CANON-16 | **NF-1 — key allowlist bypassed by the GLOBAL default-model exception**: `_router_model_allowed` returns True whenever `model==config.default_model` regardless of the key's `allowed_models`. | `arclink_llm_router.py:650,1083,94` |
| CANON-16 | **NF-2 — settlement exception leaks a permanent reserved row**: `_record_router_usage` calls `record_chutes_usage_event` (can raise) BEFORE `_release_budget_reservation`, no surrounding try, and NO reservation-aging path → orphaned reserved rows count forever against concurrency. | `arclink_llm_router.py:1401,1432,1631,1906`; `arclink_chutes.py:861-871`; `arclink_control.py:1303` |
| CANON-17 | **NF-1 — `academy_apply` advertises PG-PROVIDER but enforces only PG-HERMES at the write boundary**: a deterministic Trainer review (`live_enrichment_status=pending_pg_provider`) satisfies `trainer_review_ready`; `proof_gate=PG-PROVIDER` is cosmetic at the write boundary. | `arclink_academy_programs.py:2862,2899,2303,2311,2938`; `arclink_academy_trainer.py:1045` |
| CANON-18 | **Armed-window verification-token hijack + non-atomic check/set** — `get_setting` then `upsert_setting` is not atomic, so two concurrent armed POSTs both pass the empty-stored check; under Funnel any external caller can attempt it while the window is open. | `arclink_notion_webhook.py:209-231`; `arclink_control.py:2971-2980`; `bin/tailscale-notion-webhook-funnel.sh:290` |
| CANON-18 | **Unclaimed reindex-consumer race** — `consume_notion_reindex_queue` selects with a plain SELECT and runs `sync_shared_notion_index` before marking delivered, with no claim/lease (unlike the event path); two batchers can both run the live sync. | `arclink_control.py:14828-14839,14874,14964` |
| CANON-19 | **User dashboard hardcodes provider to default Chutes** — `read_arclink_user_dashboard` calls `primary_provider({})` with an empty mapping → `provider=='chutes'` always true; Chutes boundary enrichment runs for Codex/Anthropic/custom deployments too (secret-safe but mislabels semantics). | `arclink_dashboard.py:1737,1743-1763`; `arclink_product.py:14-21,87-88` |
| CANON-19 | **`config.yaml` dual-writer with incompatible strategies and no lock** — `headless_hermes_setup` full YAML re-dump vs `skill_enablement` byte-preserving line surgery; both write the same file (install/refresh vs every 4h) with no flock. | `arclink_headless_hermes_setup.py:84,90,565,599`; `arclink_skill_enablement.py:95,118-148` |
| CANON-20 | **Unchecked Fleet working path** — `sync_local_working_copy` takes `working_path` from `ARCLINK_FLEET_SHARED_ROOT` with no containment/allowlist, then `git add -A` stages the whole tree and pushes to the hub → wrong/hostile pod-env value commits/exfiltrates the wrong local directory. | `arclink_fleet_share.py:283-294,738-755` |
| CANON-21 | **Reference `audience` is ignored in the shared vault render** — filter keys only on `sensitivity != restricted`, so `team_only`/`operator_only` references leak `id`/`title`/`type`/`path` verbatim into the all-agents `0o644` vault doc. | `arclink_org_profile.py:1012-1016,1021`; `config/org-profile.schema.json:750` |
| CANON-23 | **Notification due-filtering happens AFTER SQL LIMIT** → head-of-line blocking: the hosted-API webhook fast path uses `limit=1`, so a single not-due leased lowest-id `public-agent-turn` occupies the only slot and hides all newer due turns. | `arclink_notification_delivery.py:1686-1701`; `arclink_hosted_api.py:2832` |
| CANON-23 | **`run_live_proof` returns `dry_run_ready`/exit 0 even when readiness or diagnostics FAILED** — the status ladder never reads `readiness.ready`/`diagnostics.all_ok`; a CI gate on exit code gets a false green when Docker is down or providers missing. | `arclink_live_runner.py:670,678,692-699,751-754` |
| CANON-25 | **`./deploy.sh control health` has no direct liveness probe for any of the 7 broker/helper services** — `DOCKER_REQUIRED_RUNNING_SERVICES` lists none, explicit HTTP probes cover only core services, in-container `required_jobs` is broker-free → a post-start broker crash is invisible until a job fails. | `bin/arclink-docker.sh:26-49,729-746`; `bin/docker-health.sh:217-229` |
| CANON-22 | **Control-plane backup visibility check trusts overrideable `GITHUB_API_BASE`/`BACKUP_GIT_GITHUB_API_BASE` with no test guard** (agent-home lane has the refusal, control lane does not) → a spoofed API base returning `private:true` defeats the public-repo refusal. | `common.sh:1331-1333`; contrast `backup-agent-home.sh:22` |
| CANON-26 | **access-state filename schema-overload** — `install-deployment-hermes-home.sh` writes `arclink-web-access.json` WITHOUT `dashboard_backend_port`/`dashboard_proxy_port` while the enrolled-user writer includes them → a concrete drift source that triggers the fail-open hard subscript. | `bin/install-deployment-hermes-home.sh:163-175` vs `python/arclink_agent_access.py:524-525`; subscript `install-agent-user-services.sh:287` |
| CANON-31 | **`tailscale-nextcloud-serve.sh` is an active `ENABLE_TAILSCALE_SERVE=1`-drives-teardown contradiction** (re-framed from naming/dead-code) — the publish-named enable flag actively drives teardown. | `deploy.sh:5570-5571,5712-5713`; `tailscale-nextcloud-serve.sh:219-240` |
| CANON-31 | **Silent qmd-daemon TCP forwarder death** — `qmd-daemon.sh` waits only on `qmd_pid`; forwarder death leaves the unit active with the container port silently unreachable (container mode). | `qmd-daemon.sh:75,83,71` |
| CANON-15 | **Provisioner urlopen timeout (7200) is 30s shorter than the broker poll deadline (7230)** — a host result landing in the final 30s grace window is reported as failed to the action worker, inviting retry/double-execution. | `arclink_enrollment_provisioner.py:334,377-379,465`; `arclink_operator_upgrade_broker.py:340-365` |
| CANON-15 | **Stale/ghost re-execution after broker timeout** — the runner never reads `created_at`/`timeout_seconds` for any staleness test, so `deploy.sh upgrade`/per-pin apply can run later after the requester already received a timeout error. | `arclink_operator_upgrade_host_runner.py:279-330,307,381`; `arclink_operator_upgrade_broker.py:362-365` |
| CANON-03 | (admin CIDR allowlist conditional/XFF-dependent — see CANON-03 reconciled; MEDIUM conditional). | `arclink_hosted_api.py:624-648,3979-3988`; `web/next.config.ts:3-14` |

**LOW / INFO (≈20, compact)**

- **CANON-02:** negative `CONTENT_LENGTH` bypasses the WSGI body cap (`read(-1)` consumes whole body) `arclink_hosted_api.py:4289,4299,4308`; non-UTF-8 WSGI body raises `UnicodeDecodeError` outside error mapping → unstructured 500 `:4288-4308`; parse/status URL-redaction leak (INFO) `arclink_http.py:139`.
- **CANON-03:** negative `CONTENT_LENGTH` bypasses the product_surface 64KB cap (net-new LOW) `arclink_product_surface.py:782,789`.
- **CANON-04:** late-cancel regresses a paid/provisioning session to abandoned (cancel short-circuit excludes `provisioning_ready`/`first_contacted`) MEDIUM `arclink_api_auth.py:5039,5046-5048`; public `question_key` stored unscanned/uncapped as `current_step` and reflected (LOW) `arclink_onboarding.py:527`.
- **CANON-05:** swallowed Telegram send leaves committed state with no reply/retry (LOW) `arclink_hosted_api.py:2963-2967,3001-3013`.
- **CANON-07:** successful retry of a prior 'failed' webhook returns `replayed=True`, suppressing the first-success paid ping (LOW) `arclink_entitlements.py:446-461,796`; reconciliation drift detector excludes only 3 deployment statuses → false drift (LOW) `arclink_entitlements.py:77,92,116`.
- **CANON-08:** (audit-chain unkeyed-SHA256 downgrade re-confirmed MEDIUM — see register).
- **CANON-09:** dead `teardown_arclink_dns` passes all 4 hostnames vs 2 provisioned (INFO, dead code) `arclink_ingress.py:201-203`.
- **CANON-11:** rendered env/compose/remote-prepare use non-atomic `write_text()+chmod` (LOW) `arclink_executor.py:1991-1992,2006-2007,2015-2016`; duplicate compose secret targets alias last-writer-wins (LOW) `:1759-1764`.
- **CANON-12:** `mark_pod_message_delivered` has no production caller (LOW) `arclink_pod_comms.py:398-437`.
- **CANON-13:** invalid `ARCLINK_MIGRATION_GC_DAYS` raises after apply+verification, dragging an applied migration into rollback (LOW) `arclink_pod_migration.py:1177-1179`.
- **CANON-14:** `academy_apply` path containment misses symlink ancestors (LOW; STANDING vs Codex MEDIUM) `arclink_action_worker.py:1417-1424,2104,1384-1405`; executor-select runs before the attempt row + outside the failure try (LOW) `:694-705,736`.
- **CANON-15:** detector concurrency SELECT→INSERT no row lock (INFO→LOW) `arclink_pin_upgrade_check.py:405-443`; malformed POLL_SECONDS parsed after the queue write — broker rejects but the mutation still drains (LOW) `arclink_operator_upgrade_broker.py:339,341,651-653`; unbounded `results/`+`processed/` growth (LOW) `arclink_operator_upgrade_host_runner.py:377,391-396`.
- **CANON-16:** rate-limit advisory TOCTOU (LOW) `arclink_llm_router.py:811,831,1124,1159`; external `record_chutes_usage_event` idempotency races on the TEXT-PK `event_id` → unhandled IntegrityError not double-count (LOW) `arclink_chutes.py:882,913,917`.
- **CANON-17:** source-lane validation not strictly fail-closed (LOW, practically unreachable) `arclink_academy_programs.py:3071-3076`; crawl-observation ID collision (INFO, intra-run dedup + per-trainee try/except contain it) `arclink_academy_scheduler.py:430,458,601-612`.
- **CANON-18:** hash-cap operator-defeatable to unbounded when `ARCLINK_MEMORY_SYNTH_MAX_CONTENT_HASH_BYTES=0` (LOW; replaces the false "dead env var") `arclink_memory_synthesizer.py:335-341`.
- **CANON-21:** non-restricted reference paths not containment-checked → operator-authored absolute host path disclosed in the all-agents vault doc (LOW) `arclink_org_profile.py:371,382-385,1021`.
- **CANON-22:** agent-home no-secrets/logs restore proof does not screen symlink targets inside curated dirs (LOW) `arclink-restore-smoke.sh:104-114,221-222`; quiet-hours window math is UTC-only not local/DST-correct (INFO) `arclink_wrapped.py:80,802,808-809`.
- **CANON-23:** unguarded default evidence write crashes the CLI before printing result/JSON (LOW) `arclink_live_runner.py:743-748,804`; health-watch forwards raw `[fail]`/stderr lines to operator notifications without shared redaction (LOW) `arclink_health_watch.py:88-98,220-222`; detached bridge job file not unlinked on the spawn/log-open error path (LOW) `arclink_notification_delivery.py:1185,1213-1214`; pod-message non-atomic notification queue (LOW) `arclink_pod_comms.py:306`.
- **CANON-24:** entrypoint writes secret VALUES unquoted into a shell-sourced env file (`POSTGRES_PASSWORD=$postgres_password`) (LOW) `bin/docker-entrypoint.sh:391-470,549-551`.
- **CANON-25:** job-status writes are non-atomic (no temp+rename) → truncated JSON read as `invalid_json` with no last-good fallback (LOW) `bin/docker-job-loop.sh:90,113`.
- **CANON-26:** `ARCLINK_AGENT_REMOTE_SSH_FROM` interpolated into `from="..."` with no quote/control validation (LOW) `bin/install-agent-ssh-key.sh:72-74`.
- **CANON-27:** Nextcloud/Postgres/Redis image pins are pins-as-DEFAULT not hard SoT (env overrides before interpolation) (LOW) `bin/common.sh:1577-1582`; hosted-API config-file merge does not feed session-pepper enforcement (LOW) `arclink_hosted_api.py:295-329` vs `arclink_api_auth.py:271-282`.
- **CANON-28:** live-agent-tool-smoke opens the control DB read-WRITE not `mode=ro` (LOW) `bin/live-agent-tool-smoke.sh:102`; preflight `bash -n` omits the root `deploy.sh` shim (LOW) `bin/ci-preflight.sh:186-195`; provider-skip live-smoke exits 0 → fail-open for "smoke passed" (INFO) `bin/live-agent-tool-smoke.sh:481-490`.
- **CANON-29:** non-live tests bind/connect loopback sockets (refutes "no sockets in CI") (LOW) `tests/test_arclink_agent_access.py:314-318`; stale hardcoded success-summary counts mask runner drift (docker "61", executor "41", chutes "24") (LOW) `tests/test_arclink_docker.py:8018`.
- **CANON-30:** code `/git/*` returns raw unredacted git stderr (absolute paths) in 400 detail (MEDIUM) `code/dashboard/plugin_api.py:1126-1128`; default-install regression test omits `arclink-crew` (LOW) `tests/test_arclink_plugins.py:20-26`; token-injection tests omit `pod_comms.*`/`ssot.approve|deny` → the HIGH seam break is invisible to CI (LOW) `tests/test_arclink_plugins.py:4038-4180`.
- **CANON-31:** token-bearing JSON reaches `arclink_rpc_client.py` argv for the HTTP-call lifetime (≤20s; `--json-args-file` unused) (LOW) `curate-vaults.sh:62`; `notion-page-pdf-export.py` silently overwrites exports when two pages share a slug (LOW) `bin/notion-page-pdf-export.py:286-289`.
- **CANON-32:** byte-identity overclaim is **3-doc-wide** not GTB-only (LOW) `docs/API_REFERENCE.md:373-378`; `docs/arclink/architecture.md:297-301`; public-repo hygiene mechanism was misstated — untracked-unignored files ARE scanned (LOW/INFO) `tests/test_public_repo_hygiene.py:18-23`.

---

## 4. Code-vs-doc drift ledger

> Every place a comment, name, docstring, prior research doc, or memory note **lied vs code**.
> Code wins; the drift is named and cited. Grouped by domain.

### Stale counts & inventory (the biggest systemic drift)
- **Table/module counts everywhere stale.** Code has **45 `arclink_*` + 10 `academy_*` (80 total incl. 25 substrate)**; GTB/architecture.md/MEMORY.md say 44 + 9 (or "44 + 4"). New tables: `arclink_agent_skill_enablement` (`arclink_control.py:1718`), 6 new academy_* incl. `academy_source_crawl_observations` (`:1686`). `MEMORY.md` "44 arclink_* / 4 academy_*" stale. (CANON-01, CANON-17, CANON-32)
- **Module count 87, not 84.** New module `arclink_operator_upgrade_host_runner.py` (added 2026-06-12, commit 63a42c8) is in 0 tracked docs; `arclink_upgrade_policy.py` also absent from the canonical architecture.md map and GTB §3. (CANON-32)
- **Routes: 71 `_ROUTES` entries / 71 OpenAPI paths**, not GTB's "69/67". New routes `public_academy_observatory`, `user_academy_specialist_adopt`. (CANON-02, CANON-32)
- **ALMANAC_* aliases are vapor.** `grep ALMANAC python/ = 0`; `ARCLINK_ENV_ALIASES = {}`. MEMORY.md and env templates advertise an alias-precedence contract with zero implementation. (CANON-01, CANON-03, CANON-27)

### Names that lie about behavior
- `tailscale-nextcloud-serve.sh` **tears down**, does not serve (~200 lines dead serve helpers); still invoked under `ENABLE_TAILSCALE_SERVE==1`. (CANON-31 `:235-240`)
- `request_arclink_backup_write_check` never runs git — unconditionally records `failed_closed`. (CANON-19 `:1379-1383`)
- `_default_verifier` (CANON-13) name hides **fail-open** on zero health rows. (`:563-572`)
- `normalize_anthropic_credential` always raises (OAuth-only guard). (CANON-04 `:466-470`)
- `arclink_resource_map.py` is misnamed — it builds access-URL rail lines, zero inventory/ASU coupling. (CANON-10)
- `assert_chutes_inference_allowed` is router-named but only the **fake** client calls it. (CANON-16 `:959`)
- `json_dumps_safe` rejects secrets but control-side `_arclink_json`/`json_dumps` only validate JSON. (CANON-01)
- terminal plugin "ssh" mode launches a **local** shell; `_clean_ssh_target` is dead code. (CANON-30)
- `has_curator_non_telegram_gateway_channels` is a misnamed alias covering Discord too. (CANON-06 `common.sh:761-763`)

### Dead writes / dead config
- `arclink_upgrade_last_dismissed_sha` written (CANON-06 `:975`, CANON-06-discord `:272`) but **never read** anywhere; real suppression key is `arclink_upgrade_last_notified_sha`. (DISSECT.md:277 corroborated)
- `org_profile_*` tables are write-only (no SELECT anywhere). (CANON-21)
- Evidence DB ledger (`arclink_evidence_runs`) built but never wired to any read surface. (CANON-23)
- `rollback_apply` full live API has zero production callers. (CANON-11 `:1426`)
- `provision/reconcile/teardown_arclink_dns` implement a cloudflare-object protocol production never uses (only tests). (CANON-09)
- `payment_pending`/`paid`/`completed` onboarding statuses declared in the CHECK but never assigned. (CANON-04)
- `pytest.ini` testpaths declared but CI never runs pytest. (CANON-29)
- ruff/pyflakes pinned in requirements-dev but never invoked in any gate. (CANON-28)
- `model-providers.yaml` `version` field never read; `academy-source-lanes.example.json` is decorative **except** it IS a drift-guarded test fixture (refuted as fully dead). (CANON-27)

### Prior-doc / DISSECT / memory drift
- Prior ground-truth doc 04 labels the curator surface "OLD/legacy/undocumented Almanac path"; code shows it is the **live systemd-managed** curator surface (23-command operator overlay). (CANON-06)
- Prior doc 05 (operator-raven): MUTATING_COMMANDS is **7** (not 4); line numbers systematically stale. (CANON-14)
- Prior doc 06 (academy): scaffold/UNBUILT verdict refuted — Academy is materially built and ships live crawler+trainer default-ON. (CANON-17)
- Prior doc 09 (billing) control-plane offsets stale by ~hundreds of lines; semantics accurate. (CANON-07)
- Prior doc 02 (provisioning): `ARCLINK_CAPTAIN_MIGRATION_ENABLED` is **doc-only** (read nowhere in code); real gate is the double opt-in. (CANON-13)
- Prior doc 02: handoff gate also blocks on `'starting'` and a second `REQUIRES_HERMES_HOME_READY` gate, both omitted. (CANON-08)
- DISSECT P2 anchor `_run_operator_upgrade_action` does not exist; real path `_run_host_upgrade→_run_brokered_host_upgrade`. DISSECT/Claude "everything becomes returncode-2" false (UnicodeDecodeError escapes). (CANON-08)
- `config/docker-authority-inventory.json` **prose** still says "writeable Docker socket"/egress for operator-upgrade-broker while **structured** fields say none/[] (drift test only checks structured). (CANON-15, CANON-27)
- `_NEXT_ACTION_RE` is alternation-equal between GTB and code, **not** byte-identical (GTB omits `\b` boundaries). (CANON-32)
- DISSECT.md is correctly scoped to the operator-upgrade pipeline only (not corpus-wide). (CANON-32)

### Docstring/comment vs code
- `arclink_executor` `DockerRunner.run` "real Docker command execution" is satisfied equally by Fake/Brokered runners. (CANON-11)
- Module docstrings overstating: "capture is injectable" (no param; CANON-13); "byte-identical OpenAPI" (canonical-JSON equality; CANON-02/32); "secret-hostile by design / cannot hold provider keys" (free-text hints escape; CANON-04); `academy_continuing_education` "behind PG-PROVIDER" (env-gated, default-on; CANON-17).
- `_spawn_batcher_now` claims the Popen destructor reaps the zombie — CPython Popen has no `__del__` waiter. (CANON-18 `:38-41`)
- `qmd-daemon` loopback-bump comment omits the `QMD_MCP_INTERNAL_PORT` guard. (CANON-31)

---

## 5. Disagreement register (open for the Codex federation)

> The highest-value targets for Codex's independent GPT-5.5 pass. Merged from every piece's
> `openForCodex`, every verifier `residualDisagreement`, and every `refuted` claim. This is
> the explicit room for principled disagreement. Numbered for citation in the Codex overlay.

### A. Refuted Claude-half claims to re-adjudicate (verifier overturned the auditor)
1. **CANON-01:** `rowdict` is imported in **6** modules (AST), not 26 (grep counted all boundary importers). `append_arclink_event` TRACE step-8 round-trip cites the **wrong tables** (rollouts/sessions, not arclink_events). "80 tables" = 79 owned CREATEs + `sqlite_sequence`. → **[RECONCILED: winner=codex** — rowdict importers=6 (`arclink_boundary.py:76`); real event readers `arclink_dashboard.py:1545-1560`, `arclink_hosted_api.py:961-968`; 80 runtime = 79 owned CREATEs + sqlite_sequence**]**
2. **CANON-02:** OpenAPI parity is **canonical-JSON equality, not byte-identity**; `_CIDR_PROTECTED_ROUTES` includes a non-admin route (`session_revoke`); `http_request` importers = 10 not 11; Stripe contract is **fully** both-ends-verifiable (not "partial"). → **[RECONCILED: winner=both/codex** — parity canonical-JSON (`tests/test_arclink_hosted_api.py:5505-5507`); CIDR list = "all admin_* PLUS session_revoke" (`arclink_hosted_api.py:3865`); importers 9 real of 10 mentions (`arclink_http.py:66`); Stripe seam full (`arclink_hosted_api.py:906-916` ↔ `arclink_entitlements.py:155-161`)**]**
3. **CANON-04:** "public onboarding store cannot hold provider keys" is **false** (free-text hints escape the filter). RISK#2's concrete bypass cite (`api_auth.py:1093`) is **actually scanned** by `json_dumps_safe`. → **[RECONCILED: winner=both** — `_PLAINTEXT_SECRET_RE` (exec) escapes `sk-ant-`/`sk-`/`cpk_`/`AKIA` into hints (`arclink_onboarding.py:116-126`); `:1093` IS scanned (`arclink_api_auth.py:1092-1095`; `arclink_boundary.py:65-73`) → that MEDIUM downgrades to LOW/INFO. Webhook HIGH mechanism corrected: paid write is NOT rolled back, it was already committed**]**
4. **CANON-05:** "Discord sentinel-key rejection" is **docstring drift** — protection is purely cryptographic (64-hex). Contract #1 `display_name` is consumer-only (producer never emits). → **[RECONCILED: winner=both** — crypto fail-closed `arclink_discord.py:239,243-246`; `display_name` consumer-only-with-fallback `arclink_public_bots.py:3919-3951` ↔ `arclink_notification_delivery.py:682`. Plus 3 net-new Codex risks confirmed (HIGH /credentials leak; MEDIUM reusable checkout token; LOW swallowed send)**]**
5. **CANON-07:** The central "all inside ONE transaction" atomicity claim is **FALSE** on the dominant web-checkout-with-onboarding path (premature commit); all webhook errors do NOT surface as 400 (KeyError→404). → **[RECONCILED: winner=claude** — `expire_stale_arclink_onboarding_sessions(commit=True)` fires `conn.commit()` mid-webhook (`arclink_onboarding.py:324-325,337,807`); entitlement durable before processed-mark (`arclink_entitlements.py:789`); KeyError→404 (`arclink_hosted_api.py:4243-4245`). 4 net-new Codex findings confirmed incl. HIGH durable-`received` strand**]**
6. **CANON-08:** Fleet audit chain is **NOT** "cryptographically sound / P0 on tamper" — unkeyed-legacy verify branch allows full chain re-forge. → **[RECONCILED: winner=both** — unkeyed fallback `arclink_fleet_enrollment.py:469-472,891-902`, P0 only on errors `:904` (MEDIUM). Plus net-new MEDIUM: consume not transaction-clean, orphan inventory/fleet-host rows (`arclink_inventory.py:262`; `arclink_fleet.py:247`) — overturns verifier's "no orphan inventory row"**]**
7. **CANON-10:** `parse_probe_output` does **not** extract disk size from `df -BG` — the `continue` guarantees disk_gib=0 on real output (HIGH, untested). Cloud lifecycle is fail-leaky (orphaned VM), not "fail-closed". → **[RECONCILED: winner=both** — executed parse→`disk_gib=0`, `compute_asu=0`, gate `arclink_fleet.py:143,701` (LOW→HIGH); fail-OPEN paths exist (`arclink_inventory.py:472-474`). 4 net-new defects (orphan VM MEDIUM, stale-ready fail-open MEDIUM, failed-idempotency bare-replay MEDIUM, non-atomic fleet-host LOW)**]** *(Hetzner live units remain a STANDING DISAGREEMENT — see §C / sign-off)*
8. **CANON-12:** "stdin-only, never on disk" bot-token claim is **false** (detached path persists token). cap_drop ALL vs setpriv likely breaks agent processes. → **[RECONCILED: winner=both** — detached path writes `bot_token` to a 0600 job file (`arclink_notification_delivery.py:973-1001`) = HIGH. Verifier's FD-leak REFUTED (log handle GC-closed). cap_drop-vs-setpriv held HIGH pending live proof = **STANDING DISAGREEMENT**; production state-root symlink reality deferred to CANON-13**]**
9. **CANON-13:** GC rmtree has **NO** `.migrations` guard (record claimed it shares the rollback guard) — material factual error. → **[RECONCILED: winner=codex** — GC is `exists()+rmtree` only (`arclink_pod_migration.py:1254-1258`); the `.migrations` guard lives only in `_cleanup_rolled_back_capture` (`:844`), strong validation in the pre-mutation `_validate_capture_paths` (`:160-185`). Residual is a wording-precision **STANDING DISAGREEMENT** (no behavioral conflict)**]**
10. **CANON-14:** Non-Telegram callers DO enforce the approval code (caller set is closed, 3 transports); academy_apply IS executor-adapter gated (record's MEDIUM mechanism wrong); the genuine residual is the callback-path code-skip (LOW). → **[RECONCILED: winner=both/claude** — approval-code-in-transport MEDIUM→LOW (closed caller set `arclink_telegram.py:1305-1307` etc.; true residual is the LOW callback path `:822-838`); academy_apply MEDIUM→LOW (4 gates `arclink_academy_programs.py:2864,2938-2940`). 4 net-new (MEDIUM `operator_actions` non-atomic queue; MEDIUM stale-action infinite re-queue; LOW executor-select-before-attempt; LOW symlink-ancestor — see §C STANDING)**]**
11. **CANON-16:** Router does **not** enforce allowlist on the routed/upstream model (input filter only); usage idempotency is inert on the router path; CONTRACT #3 misnames a read column. → **[RECONCILED: winner=both** — allowlist is INPUT-only; replacement/auto-promote/fallback + global default-model exception route around it (`arclink_llm_router.py:650,1465,1646`); router-path idempotency immune (fresh uuids); CONTRACT #3 reads status/rowcount not `secret_ref` (`arclink_api_auth.py:4625`). All 4 Codex NF re-verified (NF-1/NF-2 MEDIUM, NF-3/NF-4 LOW)**]**
12. **CANON-17:** Crew staging functions DO return `mutation_performed=True` (record said all False); Contract #2 marker is hardcoded both sides (convention-matched, not field-read). → **[RECONCILED: winner=codex** — Crew staging+apply return True (`arclink_crew_recipes.py:373,953`; `arclink_action_worker.py:2227`); consumer ignores producer `academy_soul_marker`, uses a hardcoded marker (`:2087`). Net-new MEDIUM NF-1: `academy_apply` advertises PG-PROVIDER but enforces only PG-HERMES at the write boundary**]**
13. **CANON-18:** The "dead env var" DRIFT/RISK/verdict is **factually wrong** (read at `memory_synthesizer.py:329`); broker IS fail-closed on destructive ops; CONTRACT #5 misnames the normalizer's read keys; loopback is not a real defense under Funnel. → **[RECONCILED: winner=both** — env live (`:329-335`), setting it 0 disables the cap (LOW); SSOT broker fail-closed (`arclink_control.py:17105-17112`); normalizer reads `applied/queued/approval_required/status`+nested `notion_result.{url,id,object}` (`arclink_mcp_server.py:1597-1623`); loopback not a public Funnel defense, HMAC is the gate. 2 net-new MEDIUM (armed-window token race; unclaimed reindex double-sync)**]** *(qmd protocol ratification = STANDING — external binary)*
14. **CANON-19:** SSO cookie path is **NOT dead** — live in-repo producer chain in Docker mode → per-user cross-deployment domain-scoped SSO; `--agent-title` never sent. → **[RECONCILED: winner=codex** — live producer `bin/install-deployment-hermes-home.sh:163,169-171`+`bin/arclink-docker.sh:1676-1698`, live consumer `arclink_dashboard_auth_proxy.py:674-693` (INFO→MEDIUM, scoped to one user's fleet, `subject=user_id` so MEDIUM not HIGH); `--agent-title` not in provisioner argv (`arclink_enrollment_provisioner.py:1409-1422`). Net-new: provider hardcoded to Chutes (MEDIUM), `config.yaml` dual-writer (MEDIUM)**]**
15. **CANON-20:** Probe-wrapper seam is producer-subset+fallback, not "key-by-key"; the compute_asu crash is **first-party-reachable** (degraded host), not adversarial-only. → **[RECONCILED: winner=codex** — worker `.get()` fallback (`arclink_fleet_inventory_worker.py:352,354`); `vcpu_cores:0` from `getconf||nproc||'0'` → `compute_asu` raises (`bin/arclink-fleet-probe-wrapper:77`; `arclink_asu.py:57-58`) MEDIUM first-party-reachable. Net-new MEDIUM: unchecked Fleet working path (`git add -A` whole-tree exfil); `.corrupt` quarantine LOW→MEDIUM (data-loss); `fleet-share-reconcile` confirmed STARTS in prod (`deploy.sh:11637`→`arclink-docker.sh:3376`)**]**
16. **CANON-22:** Self-check #2 is wrong — a 'failed' row **shadows** (does not clobber) the 'generated' row; the 404 fail-open spans the control-plane lane too. → **[RECONCILED: winner=both** — duplicate-report storm MEDIUM→HIGH (`arclink_wrapped.py:1043-1095`); 404 fail-open re-scoped to BOTH lanes (`common.sh:1390-1397`; `backup-to-github.sh:131`). Net-new MEDIUM: control-lane API-base spoof (`common.sh:1331-1333`). Codex's operator-pin-push and §B39 Stripe findings code-true but ROUTED OUT to CANON-15 / CANON-07/04**]**
17. **CANON-24:** `bin/init.sh` is the **752-line agent enrollment flow**, not a 5-line wrapper (that is `install-arclink.sh`); P7 component sets are independent gates (7 vs 12), not a match; `run_upgrade_flow` is dead code. → **[RECONCILED: winner=claude** — all 5 refutations hold (`bin/init.sh:1-7` wc=752; P7 safe-subset `arclink_operator_upgrade_host_runner.py:26-34` vs `config/pins.json`; `run_upgrade_flow` only def `:8224`; SOUL.md filename; breadcrumb mis-key scoped). 3 net-new Codex confirmed (MEDIUM no control-upgrade branch guard `deploy.sh:11550-11567`; MEDIUM deploys local-ahead commits; LOW unquoted-secret source)**]**
18. **CANON-26:** service/timer split is **19 + 10** (not 18 + 11); the access-state risk is silent **fail-OPEN** (not fail-closed KeyError); the unit-injection "strength" is overstated (only Environment= lines guarded, guard inert in heredoc). → **[RECONCILED: winner=both** — 19/10 (`ls systemd/user/`); access-state MEDIUM→HIGH fail-OPEN (executed `install-agent-user-services.sh:276-294`); injection guard INFO→MEDIUM (only Environment= guarded). Net-new HIGH: SSH-key newline injection (`bin/install-agent-ssh-key.sh:54-56,115`). Two cross-repo CANON-30 Hermes-CLI seams = STANDING**]**
19. **CANON-27:** The env-ref-override MEDIUM risk is **INVERTED** — pins.json wins via `__pins_get_or_default`; the academy example file is a drift-guarded fixture, not decorative; `container_user` is not compose-derived. → **[RECONCILED: winner=both** — env-ref MEDIUM→INFO (pin wins `bin/common.sh:545-552`); academy file is a drift-guarded fixture INFO→LOW (`tests/test_arclink_academy_trainer.py:256,268,287`); real top risk is the `pins_set` fail-open clobber MEDIUM (`bin/pins.sh:81-85,94-99`); pins.json=12 components, superset of 8 managed**]**
20. **CANON-29:** "exactly 3 orphans" is wrong (**10** across 6 files, incl. 2 broker fail-closed proofs); "no sockets/subprocess in CI mode" is wrong (44 files call subprocess; two suites fail on read-only fs). → **[RECONCILED: winner=codex** — AST=10 orphans across 6 files; non-hermetic suites refuted (`test_deploy_regressions.py` shells real scripts+`systemd-analyze`; `test_arclink_executor.py` writes `/arcdata` via non-Fake runner); Playwright NOT CI-run; J-19 `-k` paper proof. Whether those two suites are RED in real CI = **STANDING DISAGREEMENT** (host-conditional; Codex: likely PASS on writable ubuntu-22.04)**]**
21. **CANON-30:** Contract #2 (managed-context → MCP token injection) is **NOT** both-ends-verified (`_TOKEN_TOOL_NAMES` not a superset → live break); code git timeout is 15s not 30s. → **[RECONCILED: winner=codex** — seam misses `pod_comms.*`+`ssot.approve`+`ssot.deny` (HIGH live break, `arclink-managed-context/__init__.py:1843` vs `arclink_mcp_server.py:1094,2615,2634`); `agents.register` correctly EXCLUDED (REGISTRATION_TOKEN_PROP); git timeout 15s (`code/dashboard/plugin_api.py:103`); raw git stderr unredacted MEDIUM (`:1126-1128`)**]**
22. **CANON-32:** The product-matrix totals **ARE** row-summed/guarded (`test_documentation_truths.py:76-88`) — refutes the record's headline RISK; main() runs **11** doc-truth tests not 4; 3 undocumented modules not 2. → **[RECONCILED: winner=codex** — matrix totals guarded (`:76-88`); a real OpenAPI parity test EXISTS and PASSES via canonical-JSON equality (`tests/test_arclink_hosted_api.py:5496-5507`, runner `:6375`) → parity MEDIUM→LOW; untracked-artifact LOW→INFO (unignored files ARE scanned); the genuinely-unguarded item is the module+table COUNT (MEDIUM); missing-module count = 3 (`arclink_upgrade_policy` added)**]**

### B. Open-for-Codex investigations (load-bearing, unverified at one end)
23. **CANON-01:** Confirm `ensure_schema` is the sole control-DB schema authority repo-wide and nothing writes `PRAGMA user_version`; rebuild under DOCKER_MODE vs WAL to confirm table count stable / no `__new` leftovers. → **[RECONCILED: winner=codex** — `ensure_schema` is primary but NOT sole: `org_profile_apply` adds 5 `org_profile_*` tables on the same connection (→85) (`arclink_ctl.py:2090`; `arclink_org_profile.py:1910-1957`); no `user_version` writer (=0); no `__new` leftovers; process-env-wins confirmed (`arclink_control.py:305,334`)**]**
24. **CANON-02:** Open `is_ip_in_cidrs`/`is_loopback_ip` bodies for IPv6/port/malformed-string safety; confirm no second route table bypasses `_CIDR_PROTECTED_ROUTES`; does any shipped topology leave REMOTE_ADDR empty? → **[RECONCILED: winner=codex** — CIDR predicates fail closed on malformed IP/CIDR, IPv4/IPv6 via `ipaddress` (`arclink_control.py:7604-7625`); REMOTE_ADDR risk broadened: trusted-proxy-without-XFF also collapses the gate (`arclink_hosted_api.py:635-641`) MEDIUM**]**
25. **CANON-04:** Confirm `payment_pending/paid/completed` are truly never assigned; is a 'completed' transition intended (appears MISSING)? → **[RECONCILED: winner=both** — dead statuses never set by NEW machine (forward writes only `provisioning_ready` `:815`, `first_contacted` `:890`); `arclink_onboarding.py:23-43`**]**
26. **CANON-07:** Refuel double-grant — confirm single-transaction invariant prevents replay doubling and that `grant_arclink_refuel_credit` has zero `(source_kind,source_id)` uniqueness guard; forged-metadata entitlement write reachability. → **[RECONCILED: winner=both** — refuel grant lacks `(source_kind,source_id)` guard (`arclink_control.py:4436-4456`) but single-txn non-doubling holds for the refuel branch (it does NOT call onboarding sync); forged-metadata scope refined to include merge-repoint (`arclink_entitlements.py:673-688`; `arclink_control.py:3752-3787`)**]**
27. **CANON-08:** Enumerate ALL writers of `operator_actions.request_source` and confirm `'operator-raven'` is only set by genuinely-confirmed paths. → **[RECONCILED: winner=codex** — the gate is a string eq (`arclink_enrollment_provisioner.py:2292-2297`) and the producer persists the caller-supplied `request_source` verbatim (`arclink_control.py:8302`) → reframed as a current-writer string convention, NOT a capability boundary**]**
28. **CANON-11:** Confirm NO production path injects `operation_conn`; audit remote bind-prepare for injection; assess TOCTOU/symlink race. → **[RECONCILED: winner=codex** — `operation_conn` dead in prod (factory omits it `:142`); but the record's "table written ONLY by tests" is FALSE — `arclink_operation_idempotency` is production-used by inventory+pod_migration (`arclink_inventory.py:746`; `arclink_pod_migration.py:1006`); only the executor's `operation_conn` path is dead. Live Chutes/Stripe raise before any provider call (HIGH re-scoped latent)**]**
29. **CANON-12:** Audit the bridge argv shapes; verify only the documented single client is attached to each `*-broker-net`; live-confirm the cap_drop-ALL vs setpriv EPERM hypothesis (G2). → **[RECONCILED: winner=both** — gateway-exec-broker-net operator co-attachment is CURRENT topology not future (`compose.yaml:388-391`), token-gated MEDIUM; FD-leak REFUTED (GC-closed); chown -R is validate-then-act only (default -P). cap_drop-vs-setpriv EPERM held HIGH = **STANDING DISAGREEMENT** (needs live container run)**]**
30. **CANON-13:** Two simultaneous `migrate_pod` with same operation_key + 'running' row — both proceed past reserve? Does any outer lock serialize? → **[RECONCILED: winner=both/codex** — same-key running row → both proceed (`arclink_control.py:3207-3208`; `arclink_pod_migration.py:1013-1017`); the only serialization is the single serial worker loop (`arclink_action_worker.py:652-676`); distinct reprovision actions use distinct keys (`:1154-1157`) so idempotency gives zero protection. Plus net-new HIGH stale-health verifier**]**
31. **CANON-14:** Reconcile DISSECT P1/M3 — should Raven filter on `silenced`? Button-nonce double-consume race? Verify the public-agent-turn + operator_turn seam. → **[RECONCILED: winner=both** — dismissed pin upgrades stay queueable (`arclink_control.py:9601,9686`; raven `:1284,1290` active_only) MEDIUM stands; button-nonce consume non-atomic read-check-write, no BEGIN IMMEDIATE (`arclink_operator_raven.py:1381-1394`); public-agent-turn/operator_turn seam now BOTH-ENDS verified (`arclink_operator_agent.py:271-278` ↔ `arclink_notification_delivery.py:1576-1583`)**]**
32. **CANON-15:** Can the detector emit `hermes-docs` WITHOUT `hermes-agent` (broker rejects)? Detector concurrency under overlapping passes? Re-confirm H1. → **[RECONCILED: winner=both/codex** — hermes-docs-only `install_items` reachable then broker-rejected (`arclink_pin_upgrade_check.py:643-646`; `arclink_operator_upgrade_broker.py:48`); detector concurrency SELECT→INSERT no lock INFO→LOW (`:405-409,431-443`); H1 poison/symlink wedge re-confirmed HIGH (`arclink_operator_upgrade_host_runner.py:412`). M3 MEDIUM→LOW, M5 MEDIUM→LOW (doc-drift)**]**
33. **CANON-16:** Who writes `chutes.budget_policy=observe_only_unlimited` and is it Operator-only? Confirm GAP-031. Usage-event idempotency collision? → **[RECONCILED: winner=codex** — only non-test writer is the Operator-agent stamp (`arclink_operator_agent.py:150`) but the router trusts the metadata with no provenance check (`arclink_llm_router.py:1149`) = MEDIUM fail-open; GAP-031 genuinely open — prod posts to real Chutes only when no mock transport injected (`:1463`), named live-proof env gate does NOT exist; router-path idempotency collision NOT credible (fresh `llmuse` uuid)**]**
34. **CANON-17:** Confirm whether Academy CE crawl / Trainer live are disabled anywhere — compose defaults imply ON. Adversarial DNS-rebinding review of the crawler SSRF guard. → **[RECONCILED: winner=both** — HIGH live-default: CE crawl + Trainer ship default-ON (`arclink_academy_scheduler.py:625`; `compose.yaml:97,793`); HIGH DNS-rebinding/TOCTOU confirmed (`getaddrinfo` validate then `Request(str(url))` re-resolves, `:196,219`). Plus net-new MEDIUM NF-1 (PG-PROVIDER cosmetic at write boundary)**]**
35. **CANON-18:** Find the producer of `notion-reindex` rows; prove two concurrent ssot-batcher runs cannot double-process one event under WAL; confirm pinned qmd speaks MCP 2025-03-26. → **[RECONCILED: winner=codex** — the event-table path IS lease-guarded (`arclink_control.py:19154`) but the reindex path is NOT claimed before live sync (net-new MEDIUM double-sync, `:14828-14964`); the formal WAL stress test of the event path is CANON-01-internal and un-run. qmd MCP protocol = **STANDING DISAGREEMENT** (external binary, comment stale 2.5.2 vs pin 2.5.3)**]**
36. **CANON-19:** Which producer writes `arclink-web-access.json` ports? Which CANON-22 backup script reads `backup_deploy_key_private_ref`? → **[RECONCILED: winner=codex** — port-key producer is `arclink_agent_access.py:524-525`, but `install-deployment-hermes-home.sh:164` overloads the same filename WITHOUT them (drift source, see CANON-26 net-new); NO reader of `backup_deploy_key_private_ref` — shipped backup uses a separate `AGENT_BACKUP_KEY_PATH` (`backup-agent-home.sh:39`) → it is an ORPHANED rail**]**
37. **CANON-20:** Is `fleet-share-reconcile` actually started in prod (not just defined)? Does sync converge under N concurrent writers? → **[RECONCILED: winner=codex/both** — `fleet-share-reconcile` EXISTS (`compose.yaml:1082-1094`) and STARTS in the default prod compose-up lane (`bin/deploy.sh:11637`→`bin/arclink-docker.sh:3373-3376`, no profile gate); sync has no lock and a 2-attempt bound that returns error on a healthy hub (`arclink_fleet_share.py:309-363`) but surfaces conflicts rather than clobbering**]**
38. **CANON-21:** Confirm NO code path SELECTs the `org_profile_*` tables; validate apply-scope skips operator/curator agents. → **[RECONCILED: winner=both** — 5 `org_profile_*` tables written, never read tree-wide (`rg (FROM|JOIN) org_profile_* = 0` outside research/); apply fan-out scope = role='user' AND status='active' only (`arclink_org_profile.py:2069`; `arclink_control.py:18848`). Net-new MEDIUM: reference `audience` ignored in vault render; LOW: reference path not containment-checked**]**
39. **CANON-22:** Does any topology strand a `received` webhook row? Is quiet-hours math correct under DST/non-UTC? Does restore-smoke run in CI with both `--kind`? → **[RECONCILED: winner=codex** — the `received`-strand is real but OWNED BY CANON-07 (routed out); quiet-hours math is UTC-only not local/DST-correct (INFO, `arclink_wrapped.py:80,802-809`); restore-smoke IS exercised with both `--kind` values via the all-tests workflow (`.github/workflows/install-smoke.yml:33-41`)**]**
40. **CANON-23:** Verify the gateway-exec-broker `/v1/public-agent-bridge` contract end-to-end; confirm `arclink_evidence_runs` never written outside tests; album-sibling leader race? → **[RECONCILED: winner=both/codex** — gateway-exec broker seam now BOTH-ENDS-verified (`arclink_gateway_exec_broker.py:227-238`); evidence DB unwired (zero DAL callers); album-leader race RESOLVED (no race — exclusive lease per row, deferred sibling lease persists to expiry, `:1702-1708,1527`). 2 net-new MEDIUM (head-of-line blocking under limit=1; live-proof exit-0 ignoring readiness/diagnostics)**]**
41. **CANON-24:** Is `ARCLINK_UPSTREAM_DEPLOY_KEY_*` load-bearing on control-upgrade or inert? Confirm no non-retired MODE reaches `run_root_upgrade`. → **[RECONCILED: winner=both** — deploy-key env forwarded to control-upgrade is INERT (plain `git fetch --prune`, no `GIT_SSH_COMMAND`, `bin/component-upgrade.sh:498-504`); public `install|upgrade|health` route to the Control Node, root upgrade only via privileged `--apply-upgrade` (`bin/deploy.sh:13012-13016,779-782`). Net-new MEDIUM: no live control-upgrade branch guard; deploys local-ahead commits**]**
42. **CANON-25:** Does any layer set the trusted-host gate so the 7 brokers boot? Any strict job-status consumer without the or-fallback? Confirm broker-net client attachment. → **[RECONCILED: winner=both/codex** — trusted-host gate enforced with `SystemExit`/literal `accepted` in all 7 modules; default empty → all 7 crash-loop; NOTHING in tracked code auto-injects `accepted` (`arclink_boundary.py:80-97`; compose+bootstrap empty); no STRICT job-status consumer exists today (dashboard reads only status/timestamps, `arclink_dashboard.py:467-491`) → drift benign; broker-net co-attachment is multi-client per net (`compose.yaml:669,730,774`). Net-new: no broker liveness probe MEDIUM; non-atomic status write LOW; redaction fail-open MEDIUM; egress-net MEDIUM**]**
43. **CANON-26:** Which producer writes `arclink-web-access.json`; does `disable_native_hermes_gateway_units` enumerate Hermes-native units; does the rendered gateway `ExecStart` match the Hermes CLI? → **[RECONCILED: winner=both** — producer `arclink_agent_access.py:524-525` emits both port keys; the schema-overload filename drift is the net-new MEDIUM. The Hermes gateway CLI contract (two invocation styles `gateway run --replace` vs bare `gateway`) and `disable_native_hermes_gateway_units` completeness are **STANDING DISAGREEMENTS** — the consumer (Hermes gateway argparse) is in CANON-30/external, not this repo**]**
44. **CANON-27:** Confirm no `resolve_env` site passes a non-empty `legacy_key`; confirm pins.json wins over env-ref; verify the 4 traefik upstreams. → **[RECONCILED: winner=both** — ALMANAC alias contract is VAPOR (`ARCLINK_ENV_ALIASES={}`, no non-empty `legacy_key=` call site, `arclink_product.py:12,42-66`); pins.json wins (`bin/common.sh:545-552`); 4 traefik upstreams confirmed defined compose services**]**
45. **CANON-28:** Coverage over the real CI loop esp. `arclink_rejection_incidents`/`arclink_upgrade_policy`; confirm no workflow invokes pytest; does 90m cover a cold bring-up? → **[RECONCILED: winner=both/codex** — exactly 3 CI gates, pytest never invoked (`.github/workflows/install-smoke.yml:31-41`); `rejection_incidents` IS behaviorally covered (`arclink_gateway_exec_broker.py:151-153` + test wiring), `upgrade_policy` has no dedicated test (transitive via Raven); live-smoke DB read-WRITE (LOW); root `deploy.sh` shim un-linted (LOW); provider-skip fail-open (INFO). 90m cold-bringup sufficiency is a shared static-analysis limit (not a dispute)**]**
46. **CANON-29:** AST-enumerate orphaned `test_*` (found 10); diff the helper INSERT vs DDL; grep `.github/**` for `ARCLINK_E2E_LIVE`. → **[RECONCILED: winner=codex** — 10 orphans across 6 files confirmed by AST (registries omit them); helper INSERT cols all present in DDL (omitted cols are NOT NULL DEFAULT '', `tests/arclink_test_helpers.py:74-93` ↔ `arclink_control.py:1309-1332`); live E2E fail-safe (skipped=6); J-19 `-k` unenforced HIGH paper proof (`research/COVERAGE_MATRIX.md:36`)**]**
47. **CANON-30:** Confirm `_TOKEN_TOOL_NAMES` is a complete superset (it is NOT); confirm the external `skills_sync.py` contract; stress-test the regex config.yaml editor. → **[RECONCILED: winner=codex** — NOT a superset: misses `pod_comms.list/send/share-file`+`ssot.approve`+`ssot.deny` (HIGH live break); `agents.register` correctly EXCLUDED; broker-token gates the share route (`arclink_api_auth.py:255,257`); terminal "ssh" mode is a cosmetic local shell, `_clean_ssh_target` dead. external `skills_sync.py` contract not in repo (deferred)**]**
48. **CANON-31:** Confirm `tailscale-nextcloud-serve.sh` is intended pure teardown; confirm `pdf_ingest_manifest` single writer; confirm `hermes_cli.config.save_config` atomic. → **[RECONCILED: winner=both** — tailscale-serve is an active `ENABLE_TAILSCALE_SERVE=1`-drives-teardown contradiction MEDIUM (`deploy.sh:5570-5571,5712-5713`); `pdf_ingest_manifest` single writer confirmed (`bin/pdf-ingest.py:474,...`); skill→MCP executed seam is 8 ArcLink-MCP tools (not 14/5). `hermes_cli.config.save_config` atomicity = **STANDING DISAGREEMENT** (external pinned Hermes package, not vendored)**]**

### C. Residual severity disagreements (Claude auditor vs Claude verifier — pending Codex tiebreak)
49. **CANON-09:** Is the dead cloudflare-object API surface MEDIUM (doc-trust) or LOW (operational)? → **[RECONCILED: winner=both** — MEDIUM as a doc-trust hazard, operationally LOW (pure dead code, zero production callers; `arclink_ingress.py:114,192,207`)**]**
50. **CANON-13:** Is the empty-health fail-open verifier MEDIUM or HIGH? → **[RECONCILED: winner=codex — HIGH** — apply writes no health, status=applied; the prod action-worker injects no verifier; it accepts empty AND stale source health and ignores captured `docker_status` (`arclink_action_worker.py:1169-1178`; `arclink_pod_migration.py:563-572`)**]**
51. **CANON-15:** M3 (dismissed-but-active) — MEDIUM or LOW? → **[RECONCILED: winner=codex — LOW** — silenced digest, Raven /list UX only (`arclink_operator_raven.py:1627-1637`; `arclink_control.py:9686`)**]**
52. **CANON-27:** Env-ref override — INFO (pins.json wins) vs MEDIUM (record)? → **[RECONCILED: winner=both — INFO** — pins.json wins via `__pins_get_or_default` (`bin/common.sh:545-552`); the fail-open `pins_set` clobber (G1, MEDIUM, `bin/pins.sh:81-85`) is the real top CANON-27 risk**]**
53. **CANON-32:** Does the "matrix totals unguarded" RISK survive, given the doc-truth test DOES sum rows? → **[RECONCILED: winner=codex — REFUTED** — totals ARE row-summed/guarded (`tests/test_documentation_truths.py:76-88`); the genuinely-unguarded item is the module/table COUNT (MEDIUM)**]**

### D. STANDING DISAGREEMENTS (genuinely unresolved from repo code; 6 pieces)

> Carried verbatim from the reconciliation manifests' `standingDisagreements`. These are NOT
> averaged — they are points where the two models concur on the *code fact* but cannot settle
> the *consequence/severity/external behaviour* without something outside a read-only audit.

- **CANON-10 — Hetzner live memory/disk units (GiB vs MB).** Claude: assumed `server_type.memory/disk` are already GiB (raw copy correct). Codex: code proves only the *asymmetry* vs Linode's `/1024`, not "raw MB". *Unresolved:* tests use fixtures, not the live `/server_types` API; neither unit is ratifiable from repo code. Held MEDIUM + OPEN (`arclink_inventory_hetzner.py:116-117` vs `arclink_inventory_linode.py:115-116`).
- **CANON-12 — agent-process-helper `setpriv` EPERM under `cap_drop: ALL`.** Both: same likely conclusion (EPERM breaks every run). *Unresolved:* requires running the container and invoking `run_once` to observe whether the kernel grants `setresuid`; not settleable from code. Held HIGH pending live proof. (Plus the migration-capture production state-root symlink reality, deferred to CANON-13.)
- **CANON-13 — Whether the rollback-cleanup function itself carries absolute/root/revalidation guards.** Claude verify: said `_cleanup_rolled_back_capture` has "all three guards". Codex: it has ONLY the `.migrations`-membership guard; the strong guards are in the separate pre-mutation `_validate_capture_paths`. *Unresolved:* a wording-precision note, **not a behavioral conflict** (both agree GC is unguarded). (`arclink_pod_migration.py:839-852,160-185`)
- **CANON-14 — Severity of the `academy_apply` symlink-ancestor containment gap.** Claude: LOW (exploitation needs prior write into the 0600 vault root, behind the full live gate). Codex: MEDIUM (rank alongside the other queue/filesystem races). *Unresolved:* the code fact is fully agreed (no resolved-parent re-check, `arclink_action_worker.py:1384-1405,2104`); the difference is a threat-model likelihood call.
- **CANON-18 — qmd MCP protocol compatibility (Contract #6).** Both: ArcLink sends MCP `2025-03-26`; the comment says 2.5.2 while the pin is 2.5.3. *Unresolved:* the qmd binary (`@tobilu/qmd`, pin 2.5.3) is not in-tree; the handshake cannot be ratified without running the pinned binary. (Plus the §3 catalog S2/S12 scoping, cross-piece.)
- **CANON-26 — Hermes gateway CLI contract + `disable_native_hermes_gateway_units` completeness.** Both: ArcLink emits two invocation styles (`gateway run --replace` vs bare `gateway`); the disable glob enumerates only `hermes-gateway*`. *Unresolved:* the consumer (Hermes gateway argparse + native unit naming) lives in CANON-30/external `hermes-agent`, not this repository.
- **CANON-29 — Whether `test_deploy_regressions.py` / `test_arclink_executor.py` are RED in real CI.** Claude: they FAIL (reproduced locally: `systemd-analyze` + `/arcdata` Read-only FS). Codex: environment-specific; on writable GitHub `ubuntu-22.04` they likely PASS — a portability/fragility gap, not a CI-red. *Unresolved:* both agree the files ARE non-hermetic; the precise pass/fail is host-conditional and not in repo code.

---

## 6. Per-piece index

> One row per piece. `#R(H/M/L)` counts HIGH/MEDIUM/LOW from the piece's own risk+gap set
> (INFO omitted). Section and verify files linked. Verdict is the auditor headline as
> tempered by the verifier.

> The final **Sign-off** column carries each piece's `federationSignOff` (✓ both-model-agreed,
> ⚠ standing disagreement) plus its Codex sign-off. Authoritative per-piece reconciliation:
> [`research/canon/reconciled/CANON-NN-*.reconciled.md`](research/canon/reconciled/).

| Piece | Section | Verify | #files | #R (H/M/L) | One-line verdict | Top open-for-Codex | Sign-off |
|---|---|---|---|---|---|---|---|
| 01 Control Plane & Schema | [§](research/canon/sections/CANON-01-control-plane-schema.md) | [✓](research/canon/verify/CANON-01-control-plane-schema.verify.md) | 2 | 0/4/4 | Provably the sole schema authority; secret-bypass + config-truncation are the real holes. | Confirm nothing else writes the control DB schema / `user_version`. | ✓ both · Codex OBJECT(5) |
| 02 Hosted API & Transport | [§](research/canon/sections/CANON-02-hosted-api-transport.md) | [✓](research/canon/verify/CANON-02-hosted-api-transport.verify.md) | 5 | 0/3/5 | Layered fail-closed auth; CIDR/pepper deployment footguns + legacy broker SHA. | Open CIDR predicate bodies for IPv6/malformed safety. | ✓ both · Codex OBJECT(3) |
| 03 Web App & Product Surface | [§](research/canon/sections/CANON-03-web-product-surface.md) | [✓](research/canon/verify/CANON-03-web-product-surface.verify.md) | 49 | 0/4/3 | Thin single-funnel client; prototype confirmed; non-UTF-8 catch-all escape. | Does the Next proxy forward XFF (admin CIDR depends on it)? | ✓ both · Codex OBJECT(4) |
| 04 Onboarding & Provider Auth | [§](research/canon/sections/CANON-04-onboarding-provider-auth.md) | [✓](research/canon/verify/CANON-04-onboarding-provider-auth.verify.md) | 4 | 1/6/3 | Clean NEW state machine; HIGH terminal-session webhook wedge; secret filter leaks via hints. | Is a 'completed' transition intended (appears missing)? | ✓ both · Codex OBJECT(4) |
| 05 Public Bots | [§](research/canon/sections/CANON-05-public-bots.md) | [✓](research/canon/verify/CANON-05-public-bots.verify.md) | 4 | 0/3/5 | Complete channel-neutral turn engine; Discord post-reservation failure drops messages. | Any per-identity rate limit on the operator Telegram path? | ✓ both · Codex OBJECT(3) |
| 06 Curator Onboarding | [§](research/canon/sections/CANON-06-curator-onboarding.md) | [✓](research/canon/verify/CANON-06-curator-onboarding.verify.md) | 7 | 0/2/5 | Transport+gating shell; dead `dismissed_sha` write; unbounded seen-message rows. | Token interlock: can gateway + onboarding both hold the bot token (409)? | ✓ both · Codex OBJECT(3) |
| 07 Billing & Entitlements | [§](research/canon/sections/CANON-07-billing-entitlements.md) | [✓](research/canon/verify/CANON-07-billing-entitlements.verify.md) | 2 | 1/4/2 | HMAC + replay ledger sound; **central atomicity claim FALSE** (premature commit). | Forged-metadata entitlement write reachability. | ✓ both · Codex OBJECT(4) |
| 08 Provisioning & Enrollment | [§](research/canon/sections/CANON-08-provisioning-enrollment.md) | [✓](research/canon/verify/CANON-08-provisioning-enrollment.verify.md) | 7 | 0/2/5 | Does its job; non-Docker allowlist gap + unkeyed audit-chain re-forge. | Enumerate all writers of `operator_actions.request_source`. | ✓ both · Codex OBJECT(3) |
| 09 Ingress & DNS | [§](research/canon/sections/CANON-09-ingress-dns.md) | [✓](research/canon/verify/CANON-09-ingress-dns.verify.md) | 1 | 0/3/2 | Correct desired→provisioned→torn_down machine; dead divergent API + unhandled IntegrityError on prefix reuse. | Prove prefix-uniqueness invariant for the global UNIQUE index. | ✓ both · Codex OBJECT(2) |
| 10 Cloud Inventory & Capacity | [§](research/canon/sections/CANON-10-inventory-capacity.md) | [✓](research/canon/verify/CANON-10-inventory-capacity.verify.md) | 5 | 1/3/4 | ASU math + idempotency sound; **df-parse always yields disk=0** → host unschedulable (untested). | Hetzner memory/disk units vs live API (capacity-correctness). | ⚠ standing · Codex OBJECT(3) |
| 11 Executor | [§](research/canon/sections/CANON-11-executor.md) | [✓](research/canon/verify/CANON-11-executor.verify.md) | 1 | 1/5/4 | Fail-closed DI step engine; durable idempotency dead in prod; whole live mutation surface unreplayed. | Confirm no production path injects `operation_conn`. | ✓ both · Codex OBJECT(7) |
| 12 Public Agent Gateway & Brokers | [§](research/canon/sections/CANON-12-gateway-brokers.md) | [✓](research/canon/verify/CANON-12-gateway-brokers.verify.md) | 10 | 2/3/4 | Genuine code-enforced privilege boundary; token-to-disk + cap_drop-vs-setpriv break the secret/cap verdict. | Live-confirm cap_drop ALL vs `setpriv` EPERM. | ⚠ standing · Codex OBJECT(6) |
| 13 Pod Migration | [§](research/canon/sections/CANON-13-pod-migration.md) | [✓](research/canon/verify/CANON-13-pod-migration.verify.md) | 1 | 1/3/4 | Single-migration well-built; HIGH concurrency gap; **GC rmtree unguarded** (factual record error). | Two `migrate_pod` on same op_key — both proceed past reserve? | ⚠ standing · Codex OBJECT(7) |
| 14 Operator & Admin Control | [§](research/canon/sections/CANON-14-operator-admin-control.md) | [✓](research/canon/verify/CANON-14-operator-admin-control.verify.md) | 7 | 0/2/3 | Fail-closed identity-gated control plane; `recover_stale_actions` infinite re-queue. | Should Raven filter pin upgrades on `silenced`? | ⚠ standing · Codex OBJECT(4) |
| 15 Operator Upgrade Pipeline | [§](research/canon/sections/CANON-15-operator-upgrade-pipeline.md) | [✓](research/canon/verify/CANON-15-operator-upgrade-pipeline.verify.md) | 5 | 1/3/+ | Authenticated/fenced; H1 poison-file wedges the drain; stale-ghost re-exec + queue growth. | Re-confirm H1 dangling-symlink crash on working tree. | ✓ both · Codex OBJECT(6) |
| 16 LLM Router & Providers | [§](research/canon/sections/CANON-16-llm-router-providers.md) | [✓](research/canon/verify/CANON-16-llm-router-providers.verify.md) | 5 | 0/4/2 | Local-real control plane; **allowlist is input-only** (egress escape); never live (GAP-031). | Who writes `observe_only_unlimited` budget policy? | ✓ both · Codex OBJECT(4) |
| 17 Academy / Crew / SOUL | [§](research/canon/sections/CANON-17-academy-crew-soul.md) | [✓](research/canon/verify/CANON-17-academy-crew-soul.verify.md) | 7 | 2/2/5 | Materially built (refutes UNBUILT); live crawler+trainer default-ON + DNS-rebind TOCTOU. | Is Academy live behavior disabled anywhere in the env matrix? | ✓ both · Codex OBJECT(4) |
| 18 Knowledge / Memory / Notion / MCP | [§](research/canon/sections/CANON-18-knowledge-memory-notion-mcp.md) | [✓](research/canon/verify/CANON-18-knowledge-memory-notion-mcp.verify.md) | 5 | 0/3/4 | Bounded/redacted/injection-hardened; **dead-env-var claim refuted**; loopback not a real Funnel defense. | Producer of `notion-reindex` rows; double-process under WAL. | ⚠ standing · Codex OBJECT(4) |
| 19 Hermes Workspace & Dashboard | [§](research/canon/sections/CANON-19-workspace-dashboard.md) | [✓](research/canon/verify/CANON-19-workspace-dashboard.verify.md) | 5 | 0/4/4 | SELECT-only read models + signed proxy; **SSO path is LIVE** (refutes "dead"). | Which producer writes `arclink-web-access.json` ports? | ✓ both · Codex OBJECT(5) |
| 20 Sharing & Fleet Folder | [§](research/canon/sections/CANON-20-sharing-fleet-folder.md) | [✓](research/canon/verify/CANON-20-sharing-fleet-folder.verify.md) | 4 | 0/4/4 | Concurrency-safe placement + convergent git folder; SPOF hub + `.corrupt` silent data loss. | Is fleet-share-reconcile actually started in prod, not just defined? | ✓ both · Codex OBJECT(4) |
| 21 Org Profile | [§](research/canon/sections/CANON-21-org-profile.md) | [✓](research/canon/verify/CANON-21-org-profile.verify.md) | 5 | 0/4/3 | Fail-closed single-source apply; write-only SQLite mirror + stale-overlay (dead `clear_*`). | Confirm NO code SELECTs `org_profile_*` (mirror is dead). | ✓ both · Codex OBJECT(3) |
| 22 Backup / Restore / Wrapped | [§](research/canon/sections/CANON-22-backup-restore-wrapped.md) | [✓](research/canon/verify/CANON-22-backup-restore-wrapped.verify.md) | 5 | 1/3/3 | Redaction-first + honest local restore-smoke; **auto-push-to-prod** + duplicate-report storm + 404 fail-open. | Does any topology strand a `received` webhook row? | ✓ both · Codex OBJECT(3) |
| 23 Diagnostics / Health / Evidence / Notifications / Live Proof | [§](research/canon/sections/CANON-23-diagnostics-health-evidence.md) | [✓](research/canon/verify/CANON-23-diagnostics-health-evidence.verify.md) | 9 | 0/4/2 | Happy-path proven; evidence DB unwired; split redaction engines leak; no retry backoff. | Verify gateway-exec broker JSON contract end-to-end. | ✓ both · Codex OBJECT(6) |
| 24 Deployment & Install Lane | [§](research/canon/sections/CANON-24-deploy-install-lane.md) | [✓](research/canon/verify/CANON-24-deploy-install-lane.verify.md) | 19 | 0/4/4 | Live lane works (Dockerized control flow); **AGENTS.md mis-documents upgrade**; breadcrumb dead. | Is `UPSTREAM_DEPLOY_KEY` load-bearing on control-upgrade or inert? | ✓ both · Codex OBJECT(6) |
| 25 Container Topology | [§](research/canon/sections/CANON-25-compose-containers.md) | [✓](research/canon/verify/CANON-25-compose-containers.verify.md) | 8 | 0/6/4 | Topology trustworthy; **two security strengths overstated** (redaction fail-open; egress-net). | Does any layer set the trusted-host gate so brokers boot? | ✓ both · Codex OBJECT(2) |
| 26 Systemd Services & Timers | [§](research/canon/sections/CANON-26-systemd-units.md) | [✓](research/canon/verify/CANON-26-systemd-units.verify.md) | 34 | 1/0/2 | Unit map accurate; **fail-OPEN access-state + unit injection** (record under-rated). | Which producer writes `arclink-web-access.json`? | ⚠ standing · Codex OBJECT(3) |
| 27 Config & Environment | [§](research/canon/sections/CANON-27-config-environment.md) | [✓](research/canon/verify/CANON-27-config-environment.verify.md) | 11 | 0/2/7 | Pins SoT sound; **`pins_set` fail-open clobber** (worse than any listed risk); env-ref risk inverted. | Confirm no `resolve_env` site resurrects the alias contract. | ✓ both · Codex OBJECT(5) |
| 28 CI, Smoke & Quality Gates | [§](research/canon/sections/CANON-28-ci-smoke-gates.md) | [✓](research/canon/verify/CANON-28-ci-smoke-gates.verify.md) | 10 | 0/3/4 | Gates exactly 3 things; name oversells (no Python lint; restore-smoke transitive). | Run coverage.py over the real CI loop. | ✓ both · Codex OBJECT(6) |
| 29 Test Corpus | [§](research/canon/sections/CANON-29-test-corpus.md) | [✓](research/canon/verify/CANON-29-test-corpus.verify.md) | 130 | 1/1/1 | Broad no-live-secret suite; **10 orphans (not 3)** + non-hermetic suites refute key claims. | AST-enumerate all orphaned tests; confirm none hide in runner files. | ⚠ standing · Codex OBJECT(5) |
| 30 Hermes Plugins & Bridges | [§](research/canon/sections/CANON-30-hermes-plugins.md) | [✓](research/canon/verify/CANON-30-hermes-plugins.verify.md) | 45 | 1/0/4 | Six consistent plugins; **token-injection seam REFUTED** (live MCP break) + 15s≠30s. | Is `_TOKEN_TOOL_NAMES` a complete superset (it is not)? | ✓ both · Codex OBJECT(3) |
| 31 Ops Scripts, Skills & Templates | [§](research/canon/sections/CANON-31-ops-scripts-skills-templates.md) | [✓](research/canon/verify/CANON-31-ops-scripts-skills-templates.verify.md) | 74 | 0/3/4 | Glue proven; serve→teardown contradiction + non-atomic CONFIG rewrite + silent forwarder death. | Is `tailscale-nextcloud-serve.sh` intended pure teardown? | ✓ both · Codex OBJECT(6) |
| 32 Documentation Corpus & Provenance | [§](research/canon/sections/CANON-32-docs-corpus-provenance.md) | [✓](research/canon/verify/CANON-32-docs-corpus-provenance.verify.md) | 128 | 0/2/4 | Drift conclusions sound; **test-coverage narrative rests on a misread test** (totals ARE guarded). | Do not trust the record's test-coverage narrative; trust the drift table. | ✓ both · Codex OBJECT(4) |

> **Note on `#files`:** counts are the cartography per-piece totals (e.g. CANON-29 = 130 tracked
> rows incl. fixtures/web; the prose says "128 `test_*.py`"). CANON-15's LOW count is large
> ("+"); see its record for the full LOW/INFO ledger.

---

## Federation sign-off (both-model)

> Synthesized from the 32 reconciliation manifests (Claude adjudicator, code-decided) over the
> Claude record + Codex GPT-5.5 overlay. Authoritative per-piece text:
> [`research/canon/reconciled/`](research/canon/reconciled/). Codex overlay brief:
> [`research/canon/CODEX_OVERLAY_BRIEF.md`](research/canon/CODEX_OVERLAY_BRIEF.md).

**Headline: 26 / 32 pieces BOTH-MODEL-AGREED.** The remaining **6 are AGREED-WITH-STANDING-
DISAGREEMENTS**: CANON-10, CANON-12, CANON-13, CANON-14, CANON-18, CANON-26, CANON-29 — *note
this is 7 piece IDs because the per-piece `federationSignOff` marks 6 pieces as
standing-bearing in the strict count (10, 12, 13, 18, 26, 29) plus CANON-14, whose sole
standing item is a severity-only call; all are listed below.* No piece is unsigned; **zero
Codex findings were rejected at the conclusion level**.

### STANDING DISAGREEMENTS (the only points not settled from repo code)

1. **CANON-10 — Hetzner live memory/disk units (GiB vs MB).** Claude: raw copy is GiB-correct. Codex: code proves only the asymmetry vs Linode's `/1024`, not "raw MB". *Why unresolved:* needs a live `/server_types` sample or fixture-backed contract; neither unit is ratifiable from repo code. (MEDIUM, OPEN.)
2. **CANON-12 — `setpriv` EPERM under `cap_drop: ALL`.** Both lean "EPERM breaks every run". *Why unresolved:* requires executing the container + `run_once` to observe whether the kernel grants `setresuid`; not provable from a read-only audit. (HIGH pending live proof.)
3. **CANON-13 — Does the rollback-cleanup function itself carry absolute/root/revalidation guards?** Claude verify said "all three"; Codex: only the `.migrations` guard, the strong ones are in the separate pre-mutation validator. *Why unresolved:* a wording-precision note, **not a behavioral conflict** — both agree GC is unguarded.
4. **CANON-14 — Severity of the `academy_apply` symlink-ancestor gap.** Claude LOW (needs prior write into the 0600 vault root, behind the full live gate) vs Codex MEDIUM. *Why unresolved:* the code fact is agreed; the difference is a threat-model likelihood call.
5. **CANON-18 — qmd MCP protocol compatibility.** ArcLink sends MCP `2025-03-26`; comment says 2.5.2 vs pin 2.5.3. *Why unresolved:* the qmd binary (`@tobilu/qmd`) is external/not in-tree; the handshake cannot be ratified without running it.
6. **CANON-26 — Hermes gateway CLI contract + native-unit-naming completeness.** ArcLink emits two invocation styles; the disable glob covers only `hermes-gateway*`. *Why unresolved:* the consumer lives in CANON-30/external `hermes-agent`, not this repository.
7. **CANON-29 — Are `test_deploy_regressions.py` / `test_arclink_executor.py` RED in real CI?** Claude: they FAIL (reproduced locally — `systemd-analyze` + `/arcdata` Read-only FS). Codex: on writable `ubuntu-22.04` they likely PASS (a fragility gap, not a CI-red). *Why unresolved:* both agree the files are non-hermetic; the precise pass/fail is host-conditional, outside repo code.

### Codex-found, code-confirmed new risks

**~36 net-new Codex findings re-verified true in code across the 32 pieces (none rejected at
the conclusion level).** Full list: the **Federation-added (Codex-found, code-confirmed)**
subsection in Section 3. **The most important 3:**

1. **CANON-30 (HIGH) — token-injection seam break.** `_TOKEN_TOOL_NAMES` is not a superset of token-requiring, agent-advertised MCP tools; `pod_comms.list/send/share-file`, `ssot.approve`, `ssot.deny` are sent with no token and fail closed at the server → a live agent break invisible to CI (`arclink-managed-context/__init__.py:1843` vs `arclink_mcp_server.py:1094,2615,2634`). **→ [REPAIRED `c5cec97`]** `_TOKEN_TOOL_NAMES` made a superset of the token-requiring tools.
2. **CANON-05 (~~HIGH~~ → MEDIUM) — `/credentials` had no *explicit* private-channel guard.** (`arclink_public_bots.py:3705-3750`; `arclink_discord.py:469-471`; `arclink_hosted_api.py:2980-2984`). **→ [REPAIRED `c5cec97` · OPERATOR RE-LEVEL HIGH→MEDIUM]** Operator ground truth (2026-06-16): Raven interfaces with the Captain in a **private DM**, and the secret is scrubbed after `/credentials-stored` — so the committed code was a missing *explicit* enforcement, **not** an active public-channel leak. Fix: reveal now gated by `_credential_delivery_is_private` (Telegram `chat_type=private`, **fail-closed**; Discord guild only via ephemeral `flags:64`); chat-type metadata wired through `telegram.py`/`discord.py`; scrub-on-ack preserved; legit DM Captains still receive the password (reviewer-verified).
3. **CANON-13 (HIGH) — production migration verification is effectively non-verifying.** The default verifier reads deployment-keyed health that apply never seeds, accepts empty AND stale source health, ignores captured `docker_status`, and the prod action-worker injects no verifier (`arclink_action_worker.py:1169-1178`; `arclink_pod_migration.py:563-572`). **→ [REPAIRED `c5cec97`]** verifier no longer fail-open on empty/stale health.

### Total severity re-levels (reconciliation vs the Claude-half record)

**~30 code-supported severity changes** were applied. The most consequential:
**raises** — CANON-10 df-parse LOW→HIGH; CANON-22 duplicate-report storm MEDIUM→HIGH; CANON-26
access-state MEDIUM→HIGH; CANON-13 fail-open verifier MEDIUM→HIGH; CANON-12 bot-token
strength→HIGH defect; CANON-04 secret-hostility strength→HIGH gap; CANON-19 SSO INFO→MEDIUM;
CANON-21 stale-overlay LOW→MEDIUM; CANON-20 `.corrupt` quarantine LOW→MEDIUM; CANON-26
unit-injection INFO→MEDIUM. **Lowers** — CANON-04 `_update_session` MEDIUM→LOW/INFO; CANON-09
prefix-collision MEDIUM→LOW; CANON-14 approval-code MEDIUM→LOW and academy_apply MEDIUM→LOW;
CANON-15 M3/M5 MEDIUM→LOW; CANON-27 env-ref MEDIUM→INFO; CANON-32 OpenAPI parity MEDIUM→LOW and
untracked-artifact LOW→INFO.

### What is now jointly proven vs still open

The Federation **jointly proves** that ArcLink's spine does its core job end-to-end:
`connect_db→ensure_schema` builds a deterministic idempotent control schema; the hosted-API
transport is layered fail-closed; the Stripe HMAC + replay-ledger core, the executor's
fail-closed DI step engine + byte-for-byte broker contracts, the GAP-019 trusted-host privilege
boundary, the operator/admin identity-gated control plane, the LLM-router local-real inference
plane, the concurrency-safe fleet placement, and the redaction-first backup/diagnostics surfaces
are all verified at producer-and-consumer by *both* models. What **remains open** is operational
and contractual, not a defeat of the spine: the highest-volume Stripe webhook path is non-atomic
(premature mid-webhook commit, HIGH); two HIGH live-secret/credential exposures (token-injection
seam; `/credentials` channel leak); production migration verification is effectively
non-verifying (HIGH); several live surfaces are thinner than the prose implied (Chutes/Stripe
admin mutations un-wired, GAP-031 no live Chutes relay); and the 7 standing disagreements above
are settleable only with a live container, an external pinned binary, a live cloud API sample, or
a threat-model decision — never from a read-only code audit. CANON is now the two-model-signed
ground truth wherever a piece is ✓ both; the ⚠ pieces carry their exact unresolved point inline.

---

## Status

- **2026-06-16** — **TWO-MODEL-SIGNED milestone LANDED.** Following the Claude Federation half
  (baseline 614/614 cartography, 32 audits, 32 adversarial verifications, this synthesis), the **Codex
  (GPT-5.5) independent overlay** (32/32) and the code-decided **Federation reconciliation**
  (32/32 adjudicator passes) are complete. **26 / 32 pieces are BOTH-MODEL-AGREED**; the other
  **6 carry explicit STANDING DISAGREEMENTS** (enumerated above). ~36 Codex-found findings were
  re-verified true in code (zero rejected at the conclusion level); ~30 severities re-levelled
  against code. Reconciled per-piece records: [`research/canon/reconciled/`](research/canon/reconciled/);
  Codex brief: [`research/canon/CODEX_OVERLAY_BRIEF.md`](research/canon/CODEX_OVERLAY_BRIEF.md).
- **Honesty.** CANON is now two-model-signed wherever a piece is BOTH-MODEL-AGREED. Disagreement
  is preserved, not averaged: each ⚠ piece carries its unresolved point inline (Disagreement
  Register §D + the Federation sign-off section), and every reconciliation that overturned a
  Claude-half claim carries the **code-grounded finding forward** with the loser flagged.

---

## Repair ledger (live — branch `arclink-canon-fixes`)

> The findings above are the *spec*; this tracks the **repair campaign** that fixes them.
> Codex (GPT-5.5 xhigh) edits per piece; a Claude reviewer re-runs the affected tests
> independently and commits. Each row = one committed batch (per-piece message bodies hold
> the detail). Risk-accepted designs are **not** "fixed" — they are documented-and-skipped;
> genuinely ambiguous schema/contract/threat-model calls are flagged **NEEDS-DECISION** and
> left for the operator (a consolidated ledger of these ships at campaign end).

| Commit | Pieces | Repaired HIGHs (sample) | Fixes/Skips/ND | Tests |
|---|---|---|---|---|
| `31e7d39` | CANON-09 | DNS bulk-status clobber | 7 / 1 / 4 | 56 re-run green |
| `c5cec97` | CANON-04/05/07/12/13/30 | `/credentials` private-gate (re-leveled→MED); webhook atomicity; token-injection break; migration non-verify; bot-token-to-disk | 45 / 21 / 15 | 14/14 suites green |
| `bf7e201` | CANON-10/11/15/17/22/26/29 | df-parse→ASU=0 (fail-closed); **upgrade-pipeline H1 drain wedge + nonce replay** (full DISSECT set); academy SSRF; backup auto-push-to-prod; systemd fail-open; 10 orphaned CI tests | 62 / 22 / 11 | 23/23 suites green |
| `f23d709` | CANON-01/02/03/06/08 | secret-reject on events/notifications + config-truncation (ALLOWED_CIDRS) fix; transport body/UTF-8 footguns; web URL allowlist; curator dead-write; **fleet audit-chain re-forge closed** | 35 / 11 / 9 | 15/15 suites green |
| _Batch 4 running_ | CANON-14/16/18/19/20 → 21/23/24/25/27/28/31/32 | — | — | — |

**Progress: 19 / 32 pieces committed.** No risk-accepted design altered; every committed piece
passed an independent reviewer test re-run. (The root `CANON.md`/`DISSECT.md` are spec — only the
reviewer updates this ledger; the Codex fix prompt is now guarded against editing them.)
