#!/usr/bin/env python3
"""arclink_pin_upgrade_check - detect upstream upgrades for pinned components
and notify the operator with a digest, throttled per release.

Runs hourly via arclink-curator-refresh.timer (also callable via
`./deploy.sh pin-upgrade-notify` for an on-demand check).

For each managed component declared in config/pins.json:
  1. Resolve the upstream "latest" via bin/component-upgrade.sh <c> check
  2. If upstream != current pin:
     - If no row in pin_upgrade_notifications: insert; will notify
     - If row exists with same target_value: it's the same upgrade we've
       been tracking. For git-commit pins with a discoverable release label,
       target_value is the release version rather than the raw commit hash.
       If notify_count reaches the configured limit, the row is silenced and
       we skip. Otherwise we'll include it in the digest and increment.
     - If row exists but target_value differs: a NEW upgrade target
       appeared (upstream advanced again). Reset notify_count = 0,
       update target_value, include in digest.
  3. If pin advanced past the tracked target (i.e., the operator applied
     the upgrade or bumped to something different), delete the stale row.

After scanning, if any non-silenced component has an upgrade available, build
a single rolled-up digest message and queue it on the operator notification
channel. Only one digest per detector run, regardless of how many components
are included.

Throttle semantics:
  - Operator gets at most the configured number of notifications about the
    same target_value.
    For git-commit pins with a release label, target_value is the release
    version, so commit churn inside the same release does not restart alerts.
    After the final allowed notification, the row is silenced.
  - Silence breaks the moment target_value changes (upstream advanced)
    or the component pin advances past target_value (upgrade applied).
"""
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
PINS_PATH = REPO_ROOT / "config" / "pins.json"
COMPONENT_UPGRADE_SH = REPO_ROOT / "bin" / "component-upgrade.sh"

# Components that have a working upstream-check implementation in
# component-upgrade.sh. installer-url and uv-python kinds are floating by
# design and excluded.
MANAGED_COMPONENTS = (
    "hermes-agent",
    "hermes-docs",
    "code-server",
    "nvm",
    "node",
    "qmd",
    "nextcloud",
    "postgres",
    "redis",
)

DEFAULT_NOTIFY_LIMIT = 1  # max notifications about the same release before silence
GIT_SHA_RE = re.compile(r"^[0-9a-f]{7,64}$", re.IGNORECASE)


@dataclass
class CheckResult:
    component: str
    kind: str
    field: str            # which pins.json field carries the value (ref/tag/version)
    current: str
    target: str           # upstream "latest" - empty if check is informational only
    upgrade_available: bool
    note: str = ""        # human-readable extra context for the digest
    transient_failure: bool = False  # upstream lookup failed; preserve state, don't delete
    current_label: str = ""  # human-readable release label, when discoverable
    target_label: str = ""   # human-readable release label, when discoverable
    repo: str = ""           # upstream repo for git-commit release-label migration


# ---- helpers ---------------------------------------------------------------

def _import_arclink_control():
    """Import arclink_control without circular imports. The detector is
    callable both standalone and from arclink_ctl.py.
    """
    sys.path.insert(0, str(REPO_ROOT / "python"))
    import arclink_control  # noqa: E402  (late import on purpose)
    return arclink_control


def _read_pins() -> dict[str, Any]:
    return json.loads(PINS_PATH.read_text())


def _component_kind(pins: dict[str, Any], component: str) -> str:
    return str(pins.get("components", {}).get(component, {}).get("kind") or "")


def _component_value(pins: dict[str, Any], component: str, field: str) -> str:
    return str(pins.get("components", {}).get(component, {}).get(field) or "")


_GIT_COMMIT_LABEL_CACHE: dict[tuple[str, str], str] = {}


def _github_owner_repo(repo: str) -> str:
    repo = repo.strip()
    match = re.match(r"^https://github\.com/([^/]+/.+?)(?:\.git)?/?$", repo)
    if not match:
        match = re.match(r"^git@github\.com:([^/]+/.+?)(?:\.git)?$", repo)
    if not match:
        return ""
    return match.group(1).strip("/")


