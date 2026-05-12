#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from urllib.error import HTTPError

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "python" / "arclink_notion_ssot.py"


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


class FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def http_error(url: str, status: int, payload: dict, hdrs=None) -> HTTPError:
    return HTTPError(
        url=url,
        code=status,
        msg=str(payload.get("message") or f"http {status}"),
        hdrs=hdrs,
        fp=io.BytesIO(json.dumps(payload).encode("utf-8")),
    )


def test_extract_notion_space_id_accepts_urls_and_raw_ids() -> None:
    mod = load_module(MODULE_PATH, "arclink_notion_ssot_extract_test")
    expected = "12345678-90ab-cdef-1234-567890abcdef"
    expect(
        mod.extract_notion_space_id("https://www.notion.so/Acme-SSOT-1234567890abcdef1234567890abcdef?pvs=4") == expected,
        "expected hyphenless Notion URL id to normalize",
    )
    expect(
        mod.extract_notion_space_id("12345678-90ab-cdef-1234-567890abcdef") == expected,
        "expected raw UUID to pass through normalized",
    )
    print("PASS test_extract_notion_space_id_accepts_urls_and_raw_ids")


def test_normalize_notion_space_url_strips_query_and_fragment() -> None:
    mod = load_module(MODULE_PATH, "arclink_notion_ssot_normalize_url_test")
    expect(
        mod.normalize_notion_space_url(
            "https://www.notion.so/2c7ac68274b14a69904e4989e27b6c76?pvs=16#section"
        )
        == "https://www.notion.so/2c7ac68274b14a69904e4989e27b6c76",
        "expected Notion URL normalization to remove query parameters and fragments",
    )
    expect(
        mod.normalize_notion_space_url("12345678-90ab-cdef-1234-567890abcdef")
        == "12345678-90ab-cdef-1234-567890abcdef",
        "expected raw ids to pass through unchanged",
    )
    print("PASS test_normalize_notion_space_url_strips_query_and_fragment")


def test_handshake_notion_space_falls_back_to_database_lookup() -> None:
    mod = load_module(MODULE_PATH, "arclink_notion_ssot_handshake_test")
    target_url = "https://www.notion.so/Acme-SSOT-1234567890abcdef1234567890abcdef"
    source_url = f"{target_url}?pvs=16"
    root_page_url = "https://www.notion.so/The-ArcLink-aaaaaaaaaaaabbbbbbbbbbbbbbbb"

    def fake_urlopen(req, timeout=15):
        full_url = req.full_url
        if full_url.endswith("/users/me"):
            return FakeResponse(
                {
                    "object": "user",
                    "id": "integration-1",
                    "name": "ArcLink SSOT",
                    "type": "bot",
                    "bot": {"workspace_name": "Acme"},
                }
            )
        if full_url.endswith("/pages/12345678-90ab-cdef-1234-567890abcdef"):
            raise http_error(full_url, 404, {"message": "object not found", "code": "object_not_found"})
        if full_url.endswith("/pages/aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb"):
            return FakeResponse(
                {
                    "object": "page",
                    "id": "aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb",
                    "url": root_page_url,
                    "properties": {
                        "title": {
                            "type": "title",
                            "title": [{"plain_text": "The ArcLink"}],
                        }
                    },
                }
            )
        if full_url.endswith("/databases/12345678-90ab-cdef-1234-567890abcdef"):
            return FakeResponse(
                {
                    "object": "database",
                    "id": "12345678-90ab-cdef-1234-567890abcdef",
                    "url": target_url,
                    "title": [{"plain_text": "Acme SSOT"}],
                    "parent": {"type": "page_id", "page_id": "aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb"},
                }
            )
        raise AssertionError(f"unexpected url: {full_url}")

    payload = mod.handshake_notion_space(
        space_url=source_url,
        token="secret_test",
        api_version=mod.DEFAULT_NOTION_API_VERSION,
        urlopen_fn=fake_urlopen,
    )
    expect(payload["space_kind"] == "database", payload)
    expect(payload["space_title"] == "Acme SSOT", payload)
    expect(payload["space_url"] == target_url, payload)
    expect(payload["root_page_id"] == "aaaaaaaa-aaaa-bbbb-bbbb-bbbbbbbbbbbb", payload)
    expect(payload["root_page_url"] == root_page_url, payload)
    expect(payload["root_page_title"] == "The ArcLink", payload)
    expect(payload["integration"]["workspace_name"] == "Acme", payload)
    print("PASS test_handshake_notion_space_falls_back_to_database_lookup")


