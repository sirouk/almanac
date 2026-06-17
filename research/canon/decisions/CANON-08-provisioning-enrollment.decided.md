# CANON-08 — Provisioning & Enrollment — DECIDED (federation, operator's calls)

Adjudicator: Claude Opus 4.8 final adjudicator (ArcLink two-model Federation), DECISION mode.
Codex proposal: research/canon/decisions/CANON-08-provisioning-enrollment.codex.md.
Method: formed an independent view from symphony + re-opened code (path:line below), then converged
with Codex. The symphony is intent; the code is reality; the plan moves code toward the symphony
while failing closed. Working dir /root/arclink, branch arclink.

Code re-grounding done for this decision (line numbers current as of 2026-06-17, not the reconciled
snapshot):
- `request_operator_action` persists caller-supplied `request_source` verbatim — `python/arclink_control.py:8409-8465` (esp. INSERT at `:8448-8461`).
- `operator_actions` schema has no actor/authorization columns — `python/arclink_control.py:836-848`.
- Provisioner gate is pure string-set membership — `python/arclink_enrollment_provisioner.py:2308-2313` (`CONFIRMED_OPERATOR_ACTION_SOURCES = {"operator-raven"}`), enforced at `:2350` (upgrade) and `:2470` (pin-upgrade).
- Raven writers stamp the literal `"operator-raven"` — `python/arclink_operator_raven.py:1308-1314` (pin) and `:1582-1588` (upgrade).
- Raven producer ALREADY authenticates before queueing: `_require_operator_actor` (`python/arclink_operator_raven.py:401-410`, actor_id non-empty) + `_require_operator_confirmation` (`:413-421`, command.confirmed) gate the upgrade/pin handlers (`:1569-1574`). That proof is then discarded — only the string survives.
- `check_ingress_strategy` returns `ok=True` on BOTH branches — `python/arclink_host_readiness.py:154-161`; included in the `ready` roll-up at `:179-183`; `ReadinessCheck` is `name/ok/detail` only — `:45-49`.
- Provisioning already has a typed ingress-mode contract: `_clean_ingress_mode` rejects anything but `domain`/`tailscale` (`python/arclink_provisioning.py:702-706`); `_clean_tailscale_strategy` requires `path` (`:709-718`); reads `ARCLINK_INGRESS_MODE`, `ARCLINK_TAILSCALE_DNS_NAME`, `ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY` (`:1116-1117,1441-1483`).
- Hosted API HAS a trust-aware resolver `_remote_ip_from_headers` (forwarded headers trusted only from an allowed direct peer) — `python/arclink_hosted_api.py:633-653` — used for CIDR/rate-limit/login (`:686`, `:4142`). The fleet callback BYPASSES it: `_handle_fleet_enrollment_callback` does not receive `remote_addr` and feeds raw `x-real-ip`/`x-forwarded-for` straight into `source_ip` — `:2089-2108` (esp. `:2107`); `remote_addr` is in scope at the dispatch call site (`:4140` vs `:4142`).
- `consume_fleet_enrollment` stores `source_ip` only as audit metadata, never as authority — `python/arclink_fleet_enrollment.py:525-533,632-633`. Authorization is the Bearer token + stored-hash/HMAC compare (`:534`, reconciled #12).
- Cross-check on a stale reconciled MEDIUM: the non-Docker pin path NOW carries `ALLOWED_PIN_COMPONENTS` and enforces it — `python/arclink_enrollment_provisioner.py:104,449`. That MEDIUM is closed in current code; it is not one of the three deferred decisions, noted only so the operator is not chasing a fixed item.

---

## DECISION 1 — `operator_actions.request_source == "operator-raven"` is a string convention, not a capability boundary
[VERDICT: refine]

QUESTION: Should the operator-source gate stay a string convention, or become a real authorization
boundary — and if so, how heavy?

INDEPENDENT REASONING.
The symphony is unambiguous that this must become real authority, not a string. Identity, Access, And
Session Governance: "Admin and Operator actions should never trust client-asserted privilege ...
without server-side authorization and typed action resolution." Admin Dashboard, API, And CLI Control:
"Mutating actions should converge on one action model with actor, reason, scope, nonce/confirmation,
redaction, result, and rollback/repair guidance." The current code violates the first line literally:
`request_operator_action` writes whatever string the caller passes (`control.py:8448-8461`), and the
consumer treats one magic string as proof of confirmed operator intent before running ROOT host
maintenance (`enrollment:2350,2470`). Any current or future producer (a new dashboard route, a CLI
path, a future API) can mint `request_source="operator-raven"` and the host upgrades. Today only Raven
writes it, so it is safe-by-convention, but the symphony explicitly warns against authority-by-naming
and the producer set will grow. So the direction is not in question: this must become server-side
authorization, and host upgrade must FAIL CLOSED when authorization is absent/forged/expired.

Where I sharpen the design beyond Codex: the producer ALREADY proves operator authority before it
queues. `_handle_upgrade`/pin call `_require_operator_actor(actor_id)` and
`_require_operator_confirmation(command.confirmed)` (`operator_raven.py:401-421,1569-1574`) — a verified
operator identity plus an explicit confirm/approval-code. The defect is not "no authorization exists";
it is "the authorization is established at the producer and then thrown away — only the string
survives." That reframes the fix: carry the existing proof forward into the row, server-minted and
server-verified, instead of trusting a re-assertable string. The MAC envelope Codex wants is the right
mechanism precisely at the ONE boundary where the proof must survive a process gap and an
untrusted-input re-read: the provisioner/maintenance drain (and the operator-upgrade broker beyond it,
which is a separate process — reconciled #9). Within `arclink_control.py` (single writer, single
process), a verbatim string is the problem and a server-minted authorization record bound to
`(action_kind, requested_target, actor_id, expiry)` is the minimum fix; across the process boundary, a
keyed MAC over those same fields is what makes it non-forgeable by a different code path.

I also weigh Codex's own residual-risk note: a new `ARCLINK_OPERATOR_ACTION_AUTH_SECRET` adds a signing
secret that any code able to read private state and write the DB can still abuse. That is real, and it
means the MAC narrows the boundary to "can read the signing secret" rather than eliminating it. That is
an acceptable, smaller boundary and must be documented (consistent with GAP-019 framing), not sold as
absolute. It does NOT argue against the MAC — it argues for keeping the secret in private state with the
other operator secrets (Secrets, Keys, And Rotation: "stored only in private state") and documenting the
residual trust surface.

WHERE I AGREE / DIFFER FROM CODEX.
- Agree: demote `request_source` to audit/display; add a server-minted, server-verified authorization
  envelope; change the provisioner gate to verify the envelope (bind to action_kind + target + actor +
  expiry); failed/forged/expired marks the row `failed` with a redacted operator notice and preserves
  the row as evidence; add local regressions for forged-source-fails / valid-Raven-succeeds /
  target-tamper-fails / stale-state-fails.
- Refine: do not frame this as "build authorization from nothing." The authorization already exists at
  the Raven producer; the work is (a) capture it into the row at mint time and (b) verify it at drain
  time. This lets the same-process portion be a typed authorization record (no new crypto), and reserves
  the keyed MAC for the producer→drain→broker process boundary where forgeability is the actual threat.
  It lowers blast radius and matches "typed action resolution" verbatim.
- Refine: scope columns minimally. Codex's six columns are reasonable but I'd land
  `actor_id`, `authorization_kind` ('operator-raven-confirmed' | future kinds), `authorization_payload_json`
  (reason/scope/nonce/confirmation-id), `authorization_mac`, `authorized_at`, `authorization_expires_at`
  as ADD COLUMN (idempotent, matches the project's single ensure_schema convention — no numbered
  migrations). Old rows get NULL auth columns and therefore FAIL CLOSED on the next drain — which is the
  desired "stale fixtures fail clearly" behavior, not a regression.
- Differ (sequencing, not direction): make the producer→consumer authorization the contract owned by
  `arclink_control.request_operator_action` (it is the single chokepoint all producers already call), so
  convergence onto the one action model is structural, not per-producer discipline. When dashboard/CLI
  later queue these kinds, they MUST mint through the same helper or they fail closed — that is the
  "converge on one action model" the symphony asks for.

FINAL PLAN.
1. Schema (idempotent ADD COLUMN, `control.py:836-848` ensure_schema): add `actor_id TEXT NOT NULL
   DEFAULT ''`, `authorization_kind TEXT NOT NULL DEFAULT ''`, `authorization_payload_json TEXT NOT NULL
   DEFAULT ''`, `authorization_mac TEXT NOT NULL DEFAULT ''`, `authorized_at TEXT`,
   `authorization_expires_at TEXT` to `operator_actions`.
2. Mint (`request_operator_action`, `control.py:8409`): add an `authorization` param (kind, actor_id,
   payload, ttl). For high-authority kinds (`upgrade`, `pin-upgrade`) require it; mint
   `authorization_mac = HMAC(ARCLINK_OPERATOR_ACTION_AUTH_SECRET, action_kind | requested_target_hash |
   actor_id | authorization_kind | nonce/confirmation-id | expires_at)` and persist all auth columns;
   set `authorized_at=now`, `authorization_expires_at=now+ttl`. Keep storing `request_source` for
   audit/display ONLY. Secret lives in private state alongside operator secrets.
3. Producer (`operator_raven.py:1308-1314,1582-1588`): after the existing `_require_operator_actor` +
   `_require_operator_confirmation` pass, pass the authorization (actor_id, confirmation id/nonce,
   reason, ttl ~ a few minutes) into `request_operator_action`. The proof it already established is now
   carried, not discarded.
4. Consumer gate (`enrollment:2308-2313,2350,2470`): replace `_operator_action_has_confirmed_source`
   (string membership) with `_operator_action_authorization_valid(action)` that recomputes and
   constant-time-compares the MAC, checks expiry, and checks target/actor binding. Missing / mismatched
   / expired / tampered → keep the existing `_fail_unconfirmed_operator_action` path (mark `failed`,
   redacted operator notice, row preserved as evidence, requeue required). This keeps the stale-running
   reaper (`enrollment:2339-2345`) untouched.
5. Tests (local proof, fails-closed): forged `request_source="operator-raven"` with no/garbage MAC ->
   row failed; valid Raven-minted auth -> upgrade proceeds; target/actor tampering after mint -> MAC
   mismatch -> failed; pre-migration NULL-auth fixture row -> failed clearly. Live execution stays behind
   `PG-UPGRADE`/`PG-HERMES`/`PG-PROVISION`.
6. Docs: record the residual "can-read-the-signing-secret-and-write-the-DB" trust surface as a narrowed
   GAP-019-class boundary, not an absolute claim.

SYMPHONY ANCHOR.
- Identity, Access, And Session Governance (`symphony:1022-1024`): "Admin and Operator actions should
  never trust client-asserted privilege ... without server-side authorization and typed action
  resolution." The MAC envelope + typed authorization_kind is exactly server-side authorization + typed
  resolution; the string gate is exactly client-asserted privilege.
- Admin Dashboard, API, And CLI Control (`symphony:322-324`): "Mutating actions should converge on one
  action model with actor, reason, scope, nonce/confirmation, redaction, result, and rollback/repair
  guidance." Minting through the single `request_operator_action` chokepoint with actor/reason/
  nonce/expiry IS that convergence.

EFFORT: high. BLAST-RADIUS: `arclink_control.py` (schema + mint helper), `arclink_operator_raven.py`
(two writers), `arclink_enrollment_provisioner.py` (two gates + the helper), the operator-upgrade broker
contract as it converges, regression fixtures, one private-state secret, one doc note. Fails closed for
all existing/old rows by construction.

---

## DECISION 2 — `host_readiness.check_ingress_strategy` always returns ok
[VERDICT: agree-codex]

QUESTION: Is the ingress check meant to be a status marker with local fallback, or a hard preflight
gate? Today it is neither — it is a tautology (`ok=True` on both branches, `host_readiness.py:158-161`).

INDEPENDENT REASONING.
A readiness check that can never fail is not a check; it is decoration that lets a production host
report `ready` while its declared ingress policy is impossible. The symphony's Fleet, Provisioning,
Ingress, And Recovery section names exactly two legitimate shapes — "Ingress is either domain/Cloudflare/
Traefik with wildcard subdomains or Tailscale path routing, with clear teardown evidence"
(`symphony:967-968`) — and the provisioning layer ALREADY enforces that typed contract
(`_clean_ingress_mode` rejects non-{domain,tailscale} at `provisioning.py:702-706`;
`_clean_tailscale_strategy` requires `path` at `:709-718`). So readiness is the only place where the
declared mode is NOT validated, which is precisely backwards: readiness exists to catch misconfig before
deploy. The fix is to make readiness a LOCAL CONFIGURATION preflight against the same typed mode contract
provisioning already owns — fail when the selected mode's required local config is absent — WITHOUT
turning readiness into a live Cloudflare/Tailscale call. host_readiness is a no-mutation, no-network role
(it bind-checks ports and reads env); pulling DNS/TLS/provider reachability into it would violate the
"local dry-run proof vs authorized live proof" split (Notifications, Incidents, And Evidence:
`symphony:996-997`). External reachability is `PG-INGRESS`, by name.

This is the cleanest of the three: it removes a false "ready", aligns readiness with the existing
provisioning mode contract, keeps the no-mutation boundary, and keeps the same truth across surfaces
(dashboard/CLI/Raven all read the readiness roll-up). I agree with Codex on substance and shape.

WHERE I AGREE / DIFFER FROM CODEX.
- Agree fully: read `ARCLINK_INGRESS_MODE`; `domain` passes only with Cloudflare token+zone OR an
  explicit operator-approved local/Traefik fallback flag surfaced as `traefik_local`/`local_only`;
  `tailscale` passes only with the required DNS/strategy shape; invalid/incomplete mode FAILS; do NOT
  call Cloudflare/Tailscale from readiness; surface `PG-INGRESS` as the live-proof owner; add the four
  tests Codex lists.
- One concrete refinement to ground it in existing code: validate the SAME inputs provisioning validates
  so the two layers cannot disagree — `domain` requires `CLOUDFLARE_API_TOKEN`(_REF)+`CLOUDFLARE_ZONE_ID`
  (already read at `host_readiness.py:156-157`) unless an explicit fallback flag (e.g.
  `ARCLINK_INGRESS_LOCAL_FALLBACK=1`) is set; `tailscale` requires `ARCLINK_TAILSCALE_DNS_NAME` and
  `ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY=path` (mirroring `provisioning.py:1116-1117,1441-1483` and
  the `_clean_tailscale_strategy` "must be path" rule). That way readiness fails on exactly the configs
  provisioning would reject, not a parallel set.
- One small surface note: `ReadinessCheck` is currently `name/ok/detail` only (`host_readiness.py:45-49`).
  Rather than add a `requires_live_proof` field (schema churn across `to_dict`/dashboard/CLI), encode the
  live-proof pointer in `detail` (e.g. `detail="domain:cloudflare-config-ok;live=PG-INGRESS"` or
  `detail="domain:cloudflare-config-missing"`). Lower blast radius, same operator-visible truth. Codex
  said "in the check detail OR adjacent operator snapshot evidence" — I land on the detail string to
  avoid the dataclass change.

FINAL PLAN.
Rewrite `check_ingress_strategy(env)` (`host_readiness.py:154-161`):
- `mode = ARCLINK_INGRESS_MODE` (default `domain`, matching `provisioning.py:1442`).
- `domain`: `ok` iff (CF token+zone present) OR (`ARCLINK_INGRESS_LOCAL_FALLBACK` truthy ->
  `ok, detail="domain:traefik_local (operator-approved local-only); live=PG-INGRESS"`). CF present ->
  `detail="domain:cloudflare-config-ok; live=PG-INGRESS"`. Neither -> `ok=False,
  detail="domain:cloudflare-config-missing (token/zone) and no local fallback flag"`.
- `tailscale`: `ok` iff `ARCLINK_TAILSCALE_DNS_NAME` set AND strategy == `path`; else `ok=False` with a
  detail naming the missing piece.
- Any other / empty-after-default-invalid mode -> `ok=False, detail="ingress mode invalid: {mode}"`.
- Keep it in the `ready` roll-up (`:179`); it now legitimately gates.
Tests: domain-missing-CF -> fail; domain + local fallback flag -> pass with local-only detail; tailscale
missing DNS -> fail; tailscale path+DNS -> pass; live proof remains a separate `PG-INGRESS` evidence
state (readiness never asserts reachability). Update operator-snapshot/deploy copy so "ingress complete"
is never claimed before `PG-INGRESS` evidence exists.

SYMPHONY ANCHOR.
- Fleet, Provisioning, Ingress, And Recovery (`symphony:967-968`): "Ingress is either domain/Cloudflare/
  Traefik with wildcard subdomains or Tailscale path routing, with clear teardown evidence." Readiness
  now proves the declared shape is locally possible.
- Notifications, Incidents, And Evidence (`symphony:996-997`): "A clear split between local dry-run
  proof, authorized live proof, policy decision, and residual-risk acceptance." Local config = readiness;
  external reachability = `PG-INGRESS`.

EFFORT: medium. BLAST-RADIUS: `arclink_host_readiness.py` (one function), readiness tests, operator-
snapshot/dashboard/deploy copy. No mutation, no network added. Fails closed (a misconfigured mode now
makes the host NOT ready).

---

## DECISION 3 — hosted API `source_ip` is spoofable audit metadata, not authority
[VERDICT: agree-codex]

QUESTION: Should fleet-enrollment `source_ip` keep ingesting raw client headers, or route through the
existing trusted-origin resolver — and is this CANON-08's call at all?

INDEPENDENT REASONING.
This is a genuinely small, clearly-correct fix and the code already contains the right tool. The hosted
API has `_remote_ip_from_headers`, which trusts forwarded headers ONLY from an allowed direct peer
(`hosted_api.py:633-653`) and is used everywhere that IP matters for policy (CIDR/rate-limit/login,
`:686,4142`). The fleet callback is the one path that bypasses it: `_handle_fleet_enrollment_callback`
never receives `remote_addr` and shoves raw `x-real-ip`/`x-forwarded-for` into `source_ip`
(`:2089-2108`, esp. `:2107`). `remote_addr` is literally in scope at the dispatch call site (used at
`:4142`, not passed at `:4140`). So the fix is one parameter + one resolver call. Crucially, `source_ip`
is audit metadata only — `consume_fleet_enrollment` stores it but authorization is the Bearer
token/HMAC compare (`fleet_enrollment.py:525-533,632-633,534`), so this is not a privilege change; it is
stopping spoofable text from masquerading as a trustworthy origin in evidence. That satisfies the
symphony's redacted-but-useful-evidence intent and the "do not trust client-asserted" principle applied
to network identity.

On the "is this CANON-08's call?" framing: Codex is right that the TRUST MODEL (which proxies/headers
are trustworthy) is owned by CANON-02. But the CANON-08-local defect — the callback bypassing the
existing resolver — is fixable now without waiting on CANON-02, because the resolver already exists and
already encodes the trust rule. So: wire CANON-08 to the existing resolver now; let CANON-02 own the
proxy-config hardening and `PG-FLEET`/`PG-INGRESS` live proof. I agree with Codex.

WHERE I AGREE / DIFFER FROM CODEX.
- Agree fully: pass `remote_addr` into `_handle_fleet_enrollment_callback`; resolve through
  `_remote_ip_from_headers`; store only the resolved origin; record `unverified`/blank when no trusted
  peer context exists rather than client headers; keep authorization on the Bearer token/HMAC; if any
  future path wants `source_ip` for AUTHZ it must require a trusted origin and fail closed; add the four
  regressions Codex lists (spoofed XFF from untrusted peer records the direct peer; trusted proxy records
  forwarded client; missing remote_addr records unverified; callback auth stays token-based).
- Minor refinement: keep the stored field shape minimal. Store `source_ip` = resolved origin (or
  `"unverified"` when `remote_addr` empty/untrusted-with-no-candidate). Add a small
  `source_ip_trust` ('direct-peer' | 'trusted-proxy-forwarded' | 'unverified') so evidence is honest
  about provenance. Skip a full redacted `forwarded_chain` unless an incident need appears — it risks
  leaking client topology into evidence for little benefit (Notifications: "No raw ... in public
  artifacts"). Codex listed it as optional ("if useful"); I land on "not by default."

FINAL PLAN.
1. `_handle_fleet_enrollment_callback` (`hosted_api.py:2089`): add `remote_addr: str` param; at the
   dispatch site `:4140` pass `remote_addr`.
2. Inside it, `resolved = _remote_ip_from_headers(config, headers, remote_addr)`;
   `trust = 'direct-peer' if not _backend_client_allowed(...) else ('trusted-proxy-forwarded' if a
   forwarded candidate was used else 'direct-peer')`; if `remote_addr` empty -> `resolved=""`,
   `trust='unverified'`.
3. Call `consume_fleet_enrollment(..., source_ip=resolved or "unverified")`; optionally extend its
   metadata to also record `source_ip_trust` (`fleet_enrollment.py:632-633`).
4. Tests as above. Authorization unchanged (Bearer + stored-hash/HMAC, reconciled #11/#12).
5. Doc: note the residual risk that a trusted reverse proxy forwarding unsanitized client headers is a
   CANON-02 proxy-config concern, closed by CANON-02 proxy tests + `PG-FLEET`/`PG-INGRESS`.

SYMPHONY ANCHOR.
- Identity, Access, And Session Governance (`symphony:1022-1024`), applied to network identity: "should
  never trust client-asserted privilege" — a client-asserted `X-Forwarded-For` is client-asserted
  identity and must not be recorded as trustworthy origin.
- Notifications, Incidents, And Evidence (`symphony:993-999`): "Redacted evidence records for ...
  fleet lifecycle ..." and "No raw ... in public artifacts." Storing a resolved origin + trust label is
  evidence that is both useful and honest.

EFFORT: low. BLAST-RADIUS: `arclink_hosted_api.py` (one handler signature + one call-site arg + resolver
wiring), optional one metadata field in `arclink_fleet_enrollment.py`, hosted-API tests, one doc note.
No authorization change; fails to `unverified` rather than to a spoofed value.

---

## STANDING DISAGREEMENTS / GENUINE PRODUCT FORKS
None of the three is a product fork — all three converge to a single symphony-grounded plan. Two operator
choices live INSIDE Decision 2 (not forks, just config the operator already owns):
- Whether `ARCLINK_INGRESS_LOCAL_FALLBACK` (operator-approved Traefik/local-only) is acceptable for a
  given host is an operator policy call surfaced as `traefik_local`/`local_only` — the plan supports both
  and labels them honestly; it does not pick for the operator.
The only cross-piece dependency to flag: Decision 1's authorization MAC must use the SAME action-model
fields the broker boundary (reconciled #9) and any future dashboard/CLI producers adopt, so convergence
on "one action model" (Admin Dashboard / API / CLI Control) holds as those producers land. That is a
sequencing constraint, not a disagreement.
