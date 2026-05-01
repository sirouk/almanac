#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
FOUNDATION_DOC = REPO / "docs" / "arclink" / "foundation.md"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_access():
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    path = PYTHON_DIR / "arclink_access.py"
    spec = importlib.util.spec_from_file_location("arclink_access_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["arclink_access_test"] = module
    spec.loader.exec_module(module)
    return module


def test_nextcloud_isolation_decision_is_documented_and_test_pinned() -> None:
    access = load_access()
    doc = FOUNDATION_DOC.read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())
    expect(access.arclink_nextcloud_isolation_model() == "dedicated_per_deployment", access.arclink_nextcloud_isolation_model())
    expect("ARCLINK_NEXTCLOUD_ISOLATION_MODEL=dedicated_per_deployment" in doc, doc)
    expect("dedicated Nextcloud instance and data volume for each deployment" in normalized_doc, doc)
    print("PASS test_nextcloud_isolation_decision_is_documented_and_test_pinned")


def test_ssh_access_strategy_rejects_raw_ssh_over_http_advertising() -> None:
    access = load_access()
    record = access.build_arclink_ssh_access_record(username="dep_user", hostname="ssh-abc.example.test")
    expect(record.strategy == "cloudflare_access_tcp", str(record))
    expect(record.command_hint.startswith("cloudflared access ssh"), str(record))
    for kwargs in (
        {"username": "dep_user", "hostname": "ssh-abc.example.test", "strategy": "raw_http"},
        {"username": "dep_user", "hostname": "https://ssh-abc.example.test"},
    ):
        try:
            access.build_arclink_ssh_access_record(**kwargs)
        except access.ArcLinkAccessError as exc:
            expect("HTTP" in str(exc) or "http" in str(exc), str(exc))
        else:
            raise AssertionError(f"expected SSH HTTP advertisement to fail for {kwargs}")
    print("PASS test_ssh_access_strategy_rejects_raw_ssh_over_http_advertising")


def main() -> int:
    test_nextcloud_isolation_decision_is_documented_and_test_pinned()
    test_ssh_access_strategy_rejects_raw_ssh_over_http_advertising()
    print("PASS all 2 ArcLink access tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
