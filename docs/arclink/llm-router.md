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
| `ARCLINK_LLM_ROUTER_DEFAULT_MONTHLY_BUDGET_CENTS` | `0` | Router-side Chutes budget fallback |
| `ARCLINK_LLM_ROUTER_CENTS_PER_MILLION_INPUT_TOKENS` | `95` | Fallback input-token cost estimate for the default Kimi lane |
| `ARCLINK_LLM_ROUTER_CENTS_PER_MILLION_OUTPUT_TOKENS` | `400` | Fallback output-token cost estimate for the default Kimi lane |
| `ARCLINK_LLM_ROUTER_PUBLIC_BASE_URL` | none | Public/private ingress base URL for remote ArcPods |
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
