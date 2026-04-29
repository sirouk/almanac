#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEPLOY_SH = REPO / "bin" / "deploy.sh"
HEALTH_SH = REPO / "bin" / "health.sh"
INSTALL_SYSTEM_SERVICES_SH = REPO / "bin" / "install-system-services.sh"
CURATOR_GATEWAY_SH = REPO / "bin" / "curator-gateway.sh"
CONTROL_PY = REPO / "python" / "almanac_control.py"
BOOTSTRAP_SYSTEM_SH = REPO / "bin" / "bootstrap-system.sh"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=False)


def extract(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def extract_heredoc(text: str, marker: str) -> str:
    start = text.index(marker)
    body_start = text.index("\n", start) + 1
    body_end = text.index("\nEOF", body_start)
    return text[body_start:body_end]


def bash(script: str) -> subprocess.CompletedProcess[str]:
    # Some tests splice large deploy.sh function ranges into an inline script.
    # Linux also has a per-argument cap (MAX_ARG_STRLEN, commonly 128 KiB), so
    # a script can be far below ARG_MAX while still being too large for
    # `bash -lc <script>`. Source long scripts from a temp file to keep the
    # regression harness independent of deploy.sh growth.
    if len(script.encode("utf-8")) < 100_000:
        return run(["bash", "-lc", script], cwd=REPO)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, prefix="almanac-deploy-regression-", suffix=".sh") as handle:
        handle.write(script)
        script_path = Path(handle.name)
    try:
        return run(["bash", "-lc", f"source {shlex.quote(str(script_path))}"], cwd=REPO)
    finally:
        try:
            script_path.unlink()
        except OSError:
            pass


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_bool_env_blank_uses_default() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_regression")
    expect(mod.bool_env("X", default=True, env={"X": ""}) is True, "blank string should fall back to default=True")
    expect(mod.bool_env("X", default=False, env={"X": ""}) is False, "blank string should fall back to default=False")
    expect(mod.bool_env("X", default=True, env={"X": "   "}) is True, "whitespace string should fall back to default=True")
    expect(mod.bool_env("X", default=False, env={"X": "1"}) is True, "explicit 1 should be true")
    print("PASS test_bool_env_blank_uses_default")


def render_runtime_config(
    channels: str,
    notify_platform: str,
    tg_flag: str = "",
    dc_flag: str = "",
    *,
    enable_tailscale_serve: str = "0",
    tailscale_serve_port: str = "443",
    enable_tailscale_notion_webhook_funnel: str = "0",
    agent_enable_tailscale_serve: str = "",
    tailscale_notion_webhook_funnel_port: str = "8443",
    tailscale_notion_webhook_funnel_path: str = "/notion/webhook",
    notion_root_page_url: str = "",
    notion_root_page_id: str = "",
    notion_space_url: str = "",
    notion_space_id: str = "",
    notion_space_kind: str = "",
    notion_api_version: str = "2026-03-11",
    notion_token: str = "",
    notion_public_webhook_url: str = "",
    org_name: str = "",
    org_mission: str = "",
    org_primary_project: str = "",
    org_timezone: str = "Etc/UTC",
    org_quiet_hours: str = "",
    org_provider_enabled: str = "0",
    org_provider_preset: str = "",
    org_provider_model_id: str = "",
    org_provider_reasoning_effort: str = "medium",
    org_provider_secret_provider: str = "",
    org_provider_secret: str = "",
    hermes_docs_repo_url: str = "https://github.com/NousResearch/hermes-agent.git",
    hermes_docs_ref: str = "",
    vault_watch_debounce_seconds: str = "",
    vault_watch_max_batch_seconds: str = "",
    extra_mcp_url: str = "",
) -> str:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "write_kv() {", "write_runtime_config() {")
    script = f"""
{snippet}
ALMANAC_NAME=almanac
ALMANAC_USER=almanac
ALMANAC_HOME=/home/almanac
ALMANAC_REPO_DIR=/home/almanac/almanac
ALMANAC_PRIV_DIR=/home/almanac/almanac/almanac-priv
ALMANAC_PRIV_CONFIG_DIR=/home/almanac/almanac/almanac-priv/config
VAULT_DIR=/home/almanac/almanac/almanac-priv/vault
STATE_DIR=/home/almanac/almanac/almanac-priv/state
NEXTCLOUD_STATE_DIR=/home/almanac/almanac/almanac-priv/state/nextcloud
RUNTIME_DIR=/home/almanac/almanac/almanac-priv/state/runtime
PUBLISHED_DIR=/home/almanac/almanac/almanac-priv/published
QMD_INDEX_NAME=almanac
QMD_COLLECTION_NAME=vault
BACKUP_GIT_BRANCH=main
NEXTCLOUD_PORT=18080
NEXTCLOUD_TRUSTED_DOMAIN=almanac.example.ts.net
POSTGRES_DB=nextcloud
POSTGRES_USER=nextcloud
POSTGRES_PASSWORD=dbpass
NEXTCLOUD_ADMIN_USER=admin
NEXTCLOUD_ADMIN_PASSWORD=adminpass
ALMANAC_SSOT_NOTION_ROOT_PAGE_URL={shlex.quote(notion_root_page_url)}
ALMANAC_SSOT_NOTION_ROOT_PAGE_ID={shlex.quote(notion_root_page_id)}
ALMANAC_SSOT_NOTION_SPACE_URL={shlex.quote(notion_space_url)}
ALMANAC_SSOT_NOTION_SPACE_ID={shlex.quote(notion_space_id)}
ALMANAC_SSOT_NOTION_SPACE_KIND={shlex.quote(notion_space_kind)}
ALMANAC_SSOT_NOTION_API_VERSION={shlex.quote(notion_api_version)}
ALMANAC_SSOT_NOTION_TOKEN={shlex.quote(notion_token)}
ALMANAC_NOTION_WEBHOOK_PUBLIC_URL={shlex.quote(notion_public_webhook_url)}
ALMANAC_ORG_NAME={shlex.quote(org_name)}
ALMANAC_ORG_MISSION={shlex.quote(org_mission)}
ALMANAC_ORG_PRIMARY_PROJECT={shlex.quote(org_primary_project)}
ALMANAC_ORG_TIMEZONE={shlex.quote(org_timezone)}
ALMANAC_ORG_QUIET_HOURS={shlex.quote(org_quiet_hours)}
ALMANAC_ORG_PROVIDER_ENABLED={shlex.quote(org_provider_enabled)}
ALMANAC_ORG_PROVIDER_PRESET={shlex.quote(org_provider_preset)}
ALMANAC_ORG_PROVIDER_MODEL_ID={shlex.quote(org_provider_model_id)}
ALMANAC_ORG_PROVIDER_REASONING_EFFORT={shlex.quote(org_provider_reasoning_effort)}
ALMANAC_ORG_PROVIDER_SECRET_PROVIDER={shlex.quote(org_provider_secret_provider)}
ALMANAC_ORG_PROVIDER_SECRET={shlex.quote(org_provider_secret)}
ALMANAC_HERMES_DOCS_REPO_URL={shlex.quote(hermes_docs_repo_url)}
ALMANAC_HERMES_DOCS_REF={shlex.quote(hermes_docs_ref)}
ALMANAC_EXTRA_MCP_URL={shlex.quote(extra_mcp_url)}
ENABLE_NEXTCLOUD=0
ENABLE_TAILSCALE_SERVE={shlex.quote(enable_tailscale_serve)}
TAILSCALE_SERVE_PORT={shlex.quote(tailscale_serve_port)}
ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL={shlex.quote(enable_tailscale_notion_webhook_funnel)}
TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT={shlex.quote(tailscale_notion_webhook_funnel_port)}
TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH={shlex.quote(tailscale_notion_webhook_funnel_path)}
ENABLE_PRIVATE_GIT=1
ENABLE_QUARTO=1
SEED_SAMPLE_VAULT=1
QUARTO_PROJECT_DIR=/tmp/quarto
QUARTO_OUTPUT_DIR=/tmp/published
ALMANAC_CURATOR_CHANNELS={shlex.quote(channels)}
OPERATOR_NOTIFY_CHANNEL_PLATFORM={shlex.quote(notify_platform)}
ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED={shlex.quote(tg_flag)}
ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED={shlex.quote(dc_flag)}
ALMANAC_AGENT_ENABLE_TAILSCALE_SERVE={shlex.quote(agent_enable_tailscale_serve)}
VAULT_WATCH_DEBOUNCE_SECONDS={shlex.quote(vault_watch_debounce_seconds)}
VAULT_WATCH_MAX_BATCH_SECONDS={shlex.quote(vault_watch_max_batch_seconds)}
emit_runtime_config
"""
    result = bash(script)
    expect(result.returncode == 0, f"emit_runtime_config failed: {result.stderr}")
    return result.stdout


def render_agent_install_payload() -> str:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "render_agent_install_payload_body() {", "write_agent_install_payload_file() {")
    script = f"""
{snippet}
detect_github_repo() {{
  GITHUB_REPO_URL="https://github.com/example/almanac"
  GITHUB_REPO_OWNER_REPO="example/almanac"
  GITHUB_REPO_BRANCH="feature/smoke"
}}
resolve_agent_qmd_endpoint() {{
  AGENT_QMD_URL="https://qmd.example.test/mcp"
  QMD_COLLECTION_NAME="vault"
  PDF_INGEST_ENABLED=1
  PDF_INGEST_COLLECTION_NAME="vault-pdf-ingest"
  AGENT_QMD_URL_MODE="tailnet"
  AGENT_QMD_ROUTE_STATUS="live"
  TAILSCALE_QMD_PATH="/mcp"
}}
resolve_agent_control_plane_endpoint() {{
  AGENT_ALMANAC_MCP_URL="https://agent.example.test/almanac-mcp"
  ALMANAC_MCP_HOST="127.0.0.1"
  ALMANAC_MCP_PORT="8282"
  AGENT_ALMANAC_MCP_URL_MODE="tailnet"
  AGENT_ALMANAC_MCP_ROUTE_STATUS="live"
  TAILSCALE_ALMANAC_MCP_PATH="/almanac-mcp"
}}
ALMANAC_REPO_DIR="/repo"
ALMANAC_MODEL_PRESET_CODEX="openai:codex"
ALMANAC_MODEL_PRESET_OPUS="anthropic:claude-opus"
ALMANAC_MODEL_PRESET_CHUTES="chutes:model-router"
render_agent_install_payload_body
"""
    result = bash(script)
    expect(result.returncode == 0, f"render_agent_install_payload_body failed: {result.stderr}")
    return result.stdout


def source_value(config_text: str, key: str) -> str:
    with tempfile.NamedTemporaryFile("w", delete=False) as handle:
        handle.write(config_text)
        temp_path = handle.name
    try:
        script = f"source {shlex.quote(temp_path)} && printf '%s' \"${{{key}:-}}\""
        result = bash(script)
        expect(result.returncode == 0, f"failed to source generated config for {key}: {result.stderr}")
        return result.stdout
    finally:
        os.unlink(temp_path)


def test_emit_runtime_config_normalizes_curator_onboarding_flags() -> None:
    config = render_runtime_config("tui-only,telegram,discord", "telegram", "", "")
    tg = source_value(config, "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED")
    dc = source_value(config, "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED")
    expect(tg == "1", f"expected telegram onboarding flag to normalize to 1, got {tg!r}")
    expect(dc == "1", f"expected discord onboarding flag to normalize to 1, got {dc!r}")

    config = render_runtime_config("tui-only", "tui-only", "", "")
    tg = source_value(config, "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED")
    dc = source_value(config, "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED")
    expect(tg == "0", f"expected telegram onboarding flag to normalize to 0, got {tg!r}")
    expect(dc == "0", f"expected discord onboarding flag to normalize to 0, got {dc!r}")
    print("PASS test_emit_runtime_config_normalizes_curator_onboarding_flags")


def test_emit_runtime_config_syncs_agent_tailscale_serve_with_global_flag() -> None:
    config = render_runtime_config(
        "tui-only",
        "tui-only",
        enable_tailscale_serve="1",
        agent_enable_tailscale_serve="0",
    )
    agent_flag = source_value(config, "ALMANAC_AGENT_ENABLE_TAILSCALE_SERVE")
    expect(agent_flag == "1", f"expected agent tailscale serve flag to follow global enable, got {agent_flag!r}")
    print("PASS test_emit_runtime_config_syncs_agent_tailscale_serve_with_global_flag")


def test_emit_runtime_config_migrates_legacy_vault_watch_debounce() -> None:
    config = render_runtime_config(
        "tui-only",
        "tui-only",
        vault_watch_debounce_seconds="5",
    )
    expect("VAULT_WATCH_DEBOUNCE_SECONDS=0.5" in config, config)
    expect("VAULT_WATCH_MAX_BATCH_SECONDS=10" in config, config)

    config = render_runtime_config(
        "tui-only",
        "tui-only",
        vault_watch_debounce_seconds="2",
        vault_watch_max_batch_seconds="30",
    )
    expect("VAULT_WATCH_DEBOUNCE_SECONDS=2" in config, config)
    expect("VAULT_WATCH_MAX_BATCH_SECONDS=30" in config, config)
    print("PASS test_emit_runtime_config_migrates_legacy_vault_watch_debounce")


def test_emit_runtime_config_persists_notion_ssot_fields() -> None:
    config = render_runtime_config(
        "tui-only",
        "tui-only",
        enable_tailscale_notion_webhook_funnel="1",
        tailscale_serve_port="8445",
        tailscale_notion_webhook_funnel_port="8443",
        tailscale_notion_webhook_funnel_path="/notion/webhook",
        notion_root_page_url="https://www.notion.so/The-Almanac-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
        notion_root_page_id="aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb",
        notion_space_url="https://www.notion.so/Acme-SSOT-1234567890abcdef1234567890abcdef",
        notion_space_id="12345678-90ab-cdef-1234-567890abcdef",
        notion_space_kind="database",
        notion_api_version="2026-03-11",
        notion_token="secret_test",
        notion_public_webhook_url="https://hooks.example.com/notion/webhook",
    )
    expect(
        source_value(config, "ALMANAC_SSOT_NOTION_ROOT_PAGE_URL")
        == "https://www.notion.so/The-Almanac-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
        config,
    )
    expect(
        source_value(config, "ALMANAC_SSOT_NOTION_ROOT_PAGE_ID") == "aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb",
        config,
    )
    expect(
        source_value(config, "ALMANAC_SSOT_NOTION_SPACE_URL") == "https://www.notion.so/Acme-SSOT-1234567890abcdef1234567890abcdef",
        config,
    )
    expect(source_value(config, "ALMANAC_SSOT_NOTION_SPACE_ID") == "12345678-90ab-cdef-1234-567890abcdef", config)
    expect(source_value(config, "ALMANAC_SSOT_NOTION_SPACE_KIND") == "database", config)
    expect(source_value(config, "ALMANAC_SSOT_NOTION_API_VERSION") == "2026-03-11", config)
    expect(source_value(config, "ALMANAC_SSOT_NOTION_TOKEN") == "secret_test", config)
    expect(source_value(config, "ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL") == "1", config)
    expect(source_value(config, "TAILSCALE_SERVE_PORT") == "8445", config)
    expect(source_value(config, "TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT") == "8443", config)
    expect(source_value(config, "TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH") == "/notion/webhook", config)
    expect(
        source_value(config, "ALMANAC_NOTION_WEBHOOK_PUBLIC_URL") == "https://hooks.example.com/notion/webhook",
        config,
    )
    print("PASS test_emit_runtime_config_persists_notion_ssot_fields")


