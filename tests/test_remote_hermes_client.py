#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bin" / "setup-remote-hermes-client.sh"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_setup_remote_hermes_client_generates_key_and_wrapper() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fakebin = root / "fakebin"
        fakebin.mkdir(parents=True, exist_ok=True)
        (fakebin / "ssh-keyscan").write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$1 ssh-ed25519 AAAATESTHOSTKEY\"\n",
            encoding="utf-8",
        )
        (fakebin / "ssh-keyscan").chmod(0o755)

        home = root / "home"
        home.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                str(SCRIPT),
                "--host",
                "agent.example.ts.net",
                "--user",
                "alex",
                "--org",
                "OrgName",
                "--key-path",
                str(home / ".ssh" / "almanac-remote-hermes-ed25519"),
            ],
            env={
                **os.environ,
                "HOME": str(home),
                "PATH": f"{fakebin}:{os.environ.get('PATH', '')}",
            },
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"setup-remote-hermes-client failed: stdout={result.stdout!r} stderr={result.stderr!r}")

        wrapper = home / ".local" / "bin"
        wrappers = list(wrapper.glob("hermes-*-remote-*"))
        expect(len(wrappers) == 1, f"expected one remote wrapper, got {wrappers!r}")
        expect(wrappers[0].name == "hermes-orgname-remote-alex", f"unexpected wrapper name: {wrappers[0].name}")
        wrapper_text = wrappers[0].read_text(encoding="utf-8")
        expect("alex@agent.example.ts.net" in wrapper_text, wrapper_text)
        expect('remote_cmd=\'exec "$HOME/.local/bin/almanac-agent-hermes"\'' in wrapper_text, wrapper_text)
        expect("printf -v quoted '%q'" in wrapper_text, wrapper_text)
        expect('ssh_tty_args=()' in wrapper_text, wrapper_text)
        expect('if [[ -t 0 && -t 1 ]]; then' in wrapper_text, wrapper_text)
        expect("StrictHostKeyChecking=yes" in wrapper_text, wrapper_text)
        expect((home / ".ssh" / "almanac-remote-hermes-ed25519").is_file(), "expected generated private key")
        expect((home / ".ssh" / "almanac-remote-hermes-ed25519.pub").is_file(), "expected generated public key")
        expect("remote Hermes config, skills, MCP tools, plugins, and files" in result.stdout, result.stdout)
        expect("Do not run your local 'hermes' command" in result.stdout, result.stdout)
        expect("Public key to send back to Curator:" not in result.stdout, result.stdout)
        expect("Reply to Curator with:" in result.stdout, result.stdout)
        expect("/ssh-key ssh-ed25519" in result.stdout, result.stdout)
        expect("hermes-orgname-remote-alex" in result.stdout, result.stdout)
        expect("organization: OrgName" in result.stdout, result.stdout)
        print("PASS test_setup_remote_hermes_client_generates_key_and_wrapper")


def test_setup_remote_hermes_client_refuses_non_tailnet_host() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                str(SCRIPT),
                "--host",
                "example.com",
                "--user",
                "alex",
            ],
            env={**os.environ, "HOME": str(home)},
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode != 0, "expected non-tailnet host to be refused")
        expect("restricted to Tailscale tailnet hosts" in result.stderr, result.stderr)
        print("PASS test_setup_remote_hermes_client_refuses_non_tailnet_host")


def main() -> int:
    test_setup_remote_hermes_client_generates_key_and_wrapper()
    test_setup_remote_hermes_client_refuses_non_tailnet_host()
    print("PASS all 2 remote Hermes client regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
