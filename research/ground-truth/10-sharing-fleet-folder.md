# Ground Truth: Sharing broker, Linked resources, Fleet shared folder

Mapped 2026-05-30 (branch `arclink`). Source of truth = code. This record separates
local-real behavior from proof-gated/fake-adapter behavior.

Primary owning files:
- `python/arclink_api_auth.py` — share grant + claim-nonce lifecycle, projection
  materialization, Linked manifest, broker auth, inbox/linked-resources reads.
- `python/arclink_fleet_share.py` — fleet shared folder git sync engine + control-plane CRUD + CLI.
- `python/arclink_hosted_api.py` — HTTP route table for share-grants + linked-resources.
- `python/arclink_control.py` — schema for `arclink_share_grants`, `arclink_share_claim_nonces`,
  `arclink_fleet_shares`, `arclink_fleet_share_members`.
- `python/arclink_provisioning.py` — Linked + Fleet + hub volume mounts, `fleet-share-sync`
  compose job, broker-token secret wiring, env wiring.
- `python/arclink_executor.py` — container dir constants, agent-pod env wiring, rollback protected roots.
- `python/arclink_sovereign_worker.py` — stores broker token hash in deployment metadata.
- `python/arclink_mcp_server.py` — `shares.request` MCP tool + copy/duplicate policy string.
- `python/arclink_public_bots.py` — Raven `/share-approve|deny|accept`, `/raven approve|deny|accept`,
  `/arclink_share_accept <nonce>` dispatch.
- `plugins/hermes-agent/drive/dashboard/plugin_api.py` and `plugins/hermes-agent/code/dashboard/plugin_api.py`
  — Drive/Code root descriptors (Vault/Workspace/Fleet/Linked), writable-Linked logic, `POST /share/request` broker client.

---

## A. What is actually implemented today (local-real)

### Share grant lifecycle (cross-user + same-account)
Canonical table: `arclink_share_grants`. Statuses observed in code:
`pending_owner_approval` → `approved` → `accepted`, plus terminal `denied`, `revoked`, `expired`.
Grant TTL = `ARCLINK_SHARE_GRANT_TTL_SECONDS` = 7 days.

- `create_user_share_grant_for_owner(...)` (arclink_api_auth.py:3057) is the core creator.
  - Resource kinds: `ARCLINK_SHARE_RESOURCE_KINDS = {"drive","code","pod_comms","notion"}`.
  - Origin roots: `ARCLINK_SHARE_RESOURCE_ROOTS = {"vault","workspace"}`; Notion roots
    `{"notion","ssot"}`. Origin from `linked`/unknown roots is rejected
    ("ArcLink share cannot originate from linked or unknown roots") — **enforces no-reshare at creation**.
  - Access modes: `{"read","read_write"}`. `read_write` is hard-limited to `drive`/`code`
    ("ArcLink read_write shares are limited to Drive and Code").
  - **Same-account share** (recipient == owner, different owner/recipient deployments):
    auto-set to `accepted`, projection materialized immediately, audited
    `share_grant_auto_accepted`. Requires both deployments and they must differ.
  - Cross-user share: inserted as `pending_owner_approval`; then
    `_queue_share_grant_owner_notification` attempts to queue a Raven approval prompt.
- HTTP wrappers (all CSRF + user-session gated): `create_user_share_grant_api`,
  `approve_user_share_grant_api`, `deny_user_share_grant_api`, `accept_share_grant_for_recipient`/
  `accept_user_share_grant_api`, `revoke_user_share_grant_api`, `retry_user_share_grant_notification_api`.
- **Approve** (`approve_user_share_grant_api`, :3833): owner-only, requires status
  `pending_owner_approval`; flips to `approved`; queues recipient notification.
- **Deny** (`deny_user_share_grant_api`, :3875): owner-only; flips to `denied`; closed, no projection.
- **Accept** (`accept_share_grant_for_recipient`, :3916): recipient-only; requires `approved`;
  materializes the projection then flips to `accepted` (idempotent if already accepted).
