#!/usr/bin/env bash
# clone-team-resources.sh - pull operator-configured external resources into a
# shared-vault resource library and stamp each checkout with
# .arclink-source.json. The default remains Vault/Repos for compatibility, but
# any path under the vault is qmd-indexed and acceptable.
#
# The actual resource list is private operator data. Put it in:
#
#   arclink-priv/config/team-resources.tsv
#
# or point ARCLINK_TEAM_RESOURCES_MANIFEST at another private file. The manifest
# format is:
#
#   slug|git-url|branch|note
#
# Re-runs are safe: existing checkouts get `git fetch + git reset --hard` to
# the resolved commit; new ones get `git clone`.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="${ARCLINK_REPO_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PRIV_DIR="${ARCLINK_PRIV_DIR:-$REPO_DIR/arclink-priv}"
VAULT_REPOS_DIR="${ARCLINK_TEAM_RESOURCES_DIR:-${ARCLINK_VAULT_REPOS_DIR:-$PRIV_DIR/vault/Repos}}"
MANIFEST="${ARCLINK_TEAM_RESOURCES_MANIFEST:-$PRIV_DIR/config/team-resources.tsv}"
SUDO="${SUDO:-sudo}"

note() { printf '\033[36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!! %s\033[0m\n' "$*" >&2; }

safe_resource_slug() {
  local slug="${1:-}"
  [[ "$slug" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || return 1
  [[ "$slug" != *..* ]] || return 1
  [[ "$slug" != .* ]] || return 1
  return 0
}

if [[ ! -f "$MANIFEST" ]]; then
  warn "no team resource manifest found at $MANIFEST"
  warn "copy config/team-resources.example.tsv into arclink-priv/config/team-resources.tsv and replace the fictional examples with private repo refs."
  exit 0
fi

if ! ${SUDO} -n -u arclink true 2>/dev/null && ! ${SUDO} -v; then
  warn "this script needs sudo to write under the shared vault when it is owned by the arclink user."
  exit 1
fi

note "Vault resource dir: $VAULT_REPOS_DIR"
note "Resource manifest: $MANIFEST"
${SUDO} -u arclink mkdir -p "$VAULT_REPOS_DIR"

while IFS='|' read -r SLUG URL BRANCH NOTE_TEXT || [[ -n "${SLUG:-}${URL:-}${BRANCH:-}${NOTE_TEXT:-}" ]]; do
  SLUG="${SLUG#"${SLUG%%[![:space:]]*}"}"
  SLUG="${SLUG%"${SLUG##*[![:space:]]}"}"
  URL="${URL#"${URL%%[![:space:]]*}"}"
  URL="${URL%"${URL##*[![:space:]]}"}"
  BRANCH="${BRANCH#"${BRANCH%%[![:space:]]*}"}"
  BRANCH="${BRANCH%"${BRANCH##*[![:space:]]}"}"
  NOTE_TEXT="${NOTE_TEXT#"${NOTE_TEXT%%[![:space:]]*}"}"
  NOTE_TEXT="${NOTE_TEXT%"${NOTE_TEXT##*[![:space:]]}"}"

  [[ -z "$SLUG" || "$SLUG" == \#* ]] && continue
  if ! safe_resource_slug "$SLUG"; then
    warn "skipping unsafe resource slug: $SLUG"
    continue
  fi
  if [[ -z "$URL" ]]; then
    warn "skipping $SLUG: missing git URL"
    continue
  fi
  BRANCH="${BRANCH:-main}"
  NOTE_TEXT="${NOTE_TEXT:-Operator-provided resource}"

  TARGET="$VAULT_REPOS_DIR/$SLUG"
  note "$SLUG ($URL) - $NOTE_TEXT"

  if ${SUDO} test -d "$TARGET/.git"; then
    note "  fetching latest into existing checkout"
    ${SUDO} -u arclink git -C "$TARGET" fetch --prune origin
    ${SUDO} -u arclink git -C "$TARGET" reset --hard "origin/$BRANCH"
  elif ${SUDO} test -e "$TARGET"; then
    warn "  target exists but is not a git checkout; skipping $SLUG"
    continue
  else
    STAGE="$(mktemp -d /tmp/arclink-clone.XXXXXX)"
    git clone --branch "$BRANCH" "$URL" "$STAGE/$SLUG" \
      || { warn "  clone failed, likely auth or visibility; skipping $SLUG"; rm -rf "$STAGE"; continue; }
    ${SUDO} chown -hR arclink:arclink "$STAGE/$SLUG"
    ${SUDO} mv "$STAGE/$SLUG" "$TARGET"
    rm -rf "$STAGE"
  fi

  RESOLVED_COMMIT=$(${SUDO} -u arclink git -C "$TARGET" rev-parse HEAD)
  RESOLVED_REF="$RESOLVED_COMMIT"
  ${SUDO} -u arclink tee "$TARGET/.arclink-source.json" >/dev/null <<JSON
{
  "repo_ref": "$RESOLVED_REF",
  "repo_url": "$URL",
  "resolved_commit": "$RESOLVED_COMMIT",
  "branch": "$BRANCH",
  "note": "$NOTE_TEXT"
}
JSON
  note "  resolved $RESOLVED_COMMIT, sidecar written"
done <"$MANIFEST"

note "All configured resources synced. Triggering qmd update so the new files are searchable..."
${SUDO} -u arclink XDG_RUNTIME_DIR=/run/user/$(id -u arclink) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u arclink)/bus systemctl --user start arclink-qmd-update.service || true

note "Done. Verify:"
note "  ls -la $VAULT_REPOS_DIR"
note "  $REPO_DIR/deploy.sh health"
