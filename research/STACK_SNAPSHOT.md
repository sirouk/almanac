# Stack Snapshot

- generated_at: 2026-05-02T12:00:00Z
- project_root: .
- primary_stack: Python
- primary_score: 085/100
- confidence: high

## Project Stack Ranking

| rank | stack | score | evidence |
| --- | --- | --- | --- |
| 1 | Python | 085 | requirements-dev.txt, 142 Python files, 17 ArcLink modules (7,849 lines), 17 test files (152 test functions), control plane, workers, adapters, provisioning, API/auth, executor |
| 2 | Node.js / TypeScript | 040 | package.json, 19 TS/TSX files, Next.js 15 web app (~1,593 lines), Tailwind 4, web tests |
| 3 | Bash | 025 | 79 shell scripts in bin/, deploy.sh, init.sh, operational substrate |
| 4 | .NET | 000 | - |
| 5 | Go | 000 | - |
| 6 | Java | 000 | - |
| 7 | Ruby | 000 | - |
| 8 | Rust | 000 | - |

## Deterministic Alternatives Ranking
- Candidate evaluation is based on repository-level manifest and source signals only.
- Primary decision rule: highest score, then explicit manifest precedence.

### Top 3 stack alternatives (ranked)
- 1) Python: score=085, evidence=[requirements-dev.txt, 142 Python files, 17 ArcLink modules, full control plane]
- 2) Node.js/TypeScript: score=040, evidence=[package.json, 19 TS/TSX files, Next.js 15 + Tailwind 4 web app]
- 3) Bash: score=025, evidence=[79 shell scripts, deploy/ops substrate]
