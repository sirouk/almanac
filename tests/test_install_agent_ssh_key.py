#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bin" / "install-agent-ssh-key.sh"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_install_agent_ssh_key_adds_tailnet_restricted_entry() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home_dir = root / "alex-home"
        home_dir.mkdir(parents=True, exist_ok=True)
        pubkey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestKeyData arclink-remote-hermes@test"

        fakebin = root / "fakebin"
        fakebin.mkdir(parents=True, exist_ok=True)
        (fakebin / "id").write_text(
            "#!/usr/bin/env bash\n"
            "if [[ \"$1\" == \"alex\" ]]; then exit 0; fi\n"
            "exec /usr/bin/id \"$@\"\n",
            encoding="utf-8",
        )
        (fakebin / "id").chmod(0o755)
        (fakebin / "getent").write_text(
            "#!/usr/bin/env bash\n"
            "if [[ \"$1\" == \"passwd\" && \"$2\" == \"alex\" ]]; then\n"
            f"  printf 'alex:x:1001:1001::%s:/bin/bash\\n' '{home_dir}'\n"
            "  exit 0\n"
            "fi\n"
            "exec /usr/bin/getent \"$@\"\n",
            encoding="utf-8",
        )
        (fakebin / "getent").chmod(0o755)
        (fakebin / "chown").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        (fakebin / "chown").chmod(0o755)

        result = subprocess.run(
            [str(SCRIPT), "--unix-user", "alex", "--pubkey", pubkey],
            env={**os.environ, "PATH": f"{fakebin}:{os.environ.get('PATH', '')}"},
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"install-agent-ssh-key failed: stdout={result.stdout!r} stderr={result.stderr!r}")
        auth_keys = home_dir / ".ssh" / "authorized_keys"
        body = auth_keys.read_text(encoding="utf-8")
        expect('from="100.64.0.0/10,fd7a:115c:a1e0::/48",no-agent-forwarding,no-port-forwarding,no-user-rc,no-X11-forwarding ' in body, body)
        expect("restrict" not in body, body)
        expect(pubkey in body, body)
        print("PASS test_install_agent_ssh_key_adds_tailnet_restricted_entry")


def main() -> int:
    test_install_agent_ssh_key_adds_tailnet_restricted_entry()
    print("PASS all 1 install-agent-ssh-key regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
