#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: bin/arclink-restore-smoke.sh --kind shared|agent-home --source PATH [--restore-dir PATH] [--json]

Restores a local backup artifact into a temporary or provided directory and
runs no-secret structural checks. This command never fetches from GitHub,
starts Docker, touches systemd, or restores over a live ArcLink path.
EOF
}

die() {
  echo "restore-smoke: $*" >&2
  exit 1
}

KIND=""
SOURCE_PATH=""
RESTORE_DIR=""
JSON_OUTPUT=0
CHECKS=()

add_check() {
  CHECKS+=("$1")
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --kind)
      [[ $# -ge 2 ]] || die "--kind requires shared or agent-home"
      KIND="$2"
      shift 2
      ;;
    --source)
      [[ $# -ge 2 ]] || die "--source requires a local path"
      SOURCE_PATH="$2"
      shift 2
      ;;
    --restore-dir)
      [[ $# -ge 2 ]] || die "--restore-dir requires a path"
      RESTORE_DIR="$2"
      shift 2
      ;;
    --json)
      JSON_OUTPUT=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      die "unknown argument: $1"
      ;;
  esac
done

case "$KIND" in
  shared|agent-home)
    ;;
  "")
    usage
    die "--kind is required"
    ;;
  *)
    die "--kind must be shared or agent-home"
    ;;
esac

[[ -n "$SOURCE_PATH" ]] || { usage; die "--source is required"; }
case "$SOURCE_PATH" in
  *://*|git@*|ssh://*|http://*|https://*)
    die "--source must be a local backup artifact; clone or fetch live backups only in an authorized proof window"
    ;;
esac
[[ -e "$SOURCE_PATH" ]] || die "source path does not exist: $SOURCE_PATH"

SOURCE_ABS="$(realpath "$SOURCE_PATH")"

if [[ -z "$RESTORE_DIR" ]]; then
  RESTORE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/arclink-restore-smoke.XXXXXX")"
else
  if [[ -e "$RESTORE_DIR" ]] && [[ -n "$(find "$RESTORE_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    die "--restore-dir must be empty when it already exists"
  fi
  mkdir -p "$RESTORE_DIR"
fi
RESTORE_ABS="$(realpath "$RESTORE_DIR")"

case "$RESTORE_ABS/" in
  "$SOURCE_ABS/"*)
    die "--restore-dir must not be inside the source path"
    ;;
esac
case "$SOURCE_ABS/" in
  "$RESTORE_ABS/"*)
    die "--source must not be inside the restore directory"
    ;;
esac

validate_tar_members() {
  local archive="$1"
  local member=""
  while IFS= read -r member; do
    case "$member" in
      ""|/*|../*|*/../*|..|*/..)
        die "archive contains unsafe path: $member"
        ;;
    esac
  done < <(tar -tf "$archive")
}

restore_source() {
  if [[ -d "$SOURCE_ABS/.git" ]]; then
    git -C "$SOURCE_ABS" rev-parse --verify HEAD >/dev/null
    git -C "$SOURCE_ABS" archive --format=tar HEAD | tar -xf - -C "$RESTORE_ABS"
    add_check "git_archive_head"
    return 0
  fi

  if [[ -d "$SOURCE_ABS" ]]; then
    (cd "$SOURCE_ABS" && tar --exclude='./.git' -cf - .) | (cd "$RESTORE_ABS" && tar -xf -)
    add_check "directory_snapshot"
    return 0
  fi

  if [[ -f "$SOURCE_ABS" ]]; then
    case "$SOURCE_ABS" in
      *.tar|*.tar.gz|*.tgz)
        validate_tar_members "$SOURCE_ABS"
        tar -xf "$SOURCE_ABS" -C "$RESTORE_ABS"
        add_check "tar_snapshot"
        ;;
      *.sqlite3|*.db)
        [[ "$KIND" == "shared" ]] || die "SQLite backup files are only valid for --kind shared"
        mkdir -p "$RESTORE_ABS/state"
        cp "$SOURCE_ABS" "$RESTORE_ABS/state/$(basename "$SOURCE_ABS")"
        add_check "sqlite_backup_file"
        ;;
      *)
        die "source file must be a tar archive or SQLite backup artifact"
        ;;
    esac
    return 0
  fi

  die "unsupported source path: $SOURCE_PATH"
}