def test_emit_runtime_config_persists_hermes_docs_sync_fields() -> None:
    config = render_runtime_config("tui-only", "tui-only")
    expect(
        source_value(config, "ALMANAC_HERMES_DOCS_SYNC_ENABLED") == "1",
        config,
    )
    expect(
        source_value(config, "ALMANAC_HERMES_DOCS_REPO_URL") == "https://github.com/NousResearch/hermes-agent.git",
        config,
    )
    # Docs ref must default to the pinned runtime ref so in-vault docs cannot
    # silently drift ahead of the pinned runtime they describe.
    hermes_agent_ref = source_value(config, "ALMANAC_HERMES_AGENT_REF")
    expect(
        source_value(config, "ALMANAC_HERMES_DOCS_REF") == hermes_agent_ref,
        config,
    )
    expect(
        source_value(config, "ALMANAC_HERMES_DOCS_REF") != "main",
        "ALMANAC_HERMES_DOCS_REF must not default to 'main' (silent-drift regression)",
    )
    expect(
        source_value(config, "ALMANAC_HERMES_DOCS_SOURCE_SUBDIR") == "website/docs",
        config,
    )
    expect(
        source_value(config, "ALMANAC_HERMES_DOCS_VAULT_DIR").endswith("/vault/Agents_KB/hermes-agent-docs"),
        config,
    )
    print("PASS test_emit_runtime_config_persists_hermes_docs_sync_fields")


def test_emit_runtime_config_preserves_custom_hermes_docs_ref() -> None:
    config = render_runtime_config(
        "tui-only",
        "tui-only",
        hermes_docs_repo_url="https://example.test/custom-hermes-docs.git",
        hermes_docs_ref="main",
    )
    expect(
        source_value(config, "ALMANAC_HERMES_DOCS_REPO_URL") == "https://example.test/custom-hermes-docs.git",
        config,
    )
    expect(
        source_value(config, "ALMANAC_HERMES_DOCS_REF") == "main",
        config,
    )
    print("PASS test_emit_runtime_config_preserves_custom_hermes_docs_ref")


def test_emit_runtime_config_persists_extra_mcp_url() -> None:
    config = render_runtime_config(
        "tui-only",
        "tui-only",
        extra_mcp_url="https://kb.example/mcp",
    )
    expect(
        source_value(config, "ALMANAC_EXTRA_MCP_URL") == "https://kb.example/mcp",
        config,
    )
    print("PASS test_emit_runtime_config_persists_extra_mcp_url")


def test_deploy_guides_explicit_notion_webhook_event_selection() -> None:
    text = DEPLOY_SH.read_text()
    expect("If a subscription already exists for this exact URL, edit that subscription." in text, "expected explicit reuse guidance for existing Notion webhook subscription")
    expect("Do not create a second webhook subscription for the same Almanac endpoint." in text, "expected explicit no-duplicate Notion webhook guidance")
    expect("- Page: select all Page events" in text, "expected explicit Page event instruction")
    expect("- Database: select all Database events" in text, "expected explicit Database event instruction")
    expect("- Data source: select all Data source events" in text, "expected explicit Data source event instruction")
    expect("- File uploads: select all File upload events" in text, "expected explicit File upload event instruction")
    expect("- View: leave all View events unchecked" in text, "expected explicit View event exclusion")
    expect("- Comment: leave all Comment events unchecked" in text, "expected explicit Comment event exclusion")
    expect("webhook-confirm-verified" in text, "expected deploy guidance to include explicit operator verification confirmation")
    expect("Step 1. Open the Notion Developer Portal for this integration." in text, "expected deploy walkthrough to guide the operator into the Notion Webhooks tab")
    expect("Press ENTER once the event selection in Notion matches this checklist exactly." in text, "expected deploy walkthrough to pause after the operator sets the exact event selection")
    expect("Press ENTER immediately after Notion says the verification token was sent to the URL." in text, "expected deploy to include an interactive wait point for the Notion verification POST")
    expect("Step 6. Click Verify subscription in Notion." in text, "expected deploy walkthrough to guide the operator through the final Notion verify click")
    print("PASS test_deploy_guides_explicit_notion_webhook_event_selection")


def test_json_field_reads_json_payload() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "json_field() {", "notion_webhook_status_json() {")
    script = f"""
{snippet}
payload='{{"verified": true, "public_url": "https://hooks.example.com/notion/webhook"}}'
printf 'verified=%s\\n' "$(json_field "$payload" verified)"
printf 'public_url=%s\\n' "$(json_field "$payload" public_url)"
"""
    result = bash(script)
    expect(result.returncode == 0, f"json_field helper failed: {result.stderr}")
    expect("verified=1" in result.stdout, f"expected json_field to decode booleans, got: {result.stdout!r}")
    expect(
        "public_url=https://hooks.example.com/notion/webhook" in result.stdout,
        f"expected json_field to decode strings, got: {result.stdout!r}",
    )
    print("PASS test_json_field_reads_json_payload")


def test_noninteractive_notion_webhook_setup_flow_fails_closed_until_verified() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "json_field() {", "require_notion_subtree_ack() {")
    script = f"""
{snippet}
SELF_PATH=/tmp/deploy.sh
CONFIG_TARGET=/tmp/almanac.env
ALMANAC_NOTION_WEBHOOK_PUBLIC_URL=https://hooks.example.com/notion/webhook
notion_webhook_status_json() {{
  printf '%s' '{{"verified": false, "configured": false, "public_url": "https://hooks.example.com/notion/webhook", "verification_token": ""}}'
}}
run_notion_webhook_setup_flow /bin/true operator >/tmp/notion-flow.out 2>/tmp/notion-flow.err
rc=$?
printf 'rc=%s\\n' "$rc"
cat /tmp/notion-flow.err
"""
    result = bash(script)
    expect(result.returncode == 0, f"notion webhook flow probe failed: {result.stderr}")
    expect("rc=1" in result.stdout, f"expected non-interactive notion webhook flow to fail closed, got: {result.stdout!r}")
    expect(
        "not yet confirmed" in result.stdout,
        f"expected non-interactive notion webhook flow to explain why it stopped, got: {result.stdout!r}",
    )
    print("PASS test_noninteractive_notion_webhook_setup_flow_fails_closed_until_verified")


def test_detect_tailscale_serve_distinguishes_qmd_from_almanac_routes() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "detect_tailscale_serve() {", "normalize_http_path() {")
    script = f"""
{snippet}
TAILSCALE_SERVE_PORT=443
QMD_MCP_PORT=8181
TAILSCALE_QMD_PATH=/mcp
ALMANAC_MCP_PORT=8282
TAILSCALE_ALMANAC_MCP_PATH=/almanac-mcp
tailscale() {{
  cat <<'JSON'
{{"Web": {{"host.example.com:443": {{"Handlers": {{"/almanac-mcp": {{"Proxy": "http://127.0.0.1:8282/mcp"}}}}}}}}}}
JSON
}}
detect_tailscale_serve
printf 'qmd=%s almanac=%s\\n' "$TAILSCALE_SERVE_HAS_QMD" "$TAILSCALE_SERVE_HAS_ALMANAC_MCP"
"""
    result = bash(script)
    expect(result.returncode == 0, f"detect_tailscale_serve probe failed: {result.stderr}")
    expect("qmd=0 almanac=1" in result.stdout, f"expected exact route detection, got: {result.stdout!r}")
    print("PASS test_detect_tailscale_serve_distinguishes_qmd_from_almanac_routes")


def test_path_is_within_and_safe_remove_use_canonical_paths() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "path_is_within() {", "nextcloud_state_has_existing_data() {")
    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir) / "base"
        child = base / "child"
        base.mkdir()
        child.mkdir()
        protected = Path(temp_dir) / "protected"
        protected.mkdir()
        target = protected / "victim.txt"
        target.write_text("keep", encoding="utf-8")
        script = f"""
{snippet}
if path_is_within {shlex.quote(str(base / '../protected'))} {shlex.quote(str(base))}; then
  echo "within-bad=1"
else
  echo "within-bad=0"
fi
if path_is_within {shlex.quote(str(child))} {shlex.quote(str(base))}; then
  echo "within-good=1"
else
  echo "within-good=0"
fi
safe_remove_path {shlex.quote(str(base / '../protected'))}
"""
        result = bash(script)
        expect(result.returncode == 0, f"canonical path helpers probe failed: {result.stderr}")
        expect("within-bad=0" in result.stdout, f"expected canonical containment check to reject ../ escape, got: {result.stdout!r}")
        expect("within-good=1" in result.stdout, f"expected canonical containment check to accept real child path, got: {result.stdout!r}")
        expect(not protected.exists(), "expected safe_remove_path to resolve and remove the canonical target path")
    print("PASS test_path_is_within_and_safe_remove_use_canonical_paths")


def test_run_health_check_falls_back_when_user_bus_is_missing() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "run_health_check() {", "run_rotate_nextcloud_secrets() {")
    expect(
        'if [[ -S "/run/user/$uid/bus" ]]; then' in snippet,
        "expected run_health_check to check whether the service-user bus socket exists",
    )
    expect(
        'run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE=\'$CONFIG_TARGET\' \'$ALMANAC_REPO_DIR/bin/health.sh\'"' in snippet,
        "expected run_health_check to fall back to plain user-shell execution when the bus is absent",
    )
    print("PASS test_run_health_check_falls_back_when_user_bus_is_missing")


def test_install_and_upgrade_run_live_agent_tool_smoke_after_health() -> None:
    text = DEPLOY_SH.read_text()
    smoke_script = REPO / "bin" / "live-agent-tool-smoke.sh"
    install_snippet = extract(text, "run_root_install() {", "run_root_upgrade() {")
    upgrade_snippet = extract(text, "run_root_upgrade() {", "run_root_remove() {")
    smoke_call = 'env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/live-agent-tool-smoke.sh"'
    expect(os.access(smoke_script, os.X_OK), "live-agent-tool-smoke.sh must be executable or deploy will skip it")
    expect(smoke_call in install_snippet, install_snippet)
    expect(smoke_call in upgrade_snippet, upgrade_snippet)
    expect('echo "Running live agent tool smoke..."' in install_snippet, install_snippet)
    expect('echo "Running live agent tool smoke..."' in upgrade_snippet, upgrade_snippet)
    print("PASS test_install_and_upgrade_run_live_agent_tool_smoke_after_health")


def test_install_and_upgrade_refresh_upgrade_check_before_health() -> None:
    text = DEPLOY_SH.read_text()
    install_snippet = extract(text, "run_root_install() {", "run_root_upgrade() {")
    upgrade_snippet = extract(text, "run_root_upgrade() {", "run_root_remove() {")
    expect("refresh_upgrade_check_state_root() {" in text, "expected upgrade-check refresh helper")
    for name, snippet in [("install", install_snippet), ("upgrade", upgrade_snippet)]:
        release_index = snippet.index("write_release_state")
        refresh_index = snippet.index("refresh_upgrade_check_state_root", release_index)
        health_index = snippet.index('echo "Running health check..."', refresh_index)
        expect(release_index < refresh_index < health_index, f"{name} must refresh upgrade-check state before health")
    expect("almanac_upgrade_last_seen_sha" in text and "almanac_upgrade_relation" in text, text)
    print("PASS test_install_and_upgrade_refresh_upgrade_check_before_health")


def test_live_agent_tool_smoke_blocks_broader_python_heredoc_variants() -> None:
    body = (REPO / "bin" / "live-agent-tool-smoke.sh").read_text(encoding="utf-8")
    expect("import re" in body, body)
    expect(r"python(?:3)?\s*-\s*<<\s*\S+" in body, body)
    expect("tool_token_injected" in body, body)
    expect("Hermes quota monitoring" in body, body)
    expect("mcp_almanac_mcp_vault_search_and_fetch" in body, body)
    expect("session did not invoke the brokered Almanac knowledge/vault MCP rail" in body, body)
    expect("missing or invalid mcp-session-id" in body, body)
    expect("session attempted raw curl/MCP debugging" in body, body)
    expect("provider_auth_failed" in body, body)
    expect("provider_unavailable" in body, body)
    expect("no instances available" in body, body)
    expect("authentication_error" in body, body)
    expect("Live agent tool smoke skipped" in body, body)
    expect("almanac-bootstrap-token" in body, body)
    print("PASS test_live_agent_tool_smoke_blocks_broader_python_heredoc_variants")


def test_live_agent_tool_smoke_inspects_private_home_as_target_user() -> None:
    body = (REPO / "bin" / "live-agent-tool-smoke.sh").read_text(encoding="utf-8")
    expect("run_as_target_user()" in body, "live smoke should centralize target-user execution")
    expect('runuser -u "$TARGET_UNIX_USER" -- env HOME="$TARGET_HOME" HERMES_HOME="$TARGET_HERMES_HOME"' in body, body)
    expect('if [[ ! -d "$TARGET_HERMES_HOME" ]]' not in body, "root-owned smoke must not stat private Hermes home directly")
    expect('run_as_target_user test -d "$TARGET_HERMES_HOME"' in body, body)
    expect('chown "$TARGET_UNIX_USER" "$output_file"' in body, "target user must be able to read smoke output")
    expect('session_id="$(run_as_target_user python3 - "$output_file" "$sessions_dir" "$before_latest_session"' in body, body)
    expect('run_as_target_user test -f "$session_file"' in body, body)
    expect('run_as_target_user python3 - "$session_file" "$telemetry_path" "$session_id"' in body, body)
    print("PASS test_live_agent_tool_smoke_inspects_private_home_as_target_user")


def test_discord_onboarding_dedupes_message_ids_before_state_transitions() -> None:
    body = (REPO / "python" / "almanac_curator_discord_onboarding.py").read_text(encoding="utf-8")
    expect("_claim_discord_message_once" in body, body)
    expect("curator_discord_onboarding_seen_message:" in body, body)
    expect("INSERT OR IGNORE INTO settings" in body, body)
    expect('if not _claim_discord_message_once(str(getattr(message, "id", "") or "")):' in body, body)
    expect("await _handle_operator_channel_message(message, content)" in body, body)
    print("PASS test_discord_onboarding_dedupes_message_ids_before_state_transitions")


def test_live_agent_tool_smoke_parses_explicit_selectors() -> None:
    body = (REPO / "bin" / "live-agent-tool-smoke.sh").read_text(encoding="utf-8")
    expect("--user|-u" in body, "live smoke should accept an explicit Unix user selector")
    expect("--agent|-a" in body, "live smoke should accept an explicit agent id/name selector")
    expect("--tail" in body, "live smoke should support the documented failure-output tail option")
    expect("TAIL_LINES=40" in body, body)
    expect('tail -"$TAIL_LINES" "$output_file"' in body, body)
    expect("Unknown option:" in body, "live smoke should fail closed on unknown flags")
    expect('"$ALMANAC_DB_PATH" "$TARGET_UNIX_USER" "$TARGET_AGENT_SELECTOR"' in body, body)
    expect("lower(agent_id) = ?" in body, body)
    expect("lower(unix_user) = ?" in body, body)
    expect("lower(coalesce(display_name, '')) = ?" in body, body)
    print("PASS test_live_agent_tool_smoke_parses_explicit_selectors")


