# Ralphie Steering: ArcLink Sovereign LLM Router

## Mission

Build the production ArcLink LLM Router: a central Sovereign Control Node
service that exposes an OpenAI-compatible API to each ArcPod, verifies a
separate ArcLink-issued key per deployment, streams requests to Chutes, meters
tokens/cost, enforces quotas, and keeps raw Chutes credentials out of ArcPods.

This is a source-level implementation mission. Live Chutes proof is
operator-gated and must not run unless an operator explicitly sets the live
proof env gate for that phase.

## Core Product Contract

ArcPods do not talk directly to `https://llm.chutes.ai/v1` in production.
They talk to ArcLink:

```text
Hermes in ArcPod
  -> ArcLink LLM Router /v1/chat/completions
  -> auth, quota, billing, budget reservation, rate/concurrency checks
  -> llm.chutes.ai/v1
  -> streamed response back to Hermes
  -> usage ledger and budget settlement
```

Each ArcPod gets a separate ArcLink LLM key that behaves like a provider API
key from Hermes' perspective. The Control Node stores only a hash and metadata.
The central Chutes account key stays in the Control Node service environment or
secret store and is never mounted into ArcPods.

## Non-Negotiable Requirements

- Separate key per deployment/ArcPod; key verification must map to exactly one
  deployment and one Captain.
- Store only key hashes, never raw keys, in SQLite.
- Router must be OpenAI-compatible enough for Hermes:
  - `GET /v1/models`
  - `POST /v1/chat/completions`
  - streaming and non-streaming chat completions
  - forward compatible handling for extra OpenAI/Chutes fields
- Use a performant Python ASGI stack:
  - FastAPI
  - uvicorn
  - httpx async streaming upstream client
- Stream responses without buffering whole completions.
- Meter usage for both non-streaming and streaming paths.
- Enforce quota before sending upstream; settle actual usage after completion.
- Fail closed on missing billing, missing budget, exhausted budget, revoked key,
  invalid model, over-limit request, rate limit, or missing central Chutes
  credential.
- Do not persist raw prompts or completions by default.
- Do not add raw Chutes keys to deployment compose secrets.
- Keep existing direct-provider behavior available only behind an explicit
  compatibility flag while migration is underway.
- Keep all live/provider calls operator-gated in tests.

## Existing Code To Reuse

- `python/arclink_chutes.py`
  - `evaluate_chutes_deployment_boundary`
  - `record_chutes_usage_event`
  - budget state and billing suspension logic
- `python/arclink_control.py`
  - schema creation and migration helpers
  - `hash_token`
  - `append_arclink_event`
  - `check_arclink_rate_limit`
- `python/arclink_provisioning.py`
  - render ArcPod compose intent
  - inject Hermes provider base URL and provider key secret file
- `python/arclink_sovereign_worker.py`
  - materialize generated `secret://` refs
  - persist generated deployment secrets
- `compose.yaml`
  - add a new control-plane service, do not overload `control-api`
- `bin/install-deployment-hermes-home.sh`
  - writes Hermes provider config for deployment homes
- `docs/openapi/arclink-v1.openapi.json` and `docs/API_REFERENCE.md`
  - document any externally reachable control-plane API surfaces

## Desired Runtime Topology

Control Node compose should have a dedicated service:

```text
control-llm-router
  command: python -m uvicorn arclink_llm_router:app --host 0.0.0.0 --port 8090
  env:
    ARCLINK_DB_PATH
    ARCLINK_LLM_ROUTER_ENABLED=1
    ARCLINK_LLM_ROUTER_CHUTES_BASE_URL=https://llm.chutes.ai/v1
    ARCLINK_LLM_ROUTER_CHUTES_API_KEY or CHUTES_API_KEY
    ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS
    ARCLINK_LLM_ROUTER_CENTS_PER_MILLION_INPUT_TOKENS
    ARCLINK_LLM_ROUTER_CENTS_PER_MILLION_OUTPUT_TOKENS
  healthcheck: GET /health
```

