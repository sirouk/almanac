#!/usr/bin/env bash
# component-upgrade.sh — generic upgrade dispatcher for any pinned component.
#
# Reads config/pins.json to determine the component's kind, resolves the
# upstream "latest" (or a user-specified --ref/--tag/--version), and either
# reports the gap (check mode) or rewrites pins.json + commits + pushes +
# re-execs `./deploy.sh upgrade` (apply mode). When bumping, every component
# that declares `inherits_from: <bumped>` is also bumped to the new value.
#
# Usage:
#   component-upgrade.sh <component> check
#   component-upgrade.sh <component> apply [flags]
#
# Apply flags:
#   --ref REF        Pin to a specific commit (git-commit kind)
#   --tag TAG        Pin to a specific tag (git-tag, container-image kinds)
#   --version V      Pin to a specific version (npm, nvm-version, release-asset)
#   --branch B       Override the tracked branch in pins.json
#   --dry-run        Print the planned diff but don't write
#   --skip-push      Bump + commit locally, no push, no upgrade re-exec
#   --skip-upgrade   Push but don't re-exec ./deploy.sh upgrade
#
# Resolvers per kind:
#   git-commit       git ls-remote refs/heads/<branch>
#   git-tag          git ls-remote --tags --sort=-v:refname | head
#   container-image  Docker Hub registry API for the most recent tag-update timestamp
#   npm              `npm view <pkg> dist-tags.latest`
#   nvm-version      `nvm ls-remote <major>` then take the last (=highest)
#   release-asset    GitHub releases/latest tag
#   installer-url    "n/a — installer is the source of truth"
#   uv-python        "n/a — interpreter version is host policy"
#
# Idempotent: equal pins skip the commit/push/upgrade steps entirely.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/pins.sh"

note()  { printf '\033[36m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[33m!! %s\033[0m\n' "$*" >&2; }
fatal() { printf '\033[31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<EOF
Usage:
  $0 <component> check
  $0 <component> apply [--ref REF | --tag TAG | --version V] [--branch B]
                       [--dry-run] [--skip-push] [--skip-upgrade]

Components currently in config/pins.json:
$(pins_components 2>/dev/null | sed 's/^/  /' || echo "  (no pins file)")
EOF
}

# ---------- Resolvers ---------------------------------------------------------

# resolve_git_commit_head <repo> <branch>  →  full SHA of refs/heads/<branch>
resolve_git_commit_head() {
  local repo="$1" branch="$2"
  git ls-remote "$repo" "refs/heads/$branch" 2>/dev/null | awk 'NR==1{print $1}' || true
}

# resolve_git_commit_sha <repo> <sha>  →  verify an exact SHA is fetchable
# from the remote, even if it is no longer advertised as a ref tip.
resolve_git_commit_sha() {
  local repo="$1" sha="$2"
  local tmp="" out=""
  tmp="$(mktemp -d)"
  if git -C "$tmp" init -q >/dev/null 2>&1 \
    && git -C "$tmp" fetch --depth 1 "$repo" "$sha" >/dev/null 2>&1; then
    out="$(git -C "$tmp" rev-parse --verify -q 'FETCH_HEAD^{commit}' 2>/dev/null || true)"
  fi
  rm -rf "$tmp"
  if [[ "$out" == "$sha" ]]; then
    printf '%s' "$sha"
  fi
}

# resolve_git_commit_ref <repo> <ref>  →  resolve a SHA / tag / branch to a SHA.
resolve_git_commit_ref() {
  local repo="$1" ref="$2"
  if [[ "$ref" =~ ^[0-9a-f]{40}$ ]]; then
    if git ls-remote "$repo" 2>/dev/null | grep -q "^$ref"; then
      printf '%s' "$ref"; return 0
    fi
    local fetched
    fetched="$(resolve_git_commit_sha "$repo" "$ref")"
    if [[ -n "$fetched" ]]; then
      printf '%s' "$fetched"; return 0
    fi
  fi
  local out
  out="$(git ls-remote "$repo" "refs/tags/$ref" 2>/dev/null | awk 'NR==1{print $1}' || true)"
  [[ -z "$out" ]] && out="$(git ls-remote "$repo" "refs/heads/$ref" 2>/dev/null | awk 'NR==1{print $1}' || true)"
  [[ -z "$out" ]] && out="$(git ls-remote "$repo" "$ref" 2>/dev/null | awk 'NR==1{print $1}' || true)"
  printf '%s' "$out"
}

