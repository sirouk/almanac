# Sovereign Control Node Production Runbook

This runbook is proof-gated. It describes the production path, but a live
Control Node is not complete until credentialed health and evidence runs pass.

## Scope

Sovereign Control Node mode is the Dockerized paid self-serve control plane:
public web/API onboarding, Telegram/Discord public bot webhooks, Stripe
checkout/webhooks, domain-or-Tailscale ingress intent, fleet placement,
provisioning jobs, user/admin dashboards, and action/evidence views.

Use:

```bash
./deploy.sh control install
./deploy.sh control health
./deploy.sh control logs [SERVICE]
./deploy.sh control ps
./deploy.sh control upgrade
./deploy.sh control reconfigure
```

`./deploy.sh control upgrade` refuses dirty checkouts, fetches the configured
branch upstream, and fast-forwards before rebuilding. Use
`ARCLINK_CONTROL_UPGRADE_SKIP_UPSTREAM_SYNC=1` only for an intentional local
build window.

The old operator-led Shared Host/systemd path and public Shared Host Docker
menu are retired. Bare `./deploy.sh install`, `./deploy.sh upgrade`, and
`./deploy.sh health` are Control Node shortcuts; use explicit
`./deploy.sh control ...` commands in runbooks.

## Credential Checklist

Keep all values in private state, local environment, an interactive prompt, or a
secret manager. Never commit them.

| Area | Required Material |
| --- | --- |
| Stripe | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, product/price ids, portal configuration |
| Domain ingress | Cloudflare zone id or discoverable zone plus scoped DNS/API token |
| Tailscale ingress | Logged-in node, MagicDNS/HTTPS readiness, Serve/Funnel approval where used |
| Hosted API | `ARCLINK_SESSION_HASH_PEPPER`, `ARCLINK_SESSION_HASH_PEPPER_REQUIRED=1`, CORS/cookie settings, `ARCLINK_TRUSTED_PROXY_CIDRS` for proxy header trust, `ARCLINK_ADMIN_ALLOWED_CIDRS` for Operator admin sources, and `ARCLINK_BACKEND_ALLOWED_CIDRS` for internal backend peers |
| Public Telegram | Public onboarding bot token, `TELEGRAM_WEBHOOK_SECRET`, and webhook registration with the secret-token header |
| Public Discord | Discord bot token/application credentials and interaction endpoint |
| Model provider | Owner/admin API key for per-deployment key lifecycle |
| Fleet host | Docker access, SSH/fleet key where remote execution is enabled, writable state root |
| Notion | Shared integration token, webhook verification secret if Notion callbacks are enabled |

## Install And Configuration

1. Run `./deploy.sh control install`.
2. Choose deployment style: `single-machine` for one starter host, `hetzner`
   for registered Hetzner workers, or `akamai-linode` for registered Akamai
   Linode workers. The single-machine style defaults the executor toward the
   local worker path and starter host registration; hosted-fleet styles default
   toward SSH worker placement.
3. Choose ingress mode: `domain` or `tailscale`.
4. Choose provider adapter mode: `fake` for validation or explicit live mode
   only when credentials and operator approval are present.
5. Configure the hosted API boundary: session hash pepper, cookie/CORS values,
   proxy-trust CIDRs, Operator admin CIDRs, and internal backend CIDRs.
6. Accept the `GAP-019` Docker trusted-host acknowledgement when this machine
   is the operator-owned Control Node host. The prompt writes
   `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted` only to private Docker
   config; without it, the broker/helper services fail closed before local
   Docker/root-adjacent provisioning, upgrade, gateway, and process actions.
7. Configure Stripe price ids and webhook secret.
8. Configure public bot webhook URLs through the generated control host. The
   Telegram webhook must use `TELEGRAM_WEBHOOK_SECRET`; requests without the
   matching `X-Telegram-Bot-Api-Secret-Token` fail closed.
9. Run `./deploy.sh control health`.

If a value changes, use `./deploy.sh control reconfigure` and then rerun health.

## Workers And Mutations

`control-provisioner` is enabled by default in Control Node mode so paid
deployments do not sit silently after Stripe clears. It still fails closed until
the operator configures a real executor (`fake`, `local`, or `ssh`) and the
needed provider gates. `control-action-worker` consumes durable admin intents;
an action only proves live Docker, Stripe, Cloudflare, Tailscale, model-provider,
Discord, Telegram, or Notion mutation when the recorded executor result is
live and succeeded.

