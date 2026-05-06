#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import http.server
import json
import secrets
import socketserver
from dataclasses import dataclass
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
SESSION_COOKIE_NAME = "arclink_dash_session"
SESSION_COOKIE_PURPOSE = "arclink-basic-auth-proxy-v1"
PLUGIN_DEEPLINK_PATHS = {"/drive", "/code", "/terminal"}


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def load_access(path: Path) -> tuple[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return str(data.get("username") or ""), str(data.get("password") or "")


@dataclass(frozen=True)
class AuthState:
    ok: bool
    set_session_cookie: bool = False
    forward_authorization: str | None = None


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    access_file: Path
    target: str
    realm: str

    def _session_cookie_value(self, username: str, password: str) -> str:
        payload = f"{SESSION_COOKIE_PURPOSE}\0{self.realm}\0{username}\0{password}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _valid_session_cookie(self, username: str, password: str) -> bool:
        header = self.headers.get("Cookie") or ""
        if not header:
            return False
        cookie = SimpleCookie()
        cookie.load(header)
        morsel = cookie.get(SESSION_COOKIE_NAME)
        if morsel is None:
            return False
        expected = self._session_cookie_value(username, password)
        return secrets.compare_digest(morsel.value, expected)

    def _authorized(self) -> AuthState:
        username, password = load_access(self.access_file)
        header = self.headers.get("Authorization") or ""
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        expected = f"Basic {token}"
        if secrets.compare_digest(header, expected):
            return AuthState(ok=True, set_session_cookie=True)
        if self._valid_session_cookie(username, password):
            return AuthState(ok=True, forward_authorization=header or None)
        return AuthState(ok=False)

    def _proxy_cookie_header(self) -> str | None:
        header = self.headers.get("Cookie") or ""
        if not header:
            return None
        cookie = SimpleCookie()
        cookie.load(header)
        if SESSION_COOKIE_NAME in cookie:
            del cookie[SESSION_COOKIE_NAME]
        pairs = [f"{morsel.key}={morsel.value}" for morsel in cookie.values()]
        return "; ".join(pairs) or None

    def _session_cookie_header(self) -> str:
        username, password = load_access(self.access_file)
        value = self._session_cookie_value(username, password)
        return f"{SESSION_COOKIE_NAME}={value}; HttpOnly; Path=/; SameSite=Lax; Secure"

    def _plugin_deeplink_path(self) -> str:
        path = urlsplit(self.path).path.rstrip("/") or "/"
        return path if path in PLUGIN_DEEPLINK_PATHS else ""

    def _maybe_inject_plugin_deeplink(self, payload: bytes, response_headers: list[tuple[str, str]]) -> bytes:
        target_path = self._plugin_deeplink_path()
        if self.command != "GET" or not target_path:
            return payload

        header_map = {key.lower(): value for key, value in response_headers}
        content_type = header_map.get("content-type", "")
        if "text/html" not in content_type.lower() or header_map.get("content-encoding"):
            return payload

        try:
            body = payload.decode("utf-8")
        except UnicodeDecodeError:
            return payload
        if "data-arclink-plugin-deeplink" in body:
            return payload

        target_json = json.dumps(target_path)
        script = (
            '<script data-arclink-plugin-deeplink>(function(){'
            f"var target={target_json},done=false,tries=0;"
            "function run(){"
            "if(done)return;"
            "var link=document.querySelector('a[href$=\"'+target+'\"]');"
            "if(link){done=true;link.click();return;}"
            "if(++tries<120)setTimeout(run,100);"
            "}"
            "if(document.readyState==='loading'){"
            "document.addEventListener('DOMContentLoaded',function(){setTimeout(run,50);});"
            "}else{setTimeout(run,50);}"
            "})();</script>"
        )
        marker = "</body>"
        if marker in body:
            body = body.replace(marker, script + marker, 1)
        else:
            body += script
        return body.encode("utf-8")

    def _reject(self) -> None:
        body = b"Authentication required\n"
        self.send_response(401)
        self.send_header("WWW-Authenticate", f'Basic realm="{self.realm}"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _proxy(self) -> None:
        auth = self._authorized()
        if not auth.ok:
            self._reject()
            return

        target = urlsplit(self.target)
        connection = http.client.HTTPConnection(target.hostname, target.port, timeout=30)
        path = self.path
        if target.path and target.path != "/":
            path = f"{target.path.rstrip('/')}/{self.path.lstrip('/')}"
        body = b""
        content_length = self.headers.get("Content-Length")
        if content_length:
            body = self.rfile.read(int(content_length))
        headers = {}
        for key, value in self.headers.items():
            lowered = key.lower()
            if lowered in HOP_BY_HOP_HEADERS or lowered in {"authorization", "cookie"}:
                continue
            headers[key] = value
        forwarded_cookie = self._proxy_cookie_header()
        if forwarded_cookie:
            headers["Cookie"] = forwarded_cookie
        if auth.forward_authorization:
            headers["Authorization"] = auth.forward_authorization
        headers["Host"] = target.netloc
        try:
            connection.request(self.command, path, body=body or None, headers=headers)
            response = connection.getresponse()
            payload = response.read()
        finally:
            connection.close()
        response_headers = response.getheaders()
        if response.status == 200:
            payload = self._maybe_inject_plugin_deeplink(payload, response_headers)

        self.send_response(response.status, response.reason)
        for key, value in response_headers:
            lowered = key.lower()
            if lowered in HOP_BY_HOP_HEADERS or lowered == "content-length":
                continue
            self.send_header(key, value)
        if auth.set_session_cookie:
            self.send_header("Set-Cookie", self._session_cookie_header())
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def do_DELETE(self) -> None:  # noqa: N802
        self._proxy()

    def do_GET(self) -> None:  # noqa: N802
        self._proxy()

    def do_HEAD(self) -> None:  # noqa: N802
        self._proxy()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._proxy()

    def do_PATCH(self) -> None:  # noqa: N802
        self._proxy()

    def do_POST(self) -> None:  # noqa: N802
        self._proxy()

    def do_PUT(self) -> None:  # noqa: N802
        self._proxy()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tiny authenticated reverse proxy for local-only dashboards.")
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--access-file", required=True)
    parser.add_argument("--realm", default="ArcLink")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    handler = type(
        "ConfiguredProxyHandler",
        (ProxyHandler,),
        {
            "access_file": Path(args.access_file),
            "target": args.target,
            "realm": args.realm,
        },
    )
    with ThreadingHTTPServer((args.listen_host, args.listen_port), handler) as server:
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