def test_agent_install_payload_tracks_current_agent_contract() -> None:
    payload = render_agent_install_payload()
    expected_skills = [
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
    expected_keys = [
        "[managed:almanac-skill-ref]",
        "[managed:vault-ref]",
        "[managed:resource-ref]",
        "[managed:qmd-ref]",
        "[managed:notion-ref]",
        "[managed:vault-topology]",
        "[managed:vault-landmarks]",
        "[managed:recall-stubs]",
        "[managed:notion-landmarks]",
        "[managed:notion-stub]",
        "[managed:today-plate]",
    ]

    for skill_name in expected_skills:
        expect(
            f"https://raw.githubusercontent.com/example/almanac/feature/smoke/skills/{skill_name}/SKILL.md" in payload,
            payload,
        )
        expect(f"example/almanac/skills/{skill_name}" in payload, payload)
        expect(f'/repo/skills/{skill_name}' in payload, payload)

    for managed_key in expected_keys:
        expect(managed_key in payload, payload)

    expect("scripts/curate-vaults.sh" not in payload, payload)
    expect("almanac-managed-context" in payload, payload)
    expect("inject Almanac MCP auth" in payload, payload)
    expect("do not read HERMES_HOME secrets files" in payload, payload)
    expect("do not pass token" in payload, payload)
    expect("plugin-managed context state" in payload, payload)
    expect("do not write dynamic [managed:*] stubs into HERMES_HOME/memories/MEMORY.md" in payload, payload)
    expect("remove only those entries" in payload, payload)
    print("PASS test_agent_install_payload_tracks_current_agent_contract")


def test_emit_runtime_config_persists_org_interview_fields() -> None:
    config = render_runtime_config(
        "tui-only",
        "tui-only",
        org_name="Acme Labs",
        org_mission="Make serious research more legible and actionable.",
        org_primary_project="Hermes deployment lane",
        org_timezone="America/New_York",
        org_quiet_hours="22:00-08:00 weekdays",
    )
    expect(source_value(config, "ALMANAC_ORG_NAME") == "Acme Labs", config)
    expect(source_value(config, "ALMANAC_ORG_MISSION") == "Make serious research more legible and actionable.", config)
    expect(source_value(config, "ALMANAC_ORG_PRIMARY_PROJECT") == "Hermes deployment lane", config)
    expect(source_value(config, "ALMANAC_ORG_TIMEZONE") == "America/New_York", config)
    expect(source_value(config, "ALMANAC_ORG_QUIET_HOURS") == "22:00-08:00 weekdays", config)
    print("PASS test_emit_runtime_config_persists_org_interview_fields")


def test_emit_runtime_config_persists_org_provider_fields() -> None:
    config = render_runtime_config(
        "tui-only",
        "tui-only",
        org_provider_enabled="1",
        org_provider_preset="chutes",
        org_provider_model_id="moonshotai/Kimi-K2.6-TEE",
        org_provider_reasoning_effort="xhigh",
        org_provider_secret_provider="chutes",
        org_provider_secret="cpk_test_secret",
    )
    expect(source_value(config, "ALMANAC_ORG_PROVIDER_ENABLED") == "1", config)
    expect(source_value(config, "ALMANAC_ORG_PROVIDER_PRESET") == "chutes", config)
    expect(source_value(config, "ALMANAC_ORG_PROVIDER_MODEL_ID") == "moonshotai/Kimi-K2.6-TEE", config)
    expect(source_value(config, "ALMANAC_ORG_PROVIDER_REASONING_EFFORT") == "xhigh", config)
    expect(source_value(config, "ALMANAC_ORG_PROVIDER_SECRET_PROVIDER") == "chutes", config)
    expect(source_value(config, "ALMANAC_ORG_PROVIDER_SECRET") == "cpk_test_secret", config)
    print("PASS test_emit_runtime_config_persists_org_provider_fields")


def test_collect_org_provider_answers_defaults_yes_and_collects_chutes() -> None:
    text = DEPLOY_SH.read_text()
    helpers = extract(text, "ask() {", "json_field() {")
    snippet = extract(text, "normalize_org_provider_preset() {", "collect_backup_git_answers() {")
    script = f"""
{helpers}
{snippet}
BOOTSTRAP_DIR={shlex.quote(str(REPO))}
ALMANAC_MODEL_PRESET_CODEX="openai:codex"
ALMANAC_MODEL_PRESET_OPUS="anthropic:claude-opus"
ALMANAC_MODEL_PRESET_CHUTES="chutes:model-router"
ALMANAC_ORG_PROVIDER_ENABLED=""
ALMANAC_ORG_PROVIDER_PRESET=""
ALMANAC_ORG_PROVIDER_MODEL_ID=""
ALMANAC_ORG_PROVIDER_REASONING_EFFORT="medium"
ALMANAC_ORG_PROVIDER_SECRET_PROVIDER=""
ALMANAC_ORG_PROVIDER_SECRET=""
ALMANAC_ORG_PROVIDER_PROMPT_NONINTERACTIVE=1
collect_org_provider_answers
printf 'enabled=%s\\n' "$ALMANAC_ORG_PROVIDER_ENABLED"
printf 'preset=%s\\n' "$ALMANAC_ORG_PROVIDER_PRESET"
printf 'model=%s\\n' "$ALMANAC_ORG_PROVIDER_MODEL_ID"
printf 'reasoning=%s\\n' "$ALMANAC_ORG_PROVIDER_REASONING_EFFORT"
printf 'secret_provider=%s\\n' "$ALMANAC_ORG_PROVIDER_SECRET_PROVIDER"
printf 'secret=%s\\n' "$ALMANAC_ORG_PROVIDER_SECRET"
"""
    result = subprocess.run(
        ["bash", "-lc", script],
        input="\n\nmoonshotai/Kimi-K2.6-TEE\nxhigh\ncpk_test_secret\n",
        text=True,
        capture_output=True,
        cwd=str(REPO),
        check=False,
    )
    expect(result.returncode == 0, f"collect_org_provider_answers failed: {result.stderr}\n{result.stdout}")
    expect("enabled=1" in result.stdout, result.stdout)
    expect("preset=chutes" in result.stdout, result.stdout)
    expect("model=moonshotai/Kimi-K2.6-TEE" in result.stdout, result.stdout)
    expect("reasoning=xhigh" in result.stdout, result.stdout)
    expect("secret_provider=chutes" in result.stdout, result.stdout)
    expect("secret=cpk_test_secret" in result.stdout, result.stdout)
    print("PASS test_collect_org_provider_answers_defaults_yes_and_collects_chutes")


def test_org_interview_validators_accept_known_good_values() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "normalize_optional_answer() {", "ask_secret_with_default() {")
    script = f"""
{snippet}
validate_org_timezone America/New_York
validate_org_quiet_hours '22:00-08:00 weekdays'
"""
    result = bash(script)
    expect(result.returncode == 0, f"expected validators to accept known-good values: {result.stderr}")
    print("PASS test_org_interview_validators_accept_known_good_values")


def test_org_interview_validators_reject_bad_values() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "normalize_optional_answer() {", "ask_secret_with_default() {")
    bad_timezone = bash(
        f"""
{snippet}
validate_org_timezone Mars/Phobos
"""
    )
    expect(bad_timezone.returncode != 0, "expected invalid timezone to be rejected")
    bad_quiet_hours = bash(
        f"""
{snippet}
validate_org_quiet_hours nighttime
"""
    )
    expect(bad_quiet_hours.returncode != 0, "expected invalid quiet hours to be rejected")
    print("PASS test_org_interview_validators_reject_bad_values")


def test_describe_operator_channel_summary_avoids_tui_only_duplication() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "describe_operator_channel_summary() {", "write_runtime_config() {")
    script = f"""
{snippet}
printf 'A=%s\\n' "$(describe_operator_channel_summary tui-only '')"
printf 'B=%s\\n' "$(describe_operator_channel_summary discord 12345)"
printf 'C=%s\\n' "$(describe_operator_channel_summary discord '')"
"""
    result = bash(script)
    expect(result.returncode == 0, f"describe_operator_channel_summary failed: {result.stderr}")
    expect("A=tui-only" in result.stdout, f"expected tui-only summary without duplication, got: {result.stdout!r}")
    expect("B=discord 12345" in result.stdout, f"expected platform+channel summary, got: {result.stdout!r}")
    expect("C=discord" in result.stdout, f"expected bare platform summary when channel is empty, got: {result.stdout!r}")
    print("PASS test_describe_operator_channel_summary_avoids_tui_only_duplication")


def run_install_reexec_case(config_mode: int) -> tuple[int, str, str]:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "probe_path_status() {", "run_root_env_cmd() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        protected_dir = tmp_path / "protected"
        protected_dir.mkdir()
        config_path = protected_dir / "almanac.env"
        config_path.write_text("ALMANAC_USER=almanac\n")
        if config_mode == 0:
            protected_dir.chmod(0)
        else:
            config_path.chmod(config_mode)

        artifact_path = tmp_path / ".almanac-operator.env"
        artifact_path.write_text(f"ALMANAC_OPERATOR_DEPLOYED_CONFIG_FILE={shlex.quote(str(config_path))}\n")
        log_path = tmp_path / "sudo.log"

        script = f"""
LOG={shlex.quote(str(log_path))}
sudo() {{ printf '%s\n' "$@" >\"$LOG\"; return 0; }}
BOOTSTRAP_DIR={shlex.quote(str(REPO))}
SELF_PATH=/fake/deploy.sh
MODE=install
ALMANAC_OPERATOR_ARTIFACT_FILE={shlex.quote(str(artifact_path))}
{snippet}
maybe_reexec_install_for_config_defaults install
status=$?
printf 'STATUS=%s\n' "$status"
if [[ -f "$LOG" ]]; then
  printf 'SUDO_LOG_BEGIN\n'
  cat "$LOG"
  printf 'SUDO_LOG_END\n'
fi
"""
        try:
            result = bash(script)
            expect(result.returncode == 0, f"reexec case failed: {result.stderr}")
            status_line = next(line for line in result.stdout.splitlines() if line.startswith("STATUS="))
            status = int(status_line.split("=", 1)[1])
            sudo_log = ""
            if "SUDO_LOG_BEGIN" in result.stdout:
                sudo_log = result.stdout.split("SUDO_LOG_BEGIN\n", 1)[1].split("\nSUDO_LOG_END", 1)[0]
            return status, result.stdout, sudo_log
        finally:
            if config_mode == 0:
                protected_dir.chmod(0o700)


def test_install_reexecs_for_unreadable_breadcrumb_config() -> None:
    status, output, sudo_log = run_install_reexec_case(0)
    expect(status == 0, f"expected unreadable-config case to reexec via sudo, got status {status}")
    expect("Switching to sudo before prompting" in output, "expected install flow to announce sudo-before-prompting path")
    expect("env" in sudo_log and "ALMANAC_CONFIG_FILE=" in sudo_log and "/fake/deploy.sh" in sudo_log and "install" in sudo_log,
           f"unexpected sudo invocation: {sudo_log!r}")
    print("PASS test_install_reexecs_for_unreadable_breadcrumb_config")


def test_install_does_not_reexec_for_readable_breadcrumb_config() -> None:
    status, output, sudo_log = run_install_reexec_case(0o600)
    expect(status == 1, f"expected readable-config case to skip reexec, got status {status}")
    expect("Switching to sudo before prompting" not in output, "readable config should not trigger sudo-before-prompting path")
    expect(sudo_log.strip() == "", f"readable config should not call sudo, got {sudo_log!r}")
    print("PASS test_install_does_not_reexec_for_readable_breadcrumb_config")


def test_run_install_flow_stops_after_failed_sudo_reexec() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "run_install_flow() {", "run_remove_flow() {")
    script = f"""
MODE=install
ALMANAC_REEXEC_ATTEMPTED=0
maybe_reexec_install_for_config_defaults() {{
  ALMANAC_REEXEC_ATTEMPTED=1
  return 42
}}
collect_install_answers() {{
  echo "collect_install_answers should not run after failed reexec" >&2
  return 99
}}
seed_private_repo() {{ return 0; }}
write_runtime_config() {{ return 0; }}
write_answers_file() {{ return 0; }}
write_agent_install_payload_file() {{ return 0; }}
write_operator_checkout_artifact() {{ return 0; }}
run_root_install() {{ return 0; }}
{snippet}
run_install_flow
status=$?
printf 'STATUS=%s\\n' "$status"
"""
    result = bash(script)
    expect(result.returncode == 0, f"run_install_flow reexec-failure case failed: {result.stderr}")
    expect("STATUS=42" in result.stdout, f"expected sudo reexec failure to propagate, got: {result.stdout!r}")
    expect(
        "collect_install_answers should not run after failed reexec" not in result.stderr,
        f"expected install flow to stop before collecting prompts, got: {result.stderr!r}",
    )
    print("PASS test_run_install_flow_stops_after_failed_sudo_reexec")


def test_run_install_flow_stops_after_failed_sudo_reexec_exit_one() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "run_install_flow() {", "run_remove_flow() {")
    script = f"""
MODE=install
ALMANAC_REEXEC_ATTEMPTED=0
maybe_reexec_install_for_config_defaults() {{
  ALMANAC_REEXEC_ATTEMPTED=1
  return 1
}}
collect_install_answers() {{
  echo "collect_install_answers should not run after exit-1 reexec failure" >&2
  return 99
}}
seed_private_repo() {{ return 0; }}
write_runtime_config() {{ return 0; }}
write_answers_file() {{ return 0; }}
write_agent_install_payload_file() {{ return 0; }}
write_operator_checkout_artifact() {{ return 0; }}
run_root_install() {{ return 0; }}
{snippet}
run_install_flow
status=$?
printf 'STATUS=%s\\n' "$status"
"""
    result = bash(script)
    expect(result.returncode == 0, f"run_install_flow exit-1 reexec-failure case failed: {result.stderr}")
    expect("STATUS=1" in result.stdout, f"expected exit-1 sudo reexec failure to propagate, got: {result.stdout!r}")
    expect(
        "collect_install_answers should not run after exit-1 reexec failure" not in result.stderr,
        f"expected install flow to stop before collecting prompts on exit-1 failure, got: {result.stderr!r}",
    )
    print("PASS test_run_install_flow_stops_after_failed_sudo_reexec_exit_one")


def test_write_operator_artifact_falls_back_to_discovered_config() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "probe_path_status() {", "run_as_user() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_path = tmp_path / "deployed" / "almanac.env"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("ALMANAC_USER=operator-svc\n", encoding="utf-8")
        artifact_path = tmp_path / ".almanac-operator.env"

        script = f"""
BOOTSTRAP_DIR={shlex.quote(str(tmp_path))}
ALMANAC_OPERATOR_ARTIFACT_FILE={shlex.quote(str(artifact_path))}
DISCOVERED_CONFIG={shlex.quote(str(config_path))}
CONFIG_TARGET=""
ALMANAC_USER=operator-svc
ALMANAC_REPO_DIR=/srv/operator-svc/almanac
ALMANAC_PRIV_DIR=/srv/operator-svc/almanac-priv
{snippet}
write_operator_checkout_artifact
printf 'ARTIFACT_BEGIN\\n'
cat {shlex.quote(str(artifact_path))}
printf 'ARTIFACT_END\\n'
"""
        result = bash(script)
        expect(result.returncode == 0, f"artifact fallback case failed: {result.stderr}")
        artifact = result.stdout.split("ARTIFACT_BEGIN\n", 1)[1].split("\nARTIFACT_END", 1)[0]
        expect(
            f"ALMANAC_OPERATOR_DEPLOYED_CONFIG_FILE={config_path}" in artifact,
            f"expected artifact to record discovered config path, got: {artifact!r}",
        )
        expect(
            "ALMANAC_OPERATOR_DEPLOYED_USER=operator-svc" in artifact,
            f"expected artifact to record service user, got: {artifact!r}",
        )
    print("PASS test_write_operator_artifact_falls_back_to_discovered_config")


