#!/usr/bin/env python3
"""Tests for python/arclink_skill_enablement.py - the per-agent application
lane for central skill enablement intents (Plan section 3, step 3).

Locks in:
  - approved + locally discoverable skills are removed from config.yaml
    skills.disabled with targeted line surgery (no YAML re-dump);
  - undiscoverable skills stay untouched and report ``missing`` (fail closed);
  - skills.platform_disabled and unrelated config lines are preserved
    byte-for-byte;
  - a receipt is written with effective_at=next_session;
  - the lane is a no-op without staged intents.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_module():
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    path = PYTHON_DIR / "arclink_skill_enablement.py"
    spec = importlib.util.spec_from_file_location("arclink_skill_enablement_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["arclink_skill_enablement_test"] = module
    spec.loader.exec_module(module)
    return module


_CONFIG_TEMPLATE = """# agent config
model:
  default: example:model
skills:
  # operator notes stay intact
  disabled:
  - retrieval-and-cite
  - user-disabled-skill
  platform_disabled:
    discord:
    - retrieval-and-cite
  external_dirs:
  - {external_dir}
plugins:
  disabled: []
"""


def _seed_home(tmp: Path, *, with_intents: bool = True) -> Path:
    hermes_home = tmp / "hermes-home"
    (hermes_home / "state").mkdir(parents=True)
    (hermes_home / "skills").mkdir()
    external_dir = tmp / "fleet-skills"
    (external_dir / "retrieval-and-cite").mkdir(parents=True)
    (hermes_home / "config.yaml").write_text(
        _CONFIG_TEMPLATE.format(external_dir=external_dir),
        encoding="utf-8",
    )
    if with_intents:
        intents = [
            {
                "kind": "approved_skill_intent",
                "source_id": "src-1",
                "skill_id": "retrieval-and-cite",
                "review_status": "approved",
            },
            {
                "kind": "approved_skill_intent",
                "source_id": "src-2",
                "skill_id": "not-installed-anywhere",
                "review_status": "approved",
            },
        ]
        (hermes_home / "state" / "arclink-academy-approved-skills.json").write_text(
            json.dumps(intents, indent=2) + "\n", encoding="utf-8"
        )
    return hermes_home


def test_parse_skills_config_reads_disabled_and_external_dirs() -> None:
    mod = load_module()
    parsed = mod.parse_skills_config(_CONFIG_TEMPLATE.format(external_dir="/tmp/x"))
    expect(parsed["disabled"] == ["retrieval-and-cite", "user-disabled-skill"], str(parsed))
    expect(parsed["external_dirs"] == ["/tmp/x"], str(parsed))
    expect(mod.parse_skills_config("model:\n  default: x\n") == {"disabled": [], "external_dirs": []}, "missing skills block must parse empty")
    print("PASS test_parse_skills_config_reads_disabled_and_external_dirs")


def test_remove_skills_from_disabled_is_surgical() -> None:
    mod = load_module()
    text = _CONFIG_TEMPLATE.format(external_dir="/tmp/x")
    new_text, removed = mod.remove_skills_from_disabled(text, {"retrieval-and-cite"})
    expect(removed == ["retrieval-and-cite"], str(removed))
    expect("  - user-disabled-skill" in new_text, new_text)
    # platform_disabled entries are untouched even with the same skill name.
    expect("    - retrieval-and-cite" in new_text, new_text)
    expect("# operator notes stay intact" in new_text, new_text)
    expect("# agent config" in new_text, new_text)
    # No-op when nothing matches: byte-identical text.
    same_text, removed_none = mod.remove_skills_from_disabled(text, {"absent-skill"})
    expect(same_text == text and removed_none == [], "no-match removal must not rewrite config")
    print("PASS test_remove_skills_from_disabled_is_surgical")


def test_apply_skill_enablement_enables_discoverable_skills_and_fails_closed() -> None:
    mod = load_module()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        hermes_home = _seed_home(tmp)
        receipt = mod.apply_skill_enablement(hermes_home)
        expect(receipt["status"] == "partial", str(receipt))
        expect(receipt["config_changed"] is True, str(receipt))
        expect(receipt["removed_from_disabled"] == ["retrieval-and-cite"], str(receipt))
        by_skill = {entry["skill_id"]: entry for entry in receipt["skills"]}
        expect(by_skill["retrieval-and-cite"]["status"] == "enabled", str(receipt))
        expect(by_skill["not-installed-anywhere"]["status"] == "missing", str(receipt))
        config_text = (hermes_home / "config.yaml").read_text(encoding="utf-8")
        expect("\n  - retrieval-and-cite\n" not in config_text, config_text)
        expect("\n  - user-disabled-skill\n" in config_text, config_text)
        expect("\n    - retrieval-and-cite\n" in config_text, "platform_disabled must stay untouched")
        # Second run: already enabled, config untouched.
        second = mod.apply_skill_enablement(hermes_home)
        expect(second["config_changed"] is False, str(second))
        by_skill = {entry["skill_id"]: entry for entry in second["skills"]}
        expect(by_skill["retrieval-and-cite"]["status"] == "already_enabled", str(second))
    print("PASS test_apply_skill_enablement_enables_discoverable_skills_and_fails_closed")


def test_apply_skill_enablement_without_intents_is_a_noop() -> None:
    mod = load_module()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        hermes_home = _seed_home(tmp, with_intents=False)
        before = (hermes_home / "config.yaml").read_text(encoding="utf-8")
        receipt = mod.apply_skill_enablement(hermes_home)
        expect(receipt["status"] == "no_intents", str(receipt))
        expect(receipt["config_changed"] is False, str(receipt))
        expect((hermes_home / "config.yaml").read_text(encoding="utf-8") == before, "config must be untouched")
    print("PASS test_apply_skill_enablement_without_intents_is_a_noop")


def test_cli_writes_receipt_and_never_fails_the_refresh_lane() -> None:
    mod = load_module()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        hermes_home = _seed_home(tmp)
        rc = mod.main(["--hermes-home", str(hermes_home)])
        expect(rc == 0, f"CLI must exit 0, got {rc}")
        receipt_path = hermes_home / "state" / "arclink-skill-enablement-applied.json"
        expect(receipt_path.is_file(), "receipt must be written")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        expect(receipt["effective_at"] == "next_session", str(receipt))
        # Missing HERMES_HOME is a quiet skip, never an error.
        rc = mod.main(["--hermes-home", str(tmp / "does-not-exist")])
        expect(rc == 0, f"CLI must exit 0 for missing home, got {rc}")
    print("PASS test_cli_writes_receipt_and_never_fails_the_refresh_lane")


def test_unsafe_skill_ids_are_rejected() -> None:
    mod = load_module()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        hermes_home = _seed_home(tmp, with_intents=False)
        (hermes_home / "state" / "arclink-academy-approved-skills.json").write_text(
            json.dumps([{"skill_id": "../escape", "source_id": "src-x"}]) + "\n",
            encoding="utf-8",
        )
        receipt = mod.apply_skill_enablement(hermes_home)
        expect(receipt["skills"] == [], str(receipt))
        expect(any("unsafe skill id" in problem for problem in receipt["problems"]), str(receipt))
        expect(receipt["config_changed"] is False, str(receipt))
    print("PASS test_unsafe_skill_ids_are_rejected")


def test_user_agent_refresh_invokes_enablement_lane() -> None:
    text = (REPO / "bin" / "user-agent-refresh.sh").read_text(encoding="utf-8")
    expect("arclink_skill_enablement.py" in text, "user-agent-refresh must apply skill enablement")
    expect('--hermes-home "$HERMES_HOME"' in text, "enablement must target this agent's HERMES_HOME")
    print("PASS test_user_agent_refresh_invokes_enablement_lane")


def main() -> int:
    test_parse_skills_config_reads_disabled_and_external_dirs()
    test_remove_skills_from_disabled_is_surgical()
    test_apply_skill_enablement_enables_discoverable_skills_and_fails_closed()
    test_apply_skill_enablement_without_intents_is_a_noop()
    test_cli_writes_receipt_and_never_fails_the_refresh_lane()
    test_unsafe_skill_ids_are_rejected()
    test_user_agent_refresh_invokes_enablement_lane()
    print("PASS all 7 skill enablement tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
