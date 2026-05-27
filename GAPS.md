# ArcLink Gap Register

This register was regenerated from source evidence, not from the prior root
stub or older optimistic product-matrix reads. `research/PRODUCT_REALITY_MATRIX.md`
currently parses to 101 `real`, 0 `partial`, 0 `gap`, 15 `proof-gated`, and
5 `policy-question` rows, and `tests/test_documentation_truths.py` now guards
those totals and row evidence. This register remains the implementation
planner for proof-gated, policy-question, security, UX, ops, and doc risks.

Use this register as the implementation planner. A gap is not closed by better
copy alone unless its `Next repair` says the problem is documentation-only; it
is closed by source change, focused local proof, policy decision, or authorized
live proof that directly addresses the row. P0/P1 rows should be scheduled
before P2/P3 polish unless the operator explicitly accepts the launch risk.

## Taxonomy

Each gap row uses this shape: one `GAP-###` ID, one severity, one or more status
labels, one or more `J-##` journey joints from
`research/COVERAGE_MATRIX.md`, optional `PG-*` proof-gate IDs, source evidence,
impact, owner/surface, and next repair.

Status labels:

- `gap`: the expected product contract is absent or contradicted.
- `partial`: some code exists, but the end-to-end user contract is incomplete.
- `proof-gated`: source exists, but the claim needs authorized live/external
  proof before it can be called `real`.
- `policy-question`: code cannot choose the product behavior.
- `test-gap`: code may exist, but tests do not prove the risky contract.
- `doc-gap`: docs are stale, contradictory, or omit important contract details.
- `ux-gap`: a user can get misleading, blocked, or under-explained behavior.
- `ops-gap`: operator procedures are incomplete, unproven, or easy to misuse.
- `security-risk`: a trust, isolation, secret, auth, or destructive-operation
  boundary needs hardening or explicit proof.
- `real`: checked and supported by source evidence plus local tests or dry-run
  proof. Real items belong under "Not Gaps / Already Real", not in the active
  gap register.

Severity:

- `P0`: blocks trust, security, isolation, payment, provisioning, or production
  launch.
- `P1`: blocks a core user journey.
- `P2`: degrades or confuses a journey, or leaves an important proof/test gap.
- `P3`: polish, scale, or future-proofing.

## Operator Decision Summary

This register is not a launch checklist with boxes quietly assumed green. Treat
it as the decision map for what can ship locally, what needs implementation,
what needs policy, and what needs an authorized proof window.

- Immediate launch blockers: `GAP-001` keeps the full production journey
  proof-gated, and `GAP-019` marks Docker socket/root access as a P0
  trusted-host boundary. Local hardening now includes capability drops, a
  source-owned authority inventory, a `GAP-019-B2` broker/no-go review, and an
  action-worker lifecycle path-override guard, plus a `GAP-019-C` public-Agent
  bridge command guard, `GAP-019-D` removal of the `curator-refresh` Docker
  socket, `GAP-019-E` control-provisioner executor preflight, and `GAP-019-F`
  notification-delivery gateway exec broker split. `GAP-019-G` now removes the
  Docker socket from `control-provisioner` and adds a deployment exec broker.
  `GAP-019-H` now removes the Docker socket from the root
  `control-action-worker` by requiring the deployment exec broker for
  Docker-mode local lifecycle/apply calls. `GAP-019-I` now removes the Docker
  socket from the root `agent-supervisor` by adding an
  `agent-supervisor-broker` for dashboard network/proxy sidecar operations, but
  remaining broker/root residual risk still needs more helper work or operator
  acceptance. `GAP-019-J` now routes queued Docker-mode operator upgrades and
  pinned-component upgrade apply/final-upgrade calls through a broker with
  raw-command rejection and private operator-action log confinement.
  `GAP-019-K` now makes non-dry-run Pod migration capture fail closed unless
  the operator opens an explicit root-capture window and capture paths are
  deployment-scoped. `GAP-019-L` now validates active-agent metadata,
  canonical Docker agent homes, Hermes homes, workspace/log/process keys, and
  agent-process env/command arguments before helper, broker, or process-helper
  requests.
  `GAP-019-M` now records source-owned incident controls for the remaining
  writeable socket brokers and explicit root helpers, including monitored
  signals, status/log/audit locations, triage steps, fail-closed action, and
  escalation boundary. `GAP-019-N` now removes the root boundary from
  `control-action-worker` by adding a tokened root `migration-capture-helper`
  for Docker-mode Pod migration capture/materialization, with raw-command
  rejection and deployment-scoped path validation. `GAP-019-O` now removes
  direct user/home setup from the root `agent-supervisor` by adding a tokened
  root `agent-user-helper` for Docker-mode user/home setup, with raw-command
  rejection and canonical agent-home, Hermes-home, and workspace validation.
  `GAP-019-P` now removes explicit root and setpriv process launching from
  `agent-supervisor` by adding a tokened root `agent-process-helper` for
  Docker-mode install, refresh, cron, gateway, and dashboard process execution,
  with raw-command rejection and typed agent-context validation. `GAP-019-Q`
  now removes Docker's default Linux capability set from `agent-user-helper`
  and adds back only `CHOWN`, `DAC_OVERRIDE`, and `FOWNER` for validated
  Docker agent-home writes and ownership repair. `GAP-019-R` now keeps
  validated agent-process env values out of setpriv argv and process-helper
  startup logs, and strips supervisor broker/helper tokens from per-agent
  process specs before dispatch. `GAP-019-S` now rejects configured Docker
  agent-home, repo, private-state, state, and runtime root mismatches inside
  the root helpers before root filesystem work, helper logs, or subprocess
  execution. `GAP-019-T` now mounts the live host repo read-only for
  `agent-process-helper`, `agent-supervisor`, and `curator-refresh`, while
  `GAP-019-U` moves the writable host repo bind and upgrade operations out of
  `agent-supervisor-broker` into `operator-upgrade-broker` as the explicit
  queued Docker-mode operator-upgrade exception. `GAP-019-V` removes the
  remaining read-only Docker socket discovery boundary from `control-ingress`
  by switching Control Node ingress to static Traefik file-provider routes.
  `GAP-019-W` now rejects ArcLink broker/helper/control token env keys at the
  `agent-process-helper` boundary before logs or subprocess execution.
  `GAP-019-X` now removes broad `*arclink-env` inheritance and the global
  `arclink-priv/secrets/container` mount from the root
  `agent-process-helper`, leaving only explicit non-secret path validation env,
  token/listener keys, and the mounts needed for allowlisted agent commands.
  `GAP-019-Y` now removes broad `*arclink-env` inheritance and broad private
  config/state/secrets mounts from `gateway-exec-broker`, leaving only broker
  token/listener env, `ARCLINK_STATE_ROOT_BASE`, the deployment state-root bind,
  and the writeable Docker socket needed for public-Agent gateway exec.
  `GAP-019-Z` now applies the same service-boundary narrowing to
  `agent-supervisor-broker`, leaving only Docker binary/image, repo path,
  host/container private path metadata, broker token/listener env, and the
  writeable Docker socket needed for dashboard network/proxy sidecars.
  `GAP-019-AA` now narrows `deployment-exec-broker` to minimal service env:
  broker token/listener settings, `ARCLINK_STATE_ROOT_BASE`, optional Docker
  binary, the deployment state-root bind, and the writeable Docker socket
  needed for allowlisted deployment Compose operations.
  `GAP-019-AB` now narrows `operator-upgrade-broker` to minimal service env,
  removes broad canonical private config/state/secrets mounts, and replaces
  upgrade subprocess full-env inheritance with a child-process env allowlist.
  `GAP-019-AC` now narrows `migration-capture-helper` to minimal service env
  and configured state-root confinement: it keeps only `ARCLINK_STATE_ROOT_BASE`
  plus helper token/listener env, and source, target, and staging paths must
  resolve under that base before root copy/materialize work starts.
  `GAP-019-AD` now hardens `agent-process-helper` pre-drop executable lookup:
  request `PATH` must match `SAFE_PATH`, the helper invokes
  `/usr/bin/setpriv` by absolute path, and identity setup fails closed without
  the pinned runtime venv Python instead of falling back to bare `python3`.
  `GAP-019-AE` now hardens `agent-user-helper` root account/ownership
  executable lookup: the helper invokes `/usr/sbin/groupadd`,
  `/usr/sbin/useradd`, and `/usr/bin/chown` by absolute trusted path and fails
  closed if any required executable is unavailable before user/home mutation.
  `GAP-019-AF` now hardens `agent-supervisor-broker` Docker CLI lookup:
  `ARCLINK_DOCKER_BINARY` must resolve to a trusted Docker executable path, and
  unsafe, missing, non-executable, or non-Docker values fail closed before
  dashboard network/proxy subprocesses run. `GAP-019-AZ` now makes the same
  broker reject unsafe `ARCLINK_DOCKER_HOST_PRIV_DIR` and
  `ARCLINK_DOCKER_CONTAINER_PRIV_DIR` private bind-root values before proxy
  config hashing, Docker CLI lookup, container inspect, `docker run -v`, or a
  successful dashboard proxy response. `GAP-019-AG` now applies the same
  Docker CLI lookup hardening to `deployment-exec-broker` before deployment
  Compose subprocesses run, and `GAP-019-AH` applies it to
  `gateway-exec-broker` before public Agent gateway discovery or exec.
  `GAP-019-AI` now applies the same hardening to `operator-upgrade-broker`
  before queued Docker-mode operator upgrade or pin-upgrade child subprocesses
  run. `GAP-019-AJ` now makes `agent-process-helper` compare desired
  gateway/dashboard command, cwd, and env signatures and perform bounded
  process-group shutdown before replacement when those validated specs change.
  `GAP-019-AK` now removes default Compose network reachability from the
  tokened Docker/root brokers and helpers by placing their request lanes on
  internal networks shared only with legitimate callers, while preserving
  single-service egress networks for `agent-process-helper` and
  `operator-upgrade-broker` outbound runtime/upgrade work.
  `GAP-019-AL` now adds an explicit fail-closed trusted-host acknowledgement
  gate: the seven high-authority brokers/helpers require
  `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted` in private Docker config
  before binding request listeners or processing direct helper/broker work.
  `GAP-019-AM` now makes `agent-process-helper` and `agent-supervisor` reject
  dynamic-loader, Python path/startup, shell startup, Git/SSH command-steering,
  and secret-looking process env keys before helper logs, subprocess execution,
  or helper payload construction.
  `GAP-019-AN` now makes `agent-user-helper` and `agent-process-helper` reject
  symlink-escaped agent home, Hermes home, and workspace paths before root
  filesystem work, helper logs, or subprocess execution.
  `GAP-019-AO` now makes `agent-process-helper` reject symlink-escaped helper
  log directories before opening log files, `subprocess.run`, or
  `subprocess.Popen`.
  `GAP-019-AP` now makes direct/local execution of the seven high-authority
  broker/helper modules bind `127.0.0.1` by default, while Compose remains the
  explicit `0.0.0.0` opt-in for internal request-network reachability.
  `GAP-019-AQ` now replaces `agent-supervisor` enrollment-provisioner
  `os.environ.copy()` child inheritance with an explicit env allowlist for
  Docker mode/path config, runtime roots, service URLs, and helper/broker
  values while excluding unrelated payment, provider, bot, ingress,
  memory-synthesis, session, fleet, Python path, and Git/SSH steering env keys.
  `GAP-019-AR` now makes `agent-process-helper` and
  `agent-supervisor-broker` reject unsafe dashboard backend host values before
  dashboard process or proxy subprocess construction; accepted values are
  loopback or Docker-internal/private/link-local IPs, while wildcard, global,
  multicast, malformed, and non-IP values fail closed. `GAP-019-AS` now makes
  `agent-user-helper` and `agent-process-helper` reject symlinked configured or
  requested Docker agent-home roots before uid/gid assignment writes, ownership
  repair, helper logs, or subprocess execution. `GAP-019-AT` now makes
  `agent-process-helper` reject symlinked configured or requested repo,
  private-state, state, and runtime roots before helper logs,
  cwd/command/runtime lookup, or subprocess execution. `GAP-019-AU` now makes
  `agent-process-helper` reject missing, symlinked, directory, unreadable, or
  non-executable fixed repo command targets before helper logs or subprocess
  execution. `GAP-019-AV` now makes `operator-upgrade-broker` reject missing,
  symlinked, directory, unreadable, or non-executable fixed `deploy.sh` and
  `bin/component-upgrade.sh` targets before private operator logs or upgrade
  subprocess execution. `GAP-019-AW` now makes the same broker reject relative,
  out-of-private-state, or symlink-steered upstream deploy-key and known-hosts
  paths before child env construction, private operator logs, or upgrade
  subprocess execution. `GAP-019-AX` now makes `deployment-exec-broker`
  reject symlinked deployment config roots and symlinked, missing,
  non-regular, or unreadable rendered `config/arclink.env` and
  `config/compose.yaml` files before Docker CLI lookup or Compose subprocess
  dispatch. `GAP-019-AY` now makes `gateway-exec-broker` reject symlinked,
  missing, non-regular, unreadable, or directory Compose fallback
  `config/arclink.env` and `config/compose.yaml` targets before fallback
  dispatch or a successful public Agent gateway broker response. `GAP-019-AZ`
  now makes `agent-supervisor-broker` reject relative, root, colon-bearing,
  newline/carriage-return/NUL-bearing, dot/dotdot, or non-canonical
  host/container private bind roots before dashboard sidecar Docker lookup or
  dispatch. `GAP-019-BA` now makes `agent-user-helper` reject symlinked,
  directory, or non-regular `.arclink-user-ids.json` and
  `.arclink-user-ids.json.tmp` paths before uid/gid assignment writes, account
  commands, agent-home directory creation, or recursive ownership repair.
  `GAP-019-BB` now makes `agent-process-helper` append redacted
  rejected-request incidents to
  `state/docker/agent-process-helper/rejections.jsonl` under the configured
  private root, without raw request bodies, env values, args, tokens, private
  paths, or stack traces. `GAP-019-BC` now adds the same redacted
  rejected-request evidence for `gateway-exec-broker` under the configured
  deployment state root, and `GAP-019-BD` extends it to
  `deployment-exec-broker`, `migration-capture-helper`, `agent-user-helper`,
  `agent-supervisor-broker`, and `operator-upgrade-broker` using only scoped
  state roots or a narrow dashboard-broker incident mount.
- Core journey blockers: `GAP-002` through `GAP-006`, `GAP-018`,
  `GAP-026`, and `GAP-028` affect
  payment, bots, provisioning, Hermes workspace proof, provider policy, and
  admin live side effects, plus live upgrade and Shared Host install proof.
  `GAP-018` now has a local source-owned readiness matrix, but live side
  effects remain proof-gated. `GAP-007` now fails closed locally and remains
  live-proof-gated by `PG-NOTION`; `GAP-011`, `GAP-012`, and `GAP-025` are
  locally closed as of the 2026-05-22 product-matrix truth guard pass.
- Planning backlog: remaining P2/P3 rows cover live backup restore proof,
  browser share broker/adapter proof, live share notification delivery,
  migration, cloud fleet proof, Crew Training generation, selected-agent
  streaming, and provider self-service clarity. Browser token storage, web
  channel copy, backup pending-status handoff, share no-channel dashboard
  recovery, share notification retry queueing, the fail-closed Drive/Code
  authenticated `Request Share` contract, and linked copy policy are now
  locally repaired.
- Policy gates: provider self-service, provider account lifecycle, threshold
  behavior, Captain migration, browser share broker/adapter, backup automation,
  destructive teardown authority, and Discord Curator operator-action authority
  need operator decisions before code should pretend the behavior is settled.
- Proof gates: no live gate in the Proof Gates table is closed by this document
  handoff. Move a row to `real` only after the named proof runs and redacted
  evidence exists outside tracked public docs.

## How To Plan From This Register

Use the register as an ordered work queue, not as a loose list of concerns.

1. Start with P0 trust and launch gates: production E2E proof (`GAP-001`) and
   Docker/root trusted-host hardening (`GAP-019`). Broad local suite validation
   is currently green, but must be rerun after each source/test slice.
2. Then schedule P1 user-journey blockers: live billing, bot delivery,
   provisioning/ingress, Hermes workspace proof, provider policy/proof, Notion
   verification truth, admin live action proof, live upgrade proof, and Shared
   Host install/enrollment smoke proof.
3. Pull P2/P3 rows when they share code ownership with an active P0/P1 slice, or
   when the operator explicitly accepts the higher-priority residual risk.
4. For every row, choose the closure type before editing: code repair, local
   test, documentation correction, operator policy decision, or authorized live
   proof. A row that needs live proof is still open after fake/local tests pass.
5. When a row closes, update this register, the relevant journey status callout,
   and any matrix/runbook that would otherwise preserve the old claim.

Implementation planning rule: do not batch unrelated live proof, policy, and
code repairs into one vague "finish launch" task. Each gap row should produce a
bounded patch, a bounded proof run, or a concrete operator decision record.

Document-phase closeout rule: this register is complete for public handoff when
each source-grounded blocker has a severity, status, journey joint, owner,
impact, and next repair, and when live proof/policy gates are explicit rather
than hidden in optimistic copy. The open rows below are not document-phase
blockers unless their `Next repair` is documentation-only; they are the
implementation and operator-decision backlog.

## P0/P1 Launch Decision Ledger

This table is the shortest implementation-planning path through the hard
truth. It does not replace the detailed rows; it tells the operator what kind of
closure is required before a launch or core journey claim can move forward.