- **Revoke** (`revoke_user_share_grant_api`, :3975): owner-only; revocable from
  `{pending_owner_approval, approved, accepted}`; removes the projection + manifest entry,
  flips to `revoked`. Already-`denied` rejected; already-`revoked` idempotent.
- Every transition writes both an `append_arclink_audit` action and an `append_arclink_event`
  (`share_grant_requested|approved|denied|accepted|revoked|auto_accepted`).
- Expiry: `arclink_api_auth.py:1893+` sweeps `arclink_share_grants` (and nonces) — grants in
  `pending_owner_approval`/`approved` that pass `expires_at` flip to `expired`.

### Linked resources (projection materialization) — "gateway linked resource mounts"
- `_materialize_share_projection(...)` (arclink_api_auth.py:2771) builds the recipient-side
  projection inside the recipient deployment's `linked_resources` state root:
  - **drive/code** → a **living symlink** (`projection_mode: "living_symlink"`) under a per-grant
    slug `<grant_id>-<label>`; file shares get a child symlink, directory shares get a directory
    symlink to the owner source. read_write drive/code shares are **not** chmod read-only;
    read-only shares get `_chmod_read_only`. Source symlinks/sensitive paths/out-of-root targets
    are blocked (`source_symlink`, `source_private`, `source_outside_owner_root`,
    `projection_outside_linked_root`).
  - **notion** → virtual `ssot_inherited_subtree` projection (no filesystem), `linked_root: "notion"`,
    `inherited_subpages` honored, always read-only.
  - **pod_comms** → `not_applicable` projection.
  - States: `not_materialized`, `pending_materialization` (roots/source not yet available — soft,
    retried on accept), `blocked` (security reject), `materialized`, `removed`.
- Linked manifest file `.arclink-linked-resources.json` (`ARCLINK_LINKED_RESOURCE_MANIFEST`)
  written atomically + chmod read-only in the recipient linked root; per-slug entry records
  `grant_id, source_path, linked_path, entry_path, resource_kind, owner_user_id, read_only,
  access_mode, projection_mode: "living_symlink"`. `_upsert_/_remove_linked_manifest_entry`.
- `_remove_share_projection(...)` (:2965) tears down symlink/dir + manifest entry on revoke.
- Container/state-root layout: state root key `linked_resources` →
  `<state_root>/linked-resources` (`_render_share_state_roots`, `render_arclink_state_roots`),
  mounted into `hermes-gateway` AND `hermes-dashboard` at `/linked-resources`
  (`CONTAINER_LINKED_RESOURCES_DIR`). **The most recent commit "Repair gateway linked resource
  mounts" is about ensuring the `linked_resources_volume` (and `fleet_shared_volume`) are mounted
  into the `hermes-gateway`/`hermes-dashboard` services so projections are visible to the agent.**
  Agent-pod env (arclink_executor.py:1207-1209) sets `DRIVE_LINKED_ROOT`, `CODE_LINKED_ROOT`,
  `ARCLINK_LINKED_RESOURCES_ROOT` = `/linked-resources`.

### Writable accepted shares + no-reshare (Drive/Code plugin enforcement)
- Drive/Code expose 4 local roots: `vault`, `workspace`, `fleet`, `linked`
  (`_local_root_descriptors`). The `Linked` root is read-only at the root level but per-entry
  writable: `_linked_entry_writable(entry)` returns True only when manifest
  `access_mode == "read_write"` AND `read_only` is falsy. Only **directory** shares are writable
  from Linked (`_linked_writable_source`: "Only shared folders are writable from Linked");
  the share root itself is "system-managed".
- **No-reshare** is enforced in three places: (1) creation rejects `linked` origin roots;
  (2) `POST /share/request` rejects `linked` root ("Linked resources cannot be reshared from Drive");
  (3) cross-root copy only allowed FROM `linked` INTO owned roots (`_copy_between_roots`:
  "Cross-root copy is only supported from Linked into owned roots").
