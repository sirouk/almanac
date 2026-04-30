#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import sqlite3
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HEALTH_SH = REPO / "bin" / "health.sh"


def run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=False)


def bash(script: str) -> subprocess.CompletedProcess[str]:
    return run(["bash", "-lc", script], cwd=REPO)


def extract(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def install_active_mcp_token_row(conn: sqlite3.Connection, agent_id: str) -> None:
    conn.execute(
        """
        CREATE TABLE bootstrap_tokens (
          agent_id TEXT,
          revoked_at TEXT,
          activated_at TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO bootstrap_tokens (agent_id, revoked_at, activated_at) VALUES (?, NULL, ?)",
        (agent_id, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")),
    )


def test_placeholder_secret_detection_and_reporting() -> None:
    text = HEALTH_SH.read_text()
    snippet = extract(text, "trim_secret_marker() {", "check_curator_gateway_runtime() {")
    script = f"""
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
STRICT_MODE=0
pass() {{ printf 'PASS:%s\\n' "$1"; }}
warn() {{ printf 'WARN:%s\\n' "$1"; }}
fail() {{ printf 'FAIL:%s\\n' "$1"; }}
warn_or_fail() {{ warn "$1"; }}
lowercase() {{ printf '%s' "${{1:-}}" | tr '[:upper:]' '[:lower:]'; }}
{snippet}
ENABLE_NEXTCLOUD=1
POSTGRES_PASSWORD=change-me
NEXTCLOUD_ADMIN_PASSWORD=real-secret
check_placeholder_secrets
"""
    result = bash(script)
    expect(result.returncode == 0, f"placeholder detection case failed: {result.stderr}")
    expect(
        "WARN:POSTGRES_PASSWORD still uses a placeholder secret" in result.stdout,
        f"expected placeholder Postgres warning, got: {result.stdout!r}",
    )
    expect(
        "PASS:NEXTCLOUD_ADMIN_PASSWORD is not a placeholder secret" in result.stdout,
        f"expected non-placeholder Nextcloud admin pass, got: {result.stdout!r}",
    )
    print("PASS test_placeholder_secret_detection_and_reporting")


def test_backup_timer_job_result_reports_success_and_failure() -> None:
    text = HEALTH_SH.read_text()
    snippet = extract(text, "check_unit_state() {", "check_port_listening() {")
    script = f"""
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
STRICT_MODE=0
pass() {{ printf 'PASS:%s\\n' "$1"; }}
warn() {{ printf 'WARN:%s\\n' "$1"; }}
fail() {{ printf 'FAIL:%s\\n' "$1"; }}
warn_or_fail() {{ warn "$1"; }}
systemctl() {{
  if [[ "$1" == "--user" && "$2" == "is-active" && "$3" == "almanac-github-backup.timer" ]]; then
    printf 'active\\n'
    return 0
  fi
  if [[ "$1" == "--user" && "$2" == "show" && "$3" == "almanac-github-backup.service" ]]; then
    case "$4" in
      --property=Result) printf '%s\\n' "${{ALMANAC_BACKUP_RESULT:-success}}" ;;
      --property=ActiveState) printf '%s\\n' "${{ALMANAC_BACKUP_ACTIVE_STATE:-inactive}}" ;;
      --property=SubState) printf '%s\\n' "${{ALMANAC_BACKUP_SUB_STATE:-dead}}" ;;
      *) return 1 ;;
    esac
    return 0
  fi
  return 1
}}
{snippet}
check_unit_state almanac-github-backup.timer required
check_user_timer_job_result almanac-github-backup.service required
ALMANAC_BACKUP_RESULT=exit-code
ALMANAC_BACKUP_ACTIVE_STATE=failed
ALMANAC_BACKUP_SUB_STATE=failed
check_user_timer_job_result almanac-github-backup.service required
"""
    result = bash(script)
    expect(result.returncode == 0, f"backup timer job result case failed: {result.stderr}")
    expect("PASS:almanac-github-backup.timer is active" in result.stdout, result.stdout)
    expect("PASS:almanac-github-backup.service last result is success" in result.stdout, result.stdout)
    expect(
        "FAIL:almanac-github-backup.service last result is exit-code (state=failed/failed)" in result.stdout,
        result.stdout,
    )
    print("PASS test_backup_timer_job_result_reports_success_and_failure")


def test_activation_trigger_write_probe_reports_writable_and_unwritable_states() -> None:
    text = HEALTH_SH.read_text()
    snippet = extract(text, "check_almanac_mcp_status() {", "check_vault_definition_health() {")
    script = f"""
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
STRICT_MODE=0
pass() {{ printf 'PASS:%s\\n' "$1"; }}
warn() {{ printf 'WARN:%s\\n' "$1"; }}
fail() {{ printf 'FAIL:%s\\n' "$1"; }}
warn_or_fail() {{ warn "$1"; }}
STATE_DIR="$(mktemp -d)"
mkdir -p "$STATE_DIR/activation-triggers"
{snippet}
check_activation_trigger_write_access
chmod 0555 "$STATE_DIR/activation-triggers"
check_activation_trigger_write_access
"""
    result = bash(script)
    expect(result.returncode == 0, f"activation-trigger probe case failed: {result.stderr}")
    expect(
        "PASS:activation trigger directory is writable:" in result.stdout,
        f"expected writable activation-trigger pass, got: {result.stdout!r}",
    )
    expect(
        "WARN:activation trigger directory is not writable:" in result.stdout,
        f"expected unwritable activation-trigger warning, got: {result.stdout!r}",
    )
    print("PASS test_activation_trigger_write_probe_reports_writable_and_unwritable_states")


def test_loopback_bind_probe_reports_safe_and_unsafe_listeners() -> None:
    text = HEALTH_SH.read_text()
    snippet = extract(text, "check_port_listening() {", "check_http_json_health() {")
    script = f"""
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
STRICT_MODE=0
pass() {{ printf 'PASS:%s\\n' "$1"; }}
warn() {{ printf 'WARN:%s\\n' "$1"; }}
fail() {{ printf 'FAIL:%s\\n' "$1"; }}
warn_or_fail() {{ warn "$1"; }}
FAKEBIN="$(mktemp -d)"
cat >"$FAKEBIN/ss" <<'EOF'
#!/usr/bin/env bash
if [[ "${{ALMANAC_SS_FIXTURE:-safe}}" == "safe" ]]; then
  cat <<'SAFE'
