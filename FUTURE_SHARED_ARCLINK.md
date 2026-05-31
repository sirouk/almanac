# Future Shared ArcLink

> **DOC_STATUS: north-star / aspirational.** This is a forward-looking architecture
> note, NOT a description of current shape. Read it as the destination, not the map.
>
> **What IS built today (single-control-plane, implemented and tested locally):**
> ArcLink already ships *intra-Control-Node* sharing — every recipient is a row in
> `arclink_users` on the same control database, not a separate sovereign node. The
> real, local building blocks are:
> - **Share grants** (`arclink_share_grants`, lifecycle in `python/arclink_api_auth.py`):
>   owner-approval and same-account auto-accept, with `resource_kind ∈ {drive, code,
>   pod_comms, notion}`, `resource_root ∈ {vault, workspace}` (Notion roots `{notion,
>   ssot}`), and `access_mode ∈ {read, read_write}` (read_write limited to Drive/Code).
> - **Linked resources** — recipient-side projections materialized in the recipient
>   Pod's `linked-resources` state root: `living_symlink` for Drive/Code, virtual
>   `ssot_inherited_subtree` for Notion. No-reshare is enforced at creation and at the
>   Linked root.
> - **Ephemeral claim-nonce broker** (`arclink_share_claim_nonces`, prefix `asn_`,
>   12h TTL, hashed-only) plus the deployment-scoped share-request broker
>   (`POST /user/share-grants/broker`, OFF by default).
> - **Git fleet shared folder** (`python/arclink_fleet_share.py`, 2026-05-29): a
>   per-Captain bare hub (`/arcdata/captains/<user>/fleet-shared.git`) git-synced to a
>   writable **Fleet** root in Drive/Code, multi-writer with conflict-surfacing.
>
> **What remains UNBUILT (this document's vision):** the cross-sovereign-**node** mesh —
> per-instance keypairs, signed inter-instance requests, durable inter-node trust
> records, and node-to-node scope tokens. None of that exists in code. The scope
> strings below (`share:vault:read`, ...) are aspirational and do NOT match the real
> `resource_kind` / `resource_root` / `access_mode` model named above; treat them as
> design sketches, not current identifiers.
>
> For the route catalog see [docs/API_REFERENCE.md](docs/API_REFERENCE.md) and
> [docs/openapi/arclink-v1.openapi.json](docs/openapi/arclink-v1.openapi.json); for the
> trust boundary around Docker-socket/root services (GAP-019) see
> [docs/arclink/operations-runbook.md](docs/arclink/operations-runbook.md); for the gap
> taxonomy (GAP-014/015/016) see [GAPS.md](GAPS.md).

ArcLink should be designed around sovereign individual deployments first, with
optional collaboration links added later through explicit mutual consent.

This is not the initial launch shape. It is a north-star architecture note for
how ArcLink can grow without forcing every user into one shared host, one shared
database, or one operator-controlled workspace.

## Core Idea

Every ArcLink deployment is its own sovereign node.

Each node owns its own:

- user identity
- billing relationship
- secrets and provider credentials
- vault
- QMD index
- Notion/SSOT configuration
- agents and Hermes homes
- memory stubs
- health state
- audit trail
- admin controls

By default, nothing is shared between nodes.

Later, two or more ArcLink nodes can form a scoped collaboration link. They do
not become one instance. They create a bridge.

## Why This Fits ArcLink

The inherited shared-host model is powerful:

```text
one operator
one host
many users
shared services
operator-approved onboarding
```

That model should remain available where it is useful, but the productized
ArcLink direction is cleaner if it starts from:

```text
one user or customer
one deployment
private services
private data
optional collaboration
```

This gives ArcLink better privacy, security, billing, portability, and scale.
Collaboration becomes an intentional capability rather than a default
multi-tenant risk.

## Collaboration Model

Collaboration should require mutual action.

Example flow:

1. Alice sends a collaboration invite from her ArcLink dashboard or bot.
2. Bob receives the invite in his ArcLink dashboard or bot.
3. Bob sees the requested scopes before accepting.
4. Both ArcLink instances write a signed trust record.
5. The collaboration appears as a shared workspace, project, or pairing.
6. Either side can revoke it.

The default stance is isolation. Sharing is explicit, scoped, reversible, and
audited.

## Scope Examples

> **Aspirational, not current identifiers.** The strings below are a design sketch for
> the future cross-node mesh. They do NOT exist in code. The shipped intra-Control-Node
> model instead expresses sharing as `resource_kind ∈ {drive, code, pod_comms, notion}`
> × `resource_root ∈ {vault, workspace}` (Notion `{notion, ssot}`) × `access_mode ∈
> {read, read_write}` on an `arclink_share_grants` row — see `python/arclink_api_auth.py`.

Scopes should be small enough to reason about:

```text
share:vault:read
share:vault:write:/Projects/Example
share:qmd:search
share:qmd:retrieve
share:notion:read
share:notion:write
share:mcp:tool:project_status
share:memory:stubs
share:agent:message
```

ArcLink should avoid broad "share everything" permissions in the first version.

## Trust Records

Each side should store a durable trust record:

```text
local_instance_id
remote_instance_id
remote_public_key
shared_workspace_id
allowed_scopes
created_by
accepted_by
created_at
accepted_at
expires_at
revoked_at
audit_policy
```

API keys alone are not enough for this layer. Long-term instance collaboration
should use signed requests with per-instance keypairs, short-lived tokens, and
explicit revocation.

> **Unbuilt today.** No per-instance keypair, `remote_public_key`, signed
> inter-instance request, or durable inter-node trust record exists in code. The
> shipped sharing layer is single-control-plane: an `arclink_share_grants` row whose
> recipient is another `arclink_users` row on the *same* control database. The
> short-lived, revocable, hashed-only primitive that DOES exist is the ephemeral
> claim-nonce (`arclink_share_claim_nonces`, prefix `asn_`, 12h TTL) — a within-node
> analogue, not a cross-node trust record.

## Vault Sharing

Vault collaboration should start with explicit shared folders or project
namespaces.

ArcLink should not sync an entire vault by default.

Safer first version:

- user chooses a folder or project to share
- remote instance receives only approved files or approved retrieval access
- provenance is attached to every shared file
- writes are logged with actor, source instance, timestamp, and reason

Possible backends:

- Nextcloud/WebDAV for file-level sharing
- Git for project-style versioned sharing
- object storage for later scale
- MCP bridge for request-time retrieval

The first implementation should prefer simple scoped retrieval over full
bidirectional sync.

> **Shipped within a single Control Node:** scoped folder sharing already exists two
> ways. (1) Drive/Code **Linked resources** project an accepted owner folder into the
> recipient Pod as a `living_symlink` (no copy), writable in place only for accepted
> `read_write` Drive/Code shares, with no-reshare enforced. (2) The git-backed **Fleet
> shared folder** (`python/arclink_fleet_share.py`) gives a Captain's own Pods a
> multi-writer, conflict-surfacing project folder via a per-Captain bare hub. Both are
> intra-node (same control database); the cross-sovereign-node version above is the
> unbuilt extension. Remote git-hub transport (ssh/https) is infra-gated.

## QMD Sharing

QMD indexes should remain local at first.

Instead of merging indexes, an ArcLink node can expose a scoped QMD search MCP
tool to trusted peers.

Recommended first pattern:

```text
remote_query -> local authorization check -> scoped QMD search -> snippets/stubs
```

Full document retrieval should require an additional scope. This prevents QMD
from becoming an accidental open data pipe.

## Notion And SSOT Sharing

ArcLink should not try to merge two private Notion workspaces.

Safer first version:

- create or designate one shared Notion space
- both ArcLink nodes receive brokered access to that space
- each node mirrors relevant shared state into its local memory stubs
- every write goes through the SSOT broker and audit trail

Local private Notion data remains private unless explicitly shared.

> **Shipped analogue (intra-node, marker only):** a Notion share grant materializes a
> virtual `ssot_inherited_subtree` projection (no filesystem, always read-only) inside
> the recipient's Linked root. No real cross-workspace Notion brokering exists yet — the
> brokered shared-SSOT space above remains the north star. Live external Notion mutation
> is proof-gated behind `PG-NOTION`.

## Agent Collaboration

Agents should remain loyal to their owner.

An agent should not gain open access to another user's vault, tools, or memory.
Instead, collaboration happens through scoped tools:

- ask remote ArcLink for approved project context
- search a shared QMD scope
- append to a shared SSOT page
- send a message to a paired agent
- request a summary from a remote project memory stub

This preserves the core boundary:

```text
collaboration without dissolving ownership
```

## Product Shape

This could become:

- ArcLink Pairing
- ArcLink Mesh
- Shared Workspaces
- Linked Instances

The product promise:

- start solo with no setup burden
- invite someone later without migrating everything
- share only what the collaboration needs
- revoke access cleanly
- keep billing and ownership separate
- let agents collaborate without exposing private data by default

## Security Requirements

This feature should not be built without:

- per-instance public/private keys
- signed inter-instance requests
- short-lived scoped access tokens
- immediate revocation checks
- append-only audit logs
- visible sharing state in the dashboard
- per-scope approval UX
- rate limits
- replay protection
- clear data provenance

Sensitive scopes should require stronger confirmation.

## Risks

Important risks:

- broad sharing scopes can leak private vault data
- revoked peers may retain data they already retrieved
- Notion permission models can become confusing
- bidirectional file sync can create conflicts
- remote MCP tools can become unsafe if too powerful
- shared memory stubs can blur source authority
- users may not understand what is shared unless the UI is very clear

The first version should be conservative.

## Build Order

Do not build this before the core individual deployment is excellent.

Recommended order:

1. Launch sovereign individual ArcLink deployments.
2. Make dashboard sharing state visible even before sharing exists.
3. Add stable instance identity and keypair generation.
4. Add invite/accept/revoke trust records.
5. Add scoped remote QMD search.
6. Add shared project folder or namespace.
7. Add shared SSOT workspace support.
8. Add agent-to-agent collaboration tools.
9. Add richer workspace/team UX.

## Design Rule

Never assume collaboration means the same machine, same database, same vault, or
same operator.

Assume collaboration means trusted, scoped, revocable links between sovereign
ArcLink instances.

