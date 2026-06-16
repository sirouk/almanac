# CANON-04 — Onboarding & Provider Auth — ADVERSARIAL VERIFY

Verifier: independent Opus 4.8 skeptic. Method: re-opened all four piece files plus
every cited cross-piece end. Every statement below is cited at path:line read in this
session, not from the record.

## OVERALL VERDICT

**Record is MOSTLY TRUSTWORTHY on structure and seams, but contains one FALSE
load-bearing safety claim and misses two real fail-mode gaps.** The two-system split,
the dead `payment_pending`/`paid`/`completed` statuses, the "Chutes is API-key not
OAuth" drift, the five both-ends seams, and the OLD-path provider-auth trace all
re-confirm in code. BUT:

- **REFUTED (load-bearing):** The VERDICT's claim that "the public onboarding store
  **cannot hold provider keys or bot tokens**" and that the module is "secret-hostile
  by design" is FALSE for the most relevant key shapes. The value-regex catches a
  narrow set and lets **Anthropic (`sk-ant-`), OpenAI (`sk-proj-`/`sk-`), Chutes
  (`cpk_`), and AWS (`AKIA`)** keys through when pasted into free-text hint fields.
- **REFUTED (concrete citation):** RISK#2 / self-check #4 name `arclink_api_auth.py:1093`
  as an UNSCANNED `_update_session` bypass. That exact line goes through
  `json_dumps_safe` → `reject_secret_material`, so it IS scanned. The cited bypass is
  wrong; the underlying "`_update_session` itself doesn't scan" observation is true but
  has no reachable exploit.
- **NEW GAPS missed by record AND prior docs:** (a) terminal/expired onboarding session
  at `checkout.session.completed` time forces the ENTIRE Stripe webhook to roll back and
  re-raise (replayable-forever) — the user's `paid` entitlement write is undone;
  (b) `sync_...` returning `False` (deployment not entitled) is a SILENT no-op because the
  webhook caller ignores the return; (c) `record_arclink_onboarding_first_agent_contact`
  has no terminal guard and can resurrect an expired session.

---

## REFUTATIONS OF RECORD CLAIMS

### R1 — REFUTED: "secret-hostile by design … cannot hold provider keys or bot tokens"
Record VERDICT (l.164-166), TOUCH POINTS/Secrets (l.87), self-check #4 (l.136).
Re-read `_PLAINTEXT_SECRET_RE` (`python/arclink_onboarding.py:116-126`) and
`_SECRET_KEY_RE` (`:115`), and executed the regex against real key shapes. Findings:
- Value-match catches ONLY: `sk_(live|test)_`, `whsec_`, `gh[pousr]_`, `xox[baprs]-`,
  `ntn_`, `cloudflare...token`, telegram `\d{6,}:[a-z0-9_-]{20,}`.
