#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Mapping

from arclink_test_helpers import expect, load_module


def fake_upstream_transport(
    payload: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
    content: bytes | str | None = None,
):
    import json

    import httpx

    requests: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        raw_body = request.content
        try:
            body = json.loads(raw_body.decode("utf-8") if raw_body else "{}")
        except Exception:
            body = {}
        requests.append(
            {
                "method": request.method,
                "url": str(request.url),
                "payload": body,
                "headers": dict(request.headers),
            }
        )
        if content is not None:
            raw = content.encode("utf-8") if isinstance(content, str) else content
            return httpx.Response(status_code, content=raw)
        return httpx.Response(
            status_code,
            json=payload
            or {
                "id": "chatcmpl_fake",
                "object": "chat.completion",
                "usage": {"prompt_tokens": 8, "completion_tokens": 5, "total_tokens": 13},
            },
        )

    transport = httpx.MockTransport(handler)
    transport.requests = requests  # type: ignore[attr-defined]
    return transport


def fake_stream_transport(chunks: list[bytes], marks: list[str]):
    import httpx

    class ChunkStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for idx, chunk in enumerate(chunks):
                marks.append(f"yield:{idx}")
                yield chunk

    requests: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        import json

        requests.append({"payload": json.loads(request.content.decode("utf-8"))})
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=ChunkStream())

    transport = httpx.MockTransport(handler)
    transport.requests = requests  # type: ignore[attr-defined]
    return transport


def fake_broken_stream_transport(first_chunk: bytes, error_message: str):
    import httpx

    class BrokenStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield first_chunk
            raise OSError(error_message)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=BrokenStream())

    return httpx.MockTransport(handler)


def temp_router_db() -> tuple[tempfile.TemporaryDirectory[str], str]:
    tmp = tempfile.TemporaryDirectory()
    path = str(Path(tmp.name) / "router.sqlite3")
    conn = sqlite3.connect(path)
    conn.close()
    return tmp, path


def _client_for(env: dict[str, str], upstream_transport: Any | None = None):
    try:
        from fastapi.testclient import TestClient
    except ModuleNotFoundError as exc:
        raise AssertionError("FastAPI test dependencies are missing; install requirements-dev.txt") from exc

    router = load_module("arclink_llm_router.py", "arclink_llm_router_test")
    config = router.load_router_config(env)
    return TestClient(router.create_app(config, upstream_transport=upstream_transport))


def _seed_router_key(
    db_path: str,
    *,
    status: str = "active",
    entitlement_state: str = "paid",
    subscription_status: str = "",
    deployment_metadata: Mapping[str, Any] | None = None,
) -> str:
    control = load_module("arclink_control.py", "arclink_control_llm_router_key_test")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    control.upsert_arclink_user(
        conn,
        user_id="user_1",
        email="person@example.test",
        entitlement_state=entitlement_state,
    )
    if subscription_status:
        control.upsert_arclink_subscription_mirror(
            conn,
            subscription_id="sub_1",
            user_id="user_1",
            status=subscription_status,
        )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_1",
        user_id="user_1",
        prefix="amber-vault-1a2b",
        base_domain="example.test",
        status="active",
        metadata=dict(deployment_metadata or {}),
    )
    raw_key = control.generate_llm_router_raw_key()
    record = control.ensure_llm_router_key(
        conn,
        deployment_id="dep_1",
        user_id="user_1",
        secret_ref="secret://arclink/llm-router/dep_1/api-key",
        raw_key=raw_key,
        allowed_models=["model-a", "model-b"],
    )
    if status != "active":
        conn.execute("UPDATE arclink_llm_router_keys SET status = ? WHERE key_id = ?", (status, record["key_id"]))
        conn.commit()
    conn.close()
    return raw_key


def test_health_reports_unhealthy_without_central_chutes_key() -> None:
    tmp, db_path = temp_router_db()
    try:
        client = _client_for({"ARCLINK_DB_PATH": db_path, "ARCLINK_LLM_ROUTER_ENABLED": "1"})
        response = client.get("/health")
        payload = response.json()
        expect(response.status_code == 503, str(payload))
        expect(payload["status"] == "unhealthy", str(payload))
        expect(payload["configured"] is False, str(payload))
        expect("api_key" not in str(payload).lower() and "secret" not in str(payload).lower(), str(payload))

        legacy_client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "CHUTES_API_KEY": "cpk_test_legacy_control_secret_123",
            }
        )
        legacy_response = legacy_client.get("/health")
        legacy_payload = legacy_response.json()
        expect(legacy_response.status_code == 503, str(legacy_payload))
        expect(legacy_payload["configured"] is False, str(legacy_payload))
        expect("cpk_test_legacy_control_secret_123" not in legacy_response.text, legacy_response.text)
    finally:
        tmp.cleanup()
    print("PASS test_health_reports_unhealthy_without_central_chutes_key")