- Linked git mutations stay blocked (git skip dirs, sensitive-name skips); copy/duplicate from
  Linked into owned Vault/Workspace allowed.

### Ephemeral claim-nonce share (right-click "Share")
- Table `arclink_share_claim_nonces`. Prefix `ARCLINK_SHARE_CLAIM_NONCE_PREFIX = "asn_"`,
  format `asn_<48 hex>`. TTL = `ARCLINK_SHARE_CLAIM_NONCE_TTL_SECONDS` = 12h.
- `mint_share_claim_nonce_for_owner` (:3422) — minting IS the owner's approval; only the HMAC
  hash of the nonce is stored (`_hash_proof_token`, session-pepper based). drive/code only.
- `claim_share_nonce_for_recipient` (:3635) — atomically claims (single-use), then
  `_insert_accepted_share_grant` creates an already-`accepted` grant + materializes projection.
  Generic "invalid or has expired" error for claimed/expired/unknown (no state leak).
- `revoke_share_claim_nonce_for_owner` (:3757) — owner can revoke an unclaimed `pending` nonce.
- Drive/Code `POST /share/request` sends `share_mode="claim_nonce"` (see plugin
  `_share_request_payload`, hardcoded `requested_access: "read_write"`, `reshare_allowed: False`).

### Share-request broker (Drive/Code → hosted)
- Hosted route `POST /user/share-grants/broker` → `create_user_share_grant_from_broker_api`
  (:3283). Contract must be `"arclink-share-grants"`. Auth: deployment-scoped broker token via
  `X-ArcLink-Share-Request-Broker-Token` header (`_SHARE_REQUEST_BROKER_TOKEN_HEADER`), verified
  against a stored **hash** (`_authenticate_share_request_broker`, hash via
  `hash_share_request_broker_token`). Owner user derived from token-bound `owner_deployment_id`.
  `reshare_allowed=True` is rejected. Supports `share_mode` in `{owner_approval, claim_nonce}`.
- Plugin side: broker is **disabled by default**; enabled only when broker URL
  (`DRIVE/CODE_SHARE_REQUEST_BROKER_URL` or `ARCLINK_SHARE_REQUEST_BROKER_URL`) + token file
  (`*_SHARE_REQUEST_BROKER_TOKEN_FILE`) + owner deployment id are all present (`_share_request_state`).
  `status.share_request` advertises `enabled/disabled` + `direct_links: false`. No "Generate share
  link" wording — browsers never mint links directly.
- Provisioning wires the token as ArcPod runtime secret `share_request_broker_token` (mounted into
  `hermes-dashboard`), sets `ARCLINK_SHARE_REQUEST_BROKER_TOKEN_FILE` to the secret target
  (arclink_provisioning.py:1192, :850). Sovereign worker stores only the hash
  (`_ensure_share_request_broker_token_hash` → `set_deployment_share_request_broker_token_hash`).

### Notification rails (owner approval / recipient ready)
- `_queue_share_grant_owner_notification` / `queue_share_grant_recipient_notification` queue a
  `notification_outbox` row to the user's linked Telegram/Discord channel
  (`_share_public_channel_for_user` reads `arclink_onboarding_sessions`), with approve/deny or
  accept buttons. **Buttons use `/raven approve|deny|accept {grant_id}`** to avoid the agent slash
  namespace; legacy `/share-approve|deny|accept {grant_id}` still owner-scoped.
- If no linked public channel: grant still persists `pending_owner_approval`,
  `owner_notification.queued=false` with reason `no_public_channel`/`unsupported_public_channel`.
- `POST /user/share-grants/retry-notification` (`retry_user_share_grant_notification_api`) lets an
  authenticated participant re-queue the currently-waiting owner OR recipient prompt; rejects
  cross-user, rejects caller-supplied targets, returns `queued=false` + recovery hint when no channel.
