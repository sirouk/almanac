#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _section_between(body: str, start: str, end: str) -> str:
    try:
        start_index = body.index(start)
        end_index = body.index(end, start_index)
    except ValueError as exc:
        raise AssertionError(f"missing documentation section boundary: {exc}") from exc
    return body[start_index:end_index]


def test_agents_service_user_unit_list_matches_templates() -> None:
    body = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    section = _section_between(
        body,
        "Main service-user units installed for the Almanac service user:",
        "Whether Curator uses onboarding services",
    )
    documented_units = set(re.findall(r"\balmanac-[a-z0-9-]+\.(?:service|timer|path)\b", section))
    template_units = {path.name for path in (REPO / "systemd" / "user").iterdir() if path.is_file()}
    expect(
        documented_units == template_units,
        f"AGENTS.md service-user unit list drifted.\nmissing={sorted(template_units - documented_units)}\nextra={sorted(documented_units - template_units)}",
    )
    print("PASS test_agents_service_user_unit_list_matches_templates")


def test_org_profile_docs_mark_cli_as_shipped_contract() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    org_doc = (REPO / "docs" / "org-profile.md").read_text(encoding="utf-8")
    ctl = (REPO / "python" / "almanac_ctl.py").read_text(encoding="utf-8")
    expect('subparsers.add_parser("org-profile")' in ctl, "org-profile CLI should be implemented")
    expect("`almanac-ctl org-profile`" in readme and "validate,\npreview, apply, and doctor workflow" in readme, readme)
    expect("The commands and receipts below are the shipped operator contract." in org_doc, org_doc)
    print("PASS test_org_profile_docs_mark_cli_as_shipped_contract")


def main() -> int:
    test_agents_service_user_unit_list_matches_templates()
    test_org_profile_docs_mark_cli_as_shipped_contract()
    print("PASS all 2 documentation truth tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
