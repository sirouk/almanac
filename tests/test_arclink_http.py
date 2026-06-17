#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_module(filename: str, name: str):
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    path = PYTHON_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_http_request_redacts_sensitive_url_parts_on_transport_error() -> None:
    mod = load_module("arclink_http.py", "arclink_http_redaction")
    original_httpx = sys.modules.get("httpx")

    class FakeHTTPError(Exception):
        pass

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def request(self, *args, **kwargs):
            raise FakeHTTPError("read timed out")

    class FakeHttpx:
        HTTPError = FakeHTTPError
        Client = FakeClient

    sys.modules["httpx"] = FakeHttpx()
    try:
        try:
            mod.http_request(
                "https://api.telegram.org/bot123456:secret-token/setMyCommands?access_token=also-secret&chat_id=5"
            )
        except RuntimeError as exc:
            text = str(exc)
        else:
            raise AssertionError("transport failure should raise")
    finally:
        if original_httpx is None:
            sys.modules.pop("httpx", None)
        else:
            sys.modules["httpx"] = original_httpx

    expect("123456:secret-token" not in text, text)
    expect("also-secret" not in text, text)
    expect("/botREDACTED/setMyCommands" in text, text)
    expect("access_token=REDACTED" in text, text)
    print("PASS test_http_request_redacts_sensitive_url_parts_on_transport_error")


def test_secure_transport_rejects_non_https_schemes() -> None:
    mod = load_module("arclink_http.py", "arclink_http_scheme_test")
    mod.enforce_secure_transport("https://api.example.test/v1")
    mod.enforce_secure_transport("http://127.0.0.1:8181/mcp")
    for url in (
        "http://api.example.test/v1",
        "file:///etc/passwd",
        "ftp://api.example.test/resource",
        "//api.example.test/v1",
    ):
        try:
            mod.enforce_secure_transport(url)
        except RuntimeError as exc:
            expect("insecure transport refused" in str(exc), str(exc))
        else:
            raise AssertionError(f"expected {url} to be refused")
    print("PASS test_secure_transport_rejects_non_https_schemes")


def test_parse_json_errors_redact_url_label() -> None:
    mod = load_module("arclink_http.py", "arclink_http_parse_redaction_test")
    response = mod.HttpResponse(status_code=200, text="{bad-json", headers={})
    try:
        mod.parse_json_response(
            response,
            label="https://api.telegram.org/bot123456:secret-token/getMe?access_token=also-secret",
        )
    except RuntimeError as exc:
        text = str(exc)
    else:
        raise AssertionError("expected invalid json to raise")
    expect("123456:secret-token" not in text, text)
    expect("also-secret" not in text, text)
    expect("/botREDACTED/getMe" in text, text)
    expect("access_token=REDACTED" in text, text)

    array_response = mod.HttpResponse(status_code=200, text="[1, 2, 3]", headers={})
    try:
        mod.parse_json_object(
            array_response,
            label="https://user:secret@example.test/path?api_key=secret-value",
        )
    except RuntimeError as exc:
        text = str(exc)
    else:
        raise AssertionError("expected non-object json to raise")
    expect("user:secret" not in text, text)
    expect("api_key=REDACTED" in text, text)
    print("PASS test_parse_json_errors_redact_url_label")


if __name__ == "__main__":
    test_http_request_redacts_sensitive_url_parts_on_transport_error()
    test_secure_transport_rejects_non_https_schemes()
    test_parse_json_errors_redact_url_label()
