# ArcLink User Journey Atlas

This atlas is the intended end-to-end ArcLink story, grounded in the current
repository. It describes how the product should feel when the intended rails
are in place, while separating locally `real` contracts from proof-gated live
behavior.

Future agents should read this file as the experience story, not as launch
certification. Follow the sections in order to understand what a Captain,
Agent, Raven, Crew, and Operator should see; then use each status callout and
the final gap pointers to jump into `GAPS.md` before planning implementation or
claiming readiness.

Document ownership is split deliberately:

- `USER_JOURNEY.md` owns the readable journey and source-grounded handoffs.
- `GAPS.md` owns taxonomy, severity, gap IDs, policy questions, and proof-gate
  IDs.
- `research/COVERAGE_MATRIX.md` owns the `J-##` audit map from journey joints to
  source areas and tests.

Fast handoff for future agents:

1. Read "Whole System Map" and "One-Page Journey" before touching code. They
   define the intended human experience and the mode boundaries.
2. Use each numbered journey section to understand what the Captain, Raven,
   Agent, Crew, and Operator should experience when the rails work.
3. Treat every status callout as a claim boundary. If a status says
   `proof-gated`, do not relabel it `real` without the matching `PG-*` evidence
   in `GAPS.md`.
4. Before planning implementation, open `GAPS.md` and start from the P0/P1 rows,
   not from the most optimistic product copy or older research matrices.

Document-phase closeout rule: this atlas is complete for public handoff when a
future agent can retell the intended ArcLink experience from these sections,
can identify every proof-gated or policy-gated live claim without inference, and
can move directly to `GAPS.md` for implementation planning. It is not meant to
close live proof, policy, or security-hardening work by description.

Reviewer acceptance checklist for this atlas:

- The reader can name the three operating modes and keep Control Node,
  Shared Host, and Shared Host Docker separate.
- The reader can follow the Captain path from public entry through Raven,
  checkout, provisioning, dashboard, Hermes workspace, sharing, provider
  state, operations, and recovery.
- The reader can identify where the intended story changes from locally `real`
  source behavior to `partial`, `proof-gated`, or `policy-question` behavior.
- The reader can hand implementation planning to `GAPS.md` without rereading
  research notes or optimistic product matrices.
- The reader cannot reasonably infer that credentialed production proof,
  provider proof, public-bot delivery, Notion verification, backup restore, or
  upgrade proof passed during this document phase.

Evidence labels in this file use the canonical `GAPS.md` taxonomy. Narrative
status callouts mainly use `real`, `partial`, `proof-gated`, and
`policy-question`; `GAPS.md` owns the full status list and definitions.

Primary steering requires this document to include happy paths, alternate
choices, dead ends, recovery paths, access boundaries, and cross-system
handoffs, and requires live behavior to stay proof-gated until proven
(`research/RALPHIE_ARCLINK_USER_JOURNEY_AND_GAPS_STEERING.md:53-94`).

## Atlas Crosswalk

| Atlas section | Journey joints preserved |
| --- | --- |
| Public Entry | `J-01`, `J-02`, `J-03`, `J-05` |
| Raven Onboarding And Control | `J-03`, `J-04`, `J-18`, `J-24` |
| Billing, Entitlement, Refuel | `J-05`, `J-06`, `J-07`, `J-08` |
| Provisioning And Deployment | `J-09`, `J-10`, `J-11`, `J-17` |
| Credential Handoff | `J-12`, `J-13` |
| User Dashboard | `J-13`, `J-14`, `J-24` |
| Hermes And Agents | `J-18`, `J-19`, `J-25` |
| Knowledge, Notion, SSOT, Memory | `J-21`, `J-22`, `J-23` |
| Workspace, Linked Resources, Sharing | `J-19`, `J-20` |
| Pod Comms, Wrapped, Crew Training | `J-20`, `J-24` |
| Admin And Operator Journey | `J-14`, `J-15`, `J-16`, `J-17`, `J-25`, `J-26`, `J-27` |
| Security And Isolation Contract | `J-28` |
| Recovery Atlas | `J-02`, `J-06`, `J-09`, `J-12`, `J-20`, `J-26`, `J-27` |

## Whole System Map

ArcLink has three operating modes, and the journey must not collapse them into
one mental model.

1. Sovereign Control Node is the paid self-serve product path. Users enter from
   web, Telegram, or Discord, complete Stripe checkout, and receive an ArcPod
   deployed onto a fleet host. It owns hosted API, public web, public bot
   webhooks, Stripe, fleet placement, provisioning, dashboards, and admin
   operations (`docs/arclink/sovereign-control-node.md:3-7`,
   `docs/arclink/sovereign-control-node.md:21-36`).
2. Shared Host is the operator-led systemd path for Curator, enrolled Unix
   users, per-user Hermes homes, shared vault, qmd, Notion, backups, and live
   host repairs. Its canonical commands are still the bare `deploy.sh` commands
   in the agent operating guide.
3. Shared Host Docker is containerized validation of the shared-host substrate,
   not the paid ArcPod control surface. Control Node work uses
   `./deploy.sh control ...`, while shared-host Docker uses
   `./deploy.sh docker ...` (`docs/arclink/sovereign-control-node.md:42-49`,
   `docs/arclink/control-node-production-runbook.md:29-32`).

The actor names are part of the product contract. The paying owner is the
Captain. Raven is the public guide. A Hermes-powered occupant is an Agent. A
Captain's Agents are Crew. Operator is reserved for admin/deploy/back-office
surfaces.

Production live proof is not claimed. The README says the foundation is
implemented and tested, but the full live journey is blocked until real Stripe,
ingress, inference provider, Telegram, Discord, and production host credentials
are supplied (`README.md:26-31`). The live proof document states no
credentialed live E2E journey has been proven yet
(`docs/arclink/live-e2e-secrets-needed.md:3-22`).

## One-Page Journey

When the intended rails are in place, a Captain meets Raven through web,
Telegram, or Discord; Raven captures only safe onboarding answers, opens
checkout, and keeps recovery/status controls visible. Payment unlocks
provisioning, the Control Node places an ArcPod on a fleet host, renders the
deployment intent, applies the chosen ingress path, and queues a handoff when
health checks report ready.

The Captain then moves from public chat into the dashboard and Hermes workspace.
The dashboard shows billing, provisioning, credentials, provider state, service
links, workspace readiness, recovery actions, communications, sharing, Wrapped,
and Crew training. Hermes hosts the Agent experience with Drive, Code, Terminal,
qmd/vault retrieval, Notion/SSOT rails, memory synthesis, managed context, and
safe refresh/install defaults. Raven remains the public control layer for
status, Agent selection, channel linking, backup prep, Notion prep, share
approval, refuel, and managed upgrade guidance.

The hard boundary is equally important: today this is a source-grounded journey
atlas, not live launch certification. Local control/API/dashboard/plugin
contracts can be called `real` only where the cited source and tests support
them. Stripe, public bots, fleet apply, ingress, provider inference, Notion
permissions, Hermes browser proof, restore drills, and upgrades remain governed
by the proof gates in `GAPS.md`.

