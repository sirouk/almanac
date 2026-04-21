#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
QMD_SKILL = REPO / "skills" / "almanac-qmd-mcp" / "SKILL.md"
FIRST_CONTACT_SKILL = REPO / "skills" / "almanac-first-contact" / "SKILL.md"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_qmd_skill_includes_literal_mcp_recipe() -> None:
    body = QMD_SKILL.read_text(encoding="utf-8")
    expect('"method":"tools/call"' in body, body)
    expect('"name":"query"' in body, body)
    expect('"collections":["vault"]' in body, body)
    expect("tools/list" in body, body)
    expect("mcp-session-id" in body, body)
    expect("query" in body and "get" in body and "multi_get" in body and "status" in body, body)
    expect("combining `lex` and `vec` searches" in body, body)
    expect("structuredContent" in body, body)
    print("PASS test_qmd_skill_includes_literal_mcp_recipe")


def test_first_contact_skill_requires_real_qmd_probe() -> None:
    body = FIRST_CONTACT_SKILL.read_text(encoding="utf-8")
    expect("real qmd `tools/call` probe" in body, body)
    expect("qmd probe record" in body, body)
    print("PASS test_first_contact_skill_requires_real_qmd_probe")


def main() -> int:
    test_qmd_skill_includes_literal_mcp_recipe()
    test_first_contact_skill_requires_real_qmd_probe()
    print("PASS all 2 qmd skill text regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