- `GET /user/share-grants` (`read_user_share_grants_api`) is the dashboard inbox: buckets
  `pending_owner_approvals`, `waiting_on_owner_approval`, `pending_recipient_acceptance`, `summary`.
- `GET /user/linked-resources` (`read_user_linked_resources_api`) lists `accepted` non-revoked grants.

### Fleet shared folder (read-write git-synced, 2026-05-29 decision) — REAL engine
`python/arclink_fleet_share.py`. Tables `arclink_fleet_shares` (1 per owner, UNIQUE owner_user_id)
and `arclink_fleet_share_members` (1 per deployment per share). ID prefixes `flsh_`/`flsm_`.
Share statuses `{active, paused, removed}`; member statuses `{pending, active, removed}`.

- **Hub** = a Captain-scoped *bare* repo independent of any single agent
  (`default_hub_ref`): `ARCLINK_FLEET_SHARE_HUB_URL` (supports `{user}` template / remote ssh/https)
  or per-Captain `ARCLINK_FLEET_SHARE_HUB_ROOT` (default `/arcdata/captains`) →
  `<root>/<user>/fleet-shared.git`. `ensure_hub_repo` inits a local bare repo; remote URLs are
  trusted to be provisioned out of band.
- **Working copy** per active agent at `ARCLINK_FLEET_SHARED_ROOT` (state-root key `fleet_shared` →
  `<state_root>/fleet-shared`, container `/fleet-shared` `CONTAINER_FLEET_SHARED_DIR`).
  `ensure_member_working_copy` clones; quarantines a corrupt `.git` (`*.corrupt`) and re-clones
  rather than wedging.
- **Sync** (`sync_member`): `git add -A` → commit local edits → fetch → rebase onto `origin/main`
  → push `HEAD:main`; non-fast-forward triggers fetch+rebase retry (multi-writer convergence).
  Unresolvable rebase → `status="conflict"`, rebase aborted, local edit preserved (never clobbered).
  Unreachable hub → soft `error`, retried next pass. Injectable transport `SubprocessGitRunner`
  (so unit-tested against real local repos, no live host). Git arg-injection hardening
  (`_assert_safe_git_arg`).
- **Two-tier orchestration**:
  - Control-plane (DB-only, no git): `reconcile_fleet_share_membership` /
    `reconcile_all_fleet_shares` make membership match active deployments
    (`active`/`provisioning`/`provisioning_ready`/`running`); torn-down agents deregistered;
    **hub never touched** so removing any agent (even the first) never orphans the folder.
  - In-pod (git): `sync_local_working_copy` (env-driven, NO control DB) — the cross-machine entry
    point that runs inside the agent pod against `ARCLINK_FLEET_SHARED_ROOT` +
    `ARCLINK_FLEET_SHARE_HUB_URL`.
  - `process_due_fleet_share_syncs` / `run_fleet_share_cycle` = co-located convenience that
    reconciles + syncs in one process (single-host).
- **CLI** (`bin`-less, run via `python3 python/arclink_fleet_share.py`): subcommands
  `reconcile [--user --all --interval]`, `sync [--user --no-reconcile --interval]`,
  `sync-local [--interval]`.
- **Compose wiring**: each generated agent compose includes a `fleet-share-sync` job
  (arclink_provisioning.py:966) = `docker-job-loop.sh fleet-share-sync 120 python3
  python/arclink_fleet_share.py sync-local`, with `ARCLINK_FLEET_SHARED_ROOT` mount and a
  local hub bind at `/fleet-share-hub.git` (`CONTAINER_FLEET_SHARE_HUB_DIR`) when the hub is a
  filesystem path (`_fleet_share_hub_host_ref`/`_fleet_share_hub_container_ref`). Resource limit
  128M/0.25cpu. Drive/Code surface it as the writable `Fleet` root
  (`DRIVE/CODE_FLEET_SHARED_ROOT` env → `/fleet-shared`).
