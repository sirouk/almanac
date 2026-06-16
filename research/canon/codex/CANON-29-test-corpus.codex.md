<<<CODEX-VERDICT-START CANON-29>>>
## CANON-29 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(5)
ONE-LINE VERDICT: Core verifier direction is right, but the canonical record needs refinements: 10 Python orphans are confirmed, the Playwright CI seam is false, and the executor read-only failure claim is not proven from code.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM — CI runs `tests/test_*.py` directly with `python3`, not pytest: `.github/workflows/install-smoke.yml:31-40`; `pytest.ini:1-8` is not consumed by that code path.
- CONFIRM/REFINE — HIGH orphan risk is 10, not 3. Orphan definitions: `tests/test_arclink_chutes_and_adapters.py:527`, `tests/test_arclink_docker.py:2953,4854`, `tests/test_arclink_executor.py:1550,1586`, `tests/test_arclink_fleet.py:165,192`, `tests/test_arclink_hosted_api.py:2246`, `tests/test_deploy_regressions.py:3182,3255`; direct runners omit them at `tests/test_arclink_chutes_and_adapters.py:763-788`, `tests/test_arclink_docker.py:7947-8018`, `tests/test_arclink_executor.py:2135-2185`, `tests/test_arclink_fleet.py:598-623`, `tests/test_arclink_hosted_api.py:6292-6392`, `tests/test_deploy_regressions.py:4444-4565`.
- CONFIRM — HIGH doc proof anchor is unenforced: `research/COVERAGE_MATRIX.md:36` names `test_arclink_hosted_api.py -k share_grant_broker`, but CI never passes `-k` and the target function is absent from `main()`: `.github/workflows/install-smoke.yml:38-40`, `tests/test_arclink_hosted_api.py:2246`, `tests/test_arclink_hosted_api.py:6292-6392`.
- REFINE — MEDIUM non-hermetic/subprocess risk: record’s “no subprocess/sockets” claim is false; `test_deploy_regressions.py` shells real scripts and `systemd-analyze verify`: `tests/test_deploy_regressions.py:40-41`, `tests/test_deploy_regressions.py:2941-2948`, `tests/test_deploy_regressions.py:4064-4120`. I do not ratify the executor half as a proven host-write failure: `/arcdata` is hardcoded in sample intent, but FakeDockerRunner paths skip file materialization: `tests/test_arclink_executor.py:38-48`, `python/arclink_executor.py:908-917`.
- REFINE — MEDIUM coverage risk: `arclink_rejection_incidents` is behaviorally exercised, not just string-asserted. Gateway broker imports and calls it: `python/arclink_gateway_exec_broker.py:27`, `python/arclink_gateway_exec_broker.py:151-154`, `python/arclink_gateway_exec_broker.py:287-293`; the test is wired into main: `tests/test_arclink_notification_delivery.py:1614-1768`, `tests/test_arclink_notification_delivery.py:2355`. `arclink_upgrade_policy` remains only transitively exercised via Raven: `tests/test_arclink_operator_raven.py:288-316`.
- CONFIRM — Structural hand-listed runner fragility is real and already manifested: examples at `tests/test_arclink_e2e_fake.py:371-378`, `tests/test_deploy_regressions.py:4444-4565`, with CI relying on those exit paths at `.github/workflows/install-smoke.yml:38-40`.
- CONFIRM/REFINE — CANON-29 §B46: AST enumeration found no hidden orphans beyond the 10 above; helper INSERT columns are present/default-covered in the DDL: `tests/arclink_test_helpers.py:74-80` vs `python/arclink_control.py:1309-1331`; live E2E gate is fail-safe under the sole workflow path: `tests/test_arclink_e2e_live.py:32,63-64`, `.github/workflows/install-smoke.yml:28-40`.
- REFUTE/REFINE — CANON-29 web seam overclaims Playwright CI. CI runs `npm run lint`, `npm test`, `npm run build` only: `.github/workflows/install-smoke.yml:62-67`; `npm test` is only the two `.mjs` node tests: `web/package.json:10`; Playwright exists as a separate script, not invoked there: `web/package.json:11`, `web/playwright.config.ts:4`.

### New findings both Claude passes missed (severity + path:line)
- MEDIUM — Browser Playwright product checks are present but not CI-run, despite the CANON-29 seam saying “playwright”: `.github/workflows/install-smoke.yml:62-67`, `web/package.json:10-11`, `web/tests/browser/product-checks.spec.ts:1-11`.
- LOW — Non-live tests do bind/connect loopback sockets, so the “sockets/ports: none” claim is false beyond subprocess: `tests/test_arclink_agent_access.py:314-320`, `tests/test_arclink_dashboard_auth_proxy.py:173-217`, `tests/test_arclink_notion_webhook.py:206-220`.
- LOW — Stale success summaries mask runner drift beyond the fleet file: Chutes prints 24 with 25 defined and one orphan, Docker prints 61 while omitting two definitions, Executor prints 41 while omitting two definitions: `tests/test_arclink_chutes_and_adapters.py:527,788`, `tests/test_arclink_docker.py:2953,4854,8018`, `tests/test_arclink_executor.py:1550,1586,2185`.

### Claude citations re-confirmed or corrected
- Reconfirmed: 128 tracked Python test files and 130 tracked `tests/` artifacts; helper loads real modules and builds `:memory:` DBs: `tests/arclink_test_helpers.py:19-35`.
- Reconfirmed: fake E2E calls real hosted route and signs Stripe with `whsec_test`: `tests/test_arclink_e2e_fake.py:44-52`, `tests/arclink_test_helpers.py:109-111`.
- Reconfirmed: live E2E skips without `ARCLINK_E2E_LIVE` and refuses non-test Stripe keys: `tests/test_arclink_e2e_live.py:32,63-64,87-88,259-260`.
- Reconfirmed: ingress golden deep-equal is real: `tests/test_arclink_ingress.py:70-75`, `tests/fixtures/arclink_traefik_labels.golden.json:1-16`.
- Corrected: rejection-incidents coverage exists behaviorally; original record’s “may never be CALLED” wording is false: `tests/test_arclink_notification_delivery.py:1614-1768`.

### Residual disagreement with the Claude half (for final reconciliation)
- The consolidated MEDIUM should say `test_deploy_regressions.py` is non-hermetic; `test_arclink_executor.py` has hardcoded `/arcdata` contracts, but I did not prove a main-run host write from code because FakeDockerRunner skips local materialization: `python/arclink_executor.py:908-917`.
- The CANON-29 ↔ CANON-03 seam must be downgraded: node `.mjs` tests are CI-run, Playwright browser tests are not: `.github/workflows/install-smoke.yml:62-67`, `web/package.json:10-11`.
<<<CODEX-VERDICT-END CANON-29>>>
