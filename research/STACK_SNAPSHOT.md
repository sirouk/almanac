# Stack Snapshot

- generated_at: 2026-05-02T12:00:00Z
- project_root: .
- primary_stack: Python
- primary_score: 092/100
- confidence: high

## Project Stack Ranking

| rank | stack | score | evidence |
| --- | --- | --- | --- |
| 1 | Python | 092 | requirements-dev.txt, 21 arclink modules (8,811 lines), 23 arclink test files (234 functions), 47+ total python modules, control plane, API, workers, adapters, provisioning, executor, diagnostics |
| 2 | Node.js / TypeScript | 025 | Next.js 15 web app (9 source files, ~1,593 lines), package.json, Tailwind 4, Playwright browser tests |
| 3 | Bash | 015 | 79 shell scripts in bin/, deploy.sh, init.sh, test.sh |
| 4 | .NET | 000 | - |
| 5 | Go | 000 | - |
| 6 | Java | 000 | - |
| 7 | Ruby | 000 | - |
| 8 | Rust | 000 | - |

## Deterministic Alternatives Ranking
- Candidate evaluation is based on repository-level manifest and source signals only.
- Primary decision rule: highest score, then explicit manifest precedence.

### Top 3 stack alternatives (ranked)
- 1) Python: score=092, evidence=[requirements-dev.txt, 21 arclink modules (8,811 lines), 47+ total python modules, full control plane and API]
- 2) Node.js/TypeScript: score=025, evidence=[Next.js 15 + Tailwind 4 web app, Playwright tests, 9 source files]
- 3) Bash: score=015, evidence=[79 shell scripts for deploy/ops/health/Docker orchestration]