The admin dashboard/API publishes its action support matrix from
`python/arclink_dashboard.py` so the UI, tests, and runbook share one readiness
contract. Current local worker-backed actions are:

| Action | Operation kind | Local contract | Live proof gate |
| --- | --- | --- | --- |
| `restart` | `docker_compose_lifecycle` | Queue audited lifecycle restart intent; fake adapter is non-live evidence only. | `PG-PROVISION` |
| `reprovision` | `pod_migration` | Queue operator-only Pod migration/redeploy intent. | `PG-PROVISION` |
| `dns_repair` | `cloudflare_dns_apply` | Queue DNS repair from deployment metadata or stored DNS rows. | `PG-INGRESS` |
| `rotate_chutes_key` | `chutes_key_apply` | Queue provider-key rotation using secret references. | `PG-PROVIDER` |
| `refund` / `cancel` | `stripe_action_apply` | Queue Stripe action after resolving target through the control DB. | `PG-STRIPE` |
| `comp` | `control_db_comp` | Apply audited local entitlement comp; no external provider mutation is implied. | `LOCAL-CONTROL-DB` |
| `rollout` | `arcpod_update_rollout` | Queue audited local ArcPod update rollout rows from a ready dry-run preflight plan; optionally record one bounded fake/local batch. Live per-Pod refresh and health/smoke proof stay gated. | `PG-UPGRADE/PG-HERMES` |

`rollout` is now wired in `ARCLINK_ADMIN_ACTION_SUPPORT` (`worker_support="wired"`,
target kinds `deployment`/`system`). The action worker plans the update via
`plan_arcpod_update_rollout`, materializes typed `arclink_rollouts` rows through
`materialize_arcpod_update_rollout_job`, and can record one bounded batch through
`execute_arcpod_update_rollout_batch` under an explicit fake/local record-only
executor contract. No real per-Pod refresh, Docker, SSH, or live health is run;
that remains proof-gated (`PG-UPGRADE/PG-HERMES`, GAP-032). See
[GAPS.md](../../GAPS.md) for the gap taxonomy.

Pending actions such as suspend, unsuspend, force resynth, and bot-key rotation
stay visible as disabled entries (`worker_support="pending_not_implemented"`)
with fail-closed reasons until worker dispatch and policy are implemented.

Provisioning, provider actions, DNS changes, rollbacks, and admin actions use
idempotency keys. Reusing a key with the same inputs should replay the recorded
result; reusing a key with different inputs is an operator error and is rejected.
Action-worker claims are atomic, so multiple workers should not run the same
queued action concurrently.

Before enabling live mutation paths, verify:

- The Control Node host is the trusted operator machine and the private
  `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted` acknowledgement was
  made deliberately.
- `ARCLINK_EXECUTOR_ADAPTER` and live/E2E enablement are deliberate.
- The provisioner can reach Docker/fleet hosts and private state.
- Action worker results are recorded and visible in admin evidence/audit views.
- Rollback plans preserve state roots and do not delete vault, Nextcloud,
  memory, qmd, or workspace data by default.

## Operator Raven Control Surface

Operator Raven (`python/arclink_operator_raven.py`) is the chat-native operator
control console on the Operator's linked Telegram/Discord channel. It is no
longer read-only or dry-run-only: mutating commands queue real audited intents
or apply modeled local fleet-state mutations after identity and confirmation
gates. Treat this surface as proof-gated for live effect, but local-real for
queueing and control-state changes.

Read commands (never mutate): `status`, `agents`, `fleet_list`, `worker_probe`
(dry-run only in this slice; no live SSH/Docker/health probe), `user_lookup`,
`academy_status`, `academy_roster`, `upgrade_check` (fail-closed unless an
upgrade-check runner is injected), `upgrade_policy`, `action_status`,
`billing_status`, `backup_status`, and `workspace_status`.
`billing_status` is DB-only entitlement/credit posture, `backup_status` is
backup setup/write-check/activation posture, and `workspace_status` is
qmd/memory/Notion/share posture; none of them touch external providers or Agent
files.
`/upgrade_policy [component]` is an explainer only: it returns the source-owned
strategy, order, downtime posture, preflight checks, proof gates, and rollback
contract for the named component or for the full dependency family. It never
queues work.

