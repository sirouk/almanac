# Dependency Research

## Scope

This document records public stack and dependency signals for the ArcLink
Sovereign LLM Router mission. It does not assert live access to Stripe, Chutes,
Telegram, Discord, Notion, Cloudflare, Tailscale, production Docker hosts, or
remote SSH targets.

## Stack Components

| Component | Evidence | Router mission use | Decision |
| --- | --- | --- | --- |
| Python 3 | Backend modules and tests are primarily Python. | Router app, control DB helpers, Chutes boundary, provisioning, worker tests. | Primary backend implementation surface. |
| FastAPI | Present in runtime/dev dependency lanes and router module imports. | ASGI route definitions for `/health`, `/v1/models`, and `/v1/chat/completions`. | Use for the dedicated router service. |
| uvicorn | Present in runtime/dev dependency lanes. | Run `control-llm-router`. | Use in Compose command. |
| httpx | Present in runtime/dev dependency lanes; router uses `AsyncClient`. | Async Chutes client and streaming passthrough. | Use directly in the router boundary. |
| SQLite | `python/arclink_control.py`. | Router keys, usage ledger, budget reservations, rate/concurrency state. | Reuse current control DB; no new DB for v1. |
| Chutes helpers | `python/arclink_chutes.py`. | Billing/budget boundary and sanitized usage ingestion. | Reuse and extend integration, not duplicate provider policy. |
| Shell | `deploy.sh`, `bin/*.sh`. | Validation and install helpers. | Keep shell changes narrow. |
| Docker Compose | `compose.yaml`, `Dockerfile`. | Dedicated router service and runtime dependency availability. | Add `control-llm-router` with no Docker socket. |
| Next.js web | `web/package.json`, `web/src/`. | Optional dashboard/provider-state consumption display. | Use existing web stack only if UI changes are needed. |
| Redaction/evidence | `python/arclink_secrets_regex.py`. | Safe upstream errors, no key/prompt leakage, live-proof evidence. | Reuse shared redaction. |

## Version Snapshot

| Lane | Public signal | Planning note |
| --- | --- | --- |
| Runtime image | Node 22 Debian slim plus Python/runtime tools and `requests`, FastAPI, uvicorn, httpx. | Dependency lane already supports router imports. |
| Dev Python dependencies | Includes jsonschema, Discord/PyNaCl/PyYAML, requests, FastAPI, uvicorn, httpx, Playwright, pyflakes, ruff. | Local router tests should import without hidden dependency setup after `requirements-dev.txt` install. |
| Existing HTTP clients | `requests` remains for synchronous provider modules; router uses httpx async. | Do not retrofit unrelated modules during router BUILD. |
| Web app | Next 15, React 19, TypeScript 5, ESLint 9, Playwright. | Web changes require web validation; avoid unless provider-state display needs it. |
| Repository shape | About 191 Python files, 79 shell scripts, 4 TypeScript files, 3 JavaScript files, plus Compose/Docker. | Primary router stack is Python ASGI + SQLite + Compose. |

## Alternatives Compared

| Decision | Preferred | Alternatives | Reason |
| --- | --- | --- | --- |
| HTTP framework | FastAPI | Existing WSGI hosted API, Flask, raw ASGI | FastAPI is required by steering and fits ASGI streaming. |
| Server | uvicorn | gunicorn/WSGI, hypercorn | uvicorn is requested and simple for Compose. |
| Upstream client | httpx async streaming | `requests`, urllib, buffered httpx calls | `httpx.AsyncClient.stream` supports immediate SSE passthrough. |
| Data store | Additive SQLite tables | Separate DB, Redis/Postgres v1 | Current Control Node is SQLite-first; future counters can be abstracted later. |
| Token accounting | Provider usage plus deterministic fallback | Add tokenizer dependency in v1 | Keeps dependencies small while preserving bounded accounting. |
| Rate limiting | Existing SQLite rate table plus router scopes | Redis/leaky-bucket service | Adequate for source-level v1 and testability. |
| Provisioning migration | Router by default, direct Chutes compatibility flag | Direct Chutes default until later migration | Router default is the product contract. |

## External Integration Posture

| Integration | Local BUILD posture | Live posture |
| --- | --- | --- |
| SQLite DB | Temporary test DBs and idempotent migration tests. | No private runtime DB reads. |
| Chutes upstream | Fake async upstreams and synthetic provider responses. | Live calls only with explicit router live-proof env gate. |
| Docker Compose | Static/fake tests for service wiring and socket posture. | No production compose mutation. |
| ArcPod provisioning | Render intents in tests; no deployment apply required. | Live deploy/upgrade remains operator-gated. |
| Provider-state dashboard | Local route tests and web tests if touched. | No production dashboard mutation. |
| Payments/bots/Notion/Cloudflare/Tailscale | Not needed for local router BUILD. | Blocked unless separately authorized. |

## Dependency Risks

- Router tests require FastAPI/httpx test dependencies to be installed locally.
- SQLite rate and concurrency checks must keep transactions short so streaming
  paths are not blocked by long-held DB handles.
- Provider usage chunks may be absent on streaming responses; fallback
  estimates must be deterministic and conservative.
- Compose wiring can accidentally inherit privileged mounts; Docker tests must
  assert the router has no Docker socket.
- Direct Chutes compatibility must not keep central Chutes keys mounted into
  ArcPods by default.

## Validation Dependencies

Minimum local validation for router BUILD:

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