def test_health_and_models_report_configured_state_without_exposing_key() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path)
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_ALLOWED_MODELS": "model-a, model-b",
            }
        )
        health = client.get("/health")
        expect(health.status_code == 200, health.text)
        health_payload = health.json()
        expect(health_payload["status"] == "ok", str(health_payload))
        expect(health_payload["model_count"] == 2, str(health_payload))
        expect("cpk_test_router_secret_123" not in health.text, health.text)

        models = client.get("/v1/models", headers={"Authorization": f"Bearer {raw_key}"})
        expect(models.status_code == 200, models.text)
        model_ids = [item["id"] for item in models.json()["data"]]
        expect(model_ids == ["model-a", "model-b"], str(model_ids))
    finally:
        tmp.cleanup()
    print("PASS test_health_and_models_report_configured_state_without_exposing_key")


def test_chat_non_streaming_forwards_to_fake_upstream_and_records_usage() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path)
        upstream = fake_upstream_transport(
            {
                "id": "chatcmpl_fake",
                "object": "chat.completion",
                "model": "model-a",
                "choices": [{"message": {"role": "assistant", "content": "hello"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            }
        )
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "1000",
            },
            upstream_transport=upstream,
        )
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "messages": [{"role": "user", "content": "hello"}]},
        )
        payload = response.json()
        expect(response.status_code == 200, str(payload))
        expect(payload["id"] == "chatcmpl_fake", str(payload))
        expect(len(upstream.requests) == 1, str(upstream.requests))  # type: ignore[attr-defined]
        sent = upstream.requests[0]  # type: ignore[attr-defined]
        expect(sent["url"].endswith("/chat/completions"), str(sent))
        expect(sent["payload"]["model"] == "model-a", str(sent))
        expect(sent["headers"].get("authorization") == "Bearer cpk_test_router_secret_123", str(sent["headers"]))
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        open_reservations = conn.execute(
            "SELECT COUNT(*) AS count FROM arclink_llm_budget_reservations WHERE status = 'reserved'"
        ).fetchone()["count"]
        usage = conn.execute("SELECT * FROM arclink_llm_usage_events").fetchone()
        deployment = conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()
        conn.close()
        expect(open_reservations == 0, f"expected no leaked reservations, found {open_reservations}")
        expect(usage["status"] == "succeeded", dict(usage))
        expect(usage["input_tokens"] == 7 and usage["output_tokens"] == 3 and usage["total_tokens"] == 10, dict(usage))
        expect("hello" not in str(dict(usage)) and "hello" not in str(dict(deployment)), "prompt/completion leaked into stored usage")
    finally:
        tmp.cleanup()
    print("PASS test_chat_non_streaming_forwards_to_fake_upstream_and_records_usage")


def test_chat_preflight_rejects_invalid_model_and_size_limits() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path)
        env = {
            "ARCLINK_DB_PATH": db_path,
            "ARCLINK_LLM_ROUTER_ENABLED": "1",
            "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
            "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "1000",
            "ARCLINK_LLM_ROUTER_MAX_BODY_BYTES": "256",
            "ARCLINK_LLM_ROUTER_PROMPT_ESTIMATE_TOKEN_CAP": "24",
            "ARCLINK_LLM_ROUTER_MAX_TOKENS_CAP": "32",
        }
        client = _client_for(env)
        invalid_model = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-c", "messages": [{"role": "user", "content": "hello"}]},
        )
        expect(invalid_model.status_code == 403, invalid_model.text)
        expect(invalid_model.json()["error"]["code"] == "model_not_allowed", invalid_model.text)

        max_tokens = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "max_tokens": 33, "messages": [{"role": "user", "content": "hello"}]},
        )
        expect(max_tokens.status_code == 400, max_tokens.text)
        expect(max_tokens.json()["error"]["code"] == "max_tokens_too_large", max_tokens.text)

        prompt = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "messages": [{"role": "user", "content": "x" * 180}]},
        )
        expect(prompt.status_code == 413, prompt.text)
        expect(prompt.json()["error"]["code"] in {"request_body_too_large", "prompt_too_large"}, prompt.text)
    finally:
        tmp.cleanup()
    print("PASS test_chat_preflight_rejects_invalid_model_and_size_limits")


