# Ralphie Steering: ArcLink Product Reality And Journey Pass

## Mission

Verify and repair the full ArcLink product contract described by the operator on
2026-05-08. The first question is not "can we imagine this working?" It is:
"Which parts are real in this repository today, which are partial, which are
missing, and which require live proof or operator product/security choices?"

Ralphie must produce a truth matrix before claiming progress. For every product
claim below, classify it as one of:

- `real`: implemented locally with tests/docs or strongly traceable code.
- `partial`: implemented in one surface but not end-to-end.
- `gap`: missing or misleading.
- `proof-gated`: cannot be verified without live external accounts/secrets.
- `policy-question`: product/security/operations vector is not determined by
  code and needs operator choice.

After the truth matrix, Ralphie should repair the highest-impact gaps with code,
tests, and docs. Do not stop at docs when behavior is missing. Do not overclaim
live behavior without live proof.

## Operating Guardrails

- Read `AGENTS.md` first.
- Preserve all existing user/operator changes in the dirty worktree. Do not
  revert unrelated files.
- Do not read `arclink-priv/`, user homes, secret files, live token files,
  deploy keys, OAuth credentials, bot tokens, or `.env` values.
- Do not run live deploy/install/upgrade, live Stripe, live Cloudflare,
  live Tailscale, live Chutes, live Telegram, live Discord, live Notion, or
  host-mutating flows unless the operator explicitly authorizes them later.
- Do not edit Hermes core. Use ArcLink wrappers, plugins, hooks, generated
  config, services, docs, and tests.
- Keep public repo artifacts free of references to any external fictional
  inspiration/franchise. Product terms such as `Limited 100 Founders` are
  allowed because they are SKU/copy terms; do not explain or expand them into
  lore. The desired feeling should be achieved through restrained product
  voice, names, flow, and visual treatment, not explicit references.
- Treat "Almanac" as the knowledge-store lineage/name only. ArcLink is the
  product. Almanac is not the current top-level product identity.
- Apply the Mandate of Inquiry: for every meaningful hole, record at least
  three distinct possible product/implementation interpretations when three
  exist, name the unknowns, and ask a concrete operator-policy question if code
  cannot decide.
- Under no circumstances should one logged-in user or public visitor be able to
  read, mutate, route to, or infer another user's private data, services,
  dashboard, channels, agent inventory, Chutes keys, Stripe state, Notion state,
  vault resources, linked shares, or Hermes dashboard resources unless an
  explicit accepted share grants only the intended resource.

## Must-Inspect Surfaces

Use `rg` and focused file reads. At minimum inspect:

- Web/API: `web/src/**`, `web/tests/**`, `python/arclink_hosted_api.py`,
  `python/arclink_api_auth.py`, `python/arclink_dashboard.py`,
  `python/arclink_product.py`, `python/arclink_product_surface.py`.
- Public bots and channel state: `python/arclink_public_bots.py`,
  `python/arclink_telegram.py`, `python/arclink_discord.py`,
  public bot docs/tests.
- Private Curator onboarding: `python/arclink_onboarding_flow.py`,
  `python/arclink_onboarding_completion.py`,
  `python/arclink_enrollment_provisioner.py`, related tests.
- Control/provisioning/billing/execution: `python/arclink_control.py`,
  `python/arclink_provisioning.py`, `python/arclink_executor.py`,
  `python/arclink_action_worker.py`, `python/arclink_entitlements.py`,
  `python/arclink_fleet.py`, `python/arclink_rollout.py`, deploy/compose docs.
- Knowledge rails: `python/arclink_mcp_server.py`,
  `python/arclink_memory_synthesizer.py`, `python/arclink_notion_ssot.py`,
  `python/arclink_notion_webhook.py`, `python/arclink_ssot_batcher.py`,
  `bin/qmd-*.sh`, `bin/vault-watch.sh`, `bin/memory-synth.sh`,
  managed-context plugin, qmd/Notion/SSOT tests.
- Memory cherrypick study:
  `research/RALPHIE_MEMORY_SYSTEM_CHERRYPICK_STUDY.md`,
  `plugins/hermes-agent/arclink-managed-context/**`,
  `python/arclink_memory_synthesizer.py`, and memory-related sections/tests in
  `python/arclink_control.py`. The only permitted private-state exception for
  this study is the mirrored, non-secret Hermes docs reference corpus at
  `arclink-priv/state/hermes-docs-src/plugins/memory/**`; do not inspect
  unrelated `arclink-priv/` state.
