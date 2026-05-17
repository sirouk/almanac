# ArcLink LLM Router

The ArcLink LLM Router is the Control Node boundary for ArcPod inference. It
exposes an OpenAI-compatible surface to Hermes while keeping the central Chutes
credential in the Control Node, not in ArcPods.

Current source status: the FastAPI router, SQLite schema, key lifecycle helpers,
policy checks, Chutes relay, streaming relay, usage settlement, provider-state
usage summaries, Control Node Compose service, ArcPod provisioning defaults, and
fake-upstream tests exist locally. Live Chutes proof remains operator-gated.

## Ownership

| Surface | Owner |
| --- | --- |
| Router ASGI app | `python/arclink_llm_router.py` |
| Key and usage schema | `python/arclink_control.py` |
| Billing and budget boundary | `python/arclink_chutes.py` |
| ArcPod provider rendering | `python/arclink_provisioning.py`, `python/arclink_sovereign_worker.py` |
| Compose service | `compose.yaml` service `control-llm-router` |
| Runtime dependencies | `Dockerfile`, `requirements-dev.txt` |
| Focused tests | `tests/test_arclink_llm_router.py`, hosted provider-state tests |

The router is intentionally separate from `control-api`. `control-api` remains
the hosted WSGI API under `/api/v1`; the router is an OpenAI-compatible ASGI
service with its own `/v1` routes.

## Runtime Contract

| Route | Auth | Behavior |
| --- | --- | --- |
| `GET /health` | None | Reports enabled/configured state without exposing the upstream credential |
| `GET /v1/models` | Bearer router key | Returns the allowed model list for the ArcPod key, or the router default list |
| `POST /v1/chat/completions` | Bearer router key | Validates policy, reserves budget, relays to Chutes, returns streaming or JSON response, and records sanitized usage |

Router keys use the `acpod_live_...` format. Only hashes and metadata are stored
in SQLite. Raw keys may be returned or materialized only at the one-time
generation boundary and must not be logged, committed, or exposed through API
responses.

The stored key digest currently uses the shared SHA-256 token hash helper. This
is acceptable for the router production boundary because router keys are
ArcLink-generated high-entropy API keys, not human-memorable passwords or short
tokens. A keyed HMAC would add defense in depth if the SQLite DB is copied
without the application environment, but it would require a migration and shared
pepper distribution across worker and router processes. That migration is
deferred until the wider session/token hash migration rail is revisited.

## Request Policy

Before forwarding a chat request upstream, the router:

1. Requires `Authorization: Bearer <router-key>`.
2. Verifies the active key maps to exactly one deployment and one Captain.
3. Rejects torn-down deployments, inactive users, revoked keys, and suspended
   keys.
4. Enforces the key/deployment model allowlist.
5. Enforces request body, prompt estimate, and `max_tokens` caps.
6. Evaluates the Chutes billing and budget boundary.
7. Checks per-key, per-deployment, and per-Captain request-per-minute limits.
8. Checks the per-deployment concurrency cap.
9. Creates a budget reservation before sending the request to Chutes.

Successful and failed upstream calls settle or release reservations. The router
records token and cost usage in `arclink_llm_usage_events` and updates the
existing Chutes metadata ledger. It stores request id, deployment id, user id,
model, token counts, estimated/actual cents, status, stream flag, source kind,
safe error summary, and timestamps. It does not store raw prompts or
completions.

`/user/provider-state` and `/admin/provider-state` include an `llm_router`
summary for each deployment plus aggregate counts in `chutes_summary`. Those
payloads expose only credential counts, open reservation cents, request counts,
token counts, estimated/actual cents, status counts, and the budget/quota view.
They do not return raw router keys, central Chutes credentials, secret refs,
prompts, or completions.

## ArcPod Defaults

Provisioned ArcPods use the router by default:

```text
ARCLINK_CHUTES_BASE_URL=<router /v1 URL>
ARCLINK_CHUTES_API_KEY_FILE=/run/secrets/llm_router_api_key
ARCLINK_LLM_ROUTER_API_KEY_REF=secret://arclink/llm-router/<deployment_id>/api-key
```

Same-network Control Node deployments use
`http://control-llm-router:8090/v1`. Remote fleet deployments may use
`ARCLINK_LLM_ROUTER_PUBLIC_BASE_URL` to point at the operator-selected ingress.
Direct Chutes key mounting is retained only behind
`ARCLINK_ALLOW_DIRECT_CHUTES_IN_ARCPODS=1` for compatibility rollback.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `ARCLINK_DB_PATH` | none | Control-plane SQLite path |
| `ARCLINK_LLM_ROUTER_ENABLED` | `1` | Enables router policy and upstream forwarding |
| `ARCLINK_LLM_ROUTER_CHUTES_API_KEY` | none | Central Chutes credential used only by the router |
| `ARCLINK_LLM_ROUTER_CHUTES_BASE_URL` | `https://llm.chutes.ai/v1` | Upstream Chutes-compatible base URL |
| `ARCLINK_LLM_ROUTER_DEFAULT_MODEL` | Chutes Kimi default | Default model when no per-key allowlist is set |
| `ARCLINK_LLM_ROUTER_ALLOWED_MODELS` | default model | Comma-separated router-level model allowlist |
| `ARCLINK_LLM_ROUTER_MAX_BODY_BYTES` | `1048576` | Request body cap |
| `ARCLINK_LLM_ROUTER_PROMPT_ESTIMATE_TOKEN_CAP` | `120000` | Prompt estimate cap |
| `ARCLINK_LLM_ROUTER_MAX_TOKENS_CAP` | `8192` | Output token request cap |
| `ARCLINK_LLM_ROUTER_DEPLOYMENT_CONCURRENCY_LIMIT` | `4` | Open reservation cap per deployment |
| `ARCLINK_LLM_ROUTER_KEY_REQUESTS_PER_MINUTE` | `60` | Per-key request limit |
| `ARCLINK_LLM_ROUTER_DEPLOYMENT_REQUESTS_PER_MINUTE` | `120` | Per-deployment request limit |
| `ARCLINK_LLM_ROUTER_USER_REQUESTS_PER_MINUTE` | `300` | Per-Captain request limit |
| `ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS` | `0` | Router-side Chutes budget fallback |
| `ARCLINK_LLM_ROUTER_CENTS_PER_MILLION_INPUT_TOKENS` | `20` | Fallback input-token cost estimate |
| `ARCLINK_LLM_ROUTER_CENTS_PER_MILLION_OUTPUT_TOKENS` | `80` | Fallback output-token cost estimate |
| `ARCLINK_LLM_ROUTER_PUBLIC_BASE_URL` | none | Public/private ingress base URL for remote ArcPods |
| `ARCLINK_ALLOW_DIRECT_CHUTES_IN_ARCPODS` | `0` | Compatibility flag to restore direct Chutes key mounting |

## Proof Boundary

Local tests use a fake async upstream transport and must not call live Chutes.
Live proof is not claimed by the source-level router tests. A live proof run
must be explicitly bounded by this router gate:

```text
ARCLINK_LLM_ROUTER_LIVE_CHUTES_PROOF=1
ARCLINK_LLM_ROUTER_CHUTES_API_KEY=<secret supplied outside docs>
ARCLINK_LLM_ROUTER_LIVE_MODEL=<approved scratch model>
ARCLINK_LLM_ROUTER_LIVE_MAX_CENTS=<small bound>
```

Focused source checks:

```bash
python3 -m py_compile python/arclink_llm_router.py python/arclink_control.py python/arclink_chutes.py
PYTHONPATH=python:tests python3 tests/test_arclink_llm_router.py
```
