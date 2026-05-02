# Stack Snapshot

- generated_at: 2026-05-02T12:00:00Z
- project_root: .
- primary_stack: Python
- primary_score: 095/100
- confidence: very_high

## Project Stack Ranking

| rank | stack | score | evidence |
| --- | --- | --- | --- |
| 1 | Python | 095 | requirements-dev.txt, 148 Python source/test files, 19 ArcLink modules (8,293 lines), 21 ArcLink test files (190 tests), control plane, API, executor, adapters, diagnostics |
| 2 | Node.js / TypeScript | 040 | Next.js 15 web app (9 source files, ~1,593 lines), Playwright browser tests, package.json, tsconfig.json |
| 3 | Bash | 030 | 79 shell scripts in bin/, deploy.sh, init.sh for orchestration and operations |
| 4 | Docker | 025 | compose.yaml (16 services, 4 profiles), Dockerfile, Docker executor module |
| 5 | .NET | 000 | - |
| 6 | Go | 000 | - |
| 7 | Java | 000 | - |
| 8 | Ruby | 000 | - |
| 9 | Rust | 000 | - |

## Deterministic Alternatives Ranking

- Candidate evaluation is based on repository-level manifest and source signals only.
- Primary decision rule: highest score, then explicit manifest precedence.

### Top 3 stack alternatives (ranked)

- 1) Python: score=095, evidence=[requirements-dev.txt, 148 Python files, 19 ArcLink modules, hosted WSGI API, control plane]
- 2) Node.js/TypeScript: score=040, evidence=[Next.js 15 + Tailwind 4 web app, 9 source files, Playwright tests, package.json]
- 3) Bash: score=030, evidence=[79 shell scripts, deploy/ops orchestration]

## Stack Confidence Rationale

Python is unambiguously the primary stack. The entire control plane, API
boundary, executor, all provider adapters, diagnostics, host readiness, and all
190 ArcLink Python test functions are Python. Node.js/TypeScript serves the production
web frontend only. Bash handles deploy/ops orchestration. Docker is the
provisioning substrate. No alternative stack is viable for the core product.
