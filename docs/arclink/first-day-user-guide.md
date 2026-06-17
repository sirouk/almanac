# ArcLink First-Day User Guide

This guide is for a Captain whose first ArcPod (and Hermes Agent) has just been
provisioned, plus the Operator notes for recovering a stuck handoff.

## Which Onboarding Path You Came Through

Two onboarding systems coexist today; name both so first-day expectations match
what actually happened.

- **Raven public-bot path (the production Captain path).** You talked to
  **Raven** on Telegram or Discord, chose a package, and paid through Stripe
  checkout. Raven is the public bot persona; its default display name is "Raven"
  and a Captain can rename it per channel. This path is the
  `arclink_public_bots` turn engine plus the `arclink_onboarding` state machine
  (`arclink_onboarding_sessions` advancing
  `started -> collecting -> checkout_open -> payment_pending -> paid ->
  provisioning_ready -> first_contacted`). It hands off your Crew, dashboard
  credentials, and the in-channel commands below. If you bought ArcLink, this is
  almost certainly you.
- **Curator host-Unix path (legacy, still active).** An older intake flow
  (`arclink_onboarding_flow`) provisions a host Unix user through free-text
  prompts, provider OAuth, and an operator-approved bootstrap, then sends a
  scrub-on-acknowledge completion bundle. It still runs on curator channels and
  uses recovery commands like `/retry-contact` and `/verify-notion`. If your
  onboarding used those commands and a host login, you came through this path.

Everything below the **Where To Talk** Operator notes is written for the Raven
public-bot path. Live Telegram/Discord delivery is proof-gated (**PG-BOTS**); in
fake mode Raven answers locally with no network.

## Where To Talk

Use the chat channel where onboarding completed.

- Raven public-bot path: keep talking to Raven in the same Telegram chat or
  Discord channel. Once your ArcPod is ready, bare slash commands route to your
  Hermes Agent and `/raven <verb>` reaches Raven's own controls.
- Curator host-Unix path (Discord): you should receive a direct message from the
  agent bot after Raven shows the confirmation code. If it does not arrive, DM
  `/retry-contact`.
- Curator host-Unix path (Telegram): open the shown agent bot handle and press
  Start. Telegram bots cannot cold-DM a Captain.
- Operators can retry a Curator-path Discord handoff with
  `./bin/arclink-ctl onboarding retry-contact <unixusername|discordname>`.

## Dashboard

The Hermes Dashboard links are sent at completion and shown in the user dashboard.
Sovereign users get one dashboard username, normally their email, and one
dashboard password for their ArcLink console and Hermes Dashboards. Dashboard
access is protected by ArcLink's generated web-access credential and session
proxy. Do not send dashboard passwords or session material in shared channels.

When ArcLink presents credential handoff items, copy them into a password
manager and then acknowledge storage in the user session. After acknowledgement,
the user API hides that handoff from future responses; reissue requires an
operator rotation or recovery action.

On the Raven public-bot path, ask Raven for the handoff with `/credentials`.
Raven reveals the dashboard username and password exactly once (sourced from
`arclink_credential_handoffs`); it offers Copy Username, Copy Password, and an
"I Stored It" button (`/credentials-stored`). Confirming with "I Stored It"
marks the handoff removed and scrubs it from future responses. If the secret has
already been revealed, removed, or is not materialized on the control node,
Raven refuses rather than inventing one ("I will not invent it") and points you
to `/status` or an operator rotation. The same username/password opens every
Hermes Dashboard across your Crew.

The Hermes Dashboard includes ArcLink skills and these plugins:

- **Drive:** browse and manage vault files inside the allowed vault/workspace
  root. Accepted linked resources appear under `Linked` when the projection is
  available, and accepted Drive/Code folders are writable there.
- **Code:** edit files and inspect git status inside the configured workspace.
  Linked shared folders are writable, not reshareable, and still block git
  mutations from Linked.
- **Terminal:** managed pty sessions with bounded scrollback, same-origin SSE
  streaming, polling fallback, and confirmation-gated close.

If a workspace surface reports disabled or unavailable, treat that as a real
state. Ask the operator to run health/refresh instead of trying host paths.

## Your Crew

Send `/agents` (Show My Crew) to see your roster: each Hermes Agent's name,
role, and Hermes Dashboard orientation. A Scale plan provisions three Agents;
Founders and Sovereign provision one. The roster reply also offers Train My
Crew, Academy, and Credentials. `/name Your Name` sets what the Crew calls you.

If you have more than one Agent, switch which one a bare-slash command reaches
with `/agent` (list), `/agent <name>`, or `/agent-<slug>`. Raven switches are
Raven-owned and never relayed to a Hermes Agent. The first non-slash message in
a linked channel claims a one-time bridge intro before your Agent answers.

Selected-agent replies are delivered asynchronously by the gateway bridge, not
inline in the webhook response, and live delivery is proof-gated
(**PG-PUBLIC-AGENT-DELIVERY** / **PG-BOTS**; the Hermes gateway container is
**PG-HERMES**). Streaming is enabled by the bridge runtime unless
`ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING=0`, but the live behavior remains
proof-gated (GAP-023).

## Crew Training

