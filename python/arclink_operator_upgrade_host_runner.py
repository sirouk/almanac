#!/usr/bin/env python3
"""Host-side executor for Raven queued operator upgrades.

The Docker broker authenticates requests and writes typed JSON into private
state. This runner is installed as a host systemd oneshot/timer and executes the
same canonical host upgrade flow an operator would run manually.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shlex
import stat
import subprocess
import time
from pathlib import Path
from typing import Any


HOST_RUNNER_SCHEMA_VERSION = 1
HOST_RUNNER_RESULT_GRACE_SECONDS = 30
QUEUE_RETENTION_SECONDS = 7 * 24 * 60 * 60
QUEUE_RETENTION_MAX_FILES = 2048
SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")
REQUEST_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{7,80}$")
ALLOWED_PIN_COMPONENTS = {"hermes-agent", "qmd", "nextcloud", "postgres", "redis", "nvm", "node"}
PIN_UPGRADE_FLAGS = {
    "git-commit": "--ref",
    "git-tag": "--tag",
    "container-image": "--tag",
    "npm": "--version",
    "nvm-version": "--version",
    "release-asset": "--version",
}
UPSTREAM_ENV_KEYS = (
    "ARCLINK_UPSTREAM_REPO_URL",
    "ARCLINK_UPSTREAM_BRANCH",
    "ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED",
    "ARCLINK_UPSTREAM_DEPLOY_KEY_USER",
    "ARCLINK_UPSTREAM_DEPLOY_KEY_PATH",
    "ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE",
)
# Upstream env keys that name a host filesystem path which deploy.sh would read
# as ROOT. These must be confined to private state exactly as the broker confines
# them (arclink_operator_upgrade_broker._require_private_upstream_path).
UPSTREAM_PRIVATE_PATH_ENV_KEYS = {
    "ARCLINK_UPSTREAM_DEPLOY_KEY_PATH",
    "ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE",
}
UPSTREAM_DEPLOY_KEY_ENABLED_DISABLED = {"", "0", "false", "no", "off"}
# deploy.sh's compiled-in canonical upstream (bin/deploy.sh canonical_arclink_upstream_repo_url).
# The host runner keeps an independent copy of the SAME value so that, even when no host
# operator env names an upstream, there is still a host-immutable authority to (a) accept the
# legitimate broker upgrade against and (b) PIN deploy.sh to -- never letting it derive the
# upstream from the arclink-writable git origin remote.
CANONICAL_UPSTREAM_REPO_URL = "https://github.com/sirouk/arclink.git"
BASE_CHILD_ENV_KEYS = (
    "HOME",
    "PATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TERM",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
)
OPTIONAL_CHILD_ENV_KEYS = (
    "ARCLINK_DOCKER_BINARY",
    "ARCLINK_DOCKER_IMAGE",
    "ARCLINK_DOCKER_NETWORK",
    "ARCLINK_DOCKER_UID",
    "ARCLINK_DOCKER_GID",
    "ARCLINK_DOCKER_SOCKET_GID",
    "ARCLINK_STATE_ROOT_BASE",
    "RUNTIME_DIR",
)
SCRIPT_READ_BITS = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
SCRIPT_EXEC_BITS = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH


def _repo_dir() -> Path:
    configured = str(os.environ.get("ARCLINK_OPERATOR_UPGRADE_HOST_REPO_DIR") or "").strip()
    if configured:
        path = Path(configured).resolve(strict=False)
    else:
        path = Path(__file__).resolve().parents[1]
    if not path.is_absolute():
        raise ValueError("operator upgrade host repo path must be absolute")
    return path


def _priv_dir(repo_dir: Path) -> Path:
    configured = str(os.environ.get("ARCLINK_OPERATOR_UPGRADE_HOST_PRIV_DIR") or "").strip()
    path = Path(configured).resolve(strict=False) if configured else (repo_dir / "arclink-priv").resolve(strict=False)
    if not path.is_absolute() or path.name != "arclink-priv":
        raise ValueError("operator upgrade host private-state path must be an absolute arclink-priv path")
    return path


def _queue_root(priv_dir: Path) -> Path:
    configured = str(os.environ.get("ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR") or "").strip()
    state_root = (priv_dir / "state").resolve(strict=False)
    root = Path(configured).resolve(strict=False) if configured else state_root / "operator-upgrade-host-runner"
    if not root.is_absolute():
        raise ValueError("operator upgrade host runner queue path must be absolute")
    try:
        root.relative_to(state_root)
    except ValueError:
        raise ValueError("operator upgrade host runner queue path must stay under private state") from None
    return root


def _single_line(value: Any, *, label: str, allow_blank: bool = True, max_chars: int = 512) -> str:
    clean = str(value or "").strip()
    if not clean and allow_blank:
        return ""
    if not clean:
        raise ValueError(f"operator upgrade host runner {label} is required")
    if "\n" in clean or "\r" in clean or "\x00" in clean:
        raise ValueError(f"operator upgrade host runner {label} must be a single line")
    if len(clean) > max_chars:
        raise ValueError(f"operator upgrade host runner {label} is too long")
    return clean


def _require_child_path(value: str, *, root: Path, label: str, mkdir_parent: bool = False) -> Path:
    try:
        path = Path(value).resolve(strict=False)
    except OSError:
        raise ValueError(f"operator upgrade host runner {label} path is not valid") from None
    root = root.resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError(f"operator upgrade host runner {label} must stay under {root}") from None
    if mkdir_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _require_repo_script(repo_dir: Path, relative: str) -> Path:
    rel_path = Path(relative)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise ValueError("operator upgrade host runner script path is not allowlisted")
    path = repo_dir / rel_path
    current = repo_dir
    item_stat: os.stat_result | None = None
    for index, part in enumerate(rel_path.parts):
        current = current / part
        try:
            item_stat = current.lstat()
        except OSError:
            raise ValueError(f"operator upgrade host runner script is missing: {relative}") from None
        if stat.S_ISLNK(item_stat.st_mode):
            raise ValueError(f"operator upgrade host runner script must not be a symlink: {relative}")
        if index < len(rel_path.parts) - 1 and not stat.S_ISDIR(item_stat.st_mode):
            raise ValueError(f"operator upgrade host runner script parent is not a directory: {relative}")
    if item_stat is None or not stat.S_ISREG(item_stat.st_mode):
        raise ValueError(f"operator upgrade host runner script is not a regular file: {relative}")
    if not item_stat.st_mode & SCRIPT_READ_BITS:
        raise ValueError(f"operator upgrade host runner script is not readable: {relative}")
    if not item_stat.st_mode & SCRIPT_EXEC_BITS:
        raise ValueError(f"operator upgrade host runner script is not executable: {relative}")
    try:
        current.resolve(strict=True).relative_to(repo_dir.resolve(strict=True))
    except (OSError, ValueError):
        raise ValueError("operator upgrade host runner script escaped the host repo") from None
    return path


def _require_private_upstream_path(value: str, *, label: str, private_dir: Path) -> str:
    """Confine an upstream host path to private state with no symlink components.

    This independently mirrors arclink_operator_upgrade_broker._require_private_upstream_path
    so a queue file written directly by the arclink service user (bypassing the broker
    HMAC) still cannot point deploy.sh -- running as ROOT -- at a key/known_hosts file
    outside private state or through a symlink.
    """
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"operator upgrade host runner upstream {label} must be an absolute private-state path")
    private_root = private_dir.resolve(strict=False)
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(private_root)
    except ValueError:
        raise ValueError(f"operator upgrade host runner upstream {label} must stay under private state") from None
    try:
        rel_path = path.relative_to(private_dir)
    except ValueError:
        raise ValueError(f"operator upgrade host runner upstream {label} must stay under private state") from None
    try:
        root_stat = private_dir.lstat()
    except OSError:
        raise ValueError("operator upgrade host runner upstream private state root is unavailable") from None
    if stat.S_ISLNK(root_stat.st_mode):
        raise ValueError("operator upgrade host runner upstream private state root must not be a symlink")
    current = private_dir
    for index, part in enumerate(rel_path.parts):
        if part in ("", ".") or part == "..":
            raise ValueError(f"operator upgrade host runner upstream {label} must stay under private state")
        current = current / part
        try:
            item_stat = current.lstat()
        except OSError:
            if index < len(rel_path.parts) - 1:
                raise ValueError(f"operator upgrade host runner upstream {label} parent path is unavailable") from None
            break
        if stat.S_ISLNK(item_stat.st_mode):
            raise ValueError(f"operator upgrade host runner upstream {label} must not be a symlink")
        if index < len(rel_path.parts) - 1 and not stat.S_ISDIR(item_stat.st_mode):
            raise ValueError(f"operator upgrade host runner upstream {label} parent is not a directory")
    return value


def _trusted_deploy_key_uids() -> set[int]:
    """UIDs allowed to OWN an enabled upstream deploy key.

    Root (0) and the host runner's own effective uid (it runs as root via the systemd
    oneshot) are always trusted. An operator may extend the set with a HOST-IMMUTABLE
    process env. The arclink service account is deliberately NOT in this set, so a key the
    unprivileged caller plants in (arclink-writable) private state is rejected.
    """
    trusted: set[int] = {0}
    try:
        trusted.add(os.geteuid())
    except AttributeError:  # pragma: no cover - non-POSIX
        pass
    configured = str(os.environ.get("ARCLINK_OPERATOR_UPGRADE_HOST_DEPLOY_KEY_TRUSTED_UIDS") or "")
    for chunk in re.split(r"[,\s]+", configured):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            trusted.add(int(chunk))
        except ValueError:
            continue
    return trusted


def _require_existing_trusted_deploy_key(value: str) -> None:
    """Require an enabled upstream deploy key to EXIST as a trusted-owned regular file.

    The private-state dir is arclink-writable, so DEPLOY_KEY_ENABLED + a confined path is not
    enough on its own: an attacker could plant a key there. This requires the leaf to (a) exist,
    (b) be a regular file (not a symlink/dir/dev node), (c) be owned by a trusted uid (root /
    the runner's own uid / an operator-configured uid -- never the arclink account), and (d)
    not be group/world writable. Defense-in-depth once the URL is pinned to the canonical
    upstream (an attacker key then only authenticates to the REAL public repo), but tightened
    regardless to deny an arclink-plantable key and reject a non-existent path outright.
    """
    path = Path(value)
    try:
        leaf_stat = path.lstat()
    except OSError:
        raise ValueError("operator upgrade host runner upstream deploy key file does not exist") from None
    if stat.S_ISLNK(leaf_stat.st_mode):
        raise ValueError("operator upgrade host runner upstream deploy key must not be a symlink")
    if not stat.S_ISREG(leaf_stat.st_mode):
        raise ValueError("operator upgrade host runner upstream deploy key is not a regular file")
    if leaf_stat.st_uid not in _trusted_deploy_key_uids():
        raise ValueError(
            "operator upgrade host runner upstream deploy key is not owned by a trusted account"
        )
    if leaf_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ValueError("operator upgrade host runner upstream deploy key is group/world writable")


def _normalize_repo_url(value: str) -> str:
    """Canonicalize a git remote URL to ``host/owner/repo`` (lowercased, no scheme,
    no credentials, no ``.git``) so the SSH and HTTPS forms of the SAME repository
    compare equal. The allowlist's intent is "this repository", not a byte-exact URL
    string: the configured/queued upstream is the SSH form (deploy key) while the
    compiled-in canonical is the HTTPS form, and the almanac->arclink rename left them
    in different string forms -- without canonicalization a legitimate upgrade is
    wrongly refused with "upstream repo URL is not allowlisted". This stays SECURE:
    a different host, owner, or repo still produces a different normalized value and
    never matches (verified by tests).
    """
    clean = str(value or "").strip()
    if not clean:
        return ""
    for scheme in ("https://", "http://", "ssh://", "git+ssh://", "git://"):
        if clean.lower().startswith(scheme):
            clean = clean[len(scheme):]
            break
    # Drop any "user@" / "user:pass@" credential prefix (e.g. git@github.com:...).
    if "@" in clean:
        clean = clean.rsplit("@", 1)[1]
    # scp-style "host:owner/repo" -> "host/owner/repo", but preserve an explicit
    # "host:port" (a colon followed by a digit).
    if ":" in clean:
        host, _, rest = clean.partition(":")
        if not rest[:1].isdigit():
            clean = f"{host}/{rest}"
    clean = clean.rstrip("/").lower()
    if clean.endswith(".git"):
        clean = clean[:-4]
    return clean.rstrip("/")


def _allowlisted_upstream_repo_urls() -> set[str]:
    """Resolve the canonical upstream repo URL(s) from HOST-IMMUTABLE sources only.

    The queue writer (arclink service user) MUST NOT be able to influence any of these.
    Earlier code derived an allowed URL from `git -C <repo> remote get-url origin`, but the
    arclink user OWNS the checkout and can rewrite .git/config to poison `origin`; that source
    is therefore REMOVED here. The only authorities trusted now are ones the unprivileged caller
    cannot write:
      * the host runner's ARCLINK_OPERATOR_UPGRADE_HOST_UPSTREAM_REPO_URL_ALLOWLIST process env,
      * the host runner's ARCLINK_UPSTREAM_REPO_URL process env (set in the systemd unit), and
      * the compiled-in canonical default (mirrors deploy.sh's own compiled-in default).
    The compiled-in default guarantees the allowlist is never empty, so a queued override is only
    ever accepted when it matches the real upstream and the legitimate broker upgrade still passes.
    Anything the queue file requests must match one of these, normalized.
    """
    allow: set[str] = set()
    explicit = str(os.environ.get("ARCLINK_OPERATOR_UPGRADE_HOST_UPSTREAM_REPO_URL_ALLOWLIST") or "")
    for chunk in re.split(r"[,\n]", explicit):
        normalized = _normalize_repo_url(chunk)
        if normalized:
            allow.add(normalized)
    host_configured = _normalize_repo_url(os.environ.get("ARCLINK_UPSTREAM_REPO_URL") or "")
    if host_configured:
        allow.add(host_configured)
    canonical = _normalize_repo_url(CANONICAL_UPSTREAM_REPO_URL)
    if canonical:
        allow.add(canonical)
    return allow


def _host_pinned_upstream_repo_url() -> str:
    """The single HOST-IMMUTABLE upstream URL deploy.sh must be PINNED to.

    When a request omits ARCLINK_UPSTREAM_REPO_URL we do NOT let deploy.sh fall through to its
    own default (which reads the arclink-writable git origin remote). Instead the host runner
    pins this value into the child env. Precedence is host-immutable only: the host runner's
    ARCLINK_UPSTREAM_REPO_URL process env (systemd unit), else the compiled-in canonical default.
    The explicit allowlist env is deliberately NOT used for pinning because it may enumerate
    several URLs with no single authoritative choice.
    """
    host_configured = str(os.environ.get("ARCLINK_UPSTREAM_REPO_URL") or "").strip()
    if host_configured:
        return host_configured
    return CANONICAL_UPSTREAM_REPO_URL


def _validated_upstream(upstream: Any, *, priv_dir: Path) -> dict[str, str]:
    """Independently re-validate the queue file's upstream env before it reaches deploy.sh.

    deploy.sh runs as ROOT in run_operator_upgrade mode and will git-clone+run the
    ARCLINK_UPSTREAM_REPO_URL when DEPLOY_KEY_ENABLED=1. The host runner must therefore
    NOT trust the queued upstream blindly (the old code only passed it through
    _single_line). This load-bearing confinement holds even for a direct queue write
    that never went through the broker HMAC.
    """
    normalized: dict[str, str] = {}
    if not isinstance(upstream, dict):
        return normalized
    for key in UPSTREAM_ENV_KEYS:
        value = _single_line(upstream.get(key), label=key, allow_blank=True, max_chars=4096)
        if not value:
            continue
        if key in UPSTREAM_PRIVATE_PATH_ENV_KEYS:
            value = _require_private_upstream_path(value, label=key, private_dir=priv_dir)
        normalized[key] = value
    repo_url = normalized.get("ARCLINK_UPSTREAM_REPO_URL")
    if repo_url:
        allow = _allowlisted_upstream_repo_urls()
        # `allow` always contains at least the compiled-in canonical default, so it is never
        # empty; a queued URL is honored only when it matches a HOST-IMMUTABLE authority. A
        # poisoned git origin no longer feeds this set.
        if _normalize_repo_url(repo_url) not in allow:
            raise ValueError("operator upgrade host runner upstream repo URL is not allowlisted")
    enabled = str(normalized.get("ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED") or "").strip().lower()
    if enabled not in UPSTREAM_DEPLOY_KEY_ENABLED_DISABLED:
        # An enabled deploy key is the path deploy.sh uses to authenticate the clone as
        # root; only honor it when a confined (private-state, no-symlink) key path is set
        # AND the key file actually exists. The private-state dir is arclink-writable, so an
        # attacker could otherwise toggle DEPLOY_KEY_ENABLED with a path to a key they plant;
        # requiring existence + root/trusted ownership rejects an arclink-plantable key.
        key_path = normalized.get("ARCLINK_UPSTREAM_DEPLOY_KEY_PATH")
        if not key_path:
            raise ValueError(
                "operator upgrade host runner upstream deploy key enabled without a private-state key path"
            )
        _require_existing_trusted_deploy_key(key_path)
    return normalized


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _operator_timeout(request_body: dict[str, Any]) -> int:
    try:
        value = int(str(request_body.get("timeout_seconds") or "").strip())
    except (TypeError, ValueError):
        value = 7200
    return max(30, min(21600, value))


def _request_expiry(request_body: dict[str, Any], *, timeout_seconds: int) -> int:
    raw_created_at = request_body.get("created_at")
    # M1: a queued request MUST carry created_at. A direct queue write that omits
    # it would otherwise never expire (the old "blank -> no-expiry" path). The
    # legitimate broker always stamps created_at (see broker _run_host_runner_request).
    if raw_created_at in (None, ""):
        raise ValueError("operator upgrade host runner created_at is required")
    try:
        created_at = int(str(raw_created_at).strip())
    except (TypeError, ValueError):
        raise ValueError("operator upgrade host runner created_at is invalid") from None
    if created_at <= 0:
        raise ValueError("operator upgrade host runner created_at is invalid")
    wait_seconds = max(30, min(21630, timeout_seconds + HOST_RUNNER_RESULT_GRACE_SECONDS))
    return created_at + wait_seconds


def _container_priv_dir_value(request_body: dict[str, Any]) -> str:
    value = _single_line(request_body.get("container_priv_dir"), label="container_priv_dir", allow_blank=True, max_chars=4096)
    if not value:
        return ""
    path = Path(value)
    if not path.is_absolute() or "arclink-priv" not in path.parts:
        raise ValueError("operator upgrade host runner container_priv_dir is not an ArcLink private-state path")
    return value


def _operator_env(request_body: dict[str, Any], *, repo_dir: Path, priv_dir: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in BASE_CHILD_ENV_KEYS:
        value = _single_line(os.environ.get(key), label=key, allow_blank=True, max_chars=4096)
        if value:
            env[key] = value
    env.setdefault("HOME", "/root")
    env.setdefault("PATH", os.defpath)
    env.update(
        {
            "ARCLINK_DOCKER_MODE": "1",
            "ARCLINK_CONTAINER_RUNTIME": "docker",
            "ARCLINK_COMPONENT_UPGRADE_MODE": "docker",
            "ARCLINK_REPO_DIR": str(repo_dir),
            "ARCLINK_PRIV_DIR": str(priv_dir),
            "ARCLINK_PRIV_CONFIG_DIR": str(priv_dir / "config"),
            "ARCLINK_DOCKER_HOST_REPO_DIR": str(repo_dir),
            "ARCLINK_DOCKER_HOST_PRIV_DIR": str(priv_dir),
            "ARCLINK_DOCKER_CONTAINER_PRIV_DIR": str(request_body.get("container_priv_dir") or priv_dir),
            "STATE_DIR": str(priv_dir / "state"),
            "ARCLINK_CONFIG_FILE": str(priv_dir / "config" / "docker.env"),
        }
    )
    for key in OPTIONAL_CHILD_ENV_KEYS:
        value = _single_line(os.environ.get(key), label=key, allow_blank=True, max_chars=4096)
        if value:
            env[key] = value
    env.setdefault("RUNTIME_DIR", "/opt/arclink/runtime")
    # request_body here is the NORMALIZED request whose "upstream" already passed
    # _validated_upstream (allowlisted repo URL, confined+existing key path). Re-confirm the
    # single-line shape defensively before it reaches root deploy.sh.
    upstream = request_body.get("upstream")
    if isinstance(upstream, dict):
        for key in UPSTREAM_ENV_KEYS:
            value = _single_line(upstream.get(key), label=key, allow_blank=True, max_chars=4096)
            if value:
                env[key] = value
    # PIN the upstream repo URL to a HOST-IMMUTABLE value whenever the request did not carry an
    # (allowlisted) one. Without this, root deploy.sh would derive its default from
    # `git -C <repo> remote get-url origin`, which the arclink service user can poison by
    # rewriting .git/config. Pinning the canonical URL means an omitted-upstream request can
    # never steer the root clone at an attacker remote.
    if not env.get("ARCLINK_UPSTREAM_REPO_URL"):
        env["ARCLINK_UPSTREAM_REPO_URL"] = _host_pinned_upstream_repo_url()
    return env


def _run_logged_command(
    handle: Any,
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    handle.write(f"$ {' '.join(shlex.quote(str(arg)) for arg in args)}\n")
    handle.flush()
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd),
            env=env,
            text=True,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        handle.write(f"\ncommand timed out after {timeout_seconds}s\n")
        handle.flush()
        return subprocess.CompletedProcess(args=args, returncode=124, stdout="", stderr="timeout")
    handle.write(f"\n[exit {result.returncode}]\n")
    handle.flush()
    return result


def _component_upgrade_statuses_from_text(text: str) -> list[str]:
    prefix = "ARCLINK_COMPONENT_UPGRADE_STATUS="
    statuses: list[str] = []
    for line in text.splitlines():
        clean = line.strip()
        if clean.startswith(prefix):
            status = clean[len(prefix) :].strip().lower()
            if status:
                statuses.append(status)
    return statuses


def _pin_upgrade_log_requires_deploy(log_path: Path, *, expected_statuses: int) -> bool:
    try:
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    statuses = _component_upgrade_statuses_from_text(log_text)
    recent = statuses[-expected_statuses:] if expected_statuses > 0 else []
    if len(recent) < expected_statuses:
        return True
    if any(status not in {"noop", "changed", "pushed"} for status in recent):
        return True
    return any(status in {"changed", "pushed"} for status in recent)


def _validated_pin_upgrade(item: dict[str, Any]) -> tuple[str, str, str]:
    component = _single_line(item.get("component"), label="pin upgrade component", allow_blank=False, max_chars=96)
    if not SAFE_COMPONENT_RE.fullmatch(component) or component not in ALLOWED_PIN_COMPONENTS:
        raise ValueError("operator upgrade host runner pin upgrade component is not allowlisted")
    kind = _single_line(item.get("kind"), label=f"{component} pin upgrade kind", allow_blank=False, max_chars=64)
    target = _single_line(item.get("target"), label=f"{component} pin upgrade target", allow_blank=False, max_chars=240)
    flag = PIN_UPGRADE_FLAGS.get(kind)
    if not flag:
        raise ValueError(f"operator upgrade host runner pin upgrade kind is not allowlisted: {kind}")
    return component, flag, target


def _pin_upgrade_command(component_upgrade: Path, item: dict[str, Any]) -> list[str]:
    component, flag, target = _validated_pin_upgrade(item)
    return [str(component_upgrade), component, "apply", flag, target, "--skip-push", "--skip-upgrade"]


def _validate_request(request_body: dict[str, Any], *, repo_dir: Path, priv_dir: Path) -> dict[str, Any]:
    if any(key in request_body for key in ("args", "cmd", "command")):
        raise ValueError("operator upgrade host runner does not accept raw commands")
    schema_version = request_body.get("schema_version")
    if type(schema_version) is not int or schema_version != HOST_RUNNER_SCHEMA_VERSION:
        raise ValueError("operator upgrade host runner request schema is unsupported")
    request_id = _single_line(request_body.get("request_id"), label="request_id", allow_blank=False, max_chars=96)
    if not REQUEST_ID_RE.fullmatch(request_id):
        raise ValueError("operator upgrade host runner request id is invalid")
    operation = _single_line(request_body.get("operation"), label="operation", allow_blank=False, max_chars=64)
    if operation not in {"run_operator_upgrade", "run_pin_upgrade"}:
        raise ValueError("operator upgrade host runner operation is not allowlisted")
    supplied_repo = _single_line(request_body.get("repo_dir"), label="repo_dir", allow_blank=True, max_chars=4096)
    supplied_priv = _single_line(request_body.get("priv_dir"), label="priv_dir", allow_blank=True, max_chars=4096)
    if supplied_repo and Path(supplied_repo).resolve(strict=False) != repo_dir.resolve(strict=False):
        raise ValueError("operator upgrade host runner request repo_dir does not match this host")
    if supplied_priv and Path(supplied_priv).resolve(strict=False) != priv_dir.resolve(strict=False):
        raise ValueError("operator upgrade host runner request priv_dir does not match this host")
    log_root = priv_dir / "state" / "operator-actions"
    log_path = _require_child_path(
        _single_line(request_body.get("log_path"), label="log_path", allow_blank=False, max_chars=4096),
        root=log_root,
        label="operator log",
        mkdir_parent=True,
    )
    timeout_seconds = _operator_timeout(request_body)
    expires_at = _request_expiry(request_body, timeout_seconds=timeout_seconds)
    if expires_at and time.time() > expires_at:
        raise ValueError("operator upgrade host runner request expired before execution")
    normalized: dict[str, Any] = {
        "request_id": request_id,
        "operation": operation,
        "log_path": log_path,
        "timeout_seconds": timeout_seconds,
        "expires_at": expires_at,
        "container_priv_dir": _container_priv_dir_value(request_body),
        "upstream": {},
    }
    normalized["upstream"] = _validated_upstream(
        request_body.get("upstream"), priv_dir=priv_dir
    )
    if operation == "run_pin_upgrade":
        install_items = request_body.get("install_items")
        if not isinstance(install_items, list) or not install_items:
            raise ValueError("operator upgrade host runner pin upgrade request has no install items")
        for item in install_items:
            if not isinstance(item, dict):
                raise ValueError("operator upgrade host runner pin upgrade item must be a JSON object")
            _validated_pin_upgrade(item)  # reject any disallowed item before running a single command
        normalized["install_items"] = install_items
    return normalized


def _run_request(request_body: dict[str, Any], *, repo_dir: Path, priv_dir: Path) -> int:
    request = _validate_request(request_body, repo_dir=repo_dir, priv_dir=priv_dir)
    deploy = _require_repo_script(repo_dir, "deploy.sh")
    component_upgrade = _require_repo_script(repo_dir, "bin/component-upgrade.sh")
    env = _operator_env(request, repo_dir=repo_dir, priv_dir=priv_dir)
    timeout_seconds = int(request["timeout_seconds"])
    log_path = request["log_path"]
    assert isinstance(log_path, Path)
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write("ArcLink host operator upgrade runner executing canonical host upgrade path.\n")
        handle.flush()
        if request["operation"] == "run_operator_upgrade":
            result = _run_logged_command(handle, [str(deploy), "upgrade"], cwd=repo_dir, env=env, timeout_seconds=timeout_seconds)
            return int(result.returncode)
        last_result: subprocess.CompletedProcess[str] | None = None
        install_items = request.get("install_items")
        if not isinstance(install_items, list):
            raise ValueError("operator upgrade host runner pin upgrade request has no install items")
        for item in install_items:
            if not isinstance(item, dict):
                raise ValueError("operator upgrade host runner pin upgrade item must be a JSON object")
            command = _pin_upgrade_command(component_upgrade, item)
            last_result = _run_logged_command(handle, command, cwd=repo_dir, env=env, timeout_seconds=timeout_seconds)
            if last_result.returncode != 0:
                return int(last_result.returncode)
        handle.flush()
        if not _pin_upgrade_log_requires_deploy(log_path, expected_statuses=len(install_items)):
            handle.write("All requested pinned components were already current; skipping deploy upgrade.\n")
            handle.flush()
            return int(last_result.returncode if last_result is not None else 0)
        deploy_env = dict(env)
        deploy_env["ARCLINK_CONTROL_UPGRADE_ALLOW_DIRTY"] = "1"
        handle.write("Applying queued pin changes from the local checkout without pushing upstream.\n")
        handle.flush()
        last_result = _run_logged_command(handle, [str(deploy), "upgrade"], cwd=repo_dir, env=deploy_env, timeout_seconds=timeout_seconds)
        return int(last_result.returncode if last_result is not None else 0)


def _process_request_file(path: Path, *, repo_dir: Path, priv_dir: Path, queue_root: Path) -> None:
    done_dir = queue_root / "processed"
    result: dict[str, Any]
    request_id = path.stem if REQUEST_ID_RE.fullmatch(path.stem) else ""
    result_path: Path | None = None
    try:
        stat_result = path.lstat()
        if stat.S_ISLNK(stat_result.st_mode) or not stat.S_ISREG(stat_result.st_mode):
            raise ValueError(f"operator upgrade host runner refusing non-regular request file {path}")
        request_body = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(request_body, dict):
            raise ValueError("operator upgrade host runner request must be a JSON object")
        body_request_id = _single_line(request_body.get("request_id"), label="request_id", allow_blank=False, max_chars=96)
        if not REQUEST_ID_RE.fullmatch(body_request_id):
            raise ValueError("operator upgrade host runner request id is invalid")
        request_id = body_request_id
        result_path = queue_root / "results" / f"{request_id}.json"
        returncode = _run_request(request_body, repo_dir=repo_dir, priv_dir=priv_dir)
        result = {"ok": True, "request_id": request_id, "returncode": int(returncode), "completed_at": int(time.time())}
    except BaseException as exc:
        result = {
            "ok": False,
            "request_id": request_id or path.stem,
            "error": str(exc),
            "error_class": exc.__class__.__name__,
            "completed_at": int(time.time()),
        }
        if result_path is None and request_id:
            result_path = queue_root / "results" / f"{request_id}.json"
    if result_path is not None:
        _atomic_write_json(result_path, result)
    done_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(path, done_dir / path.name)
    except OSError:
        path.unlink(missing_ok=True)


def _prune_queue_dir(
    path: Path,
    *,
    now: float | None = None,
    max_age_seconds: int = QUEUE_RETENTION_SECONDS,
    max_files: int = QUEUE_RETENTION_MAX_FILES,
) -> None:
    if not path.exists():
        return
    cutoff = (time.time() if now is None else now) - max_age_seconds
    try:
        entries = [(item.lstat().st_mtime, item) for item in path.glob("*.json")]
    except OSError:
        return
    kept: list[tuple[float, Path]] = []
    for item_mtime, item in entries:
        if item_mtime >= cutoff:
            kept.append((item_mtime, item))
            continue
        try:
            item.unlink()
        except OSError:
            pass
    if max_files <= 0 or len(kept) <= max_files:
        return
    for _item_mtime, item in sorted(kept, key=lambda entry: (entry[0], entry[1].name))[: len(kept) - max_files]:
        try:
            item.unlink()
        except OSError:
            pass


def process_once() -> int:
    repo_dir = _repo_dir()
    priv_dir = _priv_dir(repo_dir)
    queue_root = _queue_root(priv_dir)
    pending_dir = queue_root / "pending"
    lock_path = queue_root / "runner.lock"
    pending_dir.mkdir(parents=True, exist_ok=True)
    (queue_root / "results").mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        _prune_queue_dir(queue_root / "results")
        _prune_queue_dir(queue_root / "processed")
        for request_path in sorted(pending_dir.glob("*.json"), key=lambda item: (item.lstat().st_mtime, item.name)):
            _process_request_file(request_path, repo_dir=repo_dir, priv_dir=priv_dir, queue_root=queue_root)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drain ArcLink host operator upgrade requests")
    parser.add_argument("--once", action="store_true", help="drain pending requests once and exit")
    args = parser.parse_args(argv)
    del args
    os.umask(0o077)
    return process_once()


if __name__ == "__main__":
    raise SystemExit(main())
