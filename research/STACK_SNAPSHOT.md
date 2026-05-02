# Stack Snapshot

- generated_at: 2026-05-02
- project_root: .
- primary_stack: Python
- primary_score: 092/100
- confidence: high

## Project Stack Ranking

| rank | stack | score | evidence |
| --- | --- | --- | --- |
| 1 | Python | 092 | requirements-dev.txt, 46 Python modules, 86+ test files, control plane, API, adapters, provisioning, executor |
| 2 | Bash | 070 | 70+ shell scripts in bin/, deploy.sh, test.sh, init.sh for host/Docker orchestration |
| 3 | Node.js / TypeScript | 025 | Next.js 15 + Tailwind 4 web app (9 source files, ~1,593 lines), 2 web test files, package.json |
| 4 | Docker | 020 | compose.yaml, Dockerfile, Docker scripts, compose-based runtime |
| 5 | Go | 000 | - |
| 6 | Rust | 000 | - |

## Deterministic Alternatives Ranking

- Candidate evaluation is based on repository-level manifest and source signals only.
- Primary decision rule: highest score, then explicit manifest precedence.

### Top 3 stack alternatives (ranked)

- 1) Python: score=092, evidence=[requirements-dev.txt, 46 Python modules, 86+ test files, 17 ArcLink modules (7,303 lines), 132 ArcLink test functions]
- 2) Bash: score=070, evidence=[70+ shell scripts, deploy/health/Docker/onboarding orchestration]
- 3) Node.js/TypeScript: score=025, evidence=[Next.js 15 + Tailwind 4 web app, 9 source files (~1,593 lines), 2 web test files]

## Architecture Summary

Python is the primary implementation language for the control plane, API
boundary, billing/entitlements, provisioning, executor, adapters, dashboard
read models, and all test coverage. Bash handles host-level operations,
deployment, health checks, and Docker orchestration. Node.js/TypeScript powers
the production web app (Next.js 15 + Tailwind 4) which consumes the Python
hosted API. Docker Compose is the runtime substrate for both development and
production deployment.
