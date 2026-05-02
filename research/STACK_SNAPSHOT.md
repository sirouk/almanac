# Stack Snapshot

- generated_at: 2026-05-01T12:00:00Z
- project_root: .
- primary_stack: Python
- primary_score: 085/100
- confidence: high

## Project Stack Ranking

| rank | stack | score | evidence |
| --- | --- | --- | --- |
| 1 | Python | 085 | requirements-dev.txt, 45 python modules, 89 test files, 16 arclink modules (7,094 lines), control plane (15,397 lines) |
| 2 | Node.js / TypeScript | 035 | package.json, 8 TSX/TS source files (~1,375 lines), Next.js 15 + Tailwind 4 web app, 1 web test |
| 3 | Bash | 025 | 78 bin/ scripts, deploy.sh, init.sh, test.sh |
| 4 | .NET | 000 | - |
| 5 | Go | 000 | - |
| 6 | Java | 000 | - |
| 7 | Ruby | 000 | - |
| 8 | Rust | 000 | - |

## Deterministic Alternatives Ranking
- Candidate evaluation is based on repository-level manifest and source signals only.
- Primary decision rule: highest score, then explicit manifest precedence.

### Top 3 stack alternatives (ranked)
- 1) Python: score=085, evidence=[requirements-dev.txt, 45 modules, 89 test files, primary control plane and API layer]
- 2) Node.js/TypeScript: score=035, evidence=[package.json, Next.js 15 web app with 8 source files, Tailwind 4]
- 3) Bash: score=025, evidence=[78 bin/ scripts, deploy/health/Docker orchestration]
