#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

import almanac_control as control
import almanac_memory_synthesizer as synth


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_config(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"{key}={json.dumps(value)}" for key, value in values.items()) + "\n", encoding="utf-8")


def base_config(root: Path) -> dict[str, str]:
    return {
        "ALMANAC_USER": "almanac",
        "ALMANAC_HOME": str(root / "home-almanac"),
        "ALMANAC_REPO_DIR": str(root / "repo"),
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
        "ALMANAC_MEMORY_SYNTH_ENABLED": "1",
        "ALMANAC_MEMORY_SYNTH_ENDPOINT": "https://llm.example.test/v1/chat/completions",
        "ALMANAC_MEMORY_SYNTH_MODEL": "vision-model-test",
        "ALMANAC_MEMORY_SYNTH_API_KEY": "test-key",
        "ALMANAC_MEMORY_SYNTH_MAX_SOURCES_PER_RUN": "20",
        "ALMANAC_MEMORY_SYNTH_FAILURE_RETRY_SECONDS": "60",
        "ALMANAC_MODEL_PRESET_CODEX": "openai:codex",
        "ALMANAC_MODEL_PRESET_OPUS": "anthropic:claude-opus",
        "ALMANAC_MODEL_PRESET_CHUTES": "chutes:model-router",
    }


def insert_agent(conn, root: Path) -> None:
    now = control.utc_now_iso()
    hermes_home = root / "home-testuser" / ".local" / "share" / "almanac-agent" / "hermes-home"
    (hermes_home / "state").mkdir(parents=True, exist_ok=True)
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
            "agent-test",
            "user",
            "testuser",
            "Test User",
            "active",
            str(hermes_home),
            str(root / "state" / "agents" / "agent-test" / "manifest.json"),
            None,
            "codex",
            "openai:codex",
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


def seed_sources(root: Path, conn) -> None:
    (root / "vault" / "Research").mkdir(parents=True)
    (root / "vault" / "Research" / "Horizon protocol notes.md").write_text(
        "# Horizon protocol\nPrivacy preserving distributed systems notes and open research questions.\n",
        encoding="utf-8",
    )
    (root / "vault" / "Projects" / "Nimbus Trading Lab").mkdir(parents=True)
    (root / "vault" / "Projects" / "Nimbus Trading Lab" / "Market making.md").write_text(
        "# Nimbus Trading Lab market making\nInventory control, spread policy, and execution-risk notes.\n",
        encoding="utf-8",
    )
    (root / "vault" / "Repos" / "archive-delta").mkdir(parents=True)
    (root / "vault" / "Repos" / "archive-delta" / ".git").mkdir()
    (root / "vault" / "Repos" / "archive-delta" / "README.md").write_text("# Archive Delta\n", encoding="utf-8")

    notion_md = root / "state" / "notion-index" / "markdown" / "root-1" / "abc" / "0000.md"
    notion_md.parent.mkdir(parents=True, exist_ok=True)
    notion_md.write_text(
        "# Example Work Focus\nKora owns an offline workflow prototype and latency benchmark.\n",
        encoding="utf-8",
    )
    now = control.utc_now_iso()
    conn.execute(
        """
        INSERT INTO notion_index_documents (
          doc_key, root_id, source_page_id, source_page_url, source_kind,
          file_path, page_title, section_heading, section_ordinal,
          breadcrumb_json, owners_json, last_edited_time, content_hash,
          indexed_at, state
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "root-1:abc:0",
            "root-1",
            "abc",
            "https://www.notion.so/abc",
            "page",
            str(notion_md),
            "Example Work Focus",
            "Current Work",
            0,
            json.dumps(["Example Workspace", "Work Focus", "Example Work Focus"]),
            json.dumps(["Kora"]),
            now,
            "hash-abc",
            now,
            "active",
        ),
    )
    conn.commit()


def test_memory_synthesizer_caches_cards_and_injects_recall_stubs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, base_config(root))
        old_env = os.environ.copy()
        os.environ.update(base_config(root))
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                insert_agent(conn, root)
                seed_sources(root, conn)

            calls: list[str] = []

            def fake_model(candidate: synth.SourceCandidate, settings: synth.SynthesisSettings) -> dict[str, object]:
                calls.append(f"{candidate.source_kind}:{candidate.source_key}")
                source_text = json.dumps(candidate.payload, sort_keys=True)
                return {
                    "summary": f"{candidate.source_title} contains compact orientation for retrieval.",
                    "topics": ["research" if "Horizon" in source_text else "operations"],
                    "entities": ["Horizon Protocol", "Nimbus Trading Lab", "Archive Delta", "Example Workspace"],
                    "retrieval_queries": [candidate.source_title, "Horizon protocol", "Nimbus Trading Lab market making"],
                    "source_hints": [candidate.source_title],
                    "confidence": "medium",
                    "inject": True,
                }

            first = synth.run_once(cfg, model_client=fake_model)
            expect(first["status"] == "ok", str(first))
            expect(first["synthesized"] >= 4, str(first))
            expect(any(call == "vault:Research" for call in calls), calls)
            expect(any(call == "vault:Projects" for call in calls), calls)
            expect(any(call == "vault:Repos" for call in calls), calls)
            expect(any(call.startswith("notion:Work Focus") for call in calls), calls)

            with control.connect_db(cfg) as conn:
                card_rows = conn.execute("SELECT source_kind, source_key, card_text FROM memory_synthesis_cards WHERE status = 'ok'").fetchall()
                card_text = "\n".join(str(row["card_text"] or "") for row in card_rows)
                expect("Research contains compact orientation" in card_text, card_text)
                expect("Projects contains compact orientation" in card_text, card_text)
                expect("Repos contains compact orientation" in card_text, card_text)
                expect("Nimbus Trading Lab" in card_text, card_text)
                expect("Archive Delta" in card_text, card_text)
                fanout = conn.execute(
                    "SELECT COUNT(*) AS c FROM notification_outbox WHERE target_kind = 'curator' AND channel_kind = 'brief-fanout'"
                ).fetchone()
                expect(int(fanout["c"]) == 1, f"expected one curator fanout notification, got {fanout['c']}")
                payload = control.build_managed_memory_payload(conn, cfg, agent_id="agent-test")
                expect("Semantic synthesis cards:" in payload["recall-stubs"], payload["recall-stubs"])
                expect("LLM-compressed recall hints only" in payload["recall-stubs"], payload["recall-stubs"])
                expect("[vault:Research]" in payload["recall-stubs"], payload["recall-stubs"])

            calls.clear()
            second = synth.run_once(cfg, model_client=fake_model)
            expect(second["synthesized"] == 0, str(second))
            expect(calls == [], f"unchanged sources should not call model again: {calls}")

            (root / "vault" / "Research" / "Horizon protocol notes.md").write_text(
                "# Horizon protocol\nUpdated privacy preserving distributed systems notes.\n",
                encoding="utf-8",
            )
            third = synth.run_once(cfg, model_client=fake_model)
            expect(third["synthesized"] == 1, str(third))
            expect(calls == ["vault:Research"], f"only the changed vault folder should be re-synthesized: {calls}")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_memory_synthesizer_caches_cards_and_injects_recall_stubs()
    print("PASS test_memory_synthesizer_caches_cards_and_injects_recall_stubs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