def test_discover_existing_config_uses_artifact_priv_dir_hint() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "probe_path_status() {", "load_detected_config() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        priv_dir = tmp_path / "deployed" / "almanac-priv"
        config_path = priv_dir / "config" / "almanac.env"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("ALMANAC_USER=operator-svc\n")
        artifact_path = tmp_path / ".almanac-operator.env"
        artifact_path.write_text(
            "\n".join(
                [
                    "ALMANAC_OPERATOR_DEPLOYED_USER=operator-svc",
                    f"ALMANAC_OPERATOR_DEPLOYED_PRIV_DIR={shlex.quote(str(priv_dir))}",
                    "",
                ]
            )
        )
        script = f"""
BOOTSTRAP_DIR={shlex.quote(str(REPO))}
ALMANAC_OPERATOR_ARTIFACT_FILE={shlex.quote(str(artifact_path))}
{snippet}
discover_existing_config
status=$?
printf 'STATUS=%s\\n' "$status"
printf 'DISCOVERED=%s\\n' "${{DISCOVERED_CONFIG:-}}"
"""
        result = bash(script)
        expect(result.returncode == 0, f"discover_existing_config case failed: {result.stderr}")
        expect(f"STATUS=0" in result.stdout, f"expected discover_existing_config to succeed, got: {result.stdout!r}")
        expect(
            f"DISCOVERED={config_path}" in result.stdout,
            f"expected artifact priv-dir hint to resolve {config_path}, got: {result.stdout!r}",
        )
    print("PASS test_discover_existing_config_uses_artifact_priv_dir_hint")


def test_collect_install_answers_defaults_to_detected_service_user() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "collect_install_answers() {", "collect_remove_answers() {")
    script = f"""
{snippet}
ask() {{ printf '%s' "${{2:-}}"; }}
ask_yes_no() {{ printf '%s' "${{2:-0}}"; }}
ask_secret() {{ printf '%s' ""; }}
ask_secret_with_default() {{ printf '%s' "${{2:-}}"; }}
ask_secret_keep_default() {{ printf '%s' "${{2:-}}"; }}
normalize_optional_answer() {{ printf '%s' "${{1:-}}"; }}
random_secret() {{ printf '%s' "generated-secret"; }}
require_private_github_backup_remote() {{ return 0; }}
detect_tailscale() {{
  TAILSCALE_DNS_NAME=""
  TAILSCALE_IPV4=""
  TAILSCALE_TAILNET=""
}}
nextcloud_state_has_existing_data() {{ return 1; }}
read_operator_artifact_hints() {{ return 1; }}
resolve_user_home() {{ return 1; }}
collect_upstream_git_answers() {{
  ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED=0
}}
collect_backup_git_answers() {{
  BACKUP_GIT_REMOTE=""
  BACKUP_GIT_DEPLOY_KEY_PATH=""
  BACKUP_GIT_KNOWN_HOSTS_FILE=""
}}
load_detected_config() {{
  ALMANAC_USER=operator-svc
  ALMANAC_HOME=/srv/operator-svc
  ALMANAC_REPO_DIR=/srv/operator-svc/almanac
  ALMANAC_PRIV_DIR=/srv/operator-svc/almanac-priv
  BACKUP_GIT_AUTHOR_NAME='Existing Backup'
  BACKUP_GIT_AUTHOR_EMAIL='operator-svc@example.test'
  NEXTCLOUD_ADMIN_USER='operator'
  NEXTCLOUD_ADMIN_PASSWORD='keep-me'
  return 0
}}
MODE=write-config
collect_install_answers
printf 'ALMANAC_USER=%s\\n' "$ALMANAC_USER"
printf 'ALMANAC_HOME=%s\\n' "$ALMANAC_HOME"
printf 'ALMANAC_REPO_DIR=%s\\n' "$ALMANAC_REPO_DIR"
printf 'ALMANAC_PRIV_DIR=%s\\n' "$ALMANAC_PRIV_DIR"
"""
    result = bash(script)
    expect(result.returncode == 0, f"collect_install_answers case failed: {result.stderr}")
    expect("ALMANAC_USER=operator-svc" in result.stdout, f"expected detected service user default, got: {result.stdout!r}")
    expect("ALMANAC_HOME=/srv/operator-svc" in result.stdout, f"expected detected home default, got: {result.stdout!r}")
    expect("ALMANAC_REPO_DIR=/srv/operator-svc/almanac" in result.stdout, f"expected detected repo default, got: {result.stdout!r}")
    expect("ALMANAC_PRIV_DIR=/srv/operator-svc/almanac-priv" in result.stdout, f"expected detected priv default, got: {result.stdout!r}")
    print("PASS test_collect_install_answers_defaults_to_detected_service_user")


def test_collect_install_answers_does_not_prompt_for_telegram_token_up_front() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "collect_install_answers() {", "collect_remove_answers() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        prompt_log = tmp_path / "prompts.log"
        script = f"""
PROMPT_LOG={shlex.quote(str(prompt_log))}
{snippet}
ask() {{ printf '%s' "${{2:-}}"; }}
ask_yes_no() {{ printf '%s' "${{2:-0}}"; }}
ask_secret() {{ printf '%s' ""; }}
ask_secret_with_default() {{
  printf '%s\\n' "$1" >> "$PROMPT_LOG"
  printf '%s' "${{2:-}}"
}}
ask_secret_keep_default() {{ printf '%s' "${{2:-}}"; }}
normalize_optional_answer() {{ printf '%s' "${{1:-}}"; }}
random_secret() {{ printf '%s' "generated-secret"; }}
detect_tailscale() {{
  TAILSCALE_DNS_NAME=""
  TAILSCALE_IPV4=""
  TAILSCALE_TAILNET=""
}}
nextcloud_state_has_existing_data() {{ return 1; }}
read_operator_artifact_hints() {{ return 1; }}
resolve_user_home() {{ return 1; }}
collect_upstream_git_answers() {{
  ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED=0
}}
collect_backup_git_answers() {{
  BACKUP_GIT_REMOTE=""
  BACKUP_GIT_DEPLOY_KEY_PATH=""
  BACKUP_GIT_KNOWN_HOSTS_FILE=""
}}
load_detected_config() {{
  ALMANAC_USER=operator-svc
  ALMANAC_HOME=/srv/operator-svc
  ALMANAC_REPO_DIR=/srv/operator-svc/almanac
  ALMANAC_PRIV_DIR=/srv/operator-svc/almanac-priv
  NEXTCLOUD_ADMIN_USER='operator'
  NEXTCLOUD_ADMIN_PASSWORD='keep-me'
  TELEGRAM_BOT_TOKEN='preserve-me'
  return 0
}}
MODE=write-config
collect_install_answers
printf 'TELEGRAM_BOT_TOKEN=%s\\n' "$TELEGRAM_BOT_TOKEN"
printf 'PROMPTS_BEGIN\\n'
cat "$PROMPT_LOG"
printf 'PROMPTS_END\\n'
"""
        result = bash(script)
        expect(result.returncode == 0, f"telegram prompt suppression case failed: {result.stderr}")
        expect(
            "TELEGRAM_BOT_TOKEN=preserve-me" in result.stdout,
            f"expected existing Telegram token to be preserved, got: {result.stdout!r}",
        )
        prompts = result.stdout.split("PROMPTS_BEGIN\n", 1)[1].split("\nPROMPTS_END", 1)[0]
        expect(
            "Telegram bot token for operator notifications and delivery" not in prompts,
            f"did not expect early Telegram token prompt, got: {prompts!r}",
        )
    print("PASS test_collect_install_answers_does_not_prompt_for_telegram_token_up_front")


def test_secret_prompt_helpers_do_not_prefix_newlines() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "ask_secret() {", "choose_mode() {")
    script = f"""
{snippet}
ask_result="$(ask_secret 'Secret' <<< 'hunter2')"
with_default_result="$(ask_secret_with_default 'Secret' 'keep-me' <<< '')"
keep_default_result="$(ask_secret_keep_default 'Secret' 'keep-me' <<< '')"
printf 'ASK=%q\\n' "$ask_result"
printf 'WITH_DEFAULT=%q\\n' "$with_default_result"
printf 'KEEP_DEFAULT=%q\\n' "$keep_default_result"
"""
    result = bash(script)
    expect(result.returncode == 0, f"secret prompt helper case failed: {result.stderr}")
    expect("ASK=hunter2" in result.stdout, f"expected ask_secret to return plain value, got: {result.stdout!r}")
    expect(
        "WITH_DEFAULT=keep-me" in result.stdout,
        f"expected ask_secret_with_default to keep plain default, got: {result.stdout!r}",
    )
    expect(
        "KEEP_DEFAULT=keep-me" in result.stdout,
        f"expected ask_secret_keep_default to keep plain default, got: {result.stdout!r}",
    )
    expect("$'\\n" not in result.stdout, f"expected no quoted leading newline escapes, got: {result.stdout!r}")
    print("PASS test_secret_prompt_helpers_do_not_prefix_newlines")


def test_collect_install_answers_randomizes_placeholder_passwords() -> None:
    text = DEPLOY_SH.read_text()
    helpers = extract(text, "random_secret() {", "write_kv() {")
    collect = extract(text, "collect_install_answers() {", "collect_remove_answers() {")
    script = f"""
{helpers}
{collect}
ask() {{ printf '%s' "${{2:-}}"; }}
ask_yes_no() {{ printf '%s' "${{2:-0}}"; }}
ask_secret() {{ printf '%s' ""; }}
ask_secret_with_default() {{ printf '%s' "${{2:-}}"; }}
ask_secret_keep_default() {{ printf '%s' "${{2:-}}"; }}
normalize_optional_answer() {{ printf '%s' "${{1:-}}"; }}
detect_tailscale() {{
  TAILSCALE_DNS_NAME=""
  TAILSCALE_IPV4=""
  TAILSCALE_TAILNET=""
}}
nextcloud_state_has_existing_data() {{ return 1; }}
read_operator_artifact_hints() {{ return 1; }}
resolve_user_home() {{ return 1; }}
collect_upstream_git_answers() {{
  ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED=0
}}
collect_backup_git_answers() {{
  BACKUP_GIT_REMOTE=""
  BACKUP_GIT_DEPLOY_KEY_PATH=""
  BACKUP_GIT_KNOWN_HOSTS_FILE=""
}}
load_detected_config() {{
  ALMANAC_USER=operator-svc
  ALMANAC_HOME=/srv/operator-svc
  ALMANAC_REPO_DIR=/srv/operator-svc/almanac
  ALMANAC_PRIV_DIR=/srv/operator-svc/almanac-priv
  POSTGRES_PASSWORD='change-me'
  NEXTCLOUD_ADMIN_PASSWORD='generated-at-deploy'
  NEXTCLOUD_ADMIN_USER='operator'
  return 0
}}
random_secret() {{ printf '%s' "generated-secret"; }}
MODE=write-config
collect_install_answers
printf 'POSTGRES_PASSWORD=%s\\n' "$POSTGRES_PASSWORD"
printf 'NEXTCLOUD_ADMIN_PASSWORD=%s\\n' "$NEXTCLOUD_ADMIN_PASSWORD"
"""
    result = bash(script)
    expect(result.returncode == 0, f"placeholder-password case failed: {result.stderr}")
    expect(
        "POSTGRES_PASSWORD=generated-secret" in result.stdout,
        f"expected placeholder Postgres password to randomize, got: {result.stdout!r}",
    )
    expect(
        "NEXTCLOUD_ADMIN_PASSWORD=generated-secret" in result.stdout,
        f"expected placeholder Nextcloud admin password to randomize, got: {result.stdout!r}",
    )
    expect("change-me" not in result.stdout, f"expected placeholders to be replaced, got: {result.stdout!r}")
    print("PASS test_collect_install_answers_randomizes_placeholder_passwords")


def test_collect_install_answers_preserves_placeholder_passwords_during_stateful_repair() -> None:
    text = DEPLOY_SH.read_text()
    helpers = extract(text, "random_secret() {", "write_kv() {")
    collect = extract(text, "collect_install_answers() {", "collect_remove_answers() {")
    script = f"""
{helpers}
{collect}
ask() {{ printf '%s' "${{2:-}}"; }}
ask_yes_no() {{
  case "$1" in
    *Wipe\\ existing\\ Nextcloud\\ state*) printf '%s' 0 ;;
    *) printf '%s' "${{2:-0}}" ;;
  esac
}}
ask_secret() {{ printf '%s' ""; }}
ask_secret_with_default() {{ printf '%s' "${{2:-}}"; }}
ask_secret_keep_default() {{ printf '%s' "${{2:-}}"; }}
normalize_optional_answer() {{ printf '%s' "${{1:-}}"; }}
detect_tailscale() {{
  TAILSCALE_DNS_NAME=""
  TAILSCALE_IPV4=""
  TAILSCALE_TAILNET=""
}}
nextcloud_state_has_existing_data() {{ return 0; }}
read_operator_artifact_hints() {{ return 1; }}
resolve_user_home() {{ return 1; }}
collect_upstream_git_answers() {{
  ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED=0
}}
collect_backup_git_answers() {{
  BACKUP_GIT_REMOTE=""
  BACKUP_GIT_DEPLOY_KEY_PATH=""
  BACKUP_GIT_KNOWN_HOSTS_FILE=""
}}
load_detected_config() {{
  ALMANAC_USER=operator-svc
  ALMANAC_HOME=/srv/operator-svc
  ALMANAC_REPO_DIR=/srv/operator-svc/almanac
  ALMANAC_PRIV_DIR=/srv/operator-svc/almanac-priv
  POSTGRES_PASSWORD='change-me'
  NEXTCLOUD_ADMIN_PASSWORD='change-me'
  NEXTCLOUD_ADMIN_USER='operator'
  return 0
}}
random_secret() {{ printf '%s' "generated-secret"; }}
MODE=install
collect_install_answers
printf 'POSTGRES_PASSWORD=%s\\n' "$POSTGRES_PASSWORD"
printf 'NEXTCLOUD_ADMIN_PASSWORD=%s\\n' "$NEXTCLOUD_ADMIN_PASSWORD"
"""
    result = bash(script)
    expect(result.returncode == 0, f"stateful-repair placeholder case failed: {result.stderr}")
    expect(
        "POSTGRES_PASSWORD=change-me" in result.stdout,
        f"expected stateful repair to preserve existing Postgres password, got: {result.stdout!r}",
    )
    expect(
        "NEXTCLOUD_ADMIN_PASSWORD=change-me" in result.stdout,
        f"expected stateful repair to preserve existing Nextcloud admin password, got: {result.stdout!r}",
    )
    expect(
        "generated-secret" not in result.stdout,
        f"expected no random rotation during stateful repair, got: {result.stdout!r}",
    )
    print("PASS test_collect_install_answers_preserves_placeholder_passwords_during_stateful_repair")


