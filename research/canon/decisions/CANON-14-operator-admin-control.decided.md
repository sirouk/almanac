# CANON-14 — Operator & Admin Control — DECIDED (Opus 4.8 final adjudication)

> Decision mode. One deferred operator call from the repair campaign
> (`research/canon/NEEDS_DECISION.md` "## CANON-14"). Codex's proposal is in
> `research/canon/decisions/CANON-14-operator-admin-control.codex.md`. Each
> decision below carries an independent verdict, the converged final plan, the
> symphony anchor it satisfies, effort, and blast-radius. Prose lives here; the
> structured manifest is the machine-readable summary.

---

## DECISION 1 — `academy_apply` materialization gate: PG-HERMES alone, or PG-PROVIDER + PG-HERMES? [VERDICT: agree-codex]

### The question (as deferred)
`tests/test_arclink_action_worker.py` "still fails" at
`test_academy_apply_action_materializes_local_hermes_home_when_authorized`:
current code fails closed because the PG-PROVIDER live review is not complete.
The repair campaign declined to "rewrite that CANON-17/Academy expectation in
this CANON-14 repair" — i.e. it left open whether the live Agent-home write
should be gated on PG-HERMES authorization alone, or on PG-PROVIDER **and**
PG-HERMES, and whether the test should be made to pass by establishing a real
provider review or by relaxing the gate.

### My independent reasoning (code re-opened, prove-don't-guess)

I re-opened the code before forming a view. The gate is in
`stage_academy_apply` (`python/arclink_academy_programs.py:2862`). `writes_enabled`
is `True` only when **all five** hold (`:3015`):
`live_adapter AND live_authorized AND review_ready AND trainer_review_ready AND
provider_review_ready`.

- `live_adapter` = adapter ∈ {local, ssh, live} (`:2939`) — the executor-adapter gate.
- `live_authorized` = explicit **PG-HERMES** authorization passed by the worker
  (`ARCLINK_ACADEMY_APPLY_LIVE`, `python/arclink_action_worker.py:1085`).
- `provider_review_ready` = `live_enrichment_status == "live_reviewed"` (`:2967`),
  which `run_academy_trainer_review` sets **only** when the deep dive ran on a
  live router client under `live_authorized` (`:2324`, `:2345`); a
  deterministic/engine-only review stays `pending_pg_provider`. The enrichment
  stamps `"proof_gate": "PG-PROVIDER"` (`:2344`). This is the **PG-PROVIDER** gate.

The distinct fail-closed branch at `:3026-3029` returns `failed_closed` with the
note "Academy Trainer PG-PROVIDER live review is not complete" precisely when
PG-HERMES is satisfied but PG-PROVIDER is not. The surface advertises **both**
gates: `ACADEMY_APPLY_PROOF_GATES = ("PG-PROVIDER", "PG-HERMES")`
(`python/arclink_academy_programs.py:63`), mirrored into the result `proof_gates`
(`:3077`) and the per-Agent status summary `apply_proof_gates` (`:1055`).

