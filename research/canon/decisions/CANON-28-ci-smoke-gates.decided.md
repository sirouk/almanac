# CANON-28 — CI, Smoke & Quality Gates — DECIDED (Federation final)

Adjudicator: Claude Opus 4.8 (1M) FINAL ADJUDICATOR, DECISION mode.
Counterpart: Codex (GPT-5.5 xhigh) — `CANON-28-ci-smoke-gates.codex.md`.
Method: every Codex recommendation re-opened against current code (rg/sed/AST) and the
symphony north star. Code wins over the audit snapshot, which is already stale in two
material ways (see "Code drift since audit"). Each decision below is the operator's call,
framed as one converged plan, not a menu.

## CODE DRIFT SINCE THE AUDIT (load-bearing — both reconciled/sections docs predate it)

Re-opening `.github/workflows/install-smoke.yml` shows the workflow has **already advanced**
past the audit snapshot. Decisions must start from current reality:

1. **A fatal Python lint gate already exists and passes.**
   `.github/workflows/install-smoke.yml:27-28` runs
   `python3 -m ruff check --select E9,F63,F7,F82 bin python tests plugins hooks`. I ran it:
   `All checks passed!`. The audit's "no Python style/lint gate (MEDIUM)" is now "fatal
   error-class lint gate present; full-style enforcement absent" — a different, narrower gap.
2. **`master` dead-branch trigger is gone.** Triggers are now `arclink`, `main` only
   (`:4-8`). The audit's LOW "master is a dead trigger" is resolved.
3. **Both live-smoke producers are now `-x`-guarded.** `bin/deploy.sh:5614` and `:5751`
   (`if [[ -x … ]]`), and `bin/arclink-docker.sh:2712-2716` (`docker_live_agent_smoke` returns
   0 with "skipping" if not executable). The reconciled "Docker producer is NOT -x-guarded"
   seam-5 correction is itself now stale; the Docker guard exists.
4. **Orphaned tests are GONE.** AST re-check of the three files the reconciled doc named:
   executor `main()` references all 52 `test_*` defs (52/52); docker `main()` 78/78; fleet
   lists all 26 at module scope. Repo-wide my AST orphan scan over all 128 `tests/test_*.py`
   finds **0 orphan test functions**. The specific orphans cited (executor `:1550/:1586`,
   docker `:2953/:4854`, fleet `:165/:192`) are all in their runner lists today.

This drift does not weaken the decisions — it sharpens them from "fix existing holes" to
"make the now-correct state enforceable and fail closed against regression."

---

## DECISION 1 — Orphaned tests & a repository-wide self-executing test contract

