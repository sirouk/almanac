#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEPLOY_SH = REPO / "bin" / "deploy.sh"
HEALTH_SH = REPO / "bin" / "health.sh"
INSTALL_SYSTEM_SERVICES_SH = REPO / "bin" / "install-system-services.sh"
CI_INSTALL_SMOKE_SH = REPO / "bin" / "ci-install-smoke.sh"
CI_PREFLIGHT_SH = REPO / "bin" / "ci-preflight.sh"
INSTALL_SMOKE_WORKFLOW = REPO / ".github" / "workflows" / "install-smoke.yml"
CURATOR_GATEWAY_SH = REPO / "bin" / "curator-gateway.sh"
QMD_REFRESH_SH = REPO / "bin" / "qmd-refresh.sh"
VAULT_WATCH_SH = REPO / "bin" / "vault-watch.sh"
TAILSCALE_NEXTCLOUD_SERVE_SH = REPO / "bin" / "tailscale-nextcloud-serve.sh"
TAILSCALE_NOTION_FUNNEL_SH = REPO / "bin" / "tailscale-notion-webhook-funnel.sh"
CONTROL_PY = REPO / "python" / "arclink_control.py"
BOOTSTRAP_SYSTEM_SH = REPO / "bin" / "bootstrap-system.sh"
ENSURE_PREREQS_SH = REPO / "bin" / "lib" / "ensure-prereqs.sh"


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
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, prefix="arclink-deploy-regression-", suffix=".sh") as handle:
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
    mod = load_module(CONTROL_PY, "arclink_control_regression")
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
    tailscale_notion_webhook_funnel_port: str = "443",
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
    qmd_embed_provider: str = "local",
    qmd_embed_endpoint: str = "",
    qmd_embed_endpoint_model: str = "",
    qmd_embed_api_key: str = "",
    qmd_embed_dimensions: str = "",
    qmd_embed_force_on_next_refresh: str = "0",
    arclink_base_domain: str = "arclink.example.ts.net",
    arclink_control_private_base_url: str = "",
    arclink_private_dns_name: str = "",
    arclink_tailscale_control_url: str = "",
    telegram_webhook_url: str = "",
    arclink_db_path: str = "",
    arclink_docker_host_priv_dir: str = "",
    arclink_docker_host_repo_dir: str = "",
    executor_allowlist: str = "",
) -> str:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "write_kv() {", "write_runtime_config() {")
    script = f"""
{snippet}
ARCLINK_NAME=arclink
ARCLINK_USER=arclink
ARCLINK_HOME=/home/arclink
ARCLINK_REPO_DIR=/home/arclink/arclink
ARCLINK_PRIV_DIR=/home/arclink/arclink/arclink-priv
ARCLINK_PRIV_CONFIG_DIR=/home/arclink/arclink/arclink-priv/config
ARCLINK_BASE_DOMAIN={shlex.quote(arclink_base_domain)}
ARCLINK_PRIVATE_DNS_NAME={shlex.quote(arclink_private_dns_name)}
ARCLINK_CONTROL_PRIVATE_BASE_URL={shlex.quote(arclink_control_private_base_url)}
ARCLINK_TAILSCALE_CONTROL_URL={shlex.quote(arclink_tailscale_control_url)}
TELEGRAM_WEBHOOK_URL={shlex.quote(telegram_webhook_url)}
VAULT_DIR=/home/arclink/arclink/arclink-priv/vault
STATE_DIR=/home/arclink/arclink/arclink-priv/state
ARCLINK_DB_PATH={shlex.quote(arclink_db_path)}
ARCLINK_DOCKER_HOST_PRIV_DIR={shlex.quote(arclink_docker_host_priv_dir)}
ARCLINK_DOCKER_HOST_REPO_DIR={shlex.quote(arclink_docker_host_repo_dir)}
NEXTCLOUD_STATE_DIR=/home/arclink/arclink/arclink-priv/state/nextcloud
RUNTIME_DIR=/home/arclink/arclink/arclink-priv/state/runtime
PUBLISHED_DIR=/home/arclink/arclink/arclink-priv/published
QMD_INDEX_NAME=arclink
QMD_COLLECTION_NAME=vault
QMD_RUN_EMBED=1
QMD_EMBED_PROVIDER={shlex.quote(qmd_embed_provider)}
QMD_EMBED_ENDPOINT={shlex.quote(qmd_embed_endpoint)}
QMD_EMBED_ENDPOINT_MODEL={shlex.quote(qmd_embed_endpoint_model)}
QMD_EMBED_API_KEY={shlex.quote(qmd_embed_api_key)}
QMD_EMBED_DIMENSIONS={shlex.quote(qmd_embed_dimensions)}
QMD_EMBED_FORCE_ON_NEXT_REFRESH={shlex.quote(qmd_embed_force_on_next_refresh)}
BACKUP_GIT_BRANCH=main
NEXTCLOUD_PORT=18080
NEXTCLOUD_TRUSTED_DOMAIN=arclink.example.ts.net
POSTGRES_DB=nextcloud
POSTGRES_USER=nextcloud
POSTGRES_PASSWORD=dbpass
NEXTCLOUD_ADMIN_USER=admin
NEXTCLOUD_ADMIN_PASSWORD=adminpass
ARCLINK_SSOT_NOTION_ROOT_PAGE_URL={shlex.quote(notion_root_page_url)}
ARCLINK_SSOT_NOTION_ROOT_PAGE_ID={shlex.quote(notion_root_page_id)}
ARCLINK_SSOT_NOTION_SPACE_URL={shlex.quote(notion_space_url)}
ARCLINK_SSOT_NOTION_SPACE_ID={shlex.quote(notion_space_id)}
ARCLINK_SSOT_NOTION_SPACE_KIND={shlex.quote(notion_space_kind)}
ARCLINK_SSOT_NOTION_API_VERSION={shlex.quote(notion_api_version)}
ARCLINK_SSOT_NOTION_TOKEN={shlex.quote(notion_token)}
ARCLINK_NOTION_WEBHOOK_PUBLIC_URL={shlex.quote(notion_public_webhook_url)}
ARCLINK_ORG_NAME={shlex.quote(org_name)}
ARCLINK_ORG_MISSION={shlex.quote(org_mission)}
ARCLINK_ORG_PRIMARY_PROJECT={shlex.quote(org_primary_project)}
ARCLINK_ORG_TIMEZONE={shlex.quote(org_timezone)}
ARCLINK_ORG_QUIET_HOURS={shlex.quote(org_quiet_hours)}
ARCLINK_ORG_PROVIDER_ENABLED={shlex.quote(org_provider_enabled)}
ARCLINK_ORG_PROVIDER_PRESET={shlex.quote(org_provider_preset)}
ARCLINK_ORG_PROVIDER_MODEL_ID={shlex.quote(org_provider_model_id)}
ARCLINK_ORG_PROVIDER_REASONING_EFFORT={shlex.quote(org_provider_reasoning_effort)}
ARCLINK_ORG_PROVIDER_SECRET_PROVIDER={shlex.quote(org_provider_secret_provider)}
ARCLINK_ORG_PROVIDER_SECRET={shlex.quote(org_provider_secret)}
ARCLINK_HERMES_DOCS_REPO_URL={shlex.quote(hermes_docs_repo_url)}
ARCLINK_HERMES_DOCS_REF={shlex.quote(hermes_docs_ref)}
ARCLINK_EXTRA_MCP_URL={shlex.quote(extra_mcp_url)}
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
ARCLINK_CURATOR_CHANNELS={shlex.quote(channels)}
OPERATOR_NOTIFY_CHANNEL_PLATFORM={shlex.quote(notify_platform)}
ARCLINK_EXECUTOR_MACHINE_HOST_ALLOWLIST={shlex.quote(executor_allowlist)}
ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED={shlex.quote(tg_flag)}
ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED={shlex.quote(dc_flag)}
ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE={shlex.quote(agent_enable_tailscale_serve)}
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
  GITHUB_REPO_URL="https://github.com/example/arclink"
  GITHUB_REPO_OWNER_REPO="example/arclink"
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
  AGENT_ARCLINK_MCP_URL="https://agent.example.test/arclink-mcp"
  ARCLINK_MCP_HOST="127.0.0.1"
  ARCLINK_MCP_PORT="8282"
  AGENT_ARCLINK_MCP_URL_MODE="tailnet"
  AGENT_ARCLINK_MCP_ROUTE_STATUS="live"
  TAILSCALE_ARCLINK_MCP_PATH="/arclink-mcp"
}}
ARCLINK_REPO_DIR="/repo"
ARCLINK_MODEL_PRESET_CODEX="openai:codex"
ARCLINK_MODEL_PRESET_OPUS="anthropic:claude-opus"
ARCLINK_MODEL_PRESET_CHUTES="chutes:model-router"
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
    tg = source_value(config, "ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED")
    dc = source_value(config, "ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED")
    expect(tg == "1", f"expected telegram onboarding flag to normalize to 1, got {tg!r}")
    expect(dc == "1", f"expected discord onboarding flag to normalize to 1, got {dc!r}")

    config = render_runtime_config("tui-only", "tui-only", "", "")
    tg = source_value(config, "ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED")
    dc = source_value(config, "ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED")
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
    agent_flag = source_value(config, "ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE")
    expect(agent_flag == "1", f"expected agent tailscale serve flag to follow global enable, got {agent_flag!r}")
    print("PASS test_emit_runtime_config_syncs_agent_tailscale_serve_with_global_flag")


def test_emit_runtime_config_defaults_public_telegram_webhook_to_callback_ready_route() -> None:
    config = render_runtime_config(
        "tui-only",
        "tui-only",
        arclink_base_domain="arclink.example.test",
    )
    expect(
        source_value(config, "TELEGRAM_WEBHOOK_URL") == "https://arclink.example.test/api/v1/webhooks/telegram",
        config,
    )
    config = render_runtime_config(
        "tui-only",
        "tui-only",
        arclink_tailscale_control_url="https://operator.example.ts.net",
    )
    expect(
        source_value(config, "TELEGRAM_WEBHOOK_URL") == "https://operator.example.ts.net/api/v1/webhooks/telegram",
        config,
    )
    config = render_runtime_config(
        "tui-only",
        "tui-only",
        arclink_base_domain="arclink.example.test",
        arclink_private_dns_name="control.wg.internal",
        arclink_control_private_base_url="https://control.wg.internal",
    )
    expect(source_value(config, "ARCLINK_PRIVATE_DNS_NAME") == "control.wg.internal", config)
    expect(source_value(config, "ARCLINK_CONTROL_PRIVATE_BASE_URL") == "https://control.wg.internal", config)
    expect(
        source_value(config, "TELEGRAM_WEBHOOK_URL") == "https://arclink.example.test/api/v1/webhooks/telegram",
        "private mesh control URL must not become the public Telegram webhook URL",
    )
    config = render_runtime_config(
        "tui-only",
        "tui-only",
        arclink_base_domain="arclink.example.test",
        telegram_webhook_url="https://custom.example.test/telegram",
    )
    expect(source_value(config, "TELEGRAM_WEBHOOK_URL") == "https://custom.example.test/telegram", config)
    print("PASS test_emit_runtime_config_defaults_public_telegram_webhook_to_callback_ready_route")


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
        tailscale_serve_port="8443",
        tailscale_notion_webhook_funnel_port="443",
        tailscale_notion_webhook_funnel_path="/notion/webhook",
        notion_root_page_url="https://www.notion.so/The-ArcLink-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
        notion_root_page_id="aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb",
        notion_space_url="https://www.notion.so/Acme-SSOT-1234567890abcdef1234567890abcdef",
        notion_space_id="12345678-90ab-cdef-1234-567890abcdef",
        notion_space_kind="database",
        notion_api_version="2026-03-11",
        notion_token="secret_test",
        notion_public_webhook_url="https://hooks.example.com/notion/webhook",
    )
    expect(
        source_value(config, "ARCLINK_SSOT_NOTION_ROOT_PAGE_URL")
        == "https://www.notion.so/The-ArcLink-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
        config,
    )
    expect(
        source_value(config, "ARCLINK_SSOT_NOTION_ROOT_PAGE_ID") == "aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb",
        config,
    )
    expect(
        source_value(config, "ARCLINK_SSOT_NOTION_SPACE_URL") == "https://www.notion.so/Acme-SSOT-1234567890abcdef1234567890abcdef",
        config,
    )
    expect(source_value(config, "ARCLINK_SSOT_NOTION_SPACE_ID") == "12345678-90ab-cdef-1234-567890abcdef", config)
    expect(source_value(config, "ARCLINK_SSOT_NOTION_SPACE_KIND") == "database", config)
    expect(source_value(config, "ARCLINK_SSOT_NOTION_API_VERSION") == "2026-03-11", config)
    expect(source_value(config, "ARCLINK_SSOT_NOTION_TOKEN") == "secret_test", config)
    expect(source_value(config, "ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL") == "1", config)
    expect(source_value(config, "TAILSCALE_SERVE_PORT") == "8443", config)
    expect(source_value(config, "TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT") == "443", config)
    expect(source_value(config, "TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH") == "/notion/webhook", config)
    expect(
        source_value(config, "ARCLINK_NOTION_WEBHOOK_PUBLIC_URL") == "https://hooks.example.com/notion/webhook",
        config,
    )
    print("PASS test_emit_runtime_config_persists_notion_ssot_fields")


def test_emit_runtime_config_persists_hermes_docs_sync_fields() -> None:
    config = render_runtime_config("tui-only", "tui-only")
    expect(
        source_value(config, "ARCLINK_HERMES_DOCS_SYNC_ENABLED") == "1",
        config,
    )
    expect(
        source_value(config, "ARCLINK_HERMES_DOCS_REPO_URL") == "https://github.com/NousResearch/hermes-agent.git",
        config,
    )
    # Docs ref must default to the pinned runtime ref so in-vault docs cannot
    # silently drift ahead of the pinned runtime they describe.
    hermes_agent_ref = source_value(config, "ARCLINK_HERMES_AGENT_REF")
    expect(
        source_value(config, "ARCLINK_HERMES_DOCS_REF") == hermes_agent_ref,
        config,
    )
    expect(
        source_value(config, "ARCLINK_HERMES_DOCS_REF") != "main",
        "ARCLINK_HERMES_DOCS_REF must not default to 'main' (silent-drift regression)",
    )
    expect(
        source_value(config, "ARCLINK_HERMES_DOCS_SOURCE_SUBDIR") == "website/docs",
        config,
    )
    expect(
        source_value(config, "ARCLINK_HERMES_DOCS_VAULT_DIR").endswith("/vault/Agents_KB/hermes-agent-docs"),
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
        source_value(config, "ARCLINK_HERMES_DOCS_REPO_URL") == "https://example.test/custom-hermes-docs.git",
        config,
    )
    expect(
        source_value(config, "ARCLINK_HERMES_DOCS_REF") == "main",
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
        source_value(config, "ARCLINK_EXTRA_MCP_URL") == "https://kb.example/mcp",
        config,
    )
    print("PASS test_emit_runtime_config_persists_extra_mcp_url")


def test_emit_runtime_config_persists_qmd_embedding_endpoint_fields() -> None:
    config = render_runtime_config(
        "tui-only",
        "tui-only",
        qmd_embed_provider="endpoint",
        qmd_embed_endpoint="https://embed.example.test/v1",
        qmd_embed_endpoint_model="text-embedding-3-small",
        qmd_embed_api_key="embed-secret",
        qmd_embed_dimensions="768",
        qmd_embed_force_on_next_refresh="1",
    )
    expect(source_value(config, "QMD_EMBED_PROVIDER") == "endpoint", config)
    expect(source_value(config, "QMD_EMBED_ENDPOINT") == "https://embed.example.test/v1", config)
    expect(source_value(config, "QMD_EMBED_ENDPOINT_MODEL") == "text-embedding-3-small", config)
    expect(source_value(config, "QMD_EMBED_API_KEY") == "embed-secret", config)
    expect(source_value(config, "QMD_EMBED_DIMENSIONS") == "768", config)
    expect(source_value(config, "QMD_EMBED_FORCE_ON_NEXT_REFRESH") == "1", config)
    print("PASS test_emit_runtime_config_persists_qmd_embedding_endpoint_fields")


def test_emit_runtime_config_reconciles_existing_fleet_private_endpoints_into_allowlist() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "control.sqlite3"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE arclink_fleet_hosts (
              hostname TEXT,
              metadata_json TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO arclink_fleet_hosts (hostname, metadata_json) VALUES (?, ?)",
            (
                "arclink-001",
                (
                    '{"ssh_host":"135.181.246.168",'
                    '"private_dns_name":"10.44.0.11",'
                    '"tailscale_dns_name":"worker-one.tailnet.test",'
                    '"wireguard":{"private_ip":"10.44.0.11","private_cidr":"10.44.0.11/32"}}'
                ),
            ),
        )
        conn.commit()
        conn.close()
        config = render_runtime_config(
            "tui-only",
            "tui-only",
            arclink_db_path=str(db_path),
            executor_allowlist=r"135.181.246.168\,arclink-001",
        )
    line = next(item for item in config.splitlines() if item.startswith("ARCLINK_EXECUTOR_MACHINE_HOST_ALLOWLIST="))
    expect("10.44.0.11" in line, line)
    expect("worker-one.tailnet.test" in line, line)
    expect(line.count("10.44.0.11") == 1, line)
    print("PASS test_emit_runtime_config_reconciles_existing_fleet_private_endpoints_into_allowlist")


def test_emit_runtime_config_reconciles_docker_host_state_inventory_into_allowlist() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        host_priv = Path(tmpdir) / "arclink-priv"
        state_dir = host_priv / "state"
        state_dir.mkdir(parents=True)
        db_path = state_dir / "arclink-control.sqlite3"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE arclink_fleet_hosts (
              hostname TEXT,
              metadata_json TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO arclink_fleet_hosts (hostname, metadata_json) VALUES (?, ?)",
            (
                "arclink-001",
                (
                    '{"ssh_host":"135.181.246.168",'
                    '"private_dns_name":"10.44.0.11",'
                    '"wireguard":{"private_ip":"10.44.0.11","private_cidr":"10.44.0.11/32"}}'
                ),
            ),
        )
        conn.commit()
        conn.close()
        stale_db_path = Path(tmpdir) / "stale-container-path.sqlite3"
        stale_conn = sqlite3.connect(stale_db_path)
        stale_conn.execute(
            """
            CREATE TABLE arclink_fleet_hosts (
              hostname TEXT,
              metadata_json TEXT
            )
            """
        )
        stale_conn.commit()
        stale_conn.close()
        config = render_runtime_config(
            "tui-only",
            "tui-only",
            arclink_db_path=str(stale_db_path),
            arclink_docker_host_priv_dir=str(host_priv),
            executor_allowlist="135.181.246.168,arclink-001",
        )
    line = next(item for item in config.splitlines() if item.startswith("ARCLINK_EXECUTOR_MACHINE_HOST_ALLOWLIST="))
    expect("10.44.0.11" in line, line)
    expect(line.count("10.44.0.11") == 1, line)
    print("PASS test_emit_runtime_config_reconciles_docker_host_state_inventory_into_allowlist")


def test_deploy_guides_explicit_notion_webhook_event_selection() -> None:
    text = DEPLOY_SH.read_text()
    expect("If a subscription already exists for this exact URL, edit that subscription." in text, "expected explicit reuse guidance for existing Notion webhook subscription")
    expect("Do not create a second webhook subscription for the same ArcLink endpoint." in text, "expected explicit no-duplicate Notion webhook guidance")
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


def test_deploy_uses_stable_copy_for_privileged_reexec() -> None:
    text = DEPLOY_SH.read_text()
    expect("ARCLINK_DEPLOY_STABLE_COPY" in text, "expected deploy.sh to support stable self execution")
    expect('exec bash "$DEPLOY_EXEC_PATH" "$@"' in text, "expected deploy.sh to re-exec from a temp copy")
    expect("sudo_deploy()" in text, "expected privileged deploy reexecs to preserve stable-copy env")
    expect(
        'sudo_deploy ARCLINK_INSTALL_ANSWERS_FILE="$ANSWERS_FILE" "${DEPLOY_EXEC_PATH:-$SELF_PATH}" --apply-install' in text,
        "expected install apply step to invoke the stable deploy copy",
    )
    expect(
        'sudo env ARCLINK_INSTALL_ANSWERS_FILE="$ANSWERS_FILE" "$SELF_PATH" --apply-install' not in text,
        "install apply step must not run the mutable checkout script directly",
    )
    print("PASS test_deploy_uses_stable_copy_for_privileged_reexec")


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
CONFIG_TARGET=/tmp/arclink.env
ARCLINK_NOTION_WEBHOOK_PUBLIC_URL=https://hooks.example.com/notion/webhook
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


def test_detect_tailscale_serve_distinguishes_qmd_from_arclink_routes() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "detect_tailscale_serve() {", "normalize_http_path() {")
    script = f"""
{snippet}
TAILSCALE_SERVE_PORT=443
QMD_MCP_PORT=8181
TAILSCALE_QMD_PATH=/mcp
ARCLINK_MCP_PORT=8282
TAILSCALE_ARCLINK_MCP_PATH=/arclink-mcp
tailscale() {{
  cat <<'JSON'
{{"Web": {{"host.example.com:443": {{"Handlers": {{"/arclink-mcp": {{"Proxy": "http://127.0.0.1:8282/mcp"}}}}}}}}}}
JSON
}}
detect_tailscale_serve
printf 'qmd=%s arclink=%s\\n' "$TAILSCALE_SERVE_HAS_QMD" "$TAILSCALE_SERVE_HAS_ARCLINK_MCP"
"""
    result = bash(script)
    expect(result.returncode == 0, f"detect_tailscale_serve probe failed: {result.stderr}")
    expect("qmd=0 arclink=1" in result.stdout, f"expected exact route detection, got: {result.stdout!r}")
    print("PASS test_detect_tailscale_serve_distinguishes_qmd_from_arclink_routes")


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
        'run_as_user "$ARCLINK_USER" "env ARCLINK_CONFIG_FILE=\'$CONFIG_TARGET\' \'$ARCLINK_REPO_DIR/bin/health.sh\'"' in snippet,
        "expected run_health_check to fall back to plain user-shell execution when the bus is absent",
    )
    print("PASS test_run_health_check_falls_back_when_user_bus_is_missing")


def test_install_and_upgrade_run_live_agent_tool_smoke_after_health() -> None:
    text = DEPLOY_SH.read_text()
    smoke_script = REPO / "bin" / "live-agent-tool-smoke.sh"
    install_snippet = extract(text, "run_root_install() {", "run_root_upgrade() {")
    upgrade_snippet = extract(text, "run_root_upgrade() {", "run_root_remove() {")
    smoke_call = 'env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$ARCLINK_REPO_DIR/bin/live-agent-tool-smoke.sh"'
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
    expect("arclink_upgrade_last_seen_sha" in text and "arclink_upgrade_relation" in text, text)
    expect("ArcLink update available:%" in text, "successful deploy should clear stale operator update notifications")
    expect(
        "Curator reports an ArcLink host update is available:%" in text,
        "successful deploy should clear stale user-agent update notifications",
    )
    print("PASS test_install_and_upgrade_refresh_upgrade_check_before_health")


def test_install_and_upgrade_mark_deploy_operation_window() -> None:
    text = DEPLOY_SH.read_text()
    install_snippet = extract(text, "run_root_install() {", "run_root_upgrade() {")
    upgrade_snippet = extract(text, "run_root_upgrade() {", "run_root_remove() {")
    control_snippet = extract(text, "run_control_install_flow() {", "ensure_control_operator_agent() {")
    expect("begin_deploy_operation() {" in text, "expected deploy-operation marker helper")
    expect("arclink-deploy-operation.json" in text, "expected deploy-operation marker file")
    expect("arclink-deploy-operation.lock" in text, "expected deploy-operation lock file")
    expect("flock -n" in text, "expected exclusive deploy-operation lock")
    expect("Another ArcLink deploy operation is already running" in text, "expected clear overlapping deploy refusal")
    expect("ARCLINK_DEPLOY_OPERATION_LOCK_FD" in text, "expected lock fd cleanup")
    expect('begin_deploy_operation "install" "$STATE_DIR"' in install_snippet, install_snippet)
    expect('begin_deploy_operation "upgrade" "$STATE_DIR"' in upgrade_snippet, upgrade_snippet)
    expect("finish_deploy_operation" in install_snippet, install_snippet)
    expect("finish_deploy_operation" in upgrade_snippet, upgrade_snippet)
    expect('operation="control-install"' in control_snippet, control_snippet)
    expect('operation="control-upgrade"' in control_snippet, control_snippet)
    expect('begin_deploy_operation "$operation" "$BOOTSTRAP_DIR/arclink-priv/state"' in control_snippet, control_snippet)
    expect("finish_deploy_operation" in control_snippet, control_snippet)
    print("PASS test_install_and_upgrade_mark_deploy_operation_window")


def test_install_and_upgrade_run_user_agent_refresh_before_health() -> None:
    text = DEPLOY_SH.read_text()
    helper = extract(text, "refresh_active_agent_context_root() {", "chown_managed_paths() {")
    install_snippet = extract(text, "run_root_install() {", "run_root_upgrade() {")
    upgrade_snippet = extract(text, "run_root_upgrade() {", "run_root_remove() {")
    expect("runuser -u \"$unix_user\" -- env" in helper, helper)
    expect('"$ARCLINK_REPO_DIR/bin/user-agent-refresh.sh"' in helper, helper)
    expect("ARCLINK_AGENT_ID=\"$agent_id\"" in helper, helper)
    expect("ARCLINK_MCP_URL=\"$mcp_url\"" in helper, helper)
    for name, snippet in [("install", install_snippet), ("upgrade", upgrade_snippet)]:
        wait_index = snippet.index('wait_for_port 127.0.0.1 "$ARCLINK_MCP_PORT"')
        refresh_index = snippet.index("refresh_active_agent_context_root", wait_index)
        health_index = snippet.index('echo "Running health check..."', refresh_index)
        expect(wait_index < refresh_index < health_index, f"{name} must refresh user-agent context after MCP is up and before health")
    print("PASS test_install_and_upgrade_run_user_agent_refresh_before_health")


def test_install_offers_optional_notion_ssot_setup_before_health() -> None:
    text = DEPLOY_SH.read_text()
    helper = extract(text, "maybe_offer_notion_ssot_setup_root() {", "print_post_install_guide() {")
    install_snippet = extract(text, "run_root_install() {", "run_root_upgrade() {")
    offer_index = install_snippet.index("maybe_offer_notion_ssot_setup_root")
    health_index = install_snippet.index('echo "Running health check..."')
    expect(offer_index < health_index, install_snippet)
    expect("Shared Notion SSOT is not configured yet." in helper, helper)
    expect('ask_yes_no "Configure the shared Notion SSOT page now" "0"' in helper, helper)
    expect("run_notion_ssot_setup" in helper, helper)
    expect("Run $ARCLINK_REPO_DIR/deploy.sh notion-ssot" in helper, helper)
    expect("ARCLINK_INSTALL_OFFER_NOTION_SSOT" in helper, helper)
    print("PASS test_install_offers_optional_notion_ssot_setup_before_health")


def test_live_agent_tool_smoke_blocks_broader_python_heredoc_variants() -> None:
    body = (REPO / "bin" / "live-agent-tool-smoke.sh").read_text(encoding="utf-8")
    expect("import re" in body, body)
    expect(r"python(?:3)?\s*-\s*<<\s*\S+" in body, body)
    expect("tool_token_injected" in body, body)
    expect("missing_tool_token_injected_but_brokered_tool_succeeded" in body, body)
    expect("telemetry_missing_but_brokered_tool_succeeded" in body, body)
    expect("Hermes quota monitoring" in body, body)
    expect("mcp_arclink_mcp_vault_search_and_fetch" in body, body)
    expect("session did not invoke the brokered ArcLink knowledge/vault MCP rail" in body, body)
    expect("missing or invalid mcp-session-id" in body, body)
    expect("session attempted raw curl/MCP debugging" in body, body)
    expect("provider_auth_failed" in body, body)
    expect("provider_unavailable" in body, body)
    expect("no instances available" in body, body)
    expect("authentication_error" in body, body)
    expect("stale_mcp_transport_session" in body, body)
    expect("ARCLINK_LIVE_AGENT_SMOKE_TIMEOUT_SECONDS" in body, body)
    expect('timeout --foreground --kill-after=30s "${TARGET_TIMEOUT_SECONDS}s"' in body, body)
    expect("timed_out_after_brokered_tool_returned" in body, body)
    expect("hermes chat exited with status" in body, body)
    expect("tool_result_texts" in body, body)
    expect("ARCLINK_LIVE_AGENT_SMOKE_RETRY_ATTEMPT" in body, body)
    expect("retrying once with a fresh chat session" in body, body)
    expect("Live agent tool smoke skipped" in body, body)
    expect("arclink-bootstrap-token" in body, body)
    print("PASS test_live_agent_tool_smoke_blocks_broader_python_heredoc_variants")


def test_hermes_config_migration_is_unattended() -> None:
    migrate = (REPO / "bin" / "migrate-hermes-config.sh").read_text(encoding="utf-8")
    refresh = (REPO / "bin" / "refresh-agent-install.sh").read_text(encoding="utf-8")
    curator = (REPO / "bin" / "bootstrap-curator.sh").read_text(encoding="utf-8")
    expect("migrate_config(interactive=False" in migrate, migrate)
    expect("quiet=True" in migrate, migrate)
    expect("Would you like" not in migrate and "input(" not in migrate, migrate)
    expect("migrate-hermes-config.sh" in refresh, refresh)
    expect("migrate-hermes-config.sh" in curator, curator)
    print("PASS test_hermes_config_migration_is_unattended")


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
    body = (REPO / "python" / "arclink_curator_discord_onboarding.py").read_text(encoding="utf-8")
    expect("_claim_discord_message_once" in body, body)
    expect("curator_discord_onboarding_seen_message:" in body, body)
    expect("INSERT OR IGNORE INTO settings" in body, body)
    expect('message_id = str(getattr(message, "id", "") or "")' in body, body)
    expect("if not _claim_discord_message_once(message_id):" in body, body)
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
    expect('"$ARCLINK_DB_PATH" "$TARGET_UNIX_USER" "$TARGET_AGENT_SELECTOR"' in body, body)
    expect("lower(agent_id) = ?" in body, body)
    expect("lower(unix_user) = ?" in body, body)
    expect("lower(coalesce(display_name, '')) = ?" in body, body)
    print("PASS test_live_agent_tool_smoke_parses_explicit_selectors")


def test_ci_workflow_runs_python_lint_before_direct_test_loop() -> None:
    workflow = INSTALL_SMOKE_WORKFLOW.read_text(encoding="utf-8")
    lint = "python3 -m ruff check --select E9,F63,F7,F82 bin python tests plugins hooks"
    expect("- master" not in workflow, "dead master branch trigger should not remain in CI workflow")
    expect(lint in workflow, workflow)
    expect(workflow.index(lint) < workflow.index('python3 "$test_file"'), workflow)
    print("PASS test_ci_workflow_runs_python_lint_before_direct_test_loop")


def test_ci_preflight_lints_root_deploy_and_pins_pdf_backend() -> None:
    preflight = CI_PREFLIGHT_SH.read_text(encoding="utf-8")
    pdf_flow = extract(preflight, "run_pdf_ingest_preflight() {", "run_pdf_ingest_vision_preflight() {")
    expect('local files=("$ROOT_DIR/deploy.sh" "$ROOT_DIR/test.sh")' in preflight, preflight)
    expect("PDF_INGEST_EXTRACTOR=auto" not in pdf_flow, pdf_flow)
    expect(pdf_flow.count("PDF_INGEST_EXTRACTOR=pdftotext") == 3, pdf_flow)
    print("PASS test_ci_preflight_lints_root_deploy_and_pins_pdf_backend")


def test_live_agent_tool_smoke_opens_control_db_read_only() -> None:
    body = (REPO / "bin" / "live-agent-tool-smoke.sh").read_text(encoding="utf-8")
    expect('sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)' in body, body)
    expect("sqlite3.connect(db_path)" not in body, body)
    print("PASS test_live_agent_tool_smoke_opens_control_db_read_only")


def test_agent_install_payload_tracks_current_agent_contract() -> None:
    payload = render_agent_install_payload()
    expected_skills = [
        "arclink-qmd-mcp",
        "arclink-vault-reconciler",
        "arclink-first-contact",
        "arclink-vaults",
        "arclink-ssot",
        "arclink-notion-knowledge",
        "arclink-ssot-connect",
        "arclink-notion-mcp",
        "arclink-academy",
        "arclink-resources",
    ]
    expected_keys = [
        "[managed:arclink-skill-ref]",
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
            f"/repo/skills/{skill_name}" in payload,
            payload,
        )

    for managed_key in expected_keys:
        expect(managed_key in payload, payload)

    expect('source_ref: "example/arclink#feature/smoke"' in payload, payload)
    expect("https://raw.githubusercontent.com/" not in payload, payload)
    expect("skill_sources_github:" not in payload, payload)
    expect("scripts/curate-vaults.sh" not in payload, payload)
    expect("arclink-managed-context" in payload, payload)
    expect("inject ArcLink MCP auth" in payload, payload)
    expect("do not read HERMES_HOME secrets files" in payload, payload)
    expect("do not pass token" in payload, payload)
    expect("plugin-managed context state" in payload, payload)
    expect("do not write dynamic [managed:*] stubs into HERMES_HOME/memories/MEMORY.md" in payload, payload)
    expect("remove only those entries" in payload, payload)
    print("PASS test_agent_install_payload_tracks_current_agent_contract")


def test_compose_defaults_academy_live_paths_off() -> None:
    body = (REPO / "compose.yaml").read_text(encoding="utf-8")
    expect(
        "ARCLINK_ACADEMY_TRAINER_LIVE: ${ARCLINK_ACADEMY_TRAINER_LIVE:-0}" in body,
        "control compose should keep the scoped live Academy Trainer opt-in",
    )
    expect(
        "ARCLINK_ACADEMY_CE_LIVE_CRAWL: ${ARCLINK_ACADEMY_CE_LIVE_CRAWL:-0}" in body,
        "control compose should keep Academy continuing-education live crawling opt-in",
    )
    expect(
        "ARCLINK_ACADEMY_TRAINER_ROUTER_KEY_FILE:" in body
        and "state/operator/secrets/llm_router_api_key" in body,
        "opt-in live Academy Trainer should use the scoped operator router key file",
    )
    print("PASS test_compose_defaults_academy_live_paths_off")


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
    expect(source_value(config, "ARCLINK_ORG_NAME") == "Acme Labs", config)
    expect(source_value(config, "ARCLINK_ORG_MISSION") == "Make serious research more legible and actionable.", config)
    expect(source_value(config, "ARCLINK_ORG_PRIMARY_PROJECT") == "Hermes deployment lane", config)
    expect(source_value(config, "ARCLINK_ORG_TIMEZONE") == "America/New_York", config)
    expect(source_value(config, "ARCLINK_ORG_QUIET_HOURS") == "22:00-08:00 weekdays", config)
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
    expect(source_value(config, "ARCLINK_ORG_PROVIDER_ENABLED") == "1", config)
    expect(source_value(config, "ARCLINK_ORG_PROVIDER_PRESET") == "chutes", config)
    expect(source_value(config, "ARCLINK_ORG_PROVIDER_MODEL_ID") == "moonshotai/Kimi-K2.6-TEE", config)
    expect(source_value(config, "ARCLINK_ORG_PROVIDER_REASONING_EFFORT") == "xhigh", config)
    expect(source_value(config, "ARCLINK_ORG_PROVIDER_SECRET_PROVIDER") == "chutes", config)
    expect(source_value(config, "ARCLINK_ORG_PROVIDER_SECRET") == "cpk_test_secret", config)
    print("PASS test_emit_runtime_config_persists_org_provider_fields")


def test_collect_org_provider_answers_defaults_yes_and_collects_chutes() -> None:
    text = DEPLOY_SH.read_text()
    helpers = extract(text, "ask() {", "json_field() {")
    snippet = extract(text, "normalize_org_provider_preset() {", "collect_backup_git_answers() {")
    script = f"""
{helpers}
{snippet}
BOOTSTRAP_DIR={shlex.quote(str(REPO))}
ARCLINK_MODEL_PRESET_CODEX="openai:codex"
ARCLINK_MODEL_PRESET_OPUS="anthropic:claude-opus"
ARCLINK_MODEL_PRESET_CHUTES="chutes:model-router"
ARCLINK_ORG_PROVIDER_ENABLED=""
ARCLINK_ORG_PROVIDER_PRESET=""
ARCLINK_ORG_PROVIDER_MODEL_ID=""
ARCLINK_ORG_PROVIDER_REASONING_EFFORT="medium"
ARCLINK_ORG_PROVIDER_SECRET_PROVIDER=""
ARCLINK_ORG_PROVIDER_SECRET=""
ARCLINK_ORG_PROVIDER_PROMPT_NONINTERACTIVE=1
collect_org_provider_answers
printf 'enabled=%s\\n' "$ARCLINK_ORG_PROVIDER_ENABLED"
printf 'preset=%s\\n' "$ARCLINK_ORG_PROVIDER_PRESET"
printf 'model=%s\\n' "$ARCLINK_ORG_PROVIDER_MODEL_ID"
printf 'reasoning=%s\\n' "$ARCLINK_ORG_PROVIDER_REASONING_EFFORT"
printf 'secret_provider=%s\\n' "$ARCLINK_ORG_PROVIDER_SECRET_PROVIDER"
printf 'secret=%s\\n' "$ARCLINK_ORG_PROVIDER_SECRET"
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
        config_path = protected_dir / "arclink.env"
        config_path.write_text("ARCLINK_USER=arclink\n")
        if config_mode == 0:
            protected_dir.chmod(0)
        else:
            config_path.chmod(config_mode)

        artifact_path = tmp_path / ".arclink-operator.env"
        artifact_path.write_text(f"ARCLINK_OPERATOR_DEPLOYED_CONFIG_FILE={shlex.quote(str(config_path))}\n")
        log_path = tmp_path / "sudo.log"

        script = f"""
LOG={shlex.quote(str(log_path))}
sudo() {{ printf '%s\n' "$@" >\"$LOG\"; return 0; }}
BOOTSTRAP_DIR={shlex.quote(str(REPO))}
SELF_PATH=/fake/deploy.sh
MODE=install
ARCLINK_OPERATOR_ARTIFACT_FILE={shlex.quote(str(artifact_path))}
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
    if os.geteuid() == 0:
        print("SKIP test_install_reexecs_for_unreadable_breadcrumb_config (root can read chmod 000 paths)")
        return
    status, output, sudo_log = run_install_reexec_case(0)
    expect(status == 0, f"expected unreadable-config case to reexec via sudo, got status {status}")
    expect("Switching to sudo before prompting" in output, "expected install flow to announce sudo-before-prompting path")
    expect("env" in sudo_log and "ARCLINK_CONFIG_FILE=" in sudo_log and "/fake/deploy.sh" in sudo_log and "install" in sudo_log,
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
ARCLINK_REEXEC_ATTEMPTED=0
maybe_reexec_install_for_config_defaults() {{
  ARCLINK_REEXEC_ATTEMPTED=1
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
ARCLINK_REEXEC_ATTEMPTED=0
maybe_reexec_install_for_config_defaults() {{
  ARCLINK_REEXEC_ATTEMPTED=1
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
    if os.geteuid() == 0:
        print("SKIP test_write_operator_artifact_falls_back_to_discovered_config (root does not write operator breadcrumb)")
        return
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "probe_path_status() {", "run_as_user() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_path = tmp_path / "deployed" / "arclink.env"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("ARCLINK_USER=operator-svc\n", encoding="utf-8")
        artifact_path = tmp_path / ".arclink-operator.env"

        script = f"""
