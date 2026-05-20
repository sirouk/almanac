# ArcLink User Journey

> REFERENCE DRAFT — NOT GROUND TRUTH. A quick v0 seed kept only as input for the
> Ralphie journey/gaps audit. The audit independently regenerates the root
> `USER_JOURNEY.md` from fresh source evidence and may improve on, contradict,
> or discard anything below. Treat no claim here as verified.

This is the first-sweep journey atlas for ArcLink: the simple, complete story
the product should tell when every intended rail is in place. `GAPS.md` is the
companion truth register for what still needs proof, policy, code, tests, or
operational evidence.

ArcLink's promise is that a Captain can go from "I want my own useful AI crew"
to a living private ArcPod without understanding the host machinery. Raven
guides the human path. The Control Node and Shared Host rails handle the system
path. The Agent arrives with chat, workspace, memory, knowledge, files, code,
terminal, backups, health, and governed sharing already aligned.

## Cast

| Term | User-facing meaning |
| --- | --- |
| Raven | The Captain-facing guide and control conduit. |
| Captain | The paying owner of an ArcLink deployment. |
| Agent | The Hermes-powered occupant of a provisioned deployment. |
| Crew | A Captain's Agents. |
| ArcPod or Pod | A provisioned private deployment. |
| Operator | Platform/admin/deploy role, not customer copy. |

## One-Line Story

A Captain meets Raven on the web, Telegram, or Discord; answers a few grounded
questions; pays; ArcLink provisions a private ArcPod; Raven hands over the
right links and credentials; the Agent wakes in the Captain's chosen channels
with a real dashboard, governed knowledge, a workspace, health rails, and
clear recovery paths.

## End-To-End Spine

| Joint | Captain experience | System behind it |
| --- | --- | --- |
| Entry | The Captain starts on the website, Telegram, or Discord. | Hosted API starts or resumes onboarding sessions; public bot adapters normalize Raven flows. |
| Orientation | Raven asks what to call the Captain, what the Agent should help with, and what plan/provider shape fits. | Onboarding state records choices without exposing secrets. |
| Payment | The Captain chooses Founders, Sovereign, Scale, add-agent, or refuel options where available. | Stripe entitlement events gate provisioning; local code treats live payment proof as credential-gated. |
| Provisioning | Raven says the Pod is being prepared instead of exposing infrastructure chores. | Control Node places the deployment, renders intent, applies executor work, and records audit/health. |
| Handoff | Raven returns dashboard, files, code, Hermes, and first-contact instructions with one-time credential handling. | Credential handoff is acknowledged and then hidden; recovery uses rotation/reissue rails. |
| First day | The Captain talks to the Agent, opens the dashboard, uploads knowledge, links Notion, and sees workspace readiness. | Hermes gateway, qmd, vault, Notion SSOT, memory synthesis, dashboard plugins, and health timers line up. |
| Everyday work | The Captain switches Agents, links channels, approves shares, checks health, refuels, and asks Raven for control actions. | Public bot sessions, notification outbox, share grants, provider state, billing state, and admin queues stay scoped. |
| Recovery | If something fails, the Captain gets a plain recovery action rather than raw host instructions. | Health, refresh, retry-contact, release state, action worker, and deploy/upgrade rails carry the repair path. |

## Entry Paths

Web entry begins in the product surface and posts to the hosted API. The
Captain can start onboarding, resume an existing session, view dashboard state,
and later return directly to their ArcLink console.

Telegram entry begins with Raven in a public bot chat. Telegram cannot cold-DM
a new per-user Agent bot, so the final handoff tells the Captain which bot
handle to open and to press Start. ArcLink's Telegram `/start` hook converts
that first Start into the normal Agent greeting.

Discord entry begins with Raven in DM or the configured public bot context.
After provisioning, ArcLink opens the Captain's DM with the new user-agent bot
by Discord user id. If the bot DM does not arrive, the Captain can ask Raven
for `/retry-contact`; operators can also retry by username or Discord name.

Linked-channel entry happens after one channel is already trusted. The Captain
asks Raven to link a second channel, receives a temporary code, contacts Raven
on the other platform, and claims the link. The channel inventory grows without
letting one account overwrite another account's channel.

## Plan And Payment Choices

