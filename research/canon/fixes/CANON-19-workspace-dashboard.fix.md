<<<CODEX-FIX-START CANON-19>>>
## CANON-19 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: python/arclink_dashboard.py, python/arclink_dashboard_auth_proxy.py, python/arclink_headless_hermes_setup.py, python/arclink_skill_enablement.py, tests/test_arclink_admin_actions.py, tests/test_arclink_dashboard.py, tests/test_arclink_dashboard_auth_proxy.py, tests/test_arclink_headless_hermes_setup.py
TESTS: 5 files pass + py_compile pass / 1 BLOCKED by sandbox socket bind (`tests/test_arclink_dashboard_auth_proxy.py`, PermissionError [Errno 1])

### Fixed (severity — what — path:line)
- MEDIUM — removed auth-proxy session-token fallback signing from username/password; missing `session_secret` now fails closed and sets no session cookie — `python/arclink_dashboard_auth_proxy.py:86`, `python/arclink_dashboard_auth_proxy.py:594`, `python/arclink_dashboard_auth_proxy.py:653`, `python/arclink_dashboard_auth_proxy.py:1081`
- MEDIUM — user dashboard now derives provider from deployment/onboarding metadata before falling back to configured env, so non-Chutes deployments do not get Chutes boundary semantics — `python/arclink_dashboard.py:1628`, `python/arclink_dashboard.py:1787`
- MEDIUM — scale operations snapshot now accepts injected env and passes it through readiness and rollout planning instead of reading process env directly — `python/arclink_dashboard.py:605`, `python/arclink_dashboard.py:717`
- MEDIUM — headless setup and skill enablement now share an advisory `config.yaml` lock across both writer strategies — `python/arclink_headless_hermes_setup.py:30`, `python/arclink_headless_hermes_setup.py:103`, `python/arclink_headless_hermes_setup.py:589`, `python/arclink_skill_enablement.py:50`, `python/arclink_skill_enablement.py:258`
- LOW — admin-action idempotency now catches unique-key race collisions and returns the existing matching intent — `python/arclink_dashboard.py:2426`
- LOW — operator snapshot now honors live-journey env alternates such as `CLOUDFLARE_API_TOKEN_REF` — `python/arclink_dashboard.py:526`, `python/arclink_dashboard.py:549`

### Skipped (risk-accepted / standing / out-of-scope — why)
- SSO cookie cross-deployment scope — left intact as the canon reconciles it as intended same-user/Captain fleet SSO, not cross-tenant escalation.
- `request_arclink_backup_write_check` failed-closed behavior — left intact because it is explicitly PG-BACKUP/consumer gated and does not activate backup.
- Admin `stripe_customer_id` exposure — left intact as admin-session-gated identifier exposure, not a secret.

### NEEDS-DECISION (ambiguous; left for human)
- Backup deploy-key staging persists a private key and the `backup_deploy_key_private_ref` rail has no consumer; changing/removing it would alter the public backup setup contract.
- Silent SSO secret generation/default enablement in Docker/domain mode needs a product decision on whether SSO should be opt-in.
- Process-local auth-proxy login throttle needs a shared-store design if it should survive restarts/multiple proxy processes.
- Env-derived dashboard host validation needs allowed-host policy before tightening operator env URL formats.

### Cross-piece edits made (if any) + tests added
- Cross-piece edits: none.
- Tests added/adjusted: provider metadata, env alternates, scale env injection, admin idempotency race, missing session-secret fail-closed, shared config lock path.
<<<CODEX-FIX-END CANON-19>>>