def test_collect_install_answers_guides_backup_remote_setup() -> None:
    text = DEPLOY_SH.read_text()
    helpers = extract(text, "github_owner_repo_from_remote() {", "collect_install_answers() {")
    collect = extract(text, "collect_install_answers() {", "collect_remove_answers() {")
    expect("require_private_github_backup_remote() {" in helpers, "deploy install must define the backup visibility guard before collect_install_answers")
    script = f"""
{helpers}
{collect}
github_repo_visibility() {{ printf '%s' private; }}
ask() {{
  case "$1" in
    GitHub\\ owner/repo\\ for\\ almanac-priv\\ backup*) printf '%s' 'acme/almanac-priv' ;;
    *) printf '%s' "${{2:-}}" ;;
  esac
}}
ask_yes_no() {{ printf '%s' "${{2:-0}}"; }}
ask_secret() {{ printf '%s' ""; }}
ask_secret_with_default() {{ printf '%s' "${{2:-}}"; }}
ask_secret_keep_default() {{ printf '%s' "${{2:-}}"; }}
normalize_optional_answer() {{ printf '%s' "${{1:-}}"; }}
random_secret() {{ printf '%s' "generated-secret"; }}
detect_tailscale() {{
  TAILSCALE_DNS_NAME=""
  TAILSCALE_IPV4=""
  TAILSCALE_TAILNET=""
}}
nextcloud_state_has_existing_data() {{ return 1; }}
read_operator_artifact_hints() {{ return 1; }}
resolve_user_home() {{ return 1; }}
load_detected_config() {{
  ALMANAC_USER=operator-svc
  ALMANAC_HOME=/srv/operator-svc
  ALMANAC_REPO_DIR=/srv/operator-svc/almanac
  ALMANAC_PRIV_DIR=/srv/operator-svc/almanac-priv
  NEXTCLOUD_ADMIN_USER='operator'
  NEXTCLOUD_ADMIN_PASSWORD='keep-me'
  return 0
}}
MODE=write-config
collect_install_answers
printf 'BACKUP_GIT_REMOTE=%s\\n' "$BACKUP_GIT_REMOTE"
printf 'BACKUP_GIT_DEPLOY_KEY_PATH=%s\\n' "$BACKUP_GIT_DEPLOY_KEY_PATH"
printf 'BACKUP_GIT_KNOWN_HOSTS_FILE=%s\\n' "$BACKUP_GIT_KNOWN_HOSTS_FILE"
"""
    result = bash(script)
    expect(result.returncode == 0, f"backup-guidance collect_install_answers case failed: {result.stderr}")
    expect(
        "BACKUP_GIT_REMOTE=git@github.com:acme/almanac-priv.git" in result.stdout,
        f"expected GitHub SSH backup remote, got: {result.stdout!r}",
    )
    expect(
        "BACKUP_GIT_DEPLOY_KEY_PATH=/srv/operator-svc/.ssh/almanac-backup-ed25519" in result.stdout,
        f"expected default backup deploy key path, got: {result.stdout!r}",
    )
    expect(
        "BACKUP_GIT_KNOWN_HOSTS_FILE=/srv/operator-svc/.ssh/almanac-backup-known_hosts" in result.stdout,
        f"expected default backup known_hosts path, got: {result.stdout!r}",
    )
    expect(
        "Allow write access" in result.stdout,
        f"expected backup guidance to mention Allow write access, got: {result.stdout!r}",
    )
    print("PASS test_collect_install_answers_guides_backup_remote_setup")


def test_collect_install_answers_guides_upstream_deploy_key_setup() -> None:
    text = DEPLOY_SH.read_text()
    helpers = extract(text, "github_owner_repo_from_remote() {", "collect_install_answers() {")
    collect = extract(text, "collect_install_answers() {", "collect_remove_answers() {")
    script = f"""
{helpers}
{collect}
ask() {{
  case "$1" in
    GitHub\\ owner/repo\\ for\\ Almanac\\ upstream\\ deploy\\ key*) printf '%s' "${{2:-}}" ;;
    *) printf '%s' "${{2:-}}" ;;
  esac
}}
ask_yes_no() {{
  case "$1" in
    Set\\ up\\ an\\ operator\\ deploy\\ key\\ for\\ the\\ Almanac\\ upstream\\ repo*) printf '%s' 1 ;;
    *) printf '%s' "${{2:-0}}" ;;
  esac
}}
ask_secret() {{ printf '%s' ""; }}
ask_secret_with_default() {{ printf '%s' "${{2:-}}"; }}
ask_secret_keep_default() {{ printf '%s' "${{2:-}}"; }}
normalize_optional_answer() {{ printf '%s' "${{1:-}}"; }}
random_secret() {{ printf '%s' "generated-secret"; }}
detect_tailscale() {{
  TAILSCALE_DNS_NAME=""
  TAILSCALE_IPV4=""
  TAILSCALE_TAILNET=""
}}
nextcloud_state_has_existing_data() {{ return 1; }}
read_operator_artifact_hints() {{ return 1; }}
resolve_user_home() {{ return 1; }}
collect_backup_git_answers() {{
  BACKUP_GIT_REMOTE=""
  BACKUP_GIT_DEPLOY_KEY_PATH=""
  BACKUP_GIT_KNOWN_HOSTS_FILE=""
}}
load_detected_config() {{
  ALMANAC_USER=operator-svc
  ALMANAC_HOME=/srv/operator-svc
  ALMANAC_REPO_DIR=/srv/operator-svc/almanac
  ALMANAC_PRIV_DIR=/srv/operator-svc/almanac-priv
  ALMANAC_UPSTREAM_REPO_URL=https://github.com/example/almanac.git
  ALMANAC_UPSTREAM_DEPLOY_KEY_USER=operator-svc
  NEXTCLOUD_ADMIN_USER='operator'
  NEXTCLOUD_ADMIN_PASSWORD='keep-me'
  return 0
}}
MODE=write-config
collect_install_answers
printf 'ALMANAC_UPSTREAM_REPO_URL=%s\\n' "$ALMANAC_UPSTREAM_REPO_URL"
printf 'ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED=%s\\n' "$ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED"
printf 'ALMANAC_UPSTREAM_DEPLOY_KEY_USER=%s\\n' "$ALMANAC_UPSTREAM_DEPLOY_KEY_USER"
printf 'ALMANAC_UPSTREAM_DEPLOY_KEY_PATH=%s\\n' "$ALMANAC_UPSTREAM_DEPLOY_KEY_PATH"
printf 'ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE=%s\\n' "$ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE"
"""
    result = bash(script)
    expect(result.returncode == 0, f"upstream deploy-key collect_install_answers case failed: {result.stderr}")
    expect(
        "ALMANAC_UPSTREAM_REPO_URL=git@github.com:example/almanac.git" in result.stdout,
        f"expected upstream remote to switch to SSH, got: {result.stdout!r}",
    )
    expect("ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED=1" in result.stdout, result.stdout)
    expect("ALMANAC_UPSTREAM_DEPLOY_KEY_USER=operator-svc" in result.stdout, result.stdout)
    expect(
        "ALMANAC_UPSTREAM_DEPLOY_KEY_PATH=/srv/operator-svc/.ssh/almanac-upstream-ed25519" in result.stdout,
        f"expected upstream deploy key under operator/service home, got: {result.stdout!r}",
    )
    expect(
        "ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE=/srv/operator-svc/.ssh/almanac-upstream-known_hosts" in result.stdout,
        f"expected upstream known_hosts path, got: {result.stdout!r}",
    )
    expect(
        "read/write deploy key for operator/agent code pushes" in result.stdout
        and "Allow write access" in result.stdout
        and "almanac-priv backup and per-user Hermes-home backups use separate deploy keys" in result.stdout,
        f"expected upstream deploy-key guidance to require write access and separate backup keys, got: {result.stdout!r}",
    )
    print("PASS test_collect_install_answers_guides_upstream_deploy_key_setup")


def test_upstream_deploy_key_flow_prints_key_and_verifies_read_write_access() -> None:
    text = DEPLOY_SH.read_text()
    expect(
        "Public key to paste into GitHub as a deploy key" in text,
        "upstream deploy-key setup must print the actual public key, not just the .pub path",
    )
    expect(
        "prompt_and_verify_upstream_deploy_key_access" in text
        and "verify_upstream_git_deploy_key_access" in text,
        "upstream deploy-key setup must prompt for GitHub setup and verify access",
    )
    expect(
        'git ls-remote "$remote" HEAD' in text,
        "upstream deploy-key verification must prove read access with git ls-remote",
    )
    expect(
        "-o BatchMode=yes" in text,
        "upstream deploy-key SSH checks must fail closed instead of prompting interactively",
    )
    expect(
        "-o IPQoS=none" in text,
        "upstream deploy-key SSH commands should avoid post-key-exchange stalls seen on some networks",
    )
    expect(
        "git -C \"$tmp_dir\" push --dry-run" in text
        and "Allow write access" in text
        and "dry-run write access" in text,
        "upstream deploy-key verification must prove write access with git push --dry-run",
    )
    expect(
        "ALMANAC_UPSTREAM_DEPLOY_KEY_ACCESS_VERIFIED" in text,
        "upstream deploy-key verification should not prompt twice once it has passed",
    )
    print("PASS test_upstream_deploy_key_flow_prints_key_and_verifies_read_write_access")


def test_upstream_deploy_key_flow_offers_reuse_when_existing_key_already_works() -> None:
    text = DEPLOY_SH.read_text()
    body = extract(
        text,
        "prompt_and_verify_upstream_deploy_key_access() {",
        "\n}\n",
    )
    expect(
        'verify_upstream_git_deploy_key_access >/dev/null 2>&1' in body,
        "prompt_and_verify_upstream_deploy_key_access must verify access silently before prompting the operator",
    )
    expect(
        '"Reuse existing Almanac upstream deploy key"' in body,
        'prompt_and_verify_upstream_deploy_key_access must offer a "Reuse existing" choice when verification already passes',
    )
    reuse_index = body.index('"Reuse existing Almanac upstream deploy key"')
    press_enter_index = body.index('Press ENTER after adding this deploy key')
    expect(
        reuse_index < press_enter_index,
        'the "Reuse existing" prompt must come before the "Press ENTER after adding" prompt so an already-verified key skips the manual paste step',
    )
    expect(
        'rotate_upstream_git_deploy_key_material' in text,
        'a helper must exist to rotate the Almanac upstream deploy key when the operator declines to reuse it',
    )
    rotate_body = extract(
        text,
        "rotate_upstream_git_deploy_key_material() {",
        "\n}\n",
    )
    expect(
        'rm -f --' in rotate_body and 'ensure_upstream_git_deploy_key_material_for_user' in rotate_body,
        "rotate_upstream_git_deploy_key_material must remove old key files and regenerate via the user-scoped ensure helper",
    )
    print("PASS test_upstream_deploy_key_flow_offers_reuse_when_existing_key_already_works")


def test_collect_install_answers_reuses_private_repo_backup_remote_when_config_is_unreadable() -> None:
    text = DEPLOY_SH.read_text()
    helpers = extract(text, "github_owner_repo_from_remote() {", "collect_install_answers() {")
    collect = extract(text, "collect_install_answers() {", "collect_remove_answers() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        priv_dir = tmp_path / "almanac-priv"
        priv_dir.mkdir(parents=True, exist_ok=True)
        run(["git", "init", "-b", "main", str(priv_dir)])
        run(["git", "-C", str(priv_dir), "remote", "add", "origin", "git@github.com:remembered/almanac-priv.git"])
        script = f"""
{helpers}
{collect}
ask() {{
  case "$1" in
    GitHub\\ owner/repo\\ for\\ almanac-priv\\ backup*) printf '%s' "${{2:-}}" ;;
    *) printf '%s' "${{2:-}}" ;;
  esac
}}
ask_yes_no() {{ printf '%s' "${{2:-0}}"; }}
ask_secret() {{ printf '%s' ""; }}
ask_secret_with_default() {{ printf '%s' "${{2:-}}"; }}
ask_secret_keep_default() {{ printf '%s' "${{2:-}}"; }}
normalize_optional_answer() {{ printf '%s' "${{1:-}}"; }}
random_secret() {{ printf '%s' "generated-secret"; }}
detect_tailscale() {{
  TAILSCALE_DNS_NAME=""
  TAILSCALE_IPV4=""
  TAILSCALE_TAILNET=""
}}
nextcloud_state_has_existing_data() {{ return 1; }}
read_operator_artifact_hints() {{ return 1; }}
resolve_user_home() {{ return 1; }}
load_detected_config() {{
  ALMANAC_USER=operator-svc
  ALMANAC_HOME=/srv/operator-svc
  ALMANAC_REPO_DIR=/srv/operator-svc/almanac
  ALMANAC_PRIV_DIR={shlex.quote(str(priv_dir))}
  NEXTCLOUD_ADMIN_USER='operator'
  NEXTCLOUD_ADMIN_PASSWORD='keep-me'
  return 1
}}
MODE=write-config
collect_install_answers
printf 'BACKUP_GIT_REMOTE=%s\\n' "$BACKUP_GIT_REMOTE"
"""
        result = bash(script)
        expect(result.returncode == 0, f"backup remote reuse collect_install_answers case failed: {result.stderr}")
        expect(
            "BACKUP_GIT_REMOTE=git@github.com:remembered/almanac-priv.git" in result.stdout,
            f"expected existing private repo backup remote to be reused, got: {result.stdout!r}",
        )
    print("PASS test_collect_install_answers_reuses_private_repo_backup_remote_when_config_is_unreadable")


def test_require_supported_host_mode_rejects_native_macos_install() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "require_supported_host_mode() {", "collect_host_dependency_answers() {")
    script = f"""
{snippet}
host_supports_full_deploy() {{ return 1; }}
host_is_macos() {{ return 0; }}
host_is_wsl() {{ return 1; }}
require_supported_host_mode install
"""
    result = bash(script)
    expect(result.returncode != 0, "expected native macOS install preflight to fail closed")
    expect("Native macOS is not a supported Almanac host or runtime environment." in result.stderr, result.stderr)
    expect("Helper-only commands like `./deploy.sh write-config`" in result.stderr, result.stderr)
    print("PASS test_require_supported_host_mode_rejects_native_macos_install")


def test_require_supported_host_mode_guides_wsl_without_systemd() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "require_supported_host_mode() {", "collect_host_dependency_answers() {")
    script = f"""
{snippet}
host_supports_full_deploy() {{ return 1; }}
host_is_macos() {{ return 1; }}
host_is_wsl() {{ return 0; }}
require_supported_host_mode install
"""
    result = bash(script)
    expect(result.returncode != 0, "expected WSL install preflight to fail without systemd readiness")
    expect("systemd=true" in result.stderr, result.stderr)
    expect("wsl --shutdown" in result.stderr, result.stderr)
    print("PASS test_require_supported_host_mode_guides_wsl_without_systemd")


