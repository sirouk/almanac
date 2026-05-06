#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from __future__ import annotations

import html
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default)).strip()


def https_host(name: str) -> str:
    host = env(name)
    return f"https://{host}" if host else ""


def env_url(name: str, fallback: str = "") -> str:
    value = env(name)
    if value.startswith("https://"):
        return value
    return fallback


def path_url(host: str, prefix: str, suffix: str = "") -> str:
    if not host or not prefix:
        return ""
    clean_suffix = suffix if suffix.startswith("/") or not suffix else f"/{suffix}"
    return f"https://{host}/u/{prefix}{clean_suffix}"


def public_state() -> dict[str, str]:
    prefix = env("ARCLINK_PREFIX")
    dashboard_host = env("ARCLINK_DASHBOARD_HOST")
    files_host = env("ARCLINK_FILES_HOST")
    code_host = env("ARCLINK_CODE_HOST")
    hermes_host = env("ARCLINK_HERMES_HOST")
    path_mode = (
        env("ARCLINK_INGRESS_MODE") == "tailscale"
        and env("ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY", "path") == "path"
    )
    dashboard_fallback = path_url(dashboard_host, prefix) if path_mode else https_host("ARCLINK_DASHBOARD_HOST")
    files_fallback = path_url(files_host, prefix, "/files") if path_mode else https_host("ARCLINK_FILES_HOST")
    code_fallback = path_url(code_host, prefix, "/code") if path_mode else https_host("ARCLINK_CODE_HOST")
    hermes_fallback = path_url(hermes_host, prefix, "/hermes") if path_mode else https_host("ARCLINK_HERMES_HOST")
    return {
        "deployment_id": env("ARCLINK_DEPLOYMENT_ID"),
        "prefix": prefix,
        "dashboard": env_url("ARCLINK_DASHBOARD_URL", dashboard_fallback),
        "files": env_url("ARCLINK_FILES_URL", files_fallback),
        "code": env_url("ARCLINK_CODE_URL", code_fallback),
        "hermes": env_url("ARCLINK_HERMES_URL", hermes_fallback),
        "provider": env("ARCLINK_PRIMARY_PROVIDER", "chutes"),
        "model": env("ARCLINK_CHUTES_DEFAULT_MODEL"),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "ArcLinkDashboard/0.1"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/health"):
            self._send(200, b'{"status":"ok"}\n', "application/json")
            return
        state = public_state()
        links = "\n".join(
            f'<li><a href="{html.escape(url)}">{html.escape(label.title())}</a></li>'
            for label, url in state.items()
            if label in {"files", "code", "hermes"} and url
        )
        page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ArcLink Agent</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
    body {{ margin: 0; min-height: 100vh; background: #080b10; color: #ecf4ff; display: grid; place-items: center; }}
    main {{ width: min(680px, calc(100vw - 32px)); }}
    h1 {{ font-size: clamp(32px, 6vw, 64px); margin: 0 0 12px; letter-spacing: 0; }}
    p {{ color: #aab7c7; line-height: 1.6; }}
    ul {{ display: grid; gap: 10px; padding: 0; margin: 28px 0 0; list-style: none; }}
    a {{ display: block; border: 1px solid #263244; border-radius: 8px; padding: 14px 16px; color: #d9f7ff; text-decoration: none; background: #101722; }}
    a:hover {{ border-color: #5fd4ff; }}
    code {{ color: #9be7c8; }}
  </style>
</head>
<body>
  <main>
    <h1>ArcLink Agent</h1>
    <p>Deployment <code>{html.escape(state["deployment_id"])}</code> is online with {html.escape(state["provider"])} / {html.escape(state["model"])}.</p>
    <ul>{links}</ul>
  </main>
</body>
</html>
"""
        self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")

    def log_message(self, fmt: str, *args: object) -> None:
        print(fmt % args)


ThreadingHTTPServer(("0.0.0.0", 3000), Handler).serve_forever()
PY
