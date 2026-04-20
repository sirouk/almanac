#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BOOTSTRAP_USERLAND_SH = REPO / "bin" / "bootstrap-userland.sh"
BOOTSTRAP_SYSTEM_SH = REPO / "bin" / "bootstrap-system.sh"
COMMON_SH = REPO / "bin" / "common.sh"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def extract(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def test_install_uv_if_missing_keeps_uv_current_and_installs_python_312() -> None:
    text = BOOTSTRAP_USERLAND_SH.read_text(encoding="utf-8")
    snippet = extract(text, "install_uv_if_missing() {", "install_node_if_missing() {")
    expect("uv self update" in snippet, f"expected uv self update in install_uv_if_missing, got: {snippet!r}")
    expect("uv python install 3.12" in snippet, f"expected uv python install 3.12 in install_uv_if_missing, got: {snippet!r}")
    expect("uv python install 3.11" in snippet, f"expected Python 3.11 fallback in install_uv_if_missing, got: {snippet!r}")
    print("PASS test_install_uv_if_missing_keeps_uv_current_and_installs_python_312")


def test_bootstrap_userland_passes_upstream_repo_url_to_vault_reconciler() -> None:
    text = BOOTSTRAP_USERLAND_SH.read_text(encoding="utf-8")
    expect("--repo-url \"${ALMANAC_UPSTREAM_REPO_URL:-}\"" in text, text)
    print("PASS test_bootstrap_userland_passes_upstream_repo_url_to_vault_reconciler")


def test_shared_runtime_creation_seeds_pip_and_repairs_pipless_envs() -> None:
    text = COMMON_SH.read_text(encoding="utf-8")
    runtime_has_pip = extract(text, "runtime_python_has_pip() {", "resolve_shared_runtime_seed_python() {")
    shared_runtime = extract(text, "ensure_shared_hermes_runtime() {", "ensure_hermes_dashboard_assets() {")
    expect("\"$python_bin\" -m pip --version" in runtime_has_pip, "expected runtime_python_has_pip helper to probe pip availability")
    expect("elif ! runtime_python_has_pip \"$venv_dir/bin/python3\"" in shared_runtime, "expected shared runtime to rebuild when pip is missing")
    expect("uv venv \"$venv_dir\" --python \"$seed_python\" --seed" in shared_runtime, "expected shared runtime venv to be created with --seed")
    print("PASS test_shared_runtime_creation_seeds_pip_and_repairs_pipless_envs")


def test_system_bootstrap_installs_espeak_ng_for_neutts() -> None:
    text = BOOTSTRAP_SYSTEM_SH.read_text(encoding="utf-8")
    expect("espeak-ng" in text, f"expected espeak-ng in bootstrap-system apt packages, got: {text!r}")
    print("PASS test_system_bootstrap_installs_espeak_ng_for_neutts")


def main() -> int:
    test_install_uv_if_missing_keeps_uv_current_and_installs_python_312()
    test_bootstrap_userland_passes_upstream_repo_url_to_vault_reconciler()
    test_shared_runtime_creation_seeds_pip_and_repairs_pipless_envs()
    test_system_bootstrap_installs_espeak_ng_for_neutts()
    print("PASS all 4 bootstrap-userland regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