`/train-crew` opens an additive Crew Recipe overlay: a guided workflow (role ->
mission -> treatment -> preset -> capacity -> review) that shapes Agent names,
roles, personalities, and a SOUL.md overlay. Treatments are captain/peer/coach;
presets are Frontier/Concourse/Salvage/Vanguard. Preview, confirm, regenerate,
or cancel before it applies. Training is additive: "Memories and sessions were
not rewritten."

## Academy

`/academy` opens **Academy Mode** for one Hermes Agent at a time
(specialist training). Raven gathers your steering (choose a Major, set a focus,
allow outside source lanes, schedule weekly review), opens the Agent's sticky
Academy Mode, and tells the Agent to use the `arclink-academy` skill to run
governed search, retrieval, lesson-card drafting, and evaluation. Send
`graduate` to stage the specialist corpus, or `cancel`/`exit` to leave Academy
Mode without graduating. Graduation only stages a plan locally: "Live
provider/Hermes proof is still required before calling the Agent graduated"
(live source acquisition and Trainer synthesis are **PG-PROVIDER**; real Agent
writes are **PG-HERMES**).

## Channel Pairing

Move your ArcLink chat to another Telegram chat or Discord channel with
`/pair-channel` (also `/link-channel`). The bare command mints a 6-character
code that is valid for 10 minutes. Run `/pair-channel <code>` from the
destination chat to claim it; Raven validates expiry, rejects a same-channel or
mismatched-account claim, and hands off the active ArcPod to the new channel.

## Other Account Actions

A few more Raven commands you may reach on your first day: `/refuel` (also
`/top-up`) quotes an ArcPod Refueling top-up; `/retire-agent` retires an Agent
behind a typed-name confirmation; `/rename-agent` and `/retitle-agent` adjust
Agent identity; `/wrapped-frequency` sets your ArcLink Wrapped cadence;
`/whats-changed` and `/learn` explain shipped surfaces. Refueling is local
budget accounting until live provider proof; live checkout is **PG-STRIPE**.

## Vault And Knowledge

Your `~/ArcLink` alias points at the shared vault lane made available to your
agent. Markdown, text files, and PDF sidecar markdown become searchable through
ArcLink knowledge tools after indexing. PDF conversion may take a timer cycle.

Use these agent-facing tools first:

- `knowledge.search-and-fetch`
- `vault.search-and-fetch`
- `vault.fetch`
- `notion.search-and-fetch`
- `notion.fetch`
- `ssot.read`
- `ssot.write`

Do not ask the agent to browse private runtime directories, token files, or
other users' homes.

## Notion

Shared Notion writes go through the SSOT broker. This keeps org pages under the
configured shared root and blocks destructive archive/delete/trash style
requests unless an explicit approval rail exists.

Personal Notion OAuth/MCP access, if present, is separate from shared SSOT. Use
shared SSOT for organization pages and personal Notion only for personal
workspace material.

## Backups

ArcLink may offer a private Hermes-home backup setup after onboarding. If you
skip it, the skip is durable and you should not be repeatedly prompted. If you
use it, provide only a private GitHub repo; public repos are refused.

On the Raven public-bot path, `/config_backup <repo>` records the private repo
only. It does not mint, install, or verify the deploy key, and it does not write
to GitHub yet. Key setup, the write check, activation, and restore are
proof-gated (**PG-BACKUP**, GAP-013): the dashboard projects `pending_key_setup`
and can stage a public deploy key, while the unattended write check remains
failed-closed until proven.

Vault and private runtime backups are operator-owned. Do not paste deploy keys,
tokens, or `.env` values into chat.

## Expected Recovery Paths

- Lost your dashboard credentials (Raven path): send `/credentials`. If the
  handoff is already closed, ask Raven or the operator to rotate/reissue access.
- Your Agent has not answered (Raven path): live delivery is proof-gated
  (PG-BOTS); check `/status`, and if the ArcPod is not ready Raven will say
  whether checkout is still clearing or provisioning is pending.
- No agent DM after Discord onboarding (Curator host-Unix path): use
  `/retry-contact`.
- Telegram agent has not greeted you (Curator host-Unix path): open the bot
  handle and press Start.
- Dashboard link fails: ask the operator to refresh the agent and check
  health.
- Knowledge misses a new file: wait for the qmd/vault timer or ask for a
  refresh.
- Notion write is refused: move the content under an owned/shared page or ask
  for an approved SSOT path.
- Terminal disabled: root/unrestricted workspace guards may be active; ask for
  operator repair rather than bypassing the guard.

## See Also

- Raven public-bot command contract and operator interception:
  [raven-public-bot.md](raven-public-bot.md).
- The full route catalog and auth/CORS/rate-limit details:
  [../API_REFERENCE.md](../API_REFERENCE.md) and
  [../openapi/arclink-v1.openapi.json](../openapi/arclink-v1.openapi.json).
- The Docker-socket/root trust boundary behind the dashboard sidecar and gateway
  brokers (GAP-019, risk-accepted not tenant-safe):
  [operations-runbook.md](operations-runbook.md).
- Gap and proof-gate definitions: [../../GAPS.md](../../GAPS.md).
