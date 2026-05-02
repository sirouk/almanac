# Ralphie Active Lint Repair Steering

This steering note supersedes the older favicon/responsive repair loop. Do not
advance to a new hosted request-signing/API feature until the current lint-gate
blockers are repaired.

## Immediate BUILD Scope

### Current blocking reproduction

The current 2026-05-01 LINT HOLD after the missing-session revoke repair is an
invalid-channel rate-limit mutation in `start_public_onboarding_api()`. This is
the only active BUILD target until TEST/LINT pass.

`start_public_onboarding_api(conn, channel="email", channel_identity="bad@example.test")`
raises `ArcLinkOnboardingError`, but it writes one `rate_limits` row before the
channel is rejected. Invalid input must fail before rate-limit mutation.

Repair requirements:

- Validate/clean `channel` and `channel_identity` through the shared onboarding
  validator path before calling `check_arclink_rate_limit()`.
- Unsupported channels such as `email` must leave `rate_limits` unchanged.
- Add a focused regression in `tests/test_arclink_api_auth.py` proving rejected
  public onboarding channels leave `rate_limits` unchanged.
- Keep this repair narrow. Do not expand into hosted request signing, frontend
  work, live provider mutation, admin role-grant policy, or `/api/user` and
  `/api/admin` hosted-route conversion in this pass.

The quick probe below must print `0` for the rate-limit count:

```bash
python3 - <<'PY'
import sqlite3, sys
from pathlib import Path

sys.path.insert(0, str(Path("python").resolve()))
import arclink_control as control
import arclink_api_auth as api

conn = sqlite3.connect(":memory:")
conn.row_factory = sqlite3.Row
control.ensure_schema(conn)
try:
    api.start_public_onboarding_api(conn, channel="email", channel_identity="bad@example.test")
except Exception as exc:
    print(type(exc).__name__, str(exc))
print(conn.execute("SELECT COUNT(*) AS n FROM rate_limits").fetchone()["n"])
PY
```

### Previous blocking reproduction

The 2026-05-01 lint gate reproduced a concrete missing-session revoke bug:
`revoke_arclink_session(conn, session_id="missing", session_kind="user", ...)`
returns `{"metadata": {}}` and writes an `arclink_audit_log` row even though no
user session exists. That must not be treated as a successful revoke.

Repair this before broadening scope:

- `revoke_arclink_session()` must raise `ArcLinkApiAuthError("ArcLink user session not found")`
  or `ArcLinkApiAuthError("ArcLink admin session not found")` when the target
  session id is absent.
- Missing-session revoke must not mutate a session table and must not write an
  audit row.
- Add a focused regression in `tests/test_arclink_api_auth.py` that proves the
  missing-session path raises before audit/write, at minimum for the exact user
  session case lint reproduced.
- Keep any adjacent helper cleanup only if it directly supports this fix. Do not
  expand into hosted request signing, frontend work, live provider mutation, or
  broad transport-helper scope until this blocker passes TEST and LINT.

The quick probe below must no longer print `NO_EXCEPTION`:

```bash
python3 - <<'PY'
import sqlite3, sys
from pathlib import Path

repo = Path.cwd()
sys.path.insert(0, str(repo / "python"))
import arclink_control as control
import arclink_api_auth as api

conn = sqlite3.connect(":memory:")
conn.row_factory = sqlite3.Row
control.ensure_schema(conn)
try:
    api.revoke_arclink_session(conn, session_id="missing", session_kind="user", actor_id="admin", reason="probe")
except Exception as exc:
    print(type(exc).__name__, str(exc))
else:
    print("NO_EXCEPTION")
print("audit_count", conn.execute("select count(*) from arclink_audit_log").fetchone()[0])
PY
```

Make a narrow repair for the 2026-05-01 lint hold:

1. `python/arclink_dashboard.py`
   - Admin dashboard active session counts must exclude expired and revoked
     sessions.
   - Count only rows where `status = 'active'`, `revoked_at` is blank, and
     `expires_at` is later than the current UTC timestamp.
   - Apply the same rule to both `arclink_user_sessions` and
     `arclink_admin_sessions`.

2. `python/arclink_api_auth.py`
   - `revoke_arclink_session` must validate `session_kind`.
   - Accept only `user` and `admin`.
   - Reject blank or unknown values with `ArcLinkApiAuthError`.
   - Invalid values must not revoke any session row and must not write an audit
     row.

3. `python/arclink_product_surface.py`
   - The generic `except Exception` client response must not render
     `str(exc)` or other raw internal exception detail into HTML/JSON.
   - Return generic user-safe copy such as `Request blocked. Check input and try
     again.`.
   - Keep domain-specific `ArcLinkApiAuthError` and `ArcLinkDashboardError`
     responses intact where they are intentionally user-facing.

4. Tests
   - Add focused regressions for expired/revoked session counts in
     `tests/test_arclink_dashboard.py`.
   - Add focused regressions for invalid `session_kind` rejection in
     `tests/test_arclink_api_auth.py`.
   - Add a focused regression proving the product surface generic error page
     does not expose raw exception text.
   - If public bot turns still bypass the shared onboarding rate-limit rail, add
     the smallest public-bot rate-limit helper and regression. Do not invent a
     live Telegram/Discord client in this pass.

## Do Not Do In This Repair

- Do not add hosted request-signing helpers.
- Do not start the production Next.js/Tailwind dashboard.
- Do not stage or commit. Auto-commit is disabled so untracked files are
  expected until the human commit pass groups the work.
- Do not enable live Docker, Cloudflare, Chutes, Stripe, Telegram, Discord,
  Notion, Codex, Claude, or Hetzner mutation.

## Validation

Run at minimum:

- `python3 tests/test_arclink_dashboard.py`
- `python3 tests/test_arclink_api_auth.py`
- `python3 tests/test_arclink_product_surface.py`
- `python3 tests/test_arclink_public_bots.py`
- `python3 tests/test_public_repo_hygiene.py`
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py`
- `python3 -m ruff check python/arclink_dashboard.py python/arclink_api_auth.py python/arclink_product_surface.py python/arclink_public_bots.py tests/test_arclink_dashboard.py tests/test_arclink_api_auth.py tests/test_arclink_product_surface.py tests/test_arclink_public_bots.py`
- `git diff --check`

Then return to the normal build/test/lint/document flow.
