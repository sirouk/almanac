# CANON-01 — Control Plane & Schema — DECIDED (final adjudication)

**Adjudicator:** Claude Opus 4.8 (FINAL ADJUDICATOR, DECISION mode)
**Federation partner:** Codex (GPT-5.5 xhigh) — `research/canon/decisions/CANON-01-control-plane-schema.codex.md`
**Method:** Independently re-opened every code path the reconciliation flagged
(`rg`/`sed -n` in `python/arclink_control.py`, `arclink_llm_router.py`,
`arclink_chutes.py`, `arclink_wrapped.py`, `arclink_org_profile.py`,
`arclink_ctl.py`) and anchored each call to
`docs/arclink/sovereign-control-node-symphony.md`. Code wins over any prior cite,
name, or comment.

**Headline verdict:** `NONE` — there is **no deferred operator decision** for
CANON-01. I **agree with Codex**, and I strengthen the basis: the reconciliation
surfaced three "net-new CONFIRMED" findings *after* the deferral ledger was
written, so I re-grounded all three to confirm none of them is an operator call.
Two are documentation/scope corrections and one (plus all four original MEDIUMs)
is **already repaired in the working tree**. The only true open item — versioned,
reversible, old-state-fixture migrations — is named by the symphony **itself** as
the target shape under `GAP-032`, i.e. engineering backlog, not an operator fork.

---

## DECISION 0 — Accept `NONE` as the CANON-01 resolution

**[VERDICT: agree-codex]**

### Question
The repair campaign recorded `NEEDS-DECISION — NONE` for CANON-01 and the reconciled
status is `9 fixed / 3 skipped / 0 needs-decision`. Codex recommends accepting
`NONE` and routing remaining schema-ledger work to the normal `GAP-032` backlog.
Is `NONE` actually correct once the reconciliation's three net-new findings are
weighed against symphony intent and current code?

### My independent reasoning (code-grounded)
The reconciliation (`research/canon/reconciled/CANON-01-control-plane-schema.reconciled.md`)
raised three CONFIRMED net-new items and two severity bumps that did **not** exist
when `NEEDS_DECISION.md` was authored. A clean `NONE` is only defensible if none of
them is a genuine operator decision. I re-opened each:

1. **"Helper contracts are NOT exclusive — raw-SQL bypass with plain JSON
   encoders" (reconciliation MEDIUM #2 / severity story).**
   *Re-grounded and partially refuted on the security claim.* The raw inserts do
   exist, but **every** one of them now routes through a **secret-rejecting**
   encoder, so the secret-leak widening the reconciliation worried about is
   already closed in code:
   - `arclink_llm_router.py:788`, `:1066`, `:1085` use `_safe_metadata_json`
     (`:705-706`) → `json_dumps_safe` (boundary, rejects secrets).
   - `arclink_chutes.py:924` uses `_json_dumps_object` (`:460-462`) → calls
     `reject_secret_material`.
   - `arclink_wrapped.py:1009` uses `_notification_extra_json` (`:138-139`) and
     `:1067/:1074` use `_json_dumps` (`:134-139`) → both `json_dumps_safe`.
   The reconciliation's "plain `json.dumps`/`_json_dumps`/`_json_dumps_object`"
   phrasing was anchored on pre-repair line numbers; in the current tree those
   encoders reject secrets. The **producer** helpers were also repaired:
   `_arclink_json` (`arclink_control.py:3310-3321`) and `queue_notification`
   (`:8179-8201`) both reject secrets / use `json_dumps_safe`. **Net: not an
   operator decision** — it is at most an engineering consistency/maintainability
   follow-up (see "Non-blocking follow-up" below).

2. **"Control-DB schema larger than CANON-01 captures: org-profile adds 5 tables
   on the same connection" (reconciliation MEDIUM #1).**
   *Re-grounded — true, but a scope/doc correction, not a fork.*
   `arclink_ctl.py:2090` calls `org_profile_apply(conn, ...)` on the `connect_db`
   connection; `ensure_org_profile_schema` (`arclink_org_profile.py:2049-2089`)
   creates `org_profile_revisions/roles/people/teams/relationships`. This is a
   deliberate module-owned schema extension, correctly attributed to the
   org-profile owner (CANON-21). The only action it warrants is correcting the
   reconciled doc's "entire/sole schema authority" wording — already done in the
   reconciliation table (rows 8, 44). Nothing here requires the operator to choose
   anything. **Net: not an operator decision.**

3. **"Legacy onboarding token migration writes a row-stored path without
   containment on every DB open" (reconciliation LOW #3).**
   *Re-grounded — already repaired.* `_migrate_onboarding_bot_tokens`
   (`arclink_control.py:7192`) now gates the stored path through
   `_onboarding_secret_path_is_contained(cfg, existing_path)` (`:7212`) before
   `_write_private_text`, and otherwise derives a fresh contained path via
   `write_onboarding_platform_token_secret`. The uncontained-write concern is
   closed. **Net: not an operator decision.**

