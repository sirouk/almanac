"""Shared test utilities for ArcLink test suite."""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
import time
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


def memory_db(control):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    return conn


def seed_active_public_bot_deployment(
    control,
    conn,
    *,
    channel: str = "telegram",
    channel_identity: str = "tg:42",
    prefix: str = "arc-testpod",
    base_domain: str = "control.example.ts.net",
    display_name: str = "Bot Buyer",
) -> dict[str, str]:
    user_id = f"arcusr_{prefix.replace('-', '_')}"
    deployment_id = f"arcdep_{prefix.replace('-', '_')}"
    session_id = f"onb_{prefix.replace('-', '_')}"
    now = control.utc_now_iso()
    control.upsert_arclink_user(
        conn,
        user_id=user_id,
        email=f"{prefix}@example.test",
        display_name=display_name,
        entitlement_state="paid",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id=deployment_id,
        user_id=user_id,
        prefix=prefix,
        base_domain=base_domain,
        status="active",
        metadata={
            "ingress_mode": "tailscale",
            "tailscale_dns_name": base_domain,
            "tailscale_host_strategy": "path",
            "selected_plan_id": "sovereign",
        },
    )
    conn.execute(
        """
        INSERT INTO arclink_onboarding_sessions (
          session_id, channel, channel_identity, status, current_step,
          email_hint, display_name_hint, selected_plan_id, selected_model_id,
          user_id, deployment_id, checkout_state, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, 'first_contacted', 'first_agent_contact', ?, ?, 'sovereign', 'moonshotai/Kimi-K2.6-TEE', ?, ?, 'paid', '{}', ?, ?)
        """,
        (
            session_id,
            channel,
            channel_identity,
            f"{prefix}@example.test",
            display_name,
            user_id,
            deployment_id,
            now,
            now,
        ),
    )
    conn.commit()
    return {"user_id": user_id, "deployment_id": deployment_id, "session_id": session_id, "prefix": prefix}


def auth_headers(session: dict, *, csrf: bool = False) -> dict[str, str]:
    """Build Authorization + Session-Id headers from a session dict."""
    h = {
        "Authorization": f"Bearer {session['session_token']}",
        "X-ArcLink-Session-Id": session["session_id"],
    }
    if csrf:
        h["X-ArcLink-CSRF-Token"] = session["csrf_token"]
    return h


def sign_stripe(adapters, payload: str) -> str:
    """Sign a Stripe webhook payload using the test secret."""
    return adapters.sign_stripe_webhook(payload, "whsec_test", timestamp=int(time.time()))