| Gap | Launch meaning | Closure type | First concrete action |
| --- | --- | --- | --- |
| `GAP-001` | Whole paid Control Node journey is not production-proven | Authorized live proof | Run `PG-PROD` only after real Stripe, bots, ingress, provider, host, and workspace proof inputs are ready. |
| `GAP-019` | Docker/root authority is a trusted-host P0 boundary | Security hardening and operator risk decision | Capability drops, authority inventory, B2 review, action-worker path guard, public-Agent bridge command guard, curator-refresh socket removal, control-provisioner executor preflight, notification-delivery gateway exec broker split, deployment exec broker split, action-worker socket removal, agent-supervisor dashboard broker split, operator-upgrade broker routing, root-capture opt-in, agent-supervisor metadata/path guards, migration-capture helper split, agent-user helper split, agent-process helper split, agent-user-helper capability narrowing, process-helper argv/log env hardening, helper configured-root confinement, read-only non-broker host-repo binds, static `control-ingress` routes, process-helper control-token env rejection, process-helper service env/secret-mount narrowing, gateway-exec broker service env/private-mount narrowing, agent-supervisor broker service env/private-mount narrowing, deployment-exec broker service env narrowing, operator-upgrade broker service/private-mount/child-env narrowing, migration-capture-helper service-env/state-root confinement, process-helper pre-drop executable lookup hardening, agent-user-helper root executable lookup hardening, agent-supervisor-broker Docker CLI lookup hardening, deployment-exec-broker Docker CLI lookup hardening, gateway-exec-broker Docker CLI lookup hardening, operator-upgrade-broker Docker CLI lookup hardening, process-helper desired-signature restart/bounded shutdown, broker/helper internal Compose network scoping, the explicit `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted` fail-closed acknowledgement gate, process-helper unapproved env key rejection, root agent-helper symlink path rejection, process-helper log-directory symlink rejection, loopback direct-run listener defaults, agent-supervisor provisioner child-env allowlisting, dashboard backend host confinement, configured agent-home root symlink rejection, process-helper configured-root symlink rejection, process-helper fixed command target preflight, operator-upgrade broker fixed script target preflight, operator-upgrade broker upstream deploy-key path confinement, deployment-exec broker rendered config-file preflight, gateway-exec broker fallback config-file preflight, agent-supervisor broker private-bind-root preflight, agent-user-helper assignment-file preflight, agent-process-helper rejected-request incident evidence, gateway-exec-broker rejected-request incident evidence, and remaining high-authority broker/helper rejected-request incident evidence are local repairs; next closure requires more helper/process-runner isolation or explicit accepted residual risk. |
| `GAP-002` | Payment and entitlement cannot be called live-ready | Authorized live proof | Run Stripe checkout, webhook, portal, failure, cancellation, and refuel proof rows with redacted evidence. |
| `GAP-003` | Chat-first Raven and selected-agent delivery may strand users | Authorized live proof | Prove Telegram and Discord independently, including commands, buttons, callbacks, and handoff delivery. |
| `GAP-004` | Paid ArcPod provisioning may not create a reachable deployment | Authorized live proof | Prove one domain-mode and one Tailscale-mode deployment, health check, rollback, and teardown. |
| `GAP-005` | Dashboard-to-Hermes workspace promise is not browser-proven | Authorized workspace proof | Run desktop/mobile workspace proof against a real TLS Hermes dashboard and plugin surface. |
| `GAP-006` | Agents may deploy without settled provider/inference behavior | Policy decision plus authorized provider proof | Decide provider self-service/account policy, then prove router inference, key lifecycle, usage, and budget behavior. |
| `GAP-007` | Notion setup can no longer be mistaken locally for live-verified integration | Authorized live Notion proof remains | Run shared-root read/write/webhook proof before saying setup is complete. |
| `GAP-018` | Admin buttons may be confused with live side effects | Authorized live proof after local matrix repair | Source-owned readiness matrix is local; next closure requires proving the smallest safe live action subset. |
| `GAP-026` | Upgrade paths cannot be called live-ready | Authorized live proof | Run `PG-UPGRADE` across the relevant shared-host, Docker, Control Node, and component-pin upgrade path with release-state, health, and smoke evidence. |
| `GAP-028` | Shared Host fresh install/enrollment cannot be called currently smoke-proven | Authorized host-mutating proof | Run `PG-SHARED-HOST` on a supported Linux/systemd host with redacted install, health, enrollment, and cleanup evidence. |
| `GAP-029` | Sovereign Operator Raven is not yet a full-service control plane | Product buildout plus operator-security policy | First read-only/dry-run slice exists; expand only through typed, authorized, audited action-worker/broker commands. |
| `GAP-030` | Control Node install can be up before worker capacity is proven | Code repair plus fleet/provisioning proof | Gate "ready to provision" on at least one verified worker, or clearly finish install as "control plane up, provisioning blocked." |
| `GAP-031` | Router/provider failover lacks explicit `>=429` fallback cascade | Code repair plus provider proof | Add bounded router fallback models, preserve provider-side CSV fallback guidance, record fallback usage, and prove overload recovery without raw prompt leakage. |
| `GAP-032` | Hermes/ArcPod updates are not yet rolling from the Control Node | Orchestrator buildout plus upgrade proof | Add bounded-parallel ArcPod update orchestration with per-pod health/smoke evidence and rollback/stop behavior. |
| `GAP-033` | Cross-surface experience quality is not enforced as one gate | Quality gate plus focused UI/bot/CLI tests | Add a shared finish gate for Raven, dashboard, plugins, CLI, and TUI copy/formatting so product surfaces stay clear and polished. |
| `GAP-034` | Academy Trainer is not yet a full subject-matter corpus and continuing education pipeline | Product buildout plus data/source policy | Build the Academy source-lane registry, archive manifest, curriculum/evaluation pipeline, SOUL/skill/vault application, and weekly continuing education job before claiming Crew members become trained experts. |
| `GAP-011` | Closed locally: foundation docs now align with Control Node boundaries | Documentation repair plus truth test | Keep `tests/test_documentation_truths.py` guarding stale prototype wording. |
| `GAP-025` | Closed locally: broad Python suite is green | Regression triage and repair | Keep `python3 -m pytest -q tests` as the broad no-secret local validation gate. |

Operator decision rule: if the closure type is live proof or policy, a local
fake test can reduce implementation risk but cannot close the row. If the
closure type is documentation/schema repair, it can close only after the
corresponding truth or contract test passes.

## Gap Register

Closed local rows are retained below for stable `GAP-###` handoff continuity
when they were active blockers during this buildout pass. Treat rows marked
`real` as closed local evidence, not as open implementation backlog.

### GAP-001 - Production live E2E is unproven

- Severity: P0
- Status: proof-gated
- Journey joints: `J-01`, `J-02`, `J-03`, `J-06`, `J-09`, `J-13`, `J-18`, `J-19`, `J-27`
- Proof gates: `PG-PROD`, `PG-STRIPE`, `PG-BOTS`, `PG-PROVISION`, `PG-PROVIDER`, `PG-HERMES`
- Joint: launch-live claim for the whole Sovereign Control Node journey
- Expected: a complete paid user can enter from web or public bot, pay, get an
  ArcPod, use dashboard/Hermes, receive bot handoff, refuel, and survive health
  checks with real providers.
- Actual evidence: README explicitly says production live proof is not claimed
  and waits on real Stripe, ingress, inference provider, Telegram, Discord, and
  production host credentials (`README.md:26-31`). The live proof doc says no
  credentialed live E2E journey has been proven
  (`docs/arclink/live-e2e-secrets-needed.md:3-22`).
- Missing proof/tests: `bin/arclink-live-proof --live --json` and the workspace
  live run from the production runbook (`docs/arclink/control-node-production-runbook.md:254-260`).
- Impact: ArcLink can be described as locally `real` and tested, but not
  production-proven.
- Owner/surface: release/ops, Control Node, live proof.
- Next repair: run the Production 12 proof with authorized scratch/prod
  credentials, capture the evidence ledger, and demote any failing row into its
  own repair issue.

### GAP-002 - Live Stripe checkout, portal, webhook, and refuel are not proven

- Severity: P1
- Status: proof-gated
- Journey joints: `J-06`, `J-07`
- Proof gates: `PG-STRIPE`
- Joint: billing and entitlement
- Expected: real Stripe checkout/session/webhook/portal/refuel flows move
  accounts and deployments exactly as fake/local tests prove.
- Actual evidence: local webhook processing is substantial
  (`python/arclink_entitlements.py:508-790`) and tests cover failed payment,
  refuel, and cancellation (`tests/test_arclink_entitlements.py:163-186`,
  `tests/test_arclink_entitlements.py:766-828`,
  `tests/test_arclink_entitlements.py:1077-1106`). Live proof still needs
  Stripe credentials (`docs/arclink/live-e2e-secrets-needed.md:56-60`,
  `docs/arclink/live-e2e-secrets-needed.md:99-104`).
- Missing proof/tests: authorized Stripe test-mode checkout, signed webhook,
  portal link, failed renewal, subscription delete, and refuel payment proof.
- Impact: payment is a core gate; without live proof, a production Captain could
  pay without reliable provisioning or dashboard state.
- Owner/surface: billing, hosted API, entitlements.
- Next repair: run the Stripe external proof row and record event ids, local
  entitlement rows, and webhook replay behavior without storing secrets.

### GAP-003 - Live Telegram/Discord Raven delivery is not proven

- Severity: P1
- Status: proof-gated
- Journey joints: `J-03`, `J-04`, `J-18`, `J-24`
- Proof gates: `PG-BOTS`
- Joint: Raven first contact, buttons, selected-agent bridge, handoff pings
- Expected: real Telegram and Discord public bots register commands/webhooks,
  verify signatures/secrets, deliver buttons, queue selected-agent turns, and
  return replies to the linked public channel.
- Actual evidence: hosted API routes dispatch Telegram and Discord webhooks
  (`python/arclink_hosted_api.py:2971-2974`); Telegram must include secret-token
  and callback updates (`docs/arclink/sovereign-control-node.md:58-63`);
  selected-agent turns are queued locally (`python/arclink_public_bots.py:3374-3455`).
  Live proof requires public bot credentials (`docs/arclink/live-e2e-secrets-needed.md:105-112`).
- Missing proof/tests: real Telegram button callback, Discord interaction
  signature, command refresh, selected-agent bridge reply, and handoff ping.
- Impact: the public product is chat-first; failed delivery strands users after
  checkout or hides Raven controls.
- Owner/surface: public bots, notification delivery, hosted API.
- Next repair: run live Telegram and Discord proof rows separately so a failure
  in one platform does not block the other from being classified.

### GAP-004 - Live executor, fleet, Cloudflare, and Tailscale apply are not proven

- Severity: P1
- Status: proof-gated
- Journey joints: `J-09`, `J-10`, `J-11`, `J-17`
- Proof gates: `PG-PROVISION`, `PG-FLEET`, `PG-INGRESS`
- Joint: paid provisioning onto real workers with real ingress
- Expected: after payment, the worker applies Compose, publishes DNS/Tailscale
  ingress, verifies health, and records durable handoff.
- Actual evidence: local source supports placement and execution
  (`python/arclink_sovereign_worker.py:656-775`,
  `python/arclink_executor.py:70-130`, `python/arclink_executor.py:600-723`).
  The live E2E doc says real host execution, ingress publication, and secret
  resolver are still needed (`docs/arclink/live-e2e-secrets-needed.md:172-186`).
  The Control Node boundary says live proof is gated by credentials, fleet
  capacity, SSH reachability, ingress, Notion, and service health
  (`docs/arclink/sovereign-control-node.md:236-246`).
- Missing proof/tests: local or SSH executor apply against a real host,
  Cloudflare DNS apply/teardown, Tailscale Serve/Funnel publication, service
  health, rollback, and teardown.
- Impact: provisioning is the core promise; without live apply proof, a paid
  Captain may never get a reachable ArcPod.
- Owner/surface: Sovereign worker, executor, fleet, ingress.
- Next repair: run one domain-mode and one Tailscale-mode proof, with small
  scratch deployments and teardown evidence.

### GAP-005 - Hermes/Drive/Code/Terminal live browser proof is missing

- Severity: P1
- Status: proof-gated
- Journey joints: `J-13`, `J-18`, `J-19`, `J-27`
- Proof gates: `PG-HERMES`
- Joint: user dashboard to real Hermes dashboard and native workspace plugins
- Expected: dashboard links open a real HTTPS Hermes dashboard where Drive,
  Code, and Terminal render and behave on desktop/mobile.
- Actual evidence: dashboard renders service links
  (`web/src/app/dashboard/page.tsx:364-373`,
  `web/src/app/dashboard/page.tsx:967-1005`) and plugin tests verify sanitized
  local status and root guards (`tests/test_arclink_plugins.py:470-555`).
  The live proof doc requires `ARCLINK_WORKSPACE_PROOF_TLS_URL` and auth
  (`docs/arclink/live-e2e-secrets-needed.md:49-52`).
- Missing proof/tests: Playwright/browser proof against a real HTTPS Hermes
  dashboard with Drive, Code, Terminal, and auth material supplied out of band.
- Impact: the product promise moves from chat into workspace; a broken dashboard
  makes the deployment feel unusable.
- Owner/surface: web, Hermes dashboard proxy, workspace plugins.
- Next repair: run `bin/arclink-live-proof --journey workspace --live --json`
  and attach desktop/mobile evidence.

### GAP-006 - Provider live behavior and self-service policy remain unresolved

- Severity: P1
- Status: proof-gated, policy-question
- Journey joints: `J-07`, `J-08`
- Proof gates: `PG-PROVIDER`
- Joint: provider connection, inference budget, OAuth/account lifecycle, router
- Expected: Captains have a clear provider path, ArcPods infer through the
  router, and budget/refuel behavior works against the real inference provider.
- Actual evidence: the router contract exists and avoids raw prompts/completions
  (`docs/arclink/llm-router.md:1-10`, `docs/arclink/llm-router.md:47-68`);
  ArcPods default to router mode, with Chutes as the current inference provider
  adapter family in source (`docs/arclink/llm-router.md:147-162`).
  Live provider proof is explicitly gated (`docs/arclink/llm-router.md:227-245`).
  The provider-state API marks live key creation proof-gated and self-service
  provider add as a policy question (`python/arclink_api_auth.py:3355-3380`).
- Missing proof/tests: authorized provider OAuth, key CRUD, usage/balance reads,
  router live completion with budget cap, account registration/funding only if
  operator-authorized.
- Impact: Agents may deploy but fail inference, or users may expect BYOK/self
  service that the dashboard correctly refuses.
- Owner/surface: provider policy, LLM router, provider adapters, billing.
- Next repair: decide provider self-service policy, then run bounded provider live
  proof rows. Do not claim silent account creation.

### GAP-007 - Notion setup is a preparation lane, not completed setup

- Severity: P1
- Status: proof-gated
- Journey joints: `J-22`
- Proof gates: `PG-NOTION`
- Joint: Raven `/connect_notion`, SSOT verification, shared Notion workspace
- Expected: after secure credential handoff, the user can connect Notion and see
  verified shared-root SSOT status.
- Actual evidence: Raven blocks Notion setup until credential handoff closes
  (`python/arclink_public_bots.py:3291-3358`) and then records setup intent and a
  callback. The command explicitly does not verify the integration, install
  secrets, support user-owned OAuth, or bypass verification
  (`python/arclink_public_bots.py:3759-3835`). The dashboard now reports the best
  no-secret state as `local_metadata_verified` and keeps shared-root read,
  brokered write preflight, user-owned OAuth, and live workspace proof gated
  (`python/arclink_dashboard.py:503-586`,
  `web/src/app/dashboard/page.tsx:1541-1589`). Notion proof code marks live
  mutation and user-owned OAuth as proof-gated
  (`python/arclink_notion_ssot.py:1120-1205`).
- Missing proof/tests: authorized live shared-root readability, brokered write
  preflight, webhook verification, and redacted evidence for `PG-NOTION`.
- Impact: local dashboard/API state no longer says bare `verified` while live
  proof is gated, but production Notion setup still cannot be called complete
  until the live proof passes.
- Owner/surface: Notion SSOT, public bot, dashboard.
- Next repair: run `PG-NOTION` with authorized Notion credentials and record
  shared-root read, brokered write preflight, webhook, and dashboard evidence
  without storing secrets.

### GAP-009 - Browser proof tokens use session-only storage

- Severity: P2
- Status: real
- Journey joints: `J-02`, `J-28`
- Joint: web onboarding resume and checkout success/cancel proof
- Expected: claim/cancel proof tokens should be recoverable enough for checkout
  resume without creating unnecessary persistent browser exposure.
- Actual evidence: web onboarding now keeps the durable
  `arclink_onboarding_resume` snapshot to non-proof form/session context and
  stores `claimToken`/`cancelToken` only in `sessionStorage`
  (`web/src/app/onboarding/page.tsx:12-30`,
  `web/src/app/onboarding/page.tsx:90-148`). Checkout success reads claim proof
  from `sessionStorage` and clears both proof and resume state after a
  successful browser claim (`web/src/app/checkout/success/page.tsx:73-99`).
  Checkout cancel reads cancel proof from `sessionStorage`, clears proof
  material after the cancel attempt, and rewrites the local resume snapshot
  without stale proof/session/checkout material after a successful cancellation
  (`web/src/app/checkout/cancel/page.tsx:51-80`,
  `web/src/app/checkout/cancel/page.tsx:125-145`).
- Missing proof/tests: no remaining local proof-token persistence test gap.
  HttpOnly/server-bound proof handoff or stronger cross-tab recovery remains a
  possible future hardening design, not the local `localStorage` bug.
- Impact: locally closed; proof tokens no longer persist in long-lived
  `localStorage`, and fake browser tests cover token placement plus success and
  cancel cleanup.
- Owner/surface: web onboarding, hosted auth.
- Next repair: keep the web smoke and browser storage tests in the regression
  path. Reopen only if product/security requires HttpOnly server-bound proof
  storage or a different multi-tab recovery policy.

### GAP-010 - Web preferred-channel copy is aligned with web-only identity

