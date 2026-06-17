# CANON-23 — Diagnostics / Health / Evidence — FINAL DECIDED (Claude Opus 4.8 adjudication)

Federation: Codex (GPT-5.5 xhigh) proposed; Claude Opus 4.8 independently re-grounded in code and converged.
Working tree re-read 2026-06-17 — code has moved since the reconciled/sections docs were written, and that
movement materially narrows the open decision (see "Code reality update" below).

## Code reality update (read before the decision)

The CANON-23 reconciled record listed four MEDIUM weaknesses. Re-opening the code today, the repair
campaign has ALREADY landed three of them, so they are no longer open operator calls:

- **Evidence DB now wired (conditionally).** `run_live_proof` calls `_store_evidence_run(...)` whenever
  `ARCLINK_DB_PATH` is set (`python/arclink_live_runner.py:753-758,795-826`), persisting the ledger to
  `arclink_evidence_runs` via the previously-unwired `store_evidence_run` DAL. The dashboard reads it back
  through `_latest_evidence_status_from_env` -> `latest_evidence_status` (`python/arclink_dashboard.py:832-846`).
  The "operator-visible evidence is not real" gap is closed for the local path.
- **Live-proof exit-0 false-green fixed.** Exit code now gates on `_live_proof_checks_ok(...)`, which reads
  `readiness.ready` and `diagnostics.all_ok` for the relevant journeys (`python/arclink_live_runner.py:760-792`).
  `dry_run_ready` no longer exits 0 when host readiness/diagnostics failed.
- **Unguarded evidence write fixed.** The artifact write is wrapped in try/except with
  `artifact_write_failed` forcing exit 1 (`python/arclink_live_runner.py:742-751,770-771`).

What remains genuinely open is the ONE item in `NEEDS_DECISION.md`:

> CANON-23 — `run_diagnostics(live=...)` still documents future real provider connectivity; implementing
> actual live provider checks would change external-provider semantics and needs product/threat-model decision.

Code state of that item, re-read today:
- `run_diagnostics(*, env, docker_binary, live=False)` body never branches on `live`
  (`python/arclink_diagnostics.py:200-222`); docstring says "real provider connectivity could be tested
  (future)" (`:209`).
- CLI `main()` exits `0 if result.all_ok else 1` regardless of `--live` (`python/arclink_diagnostics.py:233-235`);
  `--live` help calls it "Reserve live connectivity mode" (`:230`). So `--live` is a silent no-op today.
- The read-only dashboard operator snapshot calls `run_diagnostics(env=..., docker_binary=...)` with NO
  `live` (`python/arclink_dashboard.py:565-569`), and labels integrations `pending_credentialed_run` /
  `blocked` against named PG-* gates (`:78,87,168,601`). It is already the symphony's three-state surface.
- `run_live_proof` Phase 2 calls `run_diagnostics(env=source, docker_binary=...)` with NO `live`
  (`python/arclink_live_runner.py:684`).
- The `external` journey is a full catalog of opt-in provider proofs gated on `ARCLINK_PROOF_*`
  (`python/arclink_live_journey.py:216-296`), but has NO runner factory — `run_live_proof` only builds
  `workspace`/`router` runners (`python/arclink_live_runner.py:690-693`). So `--journey external --live`
  with all creds present yields `blocked_no_registered_runner` and exit 1
  (`python/arclink_live_runner.py:696-699,766-769`). External provider truth correctly fails closed today.
- Existing contract test only asserts `live=False` produces no live checks
  (`tests/test_arclink_diagnostics.py:175-181`).

---

### [VERDICT: refine] DECISION 1 — `run_diagnostics(live=...)` must not silently imply live provider connectivity

**Question.** Should `run_diagnostics` implement real Stripe/Cloudflare/Tailscale/Chutes/Telegram/Discord
network connectivity when `live=True`, or stay local presence-only? And what should the dead `live`
parameter do?

**My independent reasoning.**
The symphony hands diagnostics exactly one job and one owner. Third-Party Integration Boundaries requires
"three visible states: configured and locally valid, configured but live-proof pending, or missing and
blocked with the next operator action." The first and third states are *local* truth — credential
presence and host/qmd readiness — which is precisely what `run_diagnostics` already computes without ever
emitting a secret value (`_credential_check` -> `"present"` / `"missing: NAME"`,
`python/arclink_diagnostics.py:46-51`). The MIDDLE state — "configured but live-proof pending" — is by
definition NOT diagnostics' to resolve; it is the boundary where a *named* live-proof gate takes over.
Notifications/Incidents/Evidence makes the ownership split explicit: "A clear split between local dry-run
proof, authorized live proof, policy decision, and residual-risk acceptance." Governance And Proof: "A
live claim becomes real only after authorized live proof and redacted evidence."

