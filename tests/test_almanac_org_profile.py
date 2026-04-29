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
            state_payload = json.loads((alex_home / "state" / "almanac-vault-reconciler.json").read_text(encoding="utf-8"))
            expect("Operating profile:" in state_payload["org-profile"], state_payload)
            expect("Human served: Alex Rivera" in state_payload["user-responsibilities"], state_payload)
            expect("Team map:" in state_payload["team-map"], state_payload)
            expect("Discord handle: alex-rivera.example" in state_payload["user-responsibilities"], state_payload)
            expect("Repo: northstar-demo/almanac-demo" in state_payload["user-responsibilities"], state_payload)
            expect(not (alex_home / "memories" / "MEMORY.md").exists(), "managed context should not be written into MEMORY.md")
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


def test_agent_identity_rejects_duplicate_org_profile_person_links() -> None:
    control = load_module(REPO / "python" / "almanac_control.py", "almanac_control_duplicate_profile_link_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(
            config_path,
            {
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
            },
        )
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            control.upsert_agent_identity(conn, agent_id="agent-one", unix_user="one", org_profile_person_id="alex")
            try:
                control.upsert_agent_identity(conn, agent_id="agent-two", unix_user="two", org_profile_person_id="alex")
            except ValueError as exc:
                expect("already linked" in str(exc), str(exc))
            else:
                raise AssertionError("expected duplicate org_profile_person_id to fail")
        finally:
            os.environ.clear()
            os.environ.update(old_env)
    print("PASS test_agent_identity_rejects_duplicate_org_profile_person_links")


def test_builder_starter_profile_covers_operational_rails() -> None:
    org_profile = load_module(REPO / "python" / "almanac_org_profile.py", "almanac_org_profile_builder_profile_test")
    builder = load_module(REPO / "python" / "almanac_org_profile_builder.py", "almanac_org_profile_builder_test")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "org-profile.yaml"
        profile = builder.profile_starter()
        validation = org_profile.validate_profile(profile)
        expect(validation["valid"], validation)
        expect(profile["authority"]["global_requires_approval"], profile["authority"])
        expect(profile["identity_verification"]["safe_roster_prompt"] is True, profile["identity_verification"])
        expect(profile["distribution"]["managed_memory_sections"] == ["org-profile", "user-responsibilities", "team-map"], profile["distribution"])
        expect(profile["workflows"][0]["id"] == "profile-ingestion", profile["workflows"])
        expect(profile["automations"][0]["id"] == "profile-doctor", profile["automations"])
        expect(profile["benchmarks"][0]["id"] == "orientation-baseline", profile["benchmarks"])
        profile["organization"]["name"] = "Cafe \u5bb6"

        builder.write_profile(path, profile)
        expect(path.is_file(), path)
        expect((path.stat().st_mode & 0o777) == 0o600, oct(path.stat().st_mode))
        body = path.read_text(encoding="utf-8")
        expect("Cafe \u5bb6" in body, body)
        loaded = org_profile.load_profile(path)
        context = org_profile.agent_context_for_person(loaded, loaded["people"][0], agent_id="agent-example")
        expect(context["workflows"][0]["id"] == "profile-ingestion", context)
        expect(context["automations"][0]["id"] == "profile-doctor", context)
        expect(context["benchmarks"][0]["id"] == "orientation-baseline", context)

    print("PASS test_builder_starter_profile_covers_operational_rails")


def test_generated_vault_render_path_is_vault_relative_and_source_display_sanitized() -> None:
    org_profile = load_module(REPO / "python" / "almanac_org_profile.py", "almanac_org_profile_path_safety_test")
    builder = load_module(REPO / "python" / "almanac_org_profile_builder.py", "almanac_org_profile_path_builder_test")
    profile = builder.profile_starter()
    validation = org_profile.validate_profile(profile)
    expect(validation["valid"], validation)

    absolute_profile = json.loads(json.dumps(profile))
    absolute_profile.setdefault("work_surfaces", {}).setdefault("vault", {})["generated_org_profile_path"] = "/tmp/org-profile.md"
    absolute_validation = org_profile.validate_profile(absolute_profile)
    expect(not absolute_validation["valid"], absolute_validation)
    expect(any("must be relative" in error for error in absolute_validation["errors"]), absolute_validation)

    traversal_profile = json.loads(json.dumps(profile))
    traversal_profile.setdefault("work_surfaces", {}).setdefault("vault", {})["generated_org_profile_path"] = "../outside.md"
    traversal_validation = org_profile.validate_profile(traversal_profile)
    expect(not traversal_validation["valid"], traversal_validation)
    expect(any("must not traverse" in error for error in traversal_validation["errors"]), traversal_validation)

    rendered = org_profile.render_vault_profile(
        profile,
        source_path=Path("/home/example/almanac/almanac-priv/config/org-profile.yaml"),
    )
    expect("<private>/config/org-profile.yaml" in rendered, rendered)
    expect("/home/example" not in rendered, rendered)

    public_rendered = org_profile.render_vault_profile(
        profile,
        source_path=REPO / "config" / "org-profile.ultimate.example.yaml",
    )
    expect("config/org-profile.ultimate.example.yaml" in public_rendered, public_rendered)

    print("PASS test_generated_vault_render_path_is_vault_relative_and_source_display_sanitized")