The Captain's plan decides the default size of the Crew and the entitlement
shape. Limited 100 Founders, Sovereign, Scale, agent expansion, and ArcPod
Refueling are product lanes. Local code can model the entitlements, SKU
metadata, and credit ledger. Live checkout, live payment webhooks, and live
provider value movement stay proof-gated until explicitly authorized.

Payment is the provisioning gate. The ideal experience is calm: Raven does not
ask the Captain to understand Stripe webhooks, deployment queues, fleet hosts,
or executor adapters. The system waits for entitlement truth before a Pod can
move to provisioning-ready.

Failed renewal is not mysterious. Provider access suspends immediately, Raven
warns immediately and daily, day 7 language mentions account/data removal, and
day 14 queues audited purge only after warning delivery has been attempted and
recorded.

## Provisioning Story

For the Captain, provisioning is "Raven is preparing your ArcPod." For the
system, it is a chain:

| Decision | Path |
| --- | --- |
| Shared Host vs Control Node | Shared Host is operator-led enrollment; Control Node is paid self-serve onboarding and provisioning. |
| Docker Shared Host vs Control Docker | `deploy.sh docker` validates the Shared Host substrate; `deploy.sh control` runs the paid self-serve control plane. |
| Single-machine vs fleet | Control deployment style decides local starter execution or SSH fleet placement. |
| Domain vs Tailscale | Domain mode renders Cloudflare/Traefik intent; Tailscale mode skips Cloudflare DNS and uses tailnet publication. |
| Local vs SSH executor | The executor applies Docker Compose locally or over SSH while keeping secret material out of public docs. |
| Ready vs rollback/teardown | Health and audit events decide handoff, retry, rollback, or cancellation teardown. |

The Pod should include Hermes gateway/dashboard, qmd, vault watch, PDF ingest,
memory synthesis, notification delivery, health watch, Nextcloud/files where
enabled, Drive, Code, Terminal, managed context, and the provider route.

## Credential Handoff

The Captain sees credential handoff once, with direct copy-and-store language.
After acknowledgement, ArcLink hides the handoff material from future user API,
UI, and bot responses. Later recovery should be a reissue or rotation action,
not a replay of old secret material.

Hermes dashboard entry should land in the real Hermes dashboard when the Pod is
live. Local rendering can prove scoped links exist; real runtime access remains
a live proof gate until an authorized deployed Pod/browser check has passed.

## Dashboard Day One

The user dashboard should answer six questions quickly:

| Question | Dashboard answer |
| --- | --- |
| Is my Pod alive? | Service health, provisioning state, recovery actions. |
| Where do I work? | Drive, Code, Terminal, Hermes, files, and workspace links. |
| What do I owe or own? | Plan, billing posture, renewal/refuel state. |
| What model/provider path am I on? | Chutes/router/provider status without raw tokens. |
| What channels are connected? | Telegram/Discord connection and selected Agent state. |
| What needs me? | Credential acknowledgement, Notion setup, backup setup, share approvals, degraded service actions. |

Unavailable states should be honest. A disabled Terminal, pending dashboard
link, proof-gated provider state, or failed service should not be disguised as
success.

## Raven After Onboarding

Raven remains useful after payment and provisioning. Raven can show Agent
inventory, switch the selected Agent, answer status, start channel linking,
prepare Notion setup, prepare backup setup, guide upgrade rails, route selected
Agent chat, and ask the Captain to approve or deny shares.

Telegram command menus need platform-safe underscore names, while aliases such
as hyphenated commands may remain useful in chat. In active public Telegram
chats, Raven controls move behind the Raven command namespace so the selected
Agent can own bare slash commands without command collisions.

Raven identity can be customized at the message/account/channel layer. If a
platform cannot mutate a bot's display profile per channel, the selected-Agent
label must stay visible enough that the Captain always knows who is speaking.

## Agent And Crew

A new Agent gets a private Hermes home, ArcLink-managed context, official
Hermes skills from the pinned runtime, org-published skills where configured,
Drive/Code/Terminal dashboard plugins, Telegram `/start` support, reaction
defaults, home-channel repair, and a bootstrap token injected by the ArcLink
plugin rather than pasted by the user.

As the Crew grows, the Captain can switch selected Agents from Raven. The
system must never let selected-deployment metadata route one Captain into
another Captain's Agent, channel, dashboard, provider state, or files.

## Knowledge And Memory

The Captain should experience knowledge as "put it where ArcLink can see it;
the Agent knows how to find it." The machinery stays governed:

