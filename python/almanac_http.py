#!/usr/bin/env python3
from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    text: str
    headers: dict[str, str]


def _is_loopback_host(host: str) -> bool:
    normalized = str(host or "").strip().strip("[]").lower()
    if not normalized:
        return False
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def enforce_secure_transport(url: str, *, allow_loopback_http: bool = True) -> None:
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme != "http":
        return
    if allow_loopback_http and _is_loopback_host(parsed.hostname or ""):
        return
    raise RuntimeError(f"insecure transport refused for non-loopback URL: {url}")


def http_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    json_payload: Any = None,
    form_payload: dict[str, Any] | None = None,
    content: bytes | str | None = None,
    timeout: int = 20,
    allow_loopback_http: bool = True,
) -> HttpResponse:
    if sum(value is not None for value in (json_payload, form_payload, content)) > 1:
        raise ValueError("choose only one of json_payload, form_payload, or content")
    enforce_secure_transport(url, allow_loopback_http=allow_loopback_http)
    request_headers = dict(headers or {})
    normalized_form_payload = None
    if form_payload is not None:
        normalized_form_payload = {
            key: str(value) for key, value in form_payload.items() if value is not None
        }
    try:
        import httpx
    except ImportError:
        httpx = None
    if httpx is not None:
        request_kwargs: dict[str, Any] = {}
        if json_payload is not None:
            request_kwargs["json"] = json_payload
        elif normalized_form_payload is not None:
            request_kwargs["data"] = normalized_form_payload
        elif content is not None:
            request_kwargs["content"] = content
        try:
            with httpx.Client(timeout=float(timeout)) as client:
                response = client.request(method.upper(), url, headers=request_headers, **request_kwargs)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"{url} request failed: {exc}") from exc
        return HttpResponse(
            status_code=response.status_code,
            text=response.text,
            headers={key.lower(): value for key, value in response.headers.items()},
        )
    data = None
    if json_payload is not None:
        data = json.dumps(json_payload).encode("utf-8")
    elif normalized_form_payload is not None:
        data = urllib.parse.urlencode(normalized_form_payload).encode("utf-8")
    elif content is not None:
        data = content.encode("utf-8") if isinstance(content, str) else content
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpResponse(
                status_code=response.status,
                text=response.read().decode("utf-8", errors="replace"),
                headers={key.lower(): value for key, value in response.headers.items()},
            )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        response_headers = {}
        if getattr(exc, "headers", None) is not None:
            response_headers = {key.lower(): value for key, value in exc.headers.items()}
        return HttpResponse(status_code=exc.code, text=body, headers=response_headers)
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(f"{url} request failed: {reason}") from exc


def parse_json_response(response: HttpResponse, *, label: str) -> Any:
    if not response.text.strip():
        return {}
    try:
        return json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} returned invalid json: {response.text[:200]}") from exc


def parse_json_object(response: HttpResponse, *, label: str) -> dict[str, Any]:
    payload = parse_json_response(response, label=label)
    if isinstance(payload, dict):
        return payload
    raise RuntimeError(f"{label} returned unexpected payload: {response.text[:200]}")