So the symphony's "same truth across surfaces / never a cosmetic proof gate"
test is decisive: the surface tells the Captain and Operator that an Academy
write is gated by PG-PROVIDER **and** PG-HERMES. Relaxing the write to
PG-HERMES-only would make PG-PROVIDER advisory while the surface still
advertises it — exactly the cosmetic-gate anti-pattern the North Star forbids.
The symphony text is explicit that Agent mutation sits behind PG-PROVIDER and
PG-HERMES (Academy section, `:675-676`: "Live transcript/ASR,
provider-assisted synthesis, source retirement, and Agent mutation remain under
the acquisition, critic, PG-PROVIDER, and PG-HERMES gates"). Keep the gate.

**Critical correction to the deferral premise (verified, not assumed):** the
test does NOT currently fail. I ran both relevant suites on this branch:

- `python3 tests/test_arclink_action_worker.py` → "All 48 action worker tests
  passed", including `test_academy_apply_action_materializes_local_hermes_home_when_authorized`.
- `python3 tests/test_arclink_academy_programs.py` → "all academy programs tests"
  pass, including `test_academy_apply_is_fail_closed`.

The positive test already establishes the PG-PROVIDER review the way Codex
proposes: it builds a synthetic live Trainer (`_ApplyLiveTrainer`, `live = True`)
and calls `run_academy_trainer_review(conn, specialist_uid=spec_uid,
client=_ApplyLiveTrainer(), live_authorized=True)`
(`tests/test_arclink_action_worker.py:945-961`) BEFORE expecting
`applied_hermes_home`. The negative contract is asserted in two places:
`test_academy_apply_action_stages_fail_closed_without_authorization` (worker) and
`test_academy_apply_is_fail_closed` (programs, the `:621`-area test), which proves
**PG-HERMES alone → failed_closed** then **PG-PROVIDER + PG-HERMES → handoff**
(`tests/test_arclink_academy_programs.py:622-633`). The `tests/` directory is also
writable in this workspace — the CANON-29 "tests not writable" constraint that
shaped the deferral note is stale here.

Conclusion: the deferred decision has already been resolved in code in exactly
the direction the symphony demands. The NEEDS_DECISION note is **stale**, almost
certainly written against an earlier commit before the PG-PROVIDER gate + its
test fixture landed.

### Where I agree / differ from Codex

I agree with Codex on every substantive point: keep the fail-closed gate
(`live_adapter + live_authorized + review_ready + trainer_review_ready +
provider_review_ready`); derive `provider_review_ready` from
`live_enrichment_status == "live_reviewed"`; resolve the test by establishing a
real PG-PROVIDER review via a synthetic live Trainer client (not real provider
calls, which are secret-gated and flaky); keep the negative
PG-HERMES-alone → `failed_closed` assertion; treat this as CANON-17 Academy
contract alignment, NOT a CANON-14 operator-admin relaxation; reject relaxing to
PG-HERMES-only (makes PG-PROVIDER advisory while advertised) and reject
xfail/skip (hides contract drift). Codex's "low effort / no operator-admin queue
behavior change" call is right.

The only refinement — and it is a factual one, not a direction change — is that
Codex frames the work as still-to-do ("Resolve the failing test by making the
fixture establish ..."). On this branch that fixture, that gate, and both the
positive and negative assertions are **already present and green**. Codex's
own caveat ("unless the current branch lacks the fail-closed PG-PROVIDER gate")
is the branch that obtains: the gate is present. So the converged plan collapses
to **ratify the shipped contract and retire the stale NEEDS_DECISION line**,
plus two small belt-and-braces guards so the contract cannot silently regress.

### FINAL PLAN (converged)

1. **Ratify the shipped gate. Do nothing to relax it.** Keep
   `writes_enabled = live_adapter AND live_authorized AND review_ready AND
   trainer_review_ready AND provider_review_ready`
   (`python/arclink_academy_programs.py:3015`). PG-PROVIDER
   (`live_enrichment_status == "live_reviewed"`, `:2967`) and PG-HERMES
   (`live_authorized` via `ARCLINK_ACADEMY_APPLY_LIVE`) are both load-bearing.
   This is a CANON-17/Academy contract, surfaced identically on the action
   result (`proof_gates`, `:3077`) and the per-Agent status summary
   (`apply_proof_gates`, `:1055`); it does not change any operator-admin queue
   behavior in CANON-14.

2. **Retire the stale deferral.** Update `research/canon/NEEDS_DECISION.md`
   "## CANON-14" to record that the item is RESOLVED IN CODE: the test passes,
   the gate is the correct PG-PROVIDER + PG-HERMES fail-closed contract, and the
   "tests/ not writable" premise does not hold in this workspace. This keeps the
   ledger honest (the North Star's "same truth" applied to our own provenance).

3. **Belt-and-braces (cheap, prevents silent regression of an advertised
   gate).** Add one assertion to the existing
   `test_academy_apply_is_fail_closed` (or a tiny sibling) that the result's
   advertised `proof_gates`/`apply_proof_gates` contains BOTH `"PG-PROVIDER"`
   and `"PG-HERMES"`, so any future edit that drops a gate from the contract
   constant fails a test rather than silently de-advertising a proof. This is
   the concrete guard against the cosmetic-gate failure mode and costs ~3 lines.

4. **Use a synthetic live Trainer for the proof, never a real provider call in
   unit tests** — already the pattern (`_ApplyLiveTrainer`); real PG-PROVIDER
   availability belongs to the named live-proof lane, not the regression suite.
   No change needed; recorded so a future contributor does not "fix" the test by
   reaching for a live router key.

No production queue, no operator-admin, and no executor behavior changes. This
is contract ratification plus a regression fence.

### Symphony anchor

> **Academy Trainer And Subject-Matter Formation:** "Live transcript/ASR,
> provider-assisted synthesis, source retirement, and **Agent mutation remain
> under the acquisition, critic, PG-PROVIDER, and PG-HERMES gates**."
> (`docs/arclink/sovereign-control-node-symphony.md:674-676`)

> **North Star proof rule:** "Every step should have a local source owner, a
> local regression or dry-run proof where possible, and **a named live proof
> gate where external systems are required**. If any step cannot say ... how it
> fails closed, the symphony is not complete."
> (`docs/arclink/sovereign-control-node-symphony.md:158-161`)

The shipped gate satisfies both: PG-PROVIDER is the named live-proof gate for
the provider-assisted Trainer deep dive; PG-HERMES is the named gate for the
Agent-home write; the local regression proof is the synthetic-Trainer test; and
absent either gate the action fails closed without touching SOUL.md, the vault,
or qmd/memory/skill state (`:3022-3041`).

### Effort / blast-radius

**Effort: low.** Steps 1 and 4 are no-ops (ratify the existing contract). Step 2
is a one-line ledger edit. Step 3 is ~3 lines added to one existing test.

**Blast-radius: contained to CANON-17/Academy regression + the ledger.** No
operator-admin production queue, no `operator_actions`/`arclink_action_intents`
behavior, no executor adapter, no transport. Preserves Pod state by default
(the control plane itself performs no filesystem write —
`mutation_performed=False` even on success) and leaves redacted evidence (the
private apply receipt + post-apply-refresh handoff).

---

## Note on scope

The repair campaign deferred exactly ONE item under CANON-14, and it is the
above. The four net-new federation findings recorded in the reconciled doc
(`operator_actions` non-atomic queue, stale-action infinite re-queue, executor-
select-before-attempt, `_redact_text` key=value-only) and the one standing
disagreement (academy symlink-ancestor containment severity, LOW vs MEDIUM) are
**audit findings**, not deferred operator decisions, and were not listed in
NEEDS_DECISION for CANON-14. I verified during this pass that the stale-action
cap finding has already been remediated on this branch
(`test_stale_action_recovery_fails_after_attempt_cap` passes), and the
concurrent-claim guard is proven
(`test_concurrent_workers_claim_action_once` passes). Those remediation/hardening
items belong to the audit track, not this decision file; I flag only that they
exist so the operator does not mistake this single-decision file for the full
risk register. The reconciled standing disagreement (symlink severity) is
carried forward below as the operator's threat-model call.