## Vision Lens

The lore of ArcLink is that a Captain should not have to assemble an AI
company, a cloud platform, a private knowledge base, a bot fleet, a billing
system, and an operations team by hand. Raven makes the first contact feel
small: answer a few human questions, choose a launch lane, pay, and watch a
private ArcPod come online. Under that simple surface, ArcLink is quietly
creating Unix/runtime boundaries, bot channels, provider rails, dashboards,
workspace tools, memory, retrieval, SSOT, backups, health, and operator
evidence.

That is the mind-blowing part the journey must preserve: the user experiences
one coherent guide and one owned workspace, while the system joins many hard
surfaces without asking the user to understand them. The equally important
truth is that magic cannot be marketing fiction. Every place where the current
repository still needs live proof, policy, or regression repair stays labeled
in `GAPS.md`. The former broad local validation blocker, `GAP-025`, is locally
closed only while the uncapped no-secret Python suite remains green.

## 1. Public Entry

### Happy Path

A new Captain can arrive through the website, Telegram, or Discord. The public
web route presents the ArcLink product shell and starts onboarding through
`POST /api/v1/onboarding/start`. Telegram and Discord enter through hosted
webhook routes that dispatch to the same public bot engine
(`docs/arclink/sovereign-control-node.md:51-70`,
`python/arclink_hosted_api.py:2961-2974`).

The intended entry surface is responsive across desktop and mobile: web is the
desktop/card-payment path, while Telegram and Discord are first-class mobile
chat paths. Repository-level docs describe responsive dashboards and a
secret-gated live proof harness (`README.md:3-9`); mobile browser proof for the
real deployed workspace remains part of the workspace proof gate.

Raven's first job is not to recite infrastructure. Raven names the action,
helps the Captain choose a plan, asks the minimum onboarding questions, and
opens checkout. The public bot story rail says checkout hires the first Agent
and moves onboarding into the launch queue (`docs/arclink/raven-public-bot.md:7-18`).

### Choice Points

- Website: best for desktop and card/payment flow. The web onboarding page
  keeps non-proof resume context locally, while browser claim/cancel proof
  tokens are scoped to `sessionStorage` and cleared on success/cancel
  (`web/src/app/onboarding/page.tsx:96-155`,
  `web/src/app/checkout/success/page.tsx:73-99`,
  `web/src/app/checkout/cancel/page.tsx:51-80`). If the page is opened with
  `?channel=telegram` or `?channel=discord`, the channel is treated as an
  unlinked preference while onboarding remains web-scoped until a real platform
  identity is linked (`web/src/app/onboarding/page.tsx:83-94`,
  `web/src/app/onboarding/page.tsx:163-177`,
  `web/src/app/onboarding/page.tsx:293-335`).
- Telegram: good for fast public command/button flow. Production Telegram must
  register `callback_query` updates and use the secret-token header
  (`docs/arclink/raven-public-bot.md:132-136`,
  `docs/arclink/sovereign-control-node.md:58-63`).
- Discord: good for public bot interaction and later `/agent
  <message-or-command>` bridging because Discord cannot expose per-user active
  Agent command menus (`docs/arclink/raven-public-bot.md:41-44`).
- Returning visitor: onboarding tries to resume active web sessions by email or
  public channel identity before creating a new one
  (`python/arclink_onboarding.py:451-472`).

### Dead Ends And Recovery

If a web checkout is paused, the cancel page tries to mark the onboarding
session cancelled using the session-scoped cancel proof token, clears proof
material, and returns the user to resume without stale checkout state
(`web/src/app/checkout/cancel/page.tsx:51-80`,
`web/src/app/checkout/cancel/page.tsx:125-145`). If payment confirmation
or provisioning takes too long, the success page says the page can be closed and
Raven/dashboard status can continue (`web/src/app/checkout/success/page.tsx:203-210`).

If a public channel is not linked after onboarding, Raven can create a temporary
pairing code. Pairing refuses to overwrite a channel already linked to a
different account (`docs/arclink/raven-public-bot.md:103-108`,
`python/arclink_public_bots.py:3518-3759`).

Status: web and bot local flows are `real`, including the local
preferred-channel copy boundary; live Telegram/Discord delivery is
`proof-gated`.

## 2. Raven Onboarding And Control

### Happy Path

Raven asks for identity and Agent details, records a no-secret onboarding
session, rejects secret-looking values in public answers, and creates or resumes
durable session rows (`python/arclink_onboarding.py:421-554`). When the user
chooses a package, ArcLink reserves deployment rows in `entitlement_required`
state and opens Stripe Checkout with ArcLink metadata
(`python/arclink_onboarding.py:557-701`).

After the first ArcPod is active, Raven remains the public control conduit.
Normal post-onboarding messages in a linked channel queue selected-agent turns
for the active deployment, and Raven brings the Agent's final reply back to the
same channel (`docs/arclink/raven-public-bot.md:18-27`,
`python/arclink_public_bots.py:3374-3455`). The first normal message explains
that bare messages now route to the active Agent and that Raven controls remain
behind `/raven`.

### Controls

Raven supports status, account name, plan, checkout, Agent roster, selected
Agent switching, channel linking, Notion setup prep, backup prep, credential
handoff, share approval/acceptance, refuel, train-crew, Wrapped cadence, and
managed upgrade guidance (`docs/arclink/raven-public-bot.md:72-112`,
`python/arclink_public_bots.py:4930-4995`).

In active Telegram chats, Raven moves behind a selected Raven namespace, normally
`/raven`, while the active Agent owns the bare slash namespace. Discord keeps
global Raven commands and exposes `/agent <message-or-command>` as the active
Agent bridge (`docs/arclink/raven-public-bot.md:28-44`,
`docs/arclink/raven-public-bot.md:132-136`).

### Dead Ends And Recovery

- Capacity unavailable: checkout is blocked before Stripe and the user gets
  status/package buttons (`python/arclink_public_bots.py:1461-1486`).
- Not yet onboarded: account-aware commands return a "finish onboarding" style
  response rather than exposing private state
  (`python/arclink_public_bots.py:3767-3777`,
  `python/arclink_public_bots.py:3846-3856`).
- Unmanaged Hermes upgrades: Raven refuses direct `hermes update` and points to
  ArcLink-managed upgrade rails (`python/arclink_public_bots.py:4962-4995`).

Status: command routing and local queueing are `real`; live public bot
webhook registration, button delivery, and selected-agent runtime replies are
`proof-gated`.

## 3. Billing, Entitlement, Refuel

### Happy Path

The product plans are Limited 100 Founders, Sovereign, Scale, and additional
Agent expansion. Prices are rendered by config defaults in Compose and runbooks:
Founders $149/month, Sovereign $199/month, Scale $275/month, Sovereign
additional Agent $99/month, Scale additional Agent $79/month
(`compose.yaml:57-71`, `docs/arclink/raven-public-bot.md:63-70`).