- deploy.sh provisions `ARCLINK_FLEET_SHARE_HUB_ROOT` (default `/arcdata/captains`) on the host
  with correct ownership (bin/deploy.sh:8961+). `bin/arclink-fleet-join.sh` exists for joining a
  machine to the host fleet (separate concern: host fleet, not the shared folder).

---

## B. Proof-gated / fake-adapter / local-only

- **Live bot delivery is proof-gated (`PG-BOTS`)**: owner/recipient Raven prompts, button
  callbacks, and retry-after-channel-link only write local `notification_outbox` rows. No live
  Telegram/Discord delivery proof. Telegram/Discord adapters default to fake mode.
- **Browser share affordance is policy/proof-gated (`GAP-014`)**: `POST /share/request` broker
  contract exists and is unit-tested, but production workspace/browser proof, live recipient
  notification, audit/revoke-from-browser proof, and the operator decision between the native
  ArcLink broker vs a Nextcloud-backed adapter are open. Broker is OFF unless explicitly configured.
- **Remote git hub transport is infra-gated**: cross-host hub via ssh/https
  (`ARCLINK_FLEET_SHARE_HUB_URL`) needs SSH keys/known_hosts or HTTPS creds provisioned out of band
  (`ensure_hub_repo` returns True for remote refs without verifying). Local-filesystem hub
  (`/arcdata/captains/...`) is fully real and unit-tested.
- **Fleet folder durability boundary**: hub is a single bare repo; losing the hub host loses the
  folder (documented, but no replication is implemented in code).
