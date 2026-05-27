#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from arclink_test_helpers import expect


REPO = Path(__file__).resolve().parents[1]
JOIN_SH = REPO / "bin" / "arclink-fleet-join.sh"
PROBE_WRAPPER = REPO / "bin" / "arclink-fleet-probe-wrapper"
PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestArcLinkFleetJoinKey arclink-test"


def run(cmd: list[str], *, env: dict[str, str] | None = None, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(REPO),
        text=True,
        input=stdin,
        capture_output=True,
        env=env,
        check=False,
    )


def write(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)


def base_env(root: Path, sink: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "ARCLINK_FLEET_JOIN_SYSTEM_ROOT": str(root),
            "ARCLINK_SKIP_PREREQ_INSTALL": "1",
            "ARCLINK_FLEET_JOIN_CALLBACK_SINK": str(sink),
        }
    )
    return env


def test_join_rejects_enrollment_token_in_argv() -> None:
    result = run([str(JOIN_SH), "--control-url", "https://control.example.test", "--token", "arcfleet_v1.secret"])
    expect(result.returncode == 2, f"expected argv token rejection: {result.stderr}")
    rendered = result.stdout + result.stderr
    expect("arcfleet_v1.secret" not in rendered, rendered)
    expect("token-file" in rendered and "token-stdin" in rendered, rendered)
    print("PASS test_join_rejects_enrollment_token_in_argv")


def test_join_fake_root_is_idempotent_and_does_not_persist_token() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "root"
        sink = Path(tmp) / "callback.jsonl"
        token_file = Path(tmp) / "token"
        key_file = Path(tmp) / "fleet.pub"
        write(root / "etc" / "machine-id", "00112233445566778899aabbccddeeff\n")
        write(root / "etc" / "os-release", 'PRETTY_NAME="ArcLink Test OS"\n')
        write(token_file, "arcfleet_v1.flenr_test.safe-token-signature\n")
        write(key_file, PUBLIC_KEY + "\n", mode=0o644)
        env = base_env(root, sink)
        state_root = root / "var" / "lib" / "arclink-fleet"
        cmd = [
            str(JOIN_SH),
            "--callback-url",
            "https://control.example.test/api/v1/fleet/enrollment/callback",
            "--token-file",
            str(token_file),
            "--authorized-key-file",
            str(key_file),
            "--hostname",
            "worker-a.example.test",
            "--ssh-host",
            "10.0.0.10",
            "--ssh-user",
            "arclink",
            "--region",
            "iad",
            "--capacity-slots",
            "7",
            "--state-root",
            str(state_root),
            "--skip-prereq-install",
            "--json",
        ]
        first = run(cmd, env=env)
        expect(first.returncode == 0, f"first join failed: {first.stderr}\n{first.stdout}")
        second = run(cmd, env=env)
        expect(second.returncode == 0, f"second join failed: {second.stderr}\n{second.stdout}")
        expect((state_root / "admission.state").read_text(encoding="utf-8").strip() == "admitting", "worker should be admitted")
        config_file = root / "etc" / "arclink" / "fleet-worker.env"
        expect(config_file.exists(), "join should write the probe wrapper config")
        expect((config_file.stat().st_mode & 0o777) == 0o644, oct(config_file.stat().st_mode & 0o777))
        expect((state_root.stat().st_mode & 0o777) == 0o755, oct(state_root.stat().st_mode & 0o777))
        callbacks = [json.loads(line) for line in sink.read_text(encoding="utf-8").splitlines()]
        expect(len(callbacks) == 1, str(callbacks))
        payload = callbacks[0]["payload"]
        expect(payload["hostname"] == "worker-a.example.test", str(payload))
        expect(payload["ssh_host"] == "10.0.0.10", str(payload))
        expect(payload["capacity_slots"] == 7, str(payload))
        rendered = json.dumps(callbacks, sort_keys=True)
        expect("safe-token-signature" not in rendered and "arcfleet_v1" not in rendered, rendered)
        authorized_keys = root / "home" / "arclink" / ".ssh" / "authorized_keys"
        key_lines = authorized_keys.read_text(encoding="utf-8").splitlines()
        expect(key_lines.count(PUBLIC_KEY) == 1, key_lines)
    print("PASS test_join_fake_root_is_idempotent_and_does_not_persist_token")


def test_join_callback_failure_leaves_worker_non_admitting() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "root"
        sink = Path(tmp) / "callback.jsonl"
        token_file = Path(tmp) / "token"
        key_file = Path(tmp) / "fleet.pub"
        write(root / "etc" / "machine-id", "ffeeddccbbaa99887766554433221100\n")
        write(token_file, "arcfleet_v1.flenr_test.rejected-token\n")
        write(key_file, PUBLIC_KEY + "\n", mode=0o644)
        env = base_env(root, sink)
        env["ARCLINK_FLEET_JOIN_CALLBACK_FAIL"] = "1"
        state_root = root / "var" / "lib" / "arclink-fleet"
        result = run(
            [
                str(JOIN_SH),
                "--control-url",
                "https://control.example.test",
                "--token-file",
                str(token_file),
                "--authorized-key-file",
                str(key_file),
                "--hostname",
                "worker-fail.example.test",
                "--state-root",
                str(state_root),
                "--skip-prereq-install",
            ],
            env=env,
        )
        expect(result.returncode == 1, f"expected callback failure: {result.stdout}\n{result.stderr}")
        expect((state_root / "admission.state").read_text(encoding="utf-8").strip() == "disabled", "worker should remain disabled")
        rendered = result.stdout + result.stderr
        expect("rejected-token" not in rendered and "arcfleet_v1" not in rendered, rendered)
    print("PASS test_join_callback_failure_leaves_worker_non_admitting")


def test_probe_wrapper_allowlist_outputs_json_and_rejects_unknown() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "state"
        state.mkdir()
        write(state / "admission.state", "admitting\n")
        write(state / "machine-fingerprint", "sha256:abcdef1234567890abcdef1234567890\n")
        env = os.environ.copy()
        env.update({"ARCLINK_FLEET_STATE_ROOT": str(state), "ARCLINK_FLEET_HOSTNAME": "worker-probe.example.test"})
        liveness = run([str(PROBE_WRAPPER), "liveness"], env=env)
        expect(liveness.returncode == 0, f"liveness failed: {liveness.stderr}")
        payload = json.loads(liveness.stdout)
        expect(payload["ok"] is True and payload["admitting"] is True, str(payload))
        expect(payload["kind"] == "liveness", str(payload))
        inventory = run([str(PROBE_WRAPPER), "inventory"], env=env)
        expect(inventory.returncode == 0, f"inventory failed: {inventory.stderr}")
        inv_payload = json.loads(inventory.stdout)
        expect(inv_payload["machine_fingerprint"].startswith("sha256:"), str(inv_payload))
        rejected = run([str(PROBE_WRAPPER), "shell"], env=env)
        expect(rejected.returncode == 64, f"unknown probe should fail: {rejected.stdout}\n{rejected.stderr}")
    print("PASS test_probe_wrapper_allowlist_outputs_json_and_rejects_unknown")


def main() -> int:
    test_join_rejects_enrollment_token_in_argv()
    test_join_fake_root_is_idempotent_and_does_not_persist_token()
    test_join_callback_failure_leaves_worker_non_admitting()
    test_probe_wrapper_allowlist_outputs_json_and_rejects_unknown()
    print("PASS all 4 ArcLink fleet join tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