BOOTSTRAP_DIR={shlex.quote(str(tmp_path))}
ARCLINK_OPERATOR_ARTIFACT_FILE={shlex.quote(str(artifact_path))}
DISCOVERED_CONFIG={shlex.quote(str(config_path))}
CONFIG_TARGET=""
ARCLINK_USER=operator-svc
ARCLINK_REPO_DIR=/srv/operator-svc/arclink
ARCLINK_PRIV_DIR=/srv/operator-svc/arclink-priv
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
            f"ARCLINK_OPERATOR_DEPLOYED_CONFIG_FILE={config_path}" in artifact,
            f"expected artifact to record discovered config path, got: {artifact!r}",
        )
        expect(
            "ARCLINK_OPERATOR_DEPLOYED_USER=operator-svc" in artifact,
            f"expected artifact to record service user, got: {artifact!r}",
        )
    print("PASS test_write_operator_artifact_falls_back_to_discovered_config")


def test_discover_existing_config_uses_artifact_priv_dir_hint() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "probe_path_status() {", "load_detected_config() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        priv_dir = tmp_path / "deployed" / "arclink-priv"
        config_path = priv_dir / "config" / "arclink.env"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("ARCLINK_USER=operator-svc\n")
        artifact_path = tmp_path / ".arclink-operator.env"
        artifact_path.write_text(
            "\n".join(
                [
                    "ARCLINK_OPERATOR_DEPLOYED_USER=operator-svc",
                    f"ARCLINK_OPERATOR_DEPLOYED_PRIV_DIR={shlex.quote(str(priv_dir))}",
                    "",
                ]
            )
        )
        script = f"""
BOOTSTRAP_DIR={shlex.quote(str(REPO))}
ARCLINK_OPERATOR_ARTIFACT_FILE={shlex.quote(str(artifact_path))}
{snippet}
discover_existing_config
status=$?
printf 'STATUS=%s\\n' "$status"
printf 'DISCOVERED=%s\\n' "${{DISCOVERED_CONFIG:-}}"
"""
        result = bash(script)
        expect(result.returncode == 0, f"discover_existing_config case failed: {result.stderr}")
        expect("STATUS=0" in result.stdout, f"expected discover_existing_config to succeed, got: {result.stdout!r}")
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
  ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED=0
}}
collect_backup_git_answers() {{
  BACKUP_GIT_REMOTE=""
  BACKUP_GIT_DEPLOY_KEY_PATH=""
  BACKUP_GIT_KNOWN_HOSTS_FILE=""
}}
load_detected_config() {{
  ARCLINK_USER=operator-svc
  ARCLINK_HOME=/srv/operator-svc
  ARCLINK_REPO_DIR=/srv/operator-svc/arclink
  ARCLINK_PRIV_DIR=/srv/operator-svc/arclink-priv
  BACKUP_GIT_AUTHOR_NAME='Existing Backup'
  BACKUP_GIT_AUTHOR_EMAIL='operator-svc@example.test'
  NEXTCLOUD_ADMIN_USER='operator'
  NEXTCLOUD_ADMIN_PASSWORD='keep-me'
  return 0
}}
MODE=write-config
collect_install_answers
printf 'ARCLINK_USER=%s\\n' "$ARCLINK_USER"
printf 'ARCLINK_HOME=%s\\n' "$ARCLINK_HOME"
printf 'ARCLINK_REPO_DIR=%s\\n' "$ARCLINK_REPO_DIR"
printf 'ARCLINK_PRIV_DIR=%s\\n' "$ARCLINK_PRIV_DIR"
"""
    result = bash(script)
    expect(result.returncode == 0, f"collect_install_answers case failed: {result.stderr}")
    expect("ARCLINK_USER=operator-svc" in result.stdout, f"expected detected service user default, got: {result.stdout!r}")
    expect("ARCLINK_HOME=/srv/operator-svc" in result.stdout, f"expected detected home default, got: {result.stdout!r}")
    expect("ARCLINK_REPO_DIR=/srv/operator-svc/arclink" in result.stdout, f"expected detected repo default, got: {result.stdout!r}")
    expect("ARCLINK_PRIV_DIR=/srv/operator-svc/arclink-priv" in result.stdout, f"expected detected priv default, got: {result.stdout!r}")
    print("PASS test_collect_install_answers_defaults_to_detected_service_user")


def test_collect_install_answers_moves_tailnet_serve_when_public_notion_funnel_uses_443() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "collect_install_answers() {", "collect_remove_answers() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        prompt_log = tmp_path / "prompts.log"
        script = f"""