def test_chat_preflight_enforces_budget_and_billing_fail_closed() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path)
        upstream = fake_upstream_transport()
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
            },
            upstream_transport=upstream,
        )
        missing_budget = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "messages": [{"role": "user", "content": "hello"}]},
        )
        expect(missing_budget.status_code == 402, missing_budget.text)
        expect(missing_budget.json()["error"]["code"] == "budget_unconfigured", missing_budget.text)
        expect(len(upstream.requests) == 0, str(upstream.requests))  # type: ignore[attr-defined]
    finally:
        tmp.cleanup()

    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(
            db_path,
            deployment_metadata={"chutes": {"monthly_budget_cents": 100, "used_cents": 100}},
        )
        upstream = fake_upstream_transport()
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
            },
            upstream_transport=upstream,
        )
        exhausted = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "messages": [{"role": "user", "content": "hello"}]},
        )
        expect(exhausted.status_code == 402, exhausted.text)
        expect(exhausted.json()["error"]["code"] == "budget_exhausted", exhausted.text)
        expect(len(upstream.requests) == 0, str(upstream.requests))  # type: ignore[attr-defined]
    finally:
        tmp.cleanup()

    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path, subscription_status="past_due")
        upstream = fake_upstream_transport()
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "1000",
            },
            upstream_transport=upstream,
        )
        past_due = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "messages": [{"role": "user", "content": "hello"}]},
        )
        expect(past_due.status_code == 402, past_due.text)
        expect(past_due.json()["error"]["code"] == "billing_suspended", past_due.text)
        expect(len(upstream.requests) == 0, str(upstream.requests))  # type: ignore[attr-defined]
    finally:
        tmp.cleanup()
    print("PASS test_chat_preflight_enforces_budget_and_billing_fail_closed")


