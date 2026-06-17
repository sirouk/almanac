# CANON-19 — Hermes Workspace & Dashboard — DECIDED (final adjudication)

- Piece: CANON-19 (Hermes Workspace & Dashboard)
- Codex proposal: `research/canon/decisions/CANON-19-workspace-dashboard.codex.md`
- Adjudicator: Claude Opus 4.8 (1M) FINAL ADJUDICATOR, ArcLink two-model Federation, DECISION mode
- Method: each deferred item re-opened in the live tree (Read/rg). Symphony is intent; code is reality; the plan moves code toward the symphony while failing closed.
- North Star anchor for the whole piece: "Operators own the universe: hosts, secrets, fleet, policy, upgrades, backups, live proof... Captains own their Pods and Crew, not the host" (symphony §North Star, L116-118); "Every step should have a local source owner, a local regression or dry-run proof where possible, and a named live proof gate... how it fails closed" (§Whole-System Traversal, L158-161).

Four deferred operator decisions. Summary verdicts: D1 **refine** (Codex right, scope-correct one alternative), D2 **refine** (right policy, correct the "default" framing to match code), D3 **agree-codex**, D4 **agree-codex**.

---

## DECISION 1 — Backup deploy-key private-ref rail has no consumer  [VERDICT: refine]

### Question
`request_arclink_backup_deploy_key` stages a real ed25519 private key on disk and writes
`backup_deploy_key_private_ref = server_state:agent-backup-deploy-key:<digest>` into deployment
metadata, but nothing consumes that ref. Keep, wire, or remove the rail?

### Independent reasoning (code-grounded)
Re-walked the producer and every candidate consumer:
- Producer: `python/arclink_dashboard.py:1231-1307` asserts ownership, requires a recorded private repo,
  shells `ssh-keygen -t ed25519` into `<key_staging_dir>/<sha256(dep)[:24]>/arclink-agent-backup-ed25519`
  with `0o600` (`:1125-1147`), and writes `backup_deploy_key_private_ref` (`:1272`, helper `:1111-1113`).
- Consumer of the ref: **none.** `rg` for `backup_deploy_key_private_ref` / `server_state:agent-backup-deploy-key:`
  returns only the producer. The action-worker `backup_write_check` branch
  (`python/arclink_action_worker.py:1026-1059`) never runs git — it calls
  `record_arclink_backup_write_check_failed_closed` unconditionally and returns `failed_closed`.
  Activation is force-pinned `not_active` unless `github_write_check=="verified"`
  (`dashboard.py:1176-1177`), and nothing can ever set `verified`.
- Shipped backup uses a **different** key on a **different** lane:
  `AGENT_BACKUP_KEY_PATH=${...:-$HOME/.ssh/arclink-agent-backup-ed25519}`
  (`bin/backup-agent-home.sh:39,200`; `bin/configure-agent-backup.sh:36,243`), provisioned from
  `arclink-agent-backup.env` (consumed at `arclink_enrollment_provisioner.py:758`).

So today there are two private-key truths for "agent backup": a per-agent backup key that the backup
script actually uses, and an **orphaned** dashboard-staged deploy key that is written to disk, never
read, never rotated, and never activatable. This is a real residual: an unused private key persisting
on operator-controlled disk with no lifecycle.

The symphony is unambiguous about the target shape: backup must mean activation "only after read and
dry-run write checks pass" (§Backup L941-942), the key lifecycle is an Operator-owned product surface
with "status without disclosure: missing, present, invalid, expiring, stale, rotated, revoked,
live-proof pending, or blocked" and "deploy keys remain separated by lane" (§Secrets L1050-1051,
L1054-1055), and provisioning moves *references* not plaintext (§Secrets L1049). The rail is correct
in shape; it is just half-built.

### Agree / differ from Codex
Agree with Codex's core: preserve the public contract, make the rail real by adding a CANON-22
resolver/verifier that maps only the `server_state:agent-backup-deploy-key:` prefix to the staging
root, rejects missing/symlink/permission-bad keys, runs GitHub read + dry-run write **only under
`PG-BACKUP`**, and flips activation to `active` only after a real write proof — migrating orphaned
metadata to inactive/failed-closed evidence rather than deleting it silently. That is exactly the
symphony's "activation only after read and dry-run write checks pass" + "preserve state by default +
leave redacted evidence" shape.

