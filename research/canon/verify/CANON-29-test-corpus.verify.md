# CANON-29 Test Corpus — Adversarial Verification

Verifier: independent adversarial skeptic. Method: re-opened every load-bearing
file, re-ran the suite, and built independent AST + call-graph + runtime-injection
analyses rather than trusting the record's citations.

## HEADLINE VERDICT
The record is **mostly trustworthy on the easy claims (secrets, gating, golden
fixture, CI runner) but materially WRONG on its two most adversarial claims**:
1. Its central "exactly 3 orphaned tests" claim (and adversarial self-check #1
   "I confirmed exactly 3") is **REFUTED — there are 10 orphaned tests across 6
   files**, proven three independent ways (AST, call-graph reachability, runtime
   raise-injection).
2. Its TOUCH POINTS / OUTPUT CONTRACT claim "Sockets/ports/subprocess: none in
   CI mode" and "No mutation of the real repo … in CI mode" is **REFUTED** — 44+
   non-live test files call `subprocess.run`, and at least two files
   (`test_arclink_executor.py`, `test_deploy_regressions.py`) FAIL on a
   read-only filesystem because they write to hardcoded host paths
   (`/arcdata/...`) and shell out to real binaries (`systemd-analyze verify`).

The orphan undercount understates the HIGH-severity CI-wiring gap by >3x and was
self-certified as "confirmed exactly 3" — that is the worst kind of error in an
adversarial-self-check section.

---

## REFUTATIONS / CONFIRMATIONS (with citations)

