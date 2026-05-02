#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REFRESH_SH = REPO / "bin" / "refresh-agent-install.sh"
INSTALL_SH = REPO / "bin" / "install-agent-user-services.sh"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def extract_function(source: str, fn_name: str) -> str:
    """Pull a bash function definition out of a script source."""
    start_marker = f"{fn_name}() {{"
    start = source.find(start_marker)
    if start < 0:
        raise AssertionError(f"could not find function {fn_name}() in script")
    depth = 0
    end = start
    for idx in range(start, len(source)):
        ch = source[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = idx + 1
                break
    return source[start:end]


def bash_script(*, vault_dir: Path, link_path: Path, unix_user: str, extra: str = "") -> str:
    """Build a self-contained bash harness that exercises ensure_one_vault_link."""
    text = REFRESH_SH.read_text(encoding="utf-8")
    fn = extract_function(text, "ensure_one_vault_link")
    return f"""#!/usr/bin/env bash
set -euo pipefail
VAULT_DIR={str(vault_dir)!r}
UNIX_USER={unix_user!r}
{fn}

{extra}
"""


def bash_script_for_user_links(*, root: Path, vault_dir: Path, unix_user: str, extra: str = "") -> str:
    """Build a harness for ensure_user_vault_link and its alias fanout."""
    text = REFRESH_SH.read_text(encoding="utf-8")
    one_link_fn = extract_function(text, "ensure_one_vault_link")
    user_link_fn = extract_function(text, "ensure_user_vault_link")
    home_dir = root / "home" / "user"
    hermes_home = home_dir / ".local" / "share" / "arclink-agent" / "hermes-home"
    return f"""#!/usr/bin/env bash
set -euo pipefail
VAULT_DIR={str(vault_dir)!r}
UNIX_USER={unix_user!r}
TARGET_VAULT_LINK_PATH=""
TARGET_ARCLINK_LINK_PATH={str(home_dir / "ArcLink")!r}
TARGET_HERMES_HOME={str(hermes_home)!r}
{one_link_fn}
{user_link_fn}

{extra}
"""


def run_bash(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script], text=True, capture_output=True, check=False
    )


def test_vault_symlink_creates_fresh_link_to_vault_dir() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        vault_dir = root / "vault"
        vault_dir.mkdir()
        link_path = root / "home" / "user" / "Vault"
        script = bash_script(
            vault_dir=vault_dir,
            link_path=link_path,
            unix_user=os.environ.get("USER", "nobody"),
            extra=f'ensure_one_vault_link "{link_path}"',
        )
        result = run_bash(script)
        expect(result.returncode == 0, f"fresh link create failed: {result.stderr!r}")
        expect(link_path.is_symlink(), f"expected symlink at {link_path}")
        expect(os.readlink(link_path) == str(vault_dir), f"bad symlink target: {os.readlink(link_path)!r}")
    print("PASS test_vault_symlink_creates_fresh_link_to_vault_dir")


def test_vault_symlink_replaces_stale_symlink_to_wrong_target() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        vault_dir = root / "vault"
        vault_dir.mkdir()
        wrong_target = root / "stale-vault"
        wrong_target.mkdir()
        link_path = root / "home" / "user" / "Vault"
        link_path.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(str(wrong_target), str(link_path))

        script = bash_script(
            vault_dir=vault_dir,
            link_path=link_path,
            unix_user=os.environ.get("USER", "nobody"),
            extra=f'ensure_one_vault_link "{link_path}"',
        )
        result = run_bash(script)
        expect(result.returncode == 0, f"stale link replace failed: {result.stderr!r}")
        expect(link_path.is_symlink(), f"expected symlink at {link_path}")
        expect(os.readlink(link_path) == str(vault_dir), f"bad symlink target: {os.readlink(link_path)!r}")
    print("PASS test_vault_symlink_replaces_stale_symlink_to_wrong_target")


def test_vault_symlink_refuses_to_overwrite_real_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        vault_dir = root / "vault"
        vault_dir.mkdir()
        link_path = root / "home" / "user" / "Vault"
        link_path.parent.mkdir(parents=True, exist_ok=True)
        link_path.mkdir()
        (link_path / "user-file.md").write_text("keep me\n", encoding="utf-8")

        script = bash_script(
            vault_dir=vault_dir,
            link_path=link_path,
            unix_user=os.environ.get("USER", "nobody"),
            extra=f'ensure_one_vault_link "{link_path}" || echo "REFUSED"',
        )
        result = run_bash(script)
        expect(result.returncode == 0, f"script crashed: {result.stderr!r}")
        expect("REFUSED" in result.stdout, f"expected refusal on real dir, got: {result.stdout!r}")
        expect(not link_path.is_symlink(), "real directory must NOT be replaced with a symlink")
        expect((link_path / "user-file.md").read_text(encoding="utf-8") == "keep me\n", "user data was lost")
    print("PASS test_vault_symlink_refuses_to_overwrite_real_directory")