Stripe checkout is the deployment gate. The local webhook handler verifies the
event signature, records idempotent webhook rows, maps supported subscription
events to entitlement state, advances paid deployments, and syncs onboarding to
`provisioning_ready` (`python/arclink_entitlements.py:508-790`,
`python/arclink_onboarding.py:799-838`). Failed payment keeps deployment blocked
and writes an audit row (`tests/test_arclink_entitlements.py:163-186`).

Refuel is a one-time Stripe Checkout path for ArcPod model budget. A successful
refuel webhook validates customer, client reference, Captain account, and target
deployment before credit is granted and applied
(`docs/arclink/llm-router.md:75-113`,
`tests/test_arclink_entitlements.py:766-828`).

Monthly paid invoices replenish included inference budget. The default allowance
is 20 percent of plan retail and is split across active Pods on the same plan
(`docs/arclink/llm-router.md:114-145`).

### Failure Lifecycle

When billing becomes non-current, ArcLink queues Raven/user notification
messages. The hosted API billing ping text says provider access pauses, daily
reminders continue, day 7 warns removal is next, and day 14 queues audited purge
of deployed Agent data (`python/arclink_hosted_api.py:780-804`). Cancellation and
subscription deletion move entitlement to cancelled and audit the block
(`tests/test_arclink_entitlements.py:1077-1106`).

Status: entitlement logic, idempotency, failed payment, cancellation, and refuel
local behavior are `real`; live Stripe checkout, webhook delivery,
portal links, refunds, and production price/product configuration are
`proof-gated`.

## 4. Provisioning And Deployment

### Happy Path

Payment advances a deployment from `entitlement_required` to
`provisioning_ready`. The Sovereign worker claims paid deployments, marks them
`provisioning`, places them on a fleet host, renders intent, applies DNS when
domain ingress is selected, applies Docker Compose locally or over SSH, records
service health, and emits handoff events (`python/arclink_sovereign_worker.py:438-506`,
`python/arclink_sovereign_worker.py:656-775`).

Fleet placement chooses an active non-draining host with enough headroom, or an
ASU-aware best host when that strategy is enabled. Existing active placements
are idempotent (`python/arclink_fleet.py:361-433`). Worker enrollment tokens are
accepted only from a file or stdin, never argv (`bin/arclink-fleet-join.sh:14-34`,
`bin/arclink-fleet-join.sh:94-105`).

Provisioning intent includes dashboard, Hermes dashboard/gateway, qmd, vault
watch, memory synthesis, Nextcloud, Notion webhook, notification delivery,
health watch, Drive/Code/Terminal plugin roots, provider router config, access
URLs, DNS, Traefik labels, and secret refs
(`python/arclink_provisioning.py:922-1226`). It rejects plaintext secret-looking
material (`python/arclink_provisioning.py:896-920`).

### Ingress Choices

- Domain mode computes Cloudflare records and Traefik host labels for user,
  files, code, and Hermes hostnames (`docs/arclink/sovereign-control-node.md:96-107`).
- Tailscale mode skips Cloudflare DNS and uses a path or port strategy under the
  worker tailnet name (`docs/arclink/sovereign-control-node.md:108-115`).
- Per-deployment Notion callback URLs are rendered for both modes
  (`docs/arclink/sovereign-control-node.md:116-120`,
  `python/arclink_provisioning.py:1208-1215`).

### Rollback And Teardown

Failed provisioning records safe errors, health failure status, and a durable
timeline event (`python/arclink_sovereign_worker.py:493-505`). Rollback planning
preserves state roots (`python/arclink_provisioning.py:1355-1397`), and executor
rollback rejects state-root or vault deletes (`python/arclink_executor.py:2172-2202`).

Cancellation and teardown stop Compose, remove managed DNS where applicable,
revoke provider artifacts if configured, clean materialized secrets, release
placement/ports, and preserve volumes unless teardown metadata explicitly asks
to remove them (`python/arclink_sovereign_worker.py:781-885`,
`docs/arclink/control-node-production-runbook.md:240-252`).

Status: render, idempotency, fake/local contracts, placement, guarded failure
paths, and the no-secret Hetzner/Linode lifecycle harness are `real`; live
Docker/SSH fleet apply, provider worker creation/join/destroy, Cloudflare DNS,
Tailscale publication, and production health checks are `proof-gated`.

## 5. Credential Handoff

When a deployment is ready, ArcLink creates credential handoff rows for the
user, including a dashboard password reference and copy/store guidance
(`python/arclink_public_bots.py:3030-3068`). The user dashboard reads
`GET /api/v1/user/credentials`, shows masked `secret://` references and any
allowed one-time reveal material, and tells the user to store the credential
before acknowledgement (`python/arclink_api_auth.py:1647-1747`,
`web/src/app/dashboard/page.tsx:1756-1805`).

Acknowledgement is CSRF-protected, owner-scoped, audited, and moves the handoff
to `removed`, hiding it from future user API reads
(`python/arclink_api_auth.py:1750-1800`). First-day guidance says reissue
requires operator rotation or recovery (`docs/arclink/first-day-user-guide.md:17-28`).

Raven blocks Notion setup prep until credential handoffs are confirmed. That
keeps Notion secrets out of chat and forces dashboard/operator verification
(`python/arclink_public_bots.py:3291-3358`).

Status: local credential handoff and acknowledgement are `real`; live
password delivery through public/private channels remains `proof-gated`.

## 6. User Dashboard

The dashboard is the Captain's control surface after checkout. It loads user
state, billing, provisioning, credentials, linked resources, communications,
provider state, Crew recipe, Wrapped data, workspace readiness, recovery
actions, and per-deployment service links (`web/src/app/dashboard/page.tsx:393-449`,
`python/arclink_dashboard.py:799-922`).

Core tabs:

- Overview: active deployment identity, recovery actions, workspace readiness,
  and per-deployment cards.
- Billing: entitlement, subscription lifecycle, portal/refuel entry points.
- Provisioning: job state and handoff readiness.
- Services: Hermes dashboard, Drive, Code, and Terminal links
  (`web/src/app/dashboard/page.tsx:364-373`,
  `web/src/app/dashboard/page.tsx:967-1005`).
- Drive/Vault: access to the authenticated Hermes Drive surface and accepted
  Linked resources (`web/src/app/dashboard/page.tsx:1008-1048`).
- Model: provider, model, credential state, budget, and provider settings marked
  `policy-question` (`web/src/app/dashboard/page.tsx:1120-1131`,
  `web/src/app/dashboard/page.tsx:1594-1685`).
- Memory: qmd, memory synthesis, and Notion SSOT status. Notion can reach
  `local_metadata_verified` only as a local dashboard state; live shared-root
  proof remains a separate `proof_gated` badge
  (`web/src/app/dashboard/page.tsx:1140-1164`,
  `web/src/app/dashboard/page.tsx:1541-1589`).
- Security: session/CSRF facts and credential handoff
  (`web/src/app/dashboard/page.tsx:1173-1185`).
- Comms, Wrapped, Bots, Crew, Support: account-specific communications,
  reports, channel state, training recipe, and recovery information.

