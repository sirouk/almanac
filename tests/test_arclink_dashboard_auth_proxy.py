#!/usr/bin/env python3
from __future__ import annotations

import http.client
import http.server
import importlib.util
import json
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

    def do_GET(self) -> None:  # noqa: N802
        type(self).last_authorization = self.headers.get("Authorization")
        type(self).last_cookie = self.headers.get("Cookie")
        if self.path in {"/", "/drive"}:
            body = b"<html><body>dashboard</body></html>"
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
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        type(self).last_authorization = self.headers.get("Authorization")
        type(self).last_cookie = self.headers.get("Cookie")
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
    expect(cookie.startswith("arclink_dash_session="), headers)
    return cookie


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


def main() -> int:
    test_proxy_allows_hermes_bearer_api_calls_after_session_login()
    test_proxy_login_normalizes_email_username_and_copied_password_whitespace()
    test_proxy_rejects_basic_headers_and_injects_dashboard_plugin_deeplink_helper()
    test_proxy_can_run_dashboard_helpers_without_auth()
    test_proxy_rejects_cross_origin_dashboard_mutations()
    test_proxy_login_is_safe_behind_stripped_mount_prefix()
    test_proxy_mount_rewrites_root_absolute_dashboard_assets()
    print("PASS all 7 dashboard-auth-proxy regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