# resolve_git_tag_latest <repo>  →  highest semver tag ("vX.Y.Z" form).
resolve_git_tag_latest() {
  local repo="$1"
  git ls-remote --tags --sort=-v:refname "$repo" 2>/dev/null \
    | awk '{print $2}' \
    | grep -E 'refs/tags/v?[0-9]+(\.[0-9]+)*$' \
    | head -1 \
    | sed 's@refs/tags/@@; s@\^{}$@@' \
    || true
}

# resolve_container_digest <image> <tag>  →  the immutable digest the moving
# tag currently points at on Docker Hub. Returns "sha256:..." or empty.
_docker_hub_repo_path() {
  # Map an image reference (docker.io/<owner>/<name> or docker.io/<name>) to
  # the Docker Hub API's repository path. Bare official images live under
  # /v2/repositories/library/<name>/, so library/ MUST be preserved (we just
  # strip the registry prefix).
  local image="$1"
  printf '%s' "${image#docker.io/}"
}

resolve_container_digest() {
  local image="$1" tag="$2"
  local repo
  repo="$(_docker_hub_repo_path "$image")"
  local out
  out="$(curl -fsSL "https://hub.docker.com/v2/repositories/$repo/tags/$tag/" 2>/dev/null \
    | jq -r '.images[0].digest // .digest // empty' 2>/dev/null || true)"
  printf '%s' "$out"
}

# resolve_container_recent_tags <image> <limit>  →  list recent tags pushed.
resolve_container_recent_tags() {
  local image="$1" limit="${2:-10}"
  local repo
  repo="$(_docker_hub_repo_path "$image")"
  curl -fsSL "https://hub.docker.com/v2/repositories/$repo/tags/?page_size=$limit&ordering=last_updated" 2>/dev/null \
    | jq -r '.results[]? | "  \(.name)  (last_updated \(.last_updated))"' 2>/dev/null || true
}

# resolve_npm_latest <package>  →  dist-tags.latest version string.
resolve_npm_latest() {
  local pkg="$1"
  if command -v npm >/dev/null 2>&1; then
    npm view --silent "$pkg" "dist-tags.latest" 2>/dev/null || true
  elif command -v curl >/dev/null 2>&1; then
    curl -fsSL "https://registry.npmjs.org/-/package/$pkg/dist-tags" 2>/dev/null \
      | jq -r '.latest // empty' 2>/dev/null || true
  fi
}

# resolve_nvm_latest_for_major <major>  →  e.g. "v22.22.2" for major "22".
resolve_nvm_latest_for_major() {
  local major="$1"
  # Use Node's published index (no nvm runtime needed).
  curl -fsSL https://nodejs.org/dist/index.json 2>/dev/null \
    | jq -r --arg m "v${major}." '.[] | select(.version | startswith($m)) | .version' 2>/dev/null \
    | head -1 \
    || true
}

# resolve_github_release_latest <repo-url>  →  newest tag from
# /releases/latest. Falls back to "" if the repo has no published releases.
resolve_github_release_latest() {
  local url="$1"
  local owner_repo
  owner_repo="$(printf '%s' "$url" | sed -E 's@^https?://github\.com/@@; s@\.git$@@')"
  curl -fsSL "https://api.github.com/repos/$owner_repo/releases/latest" 2>/dev/null \
    | jq -r '.tag_name // empty' 2>/dev/null || true
}

# ---------- Component dispatch ------------------------------------------------