Mutating commands (`MUTATING_COMMANDS = {pod_repair, rollout, host_upgrade,
pin_upgrade, upgrade_sweep, fleet_drain, fleet_resume}`) use a four-mode
contract:

1. `--dry-run` previews and changes nothing.
2. No `--dry-run` and no verified operator identity fails closed (read-only
   refusal).
3. No `--dry-run` with verified operator identity but no `confirm`/approval code
   fails closed and queues nothing.
4. No `--dry-run` with a verified operator identity plus confirmation queues a
   real audited intent that the action worker or enrollment-provisioner root
   maintenance loop executes asynchronously, or applies the modeled local
   fleet-state mutation (`fleet_drain`/`fleet_resume`) with audit/event rows.

Even when queued, live mutation stays gated by `ARCLINK_EXECUTOR_ADAPTER`
(`fake` records only) and per-action proof gates: `pod_repair` actions
(`restart`/`reprovision` PG-PROVISION, `dns_repair` PG-INGRESS), `rollout`
(PG-UPGRADE/PG-HERMES), `host_upgrade`/`pin_upgrade` (operator-upgrade-broker,
risk-accepted under GAP-019). Fleet drain/resume does not run SSH, Docker,
provider, firewall, or port-22 changes from chat; it only changes placement
eligibility in the control DB, and draining the last eligible worker requires
an explicit `--force` maintenance-window acknowledgement.

Pinned-component upgrades are discovered hourly by
`python/arclink_pin_upgrade_check.py` through
`arclink-curator-refresh.timer` and can also be triggered from the control node
with `./deploy.sh pin-upgrade-notify`. Detector notifications are digest-style
and their buttons are preview/dismiss only. `/pin_upgrade <component> confirm`
resolves an active detector payload token with concrete target pins and queues
that token into `operator_actions`; if no active detector payload exists, Raven
refuses and tells the operator to run/wait for the detector. `/upgrade_sweep`
is the simple operator path for "apply the pending detector digest": dry-run
lists the selected payloads; confirm queues the stateless payloads; stateful
payloads (`postgres`, `redis`, `nextcloud`) require
`--include-stateful` inside a maintenance window. The root maintenance loop
applies queued pin payloads sequentially, while ArcPod runtime rollout remains
bounded/canary-driven through `/rollout <target>`.

### Operator Confirmation

All Operator Raven mutating commands require verified operator identity plus a
second confirmation. Operators should run `--dry-run` first. If no operator
approval code is configured, append the literal `confirm` token, such as
`/upgrade confirm`. If a code is configured, it is read from
`ARCLINK_OPERATOR_TELEGRAM_APPROVAL_CODE` or `ARCLINK_OPERATOR_APPROVAL_CODE`
(first non-blank wins) and verified with a constant-time compare
(`hmac.compare_digest`) on the trailing token before the command parser ever
sees it. A missing/wrong code or missing `confirm` fails closed and queues
nothing. Keep the approval code in private state only; never commit it.

### Two Action Queues

Operator Raven writes to two distinct queues, drained by different workers:

- `arclink_action_intents` (with attempts in `arclink_action_attempts`) is
  drained by `control-action-worker` (`python/arclink_action_worker.py`).
  `pod_repair` and `rollout` queue here via `queue_arclink_admin_action`, as do
  admin dashboard/API actions.
- `operator_actions` is drained by the enrollment-provisioner root maintenance
  loop. `host_upgrade` (`upgrade`) and detector-token `pin_upgrade`/
  `upgrade_sweep` (`pin-upgrade`) queue here via `request_operator_action`; in
  Docker component-upgrade mode the loop reaches the host through
  `operator-upgrade-broker` (see the
  [operations runbook](operations-runbook.md) GAP-019 entries for the
  authoritative trusted-host boundary).

### Operator Single Hermes Agent

The Operator gets exactly ONE in-stack Hermes agent
(`python/arclink_operator_agent.py`), a first-class control-stack Compose
identity (`DEFAULT_OPERATOR_AGENT_DEPLOYMENT_ID="operator"`, runtime
`control-stack`), not a tenant ArcPod and not a legacy shared-host install. The
one-agent invariant is enforced (`assert_single_operator_agent` raises if more
than one exists); the deployment is comped and stamped `operator_agent=True`,
`not_arcpod=True`. Runtime setup is handled by
`bin/install-operator-hermes-home.sh` plus the Control Node Compose services;
the module itself is control-DB only and never runs Docker or SSH.

