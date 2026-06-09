# Sovereign Control Node Symphony

This document is the source-grounded dream shape for ArcLink's Sovereign
Control Node path. It describes how the product should feel and operate when
complete, while keeping the current evidence honest. The old Shared Host and
Shared Host Docker public modes are retired; the product trajectory here is the
Sovereign Control Node: one control plane, one operator universe, many isolated
ArcPods.

## Ground Truth Boundary

The current repository already contains the main Control Node spine:

- `./deploy.sh control install` collects product, ingress, Stripe, primary
  inference-provider, public bot, executor, and fleet-worker configuration.
- `python/arclink_hosted_api.py`, `python/arclink_api_auth.py`,
  `python/arclink_dashboard.py`, and `web/` own the public API, sessions,
  dashboard, admin dashboard, and browser control surfaces.
- `web/` is the only production frontend source of truth. The old adjacent
  Vite/Bolt `arclink-frontend/` checkout is not a deploy, build, test, or
  documentation dependency and should stay absent so ArcLink does not split its
  web product between two app roots.
- `python/arclink_public_bots.py`, `python/arclink_telegram.py`, and
  `python/arclink_discord.py` own Captain-facing Raven flows, channel linking,
  selected-agent command surfaces, share approvals, Crew Training, and managed
  upgrade copy.
- `python/arclink_provisioning.py`, `python/arclink_fleet.py`,
  `python/arclink_sovereign_worker.py`, and executor modules own ArcPod
  intent, placement, apply, rollback, teardown, and deployment health.
- `python/arclink_llm_router.py` owns the central inference router contract,
  sanitized usage accounting, budget gates, model allowlists, and provider
  relay.
- Hermes homes are prepared through the ArcLink installer scripts and receive
  ArcLink skills, dashboard plugins, qmd/Notion/SSOT tools, managed context,
  recall stubs, and pinned Hermes docs.

The remaining dream work must not be described as complete until its gap rows
close. The highest-signal open product gaps are:

- `GAP-029`: Operator Raven already queues real, audited, identity- and
  approval-code-gated mutations across **both Telegram and Discord** (Discord can
  now be a secondary operator control surface, not only the primary), but is not
  yet a single full-service chat-native control plane (breadth, unified policy,
  and live proof remain).
- `GAP-030`: Control Node product readiness can still be reached without a
  verified worker-capacity proof.
- `GAP-031`: the router has live-by-default fallback cascade and a metered-but-
  unlimited Operator lane, but not live provider overload proof.
- `GAP-032`: Hermes and component upgrades exist, source-owned dependency
  policy plus `/upgrade_sweep` now guide component pins, and local ArcPod
  rollout planning/materialization exists, but real refresh/apply execution and
  live multi-Pod proof remain.
- `GAP-033`: a local cross-surface polish gate now exists and Telegram Captain
  replies now render their Markdown as real `code` entities (no more literal
  backticks), but live browser/chat/workspace proof is still required before the
  experience is product-real.
- `GAP-034`: Academy scaffolding is substantial, including sticky mode, the
  **live LLM Trainer enabled by default** (fail-closed to deterministic), governed
  source review, weekly crawl observations, real `academy_apply` SOUL/vault/
  memory-seed/approved-skill writes, and authorized apply handoff, but live
  per-lane acquisition/provider synthesis and downstream qmd/memory/skill refresh
  execution proof remain.

**Recent ground truth (2026-06-05 hardening pass).** Several motions that this
document previously listed as "remaining" are now real in source and regression-
tested, and a focused defect sweep closed concrete quirks:

- *Inference is operator-unlimited-but-observed.* The Operator's own Pod carries
  `chutes.budget_policy=observe_only_unlimited`: every inference is still metered
  and recorded (`used_cents`), but the budget boundary returns `budget_status=
  unlimited` and never fails closed, so Operator Raven reasoning can always remedy
  the stack. Install now asks for and persists the default per-Pod monthly budget,
  and the Operator's router key carries the full model allowlist (CSV), not a single
  model.
- *Shared knowledge fans out.* Fleet/Linked shared roots are now qmd-indexed
  collections (searchable through `knowledge.search-and-fetch`), mounted into the
  `qmd-mcp` and `vault-watch` containers, and the vault watcher watches those roots
  so a peer's Fleet pull or a new Linked grant triggers a fast, event-driven qmd
  re-index + memory synthesis instead of waiting for the periodic timer. A changed
  source now overrides the memory-synth failure backoff so an edit is never
  suppressed.
- *Remote dashboards reach the Captain.* Remote ArcPod dashboards are bridged
  through the control tailnet (publish-before-handoff, stale-forward pruning,
  keepalive, port-collision avoidance, remote dashboard secret ownership).
- *Placement reporting is honest.* The provisioning-readiness read model now
  counts eligibility from full host rows, so `image_sync_failed` workers are no
  longer over-counted; image-sync state survives a hostname re-registration; the
  image-sync worker resolver matches the canonical WireGuard/private-mesh
  precedence.
- *Academy review metadata is preserved.* The weekly live-trainer review now
  reports refreshed capsules accurately and no longer clobbers the Trainer's
  engine/live/summary enrichment when a capsule changes.

The remaining open items from that sweep — Telegram operator-gate unification, a
Captain `/share-create` origination command, ArcPod-upgrade command-menu refresh,
tracked nohup tailnet-forward pruning, deferring the Tailscale handoff link until
the control bridge publishes, and TUI/API/docs surface-contract coverage — are
recorded with concrete fix approaches in **Post-Audit Hardening Register** below.

## North Star

ArcLink should feel like a sovereign AI operating system that happens to have a
SaaS-grade front door. The operator installs a Control Node, admits one or more
machines into the fleet, configures provider and billing rails, pairs with
Operator Raven, and then controls the stack through a secure blend of dashboard,
CLI, and chat. Captains enter through Raven or the web, buy or claim an ArcPod,
train or accept their Crew, and operate inside a private Hermes workspace whose
Drive, Code, Terminal, knowledge, memory, sharing, and communication surfaces
all remain in lock step with the installed ArcLink release.

The system should be boringly reliable underneath and mythic on top:

- Operators own the universe: hosts, secrets, fleet, policy, upgrades, backups,
  live proof, emergency repair, and product rollout.
- Captains own their Pods and Crew, not the host.
- Agents act with dense, lore-consistent clarity, but every tool action remains
  grounded in real permissions and auditable state.
- Raven is the guide and control grammar, not a decoration. It should know the
  installed version's actual capabilities and should never leave a Captain or
  Operator guessing where to click or what command to run next.

## Whole-System Traversal

The finished Control Node should be traceable as one continuous loop, not a
pile of adjacent features:

1. The Operator installs the Control Node, configures product, ingress,
   provider, Stripe, public bot, and Operator Raven settings, then admits at
   least one worker machine.
2. The Control Node proves whether it is ready to provision ArcPods. If it is
   not ready, every surface says "control plane up, provisioning blocked" with
   the same reason and next repair.
3. A Captain enters through website, Telegram, or Discord. Raven or the web
   collects the minimum setup answers, explains plan/provider state, and opens
   checkout or entitlement recovery.
4. Stripe webhook state activates entitlement, or failed/cancelled/refund
   states block provisioning with clear Captain and Operator copy.
5. Provisioning creates deployment intent, resolves secret references, selects
   an eligible worker, applies the ArcPod, records health, and creates the
   owner-scoped credential handoff.
6. The Captain lands in Raven and dashboard with one active Agent, one clear
   home channel, Drive/Code/Terminal, knowledge rails, provider/budget state,
   backup state, share inbox, and recovery links.
7. The Agent receives the release-aligned Hermes runtime, ArcLink skills,
   plugins, docs, SOUL/context, memory stubs, qmd/Notion/SSOT tool recipes, and
   channel commands.
8. Day-two work flows through Raven, Hermes dashboard, MCP tools, and browser
   dashboard without losing role, permission, budget, or audit context.
9. Operator Raven, admin dashboard, CLI, diagnostics, live proof, and evidence
   rails show the same system truth.
10. Upgrades, backups, restore, incident repair, share revocation, provider
    failover, and teardown all preserve state by default and leave redacted
    evidence of what happened.

Every step should have a local source owner, a local regression or dry-run
proof where possible, and a named live proof gate where external systems are
required. If any step cannot say what surface owns it, what state it reads, what
state it writes, and how it fails closed, the symphony is not complete.

## Installation And Machine Admission

The complete Control Node install story should be:

1. The operator picks a machine for the Control Node and runs
   `./deploy.sh control install`, or starts `./deploy.sh` and chooses
   Sovereign Control Node from the first menu.
2. The installer asks for deployment style: single-machine, Hetzner fleet, or
   Akamai Linode fleet. The answer chooses sane defaults for the executor and
   worker-registration flow.
3. The installer asks for ingress: domain mode or Tailscale mode. Domain mode
   collects Cloudflare DNS inputs; Tailscale mode collects the Funnel/DNS shape
   and avoids Cloudflare credentials.
4. The installer collects product ports, CORS/cookie scope, Stripe price IDs,
   Stripe secrets, primary provider key, public Telegram/Discord bot
   credentials, and Operator Raven channel intent.
5. The installer must register at least one viable worker before the product is
   called ready to provision. In single-machine mode, this can be the control
   machine itself through localhost/hostname plus a generated fleet SSH key. In
   remote-fleet mode, it can be a manually registered worker or a provider
   worker admitted through inventory.
6. The installer writes private runtime config under `arclink-priv/`, builds
   and starts the Control Node Docker stack, registers public bot actions when
   credentials exist, records release state, prints reachable ports/URLs, and
   runs control health.
7. The final install screen should say one of two things plainly: "ready to
   provision ArcPods" with worker capacity and proof evidence, or "control
   plane is up, but ArcPod provisioning is blocked until a worker is admitted."

