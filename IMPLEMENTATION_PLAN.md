# Waves 4-6 Implementation Plan: Comms, Crew Training, ArcLink Wrapped

## Goal

Land the remaining ArcPod Captain Console waves in order:

1. Wave 4: Pod-to-Pod Comms plus Captain and Operator Comms Console.
2. Wave 5: Crew Training with provider-backed Crew Recipe generation and
   additive SOUL overlay.
3. Wave 6: ArcLink Wrapped reports, scheduler, delivery, and dashboards.

Waves 0-3 are treated as landed and must not be re-touched unless a direct
regression blocks these later waves.

## Constraints

- Do not touch `arclink-priv`, live secrets, user Hermes homes, deploy keys,
  production services, payment/provider mutations, public bot command
  registration, live deploys/upgrades, or Hermes core.
- Use existing Python, shell, SQLite, Compose, Next/web, MCP, share-grant,
  notification, Chutes, redaction, and managed-context rails.
- Keep code changes scoped to the active wave.
- Add focused tests before or alongside each behavior change.
- Use Captain-facing vocabulary on user surfaces and Operator/backend
  vocabulary on admin/internal surfaces.
- Crew Training must never wipe memory or sessions; the SOUL overlay is the
  only persona-shifting write.

## Selected Paths

| Wave | Selected path | Rejected alternatives |
| --- | --- | --- |
| Wave 4 | Add `python/arclink_pod_comms.py` as a broker module and adapt MCP/API/UI around it. | Inline SQL in each handler; raw file transfer attachments; global cross-Captain allow-list. |
| Wave 5 | Add `python/arclink_crew_recipes.py` and `templates/CREW_RECIPE.md.tmpl`; use injectable Chutes/fake generation with deterministic fallback. | Require live Chutes; generate overlays in frontend/bot handlers; mutate memories/sessions. |
| Wave 6 | Add `python/arclink_wrapped.py` and a named job-loop scheduler; render Captain narrative and Operator aggregate-only status. | Frontend-only report; health-watch side effects without a named job; raw private-state scans. |

## Current Candidate State

Schema foundations are already present in `python/arclink_control.py`:

- `arclink_pod_messages`;
- `arclink_crew_recipes`;
- `arclink_wrapped_reports`;
- `arclink_users.wrapped_frequency`;
- Captain role/mission/treatment fields;
- status constants, indexes, and drift checks;
- SOUL template placeholders for Agent title and Crew Recipe overlay values.

The required behavior modules, routes, MCP tools, dashboard tabs, scheduler,
Crew Recipe template, Wrapped docs, and new focused tests are not present.

## Validation Criteria

BUILD is complete only when:

- Wave 4 proves same-Captain comms, cross-Captain share-grant gating, rate
  limits, notifications, audit events, MCP tools, API routes, and Comms tabs.
- Wave 5 proves recipe preview/apply/archive, unsafe-output rejection, Chutes
  fallback, operator-on-behalf audit, bot/web flows, and additive identity
  overlay without memory/session mutation.
- Wave 6 proves deterministic report generation, documented novelty scoring,
  at least five non-standard stats, secret redaction, frequency controls,
  scheduler due/retry behavior, notification delivery, quiet-hour handling, and
  dashboard history/aggregate views.
- OpenAPI and runbooks match actual behavior after tests pass.
- No private state, live external mutation, production deploy, or Hermes-core
  change is required.

## Actionable Tasks

### Wave 4: Pod-to-Pod Comms + Comms Console

1. Add `tests/test_arclink_pod_comms.py`.
   - Cover same-Captain send, cross-Captain refusal, active `pod_comms`
     grant allow, expired/revoked/pending grant refusal, 60/minute rate limit,
     attachment references, notification row, audit/events, list scoping, and
     redaction.

2. Implement `python/arclink_pod_comms.py`.
   - Add `send_pod_message`, list helpers, delivery/redaction helpers, and
     attachment validation.
   - Use `check_arclink_rate_limit` with scope
     `pod_comms:<sender_deployment_id>`.
   - Enqueue `notification_outbox` for recipient delivery.
   - Emit `pod_message_sent`, `pod_message_delivered`, and
     `pod_message_redacted`.

3. Extend share grants for comms.
   - Add `pod_comms` to the allowed resource kinds.
   - Keep Drive/Code behavior unchanged.
   - Store only attachment/share projection references in `attachments_json`.