def _github_raw_text(repo: str, ref: str, path: str) -> str:
    owner_repo = _github_owner_repo(repo)
    if not owner_repo or not ref or not path:
        return ""
    quoted_ref = quote(ref, safe="")
    quoted_path = "/".join(quote(part, safe="") for part in path.split("/"))
    url = f"https://raw.githubusercontent.com/{owner_repo}/{quoted_ref}/{quoted_path}"
    request = Request(url, headers={"User-Agent": "arclink-pin-upgrade-check"})
    try:
        with urlopen(request, timeout=10) as response:
            return response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeError):
        return ""


def _pyproject_metadata(text: str) -> dict[str, str]:
    if not text.strip():
        return {}
    try:
        import tomllib

        project = tomllib.loads(text).get("project", {})
        version = str(project.get("version") or "").strip()
        name = str(project.get("name") or "").strip()
        return {"name": name, "version": version}
    except Exception:  # noqa: BLE001 - best-effort operator-facing label only
        version_match = re.search(r"(?m)^version\s*=\s*[\"']([^\"']+)[\"']", text)
        name_match = re.search(r"(?m)^name\s*=\s*[\"']([^\"']+)[\"']", text)
        return {
            "name": name_match.group(1).strip() if name_match else "",
            "version": version_match.group(1).strip() if version_match else "",
        }


def _python_assignment(text: str, name: str) -> str:
    match = re.search(rf"(?m)^{re.escape(name)}\s*=\s*[\"']([^\"']+)[\"']", text)
    return match.group(1).strip() if match else ""


def _git_commit_release_label(repo: str, ref: str) -> str:
    """Return a human-readable release label for a git commit when possible.

    Hermes pins are commit-addressed for reproducibility, but operators should
    still see the package release version in the chat digest. GitHub raw files
    are intentionally used instead of a shallow clone so the hourly detector
    stays cheap; failures degrade to the existing short-SHA display.
    """
    repo = repo.strip()
    ref = ref.strip()
    if not repo or not ref:
        return ""
    cache_key = (repo, ref)
    if cache_key in _GIT_COMMIT_LABEL_CACHE:
        return _GIT_COMMIT_LABEL_CACHE[cache_key]

    pyproject = _github_raw_text(repo, ref, "pyproject.toml")
    metadata = _pyproject_metadata(pyproject)
    version = metadata.get("version", "")
    release_date = ""
    if version:
        init_py = _github_raw_text(repo, ref, "hermes_cli/__init__.py")
        release_date = _python_assignment(init_py, "__release_date__")

    if not version:
        label = ""
    else:
        rendered_version = version if version.startswith("v") else f"v{version}"
        label = f"{rendered_version} ({release_date})" if release_date else rendered_version

    _GIT_COMMIT_LABEL_CACHE[cache_key] = label
    return label


def _run_check(component: str) -> str:
    """Run `component-upgrade.sh <c> check` and capture combined stdout/stderr.
    Stderr is folded in so that diagnostic warn lines (`!! could not resolve …`)
    surface in logs alongside the structured pinned/latest/status output.
    """
    try:
        proc = subprocess.run(
            ["bash", str(COMPONENT_UPGRADE_SH), component, "check"],
            capture_output=True, text=True, timeout=60,
        )
        combined = proc.stdout
        if proc.stderr:
            combined = f"{combined}\n{proc.stderr}" if combined else proc.stderr
        if proc.returncode != 0 and "status:" not in combined:
            detail = f"check runner exited {proc.returncode}"
            combined = f"{combined}\n  status: upstream-resolution-failed ({detail})" if combined else (
                f"==> Component: {component}\n"
                f"  status: upstream-resolution-failed ({detail})\n"
            )
        return _strip_ansi(combined)
    except Exception as exc:  # noqa: BLE001
        return (
            f"==> Component: {component}\n"
            f"  status: upstream-resolution-failed (check runner failed: {exc})\n"
        )


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(s: str) -> str:
    return _ANSI.sub("", s)


