# Dependency Research

## Scope

This document records stack and dependency signals relevant to Wave 5 Crew
Training. It does not assert live capability for Stripe, Telegram, Discord,
Chutes, Notion, cloud providers, Docker host mutation, or production deploy
flows.

## Stack Components

| Component | Evidence | Wave 5 use | Decision |
| --- | --- | --- | --- |
| Python 3 | `python/*.py`, `tests/test_*.py`, `requirements-dev.txt` | Recipe lifecycle, provider boundary, API/auth, bot handlers, provisioning projection, tests | Primary implementation surface. |
| SQLite | `python/arclink_control.py` | Existing `arclink_crew_recipes`, `arclink_users`, audit, events, sessions, deployments | Reuse existing schema and `ensure_schema`. |
| Chutes boundary | `python/arclink_chutes.py`, `python/arclink_chutes_live.py` | Provider-backed recipe generation when credentials allow it | Use injectable or fake clients; no live inference required. |
| Memory synthesis safety | `python/arclink_memory_synthesizer.py` | Unsafe-output rejection before accepting recipe output | Reuse or extract the existing URL, shell command, and jailbreak checks. |
| Provisioning projection | `python/arclink_provisioning.py` | Write additive recipe overlay into identity context for each Pod | Extend existing projection pattern; preserve existing keys. |
| Hosted API | `python/arclink_hosted_api.py`, `python/arclink_api_auth.py` | Crew Training routes and CSRF-gated mutations | Follow existing route table and handler style. |
| Public bots | `python/arclink_public_bots.py` | `/train-crew` and `/whats-changed` questionnaire flow | Keep pure handler tests; no live command registration. |
| Next.js / React / TypeScript | `web/package.json`, `web/src/app`, `web/src/lib/api.ts` | Captain dashboard Crew Training UI | Reuse current API helper and dashboard page patterns. |
| Docs/OpenAPI | `docs/openapi/arclink-v1.openapi.json`, runbooks | Contract and operator docs | Update after runtime behavior is implemented. |

## Version Snapshot

| Lane | Public signal | Planning note |
| --- | --- | --- |
| Python validation | `requirements-dev.txt` includes jsonschema, PyYAML, requests, Playwright, pyflakes, ruff | New code should stay standard-library first and testable without live services. |
| Web app | Next 15, React 19, TypeScript 5, ESLint 9, Playwright | Dashboard changes require `npm test`, lint, build, and browser proof when available. |
| Marketing app | A separate Vite/React app exists under `arclink-frontend` | Not in Wave 5 scope unless a direct dashboard routing issue requires it. |
| Shell/Compose | Canonical deploy and Docker scripts exist | Wave 5 should not need shell or Compose changes. |

## Alternatives Compared

| Decision area | Preferred path | Alternatives | Reason |
| --- | --- | --- | --- |
| Recipe business logic | `python/arclink_crew_recipes.py` | Inline logic in API, bot, or React | Central module makes lifecycle, fallback, unsafe-output rejection, and audit testable. |
| Generation source | Chutes-compatible injectable client plus deterministic fallback | Require live Chutes; static-only output | Meets product goal without making live credentials a build gate. |
| Fallback content | Deterministic preset/capacity overlay and truthful dry-run label | Silent generic fallback | Captains need honest state and stable local tests. |
| Unsafe-output handling | Reuse or extract memory-synth safety patterns | New ad hoc regexes; trust model output | Existing boundary already encodes required rejection classes. |
| SOUL application | Project overlay to identity context for each Pod | Rewrite memories, sessions, or Hermes core | Matches ArcLink managed-context architecture and avoids gateway restart. |
| Web integration | Add focused questionnaire UI to existing dashboard flow | Frontend architecture rewrite | Keeps Wave 5 scoped and minimizes regression risk. |
| Bot integration | Extend existing public bot handler/session metadata | New live bot workflow service | Local tests can prove behavior without external mutation. |

## External Integration Posture

| Integration | Local BUILD posture | Live posture |
| --- | --- | --- |
| SQLite control DB | Temporary DBs and schema fixtures | No private runtime DB reads. |
| Chutes inference | Fake/injectable response and deterministic fallback tests | Live inference blocked unless separately authorized. |
| Telegram/Discord | Pure handler tests with returned reply payloads | No webhook mutation, command registration, or live delivery. |
| Hermes identity context | Temporary Hermes-home fixtures only | No real user home reads. |
| Payment/provider mutation | Not needed for Crew Training BUILD | Blocked. |
| Deploy/install/upgrade | Not needed for Crew Training BUILD | Blocked. |

## Dependency Risks

- Live Chutes must not become a required test or runtime dependency for Wave 5
  completion.
- Unsafe-output checks should be shared carefully so changing them does not
  weaken memory synthesis behavior.
- Identity-context projection must be atomic and preserve existing dashboard,
  resource, and Agent identity fields.
- The web dashboard is large; additions should be localized and tested through
  existing page smoke/client tests plus a browser questionnaire proof.

## Validation Dependencies

Minimum validation after Wave 5 BUILD:

```bash
git diff --check
python3 -m py_compile python/arclink_crew_recipes.py python/arclink_provisioning.py python/arclink_api_auth.py python/arclink_hosted_api.py python/arclink_public_bots.py python/arclink_dashboard.py
python3 tests/test_arclink_crew_recipes.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_public_bots.py
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_schema.py
```

If web files change:

```bash
cd web
npm test
npm run lint
npm run build
```

If shell or Compose files unexpectedly change:

```bash
bash -n deploy.sh bin/*.sh test.sh
```