Free-form operator chat that is not a Raven command is bridged to this single
agent: when the conversation is routable, `enqueue_operator_agent_turn` queues
the message (stamped `operator_turn=True`, `source_kind="operator_chat"`)
through the existing `public-agent-turn` notification worker, and the in-stack
Hermes gateway replies asynchronously. A live reply requires a running gateway
and Hermes runtime (PG-HERMES). If the agent is not routable, the channel falls
back to the Raven control intro.

## Operator Pod Migration

Wave 3 Pod migration is an Operator-only rollout path. Captain-initiated
migration remains disabled by default with
`ARCLINK_CAPTAIN_MIGRATION_ENABLED=0`; do not expose a Captain dashboard button
or user API route until policy and live proof are complete.

Operators queue migration through the existing admin action rail:

```json
{
  "action_type": "reprovision",
  "target_kind": "deployment",
  "target_id": "<deployment_id>",
  "metadata": {
    "target_machine_id": "current",
    "reason": "redeploy in place"
  }
}
```

Use `target_machine_id=current` or omit it for redeploy-in-place. Use a fleet
host id or linked inventory machine id to move the Pod to another worker. The
action worker calls `python/arclink_pod_migration.py`, captures source state to
`<state_root_base>/.migrations/<migration_id>/`, materializes it on the target
state root, runs executor-backed Compose apply, verifies health, and records
`pod_migration_started`, `pod_migration_completed`, or
`pod_migration_rolled_back`. Failed host moves tear down the target Compose
stack without deleting retained state and restart the source Compose stack.

Migration operation idempotency keys are `arclink:migration:<migration_id>`.
Replaying the same migration id with the same intent returns the prior terminal
result; changing the target for the same migration id is rejected. Successful
migrations retain captured source-state artifacts until
`ARCLINK_MIGRATION_GC_DAYS` elapses, default `7`; the control action-worker
loop removes expired successful captures during its normal periodic pass.

## Fleet Inventory And ASU Placement

The Operator inventory path is local-first and proof-gated for cloud providers:

```bash
./deploy.sh control inventory list
./deploy.sh control inventory add manual
./deploy.sh control inventory probe <machine-id|hostname>
./deploy.sh control inventory drain <machine-id|hostname>
./deploy.sh control inventory remove <machine-id|hostname>
./deploy.sh control inventory set-strategy standard_unit
```

Manual registration works without cloud credentials and reuses the control
fleet SSH key guidance. Hetzner and Linode commands fail closed until
`HETZNER_API_TOKEN` or `LINODE_API_TOKEN` is configured in private control-node
config; missing tokens print "configure provider to enable" and do not make API
calls.

ArcPod Standard Unit sizing defaults to 1 vCPU, 4 GiB RAM, and 30 GiB disk per
Pod. Operators can tune `ARCLINK_ASU_VCPU_PER_POD`,
`ARCLINK_ASU_RAM_PER_POD`, and `ARCLINK_ASU_DISK_PER_POD`. Placement keeps the
legacy `headroom` strategy by default. Setting
`ARCLINK_FLEET_PLACEMENT_STRATEGY=standard_unit` makes new placements prefer
the machine with the most available ASU while existing placements remain
unchanged.

## Stripe Webhook

Create a selected-event Stripe destination at:

```text
https://<control-host>/api/v1/webhooks/stripe
```

Use the endpoint signing secret as `STRIPE_WEBHOOK_SECRET`. If the secret is
unset, the hosted API returns a misconfigured error and 503 so Stripe retries;
it does not silently accept or skip the event.

Webhook rows are stored in `arclink_webhook_events`.

## Public Bot Webhooks

Telegram webhook handling is intentionally fail-closed. Production must set
`TELEGRAM_WEBHOOK_SECRET`, and webhook registration must send that value as the
Telegram secret token. The API rejects missing or mismatched secret-token
headers before dispatching the update.

Discord interaction handling verifies the Discord signature, enforces timestamp
tolerance, and records interaction ids so replayed interactions do not run
twice. Stripe, Telegram, and Discord webhook routes all pass through hosted API
rate limits before expensive verification work.

## Crew Training