4. Add MCP tools.
   - Register `pod_comms.list`, `pod_comms.send`, and `pod_comms.share-file`
     in `python/arclink_mcp_server.py`.
   - Scope all agent reads/writes to the authenticated caller deployment.

5. Add hosted API and dashboards.
   - Add `GET /api/v1/user/comms` for Captain-scoped inbox/outbox.
   - Add `GET /api/v1/admin/comms` for all Captains behind admin auth and
     existing backend/CIDR boundary.
   - Add Comms tabs to `web/src/app/dashboard/page.tsx` and
     `web/src/app/admin/page.tsx`.
   - Update `web/src/lib/api.ts` and OpenAPI.

6. Run Wave 4 validation.
   - Python compile and focused tests.
   - Web tests/lint/build for dashboard changes.

### Wave 5: Crew Training

1. Add `tests/test_arclink_crew_recipes.py`.
   - Cover preset/capacity validation, active recipe uniqueness, archive of
     previous recipe, unsafe generated output rejection, retry limit,
     deterministic fallback, operator-on-behalf audit, overlay JSON, and no
     memory/session writes.

2. Implement `python/arclink_crew_recipes.py`.
   - Support preview, regenerate, confirm/apply, archive, and
     current-vs-prior diff.
   - Reuse or safely share unsafe-output rejection patterns from memory
     synthesis.
   - Use Chutes via an injectable boundary; fall back deterministically when no
     credential or live client is configured.

3. Add `templates/CREW_RECIPE.md.tmpl`.
   - Inputs: role, mission, treatment, preset, capacity, pod count, Agent
     names/titles.
   - Output contract: one paragraph plus structured overlay data.

4. Apply additive SOUL overlay.
   - Write Crew Recipe data into the existing identity-context path on next
     managed-context refresh.
   - Preserve org-profile/base SOUL material and all memories/sessions.

5. Add web and bot flows.
   - Add dashboard or `/train-crew` questionnaire.
   - Add API routes for preview/confirm/current/diff.
   - Add public bot `/train-crew` and `/whats-changed` handlers without live
     command registration.
   - Add optional Operator-on-behalf route in admin dashboard with audit.

6. Update docs/OpenAPI after behavior is true.

7. Run Wave 5 validation.

### Wave 6: ArcLink Wrapped

1. Add `tests/test_arclink_wrapped.py`.
   - Cover report generation from event/audit/comms/memory/session/vault
     fixtures, novelty score, five non-standard stats, redaction, frequency
     validation, due-captain selection, failed-report retry, quiet-hour deferral,
     notification outbox, and Operator aggregate-only view.

2. Implement `python/arclink_wrapped.py`.
   - Add `generate_wrapped_report`.
   - Read `arclink_events`, `arclink_audit_log`, `arclink_pod_messages`,
     bounded Hermes/session count fixtures, vault reconciler deltas, and
     `memory_synthesis_cards`.
   - Render plain text and Markdown.
   - Redact with `arclink_evidence.redact_value` or the shared redactor before
     storing/rendering.

3. Document novelty scoring.
   - Add `docs/arclink/arclink-wrapped.md`.
   - Define formula and bounds for net-new cards, recipe drift, interaction
     breadth, rare-event count, and score normalization.

4. Add frequency controls.
   - Use `arclink_users.wrapped_frequency` with values daily, weekly, monthly.
   - Add dashboard and `/wrapped-frequency` flow.
   - Reject anything more frequent than daily.

5. Add scheduler and delivery.
   - Add an explicit `arclink-wrapped` Compose job or a small wrapper using
     `docker-job-loop.sh`.
   - Queue `notification_outbox` rows with `target_kind='captain-wrapped'`.
   - Respect quiet hours where source data exists; otherwise use a tested
     default and document it.

6. Add dashboards.
   - Captain dashboard Wrapped tab shows history and narrative.
   - Operator/admin view shows aggregate status, period, score, and delivery
     state only, not Captain narrative.

7. Update OpenAPI/runbooks after behavior is true.

8. Run Wave 6 validation.

## Validation Floor

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

Browser proof should be run for the Crew Training questionnaire and dashboard
tabs when implementation touches layout or interactive flows.

## Completion Notes Required After BUILD

Final BUILD notes must summarize files changed per wave, schema deltas, env
vars, validation commands and results, skipped live gates, skipped
private-state proof, and residual risks or explicit deferrals. Live
infrastructure remains unproven unless the operator separately authorizes a
named live proof.