Current source supports most of this. Workerless interactive installs now stop
or continue only as control-plane-only with ArcPod provisioning disabled, a
remote worker smoke pass re-enables the provisioner, and install/reconfigure/
worker registration print a provisioning readiness summary. Admin/dashboard,
scale operations, Operator Raven, and the admin web page now share the same
local readiness state for control-plane-only, blocked, pending-SSH, and
ready-to-provision cases. The remaining flaw is live proof: `GAP-030` still
requires `PG-FLEET`/`PG-PROVISION` evidence for the chosen worker path before
ArcLink can claim real worker readiness.

## Operator Raven And Control

Operator Raven should become the chat-native operating console for the entire
Sovereign Control Node. The operator should be asked during install whether
Telegram, Discord, both, or TUI-only should be enabled, then should choose a
primary response channel. Both chat surfaces can exist at once; the primary
channel decides where proactive responses and confirmations go unless a command
arrived from an explicitly allowed secondary channel.

The full Operator Raven surface should cover:

- System status: control health, web/API status, bot webhook state, Stripe
  webhook state, provider/router health, fleet capacity, active incidents,
  failed jobs, failed deployments, and live proof status.
- Fleet: list workers, admit local machine, register remote host, rotate fleet
  SSH key, probe, drain, un-drain, remove, show capacity slots, and explain why
  a placement was rejected.
- Users and Captains: search account, view entitlement state, resend Raven
  handoff, retry channel contact, suspend/restore within policy, inspect
  deployment status, trigger safe repair, and queue backup/restore actions.
- Pods: create/apply/repair/rollback/teardown within entitlement and policy,
  retrieve one-time credential handoff state without revealing secrets in chat,
  and open dashboard/admin links.
- Billing/provider: inspect plan state, failed payment state, refuel credits,
  router budgets, provider account state, and model/provider outage state.
- Upgrades: run Control Node upgrade, component pin checks, Hermes runtime
  upgrades, ArcPod rolling updates, command-menu refresh, release-state proof,
  and health/smoke evidence from a single guided command.
- Knowledge/Notion/SSOT: show Notion health, qmd freshness, memory synthesis
  backlog, pending SSOT approvals, and safe write status.
- Security: show active sessions, admin owner status, channel bindings,
  operator allowlists, CSRF/live proof gates, and trusted-host residual risk
  acknowledgements.

Operator Raven must be powerful but fenced:

- Only the configured operator identity/channel may execute operator actions.
- Dangerous actions require structured confirmation, reason capture, audit row,
  and replay-resistant nonce or policy-equivalent channel authority.
- Secrets are never printed. Raven can report that a credential exists, is
  missing, is stale, or needs rotation, but not the value.
- Natural-language requests may plan and queue actions, but the final execution
  must resolve to typed internal commands with allowlisted parameters.
- Operator Hermes may be adjacent to Raven for reasoning and diagnosis, but it
  must cross into system mutation only through the same audited broker/action
  rails as dashboards and CLIs.

Current source already does more than a read-only preview.
`arclink_operator_raven.py` ships a real-but-fenced operator command layer with
a broad read surface (`status`, `agents`, `fleet_list`, `worker_probe` dry-run,
`user_lookup`, `academy_status`, `academy_roster`, `upgrade_check`,
`upgrade_policy`, `action_status`, `billing_status`, `backup_status`,
`workspace_status`) and a real mutation layer. The mutating
commands (`pod_repair`, `rollout`, `host_upgrade`, `pin_upgrade`,
`upgrade_sweep`, `fleet_drain`, `fleet_resume`, the `MUTATING_COMMANDS` set)
follow a four-mode contract: a `--dry-run` preview changes nothing; a real run
with no operator actor fails closed; a real run with a proven operator actor
but no `confirm`/approval code fails closed; a real run with actor plus
confirmation queues a real, audited intent or applies a modeled local
fleet-state mutation. `pod_repair` and `rollout` queue into
`arclink_action_intents` (drained by `arclink_action_worker.py`);
`host_upgrade`, detector-token `pin_upgrade`, and `upgrade_sweep` queue into
`operator_actions` (drained by the enrollment-provisioner root maintenance
loop). `billing_status`, `backup_status`, and `workspace_status` are read-model
summaries only; they do not call Stripe, providers, backup remotes, Docker,
SSH, or Agent files. `/upgrade_policy [component]` is read-only explanatory policy.
`/pin_upgrade <component>` resolves an active detector payload token with
concrete target pins instead of queueing a bare component name, and
`/upgrade_sweep` queues pending stateless detector payloads while requiring
`--include-stateful` for Postgres, Redis, and Nextcloud maintenance windows.
`/fleet_drain` and `/fleet_resume` mutate placement eligibility only; they do
not SSH into workers, stop services, change firewalls, or touch port 22 from
chat, and draining the last eligible worker requires `--force`. The second
confirmation can be the literal `confirm` token, or the configured operator
approval code (`ARCLINK_OPERATOR_TELEGRAM_APPROVAL_CODE`/
`ARCLINK_OPERATOR_APPROVAL_CODE`, constant-time compare) on the originating
channel. The operator also gets exactly one in-stack Hermes agent
(`arclink_operator_agent.py`, one-agent invariant, `control-stack` runtime)
with a free-form chat bridge that routes operator messages to that Hermes
through the `public-agent-turn` worker. Live mutation is still gated by
`ARCLINK_EXECUTOR_ADAPTER` (`fake` records only) and the per-action proof gates
(`PG-PROVISION`, `PG-INGRESS`, `PG-UPGRADE`/`PG-HERMES`, `PG-PROVIDER`,
`PG-STRIPE`, `PG-BACKUP`).

The dual-channel intent is now real on both adapters. The Telegram operator
surface activates when `telegram` is in the operator channel set
(`ARCLINK_CURATOR_CHANNELS`), and the Discord operator surface now activates when
`discord` is in that set too — not only when Discord is the *primary* response
channel — so an Operator can run, e.g., Telegram primary + Discord secondary at
once. Discord-as-secondary keys its operator channel off
`ARCLINK_OPERATOR_DISCORD_CHANNEL_ID` and stays fenced by the existing Discord
user/role allowlist (`ARCLINK_OPERATOR_DISCORD_USER_IDS`/`_ROLE_IDS`), which fails
closed for guild channels with no allowlist. Each adapter replies on the channel a
command arrived on, while `OPERATOR_NOTIFY_CHANNEL_PLATFORM` (the primary) governs
proactive/notification responses. What remains under `GAP-029` is breadth (fleet
admission/rotation, user suspend/restore, billing refuel from chat), one
unified Raven/action policy that fully reconciles the long-poll and webhook
Telegram operator gates, and authorized live proof — not a "read-only" limitation.

## Admin Dashboard, API, And CLI Control

Operator Raven is not meant to replace every other control surface. It should
stand beside the admin dashboard and CLI as the fast conversational layer over
the same typed actions.

The finished control stack should behave like this:

- The admin dashboard is the visual authority for fleet, deployments,
  entitlements, provider state, action queues, audits, incidents, proof status,
  and dangerous confirmations that are better reviewed on a larger screen.
- The hosted API owns session, CSRF, admin identity, user identity,
  rate-limited actions, dashboard reads, deployment reads, credential handoffs,
  share broker routes, and admin action submission.
- The CLI remains the explicit operator escape hatch for install, reconfigure,
  health, backup, reset, proof, diagnostics, and controlled maintenance.
- Operator Raven may request, explain, and queue the same typed actions, but it
  must not invent a separate mutation path or bypass dashboard/API/CLI audit.
- Read-only status should be available everywhere. Mutating actions should
  converge on one action model with actor, reason, scope, nonce/confirmation,
  redaction, result, and rollback/repair guidance.
- The browser dashboard, CLI, and Raven should agree on whether a job is
  pending, running, failed, blocked by policy, blocked by proof, or complete.

Current source has hosted API/admin/dashboard/action-worker foundations plus a
shared Operator Raven command surface that already queues the same typed actions
(via `queue_arclink_admin_action` into `arclink_action_intents` and
`request_operator_action` into `operator_actions`), local readiness surfaces, and
a cross-surface copy contract. The remaining product layer is broader
policy-backed Operator Raven mutation and authorized live proof that chat,
browser, workspace, and upgrade surfaces render and execute correctly. That
work remains under `GAP-029`, `GAP-030`, `GAP-032`, and `GAP-033`.

## Public Web, Account, And Checkout

The public web path should be first-class, not merely a marketing wrapper over
Raven. A Captain should be able to discover ArcLink, understand the current
offer, start onboarding, pay, recover, and reach their Pod from the browser.

The complete web/account story is:

- The website explains the current plans, provider budget/refuel model, Raven
  surfaces, ArcPod isolation, and proof-gated limitations without overclaiming.
- The Next.js `web/` app is the single web source for marketing, onboarding,
  checkout status, login, Captain dashboard, admin dashboard, policy pages, and
  Academy Observatory. No parallel frontend app should own product copy or
  browser routes.
- Onboarding collects the minimum product answers and creates a claimable
  session that cannot be hijacked without the required proof token.
- Checkout, cancellation, success, portal, failed payment, refund/cancel, and
  refuel all resolve into entitlement state before provisioning can continue.
- Returning users can sign in, view deployments, provider/budget state,
  billing/refuel state, Raven/channel state, backup state, share inbox, and
  credential handoff state.
- Admin login ignores client-asserted MFA, rate limits sensitive endpoints, and
  keeps exactly-one-operator/admin-owner expectations visible.
- Browser storage and proof tokens should not become silent security claims.
  If stronger server-bound proof is desired later, it should become an explicit
  design row rather than an implied promise.

