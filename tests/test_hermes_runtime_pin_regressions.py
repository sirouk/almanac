#!/usr/bin/env python3
from __future__ import annotations

import shlex
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMMON_SH = REPO / "bin" / "common.sh"
ENV_EXAMPLE = REPO / "config" / "almanac.env.example"
PINNED_REF = "ce089169d578b96c82641f17186ba63c288b22d8"


def run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=False)


def bash(script: str) -> subprocess.CompletedProcess[str]:
    return run(["bash", "-lc", script], cwd=REPO)


def extract(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_shared_runtime_pin_is_exposed_and_no_longer_floats() -> None:
    common_text = COMMON_SH.read_text(encoding="utf-8")
    example_text = ENV_EXAMPLE.read_text(encoding="utf-8")

    expect(
        f'ALMANAC_HERMES_AGENT_REF="${{ALMANAC_HERMES_AGENT_REF:-{PINNED_REF}}}"' in common_text,
        common_text,
    )
    expect(f"ALMANAC_HERMES_AGENT_REF={PINNED_REF}" in example_text, example_text)
    expect("git clone --depth 1 https://github.com/NousResearch/hermes-agent.git" not in common_text, common_text)
    expect('git -C "$repo_dir" pull --ff-only' not in common_text, common_text)
    expect('git -C "$repo_dir" checkout --force --detach "$resolved_commit"' in common_text, common_text)
    expect(
        'uv pip install --python "$venv_dir/bin/python3" --reinstall "$repo_dir[cli,mcp,messaging,cron,web]"'
        in common_text,
        common_text,
    )
    print("PASS test_shared_runtime_pin_is_exposed_and_no_longer_floats")


def test_ensure_shared_hermes_runtime_checks_out_requested_ref_and_reinstalls() -> None:
    text = COMMON_SH.read_text(encoding="utf-8")
    snippet = extract(text, "resolve_hermes_agent_ref_commit() {", "ensure_hermes_dashboard_assets() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        runtime_dir = tmp_path / "runtime"
        repo_dir = runtime_dir / "hermes-agent-src"
        venv_dir = runtime_dir / "hermes-venv"
        log_path = tmp_path / "calls.log"
        desired_commit = "1111111111111111111111111111111111111111"
        previous_commit = "2222222222222222222222222222222222222222"

        script = f"""
{snippet}
CALL_LOG={shlex.quote(str(log_path))}
log_call() {{
  printf '%s\\n' "$*" >>"$CALL_LOG"
}}
git() {{
  log_call "git $*"
  local repo_dir=""
  if [[ "${{1:-}}" == "-C" ]]; then
    repo_dir="$2"
    shift 2
  fi
  case "${{1:-}}" in
    clone)
      local target="${{@: -1}}"
      mkdir -p "$target/.git"
      printf '%s\\n' "https://github.com/NousResearch/hermes-agent.git" >"$target/.origin-url"
      printf '%s\\n' "{previous_commit}" >"$target/.head-commit"
      printf '%s\\n' "refs/heads/main" >"$target/.head-ref"
      ;;
    remote)
      case "${{2:-}}" in
        get-url)
          cat "$repo_dir/.origin-url"
          ;;
        add|set-url)
          printf '%s\\n' "${{4:-}}" >"$repo_dir/.origin-url"
          ;;
      esac
      ;;
    rev-parse)
      case "${{2:-}}" in
        --is-shallow-repository)
          printf '%s\\n' "true"
          ;;
        --verify)
          case "${{4:-}}" in
            "{desired_commit}^{{commit}}"|"refs/tags/v-test^{{commit}}")
              printf '%s\\n' "{desired_commit}"
              ;;
            "{previous_commit}^{{commit}}"|"origin/main^{{commit}}"|"refs/remotes/origin/main^{{commit}}")
              printf '%s\\n' "{previous_commit}"
              ;;
            *)
              return 1
              ;;
          esac
          ;;
        HEAD)
          cat "$repo_dir/.head-commit"
          ;;
        *)
          return 1
          ;;
      esac
      ;;
    fetch)
      return 0
      ;;
    symbolic-ref)
      if [[ -f "$repo_dir/.head-ref" ]]; then
        cat "$repo_dir/.head-ref"
        return 0
      fi
      return 1
      ;;
    checkout)
      printf '%s\\n' "${{@: -1}}" >"$repo_dir/.head-commit"
      rm -f "$repo_dir/.head-ref"
      ;;
    *)
      return 1
      ;;
  esac
}}
uv() {{
  log_call "uv $*"
  if [[ "${{1:-}}" == "venv" ]]; then
    local target="$2"
    mkdir -p "$target/bin"
    printf '#!/usr/bin/env bash\\n' >"$target/bin/python3"
    chmod +x "$target/bin/python3"
    return 0
  fi
  if [[ "${{1:-}}" == "pip" && "${{2:-}}" == "install" ]]; then
    local python_bin=""
    shift 2
    while [[ "$#" -gt 0 ]]; do
      if [[ "$1" == "--python" ]]; then
        python_bin="$2"
        shift 2
        continue
      fi
      shift
    done
    if [[ -n "$python_bin" ]]; then
      printf '#!/usr/bin/env bash\\n' >"$(dirname "$python_bin")/hermes"
      chmod +x "$(dirname "$python_bin")/hermes"
    fi
    return 0
  fi
  return 0
}}
ensure_uv() {{ :; }}
resolve_shared_runtime_seed_python() {{ printf '%s\\n' /usr/bin/python3; }}
shared_runtime_python_is_share_safe() {{ return 0; }}
runtime_python_has_pip() {{ return 0; }}
ensure_hermes_dashboard_assets() {{ log_call "ensure_hermes_dashboard_assets $1"; }}
sync_hermes_dashboard_assets_into_runtime() {{ log_call "sync_hermes_dashboard_assets_into_runtime $1 $2"; }}
RUNTIME_DIR={shlex.quote(str(runtime_dir))}
ALMANAC_HERMES_AGENT_REF={desired_commit}
ensure_shared_hermes_runtime
printf 'HEAD=%s\\n' "$(cat {shlex.quote(str(repo_dir / '.head-commit'))})"
printf 'HAS_HERMES=%s\\n' "$(test -x {shlex.quote(str(venv_dir / 'bin' / 'hermes'))} && printf yes || printf no)"
cat "$CALL_LOG"
"""
        result = bash(script)
        expect(result.returncode == 0, f"shared runtime pin case failed: {result.stderr}")
        expect(f"HEAD={desired_commit}" in result.stdout, result.stdout)
        expect("HAS_HERMES=yes" in result.stdout, result.stdout)
        expect(
            f"git clone https://github.com/NousResearch/hermes-agent.git {repo_dir}" in result.stdout,
            result.stdout,
        )
        expect(
            f"git -C {repo_dir} fetch --tags --force --unshallow origin" in result.stdout,
            result.stdout,
        )
        expect(
            f"git -C {repo_dir} checkout --force --detach {desired_commit}" in result.stdout,
            result.stdout,
        )
        expect(
            f"uv pip install --python {venv_dir / 'bin' / 'python3'} --reinstall {repo_dir}[cli,mcp,messaging,cron,web]"
            in result.stdout,
            result.stdout,
        )
    print("PASS test_ensure_shared_hermes_runtime_checks_out_requested_ref_and_reinstalls")


def main() -> int:
    test_shared_runtime_pin_is_exposed_and_no_longer_floats()
    test_ensure_shared_hermes_runtime_checks_out_requested_ref_and_reinstalls()
    print("PASS all 2 hermes runtime pin regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
