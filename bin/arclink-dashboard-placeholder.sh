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


def public_state() -> dict[str, str]:
    return {
        "deployment_id": env("ARCLINK_DEPLOYMENT_ID"),
        "prefix": env("ARCLINK_PREFIX"),
        "dashboard": f"https://{env('ARCLINK_DASHBOARD_HOST')}",
        "files": f"https://{env('ARCLINK_FILES_HOST')}",
        "code": f"https://{env('ARCLINK_CODE_HOST')}",
        "hermes": f"https://{env('ARCLINK_HERMES_HOST')}",
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
            if label in {"files", "code", "hermes"} and url.strip("https://")
        )
        page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ArcLink Pod</title>
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
    <h1>ArcLink Pod</h1>
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
