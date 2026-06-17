# CANON-17 — Academy / Crew / SOUL — DECIDED (final adjudication)

- Piece: CANON-17 — Academy (specialist formation) / Crew Recipe SOUL-overlay / SOUL templates
- Adjudicator: Claude Opus 4.8 (1M), DECISION mode, code-grounded.
- Codex proposal: `research/canon/decisions/CANON-17-academy-crew-soul.codex.md` — emitted NO decision blocks; asserts CANON-17 has zero deferred operator decisions.
- NEEDS_DECISION ledger: `## CANON-17 — academy crew soul (1)` → `NONE`.
- **CONVERGENCE: BOTH-MODEL-AGREED — no operator decision is owed for CANON-17.** I independently re-opened the code to test whether Codex's "no decision" is a real null or a missed call. It is a real null: every item the audit/reconciled record flagged as a candidate policy question was *repaired into landed code* by the campaign, not deferred. Inventing a decision here would violate the symphony's own governance rule.

---

## Method (why "no decision" is itself an adjudicated verdict, not a skip)

A "NONE" in the ledger could mean (a) nothing was ever in question, or (b) the repair campaign converted deferred policy calls into landed fixes so cleanly that no question survives. CANON-17 is case (b) — which is the *good* outcome but demands proof, because the reconciled record (`research/canon/reconciled/CANON-17-academy-crew-soul.reconciled.md`) was rich with confirmed risks (two HIGH, several MEDIUM/LOW, NF-1/2/3, G1-G5). I re-opened each to confirm it is now resolved in the working tree rather than merely renamed. All checks pass; the four CANON-17 suites + CANON-14 action-worker suite are green.

Symphony decision rule (the controlling anchor for this whole file):
> "A policy choice stays a policy question until the operator/product decision is recorded and tests encode it." — `docs/arclink/sovereign-control-node-symphony.md:1659` (Governance And Proof)

Its inverse is equally binding: once the decision *is* recorded in code and encoded in tests, it is **no longer** a policy question and must not be re-litigated as one. That is exactly CANON-17's state.

---

## [VERDICT: agree-codex] D0 — Does CANON-17 owe the operator any deferred decision?

**Question.** The campaign deferred ~66 operator calls across 32 pieces. Codex claims CANON-17 contributes zero. Is that correct, or did a wide-blast-radius / threat-model / product-fork item get mislabeled "fixed" when it should have been escalated to the operator?

**My independent reasoning (code re-opened).** The candidates that *could* have been escalated were the reconciled record's named risks. Each is now closed in the tree:

1. **HIGH — live crawler + live Trainer default-ON (the "single biggest canon correction").** Now opt-in. `python/arclink_academy_scheduler.py:722` gates the crawl on `ARCLINK_ACADEMY_CE_LIVE_CRAWL` with `default=False`; `compose.yaml:97-98` export `ARCLINK_ACADEMY_TRAINER_LIVE:-0` and `ARCLINK_ACADEMY_CE_LIVE_CRAWL:-0`. No `config/*.env*` lane re-enables either (grep over `config/` returns nothing). This is not a deferred fork — the symphony itself *prescribes* the answer ("The live LLM Trainer is opt-in (`ARCLINK_ACADEMY_TRAINER_LIVE=1`)", `symphony:698-699`), so making the default opt-in is convergence-with-intent, not a product choice. Decision foreclosed by the north star.

2. **NF-1 / MEDIUM — `academy_apply` advertised PG-PROVIDER but enforced only PG-HERMES (cosmetic provider gate).** Now genuinely enforced. `provider_review_ready` is initialized `False` (`programs.py:2951`) and set `True` only when `live_enrichment_status == "live_reviewed"` (`:2967`), which itself is only ever `"live_reviewed"` under `if use_live` (`:2345`) — otherwise `"pending_pg_provider"`. The writes-enabled branch now requires `... and provider_review_ready` (`:3015`), with an explicit dedicated `failed_closed` arm when trainer-ready-but-not-provider-ready (`:3026`: "Academy Trainer PG-PROVIDER live review is not complete; no Agent-home write"). The label is no longer cosmetic; it is the gate. This was the one genuinely borderline "should-this-be-a-decision" item — and it was answered the only way the symphony permits ("a named live proof gate where external systems are reached", `symphony:159`; "and how it fails closed", `:161`). Foreclosed.

