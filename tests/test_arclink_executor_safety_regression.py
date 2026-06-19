#!/usr/bin/env python3
"""Regression tests for executor C3 (subprocess timeouts) and C4 (secret scope)."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_module(filename: str, name: str):
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    path = PYTHON_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_c3_ssh_options_include_liveness_timeouts() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_c3_ssh_opts")
    runner = mod.SshDockerComposeRunner(host="w.example.test", allowed_hosts=("w.example.test",))
    opts = " ".join(runner.ssh_options)
    expect("ConnectTimeout=15" in opts, opts)
    expect("ServerAliveInterval=15" in opts, opts)
    expect("ServerAliveCountMax=3" in opts, opts)
    print("PASS test_c3_ssh_options_include_liveness_timeouts")


def test_c3_subprocess_timeout_becomes_executor_error() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_c3_timeout")

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0] if args else "cmd", timeout=kwargs.get("timeout", 1))

    original = mod.subprocess.run
    mod.subprocess.run = fake_run
    try:
        try:
            mod._run_subprocess(("docker", "ps"), timeout=5, operation="docker ps")
        except mod.ArcLinkExecutorError as exc:
            expect("timed out" in str(exc), str(exc))
        else:
            raise AssertionError("a subprocess timeout must raise ArcLinkExecutorError")
    finally:
        mod.subprocess.run = original
    print("PASS test_c3_subprocess_timeout_becomes_executor_error")


def test_c3_ssh_compose_timeout_still_cleans_remote_secrets() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_c3_cleanup")
    cleanup_calls = []

    calls = {"n": 0}

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        text = " ".join(str(p) for p in cmd)
        if "rm -rf" in text:
            cleanup_calls.append(text)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        # mkdir + rsync succeed; the compose 'up' (a long op) times out.
        if "compose" in text and "up" in text:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 1))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    original = mod.subprocess.run
    mod.subprocess.run = fake_run
    try:
        runner = mod.SshDockerComposeRunner(host="w.example.test", user="arclink", allowed_hosts=("w.example.test",))
        try:
            runner.run(
                ("up", "-d", "--remove-orphans"),
                deployment_id="dep_1",
                project_name="arclink-dep-1",
                env_file="/arcdata/deployments/dep_1/config/arclink.env",
                compose_file="/arcdata/deployments/dep_1/config/compose.yaml",
            )
        except mod.ArcLinkExecutorError as exc:
            expect("timed out" in str(exc), str(exc))
        else:
            raise AssertionError("compose up timeout must raise ArcLinkExecutorError")
    finally:
        mod.subprocess.run = original
    # The remote secret cleanup MUST still run on the timeout path.
    expect(len(cleanup_calls) == 1, f"remote secret cleanup must run on timeout: {cleanup_calls}")
    print("PASS test_c3_ssh_compose_timeout_still_cleans_remote_secrets")


def test_c4_materialized_secret_is_scoped_per_run_and_deployment() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_c4_scope")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        r_a = mod.FileMaterializingSecretResolver(lambda ref: "value-a", root, deployment_id="dep_a")
        r_b = mod.FileMaterializingSecretResolver(lambda ref: "value-b", root, deployment_id="dep_b")
        a = r_a.materialize("secret://arclink/x", "/run/secrets/api_key")
        b = r_b.materialize("secret://arclink/x", "/run/secrets/api_key")
        # Same basename, same root -- but the two copies do NOT collide.
        expect(a.source_path != b.source_path, f"{a.source_path} vs {b.source_path}")
        expect(Path(a.source_path).read_text() == "value-a", a.source_path)
        expect(Path(b.source_path).read_text() == "value-b", b.source_path)
        # Deployment id is encoded in the filename; neither lands at root/<basename>.
        expect(Path(a.source_path).name == "dep_a-api_key", a.source_path)
        expect(not (root / "api_key").exists(), "secret must never land unscoped at root/<basename>")
    print("PASS test_c4_materialized_secret_is_scoped_per_run_and_deployment")


def test_c4_apply_cleans_source_copies_on_success() -> None:
    mod = load_module("arclink_executor.py", "arclink_executor_c4_success_cleanup")
    intent = {
        "state_roots": {},
        "environment": {},
        "compose": {
            "services": {
                "app": {
                    "image": "arclink/app:local",
                    "secrets": [{"source": "api_key", "target": "/run/secrets/api_key"}],
                }
            },
            "secrets": {"api_key": {"secret_ref": "secret://arclink/x", "target": "/run/secrets/api_key"}},
        },
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / "dep_1"
        intent["state_roots"] = {"root": str(root), "config": str(root / "config")}

        class RecordingRunner:
            def run(self, args, **kwargs):
                return {"status": "ok"}

        materialized_root = root / "materialized"
        resolver = mod.FileMaterializingSecretResolver(
            value_provider=lambda ref: "sk_secret",
            materialization_root=materialized_root,
            deployment_id="dep_1",
        )
        executor = mod.ArcLinkExecutor(
            config=mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="live", state_root_base=tmpdir),
            secret_resolver=resolver,
            docker_runner=RecordingRunner(),
        )
        result = executor.docker_compose_apply(
            mod.DockerComposeApplyRequest(deployment_id="dep_1", intent=intent, idempotency_key="c4-success")
        )
        expect(result.status == "applied", str(result))
        # SUCCESS path: the intermediate plaintext source copies must NOT leak.
        leaked = [p for p in materialized_root.rglob("*") if p.is_file()] if materialized_root.exists() else []
        expect(not leaked, f"source secret copies must be cleaned on success: {leaked}")
        # The compose-referenced copy remains for container restart.
        compose_copy = Path(result.compose_file).parent / "secrets" / "api_key"
        expect(compose_copy.is_file(), f"compose-visible secret must remain: {compose_copy}")
    print("PASS test_c4_apply_cleans_source_copies_on_success")


def main() -> int:
    test_c3_ssh_options_include_liveness_timeouts()
    test_c3_subprocess_timeout_becomes_executor_error()
    test_c3_ssh_compose_timeout_still_cleans_remote_secrets()
    test_c4_materialized_secret_is_scoped_per_run_and_deployment()
    test_c4_apply_cleans_source_copies_on_success()
    print("PASS all 5 ArcLink executor safety regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