Local API/web coverage already proves many of these contracts. Live Stripe,
bot, provider, dashboard, and production proof still belong to `PG-STRIPE`,
`PG-BOTS`, `PG-PROVIDER`, `PG-HERMES`, and `PG-PROD`.

## Captains And Public Raven

Captains should be able to begin on the web, Telegram, or Discord and never
feel the machinery underneath. Raven should greet them, collect the minimum
needed setup answers, guide checkout or entitlement recovery, pair channels,
launch Crew Training when desired, and hand them to their Agent and dashboard.

The public Raven contract is:

- Telegram and Discord are both valid first-contact surfaces.
- A Captain can link another channel with a pairing code and confirm the link.
- A Captain can select the active Agent for a channel.
- Telegram public chats use a Raven control command such as `/raven` when an
  active Agent owns the bare slash menu.
- Discord uses application commands and the `/agent` style where per-chat slash
  menu replacement is not available.
- Multi-step flows must always have a cancel path and should prefer buttons,
  choices, and concise prompts over free-form typing.
- Raven should explain capability in the installed version, not in imaginary
  future terms. If live proof or a provider credential is missing, it should say
  what is blocked and what the next real action is.

The current Captain side is comparatively strong: channel linking, Crew
Training, share approvals, selected-agent handling, active Telegram command
scope, and unmanaged-upgrade refusal are all represented in source and tests.
The remaining live work is proof-gated under `PG-BOTS`, `PG-HERMES`, and the
sharing gaps already in `GAPS.md`.

## Sharing

Sharing should feel as direct as shared folders in a familiar drive product,
but with stricter ArcPod boundaries. Captains should be able to share folders,
files, vault areas, and selected workspace content from Raven, Drive, Code, and
agent tool calls.

The complete sharing shape is:

- A Captain requests a share from Drive, Code, Raven, or an agent tool.
- The request records owner, recipient, path, mode, scope, expiration, and
  audit metadata.
- The owner receives a clear approve/deny prompt on Raven, dashboard, or both.
- The recipient sees a pending or accepted state in dashboard and Raven.
- Shared roots appear as Linked resources in Drive and Code.
- Linked roots allow writes inside accepted Drive/Code shared folders while
  keeping git mutations blocked from Linked.
- Copy/duplicate into owned roots is allowed and clearly labeled.
- Resharing a Linked root is refused unless a future delegation policy exists.
- A Captain's own fleet shares one writable **Fleet** folder across every Agent,
  with multi-writer convergence and conflict surfacing rather than silent loss.
- Broken notification delivery should not silently strand the share; dashboard
  inbox and retry notification rails should keep the request recoverable.

Current source has the local broker/plugin/API contracts, plus the **fleet
shared folder** (added 2026-05-29, `arclink_fleet_share.py` +
`arclink_fleet_shares`/`arclink_fleet_share_members`). The fleet folder is a
real git-sync engine: a Captain-scoped *bare hub* repo
(`/arcdata/captains/<user>/fleet-shared.git`, durable independent of any single
Agent) plus a per-Agent read-write working clone that the Drive/Code **Fleet**
root surfaces. Each sync pass commits local edits, runs `git pull --rebase`, and
pushes, so every machine converges; unresolvable rebases are surfaced as conflicts
(never clobbered) and a corrupt working copy is quarantined and re-cloned. The
per-Agent `fleet-share-sync` job is rendered into the ArcPod for the in-pod git
sync, while the control-node `fleet-share-reconcile` compose job runs DB-only
membership convergence (`reconcile --all`, every 120s) — enrolling newly-active
agents and deregistering torn-down ones without touching the hub. Today Raven is the share **approval/accept** surface
(`/share-approve`, `/share-deny`, `/share-accept`, `/share-claim`); share
**origination** (minting a grant for a Drive/Code folder) is reachable from the
Drive/Code plugins, the web dashboard, and the MCP `_create_agent_share_request`
tool, but not yet from a Raven command — the planned `/share-create` origination
command is in the Post-Audit Hardening Register. Live
browser/bot proof, no-channel behavior, and remote
(`ssh`/`https`) hub transport remain tracked under `GAP-014`, `GAP-015`, and
`GAP-016`.

## Cross-Surface Experience Standard

ArcLink should not output clunky blocks of machine text. Telegram, Discord,
dashboard, PWA, Hermes dashboard plugins, TUI, and CLI should share a practical
style grammar:

- Short headers, dense payloads, and clear next actions.
- Buttons or slash commands where the platform supports them.
- Markdown that reads well on Telegram and Discord without layout tricks.
- No secret values, no raw tracebacks to Captains, and no giant unstructured
  logs unless the Operator explicitly requests a redacted diagnostic bundle.
- Errors should say what failed, what is safe, what is blocked, and what Raven
  can do next.
- Captain copy should stay in the ArcLink lore voice without sacrificing ground
  truth.
- Operator copy should be precise, auditable, and fast to scan.

Current source now has a local enforced finish gate:
`python/arclink_surface_contract.py` and
`tests/test_arclink_surface_contract.py` check representative Captain Raven,
Operator Raven, dashboard readiness, product surface, Drive/Code/Terminal
plugin status, and CLI readiness copy for audience vocabulary, blocked-state
next actions, proof-gate honesty, chat markdown balance, secret redaction, and
raw-traceback refusal. The Telegram render boundary now converts a Raven reply's
single-backtick code spans into real Telegram `code` entities
(`telegram_markdown_to_entities`, applied in `handle_telegram_update` when no
explicit entities are present, and forwarded through both the long-poll and
webhook send paths) — so a Captain on Telegram sees styled code instead of literal
backtick characters, matching how Discord renders the same source string natively.
`GAP-033` remains open for live browser, bot, and workspace proof, and the
surface contract's declared `tui`/`api`/`docs` channels still need real samples
(see Post-Audit Hardening Register).

## Inference And Router Policy

Inference should run through the central ArcLink router wherever ArcLink can
control the boundary. The router should power Captain Agents, Raven flows,
Crew Training, memory synthesis when configured, and Operator reasoning where
safe. It should meter Captains and Pods through entitlement-aware budgets while
letting the Operator remain effectively unlimited but still observable.

The desired router behavior is:

- Each ArcPod receives scoped router credentials, not the central provider key.
- Usage is recorded as sanitized metadata, not raw prompt/completion content.
- Plan budgets, refuel credits, provider state, and router budget state are
  visible in dashboard and Operator Raven.
- Provider `429`, transient overload, or configured outage classes can trigger
  an explicit fallback cascade.
- Provider deployments that support provider-side model fallback should
  encourage a model CSV string such as `model-a,model-b` when the provider can
  choose a fallback internally.
- ArcLink should also own a router-level fallback list so providers and
  failures outside provider-side fallback can retry safely.
- Fallbacks must be bounded, auditable, and visible: the Captain should not be
  confused about model quality changes, and the Operator should know when the
  primary is unhealthy.

The current router supports model policy, usage accounting, limits, provider
relay, model replacements, and auto-promotion. Control Node install now asks
for a default model or provider-side fallback CSV, allowed models,
ArcLink-owned fallback models/status codes, **and the default per-ArcPod monthly
budget in cents** (persisted to config, not only a compose default; 0 means
fail-closed-until-a-per-Pod-budget-is-set). The Operator lane is now explicitly
**metered but unlimited**: `ensure_operator_agent_deployment` stamps the operator
deployment with `chutes.budget_policy=observe_only_unlimited` (preserving any
accumulated `used_cents` across control re-deploys), `evaluate_chutes_deployment_
boundary` recognizes that policy and returns `budget_status=unlimited` with
`allow_inference=True` while still recording usage, and `_preflight_chat_request`
skips the reservation short-circuit for the unlimited lane — so Operator Raven
inference is observable like a Captain Pod yet never silenced by a cap. The
Operator's own router key now carries the full install-collected model allowlist
(CSV), so the Operator can deliberately select any allowed model and provider-side
fallback strings remain valid. Non-streaming chat completions now
retry bounded fallback candidates on configured retryable provider failures.
Streaming requests can retry fallback candidates before any upstream chunk is
emitted; once a stream has started, the router labels fallback as unavailable
instead of replaying a partially delivered request. Failed fallback attempts are
audited with sanitized events, and usage/reservation metadata distinguishes the
requested, primary, final, reservation-pricing, and usage-pricing models.
Catalog-backed reservations account for the most expensive configured fallback
candidate, while settlement uses the final model actually used.
Live Chutes account/usage/key and PKCE-OAuth adapters (`arclink_chutes_live.py`,
`arclink_chutes_oauth.py`) are present but **TEST-ONLY and unwired** — no live
OAuth-backed inference path exists, and the `per_user_chutes_account_oauth`
isolation lane is a posture label only. Live provider proof remains under
`GAP-031`.

## Pods, Isolation, And SOUL

An ArcPod is the Captain's private deployment, not a loose collection of shared
files. It should contain the Hermes runtime, Agent home, dashboard, Drive, Code,
Terminal, qmd/knowledge rails, managed context, memory synthesis outputs,
credential handoffs, channel bindings, backup rails, and Crew/SOUL identity.

The isolation contract is:

- Captains and Agents cannot gain host root through the Pod.
- Pods cannot read or write another Captain's state.
- Dashboard, Drive, Code, Terminal, MCP, Notion, SSOT, and share routes are
  scoped by deployment/user identity.
- Secret values are stored as references or private files, never public docs or
  chat transcripts.
- One-time handoffs reveal only to the owner and are hidden after acknowledgement.
- Terminal and process execution stay behind bounded broker/helper contracts.
- Docker/root authority on the host is treated as a high-trust boundary until
  stronger isolation is implemented or the operator explicitly accepts the
  residual risk.

