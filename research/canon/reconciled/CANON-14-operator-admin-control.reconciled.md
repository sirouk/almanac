# CANON-14 — Operator & Admin Control — RECONCILED (both-model-signed)

- **Codex (GPT-5.5 xhigh) sign-off:** OBJECT(4) — "Core CANON-14 is correct, but the final canon should down-rank two Claude risks and add two queue/filesystem race findings."
- **Final federation sign-off (Opus 4.8 adjudicator):** AGREED-WITH-STANDING-DISAGREEMENTS — every material point reconciled to one code-grounded truth; one residual is a severity-judgment difference (academy symlink gap) that is real but not settleable from code alone, recorded below.
- **Method:** the adjudicator re-opened every disputed cite (Read) and decided by what the code does. Code wins over comment/name/prior claim.

The piece's spine is independently re-confirmed: a fail-closed, identity-gated, audited operator/admin control plane with a clean dry-run / actorless-fail-closed / require-confirm / queue contract for the seven mutating Raven commands; never-inline mutation; atomic `arclink_action_intents` claim; record-only rollout; and a provisioner `request_source` re-check. The corrections below are calibration + four net-new findings, none of which break the core contract.

---

## 1. RESOLUTION TABLE (disputed points + Codex CONFIRM ratifications)

| Point | Winner | Deciding cite |
|---|---|---|
| Stale-action recovery always re-queues (never `failed`), no retry cap; docstring "queued or failed" is drift | both (Claude B1 = Codex CONFIRM) | `arclink_action_worker.py:2247` docstring vs `:2262` `status="queued"`, `:2281` `new_status:"queued"`; no cap/terminal in `:2253-2282` |
| Dismissed pin upgrades stay queueable (active filter ignores `silenced`) | both (record risk #2 = Claude A5 = Codex CONFIRM) | `arclink_control.py:9601` filters `applied_at IS NULL` only; `:9667` requires active target; dismiss sets `silenced=1` at `:9686` (never sets `applied_at`); Raven `arclink_operator_raven.py:1284,1290` calls `active_only=True` |
| Approval code enforced by transport, not Raven — original framed as open MEDIUM | both (Claude A7 + Codex REFINE down-rank); record's open-uncertainty framing rejected | Caller set is closed: only `arclink_telegram.py:1305-1307`, `arclink_curator_onboarding.py:345-347`, `arclink_curator_discord_onboarding.py:310-317`, + Raven recursion `arclink_operator_raven.py:1516`. All three transports gate typed mutating text; Raven itself requires only actor+confirm (`:400-409`, `:412-420`) |
| Real residual is the callback/`custom_id` path (skips `is_mutating`/code) | both (Claude A7b = Codex CONFIRM/REFINE) — LOW | `arclink_curator_onboarding.py:822-838` and `arclink_curator_discord_onboarding.py:955-967` dispatch `arclink:/...` with no code check; only channel/sender allowlist-gated. Designed for nonce buttons (`/upgrade_apply` not in MUTATING set; nonce consumed at `arclink_operator_raven.py:1508`) |
| `academy_apply` "gated by one env var, not the executor adapter" — original mechanism | claude (A8) + codex REFUTE-mechanism; record's stated mechanism is FALSE | `arclink_academy_programs.py:2864` `live_adapter = adapter∈{local,ssh,live}`; `writes_enabled=True` only when `live_adapter AND live_authorized AND review_ready AND trainer_review_ready` (`:2938-2940`); worker passes `executor.config.adapter_name` (`arclink_action_worker.py:1089`) + `ARCLINK_ACADEMY_APPLY_LIVE` (`:1085`) |
| Button-nonce consume is non-atomic read-check-write | both (record risk #4 = Claude A6 = Codex CONFIRM) — LOW | `arclink_operator_raven.py:1381` SELECT → `:1388` `if used_at` → `:1394` `upsert_setting` (own commit `arclink_control.py:2971-2980`); no `BEGIN IMMEDIATE`/`WHERE used_at=''` guard |
| One-agent invariant is detection-after-the-fact, not prevention at first write | both (Claude A9 = Codex REFINE) | Conditional refusal only when pinned≠new AND pinned still resolves (`arclink_operator_agent.py:112-117`); global guarantee is post-hoc count `assert_single_operator_agent` (`:198-215`) called after create at `:378`; TOCTOU between read `:111` and writes `:171` |
| `public-agent-turn`/`operator_turn` seam (record contract #7 "partial") | codex/both — now both-ends verified | Producer `arclink_operator_agent.py:271-278`; consumer reads `operator_turn`/`source_kind` at `arclink_notification_delivery.py:1576` → `_run_operator_agent_gateway_turn` (`:1577`), control-stack gateway `:820-855` |
| Atomic `arclink_action_intents` claim is race-safe | both (record + Claude A1 + Codex CONFIRM) | `arclink_action_worker.py:456` `BEGIN IMMEDIATE`, `:472-483` guarded UPDATE, `:484` rowcount guard |
| Rollout is record-only everywhere | both (record + Claude A2 + Codex CONFIRM) | `arclink_rollout.py:426-428` plan pure; worker forces `record_only:True` at `arclink_action_worker.py:1236`; contract validator fake/local+record_only at `arclink_rollout.py:837-864` |
| Provisioner re-validates `request_source=="operator-raven"` | both (record + Claude A3 + Codex CONFIRM) | `arclink_enrollment_provisioner.py:2292-2297,2334-2337,2451-2453` |
| Seven mutating commands; mutating-detection excludes dry-run | both (record + Codex CONFIRM) | `arclink_operator_raven.py:225` (7-set), `:301-306` |
| `PIN_UPGRADE_COMPONENTS` imported policy, not local literal | both (record drift-note + Codex CORRECTED) | `arclink_upgrade_policy.py:9-17`; Raven imports at `arclink_operator_raven.py:35` |
| Read handlers allowlisted, no SQL injection | both (Claude A10 + record) | static allowlist before interpolation, e.g. `arclink_operator_raven.py:2030,2053,2065-2074` |

---

## 2. CODEX NEW FINDINGS — CONFIRMED vs REJECTED

### CONFIRMED (net-new federation risks)

- **CONFIRMED — MEDIUM — `operator_actions` is not an atomic queue.** Re-opened: enqueue is plain SELECT-then-INSERT with a bare `conn.commit()` and no `BEGIN IMMEDIATE`/unique key (`arclink_control.py:8273-8308`); schema has only a non-unique index `(status,action_kind,created_at)` (`:1860-1862`, table `:760-772`). Drain is `get_pending_operator_action` SELECT (`:8246-8256`) then unconditional `UPDATE status='running' WHERE id=?` with NO `WHERE status='pending'` guard (`:8581-8591`), reached by the provisioner (`arclink_enrollment_provisioner.py:2330-2342`). Two concurrent drains can both claim the same pending row and double-run a host/pin upgrade; two concurrent requesters can both pass the dedupe SELECT and double-INSERT. This is a genuine asymmetry vs the `arclink_action_intents` lane (which has `BEGIN IMMEDIATE`+rowcount). It bears on the host-upgrade/pin-upgrade lane more directly than the nonce race. NET-NEW.

- **CONFIRMED (with precondition) — `academy_apply` path containment misses symlink ancestors.** Re-opened: `_academy_safe_relative_path` rejects absolute + `..`/`.`/empty parts *lexically only* (`arclink_action_worker.py:1417-1424`); the per-file write `path = vault / relative` (`:2104`) is never re-resolved against the vault root; `_write_private_text_atomic` does `mkstemp(dir=path.parent)` + `os.replace` with no resolved-parent containment check (`:1384-1405`). The vault root itself is resolved once at root-computation (`:1376-1380`), but a symlink at any *intermediate* directory inside the vault tree is followed. Real defense-in-depth gap. **Severity standing-disagreement: MEDIUM (Codex) vs LOW (adjudicator).** Precondition: exploitation requires an attacker who can already plant a symlink inside the deployment's 0600 private vault state root, and writes are already adapter+`ARCLINK_ACADEMY_APPLY_LIVE`+review+trainer gated. The gap is code-confirmed; the severity is a judgment that code alone does not settle (see §5).

- **CONFIRMED — LOW — executor selection runs before the attempt row / failure path.** Re-opened: `_select_action_executor` runs at `arclink_action_worker.py:694-701`, BEFORE `_record_attempt` (`:703-705`) and outside the `try` that records failure (which begins at `:736`). A raise in selection leaves the action `running` (already claimed at `:645`) with no attempt and no `action_failed` event — recoverable only after 1h by `recover_stale_actions`. Compounds with the stale-requeue finding (the same wedge re-queues forever). NET-NEW (LOW).

### REJECTED
- None. All three Codex new findings re-verified true in code. (The only divergence is a severity calibration on the academy symlink gap, recorded as a standing disagreement, not a rejection.)

---

## 3. CONFIRMED net-new findings from the Claude adversarial pass

- **MEDIUM — `recover_stale_actions` infinite re-queue, no failed-path/cap** (Claude B1, Codex CONFIRM). Cite as in §1.
- **LOW/INFO — `_redact_text` only redacts `key=value` lines.** Re-opened: `arclink_operator_raven.py:2418` fires redaction only on `_SECRETISH_RE.search(line) AND "=" in line`; a secret rendered with `:` (e.g. `Authorization: Bearer`, JSON `"token": "x"`) passes through. Record's "outputs are scrubbed" is a minor over-claim. CONFIRMED LOW/INFO.
- **INFO — host-upgrade dedupe ignores `request_source`** (Claude B3). `request_operator_action` non-`dedupe_by_target` path dedupes on `(action_kind, status∈{pending,running})` only (`arclink_control.py:8200-8216,8288`); an operator `/upgrade confirm` can dedupe onto a pre-existing non-operator-raven `upgrade` row and return `created=False`. Net effect stays safe because the provisioner `request_source` re-check fails that pre-existing row closed; the Raven "already queued" message is merely misleading. CONFIRMED INFO. (Note: this same dedupe is what the §2 atomicity finding shows is itself non-atomic.)

---

## 4. SEVERITY CHANGES (code-supported only)

| Risk | From | To | Deciding cite |
|---|---|---|---|
| Approval-code enforcement in transport (record risk #1) | MEDIUM | LOW | Caller set closed + all transports gate typed mutating text (`arclink_telegram.py:1305-1307`, `arclink_curator_onboarding.py:345-347`, `arclink_curator_discord_onboarding.py:310-317`); true residual is the LOW callback path (`arclink_curator_onboarding.py:822-838`) |
| `academy_apply` live filesystem write (record risk #3) | MEDIUM | LOW | It IS executor-adapter gated + 3 more gates: `arclink_academy_programs.py:2864,2938-2940`; record's "one env var" mechanism is wrong |
| `operator_actions` queue atomicity (new) | (none) | MEDIUM | `arclink_control.py:8273-8308,8581-8591,1860-1862` |
| stale-action infinite re-queue (new) | (none) | MEDIUM | `arclink_action_worker.py:2247 vs 2262,2281` |
| academy symlink-ancestor containment (new) | (none) | LOW (adjudicator) / MEDIUM (Codex, standing) | `arclink_action_worker.py:1417-1424,2104,1384-1405` |
| executor-select-before-attempt (new) | (none) | LOW | `arclink_action_worker.py:694-705,736` |

Unchanged: button-nonce double-consume LOW (confirmed); dismissed-pin-upgrade MEDIUM (confirmed); ctl token-persistence LOW; prior ground-truth doc INFO; `_handle_status` default-shape INFO.

---

## 5. STANDING DISAGREEMENTS (not settleable from code alone)

1. **Severity of the `academy_apply` symlink-ancestor containment gap.** Codex rates MEDIUM; the adjudicator rates LOW. The *code fact* is reconciled and agreed: there is no resolved-parent containment re-check on the per-file write (`arclink_action_worker.py:1384-1405,2104`), and `_academy_safe_relative_path` blocks `..` lexically only (`:1417-1424`). What is NOT decidable from code alone is the likelihood/impact: exploitation requires an attacker who can already write a symlink inside the deployment's private (0600) vault state root, behind the full live-adapter+`ARCLINK_ACADEMY_APPLY_LIVE`+review+trainer gate. That is a threat-model/precondition judgment, not a code question — hence preserved rather than averaged. Both models agree the gap is real and a resolved-parent containment guard should be added; only the rank differs.

---

## 6. FINAL BOTH-MODEL VERDICT

CANON-14 stands. The control plane provably does its job — fail-closed, identity-gated, audited; never-inline mutation; atomic `arclink_action_intents` claim; record-only rollout; provisioner `request_source` re-check. Reconciled corrections, all code-grounded:

1. Record risk #1 (approval code) MEDIUM → LOW: the caller set is closed (3 transports + Raven recursion, no web/API route) and all transports gate typed mutating text; the true residual is the LOW callback/`custom_id` path that an already-allowlisted operator could use to skip their own code.
2. Record risk #3 (`academy_apply`) MEDIUM → LOW: its stated mechanism ("one env var, not the executor adapter") is factually wrong — it IS executor-adapter gated plus three more gates.
3. Four net-new federation findings ratified: MEDIUM `operator_actions` non-atomic queue (Codex); MEDIUM stale-action infinite re-queue with no failed-path/cap (Claude); LOW executor-select-before-attempt (Codex); LOW/INFO `_redact_text` key=value-only (Claude). Plus INFO host-upgrade dedupe ignores `request_source`.
4. Record risk #2 (dismissed pin upgrades queueable) and risk #4 (nonce double-consume) stand as written.
5. The `public-agent-turn`/`operator_turn` seam is now both-ends verified, closing the record's last "partial" contract.

One standing disagreement remains: the *severity* (LOW vs MEDIUM) of the academy symlink-ancestor containment gap — a threat-model judgment, not a code dispute; the underlying code fact is agreed.

**FEDERATION SIGN-OFF: AGREED-WITH-STANDING-DISAGREEMENTS.**
