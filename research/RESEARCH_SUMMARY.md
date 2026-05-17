# Research Summary

<confidence>94</confidence>

## Scope

This PLAN pass inspected the public repository structure, the full LLM Router
steering document, the verified Sovereign audit brief, current research
artifacts, the live implementation plan, Compose/Docker dependency surfaces,
and the relevant Python/test surfaces for router, Chutes, provisioning,
Sovereign worker, hosted API, and Docker validation.

This pass did not inspect private state, live secrets, deploy keys, user Hermes
homes, production services, live Chutes/Stripe/Cloudflare/Tailscale/Notion
accounts, public bot registrations, remote hosts, or Hermes core.

## Mission Reconciliation

The active BUILD mission is the ArcLink Sovereign LLM Router. The authoritative
reference is `research/RALPHIE_ARCLINK_LLM_ROUTER_STEERING.md`; the live
backlog is `IMPLEMENTATION_PLAN.md`.

`research/RALPHIE_SOVEREIGN_AUDIT_VERIFICATION_20260511.md` remains a
regression gate, not the primary router backlog. Its closure revisit says the
previous FACT and actionable PARTIAL source gaps were handled locally. BUILD
should not reopen fiction or historical items without fresh source evidence,
but the router must preserve those trust-boundary repairs: shared redaction,
body caps, webhook trust checks, session/auth behavior, CIDR checks, rate
limits, and Docker user/socket posture.

## Current Source Findings

| Area | Current signal | BUILD consequence |
| --- | --- | --- |
| Router app | `python/arclink_llm_router.py` exists with FastAPI config, `/health`, authenticated `/v1/models`, authenticated `/v1/chat/completions`, non-streaming forwarding, streaming SSE passthrough, rate/concurrency checks, budget reservation/settlement, and sanitized usage recording. | Treat phases 1-4 as present in the dirty tree, then re-run focused validation before relying on them. |
| Router tests | `tests/test_arclink_llm_router.py` exists and covers health, models, key lifecycle, auth failure, model/request/budget/rate/concurrency failures, non-streaming success, streaming success, upstream error redaction, partial stream failure, no raw prompt/completion persistence, and no leaked reservations. | Keep these tests as the first validation target and extend only for new BUILD behavior. |
| Control DB | `python/arclink_control.py` contains router tables, indexes, key generation, hash-only registration, verification, revoke, rotate, and list helpers. | Reuse these helpers for worker registration and provisioning defaults. Note that generic `hash_token` is still SHA-256; a keyed verifier remains a security-hardening risk to evaluate. |
| Runtime dependencies | `Dockerfile` and `requirements-dev.txt` include FastAPI, uvicorn, and httpx. | Dependency lane is already present; keep Docker/test assertions aligned. |
| Chutes boundary | `python/arclink_chutes.py` still owns budget/billing boundary evaluation and sanitized usage ingestion. | Router should continue using this as the provider policy boundary rather than duplicating Chutes state logic. |
| Provisioning | `python/arclink_provisioning.py` still defaults ArcPod provider secret refs to `secret://arclink/chutes/<deployment_id>` and `ARCLINK_CHUTES_API_KEY_FILE=/run/secrets/chutes_api_key`. | Switch defaults to router URL plus `secret://arclink/llm-router/<deployment_id>/api-key`; keep direct Chutes only behind `ARCLINK_ALLOW_DIRECT_CHUTES_IN_ARCPODS=1`. |
| Sovereign worker | `python/arclink_sovereign_worker.py` maps `secret://arclink/chutes/` to `CHUTES_API_KEY`; generated secrets use generic `arc_...` values. | Add router-key generation/materialization and DB hash registration. Central Chutes materialization must not be the default ArcPod provider key path. |
| Compose | `compose.yaml` has `control-api` and worker services, but no `control-llm-router` service. | Add a dedicated uvicorn service with DB access, central Chutes env, healthcheck, no Docker socket, and appropriate internal/public routing. |
| Provider-state UI/API | Hosted API already exposes provider-state style surfaces for Chutes lifecycle data. | Extend only if needed to show sanitized router usage/quota; never expose raw keys, secret refs, prompts, or completions. |
| Docs/OpenAPI | API docs and OpenAPI exist; `docs/arclink/llm-router.md` also exists in the dirty tree. | Update API reference/OpenAPI/runbook once Compose/provisioning behavior is finalized. |

## Implementation Path Comparison

| Decision | Path A | Path B | Selected |
| --- | --- | --- | --- |
| Router process | Dedicated `control-llm-router` FastAPI/uvicorn service. | Fold routes into existing WSGI `control-api`. | Path A. Streaming and provider isolation fit ASGI and avoid coupling to browser/session API code. |
| Upstream relay | `httpx.AsyncClient.stream` with immediate chunk passthrough. | Synchronous or buffered forwarding. | Path A. Streaming without full buffering is non-negotiable and already implemented in source. |
| ArcPod provider default | Router URL plus per-deployment router key. | Continue direct Chutes default during migration. | Path A. The mission is to keep the central Chutes key out of ArcPods by default. |
| Router key materialization | Worker generates raw router key once, stores only hash in SQLite, materializes secret file/ref. | Store raw key in DB/metadata or reuse central Chutes key. | Path A. Raw key persistence and central-key sharing violate the contract. |
| Budget enforcement | Reserve before forwarding, settle/release after success/failure/stream end. | Post-hoc usage accounting only. | Path A. Preflight budget failure must fail closed. |
| Usage display | Add sanitized router ledger summaries to existing provider-state surfaces. | Build a new dashboard/API subsystem. | Path A. Existing surfaces are enough for v1 and reduce blast radius. |
| Hot counters | SQLite tables/rate scopes. | Redis/Postgres v1. | Path A. Current Control Node is SQLite-first; future swaps can use narrow interfaces. |

## Build Assumptions

- The current public source tree is the source of truth where older research
  artifacts disagree.
- Existing dirty work must be preserved; BUILD should patch only router,
  provisioning, worker, Compose, docs, and focused tests needed for this
  mission.
- ArcPods can consume an OpenAI-compatible base URL/key pair, so the router key
  can be installed where Hermes currently expects a provider key.
- Same-host ArcPods can use `http://control-llm-router:8090/v1`; remote fleet
  ArcPods require operator-provided `ARCLINK_LLM_ROUTER_PUBLIC_BASE_URL`.
- Live Chutes proof is forbidden unless the operator explicitly sets the router
  live-proof env gate.
- Tests must use fake upstream transports and synthetic keys by default.

## Risks

- Router keys currently use the shared `hash_token` helper, which is plain
  SHA-256 in source. The router meets "hash-only storage" but should consider a
  keyed verifier before production hardening is declared complete.
- Streaming client disconnect accounting can only be approximate unless the
  provider supplies usage chunks before disconnect.
- Provisioning default changes can break rollback unless the direct Chutes
  compatibility flag is explicit and tested.
- Remote fleet pods cannot reach an internal Compose service URL without an
  operator-provided router public/private ingress URL.
- Existing dirty files include unrelated fleet and plugin work; BUILD must
  avoid broad formatting or reversions.

## Verdict

PLAN is ready for BUILD handoff. The next BUILD slice should start at the
remaining integration boundary: ArcPod provisioning defaults, Sovereign worker
router-key materialization/registration, `control-llm-router` Compose wiring,
provider-state/docs/OpenAPI updates, then the validation floor in
`IMPLEMENTATION_PLAN.md`.
