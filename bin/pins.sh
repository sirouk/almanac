#!/usr/bin/env bash
# pins.sh - read/write the ArcLink dependency pins file (config/pins.json).
#
# This is the single source of truth for every external dependency the deploy
# hard-installs. Hot-path callers (bin/common.sh, install scripts, deploy.sh
# subcommands) source this file and use pins_get / pins_set instead of
# hard-coding values; env vars are degraded-path fallbacks when pins are
# unavailable during early bootstrap.
#
# Requires `jq`. Schema: config/pins.schema.json.

# Resolve the default path relative to this script's location so pins.sh works
# whether it's invoked from the repo root, from bin/, or via deploy.sh.
__pins_default_path() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  printf '%s/../config/pins.json' "$script_dir"
}

ARCLINK_PINS_FILE="${ARCLINK_PINS_FILE:-$(__pins_default_path)}"

# pins_require - exit nonzero with a clear message if the prerequisites aren't met.
pins_require() {
  if ! command -v jq >/dev/null 2>&1; then
    echo "pins.sh: jq is required (apt install jq)" >&2
    return 1
  fi
  if [[ ! -f "$ARCLINK_PINS_FILE" ]]; then
    echo "pins.sh: pins file not found at $ARCLINK_PINS_FILE" >&2
    return 1
  fi
  return 0
}

# pins_get <component> <jq-dotted-path>  →  prints the value or "" if missing.
# Examples:
#   pins_get hermes-agent ref
#   pins_get hermes-agent repo
#   pins_get nextcloud tag
#   pins_get hermes-agent extras.0
pins_get() {
  local component="$1" path="$2"
  pins_require || return 1
  jq -r --arg c "$component" --arg p "$path" '
    .components[$c] as $entry |
    if $entry == null then "" else
      ($p | split(".") | map(if test("^(0|[1-9][0-9]*)$") then tonumber else . end)) as $parts |
      (try ($entry | getpath($parts)) catch null) // "" |
      if (type == "object") or (type == "array") then tojson else . end
    end
  ' "$ARCLINK_PINS_FILE"
}

__pins_temp_path() {
  local dir base
  dir="$(dirname "$ARCLINK_PINS_FILE")"
  base="$(basename "$ARCLINK_PINS_FILE")"
  mktemp "$dir/.${base}.tmp.XXXXXX"
}

__pins_with_write_lock() {
  local lock_file
  if ! command -v flock >/dev/null 2>&1; then
    echo "pins.sh: flock is required for pin writes" >&2
    return 1
  fi
  lock_file="$(dirname "$ARCLINK_PINS_FILE")/.$(basename "$ARCLINK_PINS_FILE").lock"
  (
    flock -x 9 || exit 1
    "$@"
  ) 9>"$lock_file"
}

__pins_set_unlocked() {
  local component="$1" path="$2" value="$3"
  local tmp
  tmp="$(__pins_temp_path)" || return 1
  if ! jq --arg c "$component" --arg p "$path" --arg v "$value" '
    ($p | split(".") | map(if test("^(0|[1-9][0-9]*)$") then tonumber else . end)) as $parts |
    .components[$c] |= (. // {} | setpath($parts; $v))
  ' "$ARCLINK_PINS_FILE" > "$tmp"; then
    rm -f "$tmp"
    return 1
  fi
  if ! mv -f "$tmp" "$ARCLINK_PINS_FILE"; then
    rm -f "$tmp"
    return 1
  fi
}

__pins_set_raw_unlocked() {
  local component="$1" path="$2" raw="$3"
  local tmp
  tmp="$(__pins_temp_path)" || return 1
  if ! jq --arg c "$component" --arg p "$path" --argjson v "$raw" '
    ($p | split(".") | map(if test("^(0|[1-9][0-9]*)$") then tonumber else . end)) as $parts |
    .components[$c] |= (. // {} | setpath($parts; $v))
  ' "$ARCLINK_PINS_FILE" > "$tmp"; then
    rm -f "$tmp"
    return 1
  fi
  if ! mv -f "$tmp" "$ARCLINK_PINS_FILE"; then
    rm -f "$tmp"
    return 1
  fi
}

# pins_kind <component>  →  shorthand for pins_get <c> kind
pins_kind() { pins_get "$1" kind; }

# pins_resolve_inherited_ref <component>  →  if the component declares an
# inherits_from field, return the inheriting target's `ref`; otherwise return
# the component's own `ref`. Used by hermes-docs which inherits hermes-agent.
pins_resolve_inherited_ref() {
  local component="$1"
  local inherit ref
  inherit="$(pins_get "$component" inherits_from)"
  if [[ -n "$inherit" ]]; then
    ref="$(pins_get "$inherit" ref)"
    if [[ -n "$ref" ]]; then
      printf '%s' "$ref"
      return 0
    fi
  fi
  pins_get "$component" ref
}

# pins_set <component> <jq-dotted-path> <value> - atomic in-place rewrite.
# The value is treated as a string; jq's --arg quotes it. For numeric or
# boolean values use pins_set_raw.
pins_set() {
  local component="$1" path="$2" value="$3"
  pins_require || return 1
  __pins_with_write_lock __pins_set_unlocked "$component" "$path" "$value"
}

# pins_set_raw <component> <jq-dotted-path> <jq-expr>
# For non-string values: pins_set_raw foo.0 bar 'true' / '42' / '["a","b"]'.
pins_set_raw() {
  local component="$1" path="$2" raw="$3"
  pins_require || return 1
  __pins_with_write_lock __pins_set_raw_unlocked "$component" "$path" "$raw"
}

# pins_components - print the list of all component keys, one per line.
pins_components() {
  pins_require || return 1
  jq -r '.components | keys[]' "$ARCLINK_PINS_FILE"
}

# pins_show - pretty-print every pin in human-readable form. Stable ordering.
pins_show() {
  pins_require || return 1
  jq -r '
    .components | to_entries | sort_by(.key) | .[] |
    "\(.key)" + "\n" +
    (.value | to_entries | map(
      if .key == "description" then "  \(.key): \(.value | gsub("\\n"; " "))"
      else "  \(.key): \(.value | tojson)" end
    ) | join("\n")) + "\n"
  ' "$ARCLINK_PINS_FILE"
}

# pins_validate - quick structural check. Returns 0 if every component has the
# fields its kind requires, nonzero on the first broken component.
pins_validate() {
  pins_require || return 1
  local missing
  missing="$(jq -r '
    .components | to_entries[] |
    .key as $name | .value as $c |
    [
      ($c.kind == "git-commit"     and ($c.repo == null or $c.ref == null)),
      ($c.kind == "git-tag"        and ($c.repo == null or $c.tag == null)),
      ($c.kind == "container-image" and ($c.image == null or $c.tag == null)),
      ($c.kind == "npm"            and ($c.package == null or $c.version == null)),
      ($c.kind == "nvm-version"    and ($c.version == null)),
      ($c.kind == "uv-python"      and ($c.preferred == null or $c.minimum == null)),
      ($c.kind == "installer-url"  and ($c.url == null)),
      ($c.kind == "release-asset"  and ($c.repo == null))
    ] | any | if . then $name else empty end
  ' "$ARCLINK_PINS_FILE")"
  if [[ -n "$missing" ]]; then
    echo "pins.sh: component(s) failed kind-required-field validation: $missing" >&2
    return 1
  fi
  return 0
}
