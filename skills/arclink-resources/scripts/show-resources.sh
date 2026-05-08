#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path

DEFAULT_REMOTE_SETUP_URL = ""
HUMAN_SHARED_RESOURCE_SKIP_PREFIXES = (
    "hermes dashboard:",
    "dashboard username:",
    "code workspace:",
    "workspace root:",
    "arclink vault:",
    "vault access in nextcloud:",
    "qmd mcp retrieval rail:",
    "arclink mcp control rail:",
    "credentials are",
    "if the user needs",
    "these rails are",
)


def load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def clean(value: object, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit].rstrip()


def home_root(access: dict[str, object]) -> str:
    explicit = clean(access.get("workspace_root"))
    if explicit:
        return explicit
    raw_home = os.environ.get("HOME", "").strip()
    if raw_home:
        return str(Path(raw_home).expanduser())
    unix_user = clean(access.get("unix_user") or access.get("username"), 80)
    return f"/home/{unix_user}" if unix_user else ""


def vault_root(home: str) -> str:
    return f"{home.rstrip('/')}/ArcLink" if home else "~/ArcLink"


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")


def append_unique(lines: list[str], seen: set[str], line: str) -> None:
    value = str(line or "").strip()
    if not value:
        return
    marker = value.lower()
    if marker in seen:
        return
    seen.add(marker)
    lines.append(value)


def managed_resource_bullets(managed: dict[str, object]) -> list[str]:
    raw = str(managed.get("resource-ref") or "").strip()
    bullets: list[str] = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if line.startswith("- "):
            bullets.append(line[2:].strip())
    return bullets


def shared_lines(managed: dict[str, object], access: dict[str, object], home: str) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for line in managed_resource_bullets(managed):
        lowered = line.lower()
        if any(lowered.startswith(prefix) for prefix in HUMAN_SHARED_RESOURCE_SKIP_PREFIXES):
            continue
        if "nextcloud" in lowered:
            continue
        if "password" in lowered or "secret" in lowered or "credential" in lowered:
            continue
        append_unique(lines, seen, line)
    append_unique(lines, seen, f"Vault path in VS Code and shell: {vault_root(home)}")
    append_unique(lines, seen, "The shared Vault and control rails are already wired into your agent by default.")
    return lines


def remote_lines(access: dict[str, object], identity: dict[str, object]) -> list[str]:
    remote_user = clean(access.get("unix_user") or access.get("username"), 80)
    remote_host = clean(access.get("tailscale_host"), 160)
    setup_url = clean(access.get("remote_setup_url") or os.environ.get("ARCLINK_REMOTE_SETUP_URL") or DEFAULT_REMOTE_SETUP_URL)
    if not (remote_user and remote_host and setup_url):
        return []
    org_name = clean(access.get("org_name") or identity.get("org_name"), 120)
    org_arg = f" --org {shlex.quote(org_name)}" if org_name else ""
    wrapper_org = slug(org_name) or slug(remote_host)
    wrapper_user = slug(remote_user)
    wrapper_name = f"hermes-{wrapper_org}-remote-{wrapper_user}" if wrapper_user and wrapper_org else "hermes-<org>-remote-<user>"
    return [
        f"Run: `curl -fsSL {setup_url} | bash -s -- --host {shlex.quote(remote_host)} --user {shlex.quote(remote_user)}{org_arg}`",
        "That helper creates a local SSH key and wrapper. When it prints the key, reply with `/ssh-key <public key>`; ArcLink will bind it to your Unix user and install it with Tailscale-only SSH restrictions.",
        f"Use the generated `{wrapper_name}` wrapper, not your local `hermes` command.",
        f"Remote SSH target after key install: {remote_user}@{remote_host}",
    ]


hermes_home = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes")).expanduser()
state_dir = hermes_home / "state"
access = load_json(state_dir / "arclink-web-access.json")
managed = load_json(state_dir / "arclink-vault-reconciler.json")
identity = load_json(state_dir / "arclink-identity-context.json")
home = home_root(access)
vault = vault_root(home)

lines = ["ArcLink resources:", "", "Web access:"]
dashboard_url = clean(access.get("dashboard_url"))
code_url = clean(access.get("code_url"))
username = clean(access.get("username") or access.get("unix_user"), 80)
if dashboard_url:
    lines.append(f"- Hermes dashboard: {dashboard_url}")
if username:
    lines.append(f"- Dashboard username: {username}")
if code_url:
    lines.append(f"- Code workspace: {code_url}")
if home:
    lines.append(f"- Workspace root: {home}")
lines.append(f"- ArcLink vault: {vault}")
lines.extend(
    [
        "",
        "Host helper:",
        "- Remote shell helper on the host: ~/.local/bin/arclink-agent-hermes",
        "",
        "Backups:",
        "- Private Hermes-home backup: run ~/.local/bin/arclink-agent-configure-backup to set up this agent's separate private GitHub repo and read/write deploy key.",
        "- Do not reuse the ArcLink code-push deploy key or shared arclink-priv backup key for your agent backup.",
        "",
        "Shared ArcLink links:",
    ]
)
lines.extend(f"- {line}" for line in shared_lines(managed, access, home))
remote = remote_lines(access, identity)
if remote:
    lines.extend(["", "Optional remote agent CLI from your own machine:"])
    lines.extend(f"- {line}" for line in remote)
lines.extend(
    [
        "",
        "Credentials and passwords are intentionally omitted from this resource reference.",
    ]
)
print("\n".join(lines).strip())
PY
