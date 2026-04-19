#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BOOTSTRAP_USERLAND = REPO / "bin" / "bootstrap-userland.sh"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_bootstrap_userland_passes_upstream_repo_url_to_vault_reconciler() -> None:
    text = BOOTSTRAP_USERLAND.read_text(encoding="utf-8")
    expect("--repo-url \"${ALMANAC_UPSTREAM_REPO_URL:-}\"" in text, text)
    print("PASS test_bootstrap_userland_passes_upstream_repo_url_to_vault_reconciler")


def main() -> int:
    test_bootstrap_userland_passes_upstream_repo_url_to_vault_reconciler()
    print("PASS all 1 bootstrap-userland regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
