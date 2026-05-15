# Research Summary

<confidence>90</confidence>

## Scope

This PLAN pass inspected the public ArcLink repository, current research
artifacts, the ArcPod Captain Console steering document, the Sovereign audit
verification file, schema and drift checks, hosted API and dashboard patterns,
public bot handlers, notification delivery rails, Docker job-loop scheduling,
OpenAPI/docs surfaces, and focused tests.

No private state, live secrets, user Hermes homes, deploy keys, production
deploys, payment/provider mutations, live bot command registration, or Hermes
core were inspected or changed.

## Mission Reconciliation

The prompt contains two active-looking directives:

- Bootstrap objective: resolve the verified Sovereign audit backlog, starting
  with Wave 1 security and trust-boundary repairs.
- Project goals document: final ArcPod Captain Console run, landing Wave 6
  ArcLink Wrapped plus the Mission Closeout sweep.

Current source and completion notes show the audit Wave 1 trust-boundary items
already have local source-level remediations and focused tests. Therefore the
BUILD handoff treats audit Wave 1 as a verification gate: re-run and inspect
those trust-boundary checks first, repair any regression found, ignore the two
fiction/outdated audit items, then implement Wave 6 and closeout. This satisfies
the audit directive without reworking fixed code blindly.

## Current Source Findings

| Area | Finding |
| --- | --- |
| Waves 0-5 | Source now contains Wave 0-5 surfaces: vocabulary, Agent Name/Title onboarding, inventory/ASU, Pod migration, Pod Comms, Crew Training, hosted API routes, web dashboard pieces, and tests. The prior plan files were stale and still described Wave 5 as future work. |
| Audit Wave 1 | Telegram webhook secret, Discord timestamp/replay checks, hosted API body caps, CIDR gate, session hash peppering, shared secret redaction, safer auth/body errors, and webhook rate-limit tests are present in source/tests. Docker socket scoping still deserves close verification because Compose has several intentional socket mounts. |
| Wrapped schema/core | `arclink_wrapped_reports` and `arclink_users.wrapped_frequency` exist with drift checks. `python/arclink_wrapped.py`, core tests, scheduler service, and `captain-wrapped` delivery are now present; Wrapped API/routes, dashboard tab, and bot cadence command remain open. |
| Data inputs | Wrapped can read `arclink_events`, `arclink_audit_log`, `arclink_pod_messages`, `memory_synthesis_cards`, deployment metadata/state roots, job status JSON, and `arclink-vault-reconciler.json` deltas. These reads must stay scoped to the Captain's deployments and temporary test fixtures. |
| Delivery rail | `notification_outbox` supports durable delivery attempts. Wrapped now has a `target_kind='captain-wrapped'` path, quiet-hours scheduling semantics, and report delivered-state updates. |
| Redaction | `arclink_evidence.redact_value` and `arclink_secrets_regex` exist. Wrapped report rendering must redact before storing or delivering narrative text. |
| Web stack | Next.js dashboard has user/admin tabs and API helpers. No Wrapped tab or API client methods exist. |
| Docs/OpenAPI | `docs/API_REFERENCE.md`, `docs/arclink/architecture.md`, `docs/DOC_STATUS.md`, and `docs/openapi/arclink-v1.openapi.json` document Waves through Crew Training/Comms but not Wrapped. |

## Implementation Path Comparison

| Decision | Path A | Path B | Selected path |
| --- | --- | --- | --- |
| Audit Wave 1 handling | Verify current trust-boundary repairs first, patch only regressions | Re-implement all listed audit items from the historical report | Path A. Source and tests already show remediation; blind rewrites would widen risk. |
| Wrapped core | Add `python/arclink_wrapped.py` with deterministic report generation, persistence, delivery enqueue, and due-cadence helpers | Scatter Wrapped SQL/rendering inside hosted API, dashboard, scheduler, and bot handlers | Path A. One module keeps scoring, redaction, and privacy boundaries testable. |
| Scheduler | Add a named `arclink-wrapped` Compose job-loop service invoking a small `bin/arclink-wrapped.sh` runner that decides due reports | Fold Wrapped into `health-watch` or add a host cron | Path A. It matches existing Docker job-loop patterns, has visible status, and avoids unrelated health-watch coupling. |
| Report inputs | Read existing ledgers and local fixture-safe state roots, with injected state-root/session scanners in tests | Require live Hermes homes or private state to prove session/memory inputs | Path A. BUILD must remain no-secret and no-private-state. |
| Cadence changes | Expose `/user/wrapped-frequency` and public bot `/wrapped-frequency` with `daily|weekly|monthly` only | Let dashboard mutate `arclink_users` generically or accept arbitrary cron strings | Path A. It enforces the daily minimum and keeps the user API narrow. |
| Delivery | Queue `notification_outbox` rows with `target_kind='captain-wrapped'`, `next_attempt_at` honoring quiet hours, and aggregate operator status only | Deliver directly from the scheduler or expose full narratives to Operator dashboards | Path A. It reuses durable notification retries and preserves Captain narrative privacy. |
| Dashboard | Add a Captain "Wrapped" tab plus Operator aggregate status panel | Replace dashboard structure or put Wrapped in Crew Training | Path A. The current dashboard is tab-based and should stay scoped. |

## Build Assumptions

- Current source is the source of truth when historical research files disagree.
- Audit fiction items `ME-11` and `ME-25` remain ignored except as regression
  awareness.
- Wrapped generation is read-only over Captain state. It may insert/update
  `arclink_wrapped_reports` and queue notifications, but must not mutate
  sessions, memories, vault content, Hermes core, or provider/payment state.
- Captain-facing Wrapped narrative uses ArcPod, Pod, Agent, Captain, Crew,
  Raven, Comms, and ArcLink Wrapped vocabulary.
- Operator/admin views may show only aggregate Wrapped status, frequency,
  novelty score, timestamps, and failure status. They must not show the
  Captain's narrative or raw ledger snippets.
- Any state-root or Hermes-session reading must be explicitly scoped to
  deployments owned by the requested Captain and injectable for tests.

## Risks

- Quiet-hours rules are not a fully normalized per-Captain scheduling API today;
  Wrapped may need a conservative helper that delays delivery rather than
  inventing new org-profile semantics.
- `memory_synthesis_cards` is global. Wrapped must use only safe, bounded
  summaries and avoid implying per-Captain ownership when source attribution is
  ambiguous.
- Compose still mounts the Docker socket for several trusted operator-action
  services. The audit gate should verify current tests and document intentional
  mounts rather than broadening Wrapped.
- The Mission Closeout sweep is broad; docs/OpenAPI reconciliation should be
  done after behavior is true, not before.

## Verdict

PLAN is ready for no-secret BUILD handoff after the required artifacts in this
pass are updated. No blocker requires stopping BUILD, but the first BUILD task
is a trust-boundary verification gate. Any regression there blocks Wrapped work
until the focused repair and regression test land.