# component_describe <name>  →  pretty-printed kind + key fields, multi-line.
component_describe() {
  local name="$1"
  local kind; kind="$(pins_kind "$name")"
  case "$kind" in
    git-commit)
      printf '  kind: git-commit\n  repo: %s\n  ref:  %s\n  branch: %s\n' \
        "$(pins_get "$name" repo)" "$(pins_get "$name" ref)" "$(pins_get "$name" branch)"
      ;;
    git-tag)
      printf '  kind: git-tag\n  repo: %s\n  tag:  %s\n' \
        "$(pins_get "$name" repo)" "$(pins_get "$name" tag)"
      ;;
    container-image)
      printf '  kind: container-image\n  image: %s\n  tag:   %s\n' \
        "$(pins_get "$name" image)" "$(pins_get "$name" tag)"
      ;;
    npm)
      printf '  kind: npm\n  package: %s\n  version: %s\n' \
        "$(pins_get "$name" package)" "$(pins_get "$name" version)"
      ;;
    nvm-version)
      printf '  kind: nvm-version\n  version: %s\n' \
        "$(pins_get "$name" version)"
      ;;
    release-asset)
      printf '  kind: release-asset\n  repo: %s\n  version: %s\n' \
        "$(pins_get "$name" repo)" "$(pins_get "$name" version)"
      ;;
    installer-url)
      printf '  kind: installer-url\n  url: %s\n' "$(pins_get "$name" url)"
      ;;
    uv-python)
      printf '  kind: uv-python\n  preferred: %s\n  minimum: %s\n' \
        "$(pins_get "$name" preferred)" "$(pins_get "$name" minimum)"
      ;;
    *) printf '  kind: %s (no describer wired)\n' "$kind" ;;
  esac
}

# Run the kind-appropriate check. Reads from pins.json + upstream; never writes.
#
# Contract: every kind that has a resolver MUST emit at least one `pinned:`
# line and one `status:` line on stdout, even when upstream resolution fails
# (so the python detector's regex parser can always classify the component).
# When upstream is unavailable the status is "upstream-resolution-failed",
# which the detector treats as not-upgradable.
do_check() {
  local name="$1"
  local kind; kind="$(pins_kind "$name")"
  note "Component: $name"
  component_describe "$name" | sed 's/^/    /'
  case "$kind" in
    git-commit)
      local repo branch current latest
      repo="$(pins_get "$name" repo)"
      branch="$(pins_get "$name" branch)"; [[ -z "$branch" ]] && branch="main"
      current="$(pins_get "$name" ref)"
      note "  pinned: $current"
      latest="$(resolve_git_commit_head "$repo" "$branch")"
      if [[ -z "$latest" ]]; then
        warn "could not resolve refs/heads/$branch"
        note "  status: upstream-resolution-failed (network or rate-limit)"
        return 0
      fi
      note "  latest: $latest (branch HEAD)"
      if [[ "$current" == "$latest" ]]; then
        note "  status: up-to-date"
      else
        note "  status: upgrade available"
      fi
      ;;
    git-tag)
      local repo current latest
      repo="$(pins_get "$name" repo)"
      current="$(pins_get "$name" tag)"
      note "  pinned: $current"
      latest="$(resolve_git_tag_latest "$repo")"
      if [[ -z "$latest" ]]; then
        warn "could not resolve latest tag"
        note "  status: upstream-resolution-failed (network or rate-limit)"
        return 0
      fi
      note "  latest: $latest"
      if [[ "$current" == "$latest" ]]; then
        note "  status: up-to-date"
      else
        note "  status: upgrade available"
      fi
      ;;
    container-image)
      local image tag digest
      image="$(pins_get "$name" image)"
      tag="$(pins_get "$name" tag)"
      note "  pinned: $tag"
      note "  pinned image:tag = $image:$tag"
      digest="$(resolve_container_digest "$image" "$tag")"
      [[ -n "$digest" ]] && note "  current digest: $digest"
      note "  recent tags on $image:"
      resolve_container_recent_tags "$image" 8 | sed 's/^/    /' || true
      note "  status: pin is a moving tag (\"$tag\") — apply --tag <newer> to bump explicitly"
      ;;
    npm)
      local pkg current latest
      pkg="$(pins_get "$name" package)"
      current="$(pins_get "$name" version)"
      note "  pinned: $current"
      latest="$(resolve_npm_latest "$pkg")"
      if [[ -z "$latest" ]]; then
        warn "could not resolve npm latest"
        note "  status: upstream-resolution-failed (network or rate-limit)"
        return 0
      fi
      note "  latest: $latest (npm dist-tags.latest)"
      if [[ "$current" == "$latest" ]]; then
        note "  status: up-to-date"
      else
        note "  status: upgrade available"
      fi
      ;;
    nvm-version)
      local current latest
      current="$(pins_get "$name" version)"
      note "  pinned: $current"
      note "  pinned major: $current"
      latest="$(resolve_nvm_latest_for_major "$current")"
      if [[ -z "$latest" ]]; then
        warn "could not resolve latest node $current.x"
        note "  status: upstream-resolution-failed (network or rate-limit)"
        return 0
      fi
      note "  latest in series: $latest"
      note "  status: pin is a major-only spec (\"$current\") — apply --version <vX.Y.Z> to lock more tightly"
      ;;
    release-asset)
      local repo current latest
      repo="$(pins_get "$name" repo)"
      current="$(pins_get "$name" version)"
      note "  pinned: ${current:-<none>}"
      latest="$(resolve_github_release_latest "$repo")"
      if [[ -z "$latest" ]]; then
        note "  status: no GitHub releases published — install policy keeps this floating"
      else
        note "  latest: $latest"
        if [[ "${current:-}" == "$latest" ]]; then
          note "  status: up-to-date"
        else
          note "  status: upgrade available"
        fi
      fi
      ;;
    installer-url)
      local version url
      version="$(pins_get "$name" version)"
      url="$(pins_get "$name" url)"
      note "  pinned: ${version:-<floating>}"
      note "  pinned installer: $url"
      note "  status: installer-url components are install-policy floating; no upstream-check resolver."
      ;;
    uv-python)
      local preferred minimum
      preferred="$(jq -r --arg name "$name" '.components[$name].preferred // [] | join(",")' "$ARCLINK_PINS_FILE")"
      minimum="$(pins_get "$name" minimum)"
      note "  pinned: preferred=${preferred:-<none>} minimum=${minimum:-<none>}"
      note "  status: uv-python components resolve through uv preferred[] fallback; no upstream-check resolver."
      ;;
    *)
      warn "kind $kind has no resolver wired; skipping"
      ;;
  esac
}

