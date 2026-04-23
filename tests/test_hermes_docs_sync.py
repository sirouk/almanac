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


def main() -> int:
    test_sync_hermes_docs_into_vault_tracks_source_updates()
    print("PASS all 1 Hermes docs sync regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