quick_check_sqlite() {
  local db_path="$1"
  python3 - "$db_path" <<'PY'
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

path = Path(sys.argv[1]).resolve()
conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
try:
    row = conn.execute("PRAGMA quick_check").fetchone()
finally:
    conn.close()
if not row or row[0] != "ok":
    raise SystemExit(f"sqlite quick_check failed for {path}")
PY
}

validate_no_nested_git() {
  local nested=""
  nested="$(find "$RESTORE_ABS" -path '*/.git' -print -quit 2>/dev/null || true)"
  [[ -z "$nested" ]] || die "restored artifact contains nested git metadata: $nested"
  add_check "no_nested_git_metadata"
}

validate_agent_symlink_targets() {
  python3 - "$RESTORE_ABS" <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
    current = Path(dirpath)
    for name in [*dirnames, *filenames]:
        path = current / name
        if not path.is_symlink():
            continue
        target_text = os.readlink(path)
        if os.path.isabs(target_text):
            raise SystemExit(f"agent-home backup symlink uses absolute target: {path}")
        target = (path.parent / target_text).resolve(strict=False)
        try:
            relative = target.relative_to(root)
        except ValueError:
            raise SystemExit(f"agent-home backup symlink escapes restore tree: {path}") from None
        parts = set(relative.parts)
        if "secrets" in parts or "logs" in parts:
            raise SystemExit(f"agent-home backup symlink targets excluded content: {path}")
PY
  add_check "agent_symlink_targets"
}

validate_shared_restore() {
  local recognized=0
  local sqlite_count=0
  local db_path=""

  for top in config vault state published quarto; do
    if [[ -e "$RESTORE_ABS/$top" ]]; then
      recognized=1
    fi
  done

  while IFS= read -r db_path; do
    [[ -n "$db_path" ]] || continue
    quick_check_sqlite "$db_path"
    sqlite_count=$((sqlite_count + 1))
  done < <(find "$RESTORE_ABS" -type f \( -name '*.sqlite3' -o -name '*.db' \) -print 2>/dev/null)

  if (( sqlite_count > 0 )); then
    add_check "sqlite_quick_check"
    recognized=1
  fi

  (( recognized == 1 )) || die "shared restore-smoke expected config, vault, state, published, quarto, or SQLite backup content"
  add_check "shared_layout"
}

validate_agent_home_restore() {
  [[ -f "$RESTORE_ABS/MANIFEST.json" ]] || die "agent-home restore-smoke requires MANIFEST.json"
  python3 - "$RESTORE_ABS/MANIFEST.json" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if not isinstance(payload, dict):
    raise SystemExit("MANIFEST.json must contain an object")
PY
  add_check "agent_manifest_json"

  [[ ! -e "$RESTORE_ABS/secrets" ]] || die "agent-home backup artifact must not contain secrets/"
  [[ ! -e "$RESTORE_ABS/logs" ]] || die "agent-home backup artifact must not contain logs/"
  add_check "agent_secret_exclusion"
  validate_agent_symlink_targets

  local curated=0
  for path in SOUL.md config.yaml memories skills plugins cron sessions state; do
    if [[ -e "$RESTORE_ABS/$path" ]]; then
      curated=1
    fi
  done
  (( curated == 1 )) || die "agent-home restore-smoke expected at least one curated Hermes-home path"
  add_check "agent_curated_paths"
}

restore_source
validate_no_nested_git

FILE_COUNT="$(find "$RESTORE_ABS" -type f -print 2>/dev/null | wc -l | tr -d ' ')"
[[ "$FILE_COUNT" != "0" ]] || die "restore produced an empty tree"

case "$KIND" in
  shared)
    validate_shared_restore
    ;;
  agent-home)
    validate_agent_home_restore
    ;;
esac

if [[ "$JSON_OUTPUT" == "1" ]]; then
  python3 - "$KIND" "$SOURCE_ABS" "$RESTORE_ABS" "$FILE_COUNT" "${CHECKS[@]}" <<'PY'
from __future__ import annotations

import json
import sys

kind, source, restore_dir, file_count, *checks = sys.argv[1:]
print(json.dumps({
    "ok": True,
    "kind": kind,
    "source": source,
    "restore_dir": restore_dir,
    "file_count": int(file_count),
    "checks": checks,
}, sort_keys=True))
PY
else
  echo "restore-smoke passed for $KIND backup artifact"
  echo "restored_to=$RESTORE_ABS"
  echo "file_count=$FILE_COUNT"
  echo "checks=${CHECKS[*]}"
fi