# ---------- Apply (write + commit + push + re-exec upgrade) -------------------

# write_inherited_components <bumped_component> <new_value> <field>
# For every component that declares inherits_from: <bumped>, also pins_set its
# matching field to <new_value>. Used so hermes-docs follows hermes-agent.
write_inherited_components() {
  local bumped="$1" value="$2" field="$3"
  local children
  children="$(jq -r --arg b "$bumped" \
    '.components | to_entries[] | select(.value.inherits_from == $b) | .key' \
    "$ARCLINK_PINS_FILE" 2>/dev/null)"
  if [[ -z "$children" ]]; then
    return 0
  fi
  while IFS= read -r child; do
    [[ -z "$child" ]] && continue
    note "  also bumping inheritor: $child.$field = $value"
    pins_set "$child" "$field" "$value"
  done <<< "$children"
}

# commit_and_push_pins <commit-message-summary>
require_upstream_push_ready() {
  if [[ -z "${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-}" || ! -f "${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-}" ]]; then
    fatal "ARCLINK_UPSTREAM_DEPLOY_KEY_PATH not set or missing; cannot commit + push pins.json. Re-run with deploy-key env vars, or use --skip-push for a local-only bump."
  fi
}

upstream_ssh_command() {
  local known_hosts="${ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE:-${HOME:-}/.ssh/known_hosts}"
  printf 'ssh -i %q -o BatchMode=yes -o IPQoS=none -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=%q' \
    "$ARCLINK_UPSTREAM_DEPLOY_KEY_PATH" \
    "$known_hosts"
}

configure_origin_for_upstream() {
  if [[ -n "${ARCLINK_UPSTREAM_REPO_URL:-}" ]]; then
    if git -C "$REPO_DIR" remote get-url origin >/dev/null 2>&1; then
      git -C "$REPO_DIR" remote set-url origin "$ARCLINK_UPSTREAM_REPO_URL"
    else
      git -C "$REPO_DIR" remote add origin "$ARCLINK_UPSTREAM_REPO_URL"
    fi
  fi
}

upstream_git() {
  local ssh_command
  ssh_command="$(upstream_ssh_command)"
  GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/false SSH_ASKPASS=/bin/false GCM_INTERACTIVE=Never \
    GIT_SSH_COMMAND="$ssh_command" git -C "$REPO_DIR" "$@"
}