For same-host deployments, ArcPods can use the Docker control network URL:

```text
http://control-llm-router:8090/v1
```

For remote fleet deployments, provisioning must support:

```text
ARCLINK_LLM_ROUTER_PUBLIC_BASE_URL
```

so ArcPods on other workers can reach the central router through the operator's
chosen private/public ingress path.

## Schema

Add idempotent schema:

```text
arclink_llm_router_keys
  key_id TEXT PRIMARY KEY
  deployment_id TEXT NOT NULL
  user_id TEXT NOT NULL
  key_hash TEXT NOT NULL
  secret_ref TEXT NOT NULL
  status TEXT CHECK active/revoked/suspended
  allowed_models_json TEXT DEFAULT '[]'
  metadata_json TEXT DEFAULT '{}'
  created_at TEXT NOT NULL
  last_seen_at TEXT DEFAULT ''
  revoked_at TEXT DEFAULT ''

arclink_llm_usage_events
  usage_id TEXT PRIMARY KEY
  request_id TEXT NOT NULL
  deployment_id TEXT NOT NULL
  user_id TEXT NOT NULL
  provider TEXT NOT NULL
  model TEXT NOT NULL
  input_tokens INTEGER DEFAULT 0
  output_tokens INTEGER DEFAULT 0
  total_tokens INTEGER DEFAULT 0
  estimated_cents INTEGER DEFAULT 0
  actual_cents INTEGER DEFAULT 0
  status TEXT CHECK reserved/succeeded/failed/cancelled
  stream INTEGER DEFAULT 0
  source_kind TEXT DEFAULT ''
  error_summary TEXT DEFAULT ''
  started_at TEXT NOT NULL
  completed_at TEXT DEFAULT ''

arclink_llm_budget_reservations
  reservation_id TEXT PRIMARY KEY
  request_id TEXT NOT NULL
  deployment_id TEXT NOT NULL
  user_id TEXT NOT NULL
  reserved_cents INTEGER NOT NULL
  settled_cents INTEGER DEFAULT 0
  status TEXT CHECK reserved/settled/released/failed
  created_at TEXT NOT NULL
  settled_at TEXT DEFAULT ''
```

Indexes:

- active key lookup by key hash
- usage by deployment/time
- usage by user/time
- reservations by request/status

## Key Lifecycle

Add helpers in `arclink_control.py` or a small dedicated module:

- `ensure_llm_router_key(conn, deployment_id, user_id, secret_ref, raw_key)`
- `verify_llm_router_key(conn, raw_key)`
- `revoke_llm_router_key(conn, key_id, actor_id, reason)`
- `rotate_llm_router_key(...)`
- `list_llm_router_keys_for_deployment(...)`

Raw key format:

```text
acpod_live_<short_key_id>_<urlsafe_secret>
```

No raw key should appear in logs, API responses, docs, or tests except
synthetic fixtures.

## Provisioning Changes

ArcPod provisioning should render:

```text
ARCLINK_CHUTES_BASE_URL=<router /v1 URL>
ARCLINK_CHUTES_API_KEY_FILE=/run/secrets/llm_router_api_key
ARCLINK_LLM_ROUTER_API_KEY_REF=secret://arclink/llm-router/<deployment_id>/api-key
```

and should remove direct Chutes API key material from ArcPod compose secrets by
default.

`managed-context-install`, `hermes-gateway`, and `hermes-dashboard` should use
the ArcLink router key as the provider key because Hermes still expects an
OpenAI-compatible key. The server-side router uses the central Chutes key to
talk upstream.

Compatibility flag:

```text
ARCLINK_ALLOW_DIRECT_CHUTES_IN_ARCPODS=1
```

may preserve the old direct behavior for emergency rollback only. Default must
be router mode.

## Router Behavior

For every `/v1/chat/completions` request:

