#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from arclink_test_helpers import expect, load_module, use_explicit_local_session_hash_env


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


def fake_sequence_upstream_transport(responses: list[dict[str, Any]]):
    import httpx

    requests: list[dict[str, Any]] = []
    queue = list(responses)

    async def handler(request: httpx.Request) -> httpx.Response:
        raw_body = request.content
        try:
            body = json.loads(raw_body.decode("utf-8") if raw_body else "{}")
        except Exception:
            body = {}
        requests.append({"method": request.method, "url": str(request.url), "payload": body, "headers": dict(request.headers)})
        if not queue:
            return httpx.Response(500, content=b"unexpected extra upstream request")
        item = queue.pop(0)
        if item.get("raise"):
            raise httpx.ConnectError(str(item["raise"]), request=request)
        status_code = int(item.get("status_code", 200))
        if "content" in item:
            raw = item["content"]
            return httpx.Response(status_code, content=raw.encode("utf-8") if isinstance(raw, str) else raw)
        return httpx.Response(status_code, json=item.get("json") or {})

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


def fake_sequence_stream_transport(responses: list[dict[str, Any]], marks: list[str]):
    import httpx

    class ChunkStream(httpx.AsyncByteStream):
        def __init__(self, chunks: list[bytes]) -> None:
            self.chunks = chunks

        async def __aiter__(self):
            for idx, chunk in enumerate(self.chunks):
                marks.append(f"yield:{idx}")
                yield chunk

    requests: list[dict[str, Any]] = []
    queue = list(responses)

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append({"payload": json.loads(request.content.decode("utf-8"))})
        if not queue:
            return httpx.Response(500, content=b"unexpected extra upstream stream request")
        item = queue.pop(0)
        status_code = int(item.get("status_code", 200))
        if "chunks" in item:
            return httpx.Response(
                status_code,
                headers={"content-type": "text/event-stream"},
                stream=ChunkStream(list(item["chunks"])),
            )
        raw = item.get("content", b"")
        return httpx.Response(status_code, content=raw.encode("utf-8") if isinstance(raw, str) else raw)

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


class FixtureCatalogHttpClient:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.payload = payload
        self.headers: Mapping[str, str] = {}

    def get_json(self, path: str, *, headers: Mapping[str, str] | None = None) -> Mapping[str, Any]:
        expect(path == "/models", path)
        self.headers = dict(headers or {})
        return self.payload


def temp_router_db() -> tuple[tempfile.TemporaryDirectory[str], str]:
    # Establish the local-dev env so the router-key hash pepper (sec-C1) uses its
    # documented dev fallback instead of raising. Mirrors memory_db / the
    # session-pepper tests: a local-dev base domain + no REQUIRED flag.
    use_explicit_local_session_hash_env()
    tmp = tempfile.TemporaryDirectory()
    path = str(Path(tmp.name) / "router.sqlite3")
    conn = sqlite3.connect(path)
    conn.close()
    return tmp, path


def test_router_metadata_json_rejects_plaintext_secret_material() -> None:
    router = load_module("arclink_llm_router.py", "arclink_llm_router_metadata_secret_test")
    try:
        router._safe_metadata_json({"token": "sk-ant-router-secret-123456"})
    except ValueError as exc:
        expect("secret material" in str(exc), str(exc))
    else:
        raise AssertionError("expected router metadata JSON to reject plaintext secret material")
    print("PASS test_router_metadata_json_rejects_plaintext_secret_material")


def test_read_json_body_rejects_chunked_body_before_buffering_past_limit() -> None:
    import asyncio

    router = load_module("arclink_llm_router.py", "arclink_llm_router_body_limit_test")

    class ChunkedRequest:
        headers: dict[str, str] = {}

        async def stream(self):
            yield b'{"model"'
            yield b':"model-a"}'

    config = router.load_router_config(
        {
            "ARCLINK_DB_PATH": "/tmp/unused-arclink-router-body-limit.sqlite3",
            "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
            "ARCLINK_LLM_ROUTER_MAX_BODY_BYTES": "8",
        }
    )
    payload, error, body = asyncio.run(router._read_json_body(config, ChunkedRequest()))
    expect(payload is None, str(payload))
    expect(error is not None and error.status_code == 413, str(error))
    expect(len(body) <= 8, f"oversized body should not be fully buffered: {len(body)}")
    print("PASS test_read_json_body_rejects_chunked_body_before_buffering_past_limit")


class _BufferedStream:
    def __init__(self, response: Any) -> None:
        self.response = response

    def __enter__(self) -> Any:
        return self.response

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.response.close()


class _ASGITestClient:
    """Small sync wrapper around httpx.ASGITransport.

    FastAPI/Starlette's TestClient can hang indefinitely with some local
    dependency combinations. These tests need deterministic failure signals
    because they cover billing gates and prompt-secrecy assumptions.
    """

    def __init__(self, app: Any) -> None:
        self.app = app
        self._closed = False

    def __enter__(self) -> "_ASGITestClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def close(self) -> None:
        self._closed = True

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def stream(self, method: str, path: str, **kwargs: Any) -> _BufferedStream:
        return _BufferedStream(self.request(method, path, **kwargs))

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        return self._run(self._request(method, path, **kwargs))

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        import httpx

        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.request(method, path, **kwargs)
            content = await response.aread()
            return httpx.Response(
                response.status_code,
                headers=response.headers,
                content=content,
                request=response.request,
                extensions=response.extensions,
            )

    @staticmethod
    def _run(awaitable: Any) -> Any:
        import asyncio

        return asyncio.run(awaitable)


def _client_for(env: dict[str, str], upstream_transport: Any | None = None) -> _ASGITestClient:
    try:
        import httpx  # noqa: F401
    except ModuleNotFoundError as exc:
        raise AssertionError("httpx/FastAPI test dependencies are missing; install requirements-dev.txt") from exc

    router = load_module("arclink_llm_router.py", "arclink_llm_router_test")
    clean_env = {"ARCLINK_LLM_ROUTER_REFRESH_MODEL_CATALOG_ON_STARTUP": "0", **env}
    config = router.load_router_config(clean_env)
    return _ASGITestClient(router.create_app(config, upstream_transport=upstream_transport))


def _seed_router_key(
    db_path: str,
    *,
    status: str = "active",
    deployment_status: str = "active",
    entitlement_state: str = "paid",
    subscription_status: str = "",
    deployment_metadata: Mapping[str, Any] | None = None,
    allowed_models: list[str] | None = None,
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
        status=deployment_status,
        metadata=dict(deployment_metadata or {}),
    )
    raw_key = control.generate_llm_router_raw_key()
    # ``None`` -> the default 2-model key allow-list; an explicit ``[]`` -> a key
    # with NO per-key allow-list (so the global / default-model path is exercised).
    key_allowed = ["model-a", "model-b"] if allowed_models is None else list(allowed_models)
    record = control.ensure_llm_router_key(
        conn,
        deployment_id="dep_1",
        user_id="user_1",
        secret_ref="secret://arclink/llm-router/dep_1/api-key",
        raw_key=raw_key,
        allowed_models=key_allowed,
    )
    if status != "active":
        conn.execute("UPDATE arclink_llm_router_keys SET status = ? WHERE key_id = ?", (status, record["key_id"]))
        conn.commit()
    conn.close()
    return raw_key


def _seed_operator_router_key(
    db_path: str,
    *,
    deployment_id: str = "ops-dep",
    user_id: str = "ops-user",
    used_cents: int = 5_000_000,
) -> str:
    control = load_module("arclink_control.py", "arclink_control_llm_router_operator_key_test")
    operator_agent = load_module("arclink_operator_agent.py", "arclink_operator_agent_llm_router_test")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    operator_agent.ensure_operator_agent_user(conn, user_id=user_id, email="ops@example.test")
    operator_agent.ensure_operator_agent_deployment(
        conn,
        user_id=user_id,
        deployment_id=deployment_id,
        prefix="ops-helm",
        base_domain="example.test",
        status="active",
        metadata={
            "chutes": {
                "secret_ref": f"secret://arclink/chutes/{deployment_id}",
                "used_cents": used_cents,
            }
        },
    )
    raw_key = control.generate_llm_router_raw_key()
    control.ensure_llm_router_key(
        conn,
        deployment_id=deployment_id,
        user_id=user_id,
        secret_ref=f"secret://arclink/llm-router/{deployment_id}/api-key",
        raw_key=raw_key,
        allowed_models=["model-a", "model-b"],
    )
    conn.close()
    return raw_key


def _seed_model_catalog(db_path: str) -> None:
    control = load_module("arclink_control.py", "arclink_control_llm_router_model_catalog_test")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        control.ensure_schema(conn)
        control.upsert_model_catalog(
            conn,
            provider="chutes",
            models={
                "moonshotai/Kimi-K2.6-TEE": {
                    "supports_tools": True,
                    "supports_reasoning": True,
                    "supports_structured_outputs": True,
                    "confidential_compute": True,
                    "input_cents_per_million": 95,
                    "output_cents_per_million": 400,
                },
                "moonshotai/Kimi-K2.7-TEE": {
                    "supports_tools": True,
                    "supports_reasoning": True,
                    "supports_structured_outputs": True,
                    "confidential_compute": True,
                    "input_cents_per_million": 100000,
                    "output_cents_per_million": 200000,
                },
            },
        )
        control.set_model_replacement(
            conn,
            provider="chutes",
            model_id="moonshotai/Kimi-K2.6-TEE",
            replacement_model_id="moonshotai/Kimi-K2.7-TEE",
        )
    finally:
        conn.close()


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


def test_upstream_pool_config_is_public_and_secret_safe() -> None:
    import asyncio

    tmp, db_path = temp_router_db()
    try:
        router = load_module("arclink_llm_router.py", "arclink_llm_router_pool_config_test")
        config = router.load_router_config(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_UPSTREAM_CONNECT_TIMEOUT_SECONDS": "7",
                "ARCLINK_LLM_ROUTER_UPSTREAM_READ_TIMEOUT_SECONDS": "301",
                "ARCLINK_LLM_ROUTER_UPSTREAM_WRITE_TIMEOUT_SECONDS": "31",
                "ARCLINK_LLM_ROUTER_UPSTREAM_POOL_TIMEOUT_SECONDS": "6",
                "ARCLINK_LLM_ROUTER_UPSTREAM_MAX_CONNECTIONS": "11",
                "ARCLINK_LLM_ROUTER_UPSTREAM_MAX_KEEPALIVE_CONNECTIONS": "22",
                "ARCLINK_LLM_ROUTER_UPSTREAM_KEEPALIVE_EXPIRY_SECONDS": "77",
                "ARCLINK_LLM_ROUTER_UPSTREAM_WARMUP_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_REFRESH_MODEL_CATALOG_ON_STARTUP": "0",
            }
        )
        app = router.create_app(config, upstream_transport=fake_upstream_transport())

        async def run_startup() -> None:
            for handler in getattr(app.router, "on_startup", []):
                result = handler()
                if hasattr(result, "__await__"):
                    await result

        async def run_shutdown() -> None:
            for handler in getattr(app.router, "on_shutdown", []):
                result = handler()
                if hasattr(result, "__await__"):
                    await result

        asyncio.run(run_startup())
        try:
            client = _ASGITestClient(app)
            health = client.get("/health")
            payload = health.json()
            expect(health.status_code == 200, health.text)
            pool = payload["upstream_pool"]
            expect(pool["connect_timeout_seconds"] == 7, str(pool))
            expect(pool["read_timeout_seconds"] == 301, str(pool))
            expect(pool["write_timeout_seconds"] == 31, str(pool))
            expect(pool["pool_timeout_seconds"] == 6, str(pool))
            expect(pool["max_connections"] == 11, str(pool))
            expect(pool["max_keepalive_connections"] == 11, str(pool))
            expect(pool["keepalive_expiry_seconds"] == 77, str(pool))
            expect(pool["warmup_enabled"] is True, str(pool))
            expect(payload["upstream_warmup"] == {"status": "skipped", "reason": "test_transport"}, str(payload))
            expect("cpk_test_router_secret_123" not in health.text, health.text)
        finally:
            asyncio.run(run_shutdown())
    finally:
        tmp.cleanup()
    print("PASS test_upstream_pool_config_is_public_and_secret_safe")


