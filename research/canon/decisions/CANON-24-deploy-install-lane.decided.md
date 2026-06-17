# CANON-24 — Deploy & Install Lane — DECIDED (final adjudication)

Adjudicator: Claude Opus 4.8 (1M) — FINAL ADJUDICATOR, DECISION mode.
Method: formed an independent view from code first (re-opened both
`bootstrap.handshake` producers, the MCP schema, `_request_source_ip`, the
control-plane `request_bootstrap`, and the existing regression tests), then
converged with Codex (GPT-5.5 xhigh). Code wins over name/comment/claim.

Federation partner proposal: `research/canon/decisions/CANON-24-deploy-install-lane.codex.md`.

CANON-24's NEEDS_DECISION ledger carries exactly **one** deferred operator call.
(The reconciled record also surfaced HIGH auto-push, MEDIUM no-branch-guard,
MEDIUM doc drift, etc. — but those were *fixed or documented* by the repair
campaign and are NOT in the deferred ledger; the only thing the campaign
deferred for an operator call is the `bootstrap.handshake` producer-payload
unification, pending the CANON-18 consumer decision.)

---

## DECISION 1 — Unify `bootstrap.handshake` payload semantics across remote `init.sh` and host-side `bin/init.sh`

**[VERDICT: refine]** (agree with Codex's direction and code-level plan; refine
the framing — this is a contract-legibility/anti-drift fix, not a security fix —
and tighten the proof obligation and the CANON-18 ownership handoff.)

### The question (from NEEDS_DECISION.md, CANON-24)
> Whether to unify `init.sh` remote `auto_provision` and `bin/init.sh` host-side
> `source_ip` payloads for `bootstrap.handshake`; left unchanged pending CANON-18
> consumer decision.

The reconciled record logged this as **[INFO] G3** (divergent producer payloads):
remote `init.sh:266-268` sends `{requester_identity, unix_user, auto_provision:true}`
(no `source_ip`); host-side `bin/init.sh:451-453` sends `{requester_identity,
unix_user, source_ip}` (no `auto_provision`).

### My independent reasoning (from code)

1. **There is no schema divergence — only a populated-field divergence.** The MCP
   server already owns ONE versioned schema for `bootstrap.handshake`
   (`python/arclink_mcp_server.py:224-235`): `required=("unix_user",)`, every
   other field (`requester_identity`, `source_ip`, `auto_provision`,
   `model_preset`, `channels`) optional. Both producers are valid against the
   same schema. So the "divergence" is two callers populating different optional
   subsets, not two contracts. That reframes the fix away from "merge two schemas"
   toward "make each caller's intent explicit against the one schema."

2. **The asymmetry is intentional and correct, not a defect.** The two producers
   are different admission lanes by design:
   - Remote `init.sh` (`auto_provision:true`, no `source_ip`) is the
     **no-host-access** request: a Captain-style caller asks the Control Node to
     create the Unix user and provision the host-side agent *after operator
     approval*. It must NOT carry a `source_ip` because a remote client cannot
     produce a trustworthy one.
   - Host-side `bin/init.sh` (`source_ip`, no `auto_provision`) is the **on-box
     manual** enrollment run as the target user over SSH/local; it derives
     `source_ip` from `SSH_CONNECTION`/`SSH_CLIENT` (`bin/init.sh:399`) and yields
     a *pending token* directly to that on-box client.

3. **The security posture already fails closed; this is not where the risk lives.**
   - `auto_provision=true` returns **no raw token** — verified at
     `python/arclink_control.py:11287` (`if issue_pending_token and not
     auto_provision:`). The remote lane only queues a pending request awaiting
     `arclink-ctl request approve`. The operator-owns-host boundary holds.
   - A producer-declared `source_ip` is **advisory and override-gated**: the
     consumer derives the real origin from transport and honors a declared
     `source_ip` only when the request is from loopback AND
     `ARCLINK_ALLOW_LOOPBACK_SOURCE_IP_OVERRIDE=1`
     (`python/arclink_mcp_server.py:1847-1856`). That is already pinned by
     `tests/test_loopback_service_hardening.py:111-135`. So spoofed client
     metadata is ignored by default — no security change is owed here.

   => Unifying the payloads is therefore a **contract-legibility / anti-drift**
   improvement (make caller intent declarative so two callers don't re-diverge
   silently), NOT a fail-closed security fix. I want the operator to understand
   they are buying clarity and a regression pin, not closing a hole.

4. **Forcing both keys on both producers would be wrong** (Codex's rejection is
   correct): remote `init.sh` inventing a `source_ip` would feed false provenance
   into audit/status; host-side `bin/init.sh` is the deliberate *manual*
   (non-auto-provision) lane and should not silently flip to auto-provision.

### Where I agree / differ from Codex

- **Agree** with the entire code-level plan: keep the MCP schema as the single
  owner (`arclink_mcp_server.py:224-235`); add explicit `"auto_provision": false`
  to host-side `bin/init.sh` (payload at `bin/init.sh:450-454`, the
  `json.dumps({...})` block); leave remote `init.sh:266-268` as
  `auto_provision:true`; do NOT synthesize `source_ip` in remote `init.sh`; keep
  `_request_source_ip` / `_ensure_bootstrap_source_allowed`
  (`arclink_mcp_server.py:1847-1861`) as the origin authority. Effort low, no DB
  migration, no state rewrite.
- **Agree** the residual risk is schema re-drift unless CANON-18 *documents* the
  one schema and CANON-24 *pins both producer intents* with a test.
- **Refine (framing):** Codex anchors partly on a fail-closed reading. I down-rate
  that — the lane already fails closed in code (points 3a/3b). The justification
  the operator should hear is "single versioned schema + legible intent +
  regression pin against re-drift," not "we are tightening a security gap."
