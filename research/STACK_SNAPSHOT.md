# Stack Snapshot

- generated_at: 2026-05-02T12:00:00Z
- project_root: .
- primary_stack: Python
- primary_score: 092/100
- confidence: high

## Project Stack Ranking

| rank | stack | score | evidence |
| --- | --- | --- | --- |
| 1 | Python | 092 | requirements-dev.txt, 142 Python files, 17 ArcLink modules (7,792 lines), 17 ArcLink test files (147 tests), control plane, API/auth, adapters, executor, provisioning, entitlements, dashboards |
| 2 | Node.js / TypeScript | 035 | package.json (Next.js 15 + Tailwind 4), 19 TS/TSX files (~1,593 lines), 2 web test files |
| 3 | Bash | 025 | 79 shell scripts for deploy, health, Docker, bootstrap, and service operations |
| 4 | Docker | 020 | Dockerfile, compose.yaml, nextcloud-compose.yml, Docker executor boundary |
| 5 | Go | 000 | - |
| 6 | Java | 000 | - |
| 7 | Rust | 000 | - |
| 8 | .NET | 000 | - |

## Deterministic Alternatives Ranking
- Candidate evaluation is based on repository-level manifest and source signals only.
- Primary decision rule: highest score, then explicit manifest precedence.
- Scoring method: weighted combination of file count (40%), manifest presence (20%), line count share (30%), and test coverage depth (10%).

### Top 3 stack alternatives (ranked)
- 1) Python: score=092, evidence=[requirements-dev.txt, 142 files, 7,792 ArcLink lines, 147 ArcLink tests, SQLite control plane, WSGI hosted API]
- 2) Node.js/TypeScript: score=035, evidence=[package.json, Next.js 15, Tailwind 4, 19 TS/TSX files, 2 web tests]
- 3) Bash: score=025, evidence=[79 shell scripts, deploy.sh, bin/ directory, systemd units]
