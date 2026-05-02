#!/usr/bin/env python3
"""Regression tests for arclink_pin_upgrade_check (the detector + throttle).

Locks in:
  - First detection of a new upgrade target queues exactly one operator
    notification with a digest covering every non-silenced component.
  - Subsequent runs with the same release/version target stay silenced once
    notify_count reaches the configured limit.
  - When upstream advances to a new release/version target, throttle resets
    and the operator gets a fresh notification cycle.
  - When the pin advances (operator applied the upgrade), the row is
    cleared so a future detection can start fresh.
  - The detector tolerates the component-upgrade.sh shell helper failing
    on a single component without aborting the whole pass.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PIN_DETECTOR = REPO / "python" / "arclink_pin_upgrade_check.py"
CONTROL_PY = REPO / "python" / "arclink_control.py"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_config(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"{k}={json.dumps(v)}" for k, v in values.items()) + "\n", encoding="utf-8")


def config_values(root: Path) -> dict[str, str]:
    return {
        "ARCLINK_USER": "arclink",
        "ARCLINK_HOME": str(root / "home-arclink"),
        "ARCLINK_REPO_DIR": str(REPO),
        "ARCLINK_PRIV_DIR": str(root / "priv"),
        "STATE_DIR": str(root / "state"),
        "RUNTIME_DIR": str(root / "state" / "runtime"),
        "VAULT_DIR": str(root / "vault"),
        "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
        "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
        "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
        "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
        "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
        "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
        "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
        "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
        "ARCLINK_MCP_HOST": "127.0.0.1",
        "ARCLINK_MCP_PORT": "8282",
        "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "tui-only",
        "OPERATOR_NOTIFY_CHANNEL_ID": "",
        "ARCLINK_MODEL_PRESET_CODEX": "openai:codex",
        "ARCLINK_MODEL_PRESET_OPUS": "anthropic:claude-opus",
        "ARCLINK_MODEL_PRESET_CHUTES": "chutes:model-router",
        "ARCLINK_CURATOR_CHANNELS": "tui-only",
        "ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "0",
        "ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED": "0",
    }


def _fake_check_result(detector, *, component: str, kind: str, current: str, target: str,
                       upgrade_available: bool):
    return detector.CheckResult(
        component=component,
        kind=kind,
        field={"git-commit": "ref", "git-tag": "tag", "container-image": "tag",
               "npm": "version", "nvm-version": "version",
               "release-asset": "version"}.get(kind, "ref"),
        current=current,
        target=target,
        upgrade_available=upgrade_available,
    )


def _setup_env(scratch_root: Path):
    config_path = scratch_root / "config" / "arclink.env"
    write_config(config_path, config_values(scratch_root))
    old_env = os.environ.copy()
    os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
    return old_env


def test_detector_first_run_inserts_state_and_queues_one_digest_notification() -> None:
    detector = load_module(PIN_DETECTOR, "arclink_pin_upgrade_check_first_run")
    control = load_module(CONTROL_PY, "arclink_control_pin_first_run")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        old_env = _setup_env(root)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                # Stub the shell-helper invocations: only return upgrade for
                # hermes-agent (one component), so the digest has exactly one
                # component listed.
                def fake_run_check(component: str) -> str:
                    if component == "hermes-agent":
                        return ("==> Component: hermes-agent\n"
                                "  pinned: aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\n"
                                "  latest: bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222 (branch HEAD)\n"
                                "  status: upgrade available\n")
                    return ("==> Component: " + component + "\n"
                            "  pinned: x\n  latest: x (branch HEAD)\n  status: up-to-date\n")
                detector._run_check = fake_run_check
                # Avoid the real pins-file fetch path corrupting current values.
                detector._read_pins = lambda: {
                    "components": {
                        "hermes-agent": {"kind": "git-commit", "ref": "aaaa1111" + "a" * 32},
                        "hermes-docs":  {"kind": "git-commit", "ref": "aaaa1111" + "a" * 32, "inherits_from": "hermes-agent"},
                        "code-server":  {"kind": "container-image", "tag": "4.116.0"},
                        "nvm":          {"kind": "git-tag", "tag": "v0.40.3"},
                        "node":         {"kind": "nvm-version", "version": "22"},
                        "qmd":          {"kind": "npm", "version": "latest"},
                        "nextcloud":    {"kind": "container-image", "tag": "31-apache"},
                        "postgres":     {"kind": "container-image", "tag": "16-alpine"},
                        "redis":        {"kind": "container-image", "tag": "7-alpine"},
                    }
                }

                result = detector.run_detector(conn, cfg)
                expect(result["ok"], str(result))
                expect(result["notified"], "expected the digest to be queued")
                expect(result["included"] == ["hermes-agent"], str(result["included"]))

                # Exactly one operator notification queued.
                outbox = conn.execute(
                    "SELECT message FROM notification_outbox WHERE target_kind='operator' AND delivered_at IS NULL"
                ).fetchall()
                expect(len(outbox) == 1, f"expected 1 operator notification, got {len(outbox)}")
                expect("hermes-agent" in outbox[0][0], "digest should mention the component")
                expect("[#1 of 1]" in outbox[0][0], "digest should show throttle counter #1 of 1")

                state = conn.execute(
                    "SELECT component, target_value, notify_count, silenced FROM pin_upgrade_notifications"
                ).fetchall()
                expect(len(state) == 1, str(state))
                expect(state[0][0] == "hermes-agent", str(state[0]))
                expect("bbbb2222" in state[0][1], f"target_value should contain bbbb2222, got {state[0][1]!r}")
                expect(state[0][2] == 1, f"notify_count should be 1 after first send, got {state[0][2]}")
                expect(state[0][3] == 1, f"silenced should be 1 after one send, got {state[0][3]}")
        finally:
            os.environ.clear()
            os.environ.update(old_env)
    print("PASS test_detector_first_run_inserts_state_and_queues_one_digest_notification")


def test_detector_adds_operator_buttons_for_pinned_component_digest() -> None:
    detector = load_module(PIN_DETECTOR, "arclink_pin_upgrade_check_buttons")
    control = load_module(CONTROL_PY, "arclink_control_pin_buttons")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        values = config_values(root)
        values["OPERATOR_NOTIFY_CHANNEL_PLATFORM"] = "telegram"
        values["OPERATOR_NOTIFY_CHANNEL_ID"] = "1000000001"
        values["ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED"] = "1"
        write_config(config_path, values)
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                target = "bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222"
                detector.MANAGED_COMPONENTS = ("hermes-agent", "hermes-docs")
                detector._read_pins = lambda: {
                    "components": {
                        "hermes-agent": {"kind": "git-commit", "ref": "aaaa1111" + "a" * 32},
                        "hermes-docs": {
                            "kind": "git-commit",
                            "ref": "aaaa1111" + "a" * 32,
                            "inherits_from": "hermes-agent",
                        },
                    }
                }
                detector._run_check = lambda c: (
                    f"==> Component: {c}\n"
                    "  pinned: aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\n"
                    f"  latest: {target} (branch HEAD)\n"
                    "  status: upgrade available\n"
                )

                result = detector.run_detector(conn, cfg)
                expect(result["notified"], str(result))
                expect(result["included"] == ["hermes-agent", "hermes-docs"], str(result["included"]))
                expect(result["digest"].count("./deploy.sh hermes-upgrade") == 1, result["digest"])

                row = conn.execute(
                    "SELECT extra_json FROM notification_outbox WHERE target_kind='operator' ORDER BY id DESC LIMIT 1"
                ).fetchone()
                extra = json.loads(str(row["extra_json"] or "{}"))
                token = str(extra.get("pin_upgrade_action_token") or "")
                expect(token, str(extra))
                buttons = extra.get("telegram_reply_markup", {}).get("inline_keyboard", [[]])[0]
                expect([button.get("text") for button in buttons] == ["Dismiss", "Install"], str(extra))
                expect(all(f":{token}" in str(button.get("callback_data") or "") for button in buttons), str(buttons))

                payload = control.get_pin_upgrade_action_payload(conn, token)
                expect(payload is not None, "button token should resolve to a persisted payload")
                expect(
                    [item["component"] for item in payload["items"]] == ["hermes-agent", "hermes-docs"],
                    str(payload),
                )
                expect(
                    [item["component"] for item in payload["install_items"]] == ["hermes-agent"],
                    str(payload),
                )

                dismissed = control.dismiss_pin_upgrade_action(conn, token)
                expect(
                    sorted(dismissed["silenced"]) == ["hermes-agent", "hermes-docs"],
                    str(dismissed),
                )
                state = conn.execute(
                    "SELECT component, silenced FROM pin_upgrade_notifications ORDER BY component"
                ).fetchall()
                expect([tuple(row) for row in state] == [("hermes-agent", 1), ("hermes-docs", 1)], str(state))
        finally:
            os.environ.clear()
            os.environ.update(old_env)
    print("PASS test_detector_adds_operator_buttons_for_pinned_component_digest")


def test_detector_digest_includes_git_commit_release_labels() -> None:
    detector = load_module(PIN_DETECTOR, "arclink_pin_upgrade_check_release_labels")
    control = load_module(CONTROL_PY, "arclink_control_pin_release_labels")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        old_env = _setup_env(root)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                current = "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111"
                target = "bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222"
                detector.MANAGED_COMPONENTS = ("hermes-agent",)
                detector._read_pins = lambda: {
                    "components": {
                        "hermes-agent": {
                            "kind": "git-commit",
                            "repo": "https://github.com/NousResearch/hermes-agent.git",
                            "ref": current,
                            "branch": "main",
                        },
                    }
                }
                detector._run_check = lambda c: (
                    f"==> Component: {c}\n"
                    f"  pinned: {current}\n"
                    f"  latest: {target} (branch HEAD)\n"
                    "  status: upgrade available\n"
                )
                detector._git_commit_release_label = lambda repo, ref: {
                    current: "v0.11.0 (2026.4.23)",
                    target: "v0.12.0 (2026.4.30)",
                }.get(ref, "")

                result = detector.run_detector(conn, cfg)
                expect(result["notified"], str(result))
                digest = result["digest"]
                expect(
                    "hermes-agent (git-commit): v0.11.0 (2026.4.23) [aaaa1111aaaa]"
                    in digest,
                    digest,
                )
                expect("-> v0.12.0 (2026.4.30) [bbbb2222bbbb]" in digest, digest)
                state = conn.execute(
                    "SELECT target_value, notify_count, silenced FROM pin_upgrade_notifications WHERE component='hermes-agent'"
                ).fetchone()
                expect(tuple(state) == ("v0.12.0", 1, 1), f"expected release-key throttle row, got {tuple(state)}")
        finally:
            os.environ.clear()
            os.environ.update(old_env)
    print("PASS test_detector_digest_includes_git_commit_release_labels")


def test_detector_uses_release_version_target_across_git_commit_churn() -> None:
    detector = load_module(PIN_DETECTOR, "arclink_pin_upgrade_check_release_throttle")
    control = load_module(CONTROL_PY, "arclink_control_pin_release_throttle")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        old_env = _setup_env(root)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                current = "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111"
                target_one = "bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222"
                target_two = "cccc3333cccc3333cccc3333cccc3333cccc3333"
                target_three = "dddd4444dddd4444dddd4444dddd4444dddd4444"
                detector.MANAGED_COMPONENTS = ("hermes-agent",)
                detector._read_pins = lambda: {
                    "upgrade_notifications": {"notify_limit_per_release": 1},
                    "components": {
                        "hermes-agent": {
                            "kind": "git-commit",
                            "repo": "https://github.com/NousResearch/hermes-agent.git",
                            "ref": current,
                            "branch": "main",
                        },
                    },
                }
                detector._git_commit_release_label = lambda repo, ref: {
                    current: "v0.10.0 (2026.4.1)",
                    target_one: "v0.11.0 (2026.4.23)",
                    target_two: "v0.11.0 (2026.4.23)",
                    target_three: "v0.12.0 (2026.4.30)",
                }.get(ref, "")

                # Simulate a row created before release-version throttling,
                # where target_value was the raw target commit.
                conn.execute(
                    """
                    INSERT INTO pin_upgrade_notifications (
                      component, field, current_pin, target_value, first_seen_at,
                      notify_count, silenced
                    ) VALUES ('hermes-agent', 'ref', ?, ?, '2026-04-27T00:00:00+00:00', 1, 1)
                    """,
                    (current, target_one),
                )
                conn.commit()

                detector._run_check = lambda c: (
                    f"status: upgrade available\npinned: {current}\nlatest: {target_two} (branch HEAD)\n"
                )
                res = detector.run_detector(conn, cfg)
                expect(not res["notified"], f"same release should stay silenced despite new commit: {res}")
                state = conn.execute(
                    "SELECT target_value, notify_count, silenced, extra_json FROM pin_upgrade_notifications WHERE component='hermes-agent'"
                ).fetchone()
                expect(state["target_value"] == "v0.11.0", f"legacy SHA row should migrate to release key: {dict(state)}")
                expect(state["notify_count"] == 1 and state["silenced"] == 1, f"same release must preserve throttle: {dict(state)}")
                extra = json.loads(str(state["extra_json"] or "{}"))
                expect(extra.get("raw_target") == target_two, str(extra))

                detector._run_check = lambda c: (
                    f"status: upgrade available\npinned: {current}\nlatest: {target_three} (branch HEAD)\n"
                )
                res = detector.run_detector(conn, cfg)
                expect(res["notified"], f"new release version should reset throttle: {res}")
                state = conn.execute(
                    "SELECT target_value, notify_count, silenced FROM pin_upgrade_notifications WHERE component='hermes-agent'"
                ).fetchone()
                expect(tuple(state) == ("v0.12.0", 1, 1), f"expected fresh release target row, got {tuple(state)}")
        finally:
            os.environ.clear()
            os.environ.update(old_env)
    print("PASS test_detector_uses_release_version_target_across_git_commit_churn")


def test_detector_silences_after_configured_strikes_against_same_target() -> None:
    detector = load_module(PIN_DETECTOR, "arclink_pin_upgrade_check_throttle")
    control = load_module(CONTROL_PY, "arclink_control_pin_throttle")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        old_env = _setup_env(root)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                # Stub: hermes-agent always reports the same upgrade target
                # for every detector pass.
                detector._read_pins = lambda: {
                    "upgrade_notifications": {"notify_limit_per_release": 3},
                    "components": {"hermes-agent": {"kind": "git-commit"}},
                }
                detector._run_check = lambda c: ("status: upgrade available\n"
                                                  "pinned: aaaa1111\nlatest: bbbb2222 (branch HEAD)\n")
                # Restrict the scanner to one component for clarity.
                detector.MANAGED_COMPONENTS = ("hermes-agent",)

                # First three runs: each queues a notification; counter ticks 1->3.
                for run_index in range(1, 4):
                    res = detector.run_detector(conn, cfg)
                    expect(res["notified"], f"run {run_index} should notify")
                    expect(res["included"] == ["hermes-agent"], str(res["included"]))
                    state = conn.execute(
                        "SELECT notify_count, silenced FROM pin_upgrade_notifications WHERE component='hermes-agent'"
                    ).fetchone()
                    expect(state[0] == run_index, f"run {run_index}: notify_count {state[0]} != {run_index}")

                # The third send already flips silenced=1 (count >= NOTIFY_LIMIT).
                state = conn.execute(
                    "SELECT silenced FROM pin_upgrade_notifications WHERE component='hermes-agent'"
                ).fetchone()
                expect(state[0] == 1, f"silenced should be 1 after 3 strikes, got {state[0]}")

                # Fourth run with same target: do NOT notify.
                outbox_before = conn.execute(
                    "SELECT COUNT(*) FROM notification_outbox WHERE target_kind='operator'"
                ).fetchone()[0]
                res = detector.run_detector(conn, cfg)
                expect(not res["notified"], "should not notify when silenced")
                expect(res["silenced"] == ["hermes-agent"], str(res["silenced"]))
                outbox_after = conn.execute(
                    "SELECT COUNT(*) FROM notification_outbox WHERE target_kind='operator'"
                ).fetchone()[0]
                expect(outbox_after == outbox_before,
                       f"silenced run must not enqueue: before {outbox_before}, after {outbox_after}")
        finally:
            os.environ.clear()
            os.environ.update(old_env)
    print("PASS test_detector_silences_after_configured_strikes_against_same_target")


def test_detector_resets_throttle_when_target_advances() -> None:
    detector = load_module(PIN_DETECTOR, "arclink_pin_upgrade_check_advance")
    control = load_module(CONTROL_PY, "arclink_control_pin_advance")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        old_env = _setup_env(root)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                detector._read_pins = lambda: {
                    "upgrade_notifications": {"notify_limit_per_release": 3},
                    "components": {"hermes-agent": {"kind": "git-commit"}},
                }
                detector.MANAGED_COMPONENTS = ("hermes-agent",)

                # Saturate the throttle on bbbb2222
                detector._run_check = lambda c: ("status: upgrade available\n"
                                                  "pinned: aaaa1111\nlatest: bbbb2222 (branch HEAD)\n")
                for _ in range(3):
                    detector.run_detector(conn, cfg)
                state = conn.execute(
                    "SELECT silenced, notify_count, target_value FROM pin_upgrade_notifications WHERE component='hermes-agent'"
                ).fetchone()
                expect(state[0] == 1 and state[1] == 3, f"primed state wrong: {state}")

                # Upstream advances: same component, NEW target value cccc3333.
                # Detector must reset count to 0 and notify again.
                detector._run_check = lambda c: ("status: upgrade available\n"
                                                  "pinned: aaaa1111\nlatest: cccc3333 (branch HEAD)\n")
                res = detector.run_detector(conn, cfg)
                expect(res["notified"], "must notify again when target advances")
                state = conn.execute(
                    "SELECT silenced, notify_count, target_value FROM pin_upgrade_notifications WHERE component='hermes-agent'"
                ).fetchone()
                expect(state[2] == "cccc3333", f"target should advance to cccc3333, got {state[2]}")
                expect(state[0] == 0, f"silenced should reset, got {state[0]}")
                expect(state[1] == 1, f"notify_count should be 1 after reset+send, got {state[1]}")
        finally:
            os.environ.clear()
            os.environ.update(old_env)
    print("PASS test_detector_resets_throttle_when_target_advances")


def test_detector_clears_state_when_pin_no_longer_lags_upstream() -> None:
    detector = load_module(PIN_DETECTOR, "arclink_pin_upgrade_check_cleared")
    control = load_module(CONTROL_PY, "arclink_control_pin_cleared")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        old_env = _setup_env(root)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                detector._read_pins = lambda: {"components": {"hermes-agent": {"kind": "git-commit"}}}
                detector.MANAGED_COMPONENTS = ("hermes-agent",)

                # Prime an upgrade row.
                detector._run_check = lambda c: ("status: upgrade available\n"
                                                  "pinned: aaaa1111\nlatest: bbbb2222 (branch HEAD)\n")
                detector.run_detector(conn, cfg)
                rows = conn.execute("SELECT COUNT(*) FROM pin_upgrade_notifications").fetchone()[0]
                expect(rows == 1, "row should exist before clear")

                # Operator applied the upgrade — pin matches upstream now.
                detector._run_check = lambda c: ("status: up-to-date\n"
                                                  "pinned: bbbb2222\nlatest: bbbb2222 (branch HEAD)\n")
                detector.run_detector(conn, cfg)
                rows = conn.execute("SELECT COUNT(*) FROM pin_upgrade_notifications").fetchone()[0]
                expect(rows == 0, "row should be cleared once pin no longer lags upstream")
        finally:
            os.environ.clear()
            os.environ.update(old_env)
    print("PASS test_detector_clears_state_when_pin_no_longer_lags_upstream")


def test_detector_preserves_state_on_transient_upstream_failure() -> None:
    """When `component-upgrade.sh` can't reach upstream (network/rate-limit)
    it emits `status: upstream-resolution-failed`. The detector must treat
    that as a no-op: existing throttle state stays, no new notification
    fires, and the row is NOT deleted (which would otherwise let a flapping
    network reset the throttle counter on every hiccup).
    """
    detector = load_module(PIN_DETECTOR, "arclink_pin_upgrade_check_transient")
    control = load_module(CONTROL_PY, "arclink_control_pin_transient")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        old_env = _setup_env(root)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                detector._read_pins = lambda: {
                    "upgrade_notifications": {"notify_limit_per_release": 3},
                    "components": {"hermes-agent": {"kind": "git-commit"}},
                }
                detector.MANAGED_COMPONENTS = ("hermes-agent",)

                # Prime an upgrade row (count=1).
                detector._run_check = lambda c: ("status: upgrade available\n"
                                                  "pinned: aaaa1111\nlatest: bbbb2222 (branch HEAD)\n")
                detector.run_detector(conn, cfg)
                state = conn.execute(
                    "SELECT notify_count, target_value FROM pin_upgrade_notifications "
                    "WHERE component='hermes-agent'"
                ).fetchone()
                expect(state is not None and state[0] == 1, f"primed state wrong: {state}")

                # Now upstream resolution fails. Detector must NOT delete the row
                # and must NOT enqueue a new notification.
                outbox_before = conn.execute(
                    "SELECT COUNT(*) FROM notification_outbox WHERE target_kind='operator'"
                ).fetchone()[0]
                detector._run_check = lambda c: (
                    "==> Component: hermes-agent\n"
                    "  pinned: aaaa1111\n"
                    "  status: upstream-resolution-failed (network or rate-limit)\n"
                )
                res = detector.run_detector(conn, cfg)
                expect(not res["notified"], "transient failure must not notify")
                expect(res["included"] == [], f"included should be empty, got {res['included']}")

                state = conn.execute(
                    "SELECT notify_count, target_value FROM pin_upgrade_notifications "
                    "WHERE component='hermes-agent'"
                ).fetchone()
                expect(state is not None,
                       "transient failure must NOT delete the throttle row")
                expect(state[0] == 1,
                       f"notify_count must not advance on transient failure, got {state[0]}")
                expect(state[1] == "bbbb2222",
                       f"target_value should remain bbbb2222, got {state[1]!r}")

                outbox_after = conn.execute(
                    "SELECT COUNT(*) FROM notification_outbox WHERE target_kind='operator'"
                ).fetchone()[0]
                expect(outbox_after == outbox_before,
                       f"transient run must not enqueue: before {outbox_before}, after {outbox_after}")

                # Then upstream comes back — same target — and detector resumes normal behavior.
                detector._run_check = lambda c: ("status: upgrade available\n"
                                                  "pinned: aaaa1111\nlatest: bbbb2222 (branch HEAD)\n")
                res = detector.run_detector(conn, cfg)
                expect(res["notified"], "should resume notifying once upstream recovers")
                state = conn.execute(
                    "SELECT notify_count FROM pin_upgrade_notifications WHERE component='hermes-agent'"
                ).fetchone()
                expect(state[0] == 2,
                       f"notify_count should advance to 2 after recovery, got {state[0]}")
        finally:
            os.environ.clear()
            os.environ.update(old_env)
    print("PASS test_detector_preserves_state_on_transient_upstream_failure")


def test_detector_preserves_state_on_check_runner_exception_output() -> None:
    """If the shell runner itself times out or crashes before printing normal
    check output, the detector must treat it like an upstream-resolution
    transient. Otherwise a local runner hiccup deletes the throttle row and
    re-arms noisy digests after recovery.
    """
    detector = load_module(PIN_DETECTOR, "arclink_pin_upgrade_check_runner_exception")
    control = load_module(CONTROL_PY, "arclink_control_pin_runner_exception")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        old_env = _setup_env(root)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                detector._read_pins = lambda: {"components": {"hermes-agent": {"kind": "git-commit"}}}
                detector.MANAGED_COMPONENTS = ("hermes-agent",)

                detector._run_check = lambda c: ("status: upgrade available\n"
                                                  "pinned: aaaa1111\nlatest: bbbb2222 (branch HEAD)\n")
                detector.run_detector(conn, cfg)
                state = conn.execute(
                    "SELECT notify_count, target_value FROM pin_upgrade_notifications WHERE component='hermes-agent'"
                ).fetchone()
                expect(state is not None and state[0] == 1, f"primed state wrong: {state}")

                outbox_before = conn.execute(
                    "SELECT COUNT(*) FROM notification_outbox WHERE target_kind='operator'"
                ).fetchone()[0]
                detector._run_check = lambda c: "check failed: timed out after 60 seconds"
                res = detector.run_detector(conn, cfg)
                expect(not res["notified"], str(res))
                expect(res["included"] == [], str(res))

                state = conn.execute(
                    "SELECT notify_count, target_value FROM pin_upgrade_notifications WHERE component='hermes-agent'"
                ).fetchone()
                expect(state is not None, "runner exception must preserve throttle row")
                expect(state[0] == 1, f"notify_count must not advance, got {state[0]}")
                expect(state[1] == "bbbb2222", f"target_value changed unexpectedly: {state[1]!r}")
                outbox_after = conn.execute(
                    "SELECT COUNT(*) FROM notification_outbox WHERE target_kind='operator'"
                ).fetchone()[0]
                expect(outbox_after == outbox_before, f"runner exception enqueued digest: {outbox_before}->{outbox_after}")
        finally:
            os.environ.clear()
            os.environ.update(old_env)
    print("PASS test_detector_preserves_state_on_check_runner_exception_output")


def test_run_check_marks_partial_nonzero_output_transient() -> None:
    detector = load_module(PIN_DETECTOR, "arclink_pin_upgrade_check_partial_nonzero")
    detector._read_pins = lambda: {"components": {"hermes-agent": {"kind": "git-commit", "ref": "aaaa1111"}}}

    def fake_run(*args, **kwargs):
        return detector.subprocess.CompletedProcess(
            args=["component-upgrade"],
            returncode=128,
            stdout=("==> Component: hermes-agent\n"
                    "  pinned: aaaa1111\n"),
            stderr="",
        )

    detector.subprocess.run = fake_run
    output = detector._run_check("hermes-agent")
    expect("status: upstream-resolution-failed (check runner exited 128)" in output, output)
    parsed = detector._parse_check_output("hermes-agent", "git-commit", output)
    expect(parsed.transient_failure, f"partial nonzero helper output should parse as transient: {parsed}")
    expect(not parsed.upgrade_available, str(parsed))
    print("PASS test_run_check_marks_partial_nonzero_output_transient")


def main() -> int:
    test_detector_first_run_inserts_state_and_queues_one_digest_notification()
    test_detector_adds_operator_buttons_for_pinned_component_digest()
    test_detector_digest_includes_git_commit_release_labels()
    test_detector_uses_release_version_target_across_git_commit_churn()
    test_detector_silences_after_configured_strikes_against_same_target()
    test_detector_resets_throttle_when_target_advances()
    test_detector_clears_state_when_pin_no_longer_lags_upstream()
    test_detector_preserves_state_on_transient_upstream_failure()
    test_detector_preserves_state_on_check_runner_exception_output()
    test_run_check_marks_partial_nonzero_output_transient()
    print("PASS all 10 pin-upgrade detector regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