- Severity: P2
- Status: real
- Journey joints: `J-01`, `J-02`, `J-03`
- Joint: website entry from `?channel=telegram` or `?channel=discord`
- Expected: if the page says Raven will continue in Telegram/Discord, the
  session should be linked to that real channel identity or the copy should say
  web-only.
- Actual evidence: onboarding still reads `?channel=telegram|discord` as a
  preference (`web/src/app/onboarding/page.tsx:83-94`) and still starts web
  onboarding with `channel: "web"` plus a generated web contact id
  (`web/src/app/onboarding/page.tsx:163-177`). The copy now says the web flow
  shows the next setup handoff after checkout and, for Telegram/Discord query
  params, explicitly says the browser session is not linked to that platform
  yet (`web/src/app/onboarding/page.tsx:293-335`).
- Missing proof/tests: no local web-copy mismatch remains. Live public bot
  delivery and channel-link proof remain separate `PG-BOTS` work.
- Impact: locally closed; website entry no longer implies Telegram/Discord
  continuation without a real platform identity.
- Owner/surface: web onboarding, public bot linking.
- Next repair: keep the web smoke and browser onboarding checks in the
  regression path; if product later requires a pre-checkout platform handoff,
  implement it as a new linked-channel feature instead of changing copy alone.

### GAP-011 - Foundation docs align with current Control Node status

- Severity: P1
- Status: real
- Journey joints: `J-15`, `J-17`
- Joint: operator understanding of live adapters and product surface
- Expected: root and operations docs agree on what Control Node currently ships
  and what remains proof-gated.
- Actual evidence: `docs/arclink/foundation.md` and
  `docs/arclink/foundation-runbook.md` now say the local WSGI surface is a
  contract smoke tool, while the current Control Node boundary is Dockerized
  `control-web`, `control-api`, `control-provisioner`,
  `control-action-worker`, and `control-llm-router` with live mutation gated by
  explicit adapters, credentials, and proof windows. The docs also identify
  live Telegram/Discord client/webhook entrypoints without claiming live bot
  proof. `tests/test_documentation_truths.py` rejects the stale prototype
  phrases that caused this gap.
- Missing proof/tests: none for the local documentation truth repair. Live
  proof gates such as `PG-PROD`, `PG-BOTS`, `PG-PROVISION`, `PG-PROVIDER`, and
  `PG-UPGRADE`/`GAP-026` remain open.
- Impact: an operator or future agent may call the wrong deploy path or
  understate/overstate current capability if the truth guard regresses.
- Owner/surface: docs, operations.
- Next repair: keep the documentation truth guard in place; no local repair is
  currently open for this row.

### GAP-012 - Product matrix rows are locally guarded

- Severity: P2
- Status: real
- Journey joints: `J-27`
- Joint: source-of-truth claims for product readiness
- Expected: a matrix row marked `real` should have enough local source and test
  evidence, and proof-gated rows should not be hidden by aggregate optimism.
- Actual evidence: `tests/test_documentation_truths.py` now parses
  `research/PRODUCT_REALITY_MATRIX.md`, verifies declared status totals against
  the 121 parsed rows, rejects unknown status labels, requires rows marked
  `real` to carry source-owned evidence plus local test/proof/policy anchors,
  and requires `proof-gated` or `policy-question` rows to preserve live proof
  or operator/product decision language. The currently parsed matrix totals are
  101 `real`, 0 `partial`, 0 `gap`, 15 `proof-gated`, and 5
  `policy-question`.
- Missing proof/tests: no local doc-truth gap remains for the matrix guard.
  Live proof rows in the matrix remain governed by their `PG-*` gates.
- Impact: future work can no longer silently drift the matrix totals or mark a
  bare narrative row as `real`; the matrix is still not production launch
  certification.
- Owner/surface: research docs, release process.
- Next repair: keep the product-matrix truth tests in the documentation
  regression path and update matrix totals/statuses whenever rows change.

### GAP-013 - Raven backup prep stops before key setup and verification

- Severity: P2
- Status: partial, ux-gap, ops-gap
- Journey joints: `J-03`, `J-13`, `J-26`
- Proof gates: `PG-BACKUP`
- Joint: public `/config_backup` lane
- Expected: user chooses a private repo, ArcLink creates/verifies a per-pod
  deploy key, activates backup, and reports status.
- Actual evidence: public bot backup prep records the intended private repo and
  explicitly says it does not mint, install, or verify the deploy key
  (`python/arclink_public_bots.py:3838-3912`). The user dashboard now projects
  that same `repo_recorded_pending_key_setup` metadata as `pending_key_setup`,
  exposes the GitHub deploy-key settings URL, and can stage a per-deployment
  backup deploy key through an authenticated CSRF-gated API route while
  returning only the public key/status. The web dashboard now exposes those
  staged key/write-check routes through `web/src/lib/api.ts`, shows the staged
  public key and GitHub deploy-key settings URL, and labels write check,
  activation, and restore proof states without asking for private key material
  in chat. The dashboard, hosted API, and action worker now also expose a
  fail-closed GitHub write-check boundary: unattended local checks record
  `github_write_check: failed_closed`, preserve `backup_activation:
  not_active`, and require authorized `PG-BACKUP` proof before any activation
  claim (`python/arclink_dashboard.py`, `python/arclink_api_auth.py`,
  `python/arclink_hosted_api.py`, `python/arclink_action_worker.py`,
  `web/src/app/dashboard/page.tsx`, `web/src/lib/api.ts`).
  Focused tests tie the Raven workflow, hosted user dashboard route, hosted
  backup deploy-key request route, backup write-check route, action-worker
  fail-closed boundary, dashboard read model, and dashboard UI smoke together
  (`tests/test_arclink_public_bots.py`,
  `tests/test_arclink_dashboard.py`,
  `tests/test_arclink_action_worker.py`,
  `tests/test_arclink_hosted_api.py`, `web/tests/test_page_smoke.mjs`,
  `web/tests/test_api_client.mjs`).
  First-day docs say private Hermes-home backup may be offered, public repos
  are refused, and deploy keys must not be pasted in chat
  (`docs/arclink/first-day-user-guide.md:72-79`).
- Missing proof/tests: live GitHub write verification proof, backup activation
  proof, restore proof, and the operator/product decision for fully
  self-service deploy-key installation versus operator-assisted setup.
- Impact: a user can start backup setup in chat and now see the same pending
  key-verification state in the dashboard/API, including the staged public key
  when requested, but backup still cannot be called active or recoverable until
  the proof-gated steps pass.
- Owner/surface: backup, public bot, dashboard.
- Next repair: run authorized `PG-BACKUP` GitHub write, activation, and restore
  proof before claiming backup active or recoverable. `GAP-020` now provides
  local restore-smoke artifact coverage, but it does not close live disaster
  recovery proof.

### GAP-014 - Browser share requests need a live broker/adapter proof

- Severity: P2
- Status: partial, policy-question
- Journey joints: `J-19`, `J-20`
- Joint: Drive/Code share creation from user workspace
- Expected: users can create a share link or share request from the browser
  where they find the file.
- Actual evidence: backend share grants, Raven approvals, and Linked roots are
  present. Drive and Code now expose a local brokered `Request Share` contract:
  status advertises `share_request` disabled by default, writable
  Vault/Workspace roots can enable it only through an explicit broker URL,
  broker-token file, and owner deployment identity, the `/share/request` route
  rejects missing recipients, `linked` roots, sensitive paths, and URL-only
  broker configuration before broker dispatch, authenticated dispatch uses the
  `X-ArcLink-Share-Request-Broker-Token` header without returning token
  material in status or responses, and the browser bundles still omit direct
  "Generate share link" / "Create share link" wording. The hosted
  `/api/v1/user/share-grants/broker` route now accepts Drive/Code broker
  payloads without a browser session only when the token matches the supplied
  owner deployment's stored hash, derives the owner user from that deployment,
  resolves recipients by user id/email/deployment, records
  `requested_via=share_request_broker` plus `source_plugin`, and leaves the
  CSRF browser route unchanged. Control-node provisioning mounts the broker
  token as an ArcPod runtime secret and the sovereign worker stores only its
  hash in deployment metadata
  (`plugins/hermes-agent/drive/dashboard/plugin_api.py`,
  `plugins/hermes-agent/code/dashboard/plugin_api.py`,
  `python/arclink_api_auth.py`, `python/arclink_hosted_api.py`,
  `python/arclink_provisioning.py`, `python/arclink_sovereign_worker.py`,
  `tests/test_arclink_plugins.py`, `tests/test_arclink_hosted_api.py`,
  `tests/test_arclink_provisioning.py`,
  `tests/test_arclink_sovereign_worker.py`).
- Missing proof/tests: production workspace/browser proof, live recipient
  notification and bot callback delivery, audit/revoke proof from the live
  browser path, and the operator decision between the native ArcLink broker and
  an approved Nextcloud-backed adapter.
- Impact: sharing exists through API/MCP/Raven but not through the expected file
  browser affordance unless the local broker contract is explicitly configured;
  no direct public share-link generation is claimed.
- Owner/surface: Drive/Code UI, share broker, Nextcloud adapter policy.
- Next repair: run authorized production workspace and `PG-BOTS` proof for
  `Request Share`, including owner approval, recipient acceptance, no-reshare,
  audit, revoke, dashboard recovery, and Telegram/Discord delivery before
  claiming the browser share journey complete. Record any operator decision if
  a Nextcloud-backed adapter replaces or supplements the native broker.

### GAP-015 - Share approval can silently wait if the owner has no linked public channel

- Severity: P2
- Status: proof-gated
- Journey joints: `J-13`, `J-20`, `J-24`
- Proof gates: `PG-BOTS`
- Joint: cross-user share request notification
- Expected: if a share requires owner approval, the owner reliably sees the
  approval request or the requester gets a clear next step.
- Actual evidence: operations docs say share creation persists the grant as
  `pending_owner_approval`, and local code now exposes `GET /user/share-grants`
  plus a Captain dashboard share inbox for owner approval, recipient waiting,
  and recipient acceptance states. The inbox includes no-channel recovery hints
  instead of depending only on a one-time create response
  (`python/arclink_api_auth.py`, `python/arclink_hosted_api.py`,
  `web/src/app/dashboard/page.tsx`, `docs/arclink/operations-runbook.md`). The
  local `POST /user/share-grants/retry-notification` path now lets an
  authenticated grant participant retry the currently waiting Raven prompt,
  rejects cross-user and caller-supplied channel targets, returns
  `queued=false` plus dashboard/link-channel recovery when no public channel is
  linked, and queues exactly one local `notification_outbox` row after the
  waiting target links Telegram or Discord
  (`tests/test_arclink_hosted_api.py`,
  `web/tests/test_api_client.mjs`, `web/tests/test_page_smoke.mjs`).
- Missing proof/tests: authorized live Telegram/Discord delivery and button
  callback proof after local queueing.
- Impact: local dashboard/API users can see, act on, and retry queueing stalled
  share prompts, but production chat delivery remains proof-gated.
- Owner/surface: sharing UX, dashboard, public bot.
- Next repair: run authorized `PG-BOTS` proof for Telegram and Discord share
  prompt delivery, callbacks, and retry-after-channel-link behavior.

### GAP-016 - Linked copy/duplicate policy is aligned across MCP, docs, and tests

- Severity: P2
- Status: real
- Journey joints: `J-20`
- Joint: recipient copying an accepted Linked resource into owned space
- Expected: the policy is one clear product rule.
- Actual evidence: docs say Drive/Code allow copy/duplicate from Linked into the
  recipient's own Vault/Workspace (`docs/arclink/operations-runbook.md:150-165`);
  tests prove copy/duplicate works (`tests/test_arclink_plugins.py:640-686`).
  `shares.request` now returns
  `copy_duplicate_policy: accepted_linked_resources_copy_to_owned_vault_or_workspace_only`
  and destination roots `vault`/`workspace`
  (`python/arclink_mcp_server.py:1031-1042`), and managed-context guidance says
  the same rule instead of calling it a policy question
  (`plugins/hermes-agent/arclink-managed-context/__init__.py:326-330`).
  Regression tests assert the MCP description, response, and recipe wording
  (`tests/test_arclink_mcp_schemas.py:223-228`,
  `tests/test_arclink_mcp_schemas.py:356-366`,
  `tests/test_arclink_plugins.py:3048-3063`).
- Missing proof/tests: no remaining local policy proof gap for this row; live
  bot delivery and browser broker/adapter proof remain separate `PG-BOTS`,
  `GAP-014`, and `GAP-015` work.
- Impact: closed locally; agents now describe the same product rule that
  Drive/Code and the operations runbook already enforce.
- Owner/surface: MCP share tool, managed-context guidance, Drive/Code plugin
  policy.
- Next repair: keep the MCP/plugin focused tests in the regression path and
  reopen this row only if the policy string, guidance, docs, or plugin behavior
  diverge again.

### GAP-017 - Captain-initiated Pod migration is disabled by policy

- Severity: P2
- Status: policy-question
- Journey joints: `J-10`, `J-14`, `J-17`
- Joint: Captain self-service migration/reprovision
- Expected: if migration is a product feature, the Captain knows whether they
  can request it from dashboard or must ask an operator.
- Actual evidence: operations runbook says `ARCLINK_CAPTAIN_MIGRATION_ENABLED=0`
  remains default and there is no Captain-facing migration route
  (`docs/arclink/operations-runbook.md:104-107`). Production runbook says Wave 3
  Pod migration is operator-only and not to expose a dashboard button until
  policy and live proof complete
  (`docs/arclink/control-node-production-runbook.md:96-131`).
- Missing proof/tests: product decision, dashboard copy, and live migration
  proof for host move/redeploy.
- Impact: migration can exist operationally while users have no self-service
  mental model.
- Owner/surface: admin actions, dashboard, migration policy.
- Next repair: keep it operator-only with explicit dashboard copy, or define the
  Captain request/approval path.

### GAP-018 - Admin action live side effects are modeled but not proven

- Severity: P1
- Status: proof-gated, ops-gap
- Journey joints: `J-09`, `J-11`, `J-14`, `J-17`
- Proof gates: `PG-PROVISION`, `PG-INGRESS`, `PG-STRIPE`, `PG-PROVIDER`
- Joint: restart, DNS repair, key rotation, refund/cancel/comp, rollout,
  reprovision, rollback
- Expected: admin actions mutate real services/providers only when the worker and
  executor are live and record evidence.
- Actual evidence: readiness probes fail closed when executor/worker are not
  ready, queuing rejects unsupported or pending action types, and the admin read
  model publishes a source-owned support matrix for restart, reprovision, DNS
  repair, Chutes key rotation, refund, cancel, and comp with operation kind,
  local contract, required adapter, proof gate, and fail-closed reason
  (`python/arclink_dashboard.py`, `tests/test_arclink_admin_actions.py`).
  The Next.js admin page and lightweight product surface render that matrix, and
  runbooks keep fake/local readiness separate from live mutation proof
  (`web/src/app/admin/page.tsx`, `python/arclink_product_surface.py`,
  `docs/arclink/control-node-production-runbook.md`,
  `docs/arclink/operations-runbook.md`). Production docs say an action only
  proves live mutation when the recorded executor result is live and succeeded.
- Missing proof/tests: live action-worker run for each supported action class,
  plus negative tests for wrong idempotency reuse against live adapters.
- Impact: operators may see an action in UI and assume it has production effect
  when only local queueing is proven; the local matrix now reduces this risk but
  does not close the live proof gates.
- Owner/surface: admin dashboard, action worker, executor.
- Next repair: run authorized live proof rows for the smallest safe subset of
  action classes and keep adding fake/local regression tests when new actions
  move from pending to worker-backed.

### GAP-019 - Docker socket/root services are a P0 trusted-host boundary

- Severity: P0
- Status: security-risk, ops-gap
- Journey joints: `J-16`, `J-17`, `J-28`
- Joint: Control Node and Docker shared-host authority boundary
- Expected: services with Docker socket/root access are explicitly hardened and
  monitored because compromise means host/container control.
