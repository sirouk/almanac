#!/usr/bin/env python3
from __future__ import annotations

import json
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
    record = control.ensure_llm_router_key(
        conn,
        deployment_id="dep_1",
        user_id="user_1",
        secret_ref="secret://arclink/llm-router/dep_1/api-key",
        raw_key=raw_key,
        allowed_models=allowed_models or ["model-a", "model-b"],
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
    test_chat_promotes_missing_requested_model_to_latest_same_family()
    test_key_allowlist_blocks_global_default_replacement_and_fallback_escape()
    test_chat_preflight_rejects_invalid_model_and_size_limits()
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
    print("PASS all 28 ArcLink LLM router tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