LISTEN 0 4096 127.0.0.1:8282 0.0.0.0:*
LISTEN 0 4096 [::1]:8282 [::]:*
SAFE
else
  cat <<'UNSAFE'
LISTEN 0 4096 0.0.0.0:8282 0.0.0.0:*
UNSAFE
fi
EOF
chmod +x "$FAKEBIN/ss"
PATH="$FAKEBIN:$PATH"
{snippet}
check_port_loopback_only 8282 "almanac-mcp backend port 8282"
export ALMANAC_SS_FIXTURE=unsafe
check_port_loopback_only 8282 "almanac-mcp backend port 8282"
"""
    result = bash(script)
    expect(result.returncode == 0, f"loopback-bind probe case failed: {result.stderr}")
    expect(
        "PASS:almanac-mcp backend port 8282 only accepts loopback connections (127.0.0.1, ::1)" in result.stdout,
        f"expected safe loopback pass, got: {result.stdout!r}",
    )
    expect(
        "WARN:almanac-mcp backend port 8282 is exposed on non-loopback listener(s): 0.0.0.0" in result.stdout,
        f"expected unsafe loopback warning, got: {result.stdout!r}",
    )
    print("PASS test_loopback_bind_probe_reports_safe_and_unsafe_listeners")


def test_shared_notion_without_webhook_reports_sweep_fallback_warning() -> None:
    text = HEALTH_SH.read_text()
    snippet = extract(text, 'if [[ -n "${ALMANAC_SSOT_NOTION_SPACE_URL:-}" ]]; then', "check_vault_definition_health")
    script = f"""
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
STRICT_MODE=0
pass() {{ printf 'PASS:%s\\n' "$1"; }}
warn() {{ printf 'WARN:%s\\n' "$1"; }}
fail() {{ printf 'FAIL:%s\\n' "$1"; }}
warn_or_fail() {{ warn "$1"; }}
ALMANAC_SSOT_NOTION_SPACE_URL="https://www.notion.so/The-Almanac-aaaaaaaaaaaabbbbbbbbbbbbbbbb"
ALMANAC_NOTION_WEBHOOK_PUBLIC_URL=""
{snippet}
"""
    result = bash(script)
    expect(result.returncode == 0, f"shared notion sweep fallback case failed: {result.stderr}")
    expect(
        "WARN:Notion webhook public URL not configured" in result.stdout,
        f"expected WARN about missing webhook URL when shared Notion is configured, got: {result.stdout!r}",
    )
    expect(
        "4-hour Curator sweep" in result.stdout,
        f"expected sweep-fallback explanation in warning, got: {result.stdout!r}",
    )
    expect(
        "claim poller still covers self-serve verification" in result.stdout,
        f"expected claim-poller carve-out in warning, got: {result.stdout!r}",
    )
    expect(
        "PASS:Notion webhook public URL not configured" not in result.stdout,
        f"missing webhook URL must not be a clean PASS when shared Notion is configured: {result.stdout!r}",
    )
    print("PASS test_shared_notion_without_webhook_reports_sweep_fallback_warning")


def test_shared_notion_with_public_webhook_but_no_token_warns_not_ready() -> None:
    text = HEALTH_SH.read_text()
    snippet = extract(text, 'if [[ -n "${ALMANAC_SSOT_NOTION_SPACE_URL:-}" ]]; then', "check_vault_definition_health")
    script = f"""
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
STRICT_MODE=0
pass() {{ printf 'PASS:%s\\n' "$1"; }}
warn() {{ printf 'WARN:%s\\n' "$1"; }}
fail() {{ printf 'FAIL:%s\\n' "$1"; }}
warn_or_fail() {{ warn "$1"; }}
ALMANAC_SSOT_NOTION_SPACE_URL="https://www.notion.so/The-Almanac-aaaaaaaaaaaabbbbbbbbbbbbbbbb"
ALMANAC_NOTION_WEBHOOK_PUBLIC_URL="https://hooks.example.com/notion/webhook"
ALMANAC_DB_PATH="$(mktemp)"
FAKEBIN="$(mktemp -d)"
cat >"$FAKEBIN/sqlite3" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$FAKEBIN/sqlite3"
PATH="$FAKEBIN:$PATH"
{snippet}
"""
    result = bash(script)
    expect(result.returncode == 0, f"shared notion missing token case failed: {result.stderr}")
    expect(
        "PASS:Notion webhook public URL configured: https://hooks.example.com/notion/webhook" in result.stdout,
        f"expected configured public URL pass, got: {result.stdout!r}",
    )
    expect(
        "WARN:Notion webhook public URL is configured, but no verification token is installed yet" in result.stdout,
        f"expected WARN about missing installed webhook token, got: {result.stdout!r}",
    )
    expect(
        "webhook-arm-install" in result.stdout,
        f"expected arm-install guidance in warning, got: {result.stdout!r}",
    )
    print("PASS test_shared_notion_with_public_webhook_but_no_token_warns_not_ready")


def test_shared_notion_with_installed_token_but_unconfirmed_verification_warns() -> None:
    text = HEALTH_SH.read_text()
    snippet = extract(text, 'if [[ -n "${ALMANAC_SSOT_NOTION_SPACE_URL:-}" ]]; then', "check_vault_definition_health")
    script = f"""
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
STRICT_MODE=0
pass() {{ printf 'PASS:%s\\n' "$1"; }}
warn() {{ printf 'WARN:%s\\n' "$1"; }}
fail() {{ printf 'FAIL:%s\\n' "$1"; }}
warn_or_fail() {{ warn "$1"; }}
ALMANAC_REPO_DIR=/srv/almanac
ALMANAC_SSOT_NOTION_SPACE_URL="https://www.notion.so/The-Almanac-aaaaaaaaaaaabbbbbbbbbbbbbbbb"
ALMANAC_NOTION_WEBHOOK_PUBLIC_URL="https://hooks.example.com/notion/webhook"
ALMANAC_DB_PATH="$(mktemp)"
FAKEBIN="$(mktemp -d)"
cat >"$FAKEBIN/sqlite3" <<'EOF'
#!/usr/bin/env bash
if [[ "$2" == *"notion_webhook_verification_token"* ]]; then
  printf 'secret_live_token\\n'
