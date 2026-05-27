#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_module(path: Path, name: str):
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_python_module(filename: str, name: str):
    return load_module(PYTHON_DIR / filename, name)


def memory_db(control):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    return conn


def seed_active_deployment(control, fleet, conn: sqlite3.Connection, *, status: str = "active") -> dict[str, str]:
    now = control.utc_now_iso()
    user_id = "captain_surface"
    deployment_id = "pod_surface_contract"
    session_id = "onb_surface_contract"
    control.upsert_arclink_user(
        conn,
        user_id=user_id,
        email="surface-captain@example.test",
        display_name="Surface Captain",
        entitlement_state="paid",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id=deployment_id,
        user_id=user_id,
        prefix="surface-pod",
        base_domain="control.example.test",
        agent_id="agent-surface",
        agent_title="Surface Agent",
        status=status,
        metadata={"selected_plan_id": "founders", "dashboard_password": "secret://not-rendered"},
    )
    conn.execute(
        """
        INSERT INTO arclink_onboarding_sessions (
          session_id, channel, channel_identity, status, current_step,
          email_hint, display_name_hint, selected_plan_id, selected_model_id,
          user_id, deployment_id, checkout_state, metadata_json, created_at, updated_at
        ) VALUES (?, 'telegram', 'tg:surface-contract', 'first_contacted', 'first_agent_contact',
          ?, 'Surface Captain', 'founders', 'moonshotai/Kimi-K2.6-TEE',
          ?, ?, 'paid', '{}', ?, ?)
        """,
        (session_id, "surface-captain@example.test", user_id, deployment_id, now, now),
    )
    fleet.register_fleet_host(
        conn,
        host_id="host-surface",
        hostname="surface-worker",
        region="local",
        capacity_slots=2,
    )
    conn.commit()
    return {"user_id": user_id, "deployment_id": deployment_id, "session_id": session_id}


def plugin_status_samples(contract) -> list[Any]:
    samples: list[Any] = []
    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        vault = root / "vault"
        hermes_home = root / "hermes-home"
        for path in (workspace, vault, hermes_home):
            path.mkdir(parents=True, exist_ok=True)
        os.environ.clear()
        os.environ.update(old_env)
        os.environ.update(
            {
                "HOME": str(workspace),
                "HERMES_HOME": str(hermes_home),
                "DRIVE_ROOT": str(vault),
                "CODE_WORKSPACE_ROOT": str(workspace),
                "TERMINAL_WORKSPACE_ROOT": str(workspace),
                "SHELL": "/bin/sh",
            }
        )
        try:
            drive = load_module(
                REPO / "plugins/hermes-agent/drive/dashboard/plugin_api.py",
                "drive_plugin_api_surface_contract_test",
            )
            code = load_module(
                REPO / "plugins/hermes-agent/code/dashboard/plugin_api.py",
                "code_plugin_api_surface_contract_test",
            )
            terminal = load_module(
                REPO / "plugins/hermes-agent/terminal/dashboard/plugin_api.py",
                "terminal_plugin_api_surface_contract_test",
            )
            payloads = {
                "drive-plugin-status": asyncio.run(drive.status()),
                "code-plugin-status": asyncio.run(code.status()),
                "terminal-plugin-status": asyncio.run(terminal.status()),
            }
        finally:
            os.environ.clear()
            os.environ.update(old_env)
    for name, payload in payloads.items():
        samples.append(
            contract.SurfaceSample(
                name=name,
                text=json.dumps(payload, sort_keys=True),
                audience="agent",
                channel="plugin",
                required_terms=tuple(
                    term for term in ("Drive", "Code", "Terminal") if term.lower() in name
                ),
                max_chars=3600,
                max_line_chars=3600,
            )
        )
    return samples


def deploy_readiness_text() -> str:
    text = (REPO / "bin/deploy.sh").read_text(encoding="utf-8")
    return "\n".join(
        line.strip().strip('"')
        for line in text.splitlines()
        if "Sovereign provisioning readiness:" in line or "control register-worker" in line
    )


def test_surface_contract_lints_common_regressions() -> None:
    contract = load_python_module("arclink_surface_contract.py", "arclink_surface_contract_regression_test")
    sample = contract.SurfaceSample(
        name="bad-captain-copy",
        text=(
            "Traceback (most recent call last)\n"
            "File \"app.py\", line 4\n"
            "Captain, your deployment failed. An operator will inspect sk_test_example_secret."
        ),
        audience="captain",
        channel="chat",
        state="blocked",
    )
    issues = contract.surface_contract_issues(sample)
    joined = "\n".join(issues)
    expect("raw traceback" in joined, joined)
    expect("secret-looking value" in joined, joined)
    expect("ArcPod or Pod" in joined, joined)
    expect("Operator is reserved" in joined, joined)
    print("PASS test_surface_contract_lints_common_regressions")


