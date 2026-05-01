#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from html import escape
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping
from urllib.parse import parse_qs, quote, urlencode, urlparse
from wsgiref.simple_server import make_server

from almanac_control import (
    advance_arclink_entitlement_gate,
    append_arclink_event,
    create_arclink_provisioning_job,
    ensure_schema,
    set_arclink_user_entitlement,
    transition_arclink_provisioning_job,
    upsert_arclink_service_health,
    upsert_arclink_subscription_mirror,
)
from arclink_adapters import FakeStripeClient
from arclink_api_auth import ArcLinkApiAuthError
from arclink_api_auth import queue_admin_action_api
from arclink_dashboard import (
    ArcLinkDashboardError,
    read_arclink_admin_dashboard,
    read_arclink_user_dashboard,
)
from arclink_onboarding import (
    answer_arclink_onboarding_question,
    create_or_resume_arclink_onboarding_session,
    mark_arclink_onboarding_checkout_cancelled,
    open_arclink_onboarding_checkout,
    prepare_arclink_onboarding_deployment,
)
from arclink_product import base_domain as default_base_domain
from arclink_product import chutes_default_model


DEFAULT_PRICE_ID = "price_arclink_starter"
GENERIC_REQUEST_ERROR = "Request blocked. Check input and try again."
FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="12" fill="#080808"/>'
    '<path d="M18 46 32 12l14 34h-9l-5-14-5 14z" fill="#FB5005"/>'
    "</svg>"
)


@dataclass(frozen=True)
class ArcLinkSurfaceResponse:
    status: int
    body: str
    content_type: str = "text/html; charset=utf-8"
    headers: tuple[tuple[str, str], ...] = ()


def open_arclink_product_surface_db(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def seed_arclink_product_surface_fixture(conn: sqlite3.Connection, *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    existing = conn.execute(
        "SELECT * FROM arclink_onboarding_sessions WHERE session_id = 'onb_surface_fixture'"
    ).fetchone()
    if existing is not None:
        return dict(existing)

    session = create_or_resume_arclink_onboarding_session(
        conn,
        channel="web",
        channel_identity="fixture@arclink.local",
        session_id="onb_surface_fixture",
        email_hint="fixture@arclink.local",
        display_name_hint="Fixture Operator",
        selected_plan_id="starter",
        selected_model_id=chutes_default_model(env or {}),
        current_step="checkout",
        metadata={"fixture": "product_surface"},
    )
    prepared = prepare_arclink_onboarding_deployment(
        conn,
        session_id=str(session["session_id"]),
        base_domain=default_base_domain(env or {}),
        prefix="fixture-core-1a2b",
    )
    set_arclink_user_entitlement(conn, user_id=str(prepared["user_id"]), entitlement_state="paid")
    advance_arclink_entitlement_gate(conn, deployment_id=str(prepared["deployment_id"]))
    upsert_arclink_subscription_mirror(
        conn,
        subscription_id="sub_surface_fixture",
        user_id=str(prepared["user_id"]),
        stripe_customer_id="cus_surface_fixture",
        stripe_subscription_id="sub_surface_fixture",
        status="active",
    )
    for service_name, status in (
        ("qmd-mcp", "healthy"),
        ("memory-synth", "planned"),
        ("vault-watch", "healthy"),
        ("health-watch", "healthy"),
    ):
        upsert_arclink_service_health(
            conn,
            deployment_id=str(prepared["deployment_id"]),
            service_name=service_name,
            status=status,
            detail={"source": "fixture"},
        )
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=str(prepared["deployment_id"]),
        event_type="product_surface_seeded",
        metadata={"source": "local_fixture"},
    )
    create_arclink_provisioning_job(
        conn,
        job_id="job_surface_fixture",
        deployment_id=str(prepared["deployment_id"]),
        job_kind="docker_dry_run",
        idempotency_key="surface-fixture",
    )
    transition_arclink_provisioning_job(conn, job_id="job_surface_fixture", status="running")
    transition_arclink_provisioning_job(conn, job_id="job_surface_fixture", status="succeeded")
    return prepared


def _param(params: Mapping[str, Any], key: str, default: str = "") -> str:
    value = params.get(key, default)
    if isinstance(value, list):
        value = value[0] if value else default
    return str(value or default).strip()


def _rows(conn: sqlite3.Connection, sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, args).fetchall()]


