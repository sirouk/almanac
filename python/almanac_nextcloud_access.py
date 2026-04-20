#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from almanac_control import Config, config_env_value, safe_slug


NEXTCLOUD_SHARED_GROUP = "almanac-users"


def _nextcloud_enabled() -> bool:
    return config_env_value("ENABLE_NEXTCLOUD", "0").strip() == "1"


def _nextcloud_app_container_name() -> str:
    almanac_name = config_env_value("ALMANAC_NAME", "almanac").strip() or "almanac"
    return f"{almanac_name}-nextcloud-app"


def _compose_command(compose_file: Path) -> list[str] | None:
    podman_compose = shutil.which("podman-compose")
    if podman_compose:
        return [podman_compose, "-f", str(compose_file)]

    podman_bin = shutil.which("podman")
    if not podman_bin:
        return None

    result = subprocess.run(
        [podman_bin, "compose", "version"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return [podman_bin, "compose", "-f", str(compose_file)]
    return None


def _runtime_exec_base(cfg: Config, *, extra_env: dict[str, str] | None = None) -> list[str]:
    env_items = extra_env or {}
    podman_bin = shutil.which("podman")
    if podman_bin:
        cmd = ["runuser", "-u", cfg.almanac_user, "--", podman_bin, "exec"]
        for key, value in env_items.items():
            cmd.extend(["-e", f"{key}={value}"])
        cmd.extend(["-u", "33:33", _nextcloud_app_container_name()])
        return cmd

    compose_file = cfg.repo_dir / "compose" / "nextcloud-compose.yml"
    compose_cmd = _compose_command(compose_file)
    if compose_cmd is None:
        raise RuntimeError("Nextcloud runtime is unavailable: no podman or compose runtime found")

    cmd = ["runuser", "-u", cfg.almanac_user, "--", *compose_cmd, "exec", "-T"]
    for key, value in env_items.items():
        cmd.extend(["-e", f"{key}={value}"])
    cmd.extend(["-u", "33:33", "app"])
    return cmd


def _result_text(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or result.stdout or "").strip()


def _runtime_cwd(cfg: Config) -> Path:
    for candidate in (cfg.almanac_home, cfg.repo_dir, Path("/")):
        if candidate.exists():
            return candidate
    return Path("/")


def _nextcloud_occ(
    cfg: Config,
    *args: str,
    extra_env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [
            *_runtime_exec_base(cfg, extra_env=extra_env),
            "php",
            "/var/www/html/occ",
            *args,
        ],
        env=dict(os.environ),
        text=True,
        capture_output=True,
        check=False,
        cwd=str(_runtime_cwd(cfg)),
    )
    if check and result.returncode != 0:
        detail = _result_text(result) or f"exit {result.returncode}"
        raise RuntimeError(f"Nextcloud command failed ({' '.join(args)}): {detail}")
    return result


def _normalized_username(raw_username: str) -> str:
    username = safe_slug(raw_username, fallback="").strip()
    if not username:
        raise ValueError("Nextcloud username cannot be blank")
    return username


def _validated_password(raw_password: str) -> str:
    password = str(raw_password)
    if not password:
        raise ValueError("Nextcloud password cannot be blank")
    if "\n" in password or "\r" in password:
        raise ValueError("Nextcloud password cannot contain newlines")
    return password


def _normalized_display_name(raw_display_name: str, *, fallback: str) -> str:
    cleaned = " ".join(str(raw_display_name or "").strip().split())
    return cleaned or fallback


def sync_nextcloud_user_access(
    cfg: Config,
    *,
    username: str,
    password: str,
    display_name: str = "",
) -> dict[str, Any]:
    if not _nextcloud_enabled():
        return {"enabled": False, "synced": False, "skipped": "disabled"}

    nextcloud_username = _normalized_username(username)
    nextcloud_password = _validated_password(password)
    nextcloud_display_name = _normalized_display_name(display_name, fallback=nextcloud_username)

    _nextcloud_occ(cfg, "status", "--output=json")

    user_info = _nextcloud_occ(
        cfg,
        "user:info",
        nextcloud_username,
        "--output=json",
        check=False,
    )
    exists = user_info.returncode == 0

    if exists:
        _nextcloud_occ(
            cfg,
            "user:resetpassword",
            "--password-from-env",
            "--no-interaction",
            nextcloud_username,
            extra_env={"OC_PASS": nextcloud_password},
        )
    else:
        _nextcloud_occ(
            cfg,
            "user:add",
            "--password-from-env",
            "--no-interaction",
            f"--display-name={nextcloud_display_name}",
            "-g",
            NEXTCLOUD_SHARED_GROUP,
            nextcloud_username,
            extra_env={"OC_PASS": nextcloud_password},
        )

    return {
        "enabled": True,
        "synced": True,
        "username": nextcloud_username,
        "display_name": nextcloud_display_name,
        "created": not exists,
        "group": NEXTCLOUD_SHARED_GROUP,
    }


def delete_nextcloud_user_access(
    cfg: Config,
    *,
    username: str,
) -> dict[str, Any]:
    if not _nextcloud_enabled():
        return {"enabled": False, "deleted": False, "skipped": "disabled"}

    nextcloud_username = _normalized_username(username)
    _nextcloud_occ(cfg, "status", "--output=json")

    user_info = _nextcloud_occ(
        cfg,
        "user:info",
        nextcloud_username,
        "--output=json",
        check=False,
    )
    exists = user_info.returncode == 0
    if not exists:
        return {
            "enabled": True,
            "deleted": False,
            "exists": False,
            "username": nextcloud_username,
        }

    _nextcloud_occ(cfg, "user:delete", nextcloud_username)
    return {
        "enabled": True,
        "deleted": True,
        "exists": True,
        "username": nextcloud_username,
    }