Production Crew Training is available through the Captain dashboard and Raven
public bot `/train-crew`; `/whats-changed` reports the current recipe against
the prior archived recipe. The hosted API exposes user routes for read, preview,
and apply, plus an admin-on-behalf apply route guarded by admin session, CIDR,
CSRF, mutation role, MFA where configured, and audit logging.

The confirmed recipe lifecycle is one active `arclink_crew_recipes` row per
Captain. Applying a new recipe archives the old active row and writes the
Captain role, mission, and treatment fields on `arclink_users`. Persona change
is overlay-only: ArcLink projects Crew fields into
`state/arclink-identity-context.json` for local Pod Hermes homes and leaves
memory, sessions, and Hermes gateway processes untouched.

Live LLM recipe generation is proof-gated behind the existing scoped provider
credential and budget boundary. If the Captain has no allowed provider
credential, or if generated output fails the unsafe-output boundary for URLs,
shell commands, or jailbreak patterns, ArcLink uses a deterministic preset-only
fallback and labels that state in API, dashboard, and bot responses.

## ArcLink Wrapped

ArcLink Wrapped is the Captain-facing period report for scoped activity across
the Captain's own Pods, same-Captain Comms, audit/event rows, read-only Hermes
session counts, vault reconciler deltas, and memory synthesis cards. The
implementation owner is `python/arclink_wrapped.py`; API, dashboard, bot, and
scheduler surfaces should not duplicate Wrapped SQL, scoring, redaction, or
privacy rules.

The scheduler is the named Docker job-loop service `arclink-wrapped`, running
`bin/arclink-wrapped.sh`. It generates due reports on each local loop, respects
per-Captain cadence (`daily`, `weekly`, or `monthly`; default `daily`), retries
failed reports on the next eligible cycle, and queues persistent failures to
Operator notification rows without Captain narrative.

Captain delivery goes through `notification_outbox` with
`target_kind='captain-wrapped'`; delivery resolution and final delivered-state
marking remain owned by `python/arclink_notification_delivery.py`. Supported
quiet-hours windows such as `22:00-08:00` delay `next_attempt_at`. Unsupported
free-form quiet-hours text is treated as no delay rather than inventing a new
scheduling contract.

Captain surfaces are `GET /user/wrapped`, `POST /user/wrapped-frequency`, the
dashboard Wrapped tab, and Raven's pure `/wrapped-frequency` handler for
`daily`, `weekly`, or `monthly`. Operator surfaces are `GET /admin/wrapped`
and the admin Wrapped panel; they expose aggregate status and novelty scores
only, never report text, Markdown, or raw ledger snippets.

Production proof should include `./deploy.sh control health`, the focused
Wrapped and notification tests, and inspection of `arclink-wrapped` service
logs after the control stack is up. Live bot command registration and webhook
mutation remain separate operator-gated actions.

## Teardown

Cancellation and teardown are explicit lifecycle states, not implicit deletion.
The worker handles `teardown_requested`, retryable teardown failure, and
resource-bearing cancelled deployments by stopping Compose, removing managed
DNS where applicable, revoking provider artifacts when configured, releasing
fleet placement and ports, and recording audited timeline events before moving
the deployment to `torn_down`.

Compose volume deletion is off by default. It requires explicit teardown
metadata, and operators should treat it as a data-destructive action requiring a
separate approval trail. Local and remote materialized secret files are cleaned
after Compose operations, but private source secrets remain in private state.

## Evidence Capture

No production claim is complete without evidence:

```bash
bin/arclink-live-proof --live --json
bin/arclink-live-proof --journey workspace --live --json
```

The workspace proof requires the web dependencies under `web/`, a real HTTPS
Hermes dashboard URL, and auth material supplied only through environment. Save
redacted evidence using `docs/arclink/live-e2e-evidence-template.md`.

## Rollback

Use rollback only from recorded deployment/provisioning state. A safe rollback
plan preserves state roots, stops or restarts unhealthy services, and keeps
secret references for manual review. Volume deletion, state-root deletion, DNS
teardown, and provider revocation require separate explicit operator approval
and audit records.

## Known Proof-Gated States

- Fake Stripe/Cloudflare/model-provider/bot adapters prove contract behavior only.
- Dry-run provisioning proves rendered intent, not live container health.
- Queued admin actions prove operator intent, not provider mutation.
- Passing unit tests does not prove live Stripe, ingress, model-provider, bots,
  Notion, fleet host access, or customer dashboard TLS.