fi
EOF
chmod +x "$FAKEBIN/sqlite3"
PATH="$FAKEBIN:$PATH"
{snippet}
"""
    result = bash(script)
    expect(result.returncode == 0, f"shared notion unconfirmed verification case failed: {result.stderr}")
    expect(
        "WARN:Notion webhook verification token is installed, but operator confirmation is still pending" in result.stdout,
        f"expected WARN about installed token without operator confirmation, got: {result.stdout!r}",
    )
    expect(
        "webhook-confirm-verified" in result.stdout,
        f"expected explicit verification confirmation guidance, got: {result.stdout!r}",
    )
    print("PASS test_shared_notion_with_installed_token_but_unconfirmed_verification_warns")


def test_shared_notion_with_confirmed_verification_reports_ready() -> None:
    text = HEALTH_SH.read_text()
    snippet = extract(text, 'if [[ -n "${ALMANAC_SSOT_NOTION_SPACE_URL:-}" ]]; then', "check_vault_definition_health")
    script = f"""
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
STRICT_MODE=0
pass() {{ printf 'PASS:%s\\n' "$1"; }}
warn() {{ printf 'WARN:%s\\n' "$1"; }}
fail() {{ printf 'FAIL:%s\\n' "$1"; }}
warn_or_fail() {{ warn "$1"; }}
ALMANAC_SSOT_NOTION_SPACE_URL="https://www.notion.so/The-Almanac-aaaaaaaaaaaabbbbbbbbbbbbbbbb"
ALMANAC_NOTION_WEBHOOK_PUBLIC_URL="https://hooks.example.com/notion/webhook"
ALMANAC_DB_PATH="$(mktemp)"
FAKEBIN="$(mktemp -d)"
cat >"$FAKEBIN/sqlite3" <<'EOF'
#!/usr/bin/env bash
if [[ "$2" == *"notion_webhook_verification_token"* ]]; then
  printf 'secret_live_token\\n'
