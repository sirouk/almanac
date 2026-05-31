# Ground Truth 12: Diagnostics, Health, Evidence, Live Proof, Notifications, Incidents

Mapped 2026-05-30 against branch `arclink`. This subsystem is COVERAGE_MATRIX
journey **J-27** ("Health, diagnostics, live proof, evidence ledger") plus the
notification/incident rails that J-04 and J-26/J-25 also touch.

Source of truth = code. Everything below is read from the listed files.

---

## 1. What is actually implemented today (local-real)

### 1a. Host readiness — `python/arclink_host_readiness.py`
- Pure, no-secret, no-mutation checks. CLI: `python3 -m arclink_host_readiness`
  (also reachable via the live runner).
- `run_readiness(...)` aggregates `ReadinessCheck` rows into a `ReadinessResult`:
  - `check_docker` (binary on PATH), `check_docker_compose` (actually runs
    `docker compose version`, injectable `compose_runner`), `check_state_root`
    (existence + writability via temp file under `ARCLINK_STATE_ROOT` or
    `/arcdata`), `check_env_vars` (required: `ARCLINK_PRODUCT_NAME`,
    `ARCLINK_BASE_DOMAIN`, `ARCLINK_PRIMARY_PROVIDER`),
    `check_secret_env_presence` (presence-only, never value, for 9 optional
    secret vars), `check_ingress_strategy` (cloudflare vs `traefik_local`
    fallback), and per-port `check_port_available` (default 80/443/8080,
    skippable).
  - `ready` is computed ignoring `secret_*` checks (missing secrets do not flip
    readiness to false).

### 1b. Provider diagnostics — `python/arclink_diagnostics.py`
- Secret-safe credential-presence checks only. CLI: `python3 -m
  arclink_diagnostics`. Reports missing var **names**, never values.
