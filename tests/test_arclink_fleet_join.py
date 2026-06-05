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
CONTROL_WG_PUBLIC_KEY = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789+/AB="
WORKER_WG_PUBLIC_KEY = "BcDeFgHiJkLmNoPqRsTuVwXyZ0123456789+/ABC="


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
            "--private-dns-name",
            "worker-a.wg.internal",
            "--tailscale-dns-name",
            "worker-a.tailnet.ts.net",
            "--ssh-user",
            "arclink",
            "--region",
            "iad",
            "--capacity-slots",
            "7",
            "--state-root",
            str(state_root),
            "--deployment-state-root-base",
            "/arcdata/deployments",
            "--fleet-share-hub-root",
            "/arcdata/captains",
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
        deployment_root = root / "arcdata" / "deployments"
        fleet_share_root = root / "arcdata" / "captains"
        fleet_share_key = state_root / "fleet-share-ssh" / "id_ed25519"
        expect(deployment_root.is_dir(), "join should create the ArcPod deployment root")
        expect(fleet_share_root.is_dir(), "join should create the fleet-share hub root")
        expect(fleet_share_key.is_file(), "join should create a worker-local fleet-share SSH key")
        expect((fleet_share_key.stat().st_mode & 0o777) == 0o600, oct(fleet_share_key.stat().st_mode & 0o777))
        expect((deployment_root.stat().st_mode & 0o777) == 0o755, oct(deployment_root.stat().st_mode & 0o777))
        expect((fleet_share_root.stat().st_mode & 0o777) == 0o755, oct(fleet_share_root.stat().st_mode & 0o777))
        callbacks = [json.loads(line) for line in sink.read_text(encoding="utf-8").splitlines()]
        expect(len(callbacks) == 1, str(callbacks))
        payload = callbacks[0]["payload"]
        expect(payload["hostname"] == "worker-a.example.test", str(payload))
        expect(payload["ssh_host"] == "10.0.0.10", str(payload))
        expect(payload["private_dns_name"] == "worker-a.wg.internal", str(payload))
        expect(payload["tailscale_dns_name"] == "worker-a.tailnet.ts.net", str(payload))
        expect(payload["capacity_slots"] == 7, str(payload))
        expect(payload["fleet_share_ssh_key_path"] == str(fleet_share_key), str(payload))
        expect(payload["fleet_share_ssh_public_key"].startswith("ssh-ed25519 "), str(payload))
        rendered = json.dumps(callbacks, sort_keys=True)
        expect("safe-token-signature" not in rendered and "arcfleet_v1" not in rendered, rendered)
        authorized_keys = root / "home" / "arclink" / ".ssh" / "authorized_keys"
        key_lines = authorized_keys.read_text(encoding="utf-8").splitlines()
        expect(key_lines.count(PUBLIC_KEY) == 1, key_lines)
    print("PASS test_join_fake_root_is_idempotent_and_does_not_persist_token")


def test_join_fake_root_configures_wireguard_without_ssh_surgery() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        root = tmp_path / "root"
        sink = tmp_path / "callback.jsonl"
        token_file = tmp_path / "token"
        key_file = tmp_path / "fleet.pub"
        fakebin = tmp_path / "bin"
        fakebin.mkdir()
        write(root / "etc" / "machine-id", "1234567890abcdef1234567890abcdef\n")
        write(token_file, "arcfleet_v1.flenr_test.wireguard-token\n")
        write(key_file, PUBLIC_KEY + "\n", mode=0o644)
        write(
            fakebin / "wg",
            f"#!/bin/bash\nif [[ ${{1:-}} == genkey ]]; then echo test-worker-private-key; exit 0; fi\nif [[ ${{1:-}} == pubkey ]]; then cat >/dev/null; echo {WORKER_WG_PUBLIC_KEY}; exit 0; fi\nexit 64\n",
            mode=0o755,
        )
        state_root = root / "var" / "lib" / "arclink-fleet"
        authorized_keys = root / "home" / "arclink" / ".ssh" / "authorized_keys"
        write(authorized_keys, "ssh-ed25519 AAAAC3NzaExisting existing-key\n", mode=0o600)
        env = base_env(root, sink)
        env["PATH"] = f"{fakebin}:{env.get('PATH', '')}"
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
                "worker-wg.example.test",
                "--ssh-host",
                "198.51.100.44",
                "--ssh-user",
                "arclink",
                "--state-root",
                str(state_root),
                "--wireguard-worker-ip",
                "10.44.0.11/32",
                "--wireguard-control-public-key",
                CONTROL_WG_PUBLIC_KEY,
                "--wireguard-control-endpoint",
                "control.wg.example.test:51820",
                "--wireguard-listen-port",
                "51821",
                "--skip-prereq-install",
                "--json",
            ],
            env=env,
        )
        expect(result.returncode == 0, f"wireguard join failed: {result.stderr}\n{result.stdout}")
        config = root / "etc" / "wireguard" / "wg-arclink.conf"
        expect(config.exists(), "WireGuard config should be written in fake root")
        config_text = config.read_text(encoding="utf-8")
        expect("Address = 10.44.0.11/32" in config_text, config_text)
        expect(f"PublicKey = {CONTROL_WG_PUBLIC_KEY}" in config_text, config_text)
        expect("Endpoint = control.wg.example.test:51820" in config_text, config_text)
        expect("ListenPort = 51821" in config_text, config_text)
        firewall_plan = (state_root / "wireguard" / "firewall.plan").read_text(encoding="utf-8")
        expect("51821/udp" in firewall_plan and "22" not in firewall_plan, firewall_plan)
        key_lines = authorized_keys.read_text(encoding="utf-8").splitlines()
        expect("ssh-ed25519 AAAAC3NzaExisting existing-key" in key_lines, key_lines)
        expect(key_lines.count(PUBLIC_KEY) == 1, key_lines)
        payload = json.loads(sink.read_text(encoding="utf-8").splitlines()[0])["payload"]
        expect(payload["private_dns_name"] == "10.44.0.11", str(payload))
        expect(payload["wireguard_private_ip"] == "10.44.0.11", str(payload))
        expect(payload["wireguard_private_cidr"] == "10.44.0.11/32", str(payload))
        expect(payload["wireguard_public_key"] == WORKER_WG_PUBLIC_KEY, str(payload))
        expect(payload["wireguard_firewall_status"] == "planned", str(payload))
    print("PASS test_join_fake_root_configures_wireguard_without_ssh_surgery")