elif [[ "$2" == *"notion_webhook_verified_at"* ]]; then
  printf '2026-04-22T20:31:40+00:00\\n'
elif [[ "$2" == *"notion_webhook_verified_by"* ]]; then
  printf 'operator\\n'
fi
EOF
chmod +x "$FAKEBIN/sqlite3"
PATH="$FAKEBIN:$PATH"
{snippet}
"""
    result = bash(script)
    expect(result.returncode == 0, f"shared notion confirmed verification case failed: {result.stderr}")
    expect(
        "PASS:Notion webhook verification confirmed at 2026-04-22T20:31:40+00:00 by operator" in result.stdout,
        f"expected PASS about confirmed webhook verification, got: {result.stdout!r}",
    )
    print("PASS test_shared_notion_with_confirmed_verification_reports_ready")


def test_shared_notion_with_tailscale_funnel_reports_live_public_route() -> None:
    text = HEALTH_SH.read_text()
    helper = extract(text, "check_notion_webhook_funnel() {", "check_activation_trigger_write_access() {")
    snippet = extract(text, 'if [[ -n "${ALMANAC_SSOT_NOTION_SPACE_URL:-}" ]]; then', "check_vault_definition_health")
    script = f"""
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
STRICT_MODE=0
pass() {{ printf 'PASS:%s\\n' "$1"; }}
warn() {{ printf 'WARN:%s\\n' "$1"; }}
fail() {{ printf 'FAIL:%s\\n' "$1"; }}
warn_or_fail() {{ warn "$1"; }}
ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL=1
TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT=443
TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH=/notion/webhook
ALMANAC_NOTION_WEBHOOK_PORT=8283
ALMANAC_SSOT_NOTION_SPACE_URL="https://www.notion.so/The-Almanac-aaaaaaaaaaaabbbbbbbbbbbbbbbb"
ALMANAC_NOTION_WEBHOOK_PUBLIC_URL="https://almanac.example.test/notion/webhook"
ALMANAC_DB_PATH="$(mktemp)"
FAKEBIN="$(mktemp -d)"
cat >"$FAKEBIN/sqlite3" <<'EOF'
#!/usr/bin/env bash
printf 'token-installed\\n'
EOF
cat >"$FAKEBIN/tailscale" <<'EOF'
#!/usr/bin/env bash
if [[ "$1" == "funnel" && "$2" == "status" && "$3" == "--json" ]]; then
  cat <<'JSON'
{{
  "Web": {{
    "almanac.example.test:443": {{
      "Handlers": {{
        "/": {{
          "Proxy": "http://127.0.0.1:8283"
        }}
      }}
    }}
  }},
  "AllowFunnel": {{
    "almanac.example.test:443": true
  }}
}}
JSON
  exit 0