fetch_upstream_branch() {
  require_upstream_push_ready
  configure_origin_for_upstream
  local upstream_branch="${ARCLINK_UPSTREAM_BRANCH:-main}"
  local fetch_output="" fetch_status=0
  fetch_output="$(upstream_git fetch -q origin "$upstream_branch" 2>&1)" || fetch_status=$?
  if [[ "$fetch_status" -eq 0 ]]; then
    return 0
  fi
  if printf '%s\n' "$fetch_output" | grep -q "couldn't find remote ref $upstream_branch"; then
    return 2
  fi
  printf '%s\n' "$fetch_output" >&2
  return "$fetch_status"
}

tracked_worktree_is_clean() {
  git -C "$REPO_DIR" diff --quiet --ignore-submodules -- \
    && git -C "$REPO_DIR" diff --cached --quiet --ignore-submodules --
}

sync_current_head_with_upstream_branch() {
  local upstream_branch="${ARCLINK_UPSTREAM_BRANCH:-main}"
  local fetch_status=0
  fetch_upstream_branch || fetch_status=$?
  if [[ "$fetch_status" -eq 2 ]]; then
    note "No origin/$upstream_branch branch found yet; pushing current HEAD as the branch tip."
    return 0
  fi
  if [[ "$fetch_status" -ne 0 ]]; then
    return "$fetch_status"
  fi
  if git -C "$REPO_DIR" merge-base --is-ancestor FETCH_HEAD HEAD; then
    return 0
  fi
  if ! tracked_worktree_is_clean; then
    fatal "local tracked changes remain after committing pins.json; cannot integrate origin/$upstream_branch before push"
  fi
  if git -C "$REPO_DIR" merge-base --is-ancestor HEAD FETCH_HEAD; then
    note "Fast-forwarding local branch to origin/$upstream_branch before push..."
    git -C "$REPO_DIR" merge --ff-only FETCH_HEAD >/dev/null
    return 0
  fi

  local git_author_name git_author_email
  git_author_name="${ARCLINK_UPSTREAM_GIT_AUTHOR_NAME:-ArcLink Upgrade Bot}"
  git_author_email="${ARCLINK_UPSTREAM_GIT_AUTHOR_EMAIL:-arclink-upgrade@localhost}"
  note "Rebasing local pins commit onto origin/$upstream_branch before push..."
  if ! git -C "$REPO_DIR" \
      -c user.name="$git_author_name" \
      -c user.email="$git_author_email" \
      rebase FETCH_HEAD >/dev/null; then
    git -C "$REPO_DIR" rebase --abort >/dev/null 2>&1 || true
    fatal "could not rebase local pins commit onto origin/$upstream_branch; resolve the checkout and retry"
  fi
}

push_current_head() {
  require_upstream_push_ready
  local upstream_branch="${ARCLINK_UPSTREAM_BRANCH:-main}"
  sync_current_head_with_upstream_branch
  note "Pushing to ${ARCLINK_UPSTREAM_REPO_URL:-origin}#$upstream_branch..."
  upstream_git push origin "HEAD:$upstream_branch" >/dev/null
}

upstream_branch_contains_head() {
  if [[ -z "${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-}" || ! -f "${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-}" ]]; then
    return 0
  fi
  fetch_upstream_branch >/dev/null 2>&1 || return 1
  git -C "$REPO_DIR" merge-base --is-ancestor HEAD FETCH_HEAD
}

commit_and_push_pins() {
  local summary="$1"
  require_upstream_push_ready
  local git_author_name git_author_email
  git_author_name="${ARCLINK_UPSTREAM_GIT_AUTHOR_NAME:-ArcLink Upgrade Bot}"
  git_author_email="${ARCLINK_UPSTREAM_GIT_AUTHOR_EMAIL:-arclink-upgrade@localhost}"
  note "Committing pins.json bump..."
  git -C "$REPO_DIR" add -- config/pins.json
  if git -C "$REPO_DIR" diff --cached --quiet -- config/pins.json; then
    note "No pins.json diff to commit; pushing current HEAD."
  else
    git -C "$REPO_DIR" \
      -c user.name="$git_author_name" \
      -c user.email="$git_author_email" \
      commit -m "$summary" >/dev/null
  fi
  push_current_head
}

