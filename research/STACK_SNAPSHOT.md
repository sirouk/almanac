# Stack Snapshot

- generated_at: 2026-05-16
- project_type: existing public repository
- primary_stack: Python ASGI + SQLite + Docker Compose
- deterministic_confidence_score: 94/100

## Ranked Stack Hypotheses

| Rank | Stack hypothesis | Score | Evidence |
| --- | --- | --- | --- |
| 1 | Python backend/control plane with SQLite and shell-managed runtime | 94 | About 191 Python files, 79 shell scripts, `requirements-dev.txt`, large `python/arclink_control.py`, router/provisioning/worker modules, and Python test suite. |
| 2 | Docker Compose Control Node runtime | 86 | Root `compose.yaml`, `Dockerfile`, Docker-focused tests, Control Node services, and operator docker commands. |
| 3 | Next.js dashboard adjunct | 58 | `web/package.json`, React/Next/TypeScript files, Playwright tests; relevant for provider-state display but not router core. |
| 4 | Static docs/OpenAPI surface | 52 | `docs/API_REFERENCE.md`, `docs/openapi/arclink-v1.openapi.json`, router runbook/docs. |
| 5 | Standalone Node.js primary app | 18 | Some TypeScript/JavaScript exists, but backend/control/router surfaces are Python. |

## Deterministic Scoring Notes

Scoring used repository-level signals only:

- Backend/control source count and mission files: +40 Python.
- Existing test surface for target mission: +20 Python.
- Runtime declarations and Compose service model: +20 Compose/Python.
- Shell/deploy orchestration weight: +10 Python-adjacent runtime.
- Web/frontend relevance: capped because it is not the router core.

The earlier Node-first snapshot was rejected because it over-weighted a small
frontend file count and under-weighted the Python control-plane source and
tests.

## Selected Stack For BUILD

- FastAPI app in `python/arclink_llm_router.py`.
- uvicorn `control-llm-router` Compose service.
- httpx async upstream client and streaming relay.
- SQLite tables and helpers in `python/arclink_control.py`.
- Existing Chutes boundary logic in `python/arclink_chutes.py`.
- Existing provisioning/worker surfaces for ArcPod router URL/key rollout.

## Alternatives

| Alternative | Disposition |
| --- | --- |
| Reuse WSGI `control-api` for OpenAI-compatible streaming | Rejected; ASGI is a better fit and avoids hosted API session coupling. |
| Add Redis/Postgres hot counters in v1 | Deferred; SQLite-first matches current Control Node architecture. |
| Add tokenizer dependency now | Deferred; provider usage plus deterministic fallback is enough for source-level v1. |
| Continue direct Chutes keys in ArcPods by default | Rejected; violates the router mission. |
