#!/usr/bin/env python3
"""Confinement regression tests for the operator-upgrade HOST runner.

These cover the CONFIRMED root-privilege-escalation (H1) and never-expire (M1)
gaps in arclink_operator_upgrade_host_runner.py:

  H1: deploy.sh runs as ROOT in run_operator_upgrade mode and will git-clone+run
      the queued ARCLINK_UPSTREAM_REPO_URL when DEPLOY_KEY_ENABLED=1. The runner
      must independently re-validate the queued upstream (allowlist the repo URL,
      confine key/known_hosts paths to private state with no symlinks, and only
      honor DEPLOY_KEY_ENABLED when a confined key path is present) so a queue
      file written directly by the arclink service user -- bypassing the broker
      HMAC -- cannot escalate to root.

  M1: a queued request that omits created_at must be rejected (it would otherwise
      never expire).

Run: python3 tests/test_arclink_operator_upgrade_host_runner_confinement.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_runner():
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    spec = importlib.util.spec_from_file_location(
        "arclink_operator_upgrade_host_runner_confinement_test",
        PYTHON_DIR / "arclink_operator_upgrade_host_runner.py",
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load host runner module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CANONICAL_UPSTREAM = "https://github.com/sirouk/arclink.git"


def _build_repo(root: Path) -> tuple[Path, Path, Path, Path]:
    repo = root / "repo"
    priv = root / "arclink-priv"
    queue = priv / "state" / "operator-upgrade-host-runner"
    marker = root / "deploy-marker.txt"
    upstream_marker = root / "deploy-upstream-url.txt"
    (repo / "bin").mkdir(parents=True)
    (priv / "state" / "operator-actions").mkdir(parents=True)
    (priv / "config").mkdir(parents=True)
    (queue / "pending").mkdir(parents=True)
    # deploy.sh records that it ran (so we can assert it was NEVER invoked for rejected
    # requests) and, separately, the ARCLINK_UPSTREAM_REPO_URL env it saw (so we can assert
    # the host runner PINNED a host-immutable URL and never let deploy.sh derive a poisoned
    # one from the arclink-writable git origin remote).
    (repo / "deploy.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        f"printf 'deploy %s\\n' \"$1\" >> {json.dumps(str(marker))[1:-1]}\n"
        f"printf '%s\\n' \"${{ARCLINK_UPSTREAM_REPO_URL:-<unset>}}\" >> {json.dumps(str(upstream_marker))[1:-1]}\n",
        encoding="utf-8",
    )
    (repo / "bin" / "component-upgrade.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (repo / "deploy.sh").chmod(0o755)
    (repo / "bin" / "component-upgrade.sh").chmod(0o755)
    return repo, priv, queue, marker


def _base_request(repo: Path, priv: Path, request_id: str) -> dict:
    return {
        "schema_version": 1,
        "request_id": request_id,
        "created_at": int(time.time()),
        "operation": "run_operator_upgrade",
        "repo_dir": str(repo),
        "priv_dir": str(priv),
        "log_path": str(priv / "state" / "operator-actions" / f"{request_id}.log"),
        "timeout_seconds": 30,
    }


def _drain(runner, repo: Path, priv: Path, queue: Path) -> None:
    old_env = os.environ.copy()
    try:
        os.environ["ARCLINK_OPERATOR_UPGRADE_HOST_REPO_DIR"] = str(repo)
        os.environ["ARCLINK_OPERATOR_UPGRADE_HOST_PRIV_DIR"] = str(priv)
        os.environ["ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR"] = str(queue)
        # Pin the canonical upstream allowlist to a fixed value so the test does
        # not depend on the actual repo's git origin remote.
        os.environ["ARCLINK_OPERATOR_UPGRADE_HOST_UPSTREAM_REPO_URL_ALLOWLIST"] = CANONICAL_UPSTREAM
        os.environ.pop("ARCLINK_UPSTREAM_REPO_URL", None)
        runner.process_once()
    finally:
        os.environ.clear()
        os.environ.update(old_env)


def _drain_no_explicit_allowlist(
    runner, repo: Path, priv: Path, queue: Path, *, host_repo_url: str | None = None
) -> None:
    """Drain WITHOUT the explicit allowlist env.

    This forces the runner to fall back to its HOST-IMMUTABLE authorities only: the optional
    ARCLINK_UPSTREAM_REPO_URL process env (when host_repo_url is given) and the compiled-in
    canonical default. The git origin remote is deliberately NOT trusted, so a poisoned origin
    must have no effect here.
    """
    old_env = os.environ.copy()
    try:
        os.environ["ARCLINK_OPERATOR_UPGRADE_HOST_REPO_DIR"] = str(repo)
        os.environ["ARCLINK_OPERATOR_UPGRADE_HOST_PRIV_DIR"] = str(priv)
        os.environ["ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR"] = str(queue)
        os.environ.pop("ARCLINK_OPERATOR_UPGRADE_HOST_UPSTREAM_REPO_URL_ALLOWLIST", None)
        os.environ.pop("ARCLINK_UPSTREAM_REPO_URL", None)
        if host_repo_url is not None:
            os.environ["ARCLINK_UPSTREAM_REPO_URL"] = host_repo_url
        runner.process_once()
    finally:
        os.environ.clear()
        os.environ.update(old_env)


def _poison_git_origin(repo: Path, url: str) -> bool:
    """Make `git -C <repo> remote get-url origin` return `url` (the attacker-poisoned case).

    Returns False (so the caller can skip) if git is unavailable in the environment.
    """
    import shutil
    import subprocess

    if shutil.which("git") is None:
        return False
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True, env=env)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", url], check=True, env=env)
    return True


def _result(queue: Path, request_id: str) -> dict:
    return json.loads((queue / "results" / f"{request_id}.json").read_text(encoding="utf-8"))


def test_rejects_non_allowlisted_repo_url() -> None:
    runner = load_runner()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo, priv, queue, marker = _build_repo(root)
        request = _base_request(repo, priv, "op-evilrepo-0001")
        # Attacker points the root deploy at their own repo + enables the deploy key.
        request["upstream"] = {
            "ARCLINK_UPSTREAM_REPO_URL": "https://github.com/attacker/evil.git",
            "ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED": "1",
        }
        (queue / "pending" / f"{request['request_id']}.json").write_text(json.dumps(request) + "\n", encoding="utf-8")
        _drain(runner, repo, priv, queue)
        result = _result(queue, request["request_id"])
        expect(result.get("ok") is False, str(result))
        expect("upstream repo URL is not allowlisted" in str(result.get("error") or ""), str(result))
        expect(not marker.exists(), "rejected request must NOT invoke root deploy.sh")
    print("PASS test_rejects_non_allowlisted_repo_url")


def test_rejects_deploy_key_path_outside_private_state() -> None:
    runner = load_runner()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo, priv, queue, marker = _build_repo(root)
        outside_key = root / "outside" / "id_ed25519"
        outside_key.parent.mkdir(parents=True)
        outside_key.write_text("KEY\n", encoding="utf-8")
        request = _base_request(repo, priv, "op-outsidekey-0001")
        request["upstream"] = {
            "ARCLINK_UPSTREAM_REPO_URL": CANONICAL_UPSTREAM,
            "ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED": "1",
            "ARCLINK_UPSTREAM_DEPLOY_KEY_PATH": str(outside_key),
        }
        (queue / "pending" / f"{request['request_id']}.json").write_text(json.dumps(request) + "\n", encoding="utf-8")
        _drain(runner, repo, priv, queue)
        result = _result(queue, request["request_id"])
        expect(result.get("ok") is False, str(result))
        expect("must stay under private state" in str(result.get("error") or ""), str(result))
        expect(not marker.exists(), "rejected request must NOT invoke root deploy.sh")
    print("PASS test_rejects_deploy_key_path_outside_private_state")


def test_rejects_symlinked_deploy_key_path() -> None:
    runner = load_runner()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo, priv, queue, marker = _build_repo(root)
        # A key path that lives under private state and resolves to a target also
        # under private state, but the leaf component is itself a symlink. This
        # exercises the per-component symlink rejection (the broker rejects these
        # so a TOCTOU-swappable symlink cannot redirect the root deploy).
        keys_dir = priv / "state" / "upstream-keys"
        keys_dir.mkdir(parents=True)
        real_key = keys_dir / "real_id_ed25519"
        real_key.write_text("KEY\n", encoding="utf-8")
        link_path = keys_dir / "id_ed25519"
        link_path.symlink_to(real_key)
        request = _base_request(repo, priv, "op-symlinkkey-0001")
        request["upstream"] = {
            "ARCLINK_UPSTREAM_REPO_URL": CANONICAL_UPSTREAM,
            "ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED": "1",
            "ARCLINK_UPSTREAM_DEPLOY_KEY_PATH": str(link_path),
        }
        (queue / "pending" / f"{request['request_id']}.json").write_text(json.dumps(request) + "\n", encoding="utf-8")
        _drain(runner, repo, priv, queue)
        result = _result(queue, request["request_id"])
        expect(result.get("ok") is False, str(result))
        expect("must not be a symlink" in str(result.get("error") or ""), str(result))
        expect(not marker.exists(), "rejected request must NOT invoke root deploy.sh")
    print("PASS test_rejects_symlinked_deploy_key_path")


def test_rejects_deploy_key_enabled_without_key_path() -> None:
    runner = load_runner()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo, priv, queue, marker = _build_repo(root)
        request = _base_request(repo, priv, "op-enabledonly-0001")
        request["upstream"] = {
            "ARCLINK_UPSTREAM_REPO_URL": CANONICAL_UPSTREAM,
            "ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED": "1",
        }
        (queue / "pending" / f"{request['request_id']}.json").write_text(json.dumps(request) + "\n", encoding="utf-8")
        _drain(runner, repo, priv, queue)
        result = _result(queue, request["request_id"])
        expect(result.get("ok") is False, str(result))
        expect("deploy key enabled without" in str(result.get("error") or ""), str(result))
        expect(not marker.exists(), "rejected request must NOT invoke root deploy.sh")
    print("PASS test_rejects_deploy_key_enabled_without_key_path")


def test_accepts_legit_broker_shaped_request() -> None:
    runner = load_runner()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo, priv, queue, marker = _build_repo(root)
        # A confined private-state key path, exactly as the broker would confine it.
        keys_dir = priv / "state" / "upstream-keys"
        keys_dir.mkdir(parents=True)
        key_path = keys_dir / "id_ed25519"
        key_path.write_text("KEY\n", encoding="utf-8")
        known_hosts = keys_dir / "known_hosts"
        known_hosts.write_text("hosts\n", encoding="utf-8")
        request = _base_request(repo, priv, "op-legit-0001")
        request["upstream"] = {
            "ARCLINK_UPSTREAM_REPO_URL": CANONICAL_UPSTREAM,
            "ARCLINK_UPSTREAM_BRANCH": "arclink",
            "ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED": "1",
            "ARCLINK_UPSTREAM_DEPLOY_KEY_PATH": str(key_path),
            "ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE": str(known_hosts),
        }
        (queue / "pending" / f"{request['request_id']}.json").write_text(json.dumps(request) + "\n", encoding="utf-8")
        _drain(runner, repo, priv, queue)
        result = _result(queue, request["request_id"])
        expect(result.get("ok") is True and result.get("returncode") == 0, str(result))
        expect(marker.exists() and marker.read_text(encoding="utf-8").splitlines() == ["deploy upgrade"], str(marker))
    print("PASS test_accepts_legit_broker_shaped_request")


def test_rejects_request_without_created_at() -> None:
    runner = load_runner()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo, priv, queue, marker = _build_repo(root)
        request = _base_request(repo, priv, "op-nocreated-0001")
        del request["created_at"]
        (queue / "pending" / f"{request['request_id']}.json").write_text(json.dumps(request) + "\n", encoding="utf-8")
        _drain(runner, repo, priv, queue)
        result = _result(queue, request["request_id"])
        expect(result.get("ok") is False, str(result))
        expect("created_at is required" in str(result.get("error") or ""), str(result))
        expect(not marker.exists(), "request without created_at must NOT invoke root deploy.sh")
    print("PASS test_rejects_request_without_created_at")


def test_url_normalization_accepts_dot_git_and_trailing_slash_equivalence() -> None:
    runner = load_runner()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo, priv, queue, marker = _build_repo(root)
        # Allowlist carries the .git form; request omits it (+ trailing slash).
        request = _base_request(repo, priv, "op-urlnorm-0001")
        request["upstream"] = {"ARCLINK_UPSTREAM_REPO_URL": "https://github.com/sirouk/arclink/"}
        (queue / "pending" / f"{request['request_id']}.json").write_text(json.dumps(request) + "\n", encoding="utf-8")
        _drain(runner, repo, priv, queue)
        result = _result(queue, request["request_id"])
        expect(result.get("ok") is True and result.get("returncode") == 0, str(result))
        expect(marker.exists(), "allowlisted (normalized) URL should reach deploy.sh")
    print("PASS test_url_normalization_accepts_dot_git_and_trailing_slash_equivalence")


def test_normalize_repo_url_treats_ssh_and_https_of_same_repo_as_equal() -> None:
    # Rename regression: the configured/queued upstream is the SSH form (deploy key)
    # while the compiled-in canonical is HTTPS. The host runner refused a legitimate
    # upgrade ("upstream repo URL is not allowlisted") because the SSH and HTTPS forms
    # of the SAME repo did not compare equal. They must now canonicalize identically --
    # while a different host/owner/repo must STILL never match.
    runner = load_runner()
    n = runner._normalize_repo_url
    canonical = n(runner.CANONICAL_UPSTREAM_REPO_URL)
    expect(canonical == "github.com/sirouk/arclink", f"canonical normalized form: {canonical}")
    for same in (
        "git@github.com:sirouk/arclink.git",
        "https://github.com/sirouk/arclink.git",
        "ssh://git@github.com/sirouk/arclink.git",
        "https://github.com/sirouk/arclink/",
    ):
        expect(n(same) == canonical, f"same repo must match canonical: {same} -> {n(same)}")
    for evil in (
        "git@evil.com:sirouk/arclink.git",
        "git@github.com:attacker/arclink.git",
        "git@github.com:sirouk/almanac.git",
        "https://github.com/sirouk/arclink-fork.git",
    ):
        expect(n(evil) != canonical, f"different repo must NOT match canonical: {evil} -> {n(evil)}")
    print("PASS test_normalize_repo_url_treats_ssh_and_https_of_same_repo_as_equal")


def test_rejects_request_url_equal_to_poisoned_git_origin() -> None:
    """ROUND-2 fix 1: a poisoned git origin must NOT authorize a queued upstream override.

    The arclink user owns the checkout and can rewrite .git/config so that
    `git remote get-url origin` returns their repo. A queued request carrying that same URL
    (and no host-immutable allowlist authority for it) must STILL be rejected -- the runner no
    longer derives the allowlist from the origin remote.
    """
    runner = load_runner()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo, priv, queue, marker = _build_repo(root)
        poisoned = "https://github.com/attacker/evil.git"
        if not _poison_git_origin(repo, poisoned):
            print("SKIP test_rejects_request_url_equal_to_poisoned_git_origin (git unavailable)")
            return
        request = _base_request(repo, priv, "op-poisonorigin-0001")
        request["upstream"] = {
            "ARCLINK_UPSTREAM_REPO_URL": poisoned,
            "ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED": "1",
        }
        (queue / "pending" / f"{request['request_id']}.json").write_text(json.dumps(request) + "\n", encoding="utf-8")
        # No explicit allowlist env -> only host env + compiled-in canonical are trusted.
        _drain_no_explicit_allowlist(runner, repo, priv, queue)
        result = _result(queue, request["request_id"])
        expect(result.get("ok") is False, str(result))
        expect("upstream repo URL is not allowlisted" in str(result.get("error") or ""), str(result))
        expect(not marker.exists(), "poisoned-origin URL must NOT invoke root deploy.sh")
    print("PASS test_rejects_request_url_equal_to_poisoned_git_origin")


def test_omitted_upstream_pins_canonical_not_poisoned_origin() -> None:
    """ROUND-2 fix 1: an omitted upstream must pin the canonical URL, never the poisoned origin.

    deploy.sh would otherwise compute its default from `git remote get-url origin`. The runner
    pins ARCLINK_UPSTREAM_REPO_URL into the child env so the root clone can never be steered at
    the attacker remote.
    """
    runner = load_runner()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo, priv, queue, marker = _build_repo(root)
        upstream_marker = root / "deploy-upstream-url.txt"
        poisoned = "https://github.com/attacker/evil.git"
        _poison_git_origin(repo, poisoned)  # effect must be ignored even when git is present
        request = _base_request(repo, priv, "op-omitupstream-0001")
        # No "upstream" key at all.
        (queue / "pending" / f"{request['request_id']}.json").write_text(json.dumps(request) + "\n", encoding="utf-8")
        _drain_no_explicit_allowlist(runner, repo, priv, queue)
        result = _result(queue, request["request_id"])
        expect(result.get("ok") is True and result.get("returncode") == 0, str(result))
        expect(marker.exists(), "legit omitted-upstream request should reach deploy.sh")
        seen = upstream_marker.read_text(encoding="utf-8").splitlines()
        expect(seen == [CANONICAL_UPSTREAM], f"deploy.sh must see the pinned canonical URL, saw {seen}")
        expect(poisoned not in seen, "deploy.sh must NEVER see the poisoned origin URL")
    print("PASS test_omitted_upstream_pins_canonical_not_poisoned_origin")


def test_omitted_upstream_pins_host_env_when_set() -> None:
    """ROUND-2 fix 1: the host's ARCLINK_UPSTREAM_REPO_URL process env wins the pin when set."""
    runner = load_runner()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo, priv, queue, marker = _build_repo(root)
        upstream_marker = root / "deploy-upstream-url.txt"
        host_url = "https://github.com/sirouk/arclink-internal.git"
        request = _base_request(repo, priv, "op-hostpin-0001")
        (queue / "pending" / f"{request['request_id']}.json").write_text(json.dumps(request) + "\n", encoding="utf-8")
        _drain_no_explicit_allowlist(runner, repo, priv, queue, host_repo_url=host_url)
        result = _result(queue, request["request_id"])
        expect(result.get("ok") is True and result.get("returncode") == 0, str(result))
        seen = upstream_marker.read_text(encoding="utf-8").splitlines()
        expect(seen == [host_url], f"deploy.sh must see the host-env pinned URL, saw {seen}")
    print("PASS test_omitted_upstream_pins_host_env_when_set")