reexec_upgrade() {
  if [[ "${ARCLINK_COMPONENT_UPGRADE_MODE:-}" == "docker" ]]; then
    note "Re-exec ./deploy.sh docker upgrade to apply the new pin to the Docker stack..."
    exec env \
      ARCLINK_UPSTREAM_REPO_URL="${ARCLINK_UPSTREAM_REPO_URL:-}" \
      ARCLINK_UPSTREAM_BRANCH="${ARCLINK_UPSTREAM_BRANCH:-main}" \
      ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED="${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-}" \
      ARCLINK_UPSTREAM_DEPLOY_KEY_USER="${ARCLINK_UPSTREAM_DEPLOY_KEY_USER:-}" \
      ARCLINK_UPSTREAM_DEPLOY_KEY_PATH="${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-}" \
      ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE="${ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE:-}" \
      "$REPO_DIR/deploy.sh" docker upgrade
  fi

  note "Re-exec ./deploy.sh upgrade to apply the new pin to the live host..."
  exec sudo env \
    ARCLINK_CONFIG_FILE="${ARCLINK_CONFIG_FILE:-/home/arclink/arclink/arclink-priv/config/arclink.env}" \
    ARCLINK_UPSTREAM_REPO_URL="${ARCLINK_UPSTREAM_REPO_URL:-}" \
    ARCLINK_UPSTREAM_BRANCH="${ARCLINK_UPSTREAM_BRANCH:-main}" \
    ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED="${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-1}" \
    ARCLINK_UPSTREAM_DEPLOY_KEY_USER="${ARCLINK_UPSTREAM_DEPLOY_KEY_USER:-}" \
    ARCLINK_UPSTREAM_DEPLOY_KEY_PATH="${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-}" \
    ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE="${ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE:-}" \
    "$REPO_DIR/deploy.sh" --apply-upgrade
}

