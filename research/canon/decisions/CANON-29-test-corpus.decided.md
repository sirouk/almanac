# CANON-29 — Test Corpus — DECIDED (final adjudication, symphony-anchored)

- **Piece:** CANON-29 (`tests/**`: 128 tracked `tests/test_*.py`, 1 helper, 1 golden fixture)
- **Adjudicator:** Claude Opus 4.8 (1M) — FINAL ADJUDICATOR, Federation DECISION mode.
- **Codex input:** `research/canon/decisions/CANON-29-test-corpus.codex.md` (GPT-5.5 xhigh).
- **Method:** Formed an independent view from the symphony (intent) and the live code (reality), re-opened every cited line with `rg`/`sed`, re-RAN the affected tests on this host, then converged with Codex. Code wins over comment/name/prior claim.
- **Net:** One deferred decision. Verdict: **refine** (Codex's substance is right; one load-bearing premise it rests on is now stale and is corrected). Converged to a single recommended plan. No product fork.

---

## DECISION 1 — Do dedicated `tests/test_arclink_upgrade_policy.py` and `tests/test_arclink_rejection_incidents.py` files have to exist, or does wired behavioral coverage in existing runnable files satisfy CANON-29?

**[VERDICT: refine]** (right direction — accept the behavioral coverage and resolve the piece — but Codex's framing rests on "the workspace refused writes," and that is **no longer true**, so the reasoning is corrected and the recommendation is hardened rather than waived-by-necessity.)

### The question
The repair landed direct behavioral coverage for both modules inside existing runnable files instead of creating two dedicated `tests/test_*.py` files, because at repair time `tests/` was reported non-writable. The deferred call: must the literal dedicated files be created, or is the existing wired coverage the CANON-29-correct answer?

### My independent reasoning (code-grounded)
1. **The deferral's blocker is gone.** At repair time the justification was "`tests/` is not writable in this workspace." Re-checked on this host: `tests/` **IS writable** (`test -w tests` true; `touch tests/.__write_probe__` succeeded). So this can no longer be framed as "waived because we couldn't write the files." The decision must stand on the merits, not on a filesystem accident.

2. **Both modules are source-owned and the source fails closed.**
   - `python/arclink_upgrade_policy.py`: public API `upgrade_policy_catalog():270`, `upgrade_policy_for():274` (raises `ValueError("unknown ArcLink upgrade component…")` on unknown — fail-closed), `upgrade_policy_summary():283` (read-only; `mutation_performed is False`), `policy_components_by_scope():305`. This is a read-only policy surface, exactly the "operators own … upgrades … read-only summary" intent.
   - `python/arclink_rejection_incidents.py`: `state_root_rejection_path():72`, `safe_metadata():111`, `record_rejection_incident():128`, with `_safe_existing_base():18` / `_safe_child_path():39` rejecting relative roots, symlinked roots, and following symlink leaves — fail-closed, secret-redacting, the GAP-019 boundary's redacted-evidence rail.

3. **The coverage is real, deep, and asserts the symphony-relevant properties — not just imports.**
   - `tests/test_arclink_operator_raven.py:324` `test_upgrade_policy_catalog_is_sorted_grouped_and_read_only` loads the real module and asserts: rollout order is sorted, `STATEFUL_PIN_UPGRADE_COMPONENTS == {nextcloud,postgres,redis}`, `summary["mutation_performed"] is False` (read-only), proof gate `PG-HERMES` present, aliases normalize (`plugins`→`dashboard-plugins`, `wg`→`wireguard`), and **unknown component fails closed** (`ValueError`, else `AssertionError("unknown components must fail closed")`). Plus the transitive Raven-dispatch proof at `:291`.
   - `tests/test_arclink_notification_delivery.py:1933` `test_rejection_incident_helpers_redact_and_refuse_unsafe_paths` loads the real module and asserts: safe parent creation, metadata redaction (`"SECRET" not in raw`, unsafe keys dropped), **0600-ish perms** (`S_IMODE & 0o077 == 0`), **relative root rejected** (returns `None`), **symlink root rejected** (returns `None`), **symlink leaf not followed**. Plus the gateway-broker "records redacted incident before subprocess" proof at `:1757`.

4. **The coverage is wired into the ENFORCED gate, and an orphan guard now keeps it wired.** CI runs `for f in tests/test_*.py: python3 "$f"` (`.github/workflows/install-smoke.yml:31-42`) — direct `__main__`, not pytest. Both tests are wired: `test_arclink_operator_raven.py:1190-1191` and `test_arclink_notification_delivery.py:2613-2614`. The new corpus guard `test_python_test_files_wire_module_level_tests_into_direct_runners` (`tests/test_documentation_truths.py:458`, wired into its own `__main__` at `:492`) fails the build if any module-level `test_*` is not reachable from its file's direct runner. Re-ran on this host: the guard PASSES, and both owning files run GREEN end-to-end (`OK`/`all … tests passed`, exit 0). So the proof is live-real *and* fenced against future drift.

5. **A dedicated file would add zero proof strength.** The symphony's proof boundary is "a claim is local-real only when **source and regression tests prove it**" (§Governance, l.1656) — not "when a file named after the module exists." Splitting these assertions into `test_arclink_upgrade_policy.py` / `test_arclink_rejection_incidents.py` would re-home identical assertions; it strengthens the gate only if wired into the *same* direct CI runner — which the current location already is. The taxonomy gain (one-file-per-module browsability) is cosmetic.

### Where I agree / differ from Codex
- **Agree (substance):** Don't block on the literal filenames; accept the wired behavioral coverage; keep the direct-runner orphan guard as the canonical corpus contract because CI runs files directly. Codex's symphony anchor (Governance/Proof, l.1656) is the correct one. All cited lines re-verified true.
- **Differ (premise / framing):** Codex justifies the waiver partly on "after the workspace refused writes" and "this read-only host lacks a usable temp directory." Both are **stale here**: `tests/` is writable and the two tempdir-heavy tests RAN GREEN on this host (no temp/FS failure). So the right framing is not "waived because we couldn't write the files" but "**not required because source+regression already prove the claim under the enforced gate**." Same outcome, sounder reason — which matters because the operator should resolve this on the proof boundary, not on a transient sandbox limitation that could mislead a future reader into thinking the files are still owed.

### FINAL PLAN (converged)
1. **Resolve CANON-29 needs-decision as: dedicated filenames NOT required — behavioral coverage accepted.** Rationale recorded on the proof boundary, not on writability: both modules are source-owned and fail-closed; both have wired, GREEN, property-level regression coverage under the enforced `python3 tests/test_*.py` runner; the corpus orphan guard (`test_documentation_truths.py:458`) keeps them wired.
2. **Correct the stale rationale in the repair record.** Update the CANON-29 needs-decision note in `research/canon/NEEDS_DECISION.md` and the Repair-status block in `research/canon/reconciled/CANON-29-test-corpus.reconciled.md:92-93` to drop "could not be created because `tests/` is not writable" and replace with "dedicated files not required: direct property-level coverage is wired into the enforced direct-runner CI and fenced by the corpus orphan guard." (Docs-only; no code.)
3. **Keep the orphan guard as the canonical corpus contract** (`tests/test_documentation_truths.py:458`, wired `:492`). It is the structural fix that makes "behavioral coverage in any runnable file" durable; do not regress it.
4. **OPTIONAL, low-effort, operator-discretion (now unblocked by writability):** if per-module browsability is desired, move the two `test_*` functions verbatim into dedicated `tests/test_arclink_upgrade_policy.py` / `tests/test_arclink_rejection_incidents.py`, re-wire each file's `__main__`, and update any `research/COVERAGE_MATRIX.md` anchor to point at the new path. Gate: the orphan guard must stay GREEN. This is a cosmetic re-home with no proof gain; do it only if the discoverability is worth the churn.

### Symphony anchor (quoted)
- §Governance And Proof, l.1656: *"A claim is local-real only when source and regression tests prove it."* — satisfied: both modules have source ownership AND wired regression tests asserting their real behavior.
- §"the symphony is not complete" rule, l.158-161: *"Every step should have a local source owner, a local regression or dry-run proof where possible … what state it reads, what state it writes, and how it fails closed."* — satisfied: `upgrade_policy` (read-only summary, unknown-component `ValueError`) and `rejection_incidents` (redacted JSONL, relative/symlink-root refusal, 0600 perms, symlink-leaf no-follow) each have an owner, a regression proof, and an explicit fail-closed path under test.

### Effort / blast-radius
- **Effort: low.** Decision is to ratify + a docs-only rationale correction. No production code, schema, API, or threat-model change. Optional file-split is also low but is churn-only.
- **Blast radius:** none in the resolve path (touches only CANON-29 status/rationale docs). The optional split touches two test files + one matrix anchor and is fenced by the orphan guard; zero production reach.