def test_rejects_scp_userinfo_and_redirect_url_tricks() -> None:
    """ROUND-2 fix 1: scp-style / userinfo / traversal URL tricks must not slip the allowlist."""
    runner = load_runner()
    tricks = [
        "git@evil.com:sirouk/arclink.git",                       # scp-style remote
        "ssh://git@evil.com/sirouk/arclink.git",                 # explicit ssh host swap
        "https://github.com@evil.com/sirouk/arclink.git",        # userinfo @host confusion
        "https://github.com/sirouk/arclink/../../attacker/evil",  # path traversal
        "https://github.com/sirouk/arclink.evil.git",            # lookalike suffix
    ]
    for index, trick in enumerate(tricks):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, priv, queue, marker = _build_repo(root)
            request = _base_request(repo, priv, f"op-urltrick-{index:04d}")
            request["upstream"] = {"ARCLINK_UPSTREAM_REPO_URL": trick}
            (queue / "pending" / f"{request['request_id']}.json").write_text(json.dumps(request) + "\n", encoding="utf-8")
            _drain(runner, repo, priv, queue)  # allowlist pinned to CANONICAL_UPSTREAM only
            result = _result(queue, request["request_id"])
            expect(result.get("ok") is False, f"{trick}: {result}")
            expect("upstream repo URL is not allowlisted" in str(result.get("error") or ""), f"{trick}: {result}")
            expect(not marker.exists(), f"{trick}: URL trick must NOT invoke root deploy.sh")
    print("PASS test_rejects_scp_userinfo_and_redirect_url_tricks")


