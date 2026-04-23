#!/usr/bin/env python3
from __future__ import annotations

import subprocess
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
TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT=8443
TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH=/notion/webhook
ALMANAC_NOTION_WEBHOOK_PORT=8283
ALMANAC_SSOT_NOTION_SPACE_URL="https://www.notion.so/The-Almanac-aaaaaaaaaaaabbbbbbbbbbbbbbbb"
ALMANAC_NOTION_WEBHOOK_PUBLIC_URL="https://kor.tail77f45e.ts.net:8443/notion/webhook"
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
    "kor.tail77f45e.ts.net:8443": {{
      "Handlers": {{
        "/": {{
          "Proxy": "http://127.0.0.1:8283"
        }}
      }}
    }}
  }},
  "AllowFunnel": {{
    "kor.tail77f45e.ts.net:8443": true
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
        "PASS:Tailscale Funnel publishes only the configured Notion webhook route: https://kor.tail77f45e.ts.net:8443/notion/webhook" in result.stdout,
        f"expected PASS about live webhook funnel route, got: {result.stdout!r}",
    )
    expect(
        "PASS:Notion webhook verification confirmed at token-installed by token-installed" in result.stdout,
        f"expected PASS about confirmed webhook verification, got: {result.stdout!r}",
    )
    print("PASS test_shared_notion_with_tailscale_funnel_reports_live_public_route")


def main() -> int:
    test_placeholder_secret_detection_and_reporting()
    test_activation_trigger_write_probe_reports_writable_and_unwritable_states()
    test_loopback_bind_probe_reports_safe_and_unsafe_listeners()
    test_shared_notion_without_webhook_reports_sweep_fallback_warning()
    test_shared_notion_with_public_webhook_but_no_token_warns_not_ready()
    test_shared_notion_with_installed_token_but_unconfirmed_verification_warns()
    test_shared_notion_with_confirmed_verification_reports_ready()
    test_shared_notion_with_tailscale_funnel_reports_live_public_route()
    print("PASS all 8 health regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