- Value-match MISSES: `sk-ant-api03-...` (Anthropic), `sk-proj-...`/modern `sk-...`
  (OpenAI — the regex requires `sk_` underscore, not `sk-`), `cpk_...` (Chutes — the
  product's primary provider), `AKIA...` (AWS), generic JWT/bearer.
- Path-match (`_SECRET_KEY_RE`) only fires on field NAMES containing
  secret/token/api[_-]key/password/credential/webhook. The persisted free-text fields
  `email_hint`, `display_name_hint`, `agent_name`, `agent_title` have paths
  (`$.email_hint` etc.) that do NOT match.
- Therefore an end user pasting an Anthropic/OpenAI/Chutes/AWS key into `agent_name`
  (stored `:449,:493`), `agent_title`, `display_name_hint`, or `email_hint` is persisted
  in plaintext into `arclink_onboarding_sessions`. The "cannot hold provider keys"
  guarantee is false. The record only validated the regex's stated positives; it never
  tested the complement (what escapes), which the method demands.
- Note: bot tokens (telegram shape) and Stripe/GitHub keys ARE caught, so the design is
  partially effective — but the VERDICT overstates it to an absolute.

### R2 — REFUTED (citation wrong): `arclink_api_auth.py:1093` is NOT an unscanned bypass
Record RISK#2 (l.149), OPEN#2 (l.142), self-check #4 (l.136).
Re-read `arclink_api_auth.py:1093-1095`: the raw `UPDATE … SET metadata_json = ?` binds
`_json(session_metadata)`. api_auth's `_json` is the LOCAL one at `:221-222`, which calls
`json_dumps_safe` (`arclink_boundary.py:65-73`), which DOES call `reject_secret_material`
(`:72`). So that write IS secret-scanned. The record's claim that this line is the
unscanned channel is refuted. The generic observation ("the onboarding module's
`_update_session` at `:344-383` does not itself call `_reject_secret_material`") is TRUE,
but there are **zero external callers** of the private `_update_session` (grep confirmed),
and every internal caller passes either already-`_json`'d metadata (`:469`) or
non-secret-shaped scalar fields. No reachable exploit. RISK#2 MEDIUM is over-calibrated;
downgrade to LOW/INFO.

### R3 — CONFIRMED (not refuted): dead statuses `payment_pending`/`paid`/`completed`
Record DRIFT#2 (l.126), RISK (l.148). Grep across `python/` for
`status=('|")(payment_pending|paid|completed)` on onboarding sessions returns nothing;
the only NEW-module status writes are `checkout_open`/`payment_cancelled`/`abandoned`/
`payment_expired`/`payment_failed`/`provisioning_ready`/`first_contacted` (+`collecting`,
INSERT `started`) at `arclink_onboarding.py:686,735,757,777,792,815,890,527,483`. Schema
CHECK pins all three dead values (`arclink_control.py:1313`). `completed_at` column
(`:2172`) is never written for NEW sessions (the `completed_at=` writes are all OLD
`save_onboarding_session` in `_flow.py`). CONFIRMED true. `first_contacted` is the
furthest-forward NEW status and it is ALSO in the active-statuses partial unique index
(see N3), so a finished session permanently occupies the (channel,identity) slot.

### R4 — CONFIRMED: Chutes is API-key, not OAuth
DRIFT#1/INFO. `arclink_onboarding_provider_auth.py:153-165`: `auth_flow="api-key"`,
`key_env="CHUTES_API_KEY"`. CONFIRMED. Only OAuth flows are Codex device-code (`:300`)
and Anthropic PKCE (`:385`). `normalize_anthropic_credential` always raises (`:466-470`).

### R5 — CONFIRMED but UNDER-DESCRIBED: partial unique index has a status filter
Record TOUCH POINTS (l.80) cites the unique index at `:2235` on
`LOWER(channel),LOWER(channel_identity)` but omits that it is PARTIAL on active statuses
(`arclink_control.py:2237-2245`: `status IN ('started','collecting','checkout_open',
'payment_pending','paid','provisioning_ready','first_contacted')`). This is why re-entry
after expiry works (test `tests/test_arclink_onboarding.py:465-503` passes). I initially
suspected re-entry was blocked; the status filter refutes that. Record's omission is a
documentation gap, not a code defect.

---

## SEAM RE-VERIFICATION (record's 7 cross-piece contracts)

- **Seam 1 NEW→Stripe (l.109): HOLDS.** Caller reads `checkout.get("id")`/`("url")`
  (`arclink_onboarding.py:688-689`); Fake returns `{id,url,…}` (`arclink_adapters.py:42,54`),
  Live returns exactly `{id,url}` (`:128`). Kwargs are keyword-only and match
  (`:22-34` Fake, `:83-95` Live). `mode` defaults to `subscription` (caller omits it).
  Both-ends verified.
- **Seam 2 CANON-07→NEW (l.111): HOLDS as a signature, but FAIL-MODE UNEXAMINED.**
  Producer `arclink_entitlements.py:744-750` passes `session_id` (from metadata
  `arclink_onboarding_session_id`, read at `:289`, written at `arclink_onboarding.py:674`),
  `commit=False`. Consumer `arclink_onboarding.py:799`. Metadata key string matches.
  **BUT** the record's "BOTH-ENDS-VERIFIED: yes" ignores that the consumer's first line
  `_active_session_or_error` (`:807` → `:336-341`) RAISES `ArcLinkOnboardingError` for a
  terminal session and `KeyError` for a missing one. See N1 — this raises inside the
  webhook and rolls everything back. Seam is correct on shape, unsafe on unhappy path.
- **Seam 3 NEW→CANON-01 (l.113): HOLDS.** `arclink_deployment_can_provision`
  (`arclink_control.py:3927-3928`, requires entitlement_state∈{paid,comp}),
  `advance_arclink_entitlement_gate` flips `entitlement_required→provisioning_ready`
  (`:3942-3952`). Note the gate is also lifted earlier in the same webhook by
  `advance_arclink_entitlement_gates_for_user` (`arclink_entitlements.py:741`), so the
  `sync_...` gate call is usually a redundant no-op (returns False, ignored) — record's
  trace step 5 implies sync does the flip; in practice line 741 already did. Functionally
  fine; record imprecise on ordering.
- **Seam 4 CANON-08→NEW (l.115): HOLDS on shape.** Producer
  `arclink_sovereign_worker.py:2476-2481` matches consumer `arclink_onboarding.py:880`.
  But consumer has NO terminal guard (N3): it force-sets `first_contacted` even on an
  expired/terminal session.
- **Seam 5 OLD→CANON-08 (l.117): HOLDS.** Producer persists `provider_setup.as_dict()`
  (`arclink_onboarding_flow.py:2033`) and `provider_browser_auth` (`:2067`); consumer
  `arclink_enrollment_provisioner.py:1639,1642,1647` reads both and calls
  `poll_codex_device_authorization`. Round-trip through `as_dict`/`provider_setup_from_dict`
  (`arclink_onboarding_provider_auth.py:46-69`) is lossless except `reasoning_effort` is
  re-normalized with default `medium` (`:68`) — benign.
- **Seam 6 OLD→CANON-06 (l.119): HOLDS.** Only callers are the two curator modules
  (`arclink_curator_onboarding.py:685,770,1098`, `arclink_curator_discord_onboarding.py:372`);
  repo-wide grep confirms no other caller. Signature matches `:1761-1766`.
- **Seam 7 OLD→CANON-01/08 (l.121): partial, as record states.** `request_bootstrap`
  + `approve_request(surface="curator-channel")` (`arclink_onboarding_flow.py:1149,1163`).
  Bodies owned by CANON-01; not re-traced.

---

## NEW GAPS (missed by record AND prior docs)

### N1 — HIGH: terminal/missing onboarding session rolls back the entire Stripe webhook
`sync_arclink_onboarding_after_entitlement` (`arclink_onboarding.py:807`) calls
`_active_session_or_error`, which (a) runs `expire_stale_...` FIRST (`:337`), then
(b) RAISES `ArcLinkOnboardingError` if the session is terminal (`:339-340`) or `KeyError`
if missing (`:332`). The producer at `arclink_entitlements.py:744` is inside a single
webhook transaction wrapped by `try/except Exception:` at `:799-809`, which on ANY
exception does `conn.rollback()` (`:800-801`), marks the event replayable
(`:802-808`, `failure_is_replayable=True` by `:558`), and **re-raises** (`:809`). Effect:
the user's `entitlement_state="paid"` write (`:725-740`) and gate advance (`:741`) are
ALSO rolled back, and the webhook fails on every retry — because the onboarding session
will never un-terminalize. The onboarding TTL is 24h
(`ARCLINK_ONBOARDING_SESSION_TTL_SECONDS`, `:61`) and `expire_stale_...` runs at the very
start of the consumer (`:337`), so a session can be expired by the same call trying to
advance it (TOCTOU between TTL expiry and a delayed/retried Stripe `completed` event).
A paying customer whose checkout completes >24h after session creation (or after a manual
cancel) can wedge their own webhook permanently. Record's seam #2 "BOTH-ENDS-VERIFIED:
yes" never examined this. Severity HIGH: it can block a paid entitlement, not just the
onboarding row.

### N2 — MEDIUM: `sync_...` returning False is a SILENT no-op (caller ignores it)
`sync_arclink_onboarding_after_entitlement` returns `False` (no write) when the deployment
is missing or not yet entitled (`arclink_onboarding.py:808-810`). The producer
`arclink_entitlements.py:744-750` does NOT capture or check the return. So if, at webhook
time, the onboarding deployment's user entitlement_state is not yet `paid`/`comp`
(e.g., the `arclink_user_id` metadata resolved to a different/blank user, or
`advance_arclink_entitlement_gates_for_user` at `:741` didn't cover this deployment),
the session silently stalls at `checkout_open` with no error, no event, no retry signal.
Combined with N1, the two failure modes are asymmetric and neither is monitored.

### N3 — MEDIUM: `record_arclink_onboarding_first_agent_contact` has no terminal guard
Unlike `answer`/`prepare`/`open_checkout`/`sync`/`handoff` (which all call
`_active_session_or_error`), `record_arclink_onboarding_first_agent_contact`
(`arclink_onboarding.py:880-902`) calls `_update_session(status="first_contacted")`
directly with no active/terminal check. If the session expired by TTL (status='expired',
terminal) before CANON-08 fires first contact (`arclink_sovereign_worker.py:2476`), this
RESURRECTS a terminal session back to the active `first_contacted` status (which is also
in the active-statuses partial unique index `arclink_control.py:2244`), re-occupying the
(channel,identity) slot and contradicting the "terminalize so identities can re-enter"
docstring (`arclink_onboarding.py:272`). Low exploitability but a real state-machine
integrity hole.

### N4 — INFO: `prepare_...` commits deployment rows before Stripe is called
`reserve_arclink_deployment_prefix`/`reserve_generated_...` commit unconditionally
(`arclink_control.py:3616`), and `prepare_arclink_onboarding_deployment` is invoked at the
top of `open_arclink_onboarding_checkout` (`arclink_onboarding.py:656`) BEFORE
`stripe_client.create_checkout_session` (`:664`). If Stripe raises (no try/except around
`:664`), the committed `entitlement_required` deployment + session updates persist while
the session never reaches `checkout_open`. Recoverable (idempotent retry: `:657`,
`:593-595`) but leaves orphan `entitlement_required` deployments on Stripe failure. Not in
the record's trace.

---

## SEAM MISMATCHES SUMMARY

| Seam | Shape match | Unhappy-path safe |
|------|-------------|-------------------|
| 1 NEW→Stripe | yes | n/a |
| 2 CANON-07→NEW | yes | **NO — N1 rollback, N2 silent no-op** |
| 3 NEW→CANON-01 | yes | yes (record's step-5 ordering imprecise) |
| 4 CANON-08→NEW | yes | **NO — N3 resurrects terminal session** |
| 5 OLD→CANON-08 | yes | yes |
| 6 OLD→CANON-06 | yes | yes |
| 7 OLD→CANON-01/08 | partial | not traced |

## RISK RE-CALIBRATION vs RECORD
- Record MEDIUM "secret-rejection entry-point-only / `_update_session` bypass via
  `:1093`": **DOWNGRADE to LOW/INFO** — `:1093` is scanned (R2); no reachable bypass.
- Record's "secret-hostile, cannot hold keys" strength: **REFUTE / RAISE to HIGH gap** —
  Anthropic/OpenAI/Chutes/AWS keys escape (R1).
- New HIGH: webhook rollback wedge (N1) — not in record.
- Other record risks (plaintext password in chat `_completion.py:411,423,427,432`; live
  outbound HTTP `_provider_auth.py:300,326,408`; expire-on-read-path `:337`;
  IN-placeholder cosmetic `:237-249`) all re-confirmed accurate at cited lines.

## CONFIRMED-CORRECT IN RECORD (independently re-verified)
Two-system split; input/output contracts; DB write targets; env vars
(`_completion.py:204-228,379`); subprocess `git cat-file` (`:36-51`); the dead-status
finding; the Chutes-OAuth drift; `normalize_anthropic_credential` always-raises; live
OAuth client IDs present (`_provider_auth.py:17-26`, values not validated against live
APIs — left OPEN as record did); seams 1,3,5,6 fully; 2,4 on shape.
