#!/usr/bin/env bash
# clone-team-resources.sh — pull the team's external code resources into the
# shared vault under /Vault/Repos/ and stamp each with the Almanac sidecar
# (.almanac-source.json) so the existing Repos/ convention keeps working.
#
# This is intended to be run from the operator's terminal because some of
# the repos are private and reach via the operator's own github auth (the
# host's deploy key only covers sirouk/almanac upstream pushes — it isn't
# meant to clone arbitrary org repos).
#
# Re-runs are safe: existing checkouts get `git fetch + git reset --hard`
# to the resolved commit; new ones get `git clone`.

set -euo pipefail

VAULT_REPOS_DIR="${ALMANAC_VAULT_REPOS_DIR:-/home/almanac/almanac/almanac-priv/vault/Repos}"
SUDO="${SUDO:-sudo}"

# Resource list: <slug>|<https-url>|<branch>|<note>
RESOURCES=(
  "chutes-agent-toolkit|https://github.com/Veightor/chutes-agent-toolkit.git|main|Knowledge base — Veightor's Chutes agent toolkit"
  "knowledge-agent|https://github.com/chutesai/knowledge-agent.git|main|Knowledge base — chutesai/knowledge-agent"
  "chutes-docs|https://github.com/chutesai/chutes-docs.git|main|Knowledge base — chutesai/chutes-docs"
  "vane-backup|https://github.com/Vane-ChutesAI/vane-backup.git|main|Self-Aware / Persona Curation / Knowledge base"
  "slop-guard|https://github.com/eric-tramel/slop-guard.git|main|Guard rails — LLM output filtering (eric-tramel/slop-guard)"
)

note() { printf '\033[36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!! %s\033[0m\n' "$*" >&2; }

if ! ${SUDO} -n -u almanac true 2>/dev/null && ! ${SUDO} -v; then
  warn "this script needs sudo to write under /home/almanac/... (the vault is owned by the almanac user)."
  exit 1
fi

note "Vault repos dir: $VAULT_REPOS_DIR"
${SUDO} -u almanac mkdir -p "$VAULT_REPOS_DIR"

for ENTRY in "${RESOURCES[@]}"; do
  IFS='|' read -r SLUG URL BRANCH NOTE <<< "$ENTRY"
  TARGET="$VAULT_REPOS_DIR/$SLUG"
  note "$SLUG  ($URL)  — $NOTE"

  if ${SUDO} test -d "$TARGET/.git"; then
    note "  fetching latest into existing checkout"
    ${SUDO} -u almanac git -C "$TARGET" fetch --prune origin
    ${SUDO} -u almanac git -C "$TARGET" reset --hard "origin/$BRANCH"
  else
    # Stage the clone in /tmp first (operator's auth), then move into place
    # owned by the almanac user. This way private-repo HTTPS auth uses the
    # caller's credentials, but the working tree ends up owned correctly.
    STAGE="$(mktemp -d /tmp/almanac-clone.XXXXXX)"
    git clone --branch "$BRANCH" "$URL" "$STAGE/$SLUG" \
      || { warn "  clone failed (likely auth or visibility) — skipping $SLUG"; rm -rf "$STAGE"; continue; }
    ${SUDO} chown -R almanac:almanac "$STAGE/$SLUG"
    ${SUDO} mv "$STAGE/$SLUG" "$TARGET"
    rm -rf "$STAGE"
  fi

  RESOLVED_COMMIT=$(${SUDO} -u almanac git -C "$TARGET" rev-parse HEAD)
  RESOLVED_REF="$RESOLVED_COMMIT"
  ${SUDO} -u almanac tee "$TARGET/.almanac-source.json" >/dev/null <<JSON
{
  "repo_ref": "$RESOLVED_REF",
  "repo_url": "$URL",
  "resolved_commit": "$RESOLVED_COMMIT",
  "branch": "$BRANCH",
  "note": "$NOTE"
}
JSON
  note "  resolved $RESOLVED_COMMIT, sidecar written"
done

note "All resources synced. Triggering qmd update so the new files are searchable…"
${SUDO} -u almanac XDG_RUNTIME_DIR=/run/user/$(id -u almanac) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u almanac)/bus systemctl --user start almanac-qmd-update.service || true

note "Done. Verify:"
note "  ls -la $VAULT_REPOS_DIR"
note "  /home/almanac/almanac/deploy.sh health"