def test_collect_install_answers_records_missing_host_dependency_choices() -> None:
    text = DEPLOY_SH.read_text()
    helper = extract(text, "collect_host_dependency_answers() {", "usage() {")
    collect = extract(text, "collect_install_answers() {", "collect_remove_answers() {")
    with tempfile.TemporaryDirectory() as tmp:
        prompt_log = Path(tmp) / "prompts.log"
        script = f"""
PROMPT_LOG={shlex.quote(str(prompt_log))}
{helper}
{collect}
default_home_for_user() {{ printf '/home/%s\\n' "$1"; }}
command_exists() {{
  case "$1" in
    podman|tailscale|dscl|getent) return 1 ;;
    *) command -v "$1" >/dev/null 2>&1 ;;
  esac
}}
ask() {{ printf '%s' "${{2:-}}"; }}
ask_validated_optional() {{ printf '%s' "${{2:-}}"; }}
ask_yes_no() {{
  printf '%s\\n' "$1" >> "$PROMPT_LOG"
  case "$1" in
    Podman\\ is\\ not\\ installed.*|Tailscale\\ is\\ not\\ installed.*) printf '%s' 1 ;;
    *) printf '%s' "${{2:-0}}" ;;
  esac
}}
ask_secret() {{ printf '%s' ""; }}
ask_secret_with_default() {{ printf '%s' "${{2:-}}"; }}
ask_secret_keep_default() {{ printf '%s' "${{2:-}}"; }}
normalize_optional_answer() {{ printf '%s' "${{1:-}}"; }}
preserve_or_randomize_secret() {{ printf '%s' "${{1:-generated-secret}}"; }}
detect_tailscale() {{
  TAILSCALE_DNS_NAME=""
  TAILSCALE_IPV4=""
  TAILSCALE_TAILNET=""
}}
nextcloud_state_has_existing_data() {{ return 1; }}
read_operator_artifact_hints() {{ return 1; }}
resolve_user_home() {{ return 1; }}
collect_upstream_git_answers() {{
  ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED=0
}}
collect_backup_git_answers() {{
  BACKUP_GIT_REMOTE=""
  BACKUP_GIT_DEPLOY_KEY_PATH=""
  BACKUP_GIT_KNOWN_HOSTS_FILE=""
}}
load_detected_config() {{
  ALMANAC_USER=operator-svc
  ALMANAC_HOME=/srv/operator-svc
  ALMANAC_REPO_DIR=/srv/operator-svc/almanac
  ALMANAC_PRIV_DIR=/srv/operator-svc/almanac-priv
  NEXTCLOUD_ADMIN_USER='operator'
  NEXTCLOUD_ADMIN_PASSWORD='keep-me'
  return 0
}}
MODE=install
collect_install_answers
printf 'ALMANAC_INSTALL_PODMAN=%s\\n' "$ALMANAC_INSTALL_PODMAN"
printf 'ALMANAC_INSTALL_TAILSCALE=%s\\n' "$ALMANAC_INSTALL_TAILSCALE"
printf 'PROMPTS_BEGIN\\n'
cat "$PROMPT_LOG"
printf 'PROMPTS_END\\n'
"""
        result = bash(script)
        expect(result.returncode == 0, f"host dependency prompt case failed: {result.stderr}")
        expect("ALMANAC_INSTALL_PODMAN=1" in result.stdout, result.stdout)
        expect("ALMANAC_INSTALL_TAILSCALE=1" in result.stdout, result.stdout)
        prompts = result.stdout.split("PROMPTS_BEGIN\n", 1)[1].split("\nPROMPTS_END", 1)[0]
        expect("Podman is not installed." in prompts, prompts)
        expect("Tailscale is not installed." in prompts, prompts)
    print("PASS test_collect_install_answers_records_missing_host_dependency_choices")


def test_write_answers_file_persists_host_dependency_choices() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "write_answers_file() {", "seed_private_repo() {")
    expect("write_kv ALMANAC_INSTALL_PODMAN" in snippet, snippet)
    expect("write_kv ALMANAC_INSTALL_TAILSCALE" in snippet, snippet)
    print("PASS test_write_answers_file_persists_host_dependency_choices")


def test_deploy_sh_exposes_docker_control_center() -> None:
    text = DEPLOY_SH.read_text()
    expect("deploy.sh docker install" in text, "expected Docker install command in deploy usage")
    expect("Almanac Docker control center" in text, "expected Docker submenu")
    expect('MODE="docker"; DOCKER_DEPLOY_COMMAND="menu"' in text, "expected main menu to route to Docker submenu")
    expect('DOCKER_DEPLOY_COMMAND="notion-migrate"' in text, "expected Docker submenu to route to Notion workspace migration")
    expect('DOCKER_DEPLOY_COMMAND="notion-transfer"' in text, "expected Docker submenu to route to Notion page backup/restore")
    expect("docker-install|docker-upgrade|docker-reconfigure" in text, "expected Docker shortcut aliases")
    expect('local helper="$BOOTSTRAP_DIR/bin/almanac-docker.sh"' in text, "expected deploy.sh to delegate to Docker helper")
    expect("run_docker_install_flow()" in text, "expected idempotent Docker install flow")
    expect("run_docker_reconfigure_flow()" in text, "expected Docker reconfigure flow")
    expect("run_almanac_docker health" in text, "expected Docker install flow to end with health")
    print("PASS test_deploy_sh_exposes_docker_control_center")


def test_deploy_sh_guides_notion_workspace_migration() -> None:
    text = DEPLOY_SH.read_text(encoding="utf-8")
    cleanup = extract(text, "notion_migration_clear_workspace_state() {", "run_notion_migrate_flow() {")
    migration = extract(text, "run_notion_migrate_flow() {", "run_curator_setup_flow() {")
    notion_setup = extract(text, "run_notion_ssot_setup() {", "notion_migration_pause() {")
    expect("deploy.sh notion-migrate" in text, "expected direct notion migration command in usage")
    expect("deploy.sh docker notion-migrate" in text, "expected Docker notion migration command in usage")
    expect("Notion workspace migration" in text, "expected guided Notion migration submenu")
    expect("Retry last migration index sync" in text, "expected migration submenu to offer a recovery path for failed index syncs")
    expect("Type MIGRATE NOTION to continue" in migration, "expected explicit typed migration acknowledgement")
    expect("notion_migration_backup_state" in migration, "expected migration to create private backups")
    expect("notion process-pending" in migration, "expected migration to drain pending Notion events")
    expect("notion_migration_pause_write_surfaces" in migration, "expected migration to pause Notion write surfaces")
    expect("trap notion_migration_restore_paused_services EXIT" in migration, "expected migration to restore paused services if the shell exits")
    expect("trap notion_migration_restore_paused_services RETURN" not in migration, "migration must not use RETURN traps that fire after every helper function")
    expect("ALMANAC_NOTION_MIGRATION_FRESH_DEFAULTS=1" in migration, "expected migration to require fresh Notion URL/token defaults")
    expect("ALMANAC_NOTION_MIGRATION_FORCE_WEBHOOK_RESET=1" in migration, "expected migration to force a fresh webhook handshake")
    expect("Continuing workspace-state cleanup so old Notion identities" in migration, "expected migration to keep clearing old identities if webhook verification stops after config save")
    expect("No Notion webhook public URL is configured; clearing any stored webhook verification token" in migration, "expected migration to clear old webhook tokens when webhooks are disabled")
    expect("notion index-sync --full" in migration, "expected migration to run a full Notion index sync")
    expect("notion_migration_restart_services" in migration, "expected migration to restart shared services")
    expect("notion_migration_repair_state_ownership" in migration, "expected migration to repair state ownership before service-user index sync")
    expect("run_notion_migration_index_sync" in migration, "expected migration to run Notion index sync through the service-user helper")
    expect("run_notion_migration_retry_index_sync" in migration, "expected migration submenu to retry a failed full index sync without rerunning setup")
    expect("DELETE FROM settings WHERE key LIKE 'notion_verification_database%'" in cleanup, "expected verification DB cache to be cleared")
    expect("UPDATE agent_identity" in cleanup and "verification_status = 'unverified'" in cleanup, "expected identities to be reset for re-verification")
    expect("notion_identity_claims" in cleanup and "notion_identity_overrides" in cleanup, "expected Notion identity claims and overrides to be archived/cleared")
    expect("ssot_pending_writes" in cleanup, "expected old workspace pending writes to be archived/cleared")
    expect("notion_webhook_events" in cleanup, "expected old webhook events to be archived/cleared")
    expect("notion_index_documents" in cleanup and "notion-index" in cleanup, "expected old notion-shared index rows/files to be rebuilt")
    expect("ALMANAC_NOTION_MIGRATION_DEFAULT_INDEX_ROOT" in notion_setup, "expected SSOT setup to default indexing to the new root during migration")
    expect("webhook-reset-token" in notion_setup, "expected SSOT setup to clear stale webhook verification during migration")
    expect("run_service_user_cmd \"$ctl_bin\" --json notion index-sync --full --actor \"$actor\"" in text, "expected baremetal migration index sync to run as the Almanac service user")
    expect("env ALMANAC_CONFIG_FILE=\"$CONFIG_TARGET\" \"$BOOTSTRAP_DIR/bin/almanac-ctl\" --json notion index-sync --full" not in migration, "migration must not run qmd-backed index sync as root from the deploy checkout")
    print("PASS test_deploy_sh_guides_notion_workspace_migration")


def test_deploy_sh_guides_notion_page_transfer() -> None:
    text = DEPLOY_SH.read_text(encoding="utf-8")
    transfer = extract(text, "notion_transfer_prepare_context() {", "run_curator_setup_flow() {")
    expect("deploy.sh notion-transfer" in text, "expected direct Notion page transfer command in usage")
    expect("deploy.sh docker notion-transfer" in text, "expected Docker Notion page transfer command in usage")
    expect("Notion page backup / restore" in text, "expected main menu Notion page backup/restore entry")
    expect("Back up then restore" in text, "expected transfer submenu to offer one-pass backup then restore")
    expect("Source root page URL or ID to back up" in text, "expected transfer flow to ask for the source root page")
    expect("Destination parent/root page URL or ID" in text, "expected transfer flow to ask for the destination root/parent page")
    expect("source.token" in text and "dest.token" in text, "expected transfer flow to use private token file defaults")
    expect("--source-token-file" in text and "--dest-token-file" in text, "expected transfer flow to pass token files, not tokens")
    expect("--dry-run" in transfer, "expected transfer restore to dry-run before writing")
    expect("Type RESTORE NOTION to create the destination copy" in transfer, "expected explicit typed restore acknowledgement")
    expect("This creates a new child page under the destination parent" in text, "expected transfer guide to explain non-overwrite behavior")
    print("PASS test_deploy_sh_guides_notion_page_transfer")


def test_notion_ssot_setup_prompt_points_operator_at_shared_home_page() -> None:
    text = DEPLOY_SH.read_text(encoding="utf-8")
    expect(
        "https://www.notion.so/profile/integrations/internal" in text,
        "expected deploy notion-ssot guidance to include the direct Notion internal integrations link",
    )
    expect(
        "Click Create new integration." in text,
        "expected deploy notion-ssot guidance to include the create-new-integration step",
    )
    expect(
        "Name it something like Almanac Curator" in text,
        "expected deploy notion-ssot guidance to suggest a concrete internal integration name",
    )
    expect(
        "turn on every checkbox capability Notion offers on that screen" in text,
        "expected deploy notion-ssot guidance to tell operators to enable all checkbox capabilities",
    )
    expect(
        "for user information, choose Read user information including email addresses" in text,
        "expected deploy notion-ssot guidance to require user info with email addresses for verification",
    )
    expect(
        "click Show and then copy the key." in text,
        "expected deploy notion-ssot guidance to tell operators exactly how to reveal and copy the secret",
    )
    expect(
        "open Manage page access and grant access to the" in text,
        "expected deploy notion-ssot guidance to tell operators to grant page access from the integration itself",
    )
    expect(
        "parent page or Teamspace root Almanac should live under" in text,
        "expected deploy notion-ssot guidance to explain which parent/root to grant in Manage page access",
    )
    expect(
        "new child pages and databases under" in text,
        "expected deploy notion-ssot guidance to explain that child pages inherit access from the granted parent page",
    )
    expect(
        "Almanac cannot press Notion's Manage page access buttons for you via" in text,
        "expected deploy notion-ssot guidance to explain that the Manage page access UI cannot be automated through a supported API",
    )
    expect(
        "Type YES to confirm you understand this Notion access model" in text,
        "expected deploy notion-ssot setup to require an explicit typed acknowledgment of Notion's subtree access model",
    )
    expect(
        "Shared Notion page URL for Almanac (use a normal page, not the workspace Home screen)" in text,
        "expected deploy notion-ssot prompt to steer operators toward a normal page and away from the workspace Home screen",
    )
    expect(
        "Make one normal Notion page for Almanac" in text,
        "expected deploy notion-ssot guidance to tell operators to create a normal Almanac page first",
    )
    expect(
        "Almanac will use the page you paste below as its shared Notion home" in text,
        "expected deploy notion-ssot guidance to explain the role of the pasted page in simpler language",
    )
    expect(
        "If Notion lands you back in the workspace UI, open your workspace" in text,
        "expected deploy notion-ssot guidance to describe the workspace fallback path operators actually use",
    )
    expect(
        "start at https://www.notion.so/profile/integrations/internal" in text,
        "expected deploy notion-ssot secret prompt to include the direct Notion internal integrations link",
    )
    expect(
        "Notion MCP, GitHub, Slack, Jira, or other partner apps, stop there:" in text,
        "expected deploy notion-ssot guidance to warn operators away from the partner connection gallery",
    )
    print("PASS test_notion_ssot_setup_prompt_points_operator_at_shared_home_page")


def test_notion_ssot_setup_uses_current_checkout_ctl_for_handshake() -> None:
    text = DEPLOY_SH.read_text(encoding="utf-8")
    notion_setup = extract(text, "run_notion_ssot_setup() {", "run_upgrade_flow() {")
    expect(
        '"$BOOTSTRAP_DIR/bin/almanac-ctl" --json notion handshake' in notion_setup,
        "expected notion-ssot setup to use the current checkout's almanac-ctl for handshake",
    )
    expect(
        '"$ALMANAC_REPO_DIR/bin/almanac-ctl" --json notion handshake' not in notion_setup,
        "expected notion-ssot setup not to depend on an older deployed almanac-ctl during handshake",
    )
    expect(
        '--space-url "$notion_space_url"' in notion_setup,
        "expected notion-ssot setup to pass the shared Notion URL to handshake explicitly",
    )
    expect(
        '--token-file "$notion_token_file"' in notion_setup,
        "expected notion-ssot setup to pass the integration secret through a private token file",
    )
    expect(
        '--token "$notion_token"' not in notion_setup,
        "expected notion-ssot setup not to expose the integration secret in process argv",
    )
    expect(
        '--api-version "$notion_api_version"' in notion_setup,
        "expected notion-ssot setup to pass the Notion API version to handshake explicitly",
    )
    expect(
        '"$BOOTSTRAP_DIR/bin/almanac-ctl" --json notion preflight-root' in notion_setup,
        "expected notion-ssot setup to preflight child page/database creation under the resolved root page",
    )
    expect(
        '--root-page-id "$root_page_id"' in notion_setup,
        "expected notion-ssot setup to pass the resolved root page id explicitly to the preflight check",
    )
    expect(
        'ALMANAC_SSOT_NOTION_ROOT_PAGE_URL="$root_page_url"' in notion_setup,
        "expected notion-ssot setup to persist the resolved Notion root page URL",
    )
    expect(
        'ALMANAC_SSOT_NOTION_ROOT_PAGE_ID="$root_page_id"' in notion_setup,
        "expected notion-ssot setup to persist the resolved Notion root page id",
    )
    print("PASS test_notion_ssot_setup_uses_current_checkout_ctl_for_handshake")