do_apply() {
  local name="$1" override_ref="$2" override_tag="$3" override_version="$4"
  local override_branch="$5" dry_run="$6" skip_push="$7" skip_upgrade="$8"

  local kind; kind="$(pins_kind "$name")"
  local field=""        # which pins.json field gets the new value
  local current=""      # current pinned value
  local target=""       # new value to write (empty means "no change")
  local headline=""     # human-readable summary line for commit

  case "$kind" in
    git-commit)
      field="ref"
      current="$(pins_get "$name" ref)"
      local repo branch
      repo="$(pins_get "$name" repo)"
      branch="${override_branch:-$(pins_get "$name" branch)}"
      [[ -z "$branch" ]] && branch="main"
      if [[ -n "$override_ref" ]]; then
        target="$(resolve_git_commit_ref "$repo" "$override_ref")"
        [[ -z "$target" ]] && fatal "could not resolve --ref $override_ref against $repo"
      else
        target="$(resolve_git_commit_head "$repo" "$branch")"
        [[ -z "$target" ]] && fatal "could not resolve refs/heads/$branch against $repo"
      fi
      headline="bump $name to ${target:0:12} (was ${current:0:12})"
      ;;
    git-tag)
      field="tag"
      current="$(pins_get "$name" tag)"
      target="${override_tag:-$(resolve_git_tag_latest "$(pins_get "$name" repo)")}"
      [[ -z "$target" ]] && fatal "no tag resolved; pass --tag <name>"
      headline="bump $name tag $current -> $target"
      ;;
    container-image)
      field="tag"
      current="$(pins_get "$name" tag)"
      [[ -z "$override_tag" ]] && fatal "container-image upgrades require --tag <new-tag>"
      target="$override_tag"
      headline="bump $name image tag $current -> $target"
      ;;
    npm)
      field="version"
      current="$(pins_get "$name" version)"
      target="${override_version:-$(resolve_npm_latest "$(pins_get "$name" package)")}"
      [[ -z "$target" ]] && fatal "could not resolve npm latest; pass --version <vX.Y.Z>"
      headline="bump $name version $current -> $target"
      ;;
    nvm-version)
      field="version"
      current="$(pins_get "$name" version)"
      [[ -z "$override_version" ]] && fatal "nvm-version upgrades require --version <vX.Y.Z>"
      target="$override_version"
      headline="bump $name version $current -> $target"
      ;;
    release-asset)
      field="version"
      current="$(pins_get "$name" version)"
      target="${override_version:-$(resolve_github_release_latest "$(pins_get "$name" repo)")}"
      [[ -z "$target" ]] && fatal "no release tag resolved; pass --version <tag>"
      headline="bump $name version $current -> $target"
      ;;
    installer-url|uv-python)
      fatal "$kind components are floating by design; no apply path"
      ;;
    *)
      fatal "kind $kind has no apply path wired"
      ;;
  esac

  if [[ "$current" == "$target" ]]; then
    note "$name pin already at $current — no-op."
    if [[ "$dry_run" == "1" ]]; then
      return 0
    fi
    if [[ "$skip_push" != "1" ]] && ! git -C "$REPO_DIR" diff --quiet HEAD -- config/pins.json; then
      note "pins.json already contains the target but has an uncommitted diff; committing pending bump."
      local commit_msg
      commit_msg="$(printf 'pins: ensure %s.%s at %s\n\nResolved against the upstream source declared in config/pins.json.\n' "$name" "$field" "$target")"
      commit_and_push_pins "$commit_msg"
      if [[ "$skip_upgrade" != "1" ]]; then
        reexec_upgrade
      fi
    elif [[ "$skip_push" != "1" ]] && ! upstream_branch_contains_head; then
      note "Local HEAD is not present on the configured upstream branch; pushing current HEAD."
      push_current_head
      if [[ "$skip_upgrade" != "1" ]]; then
        reexec_upgrade
      fi
    fi
    return 0
  fi

  note "Planned: $name.$field $current -> $target"

  if [[ "$dry_run" == "1" ]]; then
    note "Dry run — would write to config/pins.json (and update inheritors)."
    return 0
  fi

  if [[ "$skip_push" != "1" ]]; then
    require_upstream_push_ready
  fi

  pins_set "$name" "$field" "$target"
  if [[ -n "$override_branch" && "$kind" == "git-commit" ]]; then
    pins_set "$name" branch "$override_branch"
  fi
  write_inherited_components "$name" "$target" "$field"

  if [[ "$skip_push" != "1" ]]; then
    local commit_msg
    commit_msg="$(printf 'pins: %s\n\nResolved against the upstream source declared in config/pins.json.\n' "$headline")"
    commit_and_push_pins "$commit_msg"
  fi

  if [[ "$skip_upgrade" != "1" && "$skip_push" != "1" ]]; then
    reexec_upgrade
  fi
}

# ---------- main --------------------------------------------------------------

main() {
  local component="" subcommand=""
  local override_ref="" override_tag="" override_version="" override_branch=""
  local dry_run=0 skip_push=0 skip_upgrade=0

  while [[ $# -gt 0 ]]; do
    case "$1" in
      check|apply)     subcommand="$1"; shift ;;
      --ref)           override_ref="$2"; shift 2 ;;
      --tag)           override_tag="$2"; shift 2 ;;
      --version)       override_version="$2"; shift 2 ;;
      --branch)        override_branch="$2"; shift 2 ;;
      --dry-run)       dry_run=1; shift ;;
      --skip-push)     skip_push=1; shift ;;
      --skip-upgrade)  skip_upgrade=1; shift ;;
      -h|--help)       usage; exit 0 ;;
      -*)              fatal "unknown arg: $1" ;;
      *)               if [[ -z "$component" ]]; then component="$1"; shift
                       else fatal "unexpected positional: $1"; fi ;;
    esac
  done

  [[ -z "$component" || -z "$subcommand" ]] && { usage >&2; exit 1; }
  pins_require
  if [[ -z "$(pins_kind "$component")" ]]; then
    fatal "no component named '$component' in $ARCLINK_PINS_FILE"
  fi

  case "$subcommand" in
    check) do_check "$component" ;;
    apply) do_apply "$component" "$override_ref" "$override_tag" "$override_version" "$override_branch" "$dry_run" "$skip_push" "$skip_upgrade" ;;
  esac
}

main "$@"