fi
exit 1
EOF
chmod +x "$FAKEBIN/sqlite3" "$FAKEBIN/tailscale"
PATH="$FAKEBIN:$PATH"
{helper}
{snippet}
"""
    result = bash(script)
    expect(result.returncode == 0, f"shared notion funnel case failed: {result.stderr}")
    expect(
        "PASS:Tailscale Funnel publishes only the configured Notion webhook route: https://almanac.example.test/notion/webhook" in result.stdout,
        f"expected PASS about live webhook funnel route, got: {result.stdout!r}",
    )
    expect(
        "PASS:Notion webhook verification confirmed at token-installed by token-installed" in result.stdout,
        f"expected PASS about confirmed webhook verification, got: {result.stdout!r}",
    )
    print("PASS test_shared_notion_with_tailscale_funnel_reports_live_public_route")


def test_nextcloud_health_uses_rootless_podman_runtime_dir() -> None:
    text = HEALTH_SH.read_text()
    snippet = extract(text, "check_nextcloud_vault_mount() {", "check_pdf_ingest_status() {")
    expect("podman_for_current_user()" in snippet, snippet)
    expect('local runtime_dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"' in snippet, snippet)
    expect('local podman_cwd="${HOME:-/tmp}"' in snippet, snippet)
    expect('(cd "$podman_cwd" && env XDG_RUNTIME_DIR="$runtime_dir" podman "$@")' in snippet, snippet)
    expect('(cd "$podman_cwd" && podman "$@")' in snippet, snippet)
    expect("podman container inspect" not in snippet, snippet)
    expect("podman exec" not in snippet, snippet)
    print("PASS test_nextcloud_health_uses_rootless_podman_runtime_dir")


def test_active_agent_health_treats_private_user_runtime_as_ok() -> None:
    text = HEALTH_SH.read_text()
    snippet = extract(text, "check_active_agent_state() {", "check_auto_provision_state() {")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "control.sqlite3"
        manifest_path = root / "agent-manifest.json"
        private_parent = root / "private"
        hermes_home = private_parent / "hermes-home"
        hermes_home.mkdir(parents=True)
        manifest_path.write_text('{"agent_id":"agent-private"}\n', encoding="utf-8")

        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE agents (
              agent_id TEXT,
              unix_user TEXT,
              display_name TEXT,
              hermes_home TEXT,
              manifest_path TEXT,
              channels_json TEXT,
              role TEXT,
              status TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO agents (
              agent_id, unix_user, display_name, hermes_home, manifest_path,
              channels_json, role, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "agent-private",
                "alice",
                "Alice",
                str(hermes_home),
                str(manifest_path),
                '["telegram"]',
                "user",
                "active",
            ),
        )
        conn.execute(
            "CREATE TABLE refresh_jobs (job_name TEXT, last_run_at TEXT, last_status TEXT)"
        )
        conn.execute(
            "INSERT INTO refresh_jobs (job_name, last_run_at, last_status) VALUES (?, ?, ?)",
            (
                "agent-private-refresh",
                dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "ok",
            ),
        )
        install_active_mcp_token_row(conn, "agent-private")
        conn.commit()
        conn.close()

        script = f"""
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
STRICT_MODE=0
pass() {{ printf 'PASS:%s\\n' "$1"; }}
warn() {{ printf 'WARN:%s\\n' "$1"; }}
fail() {{ printf 'FAIL:%s\\n' "$1"; }}
warn_or_fail() {{ warn "$1"; }}
ALMANAC_DB_PATH={str(db_path)!r}
{snippet}
check_active_agent_state
"""
        try:
            private_parent.chmod(0)
            result = bash(script)
        finally:
            private_parent.chmod(0o700)
        expect(result.returncode == 0, f"private user runtime health case failed: {result.stderr}")
        expect("WARN:" not in result.stdout, f"private user runtime should not warn, got: {result.stdout!r}")
        expect("FAIL:" not in result.stdout, f"private user runtime should not fail, got: {result.stdout!r}")
        expect(
            "PASS:agent-private: unix_user=alice display_name=Alice channels=telegram" in result.stdout,
            f"expected active agent pass, got: {result.stdout!r}",
        )
        expect(
            "hermes_home private; skills private; verified by user-owned refresh/service state" in result.stdout,
            f"expected privacy note in PASS, got: {result.stdout!r}",
        )
    print("PASS test_active_agent_health_treats_private_user_runtime_as_ok")


def test_active_agent_health_fails_when_shared_vault_acl_is_missing() -> None:
    text = HEALTH_SH.read_text()
    snippet = extract(text, "check_active_agent_state() {", "check_auto_provision_state() {")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "control.sqlite3"
        manifest_path = root / "agent-manifest.json"
        hermes_home = root / "hermes-home"
        vault_dir = root / "vault"
        fakebin = root / "fakebin"
        required_skill_names = [
            "almanac-qmd-mcp",
            "almanac-vault-reconciler",
            "almanac-first-contact",
            "almanac-vaults",
            "almanac-ssot",
            "almanac-notion-knowledge",
            "almanac-ssot-connect",
            "almanac-notion-mcp",
            "almanac-resources",
        ]
        hermes_home.mkdir(parents=True)
        (vault_dir / "Projects").mkdir(parents=True)
        fakebin.mkdir()
        manifest_path.write_text('{"agent_id":"agent-private"}\n', encoding="utf-8")
        for skill_name in required_skill_names:
            skill_dir = hermes_home / "skills" / skill_name
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(f"# {skill_name}\n", encoding="utf-8")
        for rel_path in ("email/himalaya", "productivity/google-workspace"):
            skill_dir = hermes_home / "skills" / rel_path
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(f"# {rel_path}\n", encoding="utf-8")
        (fakebin / "getfacl").write_text(
            """#!/usr/bin/env bash
