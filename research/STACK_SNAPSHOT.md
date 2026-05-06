# Stack Snapshot

- generated_at: 2026-05-06
- project_root: .
- primary_stack: Python
- primary_score: 094/100
- confidence: high

## Project Stack Ranking

| rank | stack | score | evidence |
| --- | --- | --- | --- |
| 1 | Python | 094 | requirements-dev.txt, 167 source files (control plane, plugin APIs, provisioning, tests, proof runner) |
| 2 | Shell | 072 | 80 scripts (deploy, Docker, health, plugin install, service orchestration) |
| 3 | Node.js | 024 | package.json, 4 JS bundles (3 plugin + 1 SW), 16 TS/TSX files (Next.js product app) |
| 4 | Docker | 018 | Dockerfile, compose.yaml, Docker wrapper scripts |
| 5 | .NET | 000 | - |
| 6 | Go | 000 | - |
| 7 | Java | 000 | - |
| 8 | Ruby | 000 | - |
| 9 | Rust | 000 | - |

## Deterministic Alternatives Ranking

- Candidate evaluation is based on repository-level manifest and source signals only.
- Primary decision rule: highest source-file count weighted by implementation role, then explicit manifest precedence.
- Counts exclude `arclink-priv/` private state, `node_modules/`, `__pycache__/`, `.next/`, and generated caches.

### Top 3 stack alternatives (ranked)

- 1) Python: score=094, evidence=[requirements-dev.txt, 167 source files spanning control plane, plugin APIs, provisioning, Docker supervisor, dashboards, hosted API, adapters, proof runner, and 24+ test files]
- 2) Shell: score=072, evidence=[80 scripts spanning deploy, Docker, health, onboarding, plugin install, service management, and operational wrappers]
- 3) Node.js: score=024, evidence=[package.json, 3 plugin JS bundles, 1 service worker, 16 TS/TSX files for Next.js product/admin surface and Playwright config]

## Architecture Summary

ArcLink is a Python and shell control-plane repository with a Docker Compose
runtime and native Hermes dashboard plugins (Drive, Code, Terminal). The
Node.js/Next.js app is an important product/admin surface but is not the
primary implementation path for the active workspace plugin mission. Plugin
frontends are plain JavaScript/CSS bundles loaded by the Hermes dashboard host.
