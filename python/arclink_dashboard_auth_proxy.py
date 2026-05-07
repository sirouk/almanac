#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import html
import http.client
import http.server
import json
import secrets
import socketserver
import time
from dataclasses import dataclass
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlsplit


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
SESSION_TOKEN_AUDIENCE = "hermes-dashboard"
SESSION_TOKEN_TTL_SECONDS = 12 * 60 * 60
PLUGIN_DEEPLINK_PATHS = {"/drive", "/code", "/terminal"}
LOGIN_PATH = "/__arclink/login"
LOGOUT_PATH = "/__arclink/logout"


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padded = value + ("=" * (-len(value) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _json_b64(data: dict[str, object]) -> str:
    return _b64url(json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _token_secret(access: dict[str, str], realm: str) -> bytes:
    configured = str(access.get("session_secret") or "").strip()
    if configured:
        return configured.encode("utf-8")
    fallback = "\0".join(
        [
            "arclink-dashboard-session-fallback-v1",
            str(realm or ""),
            str(access.get("username") or ""),
            str(access.get("password") or ""),
        ]
    )
    return hashlib.sha256(fallback.encode("utf-8")).digest()


def load_access(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {
        "username": str(data.get("username") or ""),
        "password": str(data.get("password") or ""),
        "session_secret": str(data.get("session_secret") or ""),
    }


def _safe_next(value: str) -> str:
    candidate = str(value or "").strip() or "/"
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        return "/"
    if not candidate.startswith("/"):
        return "/"
    if candidate.startswith(LOGIN_PATH):
        return "/"
    return candidate


@dataclass(frozen=True)
class AuthState:
    ok: bool
    forward_authorization: str | None = None


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    access_file: Path
    target: str
    realm: str
    require_auth: bool = True

    def _make_token(self, username: str) -> str:
        now = int(time.time())
        header = _json_b64({"alg": "HS256", "typ": "JWT"})
        payload = _json_b64(
            {
                "aud": SESSION_TOKEN_AUDIENCE,
                "exp": now + SESSION_TOKEN_TTL_SECONDS,
                "iat": now,
                "nonce": secrets.token_urlsafe(12),
                "sub": username,
            }
        )
        signing_input = f"{header}.{payload}"
        signature = hmac.new(_token_secret(load_access(self.access_file), self.realm), signing_input.encode("ascii"), hashlib.sha256)
        return f"{signing_input}.{_b64url(signature.digest())}"

    def _valid_session_cookie(self, access: dict[str, str]) -> bool:
        header = self.headers.get("Cookie") or ""
        if not header:
            return False
        cookie = SimpleCookie()
        cookie.load(header)
        morsel = cookie.get(SESSION_COOKIE_NAME)
        if morsel is None:
            return False
        token = str(morsel.value or "")
        parts = token.split(".")
        if len(parts) != 3:
            return False
        signing_input = f"{parts[0]}.{parts[1]}"
        expected = hmac.new(_token_secret(access, self.realm), signing_input.encode("ascii"), hashlib.sha256).digest()
        try:
            supplied = _b64url_decode(parts[2])
            payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
        except Exception:
            return False
        if not hmac.compare_digest(supplied, expected):
            return False
        if str(payload.get("aud") or "") != SESSION_TOKEN_AUDIENCE:
            return False
        if str(payload.get("sub") or "") != str(access.get("username") or ""):
            return False
        try:
            return int(payload.get("exp") or 0) > int(time.time())
        except (TypeError, ValueError):
            return False

    def _authorized(self) -> AuthState:
        if not self.require_auth:
            return AuthState(ok=True)
        access = load_access(self.access_file)
        if not access.get("username") or not access.get("password"):
            return AuthState(ok=False)
        if not self._valid_session_cookie(access):
            return AuthState(ok=False)
        header = self.headers.get("Authorization") or ""
        scheme, _, token = header.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            return AuthState(ok=True, forward_authorization=f"Bearer {token.strip()}")
        return AuthState(ok=True)

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

    def _session_cookie_header(self, username: str) -> str:
        value = self._make_token(username)
        return f"{SESSION_COOKIE_NAME}={value}; HttpOnly; Path=/; SameSite=Lax; Secure"

    def _clear_session_cookie_header(self) -> str:
        return f"{SESSION_COOKIE_NAME}=; HttpOnly; Path=/; SameSite=Lax; Secure; Max-Age=0"

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

    def _send_body(
        self,
        status: int,
        body: bytes,
        *,
        content_type: str = "text/plain; charset=utf-8",
        headers: list[tuple[str, str]] | None = None,
    ) -> None:
        self.send_response(status)
        for key, value in headers or []:
            self.send_header(key, value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _login_form(self, *, status: int = 401, error: str = "") -> None:
        next_path = _safe_next(parse_qs(urlsplit(self.path).query).get("next", [self.path])[0])
        if next_path.startswith(LOGIN_PATH):
            next_path = "/"
        error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
        body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(self.realm)} Login</title>
  <style>
    :root {{ color-scheme: dark; --bg:#07090d; --panel:#10151c; --line:#2b3340; --text:#eff3f6; --muted:#98a2ad; --accent:#ff6a2f; }}
    body {{ margin:0; min-height:100vh; display:grid; place-items:center; background:var(--bg); color:var(--text); font:16px system-ui,-apple-system,Segoe UI,sans-serif; }}
    form {{ width:min(420px, calc(100vw - 32px)); border:1px solid var(--line); background:var(--panel); padding:28px; }}
    h1 {{ margin:0 0 8px; font-size:22px; letter-spacing:.08em; text-transform:uppercase; }}
    p {{ margin:0 0 18px; color:var(--muted); line-height:1.45; }}
    label {{ display:block; margin-top:14px; color:var(--muted); font-size:13px; }}
    input {{ box-sizing:border-box; width:100%; margin-top:6px; padding:12px; background:#080b10; color:var(--text); border:1px solid var(--line); border-radius:6px; font:inherit; }}
    button {{ width:100%; margin-top:20px; padding:12px; border:0; border-radius:6px; background:var(--accent); color:#080b10; font-weight:700; cursor:pointer; }}
    .error {{ color:#ffb3a1; }}
  </style>
</head>
<body>
  <form method="post" action="{LOGIN_PATH}">
    <h1>{html.escape(self.realm)}</h1>
    <p>Sign in to open this Hermes dashboard.</p>
    {error_html}
    <input type="hidden" name="next" value="{html.escape(next_path, quote=True)}">
    <label for="username">Username</label>
    <input id="username" name="username" autocomplete="username" required autofocus>
    <label for="password">Password</label>
    <input id="password" name="password" type="password" autocomplete="current-password" required>
    <button type="submit">Sign In</button>
  </form>
</body>
</html>
""".encode("utf-8")
        self._send_body(status, body, content_type="text/html; charset=utf-8")

    def _handle_login_post(self) -> None:
        content_length = int(self.headers.get("Content-Length") or "0")
        raw_body = self.rfile.read(content_length) if content_length else b""
        content_type = (self.headers.get("Content-Type") or "").lower()
        if "application/json" in content_type:
            try:
                parsed = json.loads(raw_body.decode("utf-8"))
            except Exception:
                parsed = {}
            form = {key: [str(value)] for key, value in parsed.items()} if isinstance(parsed, dict) else {}
        else:
            form = parse_qs(raw_body.decode("utf-8", "replace"), keep_blank_values=True)

        username = str(form.get("username", [""])[0] or "")
        password = str(form.get("password", [""])[0] or "")
        next_path = _safe_next(str(form.get("next", ["/"])[0] or "/"))
        access = load_access(self.access_file)
        if not (
            access.get("username")
            and access.get("password")
            and secrets.compare_digest(username, access["username"])
            and secrets.compare_digest(password, access["password"])
        ):
            self._login_form(status=401, error="Invalid dashboard credentials.")
            return

        self.send_response(303)
        self.send_header("Location", next_path)
        self.send_header("Set-Cookie", self._session_cookie_header(username))
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _handle_logout(self) -> None:
        self.send_response(303)
        self.send_header("Location", LOGIN_PATH)
        self.send_header("Set-Cookie", self._clear_session_cookie_header())
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _reject(self) -> None:
        self._login_form(status=401)

    def _proxy(self) -> None:
        path = urlsplit(self.path).path
        if path == LOGIN_PATH:
            if self.command == "POST":
                self._handle_login_post()
                return
            self._login_form(status=200)
            return
        if path == LOGOUT_PATH:
            self._handle_logout()
            return

        auth = self._authorized()
        if not auth.ok:
            self._reject()
            return

        target = urlsplit(self.target)
        connection = http.client.HTTPConnection(target.hostname, target.port, timeout=30)
        proxy_path = self.path
        if target.path and target.path != "/":
            proxy_path = f"{target.path.rstrip('/')}/{self.path.lstrip('/')}"
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
            connection.request(self.command, proxy_path, body=body or None, headers=headers)
            response = connection.getresponse()
            payload = response.read()
            response_headers = response.getheaders()
            reason = response.reason
            status = response.status
        except OSError as exc:
            payload = f"Dashboard backend unavailable: {exc}\n".encode("utf-8", "replace")
            response_headers = [("Content-Type", "text/plain; charset=utf-8")]
            reason = "Bad Gateway"
            status = 502
        finally:
            connection.close()
        if status == 200:
            payload = self._maybe_inject_plugin_deeplink(payload, response_headers)

        self.send_response(status, reason)
        for key, value in response_headers:
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
    parser = argparse.ArgumentParser(description="Signed-session reverse proxy for local-only Hermes dashboards.")
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--access-file", default="")
    parser.add_argument("--realm", default="Hermes")
    parser.add_argument("--no-auth", action="store_true", help="Disable dashboard auth while keeping response helpers.")
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
            "require_auth": not args.no_auth,
        },
    )
    with ThreadingHTTPServer((args.listen_host, args.listen_port), handler) as server:
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