def test_chat_reuses_upstream_client_pool_within_event_loop() -> None:
    import asyncio

    import httpx

    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path)
        upstream = fake_upstream_transport()
        router = load_module("arclink_llm_router.py", "arclink_llm_router_pool_reuse_test")
        config = router.load_router_config(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "1000",
                "ARCLINK_LLM_ROUTER_REFRESH_MODEL_CATALOG_ON_STARTUP": "0",
            }
        )
        app = router.create_app(config, upstream_transport=upstream)

        async def exercise() -> None:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                first = await client.post(
                    "/v1/chat/completions",
                    headers={"Authorization": f"Bearer {raw_key}"},
                    json={"model": "model-a", "messages": [{"role": "user", "content": "hello"}]},
                )
                second = await client.post(
                    "/v1/chat/completions",
                    headers={"Authorization": f"Bearer {raw_key}"},
                    json={"model": "model-a", "messages": [{"role": "user", "content": "hello again"}]},
                )
            expect(first.status_code == 200, first.text)
            expect(second.status_code == 200, second.text)
            clients = dict(getattr(app.state, "router_upstream_clients", {}) or {})
            expect(len(clients) == 1, str(clients))
            pooled = next(iter(clients.values()))
            expect(not pooled.is_closed, "pooled upstream client should remain open for reuse")
            await router._close_upstream_clients(app.state)
            expect(pooled.is_closed, "pooled upstream client should close on shutdown")

        asyncio.run(exercise())
        expect(len(upstream.requests) == 2, str(upstream.requests))  # type: ignore[attr-defined]
    finally:
        tmp.cleanup()
    print("PASS test_chat_reuses_upstream_client_pool_within_event_loop")


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


def test_router_usage_settlement_error_releases_reserved_row() -> None:
    router = load_module("arclink_llm_router.py", "arclink_llm_router_settlement_release_test")
    control = load_module("arclink_control.py", "arclink_control_llm_router_settlement_release_test")
    tmp, db_path = temp_router_db()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            control.ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO arclink_llm_budget_reservations (
                  reservation_id, request_id, deployment_id, user_id, reserved_cents, status, created_at
                ) VALUES ('llmres_orphan', 'llmreq_orphan', 'dep_missing', 'user_missing', 3, 'reserved', '2026-05-16T00:00:00+00:00')
                """
            )
            conn.commit()
            config = router.load_router_config(
                {
                    "ARCLINK_DB_PATH": db_path,
                    "ARCLINK_LLM_ROUTER_ENABLED": "1",
                    "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                    "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "1000",
                }
            )
            router._record_router_usage(
                conn,
                config,
                reservation={
                    "reservation_id": "llmres_orphan",
                    "request_id": "llmreq_orphan",
                    "deployment_id": "dep_missing",
                    "user_id": "user_missing",
                    "reserved_cents": 3,
                    "requested_model": "model-a",
                    "upstream_model": "model-a",
                },
                auth_record={"deployment_id": "dep_missing", "user_id": "user_missing", "key_id": "llmk_missing"},
                model="model-a",
                stream=False,
                status="succeeded",
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
                source_kind="provider_usage",
            )
            reservation = conn.execute(
                "SELECT status, settled_cents, metadata_json FROM arclink_llm_budget_reservations WHERE reservation_id = 'llmres_orphan'"
            ).fetchone()
            open_reservations = conn.execute(
                "SELECT COUNT(*) AS count FROM arclink_llm_budget_reservations WHERE status = 'reserved'"
            ).fetchone()["count"]
            usage = conn.execute("SELECT status FROM arclink_llm_usage_events WHERE request_id = 'llmreq_orphan'").fetchone()
        finally:
            conn.close()
        reservation_meta = json.loads(reservation["metadata_json"])
        expect(open_reservations == 0, str(open_reservations))
        expect(reservation["status"] == "settled" and int(reservation["settled_cents"]) >= 0, dict(reservation))
        expect(reservation_meta["chutes_usage_recorded"] is False, str(reservation_meta))
        expect(usage["status"] == "succeeded", dict(usage))
    finally:
        tmp.cleanup()
    print("PASS test_router_usage_settlement_error_releases_reserved_row")


def test_chat_usage_queues_raven_low_fuel_notice_once() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(
            db_path,
            deployment_metadata={"chutes": {"monthly_budget_cents": 20, "used_cents": 15}},
        )
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                """
                INSERT INTO arclink_onboarding_sessions (
                  session_id, channel, channel_identity, status, user_id, deployment_id, created_at, updated_at
                ) VALUES ('onb_fuel', 'telegram', 'tg:12345', 'completed', 'user_1', 'dep_1', '2026-05-16T00:00:00+00:00', '2026-05-16T00:00:00+00:00')
                """
            )
            conn.commit()
        finally:
            conn.close()
        upstream = fake_upstream_transport(
            {
                "id": "chatcmpl_fuel",
                "object": "chat.completion",
                "model": "model-a",
                "choices": [{"message": {"role": "assistant", "content": "still flying"}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
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
        for _ in range(2):
            response = client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {raw_key}"},
                json={"model": "model-a", "messages": [{"role": "user", "content": "hello"}]},
            )
            expect(response.status_code == 200, response.text)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            notices = conn.execute(
                """
                SELECT target_kind, target_id, channel_kind, message, extra_json
                FROM notification_outbox
                WHERE target_kind = 'public-bot-user'
                """
            ).fetchall()
            events = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM arclink_events
                WHERE event_type = 'llm_router:arc_pod_fuel_notice_queued'
                """
            ).fetchone()["count"]
            metadata = json.loads(
                conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()[
                    "metadata_json"
                ]
            )
        finally:
            conn.close()
        expect(len(notices) == 1, str([dict(row) for row in notices]))
        notice = notices[0]
        expect(notice["channel_kind"] == "telegram" and notice["target_id"] == "tg:12345", str(dict(notice)))
        expect("ArcPod fuel is running low" in notice["message"], notice["message"])
        expect("Refuel ArcPod" in notice["extra_json"], notice["extra_json"])
        expect(events == 1, str(events))
        expect(metadata["chutes"]["used_cents"] == 17, str(metadata))
    finally:
        tmp.cleanup()
    print("PASS test_chat_usage_queues_raven_low_fuel_notice_once")


def test_low_fuel_notice_without_channel_does_not_poison_dedupe() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(
            db_path,
            deployment_metadata={"chutes": {"monthly_budget_cents": 20, "used_cents": 15}},
        )
        upstream = fake_upstream_transport(
            {
                "id": "chatcmpl_fuel",
                "object": "chat.completion",
                "model": "model-a",
                "choices": [{"message": {"role": "assistant", "content": "still flying"}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
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
        expect(response.status_code == 200, response.text)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            no_channel_notices = conn.execute("SELECT COUNT(*) AS count FROM notification_outbox").fetchone()["count"]
            no_channel_events = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM arclink_events
                WHERE event_type = 'llm_router:arc_pod_fuel_notice_queued'
                """
            ).fetchone()["count"]
            conn.execute(
                """
                INSERT INTO arclink_onboarding_sessions (
                  session_id, channel, channel_identity, status, user_id, deployment_id, created_at, updated_at
                ) VALUES ('onb_fuel_late', 'telegram', 'tg:67890', 'completed', 'user_1', 'dep_1', '2026-05-16T00:00:00+00:00', '2026-05-16T00:00:00+00:00')
                """
            )
            conn.commit()
        finally:
            conn.close()
        expect(no_channel_notices == 0, str(no_channel_notices))
        expect(no_channel_events == 0, str(no_channel_events))

        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "messages": [{"role": "user", "content": "hello again"}]},
        )
        expect(response.status_code == 200, response.text)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            notices = conn.execute(
                """
                SELECT target_kind, target_id, channel_kind, message
                FROM notification_outbox
                WHERE target_kind = 'public-bot-user'
                """
            ).fetchall()
            events = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM arclink_events
                WHERE event_type = 'llm_router:arc_pod_fuel_notice_queued'
                """
            ).fetchone()["count"]
        finally:
            conn.close()
        expect(len(notices) == 1, str([dict(row) for row in notices]))
        expect(notices[0]["target_id"] == "tg:67890", str(dict(notices[0])))
        expect("ArcPod fuel is running low" in notices[0]["message"], notices[0]["message"])
        expect(events == 1, str(events))
    finally:
        tmp.cleanup()
    print("PASS test_low_fuel_notice_without_channel_does_not_poison_dedupe")


def test_chat_uses_catalog_pricing_and_promotes_deprecated_models() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path, allowed_models=["moonshotai/Kimi-K2.6-TEE", "moonshotai/Kimi-K2.7-TEE"])
        _seed_model_catalog(db_path)
        upstream = fake_upstream_transport()
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "100000",
                "ARCLINK_LLM_ROUTER_CENTS_PER_MILLION_INPUT_TOKENS": "1",
                "ARCLINK_LLM_ROUTER_CENTS_PER_MILLION_OUTPUT_TOKENS": "1",
            },
            upstream_transport=upstream,
        )
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "moonshotai/Kimi-K2.6-TEE", "messages": [{"role": "user", "content": "hello"}]},
        )
        expect(response.status_code == 200, response.text)
        expect(upstream.requests[0]["payload"]["model"] == "moonshotai/Kimi-K2.7-TEE", str(upstream.requests))  # type: ignore[attr-defined]
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            usage = conn.execute("SELECT model, actual_cents FROM arclink_llm_usage_events").fetchone()
            expect(usage["model"] == "moonshotai/Kimi-K2.7-TEE", dict(usage))
            expect(int(usage["actual_cents"]) == 2, dict(usage))
        finally:
            conn.close()
    finally:
        tmp.cleanup()
    print("PASS test_chat_uses_catalog_pricing_and_promotes_deprecated_models")


def test_catalog_refreshes_and_promotes_newer_family_model() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path, allowed_models=["moonshotai/Kimi-K2.6-TEE", "moonshotai/Kimi-K2.7-TEE"])
        router = load_module("arclink_llm_router.py", "arclink_llm_router_startup_catalog_test")
        catalog_http = FixtureCatalogHttpClient(
            {
                "data": [
                    {
                        "id": "moonshotai/Kimi-K2.6-TEE",
                        "capabilities": {
                            "tools": True,
                            "reasoning": True,
                            "structured_outputs": True,
                            "confidential_compute": True,
                        },
                        "pricing": {"input": "$0.95 / 1M tokens", "output": "$4.00 / 1M tokens"},
                    },
                    {
                        "id": "moonshotai/Kimi-K2.7-TEE",
                        "capabilities": {
                            "tools": True,
                            "reasoning": True,
                            "structured_outputs": True,
                            "confidential_compute": True,
                        },
                        "input_cents_per_million": 100000,
                        "output_cents_per_million": 200000,
                    },
                ]
            }
        )
        upstream = fake_upstream_transport()
        config = router.load_router_config(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "100000",
                "ARCLINK_LLM_ROUTER_ALLOWED_MODELS": "moonshotai/Kimi-K2.6-TEE",
                "ARCLINK_LLM_ROUTER_REFRESH_MODEL_CATALOG_ON_STARTUP": "1",
            }
        )
        app = router.create_app(config, upstream_transport=upstream, catalog_http_client=catalog_http)
        app.state.router_catalog_refresh = router._refresh_model_catalog_once(config, http_client=catalog_http)
        with _ASGITestClient(app) as client:
            health = client.get("/health")
            expect(health.status_code == 200, health.text)
            expect(health.json()["model_catalog_refresh"]["status"] == "ok", health.text)
            response = client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {raw_key}"},
                json={"model": "moonshotai/Kimi-K2.6-TEE", "messages": [{"role": "user", "content": "hello"}]},
            )
        expect(response.status_code == 200, response.text)
        expect(catalog_http.headers == {"Authorization": "Bearer cpk_test_router_secret_123"}, str(catalog_http.headers))
        expect(upstream.requests[0]["payload"]["model"] == "moonshotai/Kimi-K2.7-TEE", str(upstream.requests))  # type: ignore[attr-defined]
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            usage = conn.execute("SELECT model, actual_cents FROM arclink_llm_usage_events").fetchone()
            latest = conn.execute(
                "SELECT status FROM arclink_model_catalog WHERE provider = 'chutes' AND model_id = 'moonshotai/Kimi-K2.7-TEE'"
            ).fetchone()
            expect(latest["status"] == "active", dict(latest))
            expect(usage["model"] == "moonshotai/Kimi-K2.7-TEE", dict(usage))
            expect(int(usage["actual_cents"]) == 2, dict(usage))
        finally:
            conn.close()
    finally:
        tmp.cleanup()
    print("PASS test_catalog_refreshes_and_promotes_newer_family_model")