Where I **refine**: Codex's "high effort, touch ~6 subsystems now" plan over-commits the operator to
building the live verifier in one swing, and it leaves the *two-key-lanes* divergence as an
unaddressed "alternative." The symphony's "deploy keys remain separated by lane" is satisfied either
by making the dashboard-staged key the canonical backup deploy key (one lane) **or** by keeping both
lanes with one clearly the backup-write deploy key and one the storage key — but it is NOT satisfied
by silently keeping two competing keys both named "agent backup." So the converged plan splits into a
small **fail-closed-honesty** step that ships now and a **PG-BACKUP live verifier** step that lands
the rail, and forces the lane-unification call explicitly (see standing disagreement).

### FINAL PLAN
1. **Now (low, ship-with-the-release):** Stop the rail from masquerading as half-done. The dashboard
   producer already returns a `verification` block; make the orphaned state legible: when a key is
   staged but no verifier is armed, project `deploy_key.status = "staged_pending_operator_verifier"`,
   `github_write_check = "not_run"`, `backup_activation = "not_active"`, and a redacted reason
   ("private backup-repo activation is PG-BACKUP gated; no live git write has run") — i.e. make the
   read model say *blocked, here is why, here is the gate*, matching §Cross-Surface "Errors should say
   what failed, what is safe, what is blocked, and what Raven can do next" (L458). No new key material,
   no schema change. This is the fail-closed honesty the rail lacks today.
2. **Real rail (high, PG-BACKUP):** Add a CANON-22 resolver `resolve_backup_deploy_key(private_ref)`
   that (a) accepts ONLY the `server_state:agent-backup-deploy-key:` prefix, (b) maps to
   `<key_staging_dir>/<digest>/arclink-agent-backup-ed25519` with `O_NOFOLLOW`/`lstat` symlink + mode
   `0o600` rejection, (c) is invoked by a new action-worker `backup_write_check` live path that runs a
   GitHub *read* then a *dry-run write* under `PG-BACKUP`, and (d) writes `github_write_check="verified"`
   + `backup_activation="active"` **only** on a real write proof, recording redacted evidence. Until
   that path is armed, the worker keeps returning `failed_closed` (it already does). Migrate any
   pre-existing orphaned metadata to the step-1 "blocked" projection, never delete.
3. **Lane unification (operator call, see standing disagreement):** decide whether the
   dashboard-staged deploy key BECOMES the canonical backup-write key (retire the separate
   `$HOME/.ssh/arclink-agent-backup-ed25519` write-credential role) or whether the two stay as
   storage-vs-write deploy keys with documented, distinct lanes. Do not ship the live verifier (step 2)
   until this is decided, or it will cement two truths.

### Symphony anchor
§Backup, Restore, And Data Lifecycle L941-942: "Per-agent Hermes home backup, including private backup
repo activation **only after read and dry-run write checks pass**." §Secrets, Keys, And Rotation
L1049,1054-1055: "Secret references move through provisioning instead of plaintext values"; "Deploy keys
remain separated by lane." §Whole-System Traversal L155-156: upgrades/backups/restore "preserve state by
default and leave redacted evidence."

### Effort / blast-radius
Step 1: **low** — dashboard read-model projection + `tests/test_arclink_dashboard.py`. Step 2: **high** —
CANON-22 resolver, action-worker live branch, migration of orphaned rows, redacted evidence, Raven/web
backup status copy, `tests/test_arclink_action_worker.py`. Step 3: **policy decision only.** Blast radius
of step 1 is contained (read model); step 2 touches the live backup lane and is PG-gated.

---

## DECISION 2 — Docker/domain dashboard SSO is silently generated and enabled  [VERDICT: refine]

### Question
Should cross-dashboard SSO stay silently generated-and-enabled, or become explicit operator policy
(default disabled)?

### Independent reasoning (code-grounded)
Re-walked the full producer→consumer chain; the reconciled doc's correction ("SSO is LIVE, not dead")
holds and I confirmed it:
- `bin/arclink-docker.sh:1696-1718` `sso_secret_for_subject` reuses a sibling per-user secret if one
  exists, else **generates `secrets.token_urlsafe(32)`** — there is no enable flag; presence of a secret
  is the enable.
- `:2044-2047` passes `ARCLINK_DASHBOARD_SSO_SECRET_FILE/SUBJECT/COOKIE_DOMAIN` to the installer
  **unconditionally** in Docker mode (subject always set; cookie domain only set in domain mode via
  `sso_cookie_domain`, `bin/arclink-docker.sh:1721-1726`).