def test_rejects_deploy_key_enabled_with_nonexistent_key() -> None:
    """ROUND-2 fix 2: DEPLOY_KEY_ENABLED with a confined-but-NONEXISTENT key path is rejected."""
    runner = load_runner()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo, priv, queue, marker = _build_repo(root)
        keys_dir = priv / "state" / "upstream-keys"
        keys_dir.mkdir(parents=True)
        missing_key = keys_dir / "id_ed25519"  # under private state, but never created
        request = _base_request(repo, priv, "op-missingkey-0001")
        request["upstream"] = {
            "ARCLINK_UPSTREAM_REPO_URL": CANONICAL_UPSTREAM,
            "ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED": "1",
            "ARCLINK_UPSTREAM_DEPLOY_KEY_PATH": str(missing_key),
        }
        (queue / "pending" / f"{request['request_id']}.json").write_text(json.dumps(request) + "\n", encoding="utf-8")
        _drain(runner, repo, priv, queue)
        result = _result(queue, request["request_id"])
        expect(result.get("ok") is False, str(result))
        expect("deploy key file does not exist" in str(result.get("error") or ""), str(result))
        expect(not marker.exists(), "nonexistent deploy key must NOT invoke root deploy.sh")
    print("PASS test_rejects_deploy_key_enabled_with_nonexistent_key")


