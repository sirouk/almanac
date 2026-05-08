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
  Workspace if policy allows.
- Linked ArcLink resources appear as a third navigation root named `Linked` or
  `Linked directory` in Drive and Code, below Vault and Workspace.
- Cross-user shares must be path-contained, audit logged, revocable, and scoped
  to the accepted file/directory only.

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
  decide whether to constrain it, document it as internal-only, or ask a policy
  question.
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
  user, and linked agents share the SSOT rail according to policy.
- Setup verifies connectivity and page/share correctness using the same quality
  bar as the earlier Almanac system.
- Evaluate possible Notion integration models:
  1. User creates/shares a Notion page to a control-plane email/integration.
  2. User configures a Notion integration token/connectivity directly.
  3. Control plane owns a shared root and users claim/attach scoped pages.
- Do not claim email sharing is enough for API read/write unless verified.
  Notion API permissions may still require an integration token and explicit
  page sharing. Mark this proof-gated or ask a policy question if code cannot
  verify.
- Users should be able to share their SSOT where policy permits, but only
  through explicit scoped share/accept/approval rails.

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
   - billing renewal/suspension warning lifecycle,
   - admin/user dashboard entitlement and health visibility.
4. Docs that say only what is real, partial, or proof-gated.
5. Focused validation output in `research/BUILD_COMPLETION_NOTES.md` or a new
   completion note.

## Build Priority Order

### Priority 0: Truth Matrix And Safety Invariants

- [ ] Build the product reality matrix with file/line evidence for every claim.
- [ ] Add/verify regression tests that logged-in users cannot access another
  user's dashboard data, Hermes links, agent inventory, channels, shares,
  Notion/SSOT state, provider state, Stripe state, or deployment health.
- [ ] Identify every live/proof-gated claim and remove any shipped-language
  overclaim from public docs/UI.

### Priority 1: Paid Onboarding, Credential Handoff, Dashboard Access

- [ ] Verify and repair website, Telegram, and Discord onboarding starts.
- [ ] Verify and repair Stripe payment gating before deployment/provisioning.
- [ ] Verify and repair deployment-ready notification.
- [ ] Verify and repair credential reveal, "copy and safely store", user
  confirmation, and post-confirmation removal/hiding.
- [ ] Verify and repair user dashboard and direct Hermes dashboard entry.

### Priority 2: Raven As Control Conduit

- [ ] Verify and repair Raven's post-onboarding role as user-to-agent control
  conduit.
- [ ] Verify and repair agent inventory and selected-agent switching through
  `/agents` with clear current-agent labels.
- [ ] Verify and repair Telegram/Discord channel linking with `/link-channel`
  plus aliases, code window, claim on other channel, and growing linked-channel
  inventory.

### Priority 3: Knowledge, Almanac, SSOT, Memory

- [ ] Verify and repair vault/qmd/Notion/webhook indexing story end to end.
- [ ] Verify and repair memory synthesis inputs: vault, notion-shared/SSOT, and
  daily plate materials.
- [ ] Verify and repair managed memory stubs and MCP retrieval guidance.
- [ ] Clarify Almanac as knowledge store/lineage only across docs/context.
- [ ] Verify and repair Setup SSOT post-credential flow and Notion integration
  options without overclaiming email-share sufficiency.

### Priority 4: Drive Sharing And Plugin Independence

- [ ] Design and implement or honestly mark proof-gated the ArcLink drive-share
  model: create link, logged-in accept, owner Raven approve/deny, final mount,
  no reshare, copy/duplicate option, audit, revoke.
- [ ] Expose accepted linked resources as a third `Linked` root in Drive and
  Code.
- [ ] Ensure Drive, Code, and Terminal plugins degrade gracefully when copied
  outside ArcLink.

### Priority 5: Plans, Billing, Chutes, Renewal Lifecycle

- [ ] Verify and repair Founders/Sovereign/Scale/Expansion pricing consistency.
- [ ] Verify and repair entitlement counts and agent expansion rules.
- [ ] Define or implement the Chutes per-user key adapter boundary, budget
  limits, and proof-gated live handshake.
- [ ] Implement or truthfully model failed-renewal lifecycle: suspend provider
  access, daily Raven reminders, one-week removal warning, 14-day purge policy.

### Priority 6: Operator Setup, Fleet, Ingress, Admin/User UX

- [ ] Verify and repair operator setup choices: single machine, Hetzner, Akamai
  Linode.
- [ ] Verify and repair Cloudflare/Tailscale verification gates.
- [ ] Verify and repair one-operator policy.
- [ ] Improve logged-in user and admin dashboard UI/UX while preserving Next.js
  + Tailwind and the existing brand direction.
- [ ] Verify and repair user-only health visibility and operator all-system
  power.

### Priority 7: Upgrade Control

- [ ] Verify and repair Hermes/component upgrades through ArcLink control-plane
  flows.
- [ ] Add `/upgrade-hermes` and platform-safe `/upgrade_hermes` routing if
  missing.
- [ ] Remove/suppress/override unsafe default Hermes upgrade command exposure
  when it bypasses ArcLink pinned upgrades.

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