- `bin/install-deployment-hermes-home.sh:91-103,163-171` writes `sso_session_secret`/`sso_subject`/
  `sso_cookie_domain` into `arclink-web-access.json` whenever the env/file is present.
- The proxy then issues (`auth_proxy.py:604-614,729-735`) and accepts (`:672-691`) the
  `arclink_dash_sso` cookie whenever `sso_session_secret`+`sso_subject` are non-empty. The SSO cookie is
  keyed on **subject(user_id)+secret only**, NOT deployment/prefix/target (`:566-575`) — so one valid
  SSO cookie authenticates the same user across every sibling dashboard, `Path=/`, optionally
  `Domain=<base_domain>`.

So the reach is: any Captain who owns ≥2 ArcPods gets silent single-sign-on across their own fleet of
dashboards, with a per-user secret that the operator never chose to enable and cannot see the status of.
That is a real expanded cookie boundary created as a side effect of provisioning. Severity is MEDIUM
(reconciled): the reach is the same user's own fleet, not cross-tenant.

Symphony test: §Identity L1019-1021 requires that "Session cookies, CSRF tokens, proof tokens... each
have their own lifetime, storage location, revocation path, and audit behavior." The SSO cookie does
have a revocation path (`dashboard_sso_revoked_before`, `auth_proxy.py:690`) — good — but it has **no
operator-visible enable/status surface** and is created by default. §North Star L116: "Operators own...
secrets... policy." An auth surface that silently widens the cookie boundary across a Captain's fleet
without the operator choosing it violates "operators own policy." The fix is opt-in policy + status,
not removal (removal would lose the intended same-account Crew-dashboard convenience,
§Hermes-Dashboard L780-782 wants Captains to see fleet/restore/upgrade state without bouncing between
dashboards).

### Agree / differ from Codex
Agree with Codex's recommendation in full: add `ARCLINK_DASHBOARD_SSO_MODE=disabled|captain_account`,
require an explicit `sso_enabled:true` in the access file before the proxy issues or accepts SSO
cookies, preserve existing secret files unused unless the operator enables/rotates, and surface
`disabled/enabled/legacy_secret_present/revoked` as redacted status. Anchor and rationale are correct.

Where I **refine** (factual precision, not direction): Codex frames this as "default disabled for
new/reconfigured deployments." That is the right *target*, but the symphony's stronger constraint is
§Cross-Surface "same truth across surfaces" + §Config L1083-1085 "Reconfigure is safe... without
silently deleting runtime state." So the converged plan must: (a) make `disabled` the default for NEW
deployments; (b) for EXISTING deployments that already have a working SSO secret, NOT silently flip a
Captain to "log in per dashboard" on the next reconfigure without an operator-visible migration notice —
instead surface `legacy_secret_present` and require the operator to either confirm-enable
(`captain_account`) or confirm-disable, so the change is an operator-owned decision with evidence, not a
silent reconfigure side effect. This keeps it fail-closed (default off) AND non-destructive
(state preserved, operator chooses) — exactly the symphony's two simultaneous constraints. Also gate the
proxy ACCEPT side, not just issuance: `_valid_sso_cookie` must short-circuit to False unless
`access.get("sso_enabled") is True`, so a stale issued cookie stops working the moment the operator
disables.

### FINAL PLAN
1. `bin/arclink-docker.sh` / `install-deployment-hermes-home.sh`: read `ARCLINK_DASHBOARD_SSO_MODE`
   (default `disabled`). Only when `captain_account` do they generate/pass the SSO secret and write
   `sso_enabled:true`. When `disabled`, leave any existing secret file on disk untouched but write
   `sso_enabled:false`.
2. `auth_proxy.py`: both `_make_sso_token`/`_sso_cookie_header` (issue) and `_valid_sso_cookie` (accept)
   return empty/False unless `access.get("sso_enabled") is True` — so disabling is immediate and
   fail-closed regardless of leftover secret material.
3. Dashboard read model + Operator Raven: surface SSO status as
   `disabled | enabled | legacy_secret_present | revoked` (redacted, no secret value), so the operator
   sees the boundary and its revocation state on the same surfaces (§same-truth).
4. Reconfigure migration: existing SSO-secret deployments report `legacy_secret_present` and require an
   explicit operator `captain_account`/`disabled` choice before the proxy resumes issuing/accepting —
   no silent enable, no silent break.