def _latest_session(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM arclink_onboarding_sessions
        ORDER BY updated_at DESC, created_at DESC
        LIMIT 1
        """
    ).fetchone()
    return dict(row) if row is not None else None


def _latest_user_id(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        """
        SELECT user_id
        FROM arclink_users
        ORDER BY updated_at DESC, created_at DESC
        LIMIT 1
        """
    ).fetchone()
    return str(row["user_id"] or "") if row is not None else ""


def _json_response(payload: Mapping[str, Any], *, status: int = 200) -> ArcLinkSurfaceResponse:
    return ArcLinkSurfaceResponse(status=status, body=json.dumps(dict(payload), sort_keys=True), content_type="application/json")


def _favicon_response() -> ArcLinkSurfaceResponse:
    return ArcLinkSurfaceResponse(status=200, body=FAVICON_SVG, content_type="image/svg+xml")


def _redirect(location: str) -> ArcLinkSurfaceResponse:
    return ArcLinkSurfaceResponse(status=303, body="", headers=(("Location", location),))


def _generic_error_response(route: str) -> ArcLinkSurfaceResponse:
    if route.startswith("/api/"):
        return _json_response({"error": GENERIC_REQUEST_ERROR}, status=400)
    body = f"<div class=\"panel\"><h1>Request blocked</h1><p>{GENERIC_REQUEST_ERROR}</p></div>"
    return ArcLinkSurfaceResponse(status=400, body=_layout("Request Error", body))


def _layout(title: str, main: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} - ArcLink</title>
  <style>
    :root {{
      color-scheme: dark;
      --jet: #080808;
      --carbon: #0F0F0E;
      --soft: #E7E6E6;
      --muted: #A9A7A3;
      --line: #282724;
      --signal: #FB5005;
      --blue: #2075FE;
      --green: #1AC153;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      max-width: 100%;
      background: var(--jet);
      color: var(--soft);
      font-family: Inter, Satoshi, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    a {{ color: var(--soft); overflow-wrap: anywhere; }}
    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding: 1rem clamp(1rem, 4vw, 2.5rem);
      border-bottom: 1px solid var(--line);
      background: var(--carbon);
      position: sticky;
      top: 0;
      z-index: 2;
    }}
    .brand {{ font-weight: 800; letter-spacing: .08em; }}
    .brand::before {{ content: ""; display: inline-block; width: .85rem; height: .85rem; border: 2px solid var(--signal); border-left-color: transparent; border-bottom-color: transparent; border-radius: 50%; margin-right: .55rem; }}
    nav {{ display: flex; gap: .75rem; flex-wrap: wrap; }}
    nav a {{ color: var(--muted); text-decoration: none; font-size: .92rem; }}
    main {{ width: min(1180px, 100%); max-width: 100%; margin: 0 auto; padding: clamp(1rem, 4vw, 2.5rem); }}
    h1, h2, h3 {{ font-family: "Space Grotesk", Inter, sans-serif; margin: 0 0 .75rem; letter-spacing: 0; }}
    h1 {{ font-size: clamp(2rem, 5vw, 4rem); line-height: 1; max-width: 13ch; }}
    h2 {{ font-size: 1.2rem; }}
    h3 {{ font-size: 1rem; }}
    p {{ color: var(--muted); margin: 0 0 1rem; }}
    .hero {{ display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(min(100%, 320px), .95fr); gap: 1.5rem; align-items: start; min-width: 0; }}
    .panel {{ border: 1px solid var(--line); border-radius: 8px; background: var(--carbon); padding: 1rem; min-width: 0; max-width: 100%; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; margin-top: 1rem; }}
    .grid.two {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .grid > *, .hero > *, .stack > * {{ min-width: 0; max-width: 100%; }}
    .stack {{ display: grid; gap: 1rem; min-width: 0; }}
    label {{ display: block; color: var(--muted); font-size: .85rem; margin-bottom: .35rem; }}
    input, select, textarea {{
      width: 100%;
      min-height: 2.6rem;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #121211;
      color: var(--soft);
      padding: .65rem .75rem;
      font: inherit;
    }}
    textarea {{ min-height: 5rem; resize: vertical; }}
    button, .button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: .4rem;
      min-height: 2.65rem;
      max-width: 100%;
      border: 1px solid var(--signal);
      border-radius: 6px;
      background: var(--signal);
      color: #080808;
      font-weight: 750;
      text-decoration: none;
      padding: .65rem .9rem;
      cursor: pointer;
      overflow-wrap: anywhere;
      white-space: normal;
    }}
    .secondary {{ background: transparent; color: var(--soft); border-color: var(--line); }}
    .metric {{ color: var(--soft); font-size: 1.45rem; font-weight: 800; }}
    .tag {{ display: inline-block; border: 1px solid var(--line); border-radius: 999px; color: var(--muted); padding: .15rem .55rem; font-size: .78rem; }}
    .section-list {{ display: flex; gap: .4rem; flex-wrap: wrap; min-width: 0; max-width: 100%; }}
    .ok {{ color: var(--green); }}
    .warn {{ color: var(--signal); }}
    table {{ display: block; width: 100%; max-width: 100%; overflow-x: auto; border-collapse: collapse; font-size: .92rem; }}
    thead, tbody, tr {{ width: 100%; }}
    th, td {{ text-align: left; border-bottom: 1px solid var(--line); padding: .6rem .35rem; vertical-align: top; overflow-wrap: anywhere; }}
    th {{ color: var(--muted); font-weight: 650; }}
    .actions {{ display: flex; gap: .6rem; flex-wrap: wrap; align-items: center; min-width: 0; max-width: 100%; }}
    @media (max-width: 820px) {{
      header {{ align-items: flex-start; flex-direction: column; }}
      nav, .actions {{ width: 100%; }}
      .hero, .grid, .grid.two {{ grid-template-columns: minmax(0, 1fr); }}
      h1 {{ max-width: none; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="brand">ARCLINK</div>
    <nav>
      <a href="/">Onboarding</a>
      <a href="/user">User Dashboard</a>
      <a href="/admin">Admin</a>
      <a href="/api/admin">API</a>
    </nav>
  </header>
  <main>{main}</main>
</body>
</html>"""


def _home(conn: sqlite3.Connection, *, error: str = "") -> ArcLinkSurfaceResponse:
    sessions = _rows(
        conn,
        """
        SELECT session_id, channel, channel_identity, status, selected_plan_id, updated_at
        FROM arclink_onboarding_sessions
        ORDER BY updated_at DESC
        LIMIT 6
        """,
    )
    deployments = _rows(
        conn,
        """
        SELECT deployment_id, user_id, prefix, base_domain, status, updated_at
        FROM arclink_deployments
        ORDER BY updated_at DESC
        LIMIT 6
        """,
    )
    session_rows = "".join(
        f"<tr><td><a href=\"/onboarding/{escape(row['session_id'])}\">{escape(row['session_id'])}</a></td><td>{escape(row['channel'])}</td><td>{escape(row['status'])}</td><td>{escape(row['selected_plan_id'])}</td></tr>"
        for row in sessions
    ) or "<tr><td colspan=\"4\">No onboarding sessions yet.</td></tr>"
    deployment_rows = "".join(
        f"<tr><td>{escape(row['prefix'])}</td><td>{escape(row['status'])}</td><td><a href=\"/user?user_id={quote(row['user_id'])}\">{escape(row['user_id'])}</a></td></tr>"
        for row in deployments
    ) or "<tr><td colspan=\"3\">No deployments yet.</td></tr>"
    error_html = f"<p class=\"warn\">{escape(error)}</p>" if error else ""
    html = f"""
<section class="hero">
  <div>
    <span class="tag">Private AI infrastructure</span>
    <h1>Your AI workforce. Deployed.</h1>
    <p>Start an ArcLink deployment, open a no-secret checkout contract, then inspect the user and admin control planes backed by local data.</p>
    <div class="grid">
      <div class="panel"><div class="metric">{len(sessions)}</div><p>Onboarding sessions</p></div>
      <div class="panel"><div class="metric">{len(deployments)}</div><p>Deployment records</p></div>
      <div class="panel"><div class="metric">0</div><p>Live provider mutations</p></div>
    </div>
  </div>
  <form class="panel stack" method="post" action="/onboarding/start">
    <h2>Start Deployment</h2>
    {error_html}
    <div><label>Email</label><input name="email" type="email" value="operator@example.test" required></div>
    <div><label>Name</label><input name="name" value="Operator"></div>
    <div><label>Plan</label><select name="plan"><option value="starter">Starter</option><option value="operator">Operator</option><option value="scale">Scale</option></select></div>
    <div><label>Model</label><input name="model" value="{escape(chutes_default_model({}))}"></div>
    <button type="submit">Start &gt;</button>
  </form>
</section>
<section class="grid two">
  <div class="panel">
    <h2>Recent Onboarding</h2>
    <table><thead><tr><th>Session</th><th>Channel</th><th>Status</th><th>Plan</th></tr></thead><tbody>{session_rows}</tbody></table>
  </div>
  <div class="panel">
    <h2>Deployment State</h2>
    <table><thead><tr><th>Prefix</th><th>Status</th><th>User</th></tr></thead><tbody>{deployment_rows}</tbody></table>
  </div>
</section>"""
    return ArcLinkSurfaceResponse(status=200, body=_layout("Onboarding", html))


def _session_page(conn: sqlite3.Connection, session_id: str, *, error: str = "") -> ArcLinkSurfaceResponse:
    row = conn.execute("SELECT * FROM arclink_onboarding_sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None:
        return ArcLinkSurfaceResponse(status=404, body=_layout("Missing Session", f"<div class=\"panel\"><h1>Session not found</h1><p>{escape(session_id)}</p></div>"))
    session = dict(row)
    events = _rows(
        conn,
        """
        SELECT event_type, created_at
        FROM arclink_onboarding_events
        WHERE session_id = ?
        ORDER BY created_at DESC
        LIMIT 10
        """,
        (session_id,),
    )
    event_rows = "".join(f"<tr><td>{escape(row['event_type'])}</td><td>{escape(row['created_at'])}</td></tr>" for row in events)
    checkout = ""
    if session.get("checkout_url"):
        checkout = f"<p>Checkout URL: <a href=\"{escape(session['checkout_url'])}\">{escape(session['checkout_url'])}</a></p>"
    error_html = f"<p class=\"warn\">{escape(error)}</p>" if error else ""
    user_link = (
        f"<a class=\"button secondary\" href=\"/user?user_id={quote(str(session['user_id']))}\">Open User Dashboard</a>"
        if session.get("user_id")
        else ""
    )
    html = f"""
<section class="grid two">
  <div class="panel stack">
    <span class="tag">{escape(session['channel'])}</span>
    <h1>{escape(session['status'])}</h1>
    <p>Step: {escape(session['current_step'] or 'started')} - Plan: {escape(session['selected_plan_id'] or 'unset')}</p>
    {checkout}
    {error_html}
    <form class="stack" method="post" action="/onboarding/{escape(session_id)}/answer">
      <div><label>Email</label><input name="email" value="{escape(session['email_hint'])}"></div>
      <div><label>Name</label><input name="name" value="{escape(session['display_name_hint'])}"></div>
      <div><label>Plan</label><input name="plan" value="{escape(session['selected_plan_id'] or 'starter')}"></div>
      <div><label>Model</label><input name="model" value="{escape(session['selected_model_id'] or chutes_default_model({}))}"></div>
      <div class="actions"><button type="submit">Save Answers &gt;</button>{user_link}<a class="button secondary" href="/admin">Admin</a></div>
    </form>
    <form method="post" action="/onboarding/{escape(session_id)}/checkout"><button type="submit">Open Fake Checkout &gt;</button></form>
    <form method="post" action="/onboarding/{escape(session_id)}/cancel"><button class="secondary" type="submit">Mark Cancelled</button></form>
  </div>
  <div class="panel">
    <h2>Funnel Events</h2>
    <table><thead><tr><th>Event</th><th>Created</th></tr></thead><tbody>{event_rows}</tbody></table>
  </div>
</section>"""
    return ArcLinkSurfaceResponse(status=200, body=_layout("Onboarding Session", html))


def _user_dashboard(conn: sqlite3.Connection, user_id: str = "") -> ArcLinkSurfaceResponse:
    clean_user = user_id or _latest_user_id(conn)
    if not clean_user:
        return _home(conn, error="Start an onboarding session before opening the user dashboard.")
    try:
        view = read_arclink_user_dashboard(conn, user_id=clean_user)
    except KeyError:
        return ArcLinkSurfaceResponse(status=404, body=_layout("Missing User", f"<div class=\"panel\"><h1>User not found</h1><p>{escape(clean_user)}</p></div>"))
    deployments = view["deployments"]
    cards = []
    for dep in deployments:
        urls = dep["access"]["urls"]
        health = "".join(
            f"<tr><td>{escape(item['service_name'])}</td><td>{escape(item['status'])}</td><td>{escape(item['checked_at'])}</td></tr>"
            for item in dep["service_health"]
        ) or "<tr><td colspan=\"3\">No service health yet.</td></tr>"
        links = "".join(f"<a class=\"button secondary\" href=\"{escape(url)}\">{escape(role)}</a>" for role, url in urls.items())
        sections = "".join(
            f"<span class=\"tag\">{escape(section['label'])}: {escape(section['status'])}</span>"
            for section in dep.get("sections", [])
        )
        cards.append(
            f"""
<div class="panel stack">
  <h2>{escape(dep['prefix'])}</h2>
  <p>Status: <span class="ok">{escape(dep['status'])}</span> - Model: {escape(dep['model']['model_id'])}</p>
  <div class="actions">{links}</div>
  <div class="grid two">
    <div><h3>Billing</h3><p>{escape(dep['billing']['entitlement_state'])}</p></div>
    <div><h3>Bot Contact</h3><p>{'contacted' if dep['bot_contact']['first_contacted'] else 'pending'}</p></div>
  </div>
  <h3>Service Health</h3>
  <table><thead><tr><th>Service</th><th>Status</th><th>Checked</th></tr></thead><tbody>{health}</tbody></table>
  <h3>Skills And Memory</h3>
  <p>qmd freshness is {escape(dep['freshness']['qmd']['status'])}; memory synthesis is {escape(dep['freshness']['memory']['status'])}. Skills expand the deployed workspace without changing this onboarding contract.</p>
  <h3>Dashboard Sections</h3>
  <div class="section-list">{sections}</div>
</div>"""
        )
    html = f"""
<section class="stack">
  <div class="panel">
    <span class="tag">User dashboard</span>
    <h1>{escape(view['user']['display_name'] or view['user']['email'] or clean_user)}</h1>
    <p>Entitlement: {escape(view['entitlement']['state'])}</p>
  </div>
  {''.join(cards) or '<div class="panel"><p>No deployments for this user.</p></div>'}
</section>"""
    return ArcLinkSurfaceResponse(status=200, body=_layout("User Dashboard", html))


def _admin_dashboard(conn: sqlite3.Connection, *, params: Mapping[str, Any] | None = None, error: str = "") -> ArcLinkSurfaceResponse:
    params = params or {}
    view = read_arclink_admin_dashboard(
        conn,
        channel=_param(params, "channel"),
        status=_param(params, "status"),
        deployment_id=_param(params, "deployment_id"),
        user_id=_param(params, "user_id"),
    )
    funnel = "".join(
        f"<tr><td>{escape(row['channel'])}</td><td>{escape(row['status'])}</td><td>{int(row['count'])}</td></tr>"
        for row in view["onboarding_funnel"]["sessions"]
    ) or "<tr><td colspan=\"3\">No sessions.</td></tr>"
    deployments = "".join(
        f"<tr><td>{escape(row['prefix'])}</td><td>{escape(row['status'])}</td><td>{escape(row['deployment_id'])}</td></tr>"
        for row in view["deployments"]
    ) or "<tr><td colspan=\"3\">No deployments.</td></tr>"
    failures = "".join(
        f"<tr><td>{escape(item['kind'])}</td><td>{escape(item.get('status', ''))}</td><td>{escape(item.get('deployment_id', ''))}</td></tr>"
        for item in view["recent_failures"]
    ) or "<tr><td colspan=\"3\">No recent failures.</td></tr>"
    actions = "".join(
        f"<tr><td>{escape(row['action_type'])}</td><td>{escape(row['status'])}</td><td>{escape(row['reason'])}</td></tr>"
        for row in view["action_intents"]
    ) or "<tr><td colspan=\"3\">No queued actions.</td></tr>"
    sections = "".join(
        f"<span class=\"tag\">{escape(section['label'])}: {escape(section['status'])}</span>"
        for section in view.get("sections", [])
    )
    target_id = _param(params, "deployment_id") or (view["deployments"][0]["deployment_id"] if view["deployments"] else "")
    error_html = f"<p class=\"warn\">{escape(error)}</p>" if error else ""
    html = f"""
<section class="stack">
  <div class="panel">
    <span class="tag">Admin control plane</span>
    <h1>Operations</h1>
    <p>Read models and queued actions only. Live Docker, Stripe, Cloudflare, Chutes, and host mutations stay behind later E2E gates.</p>
    <div class="section-list">{sections}</div>
  </div>
  <div class="grid two">
    <div class="panel"><h2>Onboarding Funnel</h2><table><thead><tr><th>Channel</th><th>Status</th><th>Count</th></tr></thead><tbody>{funnel}</tbody></table></div>
    <div class="panel"><h2>Deployments</h2><table><thead><tr><th>Prefix</th><th>Status</th><th>ID</th></tr></thead><tbody>{deployments}</tbody></table></div>
    <div class="panel"><h2>Recent Failures</h2><table><thead><tr><th>Kind</th><th>Status</th><th>Deployment</th></tr></thead><tbody>{failures}</tbody></table></div>
    <div class="panel"><h2>Queued Actions</h2><table><thead><tr><th>Action</th><th>Status</th><th>Reason</th></tr></thead><tbody>{actions}</tbody></table></div>
  </div>
    <form class="panel stack" method="post" action="/admin/actions">
    <h2>Queue Admin Action</h2>
    {error_html}
    <div><label>Admin Session ID</label><input name="session_id" autocomplete="off"></div>
    <div><label>Admin Session Token</label><input name="session_token" type="password" autocomplete="off"></div>
    <div><label>CSRF Token</label><input name="csrf_token" autocomplete="off"></div>
    <div><label>Action</label><select name="action_type"><option value="restart">Restart</option><option value="dns_repair">DNS Repair</option><option value="force_resynth">Force Resynth</option><option value="rollout">Rollout</option></select></div>
    <div><label>Target Kind</label><input name="target_kind" value="deployment"></div>
    <div><label>Target ID</label><input name="target_id" value="{escape(target_id)}"></div>
    <div><label>Reason</label><textarea name="reason">local operator requested no-secret test action</textarea></div>
    <button type="submit">Queue Action &gt;</button>
  </form>
</section>"""
    return ArcLinkSurfaceResponse(status=200, body=_layout("Admin Dashboard", html))


def _api_session(conn: sqlite3.Connection, session_id: str) -> ArcLinkSurfaceResponse:
    row = conn.execute("SELECT * FROM arclink_onboarding_sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None:
        return _json_response({"error": "not_found"}, status=404)
    events = _rows(
        conn,
        "SELECT event_type, created_at FROM arclink_onboarding_events WHERE session_id = ? ORDER BY created_at",
        (session_id,),
    )
    return _json_response({"session": dict(row), "events": events})


def handle_arclink_product_surface_request(
    conn: sqlite3.Connection,
    *,
    method: str,
    path: str,
    params: Mapping[str, Any] | None = None,
    stripe_client: Any | None = None,
    env: Mapping[str, str] | None = None,
) -> ArcLinkSurfaceResponse:
    parsed = urlparse(path)
    route = parsed.path.rstrip("/") or "/"
    query = {key: values for key, values in parse_qs(parsed.query).items()}
    merged: dict[str, Any] = dict(query)
    if params:
        merged.update(dict(params))
    clean_method = str(method or "GET").upper()
    stripe = stripe_client or FakeStripeClient()
    env = env or {}

    try:
        if clean_method == "GET" and route == "/favicon.ico":
            return _favicon_response()
        if clean_method == "GET" and route == "/":
            return _home(conn)
        if clean_method == "POST" and route == "/onboarding/start":
            email = _param(merged, "email")
            session = create_or_resume_arclink_onboarding_session(
                conn,
                channel="web",
                channel_identity=email,
                email_hint=email,
                display_name_hint=_param(merged, "name"),
                selected_plan_id=_param(merged, "plan", "starter"),
                selected_model_id=_param(merged, "model", chutes_default_model(env)),
                current_step="identity",
                metadata={"surface": "local_web"},
            )
            return _redirect(f"/onboarding/{quote(str(session['session_id']))}")
        if clean_method == "GET" and route.startswith("/onboarding/"):
            return _session_page(conn, route.rsplit("/", 1)[-1])
        if clean_method == "POST" and route.startswith("/onboarding/") and route.endswith("/answer"):
            session_id = route.split("/")[2]
            answer_arclink_onboarding_question(
                conn,
                session_id=session_id,
                question_key="local_web",
                answer_summary="local product surface answers",
                email_hint=_param(merged, "email"),
                display_name_hint=_param(merged, "name"),
                selected_plan_id=_param(merged, "plan"),
                selected_model_id=_param(merged, "model"),
            )
            return _redirect(f"/onboarding/{quote(session_id)}")
        if clean_method == "POST" and route.startswith("/onboarding/") and route.endswith("/checkout"):
            session_id = route.split("/")[2]
            root = "http://localhost:8088"
            session = open_arclink_onboarding_checkout(
                conn,
                session_id=session_id,
                stripe_client=stripe,
                price_id=_param(merged, "price_id", DEFAULT_PRICE_ID),
                success_url=f"{root}/checkout/success",
                cancel_url=f"{root}/checkout/cancel",
                base_domain=default_base_domain(env),
            )
            return _redirect(f"/onboarding/{quote(str(session['session_id']))}")
        if clean_method == "POST" and route.startswith("/onboarding/") and route.endswith("/cancel"):
            session_id = route.split("/")[2]
            mark_arclink_onboarding_checkout_cancelled(conn, session_id=session_id, reason="local_surface")
            return _redirect(f"/onboarding/{quote(session_id)}")
        if clean_method == "GET" and route == "/user":
            return _user_dashboard(conn, _param(merged, "user_id"))
        if clean_method == "GET" and route == "/admin":
            return _admin_dashboard(conn, params=merged)
        if clean_method == "POST" and route == "/admin/actions":
            result = queue_admin_action_api(
                conn,
                session_id=_param(merged, "session_id"),
                session_token=_param(merged, "session_token"),
                csrf_token=_param(merged, "csrf_token"),
                action_type=_param(merged, "action_type"),
                target_kind=_param(merged, "target_kind"),
                target_id=_param(merged, "target_id"),
                reason=_param(merged, "reason"),
                idempotency_key=_param(merged, "idempotency_key")
                or f"surface:{_param(merged, 'session_id')}:{_param(merged, 'action_type')}:{_param(merged, 'target_id')}",
                metadata={"surface": "local_admin"},
            )
            action = result.payload["action"]
            return _redirect(f"/admin?{urlencode({'queued': action['action_id'], 'deployment_id': action['target_id']})}")
        if clean_method == "GET" and route.startswith("/api/onboarding/"):
            return _api_session(conn, route.rsplit("/", 1)[-1])
        if clean_method == "GET" and route == "/api/user":
            return _json_response(read_arclink_user_dashboard(conn, user_id=_param(merged, "user_id") or _latest_user_id(conn)))
        if clean_method == "GET" and route == "/api/admin":
            return _json_response(read_arclink_admin_dashboard(conn))
        if clean_method == "POST" and route == "/api/admin/actions":
            result = queue_admin_action_api(
                conn,
                session_id=_param(merged, "session_id"),
                session_token=_param(merged, "session_token"),
                csrf_token=_param(merged, "csrf_token"),
                action_type=_param(merged, "action_type"),
                target_kind=_param(merged, "target_kind"),
                target_id=_param(merged, "target_id"),
                reason=_param(merged, "reason"),
                idempotency_key=_param(merged, "idempotency_key"),
                metadata={"surface": "api"},
            )
            return _json_response(result.payload, status=202)
    except ArcLinkApiAuthError as exc:
        if route == "/admin/actions":
            page = _admin_dashboard(conn, params=merged, error=str(exc))
            return ArcLinkSurfaceResponse(status=401, body=page.body)
        return _json_response({"error": str(exc)}, status=401)
    except ArcLinkDashboardError as exc:
        if route.startswith("/admin"):
            return _admin_dashboard(conn, params=merged, error=str(exc))
        return _json_response({"error": str(exc)}, status=400)
    except Exception:
        return _generic_error_response(route)

    return ArcLinkSurfaceResponse(status=404, body=_layout("Not Found", "<div class=\"panel\"><h1>Not found</h1></div>"))


def make_arclink_product_surface_app(
    conn: sqlite3.Connection,
    *,
    stripe_client: Any | None = None,
    env: Mapping[str, str] | None = None,
) -> Any:
    def app(environ: Mapping[str, Any], start_response: Any) -> list[bytes]:
        method = str(environ.get("REQUEST_METHOD", "GET"))
        path = str(environ.get("PATH_INFO", "/"))
        query = str(environ.get("QUERY_STRING", ""))
        length = int(str(environ.get("CONTENT_LENGTH") or "0") or 0)
        body = environ["wsgi.input"].read(length).decode("utf-8") if length else ""
        params = {key: values for key, values in parse_qs(body).items()}
        response = handle_arclink_product_surface_request(
            conn,
            method=method,
            path=f"{path}?{query}" if query else path,
            params=params,
            stripe_client=stripe_client,
            env=env,
        )
        status_text = {
            200: "200 OK",
            202: "202 Accepted",
            303: "303 See Other",
            400: "400 Bad Request",
            401: "401 Unauthorized",
            404: "404 Not Found",
        }.get(response.status, f"{response.status} OK")
        headers = [("Content-Type", response.content_type), *response.headers]
        start_response(status_text, headers)
        return [response.body.encode("utf-8")]

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local no-secret ArcLink product surface.")
    parser.add_argument("--db", default=os.environ.get("ARCLINK_PRODUCT_SURFACE_DB", ".arclink-product-surface.sqlite3"))
    parser.add_argument("--host", default=os.environ.get("ARCLINK_PRODUCT_SURFACE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("ARCLINK_PRODUCT_SURFACE_PORT", "8088")))
    parser.add_argument("--no-seed", action="store_true", help="do not seed the local fixture deployment")
    args = parser.parse_args()

    conn = open_arclink_product_surface_db(Path(args.db))
    if not args.no_seed:
        seed_arclink_product_surface_fixture(conn, env=os.environ)
    app = make_arclink_product_surface_app(conn, stripe_client=FakeStripeClient(), env=os.environ)
    with make_server(args.host, args.port, app) as server:
        print(f"ArcLink product surface listening at http://{args.host}:{args.port}")
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