Crew Training should be offered but not mandatory. A stock Pod should work on
day one with a capable default SOUL. If a Captain uses Crew Training, ArcLink
should project an additive SOUL overlay and role/context slices without
rewriting historical memory. Agents should receive hot injected, versioned,
grounded context from SOUL, organization profile, subscribed vaults, Notion,
SSOT, recall stubs, and the current day plate.

The root/Docker authority risk is already tracked by `GAP-019`. The command path
is now substantially built: seven trusted-host services (gateway/deployment/
agent-supervisor exec brokers plus the migration-capture, agent-user,
agent-process, and operator-upgrade helpers) front the Docker socket and root
operations with raw-command rejection, HMAC tokens, internal networks, trusted
Docker-binary pins, path/symlink validation, and redacted rejection incidents.
But each socket broker still owns a writeable Docker socket and each root helper
still runs as root, so `GAP-019` is narrowed yet **open and acknowledged-only,
not tenant-safe** — the whole family is risk-accepted behind
`ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted`. The authoritative
trust-boundary entries live in `docs/arclink/operations-runbook.md`. The SOUL and
Crew Recipe projection paths exist locally; live generation remains provider
proof under `GAP-022`.

## Academy Trainer And Subject-Matter Formation

The Academy is a **skill every ArcPod Agent ships with** (`arclink-academy`),
not a one-shot role preview. Invoked from a button or `/academy`, it flips the
Agent into a **sticky Academy Mode** that stays open until the Captain ends it.
Inside the mode an **LLM Trainer** (routed through the central router) and the
**Captain** co-curate a specialist corpus and curriculum from the governed
source lanes; the Captain steers role, depth, focus, and lane authorization.
When the Captain **ends the mode**, the staged plan is sealed for review and the
trainee becomes a **graduate** with weekly **forward-maintenance** (continuing
education) armed. Mode-end itself still writes no Agent files. The separate
`academy_apply` action is the PG-HERMES write path: when authorized, it merges
the replaceable, marker-bounded Academy SOUL section into the deployment Hermes
home, records a private apply receipt, and writes governed `Vault/Academy/...`
markdown/state artifacts for staged curriculum, memory-seed, and approved-skill
records when present. qmd refresh, memory-synthesis ingestion, and active skill
enablement remain future/proof-gated; weekly maintenance refreshes
review/capsule state and does not self-write the Agent. Captains can **browse
Academy graduates** (ready
specialists) and adopt one, or **enroll a new Trainee** against a **Major**
(specialist Program). Majors are pure data, so new trainee types are added as
rows, not code. Crew Training still curates the roster/roles/personality and the
additive SOUL overlay; the Academy is the subject-matter formation layer. The
detailed target system and full surface inventory live in
`docs/arclink/academy-trainer.md`.

The finished Academy should:

- Convert a Captain's requested role into a topic map, competency ladder,
  source plan, training rubric, SOUL overlay plan, skill map, and evaluation
  suite.
- Gather carefully selected source groups: authorized YouTube/video
  transcripts, Reddit practitioner discussions through compliant API access,
  Wikipedia/Wikimedia articles and references, GitHub repositories and docs,
  arXiv/OpenAlex/Semantic Scholar papers, standards, official docs, blogs,
  newsletters, forums, open courseware, datasets, benchmarks, podcasts,
  whitepapers, and trusted skill/MCP/tool repositories.
- Score and filter those sources by authority, freshness, specificity,
  examples, expert signal, license/permission, cross-source agreement, and
  usefulness for the Agent's role.
- Archive allowed material in private Academy state with source metadata,
  license/permission status, content hashes, quality scores, tombstone policy,
  and retrieval history.
- Convert sources into durable lesson cards, citations, vocabulary, workflows,
  mistakes-to-avoid, decision trees, practice tasks, and "where to look next"
  maps.
- Fill the Agent vault with role curriculum, source map, lesson cards,
  evaluation artifacts, skill recommendations, and continuing education notes.
- Rebuild qmd/vector indexes and memory synthesis seeds so shared vault
  material feels local and searchable to the Agent.
- Replace only the needed portions of `SOUL.md` while preserving personal
  memory, useful sessions, and deployment identity unless the Captain asks for
  a reset.
- Install or stage approved skills and tool recipes that match the role,
  rejecting unreviewed public skills until they pass safety and relevance
  checks.
- Graduate the Agent only after scenario tasks, retrieval/citation checks,
  tool-choice checks, refusal checks, and output-quality rubrics pass.

Academy Continuing Education should run weekly. It should sweep all source
lanes, refresh watched repositories/papers/docs/threads, preserve allowed
high-value material that disappears, tombstone content when deletion or license
policy requires it, replace weaker materials with stronger current ones,
queue Agent-submitted `discontinue_resource` proposals for dead-end or poisoned
resources for stronger Trainer/PG-PROVIDER or Operator review before shared
source retirement,
rebuild lesson cards/indexes/memory stubs, run evaluations, and produce a
Captain/Operator report before updating the Agent.

The control-plane experience scaffolding now exists in source. The mode/proposal
tables (`academy_programs`, `academy_trainees`, `academy_mode_sessions`,
`academy_resource_proposals`) and the central shared corpus tables
(`academy_sources`, `academy_corpus_specialists`, `academy_specialist_sources`,
`academy_source_provenance`, `academy_specialist_subscriptions`) are owned by
`python/arclink_control.py` plus `python/arclink_academy_programs.py`. Together
they own the browsable catalog of **Majors** (a seeded specialist catalog;
extensible as data), **Trainee** enrollment, sticky **Academy Mode**
(open/status/end, one open session per trainee, Captain-ends-only), the
**graduate gallery**, graduate adoption, cross-Captain deduped SME corpus
promotion, capsule refresh, and per-trainee subscriptions. Mode-end records the
commit intent and arms forward-maintenance but performs no Agent write
(`mutation_performed=False`), covered by `tests/test_arclink_academy_programs.py`.
The curation/training core remains in `python/arclink_academy_trainer.py`, which
defines the no-network Academy schemas, default governed source-lane registry,
fake acquisition reports, deterministic quality scoring, curriculum/evaluation
records, no-write application plans, a no-write `academy_apply_preview`
action-worker boundary, and weekly Continuing Education review/gate persistence.
The shipped weekly scheduler now performs bounded autonomous live crawling for
approved public source URLs. It rotates the agent responsible for each shared
specialist with durable state, honors HTTPS/robots/rate-limit/SSRF rails,
records digest-only crawl observations in `academy_source_crawl_observations`,
feeds changed/removed/tombstoned observations into the weekly review gate,
refreshes central capsules from already-approved public-lane sources, and
notifies Captains. It stores no raw crawled content and performs no Agent write.
Live transcript/ASR, provider-assisted synthesis, source retirement, and Agent
mutation remain under the acquisition, critic, PG-PROVIDER, and PG-HERMES gates
described above.
The separate `academy_apply` action now materializes the Academy SOUL overlay,
receipt, governed `Vault/Academy/...` artifacts, and a durable
`state/arclink-academy-post-apply-refresh.json` handoff for qmd indexing,
memory synthesis, and explicit skill activation proof only when PG-HERMES
authorization is present. The action worker validates that handoff against the
target Hermes home/vault/state roots, records verified/missing applied paths,
and leaves actual qmd/memory/skill execution runner-gated; record-only or
unauthorized adapters stage/fail closed. It fails closed for
disabled lanes, unsupported lanes, requested live actions, missing
license/permission or required lane metadata, raw-storage violations,
unreviewed public skills, secret-looking fixture material, deletion/tombstone
violations, and any attempt to represent ASR/transcription or provider
generation as local success. It also rejects unsafe observed-source payloads
before weekly review persistence. Compact Academy status summaries are
now staged per Agent on the active Crew Recipe overlay with audit and event
rows, mirrored into deployment metadata, projected into the Agent's local
managed identity context, shown in the dashboard Crew Training panel and Crew
Recipe API, queried read-only from Operator Raven, and previewed through the
local action worker without executor or filesystem calls. Captains enter this
lane with `/academy`, pick one Agent at a time, give the role/source/weekly
refresh rails over a turn-by-turn Raven bootstrap, and open a real sticky
Academy Mode. The Agent uses the `arclink-academy` skill to search approved
rails and submit compressed resources or reviewed discontinuation requests
through `academy.propose-resource`; the
Captain closes the mode to queue the Academy Trainer deep dive. The live LLM
Trainer is now **enabled by default in the control stack**
(`ARCLINK_ACADEMY_TRAINER_LIVE=1`): with a scoped router key present,
`run_academy_trainer_review` and the weekly scheduler route the deep dive through
the central `control-llm-router` (same inference model) with secret-redacted
derived notes, and fail closed to the deterministic engine on any missing key,
router error, or authorization gap. The weekly review also preserves the
Trainer's engine/live/summary enrichment when a capsule body changes (it
recomposes the capsule first, then writes the Trainer enrichment). Canonical
application to the Agent is split: the marker-bounded SOUL overlay apply, the
apply receipt, governed `Vault/Academy/<role>/` markdown, memory seeds, and
approved-skill records are all implemented behind the PG-HERMES action gate, while
live **per-lane source acquisition**, provider-assisted generation, and the
downstream **execution** of qmd re-indexing, memory-synthesis ingestion, and
active Hermes skill enablement remain runner/proof-gated under `GAP-034`. (The
staged Vault/Academy markdown, memory seeds, and approved-skill records are
already written, so they are no longer part of the GAP-034 remnant — only their
live execution is.)

This is larger than the current Crew Recipe system. The current source locally
supports deterministic recipe/SOUL projection and proof-gated live recipe
generation. Academy corpus acquisition, compliant archival, curriculum
generation, continuing education, source-lane governance, skill selection, and
graduation proof are tracked separately by `GAP-034`.

