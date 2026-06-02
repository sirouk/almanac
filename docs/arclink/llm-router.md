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
| Chutes account/usage/key/introspect adapter (TEST-ONLY, UNWIRED) | `python/arclink_chutes_live.py` |
| Chutes OAuth connect/callback/disconnect helpers (TEST-ONLY, UNWIRED) | `python/arclink_chutes_oauth.py` |
| Focused tests | `tests/test_arclink_llm_router.py`, hosted provider-state tests |

`python/arclink_chutes_live.py` and `python/arclink_chutes_oauth.py` are present
in the tree but are **not wired into the running router** — see
[Provider-Connection Adapters](#provider-connection-adapters-test-only-unwired)
below for what they are and what proof gate blocks them.

The router is intentionally separate from `control-api`. `control-api` remains
the hosted WSGI API under `/api/v1`; the router is an OpenAI-compatible ASGI
service with its own `/v1` routes.

## Runtime Contract

| Route | Auth | Behavior |
| --- | --- | --- |
| `GET /health` | None | Reports enabled/configured state without exposing the upstream credential |
| `GET /v1/models` | Bearer router key | Returns the allowed model list for the ArcPod key, or the router default list |
| `POST /v1/chat/completions` | Bearer router key | Validates policy, reserves budget, relays to Chutes, returns streaming or JSON response, and records sanitized usage |

Router keys use the `acpod_live_...` format. Only keyed HMAC hashes and
metadata are stored in SQLite. Raw keys may be returned or materialized only at
the one-time generation boundary and must not be logged, committed, or exposed
through API responses.

The stored key digest uses HMAC-SHA256 with
`ARCLINK_LLM_ROUTER_KEY_HASH_PEPPER` when set, falling back to the existing
`ARCLINK_SESSION_HASH_PEPPER`. Legacy SHA-256 router-key rows are accepted only
for verification migration; the successful verify path rewrites them to the
keyed HMAC format. Raw-key storage and prompt/completion storage stay rejected.

## Request Policy

Before forwarding a chat request upstream, the router:

1. Requires `Authorization: Bearer <router-key>`.
2. Verifies the active key maps to exactly one deployment and one Captain.
3. Rejects torn-down deployments, inactive users, revoked keys, and suspended
   keys.
4. Enforces the key/deployment model allowlist, then resolves configured model
   replacements or catalog-marked deprecations before forwarding.
5. Enforces request body, prompt estimate, and `max_tokens` caps.
6. Evaluates the Chutes billing and budget boundary.
7. Checks per-key, per-deployment, and per-Captain request-per-minute limits.
8. Checks the per-deployment concurrency cap.
9. Creates a budget reservation before sending the request to Chutes.

Successful and failed upstream calls settle or release reservations. The router
records token and cost usage in `arclink_llm_usage_events` and updates the
existing Chutes metadata ledger. It stores request id, deployment id, user id,
resolved upstream model, token counts, estimated/actual cents, status, stream
flag, source kind, safe error summary, and timestamps. It does not store raw
prompts or completions.

The upstream provider path is served through a bounded async keepalive pool, not
a new network client per request. The pool is created per ASGI event loop,
closed on shutdown, and warmed on startup by a safe `/models` probe when the
router is configured. Health exposes only pool shape and warmup status, never
provider credentials. Pool limits are intentionally separate from per-key,
per-deployment, and per-Captain request limits: rate and budget policy decide
who may ask, while the upstream pool protects the provider boundary under load.

When `arclink_model_catalog` contains current Chutes pricing, reservations and
settled usage use the selected model's `input_cents_per_million` and
`output_cents_per_million`. The environment price values are only a fallback for
unknown models or a stale catalog.

## ArcPod Refueling

Raven can open ArcPod Refueling after a Captain has a live Agent. ArcPod fuel is
the prepaid model budget available to that Agent's Pod. The default Checkout
product is `ArcPod Refueling`; operators can bind it to a stable Stripe Product
by setting `ARCLINK_REFUEL_STRIPE_PRODUCT_ID`, or let Checkout use inline
product data. Stripe Checkout uses `mode=payment`, not a subscription. On
`checkout.session.completed`, ArcLink grants an `arclink_refuel_credits` ledger
row and applies it to the owning ArcPod's metered router budget. The webhook
validates that the Checkout customer,
`client_reference_id`, Captain account, and target ArcPod all match before any
credit is granted.

Default retail conversion keeps ArcLink profitable before Stripe/platform
overhead:

| Captain pays | Metered provider budget | Retained gross margin |
| --- | --- | --- |
| `$10` | `$7` | `$3` |
| `$25` | `$17.50` | `$7.50` |
| `$50` | `$35` | `$15` |
| `$100` | `$70` | `$30` |

Those numbers come from `ARCLINK_REFUEL_PROVIDER_CREDIT_BPS=7000`. Change that
single value to adjust gross margin. The available refueling package sizes come from
`ARCLINK_REFUEL_TOPUP_AMOUNTS_CENTS`, and custom amounts are bounded by
`ARCLINK_REFUEL_TOPUP_MIN_CENTS` and `ARCLINK_REFUEL_TOPUP_MAX_CENTS`.

The token capacity shown to the Captain is only a reference estimate. Real
spend is settled by the router against the selected model's current catalog
price. If a Captain changes models, or ArcLink promotes a fleet from Kimi K2.6
to Kimi K2.7, the same dollar credit naturally buys the amount of usage allowed
by the new catalog price.

When the router records usage that crosses the warning threshold, it queues a
Raven `public-bot-user` notification with a **Refuel ArcPod** button. The notice
is deduped per ArcPod fuel tank so usage accounting stays automatic without
slowing the Agent's response path.

## Monthly Subscription Inference Allowance

Paid monthly subscription renewals also replenish inference budget. When Stripe
sends `invoice.payment_succeeded` or `invoice.paid` for a paid invoice, ArcLink
resolves the Captain from subscription/customer local state, applies the
configured plan allowance to that Captain's active ArcPods, and records each
grant as `source_kind='stripe_subscription_renewal'`. The source id is
`<invoice_id>:<deployment_id>`, so duplicate Stripe aliases for the same invoice
are idempotent.

By default the monthly allowance is 20% of plan retail:

| Plan | Retail/month | Default monthly inference allowance |
| --- | ---: | ---: |
| Founders | `$149` | `$29.80` |
| Sovereign | `$199` | `$39.80` |
| Scale | `$275` | `$55.00` |
| Sovereign extra Agent | `$99` | `$19.80` |
| Scale extra Agent | `$79` | `$15.80` |

`ARCLINK_SUBSCRIPTION_INFERENCE_CREDIT_BPS` controls the global percentage, and
the plan-specific `ARCLINK_*_MONTHLY_INFERENCE_CREDIT_CENTS` variables override
individual rows. When multiple active ArcPods share the same plan, ArcLink
splits that plan's monthly allowance across them deterministically instead of
granting the full plan amount to every Pod.

`/user/provider-state` and `/admin/provider-state` include an `llm_router`
summary for each deployment plus aggregate counts in `chutes_summary`. Those
payloads expose only credential counts, open reservation cents, request counts,
token counts, estimated/actual cents, status counts, and the budget/quota view.
They do not return raw router keys, central Chutes credentials, secret refs,
prompts, or completions. These two routes are part of the hosted WSGI API under
`/api/v1`; for their full request/response contract, auth, and CORS rules see
[docs/API_REFERENCE.md](../API_REFERENCE.md) and the generated
[OpenAPI spec](../openapi/arclink-v1.openapi.json) rather than duplicating the
route catalog here.

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
When a placement host is marked remote through fleet metadata, the ArcPod
renderer prefers `ARCLINK_CONTROL_PRIVATE_BASE_URL`,
`ARCLINK_WIREGUARD_CONTROL_URL`, or `ARCLINK_PRIVATE_MESH_CONTROL_URL`, then
derives `<control-url>/v1` for inference plus `<control-url>/api/v1/...` for the
share-request broker. `ARCLINK_TAILSCALE_CONTROL_URL` remains a compatibility
fallback/access-overlay lane. Remote pods do not join the control-node Docker
network.
Direct Chutes key mounting is retained only behind
`ARCLINK_ALLOW_DIRECT_CHUTES_IN_ARCPODS=1` for compatibility rollback.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `ARCLINK_DB_PATH` | none | Control-plane SQLite path |
| `ARCLINK_LLM_ROUTER_ENABLED` | `1` | Enables router policy and upstream forwarding |
| `ARCLINK_LLM_ROUTER_CHUTES_API_KEY` | none | Central Chutes credential used only by the router |
| `ARCLINK_LLM_ROUTER_KEY_HASH_PEPPER` | session pepper fallback | Optional router-specific HMAC pepper for stored ArcPod router key hashes |
| `ARCLINK_LLM_ROUTER_CHUTES_BASE_URL` | `https://llm.chutes.ai/v1` | Upstream Chutes-compatible base URL |
| `ARCLINK_LLM_ROUTER_DEFAULT_MODEL` | Chutes Kimi default | Default model when no per-key allowlist is set |
| `ARCLINK_LLM_ROUTER_ALLOWED_MODELS` | default model | Comma-separated router-level model allowlist |
| `ARCLINK_LLM_ROUTER_FALLBACK_MODELS` | none | Comma-separated router-owned fallback models attempted after retryable provider errors |
| `ARCLINK_LLM_ROUTER_FALLBACK_STATUS_CODES` | `429,500,502,503,504` | Provider status codes that trigger a fallback attempt when fallback models remain |
| `ARCLINK_LLM_ROUTER_MODEL_AUTO_PROMOTE` | `1` | Allows newer/deprecated/unavailable catalog rows to route to their replacement or latest same-family active model |
| `ARCLINK_LLM_ROUTER_MODEL_REPLACEMENTS` | none | Comma-separated `old-model=new-model` overrides for emergency promotion |
| `ARCLINK_LLM_ROUTER_REFRESH_MODEL_CATALOG_ON_STARTUP` | `1` | Refreshes Chutes `/models` into `arclink_model_catalog` when the router starts |
| `ARCLINK_LLM_ROUTER_MARK_MISSING_MODELS_UNAVAILABLE` | `1` | Marks previously active catalog rows unavailable after a successful refresh omits them |
| `ARCLINK_LLM_ROUTER_MODEL_CATALOG_AUTH_STRATEGY` | `bearer` | Auth strategy for catalog refresh: `bearer`, `x-api-key`, or `none` |
| `ARCLINK_LLM_ROUTER_MAX_BODY_BYTES` | `1048576` | Request body cap |
| `ARCLINK_LLM_ROUTER_PROMPT_ESTIMATE_TOKEN_CAP` | `120000` | Prompt estimate cap |
| `ARCLINK_LLM_ROUTER_MAX_TOKENS_CAP` | `8192` | Output token request cap |
| `ARCLINK_LLM_ROUTER_DEPLOYMENT_CONCURRENCY_LIMIT` | `4` | Open reservation cap per deployment |
| `ARCLINK_LLM_ROUTER_KEY_REQUESTS_PER_MINUTE` | `60` | Per-key request limit |
| `ARCLINK_LLM_ROUTER_DEPLOYMENT_REQUESTS_PER_MINUTE` | `120` | Per-deployment request limit |
| `ARCLINK_LLM_ROUTER_USER_REQUESTS_PER_MINUTE` | `300` | Per-Captain request limit |
| `ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS` | `0` (router code default) / `2500` (Compose `control-llm-router` service default) | Router-side Chutes budget fallback. `load_router_config` floors this at `0` in code; the deployed `control-llm-router` Compose service overrides it to `2500`, so a Pod without an explicit configured budget inherits a `$25` fallback. Always treat the per-deployment configured budget as authoritative. |
| `ARCLINK_LLM_ROUTER_CENTS_PER_MILLION_INPUT_TOKENS` | `95` | Fallback input-token cost estimate for the default Kimi lane |
| `ARCLINK_LLM_ROUTER_CENTS_PER_MILLION_OUTPUT_TOKENS` | `400` | Fallback output-token cost estimate for the default Kimi lane |
| `ARCLINK_LLM_ROUTER_UPSTREAM_CONNECT_TIMEOUT_SECONDS` | `5` | Upstream TCP/TLS connect timeout |
| `ARCLINK_LLM_ROUTER_UPSTREAM_READ_TIMEOUT_SECONDS` | `300` | Upstream read timeout; long enough for streaming pauses without hanging forever |
| `ARCLINK_LLM_ROUTER_UPSTREAM_WRITE_TIMEOUT_SECONDS` | `30` | Upstream request-body write timeout |
| `ARCLINK_LLM_ROUTER_UPSTREAM_POOL_TIMEOUT_SECONDS` | `5` | Maximum wait for a free pooled upstream connection |
| `ARCLINK_LLM_ROUTER_UPSTREAM_MAX_CONNECTIONS` | `256` | Global upstream connection cap per router worker |
| `ARCLINK_LLM_ROUTER_UPSTREAM_MAX_KEEPALIVE_CONNECTIONS` | `64` | Idle upstream keepalive cap per router worker |
| `ARCLINK_LLM_ROUTER_UPSTREAM_KEEPALIVE_EXPIRY_SECONDS` | `90` | Idle upstream connection lifetime |
| `ARCLINK_LLM_ROUTER_UPSTREAM_WARMUP_ENABLED` | `1` | Warm the provider pool on router startup when configured |
| `ARCLINK_LLM_ROUTER_PUBLIC_BASE_URL` | none | Public/private ingress base URL for remote ArcPods |
| `ARCLINK_CONTROL_PRIVATE_BASE_URL` | none | Preferred Control Node private mesh HTTPS base URL used by remote ArcPods for control API and router URLs |
| `ARCLINK_WIREGUARD_CONTROL_URL` | none | WireGuard-specific alias for `ARCLINK_CONTROL_PRIVATE_BASE_URL` |
| `ARCLINK_PRIVATE_MESH_CONTROL_URL` | none | Generic private-mesh alias for `ARCLINK_CONTROL_PRIVATE_BASE_URL` |
| `ARCLINK_TAILSCALE_CONTROL_URL` | none | Compatibility fallback Control Node Tailscale HTTPS base URL when private/public control URLs are not set |
| `ARCLINK_ALLOW_DIRECT_CHUTES_IN_ARCPODS` | `0` | Compatibility flag to restore direct Chutes key mounting |
| `ARCLINK_REFUEL_STRIPE_PRODUCT_ID` | none | Optional reusable Stripe Product id for ArcPod Refueling Checkout |
| `ARCLINK_REFUEL_STRIPE_PRODUCT_NAME` | `ArcPod Refueling` | Inline Checkout product display name when no product id is configured |
| `ARCLINK_REFUEL_TOPUP_AMOUNTS_CENTS` | `1000,2500,5000,10000` | Raven refueling package sizes |
| `ARCLINK_REFUEL_TOPUP_MIN_CENTS` | `500` | Minimum custom refueling amount |
| `ARCLINK_REFUEL_TOPUP_MAX_CENTS` | `50000` | Maximum custom refueling amount |
| `ARCLINK_REFUEL_PROVIDER_CREDIT_BPS` | `7000` | Retail-to-metered-budget conversion basis points |
| `ARCLINK_REFUEL_REFERENCE_MODEL` | router default model | Display-only model name used in refueling capacity estimates |
| `ARCLINK_SUBSCRIPTION_INFERENCE_CREDIT_BPS` | `2000` | Monthly subscription retail converted into included inference budget |
| `ARCLINK_FOUNDERS_MONTHLY_INFERENCE_CREDIT_CENTS` | `$29.80` | Override Founders monthly included inference budget |
| `ARCLINK_SOVEREIGN_MONTHLY_INFERENCE_CREDIT_CENTS` | `$39.80` | Override Sovereign monthly included inference budget |
| `ARCLINK_SCALE_MONTHLY_INFERENCE_CREDIT_CENTS` | `$55.00` | Override Scale monthly included inference budget |
| `ARCLINK_SOVEREIGN_AGENT_EXPANSION_MONTHLY_INFERENCE_CREDIT_CENTS` | `$19.80` | Override Sovereign extra-Agent monthly included inference budget |
| `ARCLINK_SCALE_AGENT_EXPANSION_MONTHLY_INFERENCE_CREDIT_CENTS` | `$15.80` | Override Scale extra-Agent monthly included inference budget |

Control Node install asks for the default model string and allowed-model list.
If the selected provider supports provider-side model fallback, the default
model can be a provider-accepted CSV string such as `model-a,model-b`.
Separately, `ARCLINK_LLM_ROUTER_FALLBACK_MODELS` enables an ArcLink-owned
bounded retry cascade for configured retryable statuses. The local
implementation covers non-streaming chat completion fallback and streaming
fallback before any upstream chunks have been emitted. Once a streaming response
has started, the router does not pretend it can safely replay the request; it
emits explicit router metadata that streaming fallback is unavailable after the
stream has started, settles the reservation, and records the failed stream
without prompt or chunk text. The local `GAP-031-A` slice landed this sanitized
fallback audit, pre-stream fallback retry, no-replay-after-stream labeling,
fallback-aware reservation pricing, and final-model settlement pricing. Only the
authorized live overload proof remains, tracked by `GAP-031` behind the
`PG-PROVIDER` proof gate.

Fallback attempts are audited as sanitized `llm_router:fallback_attempt` events.
Usage and reservation rows include metadata for requested, primary, final,
reservation-pricing, and usage-pricing models so cost-different fallbacks are
visible. When catalog prices are available, the request reservation accounts for
the highest configured fallback candidate cost and settlement uses the final
model actually used.

Streaming fallback is deliberately split into a pre-stream lane and a
post-stream lane so the router never silently replays a partially-delivered
response. Sanitized usage/audit metadata records a `streaming_fallback` value
drawn from this fixed taxonomy:

| `streaming_fallback` value | Meaning |
| --- | --- |
| `pre_stream` | The upstream returned a retryable status before any chunk was emitted; the router advanced to the next fallback candidate and emitted a leading `arclink_router` SSE metadata frame. |
| `not_available` | A pre-stream failure occurred but no further fallback candidate remained; the stream failed without replay. |
| `unavailable_after_stream_started` | The first chunk had already been yielded when a later upstream error occurred; the router refuses to replay, emits a sanitized error SSE frame, and settles the reservation. |
| `failed_after_stream_started` | The recorded outcome label for a stream that errored after chunks were yielded (paired with `unavailable_after_stream_started`). |

The same no-replay invariant applies to non-streaming fallback only in that it
never reuses an already-emitted response: non-streaming requests retry the next
candidate cleanly because nothing was sent to the Captain yet. Live provider
proof of this cascade remains tracked by `GAP-031` behind the `PG-PROVIDER`
proof gate; the local fallback semantics above are implemented and tested
locally with the fake async upstream transport.

## Model Catalog And Promotion

The Control Node stores Chutes model catalog rows in `arclink_model_catalog`.
Rows include capabilities, confidential-compute support, per-million input and
output cents, status, replacement model, inferred family, version sort key, and
raw provider metadata. On router startup, ArcLink refreshes the catalog from
Chutes `/models` with the central router credential and marks omitted active
models `unavailable` only after that refresh succeeds.

Promotion policy is centralized in the router:

- If `ARCLINK_LLM_ROUTER_MODEL_REPLACEMENTS` maps the requested model, the
  router forwards to the configured replacement.
- If the catalog row is `deprecated` or `unavailable` and has
  `replacement_model_id`, the router forwards to that replacement.
- If auto-promotion is enabled and no explicit replacement exists, the router
  forwards old active, deprecated, or unavailable requests to the latest active
  model in the same inferred family when a newer version appears.
- The Captain/Agent can keep requesting the old allowed model id; the router
  records and bills the resolved upstream model. This lets the Operator move a
  whole fleet from Kimi K2.6 to K2.7 without rewriting every ArcPod immediately.

## Provider-Connection Adapters (TEST-ONLY, UNWIRED)

ArcLink carries two provider-connection modules that model a richer Chutes
account relationship than the running router uses today. Neither is imported by
the router, the hosted API, provisioning, or entitlements — they exist only with
their own focused tests and the public-repo hygiene test, and every live effect
is proof-gated. State both halves honestly: the code shape is implemented and
tested locally, but no live OAuth-backed or account-API path runs.

- **`python/arclink_chutes_live.py` (`ChutesLiveAdapter`)** is a secret-ref
  boundary over the Chutes account, usage, key, and OAuth-introspection APIs
  (account profile, subscription usage, per-user usage, quotas, discounts, price
  overrides, API-key create/delete, scope listing, token introspection, balance
  transfer). It ships a `FakeChutesLiveTransport` with fixtures for tests. Read
  calls run against the injected transport; every mutation
  (`create_api_key`, `delete_api_key`, `transfer_balance`) is refused unless
  `allow_live_mutation=True`, raising a `ChutesLiveAdapterError` that states the
  operation is "proof-gated until operator authorizes live mutation." This
  adapter is **not wired into the running router** and has no production caller.
- **`python/arclink_chutes_oauth.py`** holds PKCE (`S256`) connect/callback/
  disconnect helpers backed by in-memory state/token stores and a
  `FakeChutesOAuthCodeExchanger`. `ChutesOAuthConnectPlan.to_public()` reports
  `connect_status: "proof_gated_until_authorized_oauth_client_is_configured"`,
  and `disconnect_chutes_oauth(revoke_live=True)` is proof-gated. There is no
  live OAuth client configured and no callback route mounted on the router or
  the hosted API.

The Chutes deployment boundary in `python/arclink_chutes.py` recognizes a
`per_user_chutes_account_oauth` isolation mode and a matching
`account_oauth_required` credential state (surfaced when
`ARCLINK_CHUTES_PER_KEY_METERING_AVAILABLE` /
`ARCLINK_CHUTES_KEY_METERING_AVAILABLE` indicate per-key metering is
unavailable). This is a **posture/label only**: there is no code path that
performs OAuth-backed inference, so an ArcPod cannot today route inference
through a Captain's own Chutes account. Treat both the isolation mode and the
credential state as proof-gated and unwired until a live OAuth-backed lane is
built and proven. The live-relay proof itself is tracked by `GAP-031` behind the
`PG-PROVIDER` proof gate (see [GAPS.md](../../GAPS.md) for the gap taxonomy).

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
