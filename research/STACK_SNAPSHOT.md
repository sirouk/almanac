# Stack Snapshot

- generated_at: 2026-05-12T02:48:53Z
- updated_at: 2026-05-11
- project_root: .
- primary_stack: Python
- primary_score: 092/100
- confidence: high

## Project Stack Ranking

| rank | stack | score | evidence |
| --- | --- | --- |--- |
| 1 | Python | 092 | 54 arclink_*.py modules (~54k lines), 99 test files (871 functions), SQLite control DB, WSGI hosted API, workers, provisioning, bots, evidence, memory synthesis |
| 2 | Bash | 065 | deploy.sh, bin/*.sh (20+ scripts), Docker/systemd/health/qmd wrappers, canonical host lifecycle |
| 3 | Docker/Compose | 055 | Dockerfile, compose.yaml, 5+ services, Sovereign Control Node and Shared Host Docker lanes |
| 4 | Node.js/TypeScript | 018 | Next.js 15 web app (12 source files, ~2.5k lines), 3 web test files, Playwright browser checks |
| 5 | .NET | 000 | - |
| 6 | Go | 000 | - |
| 7 | Java | 000 | - |
| 8 | Ruby | 000 | - |
| 9 | Rust | 000 | - |

## Deterministic Alternatives Ranking

- Candidate evaluation is based on repository-level manifest, source volume, and runtime authority signals.
- Primary decision rule: highest score by source volume and runtime authority, then explicit manifest precedence.

### Top 3 stack alternatives (ranked)

- 1) Python: score=092, evidence=[54 arclink modules, SQLite control DB, WSGI hosted API, workers, provisioning, bots, evidence, auth, memory synthesis, requirements-dev.txt]
- 2) Bash: score=065, evidence=[deploy.sh, 20+ bin/*.sh scripts, Docker/health/qmd/systemd wrappers]
- 3) Docker/Compose: score=055, evidence=[Dockerfile, compose.yaml, 5+ services, multi-lane container topology]

## Assessment Notes

The prior auto-generated snapshot incorrectly ranked Node.js and Python as tied
at 018/100 because the scoring heuristic counted only TypeScript/JS manifest
files without weighting Python source volume (~54k lines across 54 modules and
99 test files) or runtime authority (Python owns the control DB, hosted API,
auth, workers, provisioning, fleet, ingress, evidence, bots, and dashboard).

Python is unambiguously the primary stack. Node.js/TypeScript is a secondary
web surface layer (Next.js 15 App Router, ~2.5k lines, 12 source files). Bash
is the operational orchestration layer. Docker/Compose defines the container
runtime topology.
