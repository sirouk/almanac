#!/usr/bin/env python3
"""Apply central ArcLink skill enablement inside one agent's HERMES_HOME.

The control plane records Trainer-approved skill enablement intents in the
``arclink_agent_skill_enablement`` registry and mirrors the Academy intents
into the deployment's ``state/arclink-academy-approved-skills.json``. This
helper is the per-agent application lane (invoked by
``bin/user-agent-refresh.sh``, which runs every 4h and on curator refresh
signals). It:

  1. reads the approved-skill intents staged in this HERMES_HOME,
  2. checks whether each skill is locally discoverable (``$HERMES_HOME/skills``
     or any ``skills.external_dirs`` library),
  3. removes discoverable approved skills from ``config.yaml`` ``skills.disabled``
     using targeted line surgery (never a YAML re-dump, so user formatting and
     unrelated keys are preserved),
  4. writes a receipt to ``state/arclink-skill-enablement-applied.json``.

Hermes precedence rules are honored by construction:
  - skill files are never copied or overwritten (local ``~/.hermes/skills``
    always wins name collisions);
  - ``skills.platform_disabled`` is never touched;
  - entries are only ever REMOVED from ``skills.disabled`` and only for skills
    the control plane approved AND that are actually discoverable (fail
    closed: a missing skill stays untouched and is reported as ``missing``);
  - new skills enter the Hermes system-prompt index at next session start
    (``effective_at: next_session`` in the receipt).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APPROVED_SKILLS_STATE_NAME = "arclink-academy-approved-skills.json"
RECEIPT_STATE_NAME = "arclink-skill-enablement-applied.json"

_TOP_LEVEL_KEY_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]*\s*:")
_CHILD_KEY_RE = re.compile(r"^(\s+)([A-Za-z0-9_][A-Za-z0-9_-]*)\s*:")
_SKILLS_KEY_RE = re.compile(r"^skills\s*:\s*(?:#.*)?$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _list_item_name(line: str) -> str:
    match = re.match(r"^\s*-\s*(.+?)\s*$", line)
    if not match:
        return ""
    return match.group(1).split("#", 1)[0].strip().strip("\"'")


def _child_indent(block: list[str]) -> int:
    for line in block[1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _CHILD_KEY_RE.match(line)
        if match:
            return len(match.group(1).replace("\t", "  "))
    return 2


def _direct_child_key(line: str, indent: int) -> str:
    match = _CHILD_KEY_RE.match(line)
    if not match:
        return ""
    return match.group(2) if len(match.group(1).replace("\t", "  ")) == indent else ""


def _skills_block_bounds(lines: list[str]) -> tuple[int | None, int]:
    start = None
    for index, line in enumerate(lines):
        if _SKILLS_KEY_RE.match(line):
            start = index
            break
    if start is None:
        return None, 0
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].strip() and _TOP_LEVEL_KEY_RE.match(lines[index]):
            end = index
            break
    return start, end


def parse_skills_config(config_text: str) -> dict[str, list[str]]:
    """Read skills.disabled and skills.external_dirs without a YAML library.

    Only block-style lists directly under ``skills:`` are recognized; anything
    else simply yields empty lists, which makes every downstream decision fail
    closed (no config mutation).
    """
    lines = config_text.splitlines()
    start, end = _skills_block_bounds(lines)
    result: dict[str, list[str]] = {"disabled": [], "external_dirs": []}
    if start is None:
        return result
    block = lines[start:end]
    indent = _child_indent(block)
    section = ""
    for line in block[1:]:
        key = _direct_child_key(line, indent)
        if key:
            section = key if key in result else ""
            continue
        item = _list_item_name(line)
        if item and section:
            result[section].append(item)
    return result


def remove_skills_from_disabled(config_text: str, skill_ids: set[str]) -> tuple[str, list[str]]:
    """Return (new_config_text, removed_skill_ids).

    Removes only exact list items inside skills.disabled; every other line is
    preserved byte-for-byte. When the skills block or disabled section is
    absent, the text is returned unchanged.
    """
    if not skill_ids:
        return config_text, []
    lines = config_text.splitlines()
    start, end = _skills_block_bounds(lines)
    if start is None:
        return config_text, []
    indent = _child_indent(lines[start:end])
    section = ""
    removed: list[str] = []
    kept: list[str] = []
    for index, line in enumerate(lines):
        if start < index < end:
            key = _direct_child_key(line, indent)
            if key:
                section = key if key == "disabled" else ""
            item = _list_item_name(line)
            if item and section == "disabled" and item in skill_ids:
                removed.append(item)
                continue
        kept.append(line)
    if not removed:
        return config_text, []
    trailing_newline = "\n" if config_text.endswith("\n") else ""
    return "\n".join(kept) + trailing_newline, removed


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _expand_dir(value: str, hermes_home: Path) -> Path:
    expanded = os.path.expanduser(os.path.expandvars(str(value or "").strip()))
    if not expanded:
        return hermes_home / "__missing__"
    path = Path(expanded)
    if not path.is_absolute():
        path = hermes_home / path
    return path


def _skill_available(skill_id: str, *, hermes_home: Path, external_dirs: list[str]) -> str:
    local_dir = hermes_home / "skills" / skill_id
    if local_dir.is_dir():
        return str(local_dir)
    for raw_dir in external_dirs:
        candidate = _expand_dir(raw_dir, hermes_home) / skill_id
        if candidate.is_dir():
            return str(candidate)
    return ""


def _load_approved_skill_ids(state_path: Path) -> tuple[list[str], list[str]]:
    """Return (skill_ids, problems) from the staged academy intents file."""
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [], []
    except (OSError, ValueError) as exc:
        return [], [f"unreadable approved-skills state: {exc}"]
    if not isinstance(payload, list):
        return [], ["approved-skills state is not a JSON list"]
    skill_ids: list[str] = []
    problems: list[str] = []
    seen: set[str] = set()
    for intent in payload:
        if not isinstance(intent, dict):
            problems.append("skipped non-object intent entry")
            continue
        skill_id = str(intent.get("skill_id") or intent.get("source_id") or "").strip()
        if not skill_id:
            problems.append(f"intent without skill id: {str(intent.get('source_id') or 'unknown')}")
            continue
        if "/" in skill_id or "\\" in skill_id or ".." in skill_id:
            problems.append(f"rejected unsafe skill id: {skill_id}")
            continue
        if skill_id in seen:
            continue
        seen.add(skill_id)
        skill_ids.append(skill_id)
    return skill_ids, problems


def apply_skill_enablement(hermes_home: Path) -> dict[str, Any]:
    """Apply staged enablement intents and return the receipt payload."""
    hermes_home = Path(hermes_home).expanduser()
    state_dir = hermes_home / "state"
    intents_path = state_dir / APPROVED_SKILLS_STATE_NAME
    config_path = hermes_home / "config.yaml"
    skill_ids, problems = _load_approved_skill_ids(intents_path)
    receipt: dict[str, Any] = {
        "applied_at": _utc_now_iso(),
        "intents_file": str(intents_path),
        "config_file": str(config_path),
        "effective_at": "next_session",
        "skills": [],
        "problems": problems,
        "config_changed": False,
    }
    if not skill_ids:
        receipt["status"] = "no_intents" if not problems else "invalid_intents"
        return receipt

    try:
        config_text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        config_text = ""
    except OSError as exc:
        receipt["status"] = "config_unreadable"
        receipt["problems"].append(f"unreadable config.yaml: {exc}")
        return receipt
    skills_cfg = parse_skills_config(config_text)
    disabled = set(skills_cfg["disabled"])
    external_dirs = skills_cfg["external_dirs"]

    to_remove: set[str] = set()
    for skill_id in skill_ids:
        location = _skill_available(skill_id, hermes_home=hermes_home, external_dirs=external_dirs)
        if not location:
            receipt["skills"].append({"skill_id": skill_id, "status": "missing"})
            continue
        if skill_id in disabled:
            to_remove.add(skill_id)
            receipt["skills"].append({"skill_id": skill_id, "status": "enabled", "location": location})
        else:
            receipt["skills"].append({"skill_id": skill_id, "status": "already_enabled", "location": location})

    if to_remove and config_text:
        new_text, removed = remove_skills_from_disabled(config_text, to_remove)
        if removed:
            _atomic_write_text(config_path, new_text)
            receipt["config_changed"] = True
            receipt["removed_from_disabled"] = sorted(removed)
    statuses = {entry["status"] for entry in receipt["skills"]}
    receipt["status"] = "applied" if statuses <= {"enabled", "already_enabled"} else "partial"
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply ArcLink skill enablement inside one agent's HERMES_HOME.")
    parser.add_argument(
        "--hermes-home",
        default=os.environ.get("HERMES_HOME", ""),
        help="Agent HERMES_HOME (defaults to $HERMES_HOME)",
    )
    args = parser.parse_args(argv)
    hermes_home = str(args.hermes_home or "").strip()
    if not hermes_home:
        print(json.dumps({"status": "skipped", "reason": "HERMES_HOME not set"}, sort_keys=True))
        return 0
    home_path = Path(hermes_home).expanduser()
    if not home_path.is_dir():
        print(json.dumps({"status": "skipped", "reason": f"HERMES_HOME missing: {home_path}"}, sort_keys=True))
        return 0
    try:
        receipt = apply_skill_enablement(home_path)
    except Exception as exc:  # noqa: BLE001 - the refresh lane must keep running.
        receipt = {
            "applied_at": _utc_now_iso(),
            "status": "error",
            "problems": [str(exc)[:240]],
            "skills": [],
            "config_changed": False,
        }
    try:
        _atomic_write_text(
            home_path / "state" / RECEIPT_STATE_NAME,
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        )
    except OSError:
        pass
    print(json.dumps({key: receipt.get(key) for key in ("status", "config_changed")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
