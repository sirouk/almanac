# Stack Snapshot

- generated_at: 2026-05-02
- project_root: .
- primary_stack: Python
- primary_score: 085/100
- confidence: high

## Project Stack Ranking

| rank | stack | score | evidence |
| --- | --- | --- | --- |
| 1 | Python | 085 | requirements-dev.txt, 47 Python modules (17 ArcLink, 7,792 lines), 86+ test files (147 ArcLink test functions), control plane, API/auth, hosted API, provisioning, dashboard, executor, entitlements, adapters |
| 2 | Node.js / TypeScript | 012 | web/package.json (Next.js 15 + Tailwind 4), 9 source files (~1,593 lines), 2 web test files |
| 3 | Bash | 008 | bin/ (78 scripts), deploy.sh, init.sh |

## Deterministic Alternatives Ranking

- Candidate evaluation is based on repository-level manifest and source signals only.
- Primary decision rule: highest score, then explicit manifest precedence.

### Top 3 stack alternatives (ranked)

- 1) Python: score=085, evidence=[requirements-dev.txt, 47 modules, 86+ test files, entire control plane and SaaS boundary]
- 2) Node.js: score=012, evidence=[web/package.json, Next.js 15 dashboard app, 9 source files]
- 3) Bash: score=008, evidence=[78 scripts in bin/, deploy/health/Docker orchestration]