def test_join_rejects_unsafe_wireguard_shapes_before_config_write() -> None:
    cases = [
        ("bad_ip", ["--wireguard-worker-ip", "10.44.0.999/32"], "worker IP"),
        ("bad_prefix", ["--wireguard-worker-ip", "10.44.0.11/999"], "worker IP"),
        ("bad_endpoint_port", ["--wireguard-control-endpoint", "control.wg.example.test:99999"], "endpoint port"),
        ("bad_allowed_ips", ["--wireguard-control-allowed-ips", "10.44.0.1/32,bad/cidr"], "allowed IPs"),
        ("bad_interface", ["--wireguard-interface", "wg-arclink-too-long"], "interface"),
    ]
    for suffix, override, expected in cases:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / "root"
            sink = tmp_path / "callback.jsonl"
            token_file = tmp_path / "token"
            key_file = tmp_path / "fleet.pub"
            state_root = root / "var" / "lib" / "arclink-fleet"
            write(root / "etc" / "machine-id", f"{suffix}1234567890abcdef1234567890\n")
            write(token_file, f"arcfleet_v1.flenr_test.{suffix}\n")
            write(key_file, PUBLIC_KEY + "\n", mode=0o644)
            cmd = [
                str(JOIN_SH),
                "--control-url",
                "https://control.example.test",
                "--token-file",
                str(token_file),
                "--authorized-key-file",
                str(key_file),
                "--hostname",
                f"worker-{suffix}.example.test",
                "--state-root",
                str(state_root),
                "--wireguard-worker-ip",
                "10.44.0.11/32",
                "--wireguard-control-public-key",
                CONTROL_WG_PUBLIC_KEY,
                "--wireguard-control-endpoint",
                "control.wg.example.test:51820",
                "--skip-prereq-install",
            ]
            if override[0] == "--wireguard-worker-ip":
                index = cmd.index("--wireguard-worker-ip")
                cmd[index:index + 2] = override
            elif override[0] == "--wireguard-control-endpoint":
                index = cmd.index("--wireguard-control-endpoint")
                cmd[index:index + 2] = override
            elif override[0] == "--wireguard-control-allowed-ips":
                cmd.extend(override)
            else:
                cmd.extend(override)
            result = run(cmd, env=base_env(root, sink))
            expect(result.returncode == 2, f"{suffix} should fail validation: {result.stdout}\n{result.stderr}")
            expect(expected in result.stderr, f"{suffix} missing expected error {expected!r}: {result.stderr}")
            expect(not (root / "etc" / "wireguard" / "wg-arclink.conf").exists(), f"{suffix} wrote WireGuard config")
    print("PASS test_join_rejects_unsafe_wireguard_shapes_before_config_write")


def test_join_accepts_ipv6_wireguard_endpoint_shape() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        root = tmp_path / "root"
        sink = tmp_path / "callback.jsonl"
        token_file = tmp_path / "token"
        key_file = tmp_path / "fleet.pub"
        state_root = root / "var" / "lib" / "arclink-fleet"
        write(root / "etc" / "machine-id", "ipv61234567890abcdef1234567890\n")
        write(token_file, "arcfleet_v1.flenr_test.ipv6\n")
        write(key_file, PUBLIC_KEY + "\n", mode=0o644)
        cmd = [
            str(JOIN_SH),
            "--control-url",
            "https://control.example.test",
            "--token-file",
            str(token_file),
            "--authorized-key-file",
            str(key_file),
            "--hostname",
            "worker-ipv6.example.test",
            "--state-root",
            str(state_root),
            "--wireguard-worker-ip",
            "fd44::11",
            "--wireguard-control-public-key",
            CONTROL_WG_PUBLIC_KEY,
            "--wireguard-control-endpoint",
            "[fd44::1]:51820",
            "--wireguard-control-allowed-ips",
            "fd44::1/128",
            "--skip-prereq-install",
        ]
        result = run(cmd, env=base_env(root, sink))
        expect(result.returncode == 0, result.stderr or result.stdout)
        config = root / "etc" / "wireguard" / "wg-arclink.conf"
        expect(config.exists(), "IPv6 WireGuard config was not written")
        text = config.read_text(encoding="utf-8")
        expect("Address = fd44::11/128" in text, text)
        expect("Endpoint = [fd44::1]:51820" in text, text)
    print("PASS test_join_accepts_ipv6_wireguard_endpoint_shape")


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
    test_join_fake_root_configures_wireguard_without_ssh_surgery()
    test_join_rejects_unsafe_wireguard_shapes_before_config_write()
    test_join_accepts_ipv6_wireguard_endpoint_shape()
    test_join_callback_failure_leaves_worker_non_admitting()
    test_probe_wrapper_allowlist_outputs_json_and_rejects_unknown()
    print("PASS all 7 ArcLink fleet join tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