5. Live proof gate: `PG-HERMES-DASHBOARD-SSO` for the cross-dashboard same-account flow; local proxy
   regression tests for disabled-default, enabled-issue/accept, stale-cookie-after-disable, and
   legacy-secret-present.

### Symphony anchor
§Identity, Access, And Session Governance L1019-1021: "Session cookies... each have their own lifetime,
storage location, **revocation path, and audit behavior**." §North Star L116: "Operators own the
universe: hosts, secrets, fleet, **policy**." §Configuration L1083-1085: "Reconfigure is safe for
changing... without silently deleting runtime state."

### Effort / blast-radius
**med.** Touches Docker provisioning, installer, auth proxy (issue + accept), generated config/docs,
dashboard/Raven status copy, and SSO proxy/Docker regression tests. Blast radius is bounded to the
dashboard auth surface; default-off is strictly safer than today, and the accept-side gate makes it
fail-closed. The only Captain-visible change is one extra login per dashboard on legacy deployments
where the operator chooses `disabled`, which scoped per-dashboard login already supports.

---

## DECISION 3 — Auth-proxy login throttle is process-local  [VERDICT: agree-codex]

### Question
The login throttle is an in-memory module dict that resets on restart and is not shared across multiple
proxy processes. Replace it with a durable store; which store?