def test_cross_surface_contract_uses_real_local_surfaces() -> None:
    contract = load_python_module("arclink_surface_contract.py", "arclink_surface_contract_real_surface_test")
    control = load_python_module("arclink_control.py", "arclink_control_surface_contract_test")
    fleet = load_python_module("arclink_fleet.py", "arclink_fleet_surface_contract_test")
    bots = load_python_module("arclink_public_bots.py", "arclink_public_bots_surface_contract_test")
    operator_raven = load_python_module("arclink_operator_raven.py", "arclink_operator_raven_surface_contract_test")
    dashboard = load_python_module("arclink_dashboard.py", "arclink_dashboard_surface_contract_test")
    surface = load_python_module("arclink_product_surface.py", "arclink_product_surface_contract_test")
    conn = memory_db(control)
    seeded = seed_active_deployment(control, fleet, conn, status="active")

    captain_start = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:new-surface-contract",
        text="/start",
        display_name_hint="Surface Captain",
    )
    conn.execute(
        "UPDATE arclink_deployments SET status = 'provisioning_failed' WHERE deployment_id = ?",
        (seeded["deployment_id"],),
    )
    conn.commit()
    captain_blocked = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:surface-contract",
        text="/connect_notion",
    )
    operator_status = operator_raven.dispatch_operator_raven_command(
        conn,
        "/operator_status",
        env={"ARCLINK_CONTROL_PROVISIONER_ENABLED": "1", "ARCLINK_EXECUTOR_ADAPTER": "fake"},
    )
    readiness = dashboard.control_node_provisioning_readiness(
        conn,
        env={"ARCLINK_CONTROL_PROVISIONER_ENABLED": "0", "ARCLINK_EXECUTOR_ADAPTER": "fake"},
    )
    product_conn = memory_db(control)
    product_home = surface.handle_arclink_product_surface_request(product_conn, method="GET", path="/")
    product_text = contract.visible_text_from_html(product_home.body)

    samples = [
        contract.SurfaceSample(
            name="captain-raven-start",
            text=captain_start.reply,
            audience="captain",
            channel="chat",
            required_terms=("Captain", "Raven", "ArcPod", "Agent", "Crew"),
            max_chars=1500,
        ),
        contract.SurfaceSample(
            name="captain-raven-blocked",
            text=captain_blocked.reply,
            audience="captain",
            channel="chat",
            state="blocked",
            required_terms=("ArcLink support",),
            max_chars=900,
        ),
        contract.SurfaceSample(
            name="operator-raven-status",
            text=str(operator_status["message"]),
            audience="operator",
            channel="chat",
            state="proof_gated",
            required_terms=("Operator Raven", "ArcPod", "Next:"),
            proof_gates=("PG-PROD", "PG-BOTS", "PG-PROVISION", "PG-UPGRADE"),
            max_chars=1600,
        ),
        contract.SurfaceSample(
            name="dashboard-readiness-blocked",
            text=json.dumps(readiness, indent=2, sort_keys=True),
            audience="operator",
            channel="dashboard",
            state="blocked",
            required_terms=("ArcPod provisioning", "next_action"),
            proof_gates=("PG-FLEET/PG-PROVISION",),
            max_chars=1800,
        ),
        contract.SurfaceSample(
            name="product-surface-home",
            text=product_text,
            audience="captain",
            channel="web",
            required_terms=("Captain", "ArcPod", "Raven"),
            max_chars=2200,
            max_line_chars=240,
        ),
        contract.SurfaceSample(
            name="deploy-readiness-cli-copy",
            text=deploy_readiness_text(),
            audience="operator",
            channel="cli",
            state="blocked",
            required_terms=("ArcPod provisioning", "control register-worker", "ready to provision ArcPods"),
            max_chars=1600,
            max_line_chars=320,
        ),
    ]
    samples.extend(plugin_status_samples(contract))
    contract.assert_surface_contract(samples)
    expect(re.search(r"\bdeployments?\b", captain_start.reply, re.IGNORECASE) is None, captain_start.reply)
    print("PASS test_cross_surface_contract_uses_real_local_surfaces")


def main() -> int:
    test_surface_contract_lints_common_regressions()
    test_cross_surface_contract_uses_real_local_surfaces()
    print("PASS all 2 surface contract tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