- Hermes dashboard plugins: `plugins/hermes-agent/drive/**`,
  `plugins/hermes-agent/code/**`, `plugins/hermes-agent/terminal/**`,
  installer/refresh scripts and plugin tests.
- Operator setup: `deploy.sh`, `bin/deploy.sh`, `compose.yaml`,
  `docs/docker.md`, `docs/arclink/sovereign-control-node.md`,
  `docs/arclink/ingress-plan.md`,
  `docs/arclink/control-node-production-runbook.md`.
- Docs and creative/source-of-truth: `README.md`, `AGENTS.md`,
  `docs/DOC_STATUS.md`, `docs/arclink/CREATIVE_BRIEF.md`,
  `docs/arclink/raven-public-bot.md`, `docs/arclink/first-day-user-guide.md`,
  `docs/arclink/notion-human-guide.md`, `docs/arclink/data-safety.md`.

## Product Truth Claims To Verify

For each item, write `real|partial|gap|proof-gated|policy-question`, with file
references and line numbers where possible.

## Operator Policy Update - 2026-05-08

Use `research/OPERATOR_POLICY_DECISIONS_20260508.md` as the canonical answer to
the remaining policy questions. Reclassify affected rows from
`policy-question` into `real`, `partial`, `gap`, or `proof-gated` based on
actual code/tests, then repair the local buildable gaps.

- Raven identity must support per-user/per-channel Raven bot-name
  customization, in addition to selected-agent labels.
- SSOT sharing uses shared-root membership as the canonical Notion model.
- Failed renewal suspends provider/API access immediately, warns immediately
  and daily, escalates to account/data-removal language after day 7, and queues
  irreversible purge on day 14 only after warning delivery is attempted and
  audited.
- Drive sharing must expose living linked files/directories, not copied
  snapshots. Recipients may copy/duplicate accepted content into their own
  Vault or Workspace, but the accepted `Linked` root remains non-reshareable.
- Browser right-click sharing should use ArcLink grants backed by a live shared
  root. Prefer a Nextcloud/WebDAV/OCS-backed adapter where Nextcloud is enabled;
  otherwise keep the browser UI disabled or build a live ArcLink broker.
- The operator model is exactly one operator.
- Chutes fallback is a separate per-user Chutes account/OAuth session when
  per-key metering cannot be proven. Refuel Pod credits are a real product
  direction and need local SKU/config/credit accounting before shipped copy.

### Entry, Payment, Deployment, Credentials

- Users can start onboarding from website, Telegram, or Discord.
- Users pay before deployment starts; Stripe payment/entitlement webhook is the
  gate that permits provisioning.
- After deployment is ready, the user is notified.
- Credentials and dashboard links are shown to the user, with explicit "copy
  and safely store" instructions.
- The user confirms they stored credentials, then ArcLink removes/hides the
  credential material from future API/UI/bot responses.
- The user can enter the user dashboard from the site.
- The user can go directly to the Hermes dashboard from a stored link and log
  in there.
- The Hermes dashboard experience lands inside the real Hermes dashboard, not a
  placeholder or dead link.

### Knowledge, Almanac, Notion, Memory

- Each user/agent has a vault.
- qmd indexes vault files and generated PDF/Notion markdown.
- Notion is the SSOT rail and has webhook/listener flow into indexing.
- Memory synthesis gathers vault directories/files, Notion SSOT content, and
  "daily plate" materials into memory stubs.
- The managed-context Hermes plugin ingests memory stubs, including
  `[managed:recall-stubs]`.
- Memory stubs tell agents that knowledge exists without dumping all knowledge
  into context; agents should use qmd-backed MCP tools for depth.
- The qmd-backed knowledge store may be called Almanac in lineage/lore, but
  ArcLink is the product. Make all docs and managed-memory text clear:
  Almanac is a knowledge store/rail, not a separate current product.
- The preferred retrieval skill/tool path is ArcLink MCP
  `knowledge.search-and-fetch`, `vault.search-and-fetch`, `vault.fetch`,
  `notion.search-and-fetch`, `notion.fetch`, `ssot.read`, and `ssot.write`;
  do not tell agents to rummage raw files first.
- ArcLink managed context is a governed awareness/routing layer, not a generic
  conversational memory replacement. It should remain complementary to
  optional Hermes memory plugins such as mem0, Supermemory, Honcho, Hindsight,
  Holographic, OpenViking, RetainDB, or ByteRover.
