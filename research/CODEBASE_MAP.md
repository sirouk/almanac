# Codebase Map

## Scope

This map covers public repository surfaces relevant to the ArcLink Sovereign
LLM Router. It excludes private state, live credentials, generated runtime
state, dependency folders, production services, and Hermes core.

## Planning Entrypoints

| Path | Responsibility |
| --- | --- |
| `IMPLEMENTATION_PLAN.md` | Live BUILD backlog for the LLM Router mission. |
| `research/RALPHIE_ARCLINK_LLM_ROUTER_STEERING.md` | Authoritative product and runtime steering reference. |
| `research/RALPHIE_SOVEREIGN_AUDIT_VERIFICATION_20260511.md` | Historical Wave 1 security regression reference. |
| `consensus/build_gate.md` | Local BUILD scope and blocked live/private actions. |

## Directory Map

| Directory / file | Role |
| --- | --- |
| `python/` | Control DB, router app, Chutes boundary, provisioning renderer, Sovereign worker, hosted API, redaction, provider-state payloads. |
| `tests/` | Focused regression tests for router, Chutes, provisioning, worker, hosted API, Docker, and schema behavior. |
| `bin/` | Canonical deploy/control scripts, install helpers, Docker job loops, shell validation surface. |
| `compose.yaml` | Dockerized Control Node services; target for `control-llm-router`. |
| `Dockerfile` | Runtime image and Python dependency install lane. |
| `requirements-dev.txt` | Local test/lint dependency lane. |
| `web/` | Next.js dashboard; optional sanitized usage/quota display surface. |
| `docs/` | API reference, OpenAPI JSON, and operator runbooks. |
| `research/` | Ralphie steering, research artifacts, and completion notes. |
| `consensus/` | Build gate and phase gate artifacts. |

## Architecture Rails

| Rail | Current files | Architecture assumption |
| --- | --- | --- |
| Router ASGI app | `python/arclink_llm_router.py` | FastAPI owns OpenAI-compatible routes, request preflight, Chutes relay, streaming, and usage settlement. |
| Control schema | `python/arclink_control.py` | SQLite remains the control-plane store; router schema and helpers are additive and idempotent. |
| Router keys | `generate_llm_router_raw_key`, `ensure_llm_router_key`, `verify_llm_router_key`, `revoke_llm_router_key`, `rotate_llm_router_key` | Raw keys are generated at materialization time and stored only as hashes in SQLite. |
| Chutes policy | `python/arclink_chutes.py` | Billing/budget/isolation checks and sanitized usage metadata stay centralized here. |
| Provisioning | `python/arclink_provisioning.py` | ArcPod compose intent and Hermes provider env must default to router URL/key refs. |
| Secret materialization | `python/arclink_sovereign_worker.py` | Worker should generate/materialize router keys and register key hashes during apply. |
| Hermes provider config | `bin/install-deployment-hermes-home.sh` | Hermes continues to receive OpenAI-compatible provider settings; the key file becomes the router key by default. |
| Compose runtime | `compose.yaml`, `Dockerfile` | Dedicated uvicorn service is required; router does not need Docker socket access. |
| Provider state | `python/arclink_hosted_api.py` | Existing dashboard/API surfaces can expose sanitized router usage/quota. |
| Redaction | `python/arclink_secrets_regex.py` | Use shared redaction for upstream errors and evidence; do not add competing regexes. |
| Docs/OpenAPI | `docs/API_REFERENCE.md`, `docs/openapi/arclink-v1.openapi.json`, `docs/arclink/llm-router.md` | Document router auth, routes, quota failures, and live-proof gate. |

## Current Entrypoints

| Entrypoint | Current state | BUILD target |
| --- | --- | --- |
| `python/arclink_llm_router.py` | Present with health, models, chat completions, policy checks, forwarding, streaming, usage settlement. | Re-run validation and integrate with provisioning/Compose. |
| `control-api` service | Existing WSGI hosted API on port 8900. | Keep for web/admin API; do not overload with streaming router traffic. |
| `control-provisioner` / Sovereign worker | Applies ArcPod intents and materializes secrets. | Generate/register router key before compose apply. |
| `python/arclink_provisioning.py` | Still renders direct Chutes secret ref and key file by default. | Default to router URL and `llm_router_api_key`; direct Chutes only by compatibility flag. |
| `bin/install-deployment-hermes-home.sh` | Installs Hermes provider config from env/key file. | Should work if env remains OpenAI-compatible; update only if explicit router names are required. |
| `tests/test_arclink_llm_router.py` | Present with fake upstream tests. | Keep as router core regression suite. |

## Missing BUILD Surfaces

| Surface | Target files |
| --- | --- |
| Provisioning router default | `python/arclink_provisioning.py`, `tests/test_arclink_provisioning.py` |
| Worker router-key materialization and DB registration | `python/arclink_sovereign_worker.py`, `tests/test_arclink_sovereign_worker.py` |
| Compose router service | `compose.yaml`, `tests/test_arclink_docker.py` |
| Provider-state consumption summary | `python/arclink_hosted_api.py`, hosted API/web tests if touched |
| Router docs and OpenAPI | `docs/API_REFERENCE.md`, `docs/openapi/arclink-v1.openapi.json`, `docs/arclink/llm-router.md` |
| Final validation notes | `research/BUILD_COMPLETION_NOTES.md`, `mission_status.md` if used by the phase runner |

## Architecture Assumptions

- The router is stateless apart from SQLite key, reservation, rate, and usage
  rows.
- Each active router key maps to exactly one deployment and one Captain/user.
- Billing, budget, model, request, rate, and concurrency checks happen before
  upstream forwarding.
- Prompt and completion payloads are not persisted by default.
- The central Chutes credential is present only on the Control Node/router
  service, not in ArcPod compose secrets.
- Fake upstreams are the default test boundary; live Chutes calls are proof
  gates, not CI.