def test_vault_symlink_is_idempotent_when_already_correct() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        vault_dir = root / "vault"
        vault_dir.mkdir()
        link_path = root / "home" / "user" / "Vault"
        link_path.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(str(vault_dir), str(link_path))
        original_inode = link_path.lstat().st_ino

        script = bash_script(
            vault_dir=vault_dir,
            link_path=link_path,
            unix_user=os.environ.get("USER", "nobody"),
            extra=f'ensure_one_vault_link "{link_path}"',
        )
        result = run_bash(script)
        expect(result.returncode == 0, f"idempotent run failed: {result.stderr!r}")
        expect(link_path.is_symlink(), "symlink must still exist")
        expect(os.readlink(link_path) == str(vault_dir), "target must be unchanged")
        expect(link_path.lstat().st_ino == original_inode, "idempotent run should not recreate the symlink inode")
    print("PASS test_vault_symlink_is_idempotent_when_already_correct")


def test_user_vault_links_create_arclink_alias_and_internal_compat_links() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        vault_dir = root / "vault"
        vault_dir.mkdir()
        script = bash_script_for_user_links(
            root=root,
            vault_dir=vault_dir,
            unix_user=os.environ.get("USER", "nobody"),
            extra="ensure_user_vault_link",
        )
        result = run_bash(script)
        expect(result.returncode == 0, f"user link fanout failed: {result.stderr!r}")
        home_dir = root / "home" / "user"
        hermes_home = home_dir / ".local" / "share" / "arclink-agent" / "hermes-home"
        expect(not (home_dir / "Vault").exists(), "home-level Vault alias should be opt-in to avoid duplicate Explorer roots")
        for path in (home_dir / "ArcLink", hermes_home / "Vault", hermes_home / "ArcLink"):
            expect(path.is_symlink(), f"expected symlink at {path}")
            expect(os.readlink(path) == str(vault_dir), f"bad target for {path}: {os.readlink(path)!r}")
    print("PASS test_user_vault_links_create_arclink_alias_and_internal_compat_links")


def test_user_vault_links_create_home_vault_only_when_explicitly_requested() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        vault_dir = root / "vault"
        vault_dir.mkdir()
        home_dir = root / "home" / "user"
        explicit_vault = home_dir / "Vault"
        script = bash_script_for_user_links(
            root=root,
            vault_dir=vault_dir,
            unix_user=os.environ.get("USER", "nobody"),
            extra=f'TARGET_VAULT_LINK_PATH="{explicit_vault}"\nensure_user_vault_link',
        )
        result = run_bash(script)
        expect(result.returncode == 0, f"explicit home Vault link failed: {result.stderr!r}")
        expect(explicit_vault.is_symlink(), f"expected explicit home Vault symlink at {explicit_vault}")
        expect(os.readlink(explicit_vault) == str(vault_dir), f"bad explicit Vault target: {os.readlink(explicit_vault)!r}")
    print("PASS test_user_vault_links_create_home_vault_only_when_explicitly_requested")


def test_refresh_repair_chowns_local_bin_when_root_creates_wrappers() -> None:
    text = REFRESH_SH.read_text(encoding="utf-8")
    install_text = INSTALL_SH.read_text(encoding="utf-8")
    fn = extract_function(text, "install_local_user_wrappers")
    expect('chown "$UNIX_USER:$UNIX_USER" "$TARGET_LOCAL_BIN_DIR"' in fn, fn)
    expect("arclink-agent-hermes" in fn, fn)
    expect("arclink-agent-configure-backup" in fn, fn)
    expect("should_restart_gateway" in fn, fn)
    expect("systemctl --user restart arclink-user-agent-gateway.service" in fn, fn)
    expect("ensure_user_vault_link || true" not in text, "refresh must not silently ignore missing vault links")
    expect('ensure_one_vault_link "$HOME/ArcLink" || status=1' in install_text, install_text)
    print("PASS test_refresh_repair_chowns_local_bin_when_root_creates_wrappers")


def main() -> int:
    test_vault_symlink_creates_fresh_link_to_vault_dir()
    test_vault_symlink_replaces_stale_symlink_to_wrong_target()
    test_vault_symlink_refuses_to_overwrite_real_directory()
    test_vault_symlink_is_idempotent_when_already_correct()
    test_user_vault_links_create_arclink_alias_and_internal_compat_links()
    test_user_vault_links_create_home_vault_only_when_explicitly_requested()
    test_refresh_repair_chowns_local_bin_when_root_creates_wrappers()
    print("PASS all 7 vault symlink regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
