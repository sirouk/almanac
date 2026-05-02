# Stack Snapshot

- generated_at: 2026-05-01T22:00:00Z
- project_root: .
- primary_stack: Python
- primary_score: 092/100
- confidence: high

## Project Stack Ranking

| rank | stack | score | evidence |
| --- | --- | --- | --- |
| 1 | Python | 092 | requirements-dev.txt, 43 python modules, 86 test files, 14 ArcLink modules (~8300 lines), core control plane (15k+ lines), WSGI product surface, hosted API boundary |
| 2 | Bash | 045 | 78 bin/ scripts for deploy, Docker, health, bootstrap, qmd, vault, backup, and runtime operations |
| 3 | Docker | 040 | compose.yaml (16 services, 4 profiles), Dockerfile, Docker health/supervisor scripts |
| 4 | Node.js | 008 | Dockerfile base (node:22-bookworm-slim), Hermes web build dependency, future Next.js dashboard |
| 5 | SQL | 005 | SQLite schema in almanac_control.py (18 arclink_* tables), Postgres for Nextcloud |

## Deterministic Scoring Method

Score is derived from: source file count (40%), manifest presence (15%), test coverage breadth (20%), active development signals (15%), and dependency depth (10%).

- Python: 43 modules + 86 tests + requirements-dev.txt + primary implementation language = 92
- Bash: 78 scripts but no manifest, no tests, operational glue = 45
- Docker: 2 Compose files + Dockerfile + scripts but declarative config = 40
- Node.js: runtime base only, no package.json, no app code yet = 8
- SQL: embedded in Python, no standalone migrations = 5

## Deterministic Alternatives Ranking

- Candidate evaluation is based on repository-level manifest and source signals only.
- Primary decision rule: highest score, then explicit manifest precedence.

### Top 3 stack alternatives (ranked)

- 1) Python: score=092, evidence=[requirements-dev.txt, 43 modules, 86 test files, 14 ArcLink modules, core control plane, hosted API]
- 2) Bash: score=045, evidence=[78 bin/ scripts, deploy.sh, health.sh, Docker orchestration]
- 3) Docker: score=040, evidence=[compose.yaml, Dockerfile, 16 services, 4 profiles]