The recovery rail surfaces incomplete billing, provisioning, service, credential
handoff, bot handoff, Notion proof, and provider threshold states
(`web/src/app/dashboard/page.tsx:1267-1360`). Workspace readiness groups billing,
services, channel, knowledge, linked resources, and provider state
(`web/src/app/dashboard/page.tsx:1409-1468`).

Status: read models, scoped API contracts, and dashboard rendering are `real`;
production reverse proxy/TLS, real Hermes landing, and dashboard
browser proof are `proof-gated`.

## 7. Hermes And Agents

In Shared Host mode, each enrolled user gets a private Hermes home under the
ArcLink-managed user-agent path, not a guessed `~/.hermes`. Curator and
operator-run services manage enrollment, refresh, gateway, dashboard, backup,
and health. In Control Node mode, ArcPod Hermes homes are rendered by the
deployment installer path so Drive, Code, Terminal, qmd, and memory synthesis
use the release-aligned pod vault.

Agents get ArcLink-specific hooks and plugins rather than core Hermes patches:
managed context, Telegram `/start`, Drive, Code, Terminal, reaction defaults,
skills sync, config migration, and dashboard access proxy. The first-day guide
sets user expectations: Discord handoff can be retried through Curator, Telegram
requires the user to press Start, and dashboard links are sent at completion
(`docs/arclink/first-day-user-guide.md:5-41`).

Provider/model choice is visible through provider state. The default Control
Node provider lane is routed through the ArcLink LLM Router by default, with
Chutes as the current OpenAI-compatible provider adapter family in the local
source; direct provider key mounting is only a compatibility flag
(`docs/arclink/llm-router.md:147-162`). The provider settings panel states that
self-service provider add is a policy question and dashboard mutation is
disabled until product policy decides the path
(`python/arclink_api_auth.py:3355-3380`,
`web/src/app/dashboard/page.tsx:1594-1647`).

Status: install/refresh defaults and local provider-state surfaces are `real`;
live Hermes dashboard access, live LLM router upstream behavior,
and user-owned provider OAuth are `proof-gated` or `policy-question`.

## 8. Knowledge, Notion, SSOT, Memory

Agents should use ArcLink's high-level MCP rails before raw file or API
rummaging: `knowledge.search-and-fetch`, `vault.search-and-fetch`,
`vault.fetch`, `notion.search-and-fetch`, `notion.fetch`, `ssot.read`,
`ssot.write`, and `ssot.status` (`docs/arclink/data-safety.md:82-99`,
`python/arclink_mcp_server.py:80-104`).

The vault rail indexes authored markdown/text and generated PDF sidecar
markdown. Notion shared pages are indexed through a Notion-specific qmd rail,
with live fetch for exact pages/databases and index fallback when live fetch
cannot prove the page (`python/arclink_mcp_server.py:2078-2169`,
`python/arclink_mcp_server.py:2233-2368`).

SSOT writes go through the broker. `ssot.write` supports insert, update, append,
`create_page`, and `create_database`, while archive/delete/trash/destroy are
intentionally unsupported by the MCP schema
(`python/arclink_mcp_server.py:91-97`,
`python/arclink_mcp_server.py:393-455`). Status, pending, approve, deny, and
read-after paths are caller-scoped (`python/arclink_mcp_server.py:2409-2551`).

Memory synthesis is a second-stage cached sensemaking lane. Managed recall stubs
are routing hints, not evidence; the agent must fetch source rails before
answering or changing state (`docs/arclink/data-safety.md:95-103`). The managed
memory tool also includes the user-scoped today-plate work snapshot, so the
Agent's "what matters now" view should start from managed context before
fetching deeper sources (`python/arclink_mcp_server.py:80-84`).

Almanac is lineage terminology for the knowledge-store rail inside ArcLink, not
the current public product name. User-facing surfaces should say ArcLink, while
legacy/rail references can preserve Almanac context when they identify the
underlying knowledge lineage (`docs/arclink/data-safety.md:101-103`).

Raven's `/connect_notion` records setup intent and callback after credential
handoff, but it does not verify Notion, install secrets, or claim user-owned
OAuth (`python/arclink_public_bots.py:3759-3835`; see `GAP-007`). The Notion
dashboard read model distinguishes setup intent, webhook state, local metadata,
and live proof so a local setup cannot appear as bare `verified` before
`PG-NOTION` (`python/arclink_dashboard.py:503-586`). The Notion proof harness can
prove shared-root readability and optionally brokered write preflight, but live
mutation stays explicitly gated (`python/arclink_notion_ssot.py:1120-1205`).

Status: local MCP schemas, qmd/Notion rails, SSOT broker shape, and memory stubs
are `real`; live Notion workspace permissions and user-owned OAuth are
`proof-gated`.

## 9. Workspace, Linked Resources, Sharing

Drive, Code, and Terminal are native Hermes dashboard plugins. Local plugin
tests verify sanitized status, Vault/Workspace/Linked roots, read-only Linked
roots, no sharing capability from Linked, blocked writes to Linked, a
fail-closed authenticated Drive/Code `Request Share` browser contract with
deployment-scoped broker payloads, and Terminal sanitized workspace state
(`tests/test_arclink_plugins.py`).

Accepted shares appear as a read-only `Linked` root in Drive and Code, cannot be
reshared from that account, and may be copied/duplicated into the recipient's
own Vault/Workspace (`docs/arclink/operations-runbook.md:131-148`,
`tests/test_arclink_plugins.py:560-725`). The dashboard shows accepted linked
resources, projection status, access mode, and no-reshare state
(`web/src/app/dashboard/page.tsx:1710-1754`).

Agents can request shares through `shares.request`, and Pod Comms can attach a
share-grant reference through `pod_comms.share-file`. Raw files are not embedded
in message bodies (`python/arclink_mcp_server.py:333-386`,
`python/arclink_mcp_server.py:1004-1042`,
`python/arclink_mcp_server.py:1080-1105`). The share tool and managed-context
recipe now state the same copy/duplicate rule as Drive and Code: accepted
Linked resources are read-only, cannot be reshared, and may be copied only into
owned Vault or Workspace roots (`python/arclink_mcp_server.py:1031-1042`,
`plugins/hermes-agent/arclink-managed-context/__init__.py:326-330`).

Share approval and acceptance can happen through Raven, with owner scoping,
recipient scoping, audit rows, and notifications where a linked public channel
exists (`python/arclink_public_bots.py:4116-4295`). If the owner has no linked
Telegram/Discord channel, the API persists the grant and the dashboard share
inbox exposes the durable owner-approval or recipient-acceptance wait with
local approve/deny/accept actions instead of relying only on public-bot
delivery. The dashboard can also retry queueing the current Raven share prompt
after a public channel is linked, while clearly treating that as local queueing
rather than live delivery proof (`docs/arclink/operations-runbook.md:150-183`).