So a network probe inside `run_diagnostics` is the wrong owner doing live-proof work. Three concrete harms,
all code-grounded:

1. **It networkizes a read-only surface.** The dashboard operator snapshot calls `run_diagnostics`
   synchronously (`python/arclink_dashboard.py:569`). Adding provider calls would make a browser dashboard
   load fire live Stripe/Chutes/Cloudflare/Telegram/Discord requests — rate-limit exposure, latency,
   mutation-adjacency, and an outage in any provider degrading a local operator view. That breaks "boringly
   reliable underneath" (North Star) and the read-only contract of the snapshot.
2. **It conflates owners.** Live provider proof already has the right home and the right shape: the
   `external` journey catalog with `ARCLINK_PROOF_*` opt-in gates (`python/arclink_live_journey.py:216-296`),
   driven by `run_live_proof`, which writes redacted evidence and fails closed as
   `blocked_no_registered_runner` when no authorized runner exists. Duplicating that logic in diagnostics
   would create two competing truths for the same fact — the opposite of "Dashboard and Raven views of the
   same incident state."
3. **A no-op `--live` manufactures false confidence.** `--live` currently runs identical local checks and
   exits 0 on `all_ok` — an operator could read "live OK" when nothing live ran. Governance And Proof
   forbids claiming proof "not represented by source, tests, or named external evidence." This must fail
   closed, not silently pass.

**Where I agree with Codex.** Fully on the core: keep `run_diagnostics` local/presence-only; do NOT add
provider network calls; make `live=True` fail closed rather than no-op; implement real provider
connectivity ONLY as named `external`-journey runners under `ARCLINK_PROOF_*` gates with redacted evidence
through `run_live_proof`. The symphony anchors Codex cites are the right ones.

**Where I refine Codex.** Codex's "append a failed `DiagnosticCheck(provider='live-proof', ...)` so the
process exits nonzero" is directionally correct but under-specified on the seam that matters: there are two
in-process callers that pass NO `live` flag (`arclink_dashboard.py:569`, `arclink_live_runner.py:684`), so
they are unaffected — good. But Codex's phrasing risks an implementer making `live=True` *inject a failing
check into the returned result*, which would (a) flip `all_ok=False` for any future programmatic caller
that does pass `live=True` and (b) is a slightly awkward "a check failed" message for what is really
"this mode is not implemented here." I refine to a cleaner, more honest fail-closed:

- **Function level:** when `live=True`, do not silently run local-only checks. Raise a precise
  `NotImplementedError` (or return a result carrying a single explicit
  `DiagnosticCheck(provider="live-proof", name="provider_connectivity", ok=False, live=True,
  detail="live provider validation is not performed by diagnostics; run the named external live-proof gate")`).
  I lean to the explicit-failed-check form Codex proposed because it keeps the public return type stable and
  is JSON-serializable, but the message must say "not performed here / use the named gate," not imply a
  provider was contacted and failed. Keep redaction guarantees intact (no value path exists regardless).
- **CLI level (the real fix):** in `main()`, when `--live` is passed, print the redirect to the named
  live-proof gate and `return 1` (fail closed) — do not return `0 if all_ok` (`python/arclink_diagnostics.py:233-235`).
  Update `--live` help from "Reserve live connectivity mode" to point at `bin/arclink-live-proof --journey external`.
- **Docstring (`:206-210`):** delete "could be tested (future)"; state diagnostics is local presence/readiness
  only and that live provider truth is owned by the named external live-proof gate.
- **Tests:** keep the existing `live=False` no-op assertion; ADD a regression that `live=True` fails closed
  (nonzero exit / failed `live-proof` check) AND that the returned checks still emit only names, never
  values (re-assert the no-secret-value contract on the `--live` path).