PROMPT_LOG={shlex.quote(str(prompt_log))}
{snippet}
ask() {{
  printf '%s|%s\\n' "$1" "${{2:-}}" >> "$PROMPT_LOG"
  printf '%s' "${{2:-}}"
}}
ask_yes_no() {{
  case "$1" in
    Enable\\ Nextcloud*) printf '%s' 1 ;;
    Enable\\ Tailscale\\ HTTPS\\ proxy*) printf '%s' 1 ;;
    Enable\\ public\\ Tailscale\\ Funnel*) printf '%s' 1 ;;
    *) printf '%s' "${{2:-0}}" ;;
  esac
}}
ask_validated_optional() {{ printf '%s' "${{2:-}}"; }}
ask_secret() {{ printf '%s' ""; }}
ask_secret_with_default() {{ printf '%s' "${{2:-}}"; }}
ask_secret_keep_default() {{ printf '%s' "${{2:-}}"; }}
normalize_optional_answer() {{ printf '%s' "${{1:-}}"; }}
normalize_http_path() {{
  case "${{1:-/}}" in
    "") printf '%s\\n' "/" ;;
    /*) printf '%s\\n' "$1" ;;
    *) printf '/%s\\n' "$1" ;;
  esac
}}
random_secret() {{ printf '%s' "generated-secret"; }}
collect_org_provider_answers() {{ ARCLINK_ORG_PROVIDER_ENABLED=0; }}
detect_tailscale() {{
  TAILSCALE_DNS_NAME="operator.example.ts.net"
  TAILSCALE_IPV4="100.64.0.10"
  TAILSCALE_TAILNET=""
}}
nextcloud_state_has_existing_data() {{ return 1; }}
read_operator_artifact_hints() {{ return 1; }}
resolve_user_home() {{ return 1; }}
collect_upstream_git_answers() {{ ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED=0; }}
collect_backup_git_answers() {{
  BACKUP_GIT_REMOTE=""
  BACKUP_GIT_DEPLOY_KEY_PATH=""
  BACKUP_GIT_KNOWN_HOSTS_FILE=""
}}
load_detected_config() {{
  ARCLINK_USER=operator-svc
  ARCLINK_HOME=/srv/operator-svc
  ARCLINK_REPO_DIR=/srv/operator-svc/arclink
  ARCLINK_PRIV_DIR=/srv/operator-svc/arclink-priv
  NEXTCLOUD_ADMIN_USER='operator'
  NEXTCLOUD_ADMIN_PASSWORD='keep-me'
  return 0
}}
MODE=write-config
collect_install_answers
printf 'TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT=%s\\n' "$TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT"
printf 'TAILSCALE_SERVE_PORT=%s\\n' "$TAILSCALE_SERVE_PORT"
printf 'PROMPTS_BEGIN\\n'
cat "$PROMPT_LOG"
printf 'PROMPTS_END\\n'
"""
        result = bash(script)
        expect(result.returncode == 0, f"tailscale default split case failed: {result.stderr}\n{result.stdout}")
        expect("TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT=443" in result.stdout, result.stdout)
        expect("TAILSCALE_SERVE_PORT=8443" in result.stdout, result.stdout)
        prompts = result.stdout.split("PROMPTS_BEGIN\n", 1)[1].split("\nPROMPTS_END", 1)[0]
        expect(
            "Public Tailscale Funnel HTTPS port for the shared-host Notion webhook|443" in prompts,
            f"expected shared-host Notion webhook default 443, got: {prompts!r}",
        )
        expect(
            "Tailnet-only Tailscale HTTPS port for Nextcloud and internal MCP routes|8443" in prompts,
            f"expected tailnet Serve default to move to 8443 when public Funnel uses 443, got: {prompts!r}",
        )
        expect("https://login.tailscale.com/admin/dns" in result.stdout, result.stdout)
        expect("HTTPS Certificates" in result.stdout, result.stdout)
    print("PASS test_collect_install_answers_moves_tailnet_serve_when_public_notion_funnel_uses_443")


def test_tailscale_onboarding_guidance_mentions_https_certificates_in_native_flow_only() -> None:
    text = DEPLOY_SH.read_text()
    native_snippet = extract(text, "collect_install_answers() {", "collect_remove_answers() {")
    expect(
        "https://login.tailscale.com/admin/dns" in native_snippet,
        "expected native migration onboarding to point operators to the Tailscale DNS admin page",
    )
    expect(
        "MagicDNS and HTTPS Certificates" in native_snippet,
        "expected native migration onboarding to name the required Tailscale settings",
    )
    expect(
        "https://login.tailscale.com/f/funnel" in native_snippet,
        "expected native migration onboarding to explain the Tailscale Funnel approval URL",
    )
    expect(
        "tailnet-only Nextcloud/MCP" in native_snippet,
        "expected native migration onboarding to distinguish public Funnel from tailnet-only Serve",
    )
    expect("collect_docker_install_answers()" not in text, "retired Docker answer collector should stay removed")
    print("PASS test_tailscale_onboarding_guidance_mentions_https_certificates_in_native_flow_only")


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
  ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED=0
}}
collect_backup_git_answers() {{
  BACKUP_GIT_REMOTE=""
  BACKUP_GIT_DEPLOY_KEY_PATH=""
  BACKUP_GIT_KNOWN_HOSTS_FILE=""
}}
load_detected_config() {{
  ARCLINK_USER=operator-svc
  ARCLINK_HOME=/srv/operator-svc
  ARCLINK_REPO_DIR=/srv/operator-svc/arclink
  ARCLINK_PRIV_DIR=/srv/operator-svc/arclink-priv
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


def test_deploy_menu_defaults_to_sovereign_control_node() -> None:
    text = DEPLOY_SH.read_text()
    shared_snippet = extract(text, "choose_shared_host_mode() {", "choose_mode() {")
    mode_snippet = extract(text, "choose_mode() {", "control_usage() {")
    expect(
        "retired_shared_host_mode" in shared_snippet,
        "expected Shared Host submenu to be retired",
    )
    expect(
        "Install / repair from current checkout" not in shared_snippet,
        "Shared Host install action should no longer be exposed",
    )
    expect(
        "Shared Host mode control center" not in mode_snippet,
        "top-level menu must not expose Shared Host mode",
    )
    expect(
        "Sovereign Control Node control center" in mode_snippet,
        "expected top-level menu to expose Sovereign Control Node mode",
    )
    expect(
        "one public install lane" in mode_snippet,
        "expected top-level menu to explain the single-mode contract",
    )
    expect(
        "Shared Host Docker control center" not in mode_snippet,
        "top-level menu must not expose Shared Host Docker mode",
    )
    expect('read -r -p "Choose ArcLink mode [1]: "' in mode_snippet, "expected top-level default to be Sovereign Control Node mode")
    expect('case "${answer:-1}"' in mode_snippet, "expected blank top-level selection to choose Sovereign Control Node mode")
    expect('MODE="control"' in mode_snippet and 'CONTROL_DEPLOY_COMMAND="menu"' in mode_snippet, "expected Sovereign Control Node mode to route to its submenu")
    expect('MODE="docker"' not in mode_snippet and 'DOCKER_DEPLOY_COMMAND="menu"' not in mode_snippet, "Shared Host Docker must not route from the main menu")
    print("PASS test_deploy_menu_defaults_to_sovereign_control_node")


def test_baremetal_install_banner_points_to_docker_first_path() -> None:
    text = DEPLOY_SH.read_text()
    usage_snippet = extract(text, "usage() {", "retired_shared_host_mode() {")
    dispatch_snippet = extract(text, 'case "$MODE" in', "esac")
    expect(
        "deploy.sh install        # shortcut for control install" in usage_snippet,
        "expected bare install to be documented as a control install shortcut",
    )
    expect(
        "install|upgrade|health)" in dispatch_snippet and 'MODE="control"' in dispatch_snippet,
        "expected bare install/upgrade/health to route through Sovereign Control Node",
    )
    print("PASS test_baremetal_install_banner_points_to_docker_first_path")


def test_org_profile_builder_installs_jsonschema() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "org_profile_builder_python() {", "maybe_run_org_profile_builder() {")
    expect("import yaml, jsonschema" in snippet, "expected profile builder dependency probe to include jsonschema")
    expect("PyYAML jsonschema" in snippet, "expected profile builder venv install to include jsonschema")
    print("PASS test_org_profile_builder_installs_jsonschema")


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
  ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED=0
}}
collect_backup_git_answers() {{
  BACKUP_GIT_REMOTE=""
  BACKUP_GIT_DEPLOY_KEY_PATH=""
  BACKUP_GIT_KNOWN_HOSTS_FILE=""
}}
load_detected_config() {{
  ARCLINK_USER=operator-svc
  ARCLINK_HOME=/srv/operator-svc
  ARCLINK_REPO_DIR=/srv/operator-svc/arclink
  ARCLINK_PRIV_DIR=/srv/operator-svc/arclink-priv
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
  ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED=0
}}
collect_backup_git_answers() {{
  BACKUP_GIT_REMOTE=""
  BACKUP_GIT_DEPLOY_KEY_PATH=""
  BACKUP_GIT_KNOWN_HOSTS_FILE=""
}}
load_detected_config() {{
  ARCLINK_USER=operator-svc
  ARCLINK_HOME=/srv/operator-svc
  ARCLINK_REPO_DIR=/srv/operator-svc/arclink
  ARCLINK_PRIV_DIR=/srv/operator-svc/arclink-priv
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
    GitHub\\ owner/repo\\ for\\ arclink-priv\\ backup*) printf '%s' 'acme/arclink-priv' ;;
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
  ARCLINK_USER=operator-svc
  ARCLINK_HOME=/srv/operator-svc
  ARCLINK_REPO_DIR=/srv/operator-svc/arclink
  ARCLINK_PRIV_DIR=/srv/operator-svc/arclink-priv
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
        "BACKUP_GIT_REMOTE=git@github.com:acme/arclink-priv.git" in result.stdout,
        f"expected GitHub SSH backup remote, got: {result.stdout!r}",
    )
    expect(
        "BACKUP_GIT_DEPLOY_KEY_PATH=/srv/operator-svc/.ssh/arclink-backup-ed25519" in result.stdout,
        f"expected default backup deploy key path, got: {result.stdout!r}",
    )
    expect(
        "BACKUP_GIT_KNOWN_HOSTS_FILE=/srv/operator-svc/.ssh/arclink-backup-known_hosts" in result.stdout,
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
    GitHub\\ owner/repo\\ for\\ ArcLink\\ upstream\\ deploy\\ key*) printf '%s' "${{2:-}}" ;;
    *) printf '%s' "${{2:-}}" ;;
  esac
}}
ask_yes_no() {{
  case "$1" in
    Set\\ up\\ an\\ operator\\ deploy\\ key\\ for\\ the\\ ArcLink\\ upstream\\ repo*) printf '%s' 1 ;;
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
  ARCLINK_USER=operator-svc
  ARCLINK_HOME=/srv/operator-svc
  ARCLINK_REPO_DIR=/srv/operator-svc/arclink
  ARCLINK_PRIV_DIR=/srv/operator-svc/arclink-priv
  ARCLINK_UPSTREAM_REPO_URL=https://github.com/example/arclink.git
  ARCLINK_UPSTREAM_DEPLOY_KEY_USER=operator-svc
  NEXTCLOUD_ADMIN_USER='operator'
  NEXTCLOUD_ADMIN_PASSWORD='keep-me'
  return 0
}}
MODE=write-config
collect_install_answers
printf 'ARCLINK_UPSTREAM_REPO_URL=%s\\n' "$ARCLINK_UPSTREAM_REPO_URL"
printf 'ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED=%s\\n' "$ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED"
printf 'ARCLINK_UPSTREAM_DEPLOY_KEY_USER=%s\\n' "$ARCLINK_UPSTREAM_DEPLOY_KEY_USER"
printf 'ARCLINK_UPSTREAM_DEPLOY_KEY_PATH=%s\\n' "$ARCLINK_UPSTREAM_DEPLOY_KEY_PATH"
printf 'ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE=%s\\n' "$ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE"
"""
    result = bash(script)
    expect(result.returncode == 0, f"upstream deploy-key collect_install_answers case failed: {result.stderr}")
    expect(
        "ARCLINK_UPSTREAM_REPO_URL=git@github.com:example/arclink.git" in result.stdout,
        f"expected upstream remote to switch to SSH, got: {result.stdout!r}",
    )
    expect("ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED=1" in result.stdout, result.stdout)
    expect("ARCLINK_UPSTREAM_DEPLOY_KEY_USER=operator-svc" in result.stdout, result.stdout)
    expect(
        "ARCLINK_UPSTREAM_DEPLOY_KEY_PATH=/srv/operator-svc/.ssh/arclink-upstream-ed25519" in result.stdout,
        f"expected upstream deploy key under operator/service home, got: {result.stdout!r}",
    )
    expect(
        "ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE=/srv/operator-svc/.ssh/arclink-upstream-known_hosts" in result.stdout,
        f"expected upstream known_hosts path, got: {result.stdout!r}",
    )
    expect(
        "read/write deploy key for operator/agent code pushes" in result.stdout
        and "Allow write access" in result.stdout
        and "arclink-priv backup and per-user Hermes-home backups use separate deploy keys" in result.stdout,
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
        "ARCLINK_UPSTREAM_DEPLOY_KEY_ACCESS_VERIFIED" in text,
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
        '"Reuse existing ArcLink upstream deploy key"' in body,
        'prompt_and_verify_upstream_deploy_key_access must offer a "Reuse existing" choice when verification already passes',
    )
    reuse_index = body.index('"Reuse existing ArcLink upstream deploy key"')
    press_enter_index = body.index('Press ENTER after adding this deploy key')
    expect(
        reuse_index < press_enter_index,
        'the "Reuse existing" prompt must come before the "Press ENTER after adding" prompt so an already-verified key skips the manual paste step',
    )
    expect(
        'rotate_upstream_git_deploy_key_material' in text,
        'a helper must exist to rotate the ArcLink upstream deploy key when the operator declines to reuse it',
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
        priv_dir = tmp_path / "arclink-priv"
        priv_dir.mkdir(parents=True, exist_ok=True)
        run(["git", "init", "-b", "main", str(priv_dir)])
        run(["git", "-C", str(priv_dir), "remote", "add", "origin", "git@github.com:remembered/arclink-priv.git"])
        script = f"""
{helpers}
{collect}
ask() {{
  case "$1" in
    GitHub\\ owner/repo\\ for\\ arclink-priv\\ backup*) printf '%s' "${{2:-}}" ;;
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
  ARCLINK_USER=operator-svc
  ARCLINK_HOME=/srv/operator-svc
  ARCLINK_REPO_DIR=/srv/operator-svc/arclink
  ARCLINK_PRIV_DIR={shlex.quote(str(priv_dir))}
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
            "BACKUP_GIT_REMOTE=git@github.com:remembered/arclink-priv.git" in result.stdout,
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
    expect("Native macOS is not a supported ArcLink host or runtime environment." in result.stderr, result.stderr)
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
  ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED=0
}}
collect_backup_git_answers() {{
  BACKUP_GIT_REMOTE=""
  BACKUP_GIT_DEPLOY_KEY_PATH=""
  BACKUP_GIT_KNOWN_HOSTS_FILE=""
}}
load_detected_config() {{
  ARCLINK_USER=operator-svc
  ARCLINK_HOME=/srv/operator-svc
  ARCLINK_REPO_DIR=/srv/operator-svc/arclink
  ARCLINK_PRIV_DIR=/srv/operator-svc/arclink-priv
  NEXTCLOUD_ADMIN_USER='operator'
  NEXTCLOUD_ADMIN_PASSWORD='keep-me'
  return 0
}}
MODE=install
collect_install_answers
printf 'ARCLINK_INSTALL_PODMAN=%s\\n' "$ARCLINK_INSTALL_PODMAN"
printf 'ARCLINK_INSTALL_TAILSCALE=%s\\n' "$ARCLINK_INSTALL_TAILSCALE"
printf 'PROMPTS_BEGIN\\n'
cat "$PROMPT_LOG"
printf 'PROMPTS_END\\n'
"""
        result = bash(script)
        expect(result.returncode == 0, f"host dependency prompt case failed: {result.stderr}")
        expect("ARCLINK_INSTALL_PODMAN=1" in result.stdout, result.stdout)
        expect("ARCLINK_INSTALL_TAILSCALE=1" in result.stdout, result.stdout)
        prompts = result.stdout.split("PROMPTS_BEGIN\n", 1)[1].split("\nPROMPTS_END", 1)[0]
        expect("Podman is not installed." in prompts, prompts)
        expect("Tailscale is not installed." in prompts, prompts)
    print("PASS test_collect_install_answers_records_missing_host_dependency_choices")


def test_write_answers_file_persists_host_dependency_choices() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "write_answers_file() {", "seed_private_repo() {")
    expect("write_kv ARCLINK_INSTALL_PODMAN" in snippet, snippet)
    expect("write_kv ARCLINK_INSTALL_TAILSCALE" in snippet, snippet)
    print("PASS test_write_answers_file_persists_host_dependency_choices")


def test_deploy_sh_retires_public_docker_control_center() -> None:
    text = DEPLOY_SH.read_text()
    control_menu = extract(text, "choose_control_mode() {", "detect_tailscale() {")
    usage_snippet = extract(text, "usage() {", "retired_shared_host_mode() {")
    expect("deploy.sh control install" in text, "expected Sovereign Control Node install command in deploy usage")
    expect("deploy.sh control backup" in text, "expected Sovereign Control Node runtime backup command in deploy usage")
    expect("deploy.sh control reset-runtime" in text, "expected Sovereign Control Node runtime reset command in deploy usage")
    expect("deploy.sh control reset-sandbox" in text, "expected Sovereign sandbox reset command in deploy usage")
    expect("deploy.sh control reset-production" in text, "expected Sovereign production reset command in deploy usage")
    expect("deploy.sh control fleet-key" in text, "expected Sovereign fleet public key command in deploy usage")
    expect("deploy.sh control register-worker" in text, "expected Sovereign remote worker registration command in deploy usage")
    expect("ArcLink Sovereign Control Node control center" in text, "expected Sovereign Control Node submenu")
    expect("Backup runtime state and generated pod data" in text, "expected Sovereign submenu to expose runtime backup")
    expect("Reset sandbox/test user data after backup" in text, "expected Sovereign submenu to expose guarded sandbox reset")
    expect("Reset production user data after double confirmation" in text, "expected Sovereign submenu to expose guarded production reset")
    expect("Show fleet SSH public key" in text, "expected Sovereign submenu to expose fleet public key")
    expect("Register remote fleet worker" in text, "expected Sovereign submenu to expose remote worker registration")
    expect("16) Back" in control_menu and "17) Exit" in control_menu, "expected Sovereign submenu to return to the mode chooser")
    expect('MODE="control"' in text and 'CONTROL_DEPLOY_COMMAND="menu"' in text, "expected main menu to route to control submenu")
    expect("run_control_install_flow()" in text, "expected idempotent control install flow")
    expect("run_control_runtime_backup()" in text, "expected first-class control runtime backup flow")
    expect("run_control_runtime_reset()" in text, "expected first-class control runtime reset flow")
    expect("ARCLINK_CONFIRM_RUNTIME_RESET=RESET" in text, "expected non-interactive reset confirmation guard")
    expect("ARCLINK_CONFIRM_PRODUCTION_RESET" in text, "expected production reset to require explicit first confirmation")
    expect("ARCLINK_CONFIRM_PRODUCTION_RESET_HOST" in text, "expected production reset to require host confirmation")
    expect('"arclink_credential_handoffs"' in text, "runtime reset must clear credential handoffs")
    expect("remove_control_generated_secret_refs()" in text, "runtime reset must clear generated per-deployment secret refs")
    expect("sovereign-secrets" in text and "-name 'arcdep_*'" in text, "runtime reset must target generated deployment secret dirs only")
    expect("reset_control_telegram_active_command_scopes" in text, "runtime reset must clear stale active Telegram command scopes")
    expect("include_agent_commands=False" in text, "runtime reset should restore old active chats to the Raven-only command menu")
    expect("collect_control_install_answers()" in text, "expected control-node provider configuration flow")
    expect("Control-node deployment style" in text, "expected control install to ask for single-machine/hosted-fleet style")
    expect("single-machine - one starter machine runs the control node and first worker" in text, "expected single-machine setup guidance")
    expect("hetzner        - control node places pods onto registered Hetzner workers" in text, "expected Hetzner setup guidance")
    expect("akamai-linode  - control node places pods onto registered Akamai Linode workers" in text, "expected Akamai Linode setup guidance")
    expect("write_kv ARCLINK_CONTROL_DEPLOYMENT_STYLE" in text, "expected deployment style to persist in generated config")
    expect('default_executor_adapter="local"' in text, "expected single-machine style to default to local execution")
    expect('default_executor_adapter="ssh"' in text, "expected remote fleet styles to default to SSH execution")
    expect('default_register_local_fleet_host="1"' in text, "expected single-machine style to default to starter worker registration")
    expect("ArcLink ingress mode (domain/tailscale)" in text, "expected control install to ask for domain or Tailscale ingress")
    expect("publish_control_tailscale_ingress()" in text, "expected control install to publish Dockerized control surfaces through Tailscale")
    expect('"http://127.0.0.1:$api_port/api"' in text, "expected Tailscale /api route to preserve the API prefix")
    expect('"http://127.0.0.1:$notion_port$notion_path"' in text, "expected Tailscale Notion route to preserve its callback path")
    expect("Local/starter fleet SSH user" in text, "expected local starter fleet registration to collect an SSH target user")
    expect("ARCLINK_LOCAL_FLEET_SSH_USER:-arclink" in text, "expected local fleet SSH user to default to arclink")
    expect("ARCLINK_CONTROL_HOST_MAX_ARCPOD_SLOTS" in text, "expected control-host worker slot cap to be first-class config")
    expect('"placement_role": "control_reserve"' in text, "expected local control host registration to mark reserve placement role")
    expect("exceeds the control-host reserve cap" in text, "expected local control host registration to clamp ArcPod capacity")
    expect("Create/repair local fleet Unix user and authorize this key now" in text, "expected local fleet bootstrap helper prompt")
    expect("ensure_local_fleet_ssh_access()" in text, "expected idempotent local fleet authorized_keys helper")
    expect("ARCLINK_FLEET_SHARE_HUB_ROOT" in text and "/arcdata/captains" in text, "expected Captain fleet-share hub root to be a first-class control config default")
    expect("test_local_fleet_ssh_access()" in text, "expected local fleet SSH smoke test helper")
    expect("ARCLINK_LOCAL_FLEET_SSH_SMOKE_TIMEOUT_SECONDS" in text and "timeout --kill-after=5s" in text, "expected local starter SSH smoke to be time-bounded")
    expect("IdentityAgent=none" in text, "expected key-file SSH lanes to ignore inherited SSH agent sockets")
    expect("continuing control upgrade and leaving fleet health to inventory probes" in text, "expected local starter SSH smoke failure to degrade without aborting control upgrade")
    expect("install_local_fleet_probe_wrapper()" in text, "expected local starter bootstrap to install the fleet probe wrapper")
    expect("/usr/local/bin/arclink-fleet-probe-wrapper" in text, "expected local starter probe wrapper to be installed into PATH")
    expect("ARCLINK_FLEET_ADMISSION_FILE" in text, "expected local starter probe wrapper config to include admission state")
    expect("arclink-fleet-probe-wrapper liveness" in text, "expected local starter SSH smoke test to verify probe execution")
    expect("ensure_control_local_fleet_worker_registered()" in text, "expected local starter worker to be auto-registered before readiness")
    expect("sync_control_docker_image_to_fleet_workers()" in text, "expected control upgrades to seed the ArcLink image to SSH workers")
    expect("docker image save \"$image\" | timeout \"$load_timeout\" ssh" in text, "expected fleet image sync to use a bounded private SSH lane")
    expect("timeout \"$inspect_timeout\" ssh" in text and "ServerAliveInterval=5" in text and "arclink-ssh-ok" in text, "expected fleet image inspect SSH to be time-bounded and prove readiness")
    expect("docker image inspect --format '{{.Id}}' $q_image 2>/dev/null || true\" </dev/null" in text, "expected fleet image inspect SSH not to consume the worker row stream")
    expect(
        "metadata.get(\"private_dns_name\")" in text
        and "metadata.get(\"wireguard_dns_name\")" in text
        and "metadata.get(\"private_mesh_dns_name\")" in text
        and "metadata.get(\"ssh_host\")" in text,
        "expected fleet image sync to prefer WireGuard/private mesh hosts",
    )
    expect("image_sync_failed" in text and "metadata_json" in text and "image_sync_state" in text, "expected image sync failures to be tracked separately from liveness")
    expect("next successful image sync" in text, "expected image sync failure copy to require successful image sync before placement resumes")
    expect("One or more fleet image syncs failed; affected workers were marked image_sync_failed" in text and "return 1" not in extract(text, "sync_control_docker_image_to_fleet_workers() {", "derive_control_worker_join_url() {"), "fleet image sync should degrade bad workers without aborting control upgrade")
    expect("run_control_fleet_ssh_key()" in text, "expected a first-class fleet public key command")
    expect("register_control_remote_fleet_worker()" in text, "expected interactive remote fleet worker registration")
    expect("register_fleet_host(" in text, "expected remote worker registration to persist fleet inventory")
    expect("ARCLINK_EXECUTOR_MACHINE_HOST_ALLOWLIST" in text, "expected remote worker registration to update SSH executor allowlist")
    expect("usermod -aG docker" in text, "expected local fleet user to be granted Docker group access when available")
    expect("I have added this public key to the starter/fleet node authorized_keys" in text, "expected idempotent fleet SSH key handoff prompt")
    expect("No starter Sovereign worker host is selected." in text, "expected workerless control installs to be called out")
    expect("control-plane only and disable ArcPod provisioning" in text, "expected workerless installs to finish as blocked control-plane only")
    expect("ARCLINK_CONTROL_ALLOW_WORKERLESS_BOOTSTRAP" in text, "expected explicit workerless bootstrap override")
    expect('ARCLINK_CONTROL_PROVISIONER_ENABLED="0"' in text, "expected workerless bootstrap to disable provisioning")
    expect("print_control_provisioning_readiness_summary()" in text, "expected control flows to print provisioning readiness")
    expect("control_node_provisioning_readiness(conn, env=source_env)" in text, "expected deploy readiness to use docker config and dashboard truth model")
    expect("Sovereign provisioning readiness: ready to provision ArcPods" in text, "expected ready-to-provision summary copy")
    expect("Sovereign provisioning readiness: blocked" in text, "expected blocked provisioning summary copy")
    expect("Operator Raven/control channel" in text, "expected Sovereign install to collect operator Raven channel intent")
    expect("Operator Raven enabled channels" in text, "expected Sovereign install to choose one or both operator chat surfaces")
    expect('both|telegram,discord|discord,telegram' in text, "expected Sovereign install to normalize both-channel operator Raven answers")
    expect("Primary operator response channel (tui-only/telegram/discord)" in text, "expected Sovereign install to choose a primary operator response channel")
    expect("Allowed operator Telegram user IDs" in text, "expected Sovereign install to collect Telegram operator allowlist hints")
    expect("LLM router default model or provider-side fallback CSV" in text, "expected Sovereign install to ask for router fallback-capable model string")
    expect("use a two-model CSV such as model-a,model-b" in text, "expected Sovereign install to encourage provider-side fallback")
    expect("LLM router allowed models or provider-side fallback strings" in text, "expected Sovereign install to persist router allowed models")
    expect("LLM router retry fallback models for 429/5xx" in text, "expected Sovereign install to collect router retry fallback models")
    expect("LLM router fallback status codes" in text, "expected Sovereign install to collect retryable router status codes")
    expect("LLM router emergency model replacements old=new" in text, "expected Sovereign install to collect emergency model replacement policy")
    expect("write_kv ARCLINK_LLM_ROUTER_DEFAULT_MODEL" in text, "expected runtime config to persist router default model")
    expect("write_kv ARCLINK_LLM_ROUTER_ALLOWED_MODELS" in text, "expected runtime config to persist router allowed models")
    expect("write_kv ARCLINK_LLM_ROUTER_FALLBACK_MODELS" in text, "expected runtime config to persist router fallback models")
    expect("deploy.sh docker install" not in usage_snippet, "Shared Host Docker install must not be advertised in deploy usage")
    expect("choose_docker_mode()" not in text, "retired Shared Host Docker submenu should be removed")
    expect("docker_usage()" not in text, "retired Shared Host Docker usage wrapper should be removed")
    expect("run_docker_deploy_flow()" not in text, "retired Shared Host Docker deploy wrapper should be removed")
    expect("run_docker_install_flow()" not in text, "retired Shared Host Docker install flow should be removed")
    expect("run_docker_reconfigure_flow()" not in text, "retired Shared Host Docker reconfigure flow should be removed")
    expect("docker_command_from_mode()" not in text, "retired Shared Host Docker shortcut mapper should be removed")
    expect("DOCKER_DEPLOY_COMMAND" not in text and "DOCKER_DEPLOY_ARGS" not in text, "retired Docker parser state should be removed")
    expect('MODE="docker"' not in text, "main menu and parser must not route to Shared Host Docker")
    expect("docker-install|docker-upgrade|docker-reconfigure" in text, "parser should still recognize retired Docker shortcut aliases")
    expect('local helper="$BOOTSTRAP_DIR/bin/arclink-docker.sh"' in text, "expected deploy.sh to delegate to Docker helper")
    expect("retired_shared_host_docker_mode" in text, "retired Docker aliases must fail closed")
    expect("run_arclink_docker build" in text, "expected Control Node install to build through Docker helper")
    expect("run_arclink_docker record-release" in text, "expected Control Node install to record release state through Docker helper")
    expect("run_arclink_docker health" in text, "expected Control Node install to run health through Docker helper")
    print("PASS test_deploy_sh_retires_public_docker_control_center")


def test_control_deployment_style_aliases_are_normalized() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "normalize_control_deployment_style() {", "normalize_tailscale_host_strategy() {")
    script = f"""
{snippet}
normalize_control_deployment_style single_machine
normalize_control_deployment_style local
normalize_control_deployment_style hcloud
normalize_control_deployment_style linode
normalize_control_deployment_style unknown-value
"""
    result = bash(script)
    expect(result.returncode == 0, f"deployment style normalization failed: {result.stderr}")
    lines = result.stdout.strip().splitlines()
    expect(
        lines == ["single-machine", "single-machine", "hetzner", "akamai-linode", "single-machine"],
        str(lines),
    )
    print("PASS test_control_deployment_style_aliases_are_normalized")


def test_control_reconfigure_prompt_normalization_is_shell_safe() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "normalize_tailscale_host_strategy() {", "ensure_control_fleet_ssh_key() {")
    script = f"""
set -euo pipefail
{snippet}
normalize_tailscale_host_strategy subdomain
normalize_operator_channel_set Discord
normalize_operator_channel_set 'discord, telegram'
normalize_operator_channel_set 'telegram+discord'
normalize_operator_channel_set 'tui only'
normalize_operator_primary_channel Discord
normalize_operator_primary_channel none
"""
    result = bash(script)
    expect(result.returncode == 0, f"control prompt normalization failed: {result.stderr}")
    lines = result.stdout.strip().splitlines()
    expect(
        lines == ["path", "discord", "telegram,discord", "telegram,discord", "tui-only", "discord", "tui-only"],
        str(lines),
    )
    expect("price ID ($" not in text, "control price prompt labels must not expand $1/$2 under set -u")
    expect("price ID (USD 149/month)" in text, "expected shell-safe price prompt labels")
    expect("tr '[:upper:] ' '[:lower:]'" not in text, "operator channel normalization must not use invalid tr classes")
    expect(
        "Tailscale deployment URL strategy (path only; use domain mode for wildcard subdomains)" in text,
        "expected Tailscale strategy prompt to document path-only MagicDNS/Funnel behavior",
    )
    print("PASS test_control_reconfigure_prompt_normalization_is_shell_safe")


def test_control_reconfigure_autoregisters_local_starter_worker() -> None:
    text = DEPLOY_SH.read_text()
    helper = extract(text, "ensure_control_local_fleet_worker_registered() {", "run_control_enrollment() {")
    local_helper = extract(text, "ensure_local_fleet_ssh_access() {", "test_local_fleet_ssh_access() {")
    install_flow = extract(text, "run_control_install_flow() {", "run_control_reconfigure_flow() {")
    reconfigure_flow = extract(text, "run_control_reconfigure_flow() {", "control_host_priv_dir() {")
    expect("ARCLINK_REGISTER_LOCAL_FLEET_HOST" in helper, "helper should honor the local starter flag")
    expect("register_fleet_host" in helper, "helper should persist a fleet host row")
    expect('"executor": "local"' in helper, "local starter worker should persist the container-safe local executor")
    expect('"provisioner_executor_adapter": executor_adapter' in helper, "local starter metadata should retain the global provisioner adapter for diagnostics")
    expect('"registered_by": "deploy.sh control local starter auto-register"' in helper, "helper should tag auto-registration metadata")
    expect("tags={\"starter\": True, \"local\": True}" in helper, "helper should tag the local starter worker")
    expect("ensure_control_fleet_ssh_key" in helper, "helper should resolve host-side fleet SSH key paths before local starter repair")
    expect("ensure_local_fleet_ssh_access" in helper, "helper should repair local starter SSH/probe access during install and upgrade")
    expect("fleet_share_hub_root" in local_helper and "mkdir -p \"$fleet_share_hub_root\"" in local_helper, "local starter repair should create the Captain fleet-share hub root")
    expect("test_local_fleet_ssh_access" in helper, "helper should verify local starter probe access during install and upgrade")
    expect(
        install_flow.index("ensure_control_local_fleet_worker_registered") < install_flow.index("print_control_provisioning_readiness_summary"),
        "install should auto-register the local starter before printing readiness",
    )
    expect(
        reconfigure_flow.index("ensure_control_local_fleet_worker_registered") < reconfigure_flow.index("print_control_provisioning_readiness_summary"),
        "reconfigure should auto-register the local starter before printing readiness",
    )
    print("PASS test_control_reconfigure_autoregisters_local_starter_worker")


def test_control_install_collects_trusted_host_acknowledgement_before_build() -> None:
    text = DEPLOY_SH.read_text()
    helpers = extract(text, "docker_trusted_host_risk_accepted() {", "ensure_control_fleet_ssh_key() {")
    collect = extract(text, "collect_control_install_answers() {", "run_control_install_flow() {")
    install_flow = extract(text, "run_control_install_flow() {", "run_control_reconfigure_flow() {")
    reconfigure_flow = extract(text, "run_control_reconfigure_flow() {", "control_host_priv_dir() {")
    expect("Accept GAP-019 trusted-host residual risk for this operator machine" in helpers, "expected explicit trusted-host prompt")
    expect('ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED="accepted"' in helpers, "expected accepted value to be written only after acknowledgement")
    expect("collect_control_trusted_host_acknowledgement" in collect, "control answers should collect trusted-host acknowledgement")
    expect("verify_control_docker_trusted_host_risk_accepted" in install_flow, "control install/upgrade should verify trusted-host acknowledgement")
    expect(
        install_flow.index("verify_control_docker_trusted_host_risk_accepted") < install_flow.index("run_arclink_docker build"),
        "control install/upgrade should fail before image build when trusted-host acknowledgement is missing",
    )
    expect(
        reconfigure_flow.index("verify_control_docker_trusted_host_risk_accepted") < reconfigure_flow.index("run_arclink_docker config -q"),
        "control reconfigure should fail early when trusted-host acknowledgement is missing",
    )
    print("PASS test_control_install_collects_trusted_host_acknowledgement_before_build")


def test_control_runtime_reset_is_backup_first_and_guarded() -> None:
    text = DEPLOY_SH.read_text()
    reset = extract(text, "run_control_runtime_reset() {", "control_command_from_mode() {")
    backup = extract(text, "create_control_runtime_backup() {", "run_control_runtime_backup() {")
    operator_confirm = extract(text, "confirm_control_operator_runtime_reset() {", "stop_control_runtime_writers() {")
    backup_confirm = extract(text, "confirm_control_runtime_backup_choice() {", "stop_control_runtime_writers() {")
    expect("create_control_runtime_backup" in reset, "expected reset to offer a backup before clearing data")
    expect(
        reset.index("create_control_runtime_backup") < reset.index("reset_control_runtime_database"),
        "expected optional reset backup to run before touching the database",
    )
    expect("stop_control_generated_pod_containers" in text, "expected reset to quiesce generated pods before reset")
    expect(
        reset.index("stop_control_generated_pod_containers") < reset.index("create_control_runtime_backup"),
        "expected generated pods to stop before optional reset backup tar reads pod data",
    )
    expect("confirm_control_runtime_reset" in reset, "expected reset to require confirmation")
    expect('confirm_control_runtime_reset "$scope"' in reset, "expected reset confirmation to receive sandbox/production scope")
    expect('confirm_control_operator_runtime_reset "$scope"' in reset, "expected reset to separately ask about Operator state")
    expect('confirm_control_runtime_backup_choice "$scope"' in reset, "expected reset to ask whether to create a backup")
    expect("CONTROL_RESET_CREATE_BACKUP" in reset, "expected reset to carry explicit backup yes/no mode")
    expect("Create a private runtime backup before wiping data? [Y/n]" in backup_confirm,
           "expected reset backup prompt to default yes but allow no")
    expect("Skipping reset backup at operator request." in reset,
           "expected reset to support skipping the long backup step")
    expect("No reset backup was created." in reset,
           "expected reset summary to disclose when backup was skipped")
    expect("CONTROL_RESET_OPERATOR_STATE" in reset, "expected reset to carry explicit Operator preservation/wipe mode")
    expect(
        "Preserving Operator Raven/Hermes state; resetting Captain/customer runtime only." in reset,
        "expected default reset to preserve Operator state",
    )
    expect("remove_control_operator_runtime_state" in reset, "expected explicit Operator wipe to delete Operator state after backup")
    expect("ensure_control_operator_agent" in reset, "expected reset to recreate the single Operator Hermes agent")
    expect("ARCLINK_CONFIRM_RUNTIME_RESET" in text, "expected reset to support explicit non-interactive confirmation")
    expect("ARCLINK_CONFIRM_SANDBOX_RESET" in text, "expected sandbox reset to support explicit non-interactive confirmation")
    expect("ARCLINK_CONFIRM_PRODUCTION_RESET" in text, "expected production reset to support explicit non-interactive confirmation")
    expect("ARCLINK_CONFIRM_PRODUCTION_RESET_HOST" in text, "expected production reset to require host-specific confirmation")
    expect("ARCLINK_RESET_OPERATOR_STATE=wipe" in operator_confirm,
           "expected non-interactive Operator wipe to require an explicit mode")
    expect("ARCLINK_CONFIRM_OPERATOR_RESET='RESET OPERATOR'" in operator_confirm,
           "expected non-interactive Operator wipe to require the Operator phrase")
    expect("Preserve Operator Raven/Hermes state? [Y/n]" in operator_confirm,
           "expected interactive reset to default to preserving Operator Raven/Hermes")
    expect("Type RESET OPERATOR to wipe Operator Raven/Hermes too" in operator_confirm,
           "expected Operator wipe to need a typed phrase")
    expect("Type RESET SANDBOX to continue" in text, "expected sandbox reset prompt to require a typed acknowledgement")
    expect("First type RESET PRODUCTION" in text, "expected production reset prompt to require a production acknowledgement")
    expect("down --remove-orphans --volumes" in text, "expected reset to remove generated pod stacks and named volumes")
    expect("/arcdata/deployments" in text, "expected reset to remove generated pod state")
    expect("arclink-priv.tgz" in backup, "expected backup to snapshot private state")
    expect("arcdata-deployments.tgz" in backup, "expected backup to snapshot generated pod data")
    expect("tar_tree_without_sockets" in text, "expected backup to skip runtime sockets instead of warning on them")
    expect("arclink_channel_pairing_codes" in text, "expected reset to clear channel pairing codes")
    expect("arclink_users" in text, "expected reset to clear client users")
    expect("arclink_deployments" in text, "expected reset to clear deployments")
    expect("UPDATE arclink_fleet_hosts" in text, "expected reset to reconcile preserved fleet host load")
    expect("observed_load =" in text, "expected reset to clear stale fleet saturation")
    expect("DELETE FROM arclink_admins" not in text, "reset must not delete admin accounts")
    expect("DELETE FROM arclink_fleet_hosts" not in text, "reset must not delete fleet hosts")
    print("PASS test_control_runtime_reset_is_backup_first_and_guarded")


def test_runtime_backup_tar_honors_pruned_reset_backups() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "tar_tree_without_sockets() {", "create_control_runtime_backup() {")
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        output = root / "arclink-priv" / "state" / "reset-backups" / "new" / "arclink-priv.tgz"
        (root / "arclink-priv" / "config").mkdir(parents=True)
        (root / "arclink-priv" / "state" / "reset-backups" / "old").mkdir(parents=True)
        output.parent.mkdir(parents=True)
        (root / "arclink-priv" / "config" / "live.env").write_text("live=1\n", encoding="utf-8")
        (root / "arclink-priv" / "state" / "reset-backups" / "old" / "stale.txt").write_text(
            "must-not-be-packed\n",
            encoding="utf-8",
        )
        script = f"""
set -euo pipefail
{snippet}
tar_tree_without_sockets {shlex.quote(str(output))} {shlex.quote(str(root))} arclink-priv arclink-priv/state/reset-backups
tar -tzf {shlex.quote(str(output))} > {shlex.quote(str(root / "listing.txt"))}
if grep -q 'reset-backups' {shlex.quote(str(root / "listing.txt"))}; then
  cat {shlex.quote(str(root / "listing.txt"))}
  exit 1
fi
grep -q '^arclink-priv/config/live.env$' {shlex.quote(str(root / "listing.txt"))}
"""
        result = bash(script)
        expect(result.returncode == 0, result.stderr or result.stdout)
    print("PASS test_runtime_backup_tar_honors_pruned_reset_backups")


def test_control_runtime_reset_preserves_operator_state_by_default() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "reset_control_runtime_database() {", "print_control_runtime_counts() {")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "control.sqlite3"
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE arclink_users (user_id TEXT PRIMARY KEY);
                CREATE TABLE arclink_deployments (
                  deployment_id TEXT PRIMARY KEY,
                  user_id TEXT NOT NULL,
                  metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE operator_actions (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  requested_by TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE notification_outbox (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  target_kind TEXT NOT NULL,
                  target_id TEXT NOT NULL,
                  extra_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE arclink_llm_router_keys (
                  key_id TEXT PRIMARY KEY,
                  deployment_id TEXT NOT NULL,
                  user_id TEXT NOT NULL
                );
                """
            )
            conn.executemany("INSERT INTO arclink_users (user_id) VALUES (?)", [("operator",), ("captain",)])
            conn.executemany(
                "INSERT INTO arclink_deployments (deployment_id, user_id, metadata_json) VALUES (?, ?, ?)",
                [
                    ("operator", "operator", '{"operator_agent": true, "operator_agent_runtime": "control-stack"}'),
                    ("arcdep_1", "captain", "{}"),
                ],
            )
            conn.executemany(
                "INSERT INTO operator_actions (requested_by) VALUES (?)",
                [("telegram:operator",), ("discord:operator",)],
            )
            conn.executemany(
                "INSERT INTO notification_outbox (target_kind, target_id, extra_json) VALUES (?, ?, ?)",
                [
                    ("operator", "operator", "{}"),
                    ("public-agent-turn", "operator", '{"operator_turn": true, "deployment_id": "operator"}'),
                    ("public-bot-user", "captain", '{"deployment_id": "arcdep_1"}'),
                ],
            )
            conn.executemany(
                "INSERT INTO arclink_llm_router_keys (key_id, deployment_id, user_id) VALUES (?, ?, ?)",
                [("op-key", "operator", "operator"), ("captain-key", "arcdep_1", "captain")],
            )
            conn.commit()
        finally:
            conn.close()

        result = bash(f"set -euo pipefail\n{snippet}\nreset_control_runtime_database {shlex.quote(str(db_path))} preserve")
        expect(result.returncode == 0, result.stderr or result.stdout)
        expect("Operator reset mode: preserved Operator Raven/Hermes rows" in result.stdout, result.stdout)

        conn = sqlite3.connect(db_path)
        try:
            users = {row[0] for row in conn.execute("SELECT user_id FROM arclink_users")}
            deployments = {row[0] for row in conn.execute("SELECT deployment_id FROM arclink_deployments")}
            keys = {row[0] for row in conn.execute("SELECT key_id FROM arclink_llm_router_keys")}
            outbox = {
                (row[0], row[1])
                for row in conn.execute("SELECT target_kind, target_id FROM notification_outbox")
            }
            operator_action_count = conn.execute("SELECT COUNT(*) FROM operator_actions").fetchone()[0]
        finally:
            conn.close()
        expect(users == {"operator"}, str(users))
        expect(deployments == {"operator"}, str(deployments))
        expect(keys == {"op-key"}, str(keys))
        expect(operator_action_count == 2, f"operator actions should be preserved, got {operator_action_count}")
        expect(("operator", "operator") in outbox and ("public-agent-turn", "operator") in outbox, str(outbox))
        expect(("public-bot-user", "captain") not in outbox, str(outbox))
    print("PASS test_control_runtime_reset_preserves_operator_state_by_default")


def test_control_runtime_reset_can_explicitly_wipe_operator_state() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "reset_control_runtime_database() {", "print_control_runtime_counts() {")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "control.sqlite3"
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE arclink_users (user_id TEXT PRIMARY KEY);
                CREATE TABLE arclink_deployments (
                  deployment_id TEXT PRIMARY KEY,
                  user_id TEXT NOT NULL,
                  metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE operator_actions (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  requested_by TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE notification_outbox (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  target_kind TEXT NOT NULL,
                  target_id TEXT NOT NULL,
                  extra_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE arclink_llm_router_keys (
                  key_id TEXT PRIMARY KEY,
                  deployment_id TEXT NOT NULL,
                  user_id TEXT NOT NULL
                );
                """
            )
            conn.execute("INSERT INTO arclink_users (user_id) VALUES ('operator')")
            conn.execute(
                "INSERT INTO arclink_deployments (deployment_id, user_id, metadata_json) VALUES ('operator', 'operator', ?)",
                ('{"operator_agent": true}',),
            )
            conn.execute("INSERT INTO operator_actions (requested_by) VALUES ('telegram:operator')")
            conn.execute(
                "INSERT INTO notification_outbox (target_kind, target_id, extra_json) VALUES ('operator', 'operator', '{}')"
            )
            conn.execute(
                "INSERT INTO arclink_llm_router_keys (key_id, deployment_id, user_id) VALUES ('op-key', 'operator', 'operator')"
            )
            conn.commit()
        finally:
            conn.close()

        result = bash(f"set -euo pipefail\n{snippet}\nreset_control_runtime_database {shlex.quote(str(db_path))} wipe-operator")
        expect(result.returncode == 0, result.stderr or result.stdout)
        expect("Operator reset mode: wiped Operator Raven/Hermes rows" in result.stdout, result.stdout)

        conn = sqlite3.connect(db_path)
        try:
            for table in ("arclink_users", "arclink_deployments", "operator_actions", "notification_outbox", "arclink_llm_router_keys"):
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                expect(count == 0, f"{table} should be empty after explicit Operator wipe, got {count}")
        finally:
            conn.close()
    print("PASS test_control_runtime_reset_can_explicitly_wipe_operator_state")


def test_control_reset_modes_have_separate_confirmations() -> None:
    text = DEPLOY_SH.read_text()
    chooser = extract(text, "choose_control_mode() {", "detect_tailscale() {")
    commands = extract(text, "control_command_from_mode() {", "run_control_deploy_flow() {")
    dispatch = extract(text, "run_control_deploy_flow() {", "run_install_flow() {")
    confirm = extract(text, "confirm_control_runtime_reset() {", "stop_control_runtime_writers() {")
    operator_confirm = extract(text, "confirm_control_operator_runtime_reset() {", "stop_control_runtime_writers() {")
    expect('CONTROL_DEPLOY_COMMAND="reset-sandbox"' in chooser, "menu should route sandbox reset explicitly")
    expect('CONTROL_DEPLOY_COMMAND="reset-production"' in chooser, "menu should route production reset explicitly")
    expect('control-reset-runtime) printf' in commands and '"reset-runtime"' in commands, "legacy reset-runtime alias should remain")
    expect('control-reset-sandbox) printf' in commands and '"reset-sandbox"' in commands, "sandbox reset shortcut should be present")
    expect('control-reset-production) printf' in commands and '"reset-production"' in commands, "production reset shortcut should be present")
    expect("reset-runtime|reset-sandbox)" in dispatch, "reset-runtime should dispatch through the sandbox reset path")
    expect("run_control_runtime_reset sandbox" in dispatch, "sandbox reset should pass sandbox scope")
    expect("run_control_runtime_reset production" in dispatch, "production reset should pass production scope")
    expect("RESET SANDBOX" in confirm, "sandbox reset should require the sandbox phrase")
    expect("RESET PRODUCTION" in confirm, "production reset should require the production phrase")
    expect("control_runtime_reset_host_name" in text, "production reset should use a concrete host confirmation")
    expect("RESET OPERATOR" in operator_confirm, "operator wipe should require its own confirmation phrase")
    print("PASS test_control_reset_modes_have_separate_confirmations")


def test_control_fleet_worker_registration_is_first_class() -> None:
    text = DEPLOY_SH.read_text()
    fleet_key = extract(text, "run_control_fleet_ssh_key() {", "is_safe_local_fleet_user() {")
    register = extract(text, "register_control_remote_fleet_worker() {", "publish_control_tailscale_ingress() {")
    remote_bootstrap = extract(text, "run_remote_fleet_worker_bootstrap() {", "register_control_remote_fleet_worker() {")
    expect("deploy.sh control fleet-key" in text, "usage should expose fleet-key")
    expect("deploy.sh control fleet-key --rotate --json" in text, "usage should expose fleet key rotation JSON")
    expect("deploy.sh control register-worker" in text, "usage should expose register-worker")
    expect(
        "--hostname worker-1 --ssh-host 10.44.0.11 --bootstrap-remote --bootstrap-ssh-host 203.0.113.10 --bootstrap-ssh-user root --ssh-user arclink --json" in text,
        "usage should expose push-button worker bootstrap without requiring WireGuard internals",
    )
    expect("run_control_fleet_ssh_key()" in text, "expected first-class public key command")
    expect("--rotate" in fleet_key and '"rotated"' in fleet_key, "fleet-key should support audited scriptable rotation output")
    expect('"public_key"' in fleet_key and '"key_path"' in fleet_key, "fleet-key JSON should expose only public key metadata")
    expect("ensure_control_fleet_ssh_key" in register, "worker registration should reuse the Sovereign control SSH key")
    expect("--hostname" in register and "--ssh-host" in register and "--ssh-user" in register, "worker registration should parse non-interactive target flags")
    expect("--bootstrap-remote" in register and "--bootstrap-ssh-host" in register and "--bootstrap-ssh-user" in register, "worker registration should parse push-button remote bootstrap flags")
    expect("run_remote_fleet_worker_bootstrap" in register, "register-worker should be able to run the full remote join")
    expect("mint_control_fleet_enrollment_json" in remote_bootstrap, "remote bootstrap should mint the one-time token internally")
    expect("--token-stdin" in remote_bootstrap and "--token " not in remote_bootstrap, "remote bootstrap must pass enrollment tokens over stdin, not argv")
    expect('printf \'%s\\n\' "$enrollment_token" | ssh' in remote_bootstrap, "remote bootstrap should pipe the token through SSH stdin")
    expect("revoke_control_fleet_enrollment_id" in remote_bootstrap, "remote bootstrap should revoke the token on failed join")
    expect("sudo -n --" in remote_bootstrap, "non-root remote bootstrap should require passwordless sudo without prompting")
    expect("bash $q_remote_stage/bin/arclink-fleet-join.sh" in remote_bootstrap, "remote bootstrap should invoke the staged join through bash for noexec temp mounts")
    expect("arclink-fleet-join.sh" in remote_bootstrap and "arclink-fleet-probe-wrapper" in remote_bootstrap and "ensure-prereqs.sh" in remote_bootstrap, "remote bootstrap should stage the minimal join assets")
    expect("lookup_control_wireguard_worker_public_key" in register, "register-worker should read callback-reported WireGuard public keys")
    expect("--private-dns-name" in register and '"private_dns_name"' in register, "worker registration should store per-worker private mesh DNS metadata")
    expect("--tailscale-dns-name" in register and '"tailscale_dns_name"' in register, "worker registration should store per-worker Tailscale DNS metadata")
    expect("--wireguard-private-ip" in register and '"wireguard"' in register, "worker registration should store per-worker WireGuard metadata")
    expect("ensure_control_wireguard_ready" in register, "worker registration should prepare control WireGuard material")
    expect("ensure_control_wireguard_peer" in register, "worker registration should append known worker peers to control WireGuard config")
    expect("activate_control_wireguard_interface" in text, "control install/reconfigure should activate the control WireGuard interface")
    expect("ArcLink WireGuard fleet git SSH" in text and "to any port 22 proto tcp" in text, "control WireGuard setup should allow fleet Git SSH only from the private mesh subnet")
    expect("ARCLINK_WIREGUARD_ACTIVATE" in text, "control WireGuard activation should be explicitly configurable")
    expect("detect_control_wireguard_public_host" in text, "control WireGuard endpoint should be auto-derived for normal operators")
    expect("curl -4fsS --max-time 4 https://api.ipify.org" in text, "endpoint derivation should have a bounded public IPv4 probe")
    expect("ip -4 route get 1.1.1.1" in text, "endpoint derivation should fall back to the host outward IPv4")
    expect("ARCLINK_CONTROL_PRIVATE_BIND_HOST" in text, "control install should persist the private WireGuard bind host")
    expect("ARCLINK_CONTROL_PRIVATE_HTTP_PORT" in text, "control install should persist the private WireGuard HTTP port")
    expect("control_private_base_url_from_bind" in text, "control install should auto-derive private control URL from the WireGuard bind host")
    expect("ensure_control_private_mesh_defaults" in text, "WireGuard readiness should repair private control URL defaults")
    expect("ARCLINK_CONTROL_ADVANCED_PROMPTS" in text, "control WireGuard internals should only prompt in advanced mode")
    expect("ARCLINK_FLEET_REGISTER_ADVANCED_PROMPTS" in register, "worker registration internals should only prompt in advanced mode")
    expect("ArcLink will SSH in once, install or verify Docker and WireGuard" in register, "default worker registration should explain the push-button join")
    expect("next_control_wireguard_worker_ip" in register, "interactive worker registration should suggest the next tunnel IP")
    expect("sync_control_wireguard_peers_from_inventory" in text, "control install/reconfigure should sync callback-reported WireGuard peers")
    expect('"control_network_mode"] = "remote"' in register, "remote worker registration should mark ArcPods as remote control-network renders")
    expect("--tags-json" in register and "json.loads(tags_raw or \"{}\")" in register, "worker registration should accept JSON placement tags")
    expect('raw.strip().lower() in {"", "none", "null", "{}"}' in register, "plain placement tags should treat empty JSON/default answers as no tags")
    expect("--no-smoke-test" in register and "--smoke-test" in register, "worker registration should gate live SSH smoke in scriptable mode")
    expect('"$remote_bootstrap" == "1" || "$json" != "1" || "$smoke_requested" == "1"' in register, "remote bootstrap should run post-join smoke proof by default without contaminating JSON stdout")
    expect('"restart_required"' in register, "JSON worker registration should report that control workers need refresh")
    expect("Fleet inventory hostname" in register, "worker registration should ask for placement hostname")
    expect("SSH host" in register and "SSH user" in register, "worker registration should ask for SSH target")
    expect("Remote deployment state root base" in register, "worker registration should collect per-worker state root")
    expect("Fleet capacity slots" in register, "worker registration should collect capacity")
    expect("Placement tags, comma-separated key=value" in register, "worker registration should collect placement tags")
    expect("test_remote_fleet_ssh_access" in register, "worker registration should smoke-test SSH executor readiness")
    expect("ARCLINK_EXECUTOR_ADAPTER=\"ssh\"" in register, "worker registration should be able to enable SSH execution")
    expect("ARCLINK_EXECUTOR_MACHINE_MODE_ENABLED=\"1\"" in register, "worker registration should enable machine-mode guard")
    expect('smoke_status" == "passed"' in register and 'ARCLINK_CONTROL_PROVISIONER_ENABLED="1"' in register, "worker registration should enable provisioning only after a passed smoke test")
    expect("registration_smoke_failed" in register and "registration_smoke_skipped" in register and "status = 'degraded'" in register, "worker registration should fail closed when smoke proof is skipped or failed")
    expect("append_control_csv_value" in register, "worker registration should append hosts to the allowlist")
    expect("ARCLINK_EXECUTOR_MACHINE_HOST_ALLOWLIST" in register, "worker registration should update SSH host allowlist")
    expect("register_fleet_host(" in register, "worker registration should persist a fleet host row")
    expect('"ssh_host": ssh_host' in register and '"ssh_user": ssh_user' in register, "worker registration should store SSH metadata")
    expect("run_arclink_docker up control-provisioner control-action-worker control-api" in register, "worker registration should refresh control workers")
    expect("print_control_provisioning_readiness_summary" in register, "worker registration should print provisioning readiness after refresh")
    print("PASS test_control_fleet_worker_registration_is_first_class")


def test_control_inventory_submenu_and_aliases_are_first_class() -> None:
    text = DEPLOY_SH.read_text()
    docs = (REPO / "docs" / "arclink" / "fleet-cli.md").read_text(encoding="utf-8")
    inventory = extract(text, "run_control_inventory() {", "publish_control_tailscale_ingress() {")
    expect("deploy.sh control inventory list" in text, "usage should expose inventory list")
    expect("deploy.sh control inventory health --json" in text, "usage should expose inventory health JSON")
    expect("deploy.sh control inventory rotate-key --json" in text, "usage should expose inventory key rotation JSON")
    expect("deploy.sh control inventory re-attest" in text, "usage should expose explicit re-attestation")
    expect("Inventory and ASU placement" in text, "control menu should expose inventory")
    expect("control-inventory-list" in text, "shortcut alias should expose inventory list")
    expect("control-inventory-health" in text, "shortcut alias should expose inventory health")
    expect("control-inventory-rotate-key" in text, "shortcut alias should expose inventory key rotation")
    expect("control-inventory-re-attest" in text, "shortcut alias should expose re-attestation")
    expect("python/arclink_inventory.py" in inventory, "inventory should route through the Python inventory CLI")
    expect("health" in inventory and "re-attest" in inventory, "inventory command should expose health and re-attest")
    expect('db_path="$(control_host_db_path)"' in inventory, "inventory commands should translate container DB paths to host paths")
    expect('ARCLINK_DB_PATH="$db_path" ARCLINK_CONFIG_FILE="$docker_env"' in inventory, "inventory CLI should use the host DB path override")
    expect("fleet_ssh_key_path=\"${ARCLINK_FLEET_SSH_KEY_HOST_PATH:-${ARCLINK_FLEET_SSH_KEY_PATH:-}}\"" in inventory, "inventory probes should translate container SSH key paths to host paths")
    expect('ARCLINK_FLEET_SSH_KEY_PATH="$fleet_ssh_key_path"' in inventory, "inventory probe commands should receive a host-readable fleet SSH key")
    expect("rotate-key" in inventory and "run_control_fleet_ssh_key" in inventory, "inventory rotate-key should route to fleet key rotation")
    expect("add manual" in inventory and "add hetzner" in text and "add linode" in text, "inventory providers should be exposed")
    expect("ARCLINK_FLEET_PLACEMENT_STRATEGY" in inventory, "set-strategy should persist placement strategy")
    expect("python3 - \"$strategy\"" in inventory, "set-strategy should support clean JSON output")
    expect("HETZNER_API_TOKEN" in text and "LINODE_API_TOKEN" in text, "provider tokens should be config/env backed")
    expect("--filter status=ready" in docs and "Exit Codes" in docs, "fleet CLI docs should cover filters and exit codes")
    print("PASS test_control_inventory_submenu_and_aliases_are_first_class")


def test_control_enrollment_submenu_and_secret_are_first_class() -> None:
    text = DEPLOY_SH.read_text()
    compose = (REPO / "compose.yaml").read_text(encoding="utf-8")
    docker_helper = (REPO / "bin" / "arclink-docker.sh").read_text(encoding="utf-8")
    entrypoint = (REPO / "bin" / "docker-entrypoint.sh").read_text(encoding="utf-8")
    enrollment = extract(text, "run_control_enrollment() {", "run_control_inventory() {")

    expect("deploy.sh control enrollment mint" in text, "usage should expose enrollment mint")
    expect("deploy.sh control enrollment verify-audit-chain" in text, "usage should expose fleet enrollment audit-chain verification")
    expect("control-enrollment-mint" in text, "shortcut alias should expose enrollment mint")
    expect("control-enrollment-rotate-secret" in text, "shortcut alias should expose enrollment HMAC root rotation")
    expect("python/arclink_fleet_enrollment.py" in text, "control enrollment should route through Python enrollment CLI")
    expect("ARCLINK_FLEET_ENROLLMENT_SECRET" in enrollment, "control enrollment should require a dedicated HMAC root")
    expect("run_control_fleet_enrollment_cli" in text, "fleet enrollment commands should share one secret-exporting CLI wrapper")
    expect('ARCLINK_FLEET_ENROLLMENT_SECRET="${ARCLINK_FLEET_ENROLLMENT_SECRET:-}"' in text, "fleet enrollment CLI wrapper should export the HMAC root to Python")
    expect("ensure_control_fleet_enrollment_secret_ready" in text, "fleet enrollment CLI wrapper should self-repair missing HMAC roots")
    expect("write_docker_runtime_config" in enrollment, "control enrollment should backfill missing enrollment secret")
    expect("mint" in enrollment and "list" in enrollment and "revoke" in enrollment and "rotate-secret" in enrollment, "enrollment command should expose mint/list/revoke/rotate-secret")
    expect("random_secret" in enrollment and "fleet_enrollment_hmac_root_rotated" in (REPO / "python" / "arclink_fleet_enrollment.py").read_text(encoding="utf-8"), "rotation should mint a new HMAC root and audit the event")
    expect("ARCLINK_FLEET_ENROLLMENT_SECRET: ${ARCLINK_FLEET_ENROLLMENT_SECRET:-}" in compose, "Compose should pass fleet enrollment secret")
    expect('ensure_env_file_value ARCLINK_FLEET_ENROLLMENT_SECRET "$(random_secret)"' in docker_helper, "Docker bootstrap should seed fleet enrollment secret")
    expect("ARCLINK_FLEET_ENROLLMENT_SECRET=$q_fleet_enrollment_secret" in entrypoint, "Docker entrypoint should seed fleet enrollment secret")
    print("PASS test_control_enrollment_submenu_and_secret_are_first_class")


def test_control_docker_bootstrap_seeds_session_hash_pepper_and_gateway_broker_token() -> None:
    deploy = DEPLOY_SH.read_text(encoding="utf-8")
    docker_helper = (REPO / "bin" / "arclink-docker.sh").read_text(encoding="utf-8")
    entrypoint = (REPO / "bin" / "docker-entrypoint.sh").read_text(encoding="utf-8")
    compose = (REPO / "compose.yaml").read_text(encoding="utf-8")

    expect(
        'ARCLINK_SESSION_HASH_PEPPER="$(preserve_or_randomize_secret "${ARCLINK_SESSION_HASH_PEPPER:-}")"' in deploy,
        "control/docker runtime config should generate a durable session hash pepper before writing docker.env",
    )
    expect(
        'ensure_env_file_value ARCLINK_SESSION_HASH_PEPPER "$(random_secret)"' in docker_helper,
        "docker bootstrap should backfill a missing session hash pepper before Compose reads docker.env",
    )
    expect(
        "ARCLINK_SESSION_HASH_PEPPER=$q_session_hash_pepper" in entrypoint,
        "fresh Docker config generation should include the session hash pepper",
    )
    expect(
        "ARCLINK_SESSION_HASH_PEPPER: ${ARCLINK_SESSION_HASH_PEPPER:-}" in compose,
        "Compose should pass the session hash pepper into hosted API containers",
    )
    expect(
        "ARCLINK_SESSION_HASH_PEPPER_REQUIRED: ${ARCLINK_SESSION_HASH_PEPPER_REQUIRED:-1}" in compose,
        "Compose should fail closed when a raw control stack lacks a session hash pepper",
    )
    expect(
        'ARCLINK_GATEWAY_EXEC_BROKER_TOKEN="$(preserve_or_randomize_secret "${ARCLINK_GATEWAY_EXEC_BROKER_TOKEN:-}")'
        in deploy,
        "control/docker runtime config should generate a durable gateway exec broker token before writing docker.env",
    )
    expect(
        'ensure_env_file_value ARCLINK_GATEWAY_EXEC_BROKER_TOKEN "$(random_secret)"' in docker_helper,
        "docker bootstrap should backfill a missing gateway exec broker token before Compose reads docker.env",
    )
    expect(
        "ARCLINK_GATEWAY_EXEC_BROKER_TOKEN=$q_gateway_exec_broker_token" in entrypoint,
        "fresh Docker config generation should include the gateway exec broker token",
    )
    expect(
        "ARCLINK_GATEWAY_EXEC_BROKER_TOKEN: ${ARCLINK_GATEWAY_EXEC_BROKER_TOKEN:?run ./deploy.sh control bootstrap first}"
        in compose,
        "Compose should require the gateway exec broker token before starting the broker/client split",
    )
    expect(
        'ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN="$(preserve_or_randomize_secret "${ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN:-}")'
        in deploy,
        "control/docker runtime config should generate a durable deployment exec broker token before writing docker.env",
    )
    expect(
        'ensure_env_file_value ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN "$(random_secret)"' in docker_helper,
        "docker bootstrap should backfill a missing deployment exec broker token before Compose reads docker.env",
    )
    expect(
        "ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN=$q_deployment_exec_broker_token" in entrypoint,
        "fresh Docker config generation should include the deployment exec broker token",
    )
    expect(
        "ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN: ${ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN:?run ./deploy.sh control bootstrap first}"
        in compose,
        "Compose should require the deployment exec broker token before starting the broker/client split",
    )
    expect(
        'ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN="$(preserve_or_randomize_secret "${ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN:-}")'
        in deploy,
        "control/docker runtime config should generate a durable agent supervisor broker token before writing docker.env",
    )
    expect(
        'ensure_env_file_value ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN "$(random_secret)"' in docker_helper,
        "docker bootstrap should backfill a missing agent supervisor broker token before Compose reads docker.env",
    )
    expect(
        "ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN=$q_agent_supervisor_broker_token" in entrypoint,
        "fresh Docker config generation should include the agent supervisor broker token",
    )
    expect(
        "ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN: ${ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN:?run ./deploy.sh control bootstrap first}"
        in compose,
        "Compose should require the agent supervisor broker token before starting the broker/client split",
    )
    expect(
        'ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN="$(preserve_or_randomize_secret "${ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN:-}")'
        in deploy,
        "control/docker runtime config should generate a durable operator upgrade broker token before writing docker.env",
    )
    expect(
        'ensure_env_file_value ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN "$(random_secret)"' in docker_helper,
        "docker bootstrap should backfill a missing operator upgrade broker token before Compose reads docker.env",
    )
    expect(
        "ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN=$q_operator_upgrade_broker_token" in entrypoint,
        "fresh Docker config generation should include the operator upgrade broker token",
    )
    expect(
        "ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN: ${ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN:?run ./deploy.sh control bootstrap first}"
        in compose,
        "Compose should require the operator upgrade broker token before starting the broker/client split",
    )
    expect(
        'ARCLINK_AGENT_USER_HELPER_TOKEN="$(preserve_or_randomize_secret "${ARCLINK_AGENT_USER_HELPER_TOKEN:-}")'
        in deploy,
        "control/docker runtime config should generate a durable agent user helper token before writing docker.env",
    )
    expect(
        'ensure_env_file_value ARCLINK_AGENT_USER_HELPER_TOKEN "$(random_secret)"' in docker_helper,
        "docker bootstrap should backfill a missing agent user helper token before Compose reads docker.env",
    )
    expect(
        "ARCLINK_AGENT_USER_HELPER_TOKEN=$q_agent_user_helper_token" in entrypoint,
        "fresh Docker config generation should include the agent user helper token",
    )
    expect(
        "ARCLINK_AGENT_USER_HELPER_TOKEN: ${ARCLINK_AGENT_USER_HELPER_TOKEN:?run ./deploy.sh control bootstrap first}"
        in compose,
        "Compose should require the agent user helper token before starting the helper/client split",
    )
    expect(
        'ARCLINK_AGENT_PROCESS_HELPER_TOKEN="$(preserve_or_randomize_secret "${ARCLINK_AGENT_PROCESS_HELPER_TOKEN:-}")'
        in deploy,
        "control/docker runtime config should generate a durable agent process helper token before writing docker.env",
    )
    expect(
        'ensure_env_file_value ARCLINK_AGENT_PROCESS_HELPER_TOKEN "$(random_secret)"' in docker_helper,
        "docker bootstrap should backfill a missing agent process helper token before Compose reads docker.env",
    )
    expect(
        "ARCLINK_AGENT_PROCESS_HELPER_TOKEN=$q_agent_process_helper_token" in entrypoint,
        "fresh Docker config generation should include the agent process helper token",
    )
    expect(
        "ARCLINK_AGENT_PROCESS_HELPER_TOKEN: ${ARCLINK_AGENT_PROCESS_HELPER_TOKEN:?run ./deploy.sh control bootstrap first}"
        in compose,
        "Compose should require the agent process helper token before starting the helper/client split",
    )
    print("PASS test_control_docker_bootstrap_seeds_session_hash_pepper_and_gateway_broker_token")


def test_control_upgrade_syncs_checkout_from_upstream_before_build() -> None:
    text = DEPLOY_SH.read_text(encoding="utf-8")
    sync = extract(text, "control_upgrade_fetch_upstream() {", "run_control_install_flow() {")
    flow = extract(text, "run_control_install_flow() {", "run_control_reconfigure_flow() {")
    expect("git -C \"$BOOTSTRAP_DIR\" fetch --prune \"$remote\"" in sync, sync)
    expect("GIT_SSH_COMMAND=\"$ssh_command\"" in sync, "control upgrade fetch must honor the configured upstream deploy key")
    expect("configure_upstream_git_for_repo \"$BOOTSTRAP_DIR\"" in sync, "control upgrade should make forwarded upstream deploy-key env load-bearing")
    expect("Refusing control upgrade from branch" in sync and "expected '$expected_branch'" in sync, sync)
    expect("has no upstream to fetch" in sync, sync)
    expect("is ahead of upstream" in sync and "return 1" in sync, sync)
    expect("git -C \"$BOOTSTRAP_DIR\" merge --ff-only \"$upstream\"" in sync, sync)
    expect("ARCLINK_CONTROL_UPGRADE_SKIP_UPSTREAM_SYNC" in sync, sync)
    expect("merge-base --is-ancestor" in sync, sync)
    expect(
        flow.index("verify_control_upgrade_checkout_clean")
        < flow.index("require_main_upstream_branch_for_upgrade")
        < flow.index("sync_control_upgrade_checkout_from_upstream")
        < flow.index("run_arclink_docker build"),
        "control upgrade should verify a clean tree, sync upstream, then build",
    )
    print("PASS test_control_upgrade_syncs_checkout_from_upstream_before_build")


def test_component_upgrade_reexec_reads_operator_artifact_config_file_key() -> None:
    body = (REPO / "bin" / "component-upgrade.sh").read_text(encoding="utf-8")
    reexec = extract(body, "reexec_upgrade() {", "do_apply() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        repo = tmp_path / "repo"
        repo.mkdir()
        config = tmp_path / "live" / "config" / "arclink.env"
        config.parent.mkdir(parents=True)
        config.write_text("ARCLINK_USER=operator-svc\n", encoding="utf-8")
        (repo / ".arclink-operator.env").write_text(
            f"ARCLINK_OPERATOR_DEPLOYED_CONFIG_FILE={shlex.quote(str(config))}\n"
            "ARCLINK_OPERATOR_DEPLOYED_REPO_DIR=/srv/operator-svc/arclink\n",
            encoding="utf-8",
        )
        fakebin = tmp_path / "bin"
        fakebin.mkdir()
        log_path = tmp_path / "sudo.log"
        (fakebin / "sudo").write_text(
            "#!/usr/bin/env bash\n"
            f"printf '%s\\n' \"$*\" > {shlex.quote(str(log_path))}\n",
            encoding="utf-8",
        )
        (fakebin / "sudo").chmod(0o755)
        script = f"""
set -euo pipefail
PATH={shlex.quote(str(fakebin))}:$PATH
REPO_DIR={shlex.quote(str(repo))}
note() {{ printf '%s\\n' "$*"; }}
{reexec}
reexec_upgrade
"""
        result = bash(script)
        expect(result.returncode == 0, f"component-upgrade reexec artifact test failed: {result.stderr}")
        sudo_log = log_path.read_text(encoding="utf-8")
        expect(f"ARCLINK_CONFIG_FILE={config}" in sudo_log, sudo_log)
        expect("ARCLINK_OPERATOR_DEPLOYED_CONFIG:-" not in reexec, reexec)
        expect("ARCLINK_OPERATOR_DEPLOYED_CONFIG_FILE:-" in reexec, reexec)
    print("PASS test_component_upgrade_reexec_reads_operator_artifact_config_file_key")


def test_init_bootstrap_defaults_to_canonical_repo_and_safe_printf() -> None:
    body = (REPO / "init.sh").read_text(encoding="utf-8")
    expect("github.com/example/arclink" not in body, "top-level init.sh must not default to placeholder example URLs")
    expect("https://github.com/sirouk/arclink.git" in body, body)
    expect("ARCLINK_INIT_REPO_REF" in body and "raw.githubusercontent.com/sirouk/arclink/$REPO_REF/init.sh" in body, body)
    expect("git clone --depth 1 --branch \"$REPO_REF\"" in body, body)
    expect('printf "$TARGET_USER"' not in body, body)
    expect("printf '%s' \"$TARGET_USER\"" in body, body)
    print("PASS test_init_bootstrap_defaults_to_canonical_repo_and_safe_printf")


def test_operator_hermes_home_install_lock_has_timeout() -> None:
    body = (REPO / "bin" / "install-operator-hermes-home.sh").read_text(encoding="utf-8")
    expect("ARCLINK_OPERATOR_INSTALL_LOCK_TIMEOUT_SECONDS" in body, body)
    expect("flock -w \"$LOCK_TIMEOUT_SECONDS\" 9" in body, body)
    expect("Timed out waiting for operator Hermes home install lock" in body, body)
    expect("flock 9" not in body, "operator install lock must not block indefinitely")
    print("PASS test_operator_hermes_home_install_lock_has_timeout")


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def test_ensure_prereqs_ready_fake_system_is_noop() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fakebin = tmp_path / "bin"
        state = tmp_path / "state"
        fakebin.mkdir()
        state.mkdir()
        _write_executable(fakebin / "apt-get", "#!/bin/bash\necho apt-get should-not-run >&2\nexit 99\n")
        _write_executable(fakebin / "curl", "#!/bin/bash\necho curl should-not-run >&2\nexit 99\n")
        _write_executable(fakebin / "jq", "#!/bin/bash\nexit 0\n")
        _write_executable(fakebin / "rsync", "#!/bin/bash\nexit 0\n")
        _write_executable(fakebin / "ssh", "#!/bin/bash\nexit 0\n")
        _write_executable(
            fakebin / "docker",
            "#!/bin/bash\nif [[ ${1:-} == compose && ${2:-} == version ]]; then echo 'Docker Compose v2.0.0'; exit 0; fi\nexit 0\n",
        )
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{fakebin}:{os.environ.get('PATH', '')}",
                "STATE_DIR": str(state),
                "ARCLINK_PREREQ_AUDIT_FILE": str(state / "audit.jsonl"),
            }
        )
        result = subprocess.run(
            ["/bin/bash", str(ENSURE_PREREQS_SH), "--surface", "control-node", "--json"],
            text=True,
            capture_output=True,
            env=env,
            cwd=str(REPO),
            check=False,
        )
        expect(result.returncode == 0, f"expected ready fake system to pass: {result.stderr}\n{result.stdout}")
        expect('"ok": true' in result.stdout and '"surface": "control-node"' in result.stdout, result.stdout)
        audit = (state / "audit.jsonl").read_text(encoding="utf-8")
        expect('"action": "ensure_prereqs"' in audit and '"status": "completed"' in audit, audit)
    print("PASS test_ensure_prereqs_ready_fake_system_is_noop")


def test_ensure_prereqs_check_only_plans_missing_without_mutation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fakebin = tmp_path / "bin"
        fakebin.mkdir()
        _write_executable(fakebin / "apt-get", "#!/bin/bash\necho apt-get should-not-run >&2\nexit 99\n")
        env = os.environ.copy()
        env.update({"PATH": str(fakebin), "ARCLINK_SKIP_PREREQ_INSTALL": "1"})
        result = subprocess.run(
            ["/bin/bash", str(ENSURE_PREREQS_SH), "--surface", "control-node", "--json"],
            text=True,
            capture_output=True,
            env=env,
            cwd=str(REPO),
            check=False,
        )
        expect(result.returncode == 1, f"expected verify-only mode to fail when prereqs are missing: {result.stdout}")
        expect("packages:" in result.stdout and "docker-compose-plugin" in result.stdout, result.stdout)
        expect("should-not-run" not in result.stderr, result.stderr)
    print("PASS test_ensure_prereqs_check_only_plans_missing_without_mutation")


def test_ensure_prereqs_fake_install_uses_packages_and_get_docker_idiom() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fakebin = tmp_path / "bin"
        state = tmp_path / "state"
        fakebin.mkdir()
        state.mkdir()
        log = tmp_path / "commands.log"
        _write_executable(
            fakebin / "apt-get",
            f"#!/bin/bash\nprintf 'apt-get %s\\n' \"$*\" >> {shlex.quote(str(log))}\nexit 0\n",
        )
        _write_executable(
            fakebin / "curl",
            f"""#!/bin/bash
printf 'curl %s\\n' "$*" >> {shlex.quote(str(log))}
cat <<'SH'
#!/usr/bin/env sh
cat > "$FAKEBIN/docker" <<'DOCKER'
#!/usr/bin/env sh
if [ "$1" = compose ] && [ "$2" = version ]; then
  echo "Docker Compose v2.0.0"
  exit 0
fi
exit 0
DOCKER
chmod +x "$FAKEBIN/docker"
SH
""",
        )
        _write_executable(fakebin / "jq", "#!/bin/bash\nexit 0\n")
        (fakebin / "python3").symlink_to(sys.executable)
        (fakebin / "mkdir").symlink_to("/bin/mkdir")
        (fakebin / "dirname").symlink_to("/usr/bin/dirname")
        (fakebin / "cat").symlink_to("/bin/cat")
        (fakebin / "chmod").symlink_to("/bin/chmod")
        (fakebin / "sh").symlink_to("/bin/sh")
        env = os.environ.copy()
        env.update(
            {
                "PATH": str(fakebin),
                "FAKEBIN": str(fakebin),
                "STATE_DIR": str(state),
                "ARCLINK_PREREQ_AUDIT_FILE": str(state / "audit.jsonl"),
            }
        )
        result = subprocess.run(
            ["/bin/bash", str(ENSURE_PREREQS_SH), "--surface", "control-node"],
            text=True,
            capture_output=True,
            env=env,
            cwd=str(REPO),
            check=False,
        )
        expect(result.returncode == 0, f"fake prereq install failed: {result.stderr}\n{result.stdout}")
        rendered_log = log.read_text(encoding="utf-8")
        expect("apt-get update" in rendered_log and "apt-get install -y" in rendered_log, rendered_log)
        expect("https://get.docker.com" in rendered_log, rendered_log)
        audit = (state / "audit.jsonl").read_text(encoding="utf-8")
        expect('"action": "install_packages"' in audit and '"action": "install_docker"' in audit, audit)
    print("PASS test_ensure_prereqs_fake_install_uses_packages_and_get_docker_idiom")


def test_ensure_prereqs_wireguard_check_only_plans_tools() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fakebin = tmp_path / "bin"
        state = tmp_path / "state"
        fakebin.mkdir()
        state.mkdir()
        _write_executable(fakebin / "apt-get", "#!/bin/bash\necho apt-get should-not-run >&2\nexit 99\n")
        _write_executable(fakebin / "curl", "#!/bin/bash\nexit 0\n")
        _write_executable(fakebin / "jq", "#!/bin/bash\nexit 0\n")
        _write_executable(fakebin / "rsync", "#!/bin/bash\nexit 0\n")
        _write_executable(fakebin / "ssh", "#!/bin/bash\nexit 0\n")
        (fakebin / "dirname").symlink_to("/usr/bin/dirname")
        (fakebin / "mkdir").symlink_to("/bin/mkdir")
        (fakebin / "python3").symlink_to("/usr/bin/python3")
        _write_executable(
            fakebin / "docker",
            "#!/bin/bash\nif [[ ${1:-} == compose && ${2:-} == version ]]; then echo 'Docker Compose v2.0.0'; exit 0; fi\nexit 0\n",
        )
        env = os.environ.copy()
        env.update(
            {
                "PATH": str(fakebin),
                "STATE_DIR": str(state),
                "ARCLINK_PREREQ_AUDIT_FILE": str(state / "audit.jsonl"),
                "ARCLINK_PREREQ_WIREGUARD": "1",
                "ARCLINK_SKIP_PREREQ_INSTALL": "1",
            }
        )
        result = subprocess.run(
            ["/bin/bash", str(ENSURE_PREREQS_SH), "--surface", "control-node", "--json"],
            text=True,
            capture_output=True,
            env=env,
            cwd=str(REPO),
            check=False,
        )
        expect(result.returncode == 1, f"expected missing WireGuard tools to be planned: {result.stdout}\n{result.stderr}")
        expect("wireguard-tools" in result.stdout, result.stdout)
        audit = (state / "audit.jsonl").read_text(encoding="utf-8")
        expect('"action": "install_wireguard"' in audit and '"status": "planned"' in audit, audit)
        expect("should-not-run" not in result.stderr, result.stderr)
    print("PASS test_ensure_prereqs_wireguard_check_only_plans_tools")


def test_control_install_wires_prereq_auto_installation_with_skip_opt_out() -> None:
    text = DEPLOY_SH.read_text(encoding="utf-8")
    flow = extract(text, "run_control_install_flow() {", "run_control_reconfigure_flow() {")
    expect('"$BOOTSTRAP_DIR/bin/lib/ensure-prereqs.sh"' in flow, flow)
    expect("ARCLINK_PREREQ_WIREGUARD" in flow, "control install should request WireGuard tools for fleet mesh readiness")
    expect("--skip-prereq-install" in flow, flow)
    expect("ARCLINK_SKIP_PREREQ_INSTALL=1" in flow, flow)
    expect(
        flow.index('"$BOOTSTRAP_DIR/bin/lib/ensure-prereqs.sh"') < flow.index("run_arclink_docker bootstrap"),
        "control prereqs must run before Docker bootstrap/build",
    )
    expect("deploy.sh control install --skip-prereq-install" in text, "usage should document hardened-image prereq opt-out")
    print("PASS test_control_install_wires_prereq_auto_installation_with_skip_opt_out")


def test_control_upgrade_runs_full_host_namespace_and_installs_operator_runner() -> None:
    text = DEPLOY_SH.read_text(encoding="utf-8")
    flow = extract(text, "run_control_install_flow() {", "run_control_reconfigure_flow() {")
    expect("ARCLINK_BROKERED_CONTROL_UPGRADE" not in flow, flow)
    expect("skipping host prerequisite installation" not in flow, flow)
    expect("skipping host WireGuard/firewall mutation" not in flow, flow)
    expect("skipping host-local fleet repair" not in flow, flow)
    expect('"$BOOTSTRAP_DIR/bin/lib/ensure-prereqs.sh"' in flow, flow)
    expect("ensure_control_wireguard_ready" in flow, flow)
    expect("sync_control_wireguard_peers_from_inventory" in flow, flow)
    expect("ensure_control_local_fleet_worker_registered" in flow, flow)
    expect("publish_control_tailscale_ingress" in flow, flow)
    expect("install_control_tailnet_publisher_timer" in flow, flow)
    expect("install_control_operator_upgrade_host_runner_timer" in flow, flow)
    expect("run_arclink_docker build" in flow, flow)
    expect("sync_control_docker_image_to_fleet_workers" in flow, flow)
    expect("run_arclink_docker up" in flow, flow)
    expect("register_control_public_bot_actions" in flow, flow)
    expect("run_arclink_docker record-release" in flow, flow)
    expect("run_arclink_docker health" in flow, flow)
    expect("arclink-operator-upgrade-host-runner.timer" in text, text)
    expect("arclink-operator-upgrade-host-runner.sh --once" in text, text)
    print("PASS test_control_upgrade_runs_full_host_namespace_and_installs_operator_runner")


def test_deploy_sh_guides_notion_workspace_migration() -> None:
    text = DEPLOY_SH.read_text(encoding="utf-8")
    usage_snippet = extract(text, "usage() {", "retired_shared_host_mode() {")
    cleanup = extract(text, "notion_migration_clear_workspace_state() {", "run_notion_migrate_flow() {")
    migration = extract(text, "run_notion_migrate_flow() {", "run_curator_setup_flow() {")
    notion_setup = extract(text, "run_notion_ssot_setup() {", "notion_migration_pause() {")
    expect("deploy.sh notion-migrate" not in usage_snippet, "retired Shared Host Notion migration must not be advertised in usage")
    expect("deploy.sh docker notion-migrate" not in usage_snippet, "retired Shared Host Docker Notion migration must not be advertised in usage")
    expect("Notion workspace migration" in text, "expected guided Notion migration helper to remain available for internal repair/migration work")
    expect("Retry last migration index sync" in text, "expected migration submenu to offer a recovery path for failed index syncs")
    expect("Type MIGRATE NOTION to continue" in migration, "expected explicit typed migration acknowledgement")
    expect("notion_migration_backup_state" in migration, "expected migration to create private backups")
    expect("notion process-pending" in migration, "expected migration to drain pending Notion events")
    expect("notion_migration_pause_write_surfaces" in migration, "expected migration to pause Notion write surfaces")
    expect("trap notion_migration_restore_paused_services EXIT" in migration, "expected migration to restore paused services if the shell exits")
    expect("trap notion_migration_restore_paused_services RETURN" not in migration, "migration must not use RETURN traps that fire after every helper function")
    expect("ARCLINK_NOTION_MIGRATION_FRESH_DEFAULTS=1" in migration, "expected migration to require fresh Notion URL/token defaults")
    expect("ARCLINK_NOTION_MIGRATION_FORCE_WEBHOOK_RESET=1" in migration, "expected migration to force a fresh webhook handshake")
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
    expect("ARCLINK_NOTION_MIGRATION_DEFAULT_INDEX_ROOT" in notion_setup, "expected SSOT setup to default indexing to the new root during migration")
    expect("webhook-reset-token" in notion_setup, "expected SSOT setup to clear stale webhook verification during migration")
    expect("run_service_user_cmd \"$ctl_bin\" --json notion index-sync --full --actor \"$actor\"" in text, "expected baremetal migration index sync to run as the ArcLink service user")
    expect("env ARCLINK_CONFIG_FILE=\"$CONFIG_TARGET\" \"$BOOTSTRAP_DIR/bin/arclink-ctl\" --json notion index-sync --full" not in migration, "migration must not run qmd-backed index sync as root from the deploy checkout")
    print("PASS test_deploy_sh_guides_notion_workspace_migration")


def test_deploy_sh_guides_notion_page_transfer() -> None:
    text = DEPLOY_SH.read_text(encoding="utf-8")
    usage_snippet = extract(text, "usage() {", "retired_shared_host_mode() {")
    transfer = extract(text, "notion_transfer_prepare_context() {", "run_curator_setup_flow() {")
    expect("deploy.sh notion-transfer" not in usage_snippet, "retired Shared Host Notion transfer must not be advertised in usage")
    expect("deploy.sh docker notion-transfer" not in usage_snippet, "retired Shared Host Docker Notion transfer must not be advertised in usage")
    expect("Notion page backup / restore" in text, "expected Notion transfer helper to remain available for internal repair/migration work")
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
        "Name it something like Raven" in text,
        "expected deploy notion-ssot guidance to suggest a concrete integration name using current vocabulary",
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
        "parent page or Teamspace root ArcLink should live under" in text,
        "expected deploy notion-ssot guidance to explain which parent/root to grant in Manage page access",
    )
    expect(
        "new child pages and databases under" in text,
        "expected deploy notion-ssot guidance to explain that child pages inherit access from the granted parent page",
    )
    expect(
        "ArcLink cannot press Notion's Manage page access buttons for you via" in text,
        "expected deploy notion-ssot guidance to explain that the Manage page access UI cannot be automated through a supported API",
    )
    expect(
        "Type YES to confirm you understand this Notion access model" in text,
        "expected deploy notion-ssot setup to require an explicit typed acknowledgment of Notion's subtree access model",
    )
    expect(
        "Shared Notion page URL for ArcLink (use a normal page, not the workspace Home screen)" in text,
        "expected deploy notion-ssot prompt to steer operators toward a normal page and away from the workspace Home screen",
    )
    expect(
        "Make one normal Notion page for ArcLink" in text,
        "expected deploy notion-ssot guidance to tell operators to create a normal ArcLink page first",
    )
    expect(
        "ArcLink will use the page you paste below as its shared Notion home" in text,
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
        '"$BOOTSTRAP_DIR/bin/arclink-ctl" --json notion handshake' in notion_setup,
        "expected notion-ssot setup to use the current checkout's arclink-ctl for handshake",
    )
    expect(
        '"$ARCLINK_REPO_DIR/bin/arclink-ctl" --json notion handshake' not in notion_setup,
        "expected notion-ssot setup not to depend on an older deployed arclink-ctl during handshake",
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
        '"$BOOTSTRAP_DIR/bin/arclink-ctl" --json notion preflight-root' in notion_setup,
        "expected notion-ssot setup to preflight child page/database creation under the resolved root page",
    )
    expect(
        '--root-page-id "$root_page_id"' in notion_setup,
        "expected notion-ssot setup to pass the resolved root page id explicitly to the preflight check",
    )
    expect(
        'ARCLINK_SSOT_NOTION_ROOT_PAGE_URL="$root_page_url"' in notion_setup,
        "expected notion-ssot setup to persist the resolved Notion root page URL",
    )
    expect(
        'ARCLINK_SSOT_NOTION_ROOT_PAGE_ID="$root_page_id"' in notion_setup,
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


def test_qmd_refresh_bounds_embedding_work() -> None:
    refresh = QMD_REFRESH_SH.read_text(encoding="utf-8")
    common = (REPO / "bin" / "common.sh").read_text(encoding="utf-8")
    deploy = DEPLOY_SH.read_text(encoding="utf-8")
    health = HEALTH_SH.read_text(encoding="utf-8")
    example = (REPO / "config" / "arclink.env.example").read_text(encoding="utf-8")
    vault_watch = VAULT_WATCH_SH.read_text(encoding="utf-8")
    expect("timeout --foreground" in refresh, refresh)
    expect("--max-docs-per-batch" in refresh and "--max-batch-mb" in refresh, refresh)
    expect("embeddings will retry on the next refresh" in refresh, refresh)
    expect("QMD local embedding force refresh requested" in refresh, refresh)
    expect("clear_qmd_embed_force_flag" in refresh, refresh)
    expect('QMD_EMBED_TIMEOUT_SECONDS="${QMD_EMBED_TIMEOUT_SECONDS:-120}"' in common, common)
    expect('QMD_EMBED_MAX_DOCS_PER_BATCH="${QMD_EMBED_MAX_DOCS_PER_BATCH:-8}"' in common, common)
    expect('QMD_EMBED_PROVIDER="${QMD_EMBED_PROVIDER:-local}"' in common, common)
    expect('QMD_EMBED_FORCE_ON_NEXT_REFRESH="${QMD_EMBED_FORCE_ON_NEXT_REFRESH:-0}"' in common, common)
    expect('write_kv QMD_EMBED_TIMEOUT_SECONDS "$QMD_EMBED_TIMEOUT_SECONDS"' in deploy, deploy)
    expect('write_kv QMD_EMBED_PROVIDER "${QMD_EMBED_PROVIDER:-local}"' in deploy, deploy)
    expect('write_kv QMD_EMBED_FORCE_ON_NEXT_REFRESH "${QMD_EMBED_FORCE_ON_NEXT_REFRESH:-0}"' in deploy, deploy)
    expect("QMD_EMBED_TIMEOUT_SECONDS=120" in example, example)
    expect("QMD_EMBED_PROVIDER=local" in example, example)
    expect("QMD_EMBED_FORCE_ON_NEXT_REFRESH=0" in example, example)
    expect("QMD embedding endpoint provider selected" in refresh, refresh)
    expect("falling back to local qmd embeddings" in refresh, refresh)
    expect("qmd remote embedding endpoint config captured" in health, health)
    expect('"$SCRIPT_DIR/qmd-refresh.sh" --embed' in vault_watch, vault_watch)
    expect('qmd --index "$QMD_INDEX_NAME" embed' not in vault_watch, vault_watch)
    expect("qmd_note_pending_embeddings_state" in refresh, refresh)
    expect("qmd_note_pending_embeddings_state()" in common, common)
    expect("qmd_pending_embeddings_age_alert()" in common, common)
    print("PASS test_qmd_refresh_bounds_embedding_work")


def test_qmd_refresh_falls_back_to_local_embedding_when_endpoint_provider_selected() -> None:
    # The pinned qmd release has no endpoint-backed embedding support, so the
    # endpoint provider must NOT silently disable vector search: the refresh
    # logs a warning and still runs local embedding.
    text = QMD_REFRESH_SH.read_text(encoding="utf-8")
    snippet = extract(text, "clear_qmd_embed_force_flag() {", "exec 9>")
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "qmd.log"
        script = f"""
set -euo pipefail
QMD_INDEX_NAME=arclink
QMD_EMBED_PROVIDER=endpoint
QMD_EMBED_ENDPOINT=https://embed.example.test/v1
QMD_EMBED_ENDPOINT_MODEL=text-embedding-3-small
QMD_EMBED_API_KEY=secret
QMD_EMBED_TIMEOUT_SECONDS=0
LOG_FILE={shlex.quote(str(log_path))}
qmd() {{
  printf '%s\\n' "$*" >>"$LOG_FILE"
}}
{snippet}
run_qmd_embed
printf 'qmd:%s\\n' "$(cat "$LOG_FILE")"
"""
        result = bash(script)
    expect(result.returncode == 0, f"qmd endpoint fallback failed: {result.stderr}\n{result.stdout}")
    expect("QMD embedding endpoint provider selected" in result.stderr, result.stderr)
    expect("falling back to local qmd embeddings" in result.stderr, result.stderr)
    expect("qmd:--index arclink embed" in result.stdout, result.stdout)
    print("PASS test_qmd_refresh_falls_back_to_local_embedding_when_endpoint_provider_selected")


def test_qmd_refresh_forces_and_consumes_local_rebuild_flag() -> None:
    text = QMD_REFRESH_SH.read_text(encoding="utf-8")
    snippet = extract(text, "clear_qmd_embed_force_flag() {", "exec 9>")
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / "arclink.env"
        log_path = Path(tmp) / "qmd.log"
        config_path.write_text("QMD_EMBED_FORCE_ON_NEXT_REFRESH=1\nKEEP=ok\n", encoding="utf-8")
        script = f"""
set -euo pipefail
QMD_INDEX_NAME=arclink
QMD_EMBED_PROVIDER=local
QMD_EMBED_FORCE_ON_NEXT_REFRESH=1
QMD_EMBED_TIMEOUT_SECONDS=0
QMD_EMBED_MAX_DOCS_PER_BATCH=8
QMD_EMBED_MAX_BATCH_MB=16
CONFIG_FILE={shlex.quote(str(config_path))}
LOG_FILE={shlex.quote(str(log_path))}
qmd() {{
  printf '%s\\n' "$*" >>"$LOG_FILE"
}}
{snippet}
run_qmd_embed
printf 'flag:%s\\n' "$(grep '^QMD_EMBED_FORCE_ON_NEXT_REFRESH=' "$CONFIG_FILE")"
printf 'keep:%s\\n' "$(grep '^KEEP=' "$CONFIG_FILE")"
printf 'qmd:%s\\n' "$(cat "$LOG_FILE")"
"""
        result = bash(script)
    expect(result.returncode == 0, f"qmd force rebuild failed: {result.stderr}\n{result.stdout}")
    expect("QMD local embedding force refresh requested" in result.stderr, result.stderr)
    expect("flag:QMD_EMBED_FORCE_ON_NEXT_REFRESH=0" in result.stdout, result.stdout)
    expect("keep:KEEP=ok" in result.stdout, result.stdout)
    expect("qmd:--index arclink embed -f --max-docs-per-batch 8 --max-batch-mb 16" in result.stdout, result.stdout)
    print("PASS test_qmd_refresh_forces_and_consumes_local_rebuild_flag")


def test_qmd_refresh_atomically_rewrites_config_and_surfaces_embed_failure() -> None:
    text = QMD_REFRESH_SH.read_text(encoding="utf-8")
    snippet = extract(text, "clear_qmd_embed_force_flag() {", "exec 9>")
    expect('mktemp "${config}.tmp.XXXXXX"' in snippet, snippet)
    expect('mv -f "$temp" "$config"' in snippet, snippet)
    expect('cat "$temp" >"$config"' not in snippet, snippet)
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / "arclink.env"
        config_path.write_text("QMD_EMBED_FORCE_ON_NEXT_REFRESH=1\nKEEP=ok\n", encoding="utf-8")
        script = f"""
set -euo pipefail
QMD_INDEX_NAME=arclink
QMD_EMBED_PROVIDER=local
QMD_EMBED_FORCE_ON_NEXT_REFRESH=1
QMD_EMBED_TIMEOUT_SECONDS=0
CONFIG_FILE={shlex.quote(str(config_path))}
{snippet}
clear_qmd_embed_force_flag
printf 'flag:%s\\n' "$(grep '^QMD_EMBED_FORCE_ON_NEXT_REFRESH=' "$CONFIG_FILE")"
qmd() {{ return 42; }}
QMD_EMBED_FORCE_ON_NEXT_REFRESH=0
set +e
run_qmd_embed
rc=$?
set -e
printf 'embed_rc=%s\\n' "$rc"
"""
        result = bash(script)
    expect(result.returncode == 0, f"qmd refresh failure surfacing failed: {result.stderr}\n{result.stdout}")
    expect("flag:QMD_EMBED_FORCE_ON_NEXT_REFRESH=0" in result.stdout, result.stdout)
    expect("embed_rc=42" in result.stdout, result.stdout)
    print("PASS test_qmd_refresh_atomically_rewrites_config_and_surfaces_embed_failure")


def test_collect_qmd_embedding_answers_reconfigures_between_local_and_endpoint() -> None:
    text = DEPLOY_SH.read_text(encoding="utf-8")
    snippet = extract(text, "normalize_qmd_embed_provider() {", "random_secret() {")
    script = f"""
set -euo pipefail
{snippet}
lowercase() {{ printf '%s' "${{1:-}}" | tr '[:upper:]' '[:lower:]'; }}
normalize_optional_answer() {{
  case "${{1:-}}" in
    none|NONE|off|OFF|-) printf '%s' "" ;;
    *) printf '%s' "${{1:-}}" ;;
  esac
}}
ask_secret_with_default() {{ printf '%s' "endpoint-key"; }}
ASK_MODE=endpoint
ask() {{
  case "$1" in
    "QMD semantic embedding backend"*) printf '%s' "$ASK_MODE" ;;
    "OpenAI-compatible embeddings endpoint"*) printf '%s' "https://embed.example.test/v1" ;;
    "Embedding endpoint model name"*) printf '%s' "text-embedding-3-small" ;;
    "Embedding dimensions"*) printf '%s' "768" ;;
    *) printf '%s' "${{2:-}}" ;;
  esac
}}

QMD_RUN_EMBED=1
QMD_EMBED_PROVIDER=local
QMD_EMBED_ENDPOINT=
QMD_EMBED_ENDPOINT_MODEL=
QMD_EMBED_API_KEY=
QMD_EMBED_DIMENSIONS=
QMD_EMBED_FORCE_ON_NEXT_REFRESH=0
collect_qmd_embedding_answers
printf 'endpoint:%s:%s:%s:%s:%s:%s\\n' "$QMD_RUN_EMBED" "$QMD_EMBED_PROVIDER" "$QMD_EMBED_ENDPOINT" "$QMD_EMBED_ENDPOINT_MODEL" "$QMD_EMBED_DIMENSIONS" "$QMD_EMBED_FORCE_ON_NEXT_REFRESH"

ASK_MODE=local
QMD_RUN_EMBED=0
QMD_EMBED_PROVIDER=endpoint
QMD_EMBED_ENDPOINT=https://old.example/v1
QMD_EMBED_ENDPOINT_MODEL=old-model
QMD_EMBED_API_KEY=old-key
QMD_EMBED_DIMENSIONS=1024
QMD_EMBED_FORCE_ON_NEXT_REFRESH=0
collect_qmd_embedding_answers
printf 'local:%s:%s:%s:%s:%s:%s:%s\\n' "$QMD_RUN_EMBED" "$QMD_EMBED_PROVIDER" "$QMD_EMBED_ENDPOINT" "$QMD_EMBED_ENDPOINT_MODEL" "$QMD_EMBED_API_KEY" "$QMD_EMBED_DIMENSIONS" "$QMD_EMBED_FORCE_ON_NEXT_REFRESH"
"""
    result = bash(script)
    expect(result.returncode == 0, f"qmd embedding answer reconfigure failed: {result.stderr}\n{result.stdout}")
    # Endpoint credentials are persisted for a future qmd upgrade, but local
    # embedding stays ON (QMD_RUN_EMBED=1): the pinned qmd has no
    # endpoint-backed embeddings, so disabling local embedding would silently
    # disable all vector search.
    expect("endpoint:1:endpoint:https://embed.example.test/v1:text-embedding-3-small:768:0" in result.stdout, result.stdout)
    expect("endpoint-backed qmd embeddings are not supported by the pinned qmd release" in result.stdout, result.stdout)
    expect("Switching to local qmd embeddings; the next qmd refresh will rebuild local vectors." in result.stdout, result.stdout)
    expect("local:1:local:::::1" in result.stdout, result.stdout)
    print("PASS test_collect_qmd_embedding_answers_reconfigures_between_local_and_endpoint")


def test_placeholder_upstream_default_uses_checkout_origin() -> None:
    text = DEPLOY_SH.read_text(encoding="utf-8")
    snippet = extract(text, "git_origin_url() {", "write_release_state() {")
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        run(["git", "init"], cwd=repo)
        run(["git", "remote", "add", "origin", "https://github.com/acme/arclink"], cwd=repo)
        script = f"""
{snippet}
BOOTSTRAP_DIR={shlex.quote(str(repo))}
ARCLINK_UPSTREAM_REPO_URL=https://github.com/example/arclink.git
use_detected_upstream_repo_url_if_placeholder
printf '%s\\n' "$ARCLINK_UPSTREAM_REPO_URL"
"""
        result = bash(script)
    expect(result.returncode == 0, f"upstream default probe failed: {result.stderr}\n{result.stdout}")
    expect(result.stdout.strip() == "https://github.com/acme/arclink", result.stdout)
    print("PASS test_placeholder_upstream_default_uses_checkout_origin")


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
    refresh_start_index = refresh_helper.find('start arclink-user-agent-refresh.service')
    expect(
        daemon_reload_index >= 0 and refresh_start_index >= 0 and daemon_reload_index < refresh_start_index,
        "refresh-agent-install should reload the user manager before starting/restarting user units",
    )
    expect(
        'rm -f "$timer_path"' in refresh_helper
        and 'disable --now arclink-user-agent-backup.timer' in refresh_helper,
        "refresh-agent-install should disable and remove the legacy systemd backup timer during active-agent realignment",
    )
    expect(
        "ensure_gateway_home_channel_env" in refresh_helper
        and "DISCORD_HOME_CHANNEL" in refresh_helper
        and "TELEGRAM_HOME_CHANNEL" in refresh_helper,
        "refresh-agent-install should repair gateway home-channel env from enrollment state",
    )
    expect(
        "ensure_agent_mcp_auth" in refresh_helper
        and "arclink-bootstrap-token" in refresh_helper
        and "ensure_agent_mcp_bootstrap_token" in refresh_helper
        and "bootstrap token checked/repaired" in refresh_helper,
        "refresh-agent-install should validate or repair the per-agent ArcLink MCP bootstrap token during install/upgrade realignment",
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
        and "is-active arclink-user-agent-gateway.service" in refresh_helper
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
        'disable --now arclink-user-agent-code.service' in refresh_helper
        and 'restart arclink-user-agent-code.service' not in refresh_helper,
        "refresh-agent-install should retire the legacy code-server unit now that Code is dashboard-native",
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
        "ARCLINK_INSTALL_SYSTEM_SERVICES_DEFER_START=1" in install
        and "start_system_provisioning_services_root" in install
        and install.index("ARCLINK_INSTALL_SYSTEM_SERVICES_DEFER_START=1")
        < install.index("bin/install-user-services.sh")
        < install.index("start_system_provisioning_services_root"),
        "run_root_install should defer root-owned provisioning jobs until after user services are installed",
    )
    install_user_services = "bin/install-user-services.sh"
    install_user_services_index = install.index(install_user_services)
    install_pre_user_chown_index = install.rfind("chown_managed_paths", 0, install_user_services_index)
    expect(
        install_pre_user_chown_index >= 0
        and "bootstrap-userland.sh" not in install[install_pre_user_chown_index:install_user_services_index]
        and "install-system-services.sh" not in install[install_pre_user_chown_index:install_user_services_index],
        "run_root_install should repair shared-state ownership immediately before installing user services",
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
        "ARCLINK_INSTALL_SYSTEM_SERVICES_DEFER_START=1" in upgrade
        and "start_system_provisioning_services_root" in upgrade
        and upgrade.index("ARCLINK_INSTALL_SYSTEM_SERVICES_DEFER_START=1")
        < upgrade.index("bin/install-user-services.sh")
        < upgrade.index("start_system_provisioning_services_root"),
        "run_root_upgrade should defer root-owned provisioning jobs until after user services are installed",
    )
    upgrade_user_services_index = upgrade.index(install_user_services)
    upgrade_pre_user_chown_index = upgrade.rfind("chown_managed_paths", 0, upgrade_user_services_index)
    expect(
        upgrade_pre_user_chown_index >= 0
        and "bootstrap-userland.sh" not in upgrade[upgrade_pre_user_chown_index:upgrade_user_services_index]
        and "install-system-services.sh" not in upgrade[upgrade_pre_user_chown_index:upgrade_user_services_index],
        "run_root_upgrade should repair shared-state ownership immediately before installing user services",
    )
    expect(
        "run_service_user_cmd" in org_profile_apply and "run_root_env_cmd" not in org_profile_apply,
        "org-profile apply should run as the service user so generated vault/state files remain rootless-service writable",
    )
    expect(
        'find "$ARCLINK_PRIV_DIR" -ignore_readdir_race' in chown_helper
        and "*.sqlite3-shm" in chown_helper
        and "*.sqlite3-wal" in chown_helper,
        "scoped ownership repair should tolerate transient SQLite sidecar files during live upgrades",
    )
    expect(
        "-exec chown -h" in chown_helper and "chown -hR" not in chown_helper,
        "install ownership repair should not dereference stale or broken vault symlinks",
    )
    expect(
        '-path "$ARCLINK_PRIV_DIR" -prune' in chown_helper
        and '-path "$NEXTCLOUD_STATE_DIR" -prune' in chown_helper,
        "scoped ownership repair should preserve rootless Nextcloud bind-mount ownership",
    )
    expect(
        'chown -hR "$ARCLINK_USER:$ARCLINK_USER" "$ARCLINK_PRIV_DIR"' not in install
        and 'chown -hR "$ARCLINK_USER:$ARCLINK_USER" "$ARCLINK_PRIV_DIR"' not in upgrade,
        "install/upgrade should not blanket-chown private state after Nextcloud normalizes rootless bind mounts",
    )
    expect(
        "chown_tree_excluding_path" in bootstrap_system
        and 'chown_tree_excluding_path "$ARCLINK_REPO_DIR" "$ARCLINK_PRIV_DIR"' in bootstrap_system
        and 'chown_tree_excluding_path "$ARCLINK_PRIV_DIR" "$NEXTCLOUD_STATE_DIR"' in bootstrap_system,
        "system bootstrap should preserve rootless Nextcloud state ownership while repairing managed paths",
    )
    expect(
        'chown -hR "$ARCLINK_USER:$ARCLINK_USER" "$ARCLINK_REPO_DIR" "$ARCLINK_PRIV_DIR"' not in bootstrap_system,
        "system bootstrap should not blanket-chown private Nextcloud runtime state",
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


def test_restart_services_disables_only_curator_native_system_gateway_unit() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "curator_native_gateway_system_unit_name_root() {", "restart_shared_user_services_root() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        runtime_dir = tmp_path / "runtime"
        python_bin = runtime_dir / "hermes-venv" / "bin" / "python3"
        python_bin.parent.mkdir(parents=True)
        python_bin.symlink_to(sys.executable)
        package = tmp_path / "hermes_cli"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "gateway.py").write_text(
            "def get_service_name():\n"
            "    return 'hermes-gateway-curatorhash'\n",
            encoding="utf-8",
        )
        systemctl_log = tmp_path / "systemctl.log"
        script = f"""
set -euo pipefail
export PYTHONPATH={shlex.quote(str(tmp_path))}
RUNTIME_DIR={shlex.quote(str(runtime_dir))}
ARCLINK_CURATOR_HERMES_HOME={shlex.quote(str(tmp_path / "curator-home"))}
SYSTEMCTL_LOG={shlex.quote(str(systemctl_log))}
systemctl() {{
  printf '%s\\n' "$*" >> "$SYSTEMCTL_LOG"
}}
{snippet}
disable_curator_native_gateway_system_unit_root
cat "$SYSTEMCTL_LOG"
"""
        result = bash(script)
        expect(result.returncode == 0, f"native curator gateway disable case failed: {result.stderr}")
        expect(
            "disable --now hermes-gateway-curatorhash.service" in result.stdout,
            f"expected exact native curator gateway unit disable, got: {result.stdout!r}",
        )
        expect(
            "reset-failed hermes-gateway-curatorhash.service" in result.stdout,
            f"expected exact native curator gateway unit failed state reset, got: {result.stdout!r}",
        )
    print("PASS test_restart_services_disables_only_curator_native_system_gateway_unit")


def test_tailscale_serve_command_timeout_surfaces_enablement_guidance() -> None:
    text = TAILSCALE_NEXTCLOUD_SERVE_SH.read_text(encoding="utf-8")
    snippet = extract(text, "extract_tailscale_enable_url() {", "print_serve_summary() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fake_cmd = tmp_path / "fake-tailscale-serve"
        fake_cmd.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' 'Serve is not enabled on your tailnet.'\n"
            "printf '%s\\n' 'https://login.tailscale.com/f/serve?node=testnode'\n"
            "sleep 10\n",
            encoding="utf-8",
        )
        fake_cmd.chmod(0o755)
        script = f"""
set -euo pipefail
ARCLINK_TAILSCALE_COMMAND_TIMEOUT=0.2s
{snippet}
if run_serve_cmd {shlex.quote(str(fake_cmd))}; then
  echo unexpected-success
else
  echo "STATUS=$?"
fi
"""
        result = bash(script)
        expect(result.returncode == 0, f"tailscale serve timeout test shell failed: {result.stderr}")
        combined = result.stdout + result.stderr
        expect("STATUS=124" in result.stdout, result.stdout)
        expect("Serve is not enabled on your tailnet" in combined, combined)
        expect("https://login.tailscale.com/f/serve?node=testnode" in combined, combined)
        expect("Press ENTER after enabling Tailscale Serve" in combined, combined)
        expect("rerun ./deploy.sh install" in combined, combined)
    print("PASS test_tailscale_serve_command_timeout_surfaces_enablement_guidance")


def test_retired_tailscale_serve_flag_does_not_unserve_during_deploy() -> None:
    serve = TAILSCALE_NEXTCLOUD_SERVE_SH.read_text(encoding="utf-8")
    deploy = DEPLOY_SH.read_text(encoding="utf-8")
    expect('"$SCRIPT_DIR/tailscale-nextcloud-unserve.sh"' not in serve, serve)
    expect("Existing Tailscale Serve configuration is left untouched" in serve, serve)
    expect("warn_retired_tailscale_nextcloud_serve()" in deploy, deploy)
    expect('"$ARCLINK_REPO_DIR/bin/tailscale-nextcloud-serve.sh"' not in deploy, deploy)
    print("PASS test_retired_tailscale_serve_flag_does_not_unserve_during_deploy")


def test_tailscale_funnel_command_timeout_surfaces_enablement_guidance() -> None:
    text = TAILSCALE_NOTION_FUNNEL_SH.read_text(encoding="utf-8")
    snippet = extract(text, "extract_tailscale_enable_url() {", "ensure_no_conflicting_funnel_service() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fake_cmd = tmp_path / "fake-tailscale-funnel"
        fake_cmd.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' 'Funnel is not enabled on your tailnet.'\n"
            "printf '%s\\n' 'https://login.tailscale.com/f/funnel?node=testnode'\n"
            "sleep 10\n",
            encoding="utf-8",
        )
        fake_cmd.chmod(0o755)
        script = f"""
set -euo pipefail
ARCLINK_TAILSCALE_COMMAND_TIMEOUT=0.2s
{snippet}
if run_funnel_cmd {shlex.quote(str(fake_cmd))}; then
  echo unexpected-success
else
  echo "STATUS=$?"
fi
"""
        result = bash(script)
        expect(result.returncode == 0, f"tailscale funnel timeout test shell failed: {result.stderr}")
        combined = result.stdout + result.stderr
        expect("STATUS=124" in result.stdout, result.stdout)
        expect("Funnel is not enabled on your tailnet" in combined, combined)
        expect("https://login.tailscale.com/f/funnel?node=testnode" in combined, combined)
        expect("Press ENTER after enabling Tailscale Funnel" in combined, combined)
        expect("rerun ./deploy.sh install" in combined, combined)
    print("PASS test_tailscale_funnel_command_timeout_surfaces_enablement_guidance")


def test_mcp_exposes_user_owned_ssot_preflight_and_approval_tools() -> None:
    server_text = (REPO / "python" / "arclink_mcp_server.py").read_text(encoding="utf-8")
    expect('"ssot.preflight"' in server_text, "agents should be able to check Notion writeability before writing")
    expect('"ssot.approve"' in server_text and '"ssot.deny"' in server_text, "queued Notion writes should be user-approvable by the agent lane")
    expect("approve_ssot_pending_write(" in server_text, "MCP ssot.approve should apply queued writes")
    expect("deny_ssot_pending_write(" in server_text, "MCP ssot.deny should deny queued writes")
    expect("str(row.get(\"agent_id\") or \"\") != agent_id" in server_text, "MCP approval tools must stay scoped to the caller's own pending writes")
    print("PASS test_mcp_exposes_user_owned_ssot_preflight_and_approval_tools")


def test_control_py_discovers_artifact_priv_dir_config() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_artifact_discovery")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        priv_dir = tmp_path / "deployed" / "arclink-priv"
        config_path = priv_dir / "config" / "arclink.env"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("ARCLINK_USER=operator-svc\n", encoding="utf-8")
        artifact_path = tmp_path / ".arclink-operator.env"
        artifact_path.write_text(
            "\n".join(
                [
                    "ARCLINK_OPERATOR_DEPLOYED_USER=operator-svc",
                    f"ARCLINK_OPERATOR_DEPLOYED_PRIV_DIR={shlex.quote(str(priv_dir))}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        old_env = os.environ.copy()
        try:
            os.environ.pop("ARCLINK_CONFIG_FILE", None)
            os.environ["ARCLINK_REPO_DIR"] = str(repo_root)
            os.environ["ARCLINK_OPERATOR_ARTIFACT_FILE"] = str(artifact_path)
            discovered = mod._discover_config_file()
        finally:
            os.environ.clear()
            os.environ.update(old_env)

        expect(discovered == config_path, f"expected control module to discover {config_path}, got {discovered!r}")
    print("PASS test_control_py_discovers_artifact_priv_dir_config")


def test_sync_public_repo_preserves_template_arclink_priv_while_excluding_top_level_private_repo() -> None:
    text = DEPLOY_SH.read_text()
    snippet = extract(text, "sync_public_repo_from_source() {", "git_head_commit() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        source_dir = tmp_path / "source"
        target_dir = tmp_path / "target"
        (source_dir / "arclink-priv").mkdir(parents=True)
        (source_dir / "arclink-priv" / "secret.txt").write_text("should-not-copy\n", encoding="utf-8")
        (source_dir / "templates" / "arclink-priv" / "vault" / "Research").mkdir(parents=True)
        (source_dir / "templates" / "arclink-priv" / "vault" / "Research" / ".vault").write_text("name: Research\n", encoding="utf-8")
        (source_dir / "bin").mkdir(parents=True)
        (source_dir / "bin" / "bootstrap-userland.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (source_dir / ".git").write_text("gitdir: /tmp/not-for-deploy\n", encoding="utf-8")
        script = f"""
{snippet}
sync_public_repo_from_source {shlex.quote(str(source_dir))} {shlex.quote(str(target_dir))}
if [[ -e {shlex.quote(str(target_dir / 'arclink-priv'))} ]]; then
  echo 'TOP_LEVEL_PRIVATE_PRESENT=1'
else
  echo 'TOP_LEVEL_PRIVATE_PRESENT=0'
fi
if [[ -f {shlex.quote(str(target_dir / 'templates' / 'arclink-priv' / 'vault' / 'Research' / '.vault'))} ]]; then
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
    print("PASS test_sync_public_repo_preserves_template_arclink_priv_while_excluding_top_level_private_repo")


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
        subprocess.run(["git", "-C", str(source_dir), "config", "user.name", "ArcLink Test"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(source_dir), "config", "user.email", "arclink-test@example.com"], check=True, capture_output=True, text=True)
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
        subprocess.run(["git", "-C", str(source_dir), "config", "user.name", "ArcLink Test"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(source_dir), "config", "user.email", "arclink-test@example.com"], check=True, capture_output=True, text=True)
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
ARCLINK_INSTALL_PUBLIC_GIT=1 sync_public_repo_from_source {shlex.quote(str(source_dir))} {shlex.quote(str(target_dir))}
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
        '"$ARCLINK_REPO_DIR/bin/arclink-ctl"' in reset and "purge-enrollment" in reset,
        "expected enrollment reset flow to call arclink-ctl user purge-enrollment",
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
    expect("ARCLINK_ORG_NAME" in text, "expected deploy config to persist org interview fields")
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
    expect('env \\' in upgrade and '"$ARCLINK_REPO_DIR/bin/bootstrap-system.sh"' in upgrade, upgrade)
    print("PASS test_root_install_and_upgrade_do_not_globally_export_runtime_secrets")


def test_bootstrap_system_supports_optional_podman_and_tailscale_install() -> None:
    text = (REPO / "bin" / "bootstrap-system.sh").read_text(encoding="utf-8")
    expect("install_podman_if_requested()" in text, text)
    expect("install_tailscale_if_requested()" in text, text)
    expect("curl -fsSL https://tailscale.com/install.sh | sh" in text, text)
    expect("python3-jsonschema" in text and "python3-yaml" in text, text)
    expect("systemd=true" in text and "wsl --shutdown" in text, text)
    print("PASS test_bootstrap_system_supports_optional_podman_and_tailscale_install")


def test_bootstrap_userland_avoids_legacy_remote_qmd_skill_fetch() -> None:
    text = (REPO / "bin" / "bootstrap-userland.sh").read_text(encoding="utf-8")
    expect("official/research/qmd" not in text, text)
    expect("ensure_shared_hermes_runtime" in text, text)
    print("PASS test_bootstrap_userland_avoids_legacy_remote_qmd_skill_fetch")


def test_install_system_services_includes_independent_notion_claim_poller() -> None:
    text = INSTALL_SYSTEM_SERVICES_SH.read_text(encoding="utf-8")
    expect("arclink-notion-claim-poll.service" in text, "expected dedicated notion claim poll service")
    expect("arclink-notion-claim-poll.timer" in text, "expected dedicated notion claim poll timer")
    expect("--claims-only" in text, "expected claim poller to use provisioner claims-only mode")
    expect("OnUnitActiveSec=2m" in text, "expected claim poll cadence to be configured")
    expect(
        "ARCLINK_INSTALL_SYSTEM_SERVICES_DEFER_START" in text
        and "systemctl stop" in text
        and "arclink-enrollment-provision.service" in text
        and "arclink-notion-claim-poll.service" in text,
        "install-system-services should support deferring root-owned provisioning jobs during install/upgrade",
    )
    print("PASS test_install_system_services_includes_independent_notion_claim_poller")


def test_install_system_services_units_pass_systemd_analyze_verify() -> None:
    systemd_analyze = shutil.which("systemd-analyze")
    if not systemd_analyze:
        print("PASS test_install_system_services_units_pass_systemd_analyze_verify (skipped: systemd-analyze unavailable)")
        return
    text = INSTALL_SYSTEM_SERVICES_SH.read_text(encoding="utf-8")
    enrollment_service = extract_heredoc(text, 'cat >"$TARGET_DIR/arclink-enrollment-provision.service" <<EOF')
    enrollment_timer = extract_heredoc(text, 'cat >"$TARGET_DIR/arclink-enrollment-provision.timer" <<EOF')
    claim_service = extract_heredoc(text, 'cat >"$TARGET_DIR/arclink-notion-claim-poll.service" <<EOF')
    claim_timer = extract_heredoc(text, 'cat >"$TARGET_DIR/arclink-notion-claim-poll.timer" <<EOF')

    def systemd_quote(value: str, *, exec_arg: bool = False) -> str:
        value = value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
        if exec_arg:
            value = value.replace("$", "$$")
        return f'"{value}"'

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo_dir = root / "repo with %specifier"
        (repo_dir / "bin").mkdir(parents=True, exist_ok=True)
        provision_script = repo_dir / "bin" / "arclink-enrollment-provision.sh"
        provision_script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        provision_script.chmod(0o755)
        config_path = root / "config with %specifier" / "arclink.env"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("ARCLINK_USER=arclink\n", encoding="utf-8")
        replacements = {
            "$SYSTEMD_CONFIG_ENV": systemd_quote(f"ARCLINK_CONFIG_FILE={config_path}"),
            "$SYSTEMD_PROVISION_EXEC": systemd_quote(str(provision_script), exec_arg=True),
        }

        def materialize(content: str) -> str:
            rendered = content
            for needle, value in replacements.items():
                rendered = rendered.replace(needle, value)
            return rendered

        service_path = root / "arclink-enrollment-provision.service"
        timer_path = root / "arclink-enrollment-provision.timer"
        claim_service_path = root / "arclink-notion-claim-poll.service"
        claim_timer_path = root / "arclink-notion-claim-poll.timer"
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
        systemd_output = result.stderr or result.stdout
        if result.returncode != 0 and "Failed to initialize path lookup table" in systemd_output:
            print("PASS test_install_system_services_units_pass_systemd_analyze_verify (skipped: host systemd-analyze cannot initialize unit paths)")
            return
        expect(result.returncode == 0, f"systemd-analyze verify failed: {systemd_output}")
    print("PASS test_install_system_services_units_pass_systemd_analyze_verify")


def test_upgrade_fetch_is_noninteractive_and_requires_deploy_key_for_ssh() -> None:
    text = DEPLOY_SH.read_text()
    checkout = extract(text, "checkout_upstream_release() {", "write_operator_checkout_artifact() {")
    expect("GIT_TERMINAL_PROMPT=0" in checkout, checkout)
    expect("GIT_ASKPASS=/bin/false" in checkout, checkout)
    expect("SSH_ASKPASS=/bin/false" in checkout, checkout)
    expect("GCM_INTERACTIVE=Never" in checkout, checkout)
    expect("Refusing SSH upstream without the ArcLink upstream deploy-key lane enabled" in checkout, checkout)
    print("PASS test_upgrade_fetch_is_noninteractive_and_requires_deploy_key_for_ssh")


def test_upgrade_refuses_non_arclink_branch_without_explicit_override() -> None:
    text = DEPLOY_SH.read_text()
    guard = extract(text, "require_main_upstream_branch_for_upgrade() {", "write_operator_checkout_artifact() {")
    upgrade = extract(text, "run_root_upgrade() {", "run_root_remove() {")
    flow = extract(text, "run_upgrade_flow() {", "run_agent_payload() {")
    expect('ARCLINK_ALLOW_NON_ARCLINK_UPGRADE:-0' in guard, guard)
    expect("Refusing production upgrade from non-arclink upstream branch" in guard, guard)
    expect("require_main_upstream_branch_for_upgrade" in upgrade, upgrade)
    expect("require_main_upstream_branch_for_upgrade" in flow, flow)
    print("PASS test_upgrade_refuses_non_arclink_branch_without_explicit_override")


def test_install_answer_file_has_exit_trap_cleanup() -> None:
    text = DEPLOY_SH.read_text()
    install_flow = extract(text, "run_install_flow() {", "run_remove_flow() {")
    remove_flow = extract(text, "run_remove_flow() {", 'if [[ -n "$PRIVILEGED_MODE" ]]; then')
    expect("mktemp /tmp/arclink-install" in install_flow and "trap 'rm -f" in install_flow, install_flow)
    expect("mktemp /tmp/arclink-remove" in remove_flow and "trap 'rm -f" in remove_flow, remove_flow)
    print("PASS test_install_answer_file_has_exit_trap_cleanup")


def test_ci_install_smoke_force_removes_auto_provision_user() -> None:
    text = CI_INSTALL_SMOKE_SH.read_text()
    cleanup = extract(text, "remove_smoke_auto_provision_user() {", "preclean() {")
    preclean = extract(text, "preclean() {", "on_exit() {")
    expect("loginctl terminate-user" in cleanup, cleanup)
    expect("pkill -KILL -u" in cleanup, cleanup)
    expect("userdel -r" in cleanup, cleanup)
    expect("run_login_user_systemctl" in cleanup and "disable --now" in cleanup, cleanup)
    expect("remove_smoke_auto_provision_user" in preclean, preclean)
    expect("remove_smoke_auto_provision_user" in extract(text, "teardown() {", "remove_smoke_auto_provision_user() {"), text)
    print("PASS test_ci_install_smoke_force_removes_auto_provision_user")


def test_ci_install_smoke_reports_teardown_residue_on_failure_path() -> None:
    text = CI_INSTALL_SMOKE_SH.read_text()
    on_exit = extract(text, "on_exit() {", "trap 'on_exit $?")
    expect("assert_smoke_target_removed()" in text, text)
    expect("assert_smoke_target_removed ||" in on_exit, on_exit)
    expect("Smoke teardown left ArcLink residue after failure." in on_exit, on_exit)
    print("PASS test_ci_install_smoke_reports_teardown_residue_on_failure_path")


def test_ci_install_smoke_dashboard_login_uses_root_path_for_subpaths() -> None:
    text = CI_INSTALL_SMOKE_SH.read_text()
    helper = extract(text, "http_status_code() {", "wait_for_http_status() {")
    expect('"/__arclink/login"' in helper, helper)
    expect("urljoin(url.rstrip" not in helper, helper)
    expect("next_path=" in helper and 'parsed.path or "/"' in helper, helper)
    bearer = extract(text, "assert_dashboard_proxy_bearer_flow() {", "run_arclink_shell() {")
    expect('"/__arclink/login"' in bearer, bearer)
    expect("urljoin(dashboard_url.rstrip" not in bearer, bearer)
    expect("NoRedirect" in bearer, bearer)
    expect("http.cookies.SimpleCookie" in bearer and '"Cookie": cookie_header' in bearer, bearer)
    print("PASS test_ci_install_smoke_dashboard_login_uses_root_path_for_subpaths")


def test_ci_install_smoke_rate_limit_uses_actual_loopback_bucket() -> None:
    text = CI_INSTALL_SMOKE_SH.read_text()
    body = extract(text, "assert_bootstrap_rate_limit() {", "assert_admin_endpoint_auth() {")
    expect("real bucket is 127.0.0.1" in body, body)
    expect("SELECT COUNT(*) FROM rate_limits WHERE scope = 'ip' AND subject = '127.0.0.1'" in body, body)
    expect("remaining=$((cap - current_count))" in body, body)
    expect('"source_ip":"127.0.0.1"' in body, body)
    expect('"source_ip":"100.64.55.1"' not in body, body)
    expect("X-ArcLink-MCP-Error-Status".lower() in body.lower(), body)
    expect("Expected effective 429" in body, body)
    expect("DELETE FROM bootstrap_requests WHERE requester_identity LIKE 'rate-%'" in body, body)
    expect("DELETE FROM notification_outbox WHERE message LIKE '%rate-%'" in body, body)
    expect("DELETE FROM rate_limits WHERE scope IN ('ip', 'global')" in body, body)
    print("PASS test_ci_install_smoke_rate_limit_uses_actual_loopback_bucket")


def test_ci_install_smoke_admin_auth_respects_loopback_source_policy() -> None:
    text = CI_INSTALL_SMOKE_SH.read_text()
    body = extract(text, "assert_admin_endpoint_auth() {", "assert_token_reinstate() {")
    expect("operator_token required" in body or "operator_token" in body, body)
    expect("Loopback source_ip overrides are disabled" in body, body)
    expect('SELECT source_ip FROM bootstrap_requests WHERE request_id' in body, body)
    expect('stored_source" != "127.0.0.1"' in body, body)
    expect('bootstrap.status' in body and '\\"source_ip\\":\\"100.64.200.99\\"' in body, body)
    expect("DELETE FROM bootstrap_requests WHERE request_id" in body, body)
    print("PASS test_ci_install_smoke_admin_auth_respects_loopback_source_policy")


def test_ci_install_smoke_arms_notion_webhook_install_window() -> None:
    text = CI_INSTALL_SMOKE_SH.read_text()
    body = extract(text, "assert_notion_webhook_flow() {", "assert_notification_delivery_backlog() {")
    expect("webhook-arm-install" in body, body)
    expect("--actor ci-install-smoke" in body, body)
    expect("--minutes 5" in body, body)
    expect('"$resp" != "202" && "$resp" != "200"' in body, body)
    expect(
        body.index("webhook-arm-install") < body.index('--data \'{\\"verification_token\\"'),
        "expected smoke to arm Notion webhook verification-token install before posting the token",
    )
    print("PASS test_ci_install_smoke_arms_notion_webhook_install_window")


def test_ci_install_smoke_removes_synthetic_control_plane_agents_before_final_health() -> None:
    text = CI_INSTALL_SMOKE_SH.read_text()
    cleanup = extract(text, "cleanup_smoke_control_plane_agents() {", "assert_notification_delivery_backlog() {")
    expect("user purge-enrollment" in cleanup, cleanup)
    expect("smokebot ssotbot reinsbot" in cleanup, cleanup)
    expect("--purge-rate-limits" in cleanup, cleanup)
    expect("rm -rf /tmp/arclink-smoke-agent-home /tmp/arclink-smoke-ssot-home" in cleanup, cleanup)
    tail = extract(text, 'echo "Checking notification delivery backlog routing..."', 'echo "Starting runtime checks..."')
    expect("assert_notification_delivery_backlog" in tail, tail)
    expect("cleanup_smoke_control_plane_agents" in tail, tail)
    expect(tail.index("assert_notification_delivery_backlog") < tail.index("cleanup_smoke_control_plane_agents"), tail)
    print("PASS test_ci_install_smoke_removes_synthetic_control_plane_agents_before_final_health")


def test_ci_install_smoke_treats_qmd_embedding_backlog_as_retryable_after_search_proof() -> None:
    text = CI_INSTALL_SMOKE_SH.read_text()
    for marker in (
        "direct markdown changes",
        "direct text changes",
        "PDF-derived markdown changes",
    ):
        idx = text.find(f"Warning: watcher-driven qmd embedding backlog did not clear after {marker}")
        expect(idx >= 0, f"expected retryable qmd embedding warning for {marker}")
        window = text[idx : idx + 420]
        expect("return 1" not in window, window)
        expect("show_pdf_ingest_diagnostics" not in window, window)
        expect("embeddings will retry on the next refresh" in window, window)
    print("PASS test_ci_install_smoke_treats_qmd_embedding_backlog_as_retryable_after_search_proof")


def test_health_checks_failed_systemd_units_and_stale_podman_transients() -> None:
    text = HEALTH_SH.read_text()
    expect("check_system_failed_units" in text and "systemctl --failed --no-legend --plain" in text, text)
    expect("check_service_user_failed_units" in text and "systemctl --user --failed --no-legend --plain" in text, text)
    expect("failed_units_are_stale_podman_healthchecks" in text and "systemctl --user reset-failed" in text, text)
    expect("failed_units_are_stale_deleted_user_managers" in text, text)
    expect('^user@([0-9]+)\\.service$' in text and 'getent passwd "$uid"' in text, text)
    expect('systemctl reset-failed "$unit"' in text, text)
    print("PASS test_health_checks_failed_systemd_units_and_stale_podman_transients")


def test_upstream_branch_defaults_to_arclink_everywhere() -> None:
    """All deploy.sh branch fallbacks must default to arclink for the current production lane."""
    text = DEPLOY_SH.read_text()
    detect = extract(text, "detect_github_repo() {", "discover_existing_config() {")
    expect('local default_branch="${ARCLINK_UPSTREAM_BRANCH:-arclink}"' in detect, detect)
    expect('GITHUB_REPO_BRANCH="main"' not in detect, detect)
    expect('GITHUB_REPO_BRANCH="${branch:-$default_branch}"' in detect, detect)
    # Every ${ARCLINK_UPSTREAM_BRANCH:-<value>} fallback must use arclink
    import re as _re
    fallbacks = _re.findall(r'ARCLINK_UPSTREAM_BRANCH:-(\w+)', text)
    for fb in fallbacks:
        expect(fb == "arclink", f"ARCLINK_UPSTREAM_BRANCH fallback is '{fb}', expected 'arclink'")
    # common.sh must also default to the production arclink lane
    common_text = (REPO / "bin" / "common.sh").read_text()
    common_fallbacks = _re.findall(r'ARCLINK_UPSTREAM_BRANCH:-(\w+)', common_text)
    for fb in common_fallbacks:
        expect(fb == "arclink", f"common.sh ARCLINK_UPSTREAM_BRANCH fallback is '{fb}', expected 'arclink'")
    # README must not say clone -b arclink
    readme_text = (REPO / "README.md").read_text()
    expect("clone -b arclink" not in readme_text, "README still says 'clone -b arclink'")
    print("PASS test_upstream_branch_defaults_to_arclink_everywhere")


def test_bootstrap_system_includes_jq_and_iproute2() -> None:
    """Bare-metal bootstrap must install jq and iproute2."""
    text = BOOTSTRAP_SYSTEM_SH.read_text()
    expect("jq" in text and "iproute2" in text,
           "bootstrap-system.sh must install jq and iproute2 as base dependencies")
    print("PASS test_bootstrap_system_includes_jq_and_iproute2")


def test_health_db_probe_failures_cause_fail() -> None:
    """When the Python DB probe command itself fails (non-warning), health must fail, not just warn."""
    text = HEALTH_SH.read_text()
    vault_probe = extract(text, "check_vault_definition_health() {", "check_curator_state() {")
    # The non-warning failure path (case *) must use fail, not warn_or_fail
    expect('fail "could not reload .vault definitions"' in vault_probe,
           "vault definition probe command failure must use fail(), not warn_or_fail()")
    print("PASS test_health_db_probe_failures_cause_fail")


def test_systemd_unit_paths_are_quoted() -> None:
    """Generated root systemd values must be quoted and specifier-safe."""
    system_text = INSTALL_SYSTEM_SERVICES_SH.read_text()
    expect("systemd_quote_value()" in system_text, "install-system-services.sh must quote systemd values")
    expect("systemd_quote_exec_arg()" in system_text, "install-system-services.sh must quote ExecStart args")
    expect('value="${value//%/%%}"' in system_text, "systemd values must escape percent specifiers")
    expect("reject_systemd_unit_value" in system_text, "systemd unit values must reject control characters")
    expect("dollar-sign substitution" in system_text, "systemd unit values must reject dollar substitution")
    expect("Environment=$SYSTEMD_CONFIG_ENV" in system_text, "config env assignment must use quoted value")
    expect("ExecStart=$SYSTEMD_PROVISION_EXEC" in system_text,
           "install-system-services.sh ExecStart paths must use quoted values")
    # User units: ExecStart must also use quoted paths
    user_text = (REPO / "bin" / "install-agent-user-services.sh").read_text()
    expect("systemd_env_line()" in user_text, "install-agent-user-services.sh must quote generated Environment values")
    expect("reject_systemd_unit_value" in user_text, "user unit values must reject control characters and substitutions")
    import re as _re_local
    exec_lines = [l.strip() for l in user_text.splitlines() if l.strip().startswith("ExecStart=")]
    for line in exec_lines:
        first_token = line.split("=", 1)[1].split()[0]
        expect(first_token.startswith('"') or first_token.startswith("'"),
               f"install-agent-user-services.sh ExecStart path must be quoted: {line}")
    print("PASS test_systemd_unit_paths_are_quoted")


def test_deploy_uses_effective_nextcloud_enablement_for_runtime_actions() -> None:
    text = DEPLOY_SH.read_text()
    expect("nextcloud_effectively_enabled()" in text,
           "deploy.sh must define nextcloud_effectively_enabled for standalone stable-copy execution")
    expect("nextcloud_runtime_available()" in text,
           "deploy.sh must define the Nextcloud runtime probe used by nextcloud_effectively_enabled")
    expect("if nextcloud_effectively_enabled; then\n      run_as_user_systemd" in text,
           "shared service restart must use effective Nextcloud enablement")
    expect('if nextcloud_effectively_enabled; then\n    wait_for_port 127.0.0.1 "$NEXTCLOUD_PORT"' in text,
           "install/upgrade port waits must use effective Nextcloud enablement")
    expect("warn_retired_tailscale_nextcloud_serve()" in text,
           "retired Tailscale Nextcloud Serve flag must warn instead of publishing or tearing down")
    expect('"$ARCLINK_REPO_DIR/bin/tailscale-nextcloud-serve.sh"' not in text,
           "ENABLE_TAILSCALE_SERVE must not drive the retired serve/teardown script during install or upgrade")
    expect("no Nextcloud runtime is available; install podman or docker compose before rotating credentials" in text,
           "credential rotation must fail before starting a missing Nextcloud runtime")
    print("PASS test_deploy_uses_effective_nextcloud_enablement_for_runtime_actions")


def test_nextcloud_startup_repairs_persisted_runtime_config() -> None:
    text = (REPO / "bin" / "nextcloud-up.sh").read_text()
    expect("repair_podman_nextcloud_config_file()" in text,
           "Podman Nextcloud startup must repair compose-era persisted config values")
    expect("\"s/'dbhost'[[:space:]]*=>[[:space:]]*'(db|postgres)'/'dbhost' => '127.0.0.1'/\"" in text,
           "Podman Nextcloud startup must migrate existing DB hostnames to loopback")
    expect("ensure_nextcloud_system_config()" in text,
           "Nextcloud startup must enforce trusted domains and overwrite URL after occ is ready")
    expect('config:system:set trusted_domains 2 --value="$NEXTCLOUD_TRUSTED_DOMAIN"' in text,
           "Nextcloud startup must add the configured trusted domain to persisted config")
    print("PASS test_nextcloud_startup_repairs_persisted_runtime_config")


def test_control_install_wires_single_operator_hermes_agent() -> None:
    deploy_text = DEPLOY_SH.read_text()
    docker_text = (REPO / "bin" / "arclink-docker.sh").read_text()
    compose_text = (REPO / "compose.yaml").read_text()
    # Onboarding selects the ArcLink user that owns the operator's one agent.
    expect("Give the operator a dedicated Hermes agent" in deploy_text,
           "control onboarding must offer the operator's single Hermes agent")
    expect("ARCLINK_OPERATOR_AGENT_USER_ID" in deploy_text and "ARCLINK_OPERATOR_AGENT_ENABLED" in deploy_text,
           "operator agent owner/enable must be collected")
    expect('ARCLINK_OPERATOR_AGENT_ENABLED="${ARCLINK_OPERATOR_AGENT_ENABLED:-1}"' in deploy_text,
           "operator agent setup must default to enabled unless explicitly disabled")
    expect('write_kv ARCLINK_OPERATOR_AGENT_USER_ID' in deploy_text,
           "operator agent owner must be persisted to generated config")
    # Install flow provisions the control-stack service identity, idempotently.
    expect("ensure_control_operator_agent" in deploy_text,
           "control install flow must ensure the operator agent")
    expect("run_arclink_docker operator-agent-setup" in deploy_text,
           "control install must invoke the in-container operator identity setup")
    expect("control-operator-hermes-gateway:" in compose_text and "control-operator-hermes-dashboard:" in compose_text,
           "compose.yaml must expose Operator Hermes inside the Control Node stack")
    expect("control-operator-hermes-setup:" in compose_text,
           "operator Hermes home/control-router setup must be isolated into a one-shot setup service")
    expect("control-operator-nextcloud:" in compose_text and "control-operator-memory-synth:" in compose_text,
           "operator services must include own files/vault and memory lanes")
    expect("install-operator-hermes-home.sh" in compose_text,
           "operator Hermes services must seed their own Hermes home")
    operator_install_text = (REPO / "bin" / "install-operator-hermes-home.sh").read_text()
    expect("ensure_llm_router_key(" in operator_install_text and "generate_llm_router_raw_key()" in operator_install_text,
           "operator Hermes must provision its own ArcLink LLM router key")
    expect('export ARCLINK_CHUTES_API_KEY_FILE="$operator_router_key_file"' in operator_install_text,
           "operator Hermes must send the router key to the internal LLM router, not the upstream provider key")
    expect("/opt/arclink/runtime/hermes-venv/bin/hermes gateway run --replace" in compose_text,
           "operator Hermes gateway must execute the pinned runtime hermes directly")
    expect("ARCLINK_CONFIG_FILE: /home/arclink/arclink/arclink-priv/state/operator/config/operator.env" in compose_text,
           "operator services must not source the global Docker env over their operator-scoped paths")
    expect('ARCLINK_RUNTIME_ENV_CONFIG: "1"' in compose_text,
           "operator services must generate operator.env from the operator-scoped Compose environment")
    gateway_block = compose_text.split("  control-operator-hermes-gateway:", 1)[1].split("\n\n", 1)[0]
    dashboard_block = compose_text.split("  control-operator-hermes-dashboard:", 1)[1].split("\n\n", 1)[0]
    setup_block = compose_text.split("  control-operator-hermes-setup:", 1)[1].split("\n\n", 1)[0]
    vault_watch_block = compose_text.split("  control-operator-vault-watch:", 1)[1].split("\n\n", 1)[0]
    memory_synth_block = compose_text.split("  control-operator-memory-synth:", 1)[1].split("\n\n", 1)[0]
    wrapped_block = compose_text.split("  control-operator-arclink-wrapped:", 1)[1].split("\n\n", 1)[0]
    for runtime_block in (gateway_block, dashboard_block):
        expect("*arclink-control-secret-env" not in runtime_block,
               f"interactive operator runtime must not inherit control secret env\n{runtime_block}")
        expect("./arclink-priv/state:/home/arclink/arclink/arclink-priv/state" not in runtime_block,
               f"interactive operator runtime must not mount broad control state\n{runtime_block}")
        expect("ARCLINK_DB_PATH:" not in runtime_block,
               f"interactive operator runtime must not receive the control DB path\n{runtime_block}")
        expect("./arclink-priv/state/operator:/home/arclink/arclink/arclink-priv/state/operator" in runtime_block,
               f"interactive operator runtime must mount only operator state\n{runtime_block}")
    expect("./arclink-priv/state:/home/arclink/arclink/arclink-priv/state" in setup_block,
           "one-shot setup must mount the control state DIRECTORY so its router-key write shares the WAL/-shm the router reads (a single-file mount silently loses the write)")
    expect("ARCLINK_DB_PATH: /home/arclink/arclink/arclink-priv/state/arclink-control.sqlite3" in setup_block,
           "one-shot setup must scope the control DB env to setup only")
    for maintenance_block in (vault_watch_block, memory_synth_block, wrapped_block):
        expect("ARCLINK_DB_PATH: /home/arclink/arclink/arclink-priv/state/arclink-control.sqlite3" in maintenance_block,
               f"operator background maintenance job must read the control DB explicitly despite operator memory STATE_DIR\n{maintenance_block}")
        expect("./arclink-priv/state:/home/arclink/arclink/arclink-priv/state" in maintenance_block,
               f"operator background maintenance job must mount the global state directory so the control DB path exists\n{maintenance_block}")
    expect("ARCLINK_LLM_ROUTER_KEY_HASH_PEPPER: ${ARCLINK_LLM_ROUTER_KEY_HASH_PEPPER:-}" in setup_block,
           "one-shot setup must hash the operator router key with the same optional router pepper as the router")
    expect("ARCLINK_SESSION_HASH_PEPPER: ${ARCLINK_SESSION_HASH_PEPPER:-}" in setup_block,
           "one-shot setup must hash the operator router key with the same session pepper fallback as the router")
    expect("ARCLINK_SQLITE_JOURNAL_MODE: MEMORY" not in setup_block,
           "one-shot setup must not force MEMORY journal; it shares the control DB's WAL like control-api")
    expect("condition: service_completed_successfully" in gateway_block and "condition: service_completed_successfully" in dashboard_block,
           "interactive operator runtime must wait for setup instead of touching the DB on each start")
    # The docker helper runs the idempotent ensure inside the control container.
    expect("operator-agent-setup)" in docker_text and "docker_operator_agent_setup" in docker_text,
           "arclink-docker.sh must expose operator-agent-setup")
    expect("not a fleet ArcPod" in deploy_text and "not a fleet ArcPod" in docker_text,
           "operator agent docs must not describe the runtime as a Captain ArcPod")
    expect('-e ARCLINK_OPERATOR_AGENT_ENABLED="${ARCLINK_OPERATOR_AGENT_ENABLED:-1}"' in docker_text,
           "docker operator-agent setup must pass the default-on enable flag into the supervisor container")
    expect("arclink_operator_agent.py ensure --require-enabled" in docker_text,
           "operator agent setup must call the idempotent, enable-guarded ensure")
    expect("arclink_operator_agent.py ensure --require-enabled \"$@\" || true" not in docker_text,
           "operator agent setup must not mask ensure failures")
    print("PASS test_control_install_wires_single_operator_hermes_agent")


def main() -> int:
    tests = [
        test_bool_env_blank_uses_default,
        test_emit_runtime_config_normalizes_curator_onboarding_flags,
        test_emit_runtime_config_syncs_agent_tailscale_serve_with_global_flag,
        test_emit_runtime_config_defaults_public_telegram_webhook_to_callback_ready_route,
        test_emit_runtime_config_migrates_legacy_vault_watch_debounce,
        test_emit_runtime_config_persists_notion_ssot_fields,
        test_emit_runtime_config_persists_hermes_docs_sync_fields,
        test_emit_runtime_config_preserves_custom_hermes_docs_ref,
        test_emit_runtime_config_persists_extra_mcp_url,
        test_emit_runtime_config_persists_qmd_embedding_endpoint_fields,
        test_emit_runtime_config_reconciles_existing_fleet_private_endpoints_into_allowlist,
        test_emit_runtime_config_reconciles_docker_host_state_inventory_into_allowlist,
        test_deploy_guides_explicit_notion_webhook_event_selection,
        test_deploy_uses_stable_copy_for_privileged_reexec,
        test_nextcloud_rotation_uses_secret_files_instead_of_password_argv,
        test_qmd_refresh_bounds_embedding_work,
        test_qmd_refresh_falls_back_to_local_embedding_when_endpoint_provider_selected,
        test_qmd_refresh_forces_and_consumes_local_rebuild_flag,
        test_qmd_refresh_atomically_rewrites_config_and_surfaces_embed_failure,
        test_placeholder_upstream_default_uses_checkout_origin,
        test_json_field_reads_json_payload,
        test_noninteractive_notion_webhook_setup_flow_fails_closed_until_verified,
        test_detect_tailscale_serve_distinguishes_qmd_from_arclink_routes,
        test_path_is_within_and_safe_remove_use_canonical_paths,
        test_run_health_check_falls_back_when_user_bus_is_missing,
        test_install_and_upgrade_run_live_agent_tool_smoke_after_health,
        test_install_and_upgrade_refresh_upgrade_check_before_health,
        test_install_and_upgrade_mark_deploy_operation_window,
        test_install_and_upgrade_run_user_agent_refresh_before_health,
        test_install_offers_optional_notion_ssot_setup_before_health,
        test_live_agent_tool_smoke_blocks_broader_python_heredoc_variants,
        test_hermes_config_migration_is_unattended,
        test_live_agent_tool_smoke_inspects_private_home_as_target_user,
        test_discord_onboarding_dedupes_message_ids_before_state_transitions,
        test_live_agent_tool_smoke_parses_explicit_selectors,
        test_ci_workflow_runs_python_lint_before_direct_test_loop,
        test_ci_preflight_lints_root_deploy_and_pins_pdf_backend,
        test_live_agent_tool_smoke_opens_control_db_read_only,
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
        test_collect_install_answers_moves_tailnet_serve_when_public_notion_funnel_uses_443,
        test_collect_qmd_embedding_answers_reconfigures_between_local_and_endpoint,
        test_collect_install_answers_does_not_prompt_for_telegram_token_up_front,
        test_secret_prompt_helpers_do_not_prefix_newlines,
        test_deploy_menu_defaults_to_sovereign_control_node,
        test_baremetal_install_banner_points_to_docker_first_path,
        test_org_profile_builder_installs_jsonschema,
        test_collect_install_answers_randomizes_placeholder_passwords,
        test_collect_install_answers_preserves_placeholder_passwords_during_stateful_repair,
        test_collect_install_answers_guides_backup_remote_setup,
        test_collect_install_answers_guides_upstream_deploy_key_setup,
        test_tailscale_onboarding_guidance_mentions_https_certificates_in_native_flow_only,
        test_upstream_deploy_key_flow_prints_key_and_verifies_read_write_access,
        test_upstream_deploy_key_flow_offers_reuse_when_existing_key_already_works,
        test_collect_install_answers_reuses_private_repo_backup_remote_when_config_is_unreadable,
        test_require_supported_host_mode_rejects_native_macos_install,
        test_require_supported_host_mode_guides_wsl_without_systemd,
        test_collect_install_answers_records_missing_host_dependency_choices,
        test_write_answers_file_persists_host_dependency_choices,
        test_deploy_sh_retires_public_docker_control_center,
        test_control_deployment_style_aliases_are_normalized,
        test_control_reconfigure_prompt_normalization_is_shell_safe,
        test_control_reconfigure_autoregisters_local_starter_worker,
        test_control_install_collects_trusted_host_acknowledgement_before_build,
        test_control_runtime_reset_is_backup_first_and_guarded,
        test_runtime_backup_tar_honors_pruned_reset_backups,
        test_control_runtime_reset_preserves_operator_state_by_default,
        test_control_runtime_reset_can_explicitly_wipe_operator_state,
        test_control_reset_modes_have_separate_confirmations,
        test_control_fleet_worker_registration_is_first_class,
        test_control_inventory_submenu_and_aliases_are_first_class,
        test_control_enrollment_submenu_and_secret_are_first_class,
        test_control_docker_bootstrap_seeds_session_hash_pepper_and_gateway_broker_token,
        test_control_upgrade_syncs_checkout_from_upstream_before_build,
        test_component_upgrade_reexec_reads_operator_artifact_config_file_key,
        test_init_bootstrap_defaults_to_canonical_repo_and_safe_printf,
        test_operator_hermes_home_install_lock_has_timeout,
        test_ensure_prereqs_ready_fake_system_is_noop,
        test_ensure_prereqs_check_only_plans_missing_without_mutation,
        test_ensure_prereqs_fake_install_uses_packages_and_get_docker_idiom,
        test_ensure_prereqs_wireguard_check_only_plans_tools,
        test_control_install_wires_prereq_auto_installation_with_skip_opt_out,
        test_control_upgrade_runs_full_host_namespace_and_installs_operator_runner,
        test_deploy_sh_guides_notion_workspace_migration,
        test_deploy_sh_guides_notion_page_transfer,
        test_notion_ssot_setup_prompt_points_operator_at_shared_home_page,
        test_notion_ssot_setup_uses_current_checkout_ctl_for_handshake,
        test_shell_scripts_avoid_bash4_only_features,
        test_deploy_reapplies_runtime_access_after_repo_sync,
        test_curator_gateway_defaults_reactions_on,
        test_restart_services_disables_only_curator_native_system_gateway_unit,
        test_tailscale_serve_command_timeout_surfaces_enablement_guidance,
        test_retired_tailscale_serve_flag_does_not_unserve_during_deploy,
        test_tailscale_funnel_command_timeout_surfaces_enablement_guidance,
        test_mcp_exposes_user_owned_ssot_preflight_and_approval_tools,
        test_control_py_discovers_artifact_priv_dir_config,
        test_sync_public_repo_preserves_template_arclink_priv_while_excluding_top_level_private_repo,
        test_sync_public_repo_repairs_existing_git_metadata_from_source,
        test_sync_public_repo_copies_git_metadata_when_public_git_requested,
        test_enrollment_reset_supports_full_forget_purge,
        test_enrollment_align_reseeds_agent_identity,
        test_root_install_and_upgrade_do_not_globally_export_runtime_secrets,
        test_upgrade_fetch_is_noninteractive_and_requires_deploy_key_for_ssh,
        test_upgrade_refuses_non_arclink_branch_without_explicit_override,
        test_install_answer_file_has_exit_trap_cleanup,
        test_ci_install_smoke_force_removes_auto_provision_user,
        test_ci_install_smoke_reports_teardown_residue_on_failure_path,
        test_ci_install_smoke_dashboard_login_uses_root_path_for_subpaths,
        test_ci_install_smoke_rate_limit_uses_actual_loopback_bucket,
        test_ci_install_smoke_admin_auth_respects_loopback_source_policy,
        test_ci_install_smoke_arms_notion_webhook_install_window,
        test_ci_install_smoke_removes_synthetic_control_plane_agents_before_final_health,
        test_ci_install_smoke_treats_qmd_embedding_backlog_as_retryable_after_search_proof,
        test_compose_defaults_academy_live_paths_off,
        test_health_checks_failed_systemd_units_and_stale_podman_transients,
        test_bootstrap_system_supports_optional_podman_and_tailscale_install,
        test_bootstrap_userland_avoids_legacy_remote_qmd_skill_fetch,
        test_install_system_services_includes_independent_notion_claim_poller,
        test_install_system_services_units_pass_systemd_analyze_verify,
        test_upstream_branch_defaults_to_arclink_everywhere,
        test_bootstrap_system_includes_jq_and_iproute2,
        test_health_db_probe_failures_cause_fail,
        test_systemd_unit_paths_are_quoted,
        test_deploy_uses_effective_nextcloud_enablement_for_runtime_actions,
        test_nextcloud_startup_repairs_persisted_runtime_config,
        test_control_install_wires_single_operator_hermes_agent,
    ]
    for test in tests:
        test()
    print(f"PASS all {len(tests)} deploy regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