1. Extract Bearer token or OpenAI-style `Authorization: Bearer ...`.
2. Verify active deployment key.
3. Fetch deployment and Captain state.
4. Evaluate Chutes boundary and billing status.
5. Enforce model allowlist and request size/output limits.
6. Estimate input/output token budget.
7. Check rate limit and concurrency limit.
8. Reserve budget.
9. Forward request to Chutes with the central server-side key.
10. Stream or return response.
11. Extract provider usage if present.
12. Fall back to deterministic token estimate if provider usage is absent.
13. Record sanitized usage event.
14. Settle/release reservation.
15. Update deployment metadata via `record_chutes_usage_event`.

No raw prompt/completion storage. Redact all upstream error messages before
returning them or writing events.

## Streaming Requirements

- Use `httpx.AsyncClient.stream`.
- Do not read the entire upstream response into memory.
- Preserve `text/event-stream` for streaming responses.
- If the client disconnects, close/cancel upstream and settle partial usage.
- Support provider usage chunks when available.
- Request `stream_options.include_usage=true` where compatible, without
  breaking clients that already set stream options.
- Never do heavy analytics on the stream path.

## Performance And Scale

Source-level v1 may use SQLite because the current Control Node is SQLite-first.
Design the code so Redis/Postgres can replace hot counters later.

Minimum controls now:

- per-key request/minute limit
- per-deployment request/minute limit
- per-Captain request/minute limit
- per-deployment concurrent request cap
- request body max bytes
- max prompt estimate
- max output tokens

Future-ready seams:

- rate limiter interface
- budget ledger interface
- upstream provider interface
- tokenizer/estimator interface

## Tests Required

Add focused tests:

- key issue/verify/revoke/rotate
- provisioning no longer mounts raw Chutes key by default
- provisioning points provider base URL to router URL
- router rejects missing/invalid/revoked key
- router rejects exhausted budget
- router rejects past-due billing
- router forwards non-streaming request and records usage
- router streams SSE chunks without buffering and records usage
- router redacts upstream errors
- router never stores prompt/completion text
- route docs/OpenAPI/API references updated if public routes are exposed

Run at minimum:

```bash
python3 -m py_compile python/arclink_llm_router.py python/arclink_chutes.py python/arclink_control.py python/arclink_provisioning.py python/arclink_sovereign_worker.py
python3 tests/test_arclink_llm_router.py
python3 tests/test_arclink_chutes_and_adapters.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_arclink_sovereign_worker.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_docker.py
bash -n deploy.sh bin/*.sh test.sh
```

If dependencies are missing locally, record the blocker and add the declared
dependencies correctly.

## Live Proof Gate

Do not call live Chutes by default.

A live proof may run only when all are set:

```text
ARCLINK_LLM_ROUTER_LIVE_CHUTES_PROOF=1
ARCLINK_LLM_ROUTER_CHUTES_API_KEY=<central key>
ARCLINK_LLM_ROUTER_LIVE_MODEL=<approved scratch model>
ARCLINK_LLM_ROUTER_LIVE_MAX_CENTS=<small bound>
```

The live proof must use a scratch deployment/key, bounded prompt, tiny
`max_tokens`, and must write redacted evidence only.

## Dirty-Tree Safety

This repository currently may contain unrelated local work from fleet and Code
plugin tasks. Ralphie must:

- preserve unrelated dirty files
- avoid broad refactors
- avoid reverting files it did not need
- list every touched file in completion notes
- treat changes outside the LLM router/provisioning/docs/test surface as
  suspect unless directly required

## Done Means

- ArcPods are configured to use ArcLink LLM Router keys by default.
- Central Chutes key stays only on the Control Node/router service.
- Router authenticates a per-deployment key and maps it to one ArcPod/Captain.
- Router enforces billing, budget, rate, concurrency, and model limits.
- Router supports streaming and non-streaming chat completions.
- Usage ledger and provider-state surfaces show token/cost consumption.
- Tests prove the no-secret, quota, streaming, and provisioning contracts.
- Live Chutes proof remains explicitly operator-gated unless the operator
  enables the live proof environment variables.
