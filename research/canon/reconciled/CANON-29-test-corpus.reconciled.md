# CANON-29 — Test Corpus — RECONCILED (both-model-signed)

- **Piece:** CANON-29 (the `tests/**` tree: 128 tracked `tests/test_*.py`, 1 helper, 1 golden fixture)
- **Codex (GPT-5.5 xhigh) sign-off:** OBJECT(5) — "Core verifier direction is right, but the canonical record needs refinements: 10 Python orphans confirmed, the Playwright CI seam is false, and the executor read-only failure claim is not proven from code."
- **Adjudicator:** Claude Opus 4.8 (1M), final reconciliation. Method: every disputed point re-opened against live code (Read / rg / sed) and, where the dispute was about runtime behavior, re-RUN on this host. Code wins over comment/name/prior claim.
- **Federation sign-off:** AGREED-WITH-STANDING-DISAGREEMENTS — every material point reconciled to one code-grounded truth; one residual is an environment-conditional (host-dependent) fact that cannot be settled as a single binary from code alone (read-only-FS failures are real here but may be GREEN on GitHub's runner). It is enumerated below, not averaged away.

---

## RESOLUTION TABLE (point | winner | deciding cite)

| # | Disputed point | Winner | Deciding cite (re-opened by adjudicator) |
|---|---|---|---|
| 1 | Orphan count: record says "exactly 3", verifier+Codex say 10 | **codex/verifier** | Independent AST scan = 10 across 6 files (chutes `:527`; docker `:2953`,`:4854`; executor `:1550`,`:1586`; fleet `:165`,`:192`; hosted_api `:2246`; deploy_regressions `:3182`,`:3255`). Registries omit them: chutes `main()` `:763-786`, docker `main()` `:7947-8018` (count of the two names in block = 0), executor `main()` `:2135-2185`, fleet `__main__` `:598-623`, hosted_api `main()` `:6292-6392`. docker `:2287` ref is an in-`json.dumps` anchor string, not a call (re-read `:2283-2290`). |
| 2 | docker orphan name appears at `:2287` → is it a call? | **codex/verifier** | `:2285-2289`: `"...before_subprocess" in json.dumps(bb_controls.get("test_anchors") or [])` — string membership, not invocation. AST (Name/Attribute only) excludes it. |
| 3 | Web seam: record CROSS-PIECE #6 says browser run via `npx playwright test` in `web-regressions` CI job | **codex** | `install-smoke.yml:62-67` runs only `npm run lint`/`npm test`/`npm run build`. `web/package.json:10` `test` = `node --test tests/test_page_smoke.mjs tests/test_api_client.mjs`; `:11` `test:browser` = `npx playwright test` — **never invoked by CI**. Record's Playwright-in-CI claim is FALSE; seam must be downgraded. |
| 4 | Executor non-hermetic: verifier says FAILS on read-only FS writing `/arcdata`; Codex says not proven from code (FakeDockerRunner skips materialization) | **both** | Ran `python3 tests/test_arclink_executor.py` → `OSError: [Errno 30] Read-only file system: '/arcdata/deployments/dep_1'` at `arclink_executor.py:2189` (`_ensure_volume_roots` → `source_path.mkdir`). Triggering test = `test_live_docker_compose_file_preserves_service_ports` (`:1347`) which injects a **non-Fake `RecordingRunner`** (`:1343-1346`, `live_enabled=True`). Codex is right that `arclink_executor.py:908-909` only materializes when `not isinstance(runner, FakeDockerRunner)` — so the Fake path is safe — but the failure comes through the **non-Fake** path, so the verifier's empirical failure stands. The file IS non-hermetic via absolute `/arcdata` volume sources in `sample_intent()` (`tests/test_arclink_executor.py:41,48`) that bypass the `tmpdir` state-root base. |
| 5 | deploy_regressions non-hermetic / subprocess | **codex/verifier** | Ran `python3 tests/test_deploy_regressions.py` → `AssertionError: systemd-analyze verify failed: ... Read-only file system` at `:4120` (`test_install_system_services_units_pass_systemd_analyze_verify`). Real shell-outs: `:40-41` `subprocess.run` helper; `:2941-2948` `/bin/bash <bin/lib/ensure-prereqs.sh>`. Record's "subprocess: none in CI mode" / "no mutation" is REFUTED. |
| 6 | rejection_incidents: record "may never be CALLED" | **codex/verifier** | `arclink_gateway_exec_broker.py:27` imports `record_rejection_incident`, calls it `:151-153` (invoked `:292`). Test `test_gateway_exec_broker_records_redacted_rejection_incident_before_subprocess` defined `tests/test_arclink_notification_delivery.py:1614`, **wired into runner at `:2355`** (real call), asserts on-disk `rejections.jsonl` redaction (`:1665`). Behaviorally exercised. Record wording REFUTED. |
| 7 | upgrade_policy: dedicated coverage? | **claude (record)** | No `tests/test_*upgrade_policy*` file exists. Exercised transitively only via Raven `/upgrade_policy` dispatch (`tests/test_arclink_operator_raven.py:288-316`, asserts `policy.component == "hermes"` `:308`). Record correct for upgrade_policy. |
| 8 | Helper INSERT vs DDL columns (record left "partial / runtime-only") | **codex (resolves seam)** | Helper INSERT cols (`arclink_test_helpers.py:74-93`) all present in DDL `arclink_control.py:1309-1332`; omitted cols (`agent_name`,`agent_title`,`checkout_session_id`,`checkout_url`,`stripe_customer_id`,`completed_at`,`expires_at`) are all `NOT NULL DEFAULT ''`, so the partial INSERT is valid. Seam now both-ends verified, not just runtime-asserted. |
| 9 | CI is direct `python3` per file, not pytest (DRIFT #1) | **both (ratify)** | `install-smoke.yml:31-40` `for test_file in tests/test_*.py: python3 "$test_file"`; `pytest.ini` unused. |
| 10 | Doc anchor J-19 `-k share_grant_broker` unenforced (HIGH) | **both (ratify)** | `COVERAGE_MATRIX.md:36` needs `-k` (pytest); CI never passes it; target `:2246` absent from `main()` `:6292-6392`. |
| 11 | Live E2E fail-safe skip; no-live-secrets; golden ingress | **both (ratify)** | `python3 tests/test_arclink_e2e_live.py` → `OK (skipped=6)`; gate `:32,63-64`, non-`sk_test_` refusal `:87-88`, `assertNotIn("sk_live_") :259-260`. Golden deep-equal `tests/test_arclink_ingress.py:70-75` keyed `{dashboard,hermes}`. Secret literals all synthetic. |
| 12 | Counts: 128 tracked tests / 130 artifacts; brief's "129" off-by-one | **both (ratify)** | `git ls-files 'tests/test_*.py'` = 128; `git ls-files tests/` = 130. |
| 13 | Structural hand-list runner fragility (MEDIUM) | **both (ratify)** | Confirmed mechanism behind all 10 orphans; runners hand-enumerate (`test_arclink_e2e_fake.py:371-378`, etc.). |

---

## CODEX NEW FINDINGS — CONFIRMED vs REJECTED

### CONFIRMED (net-new federation risks)
- **MEDIUM — Playwright browser product-checks present but NOT CI-run, while the record's seam claims Playwright runs in CI.** `web/tests/browser/product-checks.spec.ts` exists; CI (`install-smoke.yml:62-67`) runs only `node --test` via `npm test` (`web/package.json:10`); `npx playwright test` lives in `test:browser` (`:11`) and is never invoked. Re-verified by adjudicator. (Boundary-owned by CANON-03/CANON-28, but the CANON-29 seam claim is wrong and is corrected here.)
- **LOW — Non-live tests bind/connect loopback sockets, so "Sockets/ports: none in CI mode" is false beyond subprocess.** `tests/test_arclink_agent_access.py:314-318` (`socket.bind(("127.0.0.1",0))`); `tests/test_arclink_dashboard_auth_proxy.py:204` (`ThreadingHTTPServer(("127.0.0.1",0),...)` + `HTTPConnection` `:173,192`); `tests/test_arclink_notion_webhook.py:206` (`webhook.Server(("127.0.0.1",0),...)` + request `:212`). Re-verified.
- **LOW — Stale hardcoded success-summary counts mask runner drift beyond fleet.** Independent count: chutes defines 25 / runner calls 24 / prints "all 24" (`:788`); docker defines 72 / calls 70 / prints "all 61" (`:8018`); executor defines 51 / calls 49 / prints "all 41" (`:2185`); fleet defines 26 / calls 24 / prints "All 24" (`:623`). The "61" and "41" literals are divorced from both defined and called counts. Re-verified via AST runner-call count.

### REJECTED
- **Codex's caveat that the executor read-only failure "is not proven from code" — REJECTED as a blocker, ACCEPTED as a refinement.** The FakeDockerRunner-skips-materialization fact (`arclink_executor.py:908-909`) is true, but it does not cover the failing test, which uses a non-Fake runner. The host-write failure IS proven (ran it; `OSError` at `:2189`). Recorded as winner=both in row 4 rather than a standing rejection: Codex's mechanism is correct, its conclusion ("not proven") is not.

---

## SEVERITY CHANGES (only where code supports it)

| Risk | From | To | Cite |
|---|---|---|---|
| Orphaned regression tests excluded from CI | HIGH (3 orphans) | **HIGH (10 orphans, 6 files; 3 are GAP-019 / boundary fail-closed proofs: docker `:2953`,`:4854`, hosted_api `:2246`)** | AST=10 + registries `:7947-8018`/`:6292-6392`/`:763-786`/`:2135-2185`/`:598-623`; the magnitude (not the level) changes — orphan count tripled. |
| `arclink_rejection_incidents` lacks behavioral coverage | MEDIUM | **MEDIUM → reworded (no longer "may never be CALLED"): behaviorally covered; only lacks a DEDICATED test file** | `arclink_gateway_exec_broker.py:27,151-153,292` + `tests/test_arclink_notification_delivery.py:1614,2355`. |
| Tests are subprocess/network-free, write only to `:memory:`/tempfile | (asserted clean) | **MEDIUM (false): non-hermetic — real subprocess + host writes** | `test_deploy_regressions.py:41,2941-2948,4120`; `test_arclink_executor.py:41,48` → `arclink_executor.py:2189` `OSError`. |
| Web browser seam runs Playwright in CI | (asserted run) | **MEDIUM (false): Playwright not CI-run** | `install-smoke.yml:62-67`, `web/package.json:10-11`. |

No other severity levels change. HIGH doc-anchor (J-19) and LOW pytest.ini/dead-config remain as the record had them.

---

## STANDING DISAGREEMENTS (cannot be settled from code alone)

1. **Whether `test_deploy_regressions.py` / `test_arclink_executor.py` are RED in real CI.**
   - Claude-verifier view: they FAIL (proven on this read-only host: `systemd-analyze verify ... Read-only file system` `:4120`; `OSError: Read-only file system '/arcdata/...'` `arclink_executor.py:2189`).
   - Codex view: these are environment-specific; on GitHub's `ubuntu-22.04` runner (writable `/`, full `systemd`) they likely PASS, so this is a portability/fragility gap, not necessarily a CI-red.
   - Why unresolved: the failures are real and reproduced here, but whether they reproduce on the CI host depends on that host's filesystem/`systemd` state, which is not in this repo's code. **Reconciled stance (both models accept):** the files ARE non-hermetic (proven from code: absolute `/arcdata` sources, real `subprocess` to repo scripts + `systemd-analyze`), and that non-hermeticity is the federation finding — the precise CI pass/fail is host-conditional and left as a flagged fragility, not asserted as a CI failure.

---

## FINAL BOTH-MODEL VERDICT

The piece provably does its core job: a broad, no-live-secret, in-memory regression corpus of 128 runnable files that load the REAL `python/arclink_*` modules against `ensure_schema`-built SQLite, cleanly separating fakes from credential-gated live checks (fail-safe skip verified, `OK (skipped=6)`), executed by CI as direct `python3 <file>` per file (`install-smoke.yml:38-40`). The no-live-secrets convention HOLDS; the golden ingress contract, Stripe-`whsec_test` seam, and helper-INSERT-vs-DDL seam are all both-ends verified.

Reconciled real weaknesses, code-grounded and signed by both models:
1. **HIGH — 10 orphaned regression tests across 6 files** are defined but never reached from their file's `__main__`/`main()`, so CI never runs them; 3 are security-boundary / GAP-019 fail-closed proofs (`docker:2953`, `docker:4854`, `hosted_api:2246`). The record's "exactly 3" self-certification was wrong by >3x.
2. **HIGH — `COVERAGE_MATRIX.md` J-19 `-k share_grant_broker`** is an unenforced paper proof (needs pytest; target is itself an orphan).
3. **MEDIUM — Non-hermetic tests:** `test_deploy_regressions.py` shells real repo scripts + `systemd-analyze verify`, and `test_arclink_executor.py` writes to hardcoded `/arcdata` host paths via a non-Fake runner; the record's "subprocess: none / no mutation in CI mode" is false. (CI pass/fail is host-conditional — see standing disagreement.)
4. **MEDIUM — Web seam corrected:** Playwright browser checks exist but are NOT CI-run; only the two `node --test` `.mjs` tests run.
5. **MEDIUM — `arclink_upgrade_policy`** has no dedicated test file (transitive-only via Raven); **`arclink_rejection_incidents`** IS behaviorally covered (gateway-broker test) and only lacks a dedicated file — the record's "may never be CALLED" was wrong.
6. **LOW — Non-live tests bind loopback sockets** (3 files) and **printed success-summary counts are stale hardcoded literals** (docker "61", executor "41") divorced from actual defined/called counts.

Net: the suite is strong and honest about secrets and live-gating, but its CI wiring has a larger-than-stated load-bearing gap (10 orphans, incl. boundary proofs), is non-hermetic in two files, and the record over-claimed both the orphan count and the Playwright/no-subprocess seams. Federation sign-off: **AGREED-WITH-STANDING-DISAGREEMENTS** (single host-conditional residual).

---

<!-- CANON-REPAIR-STATUS:START -->
## Repair status

> Refreshed from [`research/canon/fixes/CANON-29-test-corpus.fix.md`](../fixes/CANON-29-test-corpus.fix.md) (tracked). The audit findings above remain the adjudicated spec; this block records the repair campaign state for this piece.

- Status: `bf7e201` committed.
- Summary: 7 fixed / 4 skipped / 1 needs-decision.
- Tests: 9 files run, all pass; AST direct-runner scan reports 0 missing; git diff --check pass
- Representative fixes:
  - HIGH — wired the remaining current-tree orphan tests into direct runners — tests/test_arclink_chutes_and_adapters.py:783; tests/test_arclink_docker.py:8240,8254; tests/test_arclink_fleet.py:606,607; tests/test_arclink_hosted_api.py:6496; tests/test_deploy_regressions.py:4544,4545.
  - HIGH — made the J-19 share-grant broker proof run under the real `python3 tests/test_*.py` CI contract — tests/test_arclink_hosted_api.py:6496.
  - MEDIUM — added a corpus guard that fails when module-level `test_*` functions are not wired into direct runners — tests/test_documentation_truths.py:342.
- Needs decision:
  - Literal dedicated new `tests/test_arclink_upgrade_policy.py` / `tests/test_arclink_rejection_incidents.py` files could not be created because the `tests/` directory is not writable in this workspace. I added direct behavioral coverage inside existing runnable files instead.
<!-- CANON-REPAIR-STATUS:END -->
