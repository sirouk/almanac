#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import http.client
import http.server
import json
import secrets
import socketserver
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


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def load_access(path: Path) -> tuple[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return str(data.get("username") or ""), str(data.get("password") or "")


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    access_file: Path
    target: str
    realm: str

    def _authorized(self) -> bool:
        username, password = load_access(self.access_file)
        header = self.headers.get("Authorization") or ""
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        expected = f"Basic {token}"
        return secrets.compare_digest(header, expected)

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
        if not self._authorized():
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
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "authorization"
        }
        headers["Host"] = target.netloc
        connection.request(self.command, path, body=body or None, headers=headers)
        response = connection.getresponse()
        payload = response.read()

        self.send_response(response.status, response.reason)
        for key, value in response.getheaders():
            lowered = key.lower()
            if lowered in HOP_BY_HOP_HEADERS or lowered == "content-length":
                continue
            self.send_header(key, value)
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
    parser.add_argument("--realm", default="Almanac")
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