Status: backend sharing, dashboard listing, plugin read-only enforcement,
Raven actions, and the local Drive/Code `Request Share` handoff through the
hosted deployment-scoped broker route are `real`; production workspace/browser
proof, live bot delivery, and any Nextcloud-backed adapter choice are
`partial`/`proof-gated` or policy-gated. Direct browser share-link generation
is not claimed.

## 10. Pod Comms, Wrapped, Crew Training

Pod Comms allows same-Captain Crew messages by default. Cross-Captain messages
require accepted, unexpired `pod_comms` share grants; raw file attachments are
not allowed in message rows (`docs/arclink/operations-runbook.md:160-170`,
`python/arclink_mcp_server.py:86-88`).

ArcLink Wrapped is a periodic Captain report over scoped activity. It reads the
Captain's own Pods, same-Captain Comms, audit/event rows, memory cards, and
read-only summaries, writes reports and notifications, and never exposes report
text in operator aggregate views (`docs/arclink/operations-runbook.md:172-207`,
`docs/arclink/control-node-production-runbook.md:207-238`).

Crew Training is a Captain-facing recipe flow. The production runbook describes
read, preview, apply, admin-on-behalf apply, archived prior recipe state, and a
deterministic fallback when live LLM generation is unavailable or unsafe
(`docs/arclink/control-node-production-runbook.md:186-205`).

Status: local control/API surfaces are `real`; live LLM recipe generation
and live bot delivery are `proof-gated`.

## 11. Admin And Operator Journey

The Operator brings up Control Node with:

```bash
./deploy.sh control install
./deploy.sh control health
./deploy.sh control ports
```

Control install starts the hosted API, web control center, provisioner loop, LLM
router, MCP, qmd, Notion webhook, jobs, Redis/Postgres, and Nextcloud
(`docs/arclink/sovereign-control-node.md:8-36`). Control upgrade is distinct
from shared-host upgrade and refuses dirty checkouts before syncing upstream
unless an explicit local build override is set
(`docs/arclink/control-node-production-runbook.md:24-32`).

The admin dashboard and API expose deployments, health, DNS drift,
reconciliation, events, actions, payments, bots, security, scale operations,
provider state, and Wrapped aggregate views (`python/arclink_hosted_api.py:2994-3055`).
Admin actions require an admin id, supported action, target, reason,
idempotency key, CSRF, and mutation role; only modeled executable actions are
queued. The admin read model now publishes a source-owned action readiness
matrix for restart, reprovision, DNS repair, Chutes key rotation, refund,
cancel, and comp, with operation kind, required adapter, proof boundary, and
fail-closed reason visible to the UI and runbooks (`python/arclink_dashboard.py`,
`web/src/app/admin/page.tsx`, `docs/arclink/control-node-production-runbook.md`).

Shared Host operators still use the canonical bare deploy commands for install,
upgrade, health, enrollment trace/reset, org profile, Notion migration/transfer,
service repair, deploy keys, and release state. Docker shared-host validation
uses the `./deploy.sh docker ...` family. Live ArcPod product operations use the
`./deploy.sh control ...` family.

Backups are documented for control database, per-deployment state roots,
Nextcloud/Postgres volumes, vault git history, and configuration, with a
periodic staging restore expectation (`docs/arclink/backup-restore.md:3-77`).
The local no-secret restore-smoke helper can restore shared and agent-home
backup artifacts into a temporary directory, reject remote GitHub/SSH sources,
validate shared layout/SQLite artifacts, and reject agent-home backups that
contain `secrets/` or `logs/` without starting Docker, systemd, deploy, or live
services (`bin/arclink-restore-smoke.sh`,
`tests/test_backup_git_regressions.py`,
`tests/test_agent_backup_regressions.py`).
Raven's `/config_backup` preparation lane and the user dashboard now share the
same local pending state: a private repo can be recorded as pending key setup,
and an authenticated CSRF-gated dashboard API route can stage the dedicated
backup deploy key while returning only the public key/status. A second
CSRF-gated dashboard API route and the queued action-worker boundary can record
GitHub write-check attempts as `failed_closed` without running live git or
activating backup. GitHub installation/write verification, activation, and
restore proof stay inactive or `proof-gated` until the authorized backup rail runs
(`python/arclink_public_bots.py`, `python/arclink_dashboard.py`,
`python/arclink_hosted_api.py`, `python/arclink_action_worker.py`,
`web/src/app/dashboard/page.tsx`).

Status: local admin read/action models, readiness matrix, and command surfaces
are `real`; local backup pending-status and staged-public-key API handoff are
`real`; the local backup write-check boundary is fail-closed; local backup
artifact restore-smoke coverage is `real`; live admin mutation, backup
activation/restore drills, and provider-side changes are `proof-gated`.

## 12. Security And Isolation Contract

The product boundary is: a Captain and their Agents can work broadly inside
their own ArcPod, vault, workspace, and dashboard tools, but cannot read,
infer, mutate, route to, or share another Captain's private deployment, channels,
dashboard, provider state, Notion/SSOT data, files, Stripe state, or Hermes
resources.

Concrete source-grounded controls:

- User dashboard reads are scoped by `user_id`; a user cannot read another
  user's deployment credentials (`python/arclink_dashboard.py:799-822`,
  `python/arclink_api_auth.py:1674-1699`).
- Sessions use hashed tokens and HttpOnly cookie transport; dashboard mutation
  endpoints use CSRF (`web/src/app/dashboard/page.tsx:1173-1179`).
- Provider state exposes credential lifecycle, counts, and budget summaries, not
  raw provider tokens (`python/arclink_api_auth.py:3288-3385`,
  `docs/arclink/llm-router.md:140-145`).
- Provisioning intent uses `secret://` references or mounted secret files and
  rejects plaintext-looking secret values (`python/arclink_provisioning.py:896-920`,
  `docs/arclink/data-safety.md:67-80`).
- Fleet enrollment tokens are one-time and not accepted on argv
  (`docs/arclink/fleet-operator-runbook.md:8-15`,
  `bin/arclink-fleet-join.sh:14-34`).
- SSOT destructive writes are blocked or brokered rather than bypassed through
  raw Notion access (`docs/arclink/data-safety.md:140-144`).
- Rollback and teardown preserve state by default and require explicit
  destructive metadata for volume removal (`docs/arclink/data-safety.md:113-144`).