def test_startup_refresh_empty_response_does_not_empty_catalog() -> None:
    # BUG #2: the startup catalog refresh writes whatever /models returns with
    # mark_missing_unavailable. An empty (or near-empty) successful response must
    # NOT mark every active row unavailable -- that would silently empty the
    # DB-backed allow-list with no notice. Last-known-good must be preserved.
    tmp, db_path = temp_router_db()
    try:
        _seed_model_catalog(db_path)
        control = load_module("arclink_control.py", "arclink_control_router_startup_lkg_test")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            baseline = [
                str(row["model_id"])
                for row in conn.execute(
                    "SELECT model_id FROM arclink_model_catalog "
                    "WHERE provider='chutes' AND status='active' ORDER BY model_id"
                ).fetchall()
            ]
        finally:
            conn.close()
        expect(len(baseline) >= 1, str(baseline))

        router = load_module("arclink_llm_router.py", "arclink_llm_router_startup_lkg_test")
        config = router.load_router_config(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_REFRESH_MODEL_CATALOG_ON_STARTUP": "1",
                "ARCLINK_LLM_ROUTER_MARK_MISSING_MODELS_UNAVAILABLE": "1",
            }
        )
        # A successful-but-empty /models response (data: []).
        empty_http = FixtureCatalogHttpClient({"data": []})
        result = router._refresh_model_catalog_once(config, http_client=empty_http)
        expect(result["status"] == "skipped", str(result))
        expect(result.get("kept_last_known_good") is True, str(result))

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            after = [
                str(row["model_id"])
                for row in conn.execute(
                    "SELECT model_id FROM arclink_model_catalog "
                    "WHERE provider='chutes' AND status='active' ORDER BY model_id"
                ).fetchall()
            ]
        finally:
            conn.close()
        expect(after == baseline, f"empty refresh must not empty the catalog: {after} != {baseline}")
    finally:
        tmp.cleanup()
    print("PASS test_startup_refresh_empty_response_does_not_empty_catalog")


def test_startup_refresh_non_tee_heavy_response_keeps_tee_allow_list() -> None:
    # FIX D: a successful /models response that is HEAVY on non-TEE models but
    # carries ZERO -TEE models must NOT empty the router's -TEE allow-list.
    # The old startup path counted ALL Chutes models for its floor/proportional
    # guard, so such a response cleared the guard, then mark_missing_unavailable
    # flipped every active -TEE row (GLM/Kimi) to unavailable. The fix makes the
    # startup refresh purely additive; -TEE removal is owned by the guarded,
    # operator-notifying hourly sync worker.
    tmp, db_path = temp_router_db()
    try:
        control = load_module("arclink_control.py", "arclink_control_router_startup_tee_light_test")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            control.ensure_schema(conn)
            # Seed the production -TEE allow-list (GLM + Kimi) as active.
            control.upsert_model_catalog(
                conn,
                provider="chutes",
                models={
                    "zai-org/GLM-5.2-TEE": {"confidential_compute": True},
                    "moonshotai/Kimi-K2.6-TEE": {"confidential_compute": True},
                },
            )
            baseline = [
                str(row["model_id"])
                for row in conn.execute(
                    "SELECT model_id FROM arclink_model_catalog "
                    "WHERE provider='chutes' AND status='active' AND model_id LIKE '%-TEE' ORDER BY model_id"
                ).fetchall()
            ]
        finally:
            conn.close()
        expect(baseline == ["moonshotai/Kimi-K2.6-TEE", "zai-org/GLM-5.2-TEE"], str(baseline))

        router = load_module("arclink_llm_router.py", "arclink_llm_router_startup_tee_light_test")
        config = router.load_router_config(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_REFRESH_MODEL_CATALOG_ON_STARTUP": "1",
                "ARCLINK_LLM_ROUTER_MARK_MISSING_MODELS_UNAVAILABLE": "1",
            }
        )
        # Heavy on non-TEE models (clears any all-models floor), zero -TEE models.
        non_tee_heavy = FixtureCatalogHttpClient(
            {"data": [{"id": f"vendor/plain-model-{i:02d}"} for i in range(8)]}
        )
        result = router._refresh_model_catalog_once(config, http_client=non_tee_heavy)
        expect(result["status"] == "ok", str(result))
        expect(result["mark_missing_unavailable"] is False, str(result))

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            after_tee = [
                str(row["model_id"])
                for row in conn.execute(
                    "SELECT model_id FROM arclink_model_catalog "
                    "WHERE provider='chutes' AND status='active' AND model_id LIKE '%-TEE' ORDER BY model_id"
                ).fetchall()
            ]
        finally:
            conn.close()
        expect(after_tee == baseline, f"-TEE allow-list must survive a TEE-light startup: {after_tee} != {baseline}")
    finally:
        tmp.cleanup()
    print("PASS test_startup_refresh_non_tee_heavy_response_keeps_tee_allow_list")


def test_chat_promotes_missing_requested_model_to_latest_same_family() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path, allowed_models=["moonshotai/Kimi-K2.6-TEE", "moonshotai/Kimi-K2.7-TEE"])
        control = load_module("arclink_control.py", "arclink_control_llm_router_latest_only_catalog_test")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            control.ensure_schema(conn)
            control.upsert_model_catalog(
                conn,
                provider="chutes",
                models={
                    "moonshotai/Kimi-K2.7-TEE": {
                        "supports_tools": True,
                        "supports_reasoning": True,
                        "supports_structured_outputs": True,
                        "confidential_compute": True,
                        "input_cents_per_million": 100000,
                        "output_cents_per_million": 200000,
                    }
                },
            )
        finally:
            conn.close()
        upstream = fake_upstream_transport()
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "100000",
            },
            upstream_transport=upstream,
        )
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "moonshotai/Kimi-K2.6-TEE", "messages": [{"role": "user", "content": "hello"}]},
        )
        expect(response.status_code == 200, response.text)
        expect(upstream.requests[0]["payload"]["model"] == "moonshotai/Kimi-K2.7-TEE", str(upstream.requests))  # type: ignore[attr-defined]
    finally:
        tmp.cleanup()
    print("PASS test_chat_promotes_missing_requested_model_to_latest_same_family")


def test_key_allowlist_blocks_global_default_replacement_and_fallback_escape() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path, allowed_models=["model-a"])
        upstream = fake_upstream_transport()
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_DEFAULT_MODEL": "model-default",
                "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "1000",
            },
            upstream_transport=upstream,
        )
        default_escape = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-default", "messages": [{"role": "user", "content": "hello"}]},
        )
        expect(default_escape.status_code == 403, default_escape.text)
        expect(default_escape.json()["error"]["code"] == "model_not_allowed", default_escape.text)
        expect(len(upstream.requests) == 0, str(upstream.requests))  # type: ignore[attr-defined]
    finally:
        tmp.cleanup()

    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path, allowed_models=["moonshotai/Kimi-K2.6-TEE"])
        _seed_model_catalog(db_path)
        upstream = fake_upstream_transport()
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "100000",
            },
            upstream_transport=upstream,
        )
        replacement_escape = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "moonshotai/Kimi-K2.6-TEE", "messages": [{"role": "user", "content": "hello"}]},
        )
        expect(replacement_escape.status_code == 403, replacement_escape.text)
        expect(replacement_escape.json()["error"]["code"] == "model_not_allowed", replacement_escape.text)
        expect(len(upstream.requests) == 0, str(upstream.requests))  # type: ignore[attr-defined]
    finally:
        tmp.cleanup()

    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path, allowed_models=["model-a"])
        upstream = fake_upstream_transport()
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "1000",
                "ARCLINK_LLM_ROUTER_FALLBACK_MODELS": "model-b",
            },
            upstream_transport=upstream,
        )
        fallback_escape = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "messages": [{"role": "user", "content": "hello"}]},
        )
        expect(fallback_escape.status_code == 403, fallback_escape.text)
        expect(fallback_escape.json()["error"]["code"] == "model_not_allowed", fallback_escape.text)
        expect(len(upstream.requests) == 0, str(upstream.requests))  # type: ignore[attr-defined]
    finally:
        tmp.cleanup()
    print("PASS test_key_allowlist_blocks_global_default_replacement_and_fallback_escape")


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


def test_global_allowlist_reflects_synced_tee_catalog_without_restart() -> None:
    # With an empty per-key allow-list the router falls back to the global
    # allow-list, which is now sourced from the synced -TEE catalog rows
    # (arclink_model_catalog). Updating those rows takes effect on the next
    # request without recreating/restarting the router.
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path)
        control = load_module("arclink_control.py", "arclink_control_global_synced_allowlist_test")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            control.ensure_schema(conn)
            # Mirror production: per-key allow-lists cleared to [] so every key
            # falls back to the global (now catalog-sourced) allow-list.
            conn.execute("UPDATE arclink_llm_router_keys SET allowed_models_json = '[]'")
            conn.commit()
            control.upsert_model_catalog(
                conn,
                provider="chutes",
                models={
                    "moonshotai/Kimi-K2.6-TEE": {"confidential_compute": True},
                    "zai-org/GLM-5.1-TEE": {"confidential_compute": True},
                },
            )
        finally:
            conn.close()
        upstream = fake_upstream_transport()
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                # Static env allow-list is deliberately a *different* model so we
                # prove the catalog (not env) is what is being enforced.
                "ARCLINK_LLM_ROUTER_ALLOWED_MODELS": "env-fallback-only-model",
                "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "100000",
            },
            upstream_transport=upstream,
        )
        # /v1/models lists the synced -TEE set, not the env list.
        models_resp = client.get("/v1/models", headers={"Authorization": f"Bearer {raw_key}"})
        expect(models_resp.status_code == 200, models_resp.text)
        listed = {entry["id"] for entry in models_resp.json()["data"]}
        expect(listed == {"moonshotai/Kimi-K2.6-TEE", "zai-org/GLM-5.1-TEE"}, str(listed))

        # A synced -TEE model is allowed through the chat path.
        allowed = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "moonshotai/Kimi-K2.6-TEE", "messages": [{"role": "user", "content": "hi"}]},
        )
        expect(allowed.status_code == 200, allowed.text)

        # The static env model is NOT in the synced catalog, so it is rejected.
        blocked = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "env-fallback-only-model", "messages": [{"role": "user", "content": "hi"}]},
        )
        expect(blocked.status_code == 403, blocked.text)
        expect(blocked.json()["error"]["code"] == "model_not_allowed", blocked.text)

        # Simulate a live sync that drops one model: the router reflects it on
        # the next request, no restart.
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                "UPDATE arclink_model_catalog SET status='unavailable' WHERE model_id=?",
                ("zai-org/GLM-5.1-TEE",),
            )
            conn.commit()
        finally:
            conn.close()
        dropped = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "zai-org/GLM-5.1-TEE", "messages": [{"role": "user", "content": "hi"}]},
        )
        expect(dropped.status_code == 403, dropped.text)
    finally:
        tmp.cleanup()
    print("PASS test_global_allowlist_reflects_synced_tee_catalog_without_restart")


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

    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(
            db_path,
            deployment_status="teardown_requested",
            deployment_metadata={"chutes": {"monthly_budget_cents": 1000, "used_cents": 10}},
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
        retired = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "messages": [{"role": "user", "content": "hello"}]},
        )
        expect(retired.status_code == 403, retired.text)
        expect(retired.json()["error"]["code"] == "suspended", retired.text)
        expect("suspended" in retired.json()["error"]["message"].lower(), retired.text)
        expect(len(upstream.requests) == 0, str(upstream.requests))  # type: ignore[attr-defined]
    finally:
        tmp.cleanup()
    print("PASS test_chat_preflight_enforces_budget_and_billing_fail_closed")