[VERDICT: refine — agree with Codex's AST-verifier mechanism; re-scope from "fix orphans"
(none exist) to "lock the contract closed so orphans cannot return," and put the gate in
CANON-28's CI lane, not buried in CANON-29 docs.]

**Question.** Should CANON-28 enforce that every `tests/test_*.py` actually runs all its
declared `test_*` functions, given the corpus mixes `unittest.main` auto-discovery and
hand-maintained explicit `tests = [...]` runner lists?

**Independent reasoning.** The risk is real and structural, even though the current count is
zero. The python-regressions gate runs `python3 "$test_file"` (`install-smoke.yml:40-42`);
a file that defines `test_foo` but forgets to add it to its `main()` list runs to a green
exit having tested nothing — and the workflow cannot see it. The corpus proves the trap is
easy to fall into: `tests/test_deploy_regressions.py:4604-4745` is a literal hand-maintained
`tests = [ … ]` list of ~140 names; one omission is invisible. Only 4 files use
`unittest.main` (auto-discovery), so a naive "every `test_*` must be `()`-called" grep would
false-positive on those four and miss list-driven runners. Codex's conservative AST verifier
— pass if the file either (a) calls `unittest.main(...)`, or (b) has a `main()`/runner whose
body references every top-level `test_*` def — is exactly the right shape. I verified that
this exact rule yields 0 violations on today's corpus, so the gate ships GREEN immediately
and only catches *future* regressions. That makes it a pure fail-closed ratchet with no
cleanup tail.

**Where I differ from Codex.** (a) Codex frames the existing orphans as a thing to fix
inside CANON-29; the code shows none remain, so the deliverable is purely the *verifier*,
not a corpus sweep. (b) Codex says "approve as a CANON-29 contract, then wire into CANON-28."
I invert the ownership emphasis: the *gate* is CANON-28's (it owns the CI producer); the
*per-file convention it enforces* is documented in CANON-29. The verifier script and its CI
step land in CANON-28 so the failure is visible on every push, not deferred to a doc. (c) Add
an explicit, narrow escape hatch (a `# test-entrypoints: unittest` / `# test-entrypoints:
manual <name>` pragma) so genuinely unusual harnesses can declare intent rather than being
forced into a false shape — this keeps the verifier conservative without an allowlist file
that rots.

**FINAL PLAN.**
1. Add `bin/check-test-entrypoints.py` (no third-party deps; stdlib `ast`): for each
   `tests/test_*.py`, parse, collect top-level `test_*` defs and a `main()`/`run_all`
   runner. PASS if `unittest.main(` appears OR every `test_*` def name is referenced
   (called or listed) within the runner / module scope; FAIL (non-zero, printing the file +
   missing function names) otherwise. Honor a `# test-entrypoints: <unittest|manual>` pragma
   on line 1-5 to opt a file out with a stated reason.
2. Add a CI step in the `python-regressions` job, **before** the test loop
   (`install-smoke.yml`, after `:28`): `python3 bin/check-test-entrypoints.py tests`. Fails
   the job closed on any unrun-test file. Ships green today (0 violations).
3. Make `bin/check-test-entrypoints.py` itself covered by a runnable test under `tests/`
   (fixtures: one unittest file, one good explicit-list file, one orphan file → expect
   exit 1) so the verifier cannot silently rot.
4. Document the contract in CANON-29's test-corpus section ("every `tests/test_*.py` runs
   all its `test_*` functions; declare exceptions with the pragma"). Do **not** migrate to
   pytest — that would change the established script-runner execution model.

**SYMPHONY ANCHOR.** Whole-System Traversal: "Every step should have a local source owner, a
local regression or dry-run proof where possible … If any step cannot say what surface owns
it, what state it reads, what state it writes, and how it fails closed, the symphony is not
complete." (`docs/arclink/sovereign-control-node-symphony.md:158-161`). The verifier makes
the test gate's own coverage a local, source-owned, fail-closed proof instead of an
invisible convention.

**EFFORT:** med. **BLAST-RADIUS:** CI config + one new ~120-line stdlib script + one fixture
test + a CANON-29 doc paragraph. Zero runtime code. Ships green (no corpus cleanup, because
no orphans remain); only future regressions are blocked.

---

## DECISION 2 — Provider-auth / provider-unavailable live-smoke skip exits 0

[VERDICT: agree-codex (direction), refine (mechanism) — split "host op done" from
"PG-PROVIDER passed," but the deeper code-grounded gap is that this path records **no
evidence at all**, so the fix must add a redacted proof record, not only change an exit code.]

**Question.** `bin/live-agent-tool-smoke.sh` exits 0 on `provider_auth_failed` /
`provider_unavailable` (`:481-490`), and deploy then prints success-adjacent copy. Should the
proof script fail closed, given that blocking all upgrades on a provider outage fights the
operator-owned upgrade model?

**Independent reasoning.** Two facts from the code decide this. First, the skip-exit-0 is a
genuine fail-open *for the "proof passed" interpretation*: deploy calls the script as a bare
statement under `set -e` (`bin/deploy.sh:5617`, `:5754`) with no capture, so a 0 exit is
indistinguishable from a real pass to anything downstream. Second — and this is what neither
the audit nor Codex foregrounds — `rg` shows the smoke script writes **no evidence/proof row
anywhere** (no `record_proof`/`evidence`/DB write in `live-agent-tool-smoke.sh`), and deploy
does not persist its result. So today the path violates the symphony twice: it conflates
"not proven" with "passed," AND it leaves no redacted evidence that PG-PROVIDER was blocked.
The symphony is explicit that provider outage is an operator-notify event, not a hard stop
("provider outage/fallback" notifications, `:986`), so Codex is right that aborting every
upgrade is wrong. The correct shape is: the host operation completes (state preserved), but
the proof gate emits a structured `blocked` result + redacted evidence, and strict mode can
make blocked abort.

**Where I differ from Codex.** Codex's three moves (structured `blocked` + non-zero by
default from the script, a deploy wrapper that continues best-effort, a
`ARCLINK_REQUIRE_LIVE_AGENT_TOOL_SMOKE=1` strict mode) are right, but flipping the *script's*
default to non-zero is risky: every existing caller (deploy 5617/5754 bare-statement, docker
3437, and any operator running it by hand) would suddenly abort on a provider outage unless
each is updated in lockstep — a wide, easy-to-miss change. I refine to keep the **script's
exit code stable (0 on blocked) but make it loudly distinguishable**, and move the
fail-closed decision to the *caller* and to a recorded *status*, which is where the symphony
puts policy ("a clear split between local dry-run proof, authorized live proof, policy
decision"). Concretely: the script emits a machine-readable `status:"blocked"` /
`gate:"PG-PROVIDER"` JSON (it already prints JSON), writes a redacted evidence record, and
exits 3 (a distinct non-zero) **only** when `ARCLINK_REQUIRE_LIVE_AGENT_TOOL_SMOKE=1`,
otherwise exits 0-but-blocked. That gives strict-mode fail-closed without breaking the
best-effort default for all current callers.

**FINAL PLAN.**
1. In `bin/live-agent-tool-smoke.sh` at the two skip branches (`:481-490`), keep the JSON
   but normalize it to `{"status":"blocked","gate":"PG-PROVIDER","reason":"provider_auth_failed"|"provider_unavailable","session_id":…}`
   (redacted: no creds, no prompt/completion). Print a clearly-blocked human line
   ("PG-PROVIDER BLOCKED — not passed; …"), not the current "skipped … ok"-adjacent copy.
2. Add a redacted evidence write (reuse the existing proof/evidence rail used by other PG-*
   gates; if the script has no DB handle, emit a JSONL line under the standard evidence dir
   and let deploy/Raven ingest it) so "PG-PROVIDER blocked at <ts>, host op continued" is a
   durable same-truth record per the symphony's "redacted evidence records for live proof"
   (`:993`).
3. Exit code: default (best-effort) stays `0` on blocked so deploy/upgrade preserves state
   and completes. Under `ARCLINK_REQUIRE_LIVE_AGENT_TOOL_SMOKE=1`, a blocked result exits
   non-zero (use a distinct code, e.g. 3) and the strict caller aborts.
4. In `bin/deploy.sh` (`:5614-5617`, `:5751-5754`) and the docker path, capture the result
   and print operator-facing copy that says "PG-PROVIDER blocked (provider outage/auth) —
   host operation completed; reauthorize/retry to prove," never "smoke passed."
5. Surface consumption: dashboards/Operator Raven read the evidence record so a chat retry
   and a browser view show the same blocked state (`:991-992`).

**SYMPHONY ANCHOR.** Notifications, Incidents, And Evidence: "A clear split between local
dry-run proof, authorized live proof, policy decision, and residual-risk acceptance" and
"Redacted evidence records for live proof … upgrade runs" (`:996-997`, `:993`); reinforced by
"provider outage/fallback" being an operator *notification*, not a deploy abort (`:986`).

**EFFORT:** med. **BLAST-RADIUS:** `live-agent-tool-smoke.sh` skip branches + one evidence
write; `deploy.sh` x2 call sites + docker call site copy; one deploy-regression test for the
blocked-status shape; dashboard/Raven evidence consumer. No schema change required if the
existing evidence rail is reused.

---

## DECISION 3 — Full ruff/pyflakes style enforcement

[VERDICT: agree-codex — source-owned lint policy + baseline/ratchet to zero, Ruff as the
single engine; refine only the now-known numbers and the pyflakes dedup, which the live
backlog makes concrete and small.]

**Question.** Should CANON-28 flip on full repo-wide ruff/pyflakes as one blocking switch, or
adopt a policy/ratchet? (Audit framed this as "no lint gate"; code now has a *fatal* lint
gate but no *style* gate.)

**Independent reasoning.** I measured the backlog so this isn't guesswork: full default-rule
`ruff check bin python tests plugins hooks` = **63 errors** (32 auto-fixable); `--select F`
(pyflakes parity) = **43 errors** (32 auto-fixable). That is small — a one-sitting cleanup,
not a campaign — which means a hard flip is *feasible* but the *ratchet* is still the right
operator-owned move because (a) it makes lint policy explicit and versioned instead of an
inline `--select` string buried in YAML, (b) it prevents new debt the moment it lands, and
(c) it lets the operator schedule the ~63-item cleanup without blocking an urgent security
upgrade on unrelated cross-piece warnings. `requirements-dev.txt:12-13` pins **both**
`pyflakes` and `ruff`; Ruff's `F` rules already cover Pyflakes, so keeping both as required
deps is redundant. No `ruff.toml`/`pyproject.toml` exists yet, so the rule set lives only as
a CLI `--select` literal — the policy has no source home.

**Where I differ from Codex.** None materially — I agree with the ratchet, source-owned
config, Ruff-as-single-engine, and drop-pyflakes-after-parity. I only make it more concrete
and slightly faster given the small measured backlog: because 32 of 63 are auto-fixable and
the total is 63, I recommend the operator land the config + auto-fix in the same change and
ratchet only the ~31 residual manual items, rather than baselining all 63. This reaches an
empty baseline far sooner than a pure long-lived baseline, honoring the symphony's
"validated before deployment" intent without a permanent debt ledger.

**FINAL PLAN.**
1. Add `ruff.toml` (or `[tool.ruff]` in a new `pyproject.toml`) defining the enforced rule
   set: keep the existing fatal `E9,F63,F7,F82` as always-blocking, plus the broader `E`,`F`,
   and a curated import/style subset. This gives lint policy a source owner.
2. Run `ruff check --fix` once to clear the 32 auto-fixable items; review/commit. Manually
   resolve the ~31 residual where cheap.
3. For anything genuinely cross-piece/deferred, add a small `ruff` baseline (per-file
   `# noqa` with a tracked reason, or a baseline wrapper) — but target an **empty** baseline,
   and have the CI step print remaining counts so debt is visible.
4. Keep the CI lint step as the single enforced engine = Ruff. After confirming `F`-rule
   parity, **remove `pyflakes` from `requirements-dev.txt:12`** (or demote it to a documented
   optional cross-check) so there is one lint truth.
5. Keep `bin/ci-preflight.sh` `py_compile` (`:197-203`) as the local fast syntax check; align
   `docs/arclink/local-validation.md` to name Ruff as the lint engine so local/CI/docs agree.
6. Once the baseline is empty, the ratchet *is* strict full enforcement — no second flip
   needed.

**SYMPHONY ANCHOR.** Supply Chain, Build, And Release Integrity: "Container images, Python
dependencies, Node dependencies, shell scripts, and generated configs built from known
source and validated before deployment." (`:1244-1245`). A source-owned `ruff.toml` + ratchet
makes Python validation an explicit, known-source, fail-closed release-integrity gate.

**EFFORT:** med now (config + one auto-fix sweep over a small 63-item backlog), low to hold
zero thereafter. **BLAST-RADIUS:** CI lint step, `ruff.toml`, `requirements-dev.txt` (drop
pyflakes), `local-validation.md`, and a ~63-item one-time style cleanup across
`bin/python/tests/plugins/hooks`. No runtime behavior change.

---

## STANDING DISAGREEMENTS

None that block. One genuine **operator product choice** within Decision 3 (not a
model-vs-model disagreement): whether to (3a) land the full ~63-item ruff cleanup + drop
pyflakes in **one change now** (feasible given the small backlog, reaches strict enforcement
immediately) versus (3b) ship the `ruff.toml` + ratchet now and burn the residual ~31 manual
items down over the next maintenance cycle. Both honor the symphony; 3a is more decisive, 3b
is lower immediate blast-radius. Recommended default: 3a for the 32 auto-fixable + config in
this change, ratchet the residual — i.e. the convergence already written into the Decision 3
plan. The operator may elect pure-now (3a) if they want strict enforcement in a single PR.