- Evaluate cherrypicks from the memory study without replacing ArcLink's SSOT
  posture:
  1. normalized trust/confidence and contradiction/disagreement signals on
     memory synthesis cards,
  2. explicit `low|mid|high` recall budget tiers,
  3. cheap-layer versus expensive-layer managed-context injection cadence,
  4. a local-only/non-LLM synthesis fallback,
  5. optional conversational-memory extension points that cannot bypass user
     isolation, brokered SSOT writes, or private-state boundaries,
  6. scoped agent self-model or peer-awareness cards for multi-agent work,
     marked as policy-question unless existing code proves a safe path.
- Do not add broad auto-capture of every Hermes turn into ArcLink governed
  memory unless the operator makes that product/security decision explicitly.

### Raven, Public Bots, Channel Linking, Agent Switching

- Telegram and Discord are public-facing channels.
- Users can onboard there with Raven, the ArcLink Curator.
- Raven is the control bot conduit for user activity with their agents after
  onboarding, not only a prelaunch/prepayment greeter.
- The user can call up an inventory of agents.
- The user can switch the currently selected agent at any time.
- Replies clearly indicate which agent the user is speaking with.
- `TG` and Discord surfaces can show or otherwise distinguish the current
  selected agent for that user/channel.
- Users can customize Raven's displayed name per user/channel if platform APIs
  support it; if not, the product must use a reliable visible distinction such
  as selected-agent labels in each response.
- Swapping agents must be easy, preferably `/agents` plus buttons.
- New channel linking: a user on Telegram can initiate a link to Discord, or
  vice versa, using a canonical command such as `/link-channel` with aliases for
  likely typos and platform-safe names. The user gets a temporary code/window,
  contacts Raven on the other channel, chooses continue linking, pastes the
  code, and the linked account/channel list grows. Channel IDs may be user IDs
  or channel IDs because Hermes listens through explicit channel identifiers.

### Plans, Pricing, Expansion, Entitlements

- Limited 100 Founders: `$149/mo`, Sovereign-equivalent.
- Sovereign: `$199/mo`, single agent plus ArcLink systems.
- Scale: `$275/mo`, three agents plus ArcLink systems plus Federation.
- Agent Expansion:
  - Sovereign additional agent: `$99/mo`.
  - Scale additional agent: `$79/mo`.
- Pricing copy, API defaults, Stripe price env names, bot labels, web labels,
  entitlement counts, and tests agree.
- Stripe payments are the system of record; deployment proceeds only after
  payment is posted back.
- Failed renewal lifecycle exists or is designed truthfully:
  1. Renewal fails.
  2. User's Chutes/API access is suspended or removed from the operator account
     until billing is satisfied.
  3. Raven warns once daily.
  4. After one week unpaid, warnings explicitly mention account/data removal.
  5. After 14 days unpaid, agent deployment data is purged and unrecoverable
     only after the documented warning policy has run.

### Drive/Code/Terminal And Sharing

- Hermes dashboard ships with Drive, Code, and Terminal plugins enabled by
  ArcLink.
- Those plugins should be able to run independently from ArcLink when copied as
  Hermes community plugins, with graceful behavior when ArcLink-specific APIs
  are absent.
- New drive sharing: from Drive or Code, a user/agent can right-click a file or
  directory under Vault or Workspace and generate an ArcLink share link.
- The same share link flow is available by asking an agent through Raven to use
  an ArcLink Drive Sharing skill/tool for a named file/directory.
- The recipient must be logged into their own ArcLink account before accepting.
- The recipient accepts the share, then Raven notifies the sharing user and
  asks Approve or Deny before finalizing.
- Accepted linked resources cannot be reshared by the receiving agent/user.
- Recipients may copy or duplicate accepted content into their own Vault or
  Workspace. This creates their own copy; it does not alter the living linked
  grant or allow resharing from `Linked`.
- Linked ArcLink resources appear as a third navigation root named `Linked` or
  `Linked directory` in Drive and Code, below Vault and Workspace.
- Cross-user shares must be path-contained, audit logged, revocable, and scoped
  to the accepted file/directory only.
- Accepted shares must be living linked files/directories. A copied projection
  may be a temporary internal fallback, but it must not be represented as the
  completed product promise.
- For browser right-click sharing, evaluate Nextcloud OCS Share API plus WebDAV
  as the preferred enabled-backend path, while keeping ArcLink approval,
  account login, audit, revoke, no-reshare, and isolation above Nextcloud.

### Operator Setup, Ingress, Fleet, Admin

