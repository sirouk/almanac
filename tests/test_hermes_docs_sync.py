#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bin" / "sync-hermes-docs-into-vault.sh"


def run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=False)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_sync_hermes_docs_into_vault_tracks_source_updates() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fake_repo = root / "hermes-agent"
        docs_dir = fake_repo / "website" / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "intro.md").write_text("# Intro\n", encoding="utf-8")
        run(["git", "init", "-b", "main", str(fake_repo)])
        run(["git", "-C", str(fake_repo), "config", "user.name", "Tester"])
        run(["git", "-C", str(fake_repo), "config", "user.email", "tester@example.com"])
        run(["git", "-C", str(fake_repo), "add", "."])
        run(["git", "-C", str(fake_repo), "commit", "-m", "initial docs"])

        config_path = root / "arclink-priv" / "config" / "arclink.env"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            "\n".join(
                [
                    f"ARCLINK_REPO_DIR={REPO}",
                    f"ARCLINK_PRIV_DIR={root / 'arclink-priv'}",
                    f"STATE_DIR={root / 'arclink-priv' / 'state'}",
                    f"VAULT_DIR={root / 'arclink-priv' / 'vault'}",
                    f"ARCLINK_HERMES_DOCS_REPO_URL={fake_repo}",
                    "ARCLINK_HERMES_DOCS_REF=main",
                    "ARCLINK_HERMES_DOCS_SOURCE_SUBDIR=website/docs",
                    f"ARCLINK_HERMES_DOCS_STATE_DIR={root / 'arclink-priv' / 'state' / 'hermes-docs-src'}",
                    f"ARCLINK_HERMES_DOCS_VAULT_DIR={root / 'arclink-priv' / 'vault' / 'Repos' / 'hermes-agent-docs'}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [str(SCRIPT)],
            env={**os.environ, "ARCLINK_CONFIG_FILE": str(config_path)},
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"initial docs sync failed: stdout={result.stdout!r} stderr={result.stderr!r}")

        target_dir = root / "arclink-priv" / "vault" / "Agents_KB" / "hermes-agent-docs"
        legacy_target_dir = root / "arclink-priv" / "vault" / "Repos" / "hermes-agent-docs"
        expect((target_dir / "intro.md").read_text(encoding="utf-8") == "# Intro\n", str(list(target_dir.iterdir())))
        expect(not legacy_target_dir.exists(), "expected legacy Repos/hermes-agent-docs default to normalize into Agents_KB")
        expect((target_dir / ".arclink-source.json").is_file(), "expected sync metadata file")
        arclink_docs_dir = root / "arclink-priv" / "vault" / "Agents_KB" / "arclink-docs"
        expect((arclink_docs_dir / "README.md").is_file(), "expected top-level ArcLink README in synced docs")
        expect((arclink_docs_dir / "arclink" / "vocabulary.md").is_file(), "expected canonical ArcLink docs in synced docs")
        expect((arclink_docs_dir / "openapi" / "arclink-v1.openapi.json").is_file(), "expected OpenAPI docs in synced docs")
        arclink_meta = json.loads((arclink_docs_dir / ".arclink-source.json").read_text(encoding="utf-8"))
        expect("docs/arclink" in arclink_meta["source_paths"], str(arclink_meta))

        (docs_dir / "intro.md").unlink()
        (docs_dir / "advanced.mdx").write_text("# Advanced\n", encoding="utf-8")
        run(["git", "-C", str(fake_repo), "add", "-A"])
        run(["git", "-C", str(fake_repo), "commit", "-m", "update docs"])

        result = subprocess.run(
            [str(SCRIPT)],
            env={**os.environ, "ARCLINK_CONFIG_FILE": str(config_path)},
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"second docs sync failed: stdout={result.stdout!r} stderr={result.stderr!r}")
        expect(not (target_dir / "intro.md").exists(), "expected deleted source doc to be pruned from the vault")
        expect((target_dir / "advanced.mdx").read_text(encoding="utf-8") == "# Advanced\n", "expected updated source doc to sync")
        print("PASS test_sync_hermes_docs_into_vault_tracks_source_updates")


def test_hermes_docs_ref_defaults_to_hermes_agent_ref() -> None:
    """When ARCLINK_HERMES_DOCS_REF is unset, it must derive from the pinned
    runtime ref so docs cannot silently float to upstream main ahead of the
    runtime they describe."""
    common_text = (REPO / "bin" / "common.sh").read_text(encoding="utf-8")
    expect(
        "__pins_get_or_default hermes-docs ref" in common_text,
        "common.sh must resolve ARCLINK_HERMES_DOCS_REF from the hermes-docs pin",
    )
    expect(
        'ARCLINK_HERMES_DOCS_REF="${ARCLINK_HERMES_DOCS_REF:-main}"' not in common_text,
        "common.sh must not default ARCLINK_HERMES_DOCS_REF to 'main' (silent-drift regression)",
    )

    deploy_text = (REPO / "bin" / "deploy.sh").read_text(encoding="utf-8")
    expect(
        "deploy_pin_get_or_default hermes-docs ref" in deploy_text,
        "deploy.sh must write ARCLINK_HERMES_DOCS_REF from the hermes-docs pin",
    )
    expect(
        'write_kv ARCLINK_HERMES_DOCS_REF "${ARCLINK_HERMES_DOCS_REF:-main}"' not in deploy_text,
        "deploy.sh must not write 'main' as the default docs ref (silent-drift regression)",
    )

    sync_text = SCRIPT.read_text(encoding="utf-8")
    expect(
        'repo_ref="${ARCLINK_HERMES_DOCS_REF:-${ARCLINK_HERMES_AGENT_REF:-main}}"' in sync_text,
        "sync-hermes-docs-into-vault.sh must fall back to ARCLINK_HERMES_AGENT_REF before main",
    )
    expect(
        "Agents_KB/hermes-agent-docs" in sync_text,
        "sync-hermes-docs-into-vault.sh must default Hermes docs into Agents_KB",
    )
    expect(
        'repo_ref="${ARCLINK_HERMES_DOCS_REF:-main}"' not in sync_text,
        "sync-hermes-docs-into-vault.sh must not directly default docs to main",
    )

    example_text = (REPO / "config" / "arclink.env.example").read_text(encoding="utf-8")
    pins = json.loads((REPO / "config" / "pins.json").read_text(encoding="utf-8"))
    pinned_docs_ref = str(pins["components"]["hermes-docs"]["ref"])
    expect(
        "ARCLINK_HERMES_DOCS_REF=main" not in example_text,
        "config/arclink.env.example must not ship ARCLINK_HERMES_DOCS_REF=main as the default",
    )
    expect(
        f"ARCLINK_HERMES_DOCS_REF={pinned_docs_ref}" in example_text
        or "ARCLINK_HERMES_DOCS_REF=${ARCLINK_HERMES_AGENT_REF" in example_text,
        "config/arclink.env.example must ship a pinned SHA or reference to ARCLINK_HERMES_AGENT_REF",
    )
    print("PASS test_hermes_docs_ref_defaults_to_hermes_agent_ref")


def main() -> int:
    test_sync_hermes_docs_into_vault_tracks_source_updates()
    test_hermes_docs_ref_defaults_to_hermes_agent_ref()
    print("PASS all 2 Hermes docs sync regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
