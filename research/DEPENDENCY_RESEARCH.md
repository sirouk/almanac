# Dependency Research

## Scope

This document records stack and dependency signals relevant to ArcPod Captain
Console Waves 4-6: Pod-to-Pod Comms, Crew Training, and ArcLink Wrapped. It
does not assert live capability for Stripe, Telegram, Discord, Chutes, Notion,
Cloudflare, Tailscale, Hetzner, Linode, Docker host mutation, or production
deploy flows.

## Stack Components

| Component | Evidence | Wave 4-6 use | Decision |
| --- | --- | --- | --- |
| Python 3.11+ | `python/*.py`, `tests/test_*.py`, `requirements-dev.txt` | New comms, recipe, wrapped modules; API/auth; MCP; bot flows; tests | Primary implementation surface. |
| SQLite | `python/arclink_control.py` | Existing tables for pod messages, crew recipes, wrapped reports, audit/events, rate limits, notifications | Reuse `ensure_schema`; add only behavior-required schema deltas. |
| Next.js / React / TypeScript | `web/package.json`, `web/src/app` | Comms, Crew Training, and Wrapped dashboard surfaces | Reuse current monolithic page/tab pattern; avoid frontend architecture churn. |
| Bash | `deploy.sh`, `bin/*.sh` | Wrapped scheduler wrapper or job-loop integration | Touch only when needed for Wave 6 runtime. |
| Docker Compose | `compose.yaml` | Add or integrate `arclink-wrapped` scheduled job | Reuse existing `docker-job-loop.sh` job-service pattern. |
| Notification delivery | `notification_outbox`, `python/arclink_notification_delivery.py` | Comms recipient delivery and Wrapped delivery | Reuse; avoid bespoke delivery queues. |
| MCP server | `python/arclink_mcp_server.py` | Agent-facing `pod_comms.*` tools | Follow existing `shares.request` schema/dispatch pattern. |
| Chutes boundary | `python/arclink_chutes.py`, fake client patterns | Crew Recipe generation when credentials allow it | Use injectable/fake-tested client; deterministic fallback if unavailable. |
| Memory synthesis safety | `python/arclink_memory_synthesizer.py` | Reject unsafe recipe output | Reuse unsafe-output pattern or extract small shared helper if needed. |
| Evidence redaction | `python/arclink_evidence.py`, `python/arclink_secrets_regex.py` | Wrapped report redaction | Redact before render and delivery. |

## Version Snapshot

| Lane | Public signal | Planning note |
| --- | --- | --- |
| Python | Dev requirements include jsonschema, PyYAML, requests, Playwright, pyflakes, ruff | New code should stay standard-library first and testable without live services. |
| Web | Next 15, React 19, TypeScript 5, ESLint 9, Playwright | UI changes require `npm test`, lint, and targeted browser checks when flows are interactive. |
| Compose | Job services already use `docker-job-loop.sh` intervals | Wrapped can join this model without new infrastructure. |
| Hermes/qmd | Runtime is pinned and managed outside these waves | Do not patch Hermes core; identity-context overlays are ArcLink-owned. |

## Alternatives Compared

| Decision area | Preferred path | Alternatives | Reason |
| --- | --- | --- | --- |
| Comms implementation | Python broker module plus MCP/API adapters | SQL in handlers; external chat queue | Central module is testable and keeps trust boundaries in one place. |
| Comms authorization | Same-Captain allowed, cross-Captain requires active `pod_comms` share grant | Global allow-list; admin override by default | Share grants already model approval and projection. |
| Crew generation | Provider-backed with fake/injectable Chutes and deterministic fallback | Require live Chutes; no-LLM static only | Meets product goal while keeping BUILD no-secret. |
| Unsafe output | Reuse memory-synthesis unsafe patterns and shared redaction | Trust model output after JSON parse | Rejecting URLs/shell/jailbreak text is required before SOUL overlay. |
| Wrapped scheduler | Explicit Compose job-loop service or wrapper | Fold into health-watch; manual-only command | A named job is operable and testable; health-watch overloading is harder to reason about. |
| Wrapped data reads | Control DB plus bounded per-deployment metadata/state-root readers | Raw user-home scans | Prevents uid crossing and keeps tests local. |

## External Integration Posture

| Integration | Local BUILD posture | Live posture |
| --- | --- | --- |
| SQLite control DB | Temporary DBs and schema fixtures | No private runtime DB reads. |
| Chutes inference | Fake/injectable response and deterministic fallback tests | Live inference blocked unless operator authorizes it. |
| Telegram/Discord | Pure handler/command tests with queued notifications | No webhook mutation or command registration. |
| Notification delivery | Queue rows and fake delivery assertions | Live chat delivery blocked. |
| Hermes sessions/state | Temporary fixtures only | No real user home reads. |
| Docker/Compose | Static config and shell syntax checks | No deploy/install/upgrade. |
| Stripe/payment/provider mutation | Not needed for Waves 4-6 BUILD | Blocked. |

## Dependency Risks

- No new infrastructure is needed for Wave 4 or Wave 5. Adding one would widen
  scope unnecessarily.
- Chutes live inference must not become a hard dependency for Crew Training;
  fallback output must be deterministic and useful.
- Wrapped may need a small reader abstraction for session/vault/memory inputs
  so tests do not depend on private runtime paths.
- Web changes touch large dashboard components; keep additions localized and
  consider small presentational helpers only if duplication becomes real.

## Validation Dependencies

Minimum validation after BUILD hardening:

```bash
git diff --check
python3 -m py_compile python/arclink_pod_comms.py python/arclink_crew_recipes.py python/arclink_wrapped.py python/arclink_mcp_server.py python/arclink_api_auth.py python/arclink_hosted_api.py python/arclink_public_bots.py python/arclink_dashboard.py python/arclink_notification_delivery.py
python3 tests/test_arclink_pod_comms.py
python3 tests/test_arclink_crew_recipes.py
python3 tests/test_arclink_wrapped.py
python3 tests/test_arclink_mcp_schemas.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_public_bots.py
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_notification_delivery.py
python3 tests/test_arclink_schema.py
```

If shell or Compose files change:

```bash
bash -n deploy.sh bin/*.sh test.sh
```

If web files change:

```bash
cd web
npm test
npm run lint
npm run build
```