def test_handshake_notion_space_reports_invalid_secret_cleanly() -> None:
    mod = load_module(MODULE_PATH, "arclink_notion_ssot_invalid_secret_test")
    target_url = "https://www.notion.so/Acme-SSOT-1234567890abcdef1234567890abcdef"

    def fake_urlopen(req, timeout=15):
        raise http_error(req.full_url, 401, {"message": "unauthorized", "code": "unauthorized"})

    try:
        mod.handshake_notion_space(
            space_url=target_url,
            token="bad_secret",
            api_version=mod.DEFAULT_NOTION_API_VERSION,
            urlopen_fn=fake_urlopen,
        )
    except RuntimeError as exc:
        expect("rejected the integration secret" in str(exc), str(exc))
    else:
        raise AssertionError("expected handshake to fail for an invalid secret")
    print("PASS test_handshake_notion_space_reports_invalid_secret_cleanly")


def test_create_notion_page_prefers_database_data_source_parent() -> None:
    mod = load_module(MODULE_PATH, "arclink_notion_ssot_create_page_test")
    calls: list[tuple[str, dict]] = []

    def fake_urlopen(req, timeout=15):
        body = json.loads((req.data or b"{}").decode("utf-8"))
        calls.append((req.full_url, body))
        if req.full_url.endswith("/databases/12345678-90ab-cdef-1234-567890abcdef"):
            return FakeResponse(
                {
                    "object": "database",
                    "id": "12345678-90ab-cdef-1234-567890abcdef",
                    "data_sources": [{"id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}],
                }
            )
        if req.full_url.endswith("/pages"):
            return FakeResponse({"object": "page", "id": "feedface-0000-0000-0000-000000000000"})
        raise AssertionError(f"unexpected url: {req.full_url}")

    payload = mod.create_notion_page(
        parent_id="12345678-90ab-cdef-1234-567890abcdef",
        parent_kind="database",
        token="secret_test",
        payload={"properties": {"Name": {"title": [{"text": {"content": "hello"}}]}}},
        api_version=mod.DEFAULT_NOTION_API_VERSION,
        urlopen_fn=fake_urlopen,
    )
    expect(payload["id"] == "feedface-0000-0000-0000-000000000000", payload)
    expect(len(calls) == 2, calls)
    expect(calls[1][1]["parent"] == {"type": "data_source_id", "data_source_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}, calls)
    print("PASS test_create_notion_page_prefers_database_data_source_parent")


def test_update_notion_page_uses_patch_endpoint() -> None:
    mod = load_module(MODULE_PATH, "arclink_notion_ssot_update_page_test")
    seen: list[tuple[str, str, dict]] = []

    def fake_urlopen(req, timeout=15):
        body = json.loads((req.data or b"{}").decode("utf-8"))
        seen.append((req.get_method(), req.full_url, body))
        return FakeResponse({"object": "page", "id": "12345678-90ab-cdef-1234-567890abcdef", "archived": False})

    payload = mod.update_notion_page(
        page_id="12345678-90ab-cdef-1234-567890abcdef",
        token="secret_test",
        payload={"properties": {"Status": {"status": {"name": "In Progress"}}}},
        api_version=mod.DEFAULT_NOTION_API_VERSION,
        urlopen_fn=fake_urlopen,
    )
    expect(payload["id"] == "12345678-90ab-cdef-1234-567890abcdef", payload)
    expect(
        seen == [
            (
                "PATCH",
                "https://api.notion.com/v1/pages/12345678-90ab-cdef-1234-567890abcdef",
                {"properties": {"Status": {"status": {"name": "In Progress"}}}},
            )
        ],
        str(seen),
    )
    print("PASS test_update_notion_page_uses_patch_endpoint")


def test_request_json_retries_rate_limit_and_honors_retry_after() -> None:
    mod = load_module(MODULE_PATH, "arclink_notion_ssot_retry_test")
    attempts = {"count": 0}
    sleeps: list[float] = []

    def fake_urlopen(req, timeout=15):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise http_error(
                req.full_url,
                429,
                {"message": "slow down", "code": "rate_limited"},
                hdrs={"Retry-After": "2"},
            )
        return FakeResponse({"object": "user", "id": "integration-1"})

    payload = mod._request_json(
        "GET",
        "/users/me",
        token="secret_test",
        api_version=mod.DEFAULT_NOTION_API_VERSION,
        urlopen_fn=fake_urlopen,
        sleep_fn=lambda seconds: sleeps.append(float(seconds)),
    )
    expect(payload["id"] == "integration-1", payload)
    expect(attempts["count"] == 3, str(attempts))
    expect(sleeps == [2.0, 2.0], str(sleeps))
    print("PASS test_request_json_retries_rate_limit_and_honors_retry_after")


def test_request_json_does_not_retry_notion_conflict() -> None:
    mod = load_module(MODULE_PATH, "arclink_notion_ssot_conflict_retry_test")
    attempts = {"count": 0}

    def fake_urlopen(req, timeout=15):
        attempts["count"] += 1
        raise http_error(
            req.full_url,
            409,
            {"message": "conflict", "code": "conflict_error"},
        )

    try:
        mod._request_json(
            "PATCH",
            "/pages/11111111-2222-3333-4444-555555555555",
            token="secret_test",
            api_version=mod.DEFAULT_NOTION_API_VERSION,
            payload={"archived": False},
            urlopen_fn=fake_urlopen,
            sleep_fn=lambda _seconds: (_ for _ in ()).throw(AssertionError("409 should not sleep/retry")),
        )
    except mod.NotionApiError as exc:
        expect(exc.status == 409, str(exc))
    else:
        raise AssertionError("expected Notion conflict to raise")
    expect(attempts["count"] == 1, str(attempts))
    print("PASS test_request_json_does_not_retry_notion_conflict")


def test_preflight_notion_root_children_creates_and_trashes_temp_objects() -> None:
    mod = load_module(MODULE_PATH, "arclink_notion_ssot_preflight_root_test")
    seen: list[tuple[str, str, dict]] = []

    def fake_urlopen(req, timeout=15):
        body = json.loads((req.data or b"{}").decode("utf-8"))
        seen.append((req.get_method(), req.full_url, body))
        if req.get_method() == "POST" and req.full_url.endswith("/pages"):
            return FakeResponse({"object": "page", "id": "feedface-0000-0000-0000-000000000000"})
        if req.get_method() == "POST" and req.full_url.endswith("/databases"):
            return FakeResponse({"object": "database", "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"})
        if req.get_method() == "PATCH" and req.full_url.endswith("/pages/feedface-0000-0000-0000-000000000000"):
            return FakeResponse({"object": "page", "id": "feedface-0000-0000-0000-000000000000", "in_trash": True})
        if req.get_method() == "PATCH" and req.full_url.endswith("/databases/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"):
            return FakeResponse({"object": "database", "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "in_trash": True})
        raise AssertionError(f"unexpected request: {req.get_method()} {req.full_url}")

    payload = mod.preflight_notion_root_children(
        root_page_id="11111111-2222-3333-4444-555555555555",
        token="secret_test",
        api_version=mod.DEFAULT_NOTION_API_VERSION,
        urlopen_fn=fake_urlopen,
    )
    expect(payload["ok"] is True, payload)
    expect(payload["root_page_id"] == "11111111-2222-3333-4444-555555555555", payload)
    expect(payload["temp_page_id"] == "feedface-0000-0000-0000-000000000000", payload)
    expect(payload["temp_database_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", payload)
    expect(
        seen == [
            (
                "POST",
                "https://api.notion.com/v1/pages",
                {
                    "properties": {
                        "title": [
                            {
                                "type": "text",
                                "text": {"content": "ArcLink preflight page"},
                            }
                        ]
                    },
                    "parent": {"type": "page_id", "page_id": "11111111-2222-3333-4444-555555555555"},
                },
            ),
            (
                "POST",
                "https://api.notion.com/v1/databases",
                {
                    "parent": {"type": "page_id", "page_id": "11111111-2222-3333-4444-555555555555"},
                    "title": [
                        {"type": "text", "text": {"content": "ArcLink Preflight Database"}},
                    ],
                    "initial_data_source": {"properties": {"Name": {"title": {}}}},
                    "description": [
                        {
                            "type": "text",
                            "text": {
                                "content": "Temporary database created by ArcLink setup preflight. Safe to trash immediately."
                            },
                        }
                    ],
                },
            ),
            (
                "PATCH",
                "https://api.notion.com/v1/databases/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                {"in_trash": True},
            ),
            (
                "PATCH",
                "https://api.notion.com/v1/pages/feedface-0000-0000-0000-000000000000",
                {"in_trash": True},
            ),
        ],
        str(seen),
    )
    print("PASS test_preflight_notion_root_children_creates_and_trashes_temp_objects")


def test_update_notion_database_and_data_source_use_patch_endpoints() -> None:
    mod = load_module(MODULE_PATH, "arclink_notion_ssot_update_collection_test")
    seen: list[tuple[str, str, dict]] = []

    def fake_urlopen(req, timeout=15):
        body = json.loads((req.data or b"{}").decode("utf-8"))
        seen.append((req.get_method(), req.full_url, body))
        return FakeResponse({"object": "ok", "id": "12345678-90ab-cdef-1234-567890abcdef"})

    mod.update_notion_database(
        database_id="12345678-90ab-cdef-1234-567890abcdef",
        token="secret_test",
        payload={"in_trash": True},
        api_version=mod.DEFAULT_NOTION_API_VERSION,
        urlopen_fn=fake_urlopen,
    )
    mod.update_notion_data_source(
        data_source_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        token="secret_test",
        payload={"properties": {"Owner": {"people": {}}}},
        api_version=mod.DEFAULT_NOTION_API_VERSION,
        urlopen_fn=fake_urlopen,
    )
    expect(
        seen == [
            (
                "PATCH",
                "https://api.notion.com/v1/databases/12345678-90ab-cdef-1234-567890abcdef",
                {"in_trash": True},
            ),
            (
                "PATCH",
                "https://api.notion.com/v1/data_sources/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                {"properties": {"Owner": {"people": {}}}},
            ),
        ],
        str(seen),
    )
    print("PASS test_update_notion_database_and_data_source_use_patch_endpoints")


def test_no_secret_notion_ssot_proof_harness_covers_callback_read_write_and_nonproof_email() -> None:
    mod = load_module(MODULE_PATH, "arclink_notion_ssot_proof_harness_test")
    root_id = "11111111-2222-3333-4444-555555555555"
    seen: list[tuple[str, str, dict]] = []

    def fake_urlopen(req, timeout=15):
        body = json.loads((req.data or b"{}").decode("utf-8"))
        seen.append((req.get_method(), req.full_url, body))
        if req.get_method() == "GET" and req.full_url.endswith(f"/pages/{root_id}"):
            return FakeResponse(
                {
                    "object": "page",
                    "id": root_id,
                    "url": "https://www.notion.so/shared-root-11111111222233334444555555555555",
                    "properties": {
                        "title": {
                            "type": "title",
                            "title": [{"plain_text": "Shared Root"}],
                        }
                    },
                }
            )
        if req.get_method() == "POST" and req.full_url.endswith("/pages"):
            return FakeResponse({"object": "page", "id": "feedface-0000-0000-0000-000000000000"})
        if req.get_method() == "POST" and req.full_url.endswith("/databases"):
            return FakeResponse({"object": "database", "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"})
        if req.get_method() == "PATCH" and req.full_url.endswith("/databases/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"):
            return FakeResponse({"object": "database", "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "in_trash": True})
        if req.get_method() == "PATCH" and req.full_url.endswith("/pages/feedface-0000-0000-0000-000000000000"):
            return FakeResponse({"object": "page", "id": "feedface-0000-0000-0000-000000000000", "in_trash": True})
        raise AssertionError(f"unexpected request: {req.get_method()} {req.full_url}")

    payload = mod.run_notion_ssot_no_secret_proof(
        callback_url="https://u-amber-vault-1a2b.example.test/notion/webhook",
        root_page_id=root_id,
        token="secret_test_token",
        token_ref="secret://arclink/notion/root",
        urlopen_fn=fake_urlopen,
        run_write_preflight=True,
        proof_mode="fake",
    )
    checks = {item["name"]: item for item in payload["checks"]}
    expect(payload["ok"] is True, str(payload))
    expect(payload["model"] == "brokered_shared_root", str(payload))
    expect(payload["token_ref_status"] == "secret_reference", str(payload))
    expect(checks["callback_url_presence"]["status"] == "pass", str(checks))
    expect(checks["shared_root_page_readability"]["status"] == "pass", str(checks))
    expect(checks["shared_root_page_readability"]["evidence"]["page_title"] == "Shared Root", str(checks))
    expect(checks["brokered_ssot_write_preflight"]["status"] == "pass", str(checks))
    expect(checks["email_share_only_status"]["status"] == "not_proof", str(checks))
    expect(checks["user_owned_oauth_status"]["status"] == "proof_gated", str(checks))
    expect(checks["live_workspace_mutation_status"]["status"] == "proof_gated", str(checks))
    text = json.dumps(payload, sort_keys=True)
    expect("secret_test_token" not in text, text)
    expect("secret://arclink/notion/root" not in text, text)
    expect([item[0] for item in seen] == ["GET", "POST", "POST", "PATCH", "PATCH"], str(seen))
    print("PASS test_no_secret_notion_ssot_proof_harness_covers_callback_read_write_and_nonproof_email")


def test_notion_ssot_proof_harness_keeps_live_write_preflight_gated_without_authorization() -> None:
    mod = load_module(MODULE_PATH, "arclink_notion_ssot_proof_harness_gated_test")
    root_id = "11111111-2222-3333-4444-555555555555"
    seen: list[str] = []

    def fake_urlopen(req, timeout=15):
        seen.append(f"{req.get_method()} {req.full_url}")
        if req.get_method() == "GET" and req.full_url.endswith(f"/pages/{root_id}"):
            return FakeResponse({"object": "page", "id": root_id, "properties": {}})
        raise AssertionError(f"unexpected live-gated request: {req.get_method()} {req.full_url}")

    payload = mod.run_notion_ssot_no_secret_proof(
        callback_url="https://u-amber-vault-1a2b.example.test/notion/webhook",
        root_page_id=root_id,
        token="secret_test_token",
        token_ref="secret://arclink/notion/root",
        urlopen_fn=fake_urlopen,
        run_write_preflight=True,
        proof_mode="authorized_live",
        allow_live_mutation=False,
    )
    checks = {item["name"]: item for item in payload["checks"]}
    expect(checks["brokered_ssot_write_preflight"]["status"] == "proof_gated", str(payload))
    expect(seen == [f"GET https://api.notion.com/v1/pages/{root_id}"], str(seen))
    print("PASS test_notion_ssot_proof_harness_keeps_live_write_preflight_gated_without_authorization")


def main() -> int:
    test_extract_notion_space_id_accepts_urls_and_raw_ids()
    test_normalize_notion_space_url_strips_query_and_fragment()
    test_handshake_notion_space_falls_back_to_database_lookup()
    test_handshake_notion_space_reports_invalid_secret_cleanly()
    test_create_notion_page_prefers_database_data_source_parent()
    test_update_notion_page_uses_patch_endpoint()
    test_request_json_retries_rate_limit_and_honors_retry_after()
    test_request_json_does_not_retry_notion_conflict()
    test_preflight_notion_root_children_creates_and_trashes_temp_objects()
    test_update_notion_database_and_data_source_use_patch_endpoints()
    test_no_secret_notion_ssot_proof_harness_covers_callback_read_write_and_nonproof_email()
    test_notion_ssot_proof_harness_keeps_live_write_preflight_gated_without_authorization()
    print("PASS all 11 notion ssot regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