- Operator setup starts the Control Node and asks for deployment style:
  single-machine, distributed machinery through Hetzner, or distributed
  machinery through Akamai Linode.
- Operator can choose Tailscale or Cloudflare ingress/networking.
- Cloudflare setup verifies the account can manage the named domain/zone before
  treating connectivity as ready.
- Tailscale setup verifies connectivity/cert/serve state before treating access
  as ready.
- The operator can manage all deployments, billing, activity, health, and
  queued actions in the admin dashboard.
- There is exactly one operator. If the code supports multiple admin users,
  constrain it, hide multi-admin mechanics as internal-only, or add a
  migration-safe single-operator enforcement path.
- A user can see only their own deployment/service health and accepted shared
  resources.
- User/admin dashboards remain Next.js + Tailwind and should respect the
  existing brand guide. The logged-in user and admin portals currently need a
  higher-care UI/UX pass: denser operational surfaces, clearer hierarchy,
  service status, billing state, agent inventory, knowledge/SSOT readiness,
  linked channels, and recovery actions.

### Notion SSOT Setup Choices

- After credential confirmation/removal, Raven explains resources and offers a
  `Setup SSOT` button/action.
- SSOT setup explains that ArcLink connects Notion for all agents under the
  user, and linked agents share the SSOT rail through shared-root membership.
- Setup verifies connectivity and page/share correctness using the same quality
  bar as the earlier Almanac system.
- Canonical Notion integration model:
  1. Control plane owns a shared root and users claim/attach scoped pages via
     shared-root membership.
  2. User-created page sharing to a control-plane email/integration and
     user-owned token/OAuth are research/future alternatives, not the default
     product path.
- Do not claim email sharing is enough for API read/write unless verified.
  Notion API permissions may still require an integration token and explicit
  page sharing. Mark this proof-gated or ask a policy question if code cannot
  verify.
- Users share SSOT through shared-root membership. Do not build independent
  SSOT accept/approval rails unless a later policy changes the model.

### Upgrades And Component Control

- Upgrades to Hermes and other pinned components are controlled by ArcLink
  Control Node/operator flows, not unmanaged Hermes defaults.
- A user/operator command such as `/upgrade-hermes` or platform-safe
  `/upgrade_hermes` should route to ArcLink's correct `hermes-agent` upgrade
  check/apply path.
- Remove, suppress, or override unsafe/default Hermes upgrade commands that
  were registered during first contact if they bypass ArcLink's pinned upgrade
  path.

### Chutes API Key Lifecycle

- Each paying user should receive isolated Chutes/API credentials or an
  equivalent isolated provider lane.
- Desired future path: operator account/IDP/SSOT permissioning allows the
  control plane to create per-user Chutes API keys after an operator-approved
  login/handshake.
- API key usage must be limited to a budget/balance covered by the user's plan,
  setup, and recurring charges.
- API-key or account usage must be monitored against a max utilization
  threshold. When a user approaches or crosses the threshold, Raven and the
  dashboard should advise one of the safe continuation paths:
  - add another provider through Hermes `/provider` or the ArcLink provider
    settings flow,
  - buy inference a la carte as an add-on,
  - buy an `ArcLink Refuel Pod` to get through the overage window.
- Verify whether ArcLink can use `https://github.com/chutesai/chutes-api` with
  the operator account to read per-API-key utilization and create/rotate/remove
  keys. Public repo inspection on 2026-05-08 found key create/list/delete
  endpoints and `last_used_at`, but usage accounting appears user/chute/bucket
  based rather than per-key. Treat per-key metering as proof-gated until an
  authorized live/sandbox account proves otherwise.
- Verify whether `https://github.com/Veightor/chutes-agent-toolkit` can supply
  the safer adapter path. Public repo inspection on 2026-05-08 confirmed the
  repository exists and its README describes Chutes account/API-key management,
  usage/quota tools, and Hermes-compatible skills, but several write surfaces
  are labeled beta there; treat this as an integration candidate, not shipped
  ArcLink truth.
- If per-key usage is not available from the operator account, use a separate
  Chutes account/OAuth session per ArcLink user. In that model ArcLink monitors
  the whole account, suspends or refuels at the account boundary, and keeps
  operator/customer isolation explicit.
- `ArcLink Refuel Pod` is the working product name for paid top-ups. Ralphie
  must add pricing/config/API/docs surfaces for it before public UI claims it
  is purchasable. Use the research addendum's `$25/$75/$150` pod model unless
  tests or current pricing make it unsafe.
