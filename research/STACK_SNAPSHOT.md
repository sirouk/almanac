# Stack Snapshot

- snapshot_date: 2026-05-14
- project_type: existing ArcLink public repository
- primary_stack: Python control plane with Next.js dashboard
- deterministic_confidence_score: 092/100
- confidence: high

## Deterministic Scoring Rule

Scores are based only on public repository signals: manifest presence, source
file volume, runtime entrypoints, test coverage, and direct relevance to Wave 5
Crew Training. Private state and live services are excluded.

## Project Stack Ranking

| rank | stack | score | evidence |
| --- | --- | --- | --- |
| 1 | Python | 092 | 187 Python files, control DB, hosted API, auth, public bots, provisioning, Chutes boundary, memory safety, and focused tests. |
| 2 | TypeScript/React/Next.js | 074 | Next.js dashboard in `web/`, API helper layer, dashboard/admin pages, web tests, and browser-test lane. |
| 3 | Bash | 061 | Canonical deploy/test wrappers and service/job scripts; likely unchanged for Wave 5. |
| 4 | SQLite | 058 | Embedded control-plane DB schema and drift checks in Python; existing Crew Recipe table. |
| 5 | Docker Compose | 042 | Runtime topology for control/shared services; not expected to change for Wave 5. |
| 6 | Vite/React marketing app | 024 | Separate `arclink-frontend` app exists but is not the Wave 5 dashboard surface. |
| 7 | Unknown/other | 000 | No stronger public signals. |

## Top Stack Hypotheses

| hypothesis | confidence | rationale |
| --- | --- | --- |
| Wave 5 should be implemented primarily in Python with small Next.js additions | 92 | Recipe lifecycle, provider fallback, unsafe-output checks, DB writes, API auth, bot flow, and identity projection all live in Python. The Captain UI is Next.js. |
| Wave 5 requires new infrastructure | 12 | Existing schema, Chutes boundary, hosted API, public bot handler, and identity projection are sufficient. |
| Wave 5 belongs in Hermes core | 02 | The operating guide forbids Hermes core changes, and managed-context already consumes ArcLink identity overlays. |

## Ranked Alternatives

1. Python module plus API/bot/web adapters.
   - Score: 92
   - Use when implementing `python/arclink_crew_recipes.py`, hosted API routes,
     bot commands, and identity projection.

2. API/web-only implementation.
   - Score: 39
   - Rejected because lifecycle, unsafe-output rejection, fallback, and audit
     would be duplicated or hidden in handlers.

3. Frontend-only dry-run questionnaire.
   - Score: 18
   - Rejected because the deliverable requires durable recipe rows and SOUL
     overlay application.

4. Live-provider-first implementation.
   - Score: 15
   - Rejected because BUILD must pass without live Chutes and must never
     require provider mutation.

5. Hermes-core modification.
   - Score: 02
   - Rejected by repository operating guide and Wave 5 constraints.

## Stack Conclusion

Use existing Python, SQLite, Chutes boundary/fakes, memory-synthesis safety,
provisioning projection, hosted API/auth, public bot handlers, and Next.js
dashboard patterns. Do not add infrastructure for Wave 5.