- **Notion share** materialization is a virtual `ssot_inherited_subtree` marker — no real
  cross-workspace Notion brokering is implemented (consistent with FUTURE_SHARED_ARCLINK "brokered
  SSOT" north star, not built).
- The signed-trust-record / per-instance keypair / cross-sovereign-node mesh in
  FUTURE_SHARED_ARCLINK.md is **entirely unbuilt**. What exists is same-control-plane,
  same-user-table sharing (all recipients are rows in `arclink_users` on the same control DB).

---

## C. Canonical vocabulary (real names from code)

- Tables: `arclink_share_grants`, `arclink_share_claim_nonces`, `arclink_fleet_shares`,
  `arclink_fleet_share_members`.
- Routes (hosted, all `/api/v1/...`): `GET /user/share-grants`, `POST /user/share-grants`,
  `POST /user/share-grants/broker`, `.../approve`, `.../deny`, `.../accept`, `.../claim`,
  `.../nonce/revoke`, `.../revoke`, `.../retry-notification`, `GET /user/linked-resources`.
  Plugin: `POST /share/request` (Drive/Code), `GET /status`.
- Constants: `ARCLINK_SHARE_RESOURCE_KINDS`, `ARCLINK_SHARE_RESOURCE_ROOTS`,
  `ARCLINK_SHARE_NOTION_ROOTS`, `ARCLINK_SHARE_ACCESS_MODES`, `ARCLINK_SHARE_GRANT_TTL_SECONDS` (7d),
  `ARCLINK_SHARE_CLAIM_NONCE_TTL_SECONDS` (12h), `ARCLINK_SHARE_CLAIM_NONCE_PREFIX` (`asn_`),
  `ARCLINK_LINKED_RESOURCE_MANIFEST` (`.arclink-linked-resources.json`).
- Fleet: `SubprocessGitRunner`, `GitResult`, `FleetShareSyncResult`, `default_hub_ref`,
  `ensure_hub_repo`, `ensure_member_working_copy`, `sync_member`, `sync_local_working_copy`,
  `reconcile_fleet_share_membership`, `reconcile_all_fleet_shares`, `process_due_fleet_share_syncs`,
  `run_fleet_share_cycle`. ID prefixes `flsh_`/`flsm_`.
- Env: `ARCLINK_FLEET_SHARE_HUB_URL`, `ARCLINK_FLEET_SHARE_HUB_ROOT` (default `/arcdata/captains`),
  `ARCLINK_FLEET_SHARED_ROOT`, `DRIVE/CODE_FLEET_SHARED_ROOT`, `ARCLINK_LINKED_RESOURCES_ROOT`,
  `DRIVE/CODE_LINKED_ROOT`, `ARCLINK_SHARE_REQUEST_BROKER_URL`,
  `ARCLINK_SHARE_REQUEST_BROKER_TOKEN_FILE`, `ARCLINK_OWNER_DEPLOYMENT_ID`.
- Container dirs: `/linked-resources`, `/fleet-shared`, `/fleet-share-hub.git`.
- Compose jobs: `fleet-share-sync` (real, per-agent). Secret: `share_request_broker_token`.
- Header: `X-ArcLink-Share-Request-Broker-Token`. Broker contract: `arclink-share-grants`.
- Raven commands: `/share-approve`, `/share-deny`, `/share-accept`,
  `/raven approve|deny|accept {grant_id}`, `/arclink_share_accept <nonce>` (regex
  `ARCLINK_PUBLIC_BOT_SHARE_CLAIM_RE`). MCP tool: `shares.request`.
- Projection modes: `living_symlink` (drive/code), `ssot_inherited_subtree` (notion).

---

## D. Undocumented / newer-than-docs in code

1. **`fleet-share-reconcile` control-node compose job does NOT exist.** operations-runbook.md
   (lines 219-221) claims a scheduled control-node job `python3 python/arclink_fleet_share.py
   reconcile --all` "every 120s". Only the **per-agent** `fleet-share-sync` job is actually
   rendered in compose (arclink_provisioning.py:966). `reconcile --all` is a CLI verb with **no
   scheduler/service** wiring anywhere (verified: no reference in provisioning, deploy.sh, or any
   compose). Membership reconcile currently only runs if invoked manually or via the co-located
   `run_fleet_share_cycle`. This is a doc overclaim.
2. **MCP copy/duplicate policy string evolved past GAPS.md.** Code now returns
   `copy_duplicate_policy = "accepted_linked_resources_writable_in_place_without_reshare_or_git_mutation"`
   plus `copy_duplicate_destination_roots: ["vault","workspace"]` and a `*_policy_detail`
   (arclink_mcp_server.py:109-115, 1055-1057). GAPS.md GAP-016 (line 746) still documents the OLD
   string `accepted_linked_resources_copy_to_owned_vault_or_workspace_only`.
3. **Same-account cross-deployment share** (`same_account_share`, auto-accept) is fully
   implemented but barely surfaced in docs — useful for one Captain sharing between their own pods.
4. **`paused` fleet-share status** exists in schema/validators but no code path sets it (only
   `active`/`removed` are used by `ensure_fleet_share`/`remove_fleet_share_member`).
5. **Living-symlink projection** (not file-copy) is the implemented model for drive/code; older
   prose sometimes implied copies. `_copy_projection_tree` exists but the active path is symlink.
6. Fleet folder + Drive/Code `Fleet` writable root are **completely absent** from
   data-safety.md and from the symphony doc's Sharing section.

---

## E. Per-doc staleness verdicts

### `FUTURE_SHARED_ARCLINK.md` — staleness: heavy (intentionally a north-star)
- It is an explicit "north-star architecture note", NOT a status doc, so it is not "wrong" — but a
  reader could mistake it for current shape. It describes cross-sovereign-**node** sharing
  (per-instance keypairs, signed inter-instance requests, trust records, mesh). **None of that is
  built.** What exists is same-control-plane, same-user-table sharing.
- Needed correction: add a one-line banner pointing to what IS built today (share grants + Linked
  resources + claim-nonce broker + git fleet folder, all single-control-plane) and clarifying that
  the keypair/mesh layer remains unbuilt. Its scope strings (`share:vault:read`, etc.) do not match
  the real model (resource_kind/resource_root/access_mode).

### `docs/arclink/data-safety.md` (sharing parts) — staleness: light→missing-coverage
- The Linked-root paragraph (lines 45-50) is accurate and current: scoped, read/write for accepted
  Drive/Code folders, no reshare from that root, git mutations blocked, copy into own Vault/Workspace
  via normal boundary, root system-managed.
- **Missing coverage**: zero mention of the **Fleet shared folder** (the 2026-05-29 read-write
  git-synced folder), the claim-nonce ephemeral share, or the share-request broker. Add a short
  data-safety note for the Fleet folder (multi-writer git, conflict-surfacing not clobber, hub
  durability boundary, sensitive-file behavior) and a note that nonce material is hashed-only.

### `docs/arclink/operations-runbook.md` (sharing) — staleness: light (one concrete error)
- Lines 156-264 are otherwise excellent and current (Linked resources, claim-nonce, fleet folder,
  no-channel waiting, Pod Comms). It correctly names tables, routes, env vars, the broker header,
  the `Fleet` root, the hub model, two-tier sync, conflict handling, quarantine-and-reclone.
- **Concrete correction needed**: the `fleet-share-reconcile` control-node compose job
  (lines 218-221) is described as a wired scheduled job but **is not implemented**. Either wire the
  job in provisioning or change the doc to say membership reconcile is currently a CLI verb
  (`reconcile --all`) / part of `run_fleet_share_cycle`, not a standalone scheduled control-node
  service. The per-agent `fleet-share-sync` 120s job IS real.

### `docs/arclink/sovereign-control-node-symphony.md` (Sharing section ~288-310) — staleness: light
- This is the "dream shape". Its bullets (request → audit record → owner approve/deny on
  Raven/dashboard → recipient pending/accepted → Linked roots → writable accepted folders + blocked
  git → copy/duplicate labeled → reshare refused → dashboard inbox/retry recovery) all map to real
  code. It correctly tags GAP-014/015/016 as the open proof.
- **Gap**: no mention of the **Fleet shared folder** as a sharing surface (the doc's "fleet"
  references are all about the host/worker fleet, a different concept). Add the Fleet read-write
  git folder to the sharing dream + ground-truth note. Minor: it says "approve/deny prompt on Raven,
  dashboard, or both" — accurate; dashboard approve/deny/accept is real, Raven delivery is `PG-BOTS`.

---

## F. True current status of GAP-* touched

- **GAP-014** (browser share requests need a live broker/adapter proof): GAPS.md status
  "partial, policy-question" is **accurate**. Local brokered `Request Share` contract + hosted
  `/user/share-grants/broker` route + token-hash auth + provisioning secret wiring all real and
  tested; OFF by default. Open: production browser proof, live recipient notification/callbacks,
  browser-path audit/revoke proof, and the native-broker-vs-Nextcloud-adapter operator decision.
- **GAP-015** (share approval can silently wait without a linked public channel): GAPS.md status
  "proof-gated (`PG-BOTS`)" is **accurate**. `GET /user/share-grants` inbox, dashboard
  approve/deny/accept, `retry-notification`, no-channel recovery hints, single-row local queueing
  all real. Open only: authorized live Telegram/Discord delivery + button-callback proof.
- **GAP-016** (Linked copy/duplicate policy aligned across MCP/docs/tests): GAPS.md status "real /
  locally closed" is **substantively accurate** (policy is one rule, enforced in plugins + MCP +
  runbook). BUT GAPS.md's quoted policy STRING is stale — code now emits
  `accepted_linked_resources_writable_in_place_without_reshare_or_git_mutation` (+ destination roots
  `["vault","workspace"]`), not the `..._copy_to_owned_vault_or_workspace_only` string GAPS.md
  cites. Update the GAP-016 evidence text to the current string.
- No dedicated GAP exists for the Fleet shared folder itself; it is the newest subsystem
  (2026-05-29 decision) and is real-local + remote-hub-infra-gated, currently under-documented in
  data-safety and symphony docs.
