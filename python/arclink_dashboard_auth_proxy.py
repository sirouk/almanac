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
import os
import re
import secrets
import socketserver
import threading
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
SESSION_COOKIE_NAME_PREFIX = f"{SESSION_COOKIE_NAME}_"
SESSION_SSO_COOKIE_NAME = "arclink_dash_sso"
SESSION_SSO_COOKIE_NAME_PREFIX = f"{SESSION_SSO_COOKIE_NAME}_"
SESSION_TOKEN_AUDIENCE = "hermes-dashboard"
SESSION_SSO_TOKEN_AUDIENCE = "hermes-dashboard-sso"
SESSION_TOKEN_TTL_SECONDS = 12 * 60 * 60
PLUGIN_DEEPLINK_PATHS = {"/drive", "/code", "/terminal"}
LOGIN_PATH = "/__arclink/login"
LOGOUT_PATH = "/__arclink/logout"
MUTATING_METHODS = {"DELETE", "PATCH", "POST", "PUT"}
MANAGED_LIFECYCLE_ENDPOINTS = {"/api/gateway/restart", "/api/hermes/update"}
TRUE_VALUES = {"1", "true", "yes", "on"}
MOUNTED_HTML_ATTR_RE = re.compile(
    r"(?P<name>\b(?:action|href|poster|src)\s*=\s*)(?P<quote>[\"'])(?P<path>/(?!/)[^\"']*)(?P=quote)",
    re.IGNORECASE,
)
MOUNTED_SRCSET_ATTR_RE = re.compile(r"(?P<name>\bsrcset\s*=\s*)(?P<quote>[\"'])(?P<value>[^\"']*)(?P=quote)", re.IGNORECASE)
MOUNTED_CSS_URL_RE = re.compile(r"url\(\s*(?P<quote>[\"']?)(?P<path>/(?!/)[^)\"']+)(?P=quote)\s*\)", re.IGNORECASE)
MOUNTED_QUOTED_PATH_RE = re.compile(r"(?P<quote>\")(?P<path>/(?!/)[^\"\\]*(?:\\.[^\"\\]*)*)(?P=quote)")
MOUNTED_PUBLIC_PATH_ROOTS = ("/api/", "/assets/", "/dashboard-plugins/", "/ds-assets/", "/fonts/")
BACKEND_SESSION_HEADER_NAME = "X-Hermes-Session-Token"
BACKEND_SESSION_TOKEN_RE = re.compile(r'window\.__HERMES_SESSION_TOKEN__\s*=\s*"(?P<token>[^"]+)"')
DEFAULT_MAX_LOGIN_BODY_BYTES = 64 * 1024
DEFAULT_MAX_REQUEST_BODY_BYTES = 256 * 1024 * 1024
DEFAULT_REWRITE_BUFFER_BYTES = 4 * 1024 * 1024
MAX_REQUEST_BODY_BYTES_CEILING = 2 * 1024 * 1024 * 1024
MAX_REWRITE_BUFFER_BYTES_CEILING = 64 * 1024 * 1024
PROXY_COPY_CHUNK_BYTES = 1024 * 1024


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padded = value + ("=" * (-len(value) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _json_b64(data: dict[str, object]) -> str:
    return _b64url(json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _token_secret(access: dict[str, object], realm: str) -> bytes:
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


def _sso_token_secret(access: dict[str, object]) -> bytes:
    configured = str(access.get("sso_session_secret") or "").strip()
    return configured.encode("utf-8") if configured else b""


def _sso_subject(access: dict[str, object]) -> str:
    return str(access.get("sso_subject") or access.get("username") or "").strip()


def _int_value(value: object) -> int:
    try:
        return int(str(value or "0"))
    except (TypeError, ValueError):
        return 0


def _dashboard_revoked_before(access: dict[str, object], *keys: str) -> int:
    values = [_int_value(access.get("dashboard_auth_revoked_before"))]
    values.extend(_int_value(access.get(key)) for key in keys)
    return max(values)


def _safe_cookie_domain(value: str) -> str:
    candidate = str(value or "").strip().lower().lstrip(".").rstrip(".")
    if not candidate or candidate == "localhost":
        return ""
    if any(ch in candidate for ch in "\r\n;=, \t"):
        return ""
    if not re.fullmatch(r"[a-z0-9.-]+", candidate):
        return ""
    if "." not in candidate:
        return ""
    return candidate


def _safe_dashboard_url(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        return ""
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return ""
    return candidate


def _clean_crew_dashboards(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, object]] = []
    for raw in value[:24]:
        if not isinstance(raw, dict):
            continue
        url = _safe_dashboard_url(str(raw.get("url") or raw.get("hermes_url") or raw.get("dashboard_url") or ""))
        if not url:
            continue
        label = str(raw.get("label") or raw.get("agent_name") or "Hermes Agent").strip()[:120] or "Hermes Agent"
        items.append(
            {
                "deployment_id": str(raw.get("deployment_id") or "").strip()[:120],
                "label": label,
                "title": str(raw.get("title") or raw.get("agent_title") or "").strip()[:160],
                "status": str(raw.get("status") or "").strip()[:80],
                "theme_label": str(raw.get("theme_label") or "").strip()[:120],
                "url": url,
                "current": bool(raw.get("current")),
            }
        )
    return items


def load_access(path: Path) -> dict[str, object]:
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
        "sso_session_secret": str(data.get("sso_session_secret") or ""),
        "sso_subject": str(data.get("sso_subject") or ""),
        "sso_cookie_domain": _safe_cookie_domain(str(data.get("sso_cookie_domain") or "")),
        "deployment_id": str(data.get("deployment_id") or ""),
        "prefix": str(data.get("prefix") or ""),
        "crew_dashboards": _clean_crew_dashboards(data.get("crew_dashboards")),
        "dashboard_auth_revoked_before": _int_value(data.get("dashboard_auth_revoked_before")),
        "dashboard_session_revoked_before": _int_value(data.get("dashboard_session_revoked_before")),
        "dashboard_sso_revoked_before": _int_value(data.get("dashboard_sso_revoked_before")),
    }


def _clean_login_username(value: str) -> str:
    candidate = str(value or "").strip().lower()
    return "".join(ch for ch in candidate if ch.isalnum() or ch in "@._-").strip(".-_")


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


def _safe_mount_prefix(value: str) -> str:
    candidate = str(value or "").split(",", 1)[0].strip()
    if not candidate:
        return ""
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        return ""
    path = parsed.path.strip()
    if not path or path == "/":
        return ""
    if not path.startswith("/"):
        path = f"/{path}"
    return path.rstrip("/")


def _join_mount_path(prefix: str, path: str) -> str:
    clean_prefix = _safe_mount_prefix(prefix)
    clean_path = str(path or "").strip() or "/"
    parsed = urlsplit(clean_path)
    if parsed.scheme or parsed.netloc:
        clean_path = "/"
    elif not clean_path.startswith("/"):
        clean_path = "/"
    if not clean_prefix:
        return clean_path
    if clean_path == clean_prefix or clean_path.startswith(f"{clean_prefix}/"):
        return clean_path
    if clean_path == "/":
        return f"{clean_prefix}/"
    return f"{clean_prefix}{clean_path}"


def _mount_browser_path(prefix: str, path: str) -> str:
    clean_prefix = _safe_mount_prefix(prefix)
    candidate = str(path or "")
    if not clean_prefix or not candidate.startswith("/") or candidate.startswith("//"):
        return candidate
    if candidate == clean_prefix or candidate.startswith(f"{clean_prefix}/"):
        return candidate
    return f"{clean_prefix}{candidate}"


def _is_mounted_public_path(path: str) -> bool:
    candidate = str(path or "")
    return any(candidate.startswith(root) for root in MOUNTED_PUBLIC_PATH_ROOTS) or candidate in {
        "/api",
        "/assets",
        "/dashboard-plugins",
        "/ds-assets",
        "/fonts",
    }


def _mount_srcset(prefix: str, value: str) -> str:
    parts = []
    for raw_part in str(value or "").split(","):
        leading = raw_part[: len(raw_part) - len(raw_part.lstrip())]
        trailing = raw_part[len(raw_part.rstrip()) :]
        inner = raw_part.strip()
        if not inner:
            parts.append(raw_part)
            continue
        url, sep, descriptor = inner.partition(" ")
        mounted = _mount_browser_path(prefix, url)
        parts.append(f"{leading}{mounted}{sep}{descriptor}{trailing}")
    return ",".join(parts)


def _mount_runtime_script(prefix: str) -> str:
    prefix_json = json.dumps(_safe_mount_prefix(prefix))
    return (
        '<script data-arclink-mount-prefix>(function(){'
        f"var prefix={prefix_json};"
        "if(!prefix||window.__arclinkMountPrefixInstalled)return;"
        "window.__arclinkMountPrefixInstalled=true;"
        "function mountPath(value){"
        "if(typeof value!=='string'||value.charAt(0)!=='/'||value.indexOf('//')===0)return value;"
        "if(value===prefix||value.indexOf(prefix+'/')===0)return value;"
        "return prefix+value;"
        "}"
        "function mountURL(value){"
        "if(typeof value==='string')return mountPath(value);"
        "try{var url=value instanceof URL?value:new URL(String(value),window.location.href);"
        "if(url.origin===window.location.origin){"
        "var mounted=mountPath(url.pathname+url.search+url.hash);"
        "if(mounted!==url.pathname+url.search+url.hash)return mounted;"
        "}}catch(e){}"
        "return value;"
        "}"
        "var originalFetch=window.fetch;"
        "if(originalFetch){window.fetch=function(input,init){"
        "if(typeof input==='string'||input instanceof URL)return originalFetch.call(this,mountURL(input),init);"
        "try{if(input&&input.url){var mounted=mountURL(input.url);"
        "if(mounted!==input.url)return originalFetch.call(this,new Request(mounted,input),init);}}catch(e){}"
        "return originalFetch.call(this,input,init);};}"
        "if(window.XMLHttpRequest&&XMLHttpRequest.prototype.open){"
        "var originalOpen=XMLHttpRequest.prototype.open;"
        "XMLHttpRequest.prototype.open=function(method,url){"
        "arguments[1]=mountURL(url);return originalOpen.apply(this,arguments);};}"
        "function patchAttr(proto,name){try{var desc=Object.getOwnPropertyDescriptor(proto,name);"
        "if(desc&&desc.set){Object.defineProperty(proto,name,{get:desc.get,set:function(value){return desc.set.call(this,mountURL(value));}});}}catch(e){}}"
        "if(window.HTMLAnchorElement)patchAttr(HTMLAnchorElement.prototype,'href');"
        "if(window.HTMLFormElement)patchAttr(HTMLFormElement.prototype,'action');"
        "if(window.HTMLImageElement)patchAttr(HTMLImageElement.prototype,'src');"
        "if(window.HTMLLinkElement)patchAttr(HTMLLinkElement.prototype,'href');"
        "if(window.HTMLScriptElement)patchAttr(HTMLScriptElement.prototype,'src');"
        "if(window.HTMLSourceElement)patchAttr(HTMLSourceElement.prototype,'src');"
        "var originalSetAttribute=Element.prototype.setAttribute;"
        "Element.prototype.setAttribute=function(name,value){"
        "var key=String(name||'').toLowerCase();"
        "if(key==='href'||key==='src'||key==='action'||key==='poster')value=mountURL(value);"
        "else if(key==='srcset'&&typeof value==='string')value=value.split(',').map(function(part){"
        "var trimmed=part.trim();if(!trimmed)return part;"
        "var pieces=trimmed.split(/\\s+/);pieces[0]=mountPath(pieces[0]);"
        "return part.match(/^\\s*/)[0]+pieces.join(' ')+part.match(/\\s*$/)[0];}).join(',');"
        "return originalSetAttribute.call(this,name,value);};"
        "if(window.history&&history.pushState){var originalPushState=history.pushState;"
        "history.pushState=function(state,title,url){if(arguments.length>2&&url!=null)arguments[2]=mountURL(url);"
        "return originalPushState.apply(this,arguments);};}"
        "if(window.history&&history.replaceState){var originalReplaceState=history.replaceState;"
        "history.replaceState=function(state,title,url){if(arguments.length>2&&url!=null)arguments[2]=mountURL(url);"
        "return originalReplaceState.apply(this,arguments);};}"
        "if(window.EventSource){var OriginalEventSource=window.EventSource;"
        "window.EventSource=function(url,config){return new OriginalEventSource(mountURL(url),config);};"
        "window.EventSource.prototype=OriginalEventSource.prototype;}"
        "if(window.WebSocket){var OriginalWebSocket=window.WebSocket;"
        "window.WebSocket=function(url,protocols){return new OriginalWebSocket(mountURL(url),protocols);};"
        "window.WebSocket.prototype=OriginalWebSocket.prototype;}"
        "})();</script>"
    )


def _env_bool(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in TRUE_VALUES


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = str(os.environ.get(name) or "").strip()
    try:
        value = int(raw) if raw else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _managed_lifecycle_controls_enabled() -> bool:
    return _env_bool("ARCLINK_DASHBOARD_MANAGED_LIFECYCLE_CONTROLS")


def _managed_lifecycle_controls_script() -> str:
    labels_json = json.dumps(["restart gateway", "update hermes"])
    reason_json = json.dumps("ArcLink manages this deployment from the Sovereign Control Node.")
    return (
        '<script data-arclink-managed-lifecycle-controls>(function(){'
        f"var labels={labels_json};"
        f"var reason={reason_json};"
        "function clean(value){return String(value||'').replace(/\\s+/g,' ').trim().toLowerCase();}"
        "function isManagedControl(node){"
        "var text=clean(node&&node.textContent);"
        "return labels.indexOf(text)!==-1;"
        "}"
        "function hideManagedControl(node){"
        "if(!node||node.dataset&&node.dataset.arclinkManagedLifecycleHidden)return;"
        "if(node.dataset)node.dataset.arclinkManagedLifecycleHidden='1';"
        "try{node.disabled=true;}catch(e){}"
        "try{node.setAttribute('aria-disabled','true');node.setAttribute('aria-hidden','true');node.setAttribute('title',reason);}catch(e){}"
        "try{node.style.display='none';}catch(e){}"
        "}"
        "function patch(){"
        "document.querySelectorAll('button,[role=\"button\"]').forEach(function(node){"
        "if(isManagedControl(node))hideManagedControl(node);"
        "});"
        "}"
        "if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',patch);else patch();"
        "try{new MutationObserver(patch).observe(document.documentElement,{childList:true,subtree:true,characterData:true});}catch(e){}"
        "})();</script>"
    )


def _crew_switcher_config(access: dict[str, object]) -> dict[str, object] | None:
    raw_items = access.get("crew_dashboards")
    if not isinstance(raw_items, list):
        return None
    items = [dict(item) for item in raw_items if isinstance(item, dict) and item.get("url")]
    if len(items) < 2:
        return None
    current = next((item for item in items if item.get("current")), items[0])
    theme_label = str(current.get("theme_label") or "").strip()
    return {
        "items": [
            {
                "label": str(item.get("label") or "Hermes Agent"),
                "title": str(item.get("title") or ""),
                "status": str(item.get("status") or ""),
                "url": str(item.get("url") or ""),
                "current": bool(item.get("current")),
            }
            for item in items
        ],
        "label": str(current.get("label") or "Hermes Agent"),
        "themeLabel": theme_label,
    }


def _crew_switcher_script(access: dict[str, object]) -> str:
    config = _crew_switcher_config(access)
    if not config:
        return ""
    config_json = (
        json.dumps(config, separators=(",", ":"), sort_keys=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return (
        '<script data-arclink-crew-switcher>(function(){'
        f"var config={config_json};"
        "function text(value){return String(value||'').replace(/\\s+/g,' ').trim();}"
        "function install(){"
        "if(document.querySelector('[data-arclink-crew-switcher-root]'))return;"
        "var items=Array.isArray(config.items)?config.items:[];"
        "if(items.length<2)return;"
        "var style=document.createElement('style');style.setAttribute('data-arclink-crew-switcher-style','');"
        "style.textContent='[data-arclink-crew-switcher-root]{position:fixed;top:12px;right:16px;z-index:2147483000;font:13px system-ui,-apple-system,Segoe UI,sans-serif;color:#f7f4ef}[data-arclink-crew-switcher-root] button{max-width:min(360px,calc(100vw - 32px));height:34px;border:1px solid rgba(255,255,255,.16);border-radius:7px;background:rgba(10,13,18,.9);color:#f7f4ef;padding:0 12px;display:flex;align-items:center;gap:8px;box-shadow:0 10px 28px rgba(0,0,0,.24);cursor:pointer}[data-arclink-crew-switcher-root] button:after{content:\"v\";font-size:10px;opacity:.72}[data-arclink-crew-switcher-menu]{position:absolute;right:0;top:40px;min-width:260px;max-width:min(380px,calc(100vw - 24px));border:1px solid rgba(255,255,255,.14);border-radius:8px;background:#0b0f14;box-shadow:0 18px 44px rgba(0,0,0,.42);padding:6px;display:none}[data-arclink-crew-switcher-root][data-open=\"true\"] [data-arclink-crew-switcher-menu]{display:block}[data-arclink-crew-switcher-menu] a{display:block;border-radius:6px;padding:10px 11px;color:#f7f4ef;text-decoration:none;line-height:1.25}[data-arclink-crew-switcher-menu] a:hover{background:rgba(251,80,5,.14)}[data-arclink-crew-switcher-menu] a[aria-current=\"page\"]{border:1px solid rgba(251,80,5,.5);background:rgba(251,80,5,.1)}[data-arclink-crew-switcher-menu] span{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}[data-arclink-crew-switcher-menu] small{display:block;margin-top:3px;color:rgba(247,244,239,.62);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}@media(max-width:700px){[data-arclink-crew-switcher-root]{top:8px;right:8px}[data-arclink-crew-switcher-root] button{height:32px;max-width:calc(100vw - 16px)}}';"
        "document.head.appendChild(style);"
        "var root=document.createElement('div');root.setAttribute('data-arclink-crew-switcher-root','');"
        "var button=document.createElement('button');button.type='button';button.setAttribute('aria-haspopup','menu');button.setAttribute('aria-expanded','false');"
        "button.title='Switch Hermes Agent Dashboard';"
        "button.textContent=text(config.label)+(text(config.themeLabel)?' / '+text(config.themeLabel):'');"
        "var menu=document.createElement('div');menu.setAttribute('data-arclink-crew-switcher-menu','');menu.setAttribute('role','menu');"
        "items.forEach(function(item){var link=document.createElement('a');link.href=String(item.url||'#');link.setAttribute('role','menuitem');"
        "if(item.current)link.setAttribute('aria-current','page');"
        "var label=document.createElement('span');label.textContent=text(item.label)||'Hermes Agent';"
        "var meta=document.createElement('small');var bits=[];if(text(item.title))bits.push(text(item.title));if(text(item.status))bits.push(text(item.status));meta.textContent=bits.join(' / ');"
        "link.appendChild(label);if(meta.textContent)link.appendChild(meta);menu.appendChild(link);});"
        "button.addEventListener('click',function(event){event.stopPropagation();var open=root.getAttribute('data-open')==='true';root.setAttribute('data-open',open?'false':'true');button.setAttribute('aria-expanded',open?'false':'true');});"
        "document.addEventListener('click',function(){root.setAttribute('data-open','false');button.setAttribute('aria-expanded','false');});"
        "root.appendChild(button);root.appendChild(menu);document.body.appendChild(root);"
        "}"
        "if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install);else install();"
        "})();</script>"
    )


def _is_login_path(value: str) -> bool:
    path = urlsplit(str(value or "")).path.rstrip("/") or "/"
    return path == LOGIN_PATH or path.endswith(LOGIN_PATH)


def _normalize_host(value: str) -> str:
    return str(value or "").strip().lower().rstrip(".")


def _origin_matches_host(value: str, host: str) -> bool:
    origin = str(value or "").strip()
    expected = _normalize_host(host)
    if not origin or not expected:
        return False
    parsed = urlsplit(origin)
    supplied = _normalize_host(parsed.netloc)
    return bool(supplied and hmac.compare_digest(supplied, expected))


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
    backend_session_token: str = ""
    backend_session_token_target: str = ""
    backend_session_token_lock = threading.Lock()

    def _session_cookie_name(self, access: dict[str, object]) -> str:
        scope = "\0".join(
            [
                "arclink-dashboard-cookie-v1",
                str(self.realm or ""),
                str(self.target or ""),
                str(access.get("deployment_id") or ""),
                str(access.get("prefix") or ""),
                str(access.get("session_secret") or ""),
                str(access.get("username") or ""),
            ]
        )
        digest = hashlib.sha256(scope.encode("utf-8")).hexdigest()[:16]
        return f"{SESSION_COOKIE_NAME_PREFIX}{digest}"

    def _sso_cookie_name(self, access: dict[str, object]) -> str:
        scope = "\0".join(
            [
                "arclink-dashboard-sso-cookie-v1",
                _sso_subject(access),
                str(access.get("sso_session_secret") or ""),
            ]
        )
        digest = hashlib.sha256(scope.encode("utf-8")).hexdigest()[:16]
        return f"{SESSION_SSO_COOKIE_NAME_PREFIX}{digest}"

    def _make_signed_token(self, *, secret: bytes, subject: str, audience: str, scope: str = "") -> str:
        now = int(time.time())
        header = _json_b64({"alg": "HS256", "typ": "JWT"})
        claims: dict[str, object] = {
            "aud": audience,
            "exp": now + SESSION_TOKEN_TTL_SECONDS,
            "iat": now,
            "nonce": secrets.token_urlsafe(12),
            "sub": subject,
        }
        if scope:
            claims["scope"] = scope
        payload = _json_b64(claims)
        signing_input = f"{header}.{payload}"
        signature = hmac.new(secret, signing_input.encode("ascii"), hashlib.sha256)
        return f"{signing_input}.{_b64url(signature.digest())}"

    def _make_token(self, access: dict[str, object], username: str) -> str:
        return self._make_signed_token(
            secret=_token_secret(access, self.realm),
            subject=username,
            audience=SESSION_TOKEN_AUDIENCE,
        )

    def _make_sso_token(self, access: dict[str, object]) -> str:
        secret = _sso_token_secret(access)
        subject = _sso_subject(access)
        if not secret or not subject:
            return ""
        return self._make_signed_token(
            secret=secret,
            subject=subject,
            audience=SESSION_SSO_TOKEN_AUDIENCE,
            scope="captain-dashboard-sso",
        )

    def _valid_token(
        self,
        token: str,
        *,
        secret: bytes,
        audience: str,
        subject: str,
        scope: str = "",
        revoked_before: int = 0,
    ) -> bool:
        token = str(token or "")
        parts = token.split(".")
        if len(parts) != 3:
            return False
        signing_input = f"{parts[0]}.{parts[1]}"
        expected = hmac.new(secret, signing_input.encode("ascii"), hashlib.sha256).digest()
        try:
            supplied = _b64url_decode(parts[2])
            payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
        except Exception:
            return False
        if not hmac.compare_digest(supplied, expected):
            return False
        if str(payload.get("aud") or "") != audience:
            return False
        if str(payload.get("sub") or "") != subject:
            return False
        if scope and str(payload.get("scope") or "") != scope:
            return False
        try:
            issued_at = int(payload.get("iat") or 0)
            if revoked_before and issued_at <= revoked_before:
                return False
            return int(payload.get("exp") or 0) > int(time.time())
        except (TypeError, ValueError):
            return False

    def _valid_session_cookie(self, access: dict[str, object]) -> bool:
        header = self.headers.get("Cookie") or ""
        if not header:
            return False
        cookie = SimpleCookie()
        cookie.load(header)
        morsel = cookie.get(self._session_cookie_name(access))
        if morsel is None:
            return False
        return self._valid_token(
            str(morsel.value or ""),
            secret=_token_secret(access, self.realm),
            audience=SESSION_TOKEN_AUDIENCE,
            subject=str(access.get("username") or ""),
            revoked_before=_dashboard_revoked_before(access, "dashboard_session_revoked_before"),
        )

    def _valid_sso_cookie(self, access: dict[str, object]) -> bool:
        secret = _sso_token_secret(access)
        subject = _sso_subject(access)
        if not secret or not subject:
            return False
        header = self.headers.get("Cookie") or ""
        if not header:
            return False
        cookie = SimpleCookie()
        cookie.load(header)
        morsel = cookie.get(self._sso_cookie_name(access))
        if morsel is None:
            return False
        return self._valid_token(
            str(morsel.value or ""),
            secret=secret,
            audience=SESSION_SSO_TOKEN_AUDIENCE,
            subject=subject,
            scope="captain-dashboard-sso",
            revoked_before=_dashboard_revoked_before(access, "dashboard_sso_revoked_before"),
        )

    def _authorized(self) -> AuthState:
        if not self.require_auth:
            return AuthState(ok=True)
        access = load_access(self.access_file)
        if not access.get("username") or not access.get("password"):
            return AuthState(ok=False)
        if not self._valid_session_cookie(access) and not self._valid_sso_cookie(access):
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
        for name in list(cookie):
            if (
                name == SESSION_COOKIE_NAME
                or name.startswith(SESSION_COOKIE_NAME_PREFIX)
                or name == SESSION_SSO_COOKIE_NAME
                or name.startswith(SESSION_SSO_COOKIE_NAME_PREFIX)
            ):
                del cookie[name]
        pairs = [f"{morsel.key}={morsel.value}" for morsel in cookie.values()]
        return "; ".join(pairs) or None

    def _session_cookie_header(self, access: dict[str, object], username: str) -> str:
        value = self._make_token(access, username)
        return f"{self._session_cookie_name(access)}={value}; HttpOnly; Path={self._cookie_path()}; SameSite=Lax; Secure"

    def _sso_cookie_header(self, access: dict[str, object]) -> str:
        value = self._make_sso_token(access)
        if not value:
            return ""
        domain = str(access.get("sso_cookie_domain") or "")
        domain_part = f"; Domain={domain}" if domain else ""
        return f"{self._sso_cookie_name(access)}={value}; HttpOnly; Path=/; SameSite=Lax; Secure{domain_part}"

    def _clear_cookie_header(self, name: str, *, path: str = "", domain: str = "") -> str:
        clean_path = path or self._cookie_path()
        domain_part = f"; Domain={domain}" if domain else ""
        return f"{name}=; HttpOnly; Path={clean_path}; SameSite=Lax; Secure{domain_part}; Max-Age=0"

    def _clear_session_cookie_headers(self, access: dict[str, object] | None = None) -> list[str]:
        names = [SESSION_COOKIE_NAME]
        if access is not None:
            scoped = self._session_cookie_name(access)
            if scoped not in names:
                names.append(scoped)
        headers = [self._clear_cookie_header(name) for name in names]
        sso_names = [SESSION_SSO_COOKIE_NAME]
        if access is not None and _sso_token_secret(access):
            scoped_sso = self._sso_cookie_name(access)
            if scoped_sso not in sso_names:
                sso_names.append(scoped_sso)
        domain = str((access or {}).get("sso_cookie_domain") or "") if access is not None else ""
        for name in sso_names:
            headers.append(self._clear_cookie_header(name, path="/"))
            if domain:
                headers.append(self._clear_cookie_header(name, path="/", domain=domain))
        return headers

    def _mount_prefix(self) -> str:
        return _safe_mount_prefix(
            self.headers.get("X-Forwarded-Prefix")
            or self.headers.get("X-Forwarded-Prefixes")
            or ""
        )

    def _cookie_path(self) -> str:
        return self._mount_prefix() or "/"

    def _public_path(self, path: str) -> str:
        return _join_mount_path(self._mount_prefix(), path)

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

    def _maybe_inject_managed_lifecycle_controls(self, payload: bytes, response_headers: list[tuple[str, str]]) -> bytes:
        if self.command != "GET" or not _managed_lifecycle_controls_enabled():
            return payload

        header_map = {key.lower(): value for key, value in response_headers}
        content_type = header_map.get("content-type", "")
        if "text/html" not in content_type.lower() or header_map.get("content-encoding"):
            return payload

        try:
            body = payload.decode("utf-8")
        except UnicodeDecodeError:
            return payload
        if "data-arclink-managed-lifecycle-controls" in body:
            return payload

        script = _managed_lifecycle_controls_script()
        marker = "</body>"
        if marker in body:
            body = body.replace(marker, script + marker, 1)
        else:
            body += script
        return body.encode("utf-8")

    def _maybe_inject_crew_switcher(self, payload: bytes, response_headers: list[tuple[str, str]]) -> bytes:
        if self.command != "GET":
            return payload

        header_map = {key.lower(): value for key, value in response_headers}
        content_type = header_map.get("content-type", "")
        if "text/html" not in content_type.lower() or header_map.get("content-encoding"):
            return payload

        try:
            body = payload.decode("utf-8")
        except UnicodeDecodeError:
            return payload
        if "data-arclink-crew-switcher" in body:
            return payload

        script = _crew_switcher_script(load_access(self.access_file))
        if not script:
            return payload
        marker = "</body>"
        if marker in body:
            body = body.replace(marker, script + marker, 1)
        else:
            body += script
        return body.encode("utf-8")

    def _rewrite_mounted_html_paths(self, payload: bytes, response_headers: list[tuple[str, str]]) -> bytes:
        mount_prefix = self._mount_prefix()
        if self.command != "GET" or not mount_prefix:
            return payload

        header_map = {key.lower(): value for key, value in response_headers}
        content_type = header_map.get("content-type", "")
        if "text/html" not in content_type.lower() or header_map.get("content-encoding"):
            return payload

        try:
            body = payload.decode("utf-8")
        except UnicodeDecodeError:
            return payload

        def replace_attr(match: re.Match[str]) -> str:
            path = match.group("path")
            return f"{match.group('name')}{match.group('quote')}{_mount_browser_path(mount_prefix, path)}{match.group('quote')}"

        def replace_srcset(match: re.Match[str]) -> str:
            value = match.group("value")
            return f"{match.group('name')}{match.group('quote')}{_mount_srcset(mount_prefix, value)}{match.group('quote')}"

        body = MOUNTED_HTML_ATTR_RE.sub(replace_attr, body)
        body = MOUNTED_SRCSET_ATTR_RE.sub(replace_srcset, body)
        if "data-arclink-mount-prefix" not in body:
            script = _mount_runtime_script(mount_prefix)
            marker = "</head>"
            if marker in body:
                body = body.replace(marker, script + marker, 1)
            else:
                body = script + body
        return body.encode("utf-8")

    def _rewrite_mounted_css_paths(self, payload: bytes, response_headers: list[tuple[str, str]]) -> bytes:
        mount_prefix = self._mount_prefix()
        if self.command != "GET" or not mount_prefix:
            return payload

        header_map = {key.lower(): value for key, value in response_headers}
        content_type = header_map.get("content-type", "")
        if "text/css" not in content_type.lower() or header_map.get("content-encoding"):
            return payload

        try:
            body = payload.decode("utf-8")
        except UnicodeDecodeError:
            return payload

        def replace_url(match: re.Match[str]) -> str:
            path = match.group("path")
            if not _is_mounted_public_path(path):
                return match.group(0)
            quote = match.group("quote")
            return f"url({quote}{_mount_browser_path(mount_prefix, path)}{quote})"

        return MOUNTED_CSS_URL_RE.sub(replace_url, body).encode("utf-8")

    def _rewrite_mounted_json_paths(self, payload: bytes, response_headers: list[tuple[str, str]]) -> bytes:
        mount_prefix = self._mount_prefix()
        if self.command != "GET" or not mount_prefix:
            return payload

        header_map = {key.lower(): value for key, value in response_headers}
        content_type = header_map.get("content-type", "")
        if "application/json" not in content_type.lower() or header_map.get("content-encoding"):
            return payload

        try:
            body = payload.decode("utf-8")
        except UnicodeDecodeError:
            return payload

        def replace_path(match: re.Match[str]) -> str:
            path = match.group("path")
            if not _is_mounted_public_path(path):
                return match.group(0)
            return f'{match.group("quote")}{_mount_browser_path(mount_prefix, path)}{match.group("quote")}'

        return MOUNTED_QUOTED_PATH_RE.sub(replace_path, body).encode("utf-8")

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

    def _max_login_body_bytes(self) -> int:
        return _env_int(
            "ARCLINK_DASHBOARD_PROXY_MAX_LOGIN_BODY_BYTES",
            DEFAULT_MAX_LOGIN_BODY_BYTES,
            minimum=1,
            maximum=1024 * 1024,
        )

    def _max_request_body_bytes(self) -> int:
        return _env_int(
            "ARCLINK_DASHBOARD_PROXY_MAX_REQUEST_BODY_BYTES",
            DEFAULT_MAX_REQUEST_BODY_BYTES,
            minimum=1,
            maximum=MAX_REQUEST_BODY_BYTES_CEILING,
        )

    def _rewrite_buffer_bytes(self) -> int:
        return _env_int(
            "ARCLINK_DASHBOARD_PROXY_REWRITE_BUFFER_BYTES",
            DEFAULT_REWRITE_BUFFER_BYTES,
            minimum=1024,
            maximum=MAX_REWRITE_BUFFER_BYTES_CEILING,
        )

    def _read_limited_body(self, *, limit: int) -> bytes | None:
        try:
            content_length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            content_length = 0
        if content_length < 0:
            content_length = 0
        if content_length > limit:
            self.close_connection = True
            self._send_body(413, b"Dashboard request body is too large.\n")
            return None
        return self.rfile.read(content_length) if content_length else b""

    def _login_form(self, *, status: int = 401, error: str = "", next_path: str = "") -> None:
        raw_next = next_path or parse_qs(urlsplit(self.path).query).get("next", [self.path])[0]
        next_path = _safe_next(raw_next)
        if _is_login_path(next_path):
            next_path = "/"
        public_next = self._public_path(next_path)
        login_action = self._public_path(LOGIN_PATH)
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
  <form method="post" action="{html.escape(login_action, quote=True)}">
    <h1>{html.escape(self.realm)}</h1>
    <p>Sign in to open this Hermes Dashboard.</p>
    {error_html}
    <input type="hidden" name="next" value="{html.escape(public_next, quote=True)}">
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
        raw_body = self._read_limited_body(limit=self._max_login_body_bytes())
        if raw_body is None:
            return
        content_type = (self.headers.get("Content-Type") or "").lower()
        if "application/json" in content_type:
            try:
                parsed = json.loads(raw_body.decode("utf-8"))
            except Exception:
                parsed = {}
            form = {key: [str(value)] for key, value in parsed.items()} if isinstance(parsed, dict) else {}
        else:
            form = parse_qs(raw_body.decode("utf-8", "replace"), keep_blank_values=True)

        username = _clean_login_username(str(form.get("username", [""])[0] or ""))
        password = str(form.get("password", [""])[0] or "").strip()
        next_path = _safe_next(str(form.get("next", ["/"])[0] or "/"))
        if _is_login_path(next_path):
            next_path = self._public_path("/")
        access = load_access(self.access_file)
        access_username = _clean_login_username(access.get("username") or "")
        if not (
            access_username
            and access.get("password")
            and secrets.compare_digest(username, access_username)
            and secrets.compare_digest(password, access["password"])
        ):
            self._login_form(status=401, error="Invalid dashboard credentials.", next_path=next_path)
            return

        self.send_response(303)
        self.send_header("Location", next_path)
        for cookie_header in self._clear_session_cookie_headers(access):
            self.send_header("Set-Cookie", cookie_header)
        sso_cookie = self._sso_cookie_header(access)
        if sso_cookie:
            self.send_header("Set-Cookie", sso_cookie)
        self.send_header("Set-Cookie", self._session_cookie_header(access, access_username))
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _handle_logout(self) -> None:
        access = load_access(self.access_file)
        self.send_response(303)
        self.send_header("Location", self._public_path(LOGIN_PATH))
        for cookie_header in self._clear_session_cookie_headers(access):
            self.send_header("Set-Cookie", cookie_header)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _reject(self) -> None:
        self._login_form(status=401)

    def _csrf_origin_ok(self) -> bool:
        if self.command.upper() not in MUTATING_METHODS or not self.require_auth:
            return True
        host = self.headers.get("Host") or ""
        origin = self.headers.get("Origin") or ""
        if origin:
            return _origin_matches_host(origin, host)
        referer = self.headers.get("Referer") or ""
        if referer:
            return _origin_matches_host(referer, host)
        return False

    def _backend_session_token(self, *, force_refresh: bool = False) -> str:
        """Read Hermes' loopback-only dashboard token from the local backend.

        ArcLink's proxy is the public auth boundary. The Hermes Dashboard behind
        it still protects /api/* with an ephemeral in-process session token so
        first-party plugin fetches need that header. The proxy learns the token
        from the backend's own index HTML and forwards it only after the ArcLink
        signed-session gate has accepted the browser request.
        """
        cls = type(self)
        target_url = str(self.target or "")
        with cls.backend_session_token_lock:
            if (
                not force_refresh
                and cls.backend_session_token
                and cls.backend_session_token_target == target_url
            ):
                return cls.backend_session_token

            target = urlsplit(self.target)
            if not target.hostname or not target.port:
                return ""
            connection = http.client.HTTPConnection(target.hostname, target.port, timeout=5)
            request_path = (target.path.rstrip("/") or "") + "/"
            try:
                connection.request(
                    "GET",
                    request_path,
                    headers={
                        "Accept-Encoding": "identity",
                        "Host": target.netloc,
                    },
                )
                response = connection.getresponse()
                payload = response.read(self._rewrite_buffer_bytes() + 1)
                if len(payload) > self._rewrite_buffer_bytes():
                    return ""
            except OSError:
                return ""
            finally:
                connection.close()

            match = BACKEND_SESSION_TOKEN_RE.search(payload.decode("utf-8", "replace"))
            token = str(match.group("token") if match else "").strip()
            cls.backend_session_token = token
            cls.backend_session_token_target = target_url if token else ""
            return token

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
        if not self._csrf_origin_ok():
            self._send_body(403, b"Cross-origin dashboard mutation rejected.\n")
            return
        if (
            self.command.upper() == "POST"
            and _managed_lifecycle_controls_enabled()
            and path.rstrip("/") in MANAGED_LIFECYCLE_ENDPOINTS
        ):
            if self._read_limited_body(limit=self._max_request_body_bytes()) is None:
                return
            payload = {
                "ok": False,
                "arclink_managed": True,
                "detail": "ArcLink manages Hermes gateway and runtime lifecycle through the Sovereign Control Node.",
            }
            self._send_body(
                409,
                json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"),
                content_type="application/json; charset=utf-8",
            )
            return

        target = urlsplit(self.target)
        proxy_path = self.path
        if target.path and target.path != "/":
            proxy_path = f"{target.path.rstrip('/')}/{self.path.lstrip('/')}"
        headers = {}
        for key, value in self.headers.items():
            lowered = key.lower()
            if lowered in HOP_BY_HOP_HEADERS or lowered in {"authorization", "cookie", BACKEND_SESSION_HEADER_NAME.lower()}:
                continue
            headers[key] = value
        # We rewrite/inject small HTML/CSS/JSON payloads below. Ask the local
        # dashboard for identity encoding so browser-requested gzip/br does not
        # hide those payloads from the proxy.
        headers["Accept-Encoding"] = "identity"
        forwarded_cookie = self._proxy_cookie_header()
        if forwarded_cookie:
            headers["Cookie"] = forwarded_cookie
        if auth.forward_authorization:
            headers["Authorization"] = auth.forward_authorization
        backend_token = self._backend_session_token()
        if backend_token:
            headers[BACKEND_SESSION_HEADER_NAME] = backend_token
        headers["Host"] = target.netloc

        body = self._read_limited_body(limit=self._max_request_body_bytes())
        if body is None:
            return

        def request_backend(request_headers: dict[str, str]) -> tuple[http.client.HTTPConnection, http.client.HTTPResponse]:
            connection = http.client.HTTPConnection(target.hostname, target.port, timeout=30)
            try:
                connection.request(self.command, proxy_path, body=body or None, headers=request_headers)
                return connection, connection.getresponse()
            except BaseException:
                connection.close()
                raise

        def response_header_map(response_headers: list[tuple[str, str]]) -> dict[str, str]:
            return {key.lower(): value for key, value in response_headers}

        def response_content_length(response_headers: list[tuple[str, str]]) -> int | None:
            value = response_header_map(response_headers).get("content-length")
            if value is None:
                return None
            try:
                return max(0, int(value))
            except ValueError:
                return None

        def response_can_be_rewritten(status: int, response_headers: list[tuple[str, str]]) -> bool:
            if status != 200 or self.command != "GET":
                return False
            header_map = response_header_map(response_headers)
            if header_map.get("content-encoding"):
                return False
            content_type = header_map.get("content-type", "").lower()
            if not any(kind in content_type for kind in ("text/html", "text/css", "application/json")):
                return False
            content_length = response_content_length(response_headers)
            return content_length is not None and content_length <= self._rewrite_buffer_bytes()

        def send_proxy_headers(status: int, reason: str, response_headers: list[tuple[str, str]], *, content_length: int | None) -> None:
            self.send_response(status, reason)
            for key, value in response_headers:
                lowered = key.lower()
                if lowered in HOP_BY_HOP_HEADERS or lowered == "content-length":
                    continue
                self.send_header(key, value)
            if content_length is not None:
                self.send_header("Content-Length", str(content_length))
            self.end_headers()

        connection: http.client.HTTPConnection | None = None
        response: http.client.HTTPResponse | None = None

        try:
            connection, response = request_backend(headers)
            status, reason, response_headers = response.status, response.reason, response.getheaders()
            if status == 401 and backend_token:
                response.read(min(self._rewrite_buffer_bytes(), 1024 * 1024))
                connection.close()
                connection = None
                response = None
                refreshed = self._backend_session_token(force_refresh=True)
                if refreshed and refreshed != backend_token:
                    retry_headers = dict(headers)
                    retry_headers[BACKEND_SESSION_HEADER_NAME] = refreshed
                    connection, response = request_backend(retry_headers)
                    status, reason, response_headers = response.status, response.reason, response.getheaders()
        except OSError as exc:
            payload = f"Dashboard backend unavailable: {exc}\n".encode("utf-8", "replace")
            response_headers = [("Content-Type", "text/plain; charset=utf-8")]
            reason = "Bad Gateway"
            status = 502
            if connection is not None:
                connection.close()
            connection = None
            response = None

        if response is not None and not response_can_be_rewritten(status, response_headers):
            content_length = response_content_length(response_headers)
            if content_length is None:
                self.close_connection = True
            send_proxy_headers(status, reason, response_headers, content_length=content_length)
            if self.command != "HEAD":
                try:
                    while True:
                        chunk = response.read(PROXY_COPY_CHUNK_BYTES)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                finally:
                    if connection is not None:
                        connection.close()
            elif connection is not None:
                connection.close()
            return

        if response is not None:
            payload = response.read(self._rewrite_buffer_bytes() + 1)
            if connection is not None:
                connection.close()
            if len(payload) > self._rewrite_buffer_bytes():
                self._send_body(413, b"Dashboard response body is too large to rewrite.\n")
                return

        if status == 200:
            payload = self._rewrite_mounted_html_paths(payload, response_headers)
            payload = self._rewrite_mounted_css_paths(payload, response_headers)
            payload = self._rewrite_mounted_json_paths(payload, response_headers)
            payload = self._maybe_inject_managed_lifecycle_controls(payload, response_headers)
            payload = self._maybe_inject_crew_switcher(payload, response_headers)
            payload = self._maybe_inject_plugin_deeplink(payload, response_headers)

        send_proxy_headers(status, reason, response_headers, content_length=len(payload))
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
