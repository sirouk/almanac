#!/usr/bin/env python3
from __future__ import annotations

import base64
import http.client
import http.server
import importlib.util
import json
import sys
import tempfile
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROXY_PY = REPO / "python" / "arclink_basic_auth_proxy.py"


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
        if self.path == "/":
            body = b"<html><body>dashboard</body></html>"
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
        self.send_error(404)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def request(port: int, path: str, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], str]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        body = response.read().decode("utf-8", "replace")
        return response.status, dict(response.getheaders()), body
    finally:
        connection.close()


def basic_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def test_proxy_allows_hermes_bearer_api_calls_after_basic_login() -> None:
    proxy_mod = load_module(PROXY_PY, "arclink_basic_auth_proxy_test")
    with tempfile.TemporaryDirectory() as tmp:
        access_file = Path(tmp) / "arclink-web-access.json"
        access_file.write_text(
            json.dumps({"username": "alex", "password": "test-password"}),
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
                "realm": "ArcLink Hermes",
            },
        )
        proxy = proxy_mod.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        proxy_thread.start()

        try:
            status, headers, _body = request(proxy.server_port, "/")
            expect(status == 401, f"expected 401 for unauthenticated request, saw {status} {headers}")
            expect(headers.get("WWW-Authenticate") == 'Basic realm="ArcLink Hermes"', headers)

            status, headers, _body = request(
                proxy.server_port,
                "/",
                headers={"Authorization": basic_header("alex", "test-password")},
            )
            expect(status == 200, f"expected successful dashboard response, saw {status} {headers}")
            cookie = headers.get("Set-Cookie")
            expect(cookie is not None and cookie.startswith(f"{proxy_mod.SESSION_COOKIE_NAME}="), headers)

            status, headers, body = request(
                proxy.server_port,
                "/api/private",
                headers={"Authorization": "Bearer hermes-session-token"},
            )
            expect(status == 401, f"expected proxy challenge without cookie, saw {status} {headers} {body!r}")
            expect(headers.get("WWW-Authenticate") == 'Basic realm="ArcLink Hermes"', headers)

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
            print("PASS test_proxy_allows_hermes_bearer_api_calls_after_basic_login")
        finally:
            proxy.shutdown()
            proxy.server_close()
            proxy_thread.join(timeout=5)
            backend.shutdown()
            backend.server_close()
            backend_thread.join(timeout=5)


def main() -> int:
    test_proxy_allows_hermes_bearer_api_calls_after_basic_login()
    print("PASS all 1 basic-auth-proxy regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
