# Ralphie Steering: Executor Lint Risk Repair

Date: 2026-05-01

## Why This Exists

The prior ArcLink executor digest repair passed its focused tests, but the next
LINT gate found four additional executor correctness and validation risks. Do
not summarize the older digest repair as the active BUILD scope. The active
BUILD scope is the LINT HOLD from iteration 23.

## Required BUILD Scope

Repair `python/arclink_executor.py` and focused executor tests so these issues
are fixed or explicitly rejected by code:

1. Fake Docker Compose idempotent replay must not rematerialize secrets before
   returning a stored applied result. A replay with the same idempotency key and
   identical rendered intent should return the stored idempotent result even if
   the current resolver no longer has the secret material. Add a regression.
2. `fake_fail_after_services=0` must have deterministic safe behavior. Prefer
   rejecting `<= 0` with `ArcLinkExecutorError`, or implement a clearly tested
   fail-before-any-service mode. Do not leave the current accidental "apply one
   service" behavior.
3. Rollback destructive-delete detection must not rely on mixed `and`/`or`
   precedence. Extract a helper such as `_is_destructive_state_delete(action)`
   and cover state/vault delete cases.
4. Cloudflare DNS planning must validate record types before live adapter
   wiring. Add an allowlist appropriate for ArcLink subdomain orchestration
   (`CNAME`, `A`, `AAAA`, and `TXT` are acceptable starting points), and add an
   invalid record type regression.

## Verification Required

Run and report at minimum:

- `python3 tests/test_arclink_executor.py`
- `python3 tests/test_arclink_provisioning.py`
- `python3 tests/test_public_repo_hygiene.py`
- `python3 -m py_compile python/arclink_executor.py python/arclink_provisioning.py`
- `git diff --check`

Repo-wide `ruff`/`pyflakes`, `pytest`, `systemd-analyze`, `inotifywait`, and
live Cloudflare/Stripe/Chutes/Telegram/Discord tests remain separate release
gates unless this BUILD intentionally scopes them in.

## Completion Bar

BUILD is not complete until the completion summary names all four lint findings
above and states whether each was repaired by code and test. If only the older
intent-digest mismatch repair is mentioned, the BUILD has drifted and should be
rerouted.
