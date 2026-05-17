# Implementation Plan: ArcLink Sovereign LLM Router

## Goal

Land the ArcLink Sovereign LLM Router: a Control Node service that gives every
ArcPod a per-deployment ArcLink LLM key, verifies that key like an
OpenAI-compatible provider key, relays requests to the central Chutes account,
streams responses back to Hermes, enforces billing/quota/rate/concurrency
limits, and records sanitized token/cost usage per ArcPod and Captain.

Authoritative steering reference:
`research/RALPHIE_ARCLINK_LLM_ROUTER_STEERING.md`

Security regression reference:
`research/RALPHIE_SOVEREIGN_AUDIT_VERIFICATION_20260511.md`

## Current Ground Truth

- `python/arclink_llm_router.py` exists in the current source tree and contains the
  core FastAPI router, health/models/chat routes, non-streaming forwarding,
  streaming passthrough, preflight policy checks, budget reservation/settlement,
  and sanitized usage recording.
- `tests/test_arclink_llm_router.py` exists and exercises the core router
  behavior through fake upstream transports and temporary SQLite DBs.
- `python/arclink_control.py` contains router schema, indexes, and key
  lifecycle helpers.
- `Dockerfile` and `requirements-dev.txt` already include FastAPI, uvicorn, and
  httpx.
- `compose.yaml` includes a dedicated `control-llm-router` service.
- ArcPod provisioning defaults to router base URL/key refs and keeps direct
  Chutes only behind `ARCLINK_ALLOW_DIRECT_CHUTES_IN_ARCPODS=1`.
- `python/arclink_sovereign_worker.py` materializes/registers router keys
  idempotently for deployments.
- Docs/OpenAPI and provider-state surfaces include the local router integration
  and live-proof guard.

## Build Constraints

- Do not touch `arclink-priv`, live secrets, deploy keys, production services,
  public bot registrations, payment/provider mutations, or Hermes core.
- Do not run live Chutes calls unless the operator explicitly sets the live
  router proof env gate.
- Do not persist raw prompts, completions, central Chutes keys, or raw router
  keys.
- Preserve unrelated dirty work. If a touched file has unrelated hunks, make
  the smallest compatible patch and report it.
- Keep changes in the existing Python, shell, SQLite, Compose, docs, and
  Next/web stack. Do not introduce Redis/Postgres or a new gateway framework.

## Selected Path

| Decision | Selected path | Rejected / deferred alternatives |
| --- | --- | --- |
| Router runtime | Dedicated FastAPI app run by uvicorn in `control-llm-router`. | Folding streaming routes into WSGI `control-api` rejected. |
| Upstream relay | `httpx.AsyncClient.stream` for streaming and httpx async calls for non-streaming. | `requests`/urllib buffering rejected. |
| Key storage | Per-deployment raw key generated once, keyed HMAC hash stored in SQLite with legacy SHA migration, raw materialized as deployment secret only. | Raw key DB/metadata storage rejected. |
| ArcPod default | Router base URL and router key by default. | Direct Chutes default rejected; keep only behind `ARCLINK_ALLOW_DIRECT_CHUTES_IN_ARCPODS=1`. |
| Budget handling | Reserve before forwarding; settle/release after response using provider usage or deterministic fallback. | Post-hoc-only metering rejected. |
| Usage ledger | Router-specific request rows plus existing Chutes metadata update. | Metadata-only accounting rejected. |
| Live proof | Explicit env-gated scratch proof only. | CI/live-by-default proof rejected. |

## Phase Tasks

### Phase 1 - Core Router Already Present, Revalidate First

- [x] FastAPI, uvicorn, and httpx are present in runtime/dev dependency lanes.
- [x] `python/arclink_llm_router.py` provides the FastAPI app, config loader,
  `/health`, `GET /v1/models`, and `POST /v1/chat/completions`.
- [x] `tests/test_arclink_llm_router.py` provides fake async upstream
  transport and temporary SQLite DB coverage.
- [x] `/health` reports unhealthy when router is enabled without the central
  Chutes credential and does not expose secret material.
- [x] Re-run `python3 -m py_compile python/arclink_llm_router.py` and
  `python3 tests/test_arclink_llm_router.py` before editing downstream
  integration.

### Phase 2 - Schema, Key Lifecycle, And Auth Already Present, Revalidate

- [x] SQLite schema exists for `arclink_llm_router_keys`,
  `arclink_llm_usage_events`, and `arclink_llm_budget_reservations`.
- [x] Indexes exist for active key lookup, usage by deployment/user/time, and
  open reservations by request/status.
- [x] `ensure_llm_router_key`, `verify_llm_router_key`,
  `revoke_llm_router_key`, `rotate_llm_router_key`, and list helpers exist.
- [x] Key format follows `acpod_live_<short_key_id>_<urlsafe_secret>`.
- [x] Tests assert raw router keys are absent from key, usage, event, and
  deployment metadata rows.
- [x] Router key hashes use HMAC-SHA256 with a router-specific pepper when set,
  session pepper fallback, and legacy SHA migration on successful verify.

### Phase 3 - Policy, Budget, Rate, And Concurrency Already Present, Revalidate

- [x] Router evaluates Chutes billing/budget state through
  `evaluate_chutes_deployment_boundary`.
- [x] Router fails closed for missing budget, exhausted budget, past-due
  billing, missing central credential, invalid/revoked/suspended keys, invalid
  models, request caps, rate limit, and concurrency cap.
- [x] Router creates budget reservations before upstream forwarding and
  settles/releases them after success/failure.
- [x] Re-run focused router tests and extend only if a new provisioning/worker
  behavior changes preflight assumptions.

