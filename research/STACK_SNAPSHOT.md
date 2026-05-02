# Stack Snapshot

- generated_at: 2026-05-02T14:00:00Z
- project_root: .
- primary_stack: Python
- primary_score: 092/100
- confidence: very_high
- production_checkpoint: P10 (Brand/UI product checks)

## Project Stack Ranking

| rank | stack | score | evidence |
| --- | --- | --- | --- |
| 1 | Python | 092 | 46 Python modules (17 ArcLink, 7,879 lines), 160 ArcLink tests passing, control plane, API, workers, adapters, provisioning, executor |
| 2 | Node.js / TypeScript | 040 | Next.js 15 + Tailwind 4 web app (9 TS/TSX files), 2 web unit test files + 1 Playwright browser test file (41 browser tests passing), Node 22 runtime for qmd/Hermes |
| 3 | Bash | 025 | 79 shell scripts in bin/, deploy.sh, init.sh, operational substrate |
| 4 | Docker Compose | 020 | compose.yaml (16 services, 4 profiles), Dockerfile, provisioning target |
| 5 | .NET | 000 | - |
| 6 | Go | 000 | - |
| 7 | Java | 000 | - |
| 8 | Ruby | 000 | - |
| 9 | Rust | 000 | - |

## Deterministic Alternatives Ranking

- Candidate evaluation is based on repository-level manifest and source signals only.
- Primary decision rule: highest score, then explicit manifest precedence.

### Top 3 stack alternatives (ranked)

- 1) Python: score=092, evidence=[requirements-dev.txt, 46 Python modules, 17 ArcLink modules (7,879 lines), 160 ArcLink tests, control plane DB (15,397 lines), MCP server, CLI, onboarding, provisioning, executor, hosted API]
- 2) Node.js/TypeScript: score=040, evidence=[web/package.json, Next.js 15 + Tailwind 4 (9 source files), 2 web unit tests + 41 Playwright browser tests, Node 22 for qmd/Hermes builds]
- 3) Bash: score=025, evidence=[79 scripts in bin/, deploy.sh, init.sh, operational orchestration]

## Confidence Rationale

Score elevated from 018 to 092 based on full repository audit:
- Python is unambiguously the primary stack with 46 modules, 17 dedicated ArcLink modules, and 160 passing tests.
- Node.js/TypeScript serves the production web frontend and build tooling but is secondary.
- Bash handles deployment operations but contains no business logic.
- Docker Compose is the provisioning substrate, not an implementation language.
- No competing backend stacks exist in the repository.