- **Do NOT, in this decision, build the external provider runners.** That is the separate, larger work
  behind `PG-STRIPE`, `PG-BOTS`, `PG-INGRESS`, `PG-PROVIDER`, etc. This decision only (a) makes the dead
  param honest and fail-closed and (b) records that real provider connectivity lands as named gates. The
  reconciled doc's other CANON-23 MEDIUMs are already fixed (see Code reality update); they are not
  reopened here.

One more refinement Codex did not flag: the `external` journey advertises every provider proof in the
catalog but has zero runners, so the operator-facing message on `--journey external --live` is the generic
`"live proof requested but no runner is registered"` (`python/arclink_live_runner.py:728-731`). That is
honest fail-closed, but to satisfy "missing and blocked WITH the next operator action," the
`blocked_no_registered_runner` skip_reason for external steps should name the gate
(e.g. "PG-STRIPE runner not yet implemented; this is the next operator/build action"). I fold this in as a
low-effort copy improvement, not a behavior change.

**FINAL PLAN.**
1. `python/arclink_diagnostics.py`: docstring (`:206-210`) — remove "future"; declare diagnostics
   local-only and point at the named external live-proof gate. `--live` help (`:230`) — point at
   `bin/arclink-live-proof --journey external`.
2. `run_diagnostics` (`:200-222`): when `live=True`, append an explicit failed
   `DiagnosticCheck(provider="live-proof", name="provider_connectivity", ok=False, live=True,
   detail="live provider validation is not performed by diagnostics; use the named external live-proof gate")`
   so `all_ok` is False and the process exits nonzero — without contacting any provider. Preserve the
   names-never-values guarantee.
3. `main()` (`:233-235`): on `--live`, fail closed (`return 1`) and print the redirect line.
4. Keep both in-process callers untouched: dashboard snapshot (`arclink_dashboard.py:569`) and
   `run_live_proof` Phase 2 (`arclink_live_runner.py:684`) pass no `live` flag, so they keep their
   local-only behavior. Verify no other caller passes `live=True`.
5. `tests/test_arclink_diagnostics.py`: keep the `live=False` no-op test (`:175-181`); add a `live=True`
   fail-closed test and a no-secret-value assertion on the `--live` path.
6. Copy-only: external-step `blocked_no_registered_runner` skip_reason names the responsible PG-* gate as
   the next operator/build action (`python/arclink_live_runner.py:728-731`).
7. Real provider connectivity remains FUTURE WORK delivered as named `external`-journey runners under
   `ARCLINK_PROOF_*` gates, persisting redacted evidence via `run_live_proof` -> `store_evidence_run`
   (already wired) — NOT inside diagnostics, NOT as a dashboard side effect.

**Symphony anchor.**
- Third-Party Integration Boundaries: "Every integration must have three visible states: configured and
  locally valid, configured but live-proof pending, or missing and blocked with the next operator action."
  (Diagnostics owns states 1 and 3; the live-proof gate owns the pending->proven transition.)
- Notifications, Incidents, And Evidence: "A clear split between local dry-run proof, authorized live
  proof, policy decision, and residual-risk acceptance."
- Governance And Proof: "A live claim becomes real only after authorized live proof and redacted evidence";
  "Public docs never claim private proof that is not represented by source, tests, or named external
  evidence." (A no-op `--live` that exits 0 would be exactly such an unbacked claim — hence fail closed.)
- North Star: "boringly reliable underneath" — a read-only diagnostics/dashboard read must not become a
  networked provider probe.

**Effort.** low. (Docstring + help + one fail-closed check + one CLI return + two/three tests + one
skip_reason copy line. The medium/high work — actual provider runners — is explicitly out of this
decision and lives behind named gates.)

**Blast radius.** narrow. Only the `live=True`/`--live` path changes; both real in-process callers pass no
`live`, so dashboard, operator snapshot, and `run_live_proof` are unaffected. Risk: a hypothetical
out-of-tree caller passing `live=True` would now get a failing result/nonzero — which is the intended
fail-closed contract, and grep shows no such caller in python/bin/web.

---

## Standing disagreements (genuine operator forks)

None for the open decision. The local-vs-live ownership split is dictated by the symphony, not a product
fork — there is one right answer (fail closed in diagnostics; live truth via named gates). The only
genuine downstream FORK is sequencing, not direction: WHICH named external runner the operator funds first
(`PG-STRIPE` vs `PG-BOTS` vs `PG-INGRESS`/`PG-PROVIDER`). That is a roadmap/priority call outside this
decision's scope and does not block landing the fail-closed contract.
