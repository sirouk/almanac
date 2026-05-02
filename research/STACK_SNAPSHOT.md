# Stack Snapshot
<!-- refreshed: 2026-05-02T06:47:00Z plan-gate sync after live-proof-orchestration build -->

- generated_at: 2026-05-02T06:47:00Z
- project_root: .
- primary_stack: Python
- primary_score: 085/100
- confidence: high

## Project Stack Ranking

| rank | stack | score | evidence |
| --- | --- | --- | --- |
| 1 | Python | 085 | requirements-dev.txt, 51 Python source files (22 ArcLink modules, 9,045 lines), 24 ArcLink test files (247 functions), control plane, API, workers |
| 2 | Node.js / TypeScript | 035 | package.json, 8 TSX/TS source files (~1,593 lines), Next.js 15 + Tailwind 4 web app, Playwright browser tests |
| 3 | Bash | 025 | 78+ shell scripts in bin/, deploy.sh, Docker/health/ops orchestration |
| 4 | Docker | 020 | compose.yaml (16 services, 4 profiles), Dockerfile, Docker-first provisioning |
| 5 | .NET | 000 | - |
| 6 | Go | 000 | - |
| 7 | Java | 000 | - |
| 8 | Rust | 000 | - |

## Deterministic Alternatives Ranking
- Candidate evaluation is based on repository-level manifest and source signals only.
- Primary decision rule: highest score, then explicit manifest precedence.

### Top 3 stack alternatives (ranked)
- 1) Python: score=085, evidence=[requirements-dev.txt, 51 source files, 22 ArcLink modules (9,045 lines), 24 test files (247 functions)]
- 2) Node.js/TypeScript: score=035, evidence=[package.json, 8 TSX/TS files (~1,593 lines), Next.js 15 + Tailwind 4]
- 3) Bash: score=025, evidence=[78+ scripts, deploy/Docker/health orchestration]