cat <<'ACL'
user::rwx
user:bob:rwx
group::r-x
mask::rwx
other::---
default:user::rwx
default:user:bob:rwx
default:group::r-x
default:mask::rwx
default:other::---
ACL
""",
            encoding="utf-8",
        )
        (fakebin / "getfacl").chmod(0o755)

        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE agents (
              agent_id TEXT,
              unix_user TEXT,
              display_name TEXT,
              hermes_home TEXT,
              manifest_path TEXT,
              channels_json TEXT,
              role TEXT,
              status TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO agents (
              agent_id, unix_user, display_name, hermes_home, manifest_path,
              channels_json, role, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "agent-private",
                "alice",
                "Alice",
                str(hermes_home),
                str(manifest_path),
                '["telegram"]',
                "user",
                "active",
            ),
        )
        conn.execute(
            "CREATE TABLE refresh_jobs (job_name TEXT, last_run_at TEXT, last_status TEXT)"
        )
        conn.execute(
            "INSERT INTO refresh_jobs (job_name, last_run_at, last_status) VALUES (?, ?, ?)",
            (
                "agent-private-refresh",
                dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "ok",
            ),
        )
        install_active_mcp_token_row(conn, "agent-private")
        conn.commit()
        conn.close()

        script = f"""
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
STRICT_MODE=0
pass() {{ printf 'PASS:%s\\n' "$1"; }}
warn() {{ printf 'WARN:%s\\n' "$1"; }}
fail() {{ printf 'FAIL:%s\\n' "$1"; }}
warn_or_fail() {{ warn "$1"; }}
ALMANAC_DB_PATH={str(db_path)!r}
VAULT_DIR={str(vault_dir)!r}
PATH={str(fakebin)!r}:$PATH
{snippet}
check_active_agent_state
"""
        result = bash(script)
        expect(result.returncode == 0, f"missing vault ACL health case crashed: {result.stderr}")
        expect(
            f"FAIL:agent-private: shared vault ACL for alice is missing rwx on {vault_dir}" in result.stdout,
            f"expected missing user ACL failure, got: {result.stdout!r}",
        )
        expect(
            f"FAIL:agent-private: shared vault default ACL for alice is missing rwx on {vault_dir}" in result.stdout,
            f"expected missing default ACL failure, got: {result.stdout!r}",
        )
    print("PASS test_active_agent_health_fails_when_shared_vault_acl_is_missing")


def test_active_agent_health_fails_when_shared_vault_parent_acl_is_mount_hostile() -> None:
    text = HEALTH_SH.read_text()
    snippet = extract(text, "check_active_agent_state() {", "check_auto_provision_state() {")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "control.sqlite3"
        service_home = root / "service-home"
        private_dir = service_home / "almanac" / "almanac-priv"
        manifest_path = root / "agent-manifest.json"
        hermes_home = root / "hermes-home"
        vault_dir = private_dir / "vault"
        fakebin = root / "fakebin"
        subuid_file = root / "subuid"
        required_skill_names = [
            "almanac-qmd-mcp",
            "almanac-vault-reconciler",
            "almanac-first-contact",
            "almanac-vaults",
            "almanac-ssot",
            "almanac-notion-knowledge",
            "almanac-ssot-connect",
            "almanac-notion-mcp",
            "almanac-resources",
        ]
        hermes_home.mkdir(parents=True)
        (vault_dir / "Projects").mkdir(parents=True)
        fakebin.mkdir()
        subuid_file.write_text("alice:165536:65536\n", encoding="utf-8")
        manifest_path.write_text('{"agent_id":"agent-private"}\n', encoding="utf-8")
        for skill_name in required_skill_names:
            skill_dir = hermes_home / "skills" / skill_name
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(f"# {skill_name}\n", encoding="utf-8")
        for rel_path in ("email/himalaya", "productivity/google-workspace"):
            skill_dir = hermes_home / "skills" / rel_path
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(f"# {rel_path}\n", encoding="utf-8")
        (fakebin / "getfacl").write_text(
            f"""#!/usr/bin/env bash
path="${{@: -1}}"
case "$path" in
  {str(vault_dir)!r}|{str(vault_dir / "Projects")!r})
    cat <<'ACL'
user::rwx
user:alice:rwx
user:165536:rwx
group::r-x
mask::rwx
other::---
default:user::rwx
default:user:alice:rwx
default:user:165536:rwx
default:group::r-x
default:mask::rwx
default:other::---
ACL
    ;;
  *)
    cat <<'ACL'