### Independent reasoning (code-grounded)
Confirmed the throttle is `_LOGIN_FAILURES: dict` keyed by `monotonic()` timestamps
(`auth_proxy.py:63-66`), pruned/checked under a thread lock (`:374-405`), keyed by ip/user/combo
(`:368-371`), enforced at login (`:1065-1067`) and cleared on success (`:1080`). On restart or with a
second proxy process the failure budget resets — a real brute-force window, though bounded (the proxy
fronts one deployment's dashboard, and credentials are already per-deployment).

Symphony test: §Identity L1025-1027: "Rate limits, replay protection, nonce/confirmation... should be
consistent enough that the same action cannot be made safer or more dangerous merely by choosing chat
instead of dashboard." A throttle that silently evaporates on restart is exactly the kind of
made-safer-or-more-dangerous-by-accident inconsistency the symphony forbids. It must survive restarts
and multiple processes, and fail closed if it cannot.

The architecture question is *which* durable store. Two real options:
- (A) Reuse the central control DB `rate_limits` table — there is already a mature pattern,
  `_check_login_rate_limits` (`arclink_api_auth.py:459-523`) doing `BEGIN IMMEDIATE` + window prune +
  account/ip/combo buckets against `rate_limits` (`arclink_control.py:728-733`).
- (B) A local durable SQLite beside `arclink-web-access.json`, mirroring that same schema/pattern but
  NOT requiring every dashboard proxy to hold a write handle to the central control DB.

The decisive symphony principle is the trust boundary: §North Star "Captains own their Pods and Crew,
not the host"; the dashboard proxy is a per-Pod, potentially remote process. Giving every Pod proxy
write access to the central control DB widens that proxy's privilege far beyond "throttle my own
dashboard logins" and complicates remote Pods (they may not even have the control DB locally). The
local-durable store keeps the login boundary **local, auditable, fail-closed** while matching the
existing rate-limit schema — strictly the right boundary.

### Agree / differ from Codex
**Agree fully.** Codex's recommendation — a durable SQLite `arclink-dashboard-login-rate-limits.sqlite3`
beside the access file, reusing the `rate_limits(scope, subject, observed_at)` pattern with
`BEGIN IMMEDIATE`, window prune, deployment/prefix/realm + ip/user/combo scoping, and **fail closed
(no session cookie) if the required store cannot be opened** — is the correct boundary and the correct
reuse. Keeping a memory mode only as explicit test/dev is right. I add one clarification: the
fail-closed-on-unavailable-store must mean "treat as throttled / refuse to issue a session" rather than
"allow," so an unwritable store cannot silently disable protection — Codex says this ("fail closed with
no session cookie if the required store cannot be opened"); make it an explicit tested case.

### FINAL PLAN
1. New module helper (in `auth_proxy.py` or a small `arclink_dashboard_login_limits.py`) backed by
   SQLite at `<access-file-dir>/arclink-dashboard-login-rate-limits.sqlite3` (overridable via
   `ARCLINK_DASHBOARD_PROXY_LOGIN_RATE_DB`), schema `(scope TEXT, subject TEXT, observed_at TEXT)`
   mirroring `rate_limits`, file mode `0o600` (login-failure ip/user pairs are sensitive).
2. Replace `_login_throttled` / `_record_login_failure` / `_clear_login_failures` to do
   `BEGIN IMMEDIATE`, prune by `ARCLINK_DASHBOARD_PROXY_LOGIN_FAILURE_WINDOW_SECONDS`, scope keys by
   `deployment_id|prefix|realm` + ip/user/combo, against the local DB.
3. If the required store cannot be opened/written, **fail closed**: throttle is treated as tripped and
   no session cookie is issued (return 503 "rate-limit store unavailable"), never open.
4. Keep the in-memory implementation behind an explicit `ARCLINK_DASHBOARD_PROXY_LOGIN_RATE_MODE=memory`
   for tests/dev only; durable SQLite is the production default.
5. Tests: restart-persistence, two-process shared-budget, store-unavailable-fails-closed, window prune.

### Symphony anchor
§Identity, Access, And Session Governance L1025-1027: "Rate limits, replay protection... should be
consistent enough that the same action cannot be made safer or more dangerous merely by choosing chat
instead of dashboard." §North Star L118: "Captains own their Pods and Crew, **not the host**" (so the
proxy must NOT get central-DB write privilege — local durable store is the correct boundary).

### Effort / blast-radius
**med.** Touches auth proxy, proxy launcher defaults, access-file-adjacent state permissions, and
throttle tests (restart/multiprocess/unavailable-store). Blast radius bounded to the per-deployment
proxy; no central-DB privilege expansion, which is the whole point.

---

## DECISION 4 — Env-derived dashboard hosts need an allowed-host policy  [VERDICT: agree-codex]

### Question
`_deployment_urls` and `_control_notion_webhook_public_url` build dashboard/Notion URLs from
deployment metadata and operator env with only a `startswith("https://")` filter. Add a host policy?

### Independent reasoning (code-grounded)
Confirmed the gap: `_deployment_urls` (`dashboard.py:825-911`) takes `ingress_mode`,
`tailscale_dns_name`, `tailscale_host_strategy` from `meta` OR `os.environ`
(`ARCLINK_INGRESS_MODE`, `ARCLINK_TAILSCALE_DNS_NAME`, `ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY`,
`:832-840`) and builds `f"https://{host}/u/{prefix}"` from that env-derived host (`:850-853,898-901`).
Stored `access_urls` are accepted with only `startswith("https://")` (`:871,888`) — no host/port/path
constraint. `_control_notion_webhook_public_url` similarly accepts explicit/env hosts. These URLs flow
into Captain-facing dashboard `access.urls`, plugin links, and the SOUL/identity prefill.

Canonical ingress already defines the exact legitimate host shapes:
- Domain mode: `u-{prefix}.{base_domain}`, `hermes-{prefix}.{base_domain}` — and `arclink_adapters.py`
  already owns `arclink_hostnames` (`:233`), `arclink_tailscale_hostnames` (`:246`), and
  `arclink_access_urls` (`:275`). (`docs/arclink/ingress-plan.md:25-36`.)
- Tailscale path mode: `https://{tailscale_dns_name}/u/{prefix}` (`ingress-plan.md:46-56,135-140`).

So the legitimate output space is narrow and already computable from existing adapter helpers; the only
reason a bad host can leak is that the read paths don't validate env/metadata against that space. This
is operator-trust env (not user-controllable), so severity is LOW — but the symphony explicitly says
operator env is still *input*: §Config L1076-1077 generated config must "detect stale, missing,
deprecated, or incompatible values **before services start**," and §Fleet L967-968 ingress is "either
domain... or Tailscale path routing, with clear teardown evidence" — i.e. there IS a defined host shape
and links outside it are incompatible values that should be caught, not rendered.

Critically, validating only in the web client (CANON-03) is too late: Raven and the hosted API emit the
same links, and §Cross-Surface / §Whole-System demand "the same system truth" across surfaces (L153).
A single policy owner consumed by all readers is the only way to keep dashboard, Raven, Notion callback,
web hrefs, and live ingress proof aligned.

### Agree / differ from Codex
**Agree fully.** Codex's recommendation — a single URL/host policy owner in `arclink_adapters.py`,
consumed by all dashboard URL readers, encoding: domain hosts must match generated ArcLink hostnames
under configured base/allowed suffixes; Tailscale hosts must match configured Tailscale/control hosts;
ports only from persisted tailnet service ports; no userinfo/query/fragment/path escape; invalid env or
metadata omit/block and report `blocked_invalid_host_policy`; install/reconfigure fail before
activation — is correct, is the right home (adapters already owns the hostname computation), and has the
right blast radius. The "block read paths but don't delete metadata; require reconfigure to repair"
residual-migration handling matches §Config "without silently deleting runtime state."

One refinement (additive): the policy must reject not just non-`https` schemes but also the subtler
escapes — embedded `@` userinfo (`https://evil.com@real.example/...`), a host that *contains* but
doesn't *equal* the allowed suffix (`u-x.base_domain.evil.com`), and a `path`/`query`/`fragment` that
escapes `/u/{prefix}`. Validate host == one of the generated canonical hostnames (exact match), and for
Tailscale validate `host == configured tailscale_dns_name` AND the path begins with `/u/{prefix}`. That
closes the medium-confidence injection the section's adversarial self-check flagged (`ARCLINK_TAILSCALE_DNS_NAME`
injection).