def test_rejects_arclink_planted_deploy_key_by_owner() -> None:
    """ROUND-2 fix 2: a key owned by an untrusted (arclink-planted) uid is rejected.

    Requires root to chown the planted key to a non-trusted uid; skipped otherwise.
    """
    runner = load_runner()
    try:
        is_root = os.geteuid() == 0
    except AttributeError:
        is_root = False
    if not is_root:
        print("SKIP test_rejects_arclink_planted_deploy_key_by_owner (needs root to chown)")
        return
    # Pick an untrusted uid that exists and is neither 0 nor our euid.
    untrusted_uid = None
    for candidate in (65534, 1, 2, 3, 1000):
        if candidate != os.geteuid():
            untrusted_uid = candidate
            break
    if untrusted_uid is None:
        print("SKIP test_rejects_arclink_planted_deploy_key_by_owner (no untrusted uid)")
        return
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo, priv, queue, marker = _build_repo(root)
        keys_dir = priv / "state" / "upstream-keys"
        keys_dir.mkdir(parents=True)
        planted = keys_dir / "id_ed25519"
        planted.write_text("KEY\n", encoding="utf-8")
        planted.chmod(0o600)
        try:
            os.chown(planted, untrusted_uid, -1)
        except OSError:
            print("SKIP test_rejects_arclink_planted_deploy_key_by_owner (chown denied)")
            return
        request = _base_request(repo, priv, "op-plantedkey-0001")
        request["upstream"] = {
            "ARCLINK_UPSTREAM_REPO_URL": CANONICAL_UPSTREAM,
            "ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED": "1",
            "ARCLINK_UPSTREAM_DEPLOY_KEY_PATH": str(planted),
        }
        (queue / "pending" / f"{request['request_id']}.json").write_text(json.dumps(request) + "\n", encoding="utf-8")
        _drain(runner, repo, priv, queue)
        result = _result(queue, request["request_id"])
        expect(result.get("ok") is False, str(result))
        expect("not owned by a trusted account" in str(result.get("error") or ""), str(result))
        expect(not marker.exists(), "arclink-planted deploy key must NOT invoke root deploy.sh")
    print("PASS test_rejects_arclink_planted_deploy_key_by_owner")


def main() -> int:
    test_rejects_non_allowlisted_repo_url()
    test_rejects_deploy_key_path_outside_private_state()
    test_rejects_symlinked_deploy_key_path()
    test_rejects_deploy_key_enabled_without_key_path()
    test_accepts_legit_broker_shaped_request()
    test_rejects_request_without_created_at()
    test_url_normalization_accepts_dot_git_and_trailing_slash_equivalence()
    test_normalize_repo_url_treats_ssh_and_https_of_same_repo_as_equal()
    test_rejects_request_url_equal_to_poisoned_git_origin()
    test_omitted_upstream_pins_canonical_not_poisoned_origin()
    test_omitted_upstream_pins_host_env_when_set()
    test_rejects_scp_userinfo_and_redirect_url_tricks()
    test_rejects_deploy_key_enabled_with_nonexistent_key()
    test_rejects_arclink_planted_deploy_key_by_owner()
    print("ALL operator upgrade host runner confinement tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