Trusted-host exceptions are explicit, not hidden. `deployment-exec-broker`,
`agent-supervisor-broker`, `operator-upgrade-broker`, and
`gateway-exec-broker` mount the Docker socket,
while `migration-capture-helper`, `agent-user-helper`, and `agent-process-helper`
run as root because they manage Pod migration file copy, container-local agent
user/home setup, and setpriv-based agent process execution.
`notification-delivery` now calls the gateway broker instead of mounting the
socket directly, and `control-provisioner` now calls the deployment broker
instead of mounting the socket directly. `control-action-worker` now calls the
deployment broker for Docker-mode local lifecycle/apply calls instead of
mounting the socket directly, and it no longer runs as root. Non-dry-run Pod
migration capture still fails closed unless the operator explicitly sets the
root-capture opt-in for a bounded migration window and Docker mode also has the
tokened `migration-capture-helper` URL/token configured. That helper rejects
raw commands, reconstructs only `capture` and `materialize`, and validates
deployment-scoped source, target, and staging paths before copying files.
`GAP-019-AC` further narrows the helper by removing broad `*arclink-env`
inheritance and requiring source, target, and staging paths to stay under
`ARCLINK_STATE_ROOT_BASE` before copy or materialize work starts.
`agent-supervisor` now calls
`agent-supervisor-broker` for dashboard network/proxy sidecar work instead of
mounting the socket directly, and calls `agent-user-helper` for user/home setup
instead of performing that root operation directly. It also calls
`agent-process-helper` for Docker-mode install, identity refresh, user-agent
refresh, cron, gateway, and dashboard process execution instead of running as
root itself. The process helper passes validated env through subprocess
`env=`, not setpriv argv or startup command logs, and the supervisor strips
broker/helper tokens from per-agent process specs before dispatch. The helper
also rejects ArcLink broker/helper/control token env keys before one-shot or
long-running subprocess execution if a caller bypasses that supervisor filter.
It also rejects dynamic-loader `LD_*`, Python path/startup, shell startup,
Git/SSH command-steering, and secret-looking process env keys before helper
logs or subprocesses; `agent-supervisor` fails closed on the same unapproved
non-token key family before helper payload construction. It also rejects
caller-provided `PATH` values that differ from `SAFE_PATH`, uses
`/usr/bin/setpriv` by absolute path, and fails identity setup closed if the
pinned runtime venv Python is absent.
`control-ingress` now loads static Traefik routes from
`config/traefik-control.yaml` instead of enabling Docker provider discovery or
mounting the read-only Docker socket. The
reviewed inventory in
`config/docker-authority-inventory.json` records the socket mode, root boundary,
Linux capability boundary, `GAP-019-B2` broker/no-go review, monitoring anchor,
`GAP-019-M` incident controls, and residual policy state for each such service.
Non-root socket services drop Linux capabilities, and `agent-user-helper` drops
Docker's default capability set with only `CHOWN`, `DAC_OVERRIDE`, and `FOWNER`
added back for validated agent-home writes and ownership repair. The same
helper pins account and ownership commands to `/usr/sbin/groupadd`,
`/usr/sbin/useradd`, and `/usr/bin/chown`, and fails closed before helper
mutation if a required binary is unavailable. The
action-worker lifecycle path overrides fail closed unless an operator enables
the emergency override flag. The public-Agent bridge path also validates
detached `notification-delivery` bridge commands against the generated
`hermes-gateway` exec forms and confines Compose fallback files under the
deployment state root. `gateway-exec-broker` accepts only a bounded deployment
request, rejects raw commands, and reconstructs the `hermes-gateway` Docker exec
command itself. `GAP-019-Y` narrows that broker's service boundary: it no
longer inherits broad `*arclink-env` values and no longer mounts broad
`arclink-priv/config`, `arclink-priv/state`, or
`arclink-priv/secrets/container`, while preserving only broker token/listener
env, `ARCLINK_STATE_ROOT_BASE`, optional `ARCLINK_DOCKER_BINARY`, the
deployment state-root bind, and the writeable Docker socket needed for
public-Agent gateway exec. `GAP-019-AH` also makes that broker reject unsafe,
missing, non-executable, non-Docker, or PATH-injected Docker CLI values before
running-container discovery or gateway exec subprocesses run. `GAP-019-AY`
also makes its Compose fallback reject symlinked, missing, non-regular,
unreadable, or directory `config/arclink.env` and `config/compose.yaml`
targets before fallback dispatch or a successful public Agent broker response.
`GAP-019-BC` adds source-owned rejected-request incident evidence for the same
broker: rejected raw-command, project-name mismatch, unsupported-platform, and
trusted-host acknowledgement failures append redacted JSONL rows under
`ARCLINK_STATE_ROOT_BASE/_broker-incidents/gateway-exec-broker/rejections.jsonl`
when the deployment state root is safe. Those rows carry only safe
deployment/project metadata and sanitized reason codes, not raw request bodies,
bridge payload values, bot tokens, chat ids, user ids, message text, process
args, rendered config paths, private paths, or stack traces. Accepted broker
requests do not append rejection incidents.
`GAP-019-BD` extends the same redacted incident trail to the deployment exec,
migration capture, agent user, dashboard sidecar, and operator upgrade
broker/helper lanes using only scoped state roots or a narrow dashboard broker
incident mount. Those rows carry safe service/event, acknowledgement, error,
reason, operation, and identifier metadata, not raw command arrays, payload
values, private paths, tokens, chat/user ids, message text, secret-looking
values, or stack traces.
`GAP-019-Z`
narrows `agent-supervisor-broker` the same way for dashboard sidecar work: it no
longer inherits broad app env and no longer mounts broad private
config/state/secrets, while preserving only Docker binary/image, repo path,
host/container private path metadata, broker token/listener env, and the
writeable Docker socket. `GAP-019-AF` also makes that broker reject unsafe,
missing, non-executable, or non-Docker `ARCLINK_DOCKER_BINARY` values before
dashboard network/proxy subprocesses run. `GAP-019-AZ` makes malformed
`ARCLINK_DOCKER_HOST_PRIV_DIR` or `ARCLINK_DOCKER_CONTAINER_PRIV_DIR` values
fail before Docker lookup or dashboard auth-proxy `docker run -v`
construction. `curator-refresh` no longer mounts the Docker socket; queued
Docker-mode upgrade execution is routed through the enrollment provisioner path
instead. The local executor also preflights live Docker requests before runner
dispatch: deployment IDs must be safe path segments, apply project names must
match the deployment, and env/compose files must stay under the configured
deployment state root. `deployment-exec-broker` accepts only generated project
names and allowlisted Compose `up`, `ps`, or `down` operation kinds, rejects raw
commands, and reconstructs the Docker Compose command itself. `GAP-019-AA`
keeps that broker on minimal service env instead of broad `*arclink-env`:
broker token/listener settings, `ARCLINK_STATE_ROOT_BASE`, optional Docker
binary, the deployment state-root bind, and the writeable Docker socket.
`GAP-019-AG` also makes that broker reject unsafe, missing, non-executable, or
non-Docker `ARCLINK_DOCKER_BINARY` values before deployment Compose
subprocesses run. `GAP-019-AX` makes symlinked deployment config roots and
symlinked, missing, non-regular, or unreadable rendered `config/arclink.env`
and `config/compose.yaml` files fail before Docker CLI lookup or Compose
subprocess dispatch.
`agent-supervisor-broker` accepts only safe agent ids, deterministic
network/container names, backend IPs, ports, and private-state access-file
paths for dashboard proxy work. `operator-upgrade-broker` owns the queued
Docker-mode operator upgrade path: enrollment provisioner requests fail closed
without operator-upgrade broker URL/token, raw commands are rejected, only
allowlisted upgrade commands are reconstructed, and logs stay under private
`state/operator-actions`. `GAP-019-AB` narrows that broker further: it no
longer inherits broad app env, no longer mounts broad canonical private
config/state/secrets paths, and its upgrade subprocesses receive a
child-process env allowlist instead of the broker's full process environment.
`GAP-019-AI` makes any preserved `ARCLINK_DOCKER_BINARY` resolve to a trusted
absolute Docker CLI path before those upgrade children run; unsafe, missing,
non-executable, non-Docker, relative, or PATH-injected values fail closed.
`GAP-019-AV` also makes the same broker reject missing, symlinked, directory,
unreadable, or non-executable fixed `deploy.sh` and
`bin/component-upgrade.sh` targets before private operator logs or upgrade
subprocesses are created.
`GAP-019-AW` confines the same broker's request-supplied upstream deploy-key
metadata: non-empty `ARCLINK_UPSTREAM_DEPLOY_KEY_PATH` and
`ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE` values must be absolute non-symlink paths
under `ARCLINK_DOCKER_HOST_PRIV_DIR` before child env construction, private
operator logs, or upgrade subprocesses are created.
These are local hardening controls, not tenant isolation. The source-owned incident
controls now name monitored signals, status/log/audit locations, triage steps,
fail-closed actions, and operator escalation boundaries for the remaining
socket/root services. `agent-supervisor` validates active-agent metadata,
canonical Docker agent homes, Hermes homes, workspace/log/process keys, and
agent process inputs before helper, broker, or process-helper requests.
The root helpers also recheck configured roots themselves: `agent-user-helper`
rejects configured Docker agent-home root mismatches before root filesystem or
account mutation, and `agent-process-helper` rejects configured Docker
agent-home, repo, private-state, state, and runtime root mismatches before
helper logs or subprocess execution. They also reject symlink-escaped agent
home, Hermes home, and workspace paths before uid/gid assignment, account
commands, recursive chown, helper logs, or subprocess execution, and
`GAP-019-AS` rejects symlinked configured or requested Docker agent-home roots
before either root helper writes uid/gid assignments, repairs ownership, opens
helper logs, or starts subprocesses. This is configured-root path hardening
only; both helpers remain trusted-host residual risk.
`GAP-019-BA` narrows the `agent-user-helper` assignment persistence boundary:
symlinked, directory, or non-regular `.arclink-user-ids.json` and
`.arclink-user-ids.json.tmp` paths under the Docker agent-home root fail before
uid/gid assignment reads or writes, account commands, agent-home directory
creation, or recursive chown. This is assignment-file hardening only; the
helper remains trusted-host residual risk.
`GAP-019-BB` adds source-owned rejected-request incident evidence for
`agent-process-helper`: rejected process-helper requests append redacted JSONL
rows under `state/docker/agent-process-helper/rejections.jsonl` when the
configured private root is safe. The incident row carries only safe metadata
and sanitized reason codes, not raw request bodies, env values, args, private
paths, tokens, or stack traces. This is local incident evidence only; the root
process-helper boundary remains trusted-host residual risk.
`GAP-019-AT` applies the same fail-closed rule to the process helper's
configured repo, private-state, state, and runtime roots: symlinked
configured/requested `ARCLINK_REPO_DIR`, `ARCLINK_PRIV_DIR`,
`ARCLINK_DOCKER_CONTAINER_PRIV_DIR`, request `state_dir`, or `RUNTIME_DIR`
values fail before helper logs, cwd/command/runtime lookup, or subprocess
execution. This is process-helper path hardening only; the helper remains
trusted-host residual risk.
`GAP-019-AU` also makes fixed repo command targets fail closed: missing,
symlinked, directory, unreadable, or non-executable ArcLink script targets such
as `bin/hermes-shell.sh` are rejected before helper logs or subprocesses. This
is command target hardening only; the helper remains trusted-host residual
risk.
`GAP-019-AO` makes `agent-process-helper` reject symlink-escaped helper log
directories before opening logs or starting subprocesses. `GAP-019-X` further narrows
`agent-process-helper` at service startup: it no longer inherits broad
`*arclink-env` values and no longer mounts `arclink-priv/secrets/container`,
while preserving explicit non-secret path-validation env and the config, state,
vault, and read-only repo mounts needed for allowlisted agent commands.
`GAP-019-Y` similarly removes broad app env and broad private config/state/secrets
mounts from `gateway-exec-broker`; the broker still has writeable Docker socket
authority and remains a trusted-host boundary. `GAP-019-AH` removes Docker CLI
executable steering from the same broker; it is executable-lookup hardening,
not tenant-safe isolation. `GAP-019-BC` adds a redacted local rejection incident
trail for the same broker; it is incident evidence, not tenant-safe isolation
or live alerting. `GAP-019-BD` adds equivalent local incident trails for the
remaining high-authority broker/helper lanes; it is also incident evidence,
not live alerting or accepted residual risk. `GAP-019-Z` removes the same
broad app env and broad private config/state/secrets mounts from
`agent-supervisor-broker`; that broker still has writeable Docker socket
authority for dashboard sidecar work and remains a trusted-host boundary.
`GAP-019-AF` removes `ARCLINK_DOCKER_BINARY` steering to non-Docker
executables from the same broker; it is executable-lookup hardening, not
tenant-safe isolation.
`GAP-019-AZ` removes private-bind-root steering from the same broker: unsafe
host/container private root values fail before dashboard auth-proxy sidecar
mount construction, but the broker remains a trusted-host Docker socket
boundary.
`GAP-019-AA` removes broad app env inheritance from `deployment-exec-broker`;
that broker still has writeable Docker socket authority for deployment Compose
work and remains a trusted-host boundary. `GAP-019-AG` removes
`ARCLINK_DOCKER_BINARY` steering to non-Docker executables from the same
broker; it is executable-lookup hardening, not tenant-safe isolation.
`GAP-019-AX` removes symlink-steered rendered config-file dispatch from that
broker; it is path hardening, not tenant-safe isolation.
`GAP-019-AY` removes symlink-steered public Agent Compose fallback config-file
dispatch from `gateway-exec-broker`; it is path hardening, not tenant-safe
isolation.
`GAP-019-AB` removes broad app env, broad canonical private mounts, and full
child-process env inheritance from `operator-upgrade-broker`; that broker still
has writeable Docker socket authority and a writable host repo bind that can
reach nested private state for real upgrades.
`GAP-019-AI` removes `ARCLINK_DOCKER_BINARY` steering to non-Docker executables
from the same broker's queued upgrade children; it is executable-lookup
hardening, not tenant-safe isolation.
`GAP-019-AV` removes fixed script-target steering in the same broker:
`deploy.sh` and `bin/component-upgrade.sh` must be exact non-symlink regular
readable files with executable bits before any private operator log or upgrade
subprocess exists. This is checkout-integrity hardening, not tenant-safe
isolation.
`GAP-019-AW` removes upstream deploy-key path steering in the same broker:
`ARCLINK_UPSTREAM_DEPLOY_KEY_PATH` and
`ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE` must stay under private state and must not
be relative or symlink-steered before any child env, private operator log, or
upgrade subprocess exists. This is deploy-key path hardening, not tenant-safe
isolation.
`GAP-019-AC` removes broad app env inheritance from
`migration-capture-helper` and adds configured `ARCLINK_STATE_ROOT_BASE`
confinement for its source, target, and staging paths; that helper still runs
as root over deployment bind mounts during an approved migration window.
`GAP-019-AD` removes caller-controlled executable lookup from
`agent-process-helper` before privilege drop and removes the bare `python3`
identity fallback; that helper still runs as root for allowlisted Docker agent
process execution.
`GAP-019-AM` removes dynamic-loader, Python path/startup, shell startup,
Git/SSH command-steering, and secret-looking process env injection from the
same helper boundary before logs or subprocesses; it is env-boundary hardening,
not tenant-safe isolation.
`GAP-019-AJ` adds desired-process signature tracking and bounded shutdown to
that helper, so changed gateway/dashboard command, cwd, dashboard backend port,
or validated env contracts restart stale long-running processes instead of
silently keeping the old handle.
`GAP-019-AK` removes default Compose network reachability from the tokened
Docker/root broker and helper APIs. Their request lanes now use internal
networks shared only with legitimate callers; `agent-process-helper` and
`operator-upgrade-broker` retain separate single-service egress networks for
outbound gateway/provider runtime work and upgrade fetches.
`GAP-019-AL` adds an explicit trusted-host acknowledgement gate to those seven
services. `deployment-exec-broker`, `migration-capture-helper`,
`agent-user-helper`, `agent-process-helper`, `agent-supervisor-broker`,
`operator-upgrade-broker`, and `gateway-exec-broker` fail closed before binding
their request listeners or processing direct helper/broker work unless private
Docker config sets `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted`.
This is only an operator acknowledgement boundary; it does not make the
writeable Docker socket brokers or root helpers tenant-safe.
`GAP-019-AP` makes direct/local execution of those same broker/helper modules
bind `127.0.0.1` by default. Compose is still the explicit `0.0.0.0` opt-in
for internal request-network reachability, so broad binds are intentional and
reviewable rather than inherited from direct-run defaults.
`GAP-019-AQ` narrows the `agent-supervisor` enrollment provisioner child env:
the child no longer starts from `os.environ.copy()` and instead receives only
Docker mode/path config, runtime roots, service URLs, and helper/broker values
needed for Docker enrollment and queued operator actions. Payment, provider,
bot, ingress, memory-synthesis, session, fleet, Python path, and Git/SSH
steering env keys are not forwarded to that child. The supervisor still keeps
private config/state/vault mounts for Docker agent reconciliation, so this is
local env-exposure hardening, not tenant-safe isolation.
`GAP-019-AR` narrows the dashboard backend host boundary shared by the root
`agent-process-helper` and the dashboard `agent-supervisor-broker`: dashboard
backend host values must be loopback or Docker-internal/private/link-local IPs,
and wildcard, globally routable, multicast, malformed, or non-IP values fail
closed before dashboard process or proxy subprocess construction. This keeps
the local dashboard path behind the internal network/proxy design; it does not
make the root helper or socket broker tenant-safe.
`GAP-019-T` also makes the live host repo
bind read-only for `agent-supervisor`, `agent-process-helper`, and
`curator-refresh`; they keep script read access without checkout write access.
`GAP-019-U` moves the explicit writable host repo exception for allowlisted
queued Docker-mode operator upgrades to `operator-upgrade-broker`, while
`agent-supervisor-broker` no longer mounts the host repo.
Together, these controls leave writeable Docker socket access and the remaining
root helpers as operator trust boundaries, not tenant-safe sandboxes.