- **Refine (proof):** The *consumer*-side override behavior is already pinned
  (`test_loopback_service_hardening.py:111-135`). What is missing — and what this
  decision must add — is a **producer-intent** regression: assert
  (a) remote `init.sh` emits `auto_provision:true` and no `source_ip` key;
  (b) host-side `bin/init.sh` emits `auto_provision:false` and a `source_ip` key.
  Note: `tests/` IS writable in this workspace (verified `test -w tests` → ok;
  the CANON-29 "tests not writable" note is stale), so this can be a dedicated
  `tests/test_bootstrap_handshake_producers.py` rather than smuggled into an
  existing file. A static-text/`bash -n` style check is sufficient since these
  payloads are heredoc-literal — no live MCP server needed for the producer pin.
- **Refine (root-cause / CANON-18 handoff):** the durable fix against re-drift is
  not the explicit `auto_provision:false` line itself (the consumer already
  defaults absent → false via `_bool_arg`, so the line is purely declarative).
  It is making **CANON-18 the named schema owner** and adding a short "two caller
  intents" stanza to the canonical bootstrap doc. The explicit key is the cheap
  visible half; the doc-ownership is the load-bearing half. I require both.

### FINAL PLAN

1. **Producer edits (low):**
   - `bin/init.sh:450-454` — add `"auto_provision": False` to the `json.dumps`
     payload so the on-box manual lane declares intent explicitly.
   - `init.sh:266-268` — unchanged (`auto_provision: True`, no `source_ip`).
   - Do NOT add `source_ip` to remote `init.sh` (no trustworthy value exists).
   - Optional symmetry (declarative only): nothing else changes — `model_preset`
     / `channels` stay optional and producer-driven.
2. **Schema owner stays put:** `python/arclink_mcp_server.py:224-235` remains the
   one versioned `bootstrap.handshake` schema; `_request_source_ip` /
   `_ensure_bootstrap_source_allowed` (`:1847-1861`) remain the origin authority.
   No consumer behavior change.
3. **CANON-18 owns the documented contract (the anti-drift root fix):** record in
   the canonical bootstrap/MCP doc that `bootstrap.handshake` has exactly two
   sanctioned producer intents — remote auto-provision (no `source_ip`, returns a
   pending request, no raw token) and on-box manual (`source_ip` advisory,
   `auto_provision:false`, returns a pending token). This is the CANON-18 consumer
   decision the deferral was waiting on; it should be resolved as "schema already
   unified; document the two intents."
4. **Named regression (the missing proof):** add a producer-intent test
   (`tests/test_bootstrap_handshake_producers.py`, static heredoc assertions)
   proving: remote emits `auto_provision:true` + no `source_ip`; host-side emits
   `auto_provision:false` + a `source_ip`; spoofed `source_ip` ignored unless the
   override env is set (re-use / cross-reference the existing
   `test_loopback_service_hardening.py:111-135` consumer pin rather than
   duplicating it).
5. **Local proof:** `bash -n init.sh bin/init.sh`;
   `python3 tests/test_loopback_service_hardening.py`;
   `python3 tests/test_arclink_auto_provision.py`;
   `python3 tests/test_bootstrap_handshake_producers.py`.
6. **Named live-proof gate:** `PG-PROVISION` for the host-admission/auto-provision
   path, plus `PG-INGRESS` when the public MCP `bootstrap.handshake` path is
   exposed over Funnel/tailnet. Fails closed: auto-provision returns no token;
   declared `source_ip` ignored unless explicit loopback opt-in.

### Symphony anchor (quoted)

- `API, Webhook, And Extension Contracts`: "**Versioned MCP schemas for ArcLink
  tools, with destructive operations absent or explicitly approval-gated.**" The
  one schema is the versioned contract; auto-provision is approval-gated
  (`request_bootstrap` returns no raw token under `auto_provision`,
  `arclink_control.py:11287`).
- `Whole-System Traversal`: "**Every step should have a local source owner, a
  local regression or dry-run proof where possible, and a named live proof gate
  where external systems are required. If any step cannot say what surface owns
  it, what state it reads, what state it writes, and how it fails closed, the
  symphony is not complete.**" The decision names the source owner (MCP schema),
  adds the missing producer-intent regression, and names PG-PROVISION/PG-INGRESS.
- `North Star`: "**Operators own the universe: hosts, secrets, fleet, policy,
  upgrades, backups...**" / "**Captains own their Pods and Crew, not the host.**"
  Remote `auto_provision` lets a no-host-access caller *request* admission, but the
  Operator still owns the host because approval is mandatory and no token is
  issued until then — exactly the boundary this contract preserves.

### Effort / blast-radius

- **Effort: low.** Two heredoc-literal producer edits, one new static test, one
  CANON-18 doc stanza. No DB migration, no schema change, no consumer-behavior
  change, no state rewrite.
- **Blast radius: minimal.** The explicit `auto_provision:false` is a no-op against
  the consumer's existing absent-key default, so the change cannot alter runtime
  admission behavior; it only makes intent legible and re-drift test-detectable.
  Risk if skipped: the two payloads silently re-diverge and a future caller copies
  the wrong shape — caught only in production audit, not in CI.

---

## STANDING DISAGREEMENTS

None. The single deferred item converges to a clear refine-of-Codex plan. No
genuine product fork remains — the asymmetry between the two producers is an
intentional, code-correct design (no-host-access auto-provision vs on-box manual),
and unifying it is a legibility + anti-drift improvement with no behavior change,
so there is nothing for the operator to *choose between* — only to ratify.
