#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import pwd
import secrets
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from almanac_control import Config, safe_slug, utc_now_iso


ACCESS_STATE_FILENAME = "almanac-web-access.json"
TAILSCALE_RETRY_MARKERS = (
    "etag mismatch",
    "another client is changing the serve config",
    "preconditions failed",
)


def access_state_path(hermes_home: Path) -> Path:
    return hermes_home / "state" / ACCESS_STATE_FILENAME


def load_access_state(hermes_home: Path) -> dict[str, Any]:
    path = access_state_path(hermes_home)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def access_username(unix_user: str) -> str:
    return safe_slug(unix_user, fallback="agent")


def access_url_slug(unix_user: str) -> str:
    return access_username(unix_user).replace("_", "-")


def _write_access_state(path: Path, payload: dict[str, Any], *, uid: int, gid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        os.chown(path, uid, gid)
        path.chmod(0o600)
    except OSError:
        pass


def _owner_ids(unix_user: str) -> tuple[int, int]:
    try:
        passwd = pwd.getpwnam(unix_user)
        return passwd.pw_uid, passwd.pw_gid
    except KeyError:
        return os.getuid(), os.getgid()


def save_access_state(hermes_home: Path, payload: dict[str, Any], *, unix_user: str) -> None:
    uid, gid = _owner_ids(unix_user)
    _write_access_state(access_state_path(hermes_home), payload, uid=uid, gid=gid)


def _used_ports(conn, *, current_agent_id: str) -> set[int]:
    ports: set[int] = set()
    rows = conn.execute(
        """
        SELECT agent_id, hermes_home
        FROM agents
        WHERE role = 'user' AND status = 'active'
        """
    ).fetchall()
    for row in rows:
        agent_id = str(row["agent_id"] or "")
        if not agent_id or agent_id == current_agent_id:
            continue
        state = load_access_state(Path(str(row["hermes_home"] or "")))
        for key in ("dashboard_backend_port", "dashboard_proxy_port", "code_port"):
            try:
                value = int(state.get(key) or 0)
            except (TypeError, ValueError):
                value = 0
            if value > 0:
                ports.add(value)
    return ports


def _listening_ports() -> set[int]:
    result = subprocess.run(
        ["ss", "-ltnH"],
        text=True,
        capture_output=True,
        check=False,
    )
    ports: set[int] = set()
    if result.returncode != 0:
        return ports
    for raw_line in result.stdout.splitlines():
        parts = raw_line.split()
        if len(parts) < 4:
            continue
        local = parts[3]
        _, _, tail = local.rpartition(":")
        try:
            ports.add(int(tail))
        except ValueError:
            continue
    return ports


def _preserve_or_allocate_port(
    *,
    existing: Any,
    reserved_other: set[int],
    reserved_now: set[int],
    base: int,
    span: int,
    slot: int,
) -> int:
    try:
        existing_port = int(existing or 0)
    except (TypeError, ValueError):
        existing_port = 0
    if existing_port > 0 and existing_port not in reserved_other:
        reserved_now.add(existing_port)
        return existing_port

    for offset in range(span):
        candidate = base + ((slot + offset) % span)
        if candidate < 1024 or candidate > 65535:
            continue
        if candidate in reserved_other or candidate in reserved_now:
            continue
        reserved_now.add(candidate)
        return candidate
    raise RuntimeError(f"no free port available in range starting at {base} with span {span}")


def ensure_web_runtime(cfg: Config) -> None:
    python_bin = cfg.runtime_dir / "hermes-venv" / "bin" / "python3"
    repo_dir = cfg.runtime_dir / "hermes-agent-src"
    web_dir = repo_dir / "web"
    source_dist_dir = repo_dir / "hermes_cli" / "web_dist"
    dist_index = source_dist_dir / "index.html"
    if not python_bin.exists():
        raise RuntimeError(f"missing shared Hermes runtime at {python_bin}")
    probe = subprocess.run(
        [
            str(python_bin),
            "-c",
            "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('fastapi') and importlib.util.find_spec('uvicorn') else 1)",
        ],
        check=False,
    )
    if probe.returncode != 0:
        if not shutil_which("uv"):
            raise RuntimeError("uv is required to install Hermes dashboard web dependencies")
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python_bin),
                f"{repo_dir}[cli,mcp,messaging,cron,web]",
            ],
            check=True,
        )
    if not dist_index.exists():
        npm_bin = shutil_which("npm")
        if not npm_bin:
            raise RuntimeError("Hermes dashboard frontend is not built and npm is unavailable to build it")
        subprocess.run([npm_bin, "ci", "--no-audit", "--no-fund"], cwd=web_dir, check=True)
        subprocess.run([npm_bin, "run", "build"], cwd=web_dir, check=True)
    if not dist_index.exists():
        raise RuntimeError(f"Hermes dashboard frontend is missing at {dist_index}")
    package_dir_result = subprocess.run(
        [
            str(python_bin),
            "-c",
            "from pathlib import Path; import hermes_cli; print(Path(hermes_cli.__file__).resolve().parent)",
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    package_dir = Path(package_dir_result.stdout.strip())
    installed_dist_dir = package_dir / "web_dist"
    if installed_dist_dir.resolve() != source_dist_dir.resolve():
        if installed_dist_dir.exists():
            shutil.rmtree(installed_dist_dir)
        shutil.copytree(source_dist_dir, installed_dist_dir)
    installed_index = installed_dist_dir / "index.html"
    if not installed_index.exists():
        raise RuntimeError(f"Hermes dashboard frontend is missing from installed package at {installed_index}")


def detect_tailscale_dns_name() -> str:
    if not shutil_which("tailscale"):
        return ""
    result = subprocess.run(
        ["tailscale", "status", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return ""
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return ""
    return str((data.get("Self") or {}).get("DNSName") or "").rstrip(".")


def _tailscale_path(label: str) -> str:
    cleaned = safe_slug(label, fallback="agent")
    return f"/{cleaned}"


def _tailscale_url(host: str, label: str) -> str:
    return f"https://{host}{_tailscale_path(label)}/"


def _run_tailscale_serve(*args: str) -> None:
    last_error = ""
    for _ in range(5):
        result = subprocess.run(
            ["tailscale", "serve", *args],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return
        combined = f"{result.stdout}\n{result.stderr}".strip()
        normalized = combined.lower()
        if any(marker in normalized for marker in TAILSCALE_RETRY_MARKERS):
            last_error = combined
            time.sleep(1)
            continue
        raise RuntimeError(combined or "tailscale serve failed")
    raise RuntimeError(last_error or "tailscale serve failed after retries")


def publish_tailscale_https(access: dict[str, Any]) -> dict[str, Any]:
    dashboard_port = int(access["dashboard_proxy_port"])
    code_port = int(access["code_port"])
    dashboard_label = str(access.get("dashboard_label") or "agent-dashboard")
    code_label = str(access.get("code_label") or "agent-code")
    access["dashboard_path"] = f"{_tailscale_path(dashboard_label)}/"
    access["code_path"] = f"{_tailscale_path(code_label)}/"
    for port in (dashboard_port, code_port):
        try:
            _run_tailscale_serve(f"--https={port}", "off")
        except Exception:
            pass
    _run_tailscale_serve(
        "--bg",
        "--yes",
        "--https=443",
        f"--set-path={_tailscale_path(dashboard_label)}",
        f"http://127.0.0.1:{dashboard_port}",
    )
    _run_tailscale_serve(
        "--bg",
        "--yes",
        "--https=443",
        f"--set-path={_tailscale_path(code_label)}",
        f"http://127.0.0.1:{code_port}",
    )
    dns_name = detect_tailscale_dns_name()
    if dns_name:
        access["tailscale_host"] = dns_name
        access["dashboard_url"] = _tailscale_url(dns_name, dashboard_label)
        access["code_url"] = _tailscale_url(dns_name, code_label)
    return access


def clear_tailscale_https(hermes_home: Path) -> None:
    state = load_access_state(hermes_home)
    if not state or not shutil_which("tailscale"):
        return
    for key in ("dashboard_label", "code_label"):
        label = str(state.get(key) or "").strip()
        if not label:
            continue
        try:
            _run_tailscale_serve("--https=443", f"--set-path={_tailscale_path(label)}", "off")
        except Exception:
            continue
    for key in ("dashboard_proxy_port", "code_port"):
        try:
            port = int(state.get(key) or 0)
        except (TypeError, ValueError):
            port = 0
        if port <= 0:
            continue
        try:
            _run_tailscale_serve(f"--https={port}", "off")
        except Exception:
            continue


def wait_for_http(
    url: str,
    *,
    timeout_seconds: int = 120,
    expected_statuses: set[int] | None = None,
    username: str = "",
    password: str = "",
) -> None:
    expected = expected_statuses or {200}
    deadline = time.time() + timeout_seconds
    headers: dict[str, str] = {}
    if username or password:
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    request = urllib.request.Request(url, headers=headers)
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status in expected:
                    return
        except urllib.error.HTTPError as exc:
            if exc.code in expected:
                return
        except Exception:
            pass
        time.sleep(2)
    expected_text = ", ".join(str(item) for item in sorted(expected))
    raise RuntimeError(f"timed out waiting for {url} to return one of: {expected_text}")


def ensure_access_state(
    conn,
    cfg: Config,
    *,
    agent_id: str,
    unix_user: str,
    hermes_home: Path,
    uid: int,
) -> dict[str, Any]:
    owner_uid, owner_gid = _owner_ids(unix_user)
    state_path = access_state_path(hermes_home)
    existing = load_access_state(hermes_home)
    reserved_other = _used_ports(conn, current_agent_id=agent_id)
    reserved_now = set(_listening_ports())
    reserved_now.difference_update(
        {
            int(existing.get(key) or 0)
            for key in ("dashboard_backend_port", "dashboard_proxy_port", "code_port")
            if str(existing.get(key) or "").strip()
        }
    )
    slot = uid % max(cfg.agent_port_slot_span, 100)
    username = str(existing.get("username") or access_username(unix_user))
    url_slug = str(existing.get("url_slug") or access_url_slug(unix_user))
    dashboard_label = str(existing.get("dashboard_label") or f"agent-{url_slug}-dash")
    code_label = str(existing.get("code_label") or f"agent-{url_slug}-code")
    dashboard_path = f"{_tailscale_path(dashboard_label)}/"
    code_path = f"{_tailscale_path(code_label)}/"
    password = str(existing.get("password") or secrets.token_urlsafe(18))
    dashboard_backend_port = _preserve_or_allocate_port(
        existing=existing.get("dashboard_backend_port"),
        reserved_other=reserved_other,
        reserved_now=reserved_now,
        base=cfg.agent_dashboard_backend_port_base,
        span=cfg.agent_port_slot_span,
        slot=slot,
    )
    dashboard_proxy_port = _preserve_or_allocate_port(
        existing=existing.get("dashboard_proxy_port"),
        reserved_other=reserved_other,
        reserved_now=reserved_now,
        base=cfg.agent_dashboard_proxy_port_base,
        span=cfg.agent_port_slot_span,
        slot=slot,
    )
    code_port = _preserve_or_allocate_port(
        existing=existing.get("code_port"),
        reserved_other=reserved_other,
        reserved_now=reserved_now,
        base=cfg.agent_code_port_base,
        span=cfg.agent_port_slot_span,
        slot=slot,
    )
    tailscale_host = str(existing.get("tailscale_host") or detect_tailscale_dns_name())
    payload = {
        "agent_id": agent_id,
        "unix_user": unix_user,
        "username": username,
        "url_slug": url_slug,
        "password": password,
        "dashboard_backend_port": dashboard_backend_port,
        "dashboard_proxy_port": dashboard_proxy_port,
        "code_port": code_port,
        "dashboard_local_url": f"http://127.0.0.1:{dashboard_proxy_port}/",
        "code_local_url": f"http://127.0.0.1:{code_port}/",
        "dashboard_url": f"http://127.0.0.1:{dashboard_proxy_port}/",
        "code_url": f"http://127.0.0.1:{code_port}/",
        "tailscale_host": tailscale_host,
        "dashboard_label": dashboard_label,
        "code_label": code_label,
        "dashboard_path": dashboard_path,
        "code_path": code_path,
        "code_container_name": f"almanac-agent-code-{safe_slug(agent_id, fallback='agent')}",
        "code_server_image": cfg.agent_code_server_image,
        "updated_at": utc_now_iso(),
    }
    if cfg.agent_enable_tailscale_serve and tailscale_host:
        payload["dashboard_url"] = _tailscale_url(tailscale_host, dashboard_label)
        payload["code_url"] = _tailscale_url(tailscale_host, code_label)
    _write_access_state(state_path, payload, uid=owner_uid, gid=owner_gid)
    return payload


def shutil_which(program: str) -> str:
    path = os.environ.get("PATH", "")
    for directory in path.split(os.pathsep):
        if not directory:
            continue
        candidate = Path(directory) / program
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return ""
