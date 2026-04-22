#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence


def shared_tailnet_host(
    *,
    tailscale_serve_enabled: bool,
    tailscale_dns_name: str = "",
    nextcloud_trusted_domain: str = "",
) -> str:
    if not tailscale_serve_enabled:
        return ""
    for raw in (tailscale_dns_name, nextcloud_trusted_domain):
        value = str(raw or "").strip()
        if value:
            return value
    return ""


def shared_resource_lines(
    *,
    host: str,
    tailscale_serve_port: str = "443",
    nextcloud_enabled: bool,
    qmd_url: str,
    public_mcp_host: str,
    public_mcp_port: int,
    qmd_path: str = "/mcp",
    almanac_mcp_path: str = "/almanac-mcp",
    chutes_mcp_url: str = "",
    notion_space_url: str = "",
) -> list[str]:
    lines: list[str] = []
    serve_port = str(tailscale_serve_port or "443").strip() or "443"

    def https_url(path: str) -> str:
        normalized = "/" + str(path or "/").lstrip("/")
        if serve_port == "443":
            return f"https://{host}{normalized}"
        return f"https://{host}:{serve_port}{normalized}"

    if nextcloud_enabled:
        if host:
            lines.append(f"Vault access in Nextcloud: {https_url('/')} (shared mount: /Vault)")
        else:
            lines.append("Vault access in Nextcloud: shared on this host (mounted as /Vault)")

    if host:
        lines.append(f"QMD MCP retrieval rail: {https_url(qmd_path)}")
        lines.append(f"Almanac MCP control rail: {https_url(almanac_mcp_path)}")
    else:
        lines.append(f"QMD MCP retrieval rail: {qmd_url}")
        lines.append(f"Almanac MCP control rail: http://{public_mcp_host}:{public_mcp_port}/mcp")

    if chutes_mcp_url:
        lines.append(f"Chutes knowledge rail: {chutes_mcp_url}")

    notion_space_url = str(notion_space_url or "").strip()
    if notion_space_url:
        lines.append(f"Shared Notion SSOT: {notion_space_url}")
    lines.append("Notion webhook: shared operator-managed rail on this host")
    return lines


def managed_resource_lines(
    *,
    access: Mapping[str, Any] | None,
    workspace_root: Path | str,
    shared_lines: Sequence[str],
) -> list[str]:
    payload = dict(access or {})
    lines: list[str] = []

    dashboard_url = str(payload.get("dashboard_url") or "").strip()
    if dashboard_url:
        lines.append(f"Hermes dashboard: {dashboard_url}")

    code_url = str(payload.get("code_url") or "").strip()
    if code_url:
        lines.append(f"Code workspace: {code_url}")

    workspace_root_text = str(workspace_root or "").strip()
    if workspace_root_text:
        lines.append(f"Workspace root: {workspace_root_text}")

    lines.extend(str(line).strip() for line in shared_lines if str(line).strip())
    lines.append("Credentials are intentionally omitted from managed memory.")
    lines.append("If the user needs access reset or reissued, route that through Curator or the operator.")
    lines.append("These rails are the agent-facing source of truth even when a human-facing message summarizes them more narrowly.")
    return lines


def managed_resource_ref(
    *,
    access: Mapping[str, Any] | None,
    workspace_root: Path | str,
    shared_lines: Sequence[str],
) -> str:
    lines = managed_resource_lines(
        access=access,
        workspace_root=workspace_root,
        shared_lines=shared_lines,
    )
    if not lines:
        return ""
    return "\n".join(
        [
            "Canonical user access rails and shared Almanac addresses:",
            *[f"- {line}" for line in lines],
        ]
    )