3. **NF-2 / LOW — source-lane validation fail-open.** Now fails closed: `_validate_source_lanes` raises `ArcLinkAcademyProgramError("academy source lane registry is unavailable")` on registry-import failure instead of returning unvalidated caller lanes (`programs.py:3162-3164`).

4. **Remaining LOW/INFO (G2 crawl-limit-0, G3 robots 5xx fail-open, G4 silent live-Trainer failure, NF-3 observation-id collision).** All repaired and test-covered per the fix report and spot-verified: crawl limit `minimum=1` so `0` no longer disables the bound (`scheduler.py:737`); robots 5xx now blocks (`scheduler.py:374`, `if status >= 400: return False`); live-Trainer failure surfaces a redacted event/notification (`programs.py:2371`); observation-id includes `source_uid` + conflict-tolerant insert (`scheduler.py:519`).

5. **CANON-14 cross-piece residual.** The ledger's one CANON-14 item (`test_academy_apply_action_materializes_local_hermes_home_when_authorized` failing) now PASSES — `tests/test_arclink_action_worker.py` runs 48/48 green. The fail-closed-because-PG-PROVIDER-not-complete behavior is now the *intended* behavior with PG-PROVIDER actually wired, so the test no longer contradicts the Academy contract.

**Test gate.** `tests/test_arclink_academy_programs.py`, `_scheduler.py`, `_trainer.py`, `_crew_recipes.py` all PASS; CANON-14 action-worker 48/48 PASS. The decisions are encoded, satisfying the second half of `symphony:1659`.

**Where I agree / differ from Codex.** Full agreement on the verdict (no decision owed) and on the governing anchor (Governance And Proof, `:1659`). I differ only in *rigor of justification*: Codex asserted the null from the ledger + repair report; I re-opened the code to prove the null is real (case (b), repaired-not-deferred) rather than assumed. Same destination, stronger floor. No refinement to Codex's recommendation is warranted — there is nothing to refine in "make no decision," and the symphony forbids manufacturing one.

**FINAL PLAN.** Record CANON-17 as **NO operator decision required**. Do not open a synthetic decision. The campaign already moved the code toward the symphony (opt-in live, enforced PG-PROVIDER, fail-closed registry/robots/limit) and encoded each in tests; per `symphony:1659` these are settled, not pending. Operator action: none beyond ratifying that the shipped opt-in live defaults and the now-enforced PG-PROVIDER apply gate are the intended posture (they match the symphony verbatim).

**Symphony anchor.**
> "A policy choice stays a policy question until the operator/product decision is recorded and tests encode it." — `symphony:1659` (the decisions are recorded in code + encoded in tests → no longer questions)
> "The live LLM Trainer is opt-in (`ARCLINK_ACADEMY_TRAINER_LIVE=1`) ... and fail closed to the deterministic engine on any missing key, router error, or authorization gap." — `symphony:698-705` (the opt-in default is the prescribed answer, not a fork)

**Effort.** low. **Blast radius.** none (documentation/ratification only; no code or contract change).

---

## Agreed-open verification seams (NOT decisions — recorded for completeness)

These are tracked in the reconciled record as *agreed-open* (both models concur they are open seams, not disagreements, and not operator policy forks). They are listed so they are not silently dropped, but neither blocks and neither is the operator's call to make in this round:

- **CANON-16 router response-shape contract is producer-only verified.** `RouterAcademyTrainerClient.review` POSTs the OpenAI-compatible payload (`programs.py:2175`) and parses defensively; the `control-llm-router:8090/v1/chat/completions` consumer end is owned by CANON-16, not CANON-17. This is an engineering cross-verification task, not a policy decision. Resolution: covered when CANON-16's live-proof gate runs end-to-end. (`symphony:159` — "a named live proof gate where external systems are reached".)
- **Deploy-private `config/*.env*` could in principle re-flip the live defaults.** Confirmed in this round that no tracked `config/` lane does so; whether a *private* operator env file overrides them is outside this read-only proof and owned by CANON-27's env-matrix review. The shipped tracked default is opt-in; if an operator deliberately sets the live flags, that is their sovereign choice under the documented opt-in contract, which fails closed without the scoped router key regardless.

---

## STANDING DISAGREEMENTS
None. I converge with Codex completely: CANON-17 owes the operator no decision. The repair campaign resolved every candidate policy question into landed, test-encoded code, and the symphony's governance rule (`:1659`) makes that resolution terminal. There is no genuine product fork for the operator to pick in this piece.
