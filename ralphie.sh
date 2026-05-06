#!/usr/bin/env bash
#
# Ralphie - Unified autonomous loop for Codex and Claude Code.
# One script handles first-run setup, prompt generation, and iterative execution.
#

# Stream bootstrap:
# When executed via stdin (for example: curl ... | bash), persist the script into
# the current directory and re-exec from disk so relative paths work consistently.
if [ "${RALPHIE_LIB:-0}" != "1" ] && [ -z "${BASH_SOURCE[0]:-}" ]; then
    rb_target_script="$(pwd)/ralphie.sh"
    rb_tmp_script="${rb_target_script}.tmp.$$"
    if {
        printf '%s\n' '#!/usr/bin/env bash'
        printf '%s\n' '#'
        printf '%s\n' '# Ralphie - Unified autonomous loop for Codex and Claude Code.'
        printf '%s\n' '# Installed from stdin stream.'
        printf '%s\n' '#'
        cat
    } > "$rb_tmp_script"; then
        chmod +x "$rb_tmp_script" 2>/dev/null || true
        mv "$rb_tmp_script" "$rb_target_script"
        echo "Installed ralphie.sh to $rb_target_script"
        exec env RALPHIE_SKIP_AUTO_UPDATE=1 "$rb_target_script" "$@"
    else
        echo "Failed to persist streamed ralphie.sh to $rb_target_script" >&2
        rm -f "$rb_tmp_script"
        exit 1
    fi
fi

set -euo pipefail

SCRIPT_VERSION="2.0.0"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"

CONFIG_DIR="$PROJECT_DIR/.ralphie"
CONFIG_FILE="$CONFIG_DIR/config.env"
LOCK_FILE="$CONFIG_DIR/run.lock"
REASON_LOG_FILE="$CONFIG_DIR/reasons.log"
NOTIFICATION_LOG_FILE="$CONFIG_DIR/notifications.log"
GATE_FEEDBACK_FILE="$CONFIG_DIR/last_gate_feedback.md"
STATE_FILE="$CONFIG_DIR/state.env"
SPECIFY_DIR="$PROJECT_DIR/.specify/memory"
CONSTITUTION_FILE="$SPECIFY_DIR/constitution.md"
SPECS_DIR="$PROJECT_DIR/specs"
RESEARCH_DIR="$PROJECT_DIR/research"
RESEARCH_SUMMARY_FILE="$RESEARCH_DIR/RESEARCH_SUMMARY.md"
STACK_SNAPSHOT_FILE="$RESEARCH_DIR/STACK_SNAPSHOT.md"
CONSENSUS_DIR="$PROJECT_DIR/consensus"
LOG_DIR="$PROJECT_DIR/logs"
COMPLETION_LOG_DIR="$PROJECT_DIR/completion_log"
MARKDOWN_REPAIR_ARTIFACT_DIR="$LOG_DIR/markdown-repair"
MAPS_DIR="$PROJECT_DIR/maps"
SUBREPOS_DIR_REL="subrepos"
AGENT_SOURCE_MAP_REL="maps/agent-source-map.yaml"
BINARY_STEERING_MAP_REL="maps/binary-steering-map.yaml"
SELF_IMPROVEMENT_LOG_REL="research/SELF_IMPROVEMENT_LOG.md"
SUBREPOS_DIR="$PROJECT_DIR/$SUBREPOS_DIR_REL"
AGENT_SOURCE_MAP_FILE="$PROJECT_DIR/$AGENT_SOURCE_MAP_REL"
BINARY_STEERING_MAP_FILE="$PROJECT_DIR/$BINARY_STEERING_MAP_REL"
SELF_IMPROVEMENT_LOG_FILE="$PROJECT_DIR/$SELF_IMPROVEMENT_LOG_REL"
READY_ARCHIVE_DIR="$CONFIG_DIR/ready-archives"
SETUP_SUBREPOS_SCRIPT="$PROJECT_DIR/engines/setup-agent-subrepos.sh"

PROMPT_BUILD_FILE="$PROJECT_DIR/PROMPT_build.md"
PROMPT_PLAN_FILE="$PROJECT_DIR/PROMPT_plan.md"
PROMPT_TEST_FILE="$PROJECT_DIR/PROMPT_test.md"
PROMPT_REFACTOR_FILE="$PROJECT_DIR/PROMPT_refactor.md"
PROMPT_LINT_FILE="$PROJECT_DIR/PROMPT_lint.md"
PROMPT_DOCUMENT_FILE="$PROJECT_DIR/PROMPT_document.md"
PLAN_FILE="$PROJECT_DIR/IMPLEMENTATION_PLAN.md"
PROJECT_BOOTSTRAP_FILE="$CONFIG_DIR/project-bootstrap.md"
PROJECT_GOALS_FILE="$CONFIG_DIR/project-goals.md"
SESSION_CHANGED_PATHS_FILE="$CONFIG_DIR/session-changed-paths.txt"

# Shared logic for interactive questions and formatting.
err() { echo -e "\033[1;31m$*\033[0m" >&2; }
warn() { echo -e "\033[1;33m$*\033[0m" >&2; }
info() { echo -e "\033[0;34m$*\033[0m"; }
success() { echo -e "\033[0;32m$*\033[0m"; }
ok() { success "$@"; }

# Logging reasons for failures (doctrinal/state/inference)
log_reason_code() {
    local code="$1"
    local msg="$2"
    mkdir -p "$(dirname "$REASON_LOG_FILE")"
    echo "reason_code=$code message=\"$msg\"" >> "$REASON_LOG_FILE"
}

path_for_display() {
    local p="${1:-}"
    [ -z "$p" ] && echo "unknown" && return 0
    echo "${p#./}"
}

redact_endpoint_for_log() {
    local endpoint="${1:-}"
    if [ -z "$endpoint" ]; then
        echo "<default>"
        return 0
    fi

    # Keep logs safe: show protocol + host[:port] only, strip userinfo/path/query.
    if [[ "$endpoint" =~ ^[A-Za-z][A-Za-z0-9+.-]*:// ]]; then
        local scheme rest host
        scheme="${endpoint%%://*}://"
        rest="${endpoint#*://}"
        rest="${rest#*@}"
        rest="${rest%%/*}"
        rest="${rest%%\?*}"
        rest="${rest%%\#*}"
        host="$rest"
        if [ -n "$host" ]; then
            echo "${scheme}${host}"
            return 0
        fi
    fi

    echo "<custom-set>"
}

redact_secret_for_log() {
    local value="${1:-}"
    if [ -z "$value" ]; then
        echo "<unset>"
        return 0
    fi
    echo "<set:${#value} chars>"
}

json_escape_string() {
    local value="${1:-}"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//$'\n'/\\n}"
    value="${value//$'\r'/\\r}"
    value="${value//$'\t'/\\t}"
    printf '%s' "$value"
}

# Boolean helper
is_true() {
    case "${1:-}" in
        1|[Yy]|[Yy][Ee][Ss]|[Tt][Rr][Uu][Ee]|ON|on) return 0 ;;
        *) return 1 ;;
    esac
}

is_bool_like() {
    case "${1:-}" in
        true|TRUE|True|false|FALSE|False|1|0|yes|YES|no|NO|on|ON|off|OFF|y|Y|n|N) return 0 ;;
        *) return 1 ;;
    esac
}

is_number() {
    [[ "$1" =~ ^[0-9]+$ ]]
}

sanitize_text_for_log() {
    local value="${1:-}"
    value="$(printf '%s' "$value" | LC_ALL=C tr -d '\000-\010\013\014\016-\037\177')"
    value="$(printf '%s' "$value" | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g' | sed 's/^ *//; s/ *$//')"
    printf '%s' "$value"
}

sanitize_review_score() {
    local score="${1:-}"
    if ! is_number "$score"; then
        echo 0
        return 0
    fi
    if [ "$score" -gt 100 ]; then
        echo 0
        return 0
    fi
    echo "$score"
}

is_decimal_number() {
    [[ "${1:-}" =~ ^[0-9]+([.][0-9]+)?$ ]]
}

version_score_from_text() {
    local text="${1:-}"
    local major=0
    local minor=0
    local patch=0

    if [[ "$text" =~ ([0-9]+)[.]([0-9]+)[.]([0-9]+) ]]; then
        major="${BASH_REMATCH[1]}"
        minor="${BASH_REMATCH[2]}"
        patch="${BASH_REMATCH[3]}"
    fi

    echo $((major * 1000000 + minor * 1000 + patch))
}

discover_versioned_command_default() {
    local command_name="$1"
    shift
    local -a candidates=()
    local candidate resolved version score
    local best_cmd="$command_name"
    local best_score=-1
    local seen_paths=$'\n'

    while IFS= read -r candidate; do
        [ -n "$candidate" ] && candidates+=("$candidate")
    done < <(type -a -p "$command_name" 2>/dev/null || true)

    for candidate in "$@"; do
        [ -n "$candidate" ] && candidates+=("$candidate")
    done
    candidates+=("$command_name")

    for candidate in "${candidates[@]}"; do
        if [ "$candidate" = "$command_name" ]; then
            resolved="$(command -v "$command_name" 2>/dev/null || true)"
        else
            resolved="$candidate"
        fi
        [ -n "$resolved" ] || continue
        case "$seen_paths" in
            *$'\n'"$resolved"$'\n'*) continue ;;
        esac
        seen_paths="${seen_paths}${resolved}"$'\n'
        [ -x "$resolved" ] || continue

        version="$("$resolved" --version 2>/dev/null | head -n 1 || true)"
        score="$(version_score_from_text "$version")"
        if [ "$score" -gt "$best_score" ]; then
            best_cmd="$resolved"
            best_score="$score"
        fi
    done

    echo "$best_cmd"
}

discover_codex_command_default() {
    discover_versioned_command_default \
        "codex" \
        "/opt/homebrew/bin/codex" \
        "/usr/local/bin/codex" \
        "${HOME:-}/.local/bin/codex"
}

discover_claude_command_default() {
    discover_versioned_command_default \
        "claude" \
        "${HOME:-}/.local/bin/claude" \
        "/opt/homebrew/bin/claude" \
        "/usr/local/bin/claude"
}

extract_xml_value() {
    local file="$1"
    local tag="$2"
    local default="${3:-}"
    local value=""

    [ -f "$file" ] || { echo "$default"; return 0; }

    value="$(
        awk -v tag="$tag" '
            BEGIN {
                open_tag = "<" tag ">"
                close_tag = "</" tag ">"
                in_tag = 0
                current = ""
                last = ""
            }
            {
                line = $0
                while (length(line) > 0) {
                    if (!in_tag) {
                        start = index(line, open_tag)
                        if (start == 0) {
                            break
                        }
                        line = substr(line, start + length(open_tag))
                        current = ""
                        in_tag = 1
                    }

                    stop = index(line, close_tag)
                    if (stop > 0) {
                        current = current substr(line, 1, stop - 1)
                        last = current
                        line = substr(line, stop + length(close_tag))
                        current = ""
                        in_tag = 0
                    } else {
                        current = current line "\n"
                        break
                    }
                }
            }
            END {
                if (last != "") {
                    printf "%s", last
                }
            }
        ' "$file" 2>/dev/null
    )"
    value="$(sanitize_text_for_log "$value")"
    if [ -z "$value" ]; then
        echo "$default"
        return 0
    fi
    echo "$value"
}

extract_review_score() {
    local file="$1"
    local score
    score="$(extract_xml_value "$file" "score" "")"
    if ! is_number "$score"; then
        score=0
    fi
    sanitize_review_score "$score"
}

extract_review_verdict() {
    local file="$1"
    local verdict
    verdict="$(extract_xml_value "$file" "verdict" "")"
    case "$verdict" in
        GO|HOLD)
            echo "$verdict"
            return 0
            ;;
    esac

    verdict="$(extract_xml_value "$file" "decision" "")"
    case "$verdict" in
        GO|HOLD) echo "$verdict" ;;
        *) echo "HOLD" ;;
    esac
}

extract_review_gaps() {
    local file="$1"
    local limit="${2:-180}"
    local gaps
    gaps="$(extract_xml_value "$file" "gaps" "")"
    gaps="$(sanitize_text_for_log "$gaps" | cut -c 1-"$limit")"
    [ -n "$gaps" ] || gaps="no explicit gaps"
    echo "$gaps"
}

file_looks_like_auth_or_html_challenge() {
    local file="$1"
    [ -f "$file" ] || return 1
    grep -qiE '<!doctype html|<html[ >]|</html>|cloudflare|cf_chl|challenge-platform|enable javascript and cookies|authrequired|missing or invalid access token|invalid_token' "$file" 2>/dev/null
}

review_output_invalid_reason() {
    local file="$1"
    local mode="${2:-consensus}"
    local score verdict next_phase

    [ -s "$file" ] || { echo "missing reviewer output"; return 0; }

    if file_looks_like_auth_or_html_challenge "$file"; then
        echo "provider auth/challenge HTML or token error"
        return 0
    fi

    score="$(extract_xml_value "$file" "score" "")"
    if ! is_number "$score" || [ "$score" -gt 100 ]; then
        echo "missing or invalid <score>"
        return 0
    fi

    verdict="$(extract_xml_value "$file" "verdict" "")"
    case "$verdict" in
        GO|HOLD) : ;;
        *)
            echo "missing or invalid <verdict>"
            return 0
            ;;
    esac

    if [ "$mode" != "handoff" ]; then
        next_phase="$(extract_xml_value "$file" "next_phase" "")"
        next_phase="$(to_lower "$next_phase")"
        if ! is_phase_or_done "$next_phase"; then
            echo "missing or invalid <next_phase>"
            return 0
        fi
    fi

    echo ""
}

write_invalid_reviewer_output_placeholder() {
    local output_file="$1"
    local reason="$2"
    local raw_file="$3"

    reason="$(sanitize_text_for_log "$reason")"
    {
        echo "Reviewer output was rejected by Ralphie before consensus parsing."
        echo "reason: ${reason:-invalid reviewer output}"
        if [ -n "$raw_file" ]; then
            echo "raw_output_artifact: $(path_for_display "$raw_file")"
        fi
        echo "The raw output was not used for score, verdict, or phase routing."
    } > "$output_file"
}

safe_print_file_head() {
    local file="$1"
    local lines="${2:-80}"
    is_number "$lines" || lines=80
    if [ ! -f "$file" ]; then
        echo "- not available"
        return 0
    fi
    if file_looks_like_auth_or_html_challenge "$file"; then
        echo "- redacted: provider auth/challenge HTML or token-error output"
        return 0
    fi
    sed -n "1,${lines}p" "$file"
}

safe_print_file_tail() {
    local file="$1"
    local lines="${2:-40}"
    is_number "$lines" || lines=40
    if [ ! -f "$file" ]; then
        echo "- not available"
        return 0
    fi
    if file_looks_like_auth_or_html_challenge "$file"; then
        echo "- redacted: provider auth/challenge HTML or token-error output"
        return 0
    fi
    tail -n "$lines" "$file"
}

stream_engine_output() {
    local log_file="$1"
    local output_file="${2:-}"
    local stdout_enabled="${3:-true}"

    if [ -n "$output_file" ]; then
        : > "$output_file"
    fi

    awk -v log_file="$log_file" -v output_file="$output_file" -v stdout_enabled="$stdout_enabled" '
        function emit(line) {
            if (stdout_enabled == "true") {
                print line
            }
            print line >> log_file
            if (output_file != "") {
                print line >> output_file
            }
            if (stdout_enabled == "true") {
                fflush()
            }
            fflush(log_file)
            if (output_file != "") {
                fflush(output_file)
            }
        }
        function clear_buffer() {
            buffer_count = 0
        }
        function flush_buffer(    i) {
            for (i = 1; i <= buffer_count; i++) {
                emit(buffer[i])
            }
            clear_buffer()
        }
        function push_buffer(line,    i) {
            buffer_count++
            buffer[buffer_count] = line
            if (buffer_count > max_buffer) {
                emit(buffer[1])
                for (i = 1; i < buffer_count; i++) {
                    buffer[i] = buffer[i + 1]
                }
                buffer_count--
            }
        }
        function looks_like_challenge(line) {
            lower = tolower(line)
            return lower ~ /<!doctype html|<html[ >]|<\/html>|cloudflare|cf_chl|challenge-platform|challenge-error-text|enable javascript and cookies|auth required|missing or invalid access token|invalid_token|window\._cf_chl_opt|cdn-cgi\/challenge/
        }
        function looks_like_engine_reentry(line) {
            return line ~ /^(OpenAI Codex|Claude|workdir:|model:|provider:|approval:|sandbox:|reasoning effort:|reasoning summaries:|session id:|tokens used|--------)/
        }
        BEGIN {
            max_buffer = 80
            buffer_count = 0
            redacting = 0
            redacting_count = 0
            redacted_once = 0
        }
        {
            lower = tolower($0)
            if (redacting) {
                if (lower ~ /<\/html>/) {
                    redacting = 0
                    redacting_count = 0
                    next
                }
                if (looks_like_engine_reentry($0)) {
                    redacting = 0
                    redacting_count = 0
                    push_buffer($0)
                    next
                }
                redacting_count++
                if (redacting_count % 80 == 0) {
                    emit("[ralphie still redacting provider auth/challenge output]")
                }
                next
            }
            if (looks_like_challenge($0)) {
                clear_buffer()
                if (!redacted_once) {
                    emit("[ralphie redacted provider auth/challenge output]")
                    redacted_once = 1
                }
                if (lower !~ /<\/html>/) {
                    redacting = 1
                    redacting_count = 0
                }
                next
            }
            push_buffer($0)
        }
        END {
            if (!redacting) {
                flush_buffer()
            }
        }
    '
}

is_phase_or_done() {
    case "$1" in
        plan|build|test|refactor|lint|document|done) return 0 ;;
        *) return 1 ;;
    esac
}

normalize_phase_name() {
    local phase="${1:-}"
    phase="$(to_lower "$phase")"
    case "$phase" in
        plan) phase="plan" ;;
        build) phase="build" ;;
        test) phase="test" ;;
        refactor) phase="refactor" ;;
        lint) phase="lint" ;;
        document) phase="document" ;;
        done) phase="done" ;;
        *)
            warn "Unrecognized phase name '$phase', defaulting to 'plan'"
            phase="plan"
            ;;
    esac
    echo "$phase"
}

normalize_next_phase_recommendation() {
    local candidate="${1:-}"
    local current_phase="${2:-}"
    local fallback="${3:-done}"

    candidate="$(to_lower "$candidate")"
    current_phase="$(normalize_phase_name "$current_phase")"

    case "$candidate" in
        plan|build|test|refactor|lint|document|done) echo "$candidate" ; return 0 ;;
        next|forward|proceed|continue) echo "$fallback" ; return 0 ;;
        same|retry|retry_current|hold|stay) echo "$current_phase" ; return 0 ;;
        complete|completed|finished|finish|success|goal) echo "done" ; return 0 ;;
        stop|abort|halt) echo "done" ; return 0 ;;
        *)
            echo "$fallback"
            return 1
            ;;
    esac
}

print_array_lines() {
    local -a lines=("$@")
    local line

    [ "${#lines[@]}" -eq 0 ] && return 0
    [ "${#lines[@]}" -eq 1 ] && [ -z "${lines[0]}" ] && return 0
    for line in "${lines[@]}"; do
        printf '%s\n' "$line"
    done
}

# Compatibility layer for environments that still run Bash 3.x (for example, macOS
# default Bash), which lack the `mapfile` builtin used throughout this script.
if ! command -v mapfile >/dev/null 2>&1; then
    mapfile() {
        if [[ "${1:-}" == -t ]]; then
            shift
        fi

        local var_name="${1:-MAPFILE}"
        if [ -z "$var_name" ]; then
            return 1
        fi
        if [[ ! "$var_name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
            return 1
        fi

        # Safer alternative to eval: use nameref if available (Bash 4.3+),
        # otherwise fall back to a temp file approach
        local __mapfile_idx=0
        local __mapfile_line
        local __mapfile_escaped
        # Reset the target array
        eval "${var_name}=()"

        while IFS= read -r __mapfile_line || [ -n "$__mapfile_line" ]; do
            # Use printf %q for safe escaping of arbitrary content
            printf -v __mapfile_escaped '%q' "$__mapfile_line" 2>/dev/null || __mapfile_escaped="$__mapfile_line"
            eval "${var_name}[${__mapfile_idx}]=${__mapfile_escaped}"
            __mapfile_idx=$((__mapfile_idx + 1))
        done

        return 0
    }
fi

is_phase_noop_policy() {
    case "${1:-}" in
        hard|soft|none) return 0 ;;
        *) return 1 ;;
    esac
}

normalize_phase_noop_policy() {
    local policy="${1:-none}"
    case "$policy" in
        hard|soft|none) echo "$policy" ;;
        *) echo "none" ;;
    esac
}

is_phase_manifest_mode() {
    case "$(to_lower "${1:-}")" in
        light|deep) return 0 ;;
        *) return 1 ;;
    esac
}

normalize_phase_manifest_mode() {
    local mode
    mode="$(to_lower "${1:-$DEFAULT_PHASE_MANIFEST_MODE}")"
    case "$mode" in
        light|deep) echo "$mode" ;;
        *)
            warn "Invalid PHASE_MANIFEST_MODE '$mode'. Falling back to '$DEFAULT_PHASE_MANIFEST_MODE'."
            echo "$DEFAULT_PHASE_MANIFEST_MODE"
            ;;
    esac
}

to_lower() {
    echo "$1" | tr '[:upper:]' '[:lower:]'
}

awk_regex_is_valid() {
    local regex="${1:-}"
    [ -z "$regex" ] && return 0
    awk -v re="$regex" 'BEGIN { if ("" ~ re) { } }' >/dev/null 2>&1
}

is_allowed_config_key() {
    local key="${1:-}"
    case "$key" in
        # Preferred, namespaced settings surface.
        RALPHIE_*)
            return 0
            ;;
        # Explicitly supported non-prefixed compatibility keys.
        COMMAND_TIMEOUT_SECONDS|MAX_ITERATIONS|MAX_SESSION_CYCLES|YOLO|AUTO_UPDATE|AUTO_UPDATE_URL|\
        AUTO_UPDATE_ALLOW_DIRTY|AUTO_UPDATE_ALLOW_INSECURE|AUTO_UPDATE_TIMEOUT_SECONDS|AUTO_UPDATE_LOCK_TIMEOUT_SECONDS|\
        SWARM_MAX_PARALLEL|CONFIDENCE_TARGET|CONFIDENCE_STAGNATION_LIMIT|\
        AUTO_PLAN_BACKFILL_ON_IDLE_BUILD|AUTO_ENGINE_PREFERENCE|AUTO_INIT_GIT_IF_MISSING|\
        AUTO_COMMIT_ON_PHASE_PASS|CODEX_ENDPOINT|CODEX_USE_RESPONSES_SCHEMA|\
        CODEX_RESPONSES_SCHEMA_FILE|CODEX_THINKING_OVERRIDE|CLAUDE_ENDPOINT|CLAUDE_THINKING_OVERRIDE|\
        RUN_AGENT_MAX_ATTEMPTS|RUN_AGENT_RETRY_DELAY_SECONDS|RUN_AGENT_RETRY_VERBOSE|\
        ENGINE_OUTPUT_TO_STDOUT|ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS|STRICT_VALIDATION_NOOP|PHASE_COMPLETION_MAX_ATTEMPTS|\
        PHASE_COMPLETION_RETRY_DELAY_SECONDS|PHASE_COMPLETION_RETRY_VERBOSE|\
        MAX_CONSENSUS_ROUTING_ATTEMPTS|REQUIRE_LINT_BEFORE_DONE|REQUIRE_DOCUMENT_BEFORE_DONE|\
        REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE|REQUIRE_PLAN_FRESHNESS_FOR_BUILD|BACKLOG_SOURCES|\
        PHASE_NOOP_POLICY_PLAN|PHASE_NOOP_POLICY_BUILD|\
        PHASE_NOOP_POLICY_TEST|PHASE_NOOP_POLICY_REFACTOR|PHASE_NOOP_POLICY_LINT|\
        PHASE_NOOP_POLICY_DOCUMENT|PHASE_NOOP_PROFILE|SESSION_TOKEN_BUDGET|\
        SESSION_TOKEN_RATE_CENTS_PER_MILLION|SESSION_COST_BUDGET_CENTS|AUTO_REPAIR_MARKDOWN_ARTIFACTS|\
        AUTO_REPAIR_MARKDOWN_DRY_RUN|AUTO_REPAIR_MARKDOWN_BACKUP|AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED|\
        MARKDOWN_LOCAL_PATH_ALLOWLIST_REGEX|PHASE_MANIFEST_MODE|\
        SWARM_CONSENSUS_TIMEOUT|CONSENSUS_SCORE_THRESHOLD|ENGINE_HEALTH_MAX_ATTEMPTS|\
        ENGINE_HEALTH_RETRY_DELAY_SECONDS|ENGINE_HEALTH_RETRY_VERBOSE|ENGINE_SMOKE_TEST_TIMEOUT|\
        STARTUP_OPERATIONAL_PROBE|ENGINE_OVERRIDES_BOOTSTRAPPED|NOTIFICATIONS_ENABLED|\
        NOTIFY_TELEGRAM_ENABLED|NOTIFY_DISCORD_ENABLED|NOTIFY_DISCORD_WEBHOOK_URL|\
        NOTIFY_TTS_ENABLED|NOTIFY_TTS_STYLE|NOTIFY_CHUTES_TTS_URL|NOTIFY_CHUTES_VOICE|NOTIFY_CHUTES_SPEED|\
        NOTIFY_EVENT_DEDUP_WINDOW_SECONDS|NOTIFY_INCIDENT_REMINDER_MINUTES|\
        NOTIFICATION_WIZARD_BOOTSTRAPPED|TG_BOT_TOKEN|TG_CHAT_ID|CHUTES_API_KEY|\
        CODEX_ENGINE_CMD|CLAUDE_ENGINE_CMD|CODEX_MODEL|CLAUDE_MODEL|PHASE_WALLCLOCK_LIMIT_SECONDS)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

mark_phase_noop_policy_explicit_by_key() {
    case "${1:-}" in
        PHASE_NOOP_POLICY_PLAN|RALPHIE_PHASE_NOOP_POLICY_PLAN) PHASE_NOOP_POLICY_PLAN_EXPLICIT=true ;;
        PHASE_NOOP_POLICY_BUILD|RALPHIE_PHASE_NOOP_POLICY_BUILD) PHASE_NOOP_POLICY_BUILD_EXPLICIT=true ;;
        PHASE_NOOP_POLICY_TEST|RALPHIE_PHASE_NOOP_POLICY_TEST) PHASE_NOOP_POLICY_TEST_EXPLICIT=true ;;
        PHASE_NOOP_POLICY_REFACTOR|RALPHIE_PHASE_NOOP_POLICY_REFACTOR) PHASE_NOOP_POLICY_REFACTOR_EXPLICIT=true ;;
        PHASE_NOOP_POLICY_LINT|RALPHIE_PHASE_NOOP_POLICY_LINT) PHASE_NOOP_POLICY_LINT_EXPLICIT=true ;;
        PHASE_NOOP_POLICY_DOCUMENT|RALPHIE_PHASE_NOOP_POLICY_DOCUMENT) PHASE_NOOP_POLICY_DOCUMENT_EXPLICIT=true ;;
        *) ;;
    esac
}

# Portable pseudo-random number (0..32767). Uses $RANDOM when available (interactive
# bash), falls back to /dev/urandom or PID-seeded arithmetic for non-interactive shells.
portable_random() {
    if [ -n "${RANDOM+x}" ]; then
        echo "$RANDOM"
    elif [ -n "${BASH_VERSION:-}" ]; then
        # In some shells $RANDOM may appear unset until first use.
        # Force initialization once, then use it.
        : "${RANDOM:=0}"
        echo "$RANDOM"
    elif [ -r /dev/urandom ]; then
        od -An -tu2 -N2 /dev/urandom 2>/dev/null | tr -d ' \n' || echo 0
    else
        # Last resort: deterministic but varies per PID and second
        echo $(( ($$ * $(date +%s)) % 32768 ))
    fi
}

load_config_file_safe() {
    local file="$1"
    local file_display
    local line
    local key
    local raw_value
    local value
    local line_no=0

    [ -f "$file" ] || return 0
    file_display="$(path_for_display "$file")"

    while IFS= read -r line || [ -n "$line" ]; do
        line_no=$((line_no + 1))
        line="$(printf '%s' "$line" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
        [ -z "$line" ] && continue
        [[ "$line" == \#* ]] && continue

        if [[ ! "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            warn "Skipping invalid config line $line_no in $file_display: $line"
            continue
        fi

        key="${BASH_REMATCH[1]}"
        raw_value="${BASH_REMATCH[2]}"
        raw_value="$(printf '%s' "$raw_value" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"

        # Backward-compatibility aliases for legacy config keys.
        case "$key" in
            AUTO_UPDATE_ENABLED) key="AUTO_UPDATE" ;;
            AUTO_PREPARE_BACKFILL_ON_IDLE_BUILD) key="AUTO_PLAN_BACKFILL_ON_IDLE_BUILD" ;;
        esac

        # Prevent config files from mutating critical shell interpreter behavior.
        case "$key" in
            BASH_ENV|ENV|SHELLOPTS|BASHOPTS|BASH_XTRACEFD|IFS|PATH|CDPATH|GLOBIGNORE|PROMPT_COMMAND|PS4)
                warn "Ignoring unsafe config key '$key' in $file_display."
                continue
                ;;
        esac
        if ! is_allowed_config_key "$key"; then
            warn "Ignoring unsupported config key '$key' in $file_display."
            continue
        fi
        # Preserve exported environment precedence over config file values.
        # This keeps layering deterministic: defaults -> config.env -> env -> CLI.
        if printenv "$key" >/dev/null 2>&1; then
            continue
        fi

        # For unquoted values, allow trailing comments using '#'.
        if [[ ! "$raw_value" =~ ^\".*\"$ ]] && [[ ! "$raw_value" =~ ^\'.*\'$ ]]; then
            # Strip inline comments only when '#' is preceded by whitespace,
            # preserving literal '#' in tokens (for example API keys/URLs).
            raw_value="$(printf '%s' "$raw_value" | sed 's/[[:space:]]#.*$//; s/[[:space:]]*$//')"
        fi

        value="$raw_value"
        if [[ "$value" =~ ^\".*\"$ ]] && [ "${#value}" -ge 2 ]; then
            value="${value:1:${#value}-2}"
            value="${value//\\\"/\"}"
            value="${value//\\\\/\\}"
        elif [[ "$value" =~ ^\'.*\'$ ]] && [ "${#value}" -ge 2 ]; then
            value="${value:1:${#value}-2}"
        fi

        # Literal assignment (no command or parameter expansion).
        if ! printf -v "$key" '%s' "$value" 2>/dev/null; then
            warn "Ignoring config key '$key' in $file_display: assignment failed (readonly or invalid target)."
            continue
        fi
        mark_phase_noop_policy_explicit_by_key "$key"
    done < "$file"
}

config_escape_double_quotes() {
    local value="${1:-}"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//$'\n'/\\n}"
    value="${value//$'\r'/\\r}"
    value="${value//$'\t'/\\t}"
    printf '%s' "$value"
}

upsert_config_env_value() {
    local key="$1"
    local value="${2:-}"
    local escaped
    local tmp_config_file

    if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
        warn "Refusing to persist invalid config key '$key'."
        return 1
    fi
    if ! is_allowed_config_key "$key"; then
        warn "Refusing to persist unsupported config key '$key'."
        return 1
    fi

    mkdir -p "$(dirname "$CONFIG_FILE")"
    touch "$CONFIG_FILE"
    escaped="$(config_escape_double_quotes "$value")"
    tmp_config_file="$(mktemp "$CONFIG_DIR/config-upsert.XXXXXX")" || return 1

    if ! awk -v key="$key" -v value="$escaped" '
        BEGIN {
            found=0
        }
        {
            if ($0 ~ /^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=/) {
                line=$0
                sub(/^[[:space:]]*/, "", line)
                split(line, parts, "=")
                if (parts[1] == key) {
                    print key "=\"" value "\""
                    found=1
                    next
                }
            }
            print
        }
        END {
            if (!found) {
                print key "=\"" value "\""
            }
        }
    ' "$CONFIG_FILE" > "$tmp_config_file"; then
        rm -f "$tmp_config_file"
        return 1
    fi

    if ! mv "$tmp_config_file" "$CONFIG_FILE"; then
        rm -f "$tmp_config_file"
        return 1
    fi
    return 0
}

normalize_phase_noop_profile() {
    local profile="${1:-balanced}"
    case "$profile" in
        strict|balanced|custom) ;;
        read-only-first|read_only_first|readonly)
            profile="read-only-first"
            ;;
        *) profile="custom" ;;
    esac
    echo "$profile"
}

is_phase_noop_profile() {
    case "${1:-}" in
        strict|balanced|read-only-first|read_only_first|readonly|custom) return 0 ;;
        *) return 1 ;;
    esac
}

apply_phase_noop_profile() {
    local profile
    profile="$(normalize_phase_noop_profile "$PHASE_NOOP_PROFILE")"
    PHASE_NOOP_PROFILE="$profile"

    case "$profile" in
        strict)
            [ "$PHASE_NOOP_POLICY_PLAN_EXPLICIT" != "true" ] && PHASE_NOOP_POLICY_PLAN="hard"
            [ "$PHASE_NOOP_POLICY_BUILD_EXPLICIT" != "true" ] && PHASE_NOOP_POLICY_BUILD="hard"
            [ "$PHASE_NOOP_POLICY_TEST_EXPLICIT" != "true" ] && PHASE_NOOP_POLICY_TEST="hard"
            [ "$PHASE_NOOP_POLICY_REFACTOR_EXPLICIT" != "true" ] && PHASE_NOOP_POLICY_REFACTOR="hard"
            [ "$PHASE_NOOP_POLICY_LINT_EXPLICIT" != "true" ] && PHASE_NOOP_POLICY_LINT="hard"
            [ "$PHASE_NOOP_POLICY_DOCUMENT_EXPLICIT" != "true" ] && PHASE_NOOP_POLICY_DOCUMENT="hard"
            ;;
        read-only-first|read_only_first|readonly)
            [ "$PHASE_NOOP_POLICY_PLAN_EXPLICIT" != "true" ] && PHASE_NOOP_POLICY_PLAN="none"
            [ "$PHASE_NOOP_POLICY_BUILD_EXPLICIT" != "true" ] && PHASE_NOOP_POLICY_BUILD="hard"
            [ "$PHASE_NOOP_POLICY_TEST_EXPLICIT" != "true" ] && PHASE_NOOP_POLICY_TEST="soft"
            [ "$PHASE_NOOP_POLICY_REFACTOR_EXPLICIT" != "true" ] && PHASE_NOOP_POLICY_REFACTOR="none"
            [ "$PHASE_NOOP_POLICY_LINT_EXPLICIT" != "true" ] && PHASE_NOOP_POLICY_LINT="soft"
            [ "$PHASE_NOOP_POLICY_DOCUMENT_EXPLICIT" != "true" ] && PHASE_NOOP_POLICY_DOCUMENT="none"
            ;;
        balanced|custom|"")
            [ "$PHASE_NOOP_POLICY_PLAN_EXPLICIT" != "true" ] && PHASE_NOOP_POLICY_PLAN="none"
            [ "$PHASE_NOOP_POLICY_BUILD_EXPLICIT" != "true" ] && PHASE_NOOP_POLICY_BUILD="hard"
            [ "$PHASE_NOOP_POLICY_TEST_EXPLICIT" != "true" ] && PHASE_NOOP_POLICY_TEST="soft"
            [ "$PHASE_NOOP_POLICY_REFACTOR_EXPLICIT" != "true" ] && PHASE_NOOP_POLICY_REFACTOR="hard"
            [ "$PHASE_NOOP_POLICY_LINT_EXPLICIT" != "true" ] && PHASE_NOOP_POLICY_LINT="hard"
            [ "$PHASE_NOOP_POLICY_DOCUMENT_EXPLICIT" != "true" ] && PHASE_NOOP_POLICY_DOCUMENT="soft"
            ;;
        *)
            :
            ;;
    esac

    PHASE_NOOP_POLICY_PLAN="$(normalize_phase_noop_policy "$PHASE_NOOP_POLICY_PLAN")"
    PHASE_NOOP_POLICY_BUILD="$(normalize_phase_noop_policy "$PHASE_NOOP_POLICY_BUILD")"
    PHASE_NOOP_POLICY_TEST="$(normalize_phase_noop_policy "$PHASE_NOOP_POLICY_TEST")"
    PHASE_NOOP_POLICY_REFACTOR="$(normalize_phase_noop_policy "$PHASE_NOOP_POLICY_REFACTOR")"
    PHASE_NOOP_POLICY_LINT="$(normalize_phase_noop_policy "$PHASE_NOOP_POLICY_LINT")"
    PHASE_NOOP_POLICY_DOCUMENT="$(normalize_phase_noop_policy "$PHASE_NOOP_POLICY_DOCUMENT")"
}

finalize_phase_noop_profile_config() {
    PHASE_NOOP_PROFILE="${PHASE_NOOP_PROFILE:-$DEFAULT_PHASE_NOOP_PROFILE}"
    PHASE_NOOP_POLICY_PLAN="${PHASE_NOOP_POLICY_PLAN:-$DEFAULT_PHASE_NOOP_POLICY_PLAN}"
    PHASE_NOOP_POLICY_BUILD="${PHASE_NOOP_POLICY_BUILD:-$DEFAULT_PHASE_NOOP_POLICY_BUILD}"
    PHASE_NOOP_POLICY_TEST="${PHASE_NOOP_POLICY_TEST:-$DEFAULT_PHASE_NOOP_POLICY_TEST}"
    PHASE_NOOP_POLICY_REFACTOR="${PHASE_NOOP_POLICY_REFACTOR:-$DEFAULT_PHASE_NOOP_POLICY_REFACTOR}"
    PHASE_NOOP_POLICY_LINT="${PHASE_NOOP_POLICY_LINT:-$DEFAULT_PHASE_NOOP_POLICY_LINT}"
    PHASE_NOOP_POLICY_DOCUMENT="${PHASE_NOOP_POLICY_DOCUMENT:-$DEFAULT_PHASE_NOOP_POLICY_DOCUMENT}"

    PHASE_NOOP_PROFILE="$(to_lower "$PHASE_NOOP_PROFILE")"
    if ! is_phase_noop_profile "$PHASE_NOOP_PROFILE"; then
        PHASE_NOOP_PROFILE="$DEFAULT_PHASE_NOOP_PROFILE"
    fi
    PHASE_NOOP_PROFILE="$(normalize_phase_noop_profile "$PHASE_NOOP_PROFILE")"
    PHASE_NOOP_POLICY_PLAN="$(normalize_phase_noop_policy "$(to_lower "$PHASE_NOOP_POLICY_PLAN")")"
    PHASE_NOOP_POLICY_BUILD="$(normalize_phase_noop_policy "$(to_lower "$PHASE_NOOP_POLICY_BUILD")")"
    PHASE_NOOP_POLICY_TEST="$(normalize_phase_noop_policy "$(to_lower "$PHASE_NOOP_POLICY_TEST")")"
    PHASE_NOOP_POLICY_REFACTOR="$(normalize_phase_noop_policy "$(to_lower "$PHASE_NOOP_POLICY_REFACTOR")")"
    PHASE_NOOP_POLICY_LINT="$(normalize_phase_noop_policy "$(to_lower "$PHASE_NOOP_POLICY_LINT")")"
    PHASE_NOOP_POLICY_DOCUMENT="$(normalize_phase_noop_policy "$(to_lower "$PHASE_NOOP_POLICY_DOCUMENT")")"

    apply_phase_noop_profile

    if is_true "$STRICT_VALIDATION_NOOP"; then
        PHASE_NOOP_POLICY_TEST="hard"
        PHASE_NOOP_POLICY_LINT="hard"
    fi

    PHASE_NOOP_POLICY_PLAN="$(normalize_phase_noop_policy "$PHASE_NOOP_POLICY_PLAN")"
    PHASE_NOOP_POLICY_BUILD="$(normalize_phase_noop_policy "$PHASE_NOOP_POLICY_BUILD")"
    PHASE_NOOP_POLICY_TEST="$(normalize_phase_noop_policy "$PHASE_NOOP_POLICY_TEST")"
    PHASE_NOOP_POLICY_REFACTOR="$(normalize_phase_noop_policy "$PHASE_NOOP_POLICY_REFACTOR")"
    PHASE_NOOP_POLICY_LINT="$(normalize_phase_noop_policy "$PHASE_NOOP_POLICY_LINT")"
    PHASE_NOOP_POLICY_DOCUMENT="$(normalize_phase_noop_policy "$PHASE_NOOP_POLICY_DOCUMENT")"
    PHASE_NOOP_PROFILE="$(normalize_phase_noop_profile "$PHASE_NOOP_PROFILE")"
}

print_usage() {
    cat <<'EOF'
Usage: ./ralphie.sh [options]

Core options:
  --resume                               Resume from previous persisted session state (default: true)
  --no-resume                            Force fresh start; ignore persisted state
  --rebootstrap                          Rebuild project bootstrap context (project type/objective/build consent)
  --max-session-cycles N                 Max total inference attempts in this session (0 = unlimited)
  --session-token-budget N                Max session token budget (0 = unlimited)
  --session-token-rate-cents-per-million N  Cost rate in cents per million tokens
  --session-cost-budget-cents N           Max estimated cost budget in cents (0 = unlimited)
  --max-phase-completion-attempts N       Max completion-signal retries per phase (0=unlimited with stagnation guard)
  --phase-wallclock-limit-seconds N       Wall-clock limit per phase attempt (0 = disabled)
  --phase-completion-retry-delay-seconds N Delay in seconds between completion retries
  --phase-completion-retry-verbose bool   Verbose phase completion retry logging (true|false)
  --max-consensus-routing-attempts N      Max adaptive consensus reroutes per run (0=unlimited)
  --consensus-score-threshold N           Minimum consensus/handoff pass score (0-100)
  --run-agent-max-attempts N              Max inference retries per agent run
  --run-agent-retry-delay-seconds N       Delay in seconds between inference retries
  --run-agent-retry-verbose bool          Verbose inference retry logging (true|false)
  --auto-init-git-if-missing bool         Initialize git repository at startup when missing (true|false)
  --auto-commit-on-phase-pass bool        Auto-commit local changes after phase gate pass (true|false, no push)
  --auto-update bool                      Check and replace ralphie.sh from remote before startup (true|false)
  --auto-update-url URL                   Raw ralphie.sh URL for auto-update; defaults to GitHub origin/current branch
  --auto-update-allow-insecure bool       Allow non-HTTPS HTTP auto-update URLs (true|false; default false)
  --auto-update-lock-timeout-seconds N    Seconds to wait for another Ralphie self-update to finish
  --auto-engine-preference codex|claude   Preferred AUTO engine selection order
  --engine-output-to-stdout bool          Show or suppress live engine output stream (true|false)
  --auto-repair-markdown-artifacts bool    Auto-sanitize markdown artifacts when gate-blocked (true|false)
  --strict-validation-noop bool           Require worktree mutation for test/lint phases too (true|false)
  --phase-noop-profile strict|balanced|read-only-first|custom
  --phase-noop-policy-plan hard|soft|none  Phase worktree mutation policy for plan
  --phase-noop-policy-build hard|soft|none Phase worktree mutation policy for build
  --phase-noop-policy-test hard|soft|none  Phase worktree mutation policy for test
  --phase-noop-policy-refactor hard|soft|none Phase worktree mutation policy for refactor
  --phase-noop-policy-lint hard|soft|none  Phase worktree mutation policy for lint
  --phase-noop-policy-document hard|soft|none  Phase worktree mutation policy for document
  --require-plan-backlog-clear-before-done bool  Block terminal done while local unchecked backlog tasks remain
  --require-plan-freshness-for-build bool  Remap to plan when configured backlog sources changed after plan
  --backlog-sources PATHS                 Comma-separated markdown backlog files (default: IMPLEMENTATION_PLAN.md)
  --help, -h                             Show this help and exit

All options may also be set through config.env (eg. SESSION_TOKEN_BUDGET, MAX_SESSION_CYCLES, etc).

Additional runtime env knobs:
  RALPHIE_CODEX_ENDPOINT                 Optional OPENAI_BASE_URL override for codex calls
  RALPHIE_CODEX_USE_RESPONSES_SCHEMA     Whether to pass codex --output-schema (true|false)
  RALPHIE_CODEX_RESPONSES_SCHEMA_FILE    JSON schema file path for codex --output-schema
  RALPHIE_CODEX_THINKING_OVERRIDE        Codex reasoning override: none|minimal|low|medium|high|xhigh
  RALPHIE_CLAUDE_ENDPOINT                Optional ANTHROPIC_BASE_URL override for claude calls
  RALPHIE_CLAUDE_THINKING_OVERRIDE       Claude thinking override: none|off|low|medium|high|xhigh
  RALPHIE_ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS  Kill/retry agent run if no new output for N seconds (0=disabled)
  RALPHIE_AUTO_INIT_GIT_IF_MISSING       Initialize git repo at startup when missing (true|false)
  RALPHIE_AUTO_COMMIT_ON_PHASE_PASS      Auto-commit phase-approved changes (true|false)
  RALPHIE_AUTO_UPDATE                    Enable pre-run single-file self-update (true|false)
  RALPHIE_AUTO_UPDATE_URL                Explicit raw ralphie.sh update URL
  RALPHIE_AUTO_UPDATE_ALLOW_DIRTY        Allow replacing a locally modified ralphie.sh (true|false)
  RALPHIE_AUTO_UPDATE_ALLOW_INSECURE     Allow http:// auto-update URLs (true|false)
  RALPHIE_AUTO_UPDATE_TIMEOUT_SECONDS    Fetch timeout for single-file self-update
  RALPHIE_AUTO_UPDATE_LOCK_TIMEOUT_SECONDS  Seconds to wait for concurrent self-update lock
  RALPHIE_PHASE_MANIFEST_MODE            Worktree manifest mode: light|deep
  RALPHIE_AUTO_REPAIR_MARKDOWN_DRY_RUN   Preview markdown repairs without mutating files (true|false)
  RALPHIE_AUTO_REPAIR_MARKDOWN_BACKUP    Save markdown backup+diff artifacts before mutation (true|false)
  RALPHIE_AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED  Restrict markdown repair targets to this-session changed files
  RALPHIE_MARKDOWN_LOCAL_PATH_ALLOWLIST_REGEX  ERE for intentional documented paths in markdown hygiene
  RALPHIE_STARTUP_OPERATIONAL_PROBE      Run startup operational self-checks (true|false)
  RALPHIE_ENGINE_OVERRIDES_BOOTSTRAPPED  First-deploy engine override prompt sentinel (true|false)
  RALPHIE_NOTIFICATIONS_ENABLED          Master notifications toggle (true|false)
  RALPHIE_NOTIFY_TELEGRAM_ENABLED        Enable Telegram notifications (true|false)
  TG_BOT_TOKEN                           Telegram bot token
  TG_CHAT_ID                             Telegram chat/channel id
  RALPHIE_NOTIFY_DISCORD_ENABLED         Enable Discord webhook notifications (true|false)
  RALPHIE_NOTIFY_DISCORD_WEBHOOK_URL     Discord incoming webhook URL
  RALPHIE_NOTIFY_TTS_ENABLED             Enable Chutes TTS voice notifications for Telegram/Discord (true|false)
  RALPHIE_NOTIFY_TTS_STYLE               TTS narration text style (not voice id): standard|friendly|ralph_wiggum
  CHUTES_API_KEY                         Chutes API key for TTS
  RALPHIE_NOTIFY_CHUTES_TTS_URL          Chutes TTS endpoint URL
  RALPHIE_NOTIFY_CHUTES_VOICE            Chutes TTS voice id (example: am_michael)
  RALPHIE_NOTIFY_CHUTES_SPEED            Chutes TTS speed (example: 1.0)
  RALPHIE_NOTIFY_EVENT_DEDUP_WINDOW_SECONDS  Suppress duplicate notification events within N seconds
  RALPHIE_NOTIFY_INCIDENT_REMINDER_MINUTES   Reminder cadence (minutes) for sustained incident series
  RALPHIE_NOTIFICATION_WIZARD_BOOTSTRAPPED  First-deploy notification setup prompt sentinel (true|false)
  RALPHIE_PHASE_WALLCLOCK_LIMIT_SECONDS     Wall-clock limit per phase attempt (seconds, 0=disabled)
  RALPHIE_REQUIRE_LINT_BEFORE_DONE          Require at least one passed lint phase before terminal done routing
  RALPHIE_REQUIRE_DOCUMENT_BEFORE_DONE      Require at least one passed document phase before terminal done routing
  RALPHIE_REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE  Require local configured backlog sources to be clear before terminal done routing
  RALPHIE_REQUIRE_PLAN_FRESHNESS_FOR_BUILD  Require plan refresh when configured backlog sources change before build/done routing
  RALPHIE_BACKLOG_SOURCES                   Comma-separated markdown backlog files evaluated for local unchecked tasks
EOF
}

require_non_negative_int() {
    local name="$1"
    local value="$2"
    if ! is_number "$value"; then
        err "Invalid numeric value for $name: $value"
        exit 1
    fi
    if [ "$value" -lt 0 ]; then
        err "Negative values are not supported for $name: $value"
        exit 1
    fi
}

parse_arg_value() {
    local arg_name="$1"
    local arg_value="$2"
    if [ -z "$arg_value" ] || [[ "$arg_value" == --* ]]; then
        err "Missing value for $arg_name"
        exit 1
    fi
    echo "$arg_value"
}

parse_args() {
    while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h)
            print_usage
            exit 0
            ;;
            --resume)
                RESUME_REQUESTED=true
                shift
                ;;
        --no-resume)
            RESUME_REQUESTED=false
            shift
            ;;
        --rebootstrap)
            REBOOTSTRAP_REQUESTED=true
            shift
            ;;
        --max-session-cycles)
            MAX_SESSION_CYCLES="$(parse_arg_value "--max-session-cycles" "${2:-}")"
                require_non_negative_int "MAX_SESSION_CYCLES" "$MAX_SESSION_CYCLES"
                shift 2
                ;;
            --session-token-budget)
                SESSION_TOKEN_BUDGET="$(parse_arg_value "--session-token-budget" "${2:-}")"
                require_non_negative_int "SESSION_TOKEN_BUDGET" "$SESSION_TOKEN_BUDGET"
                shift 2
                ;;
            --session-token-rate-cents-per-million)
                SESSION_TOKEN_RATE_CENTS_PER_MILLION="$(parse_arg_value "--session-token-rate-cents-per-million" "${2:-}")"
                require_non_negative_int "SESSION_TOKEN_RATE_CENTS_PER_MILLION" "$SESSION_TOKEN_RATE_CENTS_PER_MILLION"
                shift 2
                ;;
            --session-cost-budget-cents)
                SESSION_COST_BUDGET_CENTS="$(parse_arg_value "--session-cost-budget-cents" "${2:-}")"
                require_non_negative_int "SESSION_COST_BUDGET_CENTS" "$SESSION_COST_BUDGET_CENTS"
                shift 2
                ;;
        --max-phase-completion-attempts)
            PHASE_COMPLETION_MAX_ATTEMPTS="$(parse_arg_value "--max-phase-completion-attempts" "${2:-}")"
            require_non_negative_int "PHASE_COMPLETION_MAX_ATTEMPTS" "$PHASE_COMPLETION_MAX_ATTEMPTS"
            shift 2
            ;;
        --phase-wallclock-limit-seconds)
            PHASE_WALLCLOCK_LIMIT_SECONDS="$(parse_arg_value "--phase-wallclock-limit-seconds" "${2:-}")"
            require_non_negative_int "PHASE_WALLCLOCK_LIMIT_SECONDS" "$PHASE_WALLCLOCK_LIMIT_SECONDS"
            shift 2
            ;;
        --phase-completion-retry-delay-seconds)
            PHASE_COMPLETION_RETRY_DELAY_SECONDS="$(parse_arg_value "--phase-completion-retry-delay-seconds" "${2:-}")"
            require_non_negative_int "PHASE_COMPLETION_RETRY_DELAY_SECONDS" "$PHASE_COMPLETION_RETRY_DELAY_SECONDS"
            shift 2
            ;;
            --phase-completion-retry-verbose)
                PHASE_COMPLETION_RETRY_VERBOSE="$(parse_arg_value "--phase-completion-retry-verbose" "${2:-}")"
                if ! is_bool_like "$PHASE_COMPLETION_RETRY_VERBOSE"; then
                    err "Invalid boolean value for --phase-completion-retry-verbose: $PHASE_COMPLETION_RETRY_VERBOSE"
                    exit 1
                fi
                shift 2
                ;;
            --max-consensus-routing-attempts)
                MAX_CONSENSUS_ROUTING_ATTEMPTS="$(parse_arg_value "--max-consensus-routing-attempts" "${2:-}")"
                require_non_negative_int "MAX_CONSENSUS_ROUTING_ATTEMPTS" "$MAX_CONSENSUS_ROUTING_ATTEMPTS"
                shift 2
                ;;
            --consensus-score-threshold)
                CONSENSUS_SCORE_THRESHOLD="$(parse_arg_value "--consensus-score-threshold" "${2:-}")"
                require_non_negative_int "CONSENSUS_SCORE_THRESHOLD" "$CONSENSUS_SCORE_THRESHOLD"
                if [ "$CONSENSUS_SCORE_THRESHOLD" -gt 100 ]; then
                    err "Invalid value for --consensus-score-threshold: $CONSENSUS_SCORE_THRESHOLD (expected 0-100)"
                    exit 1
                fi
                shift 2
                ;;
            --run-agent-max-attempts)
                RUN_AGENT_MAX_ATTEMPTS="$(parse_arg_value "--run-agent-max-attempts" "${2:-}")"
                require_non_negative_int "RUN_AGENT_MAX_ATTEMPTS" "$RUN_AGENT_MAX_ATTEMPTS"
                shift 2
                ;;
            --run-agent-retry-delay-seconds)
                RUN_AGENT_RETRY_DELAY_SECONDS="$(parse_arg_value "--run-agent-retry-delay-seconds" "${2:-}")"
                require_non_negative_int "RUN_AGENT_RETRY_DELAY_SECONDS" "$RUN_AGENT_RETRY_DELAY_SECONDS"
                shift 2
                ;;
            --run-agent-retry-verbose)
                RUN_AGENT_RETRY_VERBOSE="$(parse_arg_value "--run-agent-retry-verbose" "${2:-}")"
                if ! is_bool_like "$RUN_AGENT_RETRY_VERBOSE"; then
                    err "Invalid boolean value for --run-agent-retry-verbose: $RUN_AGENT_RETRY_VERBOSE"
                    exit 1
                fi
                shift 2
                ;;
            --auto-init-git-if-missing)
                AUTO_INIT_GIT_IF_MISSING="$(parse_arg_value "--auto-init-git-if-missing" "${2:-}")"
                if ! is_bool_like "$AUTO_INIT_GIT_IF_MISSING"; then
                    err "Invalid boolean value for --auto-init-git-if-missing: $AUTO_INIT_GIT_IF_MISSING"
                    exit 1
                fi
                shift 2
                ;;
            --auto-commit-on-phase-pass)
                AUTO_COMMIT_ON_PHASE_PASS="$(parse_arg_value "--auto-commit-on-phase-pass" "${2:-}")"
                if ! is_bool_like "$AUTO_COMMIT_ON_PHASE_PASS"; then
                    err "Invalid boolean value for --auto-commit-on-phase-pass: $AUTO_COMMIT_ON_PHASE_PASS"
                    exit 1
                fi
                shift 2
                ;;
            --auto-update)
                AUTO_UPDATE="$(parse_arg_value "--auto-update" "${2:-}")"
                if ! is_bool_like "$AUTO_UPDATE"; then
                    err "Invalid boolean value for --auto-update: $AUTO_UPDATE"
                    exit 1
                fi
                shift 2
                ;;
            --auto-update-url)
                AUTO_UPDATE_URL="$(parse_arg_value "--auto-update-url" "${2:-}")"
                if [ -z "$(sanitize_text_for_log "$AUTO_UPDATE_URL")" ]; then
                    err "Invalid empty value for --auto-update-url"
                    exit 1
                fi
                shift 2
                ;;
            --auto-update-allow-insecure)
                AUTO_UPDATE_ALLOW_INSECURE="$(parse_arg_value "--auto-update-allow-insecure" "${2:-}")"
                if ! is_bool_like "$AUTO_UPDATE_ALLOW_INSECURE"; then
                    err "Invalid boolean value for --auto-update-allow-insecure: $AUTO_UPDATE_ALLOW_INSECURE"
                    exit 1
                fi
                shift 2
                ;;
            --auto-update-lock-timeout-seconds)
                AUTO_UPDATE_LOCK_TIMEOUT_SECONDS="$(parse_arg_value "--auto-update-lock-timeout-seconds" "${2:-}")"
                require_non_negative_int "AUTO_UPDATE_LOCK_TIMEOUT_SECONDS" "$AUTO_UPDATE_LOCK_TIMEOUT_SECONDS"
                shift 2
                ;;
            --auto-engine-preference)
                AUTO_ENGINE_PREFERENCE="$(to_lower "$(parse_arg_value "--auto-engine-preference" "${2:-}")")"
                case "$AUTO_ENGINE_PREFERENCE" in
                    codex|claude) ;;
                    *)
                        err "Invalid value for --auto-engine-preference: $AUTO_ENGINE_PREFERENCE (expected codex|claude)"
                        exit 1
                        ;;
                esac
                shift 2
                ;;
            --engine-output-to-stdout)
                ENGINE_OUTPUT_TO_STDOUT="$(parse_arg_value "--engine-output-to-stdout" "${2:-}")"
                if ! is_bool_like "$ENGINE_OUTPUT_TO_STDOUT"; then
                    err "Invalid boolean value for --engine-output-to-stdout: $ENGINE_OUTPUT_TO_STDOUT"
                    exit 1
                fi
                ENGINE_OUTPUT_TO_STDOUT_EXPLICIT="true"
                ENGINE_OUTPUT_TO_STDOUT_OVERRIDE="$ENGINE_OUTPUT_TO_STDOUT"
                shift 2
                ;;
            --auto-repair-markdown-artifacts)
                AUTO_REPAIR_MARKDOWN_ARTIFACTS="$(parse_arg_value "--auto-repair-markdown-artifacts" "${2:-}")"
                if ! is_bool_like "$AUTO_REPAIR_MARKDOWN_ARTIFACTS"; then
                    err "Invalid boolean value for --auto-repair-markdown-artifacts: $AUTO_REPAIR_MARKDOWN_ARTIFACTS"
                    exit 1
                fi
                shift 2
                ;;
            --strict-validation-noop)
                STRICT_VALIDATION_NOOP="$(parse_arg_value "--strict-validation-noop" "${2:-}")"
                if ! is_bool_like "$STRICT_VALIDATION_NOOP"; then
                    err "Invalid boolean value for --strict-validation-noop: $STRICT_VALIDATION_NOOP"
                    exit 1
                fi
                shift 2
                ;;
            --phase-noop-profile)
                local profile_candidate
                profile_candidate="$(to_lower "$(parse_arg_value "--phase-noop-profile" "${2:-}")")"
                if ! is_phase_noop_profile "$profile_candidate"; then
                    err "Invalid phase noop profile: $profile_candidate"
                    exit 1
                fi
                PHASE_NOOP_PROFILE="$(normalize_phase_noop_profile "$profile_candidate")"
                shift 2
                ;;
            --phase-noop-policy-plan)
                PHASE_NOOP_POLICY_PLAN="$(to_lower "$(parse_arg_value "--phase-noop-policy-plan" "${2:-}")")"
                if ! is_phase_noop_policy "$PHASE_NOOP_POLICY_PLAN"; then
                    err "Invalid policy for --phase-noop-policy-plan: $PHASE_NOOP_POLICY_PLAN"
                    exit 1
                fi
                PHASE_NOOP_POLICY_PLAN_EXPLICIT=true
                shift 2
                ;;
            --phase-noop-policy-build)
                PHASE_NOOP_POLICY_BUILD="$(to_lower "$(parse_arg_value "--phase-noop-policy-build" "${2:-}")")"
                if ! is_phase_noop_policy "$PHASE_NOOP_POLICY_BUILD"; then
                    err "Invalid policy for --phase-noop-policy-build: $PHASE_NOOP_POLICY_BUILD"
                    exit 1
                fi
                PHASE_NOOP_POLICY_BUILD_EXPLICIT=true
                shift 2
                ;;
            --phase-noop-policy-test)
                PHASE_NOOP_POLICY_TEST="$(to_lower "$(parse_arg_value "--phase-noop-policy-test" "${2:-}")")"
                if ! is_phase_noop_policy "$PHASE_NOOP_POLICY_TEST"; then
                    err "Invalid policy for --phase-noop-policy-test: $PHASE_NOOP_POLICY_TEST"
                    exit 1
                fi
                PHASE_NOOP_POLICY_TEST_EXPLICIT=true
                shift 2
                ;;
            --phase-noop-policy-refactor)
                PHASE_NOOP_POLICY_REFACTOR="$(to_lower "$(parse_arg_value "--phase-noop-policy-refactor" "${2:-}")")"
                if ! is_phase_noop_policy "$PHASE_NOOP_POLICY_REFACTOR"; then
                    err "Invalid policy for --phase-noop-policy-refactor: $PHASE_NOOP_POLICY_REFACTOR"
                    exit 1
                fi
                PHASE_NOOP_POLICY_REFACTOR_EXPLICIT=true
                shift 2
                ;;
            --phase-noop-policy-lint)
                PHASE_NOOP_POLICY_LINT="$(to_lower "$(parse_arg_value "--phase-noop-policy-lint" "${2:-}")")"
                if ! is_phase_noop_policy "$PHASE_NOOP_POLICY_LINT"; then
                    err "Invalid policy for --phase-noop-policy-lint: $PHASE_NOOP_POLICY_LINT"
                    exit 1
                fi
                PHASE_NOOP_POLICY_LINT_EXPLICIT=true
                shift 2
                ;;
            --phase-noop-policy-document)
                PHASE_NOOP_POLICY_DOCUMENT="$(to_lower "$(parse_arg_value "--phase-noop-policy-document" "${2:-}")")"
                if ! is_phase_noop_policy "$PHASE_NOOP_POLICY_DOCUMENT"; then
                    err "Invalid policy for --phase-noop-policy-document: $PHASE_NOOP_POLICY_DOCUMENT"
                    exit 1
                fi
                PHASE_NOOP_POLICY_DOCUMENT_EXPLICIT=true
                shift 2
                ;;
            --require-plan-backlog-clear-before-done)
                REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE="$(parse_arg_value "--require-plan-backlog-clear-before-done" "${2:-}")"
                if ! is_bool_like "$REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE"; then
                    err "Invalid boolean value for --require-plan-backlog-clear-before-done: $REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE"
                    exit 1
                fi
                shift 2
                ;;
            --require-plan-freshness-for-build)
                REQUIRE_PLAN_FRESHNESS_FOR_BUILD="$(parse_arg_value "--require-plan-freshness-for-build" "${2:-}")"
                if ! is_bool_like "$REQUIRE_PLAN_FRESHNESS_FOR_BUILD"; then
                    err "Invalid boolean value for --require-plan-freshness-for-build: $REQUIRE_PLAN_FRESHNESS_FOR_BUILD"
                    exit 1
                fi
                shift 2
                ;;
            --backlog-sources)
                BACKLOG_SOURCES="$(parse_arg_value "--backlog-sources" "${2:-}")"
                shift 2
                ;;
            --max-iterations)
                MAX_ITERATIONS="$(parse_arg_value "--max-iterations" "${2:-}")"
                require_non_negative_int "MAX_ITERATIONS" "$MAX_ITERATIONS"
                shift 2
                ;;
            *)
                err "Unknown argument: $1"
                print_usage
                exit 1
                ;;
        esac
    done
}

# Global Registry for Background Processes (for atomic cleanup)
declare -a RALPHIE_BG_PIDS=()
INTERRUPT_MENU_ACTIVE="false"
MARKDOWN_ARTIFACTS_CLEANED_LIST=""
MARKDOWN_ARTIFACTS_PREVIEW_LIST=""
MARKDOWN_ARTIFACTS_BACKUP_LIST=""
TIMEOUT_BINARY_WARNING_EMITTED="false"
LOCK_ACQUIRED="false"
LOCK_OWNER_TOKEN=""
RALPHIE_CLEANUP_STATE_ENABLED="false"
RALPHIE_CLEANUP_IN_PROGRESS="false"
RALPHIE_TRAPS_INSTALLED="false"
AUTO_COMMIT_BASELINE_DIRTY_PATHS_FILE=""

# Configuration defaults
DEFAULT_ENGINE="auto"
DEFAULT_CODEX_CMD="$(discover_codex_command_default)"
DEFAULT_CLAUDE_CMD="$(discover_claude_command_default)"
DEFAULT_AUTO_ENGINE_PREFERENCE="codex"        # codex|claude (AUTO mode selection priority)
DEFAULT_CODEX_ENDPOINT=""                     # empty = do not override OPENAI_BASE_URL
DEFAULT_CODEX_USE_RESPONSES_SCHEMA="false"    # false = skip codex --output-schema
DEFAULT_CODEX_RESPONSES_SCHEMA_FILE=""        # path passed to codex --output-schema when enabled
DEFAULT_CODEX_THINKING_OVERRIDE="high"        # none|minimal|low|medium|high|xhigh
DEFAULT_CLAUDE_ENDPOINT=""                    # empty = do not override ANTHROPIC_BASE_URL
DEFAULT_CLAUDE_THINKING_OVERRIDE="high"       # none|off|low|medium|high|xhigh
DEFAULT_AUTO_INIT_GIT_IF_MISSING="true"       # initialize git repo at startup when missing
DEFAULT_AUTO_COMMIT_ON_PHASE_PASS="true"      # commit phase-approved local changes (no push)
DEFAULT_YOLO="true"
DEFAULT_AUTO_UPDATE="false"                  # check remote script and replace before startup
DEFAULT_AUTO_UPDATE_URL=""                   # explicit raw ralphie.sh URL; derived from GitHub origin when empty
DEFAULT_AUTO_UPDATE_ALLOW_DIRTY="false"      # refuse to overwrite local ralphie.sh edits by default
DEFAULT_AUTO_UPDATE_ALLOW_INSECURE="false"   # refuse plaintext HTTP update URLs by default
DEFAULT_AUTO_UPDATE_TIMEOUT_SECONDS=20       # network timeout for single-file self-update fetch
DEFAULT_AUTO_UPDATE_LOCK_TIMEOUT_SECONDS=30  # wait for concurrent startup self-update
DEFAULT_COMMAND_TIMEOUT_SECONDS=0           # Tolerant default: disable command timeouts unless overridden
DEFAULT_MAX_ITERATIONS=0                    # 0 means infinite
DEFAULT_MAX_SESSION_CYCLES=0                # 0 means infinite across all phases
DEFAULT_RALPHIE_QUALITY_LEVEL="standard"    # minimal|standard|high
DEFAULT_RUN_AGENT_MAX_ATTEMPTS=5
DEFAULT_RUN_AGENT_RETRY_DELAY_SECONDS=5
DEFAULT_RUN_AGENT_RETRY_VERBOSE="true"
DEFAULT_ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS=600  # recycle hung engine runs after prolonged no-output stalls (0=disabled)
DEFAULT_RESUME_REQUESTED="true"
DEFAULT_REBOOTSTRAP_REQUESTED="false"
DEFAULT_STRICT_VALIDATION_NOOP="false"
DEFAULT_PHASE_COMPLETION_MAX_ATTEMPTS=3     # Lenient default; tighten via flags/presets for CI
DEFAULT_PHASE_COMPLETION_RETRY_DELAY_SECONDS=5
DEFAULT_PHASE_COMPLETION_RETRY_VERBOSE="true"
DEFAULT_MAX_CONSENSUS_ROUTING_ATTEMPTS=4
DEFAULT_ENGINE_OUTPUT_TO_STDOUT="true"
ENGINE_OUTPUT_TO_STDOUT_EXPLICIT="false"
ENGINE_OUTPUT_TO_STDOUT_OVERRIDE=""
DEFAULT_PHASE_NOOP_POLICY_PLAN="none"
DEFAULT_PHASE_NOOP_POLICY_BUILD="hard"
DEFAULT_PHASE_NOOP_POLICY_TEST="soft"
DEFAULT_PHASE_NOOP_POLICY_REFACTOR="hard"
DEFAULT_PHASE_NOOP_POLICY_LINT="hard"
DEFAULT_PHASE_NOOP_POLICY_DOCUMENT="soft"
DEFAULT_PHASE_NOOP_PROFILE="balanced"
PHASE_NOOP_POLICY_PLAN_EXPLICIT=false
PHASE_NOOP_POLICY_BUILD_EXPLICIT=false
PHASE_NOOP_POLICY_TEST_EXPLICIT=false
PHASE_NOOP_POLICY_REFACTOR_EXPLICIT=false
PHASE_NOOP_POLICY_LINT_EXPLICIT=false
PHASE_NOOP_POLICY_DOCUMENT_EXPLICIT=false
DEFAULT_SESSION_TOKEN_BUDGET=0               # 0 means unlimited
DEFAULT_SESSION_TOKEN_RATE_CENTS_PER_MILLION=0 # 0 means no cost accounting
DEFAULT_SESSION_COST_BUDGET_CENTS=0           # 0 means unlimited
DEFAULT_AUTO_REPAIR_MARKDOWN_ARTIFACTS="true" # sanitize common local/engine leaks when gate blocked
DEFAULT_AUTO_REPAIR_MARKDOWN_DRY_RUN="false"  # preview-only remediation mode (no file mutations)
DEFAULT_AUTO_REPAIR_MARKDOWN_BACKUP="true"    # write backup+diff artifacts before markdown mutation
DEFAULT_AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED="false" # optional scope limiter for markdown remediation
DEFAULT_MARKDOWN_LOCAL_PATH_ALLOWLIST_REGEX="" # optional ERE for intentional documented paths
DEFAULT_PHASE_MANIFEST_MODE="light"           # light|deep manifest capture strategy
DEFAULT_SWARM_CONSENSUS_TIMEOUT=240             # CI-safe: 4m cap for consensus reviewers
DEFAULT_CONSENSUS_SCORE_THRESHOLD=70             # minimum avg score for consensus/handoff to pass
DEFAULT_REQUIRE_LINT_BEFORE_DONE="true"          # terminal guard: require lint pass before done
DEFAULT_REQUIRE_DOCUMENT_BEFORE_DONE="true"      # terminal guard: require document pass before done
DEFAULT_REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE="true" # terminal guard: block done while local unchecked backlog tasks remain
DEFAULT_REQUIRE_PLAN_FRESHNESS_FOR_BUILD="true"  # route guard: stale plan vs backlog sources must remap to plan
DEFAULT_BACKLOG_SOURCES="IMPLEMENTATION_PLAN.md" # comma-separated markdown backlog sources
DEFAULT_ENGINE_HEALTH_MAX_ATTEMPTS=5             # attempts before refusing to proceed
DEFAULT_ENGINE_HEALTH_RETRY_DELAY_SECONDS=5       # exponential backoff base
DEFAULT_ENGINE_HEALTH_RETRY_VERBOSE="true"        # log retry activity at startup/loop boundaries
DEFAULT_ENGINE_SMOKE_TEST_TIMEOUT=15               # seconds to wait for smoke-test canary response
DEFAULT_STARTUP_OPERATIONAL_PROBE="true"          # run startup self-checks for runtime confidence
DEFAULT_ENGINE_OVERRIDES_BOOTSTRAPPED="false"     # first-deploy interactive engine override prompt sentinel
DEFAULT_NOTIFICATIONS_ENABLED="false"              # master notifications toggle
DEFAULT_NOTIFY_TELEGRAM_ENABLED="false"            # send status messages to Telegram bot/chat
DEFAULT_NOTIFY_DISCORD_ENABLED="false"             # send status messages to Discord webhook
DEFAULT_NOTIFY_TTS_ENABLED="false"                 # enable Chutes TTS voice notifications via Telegram/Discord
DEFAULT_NOTIFY_TTS_STYLE="ralph_wiggum"            # narration text style (ralph alias supported)
DEFAULT_NOTIFY_CHUTES_TTS_URL="https://chutes-kokoro.chutes.ai/speak"
DEFAULT_NOTIFY_CHUTES_VOICE="am_puck"
DEFAULT_NOTIFY_CHUTES_SPEED="1.24"
DEFAULT_NOTIFY_EVENT_DEDUP_WINDOW_SECONDS=90       # suppress duplicate notification events in a short window
DEFAULT_NOTIFY_INCIDENT_REMINDER_MINUTES=10        # reminder cadence for ongoing incident series
DEFAULT_NOTIFICATION_WIZARD_BOOTSTRAPPED="false"  # first-deploy notification setup prompt sentinel
DEFAULT_PHASE_WALLCLOCK_LIMIT_SECONDS=0            # Default: disabled; enable for CI with presets below
# Preset hints (not enforced):
#   CI_SAFE: PHASE_COMPLETION_MAX_ATTEMPTS=2, PHASE_WALLCLOCK_LIMIT_SECONDS=900, COMMAND_TIMEOUT_SECONDS=600, SWARM_CONSENSUS_TIMEOUT=240
#   IMPATIENT: PHASE_COMPLETION_MAX_ATTEMPTS=1, PHASE_WALLCLOCK_LIMIT_SECONDS=300, COMMAND_TIMEOUT_SECONDS=300, PHASE_COMPLETION_RETRY_DELAY_SECONDS=5
#   LEGACY_LENIENT: PHASE_COMPLETION_MAX_ATTEMPTS=3, PHASE_WALLCLOCK_LIMIT_SECONDS=0, COMMAND_TIMEOUT_SECONDS=0, SWARM_CONSENSUS_TIMEOUT=600

# Load configuration from environment or file.
COMMAND_TIMEOUT_SECONDS="${COMMAND_TIMEOUT_SECONDS:-$DEFAULT_COMMAND_TIMEOUT_SECONDS}"
MAX_ITERATIONS="${MAX_ITERATIONS:-$DEFAULT_MAX_ITERATIONS}"
MAX_SESSION_CYCLES="${MAX_SESSION_CYCLES:-$DEFAULT_MAX_SESSION_CYCLES}"
YOLO="${YOLO:-$DEFAULT_YOLO}"
AUTO_UPDATE="${AUTO_UPDATE:-$DEFAULT_AUTO_UPDATE}"
AUTO_UPDATE_URL="${AUTO_UPDATE_URL:-$DEFAULT_AUTO_UPDATE_URL}"
AUTO_UPDATE_ALLOW_DIRTY="${AUTO_UPDATE_ALLOW_DIRTY:-$DEFAULT_AUTO_UPDATE_ALLOW_DIRTY}"
AUTO_UPDATE_ALLOW_INSECURE="${AUTO_UPDATE_ALLOW_INSECURE:-$DEFAULT_AUTO_UPDATE_ALLOW_INSECURE}"
AUTO_UPDATE_TIMEOUT_SECONDS="${AUTO_UPDATE_TIMEOUT_SECONDS:-$DEFAULT_AUTO_UPDATE_TIMEOUT_SECONDS}"
AUTO_UPDATE_LOCK_TIMEOUT_SECONDS="${AUTO_UPDATE_LOCK_TIMEOUT_SECONDS:-$DEFAULT_AUTO_UPDATE_LOCK_TIMEOUT_SECONDS}"
PHASE_WALLCLOCK_LIMIT_SECONDS="${PHASE_WALLCLOCK_LIMIT_SECONDS:-$DEFAULT_PHASE_WALLCLOCK_LIMIT_SECONDS}"
RALPHIE_QUALITY_LEVEL="${RALPHIE_QUALITY_LEVEL:-$DEFAULT_RALPHIE_QUALITY_LEVEL}"
SWARM_MAX_PARALLEL="${SWARM_MAX_PARALLEL:-2}"
CONFIDENCE_TARGET="${CONFIDENCE_TARGET:-85}"
CONFIDENCE_STAGNATION_LIMIT="${CONFIDENCE_STAGNATION_LIMIT:-3}"
AUTO_PLAN_BACKFILL_ON_IDLE_BUILD="${AUTO_PLAN_BACKFILL_ON_IDLE_BUILD:-true}"
AUTO_ENGINE_PREFERENCE="${AUTO_ENGINE_PREFERENCE:-$DEFAULT_AUTO_ENGINE_PREFERENCE}"
AUTO_INIT_GIT_IF_MISSING="${AUTO_INIT_GIT_IF_MISSING:-$DEFAULT_AUTO_INIT_GIT_IF_MISSING}"
AUTO_COMMIT_ON_PHASE_PASS="${AUTO_COMMIT_ON_PHASE_PASS:-$DEFAULT_AUTO_COMMIT_ON_PHASE_PASS}"
CODEX_ENDPOINT="${CODEX_ENDPOINT:-$DEFAULT_CODEX_ENDPOINT}"
CODEX_USE_RESPONSES_SCHEMA="${CODEX_USE_RESPONSES_SCHEMA:-$DEFAULT_CODEX_USE_RESPONSES_SCHEMA}"
CODEX_RESPONSES_SCHEMA_FILE="${CODEX_RESPONSES_SCHEMA_FILE:-$DEFAULT_CODEX_RESPONSES_SCHEMA_FILE}"
CODEX_THINKING_OVERRIDE="${CODEX_THINKING_OVERRIDE:-$DEFAULT_CODEX_THINKING_OVERRIDE}"
CLAUDE_ENDPOINT="${CLAUDE_ENDPOINT:-$DEFAULT_CLAUDE_ENDPOINT}"
CLAUDE_THINKING_OVERRIDE="${CLAUDE_THINKING_OVERRIDE:-$DEFAULT_CLAUDE_THINKING_OVERRIDE}"
RUN_AGENT_MAX_ATTEMPTS="${RUN_AGENT_MAX_ATTEMPTS:-$DEFAULT_RUN_AGENT_MAX_ATTEMPTS}"
RUN_AGENT_RETRY_DELAY_SECONDS="${RUN_AGENT_RETRY_DELAY_SECONDS:-$DEFAULT_RUN_AGENT_RETRY_DELAY_SECONDS}"
RUN_AGENT_RETRY_VERBOSE="${RUN_AGENT_RETRY_VERBOSE:-$DEFAULT_RUN_AGENT_RETRY_VERBOSE}"
ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS="${ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS:-$DEFAULT_ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS}"
ENGINE_OUTPUT_TO_STDOUT="${ENGINE_OUTPUT_TO_STDOUT:-$DEFAULT_ENGINE_OUTPUT_TO_STDOUT}"
STRICT_VALIDATION_NOOP="${STRICT_VALIDATION_NOOP:-$DEFAULT_STRICT_VALIDATION_NOOP}"
PHASE_COMPLETION_MAX_ATTEMPTS="${PHASE_COMPLETION_MAX_ATTEMPTS:-$DEFAULT_PHASE_COMPLETION_MAX_ATTEMPTS}"
PHASE_COMPLETION_RETRY_DELAY_SECONDS="${PHASE_COMPLETION_RETRY_DELAY_SECONDS:-$DEFAULT_PHASE_COMPLETION_RETRY_DELAY_SECONDS}"
PHASE_COMPLETION_RETRY_VERBOSE="${PHASE_COMPLETION_RETRY_VERBOSE:-$DEFAULT_PHASE_COMPLETION_RETRY_VERBOSE}"
MAX_CONSENSUS_ROUTING_ATTEMPTS="${MAX_CONSENSUS_ROUTING_ATTEMPTS:-$DEFAULT_MAX_CONSENSUS_ROUTING_ATTEMPTS}"
REQUIRE_LINT_BEFORE_DONE="${REQUIRE_LINT_BEFORE_DONE:-$DEFAULT_REQUIRE_LINT_BEFORE_DONE}"
REQUIRE_DOCUMENT_BEFORE_DONE="${REQUIRE_DOCUMENT_BEFORE_DONE:-$DEFAULT_REQUIRE_DOCUMENT_BEFORE_DONE}"
REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE="${REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE:-$DEFAULT_REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE}"
REQUIRE_PLAN_FRESHNESS_FOR_BUILD="${REQUIRE_PLAN_FRESHNESS_FOR_BUILD:-$DEFAULT_REQUIRE_PLAN_FRESHNESS_FOR_BUILD}"
BACKLOG_SOURCES="${BACKLOG_SOURCES:-$DEFAULT_BACKLOG_SOURCES}"
PHASE_NOOP_POLICY_PLAN="${PHASE_NOOP_POLICY_PLAN:-$DEFAULT_PHASE_NOOP_POLICY_PLAN}"
PHASE_NOOP_POLICY_BUILD="${PHASE_NOOP_POLICY_BUILD:-$DEFAULT_PHASE_NOOP_POLICY_BUILD}"
PHASE_NOOP_POLICY_TEST="${PHASE_NOOP_POLICY_TEST:-$DEFAULT_PHASE_NOOP_POLICY_TEST}"
PHASE_NOOP_POLICY_REFACTOR="${PHASE_NOOP_POLICY_REFACTOR:-$DEFAULT_PHASE_NOOP_POLICY_REFACTOR}"
PHASE_NOOP_POLICY_LINT="${PHASE_NOOP_POLICY_LINT:-$DEFAULT_PHASE_NOOP_POLICY_LINT}"
PHASE_NOOP_POLICY_DOCUMENT="${PHASE_NOOP_POLICY_DOCUMENT:-$DEFAULT_PHASE_NOOP_POLICY_DOCUMENT}"
PHASE_NOOP_PROFILE="${PHASE_NOOP_PROFILE:-$DEFAULT_PHASE_NOOP_PROFILE}"
SESSION_TOKEN_BUDGET="${SESSION_TOKEN_BUDGET:-$DEFAULT_SESSION_TOKEN_BUDGET}"
SESSION_TOKEN_RATE_CENTS_PER_MILLION="${SESSION_TOKEN_RATE_CENTS_PER_MILLION:-$DEFAULT_SESSION_TOKEN_RATE_CENTS_PER_MILLION}"
SESSION_COST_BUDGET_CENTS="${SESSION_COST_BUDGET_CENTS:-$DEFAULT_SESSION_COST_BUDGET_CENTS}"
AUTO_REPAIR_MARKDOWN_ARTIFACTS="${AUTO_REPAIR_MARKDOWN_ARTIFACTS:-$DEFAULT_AUTO_REPAIR_MARKDOWN_ARTIFACTS}"
AUTO_REPAIR_MARKDOWN_DRY_RUN="${AUTO_REPAIR_MARKDOWN_DRY_RUN:-$DEFAULT_AUTO_REPAIR_MARKDOWN_DRY_RUN}"
AUTO_REPAIR_MARKDOWN_BACKUP="${AUTO_REPAIR_MARKDOWN_BACKUP:-$DEFAULT_AUTO_REPAIR_MARKDOWN_BACKUP}"
AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED="${AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED:-$DEFAULT_AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED}"
MARKDOWN_LOCAL_PATH_ALLOWLIST_REGEX="${MARKDOWN_LOCAL_PATH_ALLOWLIST_REGEX:-$DEFAULT_MARKDOWN_LOCAL_PATH_ALLOWLIST_REGEX}"
PHASE_MANIFEST_MODE="${PHASE_MANIFEST_MODE:-$DEFAULT_PHASE_MANIFEST_MODE}"
SWARM_CONSENSUS_TIMEOUT="${SWARM_CONSENSUS_TIMEOUT:-$DEFAULT_SWARM_CONSENSUS_TIMEOUT}"
CONSENSUS_SCORE_THRESHOLD="${CONSENSUS_SCORE_THRESHOLD:-$DEFAULT_CONSENSUS_SCORE_THRESHOLD}"
ENGINE_HEALTH_MAX_ATTEMPTS="${ENGINE_HEALTH_MAX_ATTEMPTS:-$DEFAULT_ENGINE_HEALTH_MAX_ATTEMPTS}"
ENGINE_HEALTH_RETRY_DELAY_SECONDS="${ENGINE_HEALTH_RETRY_DELAY_SECONDS:-$DEFAULT_ENGINE_HEALTH_RETRY_DELAY_SECONDS}"
ENGINE_HEALTH_RETRY_VERBOSE="${ENGINE_HEALTH_RETRY_VERBOSE:-$DEFAULT_ENGINE_HEALTH_RETRY_VERBOSE}"
ENGINE_SMOKE_TEST_TIMEOUT="${ENGINE_SMOKE_TEST_TIMEOUT:-$DEFAULT_ENGINE_SMOKE_TEST_TIMEOUT}"
STARTUP_OPERATIONAL_PROBE="${STARTUP_OPERATIONAL_PROBE:-$DEFAULT_STARTUP_OPERATIONAL_PROBE}"
ENGINE_OVERRIDES_BOOTSTRAPPED="${ENGINE_OVERRIDES_BOOTSTRAPPED:-$DEFAULT_ENGINE_OVERRIDES_BOOTSTRAPPED}"
NOTIFICATIONS_ENABLED="${NOTIFICATIONS_ENABLED:-$DEFAULT_NOTIFICATIONS_ENABLED}"
NOTIFY_TELEGRAM_ENABLED="${NOTIFY_TELEGRAM_ENABLED:-$DEFAULT_NOTIFY_TELEGRAM_ENABLED}"
NOTIFY_DISCORD_ENABLED="${NOTIFY_DISCORD_ENABLED:-$DEFAULT_NOTIFY_DISCORD_ENABLED}"
NOTIFY_DISCORD_WEBHOOK_URL="${NOTIFY_DISCORD_WEBHOOK_URL:-}"
NOTIFY_TTS_ENABLED="${NOTIFY_TTS_ENABLED:-$DEFAULT_NOTIFY_TTS_ENABLED}"
NOTIFY_TTS_STYLE="${NOTIFY_TTS_STYLE:-$DEFAULT_NOTIFY_TTS_STYLE}"
NOTIFY_CHUTES_TTS_URL="${NOTIFY_CHUTES_TTS_URL:-$DEFAULT_NOTIFY_CHUTES_TTS_URL}"
NOTIFY_CHUTES_VOICE="${NOTIFY_CHUTES_VOICE:-$DEFAULT_NOTIFY_CHUTES_VOICE}"
NOTIFY_CHUTES_SPEED="${NOTIFY_CHUTES_SPEED:-$DEFAULT_NOTIFY_CHUTES_SPEED}"
NOTIFY_EVENT_DEDUP_WINDOW_SECONDS="${NOTIFY_EVENT_DEDUP_WINDOW_SECONDS:-$DEFAULT_NOTIFY_EVENT_DEDUP_WINDOW_SECONDS}"
NOTIFY_INCIDENT_REMINDER_MINUTES="${NOTIFY_INCIDENT_REMINDER_MINUTES:-$DEFAULT_NOTIFY_INCIDENT_REMINDER_MINUTES}"
NOTIFICATION_WIZARD_BOOTSTRAPPED="${NOTIFICATION_WIZARD_BOOTSTRAPPED:-$DEFAULT_NOTIFICATION_WIZARD_BOOTSTRAPPED}"
TG_BOT_TOKEN="${TG_BOT_TOKEN:-}"
TG_CHAT_ID="${TG_CHAT_ID:-}"
CHUTES_API_KEY="${CHUTES_API_KEY:-}"

if [ -f "$CONFIG_FILE" ]; then
    load_config_file_safe "$CONFIG_FILE"
fi

# Override with environment variables if present.
ACTIVE_ENGINE="${RALPHIE_ENGINE:-$DEFAULT_ENGINE}"
CODEX_CMD="${CODEX_ENGINE_CMD:-$DEFAULT_CODEX_CMD}"
CLAUDE_CMD="${CLAUDE_ENGINE_CMD:-$DEFAULT_CLAUDE_CMD}"
COMMAND_TIMEOUT_SECONDS="${RALPHIE_COMMAND_TIMEOUT_SECONDS:-$COMMAND_TIMEOUT_SECONDS}"
MAX_ITERATIONS="${RALPHIE_MAX_ITERATIONS:-$MAX_ITERATIONS}"
MAX_SESSION_CYCLES="${RALPHIE_MAX_SESSION_CYCLES:-$MAX_SESSION_CYCLES}"
SESSION_TOKEN_BUDGET="${RALPHIE_SESSION_TOKEN_BUDGET:-$SESSION_TOKEN_BUDGET}"
SESSION_TOKEN_RATE_CENTS_PER_MILLION="${RALPHIE_SESSION_TOKEN_RATE_CENTS_PER_MILLION:-$SESSION_TOKEN_RATE_CENTS_PER_MILLION}"
SESSION_COST_BUDGET_CENTS="${RALPHIE_SESSION_COST_BUDGET_CENTS:-$SESSION_COST_BUDGET_CENTS}"
RUN_AGENT_MAX_ATTEMPTS="${RALPHIE_RUN_AGENT_MAX_ATTEMPTS:-$RUN_AGENT_MAX_ATTEMPTS}"
RUN_AGENT_RETRY_DELAY_SECONDS="${RALPHIE_RUN_AGENT_RETRY_DELAY_SECONDS:-$RUN_AGENT_RETRY_DELAY_SECONDS}"
RUN_AGENT_RETRY_VERBOSE="${RALPHIE_RUN_AGENT_RETRY_VERBOSE:-$RUN_AGENT_RETRY_VERBOSE}"
ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS="${RALPHIE_ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS:-$ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS}"
PHASE_COMPLETION_MAX_ATTEMPTS="${RALPHIE_PHASE_COMPLETION_MAX_ATTEMPTS:-$PHASE_COMPLETION_MAX_ATTEMPTS}"
PHASE_COMPLETION_RETRY_DELAY_SECONDS="${RALPHIE_PHASE_COMPLETION_RETRY_DELAY_SECONDS:-$PHASE_COMPLETION_RETRY_DELAY_SECONDS}"
PHASE_COMPLETION_RETRY_VERBOSE="${RALPHIE_PHASE_COMPLETION_RETRY_VERBOSE:-$PHASE_COMPLETION_RETRY_VERBOSE}"
MAX_CONSENSUS_ROUTING_ATTEMPTS="${RALPHIE_MAX_CONSENSUS_ROUTING_ATTEMPTS:-$MAX_CONSENSUS_ROUTING_ATTEMPTS}"
REQUIRE_LINT_BEFORE_DONE="${RALPHIE_REQUIRE_LINT_BEFORE_DONE:-$REQUIRE_LINT_BEFORE_DONE}"
REQUIRE_DOCUMENT_BEFORE_DONE="${RALPHIE_REQUIRE_DOCUMENT_BEFORE_DONE:-$REQUIRE_DOCUMENT_BEFORE_DONE}"
REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE="${RALPHIE_REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE:-$REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE}"
REQUIRE_PLAN_FRESHNESS_FOR_BUILD="${RALPHIE_REQUIRE_PLAN_FRESHNESS_FOR_BUILD:-$REQUIRE_PLAN_FRESHNESS_FOR_BUILD}"
BACKLOG_SOURCES="${RALPHIE_BACKLOG_SOURCES:-$BACKLOG_SOURCES}"
SWARM_CONSENSUS_TIMEOUT="${RALPHIE_SWARM_CONSENSUS_TIMEOUT:-$SWARM_CONSENSUS_TIMEOUT}"
ENGINE_HEALTH_MAX_ATTEMPTS="${RALPHIE_ENGINE_HEALTH_MAX_ATTEMPTS:-$ENGINE_HEALTH_MAX_ATTEMPTS}"
ENGINE_HEALTH_RETRY_DELAY_SECONDS="${RALPHIE_ENGINE_HEALTH_RETRY_DELAY_SECONDS:-$ENGINE_HEALTH_RETRY_DELAY_SECONDS}"
ENGINE_HEALTH_RETRY_VERBOSE="${RALPHIE_ENGINE_HEALTH_RETRY_VERBOSE:-$ENGINE_HEALTH_RETRY_VERBOSE}"
ENGINE_SMOKE_TEST_TIMEOUT="${RALPHIE_ENGINE_SMOKE_TEST_TIMEOUT:-$ENGINE_SMOKE_TEST_TIMEOUT}"
RESUME_REQUESTED="${RALPHIE_RESUME_REQUESTED:-$DEFAULT_RESUME_REQUESTED}"
REBOOTSTRAP_REQUESTED="${RALPHIE_REBOOTSTRAP_REQUESTED:-$DEFAULT_REBOOTSTRAP_REQUESTED}"
ENGINE_OUTPUT_TO_STDOUT="${RALPHIE_ENGINE_OUTPUT_TO_STDOUT:-$ENGINE_OUTPUT_TO_STDOUT}"
YOLO="${RALPHIE_YOLO:-$YOLO}"
AUTO_UPDATE="${RALPHIE_AUTO_UPDATE:-$AUTO_UPDATE}"
PHASE_WALLCLOCK_LIMIT_SECONDS="${RALPHIE_PHASE_WALLCLOCK_LIMIT_SECONDS:-$PHASE_WALLCLOCK_LIMIT_SECONDS}"
PHASE_NOOP_PROFILE="${RALPHIE_PHASE_NOOP_PROFILE:-$PHASE_NOOP_PROFILE}"
PHASE_NOOP_POLICY_PLAN="${RALPHIE_PHASE_NOOP_POLICY_PLAN:-$PHASE_NOOP_POLICY_PLAN}"
PHASE_NOOP_POLICY_BUILD="${RALPHIE_PHASE_NOOP_POLICY_BUILD:-$PHASE_NOOP_POLICY_BUILD}"
PHASE_NOOP_POLICY_TEST="${RALPHIE_PHASE_NOOP_POLICY_TEST:-$PHASE_NOOP_POLICY_TEST}"
PHASE_NOOP_POLICY_REFACTOR="${RALPHIE_PHASE_NOOP_POLICY_REFACTOR:-$PHASE_NOOP_POLICY_REFACTOR}"
PHASE_NOOP_POLICY_LINT="${RALPHIE_PHASE_NOOP_POLICY_LINT:-$PHASE_NOOP_POLICY_LINT}"
PHASE_NOOP_POLICY_DOCUMENT="${RALPHIE_PHASE_NOOP_POLICY_DOCUMENT:-$PHASE_NOOP_POLICY_DOCUMENT}"
STRICT_VALIDATION_NOOP="${RALPHIE_STRICT_VALIDATION_NOOP:-$STRICT_VALIDATION_NOOP}"
AUTO_REPAIR_MARKDOWN_ARTIFACTS="${RALPHIE_AUTO_REPAIR_MARKDOWN_ARTIFACTS:-$AUTO_REPAIR_MARKDOWN_ARTIFACTS}"
AUTO_REPAIR_MARKDOWN_DRY_RUN="${RALPHIE_AUTO_REPAIR_MARKDOWN_DRY_RUN:-$AUTO_REPAIR_MARKDOWN_DRY_RUN}"
AUTO_REPAIR_MARKDOWN_BACKUP="${RALPHIE_AUTO_REPAIR_MARKDOWN_BACKUP:-$AUTO_REPAIR_MARKDOWN_BACKUP}"
AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED="${RALPHIE_AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED:-$AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED}"
MARKDOWN_LOCAL_PATH_ALLOWLIST_REGEX="${RALPHIE_MARKDOWN_LOCAL_PATH_ALLOWLIST_REGEX:-$MARKDOWN_LOCAL_PATH_ALLOWLIST_REGEX}"
PHASE_MANIFEST_MODE="${RALPHIE_PHASE_MANIFEST_MODE:-$PHASE_MANIFEST_MODE}"
AUTO_PLAN_BACKFILL_ON_IDLE_BUILD="${RALPHIE_AUTO_PLAN_BACKFILL_ON_IDLE_BUILD:-$AUTO_PLAN_BACKFILL_ON_IDLE_BUILD}"
AUTO_ENGINE_PREFERENCE="${RALPHIE_AUTO_ENGINE_PREFERENCE:-$AUTO_ENGINE_PREFERENCE}"
AUTO_INIT_GIT_IF_MISSING="${RALPHIE_AUTO_INIT_GIT_IF_MISSING:-$AUTO_INIT_GIT_IF_MISSING}"
AUTO_COMMIT_ON_PHASE_PASS="${RALPHIE_AUTO_COMMIT_ON_PHASE_PASS:-$AUTO_COMMIT_ON_PHASE_PASS}"
AUTO_UPDATE="${RALPHIE_AUTO_UPDATE:-$AUTO_UPDATE}"
AUTO_UPDATE_URL="${RALPHIE_AUTO_UPDATE_URL:-$AUTO_UPDATE_URL}"
AUTO_UPDATE_ALLOW_DIRTY="${RALPHIE_AUTO_UPDATE_ALLOW_DIRTY:-$AUTO_UPDATE_ALLOW_DIRTY}"
AUTO_UPDATE_ALLOW_INSECURE="${RALPHIE_AUTO_UPDATE_ALLOW_INSECURE:-$AUTO_UPDATE_ALLOW_INSECURE}"
AUTO_UPDATE_TIMEOUT_SECONDS="${RALPHIE_AUTO_UPDATE_TIMEOUT_SECONDS:-$AUTO_UPDATE_TIMEOUT_SECONDS}"
AUTO_UPDATE_LOCK_TIMEOUT_SECONDS="${RALPHIE_AUTO_UPDATE_LOCK_TIMEOUT_SECONDS:-$AUTO_UPDATE_LOCK_TIMEOUT_SECONDS}"
CODEX_ENDPOINT="${RALPHIE_CODEX_ENDPOINT:-$CODEX_ENDPOINT}"
CODEX_MODEL="${RALPHIE_CODEX_MODEL:-${CODEX_MODEL:-}}"
CODEX_USE_RESPONSES_SCHEMA="${RALPHIE_CODEX_USE_RESPONSES_SCHEMA:-$CODEX_USE_RESPONSES_SCHEMA}"
CODEX_RESPONSES_SCHEMA_FILE="${RALPHIE_CODEX_RESPONSES_SCHEMA_FILE:-$CODEX_RESPONSES_SCHEMA_FILE}"
CODEX_THINKING_OVERRIDE="${RALPHIE_CODEX_THINKING_OVERRIDE:-$CODEX_THINKING_OVERRIDE}"
CLAUDE_ENDPOINT="${RALPHIE_CLAUDE_ENDPOINT:-$CLAUDE_ENDPOINT}"
CLAUDE_MODEL="${RALPHIE_CLAUDE_MODEL:-${CLAUDE_MODEL:-}}"
CLAUDE_THINKING_OVERRIDE="${RALPHIE_CLAUDE_THINKING_OVERRIDE:-$CLAUDE_THINKING_OVERRIDE}"
STARTUP_OPERATIONAL_PROBE="${RALPHIE_STARTUP_OPERATIONAL_PROBE:-$STARTUP_OPERATIONAL_PROBE}"
CONSENSUS_SCORE_THRESHOLD="${RALPHIE_CONSENSUS_SCORE_THRESHOLD:-$CONSENSUS_SCORE_THRESHOLD}"
ENGINE_OVERRIDES_BOOTSTRAPPED="${RALPHIE_ENGINE_OVERRIDES_BOOTSTRAPPED:-$ENGINE_OVERRIDES_BOOTSTRAPPED}"
NOTIFICATIONS_ENABLED="${RALPHIE_NOTIFICATIONS_ENABLED:-$NOTIFICATIONS_ENABLED}"
NOTIFY_TELEGRAM_ENABLED="${RALPHIE_NOTIFY_TELEGRAM_ENABLED:-$NOTIFY_TELEGRAM_ENABLED}"
NOTIFY_DISCORD_ENABLED="${RALPHIE_NOTIFY_DISCORD_ENABLED:-$NOTIFY_DISCORD_ENABLED}"
NOTIFY_DISCORD_WEBHOOK_URL="${RALPHIE_NOTIFY_DISCORD_WEBHOOK_URL:-$NOTIFY_DISCORD_WEBHOOK_URL}"
NOTIFY_TTS_ENABLED="${RALPHIE_NOTIFY_TTS_ENABLED:-$NOTIFY_TTS_ENABLED}"
NOTIFY_TTS_STYLE="${RALPHIE_NOTIFY_TTS_STYLE:-$NOTIFY_TTS_STYLE}"
NOTIFY_CHUTES_TTS_URL="${RALPHIE_NOTIFY_CHUTES_TTS_URL:-$NOTIFY_CHUTES_TTS_URL}"
NOTIFY_CHUTES_VOICE="${RALPHIE_NOTIFY_CHUTES_VOICE:-$NOTIFY_CHUTES_VOICE}"
NOTIFY_CHUTES_SPEED="${RALPHIE_NOTIFY_CHUTES_SPEED:-$NOTIFY_CHUTES_SPEED}"
NOTIFY_EVENT_DEDUP_WINDOW_SECONDS="${RALPHIE_NOTIFY_EVENT_DEDUP_WINDOW_SECONDS:-$NOTIFY_EVENT_DEDUP_WINDOW_SECONDS}"
NOTIFY_INCIDENT_REMINDER_MINUTES="${RALPHIE_NOTIFY_INCIDENT_REMINDER_MINUTES:-$NOTIFY_INCIDENT_REMINDER_MINUTES}"
NOTIFICATION_WIZARD_BOOTSTRAPPED="${RALPHIE_NOTIFICATION_WIZARD_BOOTSTRAPPED:-$NOTIFICATION_WIZARD_BOOTSTRAPPED}"
TG_BOT_TOKEN="${RALPHIE_TG_BOT_TOKEN:-$TG_BOT_TOKEN}"
TG_CHAT_ID="${RALPHIE_TG_CHAT_ID:-$TG_CHAT_ID}"
CHUTES_API_KEY="${RALPHIE_CHUTES_API_KEY:-$CHUTES_API_KEY}"

# Treat env-provided phase no-op policies as explicit user intent so profile
# application does not overwrite them.
if printenv PHASE_NOOP_POLICY_PLAN >/dev/null 2>&1 || printenv RALPHIE_PHASE_NOOP_POLICY_PLAN >/dev/null 2>&1; then PHASE_NOOP_POLICY_PLAN_EXPLICIT=true; fi
if printenv PHASE_NOOP_POLICY_BUILD >/dev/null 2>&1 || printenv RALPHIE_PHASE_NOOP_POLICY_BUILD >/dev/null 2>&1; then PHASE_NOOP_POLICY_BUILD_EXPLICIT=true; fi
if printenv PHASE_NOOP_POLICY_TEST >/dev/null 2>&1 || printenv RALPHIE_PHASE_NOOP_POLICY_TEST >/dev/null 2>&1; then PHASE_NOOP_POLICY_TEST_EXPLICIT=true; fi
if printenv PHASE_NOOP_POLICY_REFACTOR >/dev/null 2>&1 || printenv RALPHIE_PHASE_NOOP_POLICY_REFACTOR >/dev/null 2>&1; then PHASE_NOOP_POLICY_REFACTOR_EXPLICIT=true; fi
if printenv PHASE_NOOP_POLICY_LINT >/dev/null 2>&1 || printenv RALPHIE_PHASE_NOOP_POLICY_LINT >/dev/null 2>&1; then PHASE_NOOP_POLICY_LINT_EXPLICIT=true; fi
if printenv PHASE_NOOP_POLICY_DOCUMENT >/dev/null 2>&1 || printenv RALPHIE_PHASE_NOOP_POLICY_DOCUMENT >/dev/null 2>&1; then PHASE_NOOP_POLICY_DOCUMENT_EXPLICIT=true; fi

# Validate engine selection
ENGINE_SELECTION_REQUESTED="$(to_lower "$ACTIVE_ENGINE")"
case "$ENGINE_SELECTION_REQUESTED" in
    claude|codex|auto) ;;
    *)
        warn "Unrecognized engine '$ENGINE_SELECTION_REQUESTED'. Falling back to '$DEFAULT_ENGINE'."
        ENGINE_SELECTION_REQUESTED="$DEFAULT_ENGINE"
        ;;
esac
AUTO_ENGINE_PREFERENCE="$(to_lower "$AUTO_ENGINE_PREFERENCE")"
case "$AUTO_ENGINE_PREFERENCE" in
    codex|claude) ;;
    *)
        warn "Invalid AUTO_ENGINE_PREFERENCE '$AUTO_ENGINE_PREFERENCE'. Falling back to '$DEFAULT_AUTO_ENGINE_PREFERENCE'."
        AUTO_ENGINE_PREFERENCE="$DEFAULT_AUTO_ENGINE_PREFERENCE"
        ;;
esac

AUTO_COMMIT_ON_PHASE_PASS="$(to_lower "$AUTO_COMMIT_ON_PHASE_PASS")"
if ! is_bool_like "$AUTO_COMMIT_ON_PHASE_PASS"; then
    warn "Invalid AUTO_COMMIT_ON_PHASE_PASS '$AUTO_COMMIT_ON_PHASE_PASS'. Falling back to '$DEFAULT_AUTO_COMMIT_ON_PHASE_PASS'."
    AUTO_COMMIT_ON_PHASE_PASS="$DEFAULT_AUTO_COMMIT_ON_PHASE_PASS"
fi

AUTO_UPDATE="$(to_lower "$AUTO_UPDATE")"
if ! is_bool_like "$AUTO_UPDATE"; then
    warn "Invalid AUTO_UPDATE '$AUTO_UPDATE'. Falling back to '$DEFAULT_AUTO_UPDATE'."
    AUTO_UPDATE="$DEFAULT_AUTO_UPDATE"
fi

AUTO_UPDATE_ALLOW_DIRTY="$(to_lower "$AUTO_UPDATE_ALLOW_DIRTY")"
if ! is_bool_like "$AUTO_UPDATE_ALLOW_DIRTY"; then
    warn "Invalid AUTO_UPDATE_ALLOW_DIRTY '$AUTO_UPDATE_ALLOW_DIRTY'. Falling back to '$DEFAULT_AUTO_UPDATE_ALLOW_DIRTY'."
    AUTO_UPDATE_ALLOW_DIRTY="$DEFAULT_AUTO_UPDATE_ALLOW_DIRTY"
fi

AUTO_UPDATE_ALLOW_INSECURE="$(to_lower "$AUTO_UPDATE_ALLOW_INSECURE")"
if ! is_bool_like "$AUTO_UPDATE_ALLOW_INSECURE"; then
    warn "Invalid AUTO_UPDATE_ALLOW_INSECURE '$AUTO_UPDATE_ALLOW_INSECURE'. Falling back to '$DEFAULT_AUTO_UPDATE_ALLOW_INSECURE'."
    AUTO_UPDATE_ALLOW_INSECURE="$DEFAULT_AUTO_UPDATE_ALLOW_INSECURE"
fi

if ! is_number "$AUTO_UPDATE_TIMEOUT_SECONDS" || [ "$AUTO_UPDATE_TIMEOUT_SECONDS" -lt 1 ]; then
    warn "Invalid AUTO_UPDATE_TIMEOUT_SECONDS '$AUTO_UPDATE_TIMEOUT_SECONDS'. Falling back to '$DEFAULT_AUTO_UPDATE_TIMEOUT_SECONDS'."
    AUTO_UPDATE_TIMEOUT_SECONDS="$DEFAULT_AUTO_UPDATE_TIMEOUT_SECONDS"
fi

if ! is_number "$AUTO_UPDATE_LOCK_TIMEOUT_SECONDS"; then
    warn "Invalid AUTO_UPDATE_LOCK_TIMEOUT_SECONDS '$AUTO_UPDATE_LOCK_TIMEOUT_SECONDS'. Falling back to '$DEFAULT_AUTO_UPDATE_LOCK_TIMEOUT_SECONDS'."
    AUTO_UPDATE_LOCK_TIMEOUT_SECONDS="$DEFAULT_AUTO_UPDATE_LOCK_TIMEOUT_SECONDS"
fi

AUTO_INIT_GIT_IF_MISSING="$(to_lower "$AUTO_INIT_GIT_IF_MISSING")"
if ! is_bool_like "$AUTO_INIT_GIT_IF_MISSING"; then
    warn "Invalid AUTO_INIT_GIT_IF_MISSING '$AUTO_INIT_GIT_IF_MISSING'. Falling back to '$DEFAULT_AUTO_INIT_GIT_IF_MISSING'."
    AUTO_INIT_GIT_IF_MISSING="$DEFAULT_AUTO_INIT_GIT_IF_MISSING"
fi

AUTO_PLAN_BACKFILL_ON_IDLE_BUILD="$(to_lower "$AUTO_PLAN_BACKFILL_ON_IDLE_BUILD")"
if ! is_bool_like "$AUTO_PLAN_BACKFILL_ON_IDLE_BUILD"; then
    warn "Invalid AUTO_PLAN_BACKFILL_ON_IDLE_BUILD '$AUTO_PLAN_BACKFILL_ON_IDLE_BUILD'. Falling back to 'true'."
    AUTO_PLAN_BACKFILL_ON_IDLE_BUILD="true"
fi

if ! is_number "$ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS" || [ "$ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS" -lt 0 ]; then
    warn "Invalid ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS '$ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS'. Falling back to '$DEFAULT_ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS'."
    ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS="$DEFAULT_ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS"
fi

AUTO_REPAIR_MARKDOWN_DRY_RUN="$(to_lower "$AUTO_REPAIR_MARKDOWN_DRY_RUN")"
if ! is_bool_like "$AUTO_REPAIR_MARKDOWN_DRY_RUN"; then
    warn "Invalid AUTO_REPAIR_MARKDOWN_DRY_RUN '$AUTO_REPAIR_MARKDOWN_DRY_RUN'. Falling back to '$DEFAULT_AUTO_REPAIR_MARKDOWN_DRY_RUN'."
    AUTO_REPAIR_MARKDOWN_DRY_RUN="$DEFAULT_AUTO_REPAIR_MARKDOWN_DRY_RUN"
fi

AUTO_REPAIR_MARKDOWN_BACKUP="$(to_lower "$AUTO_REPAIR_MARKDOWN_BACKUP")"
if ! is_bool_like "$AUTO_REPAIR_MARKDOWN_BACKUP"; then
    warn "Invalid AUTO_REPAIR_MARKDOWN_BACKUP '$AUTO_REPAIR_MARKDOWN_BACKUP'. Falling back to '$DEFAULT_AUTO_REPAIR_MARKDOWN_BACKUP'."
    AUTO_REPAIR_MARKDOWN_BACKUP="$DEFAULT_AUTO_REPAIR_MARKDOWN_BACKUP"
fi

AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED="$(to_lower "$AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED")"
if ! is_bool_like "$AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED"; then
    warn "Invalid AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED '$AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED'. Falling back to '$DEFAULT_AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED'."
    AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED="$DEFAULT_AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED"
fi

if [ -n "$MARKDOWN_LOCAL_PATH_ALLOWLIST_REGEX" ] && ! awk_regex_is_valid "$MARKDOWN_LOCAL_PATH_ALLOWLIST_REGEX"; then
    warn "Invalid MARKDOWN_LOCAL_PATH_ALLOWLIST_REGEX; disabling markdown path allowlist."
    MARKDOWN_LOCAL_PATH_ALLOWLIST_REGEX="$DEFAULT_MARKDOWN_LOCAL_PATH_ALLOWLIST_REGEX"
fi

PHASE_MANIFEST_MODE="$(normalize_phase_manifest_mode "$PHASE_MANIFEST_MODE")"

CODEX_USE_RESPONSES_SCHEMA="$(to_lower "$CODEX_USE_RESPONSES_SCHEMA")"
if ! is_bool_like "$CODEX_USE_RESPONSES_SCHEMA"; then
    warn "Invalid CODEX_USE_RESPONSES_SCHEMA '$CODEX_USE_RESPONSES_SCHEMA'. Falling back to '$DEFAULT_CODEX_USE_RESPONSES_SCHEMA'."
    CODEX_USE_RESPONSES_SCHEMA="$DEFAULT_CODEX_USE_RESPONSES_SCHEMA"
fi

CODEX_THINKING_OVERRIDE="$(to_lower "$CODEX_THINKING_OVERRIDE")"
case "$CODEX_THINKING_OVERRIDE" in
    none|minimal|low|medium|high|xhigh|"") ;;
    *)
        warn "Invalid CODEX_THINKING_OVERRIDE '$CODEX_THINKING_OVERRIDE'. Falling back to '$DEFAULT_CODEX_THINKING_OVERRIDE'."
        CODEX_THINKING_OVERRIDE="$DEFAULT_CODEX_THINKING_OVERRIDE"
        ;;
esac

CLAUDE_THINKING_OVERRIDE="$(to_lower "$CLAUDE_THINKING_OVERRIDE")"
case "$CLAUDE_THINKING_OVERRIDE" in
    none|off|low|medium|high|xhigh|"") ;;
    *)
        warn "Invalid CLAUDE_THINKING_OVERRIDE '$CLAUDE_THINKING_OVERRIDE'. Falling back to '$DEFAULT_CLAUDE_THINKING_OVERRIDE'."
        CLAUDE_THINKING_OVERRIDE="$DEFAULT_CLAUDE_THINKING_OVERRIDE"
        ;;
esac

if ! is_number "$CONSENSUS_SCORE_THRESHOLD" || [ "$CONSENSUS_SCORE_THRESHOLD" -lt 0 ] || [ "$CONSENSUS_SCORE_THRESHOLD" -gt 100 ]; then
    warn "Invalid CONSENSUS_SCORE_THRESHOLD '$CONSENSUS_SCORE_THRESHOLD'. Falling back to '$DEFAULT_CONSENSUS_SCORE_THRESHOLD'."
    CONSENSUS_SCORE_THRESHOLD="$DEFAULT_CONSENSUS_SCORE_THRESHOLD"
fi

REQUIRE_LINT_BEFORE_DONE="$(to_lower "$REQUIRE_LINT_BEFORE_DONE")"
if ! is_bool_like "$REQUIRE_LINT_BEFORE_DONE"; then
    warn "Invalid REQUIRE_LINT_BEFORE_DONE '$REQUIRE_LINT_BEFORE_DONE'. Falling back to '$DEFAULT_REQUIRE_LINT_BEFORE_DONE'."
    REQUIRE_LINT_BEFORE_DONE="$DEFAULT_REQUIRE_LINT_BEFORE_DONE"
fi

REQUIRE_DOCUMENT_BEFORE_DONE="$(to_lower "$REQUIRE_DOCUMENT_BEFORE_DONE")"
if ! is_bool_like "$REQUIRE_DOCUMENT_BEFORE_DONE"; then
    warn "Invalid REQUIRE_DOCUMENT_BEFORE_DONE '$REQUIRE_DOCUMENT_BEFORE_DONE'. Falling back to '$DEFAULT_REQUIRE_DOCUMENT_BEFORE_DONE'."
    REQUIRE_DOCUMENT_BEFORE_DONE="$DEFAULT_REQUIRE_DOCUMENT_BEFORE_DONE"
fi

REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE="$(to_lower "$REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE")"
if ! is_bool_like "$REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE"; then
    warn "Invalid REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE '$REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE'. Falling back to '$DEFAULT_REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE'."
    REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE="$DEFAULT_REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE"
fi

REQUIRE_PLAN_FRESHNESS_FOR_BUILD="$(to_lower "$REQUIRE_PLAN_FRESHNESS_FOR_BUILD")"
if ! is_bool_like "$REQUIRE_PLAN_FRESHNESS_FOR_BUILD"; then
    warn "Invalid REQUIRE_PLAN_FRESHNESS_FOR_BUILD '$REQUIRE_PLAN_FRESHNESS_FOR_BUILD'. Falling back to '$DEFAULT_REQUIRE_PLAN_FRESHNESS_FOR_BUILD'."
    REQUIRE_PLAN_FRESHNESS_FOR_BUILD="$DEFAULT_REQUIRE_PLAN_FRESHNESS_FOR_BUILD"
fi

if [ -z "$(sanitize_text_for_log "$BACKLOG_SOURCES")" ]; then
    BACKLOG_SOURCES="$DEFAULT_BACKLOG_SOURCES"
fi

if ! is_number "$PHASE_WALLCLOCK_LIMIT_SECONDS" || [ "$PHASE_WALLCLOCK_LIMIT_SECONDS" -lt 0 ]; then
    warn "Invalid PHASE_WALLCLOCK_LIMIT_SECONDS '$PHASE_WALLCLOCK_LIMIT_SECONDS'. Falling back to '$DEFAULT_PHASE_WALLCLOCK_LIMIT_SECONDS'."
    PHASE_WALLCLOCK_LIMIT_SECONDS="$DEFAULT_PHASE_WALLCLOCK_LIMIT_SECONDS"
fi

ENGINE_OVERRIDES_BOOTSTRAPPED="$(to_lower "$ENGINE_OVERRIDES_BOOTSTRAPPED")"
if ! is_bool_like "$ENGINE_OVERRIDES_BOOTSTRAPPED"; then
    warn "Invalid ENGINE_OVERRIDES_BOOTSTRAPPED '$ENGINE_OVERRIDES_BOOTSTRAPPED'. Falling back to '$DEFAULT_ENGINE_OVERRIDES_BOOTSTRAPPED'."
    ENGINE_OVERRIDES_BOOTSTRAPPED="$DEFAULT_ENGINE_OVERRIDES_BOOTSTRAPPED"
fi

NOTIFICATIONS_ENABLED="$(to_lower "$NOTIFICATIONS_ENABLED")"
if ! is_bool_like "$NOTIFICATIONS_ENABLED"; then
    warn "Invalid NOTIFICATIONS_ENABLED '$NOTIFICATIONS_ENABLED'. Falling back to '$DEFAULT_NOTIFICATIONS_ENABLED'."
    NOTIFICATIONS_ENABLED="$DEFAULT_NOTIFICATIONS_ENABLED"
fi

NOTIFY_TELEGRAM_ENABLED="$(to_lower "$NOTIFY_TELEGRAM_ENABLED")"
if ! is_bool_like "$NOTIFY_TELEGRAM_ENABLED"; then
    warn "Invalid NOTIFY_TELEGRAM_ENABLED '$NOTIFY_TELEGRAM_ENABLED'. Falling back to '$DEFAULT_NOTIFY_TELEGRAM_ENABLED'."
    NOTIFY_TELEGRAM_ENABLED="$DEFAULT_NOTIFY_TELEGRAM_ENABLED"
fi

NOTIFY_DISCORD_ENABLED="$(to_lower "$NOTIFY_DISCORD_ENABLED")"
if ! is_bool_like "$NOTIFY_DISCORD_ENABLED"; then
    warn "Invalid NOTIFY_DISCORD_ENABLED '$NOTIFY_DISCORD_ENABLED'. Falling back to '$DEFAULT_NOTIFY_DISCORD_ENABLED'."
    NOTIFY_DISCORD_ENABLED="$DEFAULT_NOTIFY_DISCORD_ENABLED"
fi

NOTIFY_TTS_ENABLED="$(to_lower "$NOTIFY_TTS_ENABLED")"
if ! is_bool_like "$NOTIFY_TTS_ENABLED"; then
    warn "Invalid NOTIFY_TTS_ENABLED '$NOTIFY_TTS_ENABLED'. Falling back to '$DEFAULT_NOTIFY_TTS_ENABLED'."
    NOTIFY_TTS_ENABLED="$DEFAULT_NOTIFY_TTS_ENABLED"
fi
NOTIFY_TTS_STYLE="$(to_lower "$NOTIFY_TTS_STYLE")"
case "$NOTIFY_TTS_STYLE" in
    standard|friendly|ralph_wiggum) ;;
    ralph) NOTIFY_TTS_STYLE="ralph_wiggum" ;;
    *)
        warn "Invalid NOTIFY_TTS_STYLE '$NOTIFY_TTS_STYLE'. Falling back to '$DEFAULT_NOTIFY_TTS_STYLE'."
        NOTIFY_TTS_STYLE="$DEFAULT_NOTIFY_TTS_STYLE"
        ;;
esac

NOTIFICATION_WIZARD_BOOTSTRAPPED="$(to_lower "$NOTIFICATION_WIZARD_BOOTSTRAPPED")"
if ! is_bool_like "$NOTIFICATION_WIZARD_BOOTSTRAPPED"; then
    warn "Invalid NOTIFICATION_WIZARD_BOOTSTRAPPED '$NOTIFICATION_WIZARD_BOOTSTRAPPED'. Falling back to '$DEFAULT_NOTIFICATION_WIZARD_BOOTSTRAPPED'."
    NOTIFICATION_WIZARD_BOOTSTRAPPED="$DEFAULT_NOTIFICATION_WIZARD_BOOTSTRAPPED"
fi

if ! is_decimal_number "$NOTIFY_CHUTES_SPEED"; then
    warn "Invalid NOTIFY_CHUTES_SPEED '$NOTIFY_CHUTES_SPEED'. Falling back to '$DEFAULT_NOTIFY_CHUTES_SPEED'."
    NOTIFY_CHUTES_SPEED="$DEFAULT_NOTIFY_CHUTES_SPEED"
fi
if ! is_number "$NOTIFY_EVENT_DEDUP_WINDOW_SECONDS" || [ "$NOTIFY_EVENT_DEDUP_WINDOW_SECONDS" -lt 0 ]; then
    warn "Invalid NOTIFY_EVENT_DEDUP_WINDOW_SECONDS '$NOTIFY_EVENT_DEDUP_WINDOW_SECONDS'. Falling back to '$DEFAULT_NOTIFY_EVENT_DEDUP_WINDOW_SECONDS'."
    NOTIFY_EVENT_DEDUP_WINDOW_SECONDS="$DEFAULT_NOTIFY_EVENT_DEDUP_WINDOW_SECONDS"
fi
if ! is_number "$NOTIFY_INCIDENT_REMINDER_MINUTES" || [ "$NOTIFY_INCIDENT_REMINDER_MINUTES" -lt 0 ]; then
    warn "Invalid NOTIFY_INCIDENT_REMINDER_MINUTES '$NOTIFY_INCIDENT_REMINDER_MINUTES'. Falling back to '$DEFAULT_NOTIFY_INCIDENT_REMINDER_MINUTES'."
    NOTIFY_INCIDENT_REMINDER_MINUTES="$DEFAULT_NOTIFY_INCIDENT_REMINDER_MINUTES"
fi
if [ -z "$NOTIFY_CHUTES_TTS_URL" ]; then
    NOTIFY_CHUTES_TTS_URL="$DEFAULT_NOTIFY_CHUTES_TTS_URL"
fi
if [ -z "$NOTIFY_CHUTES_VOICE" ]; then
    NOTIFY_CHUTES_VOICE="$DEFAULT_NOTIFY_CHUTES_VOICE"
fi

if ! command -v curl >/dev/null 2>&1 && is_true "$NOTIFICATIONS_ENABLED"; then
    warn "Notifications requested but 'curl' is unavailable. Disabling notifications."
    NOTIFICATIONS_ENABLED="false"
fi

if is_true "$NOTIFY_TELEGRAM_ENABLED"; then
    if [ -z "$TG_BOT_TOKEN" ] || [ -z "$TG_CHAT_ID" ]; then
        warn "Telegram notifications enabled but TG_BOT_TOKEN/TG_CHAT_ID are incomplete. Disabling Telegram channel."
        NOTIFY_TELEGRAM_ENABLED="false"
    fi
fi
if is_true "$NOTIFY_DISCORD_ENABLED" && [ -z "$NOTIFY_DISCORD_WEBHOOK_URL" ]; then
    warn "Discord notifications enabled but webhook URL is empty. Disabling Discord channel."
    NOTIFY_DISCORD_ENABLED="false"
fi
if is_true "$NOTIFY_TTS_ENABLED"; then
    if ! is_true "$NOTIFY_TELEGRAM_ENABLED" && ! is_true "$NOTIFY_DISCORD_ENABLED"; then
        warn "TTS notifications require Telegram or Discord notifications. Disabling TTS channel."
        NOTIFY_TTS_ENABLED="false"
    elif [ -z "$CHUTES_API_KEY" ]; then
        warn "TTS notifications enabled but CHUTES_API_KEY is empty. Disabling TTS channel."
        NOTIFY_TTS_ENABLED="false"
    fi
fi

if [ "$NOTIFY_TELEGRAM_ENABLED" != "true" ] && [ "$NOTIFY_DISCORD_ENABLED" != "true" ]; then
    NOTIFICATIONS_ENABLED="false"
fi

if [ "$ENGINE_SELECTION_REQUESTED" = "codex" ]; then
    ACTIVE_ENGINE="codex"
    ACTIVE_CMD="$CODEX_CMD"
elif [ "$ENGINE_SELECTION_REQUESTED" = "claude" ]; then
    ACTIVE_ENGINE="claude"
    ACTIVE_CMD="$CLAUDE_CMD"
else
    # Keep auto as the requested mode; resolve_active_engine will select the
    # active runtime engine each loop based on health/capabilities.
    ACTIVE_ENGINE="auto"
    if [ "$AUTO_ENGINE_PREFERENCE" = "claude" ]; then
        if command -v "$CLAUDE_CMD" >/dev/null 2>&1; then
            ACTIVE_CMD="$CLAUDE_CMD"
        elif command -v "$CODEX_CMD" >/dev/null 2>&1; then
            ACTIVE_CMD="$CODEX_CMD"
        else
            ACTIVE_CMD="$CLAUDE_CMD"
        fi
    else
        if command -v "$CODEX_CMD" >/dev/null 2>&1; then
            ACTIVE_CMD="$CODEX_CMD"
        elif command -v "$CLAUDE_CMD" >/dev/null 2>&1; then
            ACTIVE_CMD="$CLAUDE_CMD"
        else
            ACTIVE_CMD="$CODEX_CMD"
        fi
    fi
fi

# Runtime State variables (these change during the loop)
CURRENT_PHASE="plan"
CURRENT_PHASE_INDEX=0
ITERATION_COUNT=0
SESSION_ID="$(date +%Y%m%d_%H%M%S)_$(printf '%s' "${EPOCHREALTIME:-$(date +%s)}" | tr -d '.')_$$_$(portable_random)"
SESSION_ATTEMPT_COUNT=0
SESSION_TOKEN_COUNT=0
SESSION_COST_CENTS=0
LAST_RUN_TOKEN_COUNT=0
LAST_CONSENSUS_SCORE=0
LAST_CONSENSUS_PASS=false
LAST_CONSENSUS_DIR=""
LAST_CONSENSUS_SUMMARY=""
LAST_CONSENSUS_NEXT_PHASE="done"
LAST_CONSENSUS_NEXT_PHASE_REASON="no consensus recommendation"
LAST_CONSENSUS_RESPONDED_VOTES=0
LAST_CONSENSUS_FAILURE_KIND="none"
LAST_CONSENSUS_FAILURE_REASON=""
LAST_DONE_GUARD_REASON=""
LAST_DONE_GUARD_NEXT_PHASE="done"
LAST_PHASE_ROUTE_GUARD_REASON=""
LAST_PHASE_ROUTE_GUARD_NEXT_PHASE="done"
LAST_BACKLOG_STALE_SOURCES=""
PLAN_FRESHNESS_FINGERPRINT=""
LAST_GATE_DECISION_RECORDED_AT=""
LAST_GATE_DECISION_PHASE=""
LAST_GATE_DECISION_ATTEMPT=0
LAST_GATE_DECISION_STAGE=""
LAST_GATE_DECISION_OUTCOME=""
LAST_GATE_DECISION_SCORE=0
LAST_GATE_DECISION_PASS=false
LAST_GATE_DECISION_RESPONDED_VOTES=0
LAST_GATE_DECISION_NEXT_PHASE=""
LAST_GATE_DECISION_SUMMARY=""
LAST_HANDOFF_SCORE=0
LAST_HANDOFF_VERDICT="HOLD"
LAST_HANDOFF_GAPS="no explicit gaps"
PHASE_TRANSITION_HISTORY=()
CONSENSUS_NO_ENGINES=false
CURRENT_PHASE_ATTEMPT=1
PHASE_ATTEMPT_IN_PROGRESS="false"
AUTO_COMMIT_SESSION_ENABLED="false"
GIT_IDENTITY_READY="unknown"
GIT_IDENTITY_SOURCE="unknown"
NOTIFY_LAST_EVENT_SIGNATURE=""
NOTIFY_LAST_EVENT_SENT_AT=0
NOTIFY_INCIDENT_SERIES_ACTIVE="false"
NOTIFY_INCIDENT_SERIES_KEY=""
NOTIFY_INCIDENT_SERIES_STARTED_AT=0
NOTIFY_INCIDENT_LAST_SENT_AT=0
NOTIFY_INCIDENT_REPEAT_COUNT=0

# Capability Probing results (populated by probe_engine_capabilities)
CLAUDE_CAP_PRINT=0
CLAUDE_CAP_YOLO_FLAG=""
CODEX_CAP_OUTPUT_LAST_MESSAGE=0
CODEX_CAP_YOLO_FLAG=0
ENGINE_CAPABILITIES_PROBED=false
CODEX_CAP_NOTE=""
CLAUDE_CAP_NOTE=""
CODEX_HEALTHY="false"
CLAUDE_HEALTHY="false"
CODEX_SMOKE_PASS="false"
CLAUDE_SMOKE_PASS="false"
LAST_ENGINE_SELECTION_BLOCK_REASON=""

# Resilience Dial implementation
get_reviewer_count() {
    case "$RALPHIE_QUALITY_LEVEL" in
        minimal) echo 1 ;;
        standard) echo 3 ;;
        high) echo 5 ;;
        *) echo 3 ;;
    esac
}

get_parallel_reviewer_count() {
    case "$RALPHIE_QUALITY_LEVEL" in
        minimal) echo 1 ;;
        standard) echo 2 ;;
        high) echo 4 ;;
        *) echo 2 ;;
    esac
}

get_reviewer_max_retries() {
    case "$RALPHIE_QUALITY_LEVEL" in
        minimal) echo 0 ;;
        standard) echo 1 ;;
        high) echo 2 ;;
        *) echo 1 ;;
    esac
}

# State Management with Integrity Checks
# Returns the highest-preferred available command for SHA-256 checksums.
sha256sum_command() {
    if command -v sha256sum >/dev/null 2>&1; then
        echo "sha256sum"
        return 0
    fi
    if command -v shasum >/dev/null 2>&1; then
        echo "shasum"
        return 0
    fi
    return 1
}

sha256_file_sum() {
    local file="$1"
    local checksum_cmd

    checksum_cmd="$(sha256sum_command)" || {
        warn "No SHA-256 command available for file checksum calculation."
        return 1
    }

    if [ "$checksum_cmd" = "sha256sum" ]; then
        "$checksum_cmd" "$file" | cut -d' ' -f1
    else
        "$checksum_cmd" -a 256 "$file" | cut -d' ' -f1
    fi
}

sha256_stream_sum() {
    local checksum_cmd

    checksum_cmd="$(sha256sum_command)" || return 1

    if [ "$checksum_cmd" = "sha256sum" ]; then
        "$checksum_cmd" | awk '{print $1}'
    else
        "$checksum_cmd" -a 256 | awk '{print $1}'
    fi
}

self_update_current_script_path() {
    printf '%s/%s' "$SCRIPT_DIR" "$(basename "${BASH_SOURCE[0]}")"
}

self_update_acquire_lock() {
    local lock_dir="$1"
    local timeout_seconds="${2:-30}"
    local waited=0
    local owner_pid=""
    local pid_file="$lock_dir/pid"

    is_number "$timeout_seconds" || timeout_seconds=30
    while ! mkdir "$lock_dir" 2>/dev/null; do
        owner_pid=""
        if [ -f "$pid_file" ]; then
            owner_pid="$(head -n 1 "$pid_file" 2>/dev/null | tr -cd '0-9' || true)"
        fi
        if is_number "$owner_pid" && ! kill -0 "$owner_pid" 2>/dev/null; then
            rm -rf "$lock_dir" 2>/dev/null || true
            continue
        fi
        if [ "$waited" -ge "$timeout_seconds" ]; then
            return 1
        fi
        sleep 1
        waited=$((waited + 1))
    done

    printf '%s\n' "$$" > "$pid_file" 2>/dev/null || true
    return 0
}

self_update_release_lock() {
    local lock_dir="${1:-}"
    local pid_file owner_pid
    [ -n "$lock_dir" ] || return 0
    pid_file="$lock_dir/pid"
    if [ -f "$pid_file" ]; then
        owner_pid="$(head -n 1 "$pid_file" 2>/dev/null | tr -cd '0-9' || true)"
        if [ -n "$owner_pid" ] && [ "$owner_pid" != "$$" ]; then
            return 0
        fi
    fi
    rm -rf "$lock_dir" 2>/dev/null || true
}

self_update_url_escape_path() {
    local value="${1:-}"
    if command -v python3 >/dev/null 2>&1; then
        python3 - "$value" <<'PY' 2>/dev/null && return 0
import sys
from urllib.parse import quote
print(quote(sys.argv[1], safe="/"))
PY
    fi
    printf '%s' "$value" | sed 's/ /%20/g'
}

self_update_derive_github_raw_url() {
    command -v git >/dev/null 2>&1 || return 1

    local self_path git_root rel_path remote_url branch repo_path owner repo encoded_path
    self_path="$(self_update_current_script_path)"
    git_root="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
    [ -n "$git_root" ] || return 1
    case "$self_path" in
        "$git_root"/*) rel_path="${self_path#"$git_root"/}" ;;
        *) return 1 ;;
    esac

    remote_url="$(git -C "$git_root" config --get remote.origin.url 2>/dev/null || true)"
    [ -n "$remote_url" ] || return 1
    branch="$(git -C "$git_root" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
    if [ -z "$branch" ]; then
        branch="$(git -C "$git_root" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    fi
    [ -n "$branch" ] && [ "$branch" != "HEAD" ] || return 1

    case "$remote_url" in
        https://github.com/*) repo_path="${remote_url#https://github.com/}" ;;
        http://github.com/*) repo_path="${remote_url#http://github.com/}" ;;
        git@github.com:*) repo_path="${remote_url#git@github.com:}" ;;
        ssh://git@github.com/*) repo_path="${remote_url#ssh://git@github.com/}" ;;
        *) return 1 ;;
    esac
    repo_path="${repo_path%.git}"
    owner="${repo_path%%/*}"
    repo="${repo_path#*/}"
    repo="${repo%%/*}"
    repo="${repo%.git}"
    [ -n "$owner" ] && [ -n "$repo" ] && [ "$repo" != "$repo_path" ] || return 1

    encoded_path="$(self_update_url_escape_path "$rel_path")"
    printf 'https://raw.githubusercontent.com/%s/%s/%s/%s\n' "$owner" "$repo" "$branch" "$encoded_path"
}

self_update_url_is_allowed() {
    local url="${1:-}"
    case "$url" in
        https://*) return 0 ;;
        file://*|/*|./*|../*) return 0 ;;
        http://*)
            is_true "${AUTO_UPDATE_ALLOW_INSECURE:-false}" && return 0
            return 1
            ;;
        *) return 1 ;;
    esac
}

self_update_download_to_file() {
    local url="$1"
    local dest="$2"
    local timeout_seconds="${3:-20}"
    local max_bytes=2000000
    local local_path=""

    case "$url" in
        file://*)
            local_path="${url#file://}"
            [ -f "$local_path" ] || return 1
            cp "$local_path" "$dest"
            return $?
            ;;
        /*|./*|../*)
            [ -f "$url" ] || return 1
            cp "$url" "$dest"
            return $?
            ;;
    esac

    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --retry 2 --connect-timeout "$timeout_seconds" --max-time "$timeout_seconds" --max-filesize "$max_bytes" -o "$dest" "$url"
        return $?
    fi
    if command -v wget >/dev/null 2>&1; then
        wget -q -T "$timeout_seconds" -O "$dest" "$url"
        return $?
    fi
    if command -v python3 >/dev/null 2>&1; then
        python3 - "$url" "$dest" "$timeout_seconds" "$max_bytes" <<'PY'
import sys
import urllib.request

url, dest, timeout, max_bytes = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
with urllib.request.urlopen(url, timeout=timeout) as response:
    data = response.read(max_bytes + 1)
if len(data) > max_bytes:
    raise SystemExit("remote ralphie.sh exceeds maximum auto-update size")
with open(dest, "wb") as handle:
    handle.write(data)
PY
        return $?
    fi
    return 1
}

self_update_candidate_is_valid() {
    local candidate="$1"
    local bytes=""
    [ -f "$candidate" ] || return 1
    bytes="$(wc -c < "$candidate" | tr -d ' ')"
    is_number "$bytes" || return 1
    [ "$bytes" -ge 200 ] && [ "$bytes" -le 2000000 ] || return 1
    head -n 1 "$candidate" | grep -qE '^#!.*(bash|env[[:space:]]+bash)' || return 1
    if LC_ALL=C grep -q "$(printf '\r')" "$candidate"; then
        return 1
    fi
    grep -q 'Ralphie - Unified autonomous loop' "$candidate" || return 1
    grep -q '^SCRIPT_VERSION=' "$candidate" || return 1
    grep -q 'parse_args "$@"' "$candidate" || return 1
    grep -q 'self_update_check_and_reexec "$@"' "$candidate" || return 1
    grep -q 'RALPHIE_SKIP_AUTO_UPDATE' "$candidate" || return 1
    grep -q 'main "$@"' "$candidate" || return 1
    bash -n "$candidate" >/dev/null 2>&1
}

self_update_script_is_dirty() {
    command -v git >/dev/null 2>&1 || return 1

    local self_path git_root rel_path
    self_path="$(self_update_current_script_path)"
    git_root="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
    [ -n "$git_root" ] || return 1
    case "$self_path" in
        "$git_root"/*) rel_path="${self_path#"$git_root"/}" ;;
        *) return 1 ;;
    esac
    git -C "$git_root" ls-files --error-unmatch -- "$rel_path" >/dev/null 2>&1 || return 0
    ! git -C "$git_root" diff --quiet -- "$rel_path" 2>/dev/null && return 0
    ! git -C "$git_root" diff --cached --quiet -- "$rel_path" 2>/dev/null && return 0
    return 1
}

self_update_check_and_reexec() {
    is_true "${AUTO_UPDATE:-false}" || return 0
    [ "${RALPHIE_SKIP_AUTO_UPDATE:-}" != "1" ] || return 0
    [ "${RALPHIE_SELF_UPDATE_REEXECED:-}" != "1" ] || return 0

    local self_path update_url update_dir update_lock_dir tmp_candidate backup_path current_hash candidate_hash timestamp mode
    self_path="$(self_update_current_script_path)"
    if [ ! -f "$self_path" ]; then
        warn "Auto-update skipped: current script path is not a file."
        return 0
    fi

    update_dir="$CONFIG_DIR/self-update"
    mkdir -p "$update_dir" || {
        warn "Auto-update skipped: could not create $(path_for_display "$update_dir")."
        return 0
    }
    chmod 700 "$update_dir" 2>/dev/null || true
    update_lock_dir="$update_dir/update.lock"
    if ! self_update_acquire_lock "$update_lock_dir" "${AUTO_UPDATE_LOCK_TIMEOUT_SECONDS:-30}"; then
        warn "Auto-update skipped: another Ralphie self-update is still in progress."
        return 0
    fi

    update_url="${AUTO_UPDATE_URL:-}"
    if [ -z "$update_url" ]; then
        update_url="$(self_update_derive_github_raw_url || true)"
    fi
    if [ -z "$update_url" ]; then
        warn "Auto-update skipped: set AUTO_UPDATE_URL or run from a GitHub checkout with origin/current branch."
        self_update_release_lock "$update_lock_dir"
        return 0
    fi
    if ! self_update_url_is_allowed "$update_url"; then
        warn "Auto-update skipped: update URL must be https://, file://, or a local path. Set AUTO_UPDATE_ALLOW_INSECURE=true only for trusted http:// origins."
        self_update_release_lock "$update_lock_dir"
        return 0
    fi

    if ! is_true "${AUTO_UPDATE_ALLOW_DIRTY:-false}" && self_update_script_is_dirty; then
        warn "Auto-update skipped: local ralphie.sh has uncommitted changes. Set AUTO_UPDATE_ALLOW_DIRTY=true to override."
        self_update_release_lock "$update_lock_dir"
        return 0
    fi
    tmp_candidate="$(mktemp "$update_dir/ralphie.remote.XXXXXX")" || {
        warn "Auto-update skipped: could not create temporary update file."
        self_update_release_lock "$update_lock_dir"
        return 0
    }

    info "Auto-update: checking remote ralphie.sh from $(redact_endpoint_for_log "$update_url")."
    if ! self_update_download_to_file "$update_url" "$tmp_candidate" "${AUTO_UPDATE_TIMEOUT_SECONDS:-20}"; then
        warn "Auto-update skipped: failed to fetch remote ralphie.sh."
        rm -f "$tmp_candidate"
        self_update_release_lock "$update_lock_dir"
        return 0
    fi
    if ! self_update_candidate_is_valid "$tmp_candidate"; then
        warn "Auto-update skipped: remote ralphie.sh failed validation."
        rm -f "$tmp_candidate"
        self_update_release_lock "$update_lock_dir"
        return 0
    fi
    if cmp -s "$self_path" "$tmp_candidate"; then
        info "Auto-update: current ralphie.sh already matches remote."
        rm -f "$tmp_candidate"
        self_update_release_lock "$update_lock_dir"
        return 0
    fi

    current_hash="$(sha256_file_sum "$self_path" 2>/dev/null || echo "unknown")"
    candidate_hash="$(sha256_file_sum "$tmp_candidate" 2>/dev/null || echo "unknown")"
    timestamp="$(date '+%Y%m%d_%H%M%S')"
    backup_path="$update_dir/ralphie.sh.${timestamp}.bak"
    if ! cp -p "$self_path" "$backup_path"; then
        warn "Auto-update skipped: could not write backup before replacing ralphie.sh."
        rm -f "$tmp_candidate"
        self_update_release_lock "$update_lock_dir"
        return 0
    fi

    mode="$(stat -c '%a' "$self_path" 2>/dev/null || stat -f '%Lp' "$self_path" 2>/dev/null || echo "")"
    if [ -n "$mode" ]; then
        chmod "$mode" "$tmp_candidate" 2>/dev/null || chmod +x "$tmp_candidate" 2>/dev/null || true
    else
        chmod +x "$tmp_candidate" 2>/dev/null || true
    fi
    if ! mv "$tmp_candidate" "$self_path"; then
        warn "Auto-update failed: could not atomically replace ralphie.sh. Backup remains at $(path_for_display "$backup_path")."
        rm -f "$tmp_candidate"
        self_update_release_lock "$update_lock_dir"
        return 0
    fi

    success "Auto-update: replaced ralphie.sh ($current_hash -> $candidate_hash). Backup: $(path_for_display "$backup_path")."
    self_update_release_lock "$update_lock_dir"
    exec env RALPHIE_SKIP_AUTO_UPDATE=1 RALPHIE_SELF_UPDATE_REEXECED=1 "$self_path" "$@"
    warn "Auto-update failed: replacement succeeded but re-exec failed. Restoring backup."
    cp -p "$backup_path" "$self_path" 2>/dev/null || true
    exec env RALPHIE_SKIP_AUTO_UPDATE=1 RALPHIE_SELF_UPDATE_REEXECED=1 "$self_path" "$@"
}

state_blob_encode() {
    local payload="${1:-}"
    if command -v base64 >/dev/null 2>&1; then
        printf '%s' "$payload" | base64 | tr -d '\n'
        return "${PIPESTATUS[1]:-$?}"
    fi
    if command -v openssl >/dev/null 2>&1; then
        printf '%s' "$payload" | openssl base64 -A 2>/dev/null
        return "${PIPESTATUS[1]:-$?}"
    fi
    return 1
}

state_blob_decode() {
    local payload="${1:-}"
    [ -z "$payload" ] && { echo ""; return 0; }

    if command -v base64 >/dev/null 2>&1; then
        printf '%s' "$payload" | base64 --decode 2>/dev/null && return 0
        printf '%s' "$payload" | base64 -d 2>/dev/null && return 0
        printf '%s' "$payload" | base64 -D 2>/dev/null && return 0
    fi
    if command -v openssl >/dev/null 2>&1; then
        printf '%s' "$payload" | openssl base64 -d -A 2>/dev/null && return 0
    fi
    return 1
}

state_escape_value() {
    config_escape_double_quotes "${1:-}"
}

state_unescape_value() {
    local value="${1:-}"
    local bslash_sentinel=$'\001'

    value="${value//\\\\/$bslash_sentinel}"
    value="${value//\\n/$'\n'}"
    value="${value//\\r/$'\r'}"
    value="${value//\\t/$'\t'}"
    value="${value//\\\"/\"}"
    value="${value//$bslash_sentinel/\\}"
    printf '%s' "$value"
}

gate_decision_trim_text() {
    local value="${1:-}"
    local limit="${2:-1200}"

    is_number "$limit" || limit=1200
    value="$(sanitize_text_for_log "$value")"
    if [ "$limit" -gt 0 ]; then
        value="$(printf '%s' "$value" | cut -c 1-"$limit")"
    fi
    printf '%s' "$value"
}

record_gate_decision() {
    local phase="${1:-unknown}"
    local attempt="${2:-0}"
    local stage="${3:-phase-gate}"
    local outcome="${4:-unknown}"
    local next_phase="${5:-${LAST_CONSENSUS_NEXT_PHASE:-unknown}}"
    local explainer="${6:-${LAST_CONSENSUS_NEXT_PHASE_REASON:-no explicit routing rationale}}"
    local voting_summary
    local handoff_summary
    local failure_summary=""

    voting_summary="$(gate_decision_trim_text "${LAST_CONSENSUS_SUMMARY:-no reviewer summary}" 1400)"
    [ -n "$voting_summary" ] || voting_summary="no reviewer summary"
    explainer="$(gate_decision_trim_text "$explainer" 900)"
    [ -n "$explainer" ] || explainer="no explicit routing rationale"
    handoff_summary="$(gate_decision_trim_text "handoff verdict=${LAST_HANDOFF_VERDICT:-unknown} score=${LAST_HANDOFF_SCORE:-0} gaps=${LAST_HANDOFF_GAPS:-none}" 500)"
    if [ "${LAST_CONSENSUS_FAILURE_KIND:-none}" != "none" ] || [ -n "${LAST_CONSENSUS_FAILURE_REASON:-}" ]; then
        failure_summary="$(gate_decision_trim_text "failure=${LAST_CONSENSUS_FAILURE_KIND:-unknown}: ${LAST_CONSENSUS_FAILURE_REASON:-unspecified}" 500)"
    fi

    LAST_GATE_DECISION_RECORDED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || true)"
    LAST_GATE_DECISION_PHASE="$phase"
    LAST_GATE_DECISION_ATTEMPT="$attempt"
    LAST_GATE_DECISION_STAGE="$stage"
    LAST_GATE_DECISION_OUTCOME="$outcome"
    LAST_GATE_DECISION_SCORE="${LAST_CONSENSUS_SCORE:-0}"
    LAST_GATE_DECISION_PASS="${LAST_CONSENSUS_PASS:-false}"
    LAST_GATE_DECISION_RESPONDED_VOTES="${LAST_CONSENSUS_RESPONDED_VOTES:-0}"
    LAST_GATE_DECISION_NEXT_PHASE="$next_phase"
    LAST_GATE_DECISION_SUMMARY="$(printf 'score=%s pass=%s votes=%s next=%s outcome=%s\nvoting: %s\nexplainer: %s\n%s' \
        "$LAST_GATE_DECISION_SCORE" \
        "$LAST_GATE_DECISION_PASS" \
        "$LAST_GATE_DECISION_RESPONDED_VOTES" \
        "$LAST_GATE_DECISION_NEXT_PHASE" \
        "$LAST_GATE_DECISION_OUTCOME" \
        "$voting_summary" \
        "$explainer" \
        "$handoff_summary")"
    if [ -n "$failure_summary" ]; then
        LAST_GATE_DECISION_SUMMARY="${LAST_GATE_DECISION_SUMMARY}
$failure_summary"
    fi
}

save_state() {
    mkdir -p "$(dirname "$STATE_FILE")"
    local checksum
    local tmp_state_file
    local history_payload=""
    local history_encoded=""

    if [ "${#PHASE_TRANSITION_HISTORY[@]}" -gt 0 ]; then
        history_payload="$(printf '%s\n' "${PHASE_TRANSITION_HISTORY[@]}")"
        history_encoded="$(state_blob_encode "$history_payload" 2>/dev/null || true)"
        if [ -z "$history_encoded" ]; then
            warn "Could not encode phase transition history for state persistence."
        fi
    fi

    tmp_state_file="$(mktemp "$CONFIG_DIR/state.tmp.XXXXXX")" || {
        warn "Could not create temporary state file in $(path_for_display "$CONFIG_DIR")."
        return 1
    }

    {
        printf 'CURRENT_PHASE="%s"\n' "$(state_escape_value "$CURRENT_PHASE")"
        printf 'CURRENT_PHASE_INDEX="%s"\n' "$(state_escape_value "$CURRENT_PHASE_INDEX")"
        printf 'CURRENT_PHASE_ATTEMPT="%s"\n' "$(state_escape_value "$CURRENT_PHASE_ATTEMPT")"
        printf 'PHASE_ATTEMPT_IN_PROGRESS="%s"\n' "$(state_escape_value "$PHASE_ATTEMPT_IN_PROGRESS")"
        printf 'ITERATION_COUNT="%s"\n' "$(state_escape_value "$ITERATION_COUNT")"
        printf 'SESSION_ID="%s"\n' "$(state_escape_value "$SESSION_ID")"
        printf 'SESSION_ATTEMPT_COUNT="%s"\n' "$(state_escape_value "$SESSION_ATTEMPT_COUNT")"
        printf 'SESSION_TOKEN_COUNT="%s"\n' "$(state_escape_value "$SESSION_TOKEN_COUNT")"
        printf 'SESSION_COST_CENTS="%s"\n' "$(state_escape_value "$SESSION_COST_CENTS")"
        printf 'LAST_RUN_TOKEN_COUNT="%s"\n' "$(state_escape_value "$LAST_RUN_TOKEN_COUNT")"
        printf 'ENGINE_OUTPUT_TO_STDOUT="%s"\n' "$(state_escape_value "$ENGINE_OUTPUT_TO_STDOUT")"
        printf 'PHASE_TRANSITION_HISTORY_B64="%s"\n' "$(state_escape_value "$history_encoded")"
        printf 'PLAN_FRESHNESS_FINGERPRINT="%s"\n' "$(state_escape_value "$PLAN_FRESHNESS_FINGERPRINT")"
        printf 'GIT_IDENTITY_READY="%s"\n' "$(state_escape_value "$GIT_IDENTITY_READY")"
        printf 'GIT_IDENTITY_SOURCE="%s"\n' "$(state_escape_value "$GIT_IDENTITY_SOURCE")"
        printf 'LAST_GATE_DECISION_RECORDED_AT="%s"\n' "$(state_escape_value "$LAST_GATE_DECISION_RECORDED_AT")"
        printf 'LAST_GATE_DECISION_PHASE="%s"\n' "$(state_escape_value "$LAST_GATE_DECISION_PHASE")"
        printf 'LAST_GATE_DECISION_ATTEMPT="%s"\n' "$(state_escape_value "$LAST_GATE_DECISION_ATTEMPT")"
        printf 'LAST_GATE_DECISION_STAGE="%s"\n' "$(state_escape_value "$LAST_GATE_DECISION_STAGE")"
        printf 'LAST_GATE_DECISION_OUTCOME="%s"\n' "$(state_escape_value "$LAST_GATE_DECISION_OUTCOME")"
        printf 'LAST_GATE_DECISION_SCORE="%s"\n' "$(state_escape_value "$LAST_GATE_DECISION_SCORE")"
        printf 'LAST_GATE_DECISION_PASS="%s"\n' "$(state_escape_value "$LAST_GATE_DECISION_PASS")"
        printf 'LAST_GATE_DECISION_RESPONDED_VOTES="%s"\n' "$(state_escape_value "$LAST_GATE_DECISION_RESPONDED_VOTES")"
        printf 'LAST_GATE_DECISION_NEXT_PHASE="%s"\n' "$(state_escape_value "$LAST_GATE_DECISION_NEXT_PHASE")"
        printf 'LAST_GATE_DECISION_SUMMARY="%s"\n' "$(state_escape_value "$LAST_GATE_DECISION_SUMMARY")"
    } > "$tmp_state_file"
    # Append SHA-256 checksum to the end
    if checksum="$(sha256_file_sum "$tmp_state_file")"; then
        echo "STATE_CHECKSUM=\"$checksum\"" >> "$tmp_state_file"
    else
        warn "Could not calculate state checksum; continuing without integrity metadata."
    fi

    if ! mv "$tmp_state_file" "$STATE_FILE"; then
        warn "Could not atomically update state file: $(path_for_display "$STATE_FILE")"
        rm -f "$tmp_state_file"
        return 1
    fi
    return 0
}

save_state_or_exit() {
    local checkpoint="${1:-unspecified checkpoint}"
    if save_state; then
        return 0
    fi

    err "Failed to persist state at checkpoint: $checkpoint"
    log_reason_code "RB_STATE_SAVE_FAILED" "state persistence failed at checkpoint: $checkpoint"
    notify_event "session_error" "state_persist_failed" "checkpoint=$checkpoint" || true
    release_lock
    exit 1
}

load_state() {
    if [ ! -f "$STATE_FILE" ]; then return 1; fi

    CURRENT_PHASE="plan"
    CURRENT_PHASE_INDEX=0
    CURRENT_PHASE_ATTEMPT=1
    PHASE_ATTEMPT_IN_PROGRESS="false"
    ITERATION_COUNT=0
    SESSION_ID=""
    SESSION_ATTEMPT_COUNT=0
    SESSION_TOKEN_COUNT=0
    SESSION_COST_CENTS=0
    LAST_RUN_TOKEN_COUNT=0
    ENGINE_OUTPUT_TO_STDOUT="$DEFAULT_ENGINE_OUTPUT_TO_STDOUT"
    PHASE_TRANSITION_HISTORY=()
    PLAN_FRESHNESS_FINGERPRINT=""
    LAST_GATE_DECISION_RECORDED_AT=""
    LAST_GATE_DECISION_PHASE=""
    LAST_GATE_DECISION_ATTEMPT=0
    LAST_GATE_DECISION_STAGE=""
    LAST_GATE_DECISION_OUTCOME=""
    LAST_GATE_DECISION_SCORE=0
    LAST_GATE_DECISION_PASS=false
    LAST_GATE_DECISION_RESPONDED_VOTES=0
    LAST_GATE_DECISION_NEXT_PHASE=""
    LAST_GATE_DECISION_SUMMARY=""
    GIT_IDENTITY_READY="unknown"
    GIT_IDENTITY_SOURCE="unknown"
    local phase_transition_history_b64=""

    # Verify checksum if present
    if grep -q "STATE_CHECKSUM=" "$STATE_FILE"; then
        local expected actual state_body_file
        expected="$(grep "STATE_CHECKSUM=" "$STATE_FILE" | head -n 1 | cut -d'"' -f2)"
        state_body_file="$(mktemp "$CONFIG_DIR/state-body.XXXXXX")" || {
            warn "Unable to create temp file for state checksum validation."
            return 1
        }
        if grep -v "^STATE_CHECKSUM=" "$STATE_FILE" > "$state_body_file" 2>/dev/null && actual="$(sha256_file_sum "$state_body_file")"; then
            if [ -n "$expected" ] && [ "$expected" != "$actual" ]; then
                warn "State file checksum mismatch! Corruption detected. Forcing clean state."
                log_reason_code "RB_STATE_CORRUPTION" "checksum mismatch in state file"
                rm -f "$state_body_file"
                return 1
            fi
        else
            warn "Unable to validate state checksum. Proceeding without enforcing integrity."
        fi
        rm -f "$state_body_file"
    fi

    while IFS='=' read -r key value; do
        [ -z "$key" ] && continue
        value="${value%\"}"
        value="${value#\"}"
        value="$(state_unescape_value "$value")"
        case "$key" in
            CURRENT_PHASE) CURRENT_PHASE="$value" ;;
            CURRENT_PHASE_INDEX) is_number "$value" && CURRENT_PHASE_INDEX="$value" ;;
            CURRENT_PHASE_ATTEMPT) is_number "$value" && CURRENT_PHASE_ATTEMPT="$value" ;;
            PHASE_ATTEMPT_IN_PROGRESS) is_bool_like "$value" && PHASE_ATTEMPT_IN_PROGRESS="$value" ;;
            ITERATION_COUNT) is_number "$value" && ITERATION_COUNT="$value" ;;
            SESSION_ID) SESSION_ID="$value" ;;
            SESSION_ATTEMPT_COUNT) is_number "$value" && SESSION_ATTEMPT_COUNT="$value" ;;
            SESSION_TOKEN_COUNT) is_number "$value" && SESSION_TOKEN_COUNT="$value" ;;
            SESSION_COST_CENTS) is_number "$value" && SESSION_COST_CENTS="$value" ;;
            LAST_RUN_TOKEN_COUNT) is_number "$value" && LAST_RUN_TOKEN_COUNT="$value" ;;
            ENGINE_OUTPUT_TO_STDOUT) [ -n "$value" ] && ENGINE_OUTPUT_TO_STDOUT="$value" ;;
            PHASE_TRANSITION_HISTORY_B64) phase_transition_history_b64="$value" ;;
            PLAN_FRESHNESS_FINGERPRINT) PLAN_FRESHNESS_FINGERPRINT="$value" ;;
            GIT_IDENTITY_READY) is_bool_like "$value" && GIT_IDENTITY_READY="$value" ;;
            GIT_IDENTITY_SOURCE) [ -n "$value" ] && GIT_IDENTITY_SOURCE="$value" ;;
            LAST_GATE_DECISION_RECORDED_AT) LAST_GATE_DECISION_RECORDED_AT="$value" ;;
            LAST_GATE_DECISION_PHASE) LAST_GATE_DECISION_PHASE="$value" ;;
            LAST_GATE_DECISION_ATTEMPT) is_number "$value" && LAST_GATE_DECISION_ATTEMPT="$value" ;;
            LAST_GATE_DECISION_STAGE) LAST_GATE_DECISION_STAGE="$value" ;;
            LAST_GATE_DECISION_OUTCOME) LAST_GATE_DECISION_OUTCOME="$value" ;;
            LAST_GATE_DECISION_SCORE) is_number "$value" && LAST_GATE_DECISION_SCORE="$value" ;;
            LAST_GATE_DECISION_PASS) is_bool_like "$value" && LAST_GATE_DECISION_PASS="$value" ;;
            LAST_GATE_DECISION_RESPONDED_VOTES) is_number "$value" && LAST_GATE_DECISION_RESPONDED_VOTES="$value" ;;
            LAST_GATE_DECISION_NEXT_PHASE) LAST_GATE_DECISION_NEXT_PHASE="$value" ;;
            LAST_GATE_DECISION_SUMMARY) LAST_GATE_DECISION_SUMMARY="$value" ;;
            STATE_CHECKSUM) ;;
            *) ;;
        esac
    done < "$STATE_FILE"

    if ! is_number "$CURRENT_PHASE_INDEX"; then
        CURRENT_PHASE_INDEX=0
    fi
    CURRENT_PHASE="$(normalize_phase_name "$CURRENT_PHASE")"
    local derived_phase_index
    derived_phase_index="$(phase_index_or_done "$CURRENT_PHASE" 2>/dev/null || echo 0)"
    if is_number "$derived_phase_index" && [ "$derived_phase_index" -ge 0 ] && [ "$derived_phase_index" -ne "$CURRENT_PHASE_INDEX" ]; then
        warn "Persisted state mismatch: CURRENT_PHASE='$CURRENT_PHASE' but CURRENT_PHASE_INDEX='$CURRENT_PHASE_INDEX'. Correcting index to '$derived_phase_index'."
        CURRENT_PHASE_INDEX="$derived_phase_index"
    fi
    if ! is_number "$CURRENT_PHASE_ATTEMPT" || [ "$CURRENT_PHASE_ATTEMPT" -lt 1 ]; then
        CURRENT_PHASE_ATTEMPT=1
    fi
    if ! is_bool_like "$PHASE_ATTEMPT_IN_PROGRESS"; then
        PHASE_ATTEMPT_IN_PROGRESS="false"
    fi
    if [ -n "$phase_transition_history_b64" ]; then
        local decoded_phase_history
        decoded_phase_history="$(state_blob_decode "$phase_transition_history_b64" 2>/dev/null || true)"
        if [ -n "$decoded_phase_history" ]; then
            mapfile -t PHASE_TRANSITION_HISTORY <<< "$decoded_phase_history"
        else
            PHASE_TRANSITION_HISTORY=()
            warn "Phase transition history could not be decoded from persisted state."
        fi
    fi
    return 0
}

estimate_file_token_count() {
    local file="$1"
    if [ ! -f "$file" ]; then
        echo 0
        return 0
    fi

    local bytes
    bytes="$(wc -c < "$file" 2>/dev/null | tr -d ' ' || echo 0)"
    if ! is_number "$bytes"; then
        echo 0
        return 0
    fi
    echo $(( (bytes + 3) / 4 ))
}

estimate_run_tokens() {
    local prompt_file="$1"
    local log_file="$2"
    local output_file="$3"

    local tokens
    local prompt_tokens
    local log_tokens
    local output_tokens
    prompt_tokens="$(estimate_file_token_count "$prompt_file")"
    log_tokens="$(estimate_file_token_count "$log_file")"
    output_tokens="$(estimate_file_token_count "$output_file")"
    tokens="$(( prompt_tokens + log_tokens + output_tokens ))"
    echo "$tokens"
}

charge_session_budget() {
    local tokens="$1"
    if ! is_number "$tokens"; then
        tokens=0
    fi
    SESSION_ATTEMPT_COUNT=$((SESSION_ATTEMPT_COUNT + 1))
    SESSION_TOKEN_COUNT=$((SESSION_TOKEN_COUNT + tokens))

    if is_number "$SESSION_TOKEN_RATE_CENTS_PER_MILLION" && [ "$SESSION_TOKEN_RATE_CENTS_PER_MILLION" -gt 0 ]; then
        local run_cost
        run_cost=$(( tokens * SESSION_TOKEN_RATE_CENTS_PER_MILLION / 1000000 ))
        SESSION_COST_CENTS=$((SESSION_COST_CENTS + run_cost))
    fi

    LAST_RUN_TOKEN_COUNT="$tokens"
}

enforce_session_budget() {
    local reason_prefix="${1:-run}"
    if is_number "$MAX_SESSION_CYCLES" && [ "$MAX_SESSION_CYCLES" -gt 0 ] && [ "$SESSION_ATTEMPT_COUNT" -ge "$MAX_SESSION_CYCLES" ]; then
        log_reason_code "RB_SESSION_CYCLE_BUDGET_EXCEEDED" "$reason_prefix: session cycle budget exceeded at $SESSION_ATTEMPT_COUNT/$MAX_SESSION_CYCLES attempts"
        return 1
    fi
    if is_number "$SESSION_TOKEN_BUDGET" && [ "$SESSION_TOKEN_BUDGET" -gt 0 ] && [ "$SESSION_TOKEN_COUNT" -gt "$SESSION_TOKEN_BUDGET" ]; then
        log_reason_code "RB_SESSION_TOKEN_BUDGET_EXCEEDED" "$reason_prefix: session token budget exceeded at $SESSION_TOKEN_COUNT/$SESSION_TOKEN_BUDGET"
        return 1
    fi
    if is_number "$SESSION_COST_BUDGET_CENTS" && [ "$SESSION_COST_BUDGET_CENTS" -gt 0 ] && [ "$SESSION_COST_CENTS" -gt "$SESSION_COST_BUDGET_CENTS" ]; then
        log_reason_code "RB_SESSION_COST_BUDGET_EXCEEDED" "$reason_prefix: session cost budget exceeded at $SESSION_COST_CENTS/$SESSION_COST_BUDGET_CENTS cents"
        return 1
    fi
    return 0
}

# Interactive Questions
is_tty_input_available() {
    if [ -t 0 ]; then
        return 0
    fi
    [ -e /dev/tty ] && { : < /dev/tty > /dev/tty; } 2>/dev/null
}

prompt_read_line() {
    local prompt="$1"
    local default="$2"
    local response=""

    if [ -t 0 ]; then
        read -rp "$prompt" response
        echo "${response:-$default}"
        return 0
    fi

    if is_tty_input_available; then
        if { exec 9<>/dev/tty; } 2>/dev/null; then
            printf '%s' "$prompt" >&9
            if IFS= read -r -u 9 response; then
                exec 9>&- 9<&-
                echo "${response:-$default}"
                return 0
            fi
            exec 9>&- 9<&-
        fi
    fi

    echo "$default"
}

prompt_yes_no() {
    local prompt="$1"
    local default="${2:-y}"
    local response
    local default_marker="[Y/n]"

    case "$(to_lower "$default")" in
        n|no|false|0) default_marker="[y/N]" ;;
        *) default_marker="[Y/n]" ;;
    esac

    response="$(prompt_read_line "$prompt $default_marker: " "$default")"
    case "${response}" in
        [Yy]*) echo "true"; return 0 ;;
        *) echo "false"; return 1 ;;
    esac
}

prompt_line() {
    local prompt="$1"
    local default="$2"
    prompt_read_line "$prompt [$default]: " "$default"
}

prompt_optional_line() {
    local prompt="$1"
    local default="${2:-}"
    prompt_read_line "$prompt: " "$default"
}

prompt_multiline_block() {
    local prompt="$1"
    local default="${2:-}"
    local sentinel="${3:-EOF}"
    local line=""
    local result=""

    if ! { exec 9<>/dev/tty; } 2>/dev/null; then
        printf '%s' "$default"
        return 0
    fi

    {
        printf '%s\n' "$prompt"
        printf 'Paste multi-line input, then end with a line containing only %s (or press Ctrl+D).\n' "$sentinel"
        printf 'Press Enter immediately to keep current/default.\n'
        printf '> '
    } >&9

    while IFS= read -r -u 9 line; do
        if [ -z "$result" ] && [ -z "$line" ]; then
            exec 9>&- 9<&-
            printf '%s' "$default"
            return 0
        fi
        if [ "$line" = "$sentinel" ]; then
            break
        fi
        result="${result}${result:+$'\n'}$line"
        printf '> ' >&9
    done
    exec 9>&- 9<&-

    if [ -z "$result" ]; then
        printf '%s' "$default"
    else
        printf '%s' "$result"
    fi
}

prompt_override_value() {
    local label="$1"
    local current="${2:-}"
    local current_display="${current:-<default>}"
    local response=""

    response="$(prompt_read_line "$label [current: $current_display, enter=keep, -=clear]: " "")"
    if [ -z "$response" ]; then
        echo "$current"
        return 0
    fi
    if [ "$response" = "-" ]; then
        echo ""
        return 0
    fi
    echo "$response"
}

bootstrap_prompt_value() {
    local key="$1"
    [ -f "$PROJECT_BOOTSTRAP_FILE" ] || return 1
    awk -F': ' -v key="$key" '
        $1 == key {
            value=$0
            sub(/^"?"/, "", value)
            sub(/^"?[^:]+: /, "", value)
            sub(/"$/, "", value)
            print value
            exit
        }
    ' "$PROJECT_BOOTSTRAP_FILE"
}

bootstrap_required_text_value_is_set() {
    local value="${1:-}"
    local normalized=""

    normalized="$(sanitize_text_for_log "$value")"
    [ -n "$normalized" ] || return 1

    case "$(to_lower "$normalized")" in
        no\ explicit*|unspecified*|none|none\ stated|na|n/a|-)
            return 1
            ;;
    esac
    return 0
}

bootstrap_text_value_is_present() {
    local value="${1:-}"
    local normalized=""
    normalized="$(sanitize_text_for_log "$value")"
    [ -n "$normalized" ]
}

bootstrap_schema_missing_fields_from_values() {
    local project_type="${1:-}"
    local objective="${2:-}"
    local constraints="${3:-}"
    local success_criteria="${4:-}"
    local build_consent="${5:-}"
    local architecture_shape="${6:-}"
    local technology_choices="${7:-}"
    local interactive_prompted="${8:-}"
    local strict_mode="${9:-false}"

    case "$project_type" in
        new|existing) ;;
        *) echo "project_type" ;;
    esac

    if is_true "$strict_mode"; then
        bootstrap_required_text_value_is_set "$objective" || echo "objective"
        bootstrap_required_text_value_is_set "$constraints" || echo "constraints"
        bootstrap_required_text_value_is_set "$success_criteria" || echo "success_criteria"
        bootstrap_required_text_value_is_set "$architecture_shape" || echo "architecture_shape"
        bootstrap_required_text_value_is_set "$technology_choices" || echo "technology_choices"
    else
        bootstrap_text_value_is_present "$objective" || echo "objective"
        bootstrap_text_value_is_present "$constraints" || echo "constraints"
        bootstrap_text_value_is_present "$success_criteria" || echo "success_criteria"
        bootstrap_text_value_is_present "$architecture_shape" || echo "architecture_shape"
        bootstrap_text_value_is_present "$technology_choices" || echo "technology_choices"
    fi
    is_bool_like "$build_consent" || echo "build_consent"

    if [ -n "$interactive_prompted" ]; then
        is_bool_like "$interactive_prompted" || echo "interactive_prompted"
    fi
}

bootstrap_schema_missing_fields_from_file() {
    local strict_mode="${1:-false}"
    local project_type objective constraints success_criteria build_consent architecture_shape technology_choices interactive_prompted

    project_type="$(bootstrap_prompt_value "project_type" 2>/dev/null || true)"
    objective="$(bootstrap_prompt_value "objective" 2>/dev/null || true)"
    constraints="$(bootstrap_prompt_value "constraints" 2>/dev/null || true)"
    success_criteria="$(bootstrap_prompt_value "success_criteria" 2>/dev/null || true)"
    build_consent="$(bootstrap_prompt_value "build_consent" 2>/dev/null || true)"
    architecture_shape="$(bootstrap_prompt_value "architecture_shape" 2>/dev/null || true)"
    technology_choices="$(bootstrap_prompt_value "technology_choices" 2>/dev/null || true)"
    interactive_prompted="$(bootstrap_prompt_value "interactive_prompted" 2>/dev/null || true)"

    bootstrap_schema_missing_fields_from_values \
        "$project_type" \
        "$objective" \
        "$constraints" \
        "$success_criteria" \
        "$build_consent" \
        "$architecture_shape" \
        "$technology_choices" \
        "$interactive_prompted" \
        "$strict_mode"
}

bootstrap_alignment_state_fingerprint() {
    local project_type="${1:-}"
    local objective="${2:-}"
    local constraints="${3:-}"
    local success_criteria="${4:-}"
    local build_consent="${5:-}"
    local architecture_shape="${6:-}"
    local technology_choices="${7:-}"
    local goals_text="${8:-}"
    local payload checksum

    payload="$(
        cat <<EOF
project_type=$project_type
objective=$objective
constraints=$constraints
success_criteria=$success_criteria
build_consent=$build_consent
architecture_shape=$architecture_shape
technology_choices=$technology_choices
goals_text=$goals_text
EOF
    )"

    if checksum="$(printf '%s' "$payload" | sha256_stream_sum 2>/dev/null)"; then
        printf '%s' "$checksum"
        return 0
    fi

    printf '%s' "$(bootstrap_dense_token "$payload" "state" 96)"
}

bootstrap_clamp_percent() {
    local value="${1:-0}"
    if ! is_number "$value"; then
        echo 0
        return 0
    fi
    if [ "$value" -lt 0 ]; then
        echo 0
        return 0
    fi
    if [ "$value" -gt 100 ]; then
        echo 100
        return 0
    fi
    echo "$value"
}

bootstrap_context_is_valid() {
    local interactive_prompted=""
    local strict_mode="false"
    local -a missing_fields=()

    interactive_prompted="$(bootstrap_prompt_value "interactive_prompted" 2>/dev/null || true)"
    if is_true "$interactive_prompted"; then
        strict_mode="true"
    fi

    mapfile -t missing_fields < <(bootstrap_schema_missing_fields_from_file "$strict_mode")
    [ "${#missing_fields[@]}" -eq 0 ]
}

write_bootstrap_context_file() {
    local project_type="$1"
    local objective="$2"
    local build_consent="$3"
    local interactive_source="$4"
    local constraints="${5:-No explicit constraints provided.}"
    local success_criteria="${6:-All required phase gates pass and deliverables match project objectives.}"
    local goals_doc_present="${7:-false}"
    local goals_doc_url="${8:-}"
    local architecture_shape="${9:-No explicit structure preference provided.}"
    local technology_choices="${10:-No explicit technology preference provided.}"

    cat > "$PROJECT_BOOTSTRAP_FILE" <<EOF
# Ralphie Project Bootstrap
project_type: $project_type
build_consent: $build_consent
objective: $objective
constraints: $constraints
success_criteria: $success_criteria
architecture_shape: $architecture_shape
technology_choices: $technology_choices
goals_document_present: $goals_doc_present
goals_document_url: $goals_doc_url
interactive_prompted: $interactive_source
captured_at: $(date -u '+%Y-%m-%dT%H:%M:%SZ')
EOF
}

write_project_goals_file() {
    local goals_text="${1:-}"
    if [ -z "$goals_text" ]; then
        rm -f "$PROJECT_GOALS_FILE" 2>/dev/null || true
        return 0
    fi

    mkdir -p "$(dirname "$PROJECT_GOALS_FILE")"
    cat > "$PROJECT_GOALS_FILE" <<EOF
# Project Goals Document

$goals_text
EOF
}

bootstrap_dense_token() {
    local raw_value="${1:-}"
    local fallback="${2:-na}"
    local max_len="${3:-42}"
    local value=""

    if ! is_number "$max_len" || [ "$max_len" -lt 8 ]; then
        max_len=42
    fi

    value="$(sanitize_text_for_log "$raw_value")"
    [ -n "$value" ] || value="$fallback"
    value="$(printf '%s' "$value" | sed 's/[[:space:]]\+/_/g')"
    if [ "${#value}" -gt "$max_len" ]; then
        value="${value:0:$max_len}"
    fi
    printf '%s' "$value"
}

bootstrap_dense_reflection_line() {
    local project_type="${1:-existing}"
    local objective="${2:-}"
    local constraints="${3:-}"
    local success_criteria="${4:-}"
    local build_consent="${5:-true}"
    local architecture_shape="${6:-}"
    local technology_choices="${7:-}"
    local build_mode="mb"

    if is_true "$build_consent"; then
        build_mode="ab"
    fi

    printf 'g=%s|tp=%s|ok=%s|ng=%s|ar=%s|st=%s|b=%s' \
        "$(bootstrap_dense_token "$objective" "unspecified_goal" 64)" \
        "$(bootstrap_dense_token "$project_type" "existing" 12)" \
        "$(bootstrap_dense_token "$success_criteria" "unspecified_done" 56)" \
        "$(bootstrap_dense_token "$constraints" "none" 52)" \
        "$(bootstrap_dense_token "$architecture_shape" "unspecified_arch" 42)" \
        "$(bootstrap_dense_token "$technology_choices" "unspecified_tech" 42)" \
        "$build_mode"
}

bootstrap_persona_assessment_lines() {
    local project_type="${1:-existing}"
    local objective="${2:-}"
    local constraints="${3:-}"
    local success_criteria="${4:-}"
    local build_consent="${5:-true}"
    local architecture_shape="${6:-}"
    local technology_choices="${7:-}"
    local -a missing_fields=()
    local missing_count=0
    local missing_csv="none"
    local obj_token constr_token success_token
    local obj_len constr_len success_len
    local base_risk=20
    local has_missing_objective=false
    local has_missing_constraints=false
    local has_missing_success=false
    local has_missing_arch=false
    local has_missing_tech=false
    local missing_objective_weight=0
    local missing_constraints_weight=0
    local missing_success_weight=0
    local missing_arch_weight=0
    local missing_tech_weight=0
    local field
    local common_unknowns="none"

    mapfile -t missing_fields < <(
        bootstrap_schema_missing_fields_from_values \
            "$project_type" \
            "$objective" \
            "$constraints" \
            "$success_criteria" \
            "$build_consent" \
            "$architecture_shape" \
            "$technology_choices" \
            "" \
            "true"
    )
    missing_count="${#missing_fields[@]}"
    if [ "$missing_count" -gt 0 ]; then
        missing_csv=""
        for field in "${missing_fields[@]}"; do
            [ -n "$field" ] || continue
            missing_csv="${missing_csv}${missing_csv:+,}${field}"
        done
        [ -n "$missing_csv" ] || missing_csv="none"
    fi

    case ",$missing_csv," in *",objective,"*) has_missing_objective=true ;; esac
    case ",$missing_csv," in *",constraints,"*) has_missing_constraints=true ;; esac
    case ",$missing_csv," in *",success_criteria,"*) has_missing_success=true ;; esac
    case ",$missing_csv," in *",architecture_shape,"*) has_missing_arch=true ;; esac
    case ",$missing_csv," in *",technology_choices,"*) has_missing_tech=true ;; esac
    [ "$has_missing_objective" = "true" ] && missing_objective_weight=1
    [ "$has_missing_constraints" = "true" ] && missing_constraints_weight=1
    [ "$has_missing_success" = "true" ] && missing_success_weight=1
    [ "$has_missing_arch" = "true" ] && missing_arch_weight=1
    [ "$has_missing_tech" = "true" ] && missing_tech_weight=1

    obj_token="$(bootstrap_dense_token "$objective" "unspecified_goal" 42)"
    constr_token="$(bootstrap_dense_token "$constraints" "none" 34)"
    success_token="$(bootstrap_dense_token "$success_criteria" "unspecified_done" 38)"
    obj_len="${#obj_token}"
    constr_len="${#constr_token}"
    success_len="${#success_token}"

    [ "$obj_len" -lt 20 ] && base_risk=$((base_risk + 12))
    [ "$constr_len" -lt 16 ] && base_risk=$((base_risk + 10))
    [ "$success_len" -lt 16 ] && base_risk=$((base_risk + 10))
    base_risk=$((base_risk + missing_count * 12))
    if ! is_true "$build_consent"; then
        base_risk=$((base_risk + 5))
    fi

    if [ "$missing_count" -gt 0 ]; then
        common_unknowns="missing:${missing_csv}"
    elif [ "$obj_len" -lt 20 ]; then
        common_unknowns="objective_too_brief"
    fi

    bootstrap_emit_persona_assessment() {
        local persona="$1"
        local risk="$2"
        local focus="$3"
        local confidence blocking recommendation unknowns

        risk="$(bootstrap_clamp_percent "$risk")"
        confidence="$(bootstrap_clamp_percent "$((100 - risk))")"
        blocking="false"
        if [ "$risk" -ge 80 ] || [ "$missing_count" -gt 0 ]; then
            blocking="true"
        fi
        recommendation="proceed"
        [ "$blocking" = "true" ] && recommendation="revise"
        unknowns="$(bootstrap_dense_token "$common_unknowns" "none" 60)"

        printf '%s\n' "persona=${persona}|risk=${risk}|confidence=${confidence}|blocking=${blocking}|unknowns=${unknowns}|recommendation=${recommendation}|focus=${focus}"
    }

    bootstrap_emit_persona_assessment "Architect" "$((base_risk + missing_arch_weight * 18))" "structure_scope_fit"
    bootstrap_emit_persona_assessment "Skeptic" "$((base_risk + 12))" "ambiguity_risk_scan"
    bootstrap_emit_persona_assessment "Execution" "$((base_risk + missing_success_weight * 18 + missing_objective_weight * 10))" "deliverable_route"
    bootstrap_emit_persona_assessment "Safety" "$((base_risk + missing_constraints_weight * 16))" "guardrails_compliance"
    bootstrap_emit_persona_assessment "Operations" "$((base_risk + missing_arch_weight * 10 + missing_tech_weight * 12))" "rollback_runtime"
    bootstrap_emit_persona_assessment "Quality" "$((base_risk + missing_success_weight * 15 + missing_objective_weight * 12))" "acceptance_bar"
}

bootstrap_persona_field() {
    local line="${1:-}"
    local key="${2:-}"
    local default="${3:-}"
    local part
    local -a parts=()

    [ -n "$line" ] || { echo "$default"; return 0; }
    [ -n "$key" ] || { echo "$default"; return 0; }

    IFS='|' read -r -a parts <<< "$line"
    for part in "${parts[@]}"; do
        if [[ "$part" == "$key="* ]]; then
            echo "${part#*=}"
            return 0
        fi
    done
    echo "$default"
}

bootstrap_persona_display_line() {
    local assessment="${1:-}"
    local persona risk confidence blocking recommendation unknowns focus blocking_label

    persona="$(bootstrap_persona_field "$assessment" "persona" "Persona")"
    risk="$(bootstrap_persona_field "$assessment" "risk" "0")"
    confidence="$(bootstrap_persona_field "$assessment" "confidence" "0")"
    blocking="$(bootstrap_persona_field "$assessment" "blocking" "false")"
    recommendation="$(bootstrap_persona_field "$assessment" "recommendation" "proceed")"
    unknowns="$(bootstrap_persona_field "$assessment" "unknowns" "none")"
    focus="$(bootstrap_persona_field "$assessment" "focus" "none")"
    blocking_label="n"
    [ "$blocking" = "true" ] && blocking_label="y"

    printf '%s\n' "${persona}>r=${risk},c=${confidence},blk=${blocking_label},rec=${recommendation},unk=${unknowns},fx=${focus}" | cut -c 1-220
}

bootstrap_persona_blocking_names() {
    local assessment persona blocking
    for assessment in "$@"; do
        [ -n "$assessment" ] || continue
        persona="$(bootstrap_persona_field "$assessment" "persona" "")"
        blocking="$(bootstrap_persona_field "$assessment" "blocking" "false")"
        if [ "$blocking" = "true" ] && [ -n "$persona" ]; then
            echo "$persona"
        fi
    done
}

bootstrap_persona_feedback_lines() {
    local project_type="${1:-existing}"
    local objective="${2:-}"
    local constraints="${3:-}"
    local success_criteria="${4:-}"
    local build_consent="${5:-true}"
    local architecture_shape="${6:-}"
    local technology_choices="${7:-}"
    local assessment
    local -a assessments=()

    mapfile -t assessments < <(
        bootstrap_persona_assessment_lines \
            "$project_type" \
            "$objective" \
            "$constraints" \
            "$success_criteria" \
            "$build_consent" \
            "$architecture_shape" \
            "$technology_choices"
    )
    for assessment in "${assessments[@]}"; do
        [ -n "$assessment" ] || continue
        bootstrap_persona_display_line "$assessment"
    done
}

ensure_project_bootstrap() {
    local project_type objective build_consent interactive_source constraints success_criteria goals_text goals_doc_url architecture_shape technology_choices
    project_type="existing"
    objective="Improve project with a deterministic, evidence-first implementation path."
    build_consent="false"
    interactive_source="false"
    constraints="No explicit constraints provided."
    success_criteria="All required phase gates pass and deliverables match project objectives."
    goals_text=""
    goals_doc_url=""
    architecture_shape="No explicit structure preference provided."
    technology_choices="No explicit technology preference provided."

    mkdir -p "$(dirname "$PROJECT_BOOTSTRAP_FILE")"
    local existing_project_type=""
    local existing_objective=""
    local existing_build_consent=""
    local existing_interactive_prompted=""
    local existing_constraints=""
    local existing_success_criteria=""
    local existing_goals_doc_url=""
    local existing_architecture_shape=""
    local existing_technology_choices=""
    local needs_prompt="false"

    if [ -f "$PROJECT_BOOTSTRAP_FILE" ]; then
        existing_project_type="$(bootstrap_prompt_value "project_type" 2>/dev/null || true)"
        existing_objective="$(bootstrap_prompt_value "objective" 2>/dev/null || true)"
        existing_build_consent="$(bootstrap_prompt_value "build_consent" 2>/dev/null || true)"
        existing_interactive_prompted="$(bootstrap_prompt_value "interactive_prompted" 2>/dev/null || true)"
        existing_constraints="$(bootstrap_prompt_value "constraints" 2>/dev/null || true)"
        existing_success_criteria="$(bootstrap_prompt_value "success_criteria" 2>/dev/null || true)"
        existing_goals_doc_url="$(bootstrap_prompt_value "goals_document_url" 2>/dev/null || true)"
        existing_architecture_shape="$(bootstrap_prompt_value "architecture_shape" 2>/dev/null || true)"
        existing_technology_choices="$(bootstrap_prompt_value "technology_choices" 2>/dev/null || true)"

        if [ -n "$existing_project_type" ]; then
            project_type="$existing_project_type"
        fi
        if [ -n "$existing_objective" ]; then
            objective="$existing_objective"
        fi
        if [ -n "$existing_build_consent" ]; then
            build_consent="$existing_build_consent"
        fi
        if [ -n "$existing_constraints" ]; then
            constraints="$existing_constraints"
        fi
        if [ -n "$existing_success_criteria" ]; then
            success_criteria="$existing_success_criteria"
        fi
        if [ -n "$existing_goals_doc_url" ]; then
            goals_doc_url="$existing_goals_doc_url"
        fi
        if [ -n "$existing_architecture_shape" ]; then
            architecture_shape="$existing_architecture_shape"
        fi
        if [ -n "$existing_technology_choices" ]; then
            technology_choices="$existing_technology_choices"
        fi
        if [ "$existing_interactive_prompted" = "true" ]; then
            interactive_source="true"
        fi
    fi
    if [ -f "$PROJECT_GOALS_FILE" ]; then
        goals_text="$(cat "$PROJECT_GOALS_FILE" 2>/dev/null || true)"
    fi

    if [ "$REBOOTSTRAP_REQUESTED" = true ] || [ ! -f "$PROJECT_BOOTSTRAP_FILE" ] || ! bootstrap_context_is_valid; then
        needs_prompt="true"
    fi
    if is_tty_input_available && [ "$existing_interactive_prompted" = "false" ] && [ -f "$PROJECT_BOOTSTRAP_FILE" ]; then
        needs_prompt="true"
    fi

    if [ "$needs_prompt" = "true" ]; then
        if [ -f "$PROJECT_BOOTSTRAP_FILE" ] && ! bootstrap_context_is_valid; then
            warn "Existing project bootstrap file is invalid or incomplete. Rebuilding context."
        elif [ "$REBOOTSTRAP_REQUESTED" = true ]; then
            warn "Rebuilding project bootstrap context due to --rebootstrap request."
        elif is_tty_input_available && [ "$existing_interactive_prompted" = "false" ]; then
            info "Previous bootstrap was collected non-interactively; refreshing bootstrap context now."
        fi
    fi

    if is_true "$needs_prompt" && is_tty_input_available; then
        interactive_source="true"
        if [ "$REBOOTSTRAP_REQUESTED" = true ] || ! bootstrap_context_is_valid || [ "$existing_interactive_prompted" = "false" ] || [ ! -f "$PROJECT_BOOTSTRAP_FILE" ]; then
            if [ "$(prompt_yes_no "Is this a new project (no established implementation yet)?" "n")" = "true" ]; then
                project_type="new"
            fi
            objective="$(prompt_optional_line "What is the primary objective for this session (single line)" "$objective")"
            constraints="$(prompt_optional_line "Key constraints or non-goals (single line, optional)" "$constraints")"
            success_criteria="$(prompt_optional_line "Success criteria / definition of done (single line, optional)" "$success_criteria")"
            goals_doc_url="$(prompt_optional_line "Project goals document URL (optional)" "$goals_doc_url")"

            if [ "$(prompt_yes_no "Paste a project goals document/URL block now?" "n")" = "true" ]; then
                goals_text="$(prompt_multiline_block "Project goals/context input" "$goals_text" "EOF")"
            fi

            architecture_shape="$(prompt_optional_line "Preferred project structure / architecture (single line, optional)" "$architecture_shape")"
            technology_choices="$(prompt_optional_line "Preferred technology choices (single line, optional)" "$technology_choices")"

            if [ "$(prompt_yes_no "Proceed automatically from PLAN -> BUILD when all gates pass" "y")" = "true" ]; then
                build_consent="true"
            else
                build_consent="false"
            fi

            local alignment_round=0
            local alignment_max_rounds=12
            local no_change_rounds=0

            while true; do
                local alignment_action modify_target extra_context
                local schema_field needs_arch_clarifier needs_tech_clarifier
                local round_state_before round_state_after
                local persona_assessment persona_display
                local -a schema_missing_fields=()
                local -a persona_assessments=()
                local -a blocking_personas=()
                alignment_round=$((alignment_round + 1))
                round_state_before="$(bootstrap_alignment_state_fingerprint "$project_type" "$objective" "$constraints" "$success_criteria" "$build_consent" "$architecture_shape" "$technology_choices" "$goals_text")"

                mapfile -t schema_missing_fields < <(
                    bootstrap_schema_missing_fields_from_values \
                        "$project_type" \
                        "$objective" \
                        "$constraints" \
                        "$success_criteria" \
                        "$build_consent" \
                        "$architecture_shape" \
                        "$technology_choices" \
                        "" \
                        "true"
                )
                mapfile -t persona_assessments < <(
                    bootstrap_persona_assessment_lines \
                        "$project_type" \
                        "$objective" \
                        "$constraints" \
                        "$success_criteria" \
                        "$build_consent" \
                        "$architecture_shape" \
                        "$technology_choices"
                )
                mapfile -t blocking_personas < <(bootstrap_persona_blocking_names "${persona_assessments[@]+"${persona_assessments[@]}"}")

                info "Bootstrap alignment reflection (ultra concise):"
                info "  $(bootstrap_dense_reflection_line "$project_type" "$objective" "$constraints" "$success_criteria" "$build_consent" "$architecture_shape" "$technology_choices")"
                info "Persona inputs (dense):"
                for persona_assessment in "${persona_assessments[@]}"; do
                    [ -n "$persona_assessment" ] || continue
                    persona_display="$(bootstrap_persona_display_line "$persona_assessment")"
                    [ -n "$persona_display" ] && info "  - $persona_display"
                done
                if [ "${#schema_missing_fields[@]}" -gt 0 ]; then
                    info "Schema gaps: $(join_with_commas "${schema_missing_fields[@]+"${schema_missing_fields[@]}"}")"
                fi
                if [ "${#blocking_personas[@]}" -gt 0 ]; then
                    info "Persona blockers: $(join_with_commas "${blocking_personas[@]+"${blocking_personas[@]}"}")"
                fi

                alignment_action="$(to_lower "$(prompt_read_line "Alignment action [a=accept,m=modify,r=rerun,d=dismiss] (round ${alignment_round}/${alignment_max_rounds}): " "a")")"
                case "$alignment_action" in
                    a|accept|ok|yes|y|"")
                        if [ "${#schema_missing_fields[@]}" -gt 0 ] || [ "${#blocking_personas[@]}" -gt 0 ]; then
                            warn "Accept blocked: missing fields=$(join_with_commas "${schema_missing_fields[@]+"${schema_missing_fields[@]}"}"), blockers=$(join_with_commas "${blocking_personas[@]+"${blocking_personas[@]}"}")."
                            info "Focused clarifiers required before accept:"
                            objective="$(prompt_optional_line "Clarify primary user/workflow (single line)" "$objective")"
                            constraints="$(prompt_optional_line "Clarify highest risk/non-goal (single line)" "$constraints")"
                            success_criteria="$(prompt_optional_line "Clarify measurable done signal (single line)" "$success_criteria")"
                            needs_arch_clarifier="false"
                            needs_tech_clarifier="false"
                            for schema_field in "${schema_missing_fields[@]}"; do
                                case "$schema_field" in
                                    architecture_shape) needs_arch_clarifier="true" ;;
                                    technology_choices) needs_tech_clarifier="true" ;;
                                    *) ;;
                                esac
                            done
                            if [ "$needs_arch_clarifier" = "true" ]; then
                                architecture_shape="$(prompt_optional_line "Clarify target structure/architecture (single line)" "$architecture_shape")"
                            fi
                            if [ "$needs_tech_clarifier" = "true" ]; then
                                technology_choices="$(prompt_optional_line "Clarify target technology choices (single line)" "$technology_choices")"
                            fi
                        fi
                        [ "${#schema_missing_fields[@]}" -eq 0 ] && [ "${#blocking_personas[@]}" -eq 0 ] && break
                        ;;
                    d|dismiss|skip|good_enough)
                        info "Alignment loop dismissed as good enough."
                        break
                        ;;
                    r|rerun|again|loop)
                        extra_context="$(prompt_optional_line "Add or correct context before rerun (optional)" "")"
                        if [ -n "$extra_context" ]; then
                            goals_text="${goals_text}${goals_text:+$'\n'}$extra_context"
                        fi
                        ;;
                    m|modify|edit)
                        modify_target="$(to_lower "$(prompt_read_line "Modify field [goal|constraints|success|arch|tech|goals|type|build|all]: " "goal")")"
                        case "$modify_target" in
                            goal|objective)
                                objective="$(prompt_optional_line "Primary objective (single line)" "$objective")"
                                ;;
                            constraints|constraint|non-goals|nongoals)
                                constraints="$(prompt_optional_line "Constraints or non-goals (single line)" "$constraints")"
                                ;;
                            success|done|criteria|success_criteria)
                                success_criteria="$(prompt_optional_line "Success criteria / done (single line)" "$success_criteria")"
                                ;;
                            arch|architecture|structure)
                                architecture_shape="$(prompt_optional_line "Project structure / architecture (single line)" "$architecture_shape")"
                                ;;
                            tech|stack|technology|technology_choices)
                                technology_choices="$(prompt_optional_line "Technology choices (single line)" "$technology_choices")"
                                ;;
                            goals|goals_doc|goals_document)
                                goals_text="$(prompt_multiline_block "Project goals/context input" "$goals_text" "EOF")"
                                ;;
                            type|project_type)
                                if [ "$(prompt_yes_no "Is this a new project (no established implementation yet)?" "$( [ "$project_type" = "new" ] && echo y || echo n )")" = "true" ]; then
                                    project_type="new"
                                else
                                    project_type="existing"
                                fi
                                ;;
                            build|build_consent|autobuild)
                                if [ "$(prompt_yes_no "Proceed automatically from PLAN -> BUILD when all gates pass" "$(is_true "$build_consent" && echo y || echo n)")" = "true" ]; then
                                    build_consent="true"
                                else
                                    build_consent="false"
                                fi
                                ;;
                            all)
                                if [ "$(prompt_yes_no "Is this a new project (no established implementation yet)?" "$( [ "$project_type" = "new" ] && echo y || echo n )")" = "true" ]; then
                                    project_type="new"
                                else
                                    project_type="existing"
                                fi
                                objective="$(prompt_optional_line "Primary objective (single line)" "$objective")"
                                constraints="$(prompt_optional_line "Constraints or non-goals (single line)" "$constraints")"
                                success_criteria="$(prompt_optional_line "Success criteria / done (single line)" "$success_criteria")"
                                architecture_shape="$(prompt_optional_line "Project structure / architecture (single line)" "$architecture_shape")"
                                technology_choices="$(prompt_optional_line "Technology choices (single line)" "$technology_choices")"
                                goals_doc_url="$(prompt_optional_line "Project goals document URL (optional)" "$goals_doc_url")"
                                goals_text="$(prompt_multiline_block "Project goals/context input" "$goals_text" "EOF")"
                                if [ "$(prompt_yes_no "Proceed automatically from PLAN -> BUILD when all gates pass" "$(is_true "$build_consent" && echo y || echo n)")" = "true" ]; then
                                    build_consent="true"
                                else
                                    build_consent="false"
                                fi
                                ;;
                            *)
                                warn "Unknown field '$modify_target'."
                                ;;
                        esac
                        ;;
                    *)
                        warn "Unknown alignment action '$alignment_action'."
                        ;;
                esac

                round_state_after="$(bootstrap_alignment_state_fingerprint "$project_type" "$objective" "$constraints" "$success_criteria" "$build_consent" "$architecture_shape" "$technology_choices" "$goals_text")"
                if [ "$round_state_after" = "$round_state_before" ]; then
                    no_change_rounds=$((no_change_rounds + 1))
                else
                    no_change_rounds=0
                fi

                if [ "$alignment_round" -ge "$alignment_max_rounds" ] || [ "$no_change_rounds" -ge 2 ]; then
                    local guard_reason
                    guard_reason="max_rounds"
                    if [ "$no_change_rounds" -ge 2 ]; then
                        guard_reason="no_change"
                    fi
                    if [ "$alignment_round" -ge "$alignment_max_rounds" ] && [ "$no_change_rounds" -ge 2 ]; then
                        guard_reason="max_rounds+no_change"
                    fi
                    warn "Alignment loop guard triggered ($guard_reason). Asking focused clarifiers."
                    objective="$(prompt_optional_line "Clarify primary user/workflow (single line)" "$objective")"
                    constraints="$(prompt_optional_line "Clarify highest risk/non-goal (single line)" "$constraints")"
                    success_criteria="$(prompt_optional_line "Clarify measurable done signal (single line)" "$success_criteria")"
                    if ! bootstrap_required_text_value_is_set "$architecture_shape"; then
                        architecture_shape="$(prompt_optional_line "Clarify target structure/architecture (single line)" "$architecture_shape")"
                    fi
                    if ! bootstrap_required_text_value_is_set "$technology_choices"; then
                        technology_choices="$(prompt_optional_line "Clarify target technology choices (single line)" "$technology_choices")"
                    fi
                    alignment_round=0
                    no_change_rounds=0
                fi
            done
            info "Project bootstrap captured from interactive input."
        fi
    fi

    if ! is_true "$needs_prompt" && [ -f "$PROJECT_BOOTSTRAP_FILE" ] && is_tty_input_available; then
        info "Loaded existing project bootstrap context: $(path_for_display "$PROJECT_BOOTSTRAP_FILE")"
        info "   - project_type: $project_type"
        info "   - objective: $objective"
        info "   - build_consent: $build_consent"
        info "   - architecture_shape: $architecture_shape"
        info "   - technology_choices: $technology_choices"
        return 0
    fi

    if is_true "$needs_prompt" && ! is_tty_input_available; then
        info "Non-interactive bootstrap fallback retained: objective defaults were applied and build consent remains false."
    fi

    write_project_goals_file "$goals_text"
    write_bootstrap_context_file "$project_type" "$objective" "$build_consent" "$interactive_source" "$constraints" "$success_criteria" "$([ -s "$PROJECT_GOALS_FILE" ] && echo true || echo false)" "$goals_doc_url" "$architecture_shape" "$technology_choices"
    info "Captured project bootstrap context: $(path_for_display "$PROJECT_BOOTSTRAP_FILE")"
    if [ -s "$PROJECT_GOALS_FILE" ]; then
        info "Captured project goals document: $(path_for_display "$PROJECT_GOALS_FILE")"
    fi
    REBOOTSTRAP_REQUESTED=false
}

append_bootstrap_context_to_plan_prompt() {
    local source_prompt="$1"
    local target_prompt="$2"
    local project_type objective build_consent constraints success_criteria goals_doc_url architecture_shape technology_choices

    if [ ! -f "$source_prompt" ]; then
        warn "Plan prompt source missing: $(path_for_display "$source_prompt")"
        return 1
    fi

    if [ ! -f "$PROJECT_BOOTSTRAP_FILE" ]; then
        cp "$source_prompt" "$target_prompt" 2>/dev/null || return 1
        return 0
    fi

    project_type="$(bootstrap_prompt_value "project_type")"
    objective="$(bootstrap_prompt_value "objective")"
    build_consent="$(bootstrap_prompt_value "build_consent")"
    constraints="$(bootstrap_prompt_value "constraints")"
    success_criteria="$(bootstrap_prompt_value "success_criteria")"
    goals_doc_url="$(bootstrap_prompt_value "goals_document_url")"
    architecture_shape="$(bootstrap_prompt_value "architecture_shape")"
    technology_choices="$(bootstrap_prompt_value "technology_choices")"

    cat > "$target_prompt" <<EOF
$(cat "$source_prompt")

## Project Bootstrap Context
- Project type: ${project_type:-existing}
- Objective: ${objective:-unspecified}
- Constraints / non-goals: ${constraints:-none stated}
- Success criteria: ${success_criteria:-none stated}
- Preferred architecture / structure: ${architecture_shape:-none stated}
- Preferred technology choices: ${technology_choices:-none stated}
- Goals document URL: ${goals_doc_url:-not provided}
- Build consent after plan: ${build_consent:-true}

EOF

    if [ -s "$PROJECT_GOALS_FILE" ]; then
        {
            echo "## Project Goals Document (User-Provided)"
            echo ""
            cat "$PROJECT_GOALS_FILE"
            echo ""
        } >> "$target_prompt"
    fi
}

build_is_preapproved() {
    local consent
    consent="$(bootstrap_prompt_value "build_consent" 2>/dev/null)"
    [ "$consent" = "true" ]
}

healthy_engines_for_display() {
    local engines=""
    if [ "$CODEX_HEALTHY" = "true" ]; then
        engines="codex"
    fi
    if [ "$CLAUDE_HEALTHY" = "true" ]; then
        engines="${engines}${engines:+, }claude"
    fi
    if [ -z "$engines" ]; then
        engines="none"
    fi
    printf '%s' "$engines"
}

notification_channels_for_display() {
    local channels=""
    if is_true "$NOTIFY_TELEGRAM_ENABLED"; then
        channels="telegram"
    fi
    if is_true "$NOTIFY_DISCORD_ENABLED"; then
        channels="${channels}${channels:+, }discord"
    fi
    if is_true "$NOTIFY_TTS_ENABLED"; then
        if is_true "$NOTIFY_TELEGRAM_ENABLED"; then
            channels="${channels/telegram/telegram+tts}"
        fi
        if is_true "$NOTIFY_DISCORD_ENABLED"; then
            channels="${channels/discord/discord+tts}"
        fi
    fi
    if [ -z "$channels" ]; then
        channels="none"
    fi
    printf '%s' "$channels"
}

notification_now_epoch() {
    local now
    now="$(date +%s 2>/dev/null || echo 0)"
    if ! is_number "$now"; then
        now=0
    fi
    printf '%s' "$now"
}

notification_event_is_high_signal() {
    case "${1:-}" in
        notification_setup|session_start|phase_decision|phase_complete|phase_blocked|session_done|session_error) return 0 ;;
        *) return 1 ;;
    esac
}

phase_attempt_limit_display() {
    local limit="${1:-0}"
    if ! is_number "$limit" || [ "$limit" -lt 0 ]; then
        echo "inf"
        return 0
    fi
    if [ "$limit" -eq 0 ]; then
        echo "inf"
        return 0
    fi
    echo "$limit"
}

phase_attempt_within_budget() {
    local attempt="$1"
    local limit="$2"
    if ! is_number "$attempt" || [ "$attempt" -lt 1 ]; then
        return 1
    fi
    if ! is_number "$limit" || [ "$limit" -lt 0 ] || [ "$limit" -eq 0 ]; then
        return 0
    fi
    [ "$attempt" -le "$limit" ]
}

phase_failure_signature() {
    local payload=""
    if [ "$#" -gt 0 ]; then
        payload="$(printf '%s\n' "$@")"
    fi
    if [ -z "$payload" ]; then
        echo "none"
        return 0
    fi
    if command -v sha256sum >/dev/null 2>&1; then
        printf '%s' "$payload" | sha256sum | awk '{print $1}'
        return 0
    fi
    if command -v shasum >/dev/null 2>&1; then
        printf '%s' "$payload" | shasum -a 256 | awk '{print $1}'
        return 0
    fi
    printf '%s' "$payload" | wc -c | tr -d ' '
}

render_status_dashboard() {
    local phase="$1"
    local attempt="$2"
    local attempt_max="$3"
    local iter="$4"
    local max_iter_display
    local wallclock_display
    local cmd_timeout_display
    local consensus_to="$SWARM_CONSENSUS_TIMEOUT"

    max_iter_display="$MAX_ITERATIONS"
    [ "$MAX_ITERATIONS" -eq 0 ] && max_iter_display="inf"

    wallclock_display="${PHASE_WALLCLOCK_LIMIT_SECONDS:-0}"
    [ "$wallclock_display" -eq 0 ] && wallclock_display="inf"

    cmd_timeout_display="${COMMAND_TIMEOUT_SECONDS:-0}"
    [ "$cmd_timeout_display" -eq 0 ] && cmd_timeout_display="inf"

    printf '\n'
    printf '=== Ralphie Run Status ===\n'
    printf 'Phase: %s | Attempt: %s/%s | Iteration: %s/%s | Session: %s\n' \
        "$phase" "$attempt" "$(phase_attempt_limit_display "$attempt_max")" "$iter" "$max_iter_display" "$SESSION_ID"
    printf 'Engine (active/requested): %s (%s) | Consensus timeout: %ss | Phase wallclock: %ss | Cmd timeout: %ss\n' \
        "$ACTIVE_CMD" "$ACTIVE_ENGINE" "$consensus_to" "$wallclock_display" "$cmd_timeout_display"
    printf 'Idle output watchdog: %ss\n' "$(phase_attempt_limit_display "${ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS:-0}")"
    printf '%s\n' '---------------------------'
}

notification_reset_incident_series() {
    NOTIFY_INCIDENT_SERIES_ACTIVE="false"
    NOTIFY_INCIDENT_SERIES_KEY=""
    NOTIFY_INCIDENT_SERIES_STARTED_AT=0
    NOTIFY_INCIDENT_LAST_SENT_AT=0
    NOTIFY_INCIDENT_REPEAT_COUNT=0
}

notification_log_append() {
    local event="$1"
    local status="$2"
    local delivery="$3"
    local details="${4:-}"
    mkdir -p "$(dirname "$NOTIFICATION_LOG_FILE")"
    printf '%s\tevent=%s\tstatus=%s\tdelivery=%s\tdetails=%s\n' \
        "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
        "$event" \
        "$status" \
        "$delivery" \
        "$(printf '%s' "$details" | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g' | sed 's/^ *//; s/ *$//')" \
        >> "$NOTIFICATION_LOG_FILE"
}

send_telegram_message_raw() {
    local bot_token="$1"
    local chat_id="$2"
    local message="$3"
    local response=""

    [ -n "$bot_token" ] || return 1
    [ -n "$chat_id" ] || return 1
    command -v curl >/dev/null 2>&1 || return 1

    response="$(curl -sS -m 20 -X POST "https://api.telegram.org/bot${bot_token}/sendMessage" \
        --data-urlencode "chat_id=${chat_id}" \
        --data-urlencode "text=${message}" 2>/dev/null || true)"
    printf '%s' "$response" | grep -q '"ok":[[:space:]]*true'
}

telegram_get_updates_raw() {
    local bot_token="$1"
    [ -n "$bot_token" ] || return 1
    command -v curl >/dev/null 2>&1 || return 1
    curl -sS -m 20 "https://api.telegram.org/bot${bot_token}/getUpdates" 2>/dev/null || return 1
}

telegram_extract_chat_ids_raw() {
    local payload="${1:-}"
    [ -n "$payload" ] || return 0

    printf '%s' "$payload" | tr -d '\n' | \
        grep -oE '"chat":[[:space:]]*\{[^}]*"id":[[:space:]]*-?[0-9]+' | \
        grep -oE -- '-?[0-9]+$' | awk '!seen[$0]++'
}

telegram_suggest_chat_id_raw() {
    local bot_token="$1"
    local updates chat_ids first_id count

    updates="$(telegram_get_updates_raw "$bot_token" 2>/dev/null || true)"
    if [ -z "$updates" ]; then
        warn "Could not query Telegram getUpdates right now."
        printf '%s' ""
        return 0
    fi
    if ! printf '%s' "$updates" | grep -q '"ok":[[:space:]]*true'; then
        warn "Telegram getUpdates did not return ok=true. Verify bot token."
        printf '%s' ""
        return 0
    fi
    if printf '%s' "$updates" | grep -q '"result":[[:space:]]*\[\]'; then
        warn "Telegram getUpdates is empty. Send a message to your bot/chat first, then retry."
        printf '%s' ""
        return 0
    fi

    chat_ids="$(telegram_extract_chat_ids_raw "$updates" || true)"
    count="$(printf '%s\n' "$chat_ids" | sed '/^$/d' | wc -l | tr -d ' ')"
    if ! is_number "$count" || [ "$count" -lt 1 ]; then
        warn "Could not parse chat IDs from getUpdates response."
        printf '%s' ""
        return 0
    fi

    info "Discovered Telegram chat IDs from getUpdates:"
    printf '%s\n' "$chat_ids" | sed '/^$/d' | sed 's/^/  - /'
    first_id="$(printf '%s\n' "$chat_ids" | sed '/^$/d' | head -n 1)"
    printf '%s' "$first_id"
}

send_discord_message_raw() {
    local webhook_url="$1"
    local message="$2"
    local payload=""
    local http_code=""

    [ -n "$webhook_url" ] || return 1
    command -v curl >/dev/null 2>&1 || return 1

    payload="$(json_escape_string "$message")"
    http_code="$(curl -sS -m 20 -o /dev/null -w '%{http_code}' -X POST \
        -H "Content-Type: application/json" \
        -d "{\"content\":\"${payload}\"}" \
        "$webhook_url" 2>/dev/null || true)"
    case "$http_code" in
        200|201|202|204) return 0 ;;
        *) return 1 ;;
    esac
}

generate_chutes_tts_audio_file_raw() {
    local chutes_api_key="$1"
    local tts_url="$2"
    local voice="$3"
    local speed="$4"
    local text="$5"
    local output_file="$6"
    local escaped_text escaped_voice

    [ -n "$chutes_api_key" ] || return 1
    [ -n "$tts_url" ] || return 1
    [ -n "$voice" ] || return 1
    [ -n "$text" ] || return 1
    [ -n "$output_file" ] || return 1
    command -v curl >/dev/null 2>&1 || return 1
    is_decimal_number "$speed" || speed="$DEFAULT_NOTIFY_CHUTES_SPEED"

    escaped_text="$(json_escape_string "$text")"
    escaped_voice="$(json_escape_string "$voice")"

    if ! curl -sS -m 45 -X POST "$tts_url" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $chutes_api_key" \
        -d "{\"text\":\"${escaped_text}\",\"voice\":\"${escaped_voice}\",\"speed\":${speed}}" \
        --output "$output_file" >/dev/null 2>&1; then
        return 1
    fi
    [ -s "$output_file" ] || return 1
    return 0
}

send_telegram_voice_file_raw() {
    local bot_token="$1"
    local chat_id="$2"
    local file_path="$3"
    local caption="$4"
    local method="$5"
    local field_name="$6"
    local response http_code body

    [ -n "$bot_token" ] || return 1
    [ -n "$chat_id" ] || return 1
    [ -n "$file_path" ] || return 1
    [ -n "$method" ] || return 1
    [ -n "$field_name" ] || return 1
    command -v curl >/dev/null 2>&1 || return 1

    response="$(curl -sS -m 30 -w $'\n%{http_code}' -X POST "https://api.telegram.org/bot${bot_token}/${method}" \
        -F "chat_id=${chat_id}" \
        -F "${field_name}=@${file_path}" \
        -F "caption=${caption}" 2>/dev/null || true)"
    http_code="${response##*$'\n'}"
    body="${response%$'\n'*}"
    [ "$http_code" = "200" ] && printf '%s' "$body" | grep -q '"ok":[[:space:]]*true'
}

send_telegram_tts_raw() {
    local chutes_api_key="$1"
    local tts_url="$2"
    local voice="$3"
    local speed="$4"
    local bot_token="$5"
    local chat_id="$6"
    local text="$7"
    local caption="${8:-Ralphie TTS}"
    local tmp_audio_file=""

    [ -n "$chutes_api_key" ] || return 1
    [ -n "$tts_url" ] || return 1
    [ -n "$voice" ] || return 1
    [ -n "$bot_token" ] || return 1
    [ -n "$chat_id" ] || return 1
    [ -n "$text" ] || return 1
    command -v curl >/dev/null 2>&1 || return 1
    is_decimal_number "$speed" || speed="$DEFAULT_NOTIFY_CHUTES_SPEED"

    tmp_audio_file="$(mktemp "${TMPDIR:-/tmp}/ralphie_tts.XXXXXX")" || return 1
    if ! generate_chutes_tts_audio_file_raw "$chutes_api_key" "$tts_url" "$voice" "$speed" "$text" "$tmp_audio_file"; then
        rm -f "$tmp_audio_file"
        return 1
    fi

    if ! send_telegram_voice_file_raw "$bot_token" "$chat_id" "$tmp_audio_file" "$caption" "sendVoice" "voice" \
        && ! send_telegram_voice_file_raw "$bot_token" "$chat_id" "$tmp_audio_file" "$caption" "sendAudio" "audio" \
        && ! send_telegram_voice_file_raw "$bot_token" "$chat_id" "$tmp_audio_file" "$caption" "sendDocument" "document"; then
            rm -f "$tmp_audio_file"
            return 1
        fi

    rm -f "$tmp_audio_file"
    return 0
}

send_discord_tts_raw() {
    local chutes_api_key="$1"
    local tts_url="$2"
    local voice="$3"
    local speed="$4"
    local webhook_url="$5"
    local text="$6"
    local caption="${7:-Ralphie TTS}"
    local tmp_audio_file=""
    local payload=""
    local http_code=""

    [ -n "$chutes_api_key" ] || return 1
    [ -n "$tts_url" ] || return 1
    [ -n "$voice" ] || return 1
    [ -n "$webhook_url" ] || return 1
    [ -n "$text" ] || return 1
    command -v curl >/dev/null 2>&1 || return 1
    is_decimal_number "$speed" || speed="$DEFAULT_NOTIFY_CHUTES_SPEED"

    tmp_audio_file="$(mktemp "${TMPDIR:-/tmp}/ralphie_discord_tts.XXXXXX")" || return 1
    if ! generate_chutes_tts_audio_file_raw "$chutes_api_key" "$tts_url" "$voice" "$speed" "$text" "$tmp_audio_file"; then
        rm -f "$tmp_audio_file"
        return 1
    fi

    payload="$(json_escape_string "$caption")"
    http_code="$(curl -sS -m 30 -o /dev/null -w '%{http_code}' -X POST \
        -F "payload_json={\"content\":\"${payload}\"}" \
        -F "file=@${tmp_audio_file};filename=ralphie-tts.mp3;type=audio/mpeg" \
        "$webhook_url" 2>/dev/null || true)"

    rm -f "$tmp_audio_file"
    case "$http_code" in
        200|201|202|204) return 0 ;;
        *) return 1 ;;
    esac
}

normalize_notify_tts_style() {
    local style
    style="$(to_lower "${1:-$DEFAULT_NOTIFY_TTS_STYLE}")"
    case "$style" in
        standard|friendly|ralph_wiggum) echo "$style" ;;
        ralph) echo "ralph_wiggum" ;;
        *) echo "$DEFAULT_NOTIFY_TTS_STYLE" ;;
    esac
}

notification_tts_event_summary() {
    local event="${1:-}"
    local status="${2:-}"
    case "$event" in
        notification_setup) echo "notifications are all set" ;;
        session_start) echo "the mission started" ;;
        phase_decision) echo "I made a phase decision" ;;
        phase_complete) echo "a phase is complete" ;;
        phase_blocked) echo "a phase got blocked" ;;
        session_done) echo "the mission is complete" ;;
        session_error)
            if [ "$status" = "hold" ]; then
                echo "I hit a blocker"
            else
                echo "I hit a problem"
            fi
            ;;
        *) echo "here is an update" ;;
    esac
}

build_tts_notification_line() {
    local event="${1:-}"
    local status="${2:-}"
    local details="${3:-none}"
    local style summary normalized_details line

    style="$(normalize_notify_tts_style "${NOTIFY_TTS_STYLE:-$DEFAULT_NOTIFY_TTS_STYLE}")"
    summary="$(notification_tts_event_summary "$event" "$status")"
    normalized_details="$(printf '%s' "$details" | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g' | sed 's/^ *//; s/ *$//')"
    normalized_details="$(printf '%s' "$normalized_details" | cut -c 1-140)"
    [ -n "$normalized_details" ] || normalized_details="no extra details"

    case "$style" in
        standard)
            line="Ralphie update. ${summary}. ${normalized_details}."
            ;;
        friendly)
            line="Hey friend, Ralphie here. ${summary}. ${normalized_details}."
            ;;
        ralph_wiggum)
            line="Hi, I am Ralphie. ${summary}. ${normalized_details}. Woo hoo!"
            ;;
        *)
            line="Ralphie update. ${summary}. ${normalized_details}."
            ;;
    esac

    printf '%s' "$line" | cut -c 1-220
}

notify_event() {
    local event="$1"
    local status="$2"
    local details="${3:-}"
    local project_name branch_name timestamp_utc phase_value attempt_value iteration_value
    local message=""
    local delivered=false
    local now_epoch dedup_window reminder_minutes reminder_seconds
    local event_signature=""
    local incident_key=""
    local effective_details=""
    local delivery_details=""
    local elapsed_since_last=0
    local elapsed_series_minutes=0
    local tts_attempted=false
    local tts_failed=false

    if ! is_true "$NOTIFICATIONS_ENABLED"; then
        return 0
    fi
    command -v curl >/dev/null 2>&1 || return 0

    details="$(printf '%s' "$details" | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g' | sed 's/^ *//; s/ *$//')"
    [ -n "$details" ] || details="none"

    if ! notification_event_is_high_signal "$event"; then
        notification_log_append "$event" "$status" "suppressed" "low-signal event suppressed: $details"
        return 0
    fi

    now_epoch="$(notification_now_epoch)"
    dedup_window="$NOTIFY_EVENT_DEDUP_WINDOW_SECONDS"
    reminder_minutes="$NOTIFY_INCIDENT_REMINDER_MINUTES"
    is_number "$dedup_window" || dedup_window="$DEFAULT_NOTIFY_EVENT_DEDUP_WINDOW_SECONDS"
    is_number "$reminder_minutes" || reminder_minutes="$DEFAULT_NOTIFY_INCIDENT_REMINDER_MINUTES"
    if [ "$dedup_window" -lt 0 ]; then
        dedup_window="$DEFAULT_NOTIFY_EVENT_DEDUP_WINDOW_SECONDS"
    fi
    if [ "$reminder_minutes" -lt 0 ]; then
        reminder_minutes="$DEFAULT_NOTIFY_INCIDENT_REMINDER_MINUTES"
    fi
    reminder_seconds=$((reminder_minutes * 60))
    effective_details="$details"

    if [ "$event" = "session_error" ]; then
        incident_key="${event}|${status}"
        if [ "$NOTIFY_INCIDENT_SERIES_ACTIVE" != "true" ] || [ "$NOTIFY_INCIDENT_SERIES_KEY" != "$incident_key" ]; then
            NOTIFY_INCIDENT_SERIES_ACTIVE="true"
            NOTIFY_INCIDENT_SERIES_KEY="$incident_key"
            NOTIFY_INCIDENT_SERIES_STARTED_AT="$now_epoch"
            NOTIFY_INCIDENT_LAST_SENT_AT="$now_epoch"
            NOTIFY_INCIDENT_REPEAT_COUNT=1
        else
            NOTIFY_INCIDENT_REPEAT_COUNT=$((NOTIFY_INCIDENT_REPEAT_COUNT + 1))
            if [ "$reminder_seconds" -eq 0 ]; then
                notification_log_append "$event" "$status" "suppressed" "incident series active (reminders disabled, repeat=$NOTIFY_INCIDENT_REPEAT_COUNT): $details"
                return 0
            fi
            if [ "$now_epoch" -gt 0 ] && [ "$NOTIFY_INCIDENT_LAST_SENT_AT" -gt 0 ]; then
                elapsed_since_last=$((now_epoch - NOTIFY_INCIDENT_LAST_SENT_AT))
            else
                elapsed_since_last=0
            fi
            if [ "$elapsed_since_last" -lt "$reminder_seconds" ]; then
                notification_log_append "$event" "$status" "suppressed" "incident series active (repeat=$NOTIFY_INCIDENT_REPEAT_COUNT): $details"
                return 0
            fi
            if [ "$now_epoch" -gt 0 ] && [ "$NOTIFY_INCIDENT_SERIES_STARTED_AT" -gt 0 ]; then
                elapsed_series_minutes=$(( (now_epoch - NOTIFY_INCIDENT_SERIES_STARTED_AT) / 60 ))
            else
                elapsed_series_minutes=0
            fi
            effective_details="${details}; ongoing=${elapsed_series_minutes}m repeats=${NOTIFY_INCIDENT_REPEAT_COUNT}"
            NOTIFY_INCIDENT_LAST_SENT_AT="$now_epoch"
        fi
    else
        if [ "$NOTIFY_INCIDENT_SERIES_ACTIVE" = "true" ]; then
            notification_reset_incident_series
        fi
        event_signature="${event}|${status}|$(printf '%s' "$details" | cut -c 1-220)"
        if [ "$dedup_window" -gt 0 ] && [ -n "$NOTIFY_LAST_EVENT_SIGNATURE" ] && [ "$event_signature" = "$NOTIFY_LAST_EVENT_SIGNATURE" ] && [ "$now_epoch" -gt 0 ] && [ "$NOTIFY_LAST_EVENT_SENT_AT" -gt 0 ]; then
            elapsed_since_last=$((now_epoch - NOTIFY_LAST_EVENT_SENT_AT))
            if [ "$elapsed_since_last" -lt "$dedup_window" ]; then
                notification_log_append "$event" "$status" "suppressed" "duplicate event within ${dedup_window}s window: $details"
                return 0
            fi
        fi
    fi

    project_name="$(basename "$PROJECT_DIR")"
    branch_name="$(git -C "$PROJECT_DIR" branch --show-current 2>/dev/null || echo "detached")"
    timestamp_utc="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    phase_value="${CURRENT_PHASE:-unknown}"
    attempt_value="${CURRENT_PHASE_ATTEMPT:-0}"
    iteration_value="${ITERATION_COUNT:-0}"

    message="$(cat <<EOF
[ralphie] event=$event status=$status
project=$project_name branch=$branch_name session=${SESSION_ID:-unknown}
phase=$phase_value attempt=$attempt_value iteration=$iteration_value engine=${ACTIVE_ENGINE:-unknown}
details=$effective_details
timestamp_utc=$timestamp_utc
EOF
)"

    if is_true "$NOTIFY_TELEGRAM_ENABLED" && [ -n "$TG_BOT_TOKEN" ] && [ -n "$TG_CHAT_ID" ]; then
        if send_telegram_message_raw "$TG_BOT_TOKEN" "$TG_CHAT_ID" "$message"; then
            delivered=true
        fi
        if is_true "$NOTIFY_TTS_ENABLED" && [ -n "$CHUTES_API_KEY" ]; then
            local tts_line
            tts_line="$(build_tts_notification_line "$event" "$status" "$effective_details")"
            tts_attempted=true
            if send_telegram_tts_raw \
                "$CHUTES_API_KEY" \
                "$NOTIFY_CHUTES_TTS_URL" \
                "$NOTIFY_CHUTES_VOICE" \
                "$NOTIFY_CHUTES_SPEED" \
                "$TG_BOT_TOKEN" \
                "$TG_CHAT_ID" \
                "$tts_line" \
                "ralphie $event"; then
                delivered=true
            else
                tts_failed=true
            fi
        fi
    fi

    if is_true "$NOTIFY_DISCORD_ENABLED" && [ -n "$NOTIFY_DISCORD_WEBHOOK_URL" ]; then
        if send_discord_message_raw "$NOTIFY_DISCORD_WEBHOOK_URL" "$message"; then
            delivered=true
        fi
        if is_true "$NOTIFY_TTS_ENABLED" && [ -n "$CHUTES_API_KEY" ]; then
            local discord_tts_line
            discord_tts_line="$(build_tts_notification_line "$event" "$status" "$effective_details")"
            tts_attempted=true
            if send_discord_tts_raw \
                "$CHUTES_API_KEY" \
                "$NOTIFY_CHUTES_TTS_URL" \
                "$NOTIFY_CHUTES_VOICE" \
                "$NOTIFY_CHUTES_SPEED" \
                "$NOTIFY_DISCORD_WEBHOOK_URL" \
                "$discord_tts_line" \
                "ralphie $event"; then
                delivered=true
            else
                tts_failed=true
            fi
        fi
    fi

    if [ "$event" != "session_error" ]; then
        NOTIFY_LAST_EVENT_SIGNATURE="${event_signature:-${event}|${status}|$(printf '%s' "$details" | cut -c 1-220)}"
        NOTIFY_LAST_EVENT_SENT_AT="$now_epoch"
    fi

    delivery_details="$effective_details"
    if [ "$tts_attempted" = true ] && [ "$tts_failed" = true ]; then
        delivery_details="${delivery_details}; tts=fallback_text_only"
    fi
    notification_log_append "$event" "$status" "$([ "$delivered" = true ] && echo "delivered" || echo "failed")" "$delivery_details"
    return 0
}

persist_notification_wizard_bootstrap_flag() {
    NOTIFICATION_WIZARD_BOOTSTRAPPED="true"
    if ! upsert_config_env_value "RALPHIE_NOTIFICATION_WIZARD_BOOTSTRAPPED" "true"; then
        warn "Could not persist RALPHIE_NOTIFICATION_WIZARD_BOOTSTRAPPED to $(path_for_display "$CONFIG_FILE")."
        return 1
    fi
    return 0
}

persist_notification_value() {
    local key="$1"
    local value="${2:-}"
    if ! upsert_config_env_value "$key" "$value"; then
        warn "Could not persist $key to $(path_for_display "$CONFIG_FILE")."
        return 1
    fi
    return 0
}

run_first_deploy_notification_wizard() {
    if is_true "$NOTIFICATION_WIZARD_BOOTSTRAPPED"; then
        return 1
    fi
    if ! is_tty_input_available; then
        return 1
    fi
    if ! command -v curl >/dev/null 2>&1; then
        warn "Notification setup skipped: curl is required for Telegram/Discord/Chutes delivery checks."
        persist_notification_wizard_bootstrap_flag || true
        return 1
    fi

    info "First-deploy notification setup is available."
    info "Standardized events: session_start, phase_decision, phase_complete, phase_blocked, session_done, session_error."
    info "Channels supported: Telegram bot, Discord webhook, optional Chutes TTS voice attachments."
    info "Anti-spam policy: only high-signal events are sent; repeated incident alerts are batched with periodic reminders."

    if [ "$(prompt_yes_no "Configure notifications now (Telegram/Discord/Chutes TTS)?" "n")" != "true" ]; then
        info "Skipping first-deploy notification setup."
        persist_notification_wizard_bootstrap_flag || true
        return 1
    fi

    local telegram_selected="false"
    local discord_selected="false"
    local tts_selected="false"

    info "Telegram setup guide:"
    info "  1) Open Telegram @BotFather, run /newbot, copy bot token."
    info "  2) Send one message to your bot/chat/channel."
    info "  3) Open https://api.telegram.org/bot<token>/getUpdates and copy chat.id (or let Ralphie auto-discover it)."
    if [ "$(prompt_yes_no "Configure Telegram notifications?" "$(is_true "$NOTIFY_TELEGRAM_ENABLED" && echo y || echo n)")" = "true" ]; then
        local suggested_chat_id=""
        telegram_selected="true"
        TG_BOT_TOKEN="$(prompt_override_value "Telegram bot token (TG_BOT_TOKEN)" "$TG_BOT_TOKEN")"
        if [ -z "$TG_CHAT_ID" ] && [ -n "$TG_BOT_TOKEN" ]; then
            suggested_chat_id="$(telegram_suggest_chat_id_raw "$TG_BOT_TOKEN")"
            if [ -n "$suggested_chat_id" ]; then
                TG_CHAT_ID="$suggested_chat_id"
            fi
        fi
        TG_CHAT_ID="$(prompt_override_value "Telegram chat id (TG_CHAT_ID)" "$TG_CHAT_ID")"
        if [ -z "$TG_CHAT_ID" ] && [ -n "$TG_BOT_TOKEN" ]; then
            suggested_chat_id="$(telegram_suggest_chat_id_raw "$TG_BOT_TOKEN")"
            if [ -n "$suggested_chat_id" ]; then
                info "Using discovered chat id: $suggested_chat_id"
                TG_CHAT_ID="$suggested_chat_id"
            fi
        fi
        if [ -z "$TG_BOT_TOKEN" ] || [ -z "$TG_CHAT_ID" ]; then
            warn "Telegram credentials are incomplete; disabling Telegram channel."
            telegram_selected="false"
        elif send_telegram_message_raw "$TG_BOT_TOKEN" "$TG_CHAT_ID" "[ralphie] telegram setup test"; then
            success "Telegram test message sent."
        else
            warn "Telegram test failed. Verify bot token/chat id and bot permissions."
        fi
    fi

    info "Discord setup guide:"
    info "  1) Open Server Settings -> Integrations -> Webhooks."
    info "  2) Create webhook, copy URL, and paste it here."
    if [ "$(prompt_yes_no "Configure Discord webhook notifications?" "$(is_true "$NOTIFY_DISCORD_ENABLED" && echo y || echo n)")" = "true" ]; then
        discord_selected="true"
        NOTIFY_DISCORD_WEBHOOK_URL="$(prompt_override_value "Discord webhook URL" "$NOTIFY_DISCORD_WEBHOOK_URL")"
        if [ -z "$NOTIFY_DISCORD_WEBHOOK_URL" ]; then
            warn "Discord webhook URL is empty; disabling Discord channel."
            discord_selected="false"
        elif send_discord_message_raw "$NOTIFY_DISCORD_WEBHOOK_URL" "[ralphie] discord setup test"; then
            success "Discord test message sent."
        else
            warn "Discord webhook test failed. Verify webhook URL and channel permissions."
        fi
    fi

    if [ "$telegram_selected" = "true" ] || [ "$discord_selected" = "true" ]; then
        info "Optional Chutes TTS setup guide:"
        info "  1) Create API key at https://chutes.ai"
        info "  2) Provide CHUTES_API_KEY to enable voice notifications (Telegram and/or Discord)."
        if [ "$(prompt_yes_no "Enable Chutes TTS voice notifications?" "$(is_true "$NOTIFY_TTS_ENABLED" && echo y || echo n)")" = "true" ]; then
            tts_selected="true"
            CHUTES_API_KEY="$(prompt_override_value "Chutes API key (CHUTES_API_KEY)" "$CHUTES_API_KEY")"
            NOTIFY_TTS_STYLE="$(prompt_override_value "TTS narration style (standard|friendly|ralph_wiggum)" "$NOTIFY_TTS_STYLE")"
            NOTIFY_TTS_STYLE="$(normalize_notify_tts_style "$NOTIFY_TTS_STYLE")"
            NOTIFY_CHUTES_VOICE="$(prompt_override_value "Chutes voice id" "$NOTIFY_CHUTES_VOICE")"
            NOTIFY_CHUTES_SPEED="$(prompt_override_value "Chutes speed (example 1.0)" "$NOTIFY_CHUTES_SPEED")"
            if ! is_decimal_number "$NOTIFY_CHUTES_SPEED"; then
                warn "Invalid Chutes speed; defaulting to $DEFAULT_NOTIFY_CHUTES_SPEED."
                NOTIFY_CHUTES_SPEED="$DEFAULT_NOTIFY_CHUTES_SPEED"
            fi
            if [ -z "$CHUTES_API_KEY" ]; then
                warn "Chutes API key is empty; disabling TTS channel."
                tts_selected="false"
            else
                if [ "$telegram_selected" = "true" ]; then
                    if send_telegram_tts_raw \
                        "$CHUTES_API_KEY" \
                        "$NOTIFY_CHUTES_TTS_URL" \
                        "$NOTIFY_CHUTES_VOICE" \
                        "$NOTIFY_CHUTES_SPEED" \
                        "$TG_BOT_TOKEN" \
                        "$TG_CHAT_ID" \
                        "ralphie setup test message" \
                        "ralphie tts test"; then
                        success "Telegram TTS test voice sent."
                    else
                        warn "Telegram TTS test failed. Verify CHUTES_API_KEY and Telegram credentials."
                    fi
                fi
                if [ "$discord_selected" = "true" ] && [ -n "$NOTIFY_DISCORD_WEBHOOK_URL" ]; then
                    if send_discord_tts_raw \
                        "$CHUTES_API_KEY" \
                        "$NOTIFY_CHUTES_TTS_URL" \
                        "$NOTIFY_CHUTES_VOICE" \
                        "$NOTIFY_CHUTES_SPEED" \
                        "$NOTIFY_DISCORD_WEBHOOK_URL" \
                        "ralphie setup test message" \
                        "ralphie tts test"; then
                        success "Discord TTS test voice sent."
                    else
                        warn "Discord TTS test failed. Verify CHUTES_API_KEY and webhook permissions."
                    fi
                fi
            fi
        fi
    fi

    if [ "$(prompt_yes_no "Adjust anti-spam notification cadence?" "n")" = "true" ]; then
        local dedup_candidate reminder_candidate
        dedup_candidate="$(prompt_optional_line "Duplicate-event suppression window seconds (0 disables suppression)" "$NOTIFY_EVENT_DEDUP_WINDOW_SECONDS")"
        reminder_candidate="$(prompt_optional_line "Incident reminder interval minutes (0 disables reminders)" "$NOTIFY_INCIDENT_REMINDER_MINUTES")"
        if is_number "$dedup_candidate" && [ "$dedup_candidate" -ge 0 ]; then
            NOTIFY_EVENT_DEDUP_WINDOW_SECONDS="$dedup_candidate"
        else
            warn "Invalid dedup window '$dedup_candidate'; keeping ${NOTIFY_EVENT_DEDUP_WINDOW_SECONDS}."
        fi
        if is_number "$reminder_candidate" && [ "$reminder_candidate" -ge 0 ]; then
            NOTIFY_INCIDENT_REMINDER_MINUTES="$reminder_candidate"
        else
            warn "Invalid incident reminder interval '$reminder_candidate'; keeping ${NOTIFY_INCIDENT_REMINDER_MINUTES}."
        fi
    fi

    NOTIFY_TELEGRAM_ENABLED="$telegram_selected"
    NOTIFY_DISCORD_ENABLED="$discord_selected"
    NOTIFY_TTS_ENABLED="$tts_selected"
    if [ "$NOTIFY_TELEGRAM_ENABLED" = "true" ] || [ "$NOTIFY_DISCORD_ENABLED" = "true" ]; then
        NOTIFICATIONS_ENABLED="true"
    else
        NOTIFICATIONS_ENABLED="false"
        NOTIFY_TTS_ENABLED="false"
    fi
    if [ "$NOTIFY_TELEGRAM_ENABLED" != "true" ] && [ "$NOTIFY_DISCORD_ENABLED" != "true" ]; then
        NOTIFY_TTS_ENABLED="false"
    fi

    persist_notification_value "RALPHIE_NOTIFICATIONS_ENABLED" "$NOTIFICATIONS_ENABLED" || true
    persist_notification_value "RALPHIE_NOTIFY_TELEGRAM_ENABLED" "$NOTIFY_TELEGRAM_ENABLED" || true
    persist_notification_value "TG_BOT_TOKEN" "$TG_BOT_TOKEN" || true
    persist_notification_value "TG_CHAT_ID" "$TG_CHAT_ID" || true
    persist_notification_value "RALPHIE_NOTIFY_DISCORD_ENABLED" "$NOTIFY_DISCORD_ENABLED" || true
    persist_notification_value "RALPHIE_NOTIFY_DISCORD_WEBHOOK_URL" "$NOTIFY_DISCORD_WEBHOOK_URL" || true
    persist_notification_value "RALPHIE_NOTIFY_TTS_ENABLED" "$NOTIFY_TTS_ENABLED" || true
    persist_notification_value "RALPHIE_NOTIFY_TTS_STYLE" "$NOTIFY_TTS_STYLE" || true
    persist_notification_value "CHUTES_API_KEY" "$CHUTES_API_KEY" || true
    persist_notification_value "RALPHIE_NOTIFY_CHUTES_TTS_URL" "$NOTIFY_CHUTES_TTS_URL" || true
    persist_notification_value "RALPHIE_NOTIFY_CHUTES_VOICE" "$NOTIFY_CHUTES_VOICE" || true
    persist_notification_value "RALPHIE_NOTIFY_CHUTES_SPEED" "$NOTIFY_CHUTES_SPEED" || true
    persist_notification_value "RALPHIE_NOTIFY_EVENT_DEDUP_WINDOW_SECONDS" "$NOTIFY_EVENT_DEDUP_WINDOW_SECONDS" || true
    persist_notification_value "RALPHIE_NOTIFY_INCIDENT_REMINDER_MINUTES" "$NOTIFY_INCIDENT_REMINDER_MINUTES" || true
    persist_notification_wizard_bootstrap_flag || true

    info "Notification setup saved to $(path_for_display "$CONFIG_FILE")."
    info "Notification channels configured: $(notification_channels_for_display)"

    if is_true "$NOTIFICATIONS_ENABLED"; then
        notify_event "notification_setup" "ok" "notification channels configured via first-deploy wizard"
        return 0
    fi
    return 1
}

persist_engine_override_bootstrap_flag() {
    ENGINE_OVERRIDES_BOOTSTRAPPED="true"
    if ! upsert_config_env_value "RALPHIE_ENGINE_OVERRIDES_BOOTSTRAPPED" "true"; then
        warn "Could not persist RALPHIE_ENGINE_OVERRIDES_BOOTSTRAPPED to $(path_for_display "$CONFIG_FILE")."
        return 1
    fi
    return 0
}

persist_engine_override_value() {
    local key="$1"
    local value="${2:-}"
    if ! upsert_config_env_value "$key" "$value"; then
        warn "Could not persist $key to $(path_for_display "$CONFIG_FILE")."
        return 1
    fi
    return 0
}

run_first_deploy_engine_override_wizard() {
    if is_true "$ENGINE_OVERRIDES_BOOTSTRAPPED"; then
        return 1
    fi
    if ! is_tty_input_available; then
        return 1
    fi

    info "First-deploy engine override setup is available."
    info "Requested engine mode: $ENGINE_SELECTION_REQUESTED (auto preference: $AUTO_ENGINE_PREFERENCE)"
    info "Healthy engines from readiness checks: $(healthy_engines_for_display)"

    if [ "$(prompt_yes_no "Configure engine selection and provider/model/thinking overrides now?" "y")" != "true" ]; then
        info "Skipping first-deploy engine override setup."
        persist_engine_override_bootstrap_flag || true
        return 1
    fi

    local overrides_changed=false
    local selected_engine_choice preferred_auto_choice
    local codex_endpoint_choice codex_model_choice codex_thinking_choice
    local codex_schema_enabled_choice codex_schema_file_choice
    local claude_endpoint_choice claude_model_choice claude_thinking_choice

    selected_engine_choice="$(to_lower "$(prompt_read_line "Engine mode (auto|codex|claude) [current: $ENGINE_SELECTION_REQUESTED]: " "$ENGINE_SELECTION_REQUESTED")")"
    case "$selected_engine_choice" in
        auto|codex|claude) ;;
        *)
            warn "Invalid engine mode '$selected_engine_choice'. Keeping '$ENGINE_SELECTION_REQUESTED'."
            selected_engine_choice="$ENGINE_SELECTION_REQUESTED"
            ;;
    esac
    if [ "$selected_engine_choice" != "$ENGINE_SELECTION_REQUESTED" ]; then
        ENGINE_SELECTION_REQUESTED="$selected_engine_choice"
        overrides_changed=true
    fi
    persist_engine_override_value "RALPHIE_ENGINE" "$ENGINE_SELECTION_REQUESTED" || true

    if [ "$ENGINE_SELECTION_REQUESTED" = "auto" ]; then
        preferred_auto_choice="$(to_lower "$(prompt_read_line "AUTO preference (codex|claude) [current: $AUTO_ENGINE_PREFERENCE]: " "$AUTO_ENGINE_PREFERENCE")")"
        case "$preferred_auto_choice" in
            codex|claude) ;;
            *)
                warn "Invalid AUTO preference '$preferred_auto_choice'. Keeping '$AUTO_ENGINE_PREFERENCE'."
                preferred_auto_choice="$AUTO_ENGINE_PREFERENCE"
                ;;
        esac
        if [ "$preferred_auto_choice" != "$AUTO_ENGINE_PREFERENCE" ]; then
            AUTO_ENGINE_PREFERENCE="$preferred_auto_choice"
            overrides_changed=true
        fi
        persist_engine_override_value "RALPHIE_AUTO_ENGINE_PREFERENCE" "$AUTO_ENGINE_PREFERENCE" || true
    fi

    if [ "$CODEX_HEALTHY" = "true" ]; then
        if [ "$(prompt_yes_no "Configure Codex endpoint/model/thinking/schema overrides?" "n")" = "true" ]; then
            codex_endpoint_choice="$(prompt_override_value "Codex endpoint (OPENAI_BASE_URL)" "$CODEX_ENDPOINT")"
            codex_model_choice="$(prompt_override_value "Codex model" "${CODEX_MODEL:-}")"
            codex_thinking_choice="$(to_lower "$(prompt_override_value "Codex thinking override (none|minimal|low|medium|high|xhigh)" "$CODEX_THINKING_OVERRIDE")")"
            case "$codex_thinking_choice" in
                none|minimal|low|medium|high|xhigh|"") ;;
                *)
                    warn "Invalid codex thinking override '$codex_thinking_choice'. Keeping '$CODEX_THINKING_OVERRIDE'."
                    codex_thinking_choice="$CODEX_THINKING_OVERRIDE"
                    ;;
            esac

            if [ "$(prompt_yes_no "Enable Codex output schema?" "$(is_true "$CODEX_USE_RESPONSES_SCHEMA" && echo y || echo n)")" = "true" ]; then
                codex_schema_enabled_choice="true"
                codex_schema_file_choice="$(prompt_override_value "Codex schema file path" "$CODEX_RESPONSES_SCHEMA_FILE")"
            else
                codex_schema_enabled_choice="false"
                codex_schema_file_choice="$CODEX_RESPONSES_SCHEMA_FILE"
            fi

            [ "$codex_endpoint_choice" = "$CODEX_ENDPOINT" ] || overrides_changed=true
            [ "$codex_model_choice" = "${CODEX_MODEL:-}" ] || overrides_changed=true
            [ "$codex_thinking_choice" = "$CODEX_THINKING_OVERRIDE" ] || overrides_changed=true
            [ "$codex_schema_enabled_choice" = "$CODEX_USE_RESPONSES_SCHEMA" ] || overrides_changed=true
            [ "$codex_schema_file_choice" = "$CODEX_RESPONSES_SCHEMA_FILE" ] || overrides_changed=true

            CODEX_ENDPOINT="$codex_endpoint_choice"
            CODEX_MODEL="$codex_model_choice"
            CODEX_THINKING_OVERRIDE="$codex_thinking_choice"
            CODEX_USE_RESPONSES_SCHEMA="$codex_schema_enabled_choice"
            CODEX_RESPONSES_SCHEMA_FILE="$codex_schema_file_choice"

            persist_engine_override_value "RALPHIE_CODEX_ENDPOINT" "$CODEX_ENDPOINT" || true
            persist_engine_override_value "CODEX_MODEL" "$CODEX_MODEL" || true
            persist_engine_override_value "RALPHIE_CODEX_THINKING_OVERRIDE" "$CODEX_THINKING_OVERRIDE" || true
            persist_engine_override_value "RALPHIE_CODEX_USE_RESPONSES_SCHEMA" "$CODEX_USE_RESPONSES_SCHEMA" || true
            persist_engine_override_value "RALPHIE_CODEX_RESPONSES_SCHEMA_FILE" "$CODEX_RESPONSES_SCHEMA_FILE" || true
        fi
    fi

    if [ "$CLAUDE_HEALTHY" = "true" ]; then
        if [ "$(prompt_yes_no "Configure Claude endpoint/model/thinking overrides?" "n")" = "true" ]; then
            claude_endpoint_choice="$(prompt_override_value "Claude endpoint (ANTHROPIC_BASE_URL)" "$CLAUDE_ENDPOINT")"
            claude_model_choice="$(prompt_override_value "Claude model" "${CLAUDE_MODEL:-}")"
            claude_thinking_choice="$(to_lower "$(prompt_override_value "Claude thinking override (none|off|low|medium|high|xhigh)" "$CLAUDE_THINKING_OVERRIDE")")"
            case "$claude_thinking_choice" in
                none|off|low|medium|high|xhigh|"") ;;
                *)
                    warn "Invalid claude thinking override '$claude_thinking_choice'. Keeping '$CLAUDE_THINKING_OVERRIDE'."
                    claude_thinking_choice="$CLAUDE_THINKING_OVERRIDE"
                    ;;
            esac

            [ "$claude_endpoint_choice" = "$CLAUDE_ENDPOINT" ] || overrides_changed=true
            [ "$claude_model_choice" = "${CLAUDE_MODEL:-}" ] || overrides_changed=true
            [ "$claude_thinking_choice" = "$CLAUDE_THINKING_OVERRIDE" ] || overrides_changed=true

            CLAUDE_ENDPOINT="$claude_endpoint_choice"
            CLAUDE_MODEL="$claude_model_choice"
            CLAUDE_THINKING_OVERRIDE="$claude_thinking_choice"

            persist_engine_override_value "RALPHIE_CLAUDE_ENDPOINT" "$CLAUDE_ENDPOINT" || true
            persist_engine_override_value "CLAUDE_MODEL" "$CLAUDE_MODEL" || true
            persist_engine_override_value "RALPHIE_CLAUDE_THINKING_OVERRIDE" "$CLAUDE_THINKING_OVERRIDE" || true
        fi
    fi

    persist_engine_override_bootstrap_flag || true

    if [ "$overrides_changed" = "true" ]; then
        info "Engine overrides saved to $(path_for_display "$CONFIG_FILE")."
        return 0
    fi
    info "Engine override setup completed with no changes."
    return 1
}

run_command_with_timeout() {
    local timeout_seconds="$1"
    shift

    if ! is_number "$timeout_seconds" || [ "$timeout_seconds" -lt 1 ]; then
        timeout_seconds=15
    fi

    if command -v timeout >/dev/null 2>&1; then
        timeout "$timeout_seconds" "$@"
        return $?
    fi
    if command -v gtimeout >/dev/null 2>&1; then
        gtimeout "$timeout_seconds" "$@"
        return $?
    fi
    if command -v perl >/dev/null 2>&1; then
        perl -e 'alarm shift; exec @ARGV' "$timeout_seconds" "$@"
        return $?
    fi

    # Portable watchdog fallback if timeout/gtimeout/perl are unavailable.
    local timeout_marker cmd_pid watchdog_pid cmd_exit
    timeout_marker="$(mktemp "${TMPDIR:-/tmp}/ralphie_timeout.XXXXXX")" || return 1
    rm -f "$timeout_marker"

    "$@" &
    cmd_pid=$!
    (
        sleep "$timeout_seconds"
        if kill -0 "$cmd_pid" 2>/dev/null; then
            : > "$timeout_marker"
            kill -TERM "$cmd_pid" 2>/dev/null || true
            sleep 1
            kill -KILL "$cmd_pid" 2>/dev/null || true
        fi
    ) &
    watchdog_pid=$!

    if wait "$cmd_pid"; then
        cmd_exit=0
    else
        cmd_exit=$?
    fi

    kill -TERM "$watchdog_pid" 2>/dev/null || true
    wait "$watchdog_pid" 2>/dev/null || true

    if [ -f "$timeout_marker" ]; then
        rm -f "$timeout_marker"
        return 124
    fi
    rm -f "$timeout_marker"
    return "$cmd_exit"
}

run_startup_operational_probe() {
    local -a failures=()
    local cmd
    local probe_file=""
    local timeout_probe_exit=0
    local -a required_cmds=(
        sh sleep mktemp sed awk grep find sort date
        git seq cut head tail wc tr tee comm cmp
    )

    for cmd in "${required_cmds[@]}"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            failures+=("missing required command: $cmd")
        fi
    done

    if ! mkdir -p "$CONFIG_DIR" 2>/dev/null; then
        failures+=("unable to create config dir: $(path_for_display "$CONFIG_DIR")")
    else
        probe_file="$(mktemp "$CONFIG_DIR/operational-probe.XXXXXX" 2>/dev/null || true)"
        if [ -z "$probe_file" ]; then
            failures+=("unable to write probe file under $(path_for_display "$CONFIG_DIR")")
        else
            rm -f "$probe_file"
        fi
    fi

    if run_command_with_timeout 1 sh -c 'sleep 2' >/dev/null 2>&1; then
        timeout_probe_exit=0
    else
        timeout_probe_exit=$?
    fi
    if [ "$timeout_probe_exit" -ne 124 ] && [ "$timeout_probe_exit" -ne 142 ] && [ "$timeout_probe_exit" -ne 143 ] && [ "$timeout_probe_exit" -ne 137 ]; then
        failures+=("timeout wrapper probe failed (expected timeout-like exit, got $timeout_probe_exit)")
    fi

    if [ "${#failures[@]}" -gt 0 ]; then
        warn "Startup operational probe failed:"
        for cmd in "${failures[@]}"; do
            warn "  - $cmd"
        done
        log_reason_code "RB_STARTUP_OPERATIONAL_PROBE_FAILED" "$(summarize_blocks_for_log "${failures[@]}")"
        return 1
    fi

    if is_true "$ENGINE_HEALTH_RETRY_VERBOSE"; then
        info "Startup operational probe passed."
    fi
    return 0
}

# Engine Smoke Test — verify an engine can actually respond to a prompt
smoke_test_engine() {
    local engine_cmd="$1"
    local engine_name="$2"
    local timeout_seconds="${ENGINE_SMOKE_TEST_TIMEOUT:-15}"
    local -a smoke_prefix=()
    local -a smoke_args=()

    [ -n "$engine_cmd" ] || return 1
    command -v "$engine_cmd" >/dev/null 2>&1 || return 1

    local canary_token
    canary_token="ralphie_smoke_$(date +%s)_${RANDOM:-0}"
    local prompt_file output_file
    prompt_file="$(mktemp "${TMPDIR:-/tmp}/ralphie_smoke_prompt.XXXXXX")" || return 1
    output_file="$(mktemp "${TMPDIR:-/tmp}/ralphie_smoke_output.XXXXXX")" || { rm -f "$prompt_file"; return 1; }

    printf 'Reply with ONLY this exact token on a single line, nothing else: %s\n' "$canary_token" > "$prompt_file"

    local smoke_exit=1
    local smoke_start smoke_elapsed
    smoke_start="$(date +%s)"

    if [ "$engine_name" = "codex" ]; then
        if [ -n "$CODEX_ENDPOINT" ]; then
            smoke_prefix=("env" "OPENAI_BASE_URL=$CODEX_ENDPOINT")
        fi
        smoke_args=("$engine_cmd" "exec")
        [ -n "${CODEX_MODEL:-}" ] && smoke_args+=("--model" "$CODEX_MODEL")
        if [ -n "$CODEX_THINKING_OVERRIDE" ]; then
            smoke_args+=("-c" "model_reasoning_effort=\"$CODEX_THINKING_OVERRIDE\"")
        fi
        run_command_with_timeout "$timeout_seconds" "${smoke_prefix[@]+"${smoke_prefix[@]}"}" "${smoke_args[@]}" \
            --output-last-message "$output_file" \
            - < "$prompt_file" >/dev/null 2>&1 && smoke_exit=0 || smoke_exit=$?
    elif [ "$engine_name" = "claude" ]; then
        if [ -n "$CLAUDE_ENDPOINT" ]; then
            smoke_prefix=("env" "ANTHROPIC_BASE_URL=$CLAUDE_ENDPOINT")
        fi
        smoke_args=("$engine_cmd" "-p")
        [ -n "${CLAUDE_MODEL:-}" ] && smoke_args+=("--model" "$CLAUDE_MODEL")
        case "$CLAUDE_THINKING_OVERRIDE" in
            high|xhigh)
                smoke_args+=("--settings" '{"alwaysThinkingEnabled":true}')
                ;;
            none|off|low)
                smoke_args+=("--settings" '{"alwaysThinkingEnabled":false}')
                ;;
            medium|"")
                :
                ;;
            *)
                :
                ;;
        esac
        run_command_with_timeout "$timeout_seconds" "${smoke_prefix[@]+"${smoke_prefix[@]}"}" "${smoke_args[@]}" \
            < "$prompt_file" > "$output_file" 2>/dev/null && smoke_exit=0 || smoke_exit=$?
    fi

    smoke_elapsed=$(( $(date +%s) - smoke_start ))
    local result=1
    # Check for canary token in output regardless of exit code — the engine may
    # have written the correct response before timeout killed the process.
    # Strip newlines before matching to handle LLMs that split the token across lines.
    if [ -f "$output_file" ] && [ -s "$output_file" ]; then
        if tr -d '\n\r' < "$output_file" 2>/dev/null | grep -qF "$canary_token"; then
            result=0
        fi
    fi

    if is_true "$ENGINE_HEALTH_RETRY_VERBOSE"; then
        if [ "$result" -eq 0 ]; then
            info "Smoke test $engine_name: PASS (${smoke_elapsed}s)"
        else
            warn "Smoke test $engine_name: FAIL (exit=$smoke_exit, ${smoke_elapsed}s, token ${canary_token:0:16}...)"
        fi
    fi

    rm -f "$prompt_file" "$output_file"
    return "$result"
}

# Multi-Agent Capability Detection
probe_engine_capabilities() {
    local force_reprobe="${1:-false}"
    local probe_scope="${2:-${ENGINE_SELECTION_REQUESTED:-auto}}"
    local probe_codex="true"
    local probe_claude="true"

    if is_true "$ENGINE_CAPABILITIES_PROBED" && ! is_true "$force_reprobe"; then
        return 0
    fi
    probe_scope="$(to_lower "$probe_scope")"
    case "$probe_scope" in
        codex)
            probe_claude="false"
            ;;
        claude)
            probe_codex="false"
            ;;
        auto|"")
            ;;
        *)
            probe_scope="auto"
            ;;
    esac

    CODEX_CAP_OUTPUT_LAST_MESSAGE=0
    CODEX_CAP_YOLO_FLAG=0
    CODEX_CAP_NOTE=""
    CLAUDE_CAP_NOTE=""
    CLAUDE_CAP_PRINT=0
    CLAUDE_CAP_YOLO_FLAG=""
    CODEX_HEALTHY="false"
    CLAUDE_HEALTHY="false"
    CODEX_SMOKE_PASS="false"
    CLAUDE_SMOKE_PASS="false"

    # Probing Claude Code
    if ! is_true "$probe_claude"; then
        CLAUDE_CAP_NOTE="not probed for requested engine scope '$probe_scope'"
    elif command -v "$CLAUDE_CMD" >/dev/null 2>&1; then
        local claude_help
        claude_help="$("$CLAUDE_CMD" --help 2>&1 || true)"
        if echo "$claude_help" | grep -qE -- "-p, --print"; then
            CLAUDE_CAP_PRINT=1
        else
            CLAUDE_CAP_NOTE="missing required --print mode"
        fi

        if echo "$claude_help" | grep -qE -- "--dangerously-skip-permissions"; then
            CLAUDE_CAP_YOLO_FLAG="--dangerously-skip-permissions"
        fi

        if ! echo "$claude_help" | grep -qiE "read|write|tool|file|edit|command"; then
            if is_true "$ENGINE_HEALTH_RETRY_VERBOSE"; then
                warn "Claude help output lacks read/write/tool hints; relying on functional smoke test."
            fi
        fi

        # Functional smoke test: verify engine actually responds
        if [ -z "$CLAUDE_CAP_NOTE" ]; then
            if smoke_test_engine "$CLAUDE_CMD" "claude"; then
                CLAUDE_SMOKE_PASS="true"
            else
                CLAUDE_CAP_NOTE="smoke test failed: engine unresponsive or returned wrong output"
                CLAUDE_SMOKE_PASS="false"
            fi
        fi

        [ -z "$CLAUDE_CAP_NOTE" ] && CLAUDE_HEALTHY="true"
    else
        CLAUDE_CAP_NOTE="command not found: $CLAUDE_CMD"
    fi

    # Probing Codex
    if ! is_true "$probe_codex"; then
        CODEX_CAP_NOTE="not probed for requested engine scope '$probe_scope'"
    elif command -v "$CODEX_CMD" >/dev/null 2>&1; then
        local codex_help
        codex_help="$("$CODEX_CMD" exec --help 2>&1 || true)"
        if echo "$codex_help" | grep -qE -- "--output-last-message"; then
            CODEX_CAP_OUTPUT_LAST_MESSAGE=1
        else
            CODEX_CAP_NOTE="missing required --output-last-message"
        fi

        if echo "$codex_help" | grep -qE -- "--dangerously-bypass-approvals-and-sandbox"; then
            CODEX_CAP_YOLO_FLAG=1
        fi

        if ! echo "$codex_help" | grep -qiE "read|write|tool|file|edit|command|exec"; then
            if is_true "$ENGINE_HEALTH_RETRY_VERBOSE"; then
                warn "Codex help output lacks read/write/tool hints; relying on functional smoke test."
            fi
        fi

        # Functional smoke test: verify engine actually responds
        if [ -z "$CODEX_CAP_NOTE" ]; then
            if smoke_test_engine "$CODEX_CMD" "codex"; then
                CODEX_SMOKE_PASS="true"
            else
                CODEX_CAP_NOTE="smoke test failed: engine unresponsive or returned wrong output"
                CODEX_SMOKE_PASS="false"
            fi
        fi

        [ -z "$CODEX_CAP_NOTE" ] && CODEX_HEALTHY="true"
    else
        CODEX_CAP_NOTE="command not found: $CODEX_CMD"
    fi

    ENGINE_CAPABILITIES_PROBED=true
}

log_engine_health_summary() {
    local codex_line
    local claude_line
    if [ "$CODEX_HEALTHY" = "true" ]; then
        codex_line="codex: healthy (smoke=${CODEX_SMOKE_PASS})"
    else
        codex_line="codex: unhealthy (${CODEX_CAP_NOTE:-unknown})"
    fi
    if [ "$CLAUDE_HEALTHY" = "true" ]; then
        claude_line="claude: healthy (smoke=${CLAUDE_SMOKE_PASS})"
    else
        claude_line="claude: unhealthy (${CLAUDE_CAP_NOTE:-unknown})"
    fi
    info "Engine health: $codex_line | $claude_line"
}

resolve_active_engine() {
    local requested_engine="$1"
    LAST_ENGINE_SELECTION_BLOCK_REASON=""
    local preferred_auto_engine="${AUTO_ENGINE_PREFERENCE:-$DEFAULT_AUTO_ENGINE_PREFERENCE}"
    local fallback_auto_engine="claude"
    preferred_auto_engine="$(to_lower "$preferred_auto_engine")"
    case "$preferred_auto_engine" in
        codex|claude) ;;
        *) preferred_auto_engine="$DEFAULT_AUTO_ENGINE_PREFERENCE" ;;
    esac
    if [ "$preferred_auto_engine" = "claude" ]; then
        fallback_auto_engine="codex"
    fi

    case "$requested_engine" in
        auto)
            # Auto: prefer configured engine, fall back to the other silently.
            if [ "$preferred_auto_engine" = "codex" ] && [ "$CODEX_HEALTHY" = "true" ]; then
                ACTIVE_ENGINE="codex"
                ACTIVE_CMD="$CODEX_CMD"
                return 0
            fi
            if [ "$preferred_auto_engine" = "claude" ] && [ "$CLAUDE_HEALTHY" = "true" ]; then
                ACTIVE_ENGINE="claude"
                ACTIVE_CMD="$CLAUDE_CMD"
                return 0
            fi
            if [ "$fallback_auto_engine" = "codex" ] && [ "$CODEX_HEALTHY" = "true" ]; then
                ACTIVE_ENGINE="codex"
                ACTIVE_CMD="$CODEX_CMD"
                return 0
            fi
            if [ "$fallback_auto_engine" = "claude" ] && [ "$CLAUDE_HEALTHY" = "true" ]; then
                ACTIVE_ENGINE="claude"
                ACTIVE_CMD="$CLAUDE_CMD"
                return 0
            fi
            LAST_ENGINE_SELECTION_BLOCK_REASON="AUTO requested but neither codex nor claude is healthy."
            return 1
            ;;
        codex)
            # Explicit codex: use it or fail. No silent switch.
            if [ "$CODEX_HEALTHY" = "true" ]; then
                ACTIVE_ENGINE="codex"
                ACTIVE_CMD="$CODEX_CMD"
                return 0
            fi
            LAST_ENGINE_SELECTION_BLOCK_REASON="RALPHIE_ENGINE=codex but codex is unavailable (${CODEX_CAP_NOTE:-unknown})."
            err "$LAST_ENGINE_SELECTION_BLOCK_REASON"
            return 1
            ;;
        claude)
            # Explicit claude: use it or fail. No silent switch.
            if [ "$CLAUDE_HEALTHY" = "true" ]; then
                ACTIVE_ENGINE="claude"
                ACTIVE_CMD="$CLAUDE_CMD"
                return 0
            fi
            LAST_ENGINE_SELECTION_BLOCK_REASON="RALPHIE_ENGINE=claude but claude is unavailable (${CLAUDE_CAP_NOTE:-unknown})."
            err "$LAST_ENGINE_SELECTION_BLOCK_REASON"
            return 1
            ;;
        *)
            LAST_ENGINE_SELECTION_BLOCK_REASON="Unsupported requested engine '$requested_engine' during resolution."
            return 1
            ;;
    esac
}

ensure_engines_ready() {
    local requested_engine="$1"
    local max_attempts="$ENGINE_HEALTH_MAX_ATTEMPTS"
    local base_delay="$ENGINE_HEALTH_RETRY_DELAY_SECONDS"
    local attempt=1
    local preferred_auto_engine="${AUTO_ENGINE_PREFERENCE:-$DEFAULT_AUTO_ENGINE_PREFERENCE}"
    preferred_auto_engine="$(to_lower "$preferred_auto_engine")"
    case "$preferred_auto_engine" in
        codex|claude) ;;
        *) preferred_auto_engine="$DEFAULT_AUTO_ENGINE_PREFERENCE" ;;
    esac

    if ! is_number "$max_attempts" || [ "$max_attempts" -lt 1 ]; then
        max_attempts=1
    fi
    if ! is_number "$base_delay" || [ "$base_delay" -lt 0 ]; then
        base_delay=5
    fi

    local warned_unavailable=false
    while [ "$attempt" -le "$max_attempts" ]; do
        if is_true "$ENGINE_HEALTH_RETRY_VERBOSE"; then
            info "Engine readiness check attempt $attempt/$max_attempts..."
        fi

        probe_engine_capabilities "true" "$requested_engine"
        ENGINE_CAPABILITIES_PROBED=true

        if is_true "$ENGINE_HEALTH_RETRY_VERBOSE"; then
            log_engine_health_summary
        fi

        # Warn once about unavailable engines (not on every retry)
        if [ "$warned_unavailable" = false ]; then
            warned_unavailable=true
            if [ "$CODEX_HEALTHY" != "true" ] && [ "$CLAUDE_HEALTHY" != "true" ]; then
                warn "Both engines unavailable: codex (${CODEX_CAP_NOTE:-unknown}), claude (${CLAUDE_CAP_NOTE:-unknown})."
            elif [ "$CODEX_HEALTHY" != "true" ]; then
                warn "codex is unavailable (${CODEX_CAP_NOTE:-unknown})."
            elif [ "$CLAUDE_HEALTHY" != "true" ]; then
                warn "claude is unavailable (${CLAUDE_CAP_NOTE:-unknown})."
            fi
        fi

        if resolve_active_engine "$requested_engine"; then
            if [ "$requested_engine" = "auto" ] && [ "$ACTIVE_ENGINE" != "$preferred_auto_engine" ]; then
                warn "AUTO: preferred $preferred_auto_engine unavailable; proceeding with $ACTIVE_ENGINE."
            fi
            if [ "$attempt" -gt 1 ]; then
                notify_event "phase_decision" "engine_outage_recovered" "engine readiness recovered on attempt $attempt/$max_attempts; active_engine=$ACTIVE_ENGINE" || true
            fi
            if is_true "$ENGINE_HEALTH_RETRY_VERBOSE"; then
                info "Engine ready: $ACTIVE_ENGINE selected (codex=$CODEX_HEALTHY, claude=$CLAUDE_HEALTHY)"
            fi
            return 0
        fi

        if [ "$attempt" -ge "$max_attempts" ]; then
            warn "Engine readiness check failed after $attempt/$max_attempts attempts: $LAST_ENGINE_SELECTION_BLOCK_REASON"
            return 1
        fi

        local backoff_delay jitter
        backoff_delay=$(( base_delay * (1 << (attempt - 1)) ))
        [ "$backoff_delay" -gt 120 ] && backoff_delay=120
        jitter=$(( $(portable_random) % (base_delay + 1) ))
        backoff_delay=$((backoff_delay + jitter))
        warn "Engine readiness blocked (${LAST_ENGINE_SELECTION_BLOCK_REASON}); retrying in ${backoff_delay}s..."
        notify_event "session_error" "engine_outage" "engine readiness blocked: ${LAST_ENGINE_SELECTION_BLOCK_REASON}; attempt $attempt/$max_attempts; retry_in=${backoff_delay}s" || true
        sleep "$backoff_delay"
        attempt=$((attempt + 1))
        ENGINE_CAPABILITIES_PROBED=false
    done
}

# Lock Management (atomic via mkdir)
new_lock_owner_token() {
    local random_part
    random_part="$(portable_random 2>/dev/null || echo 0)"
    printf '%s-%s-%s' "$$" "$(date +%s 2>/dev/null || echo 0)" "$random_part"
}

write_lock_owner_files() {
    local lock_dir="$1"
    local token="$2"
    local owner_tmp
    owner_tmp="$lock_dir/owner.tmp.$$"
    {
        printf 'pid=%s\n' "$$"
        printf 'token=%s\n' "$token"
        printf 'created_at=%s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)"
    } > "$owner_tmp" || return 1
    mv "$owner_tmp" "$lock_dir/owner" || return 1
    {
        printf '%s\n' "$$"
        date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown
        printf 'token=%s\n' "$token"
    } > "$LOCK_FILE"
}

lock_owner_pid() {
    local lock_dir="${LOCK_FILE}.d"
    local owner_file="$lock_dir/owner"
    local pid=""
    if [ -f "$owner_file" ]; then
        pid="$(sed -n 's/^pid=//p' "$owner_file" 2>/dev/null | head -n 1)"
    fi
    if [ -z "$pid" ] && [ -f "$LOCK_FILE" ]; then
        pid="$(head -n 1 "$LOCK_FILE" 2>/dev/null || echo "")"
    fi
    printf '%s' "$pid"
}

lock_owner_token_matches() {
    local lock_dir="${LOCK_FILE}.d"
    local owner_file="$lock_dir/owner"
    local token="${LOCK_OWNER_TOKEN:-}"
    [ -n "$token" ] || return 1
    if [ -f "$owner_file" ] && grep -Fxq "token=$token" "$owner_file" 2>/dev/null; then
        return 0
    fi
    if [ -f "$LOCK_FILE" ] && grep -Fxq "token=$token" "$LOCK_FILE" 2>/dev/null; then
        return 0
    fi
    return 1
}

acquire_lock() {
    mkdir -p "$(dirname "$LOCK_FILE")"
    # Use a lock directory for atomic acquisition (mkdir is atomic on POSIX)
    local lock_dir="${LOCK_FILE}.d"
    if mkdir "$lock_dir" 2>/dev/null; then
        LOCK_OWNER_TOKEN="$(new_lock_owner_token)"
        if ! write_lock_owner_files "$lock_dir" "$LOCK_OWNER_TOKEN"; then
            rm -f "$LOCK_FILE"
            rm -rf "$lock_dir" 2>/dev/null || true
            LOCK_OWNER_TOKEN=""
            err "Failed to write lock owner metadata."
            return 1
        fi
        LOCK_ACQUIRED="true"
        return 0
    fi
    # Lock dir exists — check if holder is still alive
    local holder_pid=""
    local owner_wait_attempt=0
    while [ "$owner_wait_attempt" -lt 3 ]; do
        holder_pid="$(lock_owner_pid)"
        [ -n "$holder_pid" ] && break
        sleep 1
        owner_wait_attempt=$((owner_wait_attempt + 1))
    done
    if [ -n "$holder_pid" ] && kill -0 "$holder_pid" 2>/dev/null; then
        err "Orchestrator already running with PID $holder_pid."
        log_reason_code "RB_LOCK_ALREADY_HELD" "pid $holder_pid active"
        return 1
    elif [ -n "$holder_pid" ]; then
        warn "Stale lock file found (PID $holder_pid no longer running). Reclaiming."
    else
        warn "Stale lock directory found without owner metadata. Reclaiming."
    fi
    # Reclaim stale lock
    rm -f "$LOCK_FILE"
    rm -rf "$lock_dir"
    if mkdir "$lock_dir" 2>/dev/null; then
        LOCK_OWNER_TOKEN="$(new_lock_owner_token)"
        if ! write_lock_owner_files "$lock_dir" "$LOCK_OWNER_TOKEN"; then
            rm -f "$LOCK_FILE"
            rm -rf "$lock_dir" 2>/dev/null || true
            LOCK_OWNER_TOKEN=""
            err "Failed to write lock owner metadata after stale reclaim."
            return 1
        fi
        LOCK_ACQUIRED="true"
        return 0
    fi
    err "Failed to acquire lock after stale reclaim attempt."
    return 1
}

release_lock() {
    if ! is_true "$LOCK_ACQUIRED"; then
        return 0
    fi
    if ! lock_owner_token_matches; then
        warn "Lock release skipped: current process does not own $(path_for_display "$LOCK_FILE")."
        LOCK_ACQUIRED="false"
        LOCK_OWNER_TOKEN=""
        return 0
    fi
    rm -f "$LOCK_FILE"
    rm -rf "${LOCK_FILE}.d" 2>/dev/null || true
    LOCK_ACQUIRED="false"
    LOCK_OWNER_TOKEN=""
}

# Interrupt handling
register_managed_pid() {
    local pid="${1:-}"
    [ -n "$pid" ] || return 0
    RALPHIE_BG_PIDS+=("$pid")
}

unregister_managed_pid() {
    local pid="${1:-}"
    local registered
    local -a kept=()
    [ -n "$pid" ] || return 0
    for registered in "${RALPHIE_BG_PIDS[@]+"${RALPHIE_BG_PIDS[@]}"}"; do
        [ "$registered" = "$pid" ] && continue
        kept+=("$registered")
    done
    RALPHIE_BG_PIDS=("${kept[@]+"${kept[@]}"}")
}

terminate_process_tree() {
    local pid="${1:-}"
    local signal="${2:-TERM}"
    local child
    [ -n "$pid" ] || return 0
    [ "$pid" != "$$" ] || return 0

    if command -v pgrep >/dev/null 2>&1; then
        while IFS= read -r child; do
            [ -n "$child" ] || continue
            terminate_process_tree "$child" "$signal"
        done < <(pgrep -P "$pid" 2>/dev/null || true)
    fi

    kill "-$signal" "$pid" 2>/dev/null || true
}

cleanup_managed_processes() {
    if [ "${#RALPHIE_BG_PIDS[@]}" -gt 0 ]; then
        for pid in "${RALPHIE_BG_PIDS[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then
                terminate_process_tree "$pid" TERM
            fi
        done
        sleep 2
        for pid in "${RALPHIE_BG_PIDS[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then
                terminate_process_tree "$pid" KILL
            fi
        done
        RALPHIE_BG_PIDS=()
    fi
}

cleanup_resources() {
    if is_true "$RALPHIE_CLEANUP_IN_PROGRESS"; then
        return 0
    fi
    RALPHIE_CLEANUP_IN_PROGRESS="true"
    if is_true "$RALPHIE_CLEANUP_STATE_ENABLED"; then
        save_state 2>/dev/null || true
    fi
    cleanup_managed_processes
    release_lock
    RALPHIE_CLEANUP_IN_PROGRESS="false"
}

show_interrupt_menu() {
    local choice
    local output_state

    while true; do
        output_state="$(is_true "$ENGINE_OUTPUT_TO_STDOUT" && echo "on" || echo "off")"
        echo
        warn "Ctrl+C received."
        warn "Live engine output: ${output_state}"
        warn "Actions:"
        warn "  [r] resume (default)"
        warn "  [l] toggle live engine output"
        warn "  [p] persist state and pause"
        warn "  [q] immediate stop"
        warn "  [h] help"
        choice="$(prompt_read_line "Action [r/l/p/q/h]: " "r")"
        case "$(to_lower "$choice")" in
            r|"")
                info "Resuming..."
                return 0
                ;;
            l)
                if is_true "$ENGINE_OUTPUT_TO_STDOUT"; then
                    ENGINE_OUTPUT_TO_STDOUT="false"
                else
                    ENGINE_OUTPUT_TO_STDOUT="true"
                fi
                info "Live engine output is now $(is_true "$ENGINE_OUTPUT_TO_STDOUT" && echo enabled || echo suppressed)."
                save_state
                ;;
            p)
                info "Persisted state and paused."
                save_state
                cleanup_resources
                exit 0
                ;;
            q)
                warn "Immediate stop requested."
                cleanup_resources
                exit 130
                ;;
            h)
                warn "Live logs can be toggled here without restarting. Use 'p' to exit cleanly and resume later."
                ;;
            *)
                warn "Unknown option: $choice"
                ;;
        esac
    done
}

handle_interrupt() {
    if [ "$INTERRUPT_MENU_ACTIVE" = "true" ]; then
        warn "Second interrupt received. Exiting immediately."
        cleanup_resources
        exit 130
    fi
    INTERRUPT_MENU_ACTIVE="true"
    if ! is_tty_input_available; then
        warn "Interrupt received in non-interactive context."
        cleanup_resources
        exit 130
    fi
    cleanup_managed_processes
    show_interrupt_menu
    INTERRUPT_MENU_ACTIVE="false"
}

cleanup() {
    info "Received interrupt. Cleaning up..."
    cleanup_resources
    exit 143
}

install_cleanup_traps() {
    if is_true "$RALPHIE_TRAPS_INSTALLED"; then
        return 0
    fi
    trap handle_interrupt SIGINT
    trap cleanup SIGTERM
    trap cleanup_resources EXIT
    RALPHIE_TRAPS_INSTALLED="true"
}

# Unified Agent Run Function with Exponential Backoff Retries
get_timeout_command() {
    if command -v timeout >/dev/null 2>&1; then echo "timeout"; elif command -v gtimeout >/dev/null 2>&1; then echo "gtimeout"; fi
}

warn_timeout_binary_unavailable_if_needed() {
    if [ "$TIMEOUT_BINARY_WARNING_EMITTED" = "true" ]; then
        return 0
    fi
    if ! is_number "${COMMAND_TIMEOUT_SECONDS:-0}" || [ "${COMMAND_TIMEOUT_SECONDS:-0}" -le 0 ]; then
        return 0
    fi
    if [ -n "$(get_timeout_command)" ]; then
        return 0
    fi

    TIMEOUT_BINARY_WARNING_EMITTED="true"
    warn "COMMAND_TIMEOUT_SECONDS=${COMMAND_TIMEOUT_SECONDS} requested, but no timeout wrapper is installed."
    warn "Install GNU timeout via coreutils (macOS: 'brew install coreutils', Linux: 'apt/yum install coreutils')."
    warn "Ralphie will continue without hard command timeout limits."
}

file_size_bytes_safe() {
    local file="$1"
    if [ ! -f "$file" ]; then
        echo 0
        return 0
    fi
    wc -c < "$file" 2>/dev/null | tr -d ' ' || echo 0
}

aggregate_output_bytes() {
    local total=0
    local file bytes
    for file in "$@"; do
        [ -n "$file" ] || continue
        bytes="$(file_size_bytes_safe "$file")"
        if ! is_number "$bytes"; then
            bytes=0
        fi
        total=$((total + bytes))
    done
    echo "$total"
}

wait_for_process_with_idle_output_watchdog() {
    local pid="$1"
    local idle_timeout="${2:-0}"
    local label="${3:-process}"
    shift 3 || true
    local -a watch_files=("$@")
    local now
    local last_progress
    local observed_bytes
    local previous_bytes

    if ! is_number "$idle_timeout" || [ "$idle_timeout" -le 0 ]; then
        wait "$pid"
        return $?
    fi

    previous_bytes="$(aggregate_output_bytes "${watch_files[@]+"${watch_files[@]}"}")"
    last_progress="$(date +%s 2>/dev/null || echo 0)"
    is_number "$last_progress" || last_progress=0

    while kill -0 "$pid" 2>/dev/null; do
        sleep 1
        observed_bytes="$(aggregate_output_bytes "${watch_files[@]+"${watch_files[@]}"}")"
        if is_number "$observed_bytes" && [ "$observed_bytes" -gt "$previous_bytes" ]; then
            previous_bytes="$observed_bytes"
            last_progress="$(date +%s 2>/dev/null || echo 0)"
            is_number "$last_progress" || last_progress=0
            continue
        fi

        now="$(date +%s 2>/dev/null || echo 0)"
        is_number "$now" || now=0
        if [ "$last_progress" -gt 0 ] && [ "$now" -gt 0 ] && [ $((now - last_progress)) -ge "$idle_timeout" ]; then
            warn "Idle-output watchdog tripped for ${label}: no new output for ${idle_timeout}s. Recycling process."
            log_reason_code "RB_IDLE_OUTPUT_WATCHDOG" "idle output watchdog tripped for ${label} (${idle_timeout}s without new output)"
            terminate_process_tree "$pid" TERM
            sleep 2
            terminate_process_tree "$pid" KILL
            wait "$pid" 2>/dev/null || true
            return 124
        fi
    done

    wait "$pid"
    return $?
}

run_agent_with_prompt() {
    local prompt_file="$1"
    local log_file="$2"
    local output_file="$3"
    local yolo_effective="$4"
    local attempt_no="${5:-1}"
    local timeout_cmd=""
    local idle_output_timeout="${ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS:-0}"
    local exit_code=0
    local -a engine_args=()
    local -a codex_prefix=()
    local -a yolo_prefix=()

    if [ ! -f "$prompt_file" ]; then
        err "Prompt file not found: $prompt_file"
        return 2
    fi
    if [ -z "${ACTIVE_CMD:-}" ] || ! command -v "$ACTIVE_CMD" >/dev/null 2>&1; then
        err "Active engine command unavailable: ${ACTIVE_CMD:-<unset>}"
        return 2
    fi
    if [ "$ACTIVE_ENGINE" = "codex" ] && [ "$CODEX_HEALTHY" != "true" ]; then
        err "Selected engine 'codex' is currently marked unhealthy: ${CODEX_CAP_NOTE:-missing required capability state}"
        return 2
    fi
    if [ "$ACTIVE_ENGINE" = "claude" ] && [ "$CLAUDE_HEALTHY" != "true" ]; then
        err "Selected engine 'claude' is currently marked unhealthy: ${CLAUDE_CAP_NOTE:-missing required capability state}"
        return 2
    fi

    if [ "$COMMAND_TIMEOUT_SECONDS" -gt 0 ]; then
        timeout_cmd="$(get_timeout_command)"
        warn_timeout_binary_unavailable_if_needed
    fi
    if ! is_number "$idle_output_timeout" || [ "$idle_output_timeout" -lt 0 ]; then
        idle_output_timeout="$DEFAULT_ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS"
    fi

    probe_engine_capabilities

    if [ "$ACTIVE_ENGINE" = "codex" ]; then
        if ! is_true "$CODEX_CAP_OUTPUT_LAST_MESSAGE"; then
            err "Codex capability missing: --output-last-message is required."
            return 2
        fi

        if [ -n "$CODEX_ENDPOINT" ]; then
            codex_prefix=("env" "OPENAI_BASE_URL=$CODEX_ENDPOINT")
        fi

        engine_args=("$ACTIVE_CMD" "exec")
        [ -n "${CODEX_MODEL:-}" ] && engine_args+=("--model" "$CODEX_MODEL")
        if [ -n "$CODEX_THINKING_OVERRIDE" ]; then
            engine_args+=("-c" "model_reasoning_effort=\"$CODEX_THINKING_OVERRIDE\"")
        fi
        if is_true "$CODEX_USE_RESPONSES_SCHEMA"; then
            if [ -n "$CODEX_RESPONSES_SCHEMA_FILE" ] && [ -f "$CODEX_RESPONSES_SCHEMA_FILE" ]; then
                engine_args+=("--output-schema" "$CODEX_RESPONSES_SCHEMA_FILE")
            else
                warn "CODEX_USE_RESPONSES_SCHEMA is enabled but CODEX_RESPONSES_SCHEMA_FILE is missing; continuing without --output-schema."
            fi
        fi

        if is_true "$yolo_effective" && is_true "$CODEX_CAP_YOLO_FLAG"; then
            engine_args+=("--dangerously-bypass-approvals-and-sandbox")
        fi
    else
        if ! is_true "$CLAUDE_CAP_PRINT"; then
            err "Claude capability missing: print mode is required."
            return 2
        fi

        engine_args=("$ACTIVE_CMD" "-p")
        [ -n "${CLAUDE_MODEL:-}" ] && engine_args+=("--model" "$CLAUDE_MODEL")
        case "$CLAUDE_THINKING_OVERRIDE" in
            high|xhigh)
                engine_args+=("--settings" '{"alwaysThinkingEnabled":true}')
                ;;
            none|off|low)
                engine_args+=("--settings" '{"alwaysThinkingEnabled":false}')
                ;;
            medium|"")
                :
                ;;
            *)
                :
                ;;
        esac
        if [ -n "$CLAUDE_ENDPOINT" ]; then
            yolo_prefix=("env" "ANTHROPIC_BASE_URL=$CLAUDE_ENDPOINT")
        fi

        if is_true "$yolo_effective"; then
            [ -n "$CLAUDE_CAP_YOLO_FLAG" ] && engine_args+=("$CLAUDE_CAP_YOLO_FLAG")
            if [ "${#yolo_prefix[@]}" -eq 0 ]; then
                yolo_prefix=("env" "IS_SANDBOX=1")
            else
                yolo_prefix+=("IS_SANDBOX=1")
            fi
        fi
    fi

    local attempt=1
    local max_run_attempts="${RUN_AGENT_MAX_ATTEMPTS}"
    local retry_delay="${RUN_AGENT_RETRY_DELAY_SECONDS}"
    if ! is_number "$max_run_attempts" || [ "$max_run_attempts" -lt 1 ]; then
        max_run_attempts=3
    fi
    if ! is_number "$retry_delay" || [ "$retry_delay" -lt 0 ]; then
        retry_delay=5
    fi

    while [ "$attempt" -le "$max_run_attempts" ]; do
        info "Dispatching ${ACTIVE_ENGINE} for attempt ${attempt}/${max_run_attempts} (phase attempt ${attempt_no}) with prompt $(path_for_display "$prompt_file")."
        if [ "$ACTIVE_ENGINE" = "codex" ]; then
            if [ -n "$timeout_cmd" ]; then
                if is_true "$ENGINE_OUTPUT_TO_STDOUT"; then
                    (
                        "${codex_prefix[@]+"${codex_prefix[@]}"}" "$timeout_cmd" "$COMMAND_TIMEOUT_SECONDS" "${engine_args[@]}" - --output-last-message "$output_file" 2>&1 < "$prompt_file" | stream_engine_output "$log_file"
                    ) &
                else
                    (
                        "${codex_prefix[@]+"${codex_prefix[@]}"}" "$timeout_cmd" "$COMMAND_TIMEOUT_SECONDS" "${engine_args[@]}" - --output-last-message "$output_file" 2>&1 < "$prompt_file" | stream_engine_output "$log_file" "" false
                    ) &
                fi
            else
                if is_true "$ENGINE_OUTPUT_TO_STDOUT"; then
                    (
                        "${codex_prefix[@]+"${codex_prefix[@]}"}" "${engine_args[@]}" - --output-last-message "$output_file" 2>&1 < "$prompt_file" | stream_engine_output "$log_file"
                    ) &
                else
                    (
                        "${codex_prefix[@]+"${codex_prefix[@]}"}" "${engine_args[@]}" - --output-last-message "$output_file" 2>&1 < "$prompt_file" | stream_engine_output "$log_file" "" false
                    ) &
                fi
            fi
        else
            if [ -n "$timeout_cmd" ]; then
                if is_true "$ENGINE_OUTPUT_TO_STDOUT"; then
                    (
                        "$timeout_cmd" "$COMMAND_TIMEOUT_SECONDS" "${yolo_prefix[@]+"${yolo_prefix[@]}"}" "${engine_args[@]}" - 2>>"$log_file" < "$prompt_file" | stream_engine_output "$log_file" "$output_file"
                    ) &
                else
                    (
                        "$timeout_cmd" "$COMMAND_TIMEOUT_SECONDS" "${yolo_prefix[@]+"${yolo_prefix[@]}"}" "${engine_args[@]}" - 2>>"$log_file" < "$prompt_file" | stream_engine_output "$log_file" "$output_file" false
                    ) &
                fi
            else
                if is_true "$ENGINE_OUTPUT_TO_STDOUT"; then
                    (
                        "${yolo_prefix[@]+"${yolo_prefix[@]}"}" "${engine_args[@]}" - 2>>"$log_file" < "$prompt_file" | stream_engine_output "$log_file" "$output_file"
                    ) &
                else
                    (
                        "${yolo_prefix[@]+"${yolo_prefix[@]}"}" "${engine_args[@]}" - 2>>"$log_file" < "$prompt_file" | stream_engine_output "$log_file" "$output_file" false
                    ) &
                fi
            fi
        fi
        local agent_pid=$!
        register_managed_pid "$agent_pid"
        if wait_for_process_with_idle_output_watchdog "$agent_pid" "$idle_output_timeout" "${ACTIVE_ENGINE} attempt ${attempt}/${max_run_attempts}" "$log_file" "$output_file"; then
            exit_code=0
        else
            exit_code=$?
        fi
        unregister_managed_pid "$agent_pid"
        if [ "$exit_code" -eq 0 ]; then
            charge_session_budget "$(estimate_run_tokens "$prompt_file" "$log_file" "$output_file")"
            if ! enforce_session_budget "agent attempt"; then
                return 1
            fi
            break
        fi
        charge_session_budget "$(estimate_run_tokens "$prompt_file" "$log_file" "$output_file")"
        if ! enforce_session_budget "agent attempt"; then
            return 1
        fi

        local hiccup_detected=false
        local permanent_failure=false
        if grep -qiE "backend error|token error|timeout|connection refused|overloaded|rate.?limit|503|502|429|ECONNRESET|ETIMEDOUT" "$log_file" 2>/dev/null; then
            hiccup_detected=true
        elif [ "$exit_code" -eq 124 ] || [ "$exit_code" -eq 137 ] || [ "$exit_code" -eq 143 ]; then
            # 124=timeout, 137=SIGKILL, 143=SIGTERM
            hiccup_detected=true
        elif [ "$exit_code" -ne 0 ]; then
            # Check for permanent failures that should NOT be retried
            if grep -qiE "invalid.*api.?key|authentication.*failed|permission.*denied|model.*not.*found|insufficient.*quota" "$log_file" 2>/dev/null; then
                permanent_failure=true
            else
                # Default: treat unknown non-zero exits as transient (agent crash, OOM, etc.)
                hiccup_detected=true
            fi
        fi

        # If the engine command itself disappeared, mark unhealthy so the next
        # ensure_engines_ready call at the loop boundary can detect and switch.
        if ! is_true "$permanent_failure" && is_true "$hiccup_detected"; then
            if ! command -v "$ACTIVE_CMD" >/dev/null 2>&1; then
                warn "Engine command '$ACTIVE_CMD' no longer available; marking $ACTIVE_ENGINE unhealthy."
                if [ "$ACTIVE_ENGINE" = "codex" ]; then
                    CODEX_HEALTHY="false"
                    CODEX_CAP_NOTE="command disappeared mid-session"
                    CODEX_SMOKE_PASS="false"
                else
                    CLAUDE_HEALTHY="false"
                    CLAUDE_CAP_NOTE="command disappeared mid-session"
                    CLAUDE_SMOKE_PASS="false"
                fi
                ENGINE_CAPABILITIES_PROBED=false
            fi
        fi

        if is_true "$permanent_failure"; then
            warn "Permanent failure detected on attempt $attempt/$max_run_attempts. Not retrying."
            break
        fi

        if is_true "$hiccup_detected" && [ "$attempt" -lt "$max_run_attempts" ]; then
            # Exponential backoff with jitter: base_delay * 2^(attempt-1) + random(0..base_delay)
            local backoff_delay jitter
            backoff_delay=$((retry_delay * (1 << (attempt - 1))))
            # Cap at 120 seconds
            [ "$backoff_delay" -gt 120 ] && backoff_delay=120
            jitter=$(( $(portable_random) % (retry_delay + 1) ))
            backoff_delay=$((backoff_delay + jitter))
            if is_true "$RUN_AGENT_RETRY_VERBOSE"; then
                warn "Inference hiccup detected (exit=$exit_code) on attempt $attempt/$max_run_attempts. Retrying in ${backoff_delay}s..."
            fi
            sleep "$backoff_delay"
            attempt=$((attempt + 1))
            continue
        fi
        break
    done

    if [ "$exit_code" -ne 0 ]; then
        log_reason_code "RB_RUN_AGENT_RETRY_EXHAUSTED" "run_agent exceeded ${max_run_attempts} attempts for $(path_for_display "$prompt_file") with last_exit=$exit_code"
    fi

    return "$exit_code"
}

consensus_reviewer_persona() {
    local stage="${1:-plan}"
    local reviewer_index="${2:-1}"
    local normalized_index

    is_number "$reviewer_index" || reviewer_index=1
    normalized_index=$(( (reviewer_index - 1) % 6 ))
    if [ "$normalized_index" -lt 0 ]; then
        normalized_index=0
    fi

    case "$normalized_index" in
        0) echo "Architect: validate scope integrity, assumptions, and future maintainability for ${stage}." ;;
        1) echo "Skeptic: challenge edge cases, hidden risks, and silent failure modes in ${stage}." ;;
        2) echo "Execution Reviewer: verify concrete evidence and artifact completeness from this attempt." ;;
        3) echo "Safety Reviewer: enforce policy compliance, guardrails, and regression risk containment." ;;
        4) echo "Operations Reviewer: focus on operational impact, deployment readiness, and reversibility." ;;
        5) echo "Quality Reviewer: prioritize signal quality, confidence, and decision consistency." ;;
    esac
}

run_swarm_reviewer() {
    local reviewer_index="$1"
    local prompt_file="$2"
    local log_file="$3"
    local output_file="$4"
    local status_file="$5"
    local primary_cmd="$6"
    local fallback_cmd="$7"

    local -a candidate_cmds=("$primary_cmd")
    [ -n "$fallback_cmd" ] && [ "$fallback_cmd" != "$primary_cmd" ] && candidate_cmds+=("$fallback_cmd")

    rm -f "$status_file"
    local attempt_cmd
    local attempt_exit=1
    local used_cmd="${primary_cmd}"
    local invalid_reason=""
    local validation_mode="consensus"
    ACTIVE_ENGINE="unknown"
    ACTIVE_CMD=""

    if [ "$reviewer_index" = "handoff" ]; then
        validation_mode="handoff"
    fi

    for attempt_cmd in "${candidate_cmds[@]}"; do
        [ -n "$attempt_cmd" ] || continue
        if [ "$attempt_cmd" = "$CODEX_CMD" ] && [ "$CODEX_HEALTHY" != "true" ]; then
            continue
        fi
        if [ "$attempt_cmd" = "$CLAUDE_CMD" ] && [ "$CLAUDE_HEALTHY" != "true" ]; then
            continue
        fi
        command -v "$attempt_cmd" >/dev/null 2>&1 || continue

        if [ "$attempt_cmd" = "$CODEX_CMD" ]; then
            ACTIVE_ENGINE="codex"
        elif [ "$attempt_cmd" = "$CLAUDE_CMD" ]; then
            ACTIVE_ENGINE="claude"
        else
            # Guard against custom command aliases unexpectedly routing to the
            # wrong engine mode.
            warn "Reviewer command '$attempt_cmd' did not match configured engines; skipping."
            continue
        fi
        ACTIVE_CMD="$attempt_cmd"
        used_cmd="$attempt_cmd"

        rm -f "$output_file"
        if run_agent_with_prompt "$prompt_file" "$log_file" "$output_file" "false" "$reviewer_index"; then
            invalid_reason="$(review_output_invalid_reason "$output_file" "$validation_mode")"
            if [ -z "$invalid_reason" ]; then
                attempt_exit=0
                break
            fi
            local raw_invalid_output=""
            raw_invalid_output="${output_file}.invalid.${ACTIVE_ENGINE}.${reviewer_index}"
            mv "$output_file" "$raw_invalid_output" 2>/dev/null || raw_invalid_output=""
            write_invalid_reviewer_output_placeholder "$output_file" "$invalid_reason" "$raw_invalid_output"
            warn "Reviewer $reviewer_index output from ${ACTIVE_ENGINE:-unknown} was rejected: $invalid_reason"
            attempt_exit=1
            continue
        fi
    done

    {
        echo "reviewer_index=$reviewer_index"
        echo "engine=${ACTIVE_ENGINE:-unknown}"
        echo "command=$used_cmd"
        if [ "$attempt_exit" -eq 0 ]; then
            echo "status=success"
            echo "exit_code=0"
        else
            echo "status=failure"
            echo "exit_code=1"
            if [ -n "$invalid_reason" ]; then
                echo "failure_reason=$(sanitize_text_for_log "$invalid_reason")"
            fi
        fi
    } > "$status_file"
    return "$attempt_exit"
}

build_consensus_evidence_context() {
    local phase="$1"
    local attempt="$2"
    local output_file="$3"
    local log_file="$4"
    local handoff_output_file="$5"
    local handoff_status_file="$6"
    local manifest_before_file="$7"
    local manifest_after_file="$8"
    local delta_preview="$9"
    local warning_text="${10}"
    local previous_output="${11}"
    local prior_output_display="none"

    [ -f "$previous_output" ] && prior_output_display="$(path_for_display "$previous_output")"

    {
        echo "Current phase artifacts:"
        echo "- phase: $phase"
        echo "- attempt: $attempt"
        echo "- completion output: $(path_for_display "$output_file")"
        echo "- execution log: $(path_for_display "$log_file")"
        echo "- handoff status: $(path_for_display "$handoff_status_file")"
        echo "- handoff output: $(path_for_display "$handoff_output_file")"
        echo "- previous completion output: $prior_output_display"
        echo "- manifest before: $(path_for_display "$manifest_before_file")"
        echo "- manifest after: $(path_for_display "$manifest_after_file")"
        echo ""
        echo "Worktree delta preview:"
        if [ -n "$delta_preview" ]; then
            while IFS= read -r delta_line; do
                [ -n "$delta_line" ] || continue
                echo "- $delta_line"
            done <<< "$delta_preview"
        else
            echo "- no visible delta preview"
        fi
        echo ""
        echo "Phase warnings:"
        if [ -n "$warning_text" ]; then
            printf '%s\n' "$warning_text" | sed 's/^/- /'
        else
            echo "- none"
        fi
        echo ""
        echo "Completion output snippet:"
        safe_print_file_head "$output_file" 120
        echo ""
        echo "Execution log tail:"
        safe_print_file_tail "$log_file" 40
        echo ""
        echo "Handoff validator status:"
        if [ -f "$handoff_status_file" ]; then
            sed -n '1,20p' "$handoff_status_file"
        else
            echo "- not available"
        fi
        echo ""
        echo "Handoff validator output snippet:"
        safe_print_file_head "$handoff_output_file" 60
    }
}

run_swarm_consensus() {
    local stage="$1"
    local history_context="${2:-}"
    local evidence_context="${3:-}"
    local count
    local parallel
    count="$(get_reviewer_count)"
    parallel="$(get_parallel_reviewer_count)"
    local base_stage="${stage%-gate}"
    CONSENSUS_NO_ENGINES=false
    local default_next_phase
    local next_phase_vote_plan=0
    local next_phase_vote_build=0
    local next_phase_vote_test=0
    local next_phase_vote_refactor=0
    local next_phase_vote_lint=0
    local next_phase_vote_document=0
    local next_phase_vote_done=0
    local total_next_votes=0

    # Preserve global engine state before swarm (reviewers run in subshells
    # but run_swarm_reviewer also modifies globals in the parent fallback path)
    local saved_engine="$ACTIVE_ENGINE"
    local saved_cmd="$ACTIVE_CMD"

    default_next_phase="$(phase_default_next "$base_stage")"
    info "Running deep consensus swarm for '$stage'..."
    local consensus_dir="$CONSENSUS_DIR/$stage/$SESSION_ID"
    LAST_CONSENSUS_DIR="$consensus_dir"
    LAST_CONSENSUS_SUMMARY=""
    LAST_CONSENSUS_NEXT_PHASE="$default_next_phase"
    LAST_CONSENSUS_NEXT_PHASE_REASON="insufficient consensus responses"
    LAST_CONSENSUS_RESPONDED_VOTES=0
    LAST_CONSENSUS_FAILURE_KIND="none"
    LAST_CONSENSUS_FAILURE_REASON=""
    mkdir -p "$consensus_dir"

    local -a prompts=() logs=() outputs=() status_files=()
    local -a primary_cmds=() fallback_cmds=() summary_lines=()
    local claude_available=false
    local codex_available=false
    local reviewer_engine_request="${ENGINE_SELECTION_REQUESTED:-$DEFAULT_ENGINE}"
    local reviewer_engine_policy="mixed:auto"
    local pinned_reviewer_cmd=""
    if [ "$CODEX_HEALTHY" = "true" ] && command -v "$CODEX_CMD" >/dev/null 2>&1; then
        codex_available=true
    fi
    if [ "$CLAUDE_HEALTHY" = "true" ] && command -v "$CLAUDE_CMD" >/dev/null 2>&1; then
        claude_available=true
    fi
    reviewer_engine_request="$(to_lower "$reviewer_engine_request")"
    if [ "$reviewer_engine_request" = "codex" ] || [ "$reviewer_engine_request" = "claude" ]; then
        reviewer_engine_policy="pinned:${reviewer_engine_request}"
        if [ "$reviewer_engine_request" = "codex" ] && [ "$codex_available" = "true" ]; then
            pinned_reviewer_cmd="$CODEX_CMD"
        elif [ "$reviewer_engine_request" = "claude" ] && [ "$claude_available" = "true" ]; then
            pinned_reviewer_cmd="$CLAUDE_CMD"
        else
            warn "Consensus reviewers are pinned to '$reviewer_engine_request', but that engine is unavailable."
            LAST_CONSENSUS_SCORE=0
            LAST_CONSENSUS_PASS=false
            LAST_CONSENSUS_NEXT_PHASE="$default_next_phase"
            LAST_CONSENSUS_NEXT_PHASE_REASON="pinned reviewer engine unavailable"
            LAST_CONSENSUS_RESPONDED_VOTES=0
            LAST_CONSENSUS_FAILURE_KIND="infra"
            LAST_CONSENSUS_FAILURE_REASON="pinned reviewer engine '$reviewer_engine_request' unavailable"
            CONSENSUS_NO_ENGINES=true
            ACTIVE_ENGINE="$saved_engine"
            ACTIVE_CMD="$saved_cmd"
            return 1
        fi
    fi
    info "Consensus reviewer policy: $reviewer_engine_policy"
    if [ "$claude_available" = false ] && [ "$codex_available" = false ]; then
        warn "No healthy reviewer engines available for consensus."
        LAST_CONSENSUS_SCORE=0
        LAST_CONSENSUS_PASS=false
        LAST_CONSENSUS_NEXT_PHASE="$default_next_phase"
        LAST_CONSENSUS_NEXT_PHASE_REASON="no healthy reviewer engines available"
        LAST_CONSENSUS_RESPONDED_VOTES=0
        LAST_CONSENSUS_FAILURE_KIND="infra"
        LAST_CONSENSUS_FAILURE_REASON="no healthy reviewer engines available"
        CONSENSUS_NO_ENGINES=true
        ACTIVE_ENGINE="$saved_engine"
        ACTIVE_CMD="$saved_cmd"
        return 1
    fi

    local i
    for i in $(seq 1 "$count"); do
        local primary_cmd="$CLAUDE_CMD"
        local fallback_cmd=""

        if [ -n "$pinned_reviewer_cmd" ]; then
            # Explicit engine pinning means reviewer personas must stay on the selected engine.
            primary_cmd="$pinned_reviewer_cmd"
            fallback_cmd=""
        else
            if [ "$claude_available" = false ] && [ "$codex_available" = true ]; then
                primary_cmd="$CODEX_CMD"
            elif [ "$claude_available" = true ] && [ "$codex_available" = true ] && [ $(( (i - 1) % 2 )) -eq 0 ]; then
                primary_cmd="$CODEX_CMD"
            fi

            if [ "$primary_cmd" = "$CODEX_CMD" ] && [ "$claude_available" = true ]; then
                fallback_cmd="$CLAUDE_CMD"
            fi
            if [ "$primary_cmd" = "$CLAUDE_CMD" ] && [ "$codex_available" = true ]; then
                fallback_cmd="$CODEX_CMD"
            fi
        fi

        prompts+=("$consensus_dir/reviewer_${i}_prompt.md")
        logs+=("$consensus_dir/reviewer_${i}.log")
        outputs+=("$consensus_dir/reviewer_${i}.out")
        status_files+=("$consensus_dir/reviewer_${i}.status")
        primary_cmds+=("$primary_cmd")
        fallback_cmds+=("$fallback_cmd")

        {
            echo "# Consensus Review: $stage"
            consensus_prompt_for_stage "$base_stage" "$history_context" "$evidence_context" "$(consensus_reviewer_persona "$base_stage" "$i")"
        } > "${prompts[$((i - 1))]}"
    done

    local active=0
    for i in $(seq 0 $((count - 1))); do
        (
            run_swarm_reviewer \
                "$((i + 1))" \
                "${prompts[$i]}" \
                "${logs[$i]}" \
                "${outputs[$i]}" \
                "${status_files[$i]}" \
                "${primary_cmds[$i]}" \
                "${fallback_cmds[$i]}"
        ) &
        register_managed_pid "$!"
        active=$((active + 1))
        if [ "$active" -ge "$parallel" ] || [ "$i" -eq $((count - 1)) ]; then
            # wait -n requires Bash 4.3+; use portable fallback
            if [ "${BASH_VERSINFO[0]:-3}" -gt 4 ] || { [ "${BASH_VERSINFO[0]:-3}" -eq 4 ] && [ "${BASH_VERSINFO[1]:-0}" -ge 3 ]; }; then
                wait -n 2>/dev/null || true
            else
                # Portable: poll only swarm PIDs until at least one finishes
                while true; do
                    local __alive=0
                    for __pid in "${RALPHIE_BG_PIDS[@]+"${RALPHIE_BG_PIDS[@]}"}"; do
                        kill -0 "$__pid" 2>/dev/null && __alive=$((__alive + 1))
                    done
                    [ "$__alive" -lt "$active" ] && break
                    sleep 0.2 2>/dev/null || sleep 1
                done
            fi
            active=$((active - 1))
        fi
    done
    # Wait for all reviewers with a safety timeout to prevent infinite hangs
    local swarm_timeout="${SWARM_CONSENSUS_TIMEOUT:-600}"
    is_number "$swarm_timeout" || swarm_timeout=600
    local swarm_start swarm_elapsed
    swarm_start="$(date +%s)"
    local swarm_timed_out=false
    while true; do
        local running_jobs=0
        local __active_jobs=()
            for __pid in "${RALPHIE_BG_PIDS[@]+"${RALPHIE_BG_PIDS[@]}"}"; do
                if kill -0 "$__pid" 2>/dev/null; then
                    __active_jobs+=("$__pid")
                    running_jobs=$((running_jobs + 1))
                fi
            done
            RALPHIE_BG_PIDS=("${__active_jobs[@]+"${__active_jobs[@]}"}")
            [ "${running_jobs:-0}" -eq 0 ] && break
            swarm_elapsed=$(( $(date +%s) - swarm_start ))
            if [ "$swarm_elapsed" -ge "$swarm_timeout" ]; then
                warn "Swarm consensus timeout after ${swarm_timeout}s. Killing hung reviewers."
                swarm_timed_out=true
                for pid in "${RALPHIE_BG_PIDS[@]+"${RALPHIE_BG_PIDS[@]}"}"; do
                    terminate_process_tree "$pid" TERM
                done
                sleep 2
                for pid in "${RALPHIE_BG_PIDS[@]+"${RALPHIE_BG_PIDS[@]}"}"; do
                    terminate_process_tree "$pid" KILL
                done
                break
            fi
        sleep 1
    done
    wait 2>/dev/null || true
    # Clean PID registry to prevent stale accumulation
    RALPHIE_BG_PIDS=()
    if [ "$swarm_timed_out" = true ]; then
        log_reason_code "RB_SWARM_TIMEOUT" "consensus reviewers exceeded timeout (${swarm_timeout}s) for stage $stage"
        LAST_CONSENSUS_FAILURE_KIND="infra"
        LAST_CONSENSUS_FAILURE_REASON="consensus swarm timeout after ${swarm_timeout}s"
    fi

    local total_score=0
    local go_votes=0
    local responded_votes=0
    local required_votes=$((count / 2 + 1))
    local avg_score=0
    local next_phase_vote_reason=""

    local idx=0
    local status_file status engine failure_reason verdict score verdict_gaps next_phase next_phase_reason
    local recommended_next="$default_next_phase"
    local highest_next_votes=0
    local candidate_votes=0
    for ofile in "${outputs[@]}"; do
        status="failure"
        engine="unknown"
        failure_reason=""
        verdict="HOLD"
        score="0"
        verdict_gaps="no explicit gaps"
        next_phase="$default_next_phase"
        next_phase_reason=""

        status_file="${status_files[$idx]}"
        if [ -f "$status_file" ]; then
            status="$(grep -E "^status=" "$status_file" | head -n 1 | cut -d'=' -f2-)"
            engine="$(grep -E "^engine=" "$status_file" | head -n 1 | cut -d'=' -f2-)"
            engine="$(sanitize_text_for_log "$engine" | cut -c 1-40)"
            failure_reason="$(grep -E "^failure_reason=" "$status_file" | head -n 1 | cut -d'=' -f2-)"
            failure_reason="$(sanitize_text_for_log "$failure_reason" | cut -c 1-180)"
            [ "$status" = "success" ] || status="failure"
        fi

        if [ "$status" = "success" ] && [ -f "$ofile" ]; then
            score="$(extract_review_score "$ofile")"
            verdict="$(extract_review_verdict "$ofile")"

            next_phase="$(extract_xml_value "$ofile" "next_phase" "$default_next_phase")"
            next_phase="$(normalize_next_phase_recommendation "$next_phase" "$base_stage" "$default_next_phase")"
            next_phase_reason="$(extract_xml_value "$ofile" "next_phase_reason" "")"
            verdict_gaps="$(extract_review_gaps "$ofile" 180)"
            next_phase_reason="$(sanitize_text_for_log "$next_phase_reason")"
            [ -n "$next_phase_reason" ] || next_phase_reason="no explicit phase-routing rationale"
        else
            if [ -n "$failure_reason" ]; then
                verdict_gaps="reviewer failure: $failure_reason"
                next_phase_reason="reviewer failure: $failure_reason"
            else
                verdict_gaps="no valid output artifact"
                next_phase_reason="no valid output artifact"
            fi
        fi

        [ "$status" = "success" ] && responded_votes=$((responded_votes + 1))
        [ "$status" = "success" ] && total_score=$((total_score + score))
        if [ "$status" = "success" ] && is_phase_or_done "$next_phase"; then
            total_next_votes=$((total_next_votes + 1))
            case "$next_phase" in
                plan) next_phase_vote_plan=$((next_phase_vote_plan + 1)) ;;
                build) next_phase_vote_build=$((next_phase_vote_build + 1)) ;;
                test) next_phase_vote_test=$((next_phase_vote_test + 1)) ;;
                refactor) next_phase_vote_refactor=$((next_phase_vote_refactor + 1)) ;;
                lint) next_phase_vote_lint=$((next_phase_vote_lint + 1)) ;;
                document) next_phase_vote_document=$((next_phase_vote_document + 1)) ;;
                done) next_phase_vote_done=$((next_phase_vote_done + 1)) ;;
            esac
            if [ -z "$next_phase_vote_reason" ] && [ -n "$next_phase_reason" ]; then
                next_phase_vote_reason="$next_phase_reason"
            fi
        fi

        [ "$status" = "success" ] && [ "$verdict" = "GO" ] && go_votes=$((go_votes + 1))
        summary_lines+=("reviewer_$((idx + 1)):engine=$engine status=$status score=$score verdict=$verdict next=$next_phase reason=$next_phase_reason gaps=$verdict_gaps")
        idx=$((idx + 1))
    done

    if [ "$responded_votes" -gt 0 ]; then
        avg_score=$((total_score / responded_votes))
    fi

    if [ "$total_next_votes" -gt 0 ]; then
        local -a vote_phases=("plan" "build" "test" "refactor" "lint" "document" "done")
        local -a vote_counts=(
            "$next_phase_vote_plan"
            "$next_phase_vote_build"
            "$next_phase_vote_test"
            "$next_phase_vote_refactor"
            "$next_phase_vote_lint"
            "$next_phase_vote_document"
            "$next_phase_vote_done"
        )
        local -a tied_phases=()
        local vote_index=0
        local tie_summary=""
        local tie_phase=""
        local tie_count=0

        highest_next_votes=0
        for vote_index in "${!vote_counts[@]}"; do
            candidate_votes="${vote_counts[$vote_index]}"
            if [ "$candidate_votes" -gt "$highest_next_votes" ]; then
                highest_next_votes="$candidate_votes"
            fi
        done

        for vote_index in "${!vote_counts[@]}"; do
            candidate_votes="${vote_counts[$vote_index]}"
            if [ "$candidate_votes" -eq "$highest_next_votes" ] && [ "$candidate_votes" -gt 0 ]; then
                tied_phases+=("${vote_phases[$vote_index]}")
            fi
        done

        tie_count="${#tied_phases[@]}"
        if [ "$tie_count" -eq 1 ]; then
            recommended_next="${tied_phases[0]}"
        elif [ "$tie_count" -gt 1 ]; then
            recommended_next="$default_next_phase"
            for tie_phase in "${tied_phases[@]}"; do
                tie_summary="${tie_summary}${tie_summary:+, }$tie_phase"
            done
            warn "Consensus next-phase vote tie ($tie_summary at ${highest_next_votes} votes each); defaulting to $default_next_phase."
            if [ -n "$next_phase_vote_reason" ]; then
                next_phase_vote_reason="$next_phase_vote_reason (tie: $tie_summary -> default $default_next_phase)"
            else
                next_phase_vote_reason="tie on next_phase votes ($tie_summary) -> defaulted to $default_next_phase"
            fi
        fi
    fi

    LAST_CONSENSUS_NEXT_PHASE="$recommended_next"
    [ -n "$next_phase_vote_reason" ] || next_phase_vote_reason="no explicit routing rationale"
    LAST_CONSENSUS_NEXT_PHASE_REASON="$next_phase_vote_reason"
    LAST_CONSENSUS_RESPONDED_VOTES="$responded_votes"
    LAST_CONSENSUS_SCORE="$avg_score"
    if [ "${#summary_lines[@]}" -gt 0 ]; then
        LAST_CONSENSUS_SUMMARY="$(printf '%s; ' "${summary_lines[@]}")"
    else
        LAST_CONSENSUS_SUMMARY=""
    fi
    if [ "$responded_votes" -ge "$required_votes" ] && [ "$go_votes" -ge "$required_votes" ] && [ "$avg_score" -ge "$CONSENSUS_SCORE_THRESHOLD" ]; then
        LAST_CONSENSUS_PASS=true
        LAST_CONSENSUS_FAILURE_KIND="none"
        LAST_CONSENSUS_FAILURE_REASON=""
        ACTIVE_ENGINE="$saved_engine"
        ACTIVE_CMD="$saved_cmd"
        return 0
    fi
    LAST_CONSENSUS_PASS=false
    if [ "$LAST_CONSENSUS_FAILURE_KIND" != "infra" ]; then
        if [ "$responded_votes" -lt "$required_votes" ]; then
            LAST_CONSENSUS_FAILURE_KIND="infra"
            LAST_CONSENSUS_FAILURE_REASON="insufficient reviewer responses ($responded_votes/$required_votes)"
        else
            LAST_CONSENSUS_FAILURE_KIND="quality"
            LAST_CONSENSUS_FAILURE_REASON="consensus HOLD (go_votes=$go_votes/$required_votes, avg_score=$avg_score, threshold=$CONSENSUS_SCORE_THRESHOLD)"
        fi
    fi
    ACTIVE_ENGINE="$saved_engine"
    ACTIVE_CMD="$saved_cmd"
    return 1
}

write_handoff_validation_prompt() {
    local phase="$1"
    local attempt="$2"
    local output_file="$3"
    local log_file="$4"
    local prompt_file="$5"
    local manifest_before_file="$6"
    local manifest_after_file="$7"
    local delta_preview="$8"
    local noop_policy="$9"
    local warning_text="${10}"
    local previous_output="${11}"

    local prior_output_display="none"
    [ -f "$previous_output" ] && prior_output_display="$(path_for_display "$previous_output")"

    {
        echo "# Handoff Validation Prompt"
        echo ""
        echo "You are the on-rail handoff validator."
        echo "Phase: $phase"
        echo "Attempt: $attempt"
        echo "Session: $SESSION_ID"
        echo "Iteration: $ITERATION_COUNT"
        echo "Handoff policy: $noop_policy"
        echo "Execution output: $(path_for_display "$output_file")"
        echo "Execution log: $(path_for_display "$log_file")"
        echo "Previous output: $prior_output_display"
        echo "Manifest before: $(path_for_display "$manifest_before_file")"
        echo "Manifest after: $(path_for_display "$manifest_after_file")"
        echo "Delta preview:"
        if [ -n "$delta_preview" ]; then
            while IFS= read -r delta_line; do
                echo "- $delta_line"
            done <<< "$delta_preview"
        else
            echo "- no visible delta preview"
        fi
        echo ""
        echo "Recent warnings:"
        if [ -n "$warning_text" ]; then
            printf '%s\n' "$warning_text" | sed 's/^/- /'
        else
            echo "- none"
        fi
        echo ""
        echo "Rules:"
        echo "- Confirm execution output indicates concrete artifact progress for this phase."
        echo "- Confirm handoff artifacts are coherent and transition intent is explicit."
        echo "- Confirm no policy blockers are hidden."
        echo "- Emit machine-readable signal:"
    echo "  <score>0-100</score>"
    echo "  <verdict>GO|HOLD</verdict>"
    echo "  <gaps>comma-separated blockers or none</gaps>"

    if [ -f "$previous_output" ]; then
        echo "Previous handoff output snippet:"
        safe_print_file_head "$previous_output" 40
    fi

    echo "Current execution output snippet:"
    safe_print_file_head "$output_file" 80

    echo "Current execution log tail:"
    safe_print_file_tail "$log_file" 40
    } > "$prompt_file"
}

read_handoff_review_output() {
    local output_file="$1"
    local score=0
    local verdict="HOLD"
    local gaps="no explicit gaps"

    LAST_HANDOFF_SCORE=0
    LAST_HANDOFF_VERDICT="HOLD"
    LAST_HANDOFF_GAPS="no explicit gaps"

    [ -f "$output_file" ] || return 0

    local invalid_reason
    invalid_reason="$(review_output_invalid_reason "$output_file" "handoff")"
    if [ -n "$invalid_reason" ]; then
        LAST_HANDOFF_GAPS="invalid reviewer output: $(sanitize_text_for_log "$invalid_reason" | cut -c 1-160)"
        return 0
    fi

    score="$(extract_review_score "$output_file")"
    verdict="$(extract_review_verdict "$output_file")"
    gaps="$(extract_review_gaps "$output_file" 180)"

    LAST_HANDOFF_SCORE="$score"
    LAST_HANDOFF_VERDICT="$verdict"
    LAST_HANDOFF_GAPS="$gaps"
}

run_handoff_validation() {
    local phase="$1"
    local prompt_file="$2"
    local log_file="$3"
    local output_file="$4"
    local status_file="$5"
    local primary_cmd="${6:-}"
    local fallback_cmd="${7:-}"

    if [ ! -f "$prompt_file" ]; then
        err "Handoff validation prompt missing: $prompt_file"
        return 1
    fi

    # Preserve engine state — run_swarm_reviewer mutates ACTIVE_ENGINE/ACTIVE_CMD
    local saved_engine="$ACTIVE_ENGINE"
    local saved_cmd="$ACTIVE_CMD"

    run_swarm_reviewer \
        "handoff" \
        "$prompt_file" \
        "$log_file" \
        "$output_file" \
        "$status_file" \
        "$primary_cmd" \
        "$fallback_cmd"
    read_handoff_review_output "$output_file"

    # Restore engine state
    ACTIVE_ENGINE="$saved_engine"
    ACTIVE_CMD="$saved_cmd"

    local status="failure"
    if [ -f "$status_file" ]; then
        status="$(grep -E "^status=" "$status_file" | head -n 1 | cut -d'=' -f2-)"
        [ "$status" = "success" ] || status="failure"
    fi

    if [ "$status" = "success" ] && is_number "$LAST_HANDOFF_SCORE" && [ "$LAST_HANDOFF_SCORE" -ge "$CONSENSUS_SCORE_THRESHOLD" ] && [ "$LAST_HANDOFF_VERDICT" = "GO" ]; then
        return 0
    fi

    log_reason_code "RB_PHASE_HANDOFF_VALIDATOR_HOLD" "Handoff validation failed for $phase (score=${LAST_HANDOFF_SCORE}, verdict=${LAST_HANDOFF_VERDICT})"
    return 1
}

path_relative_to_project() {
    local value="${1:-}"
    if [ -z "$value" ]; then
        echo ""
        return 0
    fi
    case "$value" in
        "$PROJECT_DIR"/*) echo "${value#"$PROJECT_DIR"/}" ;;
        *) echo "${value#./}" ;;
    esac
}

phase_manifest_file_size_and_mtime() {
    local path="$1"
    if [ ! -e "$path" ]; then
        echo "-1 -1"
        return 0
    fi
    if stat -f '%z %m' "$path" >/dev/null 2>&1; then
        stat -f '%z %m' "$path" 2>/dev/null || echo "-1 -1"
        return 0
    fi
    if stat -c '%s %Y' "$path" >/dev/null 2>&1; then
        stat -c '%s %Y' "$path" 2>/dev/null || echo "-1 -1"
        return 0
    fi
    echo "-1 -1"
}

phase_manifest_file_signature() {
    local rel_path="$1"
    local mode="$2"
    local abs_path="$PROJECT_DIR/$rel_path"
    local type="missing"
    local size="-1"
    local mtime="-1"
    local checksum=""
    local stat_data=""

    if [ -d "$abs_path" ]; then
        type="dir"
    elif [ -f "$abs_path" ]; then
        type="file"
    elif [ -e "$abs_path" ]; then
        type="other"
    fi

    stat_data="$(phase_manifest_file_size_and_mtime "$abs_path")"
    size="$(printf '%s' "$stat_data" | awk '{print $1}')"
    mtime="$(printf '%s' "$stat_data" | awk '{print $2}')"
    is_number "$size" || size="-1"
    is_number "$mtime" || mtime="-1"

    if [ "$mode" = "deep" ] && [ "$type" = "file" ]; then
        checksum="$(sha256_file_sum "$abs_path" 2>/dev/null || echo "unavailable")"
        printf 'type=%s,size=%s,mtime=%s,hash=%s' "$type" "$size" "$mtime" "$checksum"
        return 0
    fi
    printf 'type=%s,size=%s,mtime=%s' "$type" "$size" "$mtime"
}

phase_capture_worktree_manifest() {
    local manifest_file="$1"
    local mode
    local line
    local status_code
    local rel_path
    local target_path
    local signature

    [ -n "$manifest_file" ] || return 1
    : > "$manifest_file"

    if ! git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        return 1
    fi

    mode="$(normalize_phase_manifest_mode "$PHASE_MANIFEST_MODE")"
    {
        git -C "$PROJECT_DIR" -c core.quotePath=false status --porcelain=v1 --untracked-files=all -- . | \
        while IFS= read -r line; do
            [ -n "$line" ] || continue
            status_code="${line:0:2}"
            rel_path="${line:3}"
            target_path="$rel_path"
            if [[ "$rel_path" == *" -> "* ]]; then
                target_path="${rel_path##* -> }"
            fi
            target_path="$(path_relative_to_project "$target_path")"
            signature="$(phase_manifest_file_signature "$target_path" "$mode")"
            printf 'P %s %s\t%s\n' "$status_code" "$signature" "$target_path"
        done
    } | sort > "$manifest_file"
    return 0
}

phase_manifest_changed() {
    local before_file="$1"
    local after_file="$2"

    if [ ! -f "$before_file" ] || [ ! -f "$after_file" ]; then
        return 1
    fi

    if cmp -s "$before_file" "$after_file"; then
        return 1
    fi
    return 0
}

phase_manifest_extract_path_from_line() {
    local line="${1:-}"
    line="${line#$'\t'}"
    case "$line" in
        P\ *$'\t'*)
            printf '%s\n' "${line#*$'\t'}"
            ;;
        *)
            printf '%s\n' ""
            ;;
    esac
}

phase_manifest_changed_paths() {
    local before_file="$1"
    local after_file="$2"
    local line path

    if [ ! -f "$before_file" ] || [ ! -f "$after_file" ]; then
        return 0
    fi

    while IFS= read -r line; do
        path="$(phase_manifest_extract_path_from_line "$line")"
        [ -n "$path" ] && printf '%s\n' "$path"
    done < <(comm -3 "$before_file" "$after_file")
}

record_session_changed_paths_from_manifest() {
    local before_file="$1"
    local after_file="$2"
    local tmp_file

    mkdir -p "$(dirname "$SESSION_CHANGED_PATHS_FILE")"
    touch "$SESSION_CHANGED_PATHS_FILE"
    tmp_file="$(mktemp "$CONFIG_DIR/session-changed-paths.XXXXXX")" || return 1

    {
        cat "$SESSION_CHANGED_PATHS_FILE"
        phase_manifest_changed_paths "$before_file" "$after_file"
    } | sed '/^$/d' | sort -u > "$tmp_file"

    mv "$tmp_file" "$SESSION_CHANGED_PATHS_FILE"
    return 0
}

session_changed_paths_contains() {
    local rel_path="$1"
    [ -f "$SESSION_CHANGED_PATHS_FILE" ] || return 1
    grep -Fxq -- "$rel_path" "$SESSION_CHANGED_PATHS_FILE" 2>/dev/null
}

phase_noop_policy() {
    local phase="$1"
    case "$phase" in
        plan)
            echo "$PHASE_NOOP_POLICY_PLAN"
            ;;
        build)
            echo "$PHASE_NOOP_POLICY_BUILD"
            ;;
        test)
            if is_true "$STRICT_VALIDATION_NOOP"; then
                echo "hard"
            else
                echo "$PHASE_NOOP_POLICY_TEST"
            fi
            ;;
        refactor)
            echo "$PHASE_NOOP_POLICY_REFACTOR"
            ;;
        lint)
            if is_true "$STRICT_VALIDATION_NOOP"; then
                echo "hard"
            else
                echo "$PHASE_NOOP_POLICY_LINT"
            fi
            ;;
        document)
            echo "$PHASE_NOOP_POLICY_DOCUMENT"
            ;;
        *)
            echo "none"
            ;;
    esac
}

phase_manifest_delta_preview() {
    local before_file="$1"
    local after_file="$2"
    local lines_limit="${3:-8}"
    local emitted=0
    local line
    local label
    local content

    if [ ! -f "$before_file" ] || [ ! -f "$after_file" ]; then
        echo ""
        return 0
    fi

    while IFS= read -r line; do
        if [ "$emitted" -ge "$lines_limit" ]; then
            break
        fi
        if [ "${line:0:1}" = $'\t' ]; then
            label="after"
            content="${line:1}"
        else
            label="before"
            content="$line"
        fi
        printf '%s: %s\n' "$label" "$content"
        emitted=$((emitted + 1))
    done < <(comm -3 "$before_file" "$after_file")
}

git_has_local_changes() {
    if ! git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        return 1
    fi

    if ! git -C "$PROJECT_DIR" diff --quiet --ignore-submodules -- .; then
        return 0
    fi
    if ! git -C "$PROJECT_DIR" diff --cached --quiet --ignore-submodules -- .; then
        return 0
    fi
    if [ -n "$(git -C "$PROJECT_DIR" ls-files --others --exclude-standard -- . 2>/dev/null | head -n 1)" ]; then
        return 0
    fi
    return 1
}

detect_git_identity() {
    GIT_IDENTITY_READY="false"
    GIT_IDENTITY_SOURCE="unknown"

    if ! command -v git >/dev/null 2>&1; then
        GIT_IDENTITY_SOURCE="git command unavailable"
        return 1
    fi

    local -a repo_scope=()
    if git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        repo_scope=(-C "$PROJECT_DIR")
    fi

    local committer_ident=""
    committer_ident="$(git "${repo_scope[@]+"${repo_scope[@]}"}" var GIT_COMMITTER_IDENT 2>/dev/null || true)"
    if [ -z "$committer_ident" ]; then
        if [ -n "${GIT_COMMITTER_NAME:-}" ] || [ -n "${GIT_COMMITTER_EMAIL:-}" ] || [ -n "${GIT_AUTHOR_NAME:-}" ] || [ -n "${GIT_AUTHOR_EMAIL:-}" ]; then
            GIT_IDENTITY_SOURCE="incomplete identity environment variables"
        else
            GIT_IDENTITY_SOURCE="git user.name/user.email not configured"
        fi
        return 1
    fi

    if [ -n "${GIT_COMMITTER_NAME:-}" ] && [ -n "${GIT_COMMITTER_EMAIL:-}" ]; then
        GIT_IDENTITY_SOURCE="environment (GIT_COMMITTER_*)"
    elif [ -n "${GIT_AUTHOR_NAME:-}" ] && [ -n "${GIT_AUTHOR_EMAIL:-}" ]; then
        GIT_IDENTITY_SOURCE="environment (GIT_AUTHOR_*)"
    else
        local local_name="" local_email="" global_name="" global_email=""
        if [ "${#repo_scope[@]}" -gt 0 ]; then
            local_name="$(git -C "$PROJECT_DIR" config --local --get user.name 2>/dev/null || true)"
            local_email="$(git -C "$PROJECT_DIR" config --local --get user.email 2>/dev/null || true)"
        fi
        global_name="$(git config --global --get user.name 2>/dev/null || true)"
        global_email="$(git config --global --get user.email 2>/dev/null || true)"

        if [ -n "$local_name" ] && [ -n "$local_email" ]; then
            GIT_IDENTITY_SOURCE="local git config"
        elif [ -n "$global_name" ] && [ -n "$global_email" ]; then
            GIT_IDENTITY_SOURCE="global git config"
        else
            GIT_IDENTITY_SOURCE="system git config"
        fi
    fi

    GIT_IDENTITY_READY="true"
    return 0
}

refresh_git_identity_status() {
    if detect_git_identity; then
        info "Git identity status: ready (${GIT_IDENTITY_SOURCE})."
        return 0
    fi
    warn "Git identity status: missing (${GIT_IDENTITY_SOURCE})."
    return 1
}

ensure_git_repository_initialized() {
    if git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        return 0
    fi

    if ! is_true "$AUTO_INIT_GIT_IF_MISSING"; then
        warn "No git repository detected and auto-init is disabled."
        return 0
    fi

    if ! command -v git >/dev/null 2>&1; then
        err "Git is required for auto-init but command is not available."
        log_reason_code "RB_GIT_INIT_FAILED" "git command missing while auto-init-git-if-missing=true"
        return 1
    fi

    warn "No git repository detected. Initializing repository in $(path_for_display "$PROJECT_DIR")."
    if ! git -C "$PROJECT_DIR" init >/dev/null 2>&1; then
        err "Failed to initialize git repository in $(path_for_display "$PROJECT_DIR")."
        log_reason_code "RB_GIT_INIT_FAILED" "git init failed in project dir"
        return 1
    fi

    if ! git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        err "git init completed but repository validation failed."
        log_reason_code "RB_GIT_INIT_FAILED" "git init reported success but rev-parse failed"
        return 1
    fi

    success "Initialized git repository (no remote configured)."
    return 0
}

build_phase_commit_message() {
    local phase="$1"
    local next_phase="${2:-$(phase_default_next "$phase")}"
    local fallback_message
    fallback_message="$(printf '%s' "${phase}->${next_phase}: gate pass" | tr '[:upper:]' '[:lower:]')"

    if ! git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "$fallback_message"
        return 0
    fi

    local paths_file groups_file total_files group_count shown extra
    local groups_summary=""
    paths_file="$(mktemp "$CONFIG_DIR/commit-paths.XXXXXX")" || { echo "$fallback_message"; return 0; }
    groups_file="$(mktemp "$CONFIG_DIR/commit-groups.XXXXXX")" || { rm -f "$paths_file"; echo "$fallback_message"; return 0; }

    if ! git -C "$PROJECT_DIR" diff --cached --name-only -- . > "$paths_file" 2>/dev/null; then
        rm -f "$paths_file" "$groups_file"
        echo "$fallback_message"
        return 0
    fi

    total_files="$(wc -l < "$paths_file" | tr -d ' ')"
    if ! is_number "$total_files" || [ "$total_files" -lt 1 ]; then
        rm -f "$paths_file" "$groups_file"
        echo "$fallback_message"
        return 0
    fi

    awk '
        {
            if ($0 ~ /\//) {
                split($0, a, "/")
                top=a[1]
            } else {
                top="repo"
            }
            print top
        }
    ' "$paths_file" | sort | uniq -c | sort -nr > "$groups_file"

    group_count="$(wc -l < "$groups_file" | tr -d ' ')"
    shown=0
    while read -r count group; do
        [ -n "${group:-}" ] || continue
        group="$(printf '%s' "$group" | tr '[:upper:]' '[:lower:]')"
        groups_summary="${groups_summary}${groups_summary:+,}${group}:${count}"
        shown=$((shown + 1))
        [ "$shown" -ge 3 ] && break
    done < "$groups_file"

    extra=$((group_count - shown))
    if [ "$extra" -gt 0 ]; then
        groups_summary="${groups_summary},+${extra}g"
    fi

    rm -f "$paths_file" "$groups_file"
    if [ -z "$groups_summary" ]; then
        echo "$fallback_message"
        return 0
    fi
    printf '%s' "${phase}->${next_phase}: ${total_files}f ${groups_summary}" | tr '[:upper:]' '[:lower:]'
}

prepare_phase_auto_commit_mode() {
    AUTO_COMMIT_SESSION_ENABLED="false"
    AUTO_COMMIT_BASELINE_DIRTY_PATHS_FILE=""
    if ! is_true "$AUTO_COMMIT_ON_PHASE_PASS"; then
        info "Phase auto-commit is disabled."
        return 0
    fi

    if ! git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        warn "Phase auto-commit requested, but project is not a git repository. Disabling auto-commit."
        return 0
    fi

    if ! detect_git_identity; then
        warn "Phase auto-commit requested, but git identity is not ready (${GIT_IDENTITY_SOURCE})."
        warn "Set git user.name/user.email (or GIT_COMMITTER_* env vars), then restart with --resume."
        return 0
    fi

    AUTO_COMMIT_BASELINE_DIRTY_PATHS_FILE="$(mktemp "$CONFIG_DIR/autocommit-baseline.XXXXXX")" || AUTO_COMMIT_BASELINE_DIRTY_PATHS_FILE=""
    if [ -n "$AUTO_COMMIT_BASELINE_DIRTY_PATHS_FILE" ]; then
        collect_git_dirty_paths > "$AUTO_COMMIT_BASELINE_DIRTY_PATHS_FILE" 2>/dev/null || true
    fi
    if [ -n "$AUTO_COMMIT_BASELINE_DIRTY_PATHS_FILE" ] && [ -s "$AUTO_COMMIT_BASELINE_DIRTY_PATHS_FILE" ]; then
        warn "Auto-commit starting from a dirty worktree; phase commits will be skipped if they overlap pre-existing dirty paths."
    fi

    AUTO_COMMIT_SESSION_ENABLED="true"
    info "Git identity ready for auto-commit (${GIT_IDENTITY_SOURCE})."
    info "Phase auto-commit enabled (local commits only; pushes are disabled)."
}

collect_git_dirty_paths() {
    if ! git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        return 0
    fi
    {
        git -C "$PROJECT_DIR" diff --name-only -- . 2>/dev/null || true
        git -C "$PROJECT_DIR" diff --cached --name-only -- . 2>/dev/null || true
        git -C "$PROJECT_DIR" ls-files --others --exclude-standard -- . 2>/dev/null || true
    } | sed '/^$/d' | sort -u
}

collect_manifest_delta_commit_paths() {
    local manifest_before="$1"
    local manifest_after="$2"
    local output_file="$3"

    [ -n "$output_file" ] || return 1
    : > "$output_file"
    if [ ! -f "$manifest_before" ] || [ ! -f "$manifest_after" ]; then
        return 1
    fi
    phase_manifest_changed_paths "$manifest_before" "$manifest_after" | sed '/^$/d' | sort -u > "$output_file"
    [ -s "$output_file" ]
}

stage_commit_paths_from_file() {
    local paths_file="$1"
    local rel_path
    local staged_any=false

    [ -f "$paths_file" ] || return 1
    while IFS= read -r rel_path; do
        [ -n "$rel_path" ] || continue
        if git -C "$PROJECT_DIR" add -A -- "$rel_path" 2>/dev/null; then
            staged_any=true
        else
            warn "Auto-commit staging skipped path '$rel_path' (path no longer resolvable)."
        fi
    done < "$paths_file"

    [ "$staged_any" = true ]
}

commit_phase_approved_changes() {
    local phase="$1"
    local next_phase="$2"
    local manifest_before="${3:-}"
    local manifest_after="${4:-}"
    local commit_paths_file=""

    if ! is_true "$AUTO_COMMIT_SESSION_ENABLED"; then
        return 0
    fi
    if ! git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        warn "Auto-commit skipped for phase '$phase': not a git repository."
        return 0
    fi
    if ! detect_git_identity; then
        warn "Auto-commit skipped for phase '$phase': git identity unavailable (${GIT_IDENTITY_SOURCE})."
        return 0
    fi
    if ! git_has_local_changes; then
        info "Phase $phase gate approved: no local changes to commit."
        return 0
    fi

    if ! git -C "$PROJECT_DIR" diff --cached --quiet -- .; then
        warn "Auto-commit skipped for phase '$phase': pre-staged changes detected; refusing to mix unrelated index state."
        return 0
    fi

    commit_paths_file="$(mktemp "$CONFIG_DIR/commit-paths.XXXXXX")" || commit_paths_file=""
    if [ -z "$commit_paths_file" ] || ! collect_manifest_delta_commit_paths "$manifest_before" "$manifest_after" "$commit_paths_file"; then
        warn "Auto-commit skipped for phase '$phase': no reliable manifest delta paths were captured for this attempt."
        rm -f "$commit_paths_file"
        return 0
    fi
    if [ -n "${AUTO_COMMIT_BASELINE_DIRTY_PATHS_FILE:-}" ] && [ -s "$AUTO_COMMIT_BASELINE_DIRTY_PATHS_FILE" ]; then
        local overlap_file
        overlap_file="$(mktemp "$CONFIG_DIR/commit-overlap.XXXXXX")" || overlap_file=""
        if [ -n "$overlap_file" ]; then
            comm -12 "$AUTO_COMMIT_BASELINE_DIRTY_PATHS_FILE" "$commit_paths_file" > "$overlap_file" 2>/dev/null || true
            if [ -s "$overlap_file" ]; then
                warn "Auto-commit skipped for phase '$phase': phase delta overlaps paths dirty before Ralphie started."
                sed 's/^/  - /' "$overlap_file" >&2 || true
                rm -f "$overlap_file" "$commit_paths_file"
                return 0
            fi
            rm -f "$overlap_file"
        fi
    fi

    if ! stage_commit_paths_from_file "$commit_paths_file"; then
        info "Phase $phase gate approved: no stageable files detected in phase manifest delta."
        rm -f "$commit_paths_file"
        return 0
    fi
    if git -C "$PROJECT_DIR" diff --cached --quiet -- .; then
        info "Phase $phase gate approved: nothing staged for commit."
        rm -f "$commit_paths_file"
        return 0
    fi

    local commit_message commit_sha commit_err_file
    commit_message="$(build_phase_commit_message "$phase" "$next_phase")"
    commit_err_file="$(mktemp "$CONFIG_DIR/commit-error.XXXXXX")" || commit_err_file=""
    if ! git -C "$PROJECT_DIR" commit -m "$commit_message" >"${commit_err_file:-/dev/null}" 2>&1; then
        if [ -n "$commit_err_file" ] && grep -qiE "author identity unknown|unable to auto-detect email address|please tell me who you are" "$commit_err_file" 2>/dev/null; then
            GIT_IDENTITY_READY="false"
            GIT_IDENTITY_SOURCE="git commit reported missing identity"
            warn "Auto-commit skipped for phase '$phase': git identity is missing."
            warn "Set git user.name/user.email (or GIT_COMMITTER_* env vars), then restart with --resume."
            rm -f "$commit_err_file"
            rm -f "$commit_paths_file"
            return 0
        fi
        err "Auto-commit failed for phase '$phase'."
        if [ -n "$commit_err_file" ] && [ -s "$commit_err_file" ]; then
            tail -n 3 "$commit_err_file" >&2 || true
        fi
        rm -f "$commit_err_file"
        rm -f "$commit_paths_file"
        return 1
    fi
    rm -f "$commit_err_file"
    rm -f "$commit_paths_file"

    commit_sha="$(git -C "$PROJECT_DIR" rev-parse --short HEAD 2>/dev/null || true)"
    info "Phase $phase committed (${commit_sha:-unknown}): $commit_message"
    return 0
}

phase_index_from_name() {
    case "$1" in
        plan) echo 0; return 0 ;;
        build) echo 1; return 0 ;;
        test) echo 2; return 0 ;;
        refactor) echo 3; return 0 ;;
        lint) echo 4; return 0 ;;
        document) echo 5; return 0 ;;
        done) echo 6; return 0 ;;
        *) echo 0; return 1 ;;
    esac
}

phase_name_from_index() {
    local index="$1"
    if ! is_number "$index"; then
        echo ""
        return 1
    fi
    case "$index" in
        0) echo "plan"; return 0 ;;
        1) echo "build"; return 0 ;;
        2) echo "test"; return 0 ;;
        3) echo "refactor"; return 0 ;;
        4) echo "lint"; return 0 ;;
        5) echo "document"; return 0 ;;
        *) echo ""; return 1 ;;
    esac
}

phase_default_next() {
    local phase="$1"
    case "$phase" in
        plan) echo "build" ;;
        build) echo "test" ;;
        test) echo "refactor" ;;
        refactor) echo "lint" ;;
        lint) echo "document" ;;
        document) echo "done" ;;
        *) echo "done" ;;
    esac
}

phase_default_previous() {
    local phase="$1"
    case "$phase" in
        plan) echo "plan" ;;
        build) echo "plan" ;;
        test) echo "build" ;;
        refactor) echo "test" ;;
        lint) echo "refactor" ;;
        document) echo "lint" ;;
        done) echo "document" ;;
        *) echo "plan" ;;
    esac
}

phase_has_passed_in_history() {
    local phase="${1:-}"
    local entry

    case "$phase" in
        plan|build|test|refactor|lint|document) ;;
        *) return 1 ;;
    esac

    if [ "${#PHASE_TRANSITION_HISTORY[@]}" -eq 0 ]; then
        return 1
    fi

    for entry in "${PHASE_TRANSITION_HISTORY[@]+"${PHASE_TRANSITION_HISTORY[@]}"}"; do
        if [[ "$entry" == *"${phase}(attempt "* ]] && [[ "$entry" == *"|pass|"* ]]; then
            return 0
        fi
    done

    return 1
}

markdown_has_unchecked_local_tasks() {
    local markdown_file="$1"
    local unchecked_lines=""
    [ -f "$markdown_file" ] || return 1

    unchecked_lines="$(
        awk '
            BEGIN { in_code = 0; in_external_section = 0 }
            /^[[:space:]]*```/ {
                in_code = 1 - in_code
                next
            }
            in_code { next }
            /^[[:space:]]*#{1,6}[[:space:]]*/ {
                heading = tolower($0)
                if (heading ~ /deferred[[:space:]]+external/ || heading ~ /external-only/ || heading ~ /external[[:space:]]+queue/) {
                    in_external_section = 1
                } else {
                    in_external_section = 0
                }
                next
            }
            /^[[:space:]]*-[[:space:]]\[[[:space:]]\][[:space:]]/ {
                if (in_external_section) {
                    next
                }
                lower = tolower($0)
                if (lower ~ /open[[:space:]]*\[[[:space:]]*external[[:space:]]*\]/ || lower ~ /external-only/ || lower ~ /\[[[:space:]]*external[[:space:]]*\]/) {
                    next
                }
                print
            }
        ' "$markdown_file" 2>/dev/null || true
    )"
    [ -n "$unchecked_lines" ] || return 1

    return 0
}

collect_backlog_source_files() {
    local sources_raw="${BACKLOG_SOURCES:-$DEFAULT_BACKLOG_SOURCES}"
    local sources_trimmed item normalized abs_path
    local -a resolved=()

    sources_trimmed="$(sanitize_text_for_log "$sources_raw")"
    if [ -z "$sources_trimmed" ]; then
        sources_trimmed="$DEFAULT_BACKLOG_SOURCES"
    fi

    while IFS= read -r item; do
        normalized="$(printf '%s' "$item" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
        [ -n "$normalized" ] || continue
        case "$normalized" in
            /*) abs_path="$normalized" ;;
            *) abs_path="$PROJECT_DIR/$normalized" ;;
        esac
        resolved+=("$abs_path")
    done < <(printf '%s' "$sources_trimmed" | tr ',' '\n')

    if [ "${#resolved[@]}" -eq 0 ]; then
        resolved+=("$PLAN_FILE")
    fi

    printf '%s\n' "${resolved[@]}" | awk '!seen[$0]++'
}

backlog_source_display_list() {
    local source_file rel_path
    local -a labels=()

    while IFS= read -r source_file; do
        [ -n "$source_file" ] || continue
        rel_path="$(path_relative_to_project "$source_file")"
        if [ -n "$rel_path" ] && [ "$rel_path" != "$source_file" ]; then
            labels+=("$(path_for_display "$rel_path")")
        else
            labels+=("$(path_for_display "$source_file")")
        fi
    done < <(collect_backlog_source_files)

    if [ "${#labels[@]}" -eq 0 ]; then
        printf '%s' "configured backlog sources"
    else
        join_with_commas "${labels[@]}"
    fi
}

backlog_sources_fingerprint() {
    local source_file rel_path file_hash

    {
        printf 'backlog_sources=%s\n' "${BACKLOG_SOURCES:-$DEFAULT_BACKLOG_SOURCES}"
        while IFS= read -r source_file; do
            [ -n "$source_file" ] || continue
            rel_path="$(path_relative_to_project "$source_file")"
            [ -n "$rel_path" ] || rel_path="$source_file"
            if [ -f "$source_file" ]; then
                file_hash="$(sha256_file_sum "$source_file" 2>/dev/null || printf 'unavailable')"
                printf 'file\t%s\t%s\n' "$rel_path" "$file_hash"
            else
                printf 'missing\t%s\n' "$rel_path"
            fi
        done < <(collect_backlog_source_files)
    } | sha256_stream_sum
}

record_plan_freshness_checkpoint() {
    local fingerprint

    fingerprint="$(backlog_sources_fingerprint 2>/dev/null || true)"
    if [ -z "$fingerprint" ]; then
        warn "Plan freshness checkpoint skipped: could not fingerprint configured backlog sources."
        return 1
    fi

    PLAN_FRESHNESS_FINGERPRINT="$fingerprint"
    info "Plan freshness checkpoint recorded for $(backlog_source_display_list)."
    return 0
}

plan_has_unchecked_local_tasks() {
    local plan_file="${1:-$PLAN_FILE}"
    markdown_has_unchecked_local_tasks "$plan_file"
}

backlog_has_unchecked_local_tasks() {
    local source_file
    while IFS= read -r source_file; do
        [ -n "$source_file" ] || continue
        if markdown_has_unchecked_local_tasks "$source_file"; then
            return 0
        fi
    done < <(collect_backlog_source_files)
    return 1
}

file_mtime_epoch() {
    local target="$1"
    [ -e "$target" ] || { echo "-1"; return 0; }
    if stat -f '%m' "$target" >/dev/null 2>&1; then
        stat -f '%m' "$target" 2>/dev/null || echo "-1"
        return 0
    fi
    if stat -c '%Y' "$target" >/dev/null 2>&1; then
        stat -c '%Y' "$target" 2>/dev/null || echo "-1"
        return 0
    fi
    echo "-1"
}

backlog_sources_newer_than_plan() {
    local plan_file="${1:-$PLAN_FILE}"
    local plan_mtime source_file source_mtime rel_path current_fingerprint
    local -a stale_sources=()

    LAST_BACKLOG_STALE_SOURCES=""

    [ -f "$plan_file" ] || return 1

    if [ -n "${PLAN_FRESHNESS_FINGERPRINT:-}" ]; then
        current_fingerprint="$(backlog_sources_fingerprint 2>/dev/null || true)"
        if [ -n "$current_fingerprint" ]; then
            if [ "$current_fingerprint" = "$PLAN_FRESHNESS_FINGERPRINT" ]; then
                return 1
            fi
            LAST_BACKLOG_STALE_SOURCES="$(backlog_source_display_list)"
            [ -n "$LAST_BACKLOG_STALE_SOURCES" ] || LAST_BACKLOG_STALE_SOURCES="configured backlog sources"
            return 0
        fi
    fi

    plan_mtime="$(file_mtime_epoch "$plan_file")"
    is_number "$plan_mtime" || return 1
    [ "$plan_mtime" -ge 0 ] || return 1

    while IFS= read -r source_file; do
        [ -n "$source_file" ] || continue
        [ -f "$source_file" ] || continue
        if [ "$source_file" = "$plan_file" ]; then
            continue
        fi
        source_mtime="$(file_mtime_epoch "$source_file")"
        if is_number "$source_mtime" && [ "$source_mtime" -gt "$plan_mtime" ]; then
            rel_path="$(path_relative_to_project "$source_file")"
            if [ -n "$rel_path" ] && [ "$rel_path" != "$source_file" ]; then
                stale_sources+=("$(path_for_display "$rel_path")")
            else
                stale_sources+=("$(path_for_display "$source_file")")
            fi
        fi
    done < <(collect_backlog_source_files)

    if [ "${#stale_sources[@]}" -eq 0 ]; then
        return 1
    fi

    LAST_BACKLOG_STALE_SOURCES="$(join_with_commas "${stale_sources[@]+"${stale_sources[@]}"}")"
    return 0
}

enforce_phase_route_prerequisites() {
    local current_phase="${1:-}"
    local candidate_next="${2:-done}"
    local remap_target="$candidate_next"
    local -a reasons=()
    local stale_sources_text=""

    LAST_PHASE_ROUTE_GUARD_REASON=""
    LAST_PHASE_ROUTE_GUARD_NEXT_PHASE="$candidate_next"

    if ! is_phase_or_done "$candidate_next"; then
        LAST_PHASE_ROUTE_GUARD_NEXT_PHASE="$candidate_next"
        echo "$candidate_next"
        return 0
    fi

    if is_true "$REQUIRE_PLAN_FRESHNESS_FOR_BUILD"; then
        if backlog_sources_newer_than_plan "$PLAN_FILE"; then
            stale_sources_text="${LAST_BACKLOG_STALE_SOURCES:-configured backlog sources}"
            case "$candidate_next" in
                build|test|refactor|lint|document|done)
                    remap_target="plan"
                    reasons+=("plan refresh required: backlog sources newer than plan ($stale_sources_text)")
                    ;;
                *)
                    ;;
            esac
        fi
    fi

    LAST_PHASE_ROUTE_GUARD_NEXT_PHASE="$remap_target"
    if [ "${#reasons[@]}" -gt 0 ]; then
        LAST_PHASE_ROUTE_GUARD_REASON="$(join_with_commas "${reasons[@]+"${reasons[@]}"}")"
    fi
    echo "$remap_target"
}

enforce_terminal_done_requirements() {
    local current_phase="${1:-}"
    local candidate_next="${2:-done}"
    local lint_satisfied=false
    local document_satisfied=false
    local -a missing_required=()
    local remap_target=""

    LAST_DONE_GUARD_REASON=""
    LAST_DONE_GUARD_NEXT_PHASE="$candidate_next"
    if [ "$candidate_next" != "done" ]; then
        LAST_DONE_GUARD_NEXT_PHASE="$candidate_next"
        echo "$candidate_next"
        return 0
    fi

    if [ "$current_phase" = "lint" ] || phase_has_passed_in_history "lint"; then
        lint_satisfied=true
    fi
    if [ "$current_phase" = "document" ] || phase_has_passed_in_history "document"; then
        document_satisfied=true
    fi

    if is_true "$REQUIRE_LINT_BEFORE_DONE" && [ "$lint_satisfied" != "true" ]; then
        missing_required+=("lint")
    fi
    if is_true "$REQUIRE_DOCUMENT_BEFORE_DONE" && [ "$document_satisfied" != "true" ]; then
        missing_required+=("document")
    fi
    if is_true "$REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE" && backlog_has_unchecked_local_tasks; then
        missing_required+=("plan_backlog")
    fi

    if [ "${#missing_required[@]}" -eq 0 ]; then
        LAST_DONE_GUARD_NEXT_PHASE="done"
        echo "done"
        return 0
    fi

    if printf '%s\n' "${missing_required[@]}" | grep -Fxq "lint"; then
        remap_target="lint"
    elif printf '%s\n' "${missing_required[@]}" | grep -Fxq "document"; then
        remap_target="document"
    elif printf '%s\n' "${missing_required[@]}" | grep -Fxq "plan_backlog"; then
        remap_target="plan"
    else
        remap_target="${missing_required[0]}"
    fi

    LAST_DONE_GUARD_REASON="terminal guard remap: done blocked until required phase pass(es): $(join_with_commas "${missing_required[@]+"${missing_required[@]}"}")"
    LAST_DONE_GUARD_NEXT_PHASE="$remap_target"
    echo "$remap_target"
}

phase_index_or_done() {
    case "$1" in
        plan) echo 0; return 0 ;;
        build) echo 1; return 0 ;;
        test) echo 2; return 0 ;;
        refactor) echo 3; return 0 ;;
        lint) echo 4; return 0 ;;
        document) echo 5; return 0 ;;
        done) echo 6; return 0 ;;
        *) echo -1; return 1 ;;
    esac
}

phase_transition_history_append() {
    local phase="${1:-}"
    local attempt="${2:-?}"
    local next_phase="${3:-$phase}"
    local outcome="${4:-hold}"
    local reason="${5:-no explicit rationale}"
    local normalized_reason

    if [ -z "$phase" ]; then
        return 0
    fi

    normalized_reason="$(printf '%s' "$reason" | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g' | sed 's/^ *//; s/ *$//')"
    normalized_reason="${normalized_reason:-no explicit rationale}"
    PHASE_TRANSITION_HISTORY+=("${phase}(attempt ${attempt})->${next_phase}|${outcome}|${normalized_reason}")
}

phase_transition_history_recent() {
    local limit="${1:-8}"
    local start=0
    local i

    if [ "${#PHASE_TRANSITION_HISTORY[@]}" -eq 0 ]; then
        echo "no transitions yet"
        return 0
    fi

    if ! is_number "$limit" || [ "$limit" -lt 1 ]; then
        limit=8
    fi
    if [ "${#PHASE_TRANSITION_HISTORY[@]}" -gt "$limit" ]; then
        start=$(( ${#PHASE_TRANSITION_HISTORY[@]} - limit ))
    fi

    for (( i = start; i < ${#PHASE_TRANSITION_HISTORY[@]}; i++ )); do
        echo "${PHASE_TRANSITION_HISTORY[$i]}"
    done
}

collect_phase_resume_blockers() {
    local phase="$1"
    local -a blockers=()
    local stale_sources_text=""
    case "$phase" in
        plan)
            ;;
        build)
            mapfile -t blockers < <(collect_build_prerequisites_issues)
            ;;
        test|refactor|lint|document)
            if [ ! -f "$PLAN_FILE" ]; then
                blockers+=("test/build prerequisite missing: IMPLEMENTATION_PLAN.md")
            fi
            if [ ! -f "$STACK_SNAPSHOT_FILE" ]; then
                blockers+=("test/build prerequisite missing: research/STACK_SNAPSHOT.md")
            fi
            if [ -f "$PLAN_FILE" ] && ! plan_is_semantically_actionable "$PLAN_FILE"; then
                blockers+=("plan is not semantically actionable")
            fi
            if is_true "$REQUIRE_PLAN_FRESHNESS_FOR_BUILD" && backlog_sources_newer_than_plan "$PLAN_FILE"; then
                stale_sources_text="${LAST_BACKLOG_STALE_SOURCES:-configured backlog sources}"
                blockers+=("plan refresh required before $phase: backlog sources newer than plan ($stale_sources_text)")
            fi
            ;;
        *)
            blockers+=("unknown phase '$phase'")
            ;;
    esac

    print_array_lines "${blockers[@]+"${blockers[@]}"}"
}

summarize_blocks_for_log() {
    local -a blockers=("$@")
    local idx=0
    local output=""
    local item
    if [ "${#blockers[@]}" -eq 0 ]; then
        printf '%s' ""
        return 0
    fi
    for item in "${blockers[@]}"; do
        [ -z "$item" ] && continue
        if [ -z "$output" ]; then
            output="$item"
        else
            output="$output; $item"
        fi
    done
    printf '%s' "$output"
}

# Build gate and artifact validation
gitignore_required_entries() {
    cat <<'EOF'
.env
.env.*
logs/
consensus/
completion_log/
.ralphie/
HUMAN_INSTRUCTIONS.md
research/HUMAN_FEEDBACK.md
coverage/
.nyc_output/
htmlcov/
EOF
}

gitignore_has_entry() {
    local gitignore_file="$1"
    local entry="$2"
    local escaped_entry

    [ -f "$gitignore_file" ] || return 1
    escaped_entry="$(printf '%s' "$entry" | sed -E 's/[][(){}.^$*+?|\\]/\\&/g')"
    # Tolerate trailing inline comments so existing entries like "logs/ # keep" don't get duplicated.
    grep -qE "^[[:space:]]*${escaped_entry}[[:space:]]*(#.*)?$" "$gitignore_file"
}

gitignore_missing_required_entries() {
    local gitignore_file="$PROJECT_DIR/.gitignore"
    local entry
    if [ ! -f "$gitignore_file" ]; then
        gitignore_required_entries
        return 0
    fi

    local required_entries
    required_entries="$(gitignore_required_entries)"
    while IFS= read -r entry; do
        [ -n "$entry" ] || continue
        if ! gitignore_has_entry "$gitignore_file" "$entry"; then
            echo "$entry"
        fi
    done <<< "$required_entries"
}

ensure_gitignore_guardrails() {
    local gitignore_file="$PROJECT_DIR/.gitignore"
    local required_entries
    required_entries="$(gitignore_required_entries)"

    mkdir -p "$(dirname "$gitignore_file")"
    touch "$gitignore_file"

    local added=false
    local entry
    while IFS= read -r entry; do
        [ -n "$entry" ] || continue
        if ! gitignore_has_entry "$gitignore_file" "$entry"; then
            echo "$entry" >> "$gitignore_file"
            added=true
        fi
    done <<< "$required_entries"

    if [ "$added" = true ]; then
        info "Updated .gitignore with required runtime-safety entries."
    fi
}

file_has_local_identity_leakage() {
    local candidate_file="$1"
    if [ ! -f "$candidate_file" ]; then
        return 1
    fi

    local home_dir home_dir_regex
    home_dir="${HOME:-}"
    home_dir_regex="$(printf '%s' "$home_dir" | sed 's/[][(){}.^$*+?|\\/]/\\&/g')"

    if awk -v home_re="$home_dir_regex" -v allow_re="${MARKDOWN_LOCAL_PATH_ALLOWLIST_REGEX:-}" '
        function scrub(line) {
            if (allow_re != "") {
                gsub(allow_re, "", line)
            }
            return line
        }
        {
            line = scrub($0)
            if (home_re != "" && line ~ ("(^|[^[:alnum:]_.-])" home_re "(/|$)")) {
                found = 1
                exit
            }
            if (line ~ /\/Users\/[A-Za-z0-9._-]+\// || line ~ /\/home\/[A-Za-z0-9._-]+\// || line ~ /\/root\/[A-Za-z0-9._-]+\//) {
                found = 1
                exit
            }
        }
        END { exit found ? 0 : 1 }
    ' "$candidate_file" 2>/dev/null; then
        return 0
    fi
    return 1
}

markdown_artifacts_are_clean() {
    local leakage_pattern='succeeded in [0-9]+ms:|assistant[[:space:]]+to=|recipient_name[[:space:]]*:|tokens used|mcp startup:'
    local file bad=0
    local files=()
    local scoped_files=()

    [ -f "$PLAN_FILE" ] && files+=("$PLAN_FILE")
    [ -f "$PROJECT_DIR/README.md" ] && files+=("$PROJECT_DIR/README.md")

    local research_files spec_files
    research_files="$(find "$RESEARCH_DIR" -maxdepth 2 -type f -name "*.md" 2>/dev/null || true)"
    while IFS= read -r file; do
        [ -n "$file" ] && files+=("$file")
    done <<< "$research_files"

    spec_files="$(find "$SPECS_DIR" -maxdepth 3 -type f -name "*.md" 2>/dev/null || true)"
    while IFS= read -r file; do
        [ -n "$file" ] && files+=("$file")
    done <<< "$spec_files"

    if is_true "$AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED"; then
        for file in "${files[@]}"; do
            [ -f "$file" ] || continue
            if session_changed_paths_contains "$(path_relative_to_project "$file")"; then
                scoped_files+=("$file")
            fi
        done
        files=("${scoped_files[@]+"${scoped_files[@]}"}")
    fi

    if [ "${#files[@]}" -gt 0 ]; then
        for file in "${files[@]}"; do
            [ -f "$file" ] || continue
            if grep -qiE "$leakage_pattern" "$file" 2>/dev/null; then
                warn "Detected tool transcript leakage in markdown artifact: $(path_for_display "$file")"
                bad=1
            fi
            if file_has_local_identity_leakage "$file"; then
                warn "Detected local identity/path leakage in markdown artifact: $(path_for_display "$file")"
                bad=1
            fi
        done
    fi

    [ "$bad" -eq 0 ]
}

sanitize_markdown_artifact_file() {
    local file="$1"
    [ -f "$file" ] || return 0

    local tmp_file
    tmp_file="$(mktemp "$CONFIG_DIR/markdown-clean.XXXXXX")" || return 1
    local artifact_dir=""
    local artifact_prefix=""
    local diff_artifact=""
    local backup_artifact=""
    local rel_file=""
    rel_file="$(path_for_display "$(path_relative_to_project "$file")")"

    if awk -v allow_re="${MARKDOWN_LOCAL_PATH_ALLOWLIST_REGEX:-}" '
        function scrub(line) {
            if (allow_re != "") {
                gsub(allow_re, "", line)
            }
            return line
        }
        {
            clean_line = scrub($0)
            if ($0 ~ /succeeded in [0-9][0-9]*ms:/ || $0 ~ /assistant[[:space:]][[:space:]]*to=/ || $0 ~ /recipient_name[[:space:]]*:/ || $0 ~ /tokens used/ || $0 ~ /mcp startup:/) { next }
            if (clean_line ~ /\/Users\/[A-Za-z0-9._-]+\// || clean_line ~ /\/root\/[A-Za-z0-9._-]+\// || clean_line ~ /\/home\/[A-Za-z0-9._-]+\//) { next }
        }
        { print }
    ' "$file" > "$tmp_file"; then
        if ! cmp -s "$file" "$tmp_file"; then
            artifact_dir="$MARKDOWN_REPAIR_ARTIFACT_DIR/$SESSION_ID"
            mkdir -p "$artifact_dir" 2>/dev/null || artifact_dir="$CONFIG_DIR"
            artifact_prefix="$(printf '%s' "$rel_file" | tr '/ ' '__' | tr -cd 'A-Za-z0-9._-')"
            [ -n "$artifact_prefix" ] || artifact_prefix="artifact"

            diff_artifact="$artifact_dir/${artifact_prefix}.diff"
            diff -u "$file" "$tmp_file" > "$diff_artifact" 2>/dev/null || true

            if is_true "$AUTO_REPAIR_MARKDOWN_DRY_RUN"; then
                MARKDOWN_ARTIFACTS_CLEANED_LIST="${MARKDOWN_ARTIFACTS_CLEANED_LIST}${MARKDOWN_ARTIFACTS_CLEANED_LIST:+$'\n'}[dry-run] ${rel_file}"
                MARKDOWN_ARTIFACTS_PREVIEW_LIST="${MARKDOWN_ARTIFACTS_PREVIEW_LIST}${MARKDOWN_ARTIFACTS_PREVIEW_LIST:+$'\n'}$(path_for_display "$diff_artifact")"
                rm -f "$tmp_file"
                return 0
            fi

            if is_true "$AUTO_REPAIR_MARKDOWN_BACKUP"; then
                backup_artifact="$artifact_dir/${artifact_prefix}.bak"
                cp "$file" "$backup_artifact" 2>/dev/null || true
                if [ -f "$backup_artifact" ]; then
                    MARKDOWN_ARTIFACTS_BACKUP_LIST="${MARKDOWN_ARTIFACTS_BACKUP_LIST}${MARKDOWN_ARTIFACTS_BACKUP_LIST:+$'\n'}$(path_for_display "$backup_artifact")"
                fi
            fi
            mv "$tmp_file" "$file"
            MARKDOWN_ARTIFACTS_CLEANED_LIST="${MARKDOWN_ARTIFACTS_CLEANED_LIST}${MARKDOWN_ARTIFACTS_CLEANED_LIST:+$'\n'}$(path_for_display "$file")"
            MARKDOWN_ARTIFACTS_PREVIEW_LIST="${MARKDOWN_ARTIFACTS_PREVIEW_LIST}${MARKDOWN_ARTIFACTS_PREVIEW_LIST:+$'\n'}$(path_for_display "$diff_artifact")"
            return 0
        fi
        rm -f "$tmp_file"
    else
        rm -f "$tmp_file"
        return 1
    fi
}

sanitize_markdown_artifacts() {
    MARKDOWN_ARTIFACTS_CLEANED_LIST=""
    MARKDOWN_ARTIFACTS_PREVIEW_LIST=""
    MARKDOWN_ARTIFACTS_BACKUP_LIST=""
    local file
    local -a targets=("$PLAN_FILE" "$PROJECT_DIR/README.md")
    local -a scoped_targets=()

    if [ -d "$RESEARCH_DIR" ]; then
        while IFS= read -r -d '' file; do
            targets+=("$file")
        done < <(find "$RESEARCH_DIR" -maxdepth 3 -type f -name "*.md" -print0)
    fi

    if [ -d "$SPECS_DIR" ]; then
        while IFS= read -r -d '' file; do
            targets+=("$file")
        done < <(find "$SPECS_DIR" -maxdepth 4 -type f -name "*.md" -print0)
    fi

    if is_true "$AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED"; then
        for file in "${targets[@]}"; do
            [ -f "$file" ] || continue
            local rel_target
            rel_target="$(path_relative_to_project "$file")"
            if session_changed_paths_contains "$rel_target"; then
                scoped_targets+=("$file")
            fi
        done
        targets=("${scoped_targets[@]+"${scoped_targets[@]}"}")
    fi

    for file in "${targets[@]}"; do
        [ -f "$file" ] || continue
        sanitize_markdown_artifact_file "$file" || true
    done

    [ -n "$MARKDOWN_ARTIFACTS_CLEANED_LIST" ]
}

markdown_artifact_cleanup_summary() {
    local summary=""
    if [ -n "$MARKDOWN_ARTIFACTS_CLEANED_LIST" ]; then
        summary="$MARKDOWN_ARTIFACTS_CLEANED_LIST"
    fi
    if [ -n "$MARKDOWN_ARTIFACTS_PREVIEW_LIST" ]; then
        summary="${summary}${summary:+$'\n'}diff artifacts: ${MARKDOWN_ARTIFACTS_PREVIEW_LIST//$'\n'/, }"
    fi
    if [ -n "$MARKDOWN_ARTIFACTS_BACKUP_LIST" ]; then
        summary="${summary}${summary:+$'\n'}backups: ${MARKDOWN_ARTIFACTS_BACKUP_LIST//$'\n'/, }"
    fi
    printf '%s' "$summary"
}

stack_primary_from_snapshot() {
    if [ ! -f "$STACK_SNAPSHOT_FILE" ]; then
        echo "Unknown"
        return 0
    fi

    local primary
    primary="$(awk -F': ' '/^[[:space:]]*-?[[:space:]]*primary_stack:/ { gsub(/^[[:space:]]*-?[[:space:]]*primary_stack:[[:space:]]*/, "", $0); print $0; exit }' "$STACK_SNAPSHOT_FILE")"
    primary="${primary:-Unknown}"
    echo "$primary"
}

join_with_commas() {
    local -a items=("$@")
    local IFS=", "
    if [ "${#items[@]}" -eq 0 ]; then
        echo "-"
        return 0
    fi
    echo "${items[*]}"
}

stack_confidence_label() {
    local score="$1"
    if [ "$score" -ge 80 ]; then
        echo "high"
    elif [ "$score" -ge 60 ]; then
        echo "medium"
    elif [ "$score" -ge 35 ]; then
        echo "low"
    else
        echo "very_low"
    fi
}

run_stack_discovery() {
    mkdir -p "$RESEARCH_DIR"
    info "Running deterministic stack discovery scan."

    local pyproject_hits
    local -a node_signal=()
    local -a python_signal=()
    local -a go_signal=()
    local -a rust_signal=()
    local -a java_signal=()
    local -a dotnet_signal=()
    local -a unknown_signal=()
    local node_score=0 python_score=0 go_score=0
    local rust_score=0 java_score=0 dotnet_score=0 unknown_score=0

    local ts_count go_count java_count cs_count rb_count rs_count js_count
    pyproject_hits="$(find "$PROJECT_DIR" -maxdepth 2 -type f \( -name "*.py" -o -name "*.pyi" -o -name "requirements*.txt" \) 2>/dev/null | wc -l | tr -d ' ')"
    ts_count="$(find "$PROJECT_DIR" -maxdepth 3 -type f -name "*.ts" 2>/dev/null | wc -l | tr -d ' ')"
    go_count="$(find "$PROJECT_DIR" -maxdepth 3 -type f -name "*.go" 2>/dev/null | wc -l | tr -d ' ')"
    java_count="$(find "$PROJECT_DIR" -maxdepth 3 -type f \( -name "*.java" -o -name "*.kt" -o -name "*.gradle" -o -name "*.gradle.kts" \) 2>/dev/null | wc -l | tr -d ' ')"
    cs_count="$(find "$PROJECT_DIR" -maxdepth 3 -type f -name "*.csproj" 2>/dev/null | wc -l | tr -d ' ')"
    rs_count="$(find "$PROJECT_DIR" -maxdepth 3 -type f -name "*.rs" 2>/dev/null | wc -l | tr -d ' ')"
    rb_count="$(find "$PROJECT_DIR" -maxdepth 3 -type f -name "*.rb" 2>/dev/null | wc -l | tr -d ' ')"
    js_count="$(find "$PROJECT_DIR" -maxdepth 3 -type f -name "*.js" 2>/dev/null | wc -l | tr -d ' ')"

    # Node / JS / TS
    [ -f "$PROJECT_DIR/package.json" ] && { node_score=$((node_score + 55)); node_signal+=("package.json"); }
    [ -f "$PROJECT_DIR/package-lock.json" ] && { node_score=$((node_score + 10)); node_signal+=("package-lock.json"); }
    [ -f "$PROJECT_DIR/pnpm-lock.yaml" ] && { node_score=$((node_score + 10)); node_signal+=("pnpm-lock.yaml"); }
    [ -f "$PROJECT_DIR/yarn.lock" ] && { node_score=$((node_score + 10)); node_signal+=("yarn.lock"); }
    [ -f "$PROJECT_DIR/tsconfig.json" ] && { node_score=$((node_score + 12)); node_signal+=("tsconfig.json"); }
    [ -d "$PROJECT_DIR/node_modules" ] && { node_score=$((node_score + 3)); node_signal+=("node_modules"); }
    if is_number "$ts_count" && [ "$ts_count" -gt 0 ]; then node_score=$((node_score + 10)); node_signal+=("${ts_count} TS files"); fi
    if is_number "$js_count" && [ "$js_count" -gt 0 ]; then node_score=$((node_score + 8)); node_signal+=("${js_count} JS files"); fi

    # Python
    [ -f "$PROJECT_DIR/pyproject.toml" ] && { python_score=$((python_score + 60)); python_signal+=("pyproject.toml"); }
    [ -f "$PROJECT_DIR/requirements.txt" ] && { python_score=$((python_score + 20)); python_signal+=("requirements.txt"); }
    [ -f "$PROJECT_DIR/requirements-dev.txt" ] && { python_score=$((python_score + 10)); python_signal+=("requirements-dev.txt"); }
    [ -f "$PROJECT_DIR/setup.py" ] && { python_score=$((python_score + 15)); python_signal+=("setup.py"); }
    [ -f "$PROJECT_DIR/Pipfile" ] && { python_score=$((python_score + 10)); python_signal+=("Pipfile"); }
    if is_number "$pyproject_hits" && [ "$pyproject_hits" -gt 0 ]; then python_score=$((python_score + 8)); python_signal+=("${pyproject_hits} python manifest/files"); fi

    # Go
    [ -f "$PROJECT_DIR/go.mod" ] && { go_score=$((go_score + 70)); go_signal+=("go.mod"); }
    [ -f "$PROJECT_DIR/go.sum" ] && { go_score=$((go_score + 15)); go_signal+=("go.sum"); }
    if is_number "$go_count" && [ "$go_count" -gt 0 ]; then go_score=$((go_score + 10)); go_signal+=("${go_count} Go files"); fi

    # Rust
    [ -f "$PROJECT_DIR/Cargo.toml" ] && { rust_score=$((rust_score + 80)); rust_signal+=("Cargo.toml"); }
    [ -f "$PROJECT_DIR/Cargo.lock" ] && { rust_score=$((rust_score + 12)); rust_signal+=("Cargo.lock"); }
    if is_number "$rs_count" && [ "$rs_count" -gt 0 ]; then rust_score=$((rust_score + 10)); rust_signal+=("${rs_count} Rust files"); fi

    # Java / JVM
    [ -f "$PROJECT_DIR/pom.xml" ] && { java_score=$((java_score + 50)); java_signal+=("pom.xml"); }
    [ -f "$PROJECT_DIR/build.gradle" ] && { java_score=$((java_score + 35)); java_signal+=("build.gradle"); }
    [ -f "$PROJECT_DIR/build.gradle.kts" ] && { java_score=$((java_score + 35)); java_signal+=("build.gradle.kts"); }
    if is_number "$java_count" && [ "$java_count" -gt 0 ]; then java_score=$((java_score + 8)); java_signal+=("${java_count} JVM files"); fi

    # .NET
    [ -f "$PROJECT_DIR/Directory.Build.props" ] && { dotnet_score=$((dotnet_score + 35)); dotnet_signal+=("Directory.Build.props"); }
    if is_number "$cs_count" && [ "$cs_count" -gt 0 ]; then dotnet_score=$((dotnet_score + 12)); dotnet_signal+=("${cs_count} csproj files"); fi

    # Ruby
    [ -f "$PROJECT_DIR/Gemfile" ] && { unknown_score=$((unknown_score + 10)); unknown_signal+=("Gemfile"); }
    if is_number "$rb_count" && [ "$rb_count" -gt 0 ]; then unknown_score=$((unknown_score + 4)); unknown_signal+=("${rb_count} Ruby files"); fi

    local node_signal_summary="-" python_signal_summary="-" go_signal_summary="-"
    local rust_signal_summary="-" java_signal_summary="-" dotnet_signal_summary="-"
    local unknown_signal_summary="-"
    if [ "${#node_signal[@]}" -gt 0 ]; then
        node_signal_summary="$(join_with_commas "${node_signal[@]}")"
    fi
    if [ "${#python_signal[@]}" -gt 0 ]; then
        python_signal_summary="$(join_with_commas "${python_signal[@]}")"
    fi
    if [ "${#go_signal[@]}" -gt 0 ]; then
        go_signal_summary="$(join_with_commas "${go_signal[@]}")"
    fi
    if [ "${#rust_signal[@]}" -gt 0 ]; then
        rust_signal_summary="$(join_with_commas "${rust_signal[@]}")"
    fi
    if [ "${#java_signal[@]}" -gt 0 ]; then
        java_signal_summary="$(join_with_commas "${java_signal[@]}")"
    fi
    if [ "${#dotnet_signal[@]}" -gt 0 ]; then
        dotnet_signal_summary="$(join_with_commas "${dotnet_signal[@]}")"
    fi
    if [ "${#unknown_signal[@]}" -gt 0 ]; then
        unknown_signal_summary="$(join_with_commas "${unknown_signal[@]}")"
    fi

    local ranking_file
    ranking_file="$(mktemp "$CONFIG_DIR/stack-ranking.XXXXXX")" || {
        warn "Unable to create temp file for stack ranking."
        return 1
    }
    {
        printf "%03d|Node.js|%s\n" "$node_score" "$node_signal_summary"
        printf "%03d|Python|%s\n" "$python_score" "$python_signal_summary"
        printf "%03d|Go|%s\n" "$go_score" "$go_signal_summary"
        printf "%03d|Rust|%s\n" "$rust_score" "$rust_signal_summary"
        printf "%03d|Java|%s\n" "$java_score" "$java_signal_summary"
        printf "%03d|.NET|%s\n" "$dotnet_score" "$dotnet_signal_summary"
        printf "%03d|Ruby|%s\n" "$unknown_score" "$unknown_signal_summary"
        printf "%03d|Unknown|-\n" "$unknown_score"
    } > "$ranking_file"

    local -a ranked_candidates=()
    while IFS='|' read -r candidate_score candidate_stack candidate_signal; do
        ranked_candidates+=( "$candidate_score|$candidate_stack|$candidate_signal" )
    done < <(sort -t'|' -k1,1nr "$ranking_file")

    rm -f "$ranking_file"

    local primary_candidate primary_score
    primary_candidate="Unknown"
    primary_score=0
    if [ "${#ranked_candidates[@]}" -gt 0 ]; then
        IFS='|' read -r primary_score primary_candidate _ <<< "${ranked_candidates[0]}"
    fi

    local primary_confidence
    primary_confidence="$(stack_confidence_label "$primary_score")"
    if ! is_number "$primary_score"; then primary_score=0; fi

    {
        echo "# Stack Snapshot"
        echo ""
        echo "- generated_at: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        echo "- project_root: ."
        echo "- primary_stack: $primary_candidate"
        echo "- primary_score: $primary_score/100"
        echo "- confidence: $primary_confidence"
        echo ""
        echo "## Project Stack Ranking"
        echo ""
        echo "| rank | stack | score | evidence |"
        echo "| --- | --- | --- | --- |"
        local idx=1
        for entry in "${ranked_candidates[@]}"; do
            if [ -z "$entry" ]; then
                continue
            fi
            IFS='|' read -r score stack evidence <<< "$entry"
            echo "| $idx | $stack | $score | $evidence |"
            idx=$((idx + 1))
        done
        echo ""
        echo "## Deterministic Alternatives Ranking"
        echo "- Candidate evaluation is based on repository-level manifest and source signals only."
        echo "- Primary decision rule: highest score, then explicit manifest precedence."
        echo ""
        echo "### Top 3 stack alternatives (ranked)"
        local alt_idx=1
        for entry in "${ranked_candidates[@]}"; do
            [ "$alt_idx" -gt 3 ] && break
            IFS='|' read -r score stack evidence <<< "$entry"
            if [ "$stack" = "Unknown" ] && [ "$score" -eq 0 ] && [ "$alt_idx" -eq 1 ]; then
                echo "- 1) Unknown (insufficient deterministic signals)"
            else
                echo "- $alt_idx) $stack: score=$score, evidence=[$evidence]"
            fi
            alt_idx=$((alt_idx + 1))
        done
    } > "$STACK_SNAPSHOT_FILE"

    info "Stack snapshot complete: primary stack ${primary_candidate} (${primary_score}/100, ${primary_confidence})."
}

plan_is_semantically_actionable() {
    local plan_file="$1"
    [ -f "$plan_file" ] || return 1

    local has_goal=false
    local has_validation=false
    local task_count=0

    if grep -qiE '(^|#{1,6}[[:space:]]*)(goal|scope|objectives?|overview|context)\b|^[[:space:]]*(goal|scope|objectives?|overview|context)[[:space:]]*:' "$plan_file" 2>/dev/null; then
        has_goal=true
    fi
    if grep -qiE '(^|#{1,6}[[:space:]]*)(validation|verification|acceptance criteria|success criteria|definition of done|readiness|qa|testing)\b|^[[:space:]]*(validation|verification|acceptance criteria|success criteria|definition of done|readiness|qa|testing)[[:space:]]*:' "$plan_file" 2>/dev/null; then
        has_validation=true
    fi
    if ! is_true "$has_validation" && grep -qiE '^[[:space:]]*-[[:space:]]\[[ xX✓✔☑☒]\][[:space:]].*\b(validation|verify|verification|acceptance|success criteria|definition of done|readiness|qa|testing|test|smoke|gate)\b' "$plan_file" 2>/dev/null; then
        has_validation=true
    fi
    task_count="$(plan_task_count "$plan_file")"

    if is_true "$has_goal" && is_true "$has_validation" && [ "${task_count:-0}" -ge 1 ]; then
        return 0
    fi
    return 1
}

plan_is_fallback_placeholder() {
    local plan_file="$1"
    [ -f "$plan_file" ] || return 1
    grep -q '^ralphie_fallback_placeholder:[[:space:]]*true[[:space:]]*$' "$plan_file" 2>/dev/null
}

plan_task_count() {
    local plan_file="$1"
    if [ ! -f "$plan_file" ]; then
        echo "0"
        return 0
    fi
    local count
    count="$(grep -cE '^[[:space:]]*([0-9]+\.[[:space:]]|-[[:space:]]\[[ xX✓✔☑☒]\][[:space:]]|-[[:space:]](Run|Add|Update|Implement|Fix|Verify|Test|Document|Research|Decide|Refactor|Remove|Deprecate)[[:space:]])' "$plan_file" 2>/dev/null || true)"
    if ! is_number "$count"; then
        count="0"
    fi
    echo "$count"
}

write_gate_feedback() {
    local stage="$1"
    shift
    mkdir -p "$(dirname "$GATE_FEEDBACK_FILE")"
    {
        echo "# Ralphie Gate Feedback"
        echo ""
        echo "- Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
        echo "- Mode: $stage"
        echo ""
        echo "## Blockers"
        if [ "$#" -eq 0 ]; then
            echo "- None"
        else
            for _entry in "$@"; do
                echo "- $_entry"
            done
        fi
    } > "$GATE_FEEDBACK_FILE"
}

check_build_prerequisites() {
    local -a missing=()
    # Re-apply guardrails on every build-gate check so retries self-heal if
    # prior phase edits removed required .gitignore entries.
    ensure_gitignore_guardrails
    mapfile -t missing < <(collect_build_prerequisites_issues)
    if [ "${#missing[@]}" -gt 0 ]; then
        warn "Build prerequisites are incomplete:"
        local entry
        for entry in "${missing[@]}"; do
            warn "  - $entry"
        done
        log_reason_code "RB_BUILD_PREREQ_MISSING" "one or more build prerequisites failed"
        write_gate_feedback "build-prerequisites" "${missing[@]}"
        return 1
    fi

    rm -f "$GATE_FEEDBACK_FILE" 2>/dev/null || true
    return 0
}

collect_build_prerequisites_issues() {
    local -a missing=()
    if [ ! -d "$SPECS_DIR" ]; then
        missing+=("spec directory missing: specs/")
    fi
    if [ ! -d "$RESEARCH_DIR" ]; then
        missing+=("research directory missing: research/")
    fi
    if [ ! -f "$PLAN_FILE" ]; then
        missing+=("IMPLEMENTATION_PLAN.md missing before build")
    elif plan_is_fallback_placeholder "$PLAN_FILE"; then
        missing+=("IMPLEMENTATION_PLAN.md still contains Ralphie fallback placeholder; run PLAN to replace it with a project-specific plan")
    elif ! plan_is_semantically_actionable "$PLAN_FILE"; then
        missing+=("plan is not semantically actionable")
    fi

    if ! markdown_artifacts_are_clean; then
        missing+=("markdown artifacts must not contain tool transcript leakage or local identity/path leakage")
    fi

    local gitignore_missing_lines
    local -a gitignore_missing=()
    gitignore_missing_lines="$(gitignore_missing_required_entries || true)"
    while IFS= read -r missing_entry; do
        [ -n "$missing_entry" ] && gitignore_missing+=("$missing_entry")
    done <<< "$gitignore_missing_lines"
    if [ "${#gitignore_missing[@]}" -gt 0 ]; then
        local missing_joined
        missing_joined="$(printf '%s,' "${gitignore_missing[@]}" | sed 's/,$//')"
        missing+=(".gitignore must include local/sensitive/runtime guardrails (missing: $missing_joined)")
    fi

    if [ ! -f "$CONSTITUTION_FILE" ]; then
        missing+=("constitution file missing: .specify/memory/constitution.md")
    fi
    if is_true "$REQUIRE_PLAN_FRESHNESS_FOR_BUILD" && backlog_sources_newer_than_plan "$PLAN_FILE"; then
        local stale_sources
        stale_sources="${LAST_BACKLOG_STALE_SOURCES:-configured backlog sources}"
        missing+=("plan refresh required: backlog sources newer than plan ($stale_sources)")
    fi

    print_array_lines "${missing[@]+"${missing[@]}"}"
}

enforce_build_gate() {
    if ! check_build_prerequisites; then
        log_reason_code "RB_BUILD_GATE_PREREQ_FAILED" "build prerequisites failed"
        return 1
    fi
    return 0
}

collect_phase_schema_issues() {
    local phase="$1"
    local log_file="$2"
    local output_file="$3"
    local -a issues=()

    [ -f "$output_file" ] || issues+=("$phase output artifact missing: $output_file")
    [ -f "$log_file" ] || issues+=("$phase log artifact missing: $log_file")
    [ -n "$phase" ] || issues+=("missing phase name for schema check")

    print_array_lines "${issues[@]+"${issues[@]}"}"
}

pick_fallback_engine() { [ "${2:-}" = "claude" ] && echo "codex" || echo "claude"; }
effective_lock_wait_seconds() {
    local wait_seconds="${LOCK_WAIT_SECONDS:-0}"
    echo $(( wait_seconds + 7 ))
}
ensure_prompt_file() {
    local phase="$1"
    local file="$2"
    if [ -f "$file" ]; then
        return 0
    fi

    local phase_name="$phase"
    case "$phase_name" in
        plan|prepare)
            cat > "$file" <<'EOF'
# Ralphie Plan Phase Prompt
You are the autonomous planning engine for this project.

Goal
- Inspect the repository structure and runtime stack.
- Produce missing research artifacts and a concrete implementation plan.

Outputs (required)
- Research summary in `research/RESEARCH_SUMMARY.md` with `<confidence>`.
- `research/CODEBASE_MAP.md` mapping directories, entrypoints, and architecture assumptions.
- `research/DEPENDENCY_RESEARCH.md` documenting stack components and alternatives.
- `research/COVERAGE_MATRIX.md` with coverage against goals.
- `research/STACK_SNAPSHOT.md` with ranked stack hypotheses, deterministic confidence score, and alternatives.
- `IMPLEMENTATION_PLAN.md` with goal, validation criteria, and actionable tasks.
- If `IMPLEMENTATION_PLAN.md` contains `ralphie_fallback_placeholder: true`, replace it with a project-specific plan and remove that marker before declaring PLAN complete.
- `consensus/build_gate.md` if needed for blockers.

Behavior
- Compare at least two viable implementation paths when uncertainty exists.
- Keep markdown artifacts portable: no local machine paths, no tool transcripts, no timing output.
- Respond with concise completion notes:
  - What artifacts were updated.
  - What assumptions were made.
  - Any blockers or risks that remain.
- Phase is done when this guidance is satisfied and artifacts are genuinely ready for BUILD handoff.
EOF
            ;;
        build)
            cat > "$file" <<'EOF'
# Ralphie Build Phase Prompt
You are the implementation agent.

Goal
- Execute the highest-priority plan tasks from `IMPLEMENTATION_PLAN.md`.
- Keep changes scoped and validated by existing project patterns.

Behavior
- Prefer minimal diffs and avoid unrelated churn.
- Update implementation and tests to satisfy plan acceptance criteria.
- When external alternatives exist, record rationale in implementation notes.
- Provide a concise completion summary:
  - Files changed and why.
  - Verification actions you ran and outcomes.
  - Any known risks before declaring BUILD complete.
EOF
            ;;
        test)
            cat > "$file" <<'EOF'
# Ralphie Test Phase Prompt
You are the verification agent.

Goal
- Exercise new/changed functionality with targeted checks.
- Record exact commands, results, and failures in `completion_log`.

Behavior
- Validate assumptions behind plan items before declaring done.
- Note any skipped checks with reason.
- Return concise test completion findings:
  - What was tested and what was not tested (with reason).
  - Whether acceptance checks passed for changed behavior.
  - Risks introduced, if any.
EOF
            ;;
        refactor)
            cat > "$file" <<'EOF'
# Ralphie Refactor Phase Prompt
You are the refactoring agent.

Goal
- Improve structure and maintainability of changed areas only.
- Keep behavior stable and backward-compatible unless explicitly changing requirements.

Behavior
- Remove duplication where risk is low.
- Preserve API boundaries and update only what is needed.
- Return concise refactor completion notes:
  - Scope changed and why.
  - Concrete risks introduced.
  - Verification checks and outcomes.
EOF
            ;;
        lint)
            cat > "$file" <<'EOF'
# Ralphie Lint Phase Prompt
You are the quality gate agent.

Goal
- Evaluate consistency, style, and likely failure modes in recent changes.
- Suggest precise fixes before build/test progression.

Behavior
- Focus on deterministic checks and policy consistency.
- Return concise lint completion notes:
  - Key quality risks/observed issues.
  - Checks run and their outcomes.
  - Whether code is safe to progress based on observed signal.
EOF
            ;;
        document)
            cat > "$file" <<'EOF'
# Ralphie Document Phase Prompt
You are the documentation agent.

Goal
- Update or add project-facing documentation describing current behavior and rationale.
- Ensure `.md` outputs are reproducible and free of local context.

Behavior
- Emphasize assumptions, ownership, and runbook changes.
- Return concise documentation completion notes:
  - Files updated and the rationale.
  - Open questions or risks introduced.
  - Whether docs are clear enough to proceed.
EOF
            ;;
        *)
            touch "$file"
            ;;
    esac
    info "Wrote fallback prompt file: $(path_for_display "$file")"
}

ensure_core_artifacts() {
    mkdir -p "$SPECS_DIR" "$RESEARCH_DIR" "$LOG_DIR" "$COMPLETION_LOG_DIR" "$CONSENSUS_DIR" "$READY_ARCHIVE_DIR" "$SPECIFY_DIR"

    ensure_constitution_bootstrap

    [ -f "$PLAN_FILE" ] || cat > "$PLAN_FILE" <<'EOF'
# Implementation Plan
ralphie_fallback_placeholder: true

## Goal
- Produce a project-specific, executable, measurable development plan.

## Research Discovery
- Inspect repository structure, entrypoints, tests, configuration, and runtime stack.
- Map the current user workflow, execution boundaries, and operational constraints.

## Stack
- Determine the canonical workflow/runtime from repository evidence.
- Record alternatives and uncertainty where stack ownership is ambiguous.

## Acceptance Criteria
- `research/RESEARCH_SUMMARY.md` includes a `<confidence>` score and current posture.
- Research artifacts describe codebase shape, dependencies, coverage, and stack signals.
- This placeholder marker is removed by the PLAN phase after a real project-specific plan is written.

## Readiness
- Plan artifacts and build prerequisites remain stable between phase transitions.
- Required artifacts are present and reviewed before build/test gates.

## Risk
- Generic fallback planning can misdirect implementation if not replaced with repository-specific evidence.
- Missing handoff consistency checks may allow phase gates to pass without actionable evidence.

## Actionable Tasks
1. Inspect repository structure and stack dependencies.
2. Generate or update research artifacts (`research/*`).
3. Replace this fallback with a concrete, project-specific implementation plan.
4. Define validation commands and done criteria for the next build/test pass.
EOF

    [ -f "$RESEARCH_SUMMARY_FILE" ] || cat > "$RESEARCH_SUMMARY_FILE" <<'EOF'
# Research Summary

<confidence>0</confidence>
## Current Posture
- Baseline confidence is provisional for a fresh or existing project.
EOF

    [ -f "$RESEARCH_DIR/CODEBASE_MAP.md" ] || cat > "$RESEARCH_DIR/CODEBASE_MAP.md" <<'EOF'
# Codebase Map

## Directory Map
- `.`: Repository root and orchestration script entrypoint
- `./.specify/memory`: governance and constitution context
- `./research`: discovery artifacts and risk signal evidence
- `./specs`: implementation and contract specifications
- `./consensus`: review and arbitration outputs

## Entrypoints
- `ralphie.sh` (root orchestrator entrypoint)
- Additional entrypoints discovered during plan/build phases

## Modules
- orchestration and governance modules mapped during plan execution
- contract and validation surfaces defined in `specs/*.md`

## Architecture
- Module boundaries and ownership are inferred from file structure and explicit contracts.
EOF
    [ -f "$RESEARCH_DIR/DEPENDENCY_RESEARCH.md" ] || cat > "$RESEARCH_DIR/DEPENDENCY_RESEARCH.md" <<'EOF'
# Dependency Research

## Primary Stack Candidates
- Unknown (preliminary until discovery completes)

## Alternatives
- Python (expected orchestration stack)
- Node.js (possible frontend or operational tooling)
- Go (candidate for future performance-sensitive components)

## Risk Register
- Dependency lockfile completeness and version pinning
- Drift between local and committed manifests
- Entrypoint ambiguity across orchestration and scripts

## Dependency Evidence Notes
- Update this file during plan execution with deterministic signal mapping.
- Include rationale and tradeoffs before build gate progression.
EOF
    [ -f "$RESEARCH_DIR/COVERAGE_MATRIX.md" ] || cat > "$RESEARCH_DIR/COVERAGE_MATRIX.md" <<'EOF'
# Coverage Matrix

## Coverage Checklist
- Research coverage for stack and architecture evidence is planned.
- Spec coverage for acceptance criteria is pending.
- Plan readiness gate is tracked by consensus review and transition checks.
EOF
    [ -f "$STACK_SNAPSHOT_FILE" ] || cat > "$STACK_SNAPSHOT_FILE" <<'EOF'
# Stack Snapshot

- generated_at: PLACEHOLDER
- primary_stack: unknown
- primary_score: 0/100
- confidence: unknown

## Project Stack Ranking
| rank | stack | score | evidence |
| --- | --- | --- | --- |
| 1 | Unknown | 0 | no deterministic signals |

## Deterministic Alternatives Ranking
- No deterministic signal snapshot available yet.
EOF

    [ -f "$SPECS_DIR/project_contracts.md" ] || cat > "$SPECS_DIR/project_contracts.md" <<'EOF'
# Project Contracts

## Purpose
- Define the required behavior surface for implementation and validation.

## Acceptance Criteria
- Research artifacts include `RESEARCH_SUMMARY`, `CODEBASE_MAP`, `DEPENDENCY_RESEARCH`, `COVERAGE_MATRIX`, and `STACK_SNAPSHOT`.
- Implementation plan includes semantic actionability and measurable outcomes.

## Quality Gates
- Build gate requires explicit build checks and consensus pass.
- No blocking build prerequisites remain before phase transition.
EOF

}

setup_phase_prompts() {
    ensure_prompt_file "plan" "$PROMPT_PLAN_FILE"
    ensure_prompt_file "build" "$PROMPT_BUILD_FILE"
    ensure_prompt_file "test" "$PROMPT_TEST_FILE"
    ensure_prompt_file "refactor" "$PROMPT_REFACTOR_FILE"
    ensure_prompt_file "lint" "$PROMPT_LINT_FILE"
    ensure_prompt_file "document" "$PROMPT_DOCUMENT_FILE"
}

consensus_prompt_for_stage() {
    local stage="${1%-gate}"
    local loop_context="${2:-}"
    local evidence_context="${3:-}"
    local reviewer_persona="${4:-}"
    local next_phase_choices="plan|build|test|refactor|lint|document|done"
    if [ -n "$loop_context" ] && [ "$loop_context" != "no transitions yet" ]; then
        echo "Recent phase path context:"
        echo "$loop_context"
        echo ""
    fi
    if [ -n "$reviewer_persona" ]; then
        echo "Reviewer Persona: $reviewer_persona"
        echo ""
    fi
    if [ -n "$evidence_context" ]; then
        echo "Evidence context from this attempt:"
        echo "$evidence_context"
        echo ""
    fi
    echo "Use this transition history to decide whether to continue, backtrack, or stop."
    echo "Ground your verdict in the supplied artifacts and snippets; only claim missing evidence when those artifacts are unavailable or contradictory."
    echo ""
    case "$stage" in
        plan)
            cat <<EOF
Review the latest PLAN artifacts and agent output from this cycle.
Focus on whether the phase intent is complete, traceable, and safe.
Do not fail on markdown template exactness; judge based on substantive completion.
- Emit <score>(0-100)</score> and <verdict>(GO|HOLD)</verdict>.
- Emit <next_phase>${next_phase_choices}</next_phase>.
- Emit <next_phase_reason>one-sentence rationale for the phase transition.</next_phase_reason>.
- Include unresolved blockers in <gaps> as a concise comma-separated list.
EOF
            ;;
        build)
            cat <<EOF
Evaluate implementation completion and traceability to the plan.
Verify changed behavior and validation intent are coherent.
Do not require strict evidence-tag formatting; use semantic judgment with the phase outputs.
- Emit <score>(0-100)</score> and <verdict>(GO|HOLD)</verdict>.
- Emit <next_phase>${next_phase_choices}</next_phase>.
- Emit <next_phase_reason>one-sentence rationale for the phase transition.</next_phase_reason>.
- Include unresolved blockers in <gaps> as a concise comma-separated list.
EOF
            ;;
        test)
            cat <<EOF
Review test output quality and whether verification intent appears complete.
Treat concrete behavior changes and rationale as higher priority than exact markers.
- Emit <score>(0-100)</score> and <verdict>(GO|HOLD)</verdict>.
- Emit <next_phase>${next_phase_choices}</next_phase>.
- Emit <next_phase_reason>one-sentence rationale for the phase transition.</next_phase_reason>.
- Include unresolved blockers in <gaps> as a concise comma-separated list.
EOF
            ;;
        refactor)
            cat <<EOF
Review refactor output for risk, stability, and meaningful code improvements.
Prioritize actual refactor effect and safety over strict markdown structure.
Do not require strict evidence-tag formatting; use semantic judgment with the phase outputs.
- Emit <score>(0-100)</score> and <verdict>(GO|HOLD)</verdict>.
- Emit <next_phase>${next_phase_choices}</next_phase>.
- Emit <next_phase_reason>one-sentence rationale for the phase transition.</next_phase_reason>.
- Include unresolved blockers in <gaps> as a concise comma-separated list.
EOF
            ;;
        lint)
            cat <<EOF
Validate linting and quality review completeness from available evidence.
Judge whether issues and outcomes are meaningful, not whether they follow exact tag patterns.
- Emit <score>(0-100)</score> and <verdict>(GO|HOLD)</verdict>.
- Emit <next_phase>${next_phase_choices}</next_phase>.
- Emit <next_phase_reason>one-sentence rationale for the phase transition.</next_phase_reason>.
- Include unresolved blockers in <gaps> as a concise comma-separated list.
EOF
            ;;
        document)
            cat <<EOF
Validate documentation updates and decision clarity for this phase.
Prioritize correctness, completeness, and intent over exact template markers.
- Emit <score>(0-100)</score> and <verdict>(GO|HOLD)</verdict>.
- Emit <next_phase>${next_phase_choices}</next_phase>.
- Emit <next_phase_reason>one-sentence rationale for the phase transition.</next_phase_reason>.
- Include unresolved blockers in <gaps> as a concise comma-separated list.
EOF
            ;;
        *)
            cat <<EOF
Run independent quality review.
Emit <score>(0-100)</score> and <verdict>(GO|HOLD)</verdict>.
Emit <next_phase>${next_phase_choices}</next_phase> and <next_phase_reason>.
Include unresolved blockers in <gaps> as a concise comma-separated list.
EOF
            ;;
    esac
}

prompt_file_for_mode() {
    case "$1" in
        build) echo "$PROMPT_BUILD_FILE" ;;
        plan|prepare) echo "$PROMPT_PLAN_FILE" ;;
        test) echo "$PROMPT_TEST_FILE" ;;
        refactor) echo "$PROMPT_REFACTOR_FILE" ;;
        lint) echo "$PROMPT_LINT_FILE" ;;
        document) echo "$PROMPT_DOCUMENT_FILE" ;;
        *) echo "" ;;
    esac
}

build_phase_prompt_with_feedback() {
    local phase="$1"
    local base_prompt="$2"
    local target_prompt="$3"
    local attempt="$4"
    shift 4
    local -a failures=("$@")

    cp "$base_prompt" "$target_prompt"
    {
        echo ""
        echo "---"
        echo "## Retry Guidance (Attempt $attempt)"
        echo "- This phase did not pass machine checks on prior attempt."
        if [ "${#failures[@]}" -eq 0 ]; then
            echo "- Re-attempt with higher care for phase artifacts and explicit completeness."
        else
            echo "- Address all blockers before re-running:"
            for blocker in "${failures[@]}"; do
                [ -n "$blocker" ] || continue
                echo "- $blocker"
            done
            if [ "$phase" = "plan" ] && printf '%s\n' "${failures[@]}" | grep -qi "plan is not semantically actionable"; then
                echo "- Plan gate contract: include an explicit Goal section, an Acceptance Criteria/Validation section, and actionable checklist tasks ('- [ ]')."
            fi
        fi
        echo "- Preserve existing work; only generate missing/repairable artifacts and rerun this phase."
        echo "- Provide a concise completion recap with changed artifacts and residual risks."
    } >> "$target_prompt"
}

collect_phase_retry_failures_from_consensus() {
    local -a failures=()
    [ -n "$LAST_CONSENSUS_DIR" ] || { print_array_lines "${failures[@]+"${failures[@]}"}"; return 0; }
    local reviewer_summary ofile
    for ofile in "$LAST_CONSENSUS_DIR"/*.out; do
        [ -f "$ofile" ] || continue
        local score verdict next_phase next_phase_reason
        score="$(extract_review_score "$ofile")"
        verdict="$(extract_review_verdict "$ofile")"
        next_phase="$(extract_xml_value "$ofile" "next_phase" "unknown")"
        next_phase_reason="$(extract_xml_value "$ofile" "next_phase_reason" "")"
        next_phase_reason="$(sanitize_text_for_log "$next_phase_reason")"
        [ -n "$next_phase_reason" ] || next_phase_reason="no explicit phase-routing rationale"
        local gaps
        gaps="$(extract_review_gaps "$ofile" 140)"
        reviewer_summary="$(basename "$ofile"): score=$score verdict=${verdict:-HOLD} next=$next_phase reason=$next_phase_reason gaps=$gaps"
        failures+=("consensus review: $reviewer_summary")
    done
    print_array_lines "${failures[@]+"${failures[@]}"}"
}

ensure_constitution_bootstrap() {
    if [ -f "$CONSTITUTION_FILE" ]; then
        return 0
    fi

    mkdir -p "$SPECIFY_DIR"
    cat > "$CONSTITUTION_FILE" <<'EOF'
# Ralphie Constitution

## Purpose
- Establish deterministic, portable, and reproducible control planes for autonomous execution.
- Define behavior for all phases from planning through documentation.

## Governance
- Keep artifacts machine-readable: avoid local absolute paths, avoid command transcript leakage, and keep logs deterministic.
- Validate phase completion through reviewer-intelligence consensus and execution/build gates; keep semantic checks close to code and outputs.
- Treat gate failures as actionable signals, not terminal failure if bounded retries remain.

## Phase Contracts
- **Plan** produces research artifacts, an explicit implementation plan, and a deterministic stack snapshot.
- **Build** executes plan tasks against evidence in IMPLEMENTATION_PLAN.md.
- **Test** verifies behavior changes and documents validation rationale.
- **Refactor** preserves behavior, reduces complexity, and documents rationale.
- **Lint** enforces deterministic quality and cleanup policies.
- **Document** closes the lifecycle with updated user-facing documentation.

## Recovery and Retry Policy
- Every phase attempt that fails consensus or transition checks is retried within
  `PHASE_COMPLETION_MAX_ATTEMPTS` using feedback from prior blockers.
- Hard stop occurs only after bounded retries are exhausted and gate feedback is persisted.

## Evidence Requirements
- Phase completion is judged by reviewer-intelligence consensus plus execution/build-time gates.
- Plan/research artifacts are reviewed for substantive quality but not by rigid template matching.

## Environment Scope
- Repository-relative paths and relative markdown links are preferred.
- External references are allowed only when version/risk tradeoffs are explicitly documented.
EOF
}

plan_prompt_for_iteration() { echo "$1"; }
run_idle_plan_refresh() { return 0; }
print_session_config_banner() {
    info "=== Ralphie Session Budget & Retry Configuration ==="
    info "script_version: ${SCRIPT_VERSION}"
    info "auto_update: ${AUTO_UPDATE:-$DEFAULT_AUTO_UPDATE} (pre-run single-file update)"
    info "auto_update_url: $(redact_endpoint_for_log "$AUTO_UPDATE_URL")"
    info "auto_update_allow_dirty: ${AUTO_UPDATE_ALLOW_DIRTY:-$DEFAULT_AUTO_UPDATE_ALLOW_DIRTY}"
    info "auto_update_allow_insecure: ${AUTO_UPDATE_ALLOW_INSECURE:-$DEFAULT_AUTO_UPDATE_ALLOW_INSECURE}"
    info "max_session_cycles: ${MAX_SESSION_CYCLES:-0} (0=unlimited)"
    info "session_token_budget: ${SESSION_TOKEN_BUDGET:-0} (0=unlimited)"
    info "session_token_rate_cents_per_million: ${SESSION_TOKEN_RATE_CENTS_PER_MILLION:-0}"
    info "session_cost_budget_cents: ${SESSION_COST_BUDGET_CENTS:-0} (0=unlimited)"
    info "session token/cost accounting is heuristic (byte-based estimation, not invoice-accurate)"
    info "phase_completion_max_attempts: $(phase_attempt_limit_display "${PHASE_COMPLETION_MAX_ATTEMPTS:-0}")"
    info "phase_completion_retry_delay_seconds: ${PHASE_COMPLETION_RETRY_DELAY_SECONDS:-0}"
    info "phase_completion_retry_verbose: ${PHASE_COMPLETION_RETRY_VERBOSE:-false}"
    info "run_agent_max_attempts: ${RUN_AGENT_MAX_ATTEMPTS:-0}"
    info "run_agent_retry_delay_seconds: ${RUN_AGENT_RETRY_DELAY_SECONDS:-0}"
    info "run_agent_retry_verbose: ${RUN_AGENT_RETRY_VERBOSE:-false}"
    info "engine_idle_output_timeout_seconds: $(phase_attempt_limit_display "${ENGINE_IDLE_OUTPUT_TIMEOUT_SECONDS:-0}")"
    info "auto_init_git_if_missing: ${AUTO_INIT_GIT_IF_MISSING:-false}"
    info "auto_commit_on_phase_pass: ${AUTO_COMMIT_ON_PHASE_PASS:-false}"
    info "auto_engine_preference: ${AUTO_ENGINE_PREFERENCE:-$DEFAULT_AUTO_ENGINE_PREFERENCE}"
    info "codex_endpoint: $(redact_endpoint_for_log "$CODEX_ENDPOINT")"
    info "codex_model: ${CODEX_MODEL:-<default>}"
    info "codex_use_responses_schema: ${CODEX_USE_RESPONSES_SCHEMA:-false}"
    info "codex_responses_schema_file: ${CODEX_RESPONSES_SCHEMA_FILE:-<unset>}"
    info "codex_thinking_override: ${CODEX_THINKING_OVERRIDE:-<unset>}"
    info "claude_endpoint: $(redact_endpoint_for_log "$CLAUDE_ENDPOINT")"
    info "claude_model: ${CLAUDE_MODEL:-<default>}"
    info "claude_thinking_override: ${CLAUDE_THINKING_OVERRIDE:-<unset>}"
    info "engine_selection_requested: ${ENGINE_SELECTION_REQUESTED:-$DEFAULT_ENGINE}"
    info "active_engine_bootstrap: ${ACTIVE_ENGINE:-unknown} (${ACTIVE_CMD:-unset})"
    info "engine_overrides_bootstrapped: ${ENGINE_OVERRIDES_BOOTSTRAPPED:-$DEFAULT_ENGINE_OVERRIDES_BOOTSTRAPPED}"
    info "notifications_enabled: ${NOTIFICATIONS_ENABLED:-$DEFAULT_NOTIFICATIONS_ENABLED}"
    info "notification_channels: $(notification_channels_for_display)"
    info "notification_wizard_bootstrapped: ${NOTIFICATION_WIZARD_BOOTSTRAPPED:-$DEFAULT_NOTIFICATION_WIZARD_BOOTSTRAPPED}"
    info "telegram_bot_token: $(redact_secret_for_log "$TG_BOT_TOKEN")"
    info "telegram_chat_id: $(redact_secret_for_log "$TG_CHAT_ID")"
    info "discord_webhook: $(redact_endpoint_for_log "$NOTIFY_DISCORD_WEBHOOK_URL")"
    info "tts_enabled: ${NOTIFY_TTS_ENABLED:-$DEFAULT_NOTIFY_TTS_ENABLED}"
    info "tts_style: ${NOTIFY_TTS_STYLE:-$DEFAULT_NOTIFY_TTS_STYLE}"
    info "notify_event_dedup_window_seconds: ${NOTIFY_EVENT_DEDUP_WINDOW_SECONDS:-$DEFAULT_NOTIFY_EVENT_DEDUP_WINDOW_SECONDS}"
    info "notify_incident_reminder_minutes: ${NOTIFY_INCIDENT_REMINDER_MINUTES:-$DEFAULT_NOTIFY_INCIDENT_REMINDER_MINUTES}"
    info "chutes_api_key: $(redact_secret_for_log "$CHUTES_API_KEY")"
    info "chutes_tts_url: $(redact_endpoint_for_log "$NOTIFY_CHUTES_TTS_URL")"
    info "chutes_voice: ${NOTIFY_CHUTES_VOICE:-$DEFAULT_NOTIFY_CHUTES_VOICE}"
    info "chutes_speed: ${NOTIFY_CHUTES_SPEED:-$DEFAULT_NOTIFY_CHUTES_SPEED}"
    info "startup_operational_probe: ${STARTUP_OPERATIONAL_PROBE:-$DEFAULT_STARTUP_OPERATIONAL_PROBE}"
    info "engine_output_to_stdout: ${ENGINE_OUTPUT_TO_STDOUT:-true}"
    info "max_consensus_routing_attempts: ${MAX_CONSENSUS_ROUTING_ATTEMPTS:-0}"
    info "consensus_score_threshold: ${CONSENSUS_SCORE_THRESHOLD:-$DEFAULT_CONSENSUS_SCORE_THRESHOLD}"
    info "require_lint_before_done: ${REQUIRE_LINT_BEFORE_DONE:-$DEFAULT_REQUIRE_LINT_BEFORE_DONE}"
    info "require_document_before_done: ${REQUIRE_DOCUMENT_BEFORE_DONE:-$DEFAULT_REQUIRE_DOCUMENT_BEFORE_DONE}"
    info "require_plan_backlog_clear_before_done: ${REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE:-$DEFAULT_REQUIRE_PLAN_BACKLOG_CLEAR_BEFORE_DONE}"
    info "require_plan_freshness_for_build: ${REQUIRE_PLAN_FRESHNESS_FOR_BUILD:-$DEFAULT_REQUIRE_PLAN_FRESHNESS_FOR_BUILD}"
    info "backlog_sources: ${BACKLOG_SOURCES:-$DEFAULT_BACKLOG_SOURCES}"
    info "phase_noop_profile: ${PHASE_NOOP_PROFILE:-$DEFAULT_PHASE_NOOP_PROFILE}"
    info "strict_validation_noop: ${STRICT_VALIDATION_NOOP:-false}"
    info "auto_repair_markdown_artifacts: ${AUTO_REPAIR_MARKDOWN_ARTIFACTS:-false}"
    info "auto_repair_markdown_dry_run: ${AUTO_REPAIR_MARKDOWN_DRY_RUN:-false}"
    info "auto_repair_markdown_backup: ${AUTO_REPAIR_MARKDOWN_BACKUP:-false}"
    info "auto_repair_markdown_only_session_changed: ${AUTO_REPAIR_MARKDOWN_ONLY_SESSION_CHANGED:-false}"
    info "phase_manifest_mode: ${PHASE_MANIFEST_MODE:-$DEFAULT_PHASE_MANIFEST_MODE}"
    info "phase noop policies: plan=${PHASE_NOOP_POLICY_PLAN}, build=${PHASE_NOOP_POLICY_BUILD}, test=${PHASE_NOOP_POLICY_TEST}, refactor=${PHASE_NOOP_POLICY_REFACTOR}, lint=${PHASE_NOOP_POLICY_LINT}, document=${PHASE_NOOP_POLICY_DOCUMENT}"
    info "maps_dir: $(path_for_display "$MAPS_DIR")"
    info "subrepos_dir: $(path_for_display "$SUBREPOS_DIR")"
    info "agent_source_map: $(path_for_display "$AGENT_SOURCE_MAP_FILE")"
    info "binary_steering_map: $(path_for_display "$BINARY_STEERING_MAP_FILE")"
    info "self_improvement_log: $(path_for_display "$SELF_IMPROVEMENT_LOG_FILE")"
    info "setup_subrepos_script: $(path_for_display "$SETUP_SUBREPOS_SCRIPT")"
}

emit_phase_transition_banner() {
    local phase="$1"
    local noop_policy
    noop_policy="$(phase_noop_policy "$phase")"
    info ">>> Entering phase '$phase' <<<"
    info "phase completion attempts remaining: $(phase_attempt_limit_display "${PHASE_COMPLETION_MAX_ATTEMPTS:-0}")"
    if [ "$noop_policy" = "hard" ]; then
        info "worktree mutation policy: hard (attempt must mutate repository contents)"
    elif [ "$noop_policy" = "soft" ]; then
        info "worktree mutation policy: soft (no mutation is allowed but surfaced)"
    else
        info "worktree mutation policy: none"
    fi
}

format_retry_budget_block_reason() {
    local phase="$1"
    local attempt="$2"
    local limit="$3"
    log_reason_code "RB_PHASE_COMPLETION_RETRY_EXHAUSTED" "$phase completion signal exhausted after $attempt/$limit attempts"
}

main() {
    parse_args "$@"
    self_update_check_and_reexec "$@"
    if [ "${RALPHIE_SELF_UPDATE_TEST:-}" = "1" ]; then
        echo "RALPHIE_SELF_UPDATE_CURRENT_OK"
        return 0
    fi
    finalize_phase_noop_profile_config
    REBOOTSTRAP_REQUESTED="$(to_lower "${REBOOTSTRAP_REQUESTED:-$DEFAULT_REBOOTSTRAP_REQUESTED}")"
    is_bool_like "$REBOOTSTRAP_REQUESTED" || REBOOTSTRAP_REQUESTED="$DEFAULT_REBOOTSTRAP_REQUESTED"
    STARTUP_OPERATIONAL_PROBE="$(to_lower "${STARTUP_OPERATIONAL_PROBE:-$DEFAULT_STARTUP_OPERATIONAL_PROBE}")"
    is_bool_like "$STARTUP_OPERATIONAL_PROBE" || STARTUP_OPERATIONAL_PROBE="$DEFAULT_STARTUP_OPERATIONAL_PROBE"

    acquire_lock || exit 1
    install_cleanup_traps

    local resume_reentry_pending="false"
    if is_true "$RESUME_REQUESTED" && load_state; then
        resume_reentry_pending="true"
        success "Resuming mission..."
        RALPHIE_CLEANUP_STATE_ENABLED="true"
    else
        rm -f "$SESSION_CHANGED_PATHS_FILE" 2>/dev/null || true
        save_state_or_exit "session bootstrap initialization"
        RALPHIE_CLEANUP_STATE_ENABLED="true"
    fi
    if is_true "$ENGINE_OUTPUT_TO_STDOUT_EXPLICIT"; then
        ENGINE_OUTPUT_TO_STDOUT="$ENGINE_OUTPUT_TO_STDOUT_OVERRIDE"
    fi

    if ! is_number "$MAX_SESSION_CYCLES" || [ "$MAX_SESSION_CYCLES" -lt 0 ]; then
        MAX_SESSION_CYCLES=0
    fi
    if ! is_number "$PHASE_COMPLETION_MAX_ATTEMPTS" || [ "$PHASE_COMPLETION_MAX_ATTEMPTS" -lt 0 ]; then
        PHASE_COMPLETION_MAX_ATTEMPTS=3
    fi
    if ! is_number "$PHASE_COMPLETION_RETRY_DELAY_SECONDS" || [ "$PHASE_COMPLETION_RETRY_DELAY_SECONDS" -lt 0 ]; then
        PHASE_COMPLETION_RETRY_DELAY_SECONDS=5
    fi
    if ! is_number "$CONFIDENCE_STAGNATION_LIMIT" || [ "$CONFIDENCE_STAGNATION_LIMIT" -lt 1 ]; then
        CONFIDENCE_STAGNATION_LIMIT=3
    fi
    if ! is_number "$MAX_CONSENSUS_ROUTING_ATTEMPTS" || [ "$MAX_CONSENSUS_ROUTING_ATTEMPTS" -lt 0 ]; then
        MAX_CONSENSUS_ROUTING_ATTEMPTS="$DEFAULT_MAX_CONSENSUS_ROUTING_ATTEMPTS"
    fi
    if ! is_number "$MAX_ITERATIONS" || [ "$MAX_ITERATIONS" -lt 0 ]; then
        MAX_ITERATIONS=0
    fi
    if ! is_number "$COMMAND_TIMEOUT_SECONDS" || [ "$COMMAND_TIMEOUT_SECONDS" -lt 0 ]; then
        COMMAND_TIMEOUT_SECONDS="$DEFAULT_COMMAND_TIMEOUT_SECONDS"
    fi
    warn_timeout_binary_unavailable_if_needed
    if ! is_number "$SWARM_CONSENSUS_TIMEOUT" || [ "$SWARM_CONSENSUS_TIMEOUT" -lt 1 ]; then
        SWARM_CONSENSUS_TIMEOUT="$DEFAULT_SWARM_CONSENSUS_TIMEOUT"
    fi
    if ! is_number "$ENGINE_SMOKE_TEST_TIMEOUT" || [ "$ENGINE_SMOKE_TEST_TIMEOUT" -lt 1 ]; then
        ENGINE_SMOKE_TEST_TIMEOUT="$DEFAULT_ENGINE_SMOKE_TEST_TIMEOUT"
    fi

    local should_exit="false"
    if ! enforce_session_budget "session init"; then
        should_exit="true"
    fi
    if is_true "$should_exit"; then
        save_state_or_exit "session budget preflight failure"
        release_lock
        exit 1
    fi

    print_session_config_banner
    if is_true "$STARTUP_OPERATIONAL_PROBE"; then
        if ! run_startup_operational_probe; then
            release_lock
            exit 1
        fi
    fi
    ensure_core_artifacts
    setup_phase_prompts
    ensure_gitignore_guardrails
    ensure_project_bootstrap
    if ! ensure_git_repository_initialized; then
        release_lock
        exit 1
    fi
    refresh_git_identity_status || true
    prepare_phase_auto_commit_mode
    save_state_or_exit "post-startup bootstrap"

    local -a phases=("plan" "build" "test" "refactor" "lint" "document")
    local phase_index=0
    local start_phase_index=0
    local start_phase_name="plan"
    local -a phase_resume_blockers=()
    local done_phase_index="${#phases[@]}"
    if is_true "$RESUME_REQUESTED"; then
        if [ "${CURRENT_PHASE:-}" = "done" ]; then
            start_phase_index="$done_phase_index"
        else
        start_phase_index="$CURRENT_PHASE_INDEX"
        if ! is_number "$start_phase_index" || [ "$start_phase_index" -lt 0 ] || [ "$start_phase_index" -ge "${#phases[@]}" ]; then
            start_phase_index="$(phase_index_from_name "$CURRENT_PHASE")" || start_phase_index=0
            if ! is_number "$start_phase_index" || [ "$start_phase_index" -lt 0 ] || [ "$start_phase_index" -ge "${#phases[@]}" ]; then
                start_phase_index=0
            fi
        fi
        fi
        start_phase_name="$(phase_name_from_index "$start_phase_index")" || start_phase_name="plan"
        if [ "$start_phase_index" -lt "${#phases[@]}" ]; then
            mapfile -t phase_resume_blockers < <(collect_phase_resume_blockers "$start_phase_name")
        else
            phase_resume_blockers=()
        fi
        if [ "${#phase_resume_blockers[@]}" -gt 0 ]; then
            local resume_blockers_summary
            resume_blockers_summary="$(summarize_blocks_for_log "${phase_resume_blockers[@]}")"
            warn "Resumption into '$start_phase_name' is blocked by unmet preconditions: $resume_blockers_summary"
            warn "Falling back to plan phase to rebuild required artifacts and references."
            log_reason_code "RB_PHASE_RESUME_FALLBACK" "resume to $start_phase_name blocked: $resume_blockers_summary"
            write_gate_feedback "resume-recovery" "resumption fallback to plan" "${phase_resume_blockers[@]}"
            start_phase_name="plan"
            start_phase_index=0
            CURRENT_PHASE="$start_phase_name"
            CURRENT_PHASE_INDEX="$start_phase_index"
            CURRENT_PHASE_ATTEMPT=1
            PHASE_ATTEMPT_IN_PROGRESS="false"
            save_state_or_exit "resume fallback to plan checkpoint"
        fi
    fi

    local consensus_route_count=0
    local routing_stagnation_signature=""
    local routing_stagnation_count=0
    local engine_override_bootstrap_checked="false"
    local notification_wizard_bootstrap_checked="false"
    local session_start_notified="false"
    while true; do
        ENGINE_CAPABILITIES_PROBED=false  # force fresh probe (including smoke test) each iteration
        if ! ensure_engines_ready "$ENGINE_SELECTION_REQUESTED"; then
            should_exit="true"
            log_reason_code "RB_ENGINE_SELECTION_FAILED" "$LAST_ENGINE_SELECTION_BLOCK_REASON"
            notify_event "session_error" "engine_selection_failed" "$LAST_ENGINE_SELECTION_BLOCK_REASON" || true
            break
        fi
        if [ "$engine_override_bootstrap_checked" = "false" ]; then
            engine_override_bootstrap_checked="true"
            if run_first_deploy_engine_override_wizard; then
                ENGINE_CAPABILITIES_PROBED=false
                if ! ensure_engines_ready "$ENGINE_SELECTION_REQUESTED"; then
                    should_exit="true"
                    log_reason_code "RB_ENGINE_SELECTION_FAILED" "$LAST_ENGINE_SELECTION_BLOCK_REASON"
                    notify_event "session_error" "engine_selection_failed" "$LAST_ENGINE_SELECTION_BLOCK_REASON" || true
                    break
                fi
            fi
        fi
        if [ "$notification_wizard_bootstrap_checked" = "false" ]; then
            notification_wizard_bootstrap_checked="true"
            run_first_deploy_notification_wizard || true
        fi
        if [ "$session_start_notified" = "false" ]; then
            session_start_notified="true"
            notify_event "session_start" "ok" "engine_request=$ENGINE_SELECTION_REQUESTED active_engine=$ACTIVE_ENGINE channels=$(notification_channels_for_display)" || true
        fi
        for ((phase_index = start_phase_index; phase_index < ${#phases[@]}; phase_index++)); do
            local phase="${phases[$phase_index]}"
            local reentering_in_progress_phase="false"
            if is_true "$should_exit"; then break 2; fi
            CURRENT_PHASE_INDEX="$phase_index"
            CURRENT_PHASE="$phase"
            if [ "$resume_reentry_pending" = "true" ] && [ "$phase_index" -eq "$start_phase_index" ] && is_true "$PHASE_ATTEMPT_IN_PROGRESS"; then
                reentering_in_progress_phase="true"
                info "Resuming in-progress phase '$phase' at iteration ${ITERATION_COUNT} attempt ${CURRENT_PHASE_ATTEMPT}."
            else
                if [ "$MAX_ITERATIONS" -gt 0 ] && [ "$ITERATION_COUNT" -ge "$MAX_ITERATIONS" ]; then
                    log_reason_code "RB_ITERATION_BUDGET_REACHED" "run iteration budget reached before phase $phase at $ITERATION_COUNT/$MAX_ITERATIONS"
                    notify_event "session_error" "iteration_budget_reached" "iteration budget reached before phase=$phase at $ITERATION_COUNT/$MAX_ITERATIONS" || true
                    should_exit="true"
                    break 2
                fi
                ITERATION_COUNT=$((ITERATION_COUNT + 1))
            fi
            if [ "$reentering_in_progress_phase" != "true" ]; then
                CURRENT_PHASE_ATTEMPT=1
                PHASE_ATTEMPT_IN_PROGRESS="false"
            fi
            resume_reentry_pending="false"
            save_state_or_exit "phase entry checkpoint ($phase)"

            local pfile
            pfile="$(prompt_file_for_mode "$phase")"
            mkdir -p "$LOG_DIR" "$COMPLETION_LOG_DIR"
            if ! enforce_session_budget "session loop"; then
                should_exit="true"
                break
            fi
            emit_phase_transition_banner "$phase"
            if [ ! -f "$pfile" ]; then
                ensure_prompt_file "$phase" "$pfile"
            fi
            if [ "$phase" = "build" ] && ! build_is_preapproved; then
                warn "Build execution was not pre-approved in project bootstrap context."
                warn "Edit $(path_for_display "$PROJECT_BOOTSTRAP_FILE") and set build_consent: true to continue automatically into BUILD."
                log_reason_code "RB_BUILD_CONSENT_REQUIRED" "bootstrap build_consent is false"
                notify_event "session_error" "build_consent_missing" "build phase blocked because bootstrap build_consent=false" || true
                should_exit="true"
                break 2
            fi
            if [ "$phase" = "plan" ]; then
                run_stack_discovery
                if [ ! -f "$STACK_SNAPSHOT_FILE" ] || ! grep -qE '^##[[:space:]]*Project Stack Ranking' "$STACK_SNAPSHOT_FILE" 2>/dev/null; then
                    warn "Stack discovery could not generate a valid ranking snapshot."
                    log_reason_code "RB_STACK_DISCOVERY_FAILED" "could not generate deterministic stack snapshot"
                    notify_event "session_error" "stack_discovery_failed" "deterministic stack snapshot generation failed" || true
                    should_exit="true"
                    break
                fi
                save_state_or_exit "plan stack discovery checkpoint"
            fi

            local phase_attempt=1
            if [ "$reentering_in_progress_phase" = "true" ] && is_number "$CURRENT_PHASE_ATTEMPT" && [ "$CURRENT_PHASE_ATTEMPT" -ge 1 ]; then
                phase_attempt="$CURRENT_PHASE_ATTEMPT"
            fi
            if ! is_number "$phase_attempt" || [ "$phase_attempt" -lt 1 ] || { [ "$PHASE_COMPLETION_MAX_ATTEMPTS" -gt 0 ] && [ "$phase_attempt" -gt "$PHASE_COMPLETION_MAX_ATTEMPTS" ]; }; then
                warn "Recovered invalid persisted phase attempt '$phase_attempt' for phase '$phase'; resetting to attempt 1."
                phase_attempt=1
            fi
            local -a cumulative_phase_failures=()
            local phase_next_target="$phase"
            local phase_route="false"
            local phase_route_reason=""
            local phase_stagnation_signature=""
            local phase_stagnation_count=0
            while phase_attempt_within_budget "$phase_attempt" "$PHASE_COMPLETION_MAX_ATTEMPTS"; do
                CURRENT_PHASE="$phase"
                CURRENT_PHASE_INDEX="$phase_index"
                CURRENT_PHASE_ATTEMPT="$phase_attempt"
                PHASE_ATTEMPT_IN_PROGRESS="true"
                save_state_or_exit "phase attempt start checkpoint ($phase attempt $phase_attempt)"
                phase_attempt_started_at="$(date +%s 2>/dev/null || echo 0)"

                local lfile="$LOG_DIR/${phase}_${SESSION_ID}_${ITERATION_COUNT}_attempt_${phase_attempt}.log"
                local ofile="$COMPLETION_LOG_DIR/${phase}_${SESSION_ID}_${ITERATION_COUNT}_attempt_${phase_attempt}.out"
                local active_prompt="$pfile"
                local -a phase_failures=()
                local -a phase_warnings=()
                local consensus_evaluated="false"
                local attempt_feedback_file="$LOG_DIR/${phase}_${SESSION_ID}_${ITERATION_COUNT}_attempt_${phase_attempt}.prompt.md"
                local bootstrap_prompt_file="$LOG_DIR/${phase}_${SESSION_ID}_${ITERATION_COUNT}_attempt_${phase_attempt}.bootstrap.prompt.md"
                local previous_attempt_output_hash=""
                local previous_attempt_output_file=""
                local phase_noop_mode manifest_before_file manifest_after_file
                phase_noop_mode="$(phase_noop_policy "$phase")"
                local phase_delta_preview=""
                local handoff_validator_prompt="$LOG_DIR/${phase}_${SESSION_ID}_${ITERATION_COUNT}_attempt_${phase_attempt}.handoff.prompt.md"
                local handoff_validator_log="$LOG_DIR/${phase}_${SESSION_ID}_${ITERATION_COUNT}_attempt_${phase_attempt}.handoff.log"
                local handoff_validator_out="$COMPLETION_LOG_DIR/${phase}_${SESSION_ID}_${ITERATION_COUNT}_attempt_${phase_attempt}.handoff.out"
                local handoff_validator_status="$COMPLETION_LOG_DIR/${phase}_${SESSION_ID}_${ITERATION_COUNT}_attempt_${phase_attempt}.handoff.status"
                local handoff_validator_primary=""
                local handoff_validator_fallback=""
                local phase_warnings_text=""
                local consensus_evidence_context=""
                local -a consensus_failures=()
                local phase_commit_target=""

                manifest_before_file="$LOG_DIR/${phase}_${SESSION_ID}_${ITERATION_COUNT}_attempt_${phase_attempt}_manifest_before.txt"
                manifest_after_file="$LOG_DIR/${phase}_${SESSION_ID}_${ITERATION_COUNT}_attempt_${phase_attempt}_manifest_after.txt"
                phase_capture_worktree_manifest "$manifest_before_file" || true
                render_status_dashboard "$phase" "$phase_attempt" "$PHASE_COMPLETION_MAX_ATTEMPTS" "$ITERATION_COUNT"

                if [ "$phase_attempt" -gt 1 ]; then
                    local previous_attempt_file="$COMPLETION_LOG_DIR/${phase}_${SESSION_ID}_${ITERATION_COUNT}_attempt_$((phase_attempt - 1)).out"
                    if [ -f "$previous_attempt_file" ]; then
                        previous_attempt_output_hash="$(sha256_file_sum "$previous_attempt_file" 2>/dev/null || echo "")"
                        previous_attempt_output_file="$previous_attempt_file"
                    fi
                fi

                if [ "$phase" = "plan" ]; then
                    if append_bootstrap_context_to_plan_prompt "$pfile" "$bootstrap_prompt_file"; then
                        active_prompt="$bootstrap_prompt_file"
                    else
                        phase_failures+=("failed to assemble plan prompt with bootstrap context")
                    fi
                fi

                if [ "$phase_attempt" -gt 1 ]; then
                    if [ "${#cumulative_phase_failures[@]}" -gt 0 ]; then
                        build_phase_prompt_with_feedback "$phase" "$active_prompt" "$attempt_feedback_file" "$phase_attempt" "${cumulative_phase_failures[@]}"
                    else
                        build_phase_prompt_with_feedback "$phase" "$active_prompt" "$attempt_feedback_file" "$phase_attempt"
                    fi
                    active_prompt="$attempt_feedback_file"
                fi

                if [ "$phase" = "build" ] && ! enforce_build_gate; then
                    local -a gate_issues=()
                    mapfile -t gate_issues < <(collect_build_prerequisites_issues)
                    local repair_summary=""
                    if is_true "$AUTO_REPAIR_MARKDOWN_ARTIFACTS" && ! markdown_artifacts_are_clean; then
                        if sanitize_markdown_artifacts; then
                            repair_summary="$(markdown_artifact_cleanup_summary)"
                            if [ -n "$repair_summary" ]; then
                                phase_warnings+=("pre-build markdown remediation: ${repair_summary//$'\\n'/; }")
                            fi
                        fi
                        if [ -n "$repair_summary" ] && enforce_build_gate; then
                            gate_issues=()
                            phase_warnings+=("build gate passed after markdown artifact remediation")
                        fi
                    fi
                    if [ "${#gate_issues[@]}" -gt 0 ] && [ -n "$repair_summary" ]; then
                        phase_failures+=("pre-build markdown remediation applied before retry")
                        phase_failures+=("pre-build markdown remediation summary: ${repair_summary//$'\\n'/; }")
                    fi
                    if [ "${#gate_issues[@]}" -gt 0 ]; then
                        local gate_requires_plan_refresh=false
                        local gate_has_non_plan_refresh=false
                        for issue in "${gate_issues[@]}"; do
                            case "$issue" in
                                "plan refresh required:"*) gate_requires_plan_refresh=true ;;
                                *) gate_has_non_plan_refresh=true ;;
                            esac
                        done
                        if is_true "$gate_requires_plan_refresh" && ! is_true "$gate_has_non_plan_refresh"; then
                            phase_next_target="plan"
                            phase_route="true"
                            phase_route_reason="${gate_issues[0]}"
                            phase_transition_history_append "$phase" "$phase_attempt" "$phase_next_target" "hold" "$phase_route_reason"
                            write_gate_feedback "$phase" "${gate_issues[@]}" "auto-reroute triggered: build -> plan for backlog freshness"
                            warn "Build gate requires plan refresh; auto-routing build -> plan instead of retrying build."
                            notify_event "phase_decision" "reroute_hold" "phase=$phase attempt=$phase_attempt rerouted_to=$phase_next_target reason=${phase_route_reason:-none}" || true
                            log_reason_code "RB_BUILD_GATE_PLAN_REFRESH_REROUTE" "$phase attempt $phase_attempt rerouted to plan after backlog freshness gate"
                            PHASE_ATTEMPT_IN_PROGRESS="false"
                            CURRENT_PHASE_ATTEMPT=1
                            save_state_or_exit "build gate plan-refresh reroute checkpoint"
                            break
                        fi
                        for issue in "${gate_issues[@]}"; do
                            phase_failures+=("build gate blocked before build execution: $issue")
                        done
                    fi
                fi

                if [ "${#phase_failures[@]}" -eq 0 ] && run_agent_with_prompt "$active_prompt" "$lfile" "$ofile" "$YOLO" "$phase_attempt"; then
                    # Verify agent produced meaningful output
                    if [ ! -f "$ofile" ] || [ ! -s "$ofile" ]; then
                        phase_failures+=("agent completed with exit 0 but produced no output artifact")
                    fi

                    if [ -n "$previous_attempt_output_hash" ] && [ "${#phase_failures[@]}" -eq 0 ]; then
                        local phase_output_hash
                        phase_output_hash="$(sha256_file_sum "$ofile" 2>/dev/null || echo "")"
                        if [ -n "$previous_attempt_output_hash" ] && [ -n "$phase_output_hash" ] && [ "$previous_attempt_output_hash" = "$phase_output_hash" ]; then
                            phase_failures+=("phase output did not materially change from prior attempt")
                        fi
                    fi

                    if [ "$phase" = "plan" ]; then
                        local -a post_plan_gate_issues=()
                        local -a post_plan_actionable_gate_issues=()
                        local post_plan_issue
                        mapfile -t post_plan_gate_issues < <(collect_build_prerequisites_issues)
                        local post_plan_repair_summary=""
                        if is_true "$AUTO_REPAIR_MARKDOWN_ARTIFACTS" && ! markdown_artifacts_are_clean; then
                            if sanitize_markdown_artifacts; then
                                post_plan_repair_summary="$(markdown_artifact_cleanup_summary)"
                                mapfile -t post_plan_gate_issues < <(collect_build_prerequisites_issues)
                                [ -n "$post_plan_repair_summary" ] && phase_warnings+=("post-plan markdown remediation: ${post_plan_repair_summary//$'\\n'/; }")
                            fi
                        fi
                        for post_plan_issue in "${post_plan_gate_issues[@]}"; do
                            case "$post_plan_issue" in
                                "plan refresh required:"*)
                                    phase_warnings+=("post-plan freshness checkpoint pending for configured backlog sources")
                                    ;;
                                *)
                                    post_plan_actionable_gate_issues+=("$post_plan_issue")
                                    ;;
                            esac
                        done
                        if [ "${#post_plan_actionable_gate_issues[@]}" -eq 0 ] && [ -n "$post_plan_repair_summary" ]; then
                            info "Build gate passed after post-plan markdown remediation."
                        fi
                        if [ "${#post_plan_actionable_gate_issues[@]}" -gt 0 ]; then
                            phase_failures+=("build gate failed after plan->build transition")
                            [ -n "$post_plan_repair_summary" ] && phase_failures+=("post-plan markdown remediation summary: ${post_plan_repair_summary//$'\\n'/; }")
                            for issue in "${post_plan_actionable_gate_issues[@]}"; do
                                phase_failures+=("build gate: $issue")
                            done
                        fi
                    fi

                    phase_capture_worktree_manifest "$manifest_after_file" || true
                    if [ -f "$manifest_before_file" ] && [ -f "$manifest_after_file" ]; then
                        if phase_manifest_changed "$manifest_before_file" "$manifest_after_file"; then
                            record_session_changed_paths_from_manifest "$manifest_before_file" "$manifest_after_file" || true
                            phase_delta_preview="$(phase_manifest_delta_preview "$manifest_before_file" "$manifest_after_file" 8)"
                            if [ -n "$phase_delta_preview" ]; then
                                phase_delta_preview="$(printf '%s' "$phase_delta_preview" | tr '\n' '; ')"
                                if [ "$phase_noop_mode" != "none" ]; then
                                    phase_warnings+=("manifest delta preview: $phase_delta_preview")
                                fi
                            fi
                        else
                            if [ "$phase_noop_mode" = "hard" ]; then
                                phase_failures+=("$phase completed with no worktree mutation for phase '$phase'")
                            elif [ "$phase_noop_mode" = "soft" ]; then
                                phase_warnings+=("soft no-op signal: $phase completed without visible worktree mutation; acceptable for validation-only phases when run outputs are present")
                            fi
                        fi
                    elif [ "$phase_noop_mode" != "none" ]; then
                        phase_warnings+=("phase no-op check skipped: could not capture a reliable manifest snapshot for this attempt")
                    fi

                    phase_warnings_text="$(printf '%s\n' "${phase_warnings[@]+"${phase_warnings[@]}"}")"
                    write_handoff_validation_prompt \
                        "$phase" \
                        "$phase_attempt" \
                        "$ofile" \
                        "$lfile" \
                        "$handoff_validator_prompt" \
                        "$manifest_before_file" \
                        "$manifest_after_file" \
                        "$phase_delta_preview" \
                        "$phase_noop_mode" \
                        "$phase_warnings_text" \
                        "$previous_attempt_output_file"

                    local handoff_engine_request="${ENGINE_SELECTION_REQUESTED:-$DEFAULT_ENGINE}"
                    handoff_engine_request="$(to_lower "$handoff_engine_request")"
                    if [ "$handoff_engine_request" = "codex" ]; then
                        handoff_validator_primary="$CODEX_CMD"
                        handoff_validator_fallback=""
                        info "Handoff reviewer policy: pinned:codex"
                    elif [ "$handoff_engine_request" = "claude" ]; then
                        handoff_validator_primary="$CLAUDE_CMD"
                        handoff_validator_fallback=""
                        info "Handoff reviewer policy: pinned:claude"
                    else
                        if [ "${ACTIVE_ENGINE}" = "codex" ]; then
                            handoff_validator_primary="$CLAUDE_CMD"
                            handoff_validator_fallback="$CODEX_CMD"
                            info "Handoff reviewer policy: mixed:auto (active=codex, primary=claude, fallback=codex)"
                        else
                            handoff_validator_primary="$CODEX_CMD"
                            handoff_validator_fallback="$CLAUDE_CMD"
                            info "Handoff reviewer policy: mixed:auto (active=claude, primary=codex, fallback=claude)"
                        fi
                    fi

                    if [ "$handoff_validator_primary" = "$CODEX_CMD" ] && [ "$CODEX_HEALTHY" != "true" ]; then
                        handoff_validator_primary=""
                    fi
                    if [ "$handoff_validator_primary" = "$CLAUDE_CMD" ] && [ "$CLAUDE_HEALTHY" != "true" ]; then
                        handoff_validator_primary=""
                    fi
                    [ -n "$handoff_validator_primary" ] && command -v "$handoff_validator_primary" >/dev/null 2>&1 || handoff_validator_primary=""

                    if [ -z "$handoff_validator_primary" ]; then
                        if [ "${ACTIVE_ENGINE}" = "codex" ] && [ "$CODEX_HEALTHY" = "true" ] && command -v "$CODEX_CMD" >/dev/null 2>&1; then
                            handoff_validator_primary="$CODEX_CMD"
                        elif [ "${ACTIVE_ENGINE}" = "claude" ] && [ "$CLAUDE_HEALTHY" = "true" ] && command -v "$CLAUDE_CMD" >/dev/null 2>&1; then
                            handoff_validator_primary="$CLAUDE_CMD"
                        fi
                    fi

                    if [ "$handoff_validator_fallback" = "$handoff_validator_primary" ] || [ -z "$handoff_validator_fallback" ]; then
                        handoff_validator_fallback=""
                    elif [ "$handoff_validator_fallback" = "$CODEX_CMD" ] && [ "$CODEX_HEALTHY" != "true" ]; then
                        handoff_validator_fallback=""
                    elif [ "$handoff_validator_fallback" = "$CLAUDE_CMD" ] && [ "$CLAUDE_HEALTHY" != "true" ]; then
                        handoff_validator_fallback=""
                    elif ! command -v "$handoff_validator_fallback" >/dev/null 2>&1; then
                        handoff_validator_fallback=""
                    fi

                    if ! run_handoff_validation \
                        "$phase" \
                        "$handoff_validator_prompt" \
                        "$handoff_validator_log" \
                        "$handoff_validator_out" \
                        "$handoff_validator_status" \
                        "$handoff_validator_primary" \
                        "$handoff_validator_fallback"; then
                        phase_failures+=("handoff validation failed after $phase")
                        phase_failures+=("handoff review: verdict=$LAST_HANDOFF_VERDICT score=$LAST_HANDOFF_SCORE gaps=$LAST_HANDOFF_GAPS")
                    fi

                    consensus_evaluated="true"
                    local consensus_infra_retry_streak=0
                    local consensus_infra_signature=""
                    consensus_evidence_context="$(build_consensus_evidence_context \
                        "$phase" \
                        "$phase_attempt" \
                        "$ofile" \
                        "$lfile" \
                        "$handoff_validator_out" \
                        "$handoff_validator_status" \
                        "$manifest_before_file" \
                        "$manifest_after_file" \
                        "$phase_delta_preview" \
                        "$phase_warnings_text" \
                        "$previous_attempt_output_file")"
                    while true; do
                        if run_swarm_consensus "$phase-gate" "$(phase_transition_history_recent 8)" "$consensus_evidence_context"; then
                            record_gate_decision "$phase" "$phase_attempt" "$phase-gate" "pass"
                            break
                        fi
                        record_gate_decision "$phase" "$phase_attempt" "$phase-gate" "hold"

                        if [ "$LAST_CONSENSUS_FAILURE_KIND" = "infra" ]; then
                            local consensus_failure_reason
                            local consensus_stagnation_limit
                            consensus_failure_reason="${LAST_CONSENSUS_FAILURE_REASON:-infrastructure failure}"
                            consensus_stagnation_limit="${CONFIDENCE_STAGNATION_LIMIT:-3}"
                            is_number "$consensus_stagnation_limit" || consensus_stagnation_limit=3
                            if [ "$consensus_stagnation_limit" -lt 1 ]; then
                                consensus_stagnation_limit=1
                            fi

                            local current_consensus_signature
                            current_consensus_signature="$(phase_failure_signature "$LAST_CONSENSUS_FAILURE_KIND" "$consensus_failure_reason" "${LAST_CONSENSUS_RESPONDED_VOTES:-0}")"
                            if [ "$current_consensus_signature" = "$consensus_infra_signature" ]; then
                                consensus_infra_retry_streak=$((consensus_infra_retry_streak + 1))
                            else
                                consensus_infra_signature="$current_consensus_signature"
                                consensus_infra_retry_streak=1
                            fi

                            if [ "$consensus_infra_retry_streak" -ge "$consensus_stagnation_limit" ]; then
                                phase_failures+=("intelligence validation infra failure persisted after ${consensus_infra_retry_streak} retries: $consensus_failure_reason")
                                break
                            fi

                            warn "Consensus infrastructure issue detected ($consensus_failure_reason). Retrying consensus without consuming phase attempt."
                            notify_event "phase_blocked" "hold" "phase=$phase attempt=$phase_attempt reason=consensus_infra_retry retry=$consensus_infra_retry_streak/$consensus_stagnation_limit" || true
                            sleep "$PHASE_COMPLETION_RETRY_DELAY_SECONDS"
                            continue
                        fi

                        phase_failures+=("intelligence validation failed after $phase")
                        phase_failures+=("consensus score/verdict: score=${LAST_CONSENSUS_SCORE} pass=${LAST_CONSENSUS_PASS}")
                        mapfile -t consensus_failures < <(collect_phase_retry_failures_from_consensus)
                        for issue in "${consensus_failures[@]+"${consensus_failures[@]}"}"; do
                            phase_failures+=("consensus: $issue")
                        done
                        if [ -n "$LAST_CONSENSUS_SUMMARY" ]; then
                            phase_failures+=("consensus summary: $LAST_CONSENSUS_SUMMARY")
                        fi
                        break
                    done
                else
                    if [ "${#phase_failures[@]}" -eq 0 ]; then
                        phase_failures+=("agent execution failed in $phase")
                    fi
                fi

                if [ "${#phase_failures[@]}" -eq 0 ] && is_true "$AUTO_COMMIT_SESSION_ENABLED"; then
                    phase_commit_target="${LAST_CONSENSUS_NEXT_PHASE:-$(phase_default_next "$phase")}"
                    [ -n "$phase_commit_target" ] || phase_commit_target="$(phase_default_next "$phase")"
                    if ! commit_phase_approved_changes "$phase" "$phase_commit_target" "$manifest_before_file" "$manifest_after_file"; then
                        phase_failures+=("auto commit failed after $phase gate approval")
                        phase_failures+=("configure git user.name/user.email or disable auto commit")
                    fi
                fi

                if [ "${#phase_failures[@]}" -gt 0 ]; then
                    cumulative_phase_failures=("${phase_failures[@]}")
                    if is_true "$CONSENSUS_NO_ENGINES"; then
                        warn "Consensus unavailable: no healthy reviewer engines; will retry within phase budget."
                        log_reason_code "RB_CONSENSUS_ENGINES_UNAVAILABLE" "no healthy reviewer engines for consensus in phase $phase"
                        notify_event "phase_blocked" "hold" "phase=$phase attempt=$phase_attempt reason=consensus_engines_unavailable" || true
                    fi
                    if [ "$consensus_evaluated" = "true" ] && [ "${LAST_CONSENSUS_RESPONDED_VOTES:-0}" -gt 0 ] && is_phase_or_done "$LAST_CONSENSUS_NEXT_PHASE" && [ "$LAST_CONSENSUS_NEXT_PHASE" != "$phase" ]; then
                        local phase_route_candidate phase_route_candidate_index
                        phase_route_candidate="$LAST_CONSENSUS_NEXT_PHASE"
                        phase_route_candidate_index="$(phase_index_or_done "$phase_route_candidate")"
                        # On failed attempts, only allow backtracking reroutes.
                        # Forward/terminal reroutes would skip unresolved phase failures.
                        if is_number "$phase_route_candidate_index" && [ "$phase_route_candidate_index" -ge 0 ] && [ "$phase_route_candidate_index" -lt "$phase_index" ]; then
                            phase_next_target="$phase_route_candidate"
                            phase_route="true"
                            phase_route_reason="${LAST_CONSENSUS_NEXT_PHASE_REASON:-no explicit phase-routing rationale}"
                            record_gate_decision "$phase" "$phase_attempt" "$phase-gate" "reroute-hold" "$phase_next_target" "$phase_route_reason"
                            phase_transition_history_append "$phase" "$phase_attempt" "$phase_next_target" "hold" "$phase_route_reason"
                            notify_event "phase_decision" "reroute_hold" "phase=$phase attempt=$phase_attempt rerouted_to=$phase_next_target reason=${phase_route_reason:-none}" || true
                            PHASE_ATTEMPT_IN_PROGRESS="false"
                            CURRENT_PHASE_ATTEMPT=1
                            save_state_or_exit "phase reroute-hold checkpoint ($phase->$phase_next_target)"
                            break
                        fi
                        phase_warnings+=("ignoring non-backtracking reroute recommendation '$phase_route_candidate' while phase '$phase' has unresolved failures")
                    fi
                    if [ "$phase" = "build" ] && [ "$phase_route" != "true" ] && is_true "$AUTO_PLAN_BACKFILL_ON_IDLE_BUILD" && [ "$PHASE_COMPLETION_MAX_ATTEMPTS" -gt 0 ] && [ "$phase_attempt" -ge "$PHASE_COMPLETION_MAX_ATTEMPTS" ]; then
                        local build_consensus_hold_detected="false"
                        local build_hold_reason="consensus HOLD"
                        # Prefer state booleans over log-string matching to detect consensus HOLD.
                        if [ "$consensus_evaluated" != "true" ]; then
                            build_consensus_hold_detected="true"
                            build_hold_reason="consensus not run"
                        elif is_true "$CONSENSUS_NO_ENGINES"; then
                            build_consensus_hold_detected="true"
                            build_hold_reason="no reviewer engines available"
                        elif [ "$LAST_CONSENSUS_PASS" = "false" ]; then
                            build_consensus_hold_detected="true"
                            build_hold_reason="consensus HOLD"
                        elif printf '%s\n' "${phase_failures[@]}" | grep -qiE '^consensus score/verdict: .*pass=false'; then
                            build_consensus_hold_detected="true"
                            build_hold_reason="consensus HOLD (log)"
                        fi
                        if is_true "$build_consensus_hold_detected"; then
                            phase_next_target="plan"
                            phase_route="true"
                            phase_route_reason="auto-backtrack: build exhausted retries on $build_hold_reason; refreshing plan scope"
                            record_gate_decision "$phase" "$phase_attempt" "$phase-gate" "reroute-hold" "$phase_next_target" "$phase_route_reason"
                            phase_transition_history_append "$phase" "$phase_attempt" "$phase_next_target" "hold" "$phase_route_reason"
                            write_gate_feedback "$phase" "${phase_failures[@]}" "auto-backtrack triggered: rerouting build -> plan"
                            warn "Build retries exhausted ($build_hold_reason); auto-backtracking to plan for scope refresh."
                            notify_event "phase_decision" "reroute_hold" "phase=$phase attempt=$phase_attempt rerouted_to=$phase_next_target reason=${phase_route_reason:-none}" || true
                            log_reason_code "RB_BUILD_AUTO_BACKTRACK_TO_PLAN" "$phase attempt $phase_attempt/$PHASE_COMPLETION_MAX_ATTEMPTS rerouted to plan after $build_hold_reason"
                            PHASE_ATTEMPT_IN_PROGRESS="false"
                            CURRENT_PHASE_ATTEMPT=1
                            save_state_or_exit "build auto-backtrack checkpoint"
                            break
                        fi
                    fi
                    write_gate_feedback "$phase" "${phase_failures[@]}"
                    for issue in "${phase_failures[@]}"; do
                        warn "$issue"
                    done
                    if [ "${#phase_warnings[@]}" -gt 0 ]; then
                        for issue in "${phase_warnings[@]+"${phase_warnings[@]}"}"; do
                            info "note: $issue"
                        done
                    fi
                    if is_number "$PHASE_WALLCLOCK_LIMIT_SECONDS" && [ "$PHASE_WALLCLOCK_LIMIT_SECONDS" -gt 0 ] && is_number "${phase_attempt_started_at:-0}" && [ "${phase_attempt_started_at:-0}" -gt 0 ]; then
                        local now elapsed
                        now="$(date +%s 2>/dev/null || echo 0)"
                        elapsed=$(( now - phase_attempt_started_at ))
                        if [ "$elapsed" -ge "$PHASE_WALLCLOCK_LIMIT_SECONDS" ]; then
                            warn "Phase $phase wall-clock guard (${PHASE_WALLCLOCK_LIMIT_SECONDS}s) tripped on attempt $phase_attempt; stopping retries."
                            log_reason_code "RB_PHASE_WALLCLOCK_EXCEEDED" "phase $phase attempt $phase_attempt exceeded wall-clock limit ${PHASE_WALLCLOCK_LIMIT_SECONDS}s (elapsed ${elapsed}s)"
                            notify_event "phase_blocked" "hold" "phase=$phase wallclock=${PHASE_WALLCLOCK_LIMIT_SECONDS}s elapsed=${elapsed}s" || true
                            PHASE_ATTEMPT_IN_PROGRESS="false"
                            save_state_or_exit "phase wallclock guard checkpoint ($phase)"
                            should_exit="true"
                            break
                        fi
                    fi
                    local failure_signature
                    local phase_stagnation_limit
                    failure_signature="$(phase_failure_signature "${phase_failures[@]+"${phase_failures[@]}"}")"
                    if [ "$failure_signature" = "$phase_stagnation_signature" ]; then
                        phase_stagnation_count=$((phase_stagnation_count + 1))
                    else
                        phase_stagnation_signature="$failure_signature"
                        phase_stagnation_count=1
                    fi
                    phase_stagnation_limit="${CONFIDENCE_STAGNATION_LIMIT:-3}"
                    is_number "$phase_stagnation_limit" || phase_stagnation_limit=3
                    if [ "$phase_stagnation_limit" -lt 1 ]; then
                        phase_stagnation_limit=1
                    fi

                    log_reason_code "RB_PHASE_RETRYABLE_FAIL" "$phase attempt $phase_attempt/$(phase_attempt_limit_display "$PHASE_COMPLETION_MAX_ATTEMPTS"): ${phase_failures[*]}"
                    if [ "$PHASE_COMPLETION_MAX_ATTEMPTS" -eq 0 ] && [ "$phase_stagnation_count" -ge "$phase_stagnation_limit" ]; then
                        warn "Phase $phase stagnated for ${phase_stagnation_count} retries with no material failure signature change; stopping unlimited retry loop."
                        log_reason_code "RB_PHASE_RETRY_STAGNATION" "phase $phase stagnated after ${phase_stagnation_count} unlimited retries"
                        notify_event "phase_blocked" "hold" "phase=$phase unlimited retries stagnated after ${phase_stagnation_count} attempts" || true
                        should_exit="true"
                        PHASE_ATTEMPT_IN_PROGRESS="false"
                        save_state_or_exit "phase stagnation checkpoint ($phase)"
                        break
                    fi

                    phase_attempt=$((phase_attempt + 1))
                    if [ "$PHASE_COMPLETION_MAX_ATTEMPTS" -gt 0 ] && [ "$phase_attempt" -gt "$PHASE_COMPLETION_MAX_ATTEMPTS" ]; then
                        local auto_backtrack_target=""
                        local exhausted_attempt_count="$((phase_attempt - 1))"
                        if [ "$phase_route" != "true" ] && [ "$phase" != "plan" ]; then
                            auto_backtrack_target="$(phase_default_previous "$phase")"
                        fi
                        if [ -n "$auto_backtrack_target" ] && [ "$auto_backtrack_target" != "$phase" ]; then
                            phase_next_target="$auto_backtrack_target"
                            phase_route="true"
                            phase_route_reason="auto-backtrack: $phase exhausted retries (${exhausted_attempt_count}/${PHASE_COMPLETION_MAX_ATTEMPTS}); rerouting to $auto_backtrack_target for blocker resolution"
                            phase_transition_history_append "$phase" "$exhausted_attempt_count" "$phase_next_target" "hold" "$phase_route_reason"
                            write_gate_feedback "$phase" "${phase_failures[@]}" "auto-backtrack triggered: rerouting $phase -> $phase_next_target"
                            warn "Phase $phase exhausted retries (${exhausted_attempt_count}/${PHASE_COMPLETION_MAX_ATTEMPTS}); auto-backtracking to $phase_next_target."
                            notify_event "phase_decision" "reroute_hold" "phase=$phase attempt=$exhausted_attempt_count rerouted_to=$phase_next_target reason=${phase_route_reason:-none}" || true
                            log_reason_code "RB_PHASE_AUTO_BACKTRACK_RETRY_EXHAUSTED" "$phase attempt $exhausted_attempt_count/$PHASE_COMPLETION_MAX_ATTEMPTS rerouted to $phase_next_target after retry exhaustion"
                            PHASE_ATTEMPT_IN_PROGRESS="false"
                            CURRENT_PHASE_ATTEMPT=1
                            save_state_or_exit "phase retry exhaustion auto-backtrack checkpoint ($phase->$phase_next_target)"
                            break
                        fi
                        warn "Phase $phase blocked after ${PHASE_COMPLETION_MAX_ATTEMPTS} attempts."
                        format_retry_budget_block_reason "$phase" "$exhausted_attempt_count" "$PHASE_COMPLETION_MAX_ATTEMPTS"
                        notify_event "phase_blocked" "hold" "phase=$phase exhausted completion retries (${PHASE_COMPLETION_MAX_ATTEMPTS})" || true
                        should_exit="true"
                        PHASE_ATTEMPT_IN_PROGRESS="false"
                        CURRENT_PHASE_ATTEMPT="$PHASE_COMPLETION_MAX_ATTEMPTS"
                        save_state_or_exit "phase retry budget exhausted checkpoint ($phase)"
                        break
                    fi
                    CURRENT_PHASE_ATTEMPT="$phase_attempt"
                    PHASE_ATTEMPT_IN_PROGRESS="true"
                    save_state_or_exit "phase retry scheduling checkpoint ($phase attempt $phase_attempt)"
                    if is_true "$PHASE_COMPLETION_RETRY_VERBOSE"; then
                        warn "Phase $phase retrying in ${PHASE_COMPLETION_RETRY_DELAY_SECONDS}s (attempt ${phase_attempt}/$(phase_attempt_limit_display "$PHASE_COMPLETION_MAX_ATTEMPTS"))."
                    fi
                    sleep "$PHASE_COMPLETION_RETRY_DELAY_SECONDS"
                    continue
                fi

                if [ "${#phase_warnings[@]}" -gt 0 ]; then
                    for issue in "${phase_warnings[@]+"${phase_warnings[@]}"}"; do
                        info "note: $issue"
                    done
                fi

                if [ "$phase" = "plan" ]; then
                    record_plan_freshness_checkpoint || phase_warnings+=("plan freshness checkpoint could not be recorded; mtime fallback remains active")
                fi

                if is_number "$PHASE_WALLCLOCK_LIMIT_SECONDS" && [ "$PHASE_WALLCLOCK_LIMIT_SECONDS" -gt 0 ] && is_number "${phase_attempt_started_at:-0}" && [ "${phase_attempt_started_at:-0}" -gt 0 ]; then
                    local now elapsed
                    now="$(date +%s 2>/dev/null || echo 0)"
                    elapsed=$(( now - phase_attempt_started_at ))
                    if [ "$elapsed" -ge "$PHASE_WALLCLOCK_LIMIT_SECONDS" ]; then
                        warn "Phase $phase wall-clock guard (${PHASE_WALLCLOCK_LIMIT_SECONDS}s) tripped after successful attempt $phase_attempt; stopping before routing."
                        log_reason_code "RB_PHASE_WALLCLOCK_EXCEEDED" "phase $phase attempt $phase_attempt exceeded wall-clock limit ${PHASE_WALLCLOCK_LIMIT_SECONDS}s (elapsed ${elapsed}s)"
                        notify_event "phase_blocked" "hold" "phase=$phase wallclock=${PHASE_WALLCLOCK_LIMIT_SECONDS}s elapsed=${elapsed}s" || true
                        PHASE_ATTEMPT_IN_PROGRESS="false"
                        save_state_or_exit "phase wallclock guard checkpoint ($phase)"
                        should_exit="true"
                        break
                    fi
                fi

                local phase_requested_next
                local raw_phase_requested_next
                phase_requested_next="${LAST_CONSENSUS_NEXT_PHASE:-$(phase_default_next "$phase")}"
                [ -n "$phase_requested_next" ] || phase_requested_next="$(phase_default_next "$phase")"
                raw_phase_requested_next="$phase_requested_next"
                enforce_phase_route_prerequisites "$phase" "$phase_requested_next" >/dev/null
                phase_requested_next="${LAST_PHASE_ROUTE_GUARD_NEXT_PHASE:-$phase_requested_next}"
                if [ -n "${LAST_PHASE_ROUTE_GUARD_REASON:-}" ] && [ "$phase_requested_next" != "$raw_phase_requested_next" ]; then
                    local route_guard_reason
                    route_guard_reason="${LAST_PHASE_ROUTE_GUARD_REASON:-phase route guard remap}"
                    warn "Phase route guard remapped next phase: ${raw_phase_requested_next} -> ${phase_requested_next} (${route_guard_reason})."
                    notify_event "phase_decision" "route_guard_remap" "phase=$phase requested_next=${raw_phase_requested_next} remapped_next=${phase_requested_next} reason=${route_guard_reason}" || true
                    if [ -n "$phase_route_reason" ]; then
                        phase_route_reason="${phase_route_reason}; ${route_guard_reason}"
                    else
                        phase_route_reason="$route_guard_reason"
                    fi
                fi
                enforce_terminal_done_requirements "$phase" "$phase_requested_next" >/dev/null
                phase_next_target="${LAST_DONE_GUARD_NEXT_PHASE:-$phase_requested_next}"
                if [ "$phase_next_target" != "$phase_requested_next" ]; then
                    local done_guard_reason
                    done_guard_reason="${LAST_DONE_GUARD_REASON:-terminal guard remap}"
                    warn "Terminal guard remapped next phase: ${phase_requested_next} -> ${phase_next_target} (${done_guard_reason})."
                    notify_event "phase_decision" "terminal_guard_remap" "phase=$phase requested_next=${phase_requested_next} remapped_next=${phase_next_target} reason=${done_guard_reason}" || true
                    if [ -n "$phase_route_reason" ]; then
                        phase_route_reason="${phase_route_reason}; ${done_guard_reason}"
                    else
                        phase_route_reason="$done_guard_reason"
                    fi
                fi
                if is_phase_or_done "$phase_next_target" && [ "$phase_next_target" != "$phase" ]; then
                    phase_route="true"
                    if [ -z "${phase_route_reason:-}" ]; then
                        phase_route_reason="${LAST_CONSENSUS_NEXT_PHASE_REASON:-no explicit phase-routing rationale}"
                    fi
                elif [ -z "$phase_route_reason" ]; then
                    phase_route_reason="no explicit phase-routing rationale"
                fi
                record_gate_decision "$phase" "$phase_attempt" "$phase-gate" "pass" "$phase_next_target" "$phase_route_reason"
                phase_transition_history_append "$phase" "$phase_attempt" "$phase_next_target" "pass" "$phase_route_reason"
                PHASE_ATTEMPT_IN_PROGRESS="false"
                CURRENT_PHASE_ATTEMPT=1
                save_state_or_exit "phase completion checkpoint ($phase)"

                success "Phase $phase completed."
                notify_event "phase_complete" "go" "phase=$phase next=${phase_next_target:-unknown} route_reason=${phase_route_reason:-none}" || true
                break
            done
            if [ "$phase_route" = "true" ] && is_phase_or_done "$phase_next_target"; then
                local route_index
                local expected_next_phase expected_route_index
                expected_next_phase="$(phase_default_next "$phase")"
                expected_route_index="$(phase_index_or_done "$expected_next_phase")"
                route_index="$(phase_index_or_done "$phase_next_target")"
                if [ "$route_index" = "-1" ] || [ -z "$route_index" ]; then
                    route_index="$((phase_index + 1))"
                fi
                if [ "$phase_next_target" = "done" ] || [ "$route_index" -ne "$expected_route_index" ]; then
                    notify_event "phase_decision" "reroute_pass" "phase=$phase rerouted_to=$phase_next_target reason=${phase_route_reason:-none}" || true
                fi
                if [ "$route_index" -lt "$phase_index" ]; then
                    local route_is_plan_freshness
                    route_is_plan_freshness="false"
                    case "${phase_route_reason:-}" in
                        "plan refresh required:"*) route_is_plan_freshness="true" ;;
                    esac

                    if is_true "$route_is_plan_freshness"; then
                        routing_stagnation_signature=""
                        routing_stagnation_count=0
                        info "Plan freshness reroute will not count as consensus routing stagnation."
                    else
                        consensus_route_count=$((consensus_route_count + 1))
                        local routing_signature
                        routing_signature="$(phase_failure_signature "$phase" "$phase_next_target" "${phase_route_reason:-none}")"
                        if [ "$routing_signature" = "$routing_stagnation_signature" ]; then
                            routing_stagnation_count=$((routing_stagnation_count + 1))
                        else
                            routing_stagnation_signature="$routing_signature"
                            routing_stagnation_count=1
                        fi
                        if [ "$MAX_CONSENSUS_ROUTING_ATTEMPTS" -gt 0 ] && [ "$consensus_route_count" -gt "$MAX_CONSENSUS_ROUTING_ATTEMPTS" ]; then
                            warn "Consensus routing attempts exceeded limit ($consensus_route_count/$MAX_CONSENSUS_ROUTING_ATTEMPTS)."
                            log_reason_code "RB_ROUTING_BUDGET_EXCEEDED" "consensus routing attempts exceeded limit ($consensus_route_count/$MAX_CONSENSUS_ROUTING_ATTEMPTS)"
                            notify_event "session_error" "routing_budget_exceeded" "consensus routing attempts exceeded limit ($consensus_route_count/$MAX_CONSENSUS_ROUTING_ATTEMPTS)" || true
                            should_exit="true"
                            PHASE_ATTEMPT_IN_PROGRESS="false"
                            save_state_or_exit "routing budget checkpoint ($phase->$phase_next_target)"
                            break
                        fi
                        if [ "$MAX_CONSENSUS_ROUTING_ATTEMPTS" -eq 0 ] && [ "$routing_stagnation_count" -ge "$CONFIDENCE_STAGNATION_LIMIT" ]; then
                            warn "Consensus routing stagnated for ${routing_stagnation_count} backtracks with unchanged route signature."
                            log_reason_code "RB_ROUTING_STAGNATION" "unlimited routing stagnated after ${routing_stagnation_count} backtracks ($phase->$phase_next_target)"
                            notify_event "session_error" "routing_stagnation" "unlimited routing stagnated after ${routing_stagnation_count} backtracks" || true
                            should_exit="true"
                            PHASE_ATTEMPT_IN_PROGRESS="false"
                            save_state_or_exit "routing stagnation checkpoint ($phase->$phase_next_target)"
                            break
                        fi
                    fi
                fi
                if [ "$phase_next_target" = "done" ] || [ "$route_index" -ge "${#phases[@]}" ]; then
                    start_phase_index="${#phases[@]}"
                    phase_index="${#phases[@]}"
                else
                    warn "Adaptive phase routing: $phase -> $phase_next_target (${phase_route_reason:-no explicit rationale})."
                    start_phase_index="$route_index"
                    phase_index=$((route_index - 1))
                fi
            fi
        done
        # If the phase loop naturally reached the end without an explicit reroute,
        # mark terminal completion so the outer loop exits deterministically.
        if ! is_true "$should_exit" && [ "$phase_index" -ge "${#phases[@]}" ] && [ "$start_phase_index" -lt "${#phases[@]}" ]; then
            start_phase_index="${#phases[@]}"
        fi
        if is_true "$should_exit"; then
            break
        fi
        # If start_phase_index is past all phases (consensus routed to "done"
        # or natural completion of all phases), exit the outer loop
        if [ "$start_phase_index" -ge "${#phases[@]}" ]; then
            info "All phases completed. Session done."
            notify_event "session_done" "ok" "all phases completed successfully" || true
            CURRENT_PHASE="done"
            CURRENT_PHASE_INDEX="${#phases[@]}"
            CURRENT_PHASE_ATTEMPT=1
            PHASE_ATTEMPT_IN_PROGRESS="false"
            save_state_or_exit "session completion checkpoint"
            break
        fi
        if [ "$MAX_ITERATIONS" -gt 0 ] && [ "$ITERATION_COUNT" -ge "$MAX_ITERATIONS" ]; then
            log_reason_code "RB_ITERATION_BUDGET_REACHED" "run iteration budget reached at $ITERATION_COUNT"
            notify_event "session_error" "iteration_budget_reached" "iteration budget reached at $ITERATION_COUNT/$MAX_ITERATIONS" || true
            break
        fi
    done

    if is_true "$should_exit"; then
        notify_event "session_error" "stopped" "session exited before full completion; see $(path_for_display "$REASON_LOG_FILE")" || true
    fi
    save_state_or_exit "final session checkpoint"
    release_lock
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