## 13. Recovery Atlas

- Web checkout paused: cancel page marks the onboarding session cancelled when
  it still has the session-scoped cancel proof token, clears token material, and
  otherwise returns to resume without claiming cancellation proof.
- Payment not yet confirmed: success page polls, then tells the Captain to wait
  for Raven or dashboard status.
- Payment failed or cancelled: entitlement stays non-current and provisioning
  remains fail-closed.
- No fleet capacity: Raven blocks checkout or provisioning with capacity status.
- Provisioning failed: job records failure, service health is marked failed, and
  rollback planning preserves state roots.
- No public handoff: Discord users retry through Curator; Telegram users must
  open the Agent bot and press Start (`docs/arclink/first-day-user-guide.md:5-15`).
- Dashboard link fails: operator runs health/refresh rather than the user
  guessing host paths (`docs/arclink/first-day-user-guide.md:81-92`).
- Credential handoff pending: user stores the credential, acknowledges removal,
  then Notion setup and other secure lanes can proceed.
- Notion setup stuck: Raven records setup intent only; dashboard state can show
  local metadata readiness, but authorized `PG-NOTION` proof is required before
  calling integration access complete.
- Private backup setup pending: Raven records the private repository intent,
  and the dashboard can stage a public deploy key, link to GitHub deploy-key
  settings, and record the local fail-closed write-check state. The local
  restore-smoke helper can inspect/restore backup artifacts into a temp
  location, but backup remains inactive and not live-recoverable until
  authorized `PG-BACKUP` write, activation, and restore proof passes.