- Actual evidence: Compose mounts the host Docker socket into
  `deployment-exec-broker`, `agent-supervisor-broker`,
  `operator-upgrade-broker`, and `gateway-exec-broker`;
  `migration-capture-helper`, `agent-user-helper`, and
  `agent-process-helper` run as root
  (`compose.yaml`, `config/docker-authority-inventory.json`). Non-root socket services now
  drop all Linux capabilities in Compose, and Docker regression tests assert the
  socket mount allowlist, supplemental socket group, capability drop, explicit
  root boundary, source-owned authority inventory drift guard, `GAP-019-B2`
  broker/proxy review schema, and Docker docs coverage
  (`tests/test_arclink_docker.py`,
  `config/docker-authority-inventory.json`). Action-worker restart lifecycle
  metadata path overrides now fail closed unless
  `ARCLINK_ACTION_WORKER_ALLOW_LIFECYCLE_PATH_OVERRIDES=1` is set for an
  operator emergency window (`python/arclink_action_worker.py`,
  `tests/test_arclink_action_worker.py`). The `GAP-019-C`
  notification-delivery guard now validates detached public-Agent bridge
  commands against the generated `hermes-gateway` exec allowlist, confines
  Compose fallback files under `ARCLINK_STATE_ROOT_BASE`, rejects tampered job
  commands before subprocess execution, and records rejected-command incidents
  (`python/arclink_notification_delivery.py`,
  `tests/test_arclink_notification_delivery.py`). The `GAP-019-D` repair removes
  the writeable Docker socket mount and socket group from `curator-refresh`;
  source evidence routes queued Docker-mode operator upgrade execution through
  the enrollment provisioner path instead (`compose.yaml`,
  `python/arclink_enrollment_provisioner.py`, `tests/test_arclink_docker.py`).
  The `GAP-019-E` repair adds executor preflight on the
  `control-provisioner` local/SSH Docker path: malformed deployment IDs,
  non-matching apply project names, and env/compose paths outside the
  configured `ARCLINK_STATE_ROOT_BASE` deployment config root fail before
  `DockerRunner.run` (`python/arclink_executor.py`,
  `tests/test_arclink_executor.py`). The authority inventory records this
  local guard for `control-provisioner` while keeping the direct socket risk
  open (`config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-F` repair removes the Docker socket mount and socket group from
  `notification-delivery` and adds a dedicated `gateway-exec-broker` service.
  Notification delivery now sends a bounded deployment id, prefix, generated
  project name, bridge payload, and timeout request to the broker; the broker
  rejects raw commands, reconstructs the `hermes-gateway` Docker exec command
  locally, and validates it before subprocess execution
  (`python/arclink_notification_delivery.py`,
  `python/arclink_gateway_exec_broker.py`,
  `tests/test_arclink_notification_delivery.py`).
  The `GAP-019-G` repair removes the Docker socket mount and socket group from
  `control-provisioner` and adds a dedicated `deployment-exec-broker` service.
  The local executor now sends deployment id, generated project name, operation
  kind, env file, and compose file requests to the broker; the broker rejects
  raw commands, validates paths under `ARCLINK_STATE_ROOT_BASE`, and
  reconstructs allowlisted Compose `up`, `ps`, and `down` operations itself
  (`python/arclink_executor.py`, `python/arclink_deployment_exec_broker.py`,
  `tests/test_arclink_executor.py`, `tests/test_arclink_docker.py`).
  The `GAP-019-AA` repair narrows the `deployment-exec-broker` Compose service
  environment so it no longer inherits broad `*arclink-env` app, billing, bot,
  provider, ingress, fleet, session, or memory-synthesis values; the broker
  keeps only token/listener settings, `ARCLINK_STATE_ROOT_BASE`, optional
  Docker binary, the deployment state-root bind, and the writeable Docker
  socket needed for allowlisted deployment Compose operations
  (`compose.yaml`, `config/docker-authority-inventory.json`,
  `tests/test_arclink_docker.py`).
  The `GAP-019-AB` repair narrows the `operator-upgrade-broker` Compose and
  subprocess boundary: the broker no longer inherits broad `*arclink-env`, no
  longer mounts broad canonical private config/state or
  `arclink-priv/secrets/container`, maps canonical operator log paths to the
  host private bind, and builds allowlisted upgrade subprocess env from basic
  runtime keys, Docker-mode path metadata, optional Docker binary metadata, and
  request-supplied `ARCLINK_UPSTREAM_*` values instead of `os.environ.copy()`
  (`compose.yaml`, `python/arclink_operator_upgrade_broker.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-H` repair removes the Docker socket mount and socket group from
  the root `control-action-worker`. Docker-mode local action executors now fail
  closed without `ARCLINK_DEPLOYMENT_EXEC_BROKER_URL` and token, so queued
  restart and reprovision Docker lifecycle/apply calls route through
  `deployment-exec-broker` (`compose.yaml`, `python/arclink_executor.py`,
  `tests/test_arclink_action_worker.py`, `tests/test_arclink_docker.py`).
  The `GAP-019-I` repair removes the Docker
  socket mount and socket group from the root `agent-supervisor` and adds a
  dedicated `agent-supervisor-broker`. The supervisor now sends bounded
  dashboard network/proxy sidecar requests to the broker; the broker rejects
  raw commands, validates safe agent ids, deterministic network/container
  names, backend IPs, ports, and access-file confinement under
  `ARCLINK_DOCKER_CONTAINER_PRIV_DIR`, then reconstructs the allowed Docker
  network/proxy operations itself (`python/arclink_docker_agent_supervisor.py`,
  `python/arclink_agent_supervisor_broker.py`, `compose.yaml`,
  `tests/test_arclink_docker.py`).
  The `GAP-019-J` repair routes queued Docker-mode operator upgrades and
  pinned-component upgrade apply/final-upgrade calls through
  `operator-upgrade-broker` instead of raw subprocess execution in the root
  supervisor path. The enrollment provisioner now fails closed without broker
  URL/token, sends bounded `run_operator_upgrade` or `run_pin_upgrade`
  requests, and the broker rejects raw commands, validates the host repo/private
  paths from Docker config, confines logs under private `state/operator-actions`,
  and reconstructs only `deploy.sh docker upgrade` or allowlisted
  `component-upgrade.sh ... --skip-upgrade` commands
  (`python/arclink_enrollment_provisioner.py`,
  `python/arclink_operator_upgrade_broker.py`, `compose.yaml`,
  `tests/test_arclink_enrollment_provisioner_regressions.py`,
  `tests/test_arclink_docker.py`).
  The `GAP-019-K` repair keeps the root Pod migration capture path fail-closed
  by default: non-dry-run capture requires
  `ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE=1`, capture paths must
  stay deployment-scoped before root file copying starts, and dry-run planning
  remains available without the root-capture window
  (`python/arclink_pod_migration.py`, `python/arclink_action_worker.py`,
  `compose.yaml`, `tests/test_arclink_pod_migration.py`,
  `tests/test_arclink_action_worker.py`, `tests/test_arclink_docker.py`).
  The `GAP-019-L` repair guards the `agent-supervisor`
  delegation path: active-agent metadata now fails closed if `agent_id`,
  `unix_user`, `hermes_home`, the Docker agent home, workspace path,
  supervisor log/process key, or agent process env key is unsafe or outside
  the canonical Docker agent-home namespace before helper, broker, or
  process-helper request
  (`python/arclink_docker_agent_supervisor.py`,
  `tests/test_arclink_docker.py`).
  The `GAP-019-M` repair adds incident controls to the authority inventory for
  `deployment-exec-broker`, `gateway-exec-broker`,
  `agent-supervisor-broker`, `operator-upgrade-broker`, `migration-capture-helper`,
  `agent-user-helper`, and `agent-process-helper`.
  Each residual row now names monitored signals, status/log/audit locations,
  triage steps, fail-closed actions, and the `GAP-019` escalation boundary; the
  Docker/security runbooks render the same response path, and Docker tests fail
  if a writeable socket or explicit root row lacks those controls
  (`config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`,
  `docs/docker.md`, `docs/arclink/operations-runbook.md`,
  `docs/arclink/data-safety.md`).
  The `GAP-019-N` repair removes root from `control-action-worker` and adds
  `migration-capture-helper`. Docker-mode non-dry-run Pod migration capture
  still requires `ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE=1`, and it
  now also fails closed without `ARCLINK_MIGRATION_CAPTURE_HELPER_URL` and
  token. The helper rejects raw command fields, reconstructs only `capture` and
  `materialize`, validates deployment id, prefix, migration id, source state
  root, target state root, and `.migrations/<migration_id>` staging path, and
  then performs the root file copy (`python/arclink_pod_migration.py`,
  `python/arclink_migration_capture_helper.py`, `compose.yaml`,
  `tests/test_arclink_pod_migration.py`,
  `tests/test_arclink_action_worker.py`, `tests/test_arclink_docker.py`).
  The `GAP-019-AC` repair narrows the same helper's ambient boundary: the
  Compose service no longer inherits broad `*arclink-env`, keeps only
  `ARCLINK_STATE_ROOT_BASE` plus helper token/listener env, and helper
  validation rejects source, target, or capture paths outside the configured
  state-root base before `_copy_capture` or `_materialize_capture` can run
  (`compose.yaml`, `python/arclink_migration_capture_helper.py`,
  `config/docker-authority-inventory.json`,
  `tests/test_arclink_pod_migration.py`, `tests/test_arclink_docker.py`).
  The `GAP-019-O` repair removes direct Docker-mode user/home setup from
  `agent-supervisor` and adds `agent-user-helper`. Docker-mode user/home setup
  now fails closed without `ARCLINK_AGENT_USER_HELPER_URL` and token. The
  helper rejects raw command fields, reconstructs only `ensure_user_home`,
  validates agent id, Unix user, Docker agent-home root, agent home, Hermes
  home, and workspace path, and then performs container-local user creation,
  persistent numeric uid/gid assignment, and agent-home ownership repair
  (`python/arclink_docker_agent_supervisor.py`,
  `python/arclink_agent_user_helper.py`, `compose.yaml`,
  `tests/test_arclink_docker.py`). The `GAP-019-P` repair removes explicit
  root and setpriv process launching from `agent-supervisor` and adds
  `agent-process-helper`. Docker-mode install, identity refresh, user-agent
  refresh, cron, gateway, and dashboard process execution now fails closed
  without `ARCLINK_AGENT_PROCESS_HELPER_URL` and token. The helper rejects raw
  command fields, reconstructs only allowlisted typed operations, validates
  agent id, Unix user, Docker agent-home root, agent home, Hermes home,
  workspace path, uid/gid, env keys/canonical env values, and dashboard
  backend fields, and owns the gateway/dashboard process handles
  (`python/arclink_docker_agent_supervisor.py`,
  `python/arclink_agent_process_helper.py`, `compose.yaml`,
  `tests/test_arclink_docker.py`). The `GAP-019-Q` repair removes Docker's
  default Linux capability set from `agent-user-helper` and gives it only
  `CHOWN`, `DAC_OVERRIDE`, and `FOWNER` on top of `cap_drop: ALL`; tests now
  distinguish default capabilities, full drops, and explicit add-backs so the
  inventory cannot overclaim `all_dropped` when a helper has `cap_add`
  (`compose.yaml`, `config/docker-authority-inventory.json`,
  `tests/test_arclink_docker.py`). The `GAP-019-AE` repair removes ambient
  `PATH` lookup from the root account/ownership command path in
  `agent-user-helper`: it preflights `/usr/sbin/groupadd`,
  `/usr/sbin/useradd`, and `/usr/bin/chown` before uid/gid assignment writes,
  directory creation, account commands, or recursive ownership repair
  (`python/arclink_agent_user_helper.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-R` repair keeps validated
  agent process env values out of setpriv argv and
  `state/docker/agent-process-helper/*.log` startup command lines by passing
  env through subprocess `env=`, and strips supervisor broker/helper tokens
  from per-agent process specs before dispatch
  (`python/arclink_agent_process_helper.py`,
  `python/arclink_docker_agent_supervisor.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-S` repair confines request-scoped root paths inside the root
  helpers. `agent-user-helper` rejects configured
  `ARCLINK_DOCKER_AGENT_HOME_ROOT` mismatches before uid/gid assignment writes,
  directory creation, account commands, or recursive ownership repair.
  `agent-process-helper` rejects configured Docker agent-home, repo,
  private-state, state, and runtime root mismatches before helper log creation,
  `subprocess.run`, or `subprocess.Popen`
  (`python/arclink_agent_user_helper.py`,
  `python/arclink_agent_process_helper.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-AN` repair rejects root agent-helper symlink escapes: both
  helpers now keep the agent home, Hermes home, and workspace lexically
  canonical and compare their resolved targets with the expected canonical
  child target before uid/gid assignment writes, account commands, recursive
  chown, helper log creation, `subprocess.run`, or `subprocess.Popen`
  (`python/arclink_agent_user_helper.py`,
  `python/arclink_agent_process_helper.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-AO` repair closes the next process-helper log path escape:
  `agent-process-helper` now verifies that
  `state/docker/agent-process-helper` is the canonical non-symlink helper log
  directory, and that each helper log file resolves to its exact canonical
  child path, before opening logs, `subprocess.run`, or `subprocess.Popen`
  (`python/arclink_agent_process_helper.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-T` repair removes unnecessary write access to the live host repo
  from Docker non-broker services. `agent-process-helper`, `agent-supervisor`,
  and `curator-refresh` now mount the host repo read-only for script reads,
  refresh, detection, and typed process execution. The `GAP-019-U` repair moves
  the writable host repo exception and the `run_operator_upgrade`/
  `run_pin_upgrade` operations out of `agent-supervisor-broker` and into a
  dedicated `operator-upgrade-broker`
  (`compose.yaml`, `config/docker-authority-inventory.json`,
  `python/arclink_agent_supervisor_broker.py`,
  `python/arclink_operator_upgrade_broker.py`, `tests/test_arclink_docker.py`).
  The `GAP-019-V` repair removes the remaining read-only Docker socket
  discovery boundary from `control-ingress`. Traefik now uses the source-owned
  static file provider config at `config/traefik-control.yaml` for
  `/notion/webhook`, `/v1`, `/api`, and `/`, and no longer enables the Docker
  provider or mounts `/var/run/docker.sock`
  (`compose.yaml`, `config/traefik-control.yaml`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-W` repair makes the `agent-process-helper` reject ArcLink
  broker/helper/control token env keys, including future `ARCLINK_*_TOKEN`
  names, before log creation, `subprocess.run`, or `subprocess.Popen`; the
  supervisor denylist is aligned so normal dispatch strips the same token
  family before helper calls
  (`python/arclink_agent_process_helper.py`,
  `python/arclink_docker_agent_supervisor.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-AM` repair closes the next process-helper env injection slice:
  `agent-process-helper` now rejects dynamic-loader `LD_*`, Python
  path/startup, shell startup, Git/SSH command-steering, and secret-looking
  `*_TOKEN`, `*_SECRET`, `*_PASSWORD`, or `*_KEY` process env keys before log
  creation, `subprocess.run`, or `subprocess.Popen`; `agent-supervisor` strips
  known ArcLink helper tokens and fails closed on the same unapproved non-token
  key family before helper payload construction
  (`python/arclink_agent_process_helper.py`,
  `python/arclink_docker_agent_supervisor.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-AD` repair hardens the same root helper's pre-drop executable
  lookup boundary: request env `PATH` must match `SAFE_PATH`, `setpriv` is
  invoked as `/usr/bin/setpriv` for both `run_once` and `ensure_processes`, and
  identity setup fails closed before `subprocess.run` unless the pinned runtime
  venv Python exists under `RUNTIME_DIR`
  (`python/arclink_agent_process_helper.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-X` repair narrows the `agent-process-helper` Compose boundary:
  the root helper no longer inherits broad `*arclink-env`, no longer receives
  app/billing/bot/provider/memory-synthesis env keys at service startup, and no
  longer mounts the global `arclink-priv/secrets/container` directory. It keeps
  only explicit non-secret Docker mode/path validation env, token/listener keys,
  config/state/vault mounts, and the read-only host repo bind needed for
  allowlisted agent commands (`compose.yaml`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-Y` repair narrows the `gateway-exec-broker` Compose boundary:
  the public-Agent gateway exec broker no longer inherits broad
  `*arclink-env`, no longer receives unrelated app/billing/bot/provider/ingress
  env keys at service startup, and no longer mounts broad
  `arclink-priv/config`, `arclink-priv/state`, or
  `arclink-priv/secrets/container`. It keeps only
  `ARCLINK_STATE_ROOT_BASE`, broker token/listener env, the deployment
  state-root bind needed for rendered Compose fallback files, and the writeable
  Docker socket for allowlisted `hermes-gateway` exec (`compose.yaml`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-Z` repair narrows the `agent-supervisor-broker` Compose boundary:
  the dashboard sidecar broker no longer inherits broad `*arclink-env`, no longer
  receives unrelated app/billing/bot/provider/ingress env keys at service
  startup, and no longer mounts broad `arclink-priv/config`,
  `arclink-priv/state`, or `arclink-priv/secrets/container`. It keeps only
  Docker binary/image, repo path, host/container private path metadata, broker
  token/listener env, and the writeable Docker socket for allowlisted dashboard
  network/proxy sidecar operations (`compose.yaml`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-AF` repair hardens the same broker's Docker CLI executable
  lookup: `ARCLINK_DOCKER_BINARY` must be `docker` or a trusted absolute Docker
  CLI path, and unsafe, missing, non-executable, or non-Docker values fail
  closed before dashboard network/proxy subprocesses run
  (`python/arclink_agent_supervisor_broker.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-AZ` repair hardens that broker's dashboard sidecar private bind
  roots: unsafe `ARCLINK_DOCKER_HOST_PRIV_DIR` and
  `ARCLINK_DOCKER_CONTAINER_PRIV_DIR` values, including relative paths, `/`,
  colon-bearing Docker volume specs, newline/carriage-return/NUL-bearing
  strings, dot/dotdot path components, and non-canonical ArcLink private roots,
  fail closed before proxy config hashing, Docker CLI lookup, Docker container
  inspect, `docker run -v`, or a successful broker response
  (`python/arclink_agent_supervisor_broker.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-AG` repair hardens the same executable-lookup class for
  `deployment-exec-broker`: `ARCLINK_DOCKER_BINARY` must resolve to the trusted
  Docker CLI before deployment Compose subprocesses run
  (`python/arclink_deployment_exec_broker.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-AH` repair hardens the same executable-lookup class for
  `gateway-exec-broker`: `ARCLINK_DOCKER_BINARY` must resolve to a trusted
  Docker CLI before running-container discovery or public Agent gateway exec
  subprocesses run, and a PATH-injected fake `docker` fails closed without
  being invoked (`python/arclink_gateway_exec_broker.py`,
  `python/arclink_notification_delivery.py`,
  `config/docker-authority-inventory.json`,
  `tests/test_arclink_docker.py`,
  `tests/test_arclink_notification_delivery.py`).
  The `GAP-019-AY` repair hardens the same broker's Compose fallback file
  boundary: if a running `hermes-gateway` container is not found, fallback
  `config/arclink.env` and `config/compose.yaml` must be exact non-symlink
  regular readable files under the deployment state-root config directory
  before `docker compose exec` dispatch or a successful broker response
  (`python/arclink_gateway_exec_broker.py`,
  `python/arclink_notification_delivery.py`,
  `config/docker-authority-inventory.json`,
  `tests/test_arclink_notification_delivery.py`,
  `tests/test_arclink_docker.py`).
  The `GAP-019-AI` repair hardens the same executable-lookup class for
  `operator-upgrade-broker`: any preserved `ARCLINK_DOCKER_BINARY` must resolve
  to a trusted Docker CLI before queued Docker-mode operator upgrade or
  pin-upgrade child subprocesses run, and unsafe, missing, non-executable,
  relative, non-Docker, or PATH-injected fake `docker` values fail closed
  without being invoked (`python/arclink_operator_upgrade_broker.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-AJ` repair hardens `agent-process-helper` desired-process
  reconciliation: gateway/dashboard processes now store a hash of the validated
  setpriv command, Hermes-home cwd, and process env contract; a changed
  dashboard backend port or env signature stops the stale process group before
  replacement, identical specs do not churn, and shutdown escalates from
  SIGTERM to SIGKILL before failing closed
  (`python/arclink_agent_process_helper.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-AK` repair scopes the high-authority broker/helper request
  surface in Compose: `deployment-exec-broker`, `migration-capture-helper`,
  `agent-user-helper`, `agent-process-helper`, `agent-supervisor-broker`,
  `operator-upgrade-broker`, and `gateway-exec-broker` no longer join the
  default network. Each request lane uses an `internal: true` network with only
  the legitimate caller services, and the process helper/operator-upgrade
  broker keep separate single-service egress networks for outbound runtime or
  upgrade work (`compose.yaml`, `config/docker-authority-inventory.json`,
  `tests/test_arclink_docker.py`).
  The `GAP-019-AL` repair adds a fail-closed acknowledgement gate to the same
  seven services. `deployment-exec-broker`, `migration-capture-helper`,
  `agent-user-helper`, `agent-process-helper`, `agent-supervisor-broker`,
  `operator-upgrade-broker`, and `gateway-exec-broker` now receive
  `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED` through Compose, and their
  entrypoints plus direct request helpers reject missing, blank, false, or
  non-`accepted` values before HTTP listener bind, request validation, Docker
  subprocesses, root filesystem work, ownership changes, or agent process
  spawning. Docker config generation writes the variable blank by default so
  the operator must set the non-secret `accepted` value in private config after
  reviewing the residual-risk boundary
  (`python/arclink_boundary.py`, `compose.yaml`,
  `bin/docker-entrypoint.sh`, `bin/arclink-docker.sh`, `bin/deploy.sh`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  This gate does not close `GAP-001`, `PG-UPGRADE`, `PG-PROVISION`,
  `PG-BOTS`, `PG-HERMES`, or any credentialed live proof gate.
  The `GAP-019-AP` repair makes direct/local execution of those same seven
  broker/helper modules bind `127.0.0.1` by default. Compose still explicitly
  sets each service-specific `ARCLINK_*_HOST` value to `0.0.0.0` for internal
  request-network reachability, and healthchecks remain loopback-local
  (`python/arclink_deployment_exec_broker.py`,
  `python/arclink_migration_capture_helper.py`,
  `python/arclink_agent_user_helper.py`,
  `python/arclink_agent_process_helper.py`,
  `python/arclink_agent_supervisor_broker.py`,
  `python/arclink_operator_upgrade_broker.py`,
  `python/arclink_gateway_exec_broker.py`, `compose.yaml`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-AQ` repair narrows the `agent-supervisor` provisioner child
  environment: `run_provisioner` now builds an explicit allowlist instead of
  inheriting `os.environ.copy()`. The enrollment provisioner child keeps Docker
  mode/path config, runtime roots, service URLs, and helper/broker values
  needed for Docker enrollment and queued operator actions while excluding
  unrelated payment, provider, bot, ingress, memory-synthesis, session, fleet,
  Python path, and Git/SSH steering env keys
  (`python/arclink_docker_agent_supervisor.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-AR` repair confines Docker-mode dashboard backend host values
  before both root dashboard process launches and dashboard auth-proxy sidecar
  construction. `agent-process-helper` parses the dashboard backend host as an
  IP literal and rejects wildcard, globally routable, multicast, malformed, or
  non-IP values before helper log creation, desired-process signature work, or
  `subprocess.Popen`; `agent-supervisor-broker` enforces the same
  loopback-or-Docker-internal/private/link-local policy before Docker CLI
  lookup or sidecar subprocess construction
  (`python/arclink_agent_process_helper.py`,
  `python/arclink_agent_supervisor_broker.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-AS` repair closes the next root helper path escape by rejecting
  symlinked configured or requested Docker agent-home roots, including
  `ARCLINK_DOCKER_AGENT_HOME_ROOT`, before root helper filesystem work,
  helper log creation, `subprocess.run`, or `subprocess.Popen`
  (`python/arclink_agent_user_helper.py`,
  `python/arclink_agent_process_helper.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-BA` repair closes the next `agent-user-helper` assignment-file
  steering path by rejecting symlinked, directory, or non-regular
  `.arclink-user-ids.json` and `.arclink-user-ids.json.tmp` paths before
  uid/gid assignment reads or writes, account commands, agent-home directory
  creation, or recursive chown. Assignment writes now use a canonical
  preflighted temp file under the Docker agent-home root with exclusive
  no-follow creation before `os.replace`
  (`python/arclink_agent_user_helper.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-BB` repair adds redacted rejected-request incident evidence to
  `agent-process-helper`: rejected helper requests append one JSONL row under
  `state/docker/agent-process-helper/rejections.jsonl` only when the configured
  private root is safe. The row includes operation, safe agent id when present,
  trusted-host acknowledgement state, error class, and a sanitized reason, and
  excludes raw request bodies, env values, process args, private paths, tokens,
  and stack traces. Accepted `run_once`, `ensure_processes`, and
  `terminate_all` requests do not append rejection incidents
  (`python/arclink_agent_process_helper.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-BC` repair adds redacted rejected-request incident evidence to
  `gateway-exec-broker`: rejected public Agent broker requests append one
  JSONL row under
  `ARCLINK_STATE_ROOT_BASE/_broker-incidents/gateway-exec-broker/rejections.jsonl`
  only when the configured deployment state root is absolute, non-root,
  existing, and non-symlinked. The row includes safe deployment id and
  generated project name when available, trusted-host acknowledgement state,
  error class, and a sanitized reason, and excludes raw request bodies, bridge
  payload values, bot tokens, chat ids, user ids, message text, process args,
  rendered config paths, private paths, and stack traces. Accepted broker
  requests do not append rejection incidents
  (`python/arclink_gateway_exec_broker.py`,
  `config/docker-authority-inventory.json`,
  `tests/test_arclink_notification_delivery.py`).
  The `GAP-019-BD` repair extends redacted rejected-request incident evidence to
  `deployment-exec-broker`, `migration-capture-helper`, `agent-user-helper`,
  `agent-supervisor-broker`, and `operator-upgrade-broker`. Rejected raw-command
  or validation failures append one JSONL row only when the configured incident
  root is absolute, existing, non-root, and non-symlinked. The rows contain
  service/event, trusted-host acknowledgement state, error class, sanitized
  reason/message, and safe operation/deployment/migration/agent/item-count
  metadata when available; they exclude raw request bodies, `cmd`/`command`/
  `args` values, process args, payload values, private paths, tokens, chat ids,
  user ids, message text, secret-looking values, and stack traces. The dashboard
  broker receives only a narrow private-state incident mount for this purpose
  (`python/arclink_rejection_incidents.py`,
  `python/arclink_deployment_exec_broker.py`,
  `python/arclink_migration_capture_helper.py`,
  `python/arclink_agent_user_helper.py`,
  `python/arclink_agent_supervisor_broker.py`,
  `python/arclink_operator_upgrade_broker.py`, `compose.yaml`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-AT` repair closes the matching process-helper configured-root
  symlink escape by rejecting symlinked configured or requested repo,
  private-state, state, and runtime roots, including `ARCLINK_REPO_DIR`,
  `ARCLINK_PRIV_DIR`, `ARCLINK_DOCKER_CONTAINER_PRIV_DIR`, request
  `state_dir`, and `RUNTIME_DIR`, before helper log creation,
  `subprocess.run`, or `subprocess.Popen`
  (`python/arclink_agent_process_helper.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-AU` repair adds fixed repo command target preflight to the same
  helper: `bin/install-agent-user-services.sh`, `bin/hermes-shell.sh`,
  `bin/user-agent-refresh.sh`, and
  `python/arclink_headless_hermes_setup.py` must be canonical repo-child
  targets, regular readable files, and shell command targets must be
  executable before helper log creation, `subprocess.run`, or
  `subprocess.Popen`
  (`python/arclink_agent_process_helper.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-AV` repair adds matching fixed script target preflight to the
  operator-upgrade broker: `deploy.sh` and `bin/component-upgrade.sh` must be
  exact non-symlink repo-child targets, regular readable files, and executable
  before private operator log creation, `_run_logged_command`, or
  `subprocess.run`
  (`python/arclink_operator_upgrade_broker.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  The `GAP-019-AW` repair adds upstream deploy-key path confinement to the same
  broker: non-empty `ARCLINK_UPSTREAM_DEPLOY_KEY_PATH` and
  `ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE` values must be absolute non-symlink paths
  under `ARCLINK_DOCKER_HOST_PRIV_DIR` before child env construction, private
  operator log creation, `_run_logged_command`, or `subprocess.run`
  (`python/arclink_operator_upgrade_broker.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`).
  Data safety documents these as trusted-host services.
- Missing proof/tests: deeper least-privilege implementation for the root
  `agent-process-helper` process-runner boundary after service env/secret-mount
  narrowing, pre-drop executable lookup hardening, desired-process
  signature restart/bounded shutdown, dashboard backend host confinement,
  configured agent-home root symlink rejection, configured-root symlink
  rejection, fixed command target preflight, operator-upgrade fixed script
  target preflight, operator-upgrade upstream deploy-key path confinement, and
  rejected-request incident evidence, and the fail-closed trusted-host
  acknowledgement gate,
  stronger isolation or an
  accepted bounded opt-in policy for the root `migration-capture-helper`,
  stronger isolation or accepted residual risk for the root `agent-user-helper`,
  residual-risk decisions for the deployment, gateway, agent-supervisor, and
  operator-upgrade brokers including the gateway broker's writeable Docker
  socket and the operator-upgrade writable host repo exception, live/runtime
  alert integration beyond the
  source-owned status/audit/log controls, and an operator risk decision for the
  residual host-equivalent Docker socket/root boundary.
- Impact: a bug in public bot delivery or a remaining socket-bearing helper
  could become host compromise in local-adapter deployments; a bug in the root
  migration-capture helper can still compromise deployment/private state during
  an approved migration window, a bug in the root agent-user helper can still
  affect Docker agent homes, and a bug in the root agent-process helper can
  still affect allowlisted Docker agent command execution even though env
  values are no longer exposed through helper argv/startup logs and ArcLink
  control-token env keys fail closed at the helper boundary, rejected helper
  requests now leave a redacted local incident trail, the helper no
  longer receives broad Compose app env or the global container-secrets mount,
  request `PATH` can no longer steer root lookup for `setpriv`, and identity
  setup no longer falls back to bare `python3`; changed gateway/dashboard
  command, cwd, dashboard backend port, or validated env contracts no longer
  leave stale long-running process handles silently active,
  the agent-user helper no longer uses ambient `PATH` to find `groupadd`,
  `useradd`, or `chown`,
  the gateway broker no longer receives broad Compose app env or broad private
  config/state/secrets mounts and can no longer use a PATH-injected fake
  `docker`, `bash`, or another non-Docker executable for running-container
  discovery or public Agent gateway exec, and rejected raw-command,
  project-name mismatch, unsupported-platform, or trusted-host acknowledgement
  gateway broker requests now leave a redacted local incident trail under the
  configured deployment state root when that root is safe;
  remaining high-authority broker/helper raw-command rejections now leave
  equivalent redacted local incident trails under scoped state roots or the
  dashboard broker's narrow incident mount when those roots are safe;
  the dashboard sidecar broker no longer
  receives broad Compose app env or broad private config/state/secrets mounts
  and can no longer use `ARCLINK_DOCKER_BINARY` to dispatch dashboard Docker
  operations through `bash` or another non-Docker executable, and unsafe
  `ARCLINK_DOCKER_HOST_PRIV_DIR` or `ARCLINK_DOCKER_CONTAINER_PRIV_DIR` values
  can no longer steer the dashboard auth-proxy sidecar private-state `-v`
  mount before Docker lookup or dispatch,
  the deployment exec broker no longer receives broad Compose app env and can
  no longer use `ARCLINK_DOCKER_BINARY` to dispatch deployment Compose
  operations through `bash` or another non-Docker executable, and the
  operator upgrade broker no longer receives broad Compose app env, broad
  canonical private mounts, or full process env inheritance in its upgrade
  subprocesses and can no longer use `ARCLINK_DOCKER_BINARY` to dispatch
  queued upgrade children through `bash`, a relative path, a PATH-injected fake
  `docker`, or another non-Docker executable. Missing or false
  `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED` now stops all seven
  high-authority services before they bind or process direct requests, but an
  accepted value is an acknowledgement of trusted-host residual risk rather
  than tenant-safe isolation.
  The process helper also rejects dynamic-loader, Python path/startup, shell
  startup, Git/SSH command-steering, and secret-looking process env keys before
  helper logs or subprocesses, while the supervisor fails closed before helper
  payload construction on the same unapproved non-token key family. The root
  agent helpers now reject symlink-escaped agent home, Hermes home, and
  workspace paths before root filesystem work, helper logs, or subprocess
  execution, and `agent-process-helper` now rejects symlink-escaped helper log
  directories before log file creation or process execution. Direct/local
  broker/helper execution now binds loopback by default rather than inheriting
  an implicit `0.0.0.0` listener; Compose remains the explicit broad-bind
  source for internal Docker request networks. The `agent-supervisor`
  enrollment-provisioner child no longer inherits unrelated live secret-bearing
  environment keys from the supervisor process. Dashboard backend hosts now
  fail closed if they are wildcard, global, multicast, malformed, or non-IP
  values before either the root process helper or dashboard broker constructs
  a dashboard subprocess. Symlinked configured or requested Docker agent-home
  roots now fail closed before the root agent helpers can write uid/gid
  assignments, repair ownership, create helper logs, or start subprocesses.
  Symlinked, directory, or non-regular `agent-user-helper` uid/gid assignment
  files and temp files now fail closed before assignment writes, account
  commands, agent-home directory creation, or recursive chown.
  Missing, symlinked, directory, unreadable, or non-executable fixed repo
  command targets now fail closed before `agent-process-helper` creates helper
  logs or starts one-shot/gateway/dashboard subprocesses.
- Owner/surface: platform security, Docker deployment.
- Next repair: no current bounded unattended local helper split is identified
  by `config/docker-authority-inventory.json`. Route closure through an
  operator residual-risk decision, an explicitly authorized stronger isolation
  design, or authorized live alert integration for the now-source-owned
  incident signals. If the operator chooses stronger isolation, first split
  that decision into a concrete new source/test repair row before editing.
  Treat the current capability-drop, static allowlist, B2 review,
  action-worker path guard, notification-delivery bridge command guard,
  curator-refresh socket removal, control-provisioner executor preflight,
  notification-delivery gateway exec broker, deployment exec broker,
  action-worker socket removal, agent-supervisor dashboard broker split, and
  queued operator-upgrade broker routing, root-capture opt-in guard, and
  agent-supervisor metadata/path guard, plus the `GAP-019-M` incident-control
  ledger, `GAP-019-N` migration-capture helper split, and `GAP-019-O`
  agent-user helper split, `GAP-019-P` agent-process helper split, and
  `GAP-019-Q` agent-user-helper capability narrowing, and `GAP-019-R`
  process-helper argv/log env hardening, and `GAP-019-S` helper configured-root
  confinement, `GAP-019-T` read-only non-broker host-repo binds,
  `GAP-019-U` operator-upgrade broker split, and `GAP-019-V` static
  `control-ingress` routes, and `GAP-019-W` process-helper control-token env
  rejection, plus `GAP-019-AD` process-helper pre-drop executable lookup
  hardening, plus `GAP-019-X`, `GAP-019-Y`, and `GAP-019-Z`
  service-env/private-mount narrowing, plus `GAP-019-AA`
  deployment-exec-broker service-env narrowing and `GAP-019-AB`
  operator-upgrade-broker service-env/private-mount/child-env narrowing, plus
  `GAP-019-AC` migration-capture-helper service-env/state-root confinement,
  plus `GAP-019-AE` agent-user-helper root executable lookup hardening and
  `GAP-019-AF` agent-supervisor-broker Docker CLI lookup hardening and
  `GAP-019-AG` deployment-exec-broker Docker CLI lookup hardening and
  `GAP-019-AH` gateway-exec-broker Docker CLI lookup hardening and
  `GAP-019-AI` operator-upgrade-broker Docker CLI lookup hardening and
  `GAP-019-AJ` process-helper desired-signature restart/bounded shutdown and
  `GAP-019-AK` broker/helper internal Compose network scoping, `GAP-019-AL`
  trusted-host acknowledgement gate, and `GAP-019-AM` process-helper
  unapproved env key rejection, and `GAP-019-AN` root agent-helper symlink path
  rejection, `GAP-019-AO` process-helper log-directory symlink rejection, and
  `GAP-019-AP` direct-run loopback listener defaults, and `GAP-019-AQ`
  agent-supervisor provisioner child-env allowlisting, `GAP-019-AR`
  dashboard backend host confinement, and `GAP-019-AS` configured agent-home
  root symlink rejection, and `GAP-019-AT` process-helper configured-root
  symlink rejection, and `GAP-019-AU` process-helper fixed command target
  preflight, and `GAP-019-AV` operator-upgrade broker fixed script target
  preflight, and `GAP-019-AW` operator-upgrade broker upstream deploy-key path
  confinement, and `GAP-019-AX` deployment-exec broker rendered config-file
  preflight, and `GAP-019-AY` gateway-exec broker fallback config-file
  preflight, and `GAP-019-AZ` agent-supervisor broker private-bind-root
  preflight, and `GAP-019-BD` remaining high-authority broker/helper
  rejected-request incident evidence
  as interim hardening, not closure of the P0
  trusted-host risk.

### GAP-020 - Backup and disaster recovery are documented but not proofed

- Severity: P2
- Status: partial, proof-gated, ops-gap
- Journey joints: `J-26`, `J-27`
- Proof gates: `PG-BACKUP`
- Joint: restore confidence after data loss or migration
- Expected: backup docs map to automated or periodically executed restore
  evidence.
- Actual evidence: backup docs list backup targets, restore steps, retention,
  a local no-secret restore-smoke command, and a periodic staging restore
  expectation (`docs/arclink/backup-restore.md`). `bin/arclink-restore-smoke.sh`
  restores a local shared or agent-home backup artifact into a temp/provided
  directory, rejects remote GitHub/SSH sources, avoids Docker/systemd/deploy
  mutation, validates shared layout and SQLite quick-checks when present, and
  rejects agent-home artifacts that contain `secrets/` or `logs/`. Focused
  regression tests cover shared local git snapshots, remote-source rejection,
  and agent-home backup artifacts produced by `bin/backup-agent-home.sh`
  (`tests/test_backup_git_regressions.py`,
  `tests/test_agent_backup_regressions.py`).
- Missing proof/tests: staging restore ledger, restored health output, restored
  dashboard load, restored deployment stack health, and live restore of at
  least one ArcPod state stack.
- Impact: backup existence does not prove recoverability.
- Owner/surface: operations, backup/restore.
- Next repair: run authorized `PG-BACKUP` staging restore proof and preserve a
  dated evidence artifact before production launch.

### GAP-021 - Cloud provider fleet creation remains proof-gated

- Severity: P2
- Status: proof-gated
- Journey joints: `J-10`
- Proof gates: `PG-FLEET`
- Joint: remote worker fleet scaling
- Expected: Hetzner/Linode worker creation, SSH wait, join, inventory health,
  drain/remove, and destroy work with provider APIs.
- Actual evidence: fleet runbook says provider-visible listing and create paths
  exist, but live provider creation, SSH wait, and join proof require explicit
  Operator authorization (`docs/arclink/fleet-operator-runbook.md:94-119`).
  Production runbook says missing provider tokens fail closed
  (`docs/arclink/control-node-production-runbook.md:133-158`). Local no-secret
  lifecycle tests now cover Hetzner and Linode create idempotency, duplicate
  hostname refusal, probe handoff, drain-before-destroy, provider delete, and
  destroy replay with fake clients
  (`tests/test_arclink_inventory.py`,
  `tests/test_arclink_inventory_hetzner.py`,
  `tests/test_arclink_inventory_linode.py`,
  `tests/test_arclink_fleet_inventory_worker.py`).
- Missing proof/tests: authorized live provider create/join/probe/drain/remove
  proof for each supported provider.
- Impact: Scale/Federation claims that depend on remote capacity remain
  source-level only.
- Owner/surface: fleet inventory, provider adapters.
- Next repair: run one authorized scratch-worker lifecycle per provider with
  real provider APIs, SSH wait, worker join, health probe, drain/remove, and
  destroy evidence preserved in redacted proof artifacts.

### GAP-022 - Crew Training live LLM generation is proof-gated

- Severity: P2
- Status: proof-gated
- Journey joints: `J-08`, `J-24`
- Proof gates: `PG-PROVIDER`
- Joint: Captain training recipe generation
- Expected: the Captain can preview/apply a Crew recipe, with live LLM help when
  policy and budget allow.
- Actual evidence: production runbook says Crew Training routes exist and
  deterministic fallback is used when provider credential or safe output checks
  are unavailable. Live LLM recipe generation remains proof-gated
  (`docs/arclink/control-node-production-runbook.md:186-205`).
- Missing proof/tests: live recipe generation under scoped provider/budget,
  unsafe output rejection, dashboard/bot copy that labels fallback vs generated.
- Impact: a headline "Train My Crew" feature may work as preset-only in the
  common unproven provider state.
- Owner/surface: Crew recipe, provider, dashboard, Raven.
- Next repair: run a bounded live generation proof and keep fallback labels
  visible.

### GAP-023 - Public selected-agent streaming is explicitly unvalidated

- Severity: P3
- Status: proof-gated
- Journey joints: `J-03`, `J-04`
- Proof gates: `PG-BOTS`
- Joint: public-channel selected-agent replies
- Expected: if streaming is advertised, Telegram/Discord users see incremental
  Agent responses safely.
- Actual evidence: Raven docs say public selected-agent turns default to
  final-message delivery and `ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING=1` is
  operator opt-in only after runtime validation
  (`docs/arclink/raven-public-bot.md:24-27`).
- Missing proof/tests: live streaming bridge runtime proof, backpressure,
  cancellation, and platform edit/rate-limit behavior.
- Impact: low if final-message delivery is the public contract; high only if
  marketing claims streaming before proof.
- Owner/surface: public bot bridge, notification delivery.
- Next repair: keep final-message copy until streaming proof passes.

### GAP-024 - Provider changes are visible but not self-service

- Severity: P2
- Status: policy-question, ux-gap
- Journey joints: `J-08`, `J-13`
- Joint: user dashboard Provider Settings
- Expected: users know whether they can add or change a provider themselves.
- Actual evidence: provider-state returns `self_service_provider_add:
  policy_question`, `dashboard_mutation: disabled`, and guidance that provider
  changes are operator-managed or secure handoff until policy defines
  self-service (`python/arclink_api_auth.py:3366-3380`). The dashboard renders
  this state instead of a mutation form (`web/src/app/dashboard/page.tsx:1594-1647`).
- Missing proof/tests: product decision, secure credential collection design if
  self-service is allowed, and user-facing copy if not.
- Impact: users may expect BYOK/provider switching but only see read-only state.
- Owner/surface: provider product, dashboard, credential handoff.
- Next repair: choose self-service or operator-only, then make dashboard and
  Raven copy unambiguous.

### GAP-025 - Broad local Python suite is green

- Severity: P1
- Status: real
- Journey joints: `J-03`, `J-15`, `J-18`, `J-19`, `J-21`, `J-22`, `J-26`, `J-27`, `J-28`
- Joint: local release confidence for the source-grounded journey and gap atlas
- Expected: the documentation handoff should not imply broad local validation is
  green unless the broad local suite actually passes or known failures are
  explicitly triaged.
- Actual evidence: Ralphie's selected no-secret validation passed 582 focused
  tests plus shell syntax and web checks, but a follow-up full-suite run of
  `python3 -m pytest -q tests` on 2026-05-20 reported 197 failed, 1012 passed,
  and 6 skipped. Failure clusters include Discord/Telegram onboarding contract,
  Notion onboarding/CLI, plugin install and linked-root behavior, repo sync,
  backup regressions, Curator bootstrap, deploy/health shell regressions,
  vault layout/symlink/watch, provider pins, user-agent refresh, and runtime
  access tests. First triage update: the Discord/Telegram public-bot adapter
  contract cluster was stale test expectation against the current Raven
  direct-package onboarding flow; `tests/test_arclink_telegram.py` and
  `tests/test_arclink_discord.py` now match the already-passing core
  `tests/test_arclink_public_bots.py` contract. Second triage update: the
  focused Notion onboarding/CLI cluster, plugins/workspace cluster, and
  vault/repo/backup cluster pass locally; the deploy/health shell cluster now
  passes after repairing a stale Notion SSOT prompt vocabulary expectation; and
  the hosted OpenAPI proof-token contract from `GAP-008` is locally closed.
  Final triage update: stale test isolation leaks in auto-provision,
  Nextcloud, notification delivery, pin-upgrade, and enrollment-provisioner
  tests were repaired; stale sovereign handoff copy assertions were aligned
  with the current Raven/Helm phrasing; and the uncapped broad no-secret suite
  stayed green after the `GAP-019-G` local repair on 2026-05-21 with
  `1225 passed, 6 skipped`, and stayed green after the `GAP-019-H` local
  repair on 2026-05-21 with `1226 passed, 6 skipped`, and stayed green after
  the `GAP-019-I` local repair on 2026-05-21 with `1227 passed, 6 skipped`,
  and stayed green after the `GAP-019-J` local repair on 2026-05-21 with
  `1231 passed, 6 skipped`, and stayed green after the `GAP-019-K` local
  repair on 2026-05-21 with `1234 passed, 6 skipped`, and stayed green after
  the `GAP-019-L` local repair on 2026-05-21 with
  `1235 passed, 6 skipped`, and stayed green after the `GAP-019-M` local repair
  on 2026-05-21 with `1235 passed, 6 skipped`, and stayed green after the
  `GAP-010` local web repair and evidence-doc update on 2026-05-21 with
  1235 passed, 6 skipped, and 81 warnings in 62.56s, and stayed green after
  the `GAP-013-B` local backup write-check boundary repair on 2026-05-21 with
  1241 passed, 6 skipped, and 81 warnings in 62.78s, and stayed green after
  the `GAP-013-C` dashboard backup UX repair on 2026-05-21 with 1241 passed,
  6 skipped, and 81 warnings in 62.82s, and stayed green after the `GAP-020`
  local restore-smoke repair on 2026-05-21 with 1243 passed, 6 skipped, and
  81 warnings in 62.56s, and stayed green after the `GAP-015-B` local share
  retry repair on 2026-05-21 with 1247 passed, 6 skipped, and 81 warnings in
  63.12s, and stayed green after the `GAP-019-N` migration-capture helper split
  on 2026-05-21 with 1251 passed, 6 skipped, and 81 warnings in 63.42s, and
  stayed green after the `GAP-019-O` agent-user helper split on 2026-05-21 with
  1253 passed, 6 skipped, and 81 warnings in 63.09s, and stayed green after
  the `GAP-019-P` agent-process helper split on 2026-05-22 with 1255 passed,
  6 skipped, and 81 warnings in 62.87s, and stayed green after the
  `GAP-019-Q` agent-user-helper capability narrowing on 2026-05-22 with
  1256 passed, 6 skipped, and 81 warnings in 63.05s, and stayed green after
  the `GAP-019-R` agent-process-helper env exposure hardening on 2026-05-22
  with 1258 passed, 6 skipped, and 81 warnings in 62.66s, and stayed green
  after the `GAP-019-S` helper configured-root confinement on 2026-05-22 with
  1260 passed, 6 skipped, and 81 warnings in 63.01s, and stayed green after
  the `GAP-019-T` read-only agent host-repo bind repair on 2026-05-22 with
  1260 passed, 6 skipped, and 81 warnings in 63.26s, and stayed green after
  the `GAP-019-U` operator-upgrade broker split on 2026-05-22 with 1260
  passed, 6 skipped, and 81 warnings in 63.74s, and stayed green after the
  `GAP-019-V` static control-ingress route repair on 2026-05-22 with 1262
  passed, 6 skipped, and 81 warnings in 63.09s, and stayed green after the
  `GAP-019-W` process-helper control-token env rejection repair on 2026-05-22
  with 1262 passed, 6 skipped, and 81 warnings in 63.36s, and stayed green
  after the `GAP-019-X` process-helper service env/secret-mount repair on
  2026-05-22 with 1263 passed, 6 skipped, and 81 warnings in 63.01s, and
  stayed green after the `GAP-019-Y` gateway-exec-broker service
  env/private-mount repair on 2026-05-22 with 1264 passed, 6 skipped, and
  81 warnings in 62.92s, and stayed green after the `GAP-019-Z`
  agent-supervisor-broker service env/private-mount repair on 2026-05-22 with
  1265 passed, 6 skipped, and 81 warnings in 62.94s, and stayed green after
  the `GAP-019-AB` operator-upgrade-broker service/private-mount/child-env
  repair on 2026-05-22 with 1267 passed, 6 skipped, and 81 warnings in 63.35s,
  and stayed green after the `GAP-019-AC` migration-capture-helper service-env
  and configured state-root confinement repair on 2026-05-22 with 1269 passed,
  6 skipped, and 81 warnings in 63.45s, and stayed green after the
  `GAP-019-AD` agent-process-helper pre-drop executable lookup repair on
  2026-05-22 with 1269 passed, 6 skipped, and 81 warnings in 62.86s, and
  stayed green after the `GAP-019-AE` agent-user-helper root executable lookup
  repair on 2026-05-22 with 1270 passed, 6 skipped, and 81 warnings in 63.07s,
  and stayed green after the `GAP-019-AF` agent-supervisor-broker Docker CLI
  lookup repair on 2026-05-22 with 1271 passed, 6 skipped, and 81 warnings in
  63.26s, and stayed green after the `GAP-019-AG`
  deployment-exec-broker Docker CLI lookup repair on 2026-05-22 with 1272
  passed, 6 skipped, and 81 warnings in 63.92s, and stayed green after the
  `GAP-019-AH` gateway-exec-broker Docker CLI lookup repair on 2026-05-22 with
  1273 passed, 6 skipped, and 81 warnings in 63.24s, and stayed green after
  the `GAP-019-AI` operator-upgrade-broker Docker CLI lookup repair on
  2026-05-22 with 1274 passed, 6 skipped, and 81 warnings in 63.24s, and
  stayed green after the `GAP-019-AJ` process-helper desired-signature restart
  and bounded shutdown repair on 2026-05-22 with 1275 passed, 6 skipped, and
  81 warnings in 63.38s, and stayed green after the `GAP-021-A` no-secret
  cloud-provider lifecycle harness on 2026-05-22 with 1280 passed, 6 skipped,
  and 81 warnings in 63.38s, and stayed green after the `GAP-019-AM`
  process-helper unapproved env key rejection repair on 2026-05-22 with
  1285 passed, 6 skipped, and 81 warnings in 63.57s, and stayed green after
  the `GAP-019-AN` root agent-helper symlink path rejection repair on
  2026-05-22 with 1286 passed, 6 skipped, and 81 warnings in 63.69s, and
  stayed green after the `GAP-019-AO` process-helper log-directory symlink
  rejection repair on 2026-05-22 with 1287 passed, 6 skipped, and 81 warnings
  in 63.35s, and stayed green after the `GAP-019-AP` direct-run loopback
  listener default repair on 2026-05-23 with 1288 passed, 6 skipped, and
  81 warnings in 63.51s, and stayed green after the `GAP-019-AQ`
  agent-supervisor provisioner child-env allowlist repair on 2026-05-23 with
  1289 passed, 6 skipped, and 81 warnings in 63.99s, and stayed green after
  the `GAP-019-AR` dashboard backend host confinement repair on 2026-05-23
  with 1291 passed, 6 skipped, and 81 warnings in 63.48s, and stayed green
  after the `GAP-019-AS` configured agent-home root symlink rejection repair on
  2026-05-23 with 1292 passed, 6 skipped, and 81 warnings in 63.10s, and
  stayed green after the `GAP-019-AT` process-helper configured-root symlink
  rejection repair on 2026-05-23 with 1293 passed, 6 skipped, and 81 warnings
  in 63.81s, and stayed green after the `GAP-014-B` authenticated Drive/Code
  share-request broker handoff on 2026-05-23 with 1294 passed, 6 skipped, and
  81 warnings in 63.55s, and stayed green after the `GAP-014-C` hosted
  Request Share broker repair on 2026-05-23 with 1295 passed, 6 skipped, and
  81 warnings in 63.99s, and stayed green after the `GAP-019-AU`
  process-helper fixed command target preflight repair on 2026-05-23 with
  1296 passed, 6 skipped, and 81 warnings in 63.38s, and stayed green after
  the `GAP-019-AV` operator-upgrade broker fixed script target preflight repair
  on 2026-05-23 with 1297 passed, 6 skipped, and 81 warnings in 63.76s, and
  stayed green after the `GAP-019-AW` operator-upgrade broker upstream
  deploy-key path confinement repair on 2026-05-23 with 1298 passed, 6 skipped,
  and 81 warnings in 64.39s, and stayed green after the `GAP-019-AX`
  deployment-exec broker rendered config-file preflight repair on 2026-05-23
  with 1299 passed, 6 skipped, and 81 warnings in 63.66s, and stayed green
  after the `GAP-019-AY` gateway-exec broker fallback config-file preflight
  repair on 2026-05-23 with 1300 passed, 6 skipped, and 81 warnings in
  63.86s, and stayed green after the `GAP-019-AZ` agent-supervisor broker
  private-bind-root preflight repair on 2026-05-23 with 1301 passed, 6 skipped,
  and 81 warnings in 63.88s, and stayed green after the `GAP-019-BA`
  agent-user-helper assignment-file preflight repair on 2026-05-23 with 1302
  passed, 6 skipped, and 81 warnings in 64.00s, and stayed green after the
  `GAP-019-BB` agent-process-helper rejected-request incident repair on
  2026-05-23 with 1303 passed, 6 skipped, and 81 warnings in 63.59s, and
  stayed green after the `GAP-019-BC` gateway-exec-broker rejected-request
  incident repair on 2026-05-23 with 1304 passed, 6 skipped, and 81 warnings
  in 63.51s, and stayed green after the `GAP-019-BD` remaining
  broker/helper rejected-request incident repair on 2026-05-23 with 1305
  passed, 6 skipped, and 81 warnings in 64.22s. A 2026-05-26 lint-phase
  adversarial recheck initially caught one local regression in the
  `agent-process-helper` rejection-incident path when only `ARCLINK_PRIV_DIR`
  was configured; `python/arclink_rejection_incidents.py` was repaired, the
  focused Docker incident tests passed, and the broad suite rerun passed with
  1305 passed, 6 skipped, and 81 warnings in 64.08s.
- Missing proof/tests: none for the broad no-secret local Python suite. This
  does not close live proof gates or web/Node validation.
- Impact: the checkout may now be described as broad Python regression-clean for
  the current public repository state, while live/external claims remain gated.
- Owner/surface: release validation, CI/preflight, affected owners from each
  failure cluster.
- Next repair: rerun `python3 -m pytest -q tests` after each future source/test
  slice; reopen this row or split a new gap if broad validation regresses.

### GAP-026 - Live upgrade proof is unproven

- Severity: P1
- Status: proof-gated, ops-gap
- Journey joints: `J-15`, `J-16`, `J-17`, `J-25`, `J-27`
- Proof gates: `PG-UPGRADE`
- Joint: shared-host, Docker, Control Node, and component-pin upgrades
- Expected: an authorized operator can run the relevant upgrade family,
  preserve private state, align agents, record release state, restart/realign
  services, and finish with strict health plus smoke evidence.
- Actual evidence: upgrade commands and local guardrails exist for shared-host,
  Docker, Control Node, deploy-key, and component-pin paths (`AGENTS.md`,
  `bin/deploy.sh`, `bin/component-upgrade.sh`,
  `python/arclink_operator_upgrade_broker.py`, `python/arclink_pin_upgrade_check.py`,
  `docs/arclink/sovereign-control-node.md`,
  `docs/arclink/control-node-production-runbook.md`,
  `tests/test_deploy_regressions.py`,
  `tests/test_arclink_upgrade_notifications.py`,
  `tests/test_arclink_pin_upgrade_detector.py`). The proof-gate table already
  declares `PG-UPGRADE`, but this row is the owning register entry that was
  missing from the active gap map.
- Missing proof/tests: authorized live upgrade evidence for the applicable
  command family, including release-state output, strict health, smoke/live
  proof where available, and redacted operator-action logs for queued Docker
  operator upgrades or component-pin upgrades.
- Impact: ArcLink can describe upgrade mechanics as locally guarded, but cannot
  claim live upgrade readiness for Shared Host, Docker validation, Sovereign
  Control Node, or component-pin application until the real upgrade path is
  exercised.
- Owner/surface: release/ops, deploy keys, component pins, operator upgrade
  broker.
- Next repair: run the smallest authorized `PG-UPGRADE` slice for the target
  deployment mode, archive redacted release/health/smoke evidence outside the
  public repo, and split any failed stage into its own repair row.

### GAP-027 - Discord Curator operator-action authority needs an explicit policy

- Severity: P2
- Status: policy-question, security-risk, doc-gap, test-gap
- Journey joints: `J-14`, `J-18`, `J-25`, `J-28`
- Joint: Curator operator-channel approvals, retries, SSOT writes, and queued
  upgrades
- Expected: every Curator operator action lane should state which factor grants
  authority and should have tests for that choice. Either Discord operator
  channel membership is the accepted approval factor, or Discord needs parity
  with Telegram's typed approval code, a role/user allowlist, or another
  explicit nonce/second-factor design.
- Actual evidence: Telegram operator commands can require
  `ARCLINK_OPERATOR_TELEGRAM_APPROVAL_CODE` or
  `ARCLINK_OPERATOR_APPROVAL_CODE`, and approval/install buttons are refused
  when that code is configured (`python/arclink_curator_onboarding.py`,
  `tests/test_arclink_curator_onboarding_regressions.py`,
  `docs/arclink/operations-runbook.md`). Discord operator slash commands and
  message components are restricted to the configured operator channel, then
  `/approve`, `/deny`, `/upgrade`, retry-contact, SSOT, and pin-upgrade actions
  execute from that channel (`python/arclink_curator_discord_onboarding.py`).
  Existing Discord tests assert the commands/buttons are exposed and routed,
  but do not encode whether channel membership alone is the intended security
  model (`tests/test_arclink_enrollment_provisioner_regressions.py`,
  `tests/test_arclink_upgrade_notifications.py`).
- Missing proof/tests: operator policy and matching tests for the Discord
  authority model. If channel membership is accepted, document the Discord
  server/channel permission assumptions and add a regression that preserves
  that exact boundary. If not, implement and test the chosen second factor or
  allowlist before treating Discord operator actions as final.
- Impact: future operators and agents may incorrectly assume Telegram's
  approval-code hardening covers Discord, or may harden one lane while leaving
  the other ambiguous.
- Owner/surface: Curator Discord operator channel, operator security policy,
  onboarding/provisioning approvals, upgrade notifications.
- Next repair: make the policy decision, then update Curator Discord code,
  runbooks, and regression tests so the intended authority model is explicit.

### GAP-028 - Shared Host install and enrollment smoke is not current

- Severity: P1
- Status: proof-gated, ops-gap
- Journey joints: `J-15`, `J-18`, `J-27`
- Proof gates: `PG-SHARED-HOST`
- Joint: operator-led Shared Host fresh install, Curator/enrollment, health,
  and cleanup proof
- Expected: the operator-led Shared Host path can still be called viable for a
  fresh supported Linux/systemd host only after the host-mutating install smoke
  proves install, service-user units, Curator/user-agent enrollment rails,
  health, live agent tool smoke where available, and cleanup.
- Actual evidence: the code path remains first-class and locally guarded:
  direct deploy dispatch exposes `./deploy.sh install`, `./deploy.sh upgrade`,
  `./deploy.sh health`, enrollment, Curator setup, and component commands
  (`bin/deploy.sh`); `run_root_install` bootstraps system packages, syncs the
  public repo, writes runtime config, installs system and user services,
  bootstraps Curator, realigns enrolled agents, records release state, runs
  strict health, and runs `bin/live-agent-tool-smoke.sh` when present
  (`bin/deploy.sh`); `test.sh` delegates to `bin/ci-preflight.sh` and the sudo
  Shared Host install smoke (`test.sh`, `bin/ci-install-smoke.sh`). Static and
  local regression coverage remains substantial across deploy, health,
  systemd, enrollment, and user-service contracts
  (`tests/test_deploy_regressions.py`, `tests/test_health_regressions.py`,
  `tests/test_arclink_agent_user_services.py`,
  `tests/test_arclink_enrollment_provisioner_regressions.py`). The current gap
  register, however, only had `PG-UPGRADE` for post-install upgrade proof and
  did not own the fresh Shared Host install/enrollment smoke as a current
  authorized host proof.
- Missing proof/tests: a current `./test.sh` or
  `sudo bin/ci-install-smoke.sh` run on a supported host, with redacted
  install/health/enrollment/cleanup evidence. This is host-mutating local
  proof, not credentialed product E2E proof, and it must remain separate from
  the Sovereign Control Node `PG-PROD` path.
- Impact: Shared Host Mode is maintained in source and tests, but future
  operators may overstate it as freshly smoke-proven when the current checkout
  has only static/local regression evidence in the public handoff.
- Owner/surface: Shared Host deploy/install, systemd services, Curator,
  enrollment provisioner, health.
- Next repair: in an explicit host proof window, run `./test.sh` or the
  narrower sudo install smoke on a supported disposable Linux/systemd host,
  keep logs secret-free/redacted, and update this row plus
  `research/COVERAGE_MATRIX.md` and `USER_JOURNEY.md` with the result.

### GAP-029 - Sovereign Operator Raven is not a full-service control plane

- Severity: P1
- Status: product-gap, security-sensitive, local-gap
- Journey joints: `J-03`, `J-04`, `J-14`, `J-17`, `J-25`, `J-26`, `J-27`,
  `J-28`
- Proof gates: `PG-BOTS`, `PG-PROVISION`, `PG-FLEET`, `PG-UPGRADE`,
  `PG-BACKUP`
- Joint: operator chat control for health, fleet, users, pods, billing,
  provider, upgrades, backups, live proof, and incidents
- Expected: the Sovereign operator can pair Telegram, Discord, or both during
  Control Node install, choose a primary response channel, and manage the
  stack from Operator Raven with the same audited action rails available to the
  admin dashboard and CLI. Natural-language requests may diagnose and plan, but
  all mutation must resolve to typed, allowlisted, audited commands with
  role-scoped authorization, replay-resistant confirmation where needed, and
  secret-free output.
- Actual evidence: the Control Node install now asks for operator Raven
  channels and primary response intent (`bin/deploy.sh`). Existing source has
  public Raven flows, operator notifications, Telegram approval-code support,
  Discord operator-channel actions, admin action workers, pin-upgrade
  notifications, and upgrade brokers
  (`python/arclink_public_bots.py`, `python/arclink_curator_onboarding.py`,
  `python/arclink_curator_discord_onboarding.py`,
  `python/arclink_notification_delivery.py`,
  `python/arclink_action_worker.py`,
  `python/arclink_operator_upgrade_broker.py`). A 2026-05-27 local slice adds
  a shared read-only/dry-run Operator Raven command layer for `status`,
  `fleet list`, `worker probe --dry-run`, `user lookup`,
  `pod repair --dry-run`, and injected `upgrade check`
  (`python/arclink_operator_raven.py`). Telegram and Discord operator adapters
  now route those commands through the shared schema while preserving existing
  Telegram operator approval-code behavior and Discord operator-channel
  gating (`python/arclink_curator_onboarding.py`,
  `python/arclink_curator_discord_onboarding.py`). Focused coverage proves
  secret-free output, no action queueing for dry-run commands, fake/local
  upgrade-check injection, and adapter authorization boundaries
  (`tests/test_arclink_operator_raven.py`).
- Missing proof/tests: broad mutation policy, audit rows, runbook coverage, and
  tests for Operator Raven actions beyond the first read-only/dry-run slice:
  fleet admission/probe/drain execution, user suspend/restore, pod
  repair/rollback/teardown execution, billing/provider state mutation,
  backup/restore, upgrade orchestration, evidence/live proof, and incident
  diagnostics. Discord authority policy from `GAP-027` must be resolved or
  inherited before broad operator actions ship.
- Impact: operators still need CLI/admin dashboard/manual runbooks for many
  day-two tasks, so the chat-native "full power of ArcLink in the operator's
  hand" promise is not yet real.
- Owner/surface: Operator Raven, notification delivery, admin action worker,
  operator security policy, deploy/control menus.
- Next repair: expand from the first read-only/dry-run slice into audited
  action-worker/broker-backed Operator Raven commands only after the intended
  chat authority and confirmation policy is explicit. Keep destructive,
  credential-sensitive, live deploy, Docker, SSH, provider, Stripe, and backup
  restore operations out of chat until they have typed schemas, confirmation,
  audit rows, and focused tests.

### GAP-030 - Sovereign worker readiness is partial

- Severity: P1
- Status: partial, proof-gated
- Journey joints: `J-09`, `J-10`, `J-17`, `J-27`
- Proof gates: `PG-PROVISION`, `PG-FLEET`
- Joint: Control Node install, worker admission, fleet placement, ArcPod apply
- Expected: a Sovereign Control Node can start its web/API/admin surfaces
  without workers, but it must not claim product readiness for paid ArcPod
  provisioning until at least one eligible worker has been registered, probed,
  authorized for the selected executor, and shown with available capacity.
- Actual evidence: `collect_control_install_answers()` asks for deployment
  style, executor adapter, worker state-root base, optional local worker
  registration, local SSH user, fleet SSH key handoff, and local SSH repair
  (`bin/deploy.sh`). Workerless interactive installs now either stop before
  config write or explicitly continue as control-plane-only with
  `ARCLINK_CONTROL_PROVISIONER_ENABLED=0`. Remote worker registration enables
  the provisioner only after a passed smoke test. `run_control_inventory()`
  provides manual/provider worker registration, probe, drain, remove,
  rotate-key, and strategy commands. Control install, reconfigure, and worker
  registration now print a provisioning readiness summary that separates
  "ready to provision ArcPods" from blocked/control-plane-only states.
- Missing proof/tests: deeper behavioral regression tests for pending-SSH,
  local-worker, and remote-worker cases; dashboard/admin/API readiness state;
  Operator Raven readiness status; live `PG-FLEET`/`PG-PROVISION` evidence for
  the chosen worker path.
- Impact: the first install can look successful while the first Captain's paid
  ArcPod would remain blocked at placement/apply time.
- Owner/surface: `bin/deploy.sh` Control Node install, fleet inventory,
  provisioning readiness, admin/dashboard readiness copy.
- Next repair: promote the readiness summary into admin/dashboard and Operator
  Raven status, add behavioral tests for no-worker/pending-SSH/local/remote
  cases, and run the chosen worker live proof before closing the row.

### GAP-031 - LLM Router fallback cascade is partial

- Severity: P2
- Status: partial, provider-proof-gated
- Journey joints: `J-07`, `J-08`, `J-24`, `J-27`
- Proof gates: `PG-PROVIDER`
- Joint: central inference, Raven/Crew Training/model fallback, budget state
- Expected: Raven, Agents, Crew Training, and memory/knowledge synthesis should
  route through central inference policy where possible. The operator can
  configure primary and fallback models, including provider-side CSV model
  strings where supported, and the router can retry bounded fallback candidates on
  `429`, overload, or explicitly configured transient provider errors while
  recording fallback metadata and preserving usage/budget controls.
- Actual evidence: the router already supports central provider relay, scoped
  router keys, sanitized usage records, request/body/token/rate/concurrency
  limits, budget reservations, allowed models, model replacements, and model
  auto-promotion (`python/arclink_llm_router.py`,
  `docs/arclink/llm-router.md`, `tests/test_arclink_llm_router.py`). Control
  Node install now asks for the router default model or provider-side fallback
  CSV, allowed models, router fallback models/status codes, emergency
  replacements, and catalog auto-promotion policy (`bin/deploy.sh`). The local
  router now retries non-streaming chat completions across
  `ARCLINK_LLM_ROUTER_FALLBACK_MODELS` for configured retryable statuses,
  records the final fallback model in usage, adds sanitized response metadata,
  and preserves prompt/secret non-storage
  (`tests/test_arclink_llm_router.py`).
- Missing proof/tests: streaming fallback behavior, live/provider overload
  proof, richer audit rows for failed pre-fallback attempts, and pricing/budget
  reservation refinement when fallback models have materially different costs.
- Impact: non-streaming provider overload has a local fallback rail, but
  streaming requests and live provider behavior still need explicit proof
  before the whole inference path can be called fallback-complete.
- Owner/surface: LLM router, model provider config, provider adapter, Raven/Crew
  Training copy, dashboard/provider state.
- Next repair: add streaming-safe fallback semantics or clear streaming
  limitations, add richer fallback attempt audit, refine pricing/reservation
  behavior for cost-different fallback models, and run live `PG-PROVIDER`
  overload proof.

### GAP-032 - Control Node lacks rolling Hermes/ArcPod update orchestration

- Severity: P1
- Status: product-gap, proof-gated
- Journey joints: `J-17`, `J-18`, `J-19`, `J-21`, `J-23`, `J-25`, `J-27`
- Proof gates: `PG-UPGRADE`, `PG-HERMES`
- Joint: Control Node release upgrade, Hermes runtime pins, ArcPod refresh,
  skills/plugins/docs/memory alignment
- Expected: a Control Node upgrade can stage or apply the new release, then
  update ArcPods in bounded parallel batches. Each Pod refreshes Hermes runtime
  pins, ArcLink skills, dashboard plugins, command menus, managed context,
  pinned Hermes docs, qmd/memory hooks, and service definitions, then reports
  per-pod health/smoke evidence. Failures halt the rollout, preserve state,
  and produce a rollback or repair plan.
- Actual evidence: deploy/control upgrade, release state, component pin
  checks, public-bot unmanaged-upgrade refusal, pin upgrade notifications, and
  local upgrade tests exist (`bin/deploy.sh`, `bin/component-upgrade.sh`,
  `python/arclink_pin_upgrade_check.py`, `python/arclink_public_bots.py`,
  `tests/test_arclink_upgrade_notifications.py`,
  `tests/test_deploy_regressions.py`). They do not yet form a Control
  Node-owned rolling ArcPod update orchestrator.
- Missing proof/tests: ArcPod update job model, batch concurrency policy,
  preflight/backup freshness checks, per-pod refresh/health/smoke collection,
  stop-on-failure semantics, dashboard/Operator Raven status, and live
  `PG-UPGRADE`/`PG-HERMES` evidence.
- Impact: Hermes and ArcLink updates remain locally guarded but operationally
  fragmented; at scale, upgrades risk becoming sequential, manual, or
  under-observed.
- Owner/surface: Control Node upgrade orchestration, provisioning/action
  workers, Hermes install/refresh scripts, command-menu refresh, health/live
  proof.
- Next repair: build the upgrade job model and dry-run planner first, then
  implement bounded batch execution through existing refresh/apply rails and
  prove one small multi-pod rollout before claiming rolling updates.

### GAP-033 - Cross-surface experience finish gate is not enforced

- Severity: P2
- Status: quality-gap, test-gap
- Journey joints: `J-01`, `J-03`, `J-04`, `J-13`, `J-14`, `J-19`, `J-24`,
  `J-27`
- Proof gates: `PG-PROD`, `PG-BOTS`, `PG-HERMES`
- Joint: Telegram, Discord, web/PWA, admin dashboard, Hermes dashboard
  plugins, CLI, and TUI output
- Expected: ArcLink surfaces should share a clear style contract: compact
  structured copy, role-appropriate Raven/Agent/Operator voice, markdown that
  renders cleanly on chat platforms, buttons/choices for guided flows, secret
  redaction, no raw tracebacks to Captains, and explicit next actions after
  errors or blocked proof gates.
- Actual evidence: individual surfaces have local tests, docs, and product
  copy checks, and a professional finish gate exists in docs. The repository
  does not yet have a single cross-surface assertion set that guards Raven
  messages, Discord/Telegram command payloads, web dashboard copy, plugin
  empty/error states, CLI/TUI summaries, and operator diagnostics together.
- Missing proof/tests: shared fixture-based message snapshots or lint rules for
  representative Captain, Operator, plugin, dashboard, and CLI states;
  platform-specific markdown checks for Telegram/Discord; and browser proof for
  dashboard/plugin text fit and non-overlap.
- Impact: product surfaces can drift independently and become clunky even while
  the underlying workflows remain correct.
- Owner/surface: public bots, web dashboard, Hermes plugins, CLI/TUI deploy
  output, docs/product voice.
- Next repair: define the cross-surface style contract, add representative
  snapshot/lint tests, and run the focused browser/chat proof cluster before
  treating experience polish as product-real.

### GAP-034 - Academy Trainer corpus and continuing education pipeline is unbuilt

- Severity: P1
- Status: product-gap, local-gap, policy-question, data-governance-gap,
  provider-proof-gated
- Journey joints: `J-21`, `J-23`, `J-24`, `J-27`, `J-28`
- Proof gates: `PG-PROVIDER`, `PG-HERMES`
- Joint: Crew Training, Academy corpus, SOUL overlays, Agent knowledge,
  continuing education, source governance
- Expected: Crew Training should be able to prepare a new or existing Agent as a
  genuine subject-matter performer by building a lawful, reusable Academy
  corpus from selected video transcripts, Reddit practitioner discussion,
  Wikipedia/Wikimedia pages, GitHub repositories, scholarly papers, standards,
  blogs/articles/threads, skill repositories, datasets, benchmarks, and
  organization-provided sources. The pipeline should produce a topic map,
  curriculum, lesson cards, source map, approved skills, qmd/vector indexes,
  memory synthesis seeds, SOUL overlay, evaluation tasks, and weekly Continuing
  Education updates.
- Actual evidence: current source supports deterministic Crew Recipes,
  preview/apply/admin-on-behalf apply, active/archived recipe state, SOUL
  overlay projection, managed context, memory synthesis, vault/qmd rails, and
  proof-gated live recipe generation (`python/arclink_crew_recipes.py`,
  `python/arclink_memory_synthesizer.py`,
  `plugins/hermes-agent/arclink-managed-context/`). The new Academy target is
  now specified in `docs/arclink/academy-trainer.md` and summarized in
  `docs/arclink/sovereign-control-node-symphony.md`, but the source-lane
  registry, crawler/fetcher policy, archive manifests, curriculum builder,
  quality scoring, skill selection, evaluation gate, weekly refresh job, and
  dashboard/Raven surfaces are not implemented.
- Missing proof/tests: Academy manifest/schema tests; source-lane registry
  tests; no-secret archive/tombstone tests; YouTube transcript authorization
  policy tests; Reddit deletion/retention compliance tests; Wikipedia/GitHub/
  arXiv/OpenAlex/Semantic Scholar metadata fetcher tests with fake fixtures;
  curriculum and lesson-card generation tests; SOUL overlay replacement tests;
  vault/qmd/memory/skill application tests; continuing education refresh tests;
  evaluation/graduation tests; dashboard/Raven status/copy tests; live/provider
  proof for Academy generation and workspace proof for the trained Agent.
- Impact: a Captain can create a Crew Recipe and apply role/personality rails,
  but ArcLink cannot yet claim it exhaustively equips a Crew member with a
  reusable expert corpus, archived training materials, selected skills, and
  continuing education.
- Owner/surface: Academy Trainer, Crew Training, memory synthesis, vault/qmd,
  skills, managed context, dashboard/Raven, source governance.
- Next repair: implement the local Academy schema and source-lane registry
  first, with fake-source fixtures for corpus manifests, quality scoring,
  curriculum output, SOUL/vault/skill application, continuing education refresh,
  and evaluation gates. Keep live crawling, ASR/transcription, provider
  generation, and external proof gated until policy and credentials are
  authorized.

## Not Gaps / Already Real

These surfaces were checked and found covered at the source/local level. They
still may have separate live proof gates above. `GAP-025` is locally closed by
the 2026-05-23 broad no-secret Python suite, but this section is not live launch
certification.

- Admin login ignores client-asserted MFA. Hosted login passes
  `mfa_verified=False` regardless of request body
  (`python/arclink_hosted_api.py:845-860`), and the regression verifies that a
  client-provided `mfa_verified: true` does not allow admin actions
  (`tests/test_arclink_hosted_api.py:669-720`).
- Entitlement gate, failed payment, refuel, and cancellation are `real`.
  Stripe webhook processing is idempotent and audited
  (`python/arclink_entitlements.py:508-790`) with focused tests for failed
  payment, refuel, and subscription deletion
  (`tests/test_arclink_entitlements.py:163-186`,
  `tests/test_arclink_entitlements.py:766-828`,
  `tests/test_arclink_entitlements.py:1077-1106`).
- Provisioning intent is secret-reference based and blocks execution until
  entitlement is current (`python/arclink_provisioning.py:896-920`,
  `python/arclink_provisioning.py:1217-1225`), with regression coverage for
  entitlement blocking and plaintext secret rejection
  (`tests/test_arclink_provisioning.py:333-346`,
  `tests/test_arclink_provisioning.py:413-458`).
- Fleet placement is deterministic and idempotent for existing active
  placements (`python/arclink_fleet.py:361-433`), with focused tests for
  headroom selection, draining/unhealthy host rejection, idempotency, and
  concurrent active-row uniqueness (`tests/test_arclink_fleet.py:137-198`,
  `tests/test_arclink_fleet.py:239-287`).
- Fleet join rejects enrollment tokens on argv and accepts file/stdin only
  (`bin/arclink-fleet-join.sh:14-34`, `bin/arclink-fleet-join.sh:94-105`),
  and the join regression verifies the argv token is rejected without echoing
  the token (`tests/test_arclink_fleet_join.py:50-56`).
- User credential handoff is owner-scoped, CSRF-protected on acknowledgement,
  and hides removed handoffs from future user API reads
  (`python/arclink_api_auth.py:1647-1800`), with hosted API coverage for
  cross-user rejection, one-time reveal, CSRF acknowledgement, and post-ack
  hiding (`tests/test_arclink_hosted_api.py:976-1098`).
- User dashboard reads are scoped by user and deployment filter
  (`python/arclink_dashboard.py:799-922`), with API/auth tests rejecting
  cross-user dashboard reads (`tests/test_arclink_api_auth.py:70-106`,
  `tests/test_arclink_hosted_api.py:914-930`).
- Drive/Code/Terminal plugin status is sanitized, and Linked roots are read-only
  for writes/git mutations while copy/duplicate into owned roots is allowed
  (`tests/test_arclink_plugins.py:470-555`,
  `tests/test_arclink_plugins.py:560-725`).
- SSOT tools are brokered and scoped. The schema supports read, pending, status,
  approve, deny, preflight, and write, and explicitly rejects destructive
  archive/delete/trash/destroy operations (`python/arclink_mcp_server.py:91-97`,
  `python/arclink_mcp_server.py:393-455`,
  `python/arclink_mcp_server.py:2409-2551`), with schema and skill text tests
  for allowed operations, destructive-operation absence, and broker guidance
  (`tests/test_arclink_mcp_schemas.py:59-70`,
  `tests/test_arclink_notion_skill_text.py:91-128`).
- Raven refuses unmanaged Hermes upgrade commands and keeps upgrades on ArcLink
  rails (`python/arclink_public_bots.py:4962-4995`), and public-bot tests cover
  both pre-onboarding and active-deployment upgrade/update commands
  (`tests/test_arclink_public_bots.py:845-865`,
  `tests/test_arclink_public_bots.py:897-914`).
- LLM Router source design avoids raw prompt/completion storage and stores only
  sanitized usage metadata (`docs/arclink/llm-router.md:47-68`), with router
  and provider-state regressions proving usage recording without prompt,
  completion, central key, or raw router-key leakage
  (`tests/test_arclink_llm_router.py:336-385`,
  `tests/test_arclink_hosted_api.py:3123-3238`).
- Teardown/rollback preserve state roots and keep volume deletion behind
  explicit destructive metadata (`python/arclink_executor.py:2172-2202`,
  `docs/arclink/control-node-production-runbook.md:240-252`), with provisioning
  and executor tests for state-preserving rollback plans, destructive rollback
  rejection, idempotency, and explicit volume-delete behavior
  (`tests/test_arclink_provisioning.py:533-566`,
  `tests/test_arclink_executor.py:774-831`,
  `tests/test_arclink_executor.py:1148-1212`).
- Hosted API rate limiting is `real` for admin login, onboarding, and
  webhooks. Runtime responses include `Retry-After` and `X-RateLimit-*` headers
  (`python/arclink_hosted_api.py:2950-2957`,
  `python/arclink_hosted_api.py:3089-3106`), and focused tests cover admin login
  and onboarding 429 behavior without leaking the subject
  (`tests/test_arclink_hosted_api.py:3883-3944`).
- `GAP-008` is closed at the local contract level. Dynamic and static OpenAPI
  now require `claim_token` for `/api/v1/onboarding/claim-session` and
  `cancel_token` for `/api/v1/onboarding/cancel`
  (`python/arclink_hosted_api.py:2602-2622`,
  `docs/openapi/arclink-v1.openapi.json:985-1017`,
  `docs/openapi/arclink-v1.openapi.json:1061-1099`), and hosted API tests
  assert both specs plus static/dynamic equality
  (`tests/test_arclink_hosted_api.py:3845-3872`).

## Proof Gates

Before any of these claims can move to `real`, run the named authorized
proof and store redacted evidence outside tracked public docs.

| ID | Claim blocked | Required proof |
| --- | --- | --- |
| `PG-PROD` | Full production journey | `bin/arclink-live-proof --live --json` (`docs/arclink/control-node-production-runbook.md:254-260`) |
| `PG-STRIPE` | Stripe checkout, webhook, portal, refuel, refund/cancel | selected `ARCLINK_PROOF_*` Stripe rows (`docs/arclink/live-e2e-secrets-needed.md:56-60`, `docs/arclink/live-e2e-secrets-needed.md:99-104`) |
| `PG-BOTS` | Telegram/Discord webhooks, command menus, buttons, delivery, selected-agent bridge | selected Telegram/Discord proof rows (`docs/arclink/live-e2e-secrets-needed.md:105-112`) |
| `PG-PROVISION` | Control Node ArcPod apply, health, rollback, teardown, dashboard reachability | production Docker/SSH, rollback credentials, secret resolver, and health proof (`docs/arclink/live-e2e-secrets-needed.md:172-186`) |
| `PG-FLEET` | Remote worker SSH, inventory, capacity, provider worker lifecycle | one scratch create/join/probe/drain/remove per provider (`docs/arclink/fleet-operator-runbook.md:94-132`) |
| `PG-INGRESS` | Cloudflare DNS/Access, Traefik routing, Tailscale Serve/Funnel/cert behavior | selected ingress credentials and teardown evidence (`docs/arclink/live-e2e-secrets-needed.md:172-186`) |
| `PG-PROVIDER` | Provider OAuth, inference, key lifecycle, usage/quota/billing sync, router relay | bounded external provider rows plus router proof (`docs/arclink/live-e2e-secrets-needed.md:113-136`, `docs/arclink/llm-router.md:227-245`) |
| `PG-NOTION` | Shared-root membership, webhook callback, page/database read, SSOT write, retained user-owned OAuth | shared-root readability, then explicitly authorized write preflight (`python/arclink_notion_ssot.py:1120-1205`) |
| `PG-HERMES` | Live Hermes dashboard, gateway response, qmd retrieval, memory refresh, Drive/Code/Terminal browser workflows | `bin/arclink-live-proof --journey workspace --live --json` with TLS URL and auth (`docs/arclink/live-e2e-secrets-needed.md:49-52`) |
| `PG-BACKUP` | Control DB restore, per-deployment volume restore, private/user backup restore, disaster drill | staging restore of control DB plus at least one ArcPod state stack (`docs/arclink/backup-restore.md:72-77`) |
| `PG-UPGRADE` | Live shared-host, Docker, Control Node, and component-pin upgrades | release-state proof from the relevant deploy/upgrade command family |
| `PG-SHARED-HOST` | Shared Host fresh install, Curator/enrollment rails, health, and cleanup | `./test.sh` or `sudo bin/ci-install-smoke.sh` on a supported Linux/systemd host with redacted evidence |

## Policy Questions

- Provider self-service: remain operator-managed/secure-handoff, or allow users
  to connect providers in dashboard?
- Provider account lane: official OAuth/account/funding path, no silent account
  creation, no challenge-bypass tooling.
- Provider threshold continuation: when budget is warning/exhausted, should
  ArcLink auto-refuel prompt only, fail closed only, model downgrade, or operator
  fallback?
- Captain migration: operator-only forever, request-and-approve, or
  self-service with guardrails?
- Browser share broker/adapter: native ArcLink broker or approved Nextcloud-backed
  adapter?
- Backup automation: how much of per-pod backup key setup should be user-facing
  versus operator-only?
- Destructive teardown: define who may request volume deletion and what
  confirmation/evidence is required.
- Discord Curator operator actions: accept configured operator-channel
  membership as the approval factor, or add a second factor/role allowlist/nonce
  before approving onboarding, SSOT writes, retries, and upgrade actions.
- Operator Raven scope: should chat-native operator control be allowed to queue
  every admin action, or only a curated subset that excludes destructive and
  credential-sensitive operations?
- Worker readiness: should Control Node install hard-fail when no worker is
  verified, or finish as a non-provisioning control plane with a prominent
  blocked status?
- Provider fallback: should router fallback be globally configured per product,
  per plan, per Captain, or per operator incident override?
- Rolling updates: what maximum batch size, health gate, and rollback threshold
  should govern ArcPod/Hermes updates at scale?
- Academy source governance: which source lanes are enabled by default, what
  raw material may be archived, how Reddit/user-generated deletion requests are
  enforced, which video transcript paths are authorized, and when derived
  lesson cards may survive after raw source removal?

## Test Plan

Focused local checks for code-owned gaps:

- GAP-008 is already closed locally; keep
  `tests/test_arclink_hosted_api.py` assertions for dynamic and static
  OpenAPI proof-token requirements in place.
- GAP-009 is locally closed for the long-lived browser persistence bug; keep
  the web static and Playwright storage/cleanup tests in place, and treat
  HttpOnly server-bound proof handoff or cross-tab recovery as a future
  product/security design if needed.
- GAP-010 is locally closed: keep the static web smoke and mocked Playwright
  tests proving `?channel=telegram|discord` remains web-scoped until a real
  platform identity is linked.
- GAP-011 is locally closed; keep the documentation truth check that rejects
  stale prototype phrases. GAP-012 is locally closed; keep the
  product-matrix truth checks that verify row totals, status labels,
  source/proof anchors for `real` rows, and live/policy boundary language for
  gated rows.
- GAP-013: pending backup status and staged public-key request now have
  Raven/dashboard/API/web tests; next local work is the GitHub
  write-verification/activation rail, while restore proof remains `PG-BACKUP`.
- GAP-014/GAP-015: dashboard/API share inbox coverage now exists for
  pending-owner-no-channel, recipient waits, scoped owner/recipient actions,
  retry-notification queueing after public channel repair, and a fail-closed
  authenticated Drive/Code `Request Share` browser contract backed by the local
  hosted broker route and deployment-scoped token hash. Next work is production
  workspace/browser proof and live bot delivery proof under `PG-BOTS`.
- GAP-016 is locally closed; keep the MCP response, managed-context recipe, and
  Drive/Code Linked-root plugin assertions in the focused plugin/MCP cluster.
- GAP-018: keep the source-owned admin action readiness matrix in sync when
  actions move from pending to worker-backed, and add authorized live proof for
  each smallest safe side-effect class before claiming production mutation.
- GAP-019: keep the Docker authority inventory/static assertion in place so any
  new Docker socket mount, explicit root service, changed writer boundary, or
  Linux capability boundary, or broker/no-go decision must update the
  trusted-boundary inventory and runbook entry; next work is stronger
  broker/root-helper isolation or an explicit operator residual-risk decision
  plus incident response integration.
- GAP-020: local restore-smoke coverage now exists for shared and agent-home
  backup artifacts; live staging restore proof remains `PG-BACKUP`.
- GAP-021: add no-secret fleet provider lifecycle harnesses; live variants stay
  skipped unless proof env gates are set.
- GAP-025 is locally closed; rerun the broad no-secret Python suite after future
  source/test slices and reopen or split a new gap on regression.
- GAP-026 is live-proof gated; keep local deploy, component-pin, and upgrade
  notification regressions green, but do not close it without authorized
  release-state, health, and smoke evidence from the relevant upgrade path.
- GAP-027 needs a policy decision first; then add either Discord channel-policy
  regression coverage or second-factor/allowlist/nonce tests for the chosen
  Curator operator-action model.
- GAP-028 is host-proof gated; keep deploy, health, systemd, and enrollment
  regressions green, but do not close it without a current authorized
  `./test.sh` or `bin/ci-install-smoke.sh` run on a supported host.
- GAP-029: keep the first Operator Raven schema/adapter tests in
  `tests/test_arclink_operator_raven.py`, and add focused tests before
  widening chat mutation. Preserve role scoping, no-secret output,
  replay/confirmation policy, and action-worker/broker routing in both
  Telegram and Discord tests.
- GAP-030: add Control Node install/readiness tests for no-worker,
  pending-SSH, local-worker, and remote-worker paths so "control plane up" and
  "ready to provision" cannot be confused.
- GAP-031: add mocked router provider-overload tests for bounded fallback
  retries, usage metadata, no raw prompt/completion storage, and response
  metadata that truthfully labels fallback use.
- GAP-032: add rolling-update planner tests before executor work: candidate
  pod selection, batch limits, preflight failures, stop-on-failure, per-pod
  health/smoke summaries, and rollback/repair output.
- GAP-033: add representative message/copy fixtures for Captain Raven,
  Operator Raven, web dashboard, Drive/Code/Terminal states, CLI/TUI summaries,
  and platform markdown rendering expectations.
- GAP-034: add fake-source Academy fixtures before any live crawling. Start
  with schema/manifest tests for source lanes, archive/tombstone policy,
  quality scoring, curriculum/lesson-card output, SOUL overlay application,
  vault/qmd/memory/skill staging, continuing education refresh, and evaluation
  gates. Do not run live YouTube/Reddit/GitHub/scholar/web searches in CI.

Live proof checks must not run by default in CI and must skip cleanly without
credentials.