### Phase 4 - Chutes Relay And Usage Settlement Already Present, Revalidate

- [x] Non-streaming forwarding uses the central server-side Chutes credential.
- [x] Streaming forwarding uses `httpx.AsyncClient.stream` and
  `text/event-stream` passthrough.
- [x] Streaming requests add `stream_options.include_usage=true` when
  compatible.
- [x] Router extracts provider usage when present and falls back to
  deterministic estimates.
- [x] Router records sanitized usage events and updates Chutes metadata without
  storing prompts/completions.
- [x] Upstream errors are redacted before response/storage.
- [x] Re-run router tests after any docs/Compose/provider-state changes to
  confirm no regressions.

### Phase 5 - Provisioning, Worker, And Compose Wiring

- [x] Change provisioning defaults to render router base URL and
  `secret://arclink/llm-router/<deployment_id>/api-key`.
- [x] Keep direct Chutes key behavior only behind
  `ARCLINK_ALLOW_DIRECT_CHUTES_IN_ARCPODS=1`.
- [x] Ensure `managed-context-install`, `hermes-gateway`, and
  `hermes-dashboard` receive the router key file and router `/v1` base URL by
  default.
- [x] Update `python/arclink_sovereign_worker.py` to generate/materialize the
  router key secret and register its hash in SQLite during apply.
- [x] Add `control-llm-router` to `compose.yaml` with no Docker socket,
  `ARCLINK_DB_PATH`, router env, Chutes credential env, healthcheck, and
  appropriate internal/public routing.
- [x] Support `ARCLINK_LLM_ROUTER_PUBLIC_BASE_URL` for remote fleet ArcPods and
  same-network `http://control-llm-router:8090/v1` for local Control Node
  deployments.

Validation criteria:

- [x] Provisioning tests prove no central Chutes key is mounted into ArcPods by
  default.
- [x] Worker tests prove router key secret generation is stable/idempotent and
  hash registration is repaired if missing.
- [x] Docker tests prove the router service exists, is healthchecked, has no
  Docker socket, and has the expected env.

### Phase 6 - Provider-State, Docs, OpenAPI, And Live-Proof Guard

- [x] Extend provider-state/dashboard surfaces, if needed, to show sanitized
  router usage/quota per deployment/Captain.
- [x] Update `docs/API_REFERENCE.md` and
  `docs/openapi/arclink-v1.openapi.json` for `/v1/models`,
  `/v1/chat/completions`, auth failures, quota failures, and live-proof policy.
- [x] Update `docs/arclink/llm-router.md` and related Control Node runbooks
  with the router topology, default ArcPod provider config, compatibility flag,
  and operational health checks.
- [x] Document live proof env gate:
  `ARCLINK_LLM_ROUTER_LIVE_CHUTES_PROOF=1`,
  `ARCLINK_LLM_ROUTER_CHUTES_API_KEY`,
  `ARCLINK_LLM_ROUTER_LIVE_MODEL`, and
  `ARCLINK_LLM_ROUTER_LIVE_MAX_CENTS`.
- [x] Ensure tests never call live Chutes unless the explicit gate is set.
- [x] Update completion notes after BUILD with validation and residual risks.

Validation criteria:

- [x] API docs contain no synthetic secrets beyond clearly fake fixtures.
- [x] Live proof path is disabled by default and bounded when explicitly
  enabled.
- [x] Provider-state payloads contain usage/quota only, not keys, secret refs,
  prompts, or completions.

## Wave 1 Security Regression Gate

Before and after router BUILD slices, verify current trust-boundary surfaces
from `research/RALPHIE_SOVEREIGN_AUDIT_VERIFICATION_20260511.md`: Telegram and
Discord webhooks, hosted API body/auth/CIDR/JSON/CORS behavior, session/CSRF
hashing, shared redaction, webhook rate limiting, and Docker user/socket
posture. If source or tests show a current regression, fix it with a focused
test before continuing router work. Do not re-open fiction/outdated items
without fresh source evidence.

## Validation Floor

Run at minimum:

```bash
git diff --check
python3 -m py_compile python/arclink_llm_router.py python/arclink_chutes.py python/arclink_control.py python/arclink_provisioning.py python/arclink_sovereign_worker.py
python3 tests/test_arclink_llm_router.py
python3 tests/test_arclink_chutes_and_adapters.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_arclink_sovereign_worker.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_docker.py
bash -n deploy.sh bin/*.sh test.sh
```

When web files change:

```bash
cd web
npm test
npm run lint
npm run build
npm run test:browser
```

## Done Means

- [x] A new Control Node LLM router service exists and is wired into Compose.
- [x] ArcPods get per-deployment ArcLink LLM keys by default.
- [x] Router verifies keys and maps each request to exactly one
  deployment/Captain.
- [x] Router enforces billing, budget, model allowlist, request limits, rate
  limits, and concurrency before forwarding.
- [x] Router streams and non-streams through Chutes using the central server
  credential only.
- [x] Usage is recorded per ArcPod/Captain without storing prompt/completion
  text.
- [x] Provider-state/dashboard surfaces can show sanitized consumption.
- [x] Tests prove invalid/revoked/exhausted/past-due paths and success paths.
- [x] Live Chutes proof remains explicitly operator-gated unless the operator
  enables the live proof environment variables.

## Explicit Deferrals

- Redis/Postgres-backed hot counters.
- Exact tokenizer dependency for model-specific token accounting.
- Multi-provider router support beyond Chutes.
- Public internet ingress automation for remote fleet workers beyond honoring
  `ARCLINK_LLM_ROUTER_PUBLIC_BASE_URL`.
- Live Chutes proof without operator env gate and bounded scratch deployment.