def test_chat_operator_observe_unlimited_is_server_authorized_and_metered() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_operator_router_key(db_path, used_cents=5_000_000)
        upstream = fake_upstream_transport(
            {
                "id": "chatcmpl_operator",
                "object": "chat.completion",
                "model": "model-a",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            }
        )
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
            },
            upstream_transport=upstream,
        )
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "messages": [{"role": "user", "content": "operator repair check"}]},
        )
        expect(response.status_code == 200, response.text)
        expect(len(upstream.requests) == 1, str(upstream.requests))  # type: ignore[attr-defined]
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id = 'ops-dep'").fetchone()
            metadata = json.loads(row["metadata_json"])
            demotions = conn.execute(
                "SELECT COUNT(*) AS count FROM arclink_events WHERE event_type = 'llm_router:budget_policy_demoted'"
            ).fetchone()["count"]
        finally:
            conn.close()
        expect(metadata["chutes"]["budget_policy"] == "observe_only_unlimited", str(metadata))
        expect(metadata["chutes"]["used_cents"] >= 5_000_000, str(metadata))
        expect(demotions == 0, str(demotions))
    finally:
        tmp.cleanup()
    print("PASS test_chat_operator_observe_unlimited_is_server_authorized_and_metered")


def test_chat_spoofed_observe_unlimited_demotes_to_capped_lane_and_records_evidence() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(
            db_path,
            deployment_metadata={
                "chutes": {
                    "secret_ref": "secret://arclink/chutes/dep_1",
                    "monthly_budget_cents": 0,
                    "used_cents": 0,
                    "budget_policy": "observe_only_unlimited",
                }
            },
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
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "messages": [{"role": "user", "content": "hello spoof"}]},
        )
        expect(response.status_code == 402, response.text)
        expect(response.json()["error"]["code"] == "budget_unconfigured", response.text)
        expect(len(upstream.requests) == 0, str(upstream.requests))  # type: ignore[attr-defined]
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            event = conn.execute(
                """
                SELECT subject_kind, subject_id, event_type, metadata_json
                FROM arclink_events
                WHERE event_type = 'llm_router:budget_policy_demoted'
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).fetchone()
            reservations = conn.execute("SELECT COUNT(*) AS count FROM arclink_llm_budget_reservations").fetchone()["count"]
            usage = conn.execute("SELECT COUNT(*) AS count FROM arclink_llm_usage_events").fetchone()["count"]
        finally:
            conn.close()
        expect(event is not None, "expected a budget policy demotion event")
        event_meta = json.loads(event["metadata_json"])
        expect(event["subject_kind"] == "deployment" and event["subject_id"] == "dep_1", str(dict(event)))
        expect(event_meta["authorized"] is False, str(event_meta))
        expect(event_meta["budget_policy"] == "observe_only_unlimited", str(event_meta))
        event_text = json.dumps(event_meta, sort_keys=True)
        expect("secret://" not in event_text and "hello spoof" not in event_text, event_text)
        expect(reservations == 0 and usage == 0, f"unexpected router side effects: reservations={reservations} usage={usage}")
    finally:
        tmp.cleanup()
    print("PASS test_chat_spoofed_observe_unlimited_demotes_to_capped_lane_and_records_evidence")


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
        # A genuinely in-flight reservation (fresh created_at) must hold the
        # concurrency slot. A current timestamp keeps it well inside the C2 TTL
        # reaper window so the reaper leaves it untouched.
        fresh_created_at = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        )
        conn.execute(
            """
            INSERT INTO arclink_llm_budget_reservations (
              reservation_id, request_id, deployment_id, user_id, reserved_cents, status, created_at
            ) VALUES ('llmres_existing', 'llmreq_existing', 'dep_1', 'user_1', 1, 'reserved', ?)
            """,
            (fresh_created_at,),
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
        row = conn.execute("SELECT key_id, key_hash FROM arclink_llm_router_keys WHERE deployment_id = 'dep_1'").fetchone()
        legacy_hash = control.hash_token(raw_key)
        expect(str(row["key_hash"]).startswith("hmac-sha256$"), str(dict(row)))
        expect(row["key_hash"] != legacy_hash, str(dict(row)))

        conn.execute("UPDATE arclink_llm_router_keys SET key_hash = ? WHERE key_id = ?", (legacy_hash, row["key_id"]))
        conn.commit()
        migrated = control.verify_llm_router_key(conn, raw_key)
        expect(migrated is not None, "legacy key hash did not verify")
        migrated_hash = conn.execute("SELECT key_hash FROM arclink_llm_router_keys WHERE key_id = ?", (row["key_id"],)).fetchone()[
            "key_hash"
        ]
        expect(str(migrated_hash).startswith("hmac-sha256$") and migrated_hash != legacy_hash, str(migrated_hash))

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


def test_chat_retries_configured_fallback_model_after_retryable_upstream_error() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path, allowed_models=["model-a", "model-b"])
        upstream = fake_sequence_upstream_transport(
            [
                {"status_code": 429, "content": "rate limited token=sk-proj-abcdefghijklmnopqrstuvwxyz"},
                {
                    "status_code": 200,
                    "json": {
                        "id": "chatcmpl_fallback",
                        "object": "chat.completion",
                        "model": "model-b",
                        "choices": [{"message": {"role": "assistant", "content": "fallback ok"}}],
                        "usage": {"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13},
                    },
                },
            ]
        )
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "1000",
                "ARCLINK_LLM_ROUTER_FALLBACK_MODELS": "model-b",
                "ARCLINK_LLM_ROUTER_FALLBACK_STATUS_CODES": "429",
            },
            upstream_transport=upstream,
        )
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "messages": [{"role": "user", "content": "do not store fallback prompt"}]},
        )
        payload = response.json()
        expect(response.status_code == 200, str(payload))
        expect(len(upstream.requests) == 2, str(upstream.requests))  # type: ignore[attr-defined]
        expect(upstream.requests[0]["payload"]["model"] == "model-a", str(upstream.requests))  # type: ignore[attr-defined]
        expect(upstream.requests[1]["payload"]["model"] == "model-b", str(upstream.requests))  # type: ignore[attr-defined]
        router_meta = payload.get("arclink_router") or {}
        expect(router_meta.get("fallback_used") is True, str(router_meta))
        expect(router_meta.get("primary_model") == "model-a" and router_meta.get("upstream_model") == "model-b", str(router_meta))
        expect("sk-proj" not in response.text and "do not store fallback prompt" not in response.text, response.text)
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
        expect(usage["status"] == "succeeded" and usage["model"] == "model-b", dict(usage))
        expect("do not store fallback prompt" not in serialized and "sk-proj" not in serialized, serialized)
    finally:
        tmp.cleanup()
    print("PASS test_chat_retries_configured_fallback_model_after_retryable_upstream_error")


def test_chat_fallback_uses_final_model_pricing_and_sanitized_attempt_audit() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path, allowed_models=["model-a", "model-b"])
        control = load_module("arclink_control.py", "arclink_control_llm_router_fallback_pricing_test")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            control.ensure_schema(conn)
            control.upsert_model_catalog(
                conn,
                provider="chutes",
                models={
                    "model-a": {
                        "input_cents_per_million": 1,
                        "output_cents_per_million": 1,
                    },
                    "model-b": {
                        "input_cents_per_million": 100000,
                        "output_cents_per_million": 200000,
                    },
                },
            )
        finally:
            conn.close()
        upstream = fake_sequence_upstream_transport(
            [
                {"status_code": 429, "content": "rate limited token=sk-proj-abcdefghijklmnopqrstuvwxyz"},
                {
                    "status_code": 200,
                    "json": {
                        "id": "chatcmpl_cost_fallback",
                        "object": "chat.completion",
                        "model": "model-b",
                        "choices": [{"message": {"role": "assistant", "content": "fallback ok"}}],
                        "usage": {"prompt_tokens": 1000, "completion_tokens": 1000, "total_tokens": 2000},
                    },
                },
            ]
        )
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "100000",
                "ARCLINK_LLM_ROUTER_FALLBACK_MODELS": "model-b",
                "ARCLINK_LLM_ROUTER_FALLBACK_STATUS_CODES": "429",
            },
            upstream_transport=upstream,
        )
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "messages": [{"role": "user", "content": "do not store cost fallback prompt"}]},
        )
        expect(response.status_code == 200, response.text)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            usage = conn.execute("SELECT model, actual_cents, metadata_json FROM arclink_llm_usage_events").fetchone()
            reservation = conn.execute("SELECT reserved_cents, settled_cents, metadata_json FROM arclink_llm_budget_reservations").fetchone()
            event = conn.execute(
                "SELECT metadata_json FROM arclink_events WHERE event_type = 'llm_router:fallback_attempt'"
            ).fetchone()
            serialized = "\n".join(
                str(dict(row))
                for table in ("arclink_llm_usage_events", "arclink_llm_budget_reservations", "arclink_events", "arclink_deployments")
                for row in conn.execute(f"SELECT * FROM {table}").fetchall()
            )
        finally:
            conn.close()
        usage_meta = json.loads(usage["metadata_json"])
        reservation_meta = json.loads(reservation["metadata_json"])
        event_meta = json.loads(event["metadata_json"])
        expect(usage["model"] == "model-b" and int(usage["actual_cents"]) == 300, dict(usage))
        expect(usage_meta["requested_model"] == "model-a" and usage_meta["primary_model"] == "model-a", str(usage_meta))
        expect(usage_meta["usage_model"] == "model-b" and usage_meta["fallback_used"] is True, str(usage_meta))
        expect(usage_meta["reservation_pricing_model"] == "model-b", str(usage_meta))
        expect(usage_meta["usage_pricing_model"] == "model-b", str(usage_meta))
        expect(reservation_meta["requested_model"] == "model-a" and reservation_meta["final_model"] == "model-b", str(reservation_meta))
        expect(reservation["reserved_cents"] > 1 and reservation["settled_cents"] == 300, dict(reservation))
        expect(reservation_meta["reservation_pricing_model"] == "model-b", str(reservation_meta))
        expect(reservation_meta["fallback_used"] is True and reservation_meta["fallback_pricing_reserved"] is True, str(reservation_meta))
        expect(reservation_meta["pricing_adjusted_at_settlement"] is False, str(reservation_meta))
        expect(event_meta["attempted_model"] == "model-a" and event_meta["next_model"] == "model-b", str(event_meta))
        expect(event_meta["status_code"] == 429 and event_meta["outcome"] == "retrying", str(event_meta))
        expect("sk-proj" not in serialized and "do not store cost fallback prompt" not in serialized, serialized)
    finally:
        tmp.cleanup()
    print("PASS test_chat_fallback_uses_final_model_pricing_and_sanitized_attempt_audit")


def test_provider_side_fallback_csv_default_model_is_allowed_as_single_model_string() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path, allowed_models=["model-a,model-b"])
        upstream = fake_upstream_transport(
            {
                "id": "chatcmpl_provider_side_fallback",
                "object": "chat.completion",
                "model": "model-a,model-b",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4},
            }
        )
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_DEFAULT_MODEL": "model-a,model-b",
                "ARCLINK_LLM_ROUTER_ALLOWED_MODELS": "model-a,model-b",
                "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "1000",
            },
            upstream_transport=upstream,
        )
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a,model-b", "messages": [{"role": "user", "content": "hello"}]},
        )
        expect(response.status_code == 200, response.text)
        expect(upstream.requests[0]["payload"]["model"] == "model-a,model-b", str(upstream.requests))  # type: ignore[attr-defined]
    finally:
        tmp.cleanup()
    print("PASS test_provider_side_fallback_csv_default_model_is_allowed_as_single_model_string")


def test_chat_streaming_retries_pre_stream_fallback_and_records_metadata() -> None:
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(db_path, allowed_models=["model-a", "model-b"])
        marks: list[str] = []
        chunks = [
            b'data: {"id":"chunk_fallback","choices":[{"delta":{"content":"hel"}}]}\n\n',
            b'data: {"id":"chunk_fallback","choices":[{"delta":{"content":"lo"}}],"usage":{"prompt_tokens":6,"completion_tokens":2,"total_tokens":8}}\n\n',
            b"data: [DONE]\n\n",
        ]
        upstream = fake_sequence_stream_transport(
            [
                {"status_code": 429, "content": "stream overloaded api_key=cpk_live_SECRETSECRETSECRETSECRET"},
                {"status_code": 200, "chunks": chunks},
            ],
            marks,
        )
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS": "1000",
                "ARCLINK_LLM_ROUTER_FALLBACK_MODELS": "model-b",
                "ARCLINK_LLM_ROUTER_FALLBACK_STATUS_CODES": "429",
            },
            upstream_transport=upstream,
        )
        with client.stream(
            "POST",
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "stream": True, "messages": [{"role": "user", "content": "do not store streaming prompt"}]},
        ) as response:
            body = b"".join(response.iter_bytes())
        text = body.decode("utf-8")
        expect(response.status_code == 200, text)
        expect(len(upstream.requests) == 2, str(upstream.requests))  # type: ignore[attr-defined]
        expect(upstream.requests[0]["payload"]["model"] == "model-a", str(upstream.requests))  # type: ignore[attr-defined]
        expect(upstream.requests[1]["payload"]["model"] == "model-b", str(upstream.requests))  # type: ignore[attr-defined]
        expect('"arclink_router"' in text and '"fallback_used":true' in text.replace(" ", ""), text)
        expect(b"".join(chunks) in body, text)
        expect(marks == ["yield:0", "yield:1", "yield:2"], str(marks))
        expect("cpk_live" not in text and "do not store streaming prompt" not in text, text)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            usage = conn.execute("SELECT model, status, stream, metadata_json FROM arclink_llm_usage_events").fetchone()
            event = conn.execute(
                "SELECT metadata_json FROM arclink_events WHERE event_type = 'llm_router:fallback_attempt'"
            ).fetchone()
            serialized = "\n".join(
                str(dict(row))
                for table in ("arclink_llm_usage_events", "arclink_llm_budget_reservations", "arclink_events", "arclink_deployments")
                for row in conn.execute(f"SELECT * FROM {table}").fetchall()
            )
        finally:
            conn.close()
        usage_meta = json.loads(usage["metadata_json"])
        event_meta = json.loads(event["metadata_json"])
        expect(usage["model"] == "model-b" and usage["status"] == "succeeded" and usage["stream"] == 1, dict(usage))
        expect(usage_meta["fallback_used"] is True and usage_meta["streaming_fallback"] == "pre_stream", str(usage_meta))
        expect(event_meta["stream"] is True and event_meta["outcome"] == "retrying", str(event_meta))
        expect("cpk_live" not in serialized and "do not store streaming prompt" not in serialized, serialized)
    finally:
        tmp.cleanup()
    print("PASS test_chat_streaming_retries_pre_stream_fallback_and_records_metadata")


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


def test_open_reservations_count_against_budget_so_concurrency_cannot_overspend() -> None:
    # C1: boundary.remaining_cents is SETTLED-only, so concurrent in-flight
    # requests each holding an OPEN reservation must be subtracted from remaining
    # before the per-request reservation gate, or N requests collectively reserve
    # past the budget. Seed remaining headroom that is already fully consumed by
    # open reservations and confirm the next request is refused (402).
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(
            db_path,
            deployment_metadata={"chutes": {"monthly_budget_cents": 100, "used_cents": 95}},
        )
        # Remaining settled headroom is 5c. An open reservation of 5c already
        # holds all of it, so the next request (>=1c) must be refused.
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        fresh = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        conn.execute(
            """
            INSERT INTO arclink_llm_budget_reservations (
              reservation_id, request_id, deployment_id, user_id, reserved_cents, status, created_at
            ) VALUES ('llmres_open', 'llmreq_open', 'dep_1', 'user_1', 5, 'reserved', ?)
            """,
            (fresh,),
        )
        conn.commit()
        conn.close()
        upstream = fake_upstream_transport()
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                # High concurrency limit so the concurrency gate does not mask the
                # budget gate -- this proves the OPEN-reservation subtraction.
                "ARCLINK_LLM_ROUTER_DEPLOYMENT_CONCURRENCY_LIMIT": "50",
            },
            upstream_transport=upstream,
        )
        blocked = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "messages": [{"role": "user", "content": "hello"}]},
        )
        expect(blocked.status_code == 402, blocked.text)
        expect(blocked.json()["error"]["code"] == "budget_exhausted", blocked.text)
        expect(len(upstream.requests) == 0, str(upstream.requests))  # type: ignore[attr-defined]
    finally:
        tmp.cleanup()
    print("PASS test_open_reservations_count_against_budget_so_concurrency_cannot_overspend")


def test_stale_reservation_reaper_releases_leaked_rows_and_keeps_fresh() -> None:
    # C2: a worker that dies mid-request leaks a 'reserved' row that consumes
    # budget headroom forever. The HEARTBEAT reaper must expire rows whose
    # heartbeat went stale past the TTL while leaving genuinely in-flight (fresh
    # heartbeat) rows untouched -- and marks them 'expired' (not a clean
    # 'released') so settlement can still reconcile them by id.
    router = load_module("arclink_llm_router.py", "arclink_llm_router_reaper_test")
    control = load_module("arclink_control.py", "arclink_control_llm_router_reaper_test")
    tmp, db_path = temp_router_db()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            control.ensure_schema(conn)
            stale = "2026-01-01T00:00:00+00:00"  # far past the TTL
            fresh = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            for rid, hb in (("llmres_stale", stale), ("llmres_fresh", fresh)):
                conn.execute(
                    """
                    INSERT INTO arclink_llm_budget_reservations (
                      reservation_id, request_id, deployment_id, user_id, reserved_cents, status, created_at, heartbeat_at
                    ) VALUES (?, ?, 'dep_1', 'user_1', 3, 'reserved', ?, ?)
                    """,
                    (rid, f"req_{rid}", stale, hb),
                )
            conn.commit()
            config = router.load_router_config(
                {"ARCLINK_DB_PATH": db_path, "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "k"}
            )
            released = router._reap_stale_reservations(conn, config)
            expect(released == 1, f"exactly the stale-heartbeat row should be reaped, got {released}")
            rows = {
                str(row["reservation_id"]): str(row["status"])
                for row in conn.execute(
                    "SELECT reservation_id, status FROM arclink_llm_budget_reservations"
                ).fetchall()
            }
            # NOTE: both rows are equally OLD (created_at far in the past); only the
            # heartbeat distinguishes them, proving the reaper keys on heartbeat
            # staleness, NOT total age -- so a long-but-live stream is never reaped.
            expect(rows["llmres_stale"] == "expired", str(rows))
            expect(rows["llmres_fresh"] == "reserved", str(rows))
            # Idempotent: a second pass reaps nothing.
            expect(router._reap_stale_reservations(conn, config) == 0, "reaper must be idempotent")
        finally:
            conn.close()
    finally:
        tmp.cleanup()
    print("PASS test_stale_reservation_reaper_releases_leaked_rows_and_keeps_fresh")


def test_omitted_max_tokens_forwards_reservation_output_cap_upstream() -> None:
    # missed-H: when the caller omits max_tokens the reservation prices a bounded
    # output (min(cap, 1024)); the forwarded upstream payload must carry that same
    # cap so actual usage cannot settle unbounded above the reservation.
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(
            db_path,
            deployment_metadata={"chutes": {"monthly_budget_cents": 100000, "used_cents": 0}},
        )
        upstream = fake_upstream_transport()
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_MAX_TOKENS_CAP": "4096",
            },
            upstream_transport=upstream,
        )
        # Caller omits max_tokens entirely.
        ok = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "messages": [{"role": "user", "content": "hi"}]},
        )
        expect(ok.status_code == 200, ok.text)
        forwarded = upstream.requests[0]["payload"]  # type: ignore[attr-defined]
        expect(forwarded.get("max_tokens") == 1024, str(forwarded))

        # An explicit caller cap is preserved (not overwritten).
        upstream.requests.clear()  # type: ignore[attr-defined]
        ok2 = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "max_tokens": 64, "messages": [{"role": "user", "content": "hi"}]},
        )
        expect(ok2.status_code == 200, ok2.text)
        forwarded2 = upstream.requests[0]["payload"]  # type: ignore[attr-defined]
        expect(forwarded2.get("max_tokens") == 64, str(forwarded2))
    finally:
        tmp.cleanup()
    print("PASS test_omitted_max_tokens_forwards_reservation_output_cap_upstream")


def test_default_model_marked_unavailable_is_not_forwarded() -> None:
    # H2: _router_model_allowed admits config.default_model regardless of catalog
    # status. Once the catalog marks that model 'unavailable' (no live
    # replacement), the router must refuse to forward it -- even as the default --
    # unless the break-glass env is set.
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(
            db_path,
            allowed_models=[],  # global allow-list / default model path
            deployment_metadata={"chutes": {"monthly_budget_cents": 100000, "used_cents": 0}},
        )
        # Seed the default model into the catalog and mark it unavailable.
        control = load_module("arclink_control.py", "arclink_control_h2_unavailable_test")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            control.ensure_schema(conn)
            control.upsert_model_catalog(
                conn,
                provider="chutes",
                models={"default-unavailable-TEE": {"confidential_compute": True}},
            )
            conn.execute(
                "UPDATE arclink_model_catalog SET status='unavailable' WHERE model_id='default-unavailable-TEE'"
            )
            conn.commit()
        finally:
            conn.close()
        upstream = fake_upstream_transport()
        base_env = {
            "ARCLINK_DB_PATH": db_path,
            "ARCLINK_LLM_ROUTER_ENABLED": "1",
            "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
            "ARCLINK_LLM_ROUTER_DEFAULT_MODEL": "default-unavailable-TEE",
            # Empty global allow-list -> env fallback is (default,), exercising the
            # default-model admission path the H2 guard must still reject.
            "ARCLINK_LLM_ROUTER_ALLOWED_MODELS": "",
        }
        client = _client_for(base_env, upstream_transport=upstream)
        refused = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "default-unavailable-TEE", "messages": [{"role": "user", "content": "hi"}]},
        )
        expect(refused.status_code == 403, refused.text)
        expect(refused.json()["error"]["code"] == "model_unavailable", refused.text)
        expect(len(upstream.requests) == 0, str(upstream.requests))  # type: ignore[attr-defined]

        # Break-glass env reopens it for incident response.
        upstream2 = fake_upstream_transport()
        client2 = _client_for(
            {**base_env, "ARCLINK_LLM_ROUTER_ALLOW_INACTIVE_MODELS": "1"},
            upstream_transport=upstream2,
        )
        allowed = client2.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "default-unavailable-TEE", "messages": [{"role": "user", "content": "hi"}]},
        )
        expect(allowed.status_code == 200, allowed.text)
        expect(len(upstream2.requests) == 1, str(upstream2.requests))  # type: ignore[attr-defined]
    finally:
        tmp.cleanup()
    print("PASS test_default_model_marked_unavailable_is_not_forwarded")


def test_health_reports_allow_list_state_and_alerts_on_collapse() -> None:
    # H3: /health must distinguish a synced catalog from the env fallback and
    # alert the Operator once when the synced allow-list COLLAPSES to env-only
    # after a prior successful sync.
    tmp, db_path = temp_router_db()
    try:
        control = load_module("arclink_control.py", "arclink_control_h3_collapse_test")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            control.ensure_schema(conn)
            # A prior successful sync exists, but the catalog is now empty -> collapse.
            control.append_arclink_audit(
                conn,
                action="llm_router:model_sync_ok",
                target_kind="llm-router",
                target_id="chutes",
                reason="synced 9 -TEE models",
                metadata={"model_count": 9},
            )
        finally:
            conn.close()
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_ALLOWED_MODELS": "model-a",
            }
        )
        health = client.get("/health")
        expect(health.status_code == 200, health.text)
        payload = health.json()
        allow_list = payload.get("allow_list") or {}
        expect(allow_list.get("source") == "env_fallback", str(allow_list))
        expect(allow_list.get("synced_catalog_collapsed") is True, str(allow_list))
        expect(allow_list.get("ever_synced") is True, str(allow_list))

        # An operator hiccup notice was queued exactly once across repeated checks.
        client.get("/health")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            notices = conn.execute(
                "SELECT message FROM notification_outbox WHERE target_kind='operator'"
            ).fetchall()
            audits = conn.execute(
                "SELECT action FROM arclink_audit_log WHERE action LIKE 'operator_hiccup:llm_router_allow_list_collapsed%'"
            ).fetchall()
        finally:
            conn.close()
        expect(len(notices) == 1, f"collapse must alert the operator exactly once, got {len(notices)}")
        expect("COLLAPSED" in str(notices[0]["message"]), str(notices[0]["message"]))
        expect(len(audits) == 1, str(audits))
    finally:
        tmp.cleanup()
    print("PASS test_health_reports_allow_list_state_and_alerts_on_collapse")


def test_fresh_heartbeat_survives_old_read_timeout_window_and_settles_by_id() -> None:
    # C2 (deploy-blocking): an httpx READ timeout is per-chunk, NOT a total stream
    # lifetime, so a long stream legitimately outlives read_timeout+120 while still
    # yielding chunks. The OLD age-based reaper would expire that LIVE reservation,
    # stop counting it against budget (C1 overspend), and the status='reserved'
    # release guard meant a reaped-but-returning request could never reconcile.
    #
    # This proves the heartbeat fix end to end:
    #   (a) a reservation with a FRESH heartbeat is NOT reaped even though its
    #       created_at is far older than the old read_timeout+120 window;
    #   (b) a reservation with a STALE heartbeat IS reaped (-> 'expired');
    #   (c) a reaped ('expired') row that then SETTLES reconciles by id -> 'settled'
    #       and stops double-counting against the C1 status='reserved' headroom sum.
    router = load_module("arclink_llm_router.py", "arclink_llm_router_heartbeat_test")
    control = load_module("arclink_control.py", "arclink_control_llm_router_heartbeat_test")
    tmp, db_path = temp_router_db()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            control.ensure_schema(conn)
            now = datetime.now(timezone.utc)
            # A short read timeout -> old TTL would be read_timeout+120 == 130s.
            config = router.load_router_config(
                {
                    "ARCLINK_DB_PATH": db_path,
                    "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "k",
                    "ARCLINK_LLM_ROUTER_UPSTREAM_READ_TIMEOUT_SECONDS": "10",
                }
            )
            # created_at 1 hour ago for BOTH rows (well past read_timeout+120) so the
            # ONLY thing that can save a row is a fresh heartbeat.
            old_created = (now - __import__("datetime").timedelta(hours=1)).replace(microsecond=0).isoformat()
            fresh_hb = now.replace(microsecond=0).isoformat()
            stale_hb = (now - __import__("datetime").timedelta(minutes=30)).replace(microsecond=0).isoformat()
            for rid, hb, cents in (("llmres_live", fresh_hb, 7), ("llmres_dead", stale_hb, 11)):
                conn.execute(
                    """
                    INSERT INTO arclink_llm_budget_reservations (
                      reservation_id, request_id, deployment_id, user_id, reserved_cents, status, created_at, heartbeat_at
                    ) VALUES (?, ?, 'dep_1', 'user_1', ?, 'reserved', ?, ?)
                    """,
                    (rid, f"req_{rid}", cents, old_created, hb),
                )
            conn.commit()

            reaped = router._reap_stale_reservations(conn, config)
            expect(reaped == 1, f"only the stale-heartbeat (dead) row should be reaped, got {reaped}")
            rows = {
                str(r["reservation_id"]): str(r["status"])
                for r in conn.execute("SELECT reservation_id, status FROM arclink_llm_budget_reservations").fetchall()
            }
            # (a) live row with a fresh heartbeat survives despite the ancient created_at.
            expect(rows["llmres_live"] == "reserved", f"fresh-heartbeat live row must survive: {rows}")
            # (b) dead row is expired (distinct from a clean 'released').
            expect(rows["llmres_dead"] == "expired", f"stale-heartbeat row must be expired: {rows}")

            # C1: the expired row no longer counts against the open-reservation sum;
            # only the live (still 'reserved') row does.
            open_cents = router._open_reserved_cents(conn, "dep_1")
            expect(open_cents == 7, f"expired row must drop out of the budget headroom sum, got {open_cents}")

            # (c) the reaped (expired) request returns and SETTLES -> reconciles by id.
            router._release_budget_reservation(
                conn,
                "llmres_dead",
                status="settled",
                settled_cents=9,
            )
            settled_row = conn.execute(
                "SELECT status, settled_cents FROM arclink_llm_budget_reservations WHERE reservation_id='llmres_dead'"
            ).fetchone()
            expect(str(settled_row["status"]) == "settled", f"expired row must reconcile to settled: {dict(settled_row)}")
            expect(int(settled_row["settled_cents"]) == 9, str(dict(settled_row)))
            # And it still does not re-enter the open headroom sum after settlement.
            expect(router._open_reserved_cents(conn, "dep_1") == 7, "settled row must not double-count")

            # A double-settle on the now-terminal row is a no-op (no row rewrite).
            router._release_budget_reservation(conn, "llmres_dead", status="failed", settled_cents=999)
            recheck = conn.execute(
                "SELECT status, settled_cents FROM arclink_llm_budget_reservations WHERE reservation_id='llmres_dead'"
            ).fetchone()
            expect(str(recheck["status"]) == "settled", f"terminal row must not be rewritten: {dict(recheck)}")
            expect(int(recheck["settled_cents"]) == 9, str(dict(recheck)))
        finally:
            conn.close()
    finally:
        tmp.cleanup()
    print("PASS test_fresh_heartbeat_survives_old_read_timeout_window_and_settles_by_id")


def test_null_max_tokens_is_dropped_and_reservation_cap_injected() -> None:
    # missed-H2: a caller can set max_tokens: null (or non-positive/invalid). The
    # reservation prices the bounded default (min(cap, 1024)), but the null key
    # EXISTS in the body -- forwarding it verbatim lets upstream treat null as
    # unbounded. The forwarded payload must DROP the null/invalid key and inject
    # the reservation output cap, with no null surviving.
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(
            db_path,
            deployment_metadata={"chutes": {"monthly_budget_cents": 100000, "used_cents": 0}},
        )
        upstream = fake_upstream_transport()
        client = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_MAX_TOKENS_CAP": "4096",
            },
            upstream_transport=upstream,
        )
        ok = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={
                "model": "model-a",
                "max_tokens": None,
                "max_completion_tokens": None,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        expect(ok.status_code == 200, ok.text)
        forwarded = upstream.requests[0]["payload"]  # type: ignore[attr-defined]
        # The null keys are gone, and a positive injected cap is present.
        expect("max_completion_tokens" not in forwarded, str(forwarded))
        expect(forwarded.get("max_tokens") == 1024, str(forwarded))
        expect(forwarded.get("max_tokens") is not None, str(forwarded))

        # A non-positive / non-int explicit value is also dropped, not forwarded.
        upstream.requests.clear()  # type: ignore[attr-defined]
        ok2 = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "max_tokens": 0, "messages": [{"role": "user", "content": "hi"}]},
        )
        expect(ok2.status_code == 200, ok2.text)
        forwarded2 = upstream.requests[0]["payload"]  # type: ignore[attr-defined]
        expect(forwarded2.get("max_tokens") == 1024, str(forwarded2))
    finally:
        tmp.cleanup()
    print("PASS test_null_max_tokens_is_dropped_and_reservation_cap_injected")


def test_reaper_ttl_exceeds_upstream_read_window_so_slow_live_request_is_safe() -> None:
    # Round-3 (deploy-blocking): the heartbeat refreshes only AFTER a streamed
    # chunk, while httpx bounds time-to-first-byte, the inter-chunk gap, AND a whole
    # non-streaming call to the upstream READ timeout. So a LIVE request can go up
    # to read_timeout seconds without refreshing -- the reaper TTL must be STRICTLY
    # GREATER than one read window (+margin) or a legitimately-slow live request is
    # false-expired, dropped from the C1 open-reservation sum -> budget over-reserved.
    router = load_module("arclink_llm_router.py", "arclink_llm_router_ttl_window_test")
    control = load_module("arclink_control.py", "arclink_control_llm_router_ttl_window_test")
    tmp, db_path = temp_router_db()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            control.ensure_schema(conn)
            # A LONG read timeout: one read window (600s) far exceeds the legacy
            # fixed 120s floor, so the TTL must track read_timeout+margin.
            read_timeout = 600
            margin = router.RESERVATION_REAPER_TTL_MARGIN_SECONDS
            config = router.load_router_config(
                {
                    "ARCLINK_DB_PATH": db_path,
                    "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "k",
                    "ARCLINK_LLM_ROUTER_UPSTREAM_READ_TIMEOUT_SECONDS": str(read_timeout),
                }
            )
            ttl = router._reservation_reaper_ttl_seconds(config)
            # TTL strictly greater than a single read window so one read-timeout gap
            # (no refresh) can never by itself trip the reaper.
            expect(ttl == read_timeout + margin, f"TTL must be read_timeout+margin, got {ttl}")
            expect(ttl > read_timeout, f"TTL must exceed one read window, got {ttl} vs {read_timeout}")

            now = datetime.now(timezone.utc)
            from datetime import timedelta as _td
            ancient_created = (now - _td(hours=6)).replace(microsecond=0).isoformat()
            # (a) live stream whose ONLY liveness signal is the heartbeat: ancient
            #     created_at, but heartbeat stale by exactly one read window (less
            #     than the TTL). MUST survive -- a single read gap can't expire it.
            within_window_hb = (now - _td(seconds=read_timeout)).replace(microsecond=0).isoformat()
            # (b) heartbeat stale by MORE than read_timeout+margin -> genuinely dead.
            past_ttl_hb = (now - _td(seconds=read_timeout + margin + 60)).replace(microsecond=0).isoformat()
            for rid, hb, cents in (
                ("llmres_slow_live", within_window_hb, 5),
                ("llmres_dead", past_ttl_hb, 9),
            ):
                conn.execute(
                    """
                    INSERT INTO arclink_llm_budget_reservations (
                      reservation_id, request_id, deployment_id, user_id, reserved_cents, status, created_at, heartbeat_at
                    ) VALUES (?, ?, 'dep_1', 'user_1', ?, 'reserved', ?, ?)
                    """,
                    (rid, f"req_{rid}", cents, ancient_created, hb),
                )
            conn.commit()

            reaped = router._reap_stale_reservations(conn, config)
            expect(reaped == 1, f"only the row stale past the new TTL should reap, got {reaped}")
            rows = {
                str(r["reservation_id"]): str(r["status"])
                for r in conn.execute("SELECT reservation_id, status FROM arclink_llm_budget_reservations").fetchall()
            }
            # Slow-but-live request whose heartbeat is one read window old survives.
            expect(rows["llmres_slow_live"] == "reserved", f"slow live request must NOT be expired: {rows}")
            # Heartbeat stale past read_timeout+margin is reaped.
            expect(rows["llmres_dead"] == "expired", f"row stale past TTL must be expired: {rows}")
            # The slow-live row still counts against the C1 headroom sum (no
            # under-counting -> no over-reservation); the dead one drops out.
            expect(router._open_reserved_cents(conn, "dep_1") == 5, "only the live row counts against headroom")
        finally:
            conn.close()
    finally:
        tmp.cleanup()
    print("PASS test_reaper_ttl_exceeds_upstream_read_window_so_slow_live_request_is_safe")


def test_all_max_output_keys_capped_no_largest_key_bypass() -> None:
    # Round-3 (new bug): the max-token cap only checked the FIRST present key, so
    # {max_tokens: null, max_completion_tokens: 999999} or
    # {max_tokens: 64, max_completion_tokens: 999999} let the huge key bypass the
    # cap and reach upstream unclamped (under-priced reservation). The effective
    # requested cap must be the MIN of usable positive values across ALL keys, the
    # reservation must price that effective max, and EVERY present max-output key
    # must be clamped <= that effective cap on the wire.
    router = load_module("arclink_llm_router.py", "arclink_llm_router_allkeys_cap_test")

    # Unit: _requested_max_tokens takes the MIN across all usable keys, not the first.
    expect(router._requested_max_tokens({"max_tokens": None, "max_completion_tokens": 999999}) == 999999,
           "null + 999999 -> effective 999999 (only usable value)")
    expect(router._requested_max_tokens({"max_tokens": 64, "max_completion_tokens": 999999}) == 64,
           "64 + 999999 -> effective MIN 64, NOT the first/largest key")
    expect(router._requested_max_tokens({"max_completion_tokens": 32, "max_tokens": 8192}) == 32,
           "min across keys regardless of order")
    expect(router._requested_max_tokens({"max_tokens": 0, "max_completion_tokens": None}) == 0,
           "no usable value -> 0 (reservation default)")

    # Unit: _prepare_upstream_payload clamps EVERY present key <= the priced ceiling.
    p1 = router._prepare_upstream_payload(
        {"max_tokens": None, "max_completion_tokens": 999999}, max_output_tokens=999999
    )
    expect(p1.get("max_tokens") is None and "max_tokens" not in p1, str(p1))  # null dropped
    expect(p1.get("max_completion_tokens") == 999999, str(p1))  # == ceiling, allowed
    p2 = router._prepare_upstream_payload(
        {"max_tokens": 64, "max_completion_tokens": 999999}, max_output_tokens=64
    )
    # BOTH keys clamped to the 64 ceiling -- the 999999 key can NOT exceed the reservation.
    expect(p2.get("max_tokens") == 64, str(p2))
    expect(p2.get("max_completion_tokens") == 64, str(p2))
    for key in ("max_tokens", "max_completion_tokens"):
        expect(int(p2.get(key)) <= 64, f"{key} must be clamped to <= ceiling: {p2}")

    # End-to-end: both payloads FORWARD (cap high enough to admit the effective max),
    # every forwarded max-output key <= the effective cap, and the reservation is
    # priced to the EFFECTIVE (capped) max -- not the bypassing huge key.
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(
            db_path,
            deployment_metadata={"chutes": {"monthly_budget_cents": 100000000, "used_cents": 0}},
        )

        # Case A: {max_tokens: null, max_completion_tokens: 999999} -> effective 999999.
        upstream_a = fake_upstream_transport()
        client_a = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_MAX_TOKENS_CAP": "1000000",
            },
            upstream_transport=upstream_a,
        )
        ra = client_a.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={
                "model": "model-a",
                "max_tokens": None,
                "max_completion_tokens": 999999,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        expect(ra.status_code == 200, ra.text)
        fwd_a = upstream_a.requests[0]["payload"]  # type: ignore[attr-defined]
        effective_a = 999999
        for key in ("max_tokens", "max_completion_tokens"):
            if key in fwd_a and fwd_a[key] is not None:
                expect(int(fwd_a[key]) <= effective_a, f"A: {key} must be <= effective cap: {fwd_a}")
        expect("max_tokens" not in fwd_a, f"A: null max_tokens must be dropped: {fwd_a}")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            res_a = conn.execute("SELECT reserved_cents FROM arclink_llm_budget_reservations ORDER BY created_at DESC LIMIT 1").fetchone()
            priced_a = int(res_a["reserved_cents"])
            conn.execute("DELETE FROM arclink_llm_budget_reservations")
            conn.commit()
        finally:
            conn.close()

        # Case B: {max_tokens: 64, max_completion_tokens: 999999} -> effective MIN 64.
        upstream_b = fake_upstream_transport()
        client_b = _client_for(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_MAX_TOKENS_CAP": "1000000",
            },
            upstream_transport=upstream_b,
        )
        rb = client_b.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={
                "model": "model-a",
                "max_tokens": 64,
                "max_completion_tokens": 999999,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        expect(rb.status_code == 200, rb.text)
        fwd_b = upstream_b.requests[0]["payload"]  # type: ignore[attr-defined]
        effective_b = 64
        # EVERY present max-output key <= 64 -- the 999999 key is clamped, not bypassed.
        for key in ("max_tokens", "max_completion_tokens"):
            expect(key in fwd_b, f"B: {key} expected present (clamped): {fwd_b}")
            expect(int(fwd_b[key]) <= effective_b, f"B: {key} must be clamped to <= 64: {fwd_b}")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            res_b = conn.execute("SELECT reserved_cents FROM arclink_llm_budget_reservations ORDER BY created_at DESC LIMIT 1").fetchone()
            priced_b = int(res_b["reserved_cents"])
        finally:
            conn.close()

        # The reservation is priced to the EFFECTIVE (capped) max: case B (effective
        # 64) must reserve far fewer cents than case A (effective 999999). If the
        # 999999 key had bypassed the cap, B would also price ~999999 output tokens.
        expect(priced_b < priced_a, f"effective-64 reservation must be cheaper than effective-999999: {priced_b} vs {priced_a}")
    finally:
        tmp.cleanup()
    print("PASS test_all_max_output_keys_capped_no_largest_key_bypass")


def test_allow_list_collapse_alert_rearms_after_recovery() -> None:
    # H3 rearm: report_operator_hiccup dedups on its key and only re-arms when a
    # matching resolve is recorded. /health must RESOLVE the collapse key on
    # recovery (synced catalog non-empty again) so a SECOND collapse re-alerts.
    tmp, db_path = temp_router_db()
    try:
        control = load_module("arclink_control.py", "arclink_control_h3_rearm_test")

        def _seed_prior_sync(c: Any) -> None:
            control.append_arclink_audit(
                c,
                action="llm_router:model_sync_ok",
                target_kind="llm-router",
                target_id="chutes",
                reason="synced 9 -TEE models",
                metadata={"model_count": 9},
            )

        def _set_catalog(models: list[str]) -> None:
            c = sqlite3.connect(db_path)
            c.row_factory = sqlite3.Row
            try:
                control.ensure_schema(c)
                c.execute("DELETE FROM arclink_model_catalog WHERE provider='chutes'")
                for mid in models:
                    control.upsert_model_catalog(c, provider="chutes", models={mid: {"confidential_compute": True}})
                c.commit()
            finally:
                c.close()

        def _collapse_audit_count() -> int:
            c = sqlite3.connect(db_path)
            c.row_factory = sqlite3.Row
            try:
                report = c.execute(
                    "SELECT COUNT(*) AS n FROM arclink_audit_log WHERE action='operator_hiccup:llm_router_allow_list_collapsed'"
                ).fetchone()
                resolve = c.execute(
                    "SELECT COUNT(*) AS n FROM arclink_audit_log WHERE action='operator_hiccup_resolved:llm_router_allow_list_collapsed'"
                ).fetchone()
                notices = c.execute(
                    "SELECT COUNT(*) AS n FROM notification_outbox WHERE target_kind='operator'"
                ).fetchone()
                return int(report["n"]), int(resolve["n"]), int(notices["n"])
            finally:
                c.close()

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            control.ensure_schema(conn)
            _seed_prior_sync(conn)
        finally:
            conn.close()

        env = {
            "ARCLINK_DB_PATH": db_path,
            "ARCLINK_LLM_ROUTER_ENABLED": "1",
            "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
            "ARCLINK_LLM_ROUTER_ALLOWED_MODELS": "model-a",
        }
        client = _client_for(env)

        # 1) First collapse: catalog empty after a prior sync -> alert exactly once.
        client.get("/health")
        client.get("/health")
        reports, resolves, notices = _collapse_audit_count()
        expect(reports == 1, f"first collapse must alert once, got {reports}")
        expect(resolves == 0, f"no resolve yet, got {resolves}")
        expect(notices == 1, f"exactly one operator notice, got {notices}")

        # 2) Recovery: synced -TEE catalog non-empty again -> /health resolves the key.
        _set_catalog(["model-a-TEE", "model-b-TEE"])
        # Use a fresh client so RouterConfig reads the now-populated catalog.
        client2 = _client_for(env)
        health = client2.get("/health")
        allow_list = health.json().get("allow_list") or {}
        expect(allow_list.get("source") == "synced_catalog", str(allow_list))
        expect(allow_list.get("synced_catalog_collapsed") is False, str(allow_list))
        reports, resolves, notices = _collapse_audit_count()
        expect(resolves == 1, f"recovery must resolve the key exactly once, got {resolves}")

        # 3) Second collapse: catalog emptied again -> alert RE-ARMS and fires again.
        _set_catalog([])
        client3 = _client_for(env)
        client3.get("/health")
        reports, resolves, notices = _collapse_audit_count()
        expect(reports == 2, f"second collapse after recovery must re-alert, got {reports}")
        expect(notices == 2, f"second operator notice must be queued, got {notices}")
    finally:
        tmp.cleanup()
    print("PASS test_allow_list_collapse_alert_rearms_after_recovery")


def test_pre_response_retries_keep_live_reservation_heartbeated_across_windows() -> None:
    # Round-4 (deploy-blocking): the heartbeat only refreshed AFTER a streamed chunk,
    # so the non-streaming retry path (and the streaming pre-first-chunk path) could
    # each burn a full upstream read timeout per attempt with NO heartbeat refresh.
    # N fallback retries -> up to N x read_timeout un-heartbeated -> the reaper
    # false-expires the LIVE reservation -> it drops from the C1 open-reservation sum
    # -> budget over-reserved. The fix touches the heartbeat at the START of every
    # attempt, so a live request can never go longer than ONE read window without a
    # heartbeat regardless of retry count.
    #
    # This drives the REAL _forward_non_streaming retry loop with a fake clock: each
    # upstream attempt advances time by a full read window and runs the reaper (as a
    # concurrent preflight would). With the per-attempt touch the live row is never
    # expired even though total elapsed time across the retries far exceeds the TTL;
    # a parallel DEAD reservation that no attempt ever touches IS reaped.
    import asyncio
    from datetime import timedelta as _td

    router = load_module("arclink_llm_router.py", "arclink_llm_router_retry_heartbeat_test")
    control = load_module("arclink_control.py", "arclink_control_retry_heartbeat_test")
    tmp, db_path = temp_router_db()
    real_datetime = router.datetime
    try:
        conn0 = sqlite3.connect(db_path)
        conn0.row_factory = sqlite3.Row
        control.ensure_schema(conn0)
        conn0.close()

        # read_timeout chosen so a few attempts' total elapsed time EXCEEDS the TTL:
        # TTL == read_timeout + margin == 240s, but 4 attempts span 480s. Without the
        # per-attempt heartbeat touch the live row's heartbeat would stay frozen at T0
        # and be reaped by the third reaper pass (T0+360 > 240); with the fix each
        # attempt refreshes it, so max staleness stays ~read_timeout < TTL.
        read_timeout = 120
        margin = router.RESERVATION_REAPER_TTL_MARGIN_SECONDS
        config = router.load_router_config(
            {
                "ARCLINK_DB_PATH": db_path,
                "ARCLINK_LLM_ROUTER_ENABLED": "1",
                "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
                "ARCLINK_LLM_ROUTER_UPSTREAM_READ_TIMEOUT_SECONDS": str(read_timeout),
                # Three fallbacks -> four candidates -> four attempts. The reaper
                # 429 (retryable) on the first three forces three pre-response retries
                # before the final 200.
                "ARCLINK_LLM_ROUTER_FALLBACK_MODELS": "model-b,model-c,model-d",
                "ARCLINK_LLM_ROUTER_FALLBACK_STATUS_CODES": "429",
            }
        )

        # Advancing fake clock shared by both the heartbeat writer and the reaper, so
        # the test is fully deterministic with zero real sleeping.
        clock = {"now": real_datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)}

        class FakeDatetime(real_datetime):  # type: ignore[misc, valid-type]
            @classmethod
            def now(cls, tz=None):  # type: ignore[override]
                value = clock["now"]
                return value if tz is None else value.astimezone(tz)

        start_iso = clock["now"].replace(microsecond=0).isoformat()
        ttl = router._reservation_reaper_ttl_seconds(config)
        # A worker that died: heartbeat already stale past the TTL at T0 and never
        # touched again, so the very first reaper pass must expire it. This isolates
        # the fix -- the live row (touched each attempt) survives the SAME reaper
        # passes that reap this dead row.
        dead_hb = (clock["now"] - _td(seconds=ttl + 60)).replace(microsecond=0).isoformat()
        # The live reservation under retry: heartbeat freshly stamped at T0.
        for rid, hb, cents in (("llmres_live_retry", start_iso, 5), ("llmres_dead_worker", dead_hb, 9)):
            conn0 = sqlite3.connect(db_path)
            conn0.execute(
                """
                INSERT INTO arclink_llm_budget_reservations (
                  reservation_id, request_id, deployment_id, user_id, reserved_cents, status, metadata_json, created_at, heartbeat_at
                ) VALUES (?, ?, 'dep_1', 'user_1', ?, 'reserved', '{}', ?, ?)
                """,
                (rid, f"req_{rid}", cents, start_iso, hb),
            )
            conn0.commit()
            conn0.close()

        reservation = {
            "reservation_id": "llmres_live_retry",
            "request_id": "req_llmres_live_retry",
            "deployment_id": "dep_1",
            "user_id": "user_1",
            "reserved_cents": 5,
            "heartbeat_at": start_iso,
            "upstream_model": "model-a",
            "input_token_estimate": 4,
            "output_token_estimate": 16,
            "effective_completions": 1,
        }

        live_status_seen: list[str] = []
        attempt_count = {"n": 0}

        def handler_factory():
            import httpx

            async def handler(request: "httpx.Request") -> "httpx.Response":
                attempt_count["n"] += 1
                # Each attempt consumes a FULL read window before any heartbeat could
                # come from streamed output. Advance the shared clock accordingly...
                clock["now"] = clock["now"] + _td(seconds=read_timeout)
                # ...then run the reaper exactly as a concurrent preflight would. With
                # the per-attempt touch already applied (start of this attempt) the
                # live row's heartbeat is fresh; without the fix it would be
                # read_timeout * (attempt-1) stale and expire on a later attempt.
                rconn = sqlite3.connect(db_path)
                rconn.row_factory = sqlite3.Row
                router.ensure_schema(rconn)
                router._reap_stale_reservations(rconn, config)
                row = rconn.execute(
                    "SELECT status FROM arclink_llm_budget_reservations WHERE reservation_id='llmres_live_retry'"
                ).fetchone()
                live_status_seen.append(str(row["status"]))
                rconn.close()
                # Retry the first three attempts (429), succeed on the fourth.
                if attempt_count["n"] < 4:
                    return httpx.Response(429, json={"error": "overloaded"})
                return httpx.Response(
                    200,
                    json={
                        "id": "chatcmpl_retry",
                        "object": "chat.completion",
                        "usage": {"prompt_tokens": 4, "completion_tokens": 6, "total_tokens": 10},
                    },
                )

            return httpx.MockTransport(handler)

        class _State:
            pass

        class _App:
            state = _State()

        class _Req:
            app = _App()

        _App.state.router_upstream_transport = handler_factory()

        # Patch the module clock so the heartbeat writer and the reaper share it.
        router.datetime = FakeDatetime
        try:
            response = asyncio.run(
                router._forward_non_streaming(
                    _Req(),
                    config,
                    auth_record={"deployment_id": "dep_1", "user_id": "user_1", "key_id": "k1"},
                    reservation=reservation,
                    payload={"model": "model-a", "messages": [{"role": "user", "content": "hi"}]},
                )
            )
        finally:
            router.datetime = real_datetime

        expect(response.status_code == 200, str(getattr(response, "body", b"")))
        # Four attempts happened, total elapsed 40s >> TTL (read_timeout+margin) -- yet
        # the live reservation was 'reserved' on EVERY reaper pass (never falsely
        # expired) because each attempt refreshed its heartbeat first.
        expect(attempt_count["n"] == 4, f"expected 4 attempts, got {attempt_count['n']}")
        expect(
            live_status_seen == ["reserved", "reserved", "reserved", "reserved"],
            f"live reservation must stay reserved across all retry windows, saw {live_status_seen}",
        )

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            live = conn.execute(
                "SELECT status FROM arclink_llm_budget_reservations WHERE reservation_id='llmres_live_retry'"
            ).fetchone()
            dead = conn.execute(
                "SELECT status FROM arclink_llm_budget_reservations WHERE reservation_id='llmres_dead_worker'"
            ).fetchone()
        finally:
            conn.close()
        # The live request settled cleanly (succeeded) -- never reaped mid-flight.
        expect(str(live["status"]) == "settled", f"live row must settle, got {dict(live)}")
        # The genuinely-dead worker (never touched, stale past the TTL) WAS reaped.
        expect(str(dead["status"]) == "expired", f"dead worker row must be reaped, got {dict(dead)}")
    finally:
        router.datetime = real_datetime
        tmp.cleanup()
    print("PASS test_pre_response_retries_keep_live_reservation_heartbeated_across_windows")


def test_multi_completion_n_reserves_and_clamps_against_single_output_cap() -> None:
    # Round-4 (deploy-blocking): the chat payload is forwarded wholesale, but the
    # reservation only priced a SINGLE output cap. A caller sending n: 5 (or best_of)
    # gets up to 5x the output while only 1x is reserved -> C1 under-reserved ->
    # over-spend. The fix prices the EFFECTIVE worst-case output (per-completion cap x
    # clamped n), clamps n into 1..MAX_COMPLETIONS, and forwards the clamped value so
    # the upstream fan-out can never exceed what was reserved.
    router = load_module("arclink_llm_router.py", "arclink_llm_router_multi_completion_unit_test")

    # Unit: completion count is the MAX usable multiplier, clamped to 1..max.
    cfg = router.load_router_config(
        {
            "ARCLINK_DB_PATH": "/tmp/unused-arclink-router-n.sqlite3",
            "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "k",
            "ARCLINK_LLM_ROUTER_MAX_COMPLETIONS": "4",
        }
    )
    expect(router._effective_completions(cfg, {}) == 1, "no n -> 1")
    expect(router._effective_completions(cfg, {"n": 1}) == 1, "n=1 -> 1")
    expect(router._effective_completions(cfg, {"n": 3}) == 3, "n=3 -> 3")
    expect(router._effective_completions(cfg, {"n": 5}) == 4, "n=5 clamped to max 4")
    expect(router._effective_completions(cfg, {"n": None}) == 1, "n=null -> 1")
    expect(router._effective_completions(cfg, {"n": 0}) == 1, "n=0 -> 1")
    expect(router._effective_completions(cfg, {"best_of": 7}) == 4, "best_of priced/clamped too")
    expect(router._effective_completions(cfg, {"n": 2, "best_of": 9}) == 4, "max across multipliers, clamped")

    # Unit: pricing scales output (not input) by the completion count.
    one = router._estimate_reservation_cents_for_model(cfg, None, 1000, 1000, 1)
    five = router._estimate_reservation_cents_for_model(cfg, None, 1000, 1000, 5)
    expect(five > one, f"5 completions must price more than 1: {five} vs {one}")

    # Unit: forwarded payload clamps every multiplier key to the priced ceiling and
    # drops unusable values.
    p = router._prepare_upstream_payload({"n": 9, "best_of": 9}, max_output_tokens=1000, max_completions=4)
    expect(p.get("n") == 4, f"n must clamp to ceiling: {p}")
    expect(p.get("best_of") == 4, f"best_of must clamp to ceiling: {p}")
    p_null = router._prepare_upstream_payload({"n": None}, max_output_tokens=1000, max_completions=4)
    expect("n" not in p_null, f"unusable n must be dropped: {p_null}")
    p_default = router._prepare_upstream_payload({"n": 1}, max_output_tokens=1000, max_completions=1)
    expect(p_default.get("n") == 1, f"single completion unchanged: {p_default}")

    # End-to-end: n: 5 with max_tokens: 1000 -> reservation priced for the CLAMPED
    # 4x1000 output, forwarded n <= the clamp; a single-completion request is
    # unchanged (n defaults to 1, priced 1x).
    tmp, db_path = temp_router_db()
    try:
        raw_key = _seed_router_key(
            db_path,
            deployment_metadata={"chutes": {"monthly_budget_cents": 100000000, "used_cents": 0}},
        )
        base_env = {
            "ARCLINK_DB_PATH": db_path,
            "ARCLINK_LLM_ROUTER_ENABLED": "1",
            "ARCLINK_LLM_ROUTER_CHUTES_API_KEY": "cpk_test_router_secret_123",
            "ARCLINK_LLM_ROUTER_MAX_TOKENS_CAP": "100000",
            "ARCLINK_LLM_ROUTER_MAX_COMPLETIONS": "4",
        }

        # Multi-completion request: n=5 -> clamped to 4.
        upstream_multi = fake_upstream_transport()
        client_multi = _client_for(base_env, upstream_transport=upstream_multi)
        rm = client_multi.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "n": 5, "max_tokens": 1000, "messages": [{"role": "user", "content": "hi"}]},
        )
        expect(rm.status_code == 200, rm.text)
        fwd_multi = upstream_multi.requests[0]["payload"]  # type: ignore[attr-defined]
        # Forwarded n is clamped to <= the configured max (4), never the raw 5.
        expect(fwd_multi.get("n") == 4, f"forwarded n must be clamped to 4: {fwd_multi}")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            res_multi = conn.execute(
                "SELECT reserved_cents FROM arclink_llm_budget_reservations ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            priced_multi = int(res_multi["reserved_cents"])
            conn.execute("DELETE FROM arclink_llm_budget_reservations")
            conn.commit()
        finally:
            conn.close()

        # Single-completion request: same max_tokens, no n -> priced 1x, n untouched.
        upstream_single = fake_upstream_transport()
        client_single = _client_for(base_env, upstream_transport=upstream_single)
        rs = client_single.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "model-a", "max_tokens": 1000, "messages": [{"role": "user", "content": "hi"}]},
        )
        expect(rs.status_code == 200, rs.text)
        fwd_single = upstream_single.requests[0]["payload"]  # type: ignore[attr-defined]
        expect("n" not in fwd_single, f"single-completion request must not inject n: {fwd_single}")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            res_single = conn.execute(
                "SELECT reserved_cents FROM arclink_llm_budget_reservations ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            priced_single = int(res_single["reserved_cents"])
        finally:
            conn.close()

        # The multi-completion reservation prices the EFFECTIVE 4x output and so must
        # reserve materially more than the single-completion request at the same
        # per-completion cap. If n had bypassed the cap, both would price 1x output.
        expect(
            priced_multi > priced_single,
            f"n=5(clamped 4) must reserve more than n=1 at same max_tokens: {priced_multi} vs {priced_single}",
        )
    finally:
        tmp.cleanup()
    print("PASS test_multi_completion_n_reserves_and_clamps_against_single_output_cap")


def main() -> int:
    test_router_metadata_json_rejects_plaintext_secret_material()
    test_read_json_body_rejects_chunked_body_before_buffering_past_limit()
    test_health_reports_unhealthy_without_central_chutes_key()
    test_health_and_models_report_configured_state_without_exposing_key()
    test_upstream_pool_config_is_public_and_secret_safe()
    test_chat_reuses_upstream_client_pool_within_event_loop()
    test_chat_non_streaming_forwards_to_fake_upstream_and_records_usage()
    test_router_usage_settlement_error_releases_reserved_row()
    test_chat_usage_queues_raven_low_fuel_notice_once()
    test_low_fuel_notice_without_channel_does_not_poison_dedupe()
    test_chat_uses_catalog_pricing_and_promotes_deprecated_models()
    test_catalog_refreshes_and_promotes_newer_family_model()
    test_startup_refresh_empty_response_does_not_empty_catalog()
    test_startup_refresh_non_tee_heavy_response_keeps_tee_allow_list()
    test_chat_promotes_missing_requested_model_to_latest_same_family()
    test_key_allowlist_blocks_global_default_replacement_and_fallback_escape()
    test_chat_preflight_rejects_invalid_model_and_size_limits()
    test_global_allowlist_reflects_synced_tee_catalog_without_restart()
    test_chat_preflight_enforces_budget_and_billing_fail_closed()
    test_chat_operator_observe_unlimited_is_server_authorized_and_metered()
    test_chat_spoofed_observe_unlimited_demotes_to_capped_lane_and_records_evidence()
    test_chat_preflight_enforces_rate_limit_and_concurrency()
    test_router_keys_verify_fail_closed_and_do_not_store_raw_material()
    test_router_auth_rejects_missing_invalid_and_suspended_keys()
    test_chat_streaming_passes_chunks_and_records_provider_usage()
    test_chat_upstream_errors_are_redacted_and_do_not_leak_reservations()
    test_chat_retries_configured_fallback_model_after_retryable_upstream_error()
    test_chat_fallback_uses_final_model_pricing_and_sanitized_attempt_audit()
    test_provider_side_fallback_csv_default_model_is_allowed_as_single_model_string()
    test_chat_streaming_retries_pre_stream_fallback_and_records_metadata()
    test_chat_partial_stream_failure_settles_without_prompt_or_secret_storage()
    test_open_reservations_count_against_budget_so_concurrency_cannot_overspend()
    test_stale_reservation_reaper_releases_leaked_rows_and_keeps_fresh()
    test_omitted_max_tokens_forwards_reservation_output_cap_upstream()
    test_default_model_marked_unavailable_is_not_forwarded()
    test_health_reports_allow_list_state_and_alerts_on_collapse()
    test_fresh_heartbeat_survives_old_read_timeout_window_and_settles_by_id()
    test_null_max_tokens_is_dropped_and_reservation_cap_injected()
    test_reaper_ttl_exceeds_upstream_read_window_so_slow_live_request_is_safe()
    test_all_max_output_keys_capped_no_largest_key_bypass()
    test_allow_list_collapse_alert_rearms_after_recovery()
    test_pre_response_retries_keep_live_reservation_heartbeated_across_windows()
    test_multi_completion_n_reserves_and_clamps_against_single_output_cap()
    print("PASS all 43 ArcLink LLM router tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