def _parse_check_output(component: str, kind: str, output: str) -> CheckResult:
    """Pull the structured fields out of component-upgrade.sh's check output.
    The script's check mode is line-based; we look for `pinned:` and `latest:`.
    """
    pins = _read_pins()
    field_map = {
        "git-commit": "ref",
        "git-tag": "tag",
        "container-image": "tag",
        "npm": "version",
        "nvm-version": "version",
        "release-asset": "version",
    }
    field = field_map.get(kind, "")
    current = _component_value(pins, component, field) if field else ""

    pinned_match = re.search(r"pinned:\s*([^\s\(]+)", output)
    latest_match = re.search(r"latest:\s*([^\s\(]+)", output)
    pinned = pinned_match.group(1).strip() if pinned_match else current
    latest = latest_match.group(1).strip() if latest_match else ""

    upgrade_available = False
    note = ""
    status_match = re.search(r"status:\s*(.+)", output)
    status_line = status_match.group(1).strip() if status_match else ""
    transient = "upstream-resolution-failed" in status_line or (
        not status_line and "check failed:" in output.lower()
    )

    if transient:
        # Network/rate-limit hiccup - keep existing throttle row intact, but
        # don't propose anything new this run.
        upgrade_available = False
        note = status_line
        latest = ""
    elif kind == "container-image":
        # Moving tags don't auto-flag as "upgrade available". Detector treats
        # them as informational - operator decides explicit --tag bumps.
        upgrade_available = False
        note = status_line or "moving tag; explicit --tag bump required"
        latest = ""  # no concrete target proposed
    elif kind == "nvm-version":
        # Major-only pin - informational only. Latest patch is shown but the
        # detector doesn't propose auto-bumping (operator decides).
        upgrade_available = False
        note = status_line or "major-only pin"
        latest = ""
    else:
        upgrade_available = "upgrade available" in status_line
        note = status_line or ""

    current_label = ""
    target_label = ""
    if kind == "git-commit":
        repo = str(pins.get("components", {}).get(component, {}).get("repo") or "")
        current_label = _git_commit_release_label(repo, pinned)
        if latest:
            target_label = _git_commit_release_label(repo, latest)
    else:
        repo = ""

    return CheckResult(
        component=component, kind=kind, field=field,
        current=pinned, target=latest,
        upgrade_available=upgrade_available, note=note,
        transient_failure=transient,
        current_label=current_label, target_label=target_label,
        repo=repo,
    )


# ---- throttle state machine ------------------------------------------------

def _ensure_state_table(conn: sqlite3.Connection) -> None:
    # Schema is created by arclink_control.ensure_schema. This function is
    # kept as a defensive backstop for ad-hoc invocations.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pin_upgrade_notifications (
          component TEXT PRIMARY KEY,
          field TEXT NOT NULL,
          current_pin TEXT NOT NULL,
          target_value TEXT NOT NULL,
          first_seen_at TEXT NOT NULL,
          last_notified_at TEXT,
          notify_count INTEGER NOT NULL DEFAULT 0,
          silenced INTEGER NOT NULL DEFAULT 0,
          applied_at TEXT,
          extra_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )


def _now_iso() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _git_release_version_key(label: str) -> str:
    """Return the release-version portion of a git commit display label.

    Hermes labels render like `v0.11.0 (2026.4.23)` for operator context, but
    the alert throttle should key on `v0.11.0` so release-date text is not part
    of the identity.
    """
    text = str(label or "").strip()
    if not text:
        return ""
    return text.split(None, 1)[0].strip()


def _notify_limit(pins: dict[str, Any]) -> int:
    config = pins.get("upgrade_notifications")
    raw = None
    if isinstance(config, dict):
        raw = config.get("notify_limit_per_release")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_NOTIFY_LIMIT
    return max(1, min(value, 10))


def _throttle_target(result: CheckResult) -> str:
    if result.kind == "git-commit":
        release_key = _git_release_version_key(result.target_label)
        if release_key:
            return release_key
    return result.target