def test_org_profile_rejects_ambiguous_identity_match_tokens() -> None:
    org_profile = load_module(REPO / "python" / "almanac_org_profile.py", "almanac_org_profile_duplicate_identity_test")
    profile = {
        "version": 1,
        "organization": {"id": "example", "name": "Example", "profile_kind": "organization", "mission": "Operate."},
        "roles": {"operator": {"description": "Operator"}},
        "people": [
            {"id": "alex-one", "display_name": "Alex", "role": "operator", "unix_user": "alex", "agent": {"name": "Guide"}},
            {"id": "alex-two", "display_name": "Alex", "role": "operator", "unix_user": "alex", "agent": {"name": "Guide Two"}},
        ],
    }
    validation = org_profile.validate_profile(profile)
    expect(not validation["valid"], validation)
    expect(any("duplicate people unix_user values" in error for error in validation["errors"]), validation)
    expect(any("duplicate people/agent exact-match identity labels" in warning for warning in validation["warnings"]), validation)

    safe_profile = {
        **profile,
        "people": [
            {"id": "alex-one", "display_name": "Alex", "role": "operator", "unix_user": "alex1", "agent": {"name": "Guide", "purpose": "Assist Alex."}},
            {"id": "alex-two", "display_name": "Alex", "role": "operator", "unix_user": "alex2", "agent": {"name": "Guide Two", "purpose": "Assist Alex."}},
        ],
    }
    validation = org_profile.validate_profile(safe_profile)
    expect(validation["valid"], validation)
    expect(any("duplicate people/agent exact-match identity labels" in warning for warning in validation["warnings"]), validation)
    expect(
        org_profile._match_person_for_agent(safe_profile, display_name="Alex") is None,
        "ambiguous display-name labels should not auto-bind an agent",
    )
    print("PASS test_org_profile_rejects_ambiguous_identity_match_tokens")


def test_org_profile_shared_vault_render_omits_people_when_policy_is_group_visible() -> None:
    org_profile = load_module(REPO / "python" / "almanac_org_profile.py", "almanac_org_profile_render_privacy_test")
    profile = org_profile.load_profile(REPO / "config" / "org-profile.ultimate.example.yaml")
    rendered = org_profile.render_vault_profile(profile)
    expect("Prototype agent: atlas-prototype" in rendered, rendered[:1000])
    expect("Alex Rivera" not in rendered, rendered)
    expect("alex-example" not in rendered, rendered)
    expect("People represented:" in rendered, rendered)
    print("PASS test_org_profile_shared_vault_render_omits_people_when_policy_is_group_visible")


def test_managed_memory_preserves_durable_org_profile_overlay_when_unmatched() -> None:
    control = load_module(REPO / "python" / "almanac_control.py", "almanac_control_clear_org_profile_test")
    org_profile = load_module(REPO / "python" / "almanac_org_profile.py", "almanac_org_profile_clear_overlay_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        hermes_home = root / "hermes-home"
        hermes_home.mkdir(parents=True)
        context = {
            "revision": "old",
            "person_id": "alex",
            "human_display_name": "Alex",
            "role_id": "operator",
            "teams": [],
            "organization": {"name": "Example", "profile_kind": "organization", "mission": "Operate."},
            "agent": {"name": "Atlas", "purpose": "Help Alex."},
        }
        org_profile.materialize_agent_context(hermes_home, context)
        payload = {
            "agent_id": "agent-alex",
            "almanac-skill-ref": "",
            "vault-ref": "Vault root: /vault",
            "resource-ref": "",
            "qmd-ref": "qmd",
            "notion-ref": "",
            "vault-topology": "",
            "recall-stubs": "",
            "notion-stub": "",
            "today-plate": "",
            "vault_path_contract": "user-home-almanac-v1",
            "catalog": [],
            "subscriptions": [],
        }
        paths = control.write_managed_memory_stubs(hermes_home=hermes_home, payload=payload)
        expect(paths["changed"], paths)
        state_payload = json.loads((hermes_home / "state" / "almanac-vault-reconciler.json").read_text(encoding="utf-8"))
        expect(state_payload["org_profile_agent_context"] == {}, state_payload)
        expect((hermes_home / "state" / "almanac-org-profile-context.json").exists(), paths)
        identity = json.loads((hermes_home / "state" / "almanac-identity-context.json").read_text(encoding="utf-8"))
        expect(identity["person_id"] == "alex", identity)
        soul = (hermes_home / "SOUL.md").read_text(encoding="utf-8")
        expect("Almanac operating-profile overlay" in soul, soul)
    print("PASS test_managed_memory_preserves_durable_org_profile_overlay_when_unmatched")


def main() -> int:
    test_ultimate_example_profile_applies_to_state_vault_and_agent_memory()
    test_human_owner_modules_and_seed_checksums_are_distributed()
    test_explicit_identity_profile_link_orients_arbitrary_agent_names()
    test_agent_identity_rejects_duplicate_org_profile_person_links()
    test_builder_starter_profile_covers_operational_rails()
    test_generated_vault_render_path_is_vault_relative_and_source_display_sanitized()
    test_org_profile_rejects_ambiguous_identity_match_tokens()
    test_org_profile_shared_vault_render_omits_people_when_policy_is_group_visible()
    test_managed_memory_preserves_durable_org_profile_overlay_when_unmatched()
    print("PASS all 9 org-profile tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