- If live Chutes key creation cannot be verified locally, implement or document
  a fail-closed adapter boundary with fake tests and mark live creation
  proof-gated. Do not invent an unaudited credential workflow.

## Required Deliverables

1. A product reality matrix in `research/` that covers every claim above.
2. An updated implementation plan/backlog with unchecked tasks for every
   `partial`, `gap`, `proof-gated`, or `policy-question` item.
3. Code/tests for high-priority local gaps, especially:
   - user isolation,
   - channel linking,
   - agent inventory/switching,
   - payment-gated deployment truth,
   - credential reveal/ack/removal,
   - drive/share model and plugin roots,
   - Notion/SSOT setup truth,
   - memory trust/contradiction signals, recall-budget tiers, and
     managed-context cadence where locally repairable,
   - billing renewal/suspension warning lifecycle,
   - admin/user dashboard entitlement and health visibility.
4. Docs that say only what is real, partial, or proof-gated.
5. Focused validation output in `research/BUILD_COMPLETION_NOTES.md` or a new
   completion note.

## Build Priority Order

### Priority 0: Truth Matrix And Safety Invariants

- [x] Build the product reality matrix with file/line evidence for every claim.
- [x] Add/verify regression tests that logged-in users cannot access another
  user's dashboard data, Hermes links, agent inventory, channels, shares,
  Notion/SSOT state, provider state, Stripe state, or deployment health.
- [x] Identify every live/proof-gated claim and remove any shipped-language
  overclaim from public docs/UI.

### Priority 1: Paid Onboarding, Credential Handoff, Dashboard Access

- [x] Verify and repair website, Telegram, and Discord onboarding starts.
- [x] Verify and repair Stripe payment gating before deployment/provisioning.
- [x] Verify and repair deployment-ready notification.
- [x] Verify and repair credential reveal, "copy and safely store", user
  confirmation, and post-confirmation removal/hiding.
- [x] Verify and repair user dashboard and direct Hermes dashboard entry.

### Priority 2: Raven As Control Conduit

- [x] Verify and repair Raven's post-onboarding role as user-to-agent control
  conduit.
- [x] Verify and repair agent inventory and selected-agent switching through
  `/agents` with clear current-agent labels.
- [x] Verify and repair Telegram/Discord channel linking with `/link-channel`
  plus aliases, code window, claim on other channel, and growing linked-channel
  inventory.

### Priority 3: Knowledge, Almanac, SSOT, Memory

- [x] Verify and repair vault/qmd/Notion/webhook indexing story end to end.
- [x] Verify and repair memory synthesis inputs: vault, notion-shared/SSOT, and
  daily plate materials.
- [x] Verify and repair managed memory stubs and MCP retrieval guidance.
- [x] Incorporate
  `research/RALPHIE_MEMORY_SYSTEM_CHERRYPICK_STUDY.md` into the truth matrix:
  classify ArcLink's memory layer and each cherrypick as `real`, `partial`,
  `gap`, `proof-gated`, or `policy-question`.
- [x] Verify or add structured trust/confidence and contradiction/disagreement
  signals for memory synthesis cards and recall-stub rendering.
- [x] Verify or add explicit managed-context recall budget tiers such as
  `ARCLINK_MANAGED_CONTEXT_RECALL_BUDGET=low|mid|high`, with tests that low
  budget preserves retrieval routing and safety guardrails.
- [x] Verify or design cheap-layer versus expensive-layer managed-context
  cadence, including telemetry for why each layer injected.
- [x] Evaluate a local-only/non-LLM synthesis fallback and mark it truthfully
  if it remains a design/backlog item.
- [x] Document optional conversational-memory plugin stacking as a sibling
  capability, not a replacement for ArcLink managed context, with isolation and
  SSOT-governance caveats.
- [x] Evaluate agent self-model and multi-agent peer-awareness cards as a
  scoped/audited policy-question; do not expose cross-agent transcripts or
  private data through memory.
- [x] Clarify Almanac as knowledge store/lineage only across docs/context.
- [x] Verify and repair Setup SSOT post-credential flow and Notion integration
  options without overclaiming email-share sufficiency.

### Priority 4: Drive Sharing And Plugin Independence

- [x] Design and implement or honestly mark proof-gated the ArcLink drive-share
  model: create link, logged-in accept, owner Raven approve/deny, final mount,
  no reshare, copy/duplicate option, audit, revoke.
- [x] Expose accepted linked resources as a third `Linked` root in Drive and
  Code.