def _stored_git_throttle_target(result: CheckResult, stored_target: str) -> str:
    target = str(stored_target or "").strip()
    if result.kind != "git-commit" or not target:
        return target
    if not GIT_SHA_RE.fullmatch(target):
        return _git_release_version_key(target) or target
    if not result.repo:
        return target
    return _git_release_version_key(_git_commit_release_label(result.repo, target)) or target


def _state_extra_json(result: CheckResult, throttle_target: str) -> str:
    return json.dumps(
        {
            "raw_target": result.target,
            "throttle_target": throttle_target,
            "current_label": result.current_label,
            "target_label": result.target_label,
        },
        sort_keys=True,
    )


def _upsert_state(
    conn: sqlite3.Connection,
    result: CheckResult,
    *,
    notify_limit: int,
) -> tuple[bool, dict[str, Any]]:
    """Update pin_upgrade_notifications for one component.

    Returns (include_in_digest, state_row_after).
    Logic:
      - If no row exists: insert (count=0). Will be included in digest;
        post-send, count goes to 1.
      - If row exists with same target: bump current_pin (in case it
        rotated below the target), do not reset count. If silenced, skip.
      - If row exists with different target: reset count, update target,
        unsilence.
      - If upgrade_available is False but a row exists for this component,
        delete it (the upgrade was applied or upstream went back).
    """
    cursor = conn.execute(
        "SELECT * FROM pin_upgrade_notifications WHERE component = ?",
        (result.component,),
    )
    existing = cursor.fetchone()

    if result.transient_failure:
        # Upstream lookup hiccupped this run - preserve any existing row so
        # we don't lose throttle state on flapping networks.
        return False, {}

    if not result.upgrade_available or not result.target:
        if existing is not None:
            # Stale row - pin advanced past the tracked target (operator
            # upgraded) or upstream rolled back.
            conn.execute(
                "DELETE FROM pin_upgrade_notifications WHERE component = ?",
                (result.component,),
            )
            conn.commit()
        return False, {}

    target_value = _throttle_target(result)
    extra_json = _state_extra_json(result, target_value)

    if existing is None:
        conn.execute(
            """
            INSERT INTO pin_upgrade_notifications
              (component, field, current_pin, target_value, first_seen_at,
               notify_count, silenced, extra_json)
            VALUES (?, ?, ?, ?, ?, 0, 0, ?)
            """,
            (
                result.component, result.field, result.current,
                target_value, _now_iso(), extra_json,
            ),
        )
        conn.commit()
        return True, {
            "component": result.component, "field": result.field,
            "current_pin": result.current, "target_value": target_value,
            "notify_count": 0, "silenced": 0,
            "extra_json": extra_json,
        }

    state = dict(zip(
        ["component", "field", "current_pin", "target_value", "first_seen_at",
         "last_notified_at", "notify_count", "silenced", "applied_at", "extra_json"],
        existing,
    ))

    stored_target = str(state["target_value"] or "")
    stored_throttle_target = _stored_git_throttle_target(result, stored_target)
    migrated_from_legacy_target = stored_throttle_target == target_value and stored_target != target_value

    if migrated_from_legacy_target:
        # Existing rows created before release-version throttling used the raw
        # commit hash. Preserve their strike count and silenced state while
        # moving the identity to the release version.
        conn.execute(
            """
            UPDATE pin_upgrade_notifications
            SET target_value = ?, current_pin = ?, extra_json = ?
            WHERE component = ?
            """,
            (target_value, result.current, extra_json, result.component),
        )
        conn.commit()
        state["target_value"] = target_value
        state["current_pin"] = result.current
        state["extra_json"] = extra_json
        if int(state["silenced"]) == 1 or int(state["notify_count"]) >= notify_limit:
            return False, state
        return True, state

    if stored_throttle_target != target_value:
        # A new upgrade target appeared - reset throttle.
        conn.execute(
            """
            UPDATE pin_upgrade_notifications
            SET target_value = ?, current_pin = ?, notify_count = 0,
                silenced = 0, last_notified_at = NULL, applied_at = NULL,
                extra_json = ?
            WHERE component = ?
            """,
            (target_value, result.current, extra_json, result.component),
        )
        conn.commit()
        state["target_value"] = target_value
        state["current_pin"] = result.current
        state["notify_count"] = 0
        state["silenced"] = 0
        state["extra_json"] = extra_json
        return True, state

    # Same target as before. Refresh current_pin in case the pin rotated
    # (it shouldn't unless the operator applied a partial bump).
    conn.execute(
        "UPDATE pin_upgrade_notifications SET current_pin = ?, extra_json = ? WHERE component = ?",
        (result.current, extra_json, result.component),
    )
    conn.commit()
    state["current_pin"] = result.current
    state["extra_json"] = extra_json

    if int(state["silenced"]) == 1 or int(state["notify_count"]) >= notify_limit:
        return False, state
    return True, state


