#!/usr/bin/env python3
"""Regression tests for config/pins.json + bin/pins.sh.

Locks in:
  - pins.json parses, schema-version is 1, every component has the kind-
    required fields (matches the schema's allOf if/then rules).
  - bin/pins.sh round-trips a value (get → set → get) without corrupting
    sibling components.
  - bin/common.sh resolves ARCLINK_HERMES_AGENT_REF through pins.json
    (not the literal fallback constants).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PINS_JSON = REPO / "config" / "pins.json"
PINS_SH = REPO / "bin" / "pins.sh"
COMMON_SH = REPO / "bin" / "common.sh"
BOOTSTRAP_USERLAND = REPO / "bin" / "bootstrap-userland.sh"
COMPONENT_UPGRADE = REPO / "bin" / "component-upgrade.sh"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_pins_json_parses_and_has_required_components() -> None:
    data = json.loads(PINS_JSON.read_text(encoding="utf-8"))
    expect(data.get("version") == 1, f"unexpected schema version: {data.get('version')!r}")
    components = data.get("components") or {}
    # Every component currently in scope MUST be present so the deployment
    # never regresses to silently floating one of them.
    required_components = {
        "hermes-agent",
        "hermes-docs",
        "nvm",
        "node",
        "python",
        "qmd",
        "nextcloud",
        "postgres",
        "redis",
        "uv",
        "tailscale",
        "quarto",
    }
    missing = required_components - set(components.keys())
    expect(not missing, f"pins.json is missing required components: {sorted(missing)}")
    notify_limit = data.get("upgrade_notifications", {}).get("notify_limit_per_release")
    expect(notify_limit == 1, f"upgrade notify limit should default to once per release, got {notify_limit!r}")
    print("PASS test_pins_json_parses_and_has_required_components")


def test_pins_json_kind_required_fields_present() -> None:
    """Spot-check the same allOf if/then rules the JSON schema enforces.

    Keeps the test free of a third-party schema validator dep - pure stdlib.
    """
    data = json.loads(PINS_JSON.read_text(encoding="utf-8"))
    components = data["components"]

    def has(c, *keys):
        return all(c.get(k) is not None for k in keys)

    rules = {
        "git-commit":      lambda c: has(c, "repo", "ref"),
        "git-tag":         lambda c: has(c, "repo", "tag"),
        "container-image": lambda c: has(c, "image", "tag"),
        "npm":             lambda c: has(c, "package", "version"),
        "nvm-version":     lambda c: has(c, "version"),
        "uv-python":       lambda c: has(c, "preferred", "minimum"),
        "installer-url":   lambda c: has(c, "url"),
        "release-asset":   lambda c: has(c, "repo"),
    }
    for name, comp in components.items():
        kind = comp.get("kind")
        expect(kind in rules, f"{name}: unknown kind {kind!r}")
        rule = rules[kind]
        expect(rule(comp), f"{name} (kind={kind}): missing kind-required fields: {comp}")
        expect(comp.get("description"), f"{name}: description must be a non-empty string")
    print("PASS test_pins_json_kind_required_fields_present")


def test_qmd_pin_is_explicit_semver() -> None:
    """qmd is the recall engine. It must not float on npm latest because a
    surprise retrieval/index behavior change would reach every agent.
    """
    data = json.loads(PINS_JSON.read_text(encoding="utf-8"))
    qmd = data["components"]["qmd"]
    version = str(qmd.get("version") or "")
    expect(re.fullmatch(r"\d+\.\d+\.\d+", version) is not None, f"qmd version must be explicit semver, got {version!r}")
    expect("latest" not in version.lower(), f"qmd version must not float on latest: {version!r}")
    print("PASS test_qmd_pin_is_explicit_semver")


def test_bootstrap_userland_enforces_qmd_pin() -> None:
    text = BOOTSTRAP_USERLAND.read_text(encoding="utf-8")
    expect("__pins_get_or_default qmd version" in text, "bootstrap must read qmd version from pins.json")
    expect("qmd --version" in text, "bootstrap must inspect installed qmd version")
    expect('installed_version" != "$qmd_version' in text, "bootstrap must reinstall qmd when installed version drifts")
    print("PASS test_bootstrap_userland_enforces_qmd_pin")


def test_pins_sh_round_trip_does_not_corrupt_other_components() -> None:
    """Copy pins.json to a tempfile, set + get a field, ensure other
    components stay byte-identical.
    """
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp) / "pins.json"
        shutil.copy(PINS_JSON, scratch)
        env = {**os.environ, "ARCLINK_PINS_FILE": str(scratch)}

        before_other = json.loads(scratch.read_text())["components"]["nextcloud"]
        # set a fake ref on hermes-agent (no commit, no push - just file edit)
        subprocess.check_call([
            "bash", "-c",
            f"source {PINS_SH}; pins_set hermes-agent ref deadbeef" + "deadbeef" * 4
        ], env=env)
        # round-trip via get
        out = subprocess.check_output([
            "bash", "-c",
            f"source {PINS_SH}; pins_get hermes-agent ref"
        ], env=env, text=True).strip()
        expect(out == "deadbeef" + "deadbeef" * 4, f"round-trip got {out!r}")

        after_other = json.loads(scratch.read_text())["components"]["nextcloud"]
        expect(before_other == after_other, "pins_set leaked into a sibling component")
    print("PASS test_pins_sh_round_trip_does_not_corrupt_other_components")


def test_pins_sh_resolve_inherited_ref_for_hermes_docs() -> None:
    """hermes-docs declares inherits_from: hermes-agent. The resolver must
    return the hermes-agent ref unless hermes-docs has its own.
    """
    data = json.loads(PINS_JSON.read_text())
    expected = data["components"]["hermes-agent"]["ref"]
    out = subprocess.check_output([
        "bash", "-c",
        f"source {PINS_SH}; pins_resolve_inherited_ref hermes-docs"
    ], text=True).strip()
    expect(out == expected, f"inherited ref mismatch: got {out!r}, expected {expected!r}")
    print("PASS test_pins_sh_resolve_inherited_ref_for_hermes_docs")


def test_common_sh_reads_hermes_pin_from_pins_json() -> None:
    """Source bin/common.sh and check that the resolved env vars match the
    values in pins.json (not stale config/env or hard-coded fallback constants).
    """
    data = json.loads(PINS_JSON.read_text())
    expected_ref = data["components"]["hermes-agent"]["ref"]
    expected_docs_ref = data["components"]["hermes-docs"]["ref"]

    out = subprocess.check_output([
        "bash", "-c",
        f"set -e; cd {REPO}; "
        "ARCLINK_HERMES_AGENT_REF=0000000000000000000000000000000000000000; "
        "ARCLINK_HERMES_DOCS_REF=1111111111111111111111111111111111111111; "
        f"source {COMMON_SH} 2>/dev/null || true; "
        "echo $ARCLINK_HERMES_AGENT_REF; echo $ARCLINK_HERMES_DOCS_REF; echo ${ARCLINK_AGENT_CODE_SERVER_IMAGE:-}"
    ], text=True).splitlines()
    expect(out[0] == expected_ref, f"hermes pin: got {out[0]!r}, expected {expected_ref!r}")
    expect(out[1] == expected_docs_ref, f"hermes docs pin: got {out[1]!r}, expected {expected_docs_ref!r}")
    expect(out[2] == "", f"legacy code-server image env should not be synthesized, got {out[2]!r}")
    print("PASS test_common_sh_reads_hermes_pin_from_pins_json")


def test_hermes_upgrade_check_is_read_only() -> None:
    """`./deploy.sh hermes-upgrade-check` must not modify pins.json."""
    before = PINS_JSON.read_bytes()
    # Run the check; ignore network failures (offline CI) - the structural
    # invariant is "doesn't write to pins.json".
    subprocess.run(
        ["bash", str(REPO / "deploy.sh"), "hermes-upgrade-check"],
        env={**os.environ, "PATH": os.environ.get("PATH", "")},
        capture_output=True,
        timeout=60,
    )
    after = PINS_JSON.read_bytes()
    expect(before == after, "hermes-upgrade-check modified pins.json (must be read-only)")
    print("PASS test_hermes_upgrade_check_is_read_only")


def test_component_upgrade_resolves_reachable_raw_sha_after_branch_advances() -> None:
    """Digest buttons pass exact SHAs. If upstream advances before the
    operator clicks Install, that SHA may no longer be a ref tip but should
    still be accepted when the remote can fetch it directly.
    """
    old_sha = "a" * 40
    digest_sha = "b" * 40
    advanced_sha = "c" * 40
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        scratch = root / "pins.json"
        scratch.write_text(
            json.dumps(
                {
                    "version": 1,
                    "components": {
                        "hermes-agent": {
                            "kind": "git-commit",
                            "repo": "https://example.invalid/hermes-agent.git",
                            "branch": "main",
                            "ref": old_sha,
                            "description": "test",
                        },
                        "hermes-docs": {
                            "kind": "git-commit",
                            "repo": "https://example.invalid/hermes-agent.git",
                            "branch": "main",
                            "ref": old_sha,
                            "inherits_from": "hermes-agent",
                            "description": "test",
                        },
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        fake_bin = root / "bin"
        fake_bin.mkdir()
        fake_git = fake_bin / "git"
        fake_git.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env bash",
                    "set -euo pipefail",
                    f"digest_sha={digest_sha!r}",
                    f"advanced_sha={advanced_sha!r}",
                    "args=(\"$@\")",
                    "if [[ \"${args[0]:-}\" == \"-C\" ]]; then",
                    "  args=(\"${args[@]:2}\")",
                    "fi",
                    "case \"${args[0]:-}\" in",
                    "  ls-remote)",
                    "    if [[ \"${args[2]:-}\" == \"refs/heads/arclink\" ]]; then",
                    "      printf '%s\\trefs/heads/arclink\\n' \"$advanced_sha\"",
                    "    else",
                    "      printf '%s\\tHEAD\\n%s\\trefs/heads/arclink\\n' \"$advanced_sha\" \"$advanced_sha\"",
                    "    fi",
                    "    ;;",
                    "  init)",
                    "    exit 0",
                    "    ;;",
                    "  fetch)",
                    "    [[ \" ${args[*]} \" == *\" $digest_sha \"* ]]",
                    "    ;;",
                    "  rev-parse)",
                    "    printf '%s\\n' \"$digest_sha\"",
                    "    ;;",
                    "  *)",
                    "    printf 'unexpected fake git args: %s\\n' \"${args[*]}\" >&2",
                    "    exit 1",
                    "    ;;",
                    "esac",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        fake_git.chmod(0o755)

        result = subprocess.run(
            [
                "bash",
                str(COMPONENT_UPGRADE),
                "hermes-agent",
                "apply",
                "--ref",
                digest_sha,
                "--dry-run",
            ],
            env={
                **os.environ,
                "ARCLINK_PINS_FILE": str(scratch),
                "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
            },
            text=True,
            capture_output=True,
            timeout=30,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        expect(result.returncode == 0, combined)
        expect(f"hermes-agent.ref {old_sha} -> {digest_sha}" in combined, combined)
    print("PASS test_component_upgrade_resolves_reachable_raw_sha_after_branch_advances")


def test_component_upgrade_check_reports_status_when_git_resolver_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        fakebin = Path(tmp) / "bin"
        fakebin.mkdir()
        fake_git = fakebin / "git"
        fake_git.write_text("#!/usr/bin/env bash\nexit 128\n", encoding="utf-8")
        fake_git.chmod(0o755)
        env = {**os.environ, "PATH": f"{fakebin}:{os.environ.get('PATH', '')}"}
        result = subprocess.run(
            ["bash", str(COMPONENT_UPGRADE), "hermes-agent", "check"],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        expect(result.returncode == 0, combined)
        expect("pinned:" in combined, combined)
        expect("status: upstream-resolution-failed" in combined, combined)
    print("PASS test_component_upgrade_check_reports_status_when_git_resolver_fails")


def test_component_upgrade_commits_pending_pin_bump_without_git_identity() -> None:
    """Queued root/operator upgrades may not have global git user config.

    If a prior attempt wrote and staged pins.json before `git commit` failed,
    re-running the same target sees the pin already at the requested value.
    It must still commit and push that pending diff with a deterministic
    ArcLink author identity.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        repo.mkdir()
        (repo / "bin").mkdir()
        (repo / "config").mkdir()
        shutil.copy(COMPONENT_UPGRADE, repo / "bin" / "component-upgrade.sh")
        shutil.copy(PINS_SH, repo / "bin" / "pins.sh")
        pins_path = repo / "config" / "pins.json"
        pins_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "components": {
                        "nvm": {
                            "kind": "nvm-version",
                            "version": "v22.22.2",
                            "description": "Node version managed by nvm.",
                        }
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-b", "arclink"], cwd=repo, check=True, capture_output=True, text=True)
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, text=True)
        initial_env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Initial Test",
            "GIT_AUTHOR_EMAIL": "initial@example.test",
            "GIT_COMMITTER_NAME": "Initial Test",
            "GIT_COMMITTER_EMAIL": "initial@example.test",
        }
        subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, env=initial_env, check=True, capture_output=True, text=True)
        remote = root / "remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)
        subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repo, check=True, capture_output=True, text=True)

        data = json.loads(pins_path.read_text(encoding="utf-8"))
        data["components"]["nvm"]["version"] = "v99.0.0"
        pins_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        subprocess.run(["git", "add", "--", "config/pins.json"], cwd=repo, check=True, capture_output=True, text=True)

        key_path = root / "upstream-key"
        known_hosts = root / "known_hosts"
        key_path.write_text("not-a-real-key\n", encoding="utf-8")
        known_hosts.write_text("", encoding="utf-8")
        home = root / "empty-home"
        home.mkdir()
        env = {
            **os.environ,
            "ARCLINK_UPSTREAM_DEPLOY_KEY_PATH": str(key_path),
            "ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE": str(known_hosts),
            "ARCLINK_UPSTREAM_BRANCH": "arclink",
            "GIT_CONFIG_GLOBAL": str(root / "missing-global-gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "HOME": str(home),
            "EMAIL": "",
        }
        for key in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
            env.pop(key, None)
        result = subprocess.run(
            [
                "bash",
                str(repo / "bin" / "component-upgrade.sh"),
                "nvm",
                "apply",
                "--version",
                "v99.0.0",
                "--skip-upgrade",
            ],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        expect(result.returncode == 0, combined)
        expect("uncommitted diff; committing pending bump" in combined, combined)
        author = subprocess.check_output(["git", "log", "-1", "--format=%an <%ae>"], cwd=repo, text=True).strip()
        expect(author == "ArcLink Upgrade Bot <arclink-upgrade@localhost>", author)
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        remote_head = subprocess.check_output(
            ["git", f"--git-dir={remote}", "rev-parse", "refs/heads/arclink"],
            text=True,
        ).strip()
        expect(remote_head == head, f"remote arclink {remote_head} did not receive {head}")
    print("PASS test_component_upgrade_commits_pending_pin_bump_without_git_identity")


def test_component_upgrade_rebases_pin_commit_when_remote_arclink_advances() -> None:
    """The deployed checkout can be stale when an operator clicks Install.

    The helper should replay the just-created pins commit onto the current
    upstream branch before pushing, instead of failing with git's "fetch first"
    non-fast-forward rejection.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        repo.mkdir()
        (repo / "bin").mkdir()
        (repo / "config").mkdir()
        shutil.copy(COMPONENT_UPGRADE, repo / "bin" / "component-upgrade.sh")
        shutil.copy(PINS_SH, repo / "bin" / "pins.sh")
        pins_path = repo / "config" / "pins.json"
        pins_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "components": {
                        "nvm": {
                            "kind": "nvm-version",
                            "version": "v22.22.2",
                            "description": "Node version managed by nvm.",
                        }
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-b", "arclink"], cwd=repo, check=True, capture_output=True, text=True)
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, text=True)
        commit_env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Initial Test",
            "GIT_AUTHOR_EMAIL": "initial@example.test",
            "GIT_COMMITTER_NAME": "Initial Test",
            "GIT_COMMITTER_EMAIL": "initial@example.test",
        }
        subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, env=commit_env, check=True, capture_output=True, text=True)
        remote = root / "remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)
        subprocess.run(["git", f"--git-dir={remote}", "symbolic-ref", "HEAD", "refs/heads/arclink"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repo, check=True, capture_output=True, text=True)
        subprocess.run(["git", "push", "-u", "origin", "arclink"], cwd=repo, check=True, capture_output=True, text=True)

        advancer = root / "advancer"
        subprocess.run(["git", "clone", str(remote), str(advancer)], check=True, capture_output=True, text=True)
        (advancer / "remote-only.txt").write_text("remote advanced\n", encoding="utf-8")
        subprocess.run(["git", "add", "remote-only.txt"], cwd=advancer, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "remote advance"], cwd=advancer, env=commit_env, check=True, capture_output=True, text=True)
        subprocess.run(["git", "push", "origin", "arclink"], cwd=advancer, check=True, capture_output=True, text=True)

        key_path = root / "upstream-key"
        known_hosts = root / "known_hosts"
        key_path.write_text("not-a-real-key\n", encoding="utf-8")
        known_hosts.write_text("", encoding="utf-8")
        home = root / "empty-home"
        home.mkdir()
        env = {
            **os.environ,
            "ARCLINK_UPSTREAM_DEPLOY_KEY_PATH": str(key_path),
            "ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE": str(known_hosts),
            "ARCLINK_UPSTREAM_BRANCH": "arclink",
            "GIT_CONFIG_GLOBAL": str(root / "missing-global-gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "HOME": str(home),
            "EMAIL": "",
        }
        for key in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
            env.pop(key, None)
        result = subprocess.run(
            [
                "bash",
                str(repo / "bin" / "component-upgrade.sh"),
                "nvm",
                "apply",
                "--version",
                "v99.0.0",
                "--skip-upgrade",
            ],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        expect(result.returncode == 0, combined)
        expect("Rebasing local pins commit onto origin/arclink before push" in combined, combined)

        remote_pins = subprocess.check_output(
            ["git", f"--git-dir={remote}", "show", "refs/heads/arclink:config/pins.json"],
            text=True,
        )
        remote_data = json.loads(remote_pins)
        expect(remote_data["components"]["nvm"]["version"] == "v99.0.0", remote_data)
        remote_note = subprocess.check_output(
            ["git", f"--git-dir={remote}", "show", "refs/heads/arclink:remote-only.txt"],
            text=True,
        ).strip()
        expect(remote_note == "remote advanced", remote_note)
    print("PASS test_component_upgrade_rebases_pin_commit_when_remote_arclink_advances")


def test_component_upgrade_requires_deploy_key_before_writing_pin() -> None:
    """A canonical upgrade must not silently become a local-only dirty pin.

    Operators can choose --skip-push for local work, but the default apply path
    is supposed to commit and push so deploy can consume the canonical branch.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        repo.mkdir()
        (repo / "bin").mkdir()
        (repo / "config").mkdir()
        shutil.copy(COMPONENT_UPGRADE, repo / "bin" / "component-upgrade.sh")
        shutil.copy(PINS_SH, repo / "bin" / "pins.sh")
        pins_path = repo / "config" / "pins.json"
        pins_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "components": {
                        "nvm": {
                            "kind": "nvm-version",
                            "version": "v22.22.2",
                            "description": "Node version managed by nvm.",
                        }
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-b", "arclink"], cwd=repo, check=True, capture_output=True, text=True)
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, text=True)
        initial_env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Initial Test",
            "GIT_AUTHOR_EMAIL": "initial@example.test",
            "GIT_COMMITTER_NAME": "Initial Test",
            "GIT_COMMITTER_EMAIL": "initial@example.test",
        }
        subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, env=initial_env, check=True, capture_output=True, text=True)

        env = {**os.environ}
        for key in (
            "ARCLINK_UPSTREAM_DEPLOY_KEY_PATH",
            "ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE",
            "GIT_AUTHOR_NAME",
            "GIT_AUTHOR_EMAIL",
            "GIT_COMMITTER_NAME",
            "GIT_COMMITTER_EMAIL",
        ):
            env.pop(key, None)

        result = subprocess.run(
            [
                "bash",
                str(repo / "bin" / "component-upgrade.sh"),
                "nvm",
                "apply",
                "--version",
                "v99.0.0",
            ],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        expect(result.returncode != 0, combined)
        expect("cannot commit + push pins.json" in combined, combined)
        data = json.loads(pins_path.read_text(encoding="utf-8"))
        expect(data["components"]["nvm"]["version"] == "v22.22.2", data)
        status = subprocess.check_output(["git", "status", "--short"], cwd=repo, text=True).strip()
        expect(status == "", status)
    print("PASS test_component_upgrade_requires_deploy_key_before_writing_pin")


def test_component_upgrade_reexec_discovers_operator_config_artifact() -> None:
    body = COMPONENT_UPGRADE.read_text(encoding="utf-8")
    reexec = body[body.index("reexec_upgrade() {"):body.index("do_apply() {")]
    expect('local discovered_config="${ARCLINK_CONFIG_FILE:-}"' in reexec, reexec)
    expect('local artifact="${REPO_DIR}/.arclink-operator.env"' in reexec, reexec)
    expect("ARCLINK_OPERATOR_DEPLOYED_CONFIG" in reexec, reexec)
    expect('ARCLINK_CONFIG_FILE="$discovered_config"' in reexec, reexec)
    expect('/home/arclink/arclink/arclink-priv/config/arclink.env' in reexec, reexec)
    print("PASS test_component_upgrade_reexec_discovers_operator_config_artifact")


def main() -> int:
    test_pins_json_parses_and_has_required_components()
    test_pins_json_kind_required_fields_present()
    test_qmd_pin_is_explicit_semver()
    test_bootstrap_userland_enforces_qmd_pin()
    test_pins_sh_round_trip_does_not_corrupt_other_components()
    test_pins_sh_resolve_inherited_ref_for_hermes_docs()
    test_common_sh_reads_hermes_pin_from_pins_json()
    test_hermes_upgrade_check_is_read_only()
    test_component_upgrade_resolves_reachable_raw_sha_after_branch_advances()
    test_component_upgrade_check_reports_status_when_git_resolver_fails()
    test_component_upgrade_commits_pending_pin_bump_without_git_identity()
    test_component_upgrade_rebases_pin_commit_when_remote_arclink_advances()
    test_component_upgrade_requires_deploy_key_before_writing_pin()
    test_component_upgrade_reexec_discovers_operator_config_artifact()
    print("PASS all 14 pins regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