## Slash Menus And Guided Control

Raven commands should be role-aware and self-refreshing:

- Operators see system, fleet, user, upgrade, backup, proof, and incident
  commands.
- Captains see onboarding, link channel, select Agent, Crew Training, share,
  billing/provider, backup, upgrade-status, and help commands.
- Agents own their Hermes/tool commands once active, with Raven moved behind an
  explicit control command when platform command namespaces collide.
- Commands should be easy to cancel when multi-step.
- Every menu refresh should be part of install/upgrade and should not require a
  manual restart or unexplained force reload.

Captain command handling is relatively mature. In an active Agent chat the
picker deliberately exposes a single `/raven` control gateway plus the Agent's
own commands (so the Agent keeps the bare slash namespace and the menu stays
uncluttered); every Captain `raven_*` sub-command remains reachable by typing
`/raven <x>` (rewritten by `_raven_prefixed_command_rewrite`) and is listed in
full in non-active chats. Operator command coverage is the remaining gap and
belongs to `GAP-029`.

## Captain "Yes, And" Behavior

The desired Captain experience is not literal "yes, and" wording. It is a
behavioral rule:

- Acknowledge the Captain's intent.
- Do the real job or start the real workflow.
- State the current ground truth.
- Offer the next best action as a button, command, or short choice.
- Keep the lore voice appropriate to Raven or the Agent personality.
- Do not bury the Captain in host details unless they ask.
- Do not pretend a blocked provider/live-proof/credential path is working.

Crew-trained Agents should keep this same pattern while reflecting their role.
They should be information dense, capable, and specific, but still give the
Captain a clean next move.

## Hermes Dashboard And Plugins

The complete ArcPod dashboard should make Hermes feel like a real workstation:

- Drive: browse Workspace, Fleet, and Linked roots; upload files and folders;
  preview common content; create, rename, move, delete, restore, search, and
  request shares; clearly mark writable accepted shared folders under Linked.
- Code: edit workspace files, browse repos, preview content, inspect git
  status, stage/unstage/commit through safe rails, request shares, and prevent
  Linked git mutation while allowing shared-folder file saves.
- Terminal: provide persistent managed sessions, bounded scrollback, SSE with
  polling fallback, safe lifecycle controls, root guardrails, and clear failure
  display.
- Dashboard auth: use ArcLink's signed session/proxy layer, not browser-facing
  Basic Auth for the workspace tools.
- Status: show provider state, memory/qmd freshness, share inbox, backup state,
  restore points, and upgrade state without forcing a Captain into the admin
  dashboard.

The plugin code and README files show the local shape is real. Live browser
proof remains part of `PG-HERMES`.

## Hermes Skills And Tool Recipes

ArcLink skills should behave like precise instruments: concise, discoverable,
and hard to misuse. They should guide the model toward the best brokered tool
first instead of raw filesystem or raw Notion rummaging.

The intended skill set includes:

- first contact and onboarding guidance;
- vault search/fetch and vault reconciliation;
- qmd retrieval across vault, PDF sidecars, and Notion markdown;
- Notion knowledge search/fetch;
- SSOT read/write/status/approval guidance;
- resource discovery through private manifests;
- upgrade orchestration guidance;
- PDF export/import where explicitly configured.

The managed-context plugin should inject short, current recipes for
`knowledge.search-and-fetch`, `vault.search-and-fetch`, `notion.search-and-fetch`,
`ssot.read`, `ssot.write`, `shares.request`, and ArcLink MCP bootstrap token
use. Skills should remain short enough that the model can use them under load,
but complete enough that it does not fall back to unsafe raw operations.

## Agent Knowledge, Memory, And Docs

Hermes docs must stay in lock step with the pinned Hermes runtime. ArcLink
should sync the docs ref that matches `ARCLINK_HERMES_AGENT_REF`, place them in
the agent-accessible knowledge rail, and update them during ArcLink upgrades.

The knowledge/memory contract is:

- Vault markdown/text, PDF sidecars, and shared Notion markdown are indexed by
  qmd under the correct collections.
- Vault changes trigger fast watcher-driven refresh and bounded synthesis, not
  only slow periodic refresh.
- Shared vault directories should feel like local knowledge to every authorized
  Agent: searchable in plugins, retrievable through MCP, and summarized into
  recall stubs when synthesis is enabled.
- Memory synthesis stays off the chat critical path, skips unchanged source
  signatures, bounds snippets/output, and treats cards as retrieval hints, not
  unquestionable facts.
- Managed context hot-injects recall stubs, vault landmarks, Notion landmarks,
  model/runtime data, and daily plate information.
- Deletions, moves, renames, and permission changes self-heal indexes and do
  not leave stale private facts available to the wrong Pod.

Shared-directory parity is now real, not aspirational. The Fleet and Linked
shared roots are registered as their own qmd collections
(`fleet-shared`/`linked-shared`, gated on the mount existing), mounted into the
`qmd-mcp` and `vault-watch` containers, and added to the default
`knowledge.search-and-fetch` collection set when those roots are configured — so a
shared document is retrievable through MCP and searchable in plugins like local
vault knowledge, for every authorized Agent. Propagation is now event-driven: the
vault watcher watches the Fleet/Linked roots in addition to the vault, so a peer's
Fleet pull (`fleet-share-sync`) or a new Linked grant triggers a fast qmd re-index
plus a bounded memory-synthesis refresh on the receiving Pod, instead of waiting
for the next periodic timer. Memory synthesis also no longer suppresses a changed
source while its prior card is in failure backoff — a new content signature
overrides the backoff so an edit is reflected immediately. Current source and
tests cover much of this locally. Live workspace proof still belongs to
`PG-HERMES`, and shared external Notion proof belongs to `PG-NOTION`.

## Hermes And ArcPod Updates

The complete update dream is rolling and centrally visible:

1. Operator Raven or admin dashboard starts an upgrade.
2. The Control Node checks release state, pins, deploy key health, provider
   health, worker capacity, backup freshness, and active incidents.
3. The Control Node upgrades itself first or stages the new release in a safe
   slot.
4. ArcPods update in bounded parallel batches, not one fragile sequential sweep.
5. Each Pod refreshes Hermes runtime, ArcLink skills, dashboard plugins, command
   menus, managed context, docs, and service definitions.
6. Health and smoke evidence is collected per Pod and summarized globally.
7. Failures stop the rollout, preserve state, and leave the operator with a
   repair plan and rollback option.

Current source has Control Node upgrade, component pin checks, release state,
notification rails, a first ArcPod rollout dry-run planner, and a local
action-worker path that materializes ready plans into deterministic per-Pod
planned rollout rows. The local path preserves candidate Pods, batch order,
preflight blockers, rollback/state-root requirements, pending health/smoke
proof, action-operation links, and secret-free result metadata through admin
scale operations and action-worker audit. It can also record one explicit
fake/local batch with `in_progress`, `completed`, or `failed` row truth, repair
hints, and stop-on-failure behavior. It does not yet have real refresh/apply
execution or live multi-Pod proof. That remains `GAP-032`.

Upgrade policy is now source-owned in `python/arclink_upgrade_policy.py` and
visible from Operator Raven through `/upgrade_policy [component]`. The policy
separates control-plane upgrades, ArcPod runtime batches, knowledge-plane jobs,
stateful infra maintenance, build-runtime pins, and worker-fabric drain/resume
work. Stateful dependencies such as Postgres, Redis, and Nextcloud are not
pretended to be stateless rolling jobs: they require backup/snapshot preflight,
a maintenance posture, and rollback contracts. Worker runtime and WireGuard
changes use `/fleet_drain <worker>` and `/fleet_resume <worker>` so new
placements avoid a worker before maintenance starts.

## Billing, Entitlements, And Refuel

The product path should keep money and capacity aligned:

- Stripe checkout, portal, webhook, subscription state, failed payment,
  cancellation, and refund/cancel policy feed entitlement state.
- Entitlement state gates provisioning and provider continuation.
- Refuel credits are explicit, auditable, and visible before exhaustion.
- Additional Agents use plan-specific expansion prices.
- Captain-facing copy should distinguish plan price, provider budget, refuel
  state, and live provider availability.
- Operator Raven should see the same state and be able to trigger safe recovery
  actions without seeing secrets.

Local entitlement logic is strong, but live Stripe proof remains `PG-STRIPE`.

## Third-Party Integration Boundaries

ArcLink depends on third parties, but the product should never let those
dependencies blur ownership or security boundaries.

The finished integration contract is:

- Stripe owns payment collection and subscription events; ArcLink owns
  entitlement interpretation, idempotency, gating, audit, and recovery copy.
- Telegram and Discord own message delivery constraints; ArcLink owns command
  registration, channel binding, role authorization, fallback copy, and retry
  state.
- Chutes or other providers own model execution; ArcLink owns router keys,
  model allowlists, fallback policy, budget enforcement, sanitized usage rows,
  and incident visibility.
- Cloudflare and Tailscale own ingress primitives; ArcLink owns desired-state
  records, teardown evidence, proof gates, and clear domain/Tailscale mode
  selection.
- Notion owns external pages/databases; ArcLink owns shared-root expectations,
  SSOT broker permissions, destructive-operation refusal, and user-OAuth
  limitations.
- GitHub or another Git host may own backups and source remotes; ArcLink owns
  deploy-key separation, private/public repo hygiene, dry-run write checks,
  restore proof, and refusal to activate unsafe public backup repos.

No third-party credential should be printed in chat, written to public docs, or
passed as an agent argument. Every integration must have three visible states:
configured and locally valid, configured but live-proof pending, or missing and
blocked with the next operator action.

## Backup, Restore, And Data Lifecycle

Backup cannot mean "files were copied once." It must mean the Operator can
prove recoverability without surprising the Captain or destroying state.