def _mark_notified(conn: sqlite3.Connection, components: list[str], *, notify_limit: int) -> None:
    """After the digest goes out, increment notify_count for each component
    listed and silence those that hit the configured notification limit.
    """
    now = _now_iso()
    for component in components:
        conn.execute(
            """
            UPDATE pin_upgrade_notifications
            SET notify_count = notify_count + 1,
                last_notified_at = ?,
                silenced = CASE WHEN notify_count + 1 >= ? THEN 1 ELSE silenced END
            WHERE component = ?
            """,
            (now, notify_limit, component),
        )
    conn.commit()


# ---- digest builder --------------------------------------------------------

def _build_digest(included: list[tuple[CheckResult, dict[str, Any]]],
                  silenced: list[CheckResult],
                  *,
                  notify_limit: int) -> str:
    def git_commit_display(ref: str, label: str) -> str:
        short = ref[:12] if ref else "?"
        if label:
            return f"{label} [{short}]"
        return short

    lines = ["Pinned-component upgrade digest:"]
    for r, state in included:
        notify_count = int(state.get("notify_count") or 0)
        attempt = f"#{notify_count + 1} of {notify_limit}"
        if r.kind == "git-commit":
            old_display = git_commit_display(r.current, r.current_label)
            new_display = git_commit_display(r.target, r.target_label)
            lines.append(
                f"  - {r.component} ({r.kind}): {old_display} -> {new_display}  [{attempt}]"
            )
        else:
            lines.append(
                f"  - {r.component} ({r.kind}): {r.current} -> {r.target}  [{attempt}]"
            )
    def target_display(result: CheckResult) -> str:
        if result.kind == "git-commit":
            return git_commit_display(result.target, result.target_label)
        return result.target

    if silenced:
        lines.append("")
        lines.append(
            "Silenced (notification limit reached; will re-notify only when a NEW release/version appears):"
        )
        for r in silenced:
            lines.append(f"  - {r.component}: target {target_display(r)}")
    lines.append("")
    lines.append("Approve via:")
    approve_commands: list[str] = []
    for r, _state in included:
        if r.kind == "git-commit":
            approve_commands.append(f"./deploy.sh {r.component.split('-')[0]}-upgrade")
        elif r.kind == "container-image":
            approve_commands.append(f"./deploy.sh {r.component}-upgrade --tag <tag>")
        elif r.kind == "git-tag":
            approve_commands.append(f"./deploy.sh {r.component}-upgrade")
        elif r.kind in ("npm", "release-asset"):
            approve_commands.append(f"./deploy.sh {r.component}-upgrade")
        elif r.kind == "nvm-version":
            approve_commands.append(f"./deploy.sh {r.component}-upgrade --version <vX.Y.Z>")
    for command in dict.fromkeys(approve_commands):
        lines.append(f"  {command}")
    lines.append("")
    lines.append("Source of truth: config/pins.json. Detector throttles each release/version target to "
                 f"{notify_limit} notification{'s' if notify_limit != 1 else ''}.")
    return "\n".join(lines)


def _pin_upgrade_action_items(included: list[tuple[CheckResult, dict[str, Any]]]) -> list[dict[str, str]]:
    return [
        {
            "component": r.component,
            "kind": r.kind,
            "field": r.field,
            "current": r.current,
            "target": r.target,
            "throttle_target": _throttle_target(r),
        }
        for r, _state in included
        if r.target
    ]


