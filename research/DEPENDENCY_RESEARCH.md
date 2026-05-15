# Dependency Research

## Scope

This document records stack and dependency signals relevant to audit-gate
verification, ArcLink Wrapped, and Mission Closeout. It does not assert live
capability for Stripe, Telegram, Discord, Chutes, Notion, cloud providers,
Docker host mutation, or production deploy flows.

## Stack Components

| Component | Evidence | Wrapped / closeout use | Decision |
| --- | --- | --- | --- |
| Python 3 | `python/*.py`, `tests/test_*.py`, `requirements-dev.txt` | Wrapped core, cadence, report persistence, delivery enqueue, API/auth, bot command handling, dashboard snapshots, tests | Primary implementation surface. |
| SQLite | `python/arclink_control.py` schema and helpers | Existing `arclink_wrapped_reports`, `arclink_users`, ledgers, audit/events, Comms, memory cards, notification outbox | Reuse existing DB rails and drift checks. |
| Shell | `bin/*.sh`, `deploy.sh`, `bin/docker-job-loop.sh` | Named Wrapped scheduler runner and syntax validation | Keep runner thin; no ad hoc deploy or host surgery. |
| Docker Compose | `compose.yaml` | Add or verify named `arclink-wrapped` job-loop service | Use existing app/job anchors; no Docker socket required. |
| Notification delivery | `notification_outbox`, `python/arclink_notification_delivery.py` | Durable Captain report delivery and operator failure notifications | Reuse outbox; `captain-wrapped` handling/tests are now present. |
| Secret redaction | `python/arclink_evidence.py`, `python/arclink_secrets_regex.py` | Redact report ledger snippets and narrative before storage/delivery | Reuse, do not create a competing redactor. |
| Hosted API | `python/arclink_hosted_api.py`, `python/arclink_api_auth.py` | Wrapped history/frequency and admin aggregate routes | Follow existing cookie/CSRF/CIDR/body-cap patterns. |
| Public bots | `python/arclink_public_bots.py` | `/wrapped-frequency` cadence command and no-live bot tests | Pure handler tests; no live command registration. |
| Next.js / React / TypeScript | `web/package.json`, `web/src/app`, `web/src/lib/api.ts` | Captain Wrapped tab, frequency selector, Operator aggregate panel | Reuse current API helper and tab patterns. |
| OpenAPI/docs | `docs/openapi/arclink-v1.openapi.json`, `docs/API_REFERENCE.md` | Route contract and closeout reconciliation | Update only after behavior is true. |

## Version Snapshot

| Lane | Public signal | Planning note |
| --- | --- | --- |
| Python validation | `requirements-dev.txt` includes jsonschema, PyYAML, requests, Playwright, pyflakes, ruff | New Wrapped code should remain standard-library first and no-secret testable. |
| Web app | Next 15, React 19, TypeScript 5, ESLint 9, Playwright | Dashboard changes require `npm test`, lint, build, and browser proof when available. |
| Runtime image | `Dockerfile` uses Node 22 base plus Python, Docker CLI, qmd, pinned Hermes runtime | Wrapped scheduler can run inside existing image without new infrastructure. |
| Compose jobs | Existing job-loop services for health, qmd, pdf, memory, docs, quarto, backup | Wrapped should follow this pattern rather than introducing cron or a new queue. |

## Alternatives Compared

| Decision area | Preferred path | Alternatives | Reason |
| --- | --- | --- | --- |
| Audit Wave 1 | Verification gate plus focused regression repair if needed | Rebuild all audit items from historical wording | Current source already contains remediations; targeted verification avoids churn. |
| Wrapped core ownership | `python/arclink_wrapped.py` | Inline SQL/scoring in API, bot, web, or scheduler | Centralizes privacy, scoring, redaction, persistence, and tests. |
| Scheduler | Named `arclink-wrapped` job-loop service and runner | Host cron; health-watch piggyback; always-on custom daemon | Job-loop is already deployed, observable, and simple. |
| Period due logic | Python helper computes due users and period windows each run | Compose cron expressions per cadence | One runner can retry failed reports and respect per-Captain cadence without multiple services. |
| Session counts | Injected read-only scanner over scoped deployment state roots | Directly reading live user Hermes homes during tests | Keeps BUILD no-private-state and supports fixtures. |
| Vault deltas | Read `arclink-vault-reconciler.json` only through scoped deployment state roots | Crawl vault content or mutate qmd/memory state | Meets report need without touching Captain data. |
| Redaction | `arclink_evidence.redact_value` and shared regex redactor | New Wrapped-specific regexes | Avoids fragmented secret handling. |
| Quiet hours | Compute `next_attempt_at` conservatively and let delivery worker retry | Direct-send from scheduler, ignoring quiet windows | Preserves notification retry rail and Captain quiet-time boundary. |
| Operator view | Aggregate rows only | Full narratives in admin dashboard | Matches privacy requirement. |

## External Integration Posture

| Integration | Local BUILD posture | Live posture |
| --- | --- | --- |
| SQLite control DB | Temporary DBs and schema fixtures | No private runtime DB reads. |
| Telegram/Discord | Pure command/handler tests for frequency updates | No webhook mutation, command registration, or live delivery. |
| Hermes sessions | Temporary fixture roots and injected scanners | No real user home reads. |
| Notification delivery | Outbox row assertions and fake transports | Live delivery remains operator-gated. |
| Payments/providers/cloud | Not needed for Wrapped BUILD | Blocked. |
| Deploy/install/upgrade | Not needed for PLAN or local BUILD | Blocked unless operator separately authorizes. |

## Dependency Risks

- The current `arclink_wrapped_reports` table has `ledger_json` but no separate
  text/markdown columns. BUILD should first try storing rendered forms inside
  `ledger_json`; add columns only if API/query ergonomics require it and pair
  them with drift checks.
- Quiet-hours parsing may be imperfect because org quiet-hours text is
  currently free-form in some identity contexts. Fail conservatively by
  delaying when a supported window is known and documenting unsupported text.
- `memory_synthesis_cards` is not inherently per-Captain. Use it as a bounded
  recall-signal source, not as authoritative personal narrative unless the
  source path can be scoped.
- Compose socket mounts are unrelated to Wrapped but remain trust-boundary
  sensitive. Verification should keep them intentional and tested.

## Validation Dependencies

Minimum validation after BUILD:

```bash
git diff --check
python3 -m py_compile python/arclink_wrapped.py python/arclink_api_auth.py python/arclink_hosted_api.py python/arclink_dashboard.py python/arclink_public_bots.py python/arclink_notification_delivery.py
python3 tests/test_arclink_wrapped.py
python3 tests/test_arclink_notification_delivery.py
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_public_bots.py
python3 tests/test_arclink_schema.py
```

When shell or Compose changes:

```bash
bash -n deploy.sh bin/*.sh test.sh
```

When web files change:

```bash
cd web
npm test
npm run lint
npm run build
npm run test:browser
```