- [x] Ensure Drive, Code, and Terminal plugins degrade gracefully when copied
  outside ArcLink.

### Priority 5: Plans, Billing, Chutes, Renewal Lifecycle

- [x] Verify and repair Founders/Sovereign/Scale/Expansion pricing consistency.
- [x] Verify and repair entitlement counts and agent expansion rules.
- [x] Define or implement the Chutes per-user key adapter boundary, budget
  limits, and proof-gated live handshake.
- [x] Verify or design Chutes utilization monitoring: per-API-key usage if
  available from operator credentials, otherwise per-user Chutes account usage.
- [x] Truthfully model utilization-threshold notifications, provider
  fallback guidance through Hermes `/provider`, and `ArcLink Refuel Pod`
  a-la-carte top-up purchase flow as policy/proof-gated until operator policy
  and live Chutes usage proof exist.
- [x] Implement failed-renewal provider suspension and truthfully model daily
  Raven reminders, one-week removal warning, and 14-day purge policy.

### Priority 6: Operator Setup, Fleet, Ingress, Admin/User UX

- [x] Verify and repair operator setup choices: single machine, Hetzner, Akamai
  Linode.
- [x] Verify and repair Cloudflare/Tailscale verification gates.
- [x] Record one-operator behavior as a policy-question while preserving the
  current multi-admin truth in auth, UI, docs, and tests.
- [x] Improve logged-in user and admin dashboard UI/UX while preserving Next.js
  + Tailwind and the existing brand direction.
- [x] Verify and repair user-only health visibility and operator all-system
  power.

### Priority 7: Upgrade Control

- [x] Verify and repair Hermes/component upgrades through ArcLink control-plane
  flows.
- [x] Add `/upgrade-hermes` and platform-safe `/upgrade_hermes` routing if
  missing.
- [x] Remove/suppress/override unsafe default Hermes upgrade command exposure
  when it bypasses ArcLink pinned upgrades.

### Priority 8: Operator Policy Resolution Pass

- [x] Reclassify the 2026-05-08 operator policy decisions in
  `research/OPERATOR_POLICY_DECISIONS_20260508.md` across the product matrix,
  implementation plan, build gate, docs, UI, and tests.
- [x] Implement or honestly mark partial/gated per-user/per-channel Raven
  display-name customization beyond selected-agent labels.
- [x] Align SSOT sharing around shared-root membership and demote user-owned
  OAuth/token and email-share-only paths to non-default research/proof-gated
  alternatives.
- [x] Implement the failed-renewal warning cadence and purge policy:
  immediate suspension, immediate notice, daily reminders, day-7 removal
  warning, and day-14 audited purge queue.
- [x] Replace copied-share completion claims with living linked-resource
  behavior. Prefer a Nextcloud/WebDAV/OCS adapter where enabled; otherwise keep
  browser right-click sharing disabled until a live ArcLink broker exists.
- [x] Add recipient copy/duplicate actions from accepted `Linked` resources
  into the recipient's own Vault or Workspace while preserving no-reshare on
  the linked grant.
- [x] Enforce exactly one operator or make all multi-admin mechanics
  internal-only/subordinate to the single-operator policy.
- [x] Add Chutes Refuel Pod local SKU/config/credit accounting using fair
  provider-budget credits, while keeping live purchase and live Chutes balance
  application proof-gated.
- [x] Prefer per-user Chutes account/OAuth fallback when per-key metering is
  unavailable; keep per-key usage proof gated until an authorized Chutes
  account proves it.

## Validation Floor

Run focused tests for touched surfaces. Likely suites include:

```bash
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_public_bots.py
python3 tests/test_arclink_onboarding_prompts.py
python3 tests/test_arclink_enrollment_provisioner_regressions.py
python3 tests/test_arclink_plugins.py
python3 tests/test_arclink_mcp_schemas.py
python3 tests/test_arclink_notion_knowledge.py
python3 tests/test_memory_synthesizer.py
python3 tests/test_arclink_docker.py
python3 tests/test_deploy_regressions.py
python3 tests/test_health_regressions.py
python3 tests/test_documentation_truths.py
```

For web/dashboard work:

```bash
cd web
npm test
npm run lint
npm run build
npm run test:browser
```

Always run:

```bash
git diff --check
bash -n deploy.sh bin/*.sh test.sh
python3 -m py_compile <touched python files>
```

Heavy/live checks remain proof-gated unless the operator explicitly authorizes
them.