### FINAL PLAN
1. New validator in `python/arclink_adapters.py`, e.g.
   `validate_arclink_dashboard_url(url, *, prefix, base_domain, ingress_mode, tailscale_dns_name,
   tailnet_service_ports) -> str | None` returning the URL if it exactly matches a generated canonical
   host (reusing `arclink_hostnames`/`arclink_tailscale_hostnames`) with allowed port and no
   userinfo/query/fragment/path-escape, else `None`.
2. `dashboard._deployment_urls` and `_control_notion_webhook_public_url` route every env/metadata-derived
   and stored URL through it; on failure, omit the URL and set a `blocked_invalid_host_policy` marker on
   the deployment card (redacted, names the gate), per §Cross-Surface "what failed... what is blocked."
3. Provisioning/Docker URL materialization and install/reconfigure call the same validator and **fail
   before activation** on an invalid generated/env host (§Config "before services start").
4. Do not delete stored unsafe metadata; block the read and require reconfigure to repair (non-destructive).
5. Tests: valid domain host, valid Tailscale path host, stored unsafe URL blocked, bad
   `ARCLINK_TAILSCALE_DNS_NAME` env fails closed, userinfo/suffix-substring/path-escape rejected.

### Symphony anchor
§Fleet, Provisioning, Ingress, And Recovery L967-968: "Ingress is either domain/Cloudflare/Traefik...
or Tailscale path routing, with clear teardown evidence." §Configuration, Schema, And Migration
L1076-1077: generated config "detect[s] stale, missing, deprecated, or incompatible values **before
services start**." §Whole-System Traversal L153: "Operator Raven, admin dashboard, CLI, diagnostics,
live proof, and evidence rails show the **same system truth**" (one validator, all readers).

### Effort / blast-radius
**med.** Touches adapters (new policy), dashboard read model, provisioning/Docker URL materialization,
hosted web link assumptions, ingress docs, and regression tests. Blast radius bounded — read paths
block-not-delete, and a central validator removes the duplicated, drift-prone per-surface checks.

---

## STANDING DISAGREEMENTS (genuine product forks the operator must decide)

1. **D1 lane choice — does the dashboard-staged backup deploy key BECOME the canonical backup-write key,
   or do the two key lanes (`server_state:agent-backup-deploy-key:<digest>` staging key vs
   `$HOME/.ssh/arclink-agent-backup-ed25519` from `arclink-agent-backup.env`) stay distinct with
   documented storage-vs-write roles?** Both satisfy §Secrets "deploy keys remain separated by lane,"
   but they imply different live verifiers and different rotation stories. The PG-BACKUP live rail
   (D1 step 2) must not ship until this is chosen, or it cements two competing "agent backup" keys.

2. **D2 SSO default on reconfigure of EXISTING deployments — operator confirmation vs leave-as-is.**
   New deployments are unambiguously `disabled` by default. For an existing deployment that already has
   a working per-user SSO secret, the converged plan surfaces `legacy_secret_present` and requires the
   operator to choose `captain_account` or `disabled`. The operator should confirm that this one-time
   "choose your SSO posture on next reconfigure" prompt is acceptable, versus grandfathering existing
   SSO as `enabled` to avoid any Captain re-login (which keeps the silent-default boundary for legacy
   Pods). Recommended: require the explicit choice (fail-closed, operator-owned); flagged because it is
   a UX-vs-strictness fork the operator owns.