- `run_diagnostics(...)` -> `DiagnosticsResult` of `DiagnosticCheck` rows for:
  stripe (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`), ingress (cloudflare OR
  tailscale depending on `ARCLINK_INGRESS_MODE=tailscale`), chutes
  (`CHUTES_API_KEY`), telegram (`TELEGRAM_BOT_TOKEN`), discord
  (`DISCORD_BOT_TOKEN`, `DISCORD_APP_ID`), docker (binary on PATH).
- `live=True` is reserved/unimplemented — the docstring says "real provider
  connectivity could be tested (future)". Today `live` does nothing.

### 1c. Live journey model — `python/arclink_live_journey.py`
- Ordered `JourneyStep` dataclass (name, description, `required_env`, status,
  skip_reason, error, evidence, timing). Statuses: pending|skipped|running|
  passed|failed.
- `build_journey(kind, env)` builds one of four journeys:
  - **hosted** (`_HOSTED_JOURNEY_STEP_SPECS`, 12 steps): `web_onboarding_start`,
    `web_onboarding_checkout`, `stripe_webhook_delivery`,
    `entitlement_activation`, `provisioning_request`, ingress step
    (`dns_health_check` for Cloudflare OR `tailscale_ingress_health_check` when
    `ARCLINK_INGRESS_MODE=tailscale`), `docker_deployment_check`,
    `chutes_key_provisioning`, `user_dashboard_verification`,
    `admin_dashboard_verification`, `telegram_bot_check`, `discord_bot_check`.
  - **workspace** (`_WORKSPACE_JOURNEY_STEPS`, 8 steps): `workspace_control_upgrade`,
    `workspace_control_health`, then `{drive,code,terminal}_tls_{desktop,mobile}_proof`.
  - **external** (`_EXTERNAL_PROOF_STEPS`, 12 opt-in provider rows — see §2c).
  - **all** = hosted + external + workspace.
- `evaluate_journey(steps, runners, stop_on_failure=True)` runs the steps in
  order: missing creds -> skipped; no runner -> skipped; runner present ->
  running -> passed/failed; on failure with `stop_on_failure` remaining steps are
  skipped with `"prior step failed"`.
- `_ENV_ALTERNATES` lets `CLOUDFLARE_API_TOKEN` be satisfied by
  `CLOUDFLARE_API_TOKEN_REF`.

### 1d. Live proof orchestration runner — `python/arclink_live_runner.py`
- CLI shim: `bin/arclink-live-proof` -> `python3 -m arclink_live_runner`.
  Dry-run by default; `--live`, `--journey {hosted,external,workspace,all}`,
  `--artifact-dir`, `--docker-binary`, `--json`.
- `run_live_proof(...)` is 6 phases: (1) host readiness, (2) provider
  diagnostics, (3) journey planning + missing-env collection, (4) journey
  evaluation (only when `live_executed`), (5) build evidence ledger, (6) write
  artifact JSON to `evidence/<run_id>.json`.
- Returns a `LiveProofResult` dataclass with **status** one of:
  `blocked_missing_credentials`, `blocked_no_registered_runner`,
  `dry_run_ready`, `live_executed`. Exit code 0 = dry-run ready / passed live;
  1 = blocked-while-live or a live step failed; 2 = invalid CLI input.
- Proof opt-in semantics: any `ARCLINK_PROOF_*` flag set marks all *other*
  unselected proof-opt-in steps as `skipped` with reason
  `"proof opt-in not set: ..."`. This drives the external journey's
  per-provider selectivity (`_step_is_unselected_proof_opt_in`,
  `_mark_unselected_proof_opt_in_steps`).
- **Real, no-secret workspace live runners** (`build_workspace_live_runners`):
  - `workspace_control_upgrade` -> `./deploy.sh control upgrade`
    (timeout `ARCLINK_WORKSPACE_PROOF_DOCKER_TIMEOUT_SECONDS`, default 2700s).
  - `workspace_control_health` -> `./deploy.sh control health`
    (timeout `ARCLINK_WORKSPACE_PROOF_HEALTH_TIMEOUT_SECONDS`, default 900s).
  - Six browser proofs (`_BROWSER_STEP_SPECS`) run an inline Playwright/chromium
    `.cjs` script (`_browser_runner_script`) under `web/` against
    `ARCLINK_WORKSPACE_PROOF_TLS_URL` (HTTPS required). It exercises real
    Drive/Code/Terminal plugin API routes (`/api/plugins/drive/*`, `/code/*`,
    `/terminal/*`) and captures a **sanitized** (text-transparent) screenshot to
    `evidence/workspace-screenshots/`.
  - Command output is reduced to a `_redacted_command_label` ("deploy.sh control
    upgrade", "npx playwright workspace-proof"); raw stdout is never put in the
    result except parsed JSON counts (checks/roots/repos) and a screenshot path.
  - Auth is read only from `ARCLINK_WORKSPACE_PROOF_AUTH` (Cookie:/Bearer/raw),
    passed via env to the browser process, never written to evidence.

### 1e. Evidence ledger — `python/arclink_evidence.py`
- Redaction layer: `_SECRET_PATTERNS` (Stripe `sk_`/`whsec_`/`rk_`, generic
  `?key=`/`token=`/`secret=`/`password=` query params), `_SENSITIVE_KEY_PARTS`,
  `_REDACT_ENV_KEYS` (explicit secret env-var allowlist). `redact_value` keeps
  an 8-char prefix; `redact_text`/`redact_any`/`redact_dict` recursively scrub.
- `EvidenceRecord` / `EvidenceLedger` dataclasses; `EvidenceRecord.to_dict()`
  re-redacts provider_id/url/health_summary/detail/error on serialization.
- Helpers: `get_commit_hash()` (git short HEAD), `generate_run_id()`
  (sha256-of prefix/commit/ts, `run_<12hex>`), `record_from_step`,
  `ledger_from_journey`.
- **DB persistence layer (implemented + tested, but unwired — see §4):**
  `store_evidence_run`, `get_evidence_run`, `list_evidence_runs`,
  `latest_evidence_status` against table `arclink_evidence_runs`.
  `_evidence_status_from_ledger` collapses ledger statuses to the table CHECK
  domain `{pending,skipped,passed,failed,blocked}`.
  - `EVIDENCE_STATUSES` / `EVIDENCE_LEDGER_STATUSES` frozensets define the
    domain; `blocked_*` ledger statuses collapse to `blocked`.

### 1f. Health watch -> operator notifications — `python/arclink_health_watch.py`
- Entry: `bin/health-watch.sh` -> `arclink_health_watch.main`. Systemd:
  `arclink-health-watch.service` + `.timer` (`OnBootSec=5s`,
  `OnUnitActiveSec=15m`). Restarted/started by `bin/deploy.sh` control flows.
- `run_once(cfg, ...)`:
  - Skips entirely while an `active_deploy_operation(cfg)` is in progress
    (returns status `skipped`, `deploy_operation_active: True`).
  - Runs the health command (`ARCLINK_HEALTH_WATCH_HEALTH_CMD` or
    `bin/health.sh`) with `ARCLINK_HEALTH_WATCH_CHILD=1` and optional
    `ARCLINK_HEALTH_STRICT`. Parses the `Summary: N ok, N warn, N fail` line and
    `[fail]`/`[warn]` lines from health.sh output.
  - Computes a `_failure_fingerprint` (sha256[:16] of status/returncode/summary/
    problem_lines). Edge-triggered notify: only queues a notification when
    status is fail/warn AND the fingerprint **changed** vs the last stored one;
    queues a recovery message when transitioning back to ok.
  - State stored in the settings table via keys
    `arclink_health_watch_last_status`, `_last_fingerprint`, `_last_summary`,
    `_last_notified_at`.
  - Operator target resolved from `cfg.operator_notify_platform` /
    `operator_notify_channel_id` (default platform `tui-only`, default id
    `operator`). Enqueues via `queue_notification(target_kind="operator", ...)`.
  - Problem lines are clipped (`_clip_lines`, max 12 lines / 2200 chars) with a
    "run ./deploy.sh health" pointer. No secrets/paths beyond health.sh output.
- CLI flags / env: `--timeout-seconds` (`ARCLINK_HEALTH_WATCH_TIMEOUT_SECONDS`
  default 300), `--strict`, `--notify-warnings`
  (`ARCLINK_HEALTH_WATCH_NOTIFY_WARNINGS`).

### 1g. Notification delivery worker — `python/arclink_notification_delivery.py`
- Entry: `bin/arclink-notification-delivery.sh`. Systemd:
  `arclink-notification-delivery.service` + `.timer` (`OnBootSec=5s`,
  `OnUnitActiveSec=5s` — i.e. effectively continuous). Idempotent: only rows
  with `delivered_at IS NULL`, due by `next_attempt_at`.
- `run_once(cfg, ...)` dispatches `deliver_row` per undelivered row by
  `target_kind`:
  - **operator** -> platform from `_operator_platform` (channel_kind stamped at
    enqueue wins, else `cfg.operator_notify_platform`): discord
    (webhook via `deliver_discord` OR bot channel via `deliver_discord_channel`),
    telegram (`deliver_telegram`), or **tui-only** = no-op (marked delivered,
    stays readable via `notifications.list`). Operator upgrade notifications
    (message starts `ArcLink update available:`) are **deferred** while a deploy
    operation is active.
  - **curator** -> `HANDLED_BY_CONSUMER` (curator brief-fanout actuated by
    `consume_curator_brief_fanout`).
  - **user-agent** -> `DEFERRED_TO_AGENT` (consumed by the agent itself).
  - **public-bot-user** -> `_deliver_public_bot_user` (Raven outbound to a
    Telegram/Discord user; supports edit-in-place of provisioning hub messages
    via `_provisioning_message_ref` / `_store_provisioning_message_ref`).
  - **captain-wrapped** -> ArcLink Wrapped reports over the same public rail;
    resolves channel via `_resolve_captain_wrapped_public_channel`; marks the
    `arclink_wrapped_reports` row delivered.
  - **public-agent-turn** -> `_deliver_public_agent_turn` (bridges a public/
    operator chat turn into the deployment's in-stack Hermes gateway; see §2d).
- Per-row errors recorded in `delivery_error` via `mark_notification_error`;
  success via `mark_notification_delivered`. Rows are leased
  (`_claim_notification_for_delivery`) so the live webhook fast path
  (`run_public_agent_turns_once`) and the periodic loop don't double-deliver.

### 1h. Rejection-incident logs — `python/arclink_rejection_incidents.py`
- This is the only thing in the codebase literally called an "incident": broker/
  helper **rejection** incident JSONL logs (not the dashboard incident state the
  symphony dreams of). `record_rejection_incident(...)` appends a redacted,
  symlink-safe, 0o600 JSONL row (`rejections.jsonl`) under state roots.
- `safe_metadata` only keeps keys/values matching `^[A-Za-z0-9_.:-]{1,160}$` —
  no free-text, no secrets. Each row stamps `trusted_host_acknowledged`.
- Consumers: `arclink_agent_process_helper.py`, `arclink_agent_user_helper.py`,
  `arclink_agent_supervisor_broker.py`, `arclink_deployment_exec_broker.py`,
  `arclink_gateway_exec_broker.py` (each records rejections when a brokered
  command is refused).

---

## 2. Proof-gated / fake-adapter / local-only behavior

### 2a. The whole live journey is gated by `ARCLINK_E2E_LIVE`
Every hosted/external/workspace step lists `ARCLINK_E2E_LIVE` in `required_env`.
With it absent, `run_live_proof` returns `blocked_missing_credentials` (exit 0
when not `--live`). No live customer journey has been proven (per
`live-e2e-secrets-needed.md`).

### 2b. Provider diagnostics `live` mode is unimplemented
`run_diagnostics(live=True)` does nothing beyond presence checks. There is no
real Stripe/Cloudflare/Chutes/Telegram/Discord connectivity probe in this module.

### 2c. External journey is opt-in per provider (`ARCLINK_PROOF_*`)
12 rows, each behind its own flag + secret refs:
`stripe_checkout_webhook_proof` (`ARCLINK_PROOF_STRIPE`),
`telegram_raven_delivery_proof` (`ARCLINK_PROOF_TELEGRAM`),
`discord_raven_delivery_proof` (`ARCLINK_PROOF_DISCORD`),
`hermes_dashboard_landing_proof` (`ARCLINK_PROOF_HERMES_DASHBOARD`),
`chutes_oauth_connect_proof` (`ARCLINK_PROOF_CHUTES_OAUTH`),
`chutes_usage_billing_sync_proof` (`ARCLINK_PROOF_CHUTES_USAGE`),
`chutes_api_key_crud_proof` (`ARCLINK_PROOF_CHUTES_KEY_CRUD` +
`ARCLINK_CHUTES_ALLOW_MUTATION`),
`chutes_account_registration_proof` (`ARCLINK_PROOF_CHUTES_ACCOUNT_REGISTRATION`),
`chutes_balance_transfer_proof` (`ARCLINK_PROOF_CHUTES_BALANCE_TRANSFER` +
mutation gate + recipient/amount),
`notion_shared_root_ssot_proof` (`ARCLINK_PROOF_NOTION_SSOT`),
`cloudflare_zone_ingress_proof` (`ARCLINK_PROOF_CLOUDFLARE`),
`tailscale_serve_cert_proof` (`ARCLINK_PROOF_TAILSCALE`).
**Important:** the runner has **no registered runners for external steps** —
with creds present and `--live`, external steps resolve to
`blocked_no_registered_runner` / "no runner registered". The external journey is
a *plan/catalog* today, not an executable proof. Only the **workspace** journey
ships executable runners.

### 2d. Public/operator agent bridge (notification delivery)
`_run_public_agent_gateway_turn` / `_run_operator_agent_gateway_turn` exec a
bridge helper *inside the deployment Hermes gateway container* (direct
`docker exec`/`docker compose exec`, or via `ARCLINK_GATEWAY_EXEC_BROKER_URL`
when the worker has no Docker socket). Command shapes are allowlisted by
`_validate_public_agent_bridge_cmd` (only `hermes-gateway` /
`control-operator-hermes-gateway`, allowlisted project regex, deployment-config
preflight). Detached mode (`ARCLINK_PUBLIC_AGENT_BRIDGE_DETACHED`, default on)
spawns a worker job (`--public-agent-bridge-worker`) so a turn can outlive the
trigger. Degraded `hermes chat -Q` fallback is **fail-closed** unless
`ARCLINK_PUBLIC_AGENT_QUIET_FALLBACK=1`. This requires a live deployment with a
running Hermes gateway — local unit behavior is the allowlist/preflight logic,
not real chat.

### 2e. Bot delivery adapters fake by default
Telegram/Discord delivery uses `arclink_telegram` / `arclink_discord`, which run
in fake mode when tokens are absent (per project conventions). Live delivery is
`PG-BOTS`.

---

## 3. Canonical vocabulary (exact names from code)

- **Modules:** `arclink_live_runner`, `arclink_live_journey`, `arclink_evidence`,
  `arclink_host_readiness`, `arclink_diagnostics`, `arclink_health_watch`,
  `arclink_notification_delivery`, `arclink_rejection_incidents`.
- **Commands / entry points:** `bin/arclink-live-proof`,
  `bin/health-watch.sh`, `bin/arclink-notification-delivery.sh`,
  `bin/health.sh`, `bin/docker-health.sh`; `python3 -m arclink_host_readiness`,
  `python3 -m arclink_diagnostics`, `python3 -m arclink_live_runner`.
- **Systemd units:** `arclink-health-watch.service`/`.timer`,
  `arclink-notification-delivery.service`/`.timer`.
- **Live runner statuses:** `blocked_missing_credentials`,
  `blocked_no_registered_runner`, `dry_run_ready`, `live_executed`.
- **Journey kinds:** `hosted`, `external`, `workspace`, `all`.
- **Tables:** `notification_outbox` (target_kind, target_id, channel_kind,
  message, extra_json, attempt_count, last_attempt_at, next_attempt_at,
  delivered_at, delivery_error), `arclink_evidence_runs` (run_id, deployment_id,
  journey, status CHECK{pending,skipped,passed,failed,blocked}, commit_hash,
  started_at[/_state], finished_at[/_state], summary_json, ledger_json,
  evidence_path, created_at), `arclink_service_health` (deployment_id,
  service_name, status, checked_at, detail_json).
- **notification_outbox target_kinds:** `operator`, `curator`, `user-agent`,
  `public-bot-user`, `captain-wrapped`, `public-agent-turn`.
- **channel_kinds:** `discord`, `telegram`, `tui-only`.
- **Control helpers:** `queue_notification`, `fetch_undelivered_notifications`,
  `mark_notification_delivered`, `mark_notification_error`,
  `active_deploy_operation`, `get_setting`/`upsert_setting`.
- **Settings keys:** `arclink_health_watch_last_status`,
  `arclink_health_watch_last_fingerprint`, `arclink_health_watch_last_summary`,
  `arclink_health_watch_last_notified_at`.
- **Evidence artifacts:** `evidence/<run_id>.json`,
  `evidence/workspace-screenshots/`.
- **Bridge sentinels:** `DEFERRED_TO_PUBLIC_AGENT_BRIDGE`, `DEFERRED_TO_AGENT`,
  `HANDLED_BY_CONSUMER`.

---

## 4. Undocumented / newer-than-docs in code

1. **`arclink_evidence_runs` DB persistence is implemented + unit-tested but
   NOT wired into anything.** `run_live_proof` writes only a JSON file under
   `evidence/`; it **never calls `store_evidence_run`** (the runner imports no
   `arclink_control`/DB at all). `store_evidence_run`/`get_evidence_run`/
   `list_evidence_runs`/`latest_evidence_status` and the table only appear in
   `tests/test_arclink_evidence.py`. No dashboard/API/operator_raven surface
   reads `arclink_evidence_runs` (grep over `arclink_dashboard.py`,
   `arclink_hosted_api.py`, `arclink_api_auth.py`, `arclink_operator_raven.py`
   found zero references). **This is a real gap between the symphony's "Dashboard
   and Raven views of the same incident/evidence state" and reality.** No doc
   states that the evidence ledger is persisted or operator-visible.
2. **External journey rows have no executable runners.** Docs imply
   `--journey external --live` runs provider proof; the code returns
   `blocked_no_registered_runner` for those steps. Only `workspace` ships
   runners (`build_workspace_live_runners`). The 12 external rows are a catalog.
3. **Workspace live runners are real and no-secret** (`deploy.sh control
   upgrade/health` + Playwright Drive/Code/Terminal). The inline browser script
   (`_browser_runner_script`) and sanitized-screenshot capture are newer than
   most prose; `live-e2e-evidence-template.md` documents them, but the
   foundation docs barely mention them.
4. **Health-watch deploy-suppression + edge-triggered fingerprint notifications**
   (skip during active deploy, only notify on fingerprint change, recovery
   message on ok) are implemented but not described in `alert-candidates.md`.
5. **The notification rail is far richer than docs describe** — 6 target_kinds
   including `captain-wrapped`, `public-agent-turn`, the detached Hermes gateway
   bridge, gateway exec broker, and message edit-in-place. `alert-candidates.md`
   doesn't mention `notification_outbox` at all.
6. **Tailscale ingress branch** in both the journey (`tailscale_ingress_health_check`)
   and diagnostics (`diagnose_tailscale`) keyed on `ARCLINK_INGRESS_MODE` is
   present in code; `live-e2e-evidence-template.md` step 6 only names the
   Cloudflare `dns_health_check`.
7. **`arclink_service_health` table** exists for per-service health snapshots but
   is populated by provisioning/other paths, not by `health_watch` (which uses
   the settings table). Worth noting so docs don't conflate the two.

---

## 5. Per-doc staleness verdicts

### docs/arclink/live-e2e-secrets-needed.md — **fresh (light)**
Accurate and current: names the live runner, all four journeys, the exact env
matrix (hosted/workspace/external), the per-provider `ARCLINK_PROOF_*` opt-in
behavior, mutation gates, and the "externally blocked, no live journey proven"
status. Correction needed: it does not warn that the **external** journey rows
have no executable runners — a reader could expect `--journey external --live`
to actually exercise providers when it returns `blocked_no_registered_runner`.

### docs/arclink/live-e2e-evidence-template.md — **light**
Matches the runner statuses and the 12 hosted + 8 workspace steps and the
sanitized-screenshot contract. Corrections: (a) step 6 should note the
Tailscale alternative (`tailscale_ingress_health_check`) when
`ARCLINK_INGRESS_MODE=tailscale`; (b) the JSON skeleton omits the ledger
`status` field that `run_live_proof` sets for blocked-while-live runs; (c) no
mention that evidence is currently file-only (not persisted to
`arclink_evidence_runs`).

### docs/arclink/local-validation.md — **fresh**
Correct: no-secret vs web vs credentialed split, `requirements-dev.txt`,
`bin/ci-preflight.sh`, the workspace live-proof invocation, and the
"skipped != proven" caution. No changes required for this subsystem beyond
optionally listing `python3 -m arclink_host_readiness`/`arclink_diagnostics`
dry-run commands.

### docs/arclink/alert-candidates.md — **heavy**
Most stale doc for this subsystem. It describes an *external* alerting pipeline
(PagerDuty/OpsGenie) polling tables, but never mentions the **in-product**
alerting that actually exists: `arclink_health_watch` edge-triggered operator
notifications, `notification_outbox`, the `tui-only`/telegram/discord operator
channel, or deploy-window suppression. Corrections: add a section on the
health-watch -> `notification_outbox` -> operator-channel rail; note the
`arclink_service_health` table is the row behind "Service unhealthy"; clarify
which signals are implemented (health-watch) vs aspirational (poll-based
Stripe/provisioning alerts have no in-repo emitter to a pager). The table still
correctly names the underlying state tables.

### docs/arclink/foundation.md — **light**
Mentions "health, notification" rails and "live proof remains gated" (lines
~90, ~180, ~285) accurately but generically. Correction: it lists
"dashboard-native Drive/Code/Terminal" health/notification as part of the
provisioned stack but doesn't enumerate the live-proof runner or evidence
ledger; acceptable as a high-level doc, but should not imply evidence is
operator-visible.

### docs/arclink/foundation-runbook.md — **light**
Line ~185 correctly lists "notification delivery, health watch" as provisioned
services; line ~574 correctly separates "completed workspace Docker/TLS proof"
from "the separate hosted customer live-proof gate". This matches code. No
correction beyond the same evidence-persistence caveat.

### docs/arclink/sovereign-control-node-symphony.md (§"Notifications, Incidents,
And Evidence", lines 734-760) — **dream shape, partially real**
This is the intended target. Honest delta vs code today:
- "Operator notifications for failed provisioning, bot delivery problems, ...":
  **partially real** — health-watch covers health failures; bot-delivery errors
  land in `delivery_error` (no operator alert is raised from them); provider
  outage/upgrade-drift/backup/ingress operator alerts are emitted by *other*
  modules, not this subsystem.
- "Dashboard and Raven views of the same incident state": **not real** — there
  is no shared incident/evidence read model; `arclink_evidence_runs` is unwired
  and unsurfaced.
- "Redacted evidence records for live proof, health runs, upgrade runs, ...":
  **partially real** — live-proof evidence JSON is redacted and written to disk;
  health/upgrade/backup runs do not produce evidence ledger records.
- Redaction guarantees (no secrets/paths/prompts in artifacts): **real** —
  enforced by `arclink_evidence` redaction + workspace command/screenshot
  sanitization + `safe_metadata` in rejection incidents.

---

## 6. GAP-* true status (subsystem touches)

J-27 maps this subsystem to `GAP-001, 005, 012, 020, 025, 026, 028, 029, 030,
031, 032, 033` plus gates `PG-PROD, PG-HERMES, PG-BACKUP, PG-SHARED-HOST`.
The subsystem-owning gaps:

- **GAP-029** (notification/incident rail, command-collision, operator
  delivery): notification_outbox rail with 6 target_kinds + health-watch
  edge-triggered operator alerts are implemented locally; live bot delivery is
  `PG-BOTS`. *Source-complete locally; live delivery proof-gated.*
- **GAP-030** (live proof / sovereign worker readiness): host readiness +
  diagnostics + journey + evidence + workspace runners implemented and
  dry-run/local-real; no credentialed live customer journey has been run
  (externally blocked). *Scaffold complete; live run pending.*
- **GAP-031** (provider state / fallback evidence): diagnostics are
  presence-only; live provider connectivity unimplemented (`live=True` is a
  stub). External provider proof rows are catalog-only (no runners).
  *Local presence checks done; live provider proof gated under PG-PROVIDER.*
- **GAP-032 / GAP-033** (evidence/governance visibility, operator surface):
  evidence ledger redaction + DB schema exist, but persistence and
  dashboard/Raven surfacing are **not wired** — the biggest open delta.
  *Partial: ledger model real, operator-visible incident/evidence state NOT.*

PG gates this subsystem proves/blocks: `PG-HERMES` (workspace TLS browser
proof), `PG-STRIPE`/`PG-PROVIDER`/`PG-BOTS`/`PG-NOTION`/`PG-CLOUDFLARE`/`PG-
TAILSCALE` (external journey catalog rows — none executable yet), `PG-PROD`
(hosted customer live proof). The live runner is the *vehicle* for these gates;
today it can only execute the workspace (PG-HERMES) runners.

---

## 7. File map (cite)
- `python/arclink_live_runner.py` — orchestration, workspace runners, CLI.
- `python/arclink_live_journey.py` — step model + 4 journey catalogs.
- `python/arclink_evidence.py` — redaction, ledger, `arclink_evidence_runs` DAL.
- `python/arclink_host_readiness.py` — readiness checks.
- `python/arclink_diagnostics.py` — presence-only provider diagnostics.
- `python/arclink_health_watch.py` — health-watch -> operator notification.
- `python/arclink_notification_delivery.py` — outbox delivery worker + bridge.
- `python/arclink_rejection_incidents.py` — redacted broker/helper incident logs.
- `bin/arclink-live-proof`, `bin/health-watch.sh`,
  `bin/arclink-notification-delivery.sh`, `bin/health.sh`, `bin/docker-health.sh`.
- `systemd/user/arclink-health-watch.{service,timer}`,
  `systemd/user/arclink-notification-delivery.{service,timer}`.
- Schema: `python/arclink_control.py` lines ~745 (notification_outbox), ~1224
  (arclink_service_health), ~2359 (arclink_evidence_runs).
- Tests: `tests/test_arclink_live_runner.py`, `test_arclink_live_journey.py`,
  `test_arclink_evidence.py`, `test_arclink_host_readiness.py`,
  `test_arclink_diagnostics.py`, `test_health_watch.py`,
  `test_health_regressions.py`, `test_arclink_notification_delivery.py`.