The finished data lifecycle should cover:

- Control DB backup and restore.
- Per-ArcPod state backup and restore.
- Per-agent Hermes home backup, including private backup repo activation only
  after read and dry-run write checks pass.
- Shared vault, generated markdown, Notion index, qmd state, memory synthesis
  cards, and PDF sidecars as recoverable but clearly classified state.
- Credential handoff reissue without leaking old secrets.
- Enrollment/deployment reset, rollback, teardown, and volume deletion as
  separate operations with separate confirmations.
- Retention, purge warning, suspension, cancellation, and refund/cancel policy
  reflected in entitlement and data-state copy.
- Restore drills that end with health, dashboard load, workspace proof, and
  redacted evidence.

Local restore-smoke and backup tests provide a base. Staging/live restore proof
is still `PG-BACKUP`, and backup user experience work remains tied to the
backup rows in `GAPS.md`.

## Fleet, Provisioning, Ingress, And Recovery

The Control Node should be the one place where fleet and Pod state are
understood:

- Fleet hosts are registered with hostname, SSH endpoint, user, region, tags,
  capacity, state root, and health/probe evidence.
- Placement rejects unhealthy, drained, or insufficient-capacity workers.
- Provisioning writes secret references and deployment intent, then applies
  through the selected executor.
- Ingress is either domain/Cloudflare/Traefik with wildcard subdomains or
  Tailscale path routing, with clear teardown evidence.
- Rollback preserves state by default and only deletes volumes with explicit
  destructive metadata and confirmation.
- Recovery surfaces include credential reissue, dashboard repair, provider
  repair, share retry, backup restore, and Pod teardown/rollback.

Local source implements much of this. Live apply, remote worker, and ingress
proof remain under `PG-PROVISION`, `PG-FLEET`, and `PG-INGRESS`.

## Notifications, Incidents, And Evidence

ArcLink should never fail silently. Every important background path should have
an owner-visible state, a retry or repair path, and evidence that can be shared
without secrets.

The finished incident/evidence layer should provide:

- Operator notifications for failed provisioning, bot delivery problems,
  provider outage/fallback, upgrade drift, command collision, backup failure,
  restore failure, and ingress/fleet health loss.
- Captain notifications for their own blocked setup, failed payment, provider
  budget exhaustion, share request, backup status, credential handoff, and Pod
  health when appropriate.
- Dashboard and Raven views of the same incident state, so a chat retry and a
  browser retry do not create competing truths.
- Redacted evidence records for live proof, health runs, upgrade runs, backup
  restore, Stripe events, provider fallback, bot delivery, fleet lifecycle, and
  ingress apply/teardown.
- A clear split between local dry-run proof, authorized live proof, policy
  decision, and residual-risk acceptance.
- No raw stack traces, secrets, private file paths, or prompt/completion
  payloads in public artifacts.

This layer connects `GAP-029`, `GAP-030`, `GAP-031`, `GAP-032`, `GAP-033`,
`GAP-034`, and the live proof gates. It is also the protection against
beautiful docs drifting away from operational truth.

## Identity, Access, And Session Governance

ArcLink has to know who is speaking before it decides what the words can do.
The finished identity model should be explicit across web, Raven, dashboard,
CLI, API, and agents:

- Exactly one platform Operator/admin owner is established for the Control
  Node, with any future delegated roles modeled as deliberate RBAC, not as
  accidental shared admin access.
- Captain identity, deployment ownership, channel bindings, dashboard sessions,
  API sessions, credential handoffs, and ArcPod bootstrap tokens all remain
  scoped to the same account/deployment truth.
- Telegram and Discord channel identity is not treated as the same thing as
  web identity until pairing/confirmation has completed and been audited.
- Session cookies, CSRF tokens, proof tokens, pairing codes, router keys, and
  bootstrap tokens each have their own lifetime, storage location, revocation
  path, and audit behavior.
- Admin and Operator actions should never trust client-asserted privilege,
  client-asserted MFA, or natural-language intent without server-side
  authorization and typed action resolution.
- Rate limits, replay protection, nonce/confirmation, channel allowlists, and
  reason capture should be consistent enough that the same action cannot be
  made safer or more dangerous merely by choosing chat instead of dashboard.
- Account recovery, channel unlink, session revoke, token rotation, and device
  loss should be normal product flows, not emergency database surgery.

Current source contains strong pieces: session/CSRF/auth tests, exactly-one
admin assumptions, rate limiting, owner-scoped handoffs, and tokenized MCP
bootstrap. The remaining shape is a unified Operator Raven/action policy and
clearer recovery/revocation experience, mainly tied to `GAP-027`, `GAP-029`,
and `GAP-033`.

## Secrets, Keys, And Rotation

ArcLink's power depends on many credentials, so the secret lifecycle must be a
product surface rather than a hidden install detail.

The complete secret contract is:

- Stripe, Telegram, Discord, Chutes/provider, Cloudflare, Tailscale, SSH,
  deploy-key, backup-key, Notion, router, and per-ArcPod bootstrap credentials
  are stored only in private state or provider-owned stores.
- Public docs, chat transcripts, logs, evidence artifacts, command arguments,
  and generated markdown must never contain secret values.
- Secret references move through provisioning instead of plaintext values.
- Every credential should have status without disclosure: missing, present,
  invalid, expiring, stale, rotated, revoked, live-proof pending, or blocked.
- Rotation should be guided from Operator Raven, admin dashboard, and CLI,
  with preflight checks before cutting over and rollback/repair guidance after.
- Deploy keys remain separated by lane: public ArcLink upstream, private
  `arclink-priv` backup, and per-user/private agent backup keys.
- Bot and provider tokens should be validated with the smallest safe live call
  and should fail closed if validation cannot run.
- Any helper that requires a token should prefer a file, secret reference, or
  private env over argv, logs, or user-visible prompts after collection.

This section is governed by the existing secret hygiene, provisioning, backup,
and deploy-key rows. If future audit finds a credential that lacks a status,
rotation, revocation, or redaction story, it should become a concrete local gap
instead of staying tribal knowledge.

## Configuration, Schema, And Migration

The Control Node should be upgradeable because its configuration and state are
versioned, validated, and migrated deliberately.

The finished migration contract is:

- `./deploy.sh control install`, `reconfigure`, `upgrade`, `backup`, and
  `reset-runtime` all understand which config/state files they own and which
  private files they must preserve.
- Generated config includes enough version/release context to detect stale,
  missing, deprecated, or incompatible values before services start.
- Database schema changes are migration-aware, idempotent, reversible where
  practical, and tested against old-state fixtures.
- OpenAPI/static docs, hosted API behavior, web clients, bot command schemas,
  MCP schemas, and action-worker schemas remain compatible within a release or
  fail with a clear upgrade requirement.
- Reconfigure is safe for changing ports, ingress mode, provider defaults,
  operator channels, worker settings, and router fallback policy without
  silently deleting runtime state.
- Restore and migration flows validate state before activation and leave a
  release/evidence record after activation.

ArcLink already has release state, pin checks, config generation, local schema
tests, and OpenAPI truth checks. The schema mechanism today is a single
idempotent `ensure_schema()` in `arclink_control.py` — `CREATE TABLE IF NOT EXISTS`
for every table plus a few in-place rebuild migrations (`*__new` table copy +
`RENAME`). It is idempotent and create-if-absent, but there is **no version
ledger and no numbered/reversible migration history yet**; the "reversible where
practical, versioned, old-state-fixture" contract above is the target shape, not
the current state. Rolling migrations, a release/version detector, and broad
compatibility fixtures should expand as `GAP-032` and the Operator Raven/action
model become real.

## Observability, SLOs, Capacity, And Scale

The Operator should be able to answer "is ArcLink healthy?" without reading raw
logs or guessing which subsystem matters.

The complete observability shape is:

- Health is layered: control process health, API/web health, bot webhook health,
  Stripe webhook health, provider/router health, queue health, fleet capacity,
  ArcPod health, workspace health, backup freshness, qmd/memory freshness, and
  proof status.
- Metrics should expose queue depth, provisioning latency, provider fallback
  rate, token/cost usage, failed bot deliveries, webhook failures, upgrade
  progress, backup age, worker capacity, dashboard latency, and error budgets.
- Logs should be structured, redacted, role-aware, and linkable to action,
  incident, deployment, session, or proof IDs without leaking secrets or raw
  prompts.
- Alerts should distinguish Captain-impacting incidents from operator-only
  maintenance issues and should route to the primary Operator Raven channel
  plus dashboard.
- Scale controls should model worker slots, provider budget, queue backpressure,
  rolling-update batch size, memory/qmd work scheduling, web/API rate limits,
  and per-plan concurrency.
- SLO-style targets should exist for checkout-to-provisioning, Raven response,
  dashboard load, provider fallback, backup freshness, restore drill, and
  incident acknowledgement once real production evidence exists.

Current code has health, diagnostics, evidence, rate limits, fleet capacity, and
usage rows. The product gap is converging these into shared status, alerting,
and Operator Raven views without overclaiming live SLOs before evidence exists.

## API, Webhook, And Extension Contracts

ArcLink is a product and a platform. Its internal and public contracts should
be stable enough for web, bots, workers, plugins, and future integrations to
evolve without hidden breakage.

The finished contract layer should include:

- Versioned hosted API routes with OpenAPI/static-dynamic parity tests.
- Idempotent webhook handlers for Stripe, bots, Notion, and any future provider
  callbacks.
- Versioned bot command/action schemas for Telegram and Discord, including
  command namespace collision rules.
- Versioned MCP schemas for ArcLink tools, with destructive operations absent
  or explicitly approval-gated.
- Plugin contracts for Drive, Code, Terminal, managed context, shares, and
  future workspace tools.