def test_nextcloud_rotation_uses_secret_files_instead_of_password_argv() -> None:
    text = DEPLOY_SH.read_text(encoding="utf-8")
    rotate = extract(text, "run_rotate_nextcloud_secrets() {", "run_notion_ssot_setup() {")
    expect(
        "NEXTCLOUD_ROTATE_POSTGRES_PASSWORD_FILE" in rotate,
        "expected Nextcloud rotation to pass the Postgres password through a private file",
    )
    expect(
        "NEXTCLOUD_ROTATE_ADMIN_PASSWORD_FILE" in rotate,
        "expected Nextcloud rotation to pass the admin password through a private file",
    )
    expect(
        "NEXTCLOUD_ROTATE_POSTGRES_PASSWORD=$pg_q" not in rotate,
        "expected Nextcloud rotation not to expose the Postgres password in process argv",
    )
    expect(
        "NEXTCLOUD_ROTATE_ADMIN_PASSWORD=$admin_q" not in rotate,
        "expected Nextcloud rotation not to expose the admin password in process argv",
    )
    print("PASS test_nextcloud_rotation_uses_secret_files_instead_of_password_argv")


def test_shell_scripts_avoid_bash4_only_features() -> None:
    case_mod = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*(?:\[[^]]+\])?(?:,{1,2}|\^{1,2})\}")
    for path in sorted((REPO / "bin").glob("*.sh")):
        text = path.read_text(encoding="utf-8")
        expect("mapfile" not in text, f"expected {path} to avoid bash-4-only mapfile")
        expect("readarray" not in text, f"expected {path} to avoid bash-4-only readarray")
        expect("declare -A" not in text, f"expected {path} to avoid bash-4-only associative arrays")
        match = case_mod.search(text)
        if match is not None:
            raise AssertionError(
                f"expected {path} to avoid bash-4-only case-modifying expansion; found {match.group(0)!r}"
            )
    print("PASS test_shell_scripts_avoid_bash4_only_features")


def test_deploy_reapplies_runtime_access_after_repo_sync() -> None:
    text = DEPLOY_SH.read_text()
    bootstrap_system = BOOTSTRAP_SYSTEM_SH.read_text(encoding="utf-8")
    refresh_helper = (REPO / "bin" / "refresh-agent-install.sh").read_text(encoding="utf-8")
    helper = extract(text, "realign_active_enrolled_agents_root() {", "chown_managed_paths() {")
    chown_helper = extract(text, "chown_managed_paths() {", "enrollment_snapshot_json() {")
    org_profile_apply = extract(text, "apply_org_profile_if_present_root() {", "seed_private_repo() {")
    install = extract(text, "run_root_install() {", "run_root_upgrade() {")
    upgrade = extract(text, "run_root_upgrade() {", "run_root_remove() {")
    enrollment_align = extract(text, "run_enrollment_align() {", "run_enrollment_reset() {")
    expect(
        'user sync-access "$unix_user" --agent-id "$agent_id"' in helper,
        "active-agent realignment should reapply per-user runtime access before running user-owned services",
    )
    expect(
        'refresh-agent-install.sh' in helper,
        "active-agent realignment should reinstall user-owned Hermes assets and services",
    )
    daemon_reload_index = refresh_helper.find('daemon-reload')
    refresh_start_index = refresh_helper.find('start almanac-user-agent-refresh.service')
    expect(
        daemon_reload_index >= 0 and refresh_start_index >= 0 and daemon_reload_index < refresh_start_index,
        "refresh-agent-install should reload the user manager before starting/restarting user units",
    )
    expect(
        'rm -f "$timer_path"' in refresh_helper
        and 'disable --now almanac-user-agent-backup.timer' in refresh_helper,
        "refresh-agent-install should disable and remove the legacy systemd backup timer during active-agent realignment",
    )
    expect(
        "ensure_gateway_home_channel_env" in refresh_helper
        and "DISCORD_HOME_CHANNEL" in refresh_helper
        and "TELEGRAM_HOME_CHANNEL" in refresh_helper,
        "refresh-agent-install should repair gateway home-channel env from enrollment state",
    )
    expect(
        "TELEGRAM_REACTIONS" in refresh_helper
        and "DISCORD_REACTIONS" in refresh_helper,
        "refresh-agent-install should keep messaging reactions enabled by default",
    )
    expect(
        refresh_helper.index('"TELEGRAM_REACTIONS": "true"')
        < refresh_helper.index('home_channel = state.get("home_channel")'),
        "refresh-agent-install should write reaction defaults even when old state lacks a messaging home_channel",
    )
    expect(
        "ensure_gateway_running_without_interrupting_active_turns" in refresh_helper
        and "is-active almanac-user-agent-gateway.service" in refresh_helper
        and 'if [[ "$RESTART_GATEWAY" == "1" ]]' in refresh_helper
        and "restart deferred to avoid interrupting user work" in refresh_helper,
        "refresh-agent-install should defer active gateway restarts unless explicitly told the shared runtime changed",
    )
    expect(
        "--restart-gateway" in refresh_helper
        and "Hermes gateway runtime restart" in refresh_helper,
        "refresh-agent-install should support an explicit runtime-upgrade gateway restart path",
    )
    expect(
        "ensure_systemd_bundled_skills_env" in refresh_helper
        and "HERMES_BUNDLED_SKILLS" in refresh_helper
        and 'RESTART_GATEWAY="1"' in refresh_helper
        and "added Hermes bundled skills source" in refresh_helper,
        "refresh-agent-install should repair old user service units and restart gateways when the bundled skills env is added",
    )
    expect(
        'restart almanac-user-agent-code.service' in refresh_helper
        and 'code workspace' in refresh_helper,
        "refresh-agent-install should restart the code workspace so launcher/mount fixes take effect",
    )
    expect(
        "shared_hermes_runtime_commit" in text
        and "report_shared_hermes_runtime_transition" in text
        and "gateway_restart_policy" in helper,
        "active-agent realignment should have an explicit Hermes-runtime transition policy",
    )
    expect(
        'git -c safe.directory="$repo_dir" -C "$repo_dir" rev-parse HEAD' in text,
        "root deploy should compare the managed Hermes checkout without tripping Git dubious-ownership protection",
    )
    expect(
        "update_agent_display_name" in helper,
        "active-agent realignment should keep the stored agent display name aligned with the saved bot label",
    )
    expect(
        "repair_active_agent_runtime_access" in install,
        "run_root_install should repair enrolled-user runtime access after syncing the shared repo",
    )
    expect(
        "hermes_runtime_before" in install
        and "hermes_runtime_after" in install
        and 'gateway_restart_policy="restart"' in install
        and 'realign_active_enrolled_agents_root "$gateway_restart_policy"' in install,
        "run_root_install should restart enrolled gateways only when the shared Hermes runtime commit changes",
    )
    expect(
        "chown_managed_paths" in install,
        "run_root_install should use the scoped ownership helper instead of blanket chowning private state",
    )
    expect(
        "repair_active_agent_runtime_access" in upgrade,
        "run_root_upgrade should repair enrolled-user runtime access after syncing the shared repo",
    )
    expect(
        "hermes_runtime_before" in upgrade
        and "hermes_runtime_after" in upgrade
        and 'gateway_restart_policy="restart"' in upgrade
        and 'realign_active_enrolled_agents_root "$gateway_restart_policy"' in upgrade,
        "run_root_upgrade should restart enrolled gateways only when the shared Hermes runtime commit changes",
    )
    expect(
        "chown_managed_paths" in upgrade,
        "run_root_upgrade should use the scoped ownership helper instead of blanket chowning private state",
    )
    expect(
        "run_service_user_cmd" in org_profile_apply and "run_root_env_cmd" not in org_profile_apply,
        "org-profile apply should run as the service user so generated vault/state files remain rootless-service writable",
    )
    expect(
        'find "$ALMANAC_PRIV_DIR" -ignore_readdir_race' in chown_helper
        and "*.sqlite3-shm" in chown_helper
        and "*.sqlite3-wal" in chown_helper,
        "scoped ownership repair should tolerate transient SQLite sidecar files during live upgrades",
    )
    expect(
        "chown -hR" in chown_helper and "-exec chown -h" in chown_helper and "chown -hR" in bootstrap_system,
        "install ownership repair should not dereference stale or broken vault symlinks",
    )
    expect(
        "realign_active_enrolled_agents_root" in enrollment_align,
        "run_enrollment_align should reuse the shared active-agent realignment helper",
    )
    print("PASS test_deploy_reapplies_runtime_access_after_repo_sync")


def test_curator_gateway_defaults_reactions_on() -> None:
    text = CURATOR_GATEWAY_SH.read_text(encoding="utf-8")
    expect('export TELEGRAM_REACTIONS="${TELEGRAM_REACTIONS:-true}"' in text, text)
    expect('export DISCORD_REACTIONS="${DISCORD_REACTIONS:-true}"' in text, text)
    print("PASS test_curator_gateway_defaults_reactions_on")


def test_mcp_exposes_user_owned_ssot_preflight_and_approval_tools() -> None:
    server_text = (REPO / "python" / "almanac_mcp_server.py").read_text(encoding="utf-8")
    expect('"ssot.preflight"' in server_text, "agents should be able to check Notion writeability before writing")
    expect('"ssot.approve"' in server_text and '"ssot.deny"' in server_text, "queued Notion writes should be user-approvable by the agent lane")
    expect("approve_ssot_pending_write(" in server_text, "MCP ssot.approve should apply queued writes")
    expect("deny_ssot_pending_write(" in server_text, "MCP ssot.deny should deny queued writes")
    expect("str(row.get(\"agent_id\") or \"\") != agent_id" in server_text, "MCP approval tools must stay scoped to the caller's own pending writes")
    print("PASS test_mcp_exposes_user_owned_ssot_preflight_and_approval_tools")


