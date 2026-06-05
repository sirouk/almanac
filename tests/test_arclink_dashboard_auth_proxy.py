#!/usr/bin/env python3
from __future__ import annotations

import http.client
import http.server
import importlib.util
import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlencode

REPO = Path(__file__).resolve().parents[1]
PROXY_PY = REPO / "python" / "arclink_dashboard_auth_proxy.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class TestBackend(http.server.BaseHTTPRequestHandler):
    last_authorization: str | None = None
    last_cookie: str | None = None
    last_accept_encoding: str | None = None
    last_session_token: str | None = None

    def do_GET(self) -> None:  # noqa: N802
        type(self).last_authorization = self.headers.get("Authorization")
        type(self).last_cookie = self.headers.get("Cookie")
        type(self).last_accept_encoding = self.headers.get("Accept-Encoding")
        type(self).last_session_token = self.headers.get("X-Hermes-Session-Token")
        if self.path in {"/", "/drive"}:
            body = (
                b'<html><head><script>window.__HERMES_SESSION_TOKEN__="backend-session-token";</script></head>'
                b"<body>dashboard<button>RESTART GATEWAY</button><button>UPDATE HERMES</button></body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/mounted-spa":
            body = (
                b'<!doctype html><html><head><link rel="stylesheet" href="/assets/index.css">'
                b'<script type="module" src="/assets/index.js"></script></head>'
                b'<body><img src="/assets/logo.png" srcset="/assets/logo.png 1x, /assets/logo@2x.png 2x">'
                b'<a href="/drive">Drive</a><form action="/api/mutate"></form>'
                b'<script>fetch("/api/status");</script></body></html>'
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/private":
            if self.headers.get("Authorization") != "Bearer hermes-session-token":
                body = b'{"detail":"Unauthorized"}'
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/plugin-private":
            if self.headers.get("X-Hermes-Session-Token") != "backend-session-token":
                body = b'{"detail":"Unauthorized"}'
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/dashboard/plugins":
            body = json.dumps(
                {
                    "plugins": [
                        {
                            "id": "code",
                            "script": "/dashboard-plugins/code/dist/index.js",
                            "style": "/dashboard-plugins/code/dist/style.css",
                        }
                    ],
                    "server_path": "/home/arc-test/not-a-browser-url",
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/assets/index.css":
            body = b'@font-face{src:url("/fonts/font.woff2")}body{background:url(/ds-assets/bg.jpg)}'
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/large-json":
            body = b'{"asset":"/assets/large.json","ok":true,"padding":"' + (b"x" * 2048) + b'"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/download.bin":
            body = b"binary-download-proof"
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        type(self).last_authorization = self.headers.get("Authorization")
        type(self).last_cookie = self.headers.get("Cookie")
        type(self).last_accept_encoding = self.headers.get("Accept-Encoding")
        type(self).last_session_token = self.headers.get("X-Hermes-Session-Token")
        if self.path == "/api/mutate":
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def request(
    port: int,
    path: str,
    *,
    method: str = "GET",
    body: bytes | str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], str]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        payload = body.encode("utf-8") if isinstance(body, str) else body
        connection.request(method, path, body=payload, headers=headers or {})
        response = connection.getresponse()
        response_body = response.read().decode("utf-8", "replace")
        return response.status, dict(response.getheaders()), response_body
    finally:
        connection.close()


def request_with_header_pairs(
    port: int,
    path: str,
    *,
    method: str = "GET",
    body: bytes | str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, list[tuple[str, str]], str]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        payload = body.encode("utf-8") if isinstance(body, str) else body
        connection.request(method, path, body=payload, headers=headers or {})
        response = connection.getresponse()
        response_body = response.read().decode("utf-8", "replace")
        return response.status, response.getheaders(), response_body
    finally:
        connection.close()


def start_proxy(proxy_mod, access_file: Path):
    backend = proxy_mod.ThreadingHTTPServer(("127.0.0.1", 0), TestBackend)
    backend_thread = threading.Thread(target=backend.serve_forever, daemon=True)
    backend_thread.start()

    handler = type(
        "ConfiguredProxyHandler",
        (proxy_mod.ProxyHandler,),
        {
            "access_file": access_file,
            "target": f"http://127.0.0.1:{backend.server_port}",
            "realm": "Hermes",
        },
    )
    proxy = proxy_mod.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    proxy_thread.start()
    return backend, backend_thread, proxy, proxy_thread


def stop_proxy(backend, backend_thread, proxy, proxy_thread) -> None:
    proxy.shutdown()
    proxy.server_close()
    proxy_thread.join(timeout=5)
    backend.shutdown()
    backend.server_close()
    backend_thread.join(timeout=5)


def cookie_pair(cookie_header: str) -> str:
    return str(cookie_header or "").split(";", 1)[0]


def cookie_name(cookie_header: str) -> str:
    return cookie_pair(cookie_header).split("=", 1)[0]


def login(port: int, *, username: str = "alex", password: str = "test-password") -> str:
    body = urlencode({"username": username, "password": password, "next": "/"})
    status, headers, _body = request(
        port,
        "/__arclink/login",
        method="POST",
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    expect(status == 303, f"expected login redirect, saw {status} {headers}")
    cookie = headers.get("Set-Cookie") or ""
    expect(cookie_name(cookie).startswith("arclink_dash_session_"), headers)
    return cookie


def login_cookie_header(port: int, *, username: str = "alex", password: str = "test-password") -> str:
    body = urlencode({"username": username, "password": password, "next": "/"})
    status, headers, _body = request_with_header_pairs(
        port,
        "/__arclink/login",
        method="POST",
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    expect(status == 303, f"expected login redirect, saw {status} {headers}")
    cookies = [
        cookie_pair(value)
        for key, value in headers
        if key.lower() == "set-cookie" and "Max-Age=0" not in value
    ]
    expect(any(cookie.startswith("arclink_dash_session_") for cookie in cookies), str(headers))
    return "; ".join(cookies)


def test_proxy_allows_hermes_bearer_api_calls_after_session_login() -> None:
    proxy_mod = load_module(PROXY_PY, "arclink_dashboard_auth_proxy_test")
    with tempfile.TemporaryDirectory() as tmp:
        access_file = Path(tmp) / "arclink-web-access.json"
        access_file.write_text(
            json.dumps({"username": "alex", "password": "test-password", "session_secret": "session-secret"}),
            encoding="utf-8",
        )

        backend, backend_thread, proxy, proxy_thread = start_proxy(proxy_mod, access_file)
        try:
            status, headers, body = request(proxy.server_port, "/")
            expect(status == 401, f"expected 401 login gate, saw {status} {headers}")
            expect("WWW-Authenticate" not in headers, headers)
            expect("<form" in body and "password" in body.lower(), body)

            cookie = login(proxy.server_port)

            status, headers, body = request(
                proxy.server_port,
                "/api/private",
                headers={"Authorization": "Bearer hermes-session-token"},
            )
            expect(status == 401, f"expected proxy login gate without cookie, saw {status} {headers} {body!r}")
            expect("WWW-Authenticate" not in headers, headers)

            status, headers, body = request(
                proxy.server_port,
                "/api/private",
                headers={
                    "Authorization": "Bearer hermes-session-token",
                    "Cookie": cookie,
                },
            )
            expect(status == 200, f"expected protected API success, saw {status} {headers} {body!r}")
            expect(TestBackend.last_authorization == "Bearer hermes-session-token", TestBackend.last_authorization)
            expect(
                TestBackend.last_cookie in (None, ""),
                f"expected proxy session cookie to stay at the proxy, saw {TestBackend.last_cookie!r}",
            )
            print("PASS test_proxy_allows_hermes_bearer_api_calls_after_session_login")
        finally:
            stop_proxy(backend, backend_thread, proxy, proxy_thread)


def test_proxy_bridges_arclink_session_to_backend_hermes_api_token() -> None:
    proxy_mod = load_module(PROXY_PY, "arclink_dashboard_auth_proxy_backend_token_test")
    with tempfile.TemporaryDirectory() as tmp:
        access_file = Path(tmp) / "arclink-web-access.json"
        access_file.write_text(
            json.dumps({"username": "alex", "password": "test-password", "session_secret": "session-secret"}),
            encoding="utf-8",
        )

        backend, backend_thread, proxy, proxy_thread = start_proxy(proxy_mod, access_file)
        try:
            cookie = login(proxy.server_port)

            status, headers, body = request(
                proxy.server_port,
                "/api/plugin-private",
                headers={
                    "Cookie": cookie,
                    "X-Hermes-Session-Token": "browser-supplied-bogus-token",
                },
            )
            expect(status == 200, f"expected bridged plugin API success, saw {status} {headers} {body!r}")
            expect(
                TestBackend.last_session_token == "backend-session-token",
                f"expected proxy to inject backend token, saw {TestBackend.last_session_token!r}",
            )
            print("PASS test_proxy_bridges_arclink_session_to_backend_hermes_api_token")
        finally:
            stop_proxy(backend, backend_thread, proxy, proxy_thread)


def test_proxy_bounds_public_login_body_and_streams_large_backend_responses() -> None:
    proxy_mod = load_module(PROXY_PY, "arclink_dashboard_auth_proxy_streaming_body_limit_test")
    with tempfile.TemporaryDirectory() as tmp:
        access_file = Path(tmp) / "arclink-web-access.json"
        access_file.write_text(
            json.dumps({"username": "alex", "password": "test-password", "session_secret": "session-secret"}),
            encoding="utf-8",
        )

        old_env = os.environ.copy()
        os.environ["ARCLINK_DASHBOARD_PROXY_MAX_LOGIN_BODY_BYTES"] = "16"
        os.environ["ARCLINK_DASHBOARD_PROXY_REWRITE_BUFFER_BYTES"] = "16"
        backend, backend_thread, proxy, proxy_thread = start_proxy(proxy_mod, access_file)
        try:
            status, _headers, body = request(
                proxy.server_port,
                "/__arclink/login",
                method="POST",
                body="username=alex&password=this-body-is-too-large",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            expect(status == 413 and "too large" in body.lower(), f"expected capped login body, saw {status} {body!r}")

            os.environ["ARCLINK_DASHBOARD_PROXY_MAX_LOGIN_BODY_BYTES"] = str(64 * 1024)
            cookie = login(proxy.server_port)
            status, _headers, body = request(
                proxy.server_port,
                "/large-json",
                headers={"Cookie": cookie, "X-Forwarded-Prefix": "/agent/atlas"},
            )
            expect(status == 200, f"expected large JSON stream success, saw {status} {body!r}")
            expect('"/assets/large.json"' in body, "large JSON should stream without mount-prefix rewriting")

            status, _headers, body = request(proxy.server_port, "/download.bin", headers={"Cookie": cookie})
            expect(status == 200 and body == "binary-download-proof", f"expected streamed binary response, saw {status} {body!r}")
            print("PASS test_proxy_bounds_public_login_body_and_streams_large_backend_responses")
        finally:
            stop_proxy(backend, backend_thread, proxy, proxy_thread)
            os.environ.clear()
            os.environ.update(old_env)


def test_proxy_login_normalizes_email_username_and_copied_password_whitespace() -> None:
    proxy_mod = load_module(PROXY_PY, "arclink_dashboard_auth_proxy_normalized_login_test")
    with tempfile.TemporaryDirectory() as tmp:
        access_file = Path(tmp) / "arclink-web-access.json"
        access_file.write_text(
            json.dumps(
                {
                    "username": "owner@example.test",
                    "password": "arc_test_password",
                    "session_secret": "session-secret",
                }
            ),
            encoding="utf-8",
        )

        backend, backend_thread, proxy, proxy_thread = start_proxy(proxy_mod, access_file)
        try:
            cookie = login(
                proxy.server_port,
                username="  OWNER@EXAMPLE.TEST  ",
                password="arc_test_password\n",
            )
            status, headers, body = request(proxy.server_port, "/", headers={"Cookie": cookie})
            expect(status == 200, f"expected normalized login success, saw {status} {headers} {body!r}")
            print("PASS test_proxy_login_normalizes_email_username_and_copied_password_whitespace")
        finally:
            stop_proxy(backend, backend_thread, proxy, proxy_thread)


def test_proxy_scopes_session_cookie_per_dashboard_instance() -> None:
    proxy_mod = load_module(PROXY_PY, "arclink_dashboard_auth_proxy_scoped_cookie_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        access_one = root / "one" / "arclink-web-access.json"
        access_two = root / "two" / "arclink-web-access.json"
        access_one.parent.mkdir(parents=True, exist_ok=True)
        access_two.parent.mkdir(parents=True, exist_ok=True)
        access_one.write_text(
            json.dumps(
                {
                    "username": "captain@example.test",
                    "password": "shared-dashboard-password",
                    "session_secret": "session-secret-one",
                    "deployment_id": "arcdep_one",
                    "prefix": "one-agent",
                }
            ),
            encoding="utf-8",
        )
        access_two.write_text(
            json.dumps(
                {
                    "username": "captain@example.test",
                    "password": "shared-dashboard-password",
                    "session_secret": "session-secret-two",
                    "deployment_id": "arcdep_two",
                    "prefix": "two-agent",
                }
            ),
            encoding="utf-8",
        )

        backend_one, backend_thread_one, proxy_one, proxy_thread_one = start_proxy(proxy_mod, access_one)
        backend_two, backend_thread_two, proxy_two, proxy_thread_two = start_proxy(proxy_mod, access_two)
        try:
            first_cookie = login(
                proxy_one.server_port,
                username="captain@example.test",
                password="shared-dashboard-password",
            )
            second_cookie = login(
                proxy_two.server_port,
                username="captain@example.test",
                password="shared-dashboard-password",
            )
            expect(cookie_name(first_cookie) != cookie_name(second_cookie), f"expected scoped cookie names, got {first_cookie} and {second_cookie}")
            browser_cookie_header = f"{cookie_pair(first_cookie)}; {cookie_pair(second_cookie)}"

            status, headers, body = request(proxy_one.server_port, "/", headers={"Cookie": browser_cookie_header})
            expect(status == 200, f"expected first dashboard to stay logged in, saw {status} {headers} {body!r}")
            status, headers, body = request(proxy_two.server_port, "/", headers={"Cookie": browser_cookie_header})
            expect(status == 200, f"expected second dashboard to stay logged in, saw {status} {headers} {body!r}")
            expect(
                TestBackend.last_cookie in (None, ""),
                f"expected dashboard session cookies to stay at proxy, saw backend cookie {TestBackend.last_cookie!r}",
            )
            print("PASS test_proxy_scopes_session_cookie_per_dashboard_instance")
        finally:
            stop_proxy(backend_one, backend_thread_one, proxy_one, proxy_thread_one)
            stop_proxy(backend_two, backend_thread_two, proxy_two, proxy_thread_two)


def test_proxy_accepts_user_scoped_sso_cookie_across_agent_dashboards() -> None:
    proxy_mod = load_module(PROXY_PY, "arclink_dashboard_auth_proxy_sso_cookie_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        access_one = root / "one" / "arclink-web-access.json"
        access_two = root / "two" / "arclink-web-access.json"
        access_other = root / "other" / "arclink-web-access.json"
        for path in (access_one, access_two, access_other):
            path.parent.mkdir(parents=True, exist_ok=True)
        shared = {
            "username": "captain@example.test",
            "password": "shared-dashboard-password",
            "sso_session_secret": "shared-sso-secret",
            "sso_subject": "user_1",
        }
        access_one.write_text(json.dumps({**shared, "session_secret": "session-one", "deployment_id": "arcdep_one", "prefix": "one"}), encoding="utf-8")
        access_two.write_text(json.dumps({**shared, "session_secret": "session-two", "deployment_id": "arcdep_two", "prefix": "two"}), encoding="utf-8")
        access_other.write_text(
            json.dumps(
                {
                    "username": "other@example.test",
                    "password": "other-password",
                    "session_secret": "session-other",
                    "sso_session_secret": "other-sso-secret",
                    "sso_subject": "user_2",
                    "deployment_id": "arcdep_other",
                    "prefix": "other",
                }
            ),
            encoding="utf-8",
        )

        backend_one, backend_thread_one, proxy_one, proxy_thread_one = start_proxy(proxy_mod, access_one)
        backend_two, backend_thread_two, proxy_two, proxy_thread_two = start_proxy(proxy_mod, access_two)
        backend_other, backend_thread_other, proxy_other, proxy_thread_other = start_proxy(proxy_mod, access_other)
        try:
            browser_cookie_header = login_cookie_header(
                proxy_one.server_port,
                username="captain@example.test",
                password="shared-dashboard-password",
            )
            sso_cookie = "; ".join(
                part.strip()
                for part in browser_cookie_header.split(";")
                if part.strip().startswith("arclink_dash_sso_")
            )
            expect(sso_cookie, browser_cookie_header)

            status, headers, body = request(proxy_two.server_port, "/", headers={"Cookie": sso_cookie})
            expect(status == 200, f"expected SSO cookie to open sibling dashboard, saw {status} {headers} {body!r}")
            expect(
                TestBackend.last_cookie in (None, ""),
                f"expected SSO cookie to stay at proxy, saw backend cookie {TestBackend.last_cookie!r}",
            )

            status, headers, body = request(proxy_other.server_port, "/", headers={"Cookie": sso_cookie})
            expect(status == 401, f"expected SSO cookie to be rejected for another Captain, saw {status} {headers} {body!r}")
            print("PASS test_proxy_accepts_user_scoped_sso_cookie_across_agent_dashboards")
        finally:
            stop_proxy(backend_one, backend_thread_one, proxy_one, proxy_thread_one)
            stop_proxy(backend_two, backend_thread_two, proxy_two, proxy_thread_two)
            stop_proxy(backend_other, backend_thread_other, proxy_other, proxy_thread_other)


def test_proxy_rejects_session_and_sso_cookies_after_revocation_epoch() -> None:
    proxy_mod = load_module(PROXY_PY, "arclink_dashboard_auth_proxy_revocation_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        access_one = root / "one" / "arclink-web-access.json"
        access_two = root / "two" / "arclink-web-access.json"
        access_one.parent.mkdir(parents=True, exist_ok=True)
        access_two.parent.mkdir(parents=True, exist_ok=True)
        shared = {
            "username": "captain@example.test",
            "password": "shared-dashboard-password",
            "sso_session_secret": "shared-sso-secret",
            "sso_subject": "user_1",
        }
        one_payload = {**shared, "session_secret": "session-one", "deployment_id": "arcdep_one", "prefix": "one"}
        two_payload = {**shared, "session_secret": "session-two", "deployment_id": "arcdep_two", "prefix": "two"}
        access_one.write_text(json.dumps(one_payload), encoding="utf-8")
        access_two.write_text(json.dumps(two_payload), encoding="utf-8")

        backend_one, backend_thread_one, proxy_one, proxy_thread_one = start_proxy(proxy_mod, access_one)
        backend_two, backend_thread_two, proxy_two, proxy_thread_two = start_proxy(proxy_mod, access_two)
        try:
            browser_cookie_header = login_cookie_header(
                proxy_one.server_port,
                username="captain@example.test",
                password="shared-dashboard-password",
            )
            session_cookie = "; ".join(
                part.strip()
                for part in browser_cookie_header.split(";")
                if part.strip().startswith("arclink_dash_session_")
            )
            sso_cookie = "; ".join(
                part.strip()
                for part in browser_cookie_header.split(";")
                if part.strip().startswith("arclink_dash_sso_")
            )
            expect(session_cookie and sso_cookie, browser_cookie_header)

            status, headers, body = request(proxy_one.server_port, "/", headers={"Cookie": session_cookie})
            expect(status == 200, f"expected session cookie before revocation, saw {status} {headers} {body!r}")
            status, headers, body = request(proxy_two.server_port, "/", headers={"Cookie": sso_cookie})
            expect(status == 200, f"expected SSO cookie before revocation, saw {status} {headers} {body!r}")

            access_one.write_text(
                json.dumps({**one_payload, "dashboard_session_revoked_before": 4102444800}),
                encoding="utf-8",
            )
            access_two.write_text(
                json.dumps({**two_payload, "dashboard_sso_revoked_before": 4102444800}),
                encoding="utf-8",
            )

            status, headers, body = request(proxy_one.server_port, "/", headers={"Cookie": session_cookie})
            expect(status == 401, f"expected session cookie rejection after revocation, saw {status} {headers} {body!r}")
            status, headers, body = request(proxy_two.server_port, "/", headers={"Cookie": sso_cookie})
            expect(status == 401, f"expected SSO cookie rejection after revocation, saw {status} {headers} {body!r}")
            print("PASS test_proxy_rejects_session_and_sso_cookies_after_revocation_epoch")
        finally:
            stop_proxy(backend_one, backend_thread_one, proxy_one, proxy_thread_one)
            stop_proxy(backend_two, backend_thread_two, proxy_two, proxy_thread_two)


def test_proxy_injects_crew_switcher_from_access_state() -> None:
    proxy_mod = load_module(PROXY_PY, "arclink_dashboard_auth_proxy_crew_switcher_test")
    with tempfile.TemporaryDirectory() as tmp:
        access_file = Path(tmp) / "arclink-web-access.json"
        access_file.write_text(
            json.dumps(
                {
                    "username": "alex",
                    "password": "test-password",
                    "session_secret": "session-secret",
                    "crew_dashboards": [
                        {
                            "label": "Atlas",
                            "title": "Research Lead",
                            "status": "active",
                            "theme_label": "ArcLink Signal Orange",
                            "url": "https://hermes-atlas.example.test",
                            "current": True,
                        },
                        {
                            "label": "Vela </script>",
                            "title": "Signal Strategist",
                            "status": "active",
                            "theme_label": "Deep Violet",
                            "url": "https://hermes-vela.example.test",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        backend, backend_thread, proxy, proxy_thread = start_proxy(proxy_mod, access_file)
        try:
            cookie = login(proxy.server_port)
            status, headers, body = request(proxy.server_port, "/", headers={"Cookie": cookie})
            expect(status == 200, f"expected dashboard response, saw {status} {headers}")
            expect("data-arclink-crew-switcher" in body, body)
            expect("Atlas" in body and "Research Lead" in body, body)
            expect("hermes-vela.example.test" in body, body)
            expect("Vela </script>" not in body, body)
            expect("\\u003c/script\\u003e" in body, body)
            print("PASS test_proxy_injects_crew_switcher_from_access_state")
        finally:
            stop_proxy(backend, backend_thread, proxy, proxy_thread)


def test_proxy_rejects_basic_headers_and_injects_dashboard_plugin_deeplink_helper() -> None:
    proxy_mod = load_module(PROXY_PY, "arclink_dashboard_auth_proxy_deeplink_test")
    with tempfile.TemporaryDirectory() as tmp:
        access_file = Path(tmp) / "arclink-web-access.json"
        access_file.write_text(
            json.dumps({"username": "alex", "password": "test-password", "session_secret": "session-secret"}),
            encoding="utf-8",
        )

        backend, backend_thread, proxy, proxy_thread = start_proxy(proxy_mod, access_file)
        try:
            status, headers, _body = request(proxy.server_port, "/drive", headers={"Authorization": "Basic tainted"})
            expect(status == 401, f"expected Basic header to be ignored, saw {status} {headers}")
            expect("WWW-Authenticate" not in headers, headers)

            cookie = login(proxy.server_port)
            status, headers, body = request(proxy.server_port, "/drive", headers={"Cookie": cookie})
            expect(status == 200, f"expected successful dashboard response, saw {status} {headers}")
            expect("data-arclink-plugin-deeplink" in body, body)
            expect('target="/drive"' in body or "target='/drive'" in body or 'target=\\"/drive\\"' in body, body)
            expect(headers.get("Content-Length") == str(len(body.encode("utf-8"))), headers)
            print("PASS test_proxy_rejects_basic_headers_and_injects_dashboard_plugin_deeplink_helper")
        finally:
            stop_proxy(backend, backend_thread, proxy, proxy_thread)


def test_proxy_can_run_dashboard_helpers_without_auth() -> None:
    proxy_mod = load_module(PROXY_PY, "arclink_dashboard_auth_proxy_no_auth_test")
    with tempfile.TemporaryDirectory() as tmp:
        access_file = Path(tmp) / "arclink-web-access.json"
        access_file.write_text(
            json.dumps({"username": "unused", "password": "unused"}),
            encoding="utf-8",
        )

        backend = proxy_mod.ThreadingHTTPServer(("127.0.0.1", 0), TestBackend)
        backend_thread = threading.Thread(target=backend.serve_forever, daemon=True)
        backend_thread.start()

        handler = type(
            "ConfiguredProxyHandler",
            (proxy_mod.ProxyHandler,),
            {
                "access_file": access_file,
                "target": f"http://127.0.0.1:{backend.server_port}",
                "realm": "Hermes",
                "require_auth": False,
            },
        )
        proxy = proxy_mod.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        proxy_thread.start()

        try:
            status, headers, body = request(proxy.server_port, "/drive")
            expect(status == 200, f"expected no-auth dashboard response, saw {status} {headers} {body!r}")
            expect("WWW-Authenticate" not in headers, headers)
            expect("data-arclink-plugin-deeplink" in body, body)
            print("PASS test_proxy_can_run_dashboard_helpers_without_auth")
        finally:
            stop_proxy(backend, backend_thread, proxy, proxy_thread)


def test_proxy_rejects_cross_origin_dashboard_mutations() -> None:
    proxy_mod = load_module(PROXY_PY, "arclink_dashboard_auth_proxy_csrf_test")
    with tempfile.TemporaryDirectory() as tmp:
        access_file = Path(tmp) / "arclink-web-access.json"
        access_file.write_text(
            json.dumps({"username": "alex", "password": "test-password", "session_secret": "session-secret"}),
            encoding="utf-8",
        )

        backend, backend_thread, proxy, proxy_thread = start_proxy(proxy_mod, access_file)
        try:
            cookie = login(proxy.server_port)
            same_origin = f"http://127.0.0.1:{proxy.server_port}"
            status, _headers, body = request(
                proxy.server_port,
                "/api/mutate",
                method="POST",
                body="{}",
                headers={"Cookie": cookie, "Origin": same_origin},
            )
            expect(status == 200, f"expected same-origin mutation success, saw {status} {body!r}")

            status, _headers, body = request(
                proxy.server_port,
                "/api/mutate",
                method="POST",
                body="{}",
                headers={"Cookie": cookie, "Origin": "https://example.invalid"},
            )
            expect(status == 403, f"expected cross-origin mutation rejection, saw {status} {body!r}")
            expect("Cross-origin" in body, body)

            status, _headers, body = request(
                proxy.server_port,
                "/api/mutate",
                method="POST",
                body="{}",
                headers={"Cookie": cookie},
            )
            expect(status == 403, f"expected headerless mutation rejection, saw {status} {body!r}")
            expect("Cross-origin" in body, body)
            print("PASS test_proxy_rejects_cross_origin_dashboard_mutations")
        finally:
            stop_proxy(backend, backend_thread, proxy, proxy_thread)


def test_proxy_login_is_safe_behind_stripped_mount_prefix() -> None:
    proxy_mod = load_module(PROXY_PY, "arclink_dashboard_auth_proxy_mount_test")
    with tempfile.TemporaryDirectory() as tmp:
        access_file = Path(tmp) / "arclink-web-access.json"
        access_file.write_text(
            json.dumps({"username": "arc-test", "password": "test-password", "session_secret": "session-secret"}),
            encoding="utf-8",
        )

        backend, backend_thread, proxy, proxy_thread = start_proxy(proxy_mod, access_file)
        try:
            prefix = "/u/arc-test"
            status, _headers, body = request(
                proxy.server_port,
                "/",
                headers={"X-Forwarded-Prefix": prefix},
            )
            expect(status == 401, f"expected login gate, saw {status}")
            expect(f'action="{prefix}/__arclink/login"' in body, body)
            expect(f'name="next" value="{prefix}/"' in body, body)

            form = urlencode({"username": "arc-test", "password": "test-password", "next": f"{prefix}/"})
            status, headers, _body = request(
                proxy.server_port,
                "/__arclink/login",
                method="POST",
                body=form,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-Forwarded-Prefix": prefix,
                },
            )
            expect(status == 303, f"expected login redirect, saw {status} {headers}")
            expect(headers.get("Location") == f"{prefix}/", headers)
            cookie = headers.get("Set-Cookie") or ""
            expect("Path=/u/arc-test" in cookie, cookie)
            expect("Path=/" not in cookie.replace("Path=/u/arc-test", ""), cookie)
            print("PASS test_proxy_login_is_safe_behind_stripped_mount_prefix")
        finally:
            stop_proxy(backend, backend_thread, proxy, proxy_thread)


def test_proxy_mount_rewrites_root_absolute_dashboard_assets() -> None:
    proxy_mod = load_module(PROXY_PY, "arclink_dashboard_auth_proxy_mount_assets_test")
    with tempfile.TemporaryDirectory() as tmp:
        access_file = Path(tmp) / "arclink-web-access.json"
        access_file.write_text(
            json.dumps({"username": "arc-test", "password": "test-password", "session_secret": "session-secret"}),
            encoding="utf-8",
        )

        backend, backend_thread, proxy, proxy_thread = start_proxy(proxy_mod, access_file)
        try:
            prefix = "/u/arc-test"
            cookie = login(proxy.server_port, username="arc-test")
            status, _headers, body = request(
                proxy.server_port,
                "/mounted-spa",
                headers={
                    "Cookie": cookie,
                    "X-Forwarded-Prefix": prefix,
                },
            )
            expect(status == 200, f"expected mounted dashboard HTML, saw {status}")
            expect('href="/u/arc-test/assets/index.css"' in body, body)
            expect('src="/u/arc-test/assets/index.js"' in body, body)
            expect('src="/u/arc-test/assets/logo.png"' in body, body)
            expect('srcset="/u/arc-test/assets/logo.png 1x, /u/arc-test/assets/logo@2x.png 2x"' in body, body)
            expect('href="/u/arc-test/drive"' in body, body)
            expect('action="/u/arc-test/api/mutate"' in body, body)
            expect("data-arclink-mount-prefix" in body and 'var prefix="/u/arc-test";' in body, body)
            expect("window.fetch=function" in body and "XMLHttpRequest.prototype.open" in body, body)
            expect("Element.prototype.setAttribute" in body and "history.pushState=function" in body, body)

            status, _headers, css_body = request(
                proxy.server_port,
                "/assets/index.css",
                headers={
                    "Cookie": cookie,
                    "X-Forwarded-Prefix": prefix,
                },
            )
            expect(status == 200, f"expected mounted dashboard CSS, saw {status}")
            expect('url("/u/arc-test/fonts/font.woff2")' in css_body, css_body)
            expect("url(/u/arc-test/ds-assets/bg.jpg)" in css_body, css_body)

            status, _headers, json_body = request(
                proxy.server_port,
                "/api/dashboard/plugins",
                headers={
                    "Cookie": cookie,
                    "X-Forwarded-Prefix": prefix,
                },
            )
            expect(status == 200, f"expected mounted dashboard plugin JSON, saw {status}")
            expect('"/u/arc-test/dashboard-plugins/code/dist/index.js"' in json_body, json_body)
            expect('"/u/arc-test/dashboard-plugins/code/dist/style.css"' in json_body, json_body)
            expect('"/home/arc-test/not-a-browser-url"' in json_body, json_body)
            print("PASS test_proxy_mount_rewrites_root_absolute_dashboard_assets")
        finally:
            stop_proxy(backend, backend_thread, proxy, proxy_thread)


def test_proxy_hides_arc_managed_lifecycle_controls_and_blocks_mutations() -> None:
    proxy_mod = load_module(PROXY_PY, "arclink_dashboard_auth_proxy_managed_lifecycle_test")
    with tempfile.TemporaryDirectory() as tmp:
        access_file = Path(tmp) / "arclink-web-access.json"
        access_file.write_text(
            json.dumps({"username": "alex", "password": "test-password", "session_secret": "session-secret"}),
            encoding="utf-8",
        )

        previous = os.environ.get("ARCLINK_DASHBOARD_MANAGED_LIFECYCLE_CONTROLS")
        previous_body_cap = os.environ.get("ARCLINK_DASHBOARD_PROXY_MAX_REQUEST_BODY_BYTES")
        os.environ["ARCLINK_DASHBOARD_MANAGED_LIFECYCLE_CONTROLS"] = "1"
        backend, backend_thread, proxy, proxy_thread = start_proxy(proxy_mod, access_file)
        try:
            cookie = login(proxy.server_port)
            status, headers, body = request(proxy.server_port, "/", headers={"Cookie": cookie})
            expect(status == 200, f"expected managed dashboard response, saw {status} {headers}")
            expect("data-arclink-managed-lifecycle-controls" in body, body)
            expect("RESTART GATEWAY" in body and "UPDATE HERMES" in body, body)
            expect("toLowerCase()" in body, body)
            status, headers, body = request(
                proxy.server_port,
                "/",
                headers={"Cookie": cookie, "Accept-Encoding": "gzip, br"},
            )
            expect(status == 200, f"expected managed dashboard response with browser encoding, saw {status} {headers}")
            expect(TestBackend.last_accept_encoding == "identity", str(TestBackend.last_accept_encoding))
            expect("data-arclink-managed-lifecycle-controls" in body, body)

            same_origin = f"http://127.0.0.1:{proxy.server_port}"
            for endpoint in ("/api/gateway/restart", "/api/hermes/update"):
                status, headers, body = request(
                    proxy.server_port,
                    endpoint,
                    method="POST",
                    body="{}",
                    headers={"Cookie": cookie, "Origin": same_origin},
                )
                expect(status == 409, f"expected managed lifecycle block for {endpoint}, saw {status} {headers} {body!r}")
                parsed = json.loads(body)
                expect(parsed.get("arclink_managed") is True, parsed)

            connection = http.client.HTTPConnection("127.0.0.1", proxy.server_port, timeout=5)
            try:
                headers = {
                    "Cookie": cookie,
                    "Origin": same_origin,
                    "Content-Type": "application/json",
                }
                connection.request("POST", "/api/gateway/restart", body=b"{}", headers=headers)
                response = connection.getresponse()
                first_body = response.read().decode("utf-8", "replace")
                expect(response.status == 409, f"expected first keep-alive block, saw {response.status} {first_body!r}")

                connection.request("POST", "/api/hermes/update", body=b"{}", headers=headers)
                response = connection.getresponse()
                second_body = response.read().decode("utf-8", "replace")
                expect(response.status == 409, f"expected second keep-alive block, saw {response.status} {second_body!r}")
                parsed = json.loads(second_body)
                expect(parsed.get("arclink_managed") is True, parsed)
            finally:
                connection.close()

            os.environ["ARCLINK_DASHBOARD_PROXY_MAX_REQUEST_BODY_BYTES"] = "4"
            status, headers, body = request(
                proxy.server_port,
                "/api/gateway/restart",
                method="POST",
                body='{"body":"too-large"}',
                headers={"Cookie": cookie, "Origin": same_origin, "Content-Type": "application/json"},
            )
            expect(status == 413 and "too large" in body.lower(), f"expected capped managed lifecycle body, saw {status} {body!r}")
            print("PASS test_proxy_hides_arc_managed_lifecycle_controls_and_blocks_mutations")
        finally:
            if previous is None:
                os.environ.pop("ARCLINK_DASHBOARD_MANAGED_LIFECYCLE_CONTROLS", None)
            else:
                os.environ["ARCLINK_DASHBOARD_MANAGED_LIFECYCLE_CONTROLS"] = previous
            if previous_body_cap is None:
                os.environ.pop("ARCLINK_DASHBOARD_PROXY_MAX_REQUEST_BODY_BYTES", None)
            else:
                os.environ["ARCLINK_DASHBOARD_PROXY_MAX_REQUEST_BODY_BYTES"] = previous_body_cap
            stop_proxy(backend, backend_thread, proxy, proxy_thread)


def main() -> int:
    test_proxy_allows_hermes_bearer_api_calls_after_session_login()
    test_proxy_bridges_arclink_session_to_backend_hermes_api_token()
    test_proxy_bounds_public_login_body_and_streams_large_backend_responses()
    test_proxy_login_normalizes_email_username_and_copied_password_whitespace()
    test_proxy_scopes_session_cookie_per_dashboard_instance()
    test_proxy_accepts_user_scoped_sso_cookie_across_agent_dashboards()
    test_proxy_rejects_session_and_sso_cookies_after_revocation_epoch()
    test_proxy_injects_crew_switcher_from_access_state()
    test_proxy_rejects_basic_headers_and_injects_dashboard_plugin_deeplink_helper()
    test_proxy_can_run_dashboard_helpers_without_auth()
    test_proxy_rejects_cross_origin_dashboard_mutations()
    test_proxy_login_is_safe_behind_stripped_mount_prefix()
    test_proxy_mount_rewrites_root_absolute_dashboard_assets()
    test_proxy_hides_arc_managed_lifecycle_controls_and_blocks_mutations()
    print("PASS all 14 dashboard-auth-proxy regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