- Action-worker contracts that define actor, action, target, reason, status,
  audit, dry-run, confirmation, retry, timeout, and rollback fields.
- Compatibility tests that prove old clients fail clearly or continue safely
  across an ArcLink release.

Whenever a new surface is added, it should declare whether it is Captain-facing,
Operator-facing, Agent-facing, worker-facing, or internal-only. That declaration
should decide auth, audit, redaction, rate limiting, docs, and tests.

## Support, Offboarding, And Customer Lifecycle

The dream system is not complete if it only covers happy customers. It must
cover confused, blocked, cancelling, suspended, refunded, migrating, and
departing customers too.

The complete lifecycle should cover:

- Trial/checkout recovery, failed payment, refuel prompt, cancellation,
  refund/cancel, suspension, warning, purge, and reactivation.
- Support-safe account lookup that reveals status and next action without
  exposing secrets or private workspace content.
- Captain self-service for channel relink, credential handoff recovery,
  provider/budget status, backup setup, share review, and dashboard repair.
- Operator repair flows for failed provisioning, stuck backup setup, bot contact
  retry, provider outage, worker capacity loss, and dashboard access failure.
- Data export, backup handoff, retention, deletion, and teardown choices that
  are consistent with entitlement and policy.
- Migration between workers or future regions with state preservation and
  explicit downtime/rollback expectations.
- Clear "what happens next" copy at every lifecycle edge.

Many lifecycle pieces already exist locally in entitlement, onboarding,
dashboard, backup, and retry code. Remaining policy choices should stay in
`GAPS.md` until the product decision is explicit and encoded in tests.

## Abuse, Safety, And Platform Boundaries

ArcLink should assume that public entry points will be poked, spammed, and
misused. Safety here means protecting the platform, Captains, Operators, and
third-party accounts without weakening the intended power of ArcPods.

The finished abuse/safety layer should provide:

- Rate limits and replay resistance for onboarding, login, pairing, checkout,
  webhook, bot command, share request, provider, and admin paths.
- Bot-spam and command-flood handling that does not accidentally execute stale
  multi-step actions.
- Provider budget abuse protection and clear refusal when a plan or refuel
  limit is exhausted.
- Upload/file safeguards for oversized, binary, executable, symlink, path
  escape, and archive-bomb cases in Drive, Code, memory synthesis, PDF ingest,
  and qmd indexing.
- Terminal/process/root-helper restrictions that treat shell execution as a
  brokered capability, never as ambient trust.
- Content/prompt handling that avoids storing raw prompts/completions in router
  usage logs and avoids feeding secret-bearing output back into Agent prompts.
- An Operator policy place for acceptable use, takedown, abuse escalation, and
  account termination.

Some of this is already covered by rate limits, secret regex tests, plugin root
guards, qmd/memory bounds, and the Docker/root trusted-host rows. Any new unsafe
entry point should be added to the security/isolation journey and mapped to a
specific gap or proof gate.

## Accessibility, Responsiveness, And Surface Fit

The product should be beautiful because it is usable under pressure, not merely
because the prose is polished.

The complete surface-fit standard is:

- Web and PWA surfaces work on mobile and desktop without hidden critical
  actions, clipped text, or overlapping controls.
- Dashboard and admin views support keyboard navigation, visible focus,
  semantic labels, readable contrast, and stable layout under loading/error
  states.
- Telegram and Discord messages fit their platform markdown and button limits.
- CLI and TUI output is scan-friendly, redacted, and copy-paste safe.
- Raven and Agent text keeps the lore voice, but status, warnings, errors, and
  confirmations remain plain enough for tired Operators and new Captains.
- Localization is not required for the current product unless chosen, but all
  user-visible copy should be centralized enough that future localization is
  possible.

Local fixture enforcement now belongs to `tests/test_arclink_surface_contract.py`.
`GAP-033` stays open until authorized browser, bot, plugin, CLI, and TUI proof
confirms the rendered experience outside local fixtures.

## Supply Chain, Build, And Release Integrity

The Control Node should know what it is running and where it came from.

The finished release-integrity story should include:

- Pinned Hermes runtime and docs refs, ArcLink release state, component pins,
  and upgrade checks before rollout.
- Container images, Python dependencies, Node dependencies, shell scripts, and
  generated configs built from known source and validated before deployment.
- Deploy-key provenance for upstream source updates and private backup keys,
  with branch expectations explicit.
- Dependency and vulnerability review appropriate to the release channel.
- Reproducible or at least explainable builds for the Control Node and ArcPod
  homes.
- Rollback expectations for code, config, database schema, images, and ArcPod
  refresh state.
- A future SBOM/signature lane if ArcLink is distributed beyond trusted
  operator-controlled installs.

Current source has pins, release state, deploy-key guidance, syntax checks,
local tests, and upgrade rails. The larger supply-chain posture should mature
with rolling updates and production release proof under `GAP-026` and
`GAP-032`.

## Operator Delight And Golden Paths

The best Control Node is powerful without making the Operator feel trapped in
machinery. Installation, repair, and expansion should feel like guided flight
checks: exact, calm, reversible, and proud of the system it is bringing online.

The golden path should provide:

- A first menu that exposes the Sovereign Control Node as the only public
  install lane, with retired legacy-mode guardrails for old commands.
- Preflight checks that explain missing Docker, network, ports, DNS, Tailscale,
  Stripe, provider, bot, and worker prerequisites before half-building the
  stack.
- An install questionnaire that accepts defaults when safe, explains why each
  sensitive answer matters, refuses impossible combinations, and can be rerun
  idempotently.
- A final install report with URLs, ports, active services, worker capacity,
  bot/channel status, provider/router status, Stripe status, backup status,
  proof gaps, and the next best action.
- A "control plane up, provisioning blocked" path that feels intentional rather
  than broken when no worker has been admitted yet.
- Operator Raven, admin dashboard, and CLI summaries that use the same language
  and never force the Operator to translate between three vocabularies.
- Guided repair flows for the common failures: no worker, no bot delivery,
  no provider, no Stripe webhook, DNS/Tailscale drift, dashboard unreachable,
  backup stale, and upgrade blocked.

The product bar is not merely that install succeeds. The bar is that the
Operator can rerun, repair, expand, and explain the install without needing to
remember hidden tribal steps.

## Maintenance Rhythm

ArcLink should be maintainable as a living system. Operators should not need to
wait for an incident to discover that backups, workers, providers, or command
menus have drifted.

The finished maintenance rhythm should include:

- Daily health and incident review: failed jobs, failed bot delivery, provider
  fallback, webhook failures, stuck actions, backup age, and queue depth.
- Weekly readiness review: fleet capacity, worker health, provisioning
  dry-runs, dashboard/workspace smoke, command-menu drift, and qmd/memory
  freshness.
- Monthly recovery review: control DB restore drill, at least one ArcPod state
  restore drill, backup key validity, deploy-key validity, and evidence ledger
  completeness.
- Release review: dependency/pin check, upgrade dry-run, schema compatibility,
  web/API/bot/OpenAPI truth, rolling-update plan, and rollback plan.
- Policy review: provider fallback policy, retention/deletion posture,
  operator action scope, residual trusted-host risk, and self-service provider
  stance.
- Captain experience review: checkout friction, Raven confusion points,
  dashboard error copy, share recovery, provider-budget copy, and support
  contact loops.

These rhythms should become dashboard and Operator Raven views as the product
matures. Until then, runbooks and `GAPS.md` keep them honest.

## Expansion, Ecosystem, And Extensibility

ArcLink should grow without turning into a bag of special cases. New providers,
workers, plugins, skills, knowledge sources, and surfaces should plug into
clear contracts.

The expansion story should cover:

- Provider expansion: add a model provider through catalog/config, router
  policy, budget/cost metadata, fallback behavior, live proof, and user-facing
  copy.
- Worker expansion: add a provider or host class through inventory, capacity,
  probe, admission, drain, teardown, and proof contracts.
- Plugin expansion: add workspace tools through plugin manifests, auth proxy,
  root guards, UI fit, MCP/tool recipes, tests, and install/refresh hooks.
- Skill expansion: add concise Hermes skills that point agents toward brokered
  tools and stay versioned with the installed runtime.
- Knowledge expansion: add Notion roots, vault subscriptions, PDF/media lanes,
  repo inventories, and external MCPs through private manifests and scoped
  retrieval.
- Plan expansion: add new commercial plans, expansion prices, budgets,
  entitlements, checkout IDs, dashboard copy, and tests without changing
  provisioning logic by hand.
- Region/provider expansion: add new fleet regions and cloud providers without
  changing the Captain's conceptual model of a private ArcPod.

The expansion principle is simple: a new lane must declare ownership, state,
auth, rate limits, proof, rollback, docs, and tests before it is considered
part of the ArcLink universe.

## Review, Certification, And Recommendation

ArcLink should be easy to review and safe to recommend because its truth is
inspectable. A serious evaluator should be able to ask "what is real, what is
proof-gated, what is policy-gated, and what remains risk-accepted?" and get the
same answer from docs, tests, CLI, dashboard, and Raven.

The review and recommendation layer should include:

- A product reality ledger that separates local-real, live-proof-gated,
  policy-question, residual-risk, and future-work claims.
- A release checklist that links each claim to source, regression tests,
  browser/bot proof, live proof, or explicit handoff.
- A demo mode or redacted proof bundle that shows the complete Control Node
  traversal without exposing secrets or mutating production.
- A reviewer map from user journey to source files, tests, proof gates, and
  remaining gaps.
- Security review notes for auth, CSRF, sessions, channels, brokered actions,
  root/helper boundaries, secret handling, and third-party integrations.
- Operational review notes for install, upgrade, backup, restore, capacity,
  incident response, and rollback.
- Experience review notes for web, Raven, dashboard, plugins, CLI/TUI,
  accessibility, and platform message fit.
