#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"


def load_module(path: Path, name: str):
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def expect(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(str(message))


def write_config(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"{key}={json.dumps(value)}" for key, value in values.items()) + "\n", encoding="utf-8")


def insert_agent(conn: sqlite3.Connection, *, agent_id: str, unix_user: str, display_name: str, hermes_home: Path, now: str) -> None:
    conn.execute(
        """
        INSERT INTO agents (
          agent_id, role, unix_user, display_name, status, hermes_home, manifest_path,
          archived_state_path, model_preset, model_string, channels_json,
          allowed_mcps_json, home_channel_json, operator_notify_channel_json,
          notes, created_at, last_enrolled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            agent_id,
            "user",
            unix_user,
            display_name,
            "active",
            str(hermes_home),
            str(hermes_home.parent / "manifest.json"),
            None,
            "codex",
            "openai-codex:gpt-5.5",
            json.dumps(["tui-only"]),
            json.dumps([]),
            json.dumps({"platform": "tui", "channel_id": ""}),
            json.dumps({}),
            "",
            now,
            now,
        ),
    )
    conn.commit()


def test_ultimate_example_profile_applies_to_state_vault_and_agent_memory() -> None:
    control = load_module(REPO / "python" / "almanac_control.py", "almanac_control_org_profile_test")
    org_profile = load_module(REPO / "python" / "almanac_org_profile.py", "almanac_org_profile_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        values = {
            "ALMANAC_USER": "almanac",
            "ALMANAC_HOME": str(root / "home-almanac"),
            "ALMANAC_REPO_DIR": str(REPO),
            "ALMANAC_PRIV_DIR": str(root / "priv"),
            "STATE_DIR": str(root / "state"),
            "RUNTIME_DIR": str(root / "state" / "runtime"),
            "VAULT_DIR": str(root / "vault"),
            "ALMANAC_DB_PATH": str(root / "state" / "almanac-control.sqlite3"),
            "ALMANAC_AGENTS_STATE_DIR": str(root / "state" / "agents"),
            "ALMANAC_CURATOR_DIR": str(root / "state" / "curator"),
            "ALMANAC_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
            "ALMANAC_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
            "ALMANAC_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
            "ALMANAC_RELEASE_STATE_FILE": str(root / "state" / "almanac-release.json"),
            "ALMANAC_QMD_URL": "http://127.0.0.1:8181/mcp",
            "ALMANAC_MCP_HOST": "127.0.0.1",
            "ALMANAC_MCP_PORT": "8282",
        }
        write_config(config_path, values)

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            now = control.utc_now_iso()
            alex_home = root / "home-alex" / ".local" / "share" / "almanac-agent" / "hermes-home"
            ren_home = root / "home-ren" / ".local" / "share" / "almanac-agent" / "hermes-home"
            alex_home.mkdir(parents=True)
            ren_home.mkdir(parents=True)
            insert_agent(conn, agent_id="agent-alex", unix_user="alex", display_name="Atlas", hermes_home=alex_home, now=now)
            insert_agent(conn, agent_id="agent-ren", unix_user="ren", display_name="Quill", hermes_home=ren_home, now=now)

            source_path = REPO / "config" / "org-profile.ultimate.example.yaml"
            profile = org_profile.load_profile(source_path)
            validation = org_profile.validate_profile(profile, cfg)
            expect(validation["valid"], validation)
            expect(validation["errors"] == [], validation)
            expect(any("source-packet" in warning for warning in validation["warnings"]), validation["warnings"])

            applied = org_profile.apply_profile(conn, cfg, profile=profile, source_path=source_path, actor="test")
            expect(applied["applied"], applied)
            expect({row["agent_id"] for row in applied["matched_agents"]} == {"agent-alex", "agent-ren"}, applied)
            generated_doc = Path(applied["generated_vault_doc"])
            expect(generated_doc.is_file(), generated_doc)
            generated_body = generated_doc.read_text(encoding="utf-8")
            expect("Prototype agent: atlas-prototype" in generated_body, generated_body[:1000])
            expect("discord_user_id" not in generated_body, generated_body)

            payload = control.build_managed_memory_payload(conn, cfg, agent_id="agent-alex")
            expect("Operating profile:" in payload["org-profile"], payload["org-profile"])
            expect("Human served: Alex Rivera" in payload["user-responsibilities"], payload["user-responsibilities"])
            expect("Team map:" in payload["team-map"], payload["team-map"])
            expect(payload["org_profile_agent_context"]["person_id"] == "alex-rivera", payload["org_profile_agent_context"])

            paths = control.write_managed_memory_stubs(hermes_home=alex_home, payload=payload)
            expect(paths["changed"], paths)
            identity = json.loads((alex_home / "state" / "almanac-identity-context.json").read_text(encoding="utf-8"))
            expect(identity["person_id"] == "alex-rivera", identity)
            expect(identity["github"]["username"] == "alex-example", identity)
            expect(identity["contact"]["discord_handle"] == "alex-rivera.example", identity)
            soul = (alex_home / "SOUL.md").read_text(encoding="utf-8")
            expect("Almanac operating-profile overlay:" in soul, soul)
            memory = (alex_home / "memories" / "MEMORY.md").read_text(encoding="utf-8")
            expect("[managed:org-profile]" in memory, memory)
            expect("[managed:user-responsibilities]" in memory, memory)
            expect("[managed:team-map]" in memory, memory)
            expect("Discord handle: alex-rivera.example" in memory, memory)
            expect("Repo: northstar-demo/almanac-demo" in memory, memory)
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    print("PASS test_ultimate_example_profile_applies_to_state_vault_and_agent_memory")


def test_human_owner_modules_and_seed_checksums_are_distributed() -> None:
    org_profile = load_module(REPO / "python" / "almanac_org_profile.py", "almanac_org_profile_modules_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        vault_dir = root / "vault"
        seed_path = vault_dir / "Seeds" / "source.md"
        seed_path.parent.mkdir(parents=True)
        seed_path.write_text("# Source\n\nNon-secret source packet.\n", encoding="utf-8")
        checksum = org_profile.hashlib.sha256(seed_path.read_bytes()).hexdigest()
        cfg = SimpleNamespace(vault_dir=vault_dir, private_dir=root / "priv", state_dir=root / "state")
        profile = {
            "version": 1,
            "organization": {
                "id": "example-context",
                "name": "Example Context",
                "profile_kind": "project_collective",
                "mission": "Keep the project operating profile coherent.",
            },
            "roles": {
                "operator": {
                    "description": "Owns the profile.",
                }
            },
            "people": [
                {
                    "id": "alex",
                    "display_name": "Alex",
                    "role": "operator",
                    "unix_user": "alex",
                    "agent": {
                        "name": "Atlas",
                        "purpose": "Help Alex operate the profile.",
                        "serves": "alex",
                    },
                }
            ],
            "agent_lineage": {
                "purpose": "Compose agents from baseline, function layers, owner modules, and explicit onboarding preferences.",
                "prototype_agent": "atlas-prototype",
                "baseline": {
                    "doctrine": ["Use the structured profile as the authority."],
                },
                "department_modules": [
                    {"id": "operator", "name": "Operator module", "applies_to": ["operator"]},
                ],
                "function_modules": [
                    {"id": "profile-ingestion", "name": "Profile ingestion module", "applies_to": ["alex"]},
                ],
                "human_owner_modules": [
                    {"id": "alex-owner", "name": "Alex owner module", "serves": "alex"},
                ],
                "agent_modules": [
                    {"id": "atlas-agent", "name": "Atlas agent module", "serves": "alex"},
                ],
                "seed_sources": [
                    {
                        "id": "source-packet",
                        "path": "Seeds/source.md",
                        "purpose": "Canonical non-secret seed packet.",
                        "canonical_initial_seed": True,
                        "expected_sha256": checksum,
                    }
                ],
            },
        }
        validation = org_profile.validate_profile(profile, cfg)
        expect(validation["valid"], validation)
        preview = org_profile.preview_payload(profile, cfg=cfg, source_path=root / "org-profile.yaml")
        expect(preview["lineage"]["human_owner_modules"] == ["alex-owner"], preview["lineage"])
        preview_text = org_profile.format_preview(preview)
        expect("Human owner modules: alex-owner" in preview_text, preview_text)
        expect("source-packet: Seeds/source.md canonical sha256:set" in preview_text, preview_text)
        context = org_profile.agent_context_for_person(profile, profile["people"][0], agent_id="agent-alex")
        expect(
            [module["id"] for module in context["modules"]] == [
                "operator",
                "profile-ingestion",
                "alex-owner",
                "atlas-agent",
            ],
            context["modules"],
        )
        render = org_profile.render_vault_profile(profile)
        expect("alex-owner: Alex owner module" in render, render)

        bad_profile = json.loads(json.dumps(profile))
        bad_profile["agent_lineage"]["seed_sources"][0]["expected_sha256"] = "0" * 64
        bad_validation = org_profile.validate_profile(bad_profile, cfg)
        expect(not bad_validation["valid"], bad_validation)
        expect(any("expected_sha256 mismatch" in error for error in bad_validation["errors"]), bad_validation)

    print("PASS test_human_owner_modules_and_seed_checksums_are_distributed")


def test_explicit_identity_profile_link_orients_arbitrary_agent_names() -> None:
    control = load_module(REPO / "python" / "almanac_control.py", "almanac_control_org_profile_identity_test")
    org_profile = load_module(REPO / "python" / "almanac_org_profile.py", "almanac_org_profile_identity_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        values = {
            "ALMANAC_USER": "almanac",
            "ALMANAC_HOME": str(root / "home-almanac"),
            "ALMANAC_REPO_DIR": str(REPO),
            "ALMANAC_PRIV_DIR": str(root / "priv"),
            "STATE_DIR": str(root / "state"),
            "RUNTIME_DIR": str(root / "state" / "runtime"),
            "VAULT_DIR": str(root / "vault"),
            "ALMANAC_DB_PATH": str(root / "state" / "almanac-control.sqlite3"),
            "ALMANAC_AGENTS_STATE_DIR": str(root / "state" / "agents"),
            "ALMANAC_CURATOR_DIR": str(root / "state" / "curator"),
            "ALMANAC_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
            "ALMANAC_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
            "ALMANAC_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
            "ALMANAC_RELEASE_STATE_FILE": str(root / "state" / "almanac-release.json"),
            "ALMANAC_QMD_URL": "http://127.0.0.1:8181/mcp",
            "ALMANAC_MCP_HOST": "127.0.0.1",
            "ALMANAC_MCP_PORT": "8282",
        }
        write_config(config_path, values)

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            now = control.utc_now_iso()
            hermes_home = root / "home-random" / ".local" / "share" / "almanac-agent" / "hermes-home"
            hermes_home.mkdir(parents=True)
            insert_agent(
                conn,
                agent_id="agent-random",
                unix_user="randomlane",
                display_name="My Own Bot Name",
                hermes_home=hermes_home,
                now=now,
            )
            control.upsert_agent_identity(
                conn,
                agent_id="agent-random",
                unix_user="randomlane",
                org_profile_person_id="alex-rivera",
                human_display_name="A user-provided name",
                agent_name="My Own Bot Name",
            )

            source_path = REPO / "config" / "org-profile.ultimate.example.yaml"
            profile = org_profile.load_profile(source_path)
            applied = org_profile.apply_profile(conn, cfg, profile=profile, source_path=source_path, actor="test")
            expect(applied["applied"], applied)
            expect(applied["matched_agents"][0]["person_id"] == "alex-rivera", applied)

            payload = control.build_managed_memory_payload(conn, cfg, agent_id="agent-random")
            expect(payload["org_profile_agent_context"]["person_id"] == "alex-rivera", payload["org_profile_agent_context"])
            paths = control.write_managed_memory_stubs(hermes_home=hermes_home, payload=payload)
            expect(paths["changed"], paths)
            identity = json.loads((hermes_home / "state" / "almanac-identity-context.json").read_text(encoding="utf-8"))
            expect(identity["person_id"] == "alex-rivera", identity)
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    print("PASS test_explicit_identity_profile_link_orients_arbitrary_agent_names")


def main() -> int:
    test_ultimate_example_profile_applies_to_state_vault_and_agent_memory()
    test_human_owner_modules_and_seed_checksums_are_distributed()
    test_explicit_identity_profile_link_orients_arbitrary_agent_names()
    print("PASS all 3 org-profile tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