user::rwx
user:alice:r-x
user:165536:--x
group::r-x
mask::rwx
other::---
ACL
    ;;
esac
""",
            encoding="utf-8",
        )
        (fakebin / "getfacl").chmod(0o755)

        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE agents (
              agent_id TEXT,
              unix_user TEXT,
              display_name TEXT,
              hermes_home TEXT,
              manifest_path TEXT,
              channels_json TEXT,
              role TEXT,
              status TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO agents (
              agent_id, unix_user, display_name, hermes_home, manifest_path,
              channels_json, role, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "agent-private",
                "alice",
                "Alice",
                str(hermes_home),
                str(manifest_path),
                '["telegram"]',
                "user",
                "active",
            ),
        )
        conn.execute("CREATE TABLE refresh_jobs (job_name TEXT, last_run_at TEXT, last_status TEXT)")
        conn.execute(
            "INSERT INTO refresh_jobs (job_name, last_run_at, last_status) VALUES (?, ?, ?)",
            (
                "agent-private-refresh",
                dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "ok",
            ),
        )
        install_active_mcp_token_row(conn, "agent-private")
        conn.commit()
        conn.close()

        script = f"""
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
STRICT_MODE=0
pass() {{ printf 'PASS:%s\\n' "$1"; }}
warn() {{ printf 'WARN:%s\\n' "$1"; }}
fail() {{ printf 'FAIL:%s\\n' "$1"; }}
warn_or_fail() {{ warn "$1"; }}
ALMANAC_DB_PATH={str(db_path)!r}
ALMANAC_HOME={str(service_home)!r}
export ALMANAC_ROOTLESS_SUBUID_FILE={str(subuid_file)!r}
VAULT_DIR={str(vault_dir)!r}
PATH={str(fakebin)!r}:$PATH
{snippet}
check_active_agent_state
"""
        result = bash(script)
        expect(result.returncode == 0, f"mount-hostile vault parent ACL health case crashed: {result.stderr}")
        expect(
            f"FAIL:agent-private: shared vault mount-source ACL for rootless Podman subuid 165536 for alice is missing rX on {private_dir}" in result.stdout,
            f"expected missing mount-source parent ACL failure, got: {result.stdout!r}",
        )
    print("PASS test_active_agent_health_fails_when_shared_vault_parent_acl_is_mount_hostile")


def test_active_agent_health_fails_when_agent_backup_cron_last_run_failed() -> None:
    text = HEALTH_SH.read_text()
    snippet = extract(text, "check_active_agent_state() {", "check_auto_provision_state() {")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "control.sqlite3"
        manifest_path = root / "agent-manifest.json"
        hermes_home = root / "hermes-home"
        required_skill_names = [
            "almanac-qmd-mcp",
            "almanac-vault-reconciler",
            "almanac-first-contact",
            "almanac-vaults",
            "almanac-ssot",
            "almanac-notion-knowledge",
            "almanac-ssot-connect",
            "almanac-notion-mcp",
            "almanac-resources",
        ]
        hermes_home.mkdir(parents=True)
        manifest_path.write_text('{"agent_id":"agent-backup"}\n', encoding="utf-8")
        for skill_name in required_skill_names:
            skill_dir = hermes_home / "skills" / skill_name
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(f"# {skill_name}\n", encoding="utf-8")
        for rel_path in ("email/himalaya", "productivity/google-workspace"):
            skill_dir = hermes_home / "skills" / rel_path
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(f"# {rel_path}\n", encoding="utf-8")
        (hermes_home / "state").mkdir(parents=True)
        (hermes_home / "state" / "almanac-agent-backup.env").write_text("AGENT_BACKUP_REMOTE=x\n", encoding="utf-8")
        (hermes_home / "scripts").mkdir(parents=True)
        (hermes_home / "scripts" / "almanac_agent_backup.py").write_text("# backup wrapper\n", encoding="utf-8")
        (hermes_home / "cron").mkdir(parents=True)
        (hermes_home / "cron" / "jobs.json").write_text(
            """
{
  "jobs": [
    {
      "id": "a1bac0ffee42",
      "managed_by": "almanac",
      "managed_kind": "agent-home-backup",
      "enabled": true,
      "state": "scheduled",
      "script": "almanac_agent_backup.py",
      "schedule": {"kind": "interval", "minutes": 240, "display": "every 240m"}
    }
  ]
}
""",
            encoding="utf-8",
        )
        last_run_dir = hermes_home / "state" / "agent-home-backup"
        last_run_dir.mkdir(parents=True)
        (last_run_dir / "last-run.json").write_text(
            '{"ok": false, "ran_at": "2026-04-27T00:00:00+00:00", "summary": "push failed"}\n',
            encoding="utf-8",
        )

        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE agents (
              agent_id TEXT,
              unix_user TEXT,
              display_name TEXT,
              hermes_home TEXT,
              manifest_path TEXT,
              channels_json TEXT,
              role TEXT,
              status TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO agents (
              agent_id, unix_user, display_name, hermes_home, manifest_path,
              channels_json, role, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "agent-backup",
                "alice",
                "Alice",
                str(hermes_home),
                str(manifest_path),
                '["discord"]',
                "user",
                "active",
            ),
        )
        conn.execute(
            "CREATE TABLE refresh_jobs (job_name TEXT, last_run_at TEXT, last_status TEXT)"
        )
        conn.execute(
            "INSERT INTO refresh_jobs (job_name, last_run_at, last_status) VALUES (?, ?, ?)",
            (
                "agent-backup-refresh",
                dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "ok",
            ),
        )
        install_active_mcp_token_row(conn, "agent-backup")
        conn.commit()
        conn.close()

        script = f"""
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
STRICT_MODE=0
pass() {{ printf 'PASS:%s\\n' "$1"; }}
warn() {{ printf 'WARN:%s\\n' "$1"; }}
fail() {{ printf 'FAIL:%s\\n' "$1"; }}
warn_or_fail() {{ warn "$1"; }}
ALMANAC_DB_PATH={str(db_path)!r}
VAULT_DIR=
{snippet}
check_active_agent_state
"""
        result = bash(script)
        expect(result.returncode == 0, f"backup cron health case crashed: {result.stderr}")
        expect(
            "FAIL:agent-backup: agent backup last run failed: push failed" in result.stdout,
            f"expected backup last-run failure, got: {result.stdout!r}",
        )
    print("PASS test_active_agent_health_fails_when_agent_backup_cron_last_run_failed")


def test_active_agent_health_allows_clean_zero_user_enrollment_state() -> None:
    text = HEALTH_SH.read_text()
    snippet = extract(text, "check_active_agent_state() {", "check_auto_provision_state() {")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "control.sqlite3"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE agents (
              agent_id TEXT,
              unix_user TEXT,
              display_name TEXT,
              hermes_home TEXT,
              manifest_path TEXT,
              channels_json TEXT,
              role TEXT,
              status TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE bootstrap_requests (
              auto_provision INTEGER,
              status TEXT,
              provisioned_at TEXT
            )
            """
        )
        conn.commit()
        conn.close()

        script = f"""
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
STRICT_MODE=1
pass() {{ printf 'PASS:%s\\n' "$1"; }}
warn() {{ printf 'WARN:%s\\n' "$1"; }}
fail() {{ printf 'FAIL:%s\\n' "$1"; }}
warn_or_fail() {{ fail "$1"; }}
ALMANAC_DB_PATH={str(db_path)!r}
{snippet}
check_active_agent_state
"""
        result = bash(script)
        expect(result.returncode == 0, f"zero-user health case failed: {result.stderr}")
        expect(
            "PASS:no active enrolled user agents yet" in result.stdout,
            f"expected clean zero-user state to pass, got: {result.stdout!r}",
        )
        expect("WARN:" not in result.stdout and "FAIL:" not in result.stdout, result.stdout)
    print("PASS test_active_agent_health_allows_clean_zero_user_enrollment_state")


def main() -> int:
    test_placeholder_secret_detection_and_reporting()
    test_backup_timer_job_result_reports_success_and_failure()
    test_activation_trigger_write_probe_reports_writable_and_unwritable_states()
    test_loopback_bind_probe_reports_safe_and_unsafe_listeners()
    test_shared_notion_without_webhook_reports_sweep_fallback_warning()
    test_shared_notion_with_public_webhook_but_no_token_warns_not_ready()
    test_shared_notion_with_installed_token_but_unconfirmed_verification_warns()
    test_shared_notion_with_confirmed_verification_reports_ready()
    test_shared_notion_with_tailscale_funnel_reports_live_public_route()
    test_nextcloud_health_uses_rootless_podman_runtime_dir()
    test_active_agent_health_treats_private_user_runtime_as_ok()
    test_active_agent_health_fails_when_shared_vault_acl_is_missing()
    test_active_agent_health_fails_when_shared_vault_parent_acl_is_mount_hostile()
    test_active_agent_health_fails_when_agent_backup_cron_last_run_failed()
    test_active_agent_health_allows_clean_zero_user_enrollment_state()
    print("PASS all 15 health regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