### REFUTED — "exactly 3 orphaned tests" (RISK HIGH + self-check #1 + OPEN #2)
Record (RISKS, line ~80; self-check #1, line ~66; verdict, line ~90) claims
exactly 3 orphans: fleet ×2 + hosted_api ×1. **There are 10.**

Independent proofs (all three agree):
- AST orphan scan (defined module-level `test_*` minus any `Name`/`Attribute`
  reference anywhere in module) → 10.
- Call-graph reachability from `__main__`/`main()` (BFS over actual call edges)
  → 10 unreachable.
- Runtime injection: I inserted `raise RuntimeError('ORPHAN_EXECUTED')` at the
  top of each of the 10 bodies and ran each file as `python3 <file>` (the exact
  CI command). For every one the body never executed (`orphan_body_ran=False`);
  4 files still exited 0 GREEN with the orphan poisoned.

The 7 orphans the record MISSED:
- `tests/test_arclink_chutes_and_adapters.py:527`
  `test_chutes_boundary_operator_observe_only_unlimited_is_metered_but_never_blocked`
  (25 defined, 24 reachable).
- `tests/test_arclink_docker.py:4854`
  `test_agent_process_helper_records_redacted_rejection_incident_before_subprocess`
  and `tests/test_arclink_docker.py:2953`
  `test_operator_upgrade_broker_rejects_symlinked_or_non_executable_repo_scripts_before_subprocess`
  (72 defined, 70 in the `main()` registry at :7947-8022; the name at :2287 is
  an in-`json.dumps` anchor string, NOT a call).
- `tests/test_arclink_executor.py:1550`
  `test_ssh_docker_runner_read_without_allowed_root_raises_on_failure` and
  `tests/test_arclink_executor.py:1586`
  `test_ssh_docker_runner_write_text_file_shell_quotes_remote_command`.
- `tests/test_deploy_regressions.py:3182`
  `test_notion_ssot_setup_prompt_points_operator_at_shared_home_page` and
  `tests/test_deploy_regressions.py:3255`
  `test_notion_ssot_setup_uses_current_checkout_ctl_for_handshake`.

The 3 it DID catch are confirmed:
- `tests/test_arclink_fleet.py:165`/`:192` (26 defined, `__main__` :598-623
  calls 24, prints `"All 24 fleet tests passed."` :623).
- `tests/test_arclink_hosted_api.py:2246`
  `test_user_share_grant_broker_requires_deployment_scoped_token`
  (100 defined, not in `main()` :6292).

Two of the missed orphans are security-relevant boundary tests
(`agent_process_helper records redacted rejection incident BEFORE subprocess`;
`operator_upgrade_broker rejects symlinked/non-exec repo scripts BEFORE
subprocess`) — i.e. GAP-019 broker fail-closed proofs that NEVER run in CI.

### REFUTED — "Sockets/ports/subprocess: none in CI mode" (TOUCH POINTS) and "No mutation of the real repo, no network in CI mode" (OUTPUT CONTRACT)
- 44 non-`e2e_live` test files import and call `subprocess.run/check_call`.
- `tests/test_deploy_regressions.py:41` is a `subprocess.run` helper; :2941,
  :2964, :3024, :3070 run `/bin/bash <real repo script>`; the prereq script
  path reaches `systemd-analyze verify`, which on this host raised
  `AssertionError: systemd-analyze verify failed: Failed to initialize path
  lookup table: Read-only file system` — the file exits 1 unpatched.
- `tests/test_arclink_executor.py` hardcodes host paths
  `"/arcdata/deployments/dep_1"` (:41, :48, :57, :214, :234-235, :246, :783-785)
  and a code path tries `mkdir` under `/arcdata` → unpatched run raises
  `OSError: [Errno 30] Read-only file system: '/arcdata/deployments/dep_1'`,
  exit 1.
These are real mutation/subprocess/network-adjacent behaviors the record
explicitly denied. NOTE: both failures are environment-specific (read-only
sandbox), so they may be GREEN on the CI runner — but the record's categorical
"none in CI mode" / "no mutation" is false as written, and these two files are
fragile to the host environment in a way the record did not surface.

### PARTIALLY REFUTED — MEDIUM risk "arclink_rejection_incidents may never be CALLED in any test"
Record (RISKS MEDIUM, ~line 82; self-check #3, ~line 68) says rejection_incidents
is touched "only by SOURCE-STRING assertions" and its functions "may never be
CALLED." **Refuted:** `tests/test_arclink_notification_delivery.py:1614`
`test_gateway_exec_broker_records_redacted_rejection_incident_before_subprocess`
(executed at :2355) drives `arclink_gateway_exec_broker`, which imports
`record_rejection_incident` (`python/arclink_gateway_exec_broker.py:27`), and
asserts the on-disk `rejections.jsonl` content (:1665, :1768). So
`record_rejection_incident` IS behaviorally exercised. The record both
overstated this risk AND missed the notification_delivery test entirely (plus the
two docker rejection-incident orphans). `arclink_upgrade_policy` IS exercised
through `arclink_operator_raven` dispatch
(`tests/test_arclink_operator_raven.py:288` calls `/upgrade_policy hermes` and
asserts `policy.component == "hermes"`); the "no dedicated file" part is fair,
but "indirect only" is correct only for upgrade_policy, not rejection_incidents.

### CONFIRMED — CI runner is direct `python3` per file, never pytest
`.github/workflows/install-smoke.yml:32-41` (nullglob, `exit 1` on empty, `for …
python3 "$test_file"`, `set -euo pipefail` :31, Python 3.11 :23,
`requirements-dev.txt` :26). No `pytest` invocation anywhere in `.github/`,
`bin/`, or `test.sh` (only `.pytest_cache` exclusions in
`bin/install-arclink-plugins.sh`). `pytest.ini` exists (testpaths=tests) but is
dead config. DRIFT #1 confirmed.

### CONFIRMED — `ARCLINK_E2E_LIVE` never set in CI; live tests skip cleanly
`grep -rn ARCLINK_E2E_LIVE .github/` → NONE. `python3 tests/test_arclink_e2e_live.py`
with no env → `Ran 2 tests … OK (skipped=6)`. Gate at :32, `setUpClass`
SkipTest :63-64, non-`sk_test_` refusal :87-88, Cloudflare `per_page=1`
read-only :144, `assertNotIn("sk_live_", j)` :259-260. Self-check #4 confirmed.

### CONFIRMED — no-live-secret convention holds
All "secret-shaped" literals are synthetic: `sk_live_EXTREMELY_SECRET_123`
(`test_arclink_diagnostics.py:54`), `sk_live_extremely_secret_value_12345`
(`test_arclink_host_readiness.py:116`), `-----BEGIN PRIVATE KEY-----\nabc123`
(`test_arclink_secrets_regex.py:32`), `sk_live_plaintext`
(`test_arclink_provisioning.py:485`), `sk-ant-abcdefghijklmnopqrstuvwxyz`
(`test_arclink_wrapped.py:199`), `AKIAABCDEFGHIJKLMNOP`
(`test_arclink_provisioning.py:553`). No real-entropy secret found. Confirmed.

### CONFIRMED — golden ingress contract, e2e_fake trace, meta-tests
`tests/test_arclink_ingress.py:70-76` renders
`render_traefik_dynamic_labels(prefix="amber-vault-1a2b", base_domain="example.test")`,
deep-equals `tests/fixtures/arclink_traefik_labels.golden.json`, asserts
key-set `{dashboard, hermes}`. e2e_fake trace citations accurate within ±2 lines
(`_setup` is :34 not :32; `whsec_test` :38 not :36 — trivial). e2e_fake runs
GREEN ("All fake E2E tests passed."). Meta-tests confirmed:
`test_documentation_truths.py:9` (PRODUCT_MATRIX), :76 (totals test);
`test_public_repo_hygiene.py:44,46` (env config). COVERAGE_MATRIX J-19 cites
`tests/test_arclink_hosted_api.py -k share_grant_broker` (line 36, requires
pytest) and line 56 names `python3 -m pytest -q tests` as the broad gate —
DRIFT #2 confirmed. `web/package.json:10` runs `node --test`;
`web/tests/test_api_client.mjs:3-5` "Replicates the api module logic" — DRIFT #6
confirmed.

### CONFIRMED — counts
`git ls-files 'tests/test_*.py'` = 128 (record correct vs the brief's "129").
130 total tracked under `tests/` (128 tests + helper + golden fixture).
128/128 files have `if __name__ == "__main__"`.

---

## NEW GAPS BOTH MISSED
1. **HIGH — 7 additional orphaned regression tests beyond the record's 3** (full
   list above), TWO of which are GAP-019 broker fail-closed boundary proofs
   (`docker.py:2953`, `docker.py:4854`) that never run in CI. This roughly
   quadruples the record's headline HIGH risk and was actively mis-certified by
   its self-check.
2. **MEDIUM — `test_arclink_executor.py` and `test_deploy_regressions.py` are
   not hermetic.** They write to hardcoded host paths (`/arcdata/...`) and shell
   out to real binaries (`systemd-analyze verify`, `/bin/bash <repo script>`,
   `git`). On a read-only / minimal host they FAIL with environment errors, not
   logic errors — directly contradicting the record's "tests write only to
   `:memory:`/`tempfile`" and "subprocess: none in CI mode." This is a real CI
   portability/fragility gap.
3. **LOW — record's runtime-PASS-count heuristic is unsound.** PASS-line counts
   do not map 1:1 to module-level test functions (chutes/hosted_api show 0 by
   PASS-diff yet have real orphans), which is likely how the record's manual
   "verified exactly 3" undercounted. The defended count needs AST, not grep.

## SEAM MISMATCHES
- The record's CROSS-PIECE #1 (Tests ↔ CANON-01 schema) is honestly marked
  "partial / runtime-asserted only"; the helper INSERT column list
  (`arclink_test_helpers.py:74-93`) is verified on the consumer side, but
  `ensure_schema`'s DDL was not diffed by the record OR by me here (out of scope
  — it is CANON-01). Leaving as an unverified-both-ends seam, correctly flagged.
- CROSS-PIECE #5 (Tests ↔ CI) is "both-ends verified" and HOLDS for the run
  mechanism, but the contract it implies ("every `test_*` runs") is violated by
  the 10 orphans — the seam is mechanically sound but its coverage promise is
  not. The record under-counted the breach.

## RESIDUAL DISAGREEMENTS
- Record verdict "only `arclink_rejection_incidents` and `arclink_upgrade_policy`
  lack dedicated/behavioral coverage" — rejection_incidents DOES have behavioral
  coverage via the gateway-exec-broker test; the claim should be narrowed to
  "lack a DEDICATED test FILE," not "lack behavioral coverage."
- Record severity calibration: the orphan risk is correctly HIGH, but the
  magnitude (3) is understated; with 10 (incl. 2 security-broker proofs) it is
  arguably the dominant risk of the piece.

## TRUSTWORTHINESS
Use the record for: secrets convention, live-gate fail-safe, golden fixture,
CI-is-not-pytest, module-reach overview — all independently re-confirmed. Do
NOT trust its orphan count, its "exactly 3" self-certification, its
"no subprocess / no mutation in CI mode" claim, or its rejection_incidents
risk wording. Net: directionally correct, but its two most adversarial
conclusions are wrong and were over-confidently self-certified.
