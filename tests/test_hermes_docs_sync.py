#!/usr/bin/env python3
from __future__ import annotations

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

        config_path = root / "almanac-priv" / "config" / "almanac.env"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            "\n".join(
                [
                    f"ALMANAC_REPO_DIR={REPO}",
                    f"ALMANAC_PRIV_DIR={root / 'almanac-priv'}",
                    f"STATE_DIR={root / 'almanac-priv' / 'state'}",
                    f"VAULT_DIR={root / 'almanac-priv' / 'vault'}",
                    f"ALMANAC_HERMES_DOCS_REPO_URL={fake_repo}",
                    "ALMANAC_HERMES_DOCS_REF=main",
                    "ALMANAC_HERMES_DOCS_SOURCE_SUBDIR=website/docs",
                    f"ALMANAC_HERMES_DOCS_STATE_DIR={root / 'almanac-priv' / 'state' / 'hermes-docs-src'}",
                    f"ALMANAC_HERMES_DOCS_VAULT_DIR={root / 'almanac-priv' / 'vault' / 'Repos' / 'hermes-agent-docs'}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [str(SCRIPT)],
            env={**os.environ, "ALMANAC_CONFIG_FILE": str(config_path)},
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"initial docs sync failed: stdout={result.stdout!r} stderr={result.stderr!r}")

        target_dir = root / "almanac-priv" / "vault" / "Repos" / "hermes-agent-docs"
        expect((target_dir / "intro.md").read_text(encoding="utf-8") == "# Intro\n", str(list(target_dir.iterdir())))
        expect((target_dir / ".almanac-source.json").is_file(), "expected sync metadata file")

        (docs_dir / "intro.md").unlink()
        (docs_dir / "advanced.mdx").write_text("# Advanced\n", encoding="utf-8")
        run(["git", "-C", str(fake_repo), "add", "-A"])
        run(["git", "-C", str(fake_repo), "commit", "-m", "update docs"])

        result = subprocess.run(
            [str(SCRIPT)],
            env={**os.environ, "ALMANAC_CONFIG_FILE": str(config_path)},
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"second docs sync failed: stdout={result.stdout!r} stderr={result.stderr!r}")
        expect(not (target_dir / "intro.md").exists(), "expected deleted source doc to be pruned from the vault")
        expect((target_dir / "advanced.mdx").read_text(encoding="utf-8") == "# Advanced\n", "expected updated source doc to sync")
        print("PASS test_sync_hermes_docs_into_vault_tracks_source_updates")


def test_hermes_docs_ref_defaults_to_hermes_agent_ref() -> None:
    """When ALMANAC_HERMES_DOCS_REF is unset, it must derive from the pinned
    runtime ref so docs cannot silently float to upstream main ahead of the
    runtime they describe."""
    common_text = (REPO / "bin" / "common.sh").read_text(encoding="utf-8")
    expect(
        'ALMANAC_HERMES_DOCS_REF="${ALMANAC_HERMES_DOCS_REF:-$ALMANAC_HERMES_AGENT_REF}"' in common_text,
        "common.sh must default ALMANAC_HERMES_DOCS_REF to $ALMANAC_HERMES_AGENT_REF; found a different default",
    )
    expect(
        'ALMANAC_HERMES_DOCS_REF="${ALMANAC_HERMES_DOCS_REF:-main}"' not in common_text,
        "common.sh must not default ALMANAC_HERMES_DOCS_REF to 'main' (silent-drift regression)",
    )

    deploy_text = (REPO / "bin" / "deploy.sh").read_text(encoding="utf-8")
    expect(
        'write_kv ALMANAC_HERMES_DOCS_REF "${ALMANAC_HERMES_DOCS_REF:-${ALMANAC_HERMES_AGENT_REF' in deploy_text,
        "deploy.sh write_kv for ALMANAC_HERMES_DOCS_REF must default to ${ALMANAC_HERMES_AGENT_REF:-...}",
    )
    expect(
        'write_kv ALMANAC_HERMES_DOCS_REF "${ALMANAC_HERMES_DOCS_REF:-main}"' not in deploy_text,
        "deploy.sh must not write 'main' as the default docs ref (silent-drift regression)",
    )

    sync_text = SCRIPT.read_text(encoding="utf-8")
    expect(
        'repo_ref="${ALMANAC_HERMES_DOCS_REF:-${ALMANAC_HERMES_AGENT_REF:-main}}"' in sync_text,
        "sync-hermes-docs-into-vault.sh must fall back to ALMANAC_HERMES_AGENT_REF before main",
    )
    expect(
        'repo_ref="${ALMANAC_HERMES_DOCS_REF:-main}"' not in sync_text,
        "sync-hermes-docs-into-vault.sh must not directly default docs to main",
    )

    example_text = (REPO / "config" / "almanac.env.example").read_text(encoding="utf-8")
    expect(
        "ALMANAC_HERMES_DOCS_REF=main" not in example_text,
        "config/almanac.env.example must not ship ALMANAC_HERMES_DOCS_REF=main as the default",
    )
    expect(
        "ALMANAC_HERMES_DOCS_REF=ce089169d578b96c82641f17186ba63c288b22d8" in example_text
        or "ALMANAC_HERMES_DOCS_REF=${ALMANAC_HERMES_AGENT_REF" in example_text,
        "config/almanac.env.example must ship a pinned SHA or reference to ALMANAC_HERMES_AGENT_REF",
    )
    print("PASS test_hermes_docs_ref_defaults_to_hermes_agent_ref")


def main() -> int:
    test_sync_hermes_docs_into_vault_tracks_source_updates()
    test_hermes_docs_ref_defaults_to_hermes_agent_ref()
    print("PASS all 2 Hermes docs sync regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