- Share pending with no public owner channel: grant remains pending; owner must
  link a channel, approve through authenticated API, or retry the Raven prompt
  after a public channel is linked (`docs/arclink/operations-runbook.md:150-183`).
- Provider threshold/exhaustion: dashboard shows state; refuel and fallback
  paths are partly `policy-question`
  (`web/src/app/dashboard/page.tsx:1350-1356`).
- Live claim missing: run the relevant proof gate, do not upgrade the claim to
  `real` from fake tests.

## 14. Gap And Proof Pointers

This journey intentionally does not repeat the gap register. The blocking
production and validation claims are tracked as `GAP-001` through `GAP-025` in `GAPS.md`, with
canonical proof-gate IDs such as `PG-PROD`, `PG-STRIPE`, `PG-BOTS`,
`PG-PROVISION`, `PG-FLEET`, `PG-INGRESS`, `PG-PROVIDER`, `PG-NOTION`,
`PG-HERMES`, `PG-BACKUP`, and `PG-UPGRADE`.

Until those gates pass, ArcLink should be described as a locally `real` and
tested control plane with credential-gated production proof outstanding.
`GAP-010`, `GAP-013-C`, and `GAP-025` are now locally closed by the web
preferred-channel tests, dashboard backup UX/API-client tests, and broad Python
suite respectively. `GAP-015-B` is locally repaired for share notification
retry queueing, but live Telegram/Discord delivery still requires `PG-BOTS`.

The public documentation handoff is therefore terminal for the document phase:
`USER_JOURNEY.md` owns the intended experience, `GAPS.md` owns the hard missing
and unproven work, and new implementation should start from the gap register
instead of reopening this atlas unless source behavior changes.

Final reader test: if a future agent can explain both the beautiful intended
journey and the current hard truth without adding live claims, this document has
done its job. If that agent wants to schedule work, the next file is `GAPS.md`,
not another journey rewrite.