def _pin_upgrade_install_items(
    pins: dict[str, Any],
    included: list[tuple[CheckResult, dict[str, Any]]],
) -> list[dict[str, str]]:
    """Return the component upgrades the Install button should run.

    If both a parent component and an inheritor are in the digest (for example
    hermes-agent and hermes-docs), applying the parent is enough because
    component-upgrade.sh bumps inheritors automatically.
    """
    included_names = {r.component for r, _state in included}
    items: list[dict[str, str]] = []
    for r, _state in included:
        entry = pins.get("components", {}).get(r.component, {})
        parent = str(entry.get("inherits_from") or "").strip()
        if parent and parent in included_names:
            continue
        if not r.target:
            continue
        items.append(
            {
                "component": r.component,
                "kind": r.kind,
                "field": r.field,
                "current": r.current,
                "target": r.target,
                "throttle_target": _throttle_target(r),
            }
        )
    return items


# ---- main entry points -----------------------------------------------------

def run_detector(conn: sqlite3.Connection, cfg: Any) -> dict[str, Any]:
    """Single detection pass. Returns a structured result for callers."""
    _ensure_state_table(conn)
    pins = _read_pins()
    notify_limit = _notify_limit(pins)

    included: list[tuple[CheckResult, dict[str, Any]]] = []
    silenced_results: list[CheckResult] = []
    cleared: list[str] = []
    seen_components: list[str] = []

    for name in MANAGED_COMPONENTS:
        kind = _component_kind(pins, name)
        if not kind:
            continue
        seen_components.append(name)
        output = _run_check(name)
        result = _parse_check_output(name, kind, output)
        include, state = _upsert_state(conn, result, notify_limit=notify_limit)
        if include:
            included.append((result, state))
        else:
            # Was a state row cleared in upsert? Detect that by re-querying.
            # If the row no longer exists AND result was upgrade_available,
            # something raced; otherwise silenced.
            row = conn.execute(
                "SELECT silenced, target_value FROM pin_upgrade_notifications WHERE component = ?",
                (name,),
            ).fetchone()
            if row is None and not result.upgrade_available:
                cleared.append(name)
            elif row is not None and int(row[0]) == 1:
                silenced_results.append(result)

    digest = ""
    if included:
        # Import lazily so this module can be imported in tests without dragging
        # in the full arclink_control import graph.
        ac = _import_arclink_control()
        operator_target = (
            getattr(cfg, "operator_notify_channel_id", "")
            or getattr(cfg, "operator_notify_platform", "")
            or "operator"
        )
        operator_channel = getattr(cfg, "operator_notify_platform", "") or "tui-only"
        digest = _build_digest(included, silenced_results, notify_limit=notify_limit)
        action_token = ac.register_pin_upgrade_action(
            conn,
            items=_pin_upgrade_action_items(included),
            install_items=_pin_upgrade_install_items(pins, included),
            notify_limit=notify_limit,
        )
        extra: dict[str, Any] = {
            "source": "pin-upgrade-detector",
            "pin_upgrade_action_token": action_token,
        }
        action_extra = ac.operator_pin_upgrade_action_extra(cfg, token=action_token)
        if action_extra:
            extra.update(action_extra)
        ac.queue_notification(
            conn,
            target_kind="operator",
            target_id=str(operator_target),
            channel_kind=str(operator_channel),
            message=digest,
            extra=extra,
        )
        _mark_notified(conn, [r.component for r, _ in included], notify_limit=notify_limit)

    return {
        "ok": True,
        "scanned": seen_components,
        "included": [r.component for r, _ in included],
        "silenced": [r.component for r in silenced_results],
        "cleared": cleared,
        "digest": digest,
        "notified": bool(included),
        "notify_limit": notify_limit,
    }


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(REPO_ROOT / "python"))
    import arclink_control as ac

    cfg = ac.Config.from_env()
    with ac.connect_db(cfg) as conn:
        result = run_detector(conn, cfg)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
