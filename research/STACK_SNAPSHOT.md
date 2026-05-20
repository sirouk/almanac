# Stack Snapshot

- generated_at: 2026-05-20T03:06:40Z
- project_root: .
- primary_stack: Python control plane + shell orchestration + Docker Compose
- primary_score: 094/100
- confidence: high

## Project Stack Ranking

| rank | stack | score | evidence |
| --- | --- | --- | --- |
| 1 | Python backend/control plane | 094 | `requirements-dev.txt`, about 192 Python files, `python/arclink_control.py`, hosted API, provisioning, executor, fleet, provider, router, MCP, Notion, memory, and broad `tests/test_arclink_*.py` coverage |
| 2 | Shell-managed host runtime | 088 | `deploy.sh`, `bin/deploy.sh`, many `bin/*.sh` host lifecycle scripts, systemd service templates, and shell validation guidance |
| 3 | Docker Compose Control Node runtime | 086 | Root `compose.yaml`, `Dockerfile`, Control Node services, Docker health paths, and Docker-focused regression tests |
| 4 | Next.js dashboard adjunct | 058 | `web/package.json`, `web/src/**`, and browser tests support the product UI but are not the primary backend/runtime |
| 5 | Static docs/OpenAPI surface | 052 | `docs/**`, `research/**`, root docs, and OpenAPI artifacts describe and validate the public contract |
| 6 | Standalone Node.js app | 018 | TypeScript/JavaScript exists mainly under `web/`; it does not dominate control-plane runtime behavior |

## Deterministic Alternatives Ranking
- Candidate evaluation is based on repository-level manifests, source volume,
  runtime entrypoints, and test ownership.
- The earlier Node-first result was rejected because it over-weighted frontend
  file counts and under-weighted Python control-plane entrypoints, shell
  lifecycle scripts, Compose services, and Python regression coverage.

### Top 3 stack alternatives (ranked)
- 1) Python backend/control plane: score=094, evidence=`python/**`, `tests/test_arclink_*.py`, `requirements-dev.txt`
- 2) Shell-managed host runtime: score=088, evidence=`deploy.sh`, `bin/*.sh`, service install/health scripts
- 3) Docker Compose Control Node runtime: score=086, evidence=`compose.yaml`, `Dockerfile`, Docker/Control Node tests