| Rail | Role |
| --- | --- |
| Vault | Markdown/text/PDF source lane for the Captain and Agents. |
| qmd | Search/fetch index over vault, PDF sidecars, and shared Notion markdown. |
| Notion SSOT | Brokered shared-root read/write lane with destructive operations guarded. |
| PDF ingest | Converts PDFs into generated markdown sidecars. |
| Memory synthesis | Builds compact recall cards and stubs from bounded source signatures. |
| Managed context | Tells the Agent what exists and which retrieval tools to use, without dumping all knowledge into prompt context. |

Agents should prefer ArcLink MCP tools such as `knowledge.search-and-fetch`,
`vault.search-and-fetch`, `vault.fetch`, `notion.search-and-fetch`,
`notion.fetch`, `ssot.read`, and `ssot.write`. Almanac is knowledge-store
lineage vocabulary, not the top-level product name.

## Workspace

Drive is for browsing and managing files inside allowed roots. Code is for
workspace edits and git-aware reads in the configured scope. Terminal is a
managed pty surface with session controls and guardrails. All three should be
dashboard-native and isolated to the Captain's permitted workspace.

Accepted linked resources appear under a read-only `Linked` root. Recipients
may copy or duplicate accepted content into their own owned Vault or Workspace,
but the linked source remains read-only and non-reshareable.

Browser right-click share-link creation is intentionally not a shipped promise
until a live ArcLink broker or approved Nextcloud/WebDAV-backed adapter exists,
is tested, and is enabled.

## Sharing

The ideal share path is:

| Step | Experience |
| --- | --- |
| Request | An Agent or dashboard flow requests a share for a named file or directory. |
| Owner approval | Raven asks the owner to approve or deny. |
| Recipient accept | The recipient logs into their own ArcLink account and accepts. |
| Projection | The resource appears under the recipient's `Linked` root. |
| Boundaries | No reshare, no writes to linked source, audited revoke, path containment. |
| Copy out | Recipient can copy/duplicate into owned space when policy allows. |

## Provider And Refueling

Chutes is the default provider lane, with ArcLink enforcing scoped credentials,
budget state, router boundaries, and sanitized usage metadata. The long-term
experience should make model access feel like part of the Pod, not a private
token juggling exercise.

The unsettled provider choices are important: per-user Chutes OAuth, operator
key lifecycle, threshold continuation behavior, self-service provider changes,
and live Refuel purchase/provider application all require proof or policy
before they become public promises.

## Admin And Operator Journey

The Operator sees the whole system through deploy rails, health checks,
release state, component pins, action queues, service units, enrollment status,
Control Node logs, Docker/shared-host menus, live proof tools, and private
state backups. The Captain sees only their own deployment truth.

Ordinary code changes deploy through commit, push, and `./deploy.sh upgrade`.
Shared Host Docker validation stays under `./deploy.sh docker`. Paid self-serve
Control Node work stays under `./deploy.sh control`.

## Recovery Paths

| Failure | Human path | System path |
| --- | --- | --- |
| Discord Agent DM missing | Ask Raven `/retry-contact`. | Reuse stored confirmation code and queue root-side handoff. |
| Telegram Agent not awake | Open the bot handle and press Start. | `/start` hook rewrites first Start into an Agent greeting. |
| Dashboard link fails | Ask for refresh/health, not host surgery. | Agent refresh, dashboard proxy, service health, release state. |
| Knowledge misses a file | Wait for qmd/vault timer or ask for refresh. | qmd refresh, vault watch, PDF sidecar cleanup, Notion indexing. |
| Notion write refused | Use shared SSOT parent or approved path. | SSOT broker rejects unsafe/destructive/private-parent writes. |
| Billing fails | Restore payment before data-removal window. | Suspension, warnings, audit, day-14 purge queue. |
| Provider exhausted | Follow policy-approved continuation/refuel path. | Provider state blocks or warns without leaking raw keys. |
| Share wrong or stale | Deny, revoke, or reissue. | Owner-scoped grants, audit, projection cleanup. |

## Trust Boundaries

ArcLink's magic depends on boringly strict boundaries. One Captain must not be
able to read, mutate, infer, route to, or share another Captain's deployment,
channels, dashboard, files, provider state, billing state, Notion state,
Hermes resources, Agent roster, or health data unless an explicit accepted
share grants only the intended resource.

The product can feel simple only because every rail knows what it is allowed to
touch.