- A clear recommendation threshold: recommend for local validation, controlled
  pilot, production launch, or scale rollout only when the matching proof gates
  and policy decisions are complete.

This turns ArcLink from "trust the builder" into "inspect the score, inspect
the proof, then decide the rollout stage."

## Demo, Training, And Adoption

The dream system should be learnable. Operators, Captains, support humans, and
future agents should have a smooth path from curiosity to competence.

The complete adoption layer should include:

- A safe demo story with fictional data, no live secrets, and no accidental
  billing/provider calls.
- Operator first-day training: install, worker admission, Raven pairing,
  dashboard tour, proof gates, backup, restore, upgrade, and emergency repair.
- Captain first-day training: Raven start, checkout/claim, channel link,
  Agent selection, dashboard, Drive/Code/Terminal, sharing, backup, and provider
  budget/refuel.
- Support training: account lookup, entitlement state, failed payment,
  provisioning stuck, bot contact retry, dashboard access, provider outage,
  backup status, and escalation.
- Agent/developer training: use the coverage matrix, gaps, steering docs,
  tests, and source-owned wrappers before inventing new behavior.
- A changelog/release-note style that tells Operators what changed, what needs
  action, what was proofed, what stayed proof-gated, and what policy changed.

Adoption is part of the product. A system this broad is only excellent if new
people can enter it without being handed a maze.

## Post-Audit Hardening Register

This register records the 2026-06-05 ground-truth defect sweep so the symphony,
`GAPS.md`, and the code agree on the same traversal. Each landed fix is source-
real and regression-tested; each forward-plan item names the exact owner and
approach so it can be picked up without re-discovery.

**Landed this pass (source-real + tested).**

- *Executor boundary* — `SshDockerComposeRunner.read_text_file` now fails closed
  (raises) instead of silently returning `None` when a remote read fails with no
  `allowed_root`; `write_text_file` sends a single shell-quoted remote command
  (matching `read_text_file`) so a remote login shell cannot re-split the path on
  metacharacters.
- *Placement reporting* — `control_node_provisioning_readiness` builds eligibility
  from full `list_fleet_hosts` rows (which carry `metadata_json`) rather than the
  metadata-stripped capacity-summary projection, so `image_sync_failed` workers are
  no longer over-counted as eligible; `register_fleet_host` preserves `image_sync_*`
  keys across a hostname re-registration; the `deploy.sh` image-sync resolver matches
  the canonical `private_dns_name → wireguard_dns_name → private_mesh_dns_name →
  ssh_host` precedence.
- *Academy* — the weekly live-trainer review returns the capsule `changed` flag so
  `central_capsules_refreshed` is accurate, and it recomposes the capsule *before*
  writing the Trainer enrichment so the engine/live/summary metadata is no longer
  clobbered when a capsule body changes.
- *Inference* — Operator Pod is `observe_only_unlimited` (metered but never
  fails closed); install asks for and persists the default per-Pod monthly budget;
  the Operator router key carries the full model allowlist (CSV).
- *Shared knowledge* — Fleet/Linked roots are qmd-indexed collections, mounted into
  `qmd-mcp`/`vault-watch`, and added to the default search collection set; the vault
  watcher watches those roots for event-driven re-index + memory synthesis; a changed
  source overrides the memory-synth failure backoff.
- *Experience* — Telegram Captain replies render Markdown code spans as real `code`
  entities instead of literal backticks, forwarded through long-poll and webhook send.
- *Operator control* — Discord can now be a *secondary* operator surface (not only the
  primary), gated by the Discord user/role allowlist and an explicit operator channel.
- *Hygiene* — pairing-code cancel now supersedes the still-claimable DB code and clears
  the pairing session keys; the `arclink-academy` skill teaches the correct
  `knowledge.search-and-fetch` params (`vault_fetch_limit`/`notion_fetch_limit`);
  `curate-notion.sh` is executable; the installed-skill-count ground-truth doc is
  corrected (10 user / 11 Curator; `notion-page-pdf-export` is an optional
  chromium-gated operator skill, not in the default set).

**Forward plan (named owner + approach; not yet landed).**

- *`GAP-033` Telegram handoff link in Tailscale mode* (high) — on a successful
  tailscale/path-mode apply, `arclink_sovereign_worker.process_sovereign_deployment`
  fires `user_handoff_ready` with the *worker* tailnet DNS URL before the control-node
  bridge is published, so the first link can be unreachable. Plan: defer the handoff
  event + `_queue_vessel_online_notifications` until metadata
  `tailnet_app_publication.status == 'published'`, and let the existing
  `recover_succeeded_sovereign_handoffs` sweep re-fire it once the control publisher
  has rewritten `access_urls` to the control DNS. Requires live tailscale-mode proof
  before landing (deferring the handoff must not strand it).
- *Raven `/share-create` origination* (`GAP-014` adjacent) — Raven today is an
  approve/accept surface only; the plugin/web/MCP paths can mint a share but Raven
  cannot. Plan: add an `ARCLINK_PUBLIC_BOT_SHARE_CREATE_RE` command dispatched to a
  new `_share_create_reply` that resolves `session.user_id` as owner and calls the
  same `create_user_share_grant_for_owner` broker (inheriting no-reshare + root
  validation), with owner-approval/claim copy. Security-review the recipient
  resolution before enabling.
- *ArcPod-upgrade command-menu refresh* (`GAP-032`) — a Captain-initiated ArcPod
  Hermes upgrade does not re-push that Pod's active-chat command scope, and the
  per-turn lazy refresh reads control-node-local Hermes rather than the Pod's
  container. Plan: call `refresh_active_telegram_command_scopes` (or a per-deployment
  variant) on rollout completion in `arclink_action_worker`, and include a description
  hash in the per-turn cache signature so description-only changes are not skipped.
- *Tracked nohup tailnet forwards* — when `systemd-run` is unavailable,
  `docker_ensure_tailnet_forward` falls back to a `nohup ssh -L` that
  `docker_prune_tailnet_forwards` cannot stop (no `.ctl` socket, no unit), so it leaks.
  Plan: write a pidfile next to the existing `.log`, prune by killing tracked pids not
  in the desired route set, and scope the local-http short-circuit to a known-good
  tracked forward for this deployment+port.
- *Operator gate unification* (`GAP-029`) — the curator-onboarding long-poll Telegram
  operator gate and the hosted-API webhook gate use slightly different rules. Plan:
  unify both behind one `operator_telegram_sender_allowed` helper so the same update
  yields the same allow/deny regardless of transport.
- *Surface-contract TUI/API/docs coverage* (`GAP-033`) — the contract declares those
  channels but the test samples none. Plan: run a read-only `arclink_ctl` command and
  representative TUI/docs strings through `assert_surface_contract`, or trim the
  `SurfaceChannel` Literal to what is actually exercised.

## Governance And Proof

ArcLink should govern itself with explicit proof boundaries:

- A claim is local-real only when source and regression tests prove it.
- A live claim becomes real only after authorized live proof and redacted
  evidence.
- A policy choice stays a policy question until the operator/product decision
  is recorded and tests encode it.
- A residual risk stays visible until removed or explicitly accepted.
- Public docs never claim private proof that is not represented by source,
  tests, or named external evidence.

This document is therefore a target score, not a launch certificate. The score
is finished when `GAPS.md`, `USER_JOURNEY.md`, `research/COVERAGE_MATRIX.md`,
the implementation plan, and the code all agree on the same traversal.

## Completion Checklist

The symphony is complete as a document only when it names every major motion:

- Operator install, worker admission, configuration, readiness, and proof.
- Public web entry, account/session, checkout, billing, and entitlement.
- Identity, access, sessions, CSRF, channel binding, recovery, and revocation.
- Secrets, deploy keys, provider keys, bot tokens, rotation, and redaction.
- Captain Raven, channel linking, Crew Training, selected Agent, and handoff.
- ArcPod provisioning, isolation, dashboard, credential handoff, and recovery.
- Drive, Code, Terminal, sharing, Linked roots, and no-reshare boundaries.
- Central inference, provider fallback, budgets, refuel, and usage audit.
- Academy Trainer, subject-matter corpus, lawful source lanes, SOUL overlay,
  skill equipping, evaluation, and weekly continuing education.
- Hermes skills, docs, qmd, Notion, SSOT, memory synthesis, and SOUL context.
- Operator Raven, admin dashboard, CLI, action workers, and incident response.
- Fleet, ingress, backup, restore, upgrade, rollback, teardown, and evidence.
- Configuration, schema migration, API/webhook/action/plugin compatibility, and
  OpenAPI/MCP truth.
- Observability, SLO candidates, capacity, scale, alerts, and redacted logs.
- Support, offboarding, customer lifecycle, data export, retention, deletion,
  and migration.
- Abuse controls, upload/file safety, terminal/process boundaries, and provider
  budget abuse protection.
- Accessibility, responsiveness, keyboard/screen-reader basics, and platform
  message fit.
- Supply-chain provenance, dependency health, release integrity, and rollback.
- Operator delight, golden paths, repair ergonomics, and repeatable install
  reports.
- Maintenance rhythm, release review, recovery review, and policy review.
- Expansion contracts for providers, workers, plugins, skills, knowledge
  sources, plans, regions, and future surfaces.
- Review, certification, demo, training, adoption, recommendation thresholds,
  and redacted proof bundles.
- Cross-surface polish for Telegram, Discord, web/PWA, Hermes dashboard, CLI,
  and TUI.
- Policy, live proof, local proof, and residual-risk boundaries.

The product is complete only when those document motions are implemented,
tested, and either locally proven or live-proofed under the matching `PG-*`
gate. Until then, this document is the score the implementation follows and `GAPS.md`
remains the conductor's ledger.