def test_chat_preflight_enforces_rate_limit_and_concurrency() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path)
        upstream = fake_upstream_transport()
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "1000",
                "ARCLINK_LLM_ROUTER_KEY_REQUESTS_PER_MINUTE": "1",
            },
            upstream_transport=upstream,
        )
        first = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "messages": [{"role": "user", "content": "hello"}]},
        )
        expect(first.status_code == 200, first.text)
        second = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "messages": [{"role": "user", "content": "hello"}]},
        )
        expect(second.status_code == 429, second.text)
        expect(second.json()["error"]["code"] == "rate_limited", second.text)
        expect(len(upstream.requests) == 1, str(upstream.requests))  # type: ignore[attr-defined]
    finally:
        tmp.cleanup()

    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO arclink_llm_budget_reservations (
              reservation_id, request_id, deployment_id, user_id, reserved_cents, status, created_at
            ) VALUES ('llmres_existing', 'llmreq_existing', 'dep_1', 'user_1', 1, 'reserved', '2026-05-16T00:00:00+00:00')
            """
        )
        conn.commit()
        conn.close()
        upstream = fake_upstream_transport()
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "1000",
                "ARCLINK_LLM_ROUTER_DEPLOYMENT_CONCURRENCY_LIMIT": "1",
            },
            upstream_transport=upstream,
        )
        limited = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "messages": [{"role": "user", "content": "hello"}]},
        )
        expect(limited.status_code == 429, limited.text)
        expect(limited.json()["error"]["code"] == "concurrency_limited", limited.text)
        expect(len(upstream.requests) == 0, str(upstream.requests))  # type: ignore[attr-defined]
    finally:
        tmp.cleanup()
    print("PASS test_chat_preflight_enforces_rate_limit_and_concurrency")


def test_router_keys_verify_fail_closed_and_do_not_store_raw_material() -> None:
    control = load_module("arclink_control.py", "arclink_control_llm_router_key_lifecycle_test")
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        verified = control.verify_llm_router_key(conn, raw_key)
        expect(verified is not None, "expected generated key to verify")
        expect(verified["deployment_id"] == "dep_1", str(verified))
        expect(verified["user_id"] == "user_1", str(verified))
        expect("key_hash" not in verified and "raw_key" not in verified, str(verified))
        expect(control.verify_llm_router_key(conn, "not-a-router-key") is None, "malformed key verified")
        expect(control.verify_llm_router_key(conn, raw_key + "x") is None, "invalid key verified")

        serialized_rows = "\n".join(
            str(dict(row))
            for table in (
                "arclink_llm_router_keys",
                "arclink_llm_usage_events",
                "arclink_llm_budget_reservations",
                "arclink_events",
                "arclink_deployments",
            )
            for row in conn.execute(f"SELECT * FROM {table}").fetchall()
        )
        expect(raw_key not in serialized_rows, serialized_rows)

        record = control.list_llm_router_keys_for_deployment(conn, "dep_1")[0]
        control.revoke_llm_router_key(conn, record["key_id"], actor_id="test", reason="unit")
        expect(control.verify_llm_router_key(conn, raw_key) is None, "revoked key verified")
        rotated = control.rotate_llm_router_key(
            conn,
            old_key_id=record["key_id"],
            deployment_id="dep_1",
            user_id="user_1",
            secret_ref="secret://arclink/llm-router/dep_1/api-key",
        )
        expect(rotated["raw_key"].startswith("acpod_live_"), str(rotated))
        expect(control.verify_llm_router_key(conn, rotated["raw_key"]) is not None, "rotated key did not verify")
        conn.close()
    finally:
        tmp.cleanup()
    print("PASS test_router_keys_verify_fail_closed_and_do_not_store_raw_material")


def test_router_auth_rejects_missing_invalid_and_suspended_keys() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path, status="suspended")
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
            }
        )
        missing = client.get("/v1/models")
        expect(missing.status_code == 401, missing.text)
        malformed = client.get("/v1/models", headers={"Authorization": "Basic nope"})
        expect(malformed.status_code == 401, malformed.text)
        invalid = client.get("/v1/models", headers={"Authorization": "Bearer acpod_live_12345678_not_real_secret_not_real_secret_not_real_secret"})
        expect(invalid.status_code == 401, invalid.text)
        suspended = client.get("/v1/models", headers={"Authorization": f"Bearer {raw_key}"})
        expect(suspended.status_code == 401, suspended.text)
    finally:
        tmp.cleanup()
    print("PASS test_router_auth_rejects_missing_invalid_and_suspended_keys")


def test_chat_streaming_passes_chunks_and_records_provider_usage() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path)
        marks: list[str] = []
        chunks = [
            b'data: {"id":"chunk_1","choices":[{"delta":{"content":"hel"}}]}\n\n',
            b'data: {"id":"chunk_1","choices":[{"delta":{"content":"lo"}}],"usage":{"prompt_tokens":4,"completion_tokens":2,"total_tokens":6}}\n\n',
            b"data: [DONE]\n\n",
        ]
        upstream = fake_stream_transport(chunks, marks)
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "1000",
            },
            upstream_transport=upstream,
        )
        with client.stream(
            "POST",
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "stream": True, "messages": [{"role": "user", "content": "hello"}]},
        ) as response:
            body = b"".join(response.iter_bytes())
        expect(response.status_code == 200, body.decode("utf-8"))
        expect(body == b"".join(chunks), body.decode("utf-8"))
        expect(marks == ["yield:0", "yield:1", "yield:2"], str(marks))
        expect(upstream.requests[0]["payload"]["stream_options"]["include_usage"] is True, str(upstream.requests))  # type: ignore[attr-defined]
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        usage = conn.execute("SELECT * FROM arclink_llm_usage_events").fetchone()
        open_reservations = conn.execute(
            "SELECT COUNT(*) AS count FROM arclink_llm_budget_reservations WHERE status = 'reserved'"
        ).fetchone()["count"]
        conn.close()
        expect(open_reservations == 0, f"expected no leaked reservations, found {open_reservations}")
        expect(usage["status"] == "succeeded" and usage["stream"] == 1, dict(usage))
        expect(usage["input_tokens"] == 4 and usage["output_tokens"] == 2 and usage["source_kind"] == "provider_usage", dict(usage))
    finally:
        tmp.cleanup()
    print("PASS test_chat_streaming_passes_chunks_and_records_provider_usage")


def test_chat_upstream_errors_are_redacted_and_do_not_leak_reservations() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path)
        upstream = fake_upstream_transport(
            status_code=500,
            content="provider exploded api_key=cpk_live_SECRETSECRETSECRETSECRET and token=sk-proj-abcdefghijklmnopqrstuvwxyz",
        )
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "1000",
            },
            upstream_transport=upstream,
        )
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "messages": [{"role": "user", "content": "do not store me"}]},
        )
        expect(response.status_code == 502, response.text)
        expect("cpk_live" not in response.text and "sk-proj" not in response.text, response.text)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        usage = conn.execute("SELECT * FROM arclink_llm_usage_events").fetchone()
        open_reservations = conn.execute(
            "SELECT COUNT(*) AS count FROM arclink_llm_budget_reservations WHERE status = 'reserved'"
        ).fetchone()["count"]
        serialized = "\n".join(
            str(dict(row))
            for table in ("arclink_llm_usage_events", "arclink_llm_budget_reservations", "arclink_events", "arclink_deployments")
            for row in conn.execute(f"SELECT * FROM {table}").fetchall()
        )
        conn.close()
        expect(open_reservations == 0, f"expected no leaked reservations, found {open_reservations}")
        expect(usage["status"] == "failed", dict(usage))
        expect("cpk_live" not in usage["error_summary"] and "sk-proj" not in usage["error_summary"], dict(usage))
        expect("do not store me" not in serialized, serialized)
    finally:
        tmp.cleanup()
    print("PASS test_chat_upstream_errors_are_redacted_and_do_not_leak_reservations")


def test_chat_partial_stream_failure_settles_without_prompt_or_secret_storage() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path)
        first_chunk = b'data: {"id":"chunk_1","choices":[{"delta":{"content":"partial"}}]}\n\n'
        upstream = fake_broken_stream_transport(
            first_chunk,
            "socket reset while using api_key=cpk_live_SECRETSECRETSECRETSECRET",
        )
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "1000",
            },
            upstream_transport=upstream,
        )
        with client.stream(
            "POST",
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "stream": True, "messages": [{"role": "user", "content": "store neither prompt nor chunk"}]},
        ) as response:
            body = b"".join(response.iter_bytes())
        text = body.decode("utf-8")
        expect(response.status_code == 200, text)
        expect(first_chunk in body, text)
        expect("upstream_unavailable" in text, text)
        expect("cpk_live" not in text, text)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        usage = conn.execute("SELECT * FROM arclink_llm_usage_events").fetchone()
        open_reservations = conn.execute(
            "SELECT COUNT(*) AS count FROM arclink_llm_budget_reservations WHERE status = 'reserved'"
        ).fetchone()["count"]
        serialized = "\n".join(
            str(dict(row))
            for table in ("arclink_llm_usage_events", "arclink_llm_budget_reservations", "arclink_events", "arclink_deployments")
            for row in conn.execute(f"SELECT * FROM {table}").fetchall()
        )
        conn.close()
        expect(open_reservations == 0, f"expected no leaked reservations, found {open_reservations}")
        expect(usage["status"] == "failed" and usage["stream"] == 1, dict(usage))
        expect("cpk_live" not in usage["error_summary"], dict(usage))
        expect("store neither prompt nor chunk" not in serialized and "partial" not in serialized, serialized)
    finally:
        tmp.cleanup()
    print("PASS test_chat_partial_stream_failure_settles_without_prompt_or_secret_storage")


def main() -> int:
    test_health_reports_unhealthy_without_central_chutes_key()
    test_health_and_models_report_configured_state_without_exposing_key()
    test_chat_non_streaming_forwards_to_fake_upstream_and_records_usage()
    test_chat_preflight_rejects_invalid_model_and_size_limits()
    test_chat_preflight_enforces_budget_and_billing_fail_closed()
    test_chat_preflight_enforces_rate_limit_and_concurrency()
    test_router_keys_verify_fail_closed_and_do_not_store_raw_material()
    test_router_auth_rejects_missing_invalid_and_suspended_keys()
    test_chat_streaming_passes_chunks_and_records_provider_usage()
    test_chat_upstream_errors_are_redacted_and_do_not_leak_reservations()
    test_chat_partial_stream_failure_settles_without_prompt_or_secret_storage()
    print("PASS all 11 ArcLink LLM router tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