def test_control_py_discovers_artifact_priv_dir_config() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_artifact_discovery")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        priv_dir = tmp_path / "deployed" / "almanac-priv"
        config_path = priv_dir / "config" / "almanac.env"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("ALMANAC_USER=operator-svc\n", encoding="utf-8")
        artifact_path = tmp_path / ".almanac-operator.env"
        artifact_path.write_text(
            "\n".join(
                [
                    "ALMANAC_OPERATOR_DEPLOYED_USER=operator-svc",
                    f"ALMANAC_OPERATOR_DEPLOYED_PRIV_DIR={shlex.quote(str(priv_dir))}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        old_env = os.environ.copy()
        try:
            os.environ.pop("ALMANAC_CONFIG_FILE", None)
            os.environ["ALMANAC_REPO_DIR"] = str(repo_root)
            os.environ["ALMANAC_OPERATOR_ARTIFACT_FILE"] = str(artifact_path)
            discovered = mod._discover_config_file()
        finally:
            os.environ.clear()
            os.environ.update(old_env)

        expect(discovered == config_path, f"expected control module to discover {config_path}, got {discovered!r}")
    print("PASS test_control_py_discovers_artifact_priv_dir_config")


def test_sync_public_repo_preserves_template_almanac_priv_while_excluding_top_level_private_repo() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "sync_public_repo_from_source() {", "git_head_commit() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        source_dir = tmp_path / "source"
        target_dir = tmp_path / "target"
        (source_dir / "almanac-priv").mkdir(parents=True)
        (source_dir / "almanac-priv" / "secret.txt").write_text("should-not-copy\n", encoding="utf-8")
        (source_dir / "templates" / "almanac-priv" / "vault" / "Research").mkdir(parents=True)
        (source_dir / "templates" / "almanac-priv" / "vault" / "Research" / ".vault").write_text("name: Research\n", encoding="utf-8")
        (source_dir / "bin").mkdir(parents=True)
        (source_dir / "bin" / "bootstrap-userland.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (source_dir / ".git").write_text("gitdir: /tmp/not-for-deploy\n", encoding="utf-8")
        script = f"""
{snippet}
sync_public_repo_from_source {shlex.quote(str(source_dir))} {shlex.quote(str(target_dir))}
if [[ -e {shlex.quote(str(target_dir / 'almanac-priv'))} ]]; then
  echo 'TOP_LEVEL_PRIVATE_PRESENT=1'
else
  echo 'TOP_LEVEL_PRIVATE_PRESENT=0'
fi
if [[ -f {shlex.quote(str(target_dir / 'templates' / 'almanac-priv' / 'vault' / 'Research' / '.vault'))} ]]; then
  echo 'TEMPLATE_PRIVATE_PRESENT=1'
else
  echo 'TEMPLATE_PRIVATE_PRESENT=0'
fi
if [[ -e {shlex.quote(str(target_dir / '.git'))} ]]; then
  echo 'GIT_POINTER_PRESENT=1'
else
  echo 'GIT_POINTER_PRESENT=0'
fi
"""
        result = bash(script)
        expect(result.returncode == 0, f"sync_public_repo_from_source case failed: {result.stderr}")
        expect("TOP_LEVEL_PRIVATE_PRESENT=0" in result.stdout, result.stdout)
        expect("TEMPLATE_PRIVATE_PRESENT=1" in result.stdout, result.stdout)
        expect("GIT_POINTER_PRESENT=0" in result.stdout, result.stdout)
    print("PASS test_sync_public_repo_preserves_template_almanac_priv_while_excluding_top_level_private_repo")


def test_sync_public_repo_repairs_existing_git_metadata_from_source() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "sync_public_repo_from_source() {", "git_head_commit() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        source_dir = tmp_path / "source"
        target_dir = tmp_path / "target"
        source_dir.mkdir()
        target_dir.mkdir()
        subprocess.run(["git", "init", "-b", "main", str(source_dir)], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(source_dir), "config", "user.name", "Almanac Test"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(source_dir), "config", "user.email", "almanac-test@example.com"], check=True, capture_output=True, text=True)
        (source_dir / "README.md").write_text("ready\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(source_dir), "add", "README.md"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(source_dir), "commit", "-m", "ready"], check=True, capture_output=True, text=True)
        source_head = subprocess.run(
            ["git", "-C", str(source_dir), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        # This mirrors the bad live shape we found: an initialized target repo
        # with no commits. Sync should not preserve that orphaned metadata.
        subprocess.run(["git", "init", "-b", "main", str(target_dir)], check=True, capture_output=True, text=True)
        script = f"""
{snippet}
sync_public_repo_from_source {shlex.quote(str(source_dir))} {shlex.quote(str(target_dir))}
git -C {shlex.quote(str(target_dir))} rev-parse HEAD
"""
        result = bash(script)
        expect(result.returncode == 0, f"sync_public_repo_from_source should repair target git metadata: {result.stderr}")
        expect(source_head in result.stdout, result.stdout)
    print("PASS test_sync_public_repo_repairs_existing_git_metadata_from_source")


def test_sync_public_repo_copies_git_metadata_when_public_git_requested() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "sync_public_repo_from_source() {", "git_head_commit() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        source_dir = tmp_path / "source"
        target_dir = tmp_path / "target"
        source_dir.mkdir()
        subprocess.run(["git", "init", "-b", "main", str(source_dir)], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(source_dir), "config", "user.name", "Almanac Test"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(source_dir), "config", "user.email", "almanac-test@example.com"], check=True, capture_output=True, text=True)
        (source_dir / "README.md").write_text("ready\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(source_dir), "add", "README.md"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(source_dir), "commit", "-m", "ready"], check=True, capture_output=True, text=True)
        source_head = subprocess.run(
            ["git", "-C", str(source_dir), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        script = f"""
{snippet}
ALMANAC_INSTALL_PUBLIC_GIT=1 sync_public_repo_from_source {shlex.quote(str(source_dir))} {shlex.quote(str(target_dir))}
git -C {shlex.quote(str(target_dir))} rev-parse HEAD
"""
        result = bash(script)
        expect(result.returncode == 0, f"sync_public_repo_from_source should copy git metadata when requested: {result.stderr}")
        expect(source_head in result.stdout, result.stdout)
    print("PASS test_sync_public_repo_copies_git_metadata_when_public_git_requested")


def test_enrollment_reset_supports_full_forget_purge() -> None:
    text = DEPLOY_SH.read_text()
    reset = extract(text, "run_enrollment_reset() {", "run_health_check() {")
    expect(
        "Forget completed enrollment history and local app accounts so this user can onboard as new" in reset,
        "expected enrollment reset flow to offer a full forget-history purge path",
    )
    expect(
        '"$ALMANAC_REPO_DIR/bin/almanac-ctl"' in reset and "purge-enrollment" in reset,
        "expected enrollment reset flow to call almanac-ctl user purge-enrollment",
    )
    expect(
        "--remove-nextcloud-user" in reset,
        "expected full purge path to support removing the matching Nextcloud user",
    )
    print("PASS test_enrollment_reset_supports_full_forget_purge")


def test_enrollment_align_reseeds_agent_identity() -> None:
    text = DEPLOY_SH.read_text()
    helper = (REPO / "bin" / "refresh-agent-install.sh").read_text(encoding="utf-8")
    align = extract(text, "run_enrollment_align() {", "run_enrollment_reset() {")
    expect("realign_active_enrolled_agents_root" in align, align)
    expect("--identity-only" in helper, "expected refresh-agent-install to run headless identity reseed")
    expect("--user-name" in helper, "expected refresh-agent-install identity reseed to pass the saved user name")
    expect("SELECT linked_agent_id, answers_json, sender_display_name" in text, text)
    expect("ALMANAC_ORG_NAME" in text, "expected deploy config to persist org interview fields")
    print("PASS test_enrollment_align_reseeds_agent_identity")


def test_root_install_and_upgrade_do_not_globally_export_runtime_secrets() -> None:
    text = DEPLOY_SH.read_text()
    install = extract(text, "run_root_install() {", "run_root_upgrade() {")
    upgrade = extract(text, "run_root_upgrade() {", "run_root_remove() {")
    expect("export POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD" not in install, install)
    expect("export NEXTCLOUD_ADMIN_USER NEXTCLOUD_ADMIN_PASSWORD" not in install, install)
    expect('env \\' in install and '"$BOOTSTRAP_DIR/bin/bootstrap-system.sh"' in install, install)
    expect("export POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD" not in upgrade, upgrade)
    expect("export NEXTCLOUD_ADMIN_USER NEXTCLOUD_ADMIN_PASSWORD" not in upgrade, upgrade)
    expect('env \\' in upgrade and '"$ALMANAC_REPO_DIR/bin/bootstrap-system.sh"' in upgrade, upgrade)
    print("PASS test_root_install_and_upgrade_do_not_globally_export_runtime_secrets")


def test_bootstrap_system_supports_optional_podman_and_tailscale_install() -> None:
    text = (REPO / "bin" / "bootstrap-system.sh").read_text(encoding="utf-8")
    expect("install_podman_if_requested()" in text, text)
    expect("install_tailscale_if_requested()" in text, text)
    expect("curl -fsSL https://tailscale.com/install.sh | sh" in text, text)
    expect("systemd=true" in text and "wsl --shutdown" in text, text)
    print("PASS test_bootstrap_system_supports_optional_podman_and_tailscale_install")


def test_bootstrap_userland_avoids_legacy_remote_qmd_skill_fetch() -> None:
    text = (REPO / "bin" / "bootstrap-userland.sh").read_text(encoding="utf-8")
    expect("official/research/qmd" not in text, text)
    expect("ensure_shared_hermes_runtime" in text, text)
    print("PASS test_bootstrap_userland_avoids_legacy_remote_qmd_skill_fetch")


def test_install_system_services_includes_independent_notion_claim_poller() -> None:
    text = INSTALL_SYSTEM_SERVICES_SH.read_text(encoding="utf-8")
    expect("almanac-notion-claim-poll.service" in text, "expected dedicated notion claim poll service")
    expect("almanac-notion-claim-poll.timer" in text, "expected dedicated notion claim poll timer")
    expect("--claims-only" in text, "expected claim poller to use provisioner claims-only mode")
    expect("OnUnitActiveSec=2m" in text, "expected claim poll cadence to be configured")
    print("PASS test_install_system_services_includes_independent_notion_claim_poller")


def test_install_system_services_units_pass_systemd_analyze_verify() -> None:
    systemd_analyze = shutil.which("systemd-analyze")
    if not systemd_analyze:
        print("PASS test_install_system_services_units_pass_systemd_analyze_verify (skipped: systemd-analyze unavailable)")
        return
    text = INSTALL_SYSTEM_SERVICES_SH.read_text(encoding="utf-8")
    enrollment_service = extract_heredoc(text, 'cat >"$TARGET_DIR/almanac-enrollment-provision.service" <<EOF')
    enrollment_timer = extract_heredoc(text, 'cat >"$TARGET_DIR/almanac-enrollment-provision.timer" <<EOF')
    claim_service = extract_heredoc(text, 'cat >"$TARGET_DIR/almanac-notion-claim-poll.service" <<EOF')
    claim_timer = extract_heredoc(text, 'cat >"$TARGET_DIR/almanac-notion-claim-poll.timer" <<EOF')

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo_dir = root / "repo"
        (repo_dir / "bin").mkdir(parents=True, exist_ok=True)
        provision_script = repo_dir / "bin" / "almanac-enrollment-provision.sh"
        provision_script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        provision_script.chmod(0o755)
        replacements = {
            "$CONFIG_PATH": str(root / "almanac.env"),
            "$ALMANAC_REPO_DIR": str(repo_dir),
        }

        def materialize(content: str) -> str:
            rendered = content
            for needle, value in replacements.items():
                rendered = rendered.replace(needle, value)
            return rendered

        service_path = root / "almanac-enrollment-provision.service"
        timer_path = root / "almanac-enrollment-provision.timer"
        claim_service_path = root / "almanac-notion-claim-poll.service"
        claim_timer_path = root / "almanac-notion-claim-poll.timer"
        service_path.write_text(materialize(enrollment_service) + "\n", encoding="utf-8")
        timer_path.write_text(materialize(enrollment_timer) + "\n", encoding="utf-8")
        claim_service_path.write_text(materialize(claim_service) + "\n", encoding="utf-8")
        claim_timer_path.write_text(materialize(claim_timer) + "\n", encoding="utf-8")
        result = run(
            [
                systemd_analyze,
                "verify",
                str(service_path),
                str(timer_path),
                str(claim_service_path),
                str(claim_timer_path),
            ]
        )
        expect(result.returncode == 0, f"systemd-analyze verify failed: {result.stderr or result.stdout}")
    print("PASS test_install_system_services_units_pass_systemd_analyze_verify")


def test_upgrade_fetch_is_noninteractive_and_requires_deploy_key_for_ssh() -> None:
    text = DEPLOY_SH.read_text()
    checkout = extract(text, "checkout_upstream_release() {", "write_operator_checkout_artifact() {")
    expect("GIT_TERMINAL_PROMPT=0" in checkout, checkout)
    expect("GIT_ASKPASS=/bin/false" in checkout, checkout)
    expect("SSH_ASKPASS=/bin/false" in checkout, checkout)
    expect("GCM_INTERACTIVE=Never" in checkout, checkout)
    expect("Refusing SSH upstream without the Almanac upstream deploy-key lane enabled" in checkout, checkout)
    print("PASS test_upgrade_fetch_is_noninteractive_and_requires_deploy_key_for_ssh")


def test_upgrade_refuses_non_main_branch_without_explicit_override() -> None:
    text = DEPLOY_SH.read_text()
    guard = extract(text, "require_main_upstream_branch_for_upgrade() {", "write_operator_checkout_artifact() {")
    upgrade = extract(text, "run_root_upgrade() {", "run_root_remove() {")
    flow = extract(text, "run_upgrade_flow() {", "run_agent_payload() {")
    expect('ALMANAC_ALLOW_NON_MAIN_UPGRADE:-0' in guard, guard)
    expect("Refusing production upgrade from non-main upstream branch" in guard, guard)
    expect("require_main_upstream_branch_for_upgrade" in upgrade, upgrade)
    expect("require_main_upstream_branch_for_upgrade" in flow, flow)
    print("PASS test_upgrade_refuses_non_main_branch_without_explicit_override")


def test_install_answer_file_has_exit_trap_cleanup() -> None:
    text = DEPLOY_SH.read_text()
    install_flow = extract(text, "run_install_flow() {", "run_remove_flow() {")
    remove_flow = extract(text, "run_remove_flow() {", 'if [[ -n "$PRIVILEGED_MODE" ]]; then')
    expect("mktemp /tmp/almanac-install" in install_flow and "trap 'rm -f" in install_flow, install_flow)
    expect("mktemp /tmp/almanac-remove" in remove_flow and "trap 'rm -f" in remove_flow, remove_flow)
    print("PASS test_install_answer_file_has_exit_trap_cleanup")


def test_health_checks_failed_systemd_units_and_stale_podman_transients() -> None:
    text = HEALTH_SH.read_text()
    expect("check_system_failed_units" in text and "systemctl --failed --no-legend --plain" in text, text)
    expect("check_service_user_failed_units" in text and "systemctl --user --failed --no-legend --plain" in text, text)
    expect("failed_units_are_stale_podman_healthchecks" in text and "systemctl --user reset-failed" in text, text)
    print("PASS test_health_checks_failed_systemd_units_and_stale_podman_transients")


def main() -> int:
    tests = [
        test_bool_env_blank_uses_default,
        test_emit_runtime_config_normalizes_curator_onboarding_flags,
        test_emit_runtime_config_syncs_agent_tailscale_serve_with_global_flag,
        test_emit_runtime_config_migrates_legacy_vault_watch_debounce,
        test_emit_runtime_config_persists_notion_ssot_fields,
        test_emit_runtime_config_persists_hermes_docs_sync_fields,
        test_emit_runtime_config_preserves_custom_hermes_docs_ref,
        test_emit_runtime_config_persists_extra_mcp_url,
        test_deploy_guides_explicit_notion_webhook_event_selection,
        test_nextcloud_rotation_uses_secret_files_instead_of_password_argv,
        test_json_field_reads_json_payload,
        test_noninteractive_notion_webhook_setup_flow_fails_closed_until_verified,
        test_detect_tailscale_serve_distinguishes_qmd_from_almanac_routes,
        test_path_is_within_and_safe_remove_use_canonical_paths,
        test_run_health_check_falls_back_when_user_bus_is_missing,
        test_install_and_upgrade_run_live_agent_tool_smoke_after_health,
        test_install_and_upgrade_refresh_upgrade_check_before_health,
        test_live_agent_tool_smoke_blocks_broader_python_heredoc_variants,
        test_live_agent_tool_smoke_inspects_private_home_as_target_user,
        test_discord_onboarding_dedupes_message_ids_before_state_transitions,
        test_live_agent_tool_smoke_parses_explicit_selectors,
        test_agent_install_payload_tracks_current_agent_contract,
        test_emit_runtime_config_persists_org_interview_fields,
        test_emit_runtime_config_persists_org_provider_fields,
        test_collect_org_provider_answers_defaults_yes_and_collects_chutes,
        test_org_interview_validators_accept_known_good_values,
        test_org_interview_validators_reject_bad_values,
        test_describe_operator_channel_summary_avoids_tui_only_duplication,
        test_install_reexecs_for_unreadable_breadcrumb_config,
        test_install_does_not_reexec_for_readable_breadcrumb_config,
        test_run_install_flow_stops_after_failed_sudo_reexec,
        test_run_install_flow_stops_after_failed_sudo_reexec_exit_one,
        test_write_operator_artifact_falls_back_to_discovered_config,
        test_discover_existing_config_uses_artifact_priv_dir_hint,
        test_collect_install_answers_defaults_to_detected_service_user,
        test_collect_install_answers_does_not_prompt_for_telegram_token_up_front,
        test_secret_prompt_helpers_do_not_prefix_newlines,
        test_collect_install_answers_randomizes_placeholder_passwords,
        test_collect_install_answers_preserves_placeholder_passwords_during_stateful_repair,
        test_collect_install_answers_guides_backup_remote_setup,
        test_collect_install_answers_guides_upstream_deploy_key_setup,
        test_upstream_deploy_key_flow_prints_key_and_verifies_read_write_access,
        test_upstream_deploy_key_flow_offers_reuse_when_existing_key_already_works,
        test_collect_install_answers_reuses_private_repo_backup_remote_when_config_is_unreadable,
        test_require_supported_host_mode_rejects_native_macos_install,
        test_require_supported_host_mode_guides_wsl_without_systemd,
        test_collect_install_answers_records_missing_host_dependency_choices,
        test_write_answers_file_persists_host_dependency_choices,
        test_deploy_sh_exposes_docker_control_center,
        test_deploy_sh_guides_notion_workspace_migration,
        test_deploy_sh_guides_notion_page_transfer,
        test_shell_scripts_avoid_bash4_only_features,
        test_deploy_reapplies_runtime_access_after_repo_sync,
        test_curator_gateway_defaults_reactions_on,
        test_mcp_exposes_user_owned_ssot_preflight_and_approval_tools,
        test_control_py_discovers_artifact_priv_dir_config,
        test_sync_public_repo_preserves_template_almanac_priv_while_excluding_top_level_private_repo,
        test_sync_public_repo_repairs_existing_git_metadata_from_source,
        test_sync_public_repo_copies_git_metadata_when_public_git_requested,
        test_enrollment_reset_supports_full_forget_purge,
        test_enrollment_align_reseeds_agent_identity,
        test_root_install_and_upgrade_do_not_globally_export_runtime_secrets,
        test_upgrade_fetch_is_noninteractive_and_requires_deploy_key_for_ssh,
        test_upgrade_refuses_non_main_branch_without_explicit_override,
        test_install_answer_file_has_exit_trap_cleanup,
        test_health_checks_failed_systemd_units_and_stale_podman_transients,
        test_bootstrap_system_supports_optional_podman_and_tailscale_install,
        test_bootstrap_userland_avoids_legacy_remote_qmd_skill_fetch,
        test_install_system_services_includes_independent_notion_claim_poller,
        test_install_system_services_units_pass_systemd_analyze_verify,
    ]
    for test in tests:
        test()
    print(f"PASS all {len(tests)} deploy regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