I also re-confirmed the four original MEDIUMs are repaired (not deferred):
- Unguarded `int()` casts → `_config_int` defaults-with-`RuntimeWarning`
  (`arclink_control.py:161-169`), no hard crash on bad override.
- Config-file shlex truncation → multi-token values preserved via
  `shlex.split` + re-join (`:386-392`); `export KEY=value` handled (`:378-381`);
  explicit-but-missing config now **fails loud** (`FileNotFoundError`, `:362-363`)
  while preserving the `/dev/null` sentinel.
- Secret-leak in producer JSON helpers → both `_arclink_json` and
  `queue_notification` reject secrets (cites above).

That leaves exactly one open symphony delta: a **version ledger / numbered,
reversible, old-state-fixture migrations** (`PRAGMA user_version` stays 0; only
`*__new` rebuild copies). The symphony **names this itself** as future work:
"there is **no version ledger and no numbered/reversible migration history
yet**; the 'reversible where practical, versioned, old-state-fixture' contract
above is the target shape, not the current state … should expand as `GAP-032`."
A roadmap engineering gap the document already owns is **not** an operator
decision the campaign deferred.

### Where I agree / differ from Codex
**Agree** on the verdict, the symphony anchors, and the disposition (accept
`NONE`; keep schema-ledger work in `GAP-032`; do not invent an operator schema/
policy call; reject promoting org-profile ownership, ledger timing, or GAP-019
into new CANON-01 decisions). **Differ only by adding rigor:** Codex's note cited
the reconciliation's three findings at a high level; I independently re-opened
each in the current tree and showed the secret-leak teeth of finding #2 and the
containment gap of finding #3 are **already closed in code**, and finding #1 is a
doc-scope correction. So `NONE` is not merely "nothing was flagged" — it is
"every candidate was weighed against code and symphony and none is an operator
call." I add one **non-blocking engineering follow-up** below that is explicitly
**not** an operator decision.

### FINAL PLAN
1. **Accept `NONE`.** Do not emit any `### DECISION` block or operator fork for
   CANON-01. No code change is required from this decision pass.
2. **Route the one real symphony delta to `GAP-032`** (version ledger + numbered/
   reversible migrations + old-state-fixture compatibility tests + a stale/
   incompatible-config release detector). This is engineering backlog under the
   existing gap, not an operator policy call.
3. **Non-blocking engineering follow-up (NOT an operator decision):** add a
   single regression test asserting that every raw `INSERT INTO arclink_events` /
   `INSERT INTO notification_outbox` site outside `arclink_control.py` routes its
   JSON through a secret-rejecting encoder (`json_dumps_safe` /
   `reject_secret_material`). Today they all do (llm_router/chutes/wrapped verified
   above), but the contract is convention, not enforced — a test pins the
   now-closed secret hygiene against regression. Optionally consolidate those raw
   inserts behind `append_arclink_event` / `queue_notification` for single-author
   schema discipline. Hand to the owning pieces (CANON-11/16/19), not the operator.

### Symphony anchor (quoted)
- **Configuration, Schema, And Migration** — "Database schema changes are
  migration-aware, idempotent, **reversible where practical**, and **tested
  against old-state fixtures**." The doc itself adds: "there is **no version
  ledger and no numbered/reversible migration history yet**; the … contract above
  is the **target shape, not the current state** … should expand as `GAP-032`."
  → the remaining delta is roadmap work the symphony already owns, not an operator
  call. CANON-01's `ensure_schema` already satisfies the "idempotent,
  create-if-absent" half it claims today.
- **Secrets, Keys, And Rotation** — "Public docs, chat transcripts, logs,
  evidence artifacts, command arguments, and generated markdown **must never
  contain secret values**." → repaired producers + secret-rejecting raw-insert
  encoders satisfy this at the persistence boundary; the follow-up test merely
  **fails closed** against future drift.
- **Whole-System Traversal** — "If any step cannot say what surface owns it, what
  state it reads, what state it writes, and **how it fails closed**, the symphony
  is not complete." → CANON-01's owners are clear, env-precedence is proven, and
  bad config now defaults-with-warning rather than crashing; the org-profile
  schema is correctly attributed to its own owner.

### Effort / blast-radius
- **Decision pass: low.** No code surfaces change from accepting `NONE`.
- **Non-blocking follow-up: low** (one regression test; no behavior change).
- **`GAP-032` ledger work: high** but explicitly out of scope for this decision
  pass and already roadmap-tracked.
- **Blast radius of this decision: none.** No schema, contract, or policy changes.

---

## STANDING DISAGREEMENTS
None. No genuine product fork exists for CANON-01. The schema-ledger/migration
target is owned by `GAP-032` (engineering roadmap), the org-profile tables are
owned by CANON-21, and the raw-insert hygiene follow-up is owned by the producing
pieces — none requires an operator choice.
