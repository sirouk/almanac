# Build Completion Notes

## 2026-05-27 GAP-029-A Operator Raven Minimal Console

Gap slice: reduce `GAP-029` with the smallest safe Operator Raven vertical
slice. This is not full-service chat-native operation; it is a local
read-only/dry-run command layer that keeps mutation, live proof, and policy
gates visible.

Files changed:

- `python/arclink_operator_raven.py`: added the shared Operator Raven parser
  and dispatch layer for `status`, `fleet list`, `worker probe --dry-run`,
  `user lookup`, `pod repair --dry-run`, and injected `upgrade check`.
- `python/arclink_curator_onboarding.py`: registered and routed the Telegram
  operator commands through the shared layer while preserving the existing
  operator-channel and approval-code boundaries.
- `python/arclink_curator_discord_onboarding.py`: registered and routed
  Discord operator slash/text commands through the shared layer while keeping
  the existing operator-channel gate and leaving `GAP-027` open.
- `tests/test_arclink_operator_raven.py`: added focused coverage for command
  parsing, secret-free output, read-only/dry-run behavior, no action queueing,
  injected upgrade checks, and Telegram/Discord authorization boundaries.
- `GAPS.md`, `research/COVERAGE_MATRIX.md`, and `IMPLEMENTATION_PLAN.md`:
  recorded the local slice without closing `GAP-029` or any live/policy gate.
- `mission_status.md` and `research/BUILD_COMPLETION_NOTES.md`: recorded this
  build slice and validation.

Commands run:

- `python3 tests/test_arclink_operator_raven.py` passed: 5 tests.
- `python3 -m py_compile python/arclink_operator_raven.py python/arclink_curator_onboarding.py python/arclink_curator_discord_onboarding.py` passed.
- `python3 tests/test_arclink_curator_onboarding_regressions.py` passed: 10 tests.
- `python3 tests/test_arclink_enrollment_provisioner_regressions.py` passed: 26 tests.
- `python3 tests/test_arclink_admin_actions.py` passed: 8 tests.
- `python3 tests/test_arclink_fleet.py` passed: 18 tests.
- `python3 tests/test_arclink_upgrade_notifications.py` passed: 9 tests.
- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1312 passed, 6 skipped, 89 warnings.

Remaining: `GAP-029` still needs broader audited Operator Raven actions,
confirmation policy, runbook coverage, live bot proof where applicable, and
the `GAP-027` Discord authority decision before broad chat mutation can ship.
The next local slice is `GAP-030` readiness surfacing unless the operator
chooses to continue widening Operator Raven read-only coverage first.

No live proof, Docker lifecycle, deploy/install/upgrade, systemd, credentialed
service, private-state read, or host mutation was run.

## 2026-05-27 README And Deploy Mode Trace Repair

Gap slice: make the three deployment paths legible from the README opening and
from the first interactive `deploy.sh` choices.

Files changed:

- `README.md`: added an Introduction, Lore Intro, front-loaded Deployment Paths
  breakdown, install trace for all three modes, and day-two management command
  split. The order now starts with Sovereign Control Node, then Shared Host,
  then Shared Host Docker.
- `bin/deploy.sh`: clarified the top-level mode chooser and gave Sovereign
  Control Node and Shared Host Docker submenus the same Back/Exit behavior as
  Shared Host.
- `tests/test_deploy_regressions.py`: added regression assertions for the
  clearer mode split and submenu return behavior.
- `mission_status.md`: recorded the follow-up.

Commands run:

- `python3 tests/test_deploy_regressions.py` passed: 115 tests.
- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_arclink_docker.py` passed: 56 tests.
- `bash -n deploy.sh bin/deploy.sh` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.

No live proof, Docker lifecycle, deploy/install/upgrade, systemd, credentialed
service, private-state read, or host mutation was run.

## 2026-05-27 Deployment Mode Viability Audit

Gap slice: source-grounded audit of whether ArcLink still supports deployment
modes beyond Sovereign Control Node.

Findings:

- Sovereign Control Node, Shared Host, and Shared Host Docker are all
  first-class command families in `bin/deploy.sh` and are documented as
  separate product/operations paths.
- Shared Host Mode remains maintained by direct install/upgrade/health code,
  systemd-service installers, Curator bootstrap, enrolled-agent realignment,
  deploy/health/user-service regression tests, and the host-mutating
  `test.sh` / `bin/ci-install-smoke.sh` smoke path.
- Shared Host Docker Mode remains maintained by its Docker install/upgrade
  wrapper, `agent-supervisor`, Docker health/live-smoke, and the large Docker
  regression suite.
- The actual gap was not code viability; it was missing explicit ownership for
  current Shared Host fresh-install/enrollment smoke proof.

Files changed:

- `GAPS.md`: added `GAP-028` and `PG-SHARED-HOST`.
- `USER_JOURNEY.md`: added the maintained-but-host-proof-gated Shared Host
  install callout.
- `research/COVERAGE_MATRIX.md`: linked `GAP-028` to `J-15`, `J-18`, and
  `J-27`.
- `docs/arclink/local-validation.md`: named the host-mutating Shared Host smoke
  command as `PG-SHARED-HOST` proof.
- `IMPLEMENTATION_PLAN.md`: added the `GAP-028` host-smoke handoff.
- `mission_status.md` and `research/BUILD_COMPLETION_NOTES.md`: recorded this
  audit.

Commands run:

- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- Gap/proof cross-reference check passed: `PG-SHARED-HOST` now has `GAP-028`
  as its owning row, and every `GAP-028` journey joint is represented in the
  coverage matrix.
- `python3 tests/test_deploy_regressions.py` passed: 115 tests.
- `python3 tests/test_health_regressions.py` passed: 20 tests.
- `python3 tests/test_arclink_docker.py` passed: 56 tests.
- `git diff --check` passed.

No live proof, Docker lifecycle, deploy/install/upgrade, systemd, credentialed
service, private-state read, or host mutation was run.

## 2026-05-27 Journey And Gap Atlas Consistency Repair

Gap slice: source-grounded document repair for the ArcLink journey/gap atlas.
The current `USER_JOURNEY.md`, `GAPS.md`, coverage matrix, and Ralphie steering
paths were checked for whether the system story needed a full restart. The
atlas is coherent enough to avoid re-running the full Ralphie journey audit,
but two explicit handoffs were missing.

Files changed:

- `GAPS.md`: added `GAP-026` as the owning row for `PG-UPGRADE`, and
  `GAP-027` for the Discord Curator operator-action authority policy.
- `USER_JOURNEY.md`: added the live upgrade proof and Curator
  operator-authority callouts.
- `research/COVERAGE_MATRIX.md`: linked the new gap rows to the owning journey
  joints.
- `docs/arclink/operations-runbook.md`: named the current Discord
  operator-channel authority boundary.
- `IMPLEMENTATION_PLAN.md` and `mission_status.md`: refreshed the active
  handoff so the new rows route to live proof and policy decision, not
  speculative local repair.
- `research/BUILD_COMPLETION_NOTES.md`: added this note.

Commands run:

- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- Gap/proof cross-reference check passed: `PG-UPGRADE` now has `GAP-026` as
  its owning row, and `GAP-026`/`GAP-027` are referenced by the journey,
  coverage matrix, plan, and mission status.
- `git diff --check` passed.

Remaining gates: `GAP-026` needs authorized `PG-UPGRADE` evidence, `GAP-027`
needs an operator/security policy decision, and the prior live-proof,
policy-decision, and residual-risk rows remain open. No live proof, Docker
lifecycle, deploy/install/upgrade, systemd, credentialed service, private-state
read, or host mutation was run.

## 2026-05-26 Plan Refresh Required-Read Recheck

Gap slice: plan refresh for the current Ralphie buildout prompt. The required
planning inputs were re-read, `GAP-025` was checked first with the broad
no-secret Python suite, and the current unattended `LOCAL` queue remains empty.

Files changed:

- `IMPLEMENTATION_PLAN.md`: refreshed the active plan status, current
  broad-suite result, completed planning checklist item, and remaining external
  handoffs.
- `mission_status.md`: added this current handoff status.
- `research/BUILD_COMPLETION_NOTES.md`: added this note.

Commands run:

- `python3 -m pytest -q tests` passed: 1305 passed, 6 skipped, 81 warnings in
  64.03s.
- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'docker_authority_inventory_matches_compose_boundary or docker_docs_cover_socket' --maxfail=5`
  passed: 2 passed, 62 deselected.
- `git diff --check` passed.

Remaining gates are unchanged: authorized live proof remains for `GAP-001`,
`GAP-002`, `GAP-003`, `GAP-004`, `GAP-005`, `GAP-007`, `GAP-013`,
`GAP-015`, `GAP-018`, `GAP-020`, `GAP-021`, `GAP-022`, and `GAP-023`;
operator/product policy decisions remain for `GAP-006`, `GAP-014`, `GAP-017`,
and `GAP-024`; `GAP-019` remains a trusted-host residual-risk gate until
accepted, redesigned, or connected to authorized live alerting. No live proof,
Docker lifecycle, deploy/install/upgrade, systemd, credentialed service,
private-state read, or host mutation was run.

## 2026-05-26 Document Phase Source Truth Handoff After Lint Repair

Gap slice: document-phase handoff after the lint repair. The current
unattended `LOCAL` queue is empty; the repaired local blocker was the
`agent-process-helper` rejection-incident root selection bug already recorded
under `GAP-025` validation evidence, not a new live-proof closure.

Files changed:

- `IMPLEMENTATION_PLAN.md`: refreshed the current repair status, broad-suite
  result, completed handoff checklist item, and external gate routing.
- `mission_status.md`: added the current document-phase closeout.
- `research/BUILD_COMPLETION_NOTES.md`: added this note.
- `GAPS.md`: inspected and left unchanged for this document phase because no
  gap row's source/test/proof status changed after the already-recorded lint
  repair evidence.
- `USER_JOURNEY.md`: inspected and left unchanged because the user journey did
  not change.

Commands run:

- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'docker_authority_inventory_matches_compose_boundary or docker_docs_cover_socket' --maxfail=5`
  passed: 2 passed, 62 deselected.
- `git diff --check` passed.

Remaining proof/policy/test gates: authorized live proof remains for
`GAP-001`, `GAP-002`, `GAP-003`, `GAP-004`, `GAP-005`, `GAP-007`,
`GAP-013`, `GAP-015`, `GAP-018`, `GAP-020`, `GAP-021`, `GAP-022`, and
`GAP-023`; operator/product decisions remain for `GAP-006`, `GAP-014`,
`GAP-017`, and `GAP-024`; `GAP-019` remains a trusted-host residual-risk gate
until accepted, redesigned, or connected to authorized live alerting. No live
proof, Docker lifecycle, deploy/install/upgrade, systemd, credentialed
service, private-state read, or host mutation was run.

## 2026-05-26 Lint Phase Adversarial Buildout Review

Gap slice: adversarial local lint/review for the current Ralphie buildout
handoff. The pass found one unattended local blocker before advancement: the
broad no-secret Python suite failed because `agent-process-helper` rejected a
symlinked Docker agent home root but skipped the expected redacted rejection
incident when only `ARCLINK_PRIV_DIR` was configured.

Changed:

- `python/arclink_rejection_incidents.py`: `private_state_rejection_path()` now
  accepts whichever configured private-state root is present, while still
  rejecting unsafe roots and disagreement when multiple roots are configured.
- `research/STACK_SNAPSHOT.md`: corrected the generated stack snapshot back to
  ArcLink's actual Python control plane, shell orchestration, and Docker
  Compose shape instead of a Node-first misclassification.
- `mission_status.md` and `research/BUILD_COMPLETION_NOTES.md`: recorded this
  lint-phase blocker and repair.

Validation:

- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_helpers_reject_symlinked_home_root_before_root_work --maxfail=1`
  passed: 1 passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_helpers_reject_symlinked_home_root_before_root_work or agent_process_helper_records_redacted_rejection_incident_before_subprocess or agent_process_helper_rejects_configured_root_mismatch' --maxfail=5`
  passed: 3 passed, 61 deselected.
- `python3 -m py_compile python/arclink_rejection_incidents.py python/arclink_agent_process_helper.py` passed.
- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 -m compileall -q python plugins/hermes-agent/arclink-managed-context plugins/hermes-agent/code/dashboard plugins/hermes-agent/drive/dashboard` passed.
- `npm test`, `npm run lint`, and `npm run build` passed in `web/`.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1305 passed, 6 skipped, and
  81 warnings in 64.08s.

Remaining gates: authorized live proof remains for `GAP-001`, `GAP-002`,
`GAP-003`, `GAP-004`, `GAP-005`, `GAP-007`, `GAP-013`, `GAP-015`,
`GAP-018`, `GAP-020`, `GAP-021`, `GAP-022`, and `GAP-023`; policy decisions
remain for `GAP-006`, `GAP-014`, `GAP-017`, and `GAP-024`; `GAP-019` remains
a trusted-host residual-risk gate until accepted, redesigned, or connected to
authorized live alerting. No live proof, Docker lifecycle,
deploy/install/upgrade, systemd, credentialed service, private-state read, or
host mutation was run.

## 2026-05-26 Plan Phase Build-Gate Repair

Gap slice: planning-contract repair for the Ralphie plan phase. The previous
plan route was substantively correct but lacked the explicit section names the
machine gate requires.

Changed:

- `IMPLEMENTATION_PLAN.md`: added explicit `Goal` and
  `Acceptance Criteria/Validation` sections, retained the current
  `LOCAL`/`LIVE_PROOF`/`POLICY_DECISION`/`RESIDUAL_RISK_ACCEPTANCE` queue, and
  kept the bounded first slice as documentation/handoff because there is no
  current unattended local repair row.
- `mission_status.md`: added the current build-gate repair status.
- `research/BUILD_COMPLETION_NOTES.md`: added this note.

Validation:

- `python3 -m pytest -q tests` passed: 1305 passed, 6 skipped, and
  81 warnings in 64.67s.
- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'docker_authority_inventory_matches_compose_boundary or docker_docs_cover_socket' --maxfail=5`
  passed: 2 passed, 62 deselected.
- `git diff --check` passed.

Remaining gates: authorized live proof remains for `GAP-001`, `GAP-002`,
`GAP-003`, `GAP-004`, `GAP-005`, `GAP-007`, `GAP-013`, `GAP-015`,
`GAP-018`, `GAP-020`, `GAP-021`, `GAP-022`, and `GAP-023`; policy decisions
remain for `GAP-006`, `GAP-014`, `GAP-017`, and `GAP-024`; `GAP-019` remains
a trusted-host residual-risk gate until accepted, redesigned, or connected to
authorized live alerting. No live proof, Docker lifecycle,
deploy/install/upgrade, systemd, credentialed service, private-state read, or
host mutation was run.

## 2026-05-26 Document Phase Retry 2 Closeout

Gap slice: external-gate and residual-risk handoff refresh for an empty
unattended `LOCAL` queue. This closeout does not claim live proof or close
`GAP-019`; it leaves Ralphie resumable for the next authorized proof, policy,
or residual-risk window.

Files changed:

- `IMPLEMENTATION_PLAN.md`: marked the document-phase closeout tasks complete
  and named the remaining external handoffs.
- `mission_status.md`: recorded the current repair status and closeout
  validation.
- `research/BUILD_COMPLETION_NOTES.md`: added this note.
- `GAPS.md`: inspected and left unchanged in this closeout because no source,
  test, or proof status changed after the existing `GAP-019` reroute.
- `USER_JOURNEY.md`: inspected and left unchanged because the user journey did
  not change.

Commands run:

- `python3 tests/test_documentation_truths.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'docker_authority_inventory_matches_compose_boundary or docker_docs_cover_socket' --maxfail=5`
  passed: 2 passed, 62 deselected.
- `git diff --check` passed.

Remaining gates: authorized live proof remains for `GAP-001`, `GAP-002`,
`GAP-003`, `GAP-004`, `GAP-005`, `GAP-007`, `GAP-013`, `GAP-015`, `GAP-018`,
`GAP-020`, `GAP-021`, `GAP-022`, and `GAP-023`; operator/product policy
decisions remain for `GAP-006`, `GAP-014`, `GAP-017`, and `GAP-024`;
`GAP-019` remains a trusted-host residual-risk gate until accepted, redesigned,
or connected to authorized live alerting. `GAP-025` remains locally closed
while the broad no-secret Python suite stays green. No live proof, Docker
lifecycle, deploy/install/upgrade, systemd, credentialed service,
private-state read, or host mutation was run.

## 2026-05-26 Plan Retry 2 Empty Local Queue Confirmation

Scope: refreshed the plan routing after the previous post-plan validators
reported GO/no-gap reviews but still required document handoff routing. The
current `GAPS.md` queue remains empty for unattended `LOCAL` work; all non-real
rows are live proof, operator/product policy, or `GAP-019` residual-risk
handoffs.

Changed:

- `IMPLEMENTATION_PLAN.md`: added the retry 2 routing note and concrete next
  phase as `document`, with no speculative code repair or live proof.
- `mission_status.md`: recorded the empty-local-queue route for this retry.
- `research/BUILD_COMPLETION_NOTES.md`: recorded this plan refresh.

Validation run:

- `python3 -m pytest -q tests` passed: 1305 passed, 6 skipped, 81 warnings
  in 64.30s.
- `python3 tests/test_documentation_truths.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'docker_authority_inventory_matches_compose_boundary or docker_docs_cover_socket' --maxfail=5`
  passed: 2 passed, 62 deselected in 0.05s.
- `git diff --check` passed.

Remaining gates are unchanged: live proof for `GAP-001`, `GAP-002`,
`GAP-003`, `GAP-004`, `GAP-005`, `GAP-007`, `GAP-013`, `GAP-015`, `GAP-018`,
`GAP-020`, `GAP-021`, `GAP-022`, and `GAP-023`; policy decisions for
`GAP-006`, `GAP-014`, `GAP-017`, and `GAP-024`; and `GAP-019`
residual-risk acceptance, stronger isolation design, or authorized live alert
integration.

## 2026-05-26 External Gate And GAP-019 Residual-Risk Handoff

Gap slice: document-phase handoff for the empty unattended `LOCAL` queue,
with `GAP-019` routed to residual-risk acceptance, stronger isolation design,
or authorized live alert integration.

Files changed:

- `GAPS.md`: updated only `GAP-019` next-repair wording to match the current
  source inventory.
- `IMPLEMENTATION_PLAN.md`: completed the document-phase checklist and kept the
  live-proof, policy, and residual-risk buckets explicit.
- `mission_status.md`: added the current handoff status.
- `research/BUILD_COMPLETION_NOTES.md`: recorded this completion note.

Commands run:

- `python3 -m pytest -q tests` passed: 1305 passed, 6 skipped, 81 warnings
  in 63.85s.
- `python3 tests/test_documentation_truths.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'docker_authority_inventory_matches_compose_boundary or docker_docs_cover_socket' --maxfail=5`
  passed: 2 passed, 62 deselected in 0.05s.
- `git diff --check` passed.

Remaining gates: authorized live proof remains for `GAP-001`, `GAP-002`,
`GAP-003`, `GAP-004`, `GAP-005`, `GAP-007`, `GAP-013`, `GAP-015`, `GAP-018`,
`GAP-020`, `GAP-021`, `GAP-022`, and `GAP-023`; operator/product policy
decisions remain for `GAP-006`, `GAP-014`, `GAP-017`, and `GAP-024`;
`GAP-019` remains a trusted-host residual-risk gate until accepted, redesigned,
or connected to authorized live alerting. No live proof, Docker lifecycle,
deploy/install/upgrade, systemd, credentialed service, private-state read, or
host mutation was run.

## 2026-05-23 GAP-019-BD Remaining Broker/Helper Rejection Incidents

Scope: reduced the `GAP-019` Docker/root trusted-host boundary locally by
adding redacted rejected-request incident evidence to the remaining
high-authority lanes: `deployment-exec-broker`,
`migration-capture-helper`, `agent-user-helper`,
`agent-supervisor-broker`, and `operator-upgrade-broker`. Rejected validation
failures now append one JSONL row only under scoped safe roots or the
dashboard broker's narrow incident mount. Rows include service/event,
trusted-host acknowledgement state, error class, sanitized reason/message, and
safe identifiers when available; they omit raw request bodies, command arrays,
process args, payload values, private paths, tokens, chat ids, user ids,
message text, secret-looking values, and stack traces.

Changed:

- `python/arclink_rejection_incidents.py`: added the shared safe-path and
  no-follow JSONL incident writer.
- `python/arclink_deployment_exec_broker.py`,
  `python/arclink_migration_capture_helper.py`,
  `python/arclink_agent_user_helper.py`,
  `python/arclink_agent_supervisor_broker.py`, and
  `python/arclink_operator_upgrade_broker.py`: record redacted incidents on
  rejected requests without changing accepted request behavior.
- `compose.yaml`: added a narrow dashboard-broker incident mount only for
  `state/docker/agent-supervisor-broker`.
- `tests/test_arclink_docker.py`: added the cross-lane rejection incident
  regression and updated authority/docs expectations.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/data-safety.md`, `docs/arclink/operations-runbook.md`,
  `GAPS.md`, `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: recorded
  `GAP-019-BD` as interim hardening, not closure of `GAP-019`.

Validation so far:

- `python3 -m py_compile python/arclink_rejection_incidents.py python/arclink_deployment_exec_broker.py python/arclink_migration_capture_helper.py python/arclink_agent_user_helper.py python/arclink_agent_supervisor_broker.py python/arclink_operator_upgrade_broker.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k remaining_high_authority_services_record_redacted_rejection_incidents --maxfail=1`
  passed: 1 passed.
- `python3 -m json.tool config/docker-authority-inventory.json` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'remaining_high_authority_services_record_redacted_rejection_incidents or docker_authority_inventory_matches_compose_boundary' --maxfail=2`
  passed: 2 passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'remaining_high_authority_services_record_redacted_rejection_incidents or deployment_exec_broker or migration_capture_helper or agent_user_helper or agent_supervisor_broker or operator_upgrade_broker or docker_authority_inventory or docker_docs_cover_socket or compose_defines_full_stack_services' --maxfail=10`
  passed: 23 passed.
- `python3 -m pytest -q tests/test_arclink_executor.py -k deployment_exec_broker --maxfail=5`
  passed: 3 passed.
- `python3 -m pytest -q tests/test_arclink_pod_migration.py -k migration_capture_helper --maxfail=5`
  passed: 2 passed.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20`
  passed: 64 passed.
- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1305 passed, 6 skipped, 81 warnings
  in 64.22s.

No Docker lifecycle/mutation, deploy/install/upgrade, systemd, live service,
credentialed, private-state, or host-mutating command was run.

## 2026-05-23 GAP-019-BC Gateway Exec Broker Rejection Incidents

Scope: reduced the `GAP-019` Docker/root trusted-host boundary locally by
making `gateway-exec-broker` record redacted rejected-request incidents under
the configured deployment state root. Unsafe raw-command, project-name
mismatch, unsupported-platform, and trusted-host acknowledgement rejections now
append one JSONL row to
`ARCLINK_STATE_ROOT_BASE/_broker-incidents/gateway-exec-broker/rejections.jsonl`
when that state root is absolute, non-root, existing, and non-symlinked. Rows
contain safe metadata and sanitized reason codes, not raw request bodies,
bridge payload values, bot tokens, chat ids, user ids, message text, process
args, rendered config paths, private paths, or stack traces. This is local
incident evidence only and does not close the gateway broker residual-risk
decision.

Changed:

- `python/arclink_gateway_exec_broker.py`: added deployment-state-root-confined
  rejection incident recording around broker validation failure paths.
- `tests/test_arclink_notification_delivery.py`: added the failing
  redaction/incident regression and wired it into the script-style runner.
- `config/docker-authority-inventory.json` and `tests/test_arclink_docker.py`:
  recorded `GAP-019-BC` summary/service controls while keeping `GAP-019` open.
- `docs/docker.md`, `docs/arclink/data-safety.md`,
  `docs/arclink/operations-runbook.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: recorded the local
  hardening without claiming live alerting, Docker runtime proof, public bot
  delivery, or `GAP-019` closure.

Pre-repair reproduction:

- A temp-only local probe submitted an unsafe raw `cmd` request with a
  configured deployment state root. Before the repair the broker returned
  `gateway exec broker does not accept raw commands` and no
  `_broker-incidents/gateway-exec-broker/rejections.jsonl` file existed.
- After adding the regression,
  `python3 -m pytest -q tests/test_arclink_notification_delivery.py -k 'gateway_exec_broker_records_redacted_rejection_incident_before_subprocess' --maxfail=1`
  failed before repair because rejected gateway broker requests did not create
  a deployment-state incident log.

Validation:

- `python3 -m pytest -q tests/test_arclink_notification_delivery.py -k 'gateway_exec_broker_records_redacted_rejection_incident_before_subprocess' --maxfail=1`
  passed: 1 passed.
- `python3 -m pytest -q tests/test_arclink_notification_delivery.py -k 'gateway_exec_broker_records_redacted_rejection_incident_before_subprocess or gateway_exec_broker_rejects_raw_commands_and_builds_vetted_exec or gateway_exec_broker_rejects_symlinked_compose_fallback_config_before_docker or public_agent_bridge_command_validator or public_agent_gateway_turn_uses_gateway_exec_broker_when_configured or public_agent_bridge_worker_uses_gateway_exec_broker_request_jobs' --maxfail=10`
  passed: 6 passed.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null` and
  `python3 -m pytest -q tests/test_arclink_docker.py -k 'gateway_exec_broker or docker_authority_inventory or docker_docs_cover_socket' --maxfail=10`
  passed: 4 passed.
- `python3 -m py_compile python/arclink_gateway_exec_broker.py python/arclink_notification_delivery.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_notification_delivery.py tests/test_arclink_public_bots.py tests/test_arclink_telegram.py tests/test_arclink_discord.py tests/test_arclink_docker.py --maxfail=20`
  passed: 147 passed.
- `python3 tests/test_documentation_truths.py`, `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1304 passed, 6 skipped, 81 warnings in
  63.51s.

Residual risk:

- `GAP-019` remains open. `gateway-exec-broker` still intentionally carries
  writeable Docker socket authority for allowlisted public Agent Hermes gateway
  exec; remaining closure requires stronger broker isolation, live alert
  integration, or an operator residual-risk decision.

## 2026-05-23 GAP-019-BB Agent Process Helper Rejection Incidents

Scope: reduced the `GAP-019` Docker/root trusted-host boundary locally by
making `agent-process-helper` record redacted rejected-request incidents under
configured private state. Unsafe raw-command, unapproved env, and unsafe
dashboard-host requests now append one JSONL row to
`state/docker/agent-process-helper/rejections.jsonl` when the configured
private root is safe. Rows contain safe metadata and sanitized reason codes,
not raw request bodies, env values, process args, private paths, tokens, or
stack traces. This is local incident evidence only and does not close the root
process-helper residual-risk decision.

Changed:

- `python/arclink_agent_process_helper.py`: added private-root-confined
  rejection incident recording around helper failure paths.
- `tests/test_arclink_docker.py`: added the failing redaction/incident
  regression and updated existing helper rejection tests to distinguish
  `rejections.jsonl` from normal process logs.
- `config/docker-authority-inventory.json`: recorded `GAP-019-BB` summary and
  service controls while keeping `GAP-019` open.
- `docs/docker.md`, `docs/arclink/data-safety.md`,
  `docs/arclink/operations-runbook.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: recorded the local
  hardening without claiming live alerting, Docker runtime proof, or
  `GAP-019` closure.

Pre-repair reproduction:

- A temp-only local probe submitted an unsafe raw `cmd` request with a
  configured private state root. Before the repair the helper returned
  `agent process helper does not accept raw commands` and no
  `rejections.jsonl` file existed.
- After adding the regression,
  `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper_records_redacted_rejection_incident_before_subprocess' --maxfail=1`
  failed before repair because rejected helper requests did not create a
  private-state incident log.

Validation:

- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper_records_redacted_rejection_incident_before_subprocess' --maxfail=1`
  passed: 1 passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper_records_redacted_rejection_incident_before_subprocess or agent_process_helper_rejects_raw_commands_and_runs_allowlisted_agent_ops or agent_process_helper_rejects_unapproved_agent_env_keys_before_subprocess or agent_process_helper_rejects_unsafe_dashboard_backend_host_before_subprocess or agent_process_helper_rejects_configured_root_mismatch or agent_process_helper_rejects_symlinked_configured_roots_before_work or agent_process_helper_rejects_symlink_escaped_log_directory or agent_process_helper_does_not_log_or_argv_env_values or docker_authority_inventory or docker_docs_cover_socket' --maxfail=10`
  passed: 10 passed.
- `python3 -m py_compile python/arclink_agent_process_helper.py python/arclink_docker_agent_supervisor.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py tests/test_arclink_agent_user_services.py --maxfail=20`
  passed: 93 passed.
- `python3 tests/test_documentation_truths.py`, `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1303 passed, 6 skipped, 81 warnings in
  63.59s.

Residual risk:

- `GAP-019` remains open. `agent-process-helper` still intentionally carries
  bounded root authority for allowlisted Docker agent process execution;
  remaining closure requires stronger helper/broker isolation, live alert
  integration, or an operator residual-risk decision.

## 2026-05-23 GAP-019-BA Agent User Helper Assignment-File Preflight

Scope: reduced the `GAP-019` Docker/root trusted-host boundary locally by
making `agent-user-helper` treat its uid/gid assignment JSON and temp-file paths
as untrusted filesystem objects. Symlinked, directory, or non-regular
`.arclink-user-ids.json` and `.arclink-user-ids.json.tmp` paths now fail before
assignment writes, account commands, agent-home directory creation, or
recursive chown. This is local hardening only and does not close the root helper
residual-risk decision.

Changed:

- `python/arclink_agent_user_helper.py`: added canonical assignment-file and
  temp-file preflight plus exclusive no-follow temp-file creation before
  `os.replace`.
- `tests/test_arclink_docker.py`: added the failing assignment-file
  symlink/directory regression, preserved valid helper behavior, and updated
  Docker authority inventory/docs guards.
- `config/docker-authority-inventory.json`: recorded `GAP-019-BA` as
  assignment-file preflight while keeping `GAP-019` open.
- `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, `mission_status.md`,
  `docs/docker.md`, `docs/arclink/data-safety.md`, and
  `docs/arclink/operations-runbook.md`: recorded the local hardening without
  claiming live proof or `GAP-019` closure.

Pre-repair reproduction:

- A temp-only local probe showed a pre-existing `.arclink-user-ids.json.tmp`
  symlink was followed, the outside target was modified, the agent home was
  created, fake root commands ran, and the helper returned success.
- After adding the regression,
  `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_user_helper_rejects_symlinked_uid_assignment_files_before_root_work' --maxfail=1`
  failed before repair with `tmp-symlink` returning a success payload.

Validation:

- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_user_helper_rejects_symlinked_uid_assignment_files_before_root_work' --maxfail=1`
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_user_helper_rejects_symlinked_uid_assignment_files_before_root_work or agent_user_helper_rejects_raw_commands_and_unscoped_paths or agent_user_helper_requires_trusted_absolute_root_executables or agent_user_helper_rejects_configured_home_root_mismatch or agent_helpers_reject_symlink_escaped_agent_paths or agent_helpers_reject_symlinked_home_root_before_root_work or agent_user_helper_root_boundary_uses_explicit_minimum_capabilities or docker_authority_inventory or docker_docs_cover_socket' --maxfail=10`
- `python3 -m py_compile python/arclink_agent_user_helper.py python/arclink_docker_agent_supervisor.py`
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py tests/test_arclink_agent_user_services.py --maxfail=20`
  passed: 92 passed.
- `python3 tests/test_documentation_truths.py`
- `python3 tests/test_public_repo_hygiene.py`
- `git diff --check`
- `python3 -m pytest -q tests` passed: 1302 passed, 6 skipped, 81 warnings in
  64.00s.

Residual risk:

- `GAP-019` remains open. `agent-user-helper` still intentionally carries
  bounded root authority for validated Docker agent-home setup; remaining
  closure requires stronger helper/broker isolation, live alert integration, or
  an operator residual-risk decision.

## 2026-05-23 GAP-019-AZ Agent Supervisor Broker Private Bind-Root Preflight

Scope: reduced the `GAP-019` Docker/root trusted-host boundary locally by
making `agent-supervisor-broker` treat the dashboard auth-proxy sidecar
host/container private bind roots as untrusted. Unsafe
`ARCLINK_DOCKER_HOST_PRIV_DIR` and `ARCLINK_DOCKER_CONTAINER_PRIV_DIR` values
now fail before proxy config hashing, Docker CLI lookup, Docker container
inspect, sidecar `docker run -v`, or a successful broker response. This is local
hardening only and does not close the dashboard broker residual-risk decision.

Changed:

- `python/arclink_agent_supervisor_broker.py`: added private bind-root
  preflight for the dashboard sidecar broker.
- `tests/test_arclink_docker.py`: added the failing unsafe private bind-root
  regression, preserved valid sidecar command coverage, updated the Docker
  authority inventory schema guard, and wired the script-style test runner.
- `config/docker-authority-inventory.json`: recorded `GAP-019-AZ` as
  dashboard sidecar private-bind-root preflight while keeping the broker's
  writeable Docker socket residual risk open.
- `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, `mission_status.md`,
  `docs/docker.md`, `docs/arclink/data-safety.md`, and
  `docs/arclink/operations-runbook.md`: recorded the local hardening without
  claiming `GAP-019` closure or live proof.

Pre-repair reproduction:

- The focused selector initially had no coverage: 60 deselected.
- After adding the regression, it failed against the old loose bind-root
  contract before source repair.

Validation:

- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_supervisor_broker_rejects_unsafe_private_bind_roots_before_dashboard_proxy' --maxfail=1`
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_supervisor_broker_rejects_unsafe_private_bind_roots or agent_supervisor_broker_rejects_raw_commands_and_builds_dashboard_proxy or agent_supervisor_broker_rejects_unsafe_dashboard_backend_host or agent_supervisor_broker_rejects_unsafe_docker_binary or docker_authority_inventory or docker_docs_cover_socket' --maxfail=10`
- `python3 -m py_compile python/arclink_agent_supervisor_broker.py python/arclink_docker_agent_supervisor.py`
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_dashboard.py tests/test_arclink_plugins.py --maxfail=20`
  passed: 107 passed.
- `python3 tests/test_documentation_truths.py`
- `python3 tests/test_public_repo_hygiene.py`
- `git diff --check`
- `python3 -m pytest -q tests` passed: 1301 passed, 6 skipped, 81 warnings in
  63.88s.

Residual risk:

- `GAP-019` remains open. The dashboard sidecar broker still intentionally
  carries the writeable Docker socket for allowlisted dashboard network/proxy
  sidecar work; remaining closure requires stronger helper/broker isolation,
  live alert integration, or an operator residual-risk decision.

## 2026-05-23 GAP-019-AY Gateway Exec Broker Fallback Config-File Preflight

Scope: reduced the `GAP-019` Docker/root trusted-host boundary locally by
making `gateway-exec-broker` treat public Agent Compose fallback config paths
as untrusted until the exact fallback deployment root, config directory, and
config files pass non-symlink, regular-file, and readability checks. This is
local hardening only and does not close the gateway broker residual-risk
decision.

Changed:

- `python/arclink_gateway_exec_broker.py`: added fallback config-file preflight
  before building or dispatching the `docker compose exec -T hermes-gateway`
  fallback command.
- `python/arclink_notification_delivery.py`: added shared deployment Compose
  config preflight and applied it to detached public Agent bridge validation,
  direct public Agent gateway fallback, and the quiet public Agent turn fallback.
- `tests/test_arclink_notification_delivery.py`: added the symlinked fallback
  regression, extended stored-command validation coverage, and preserved valid
  running-container plus valid fallback command behavior.
- `tests/test_arclink_docker.py` and `config/docker-authority-inventory.json`:
  recorded `GAP-019-AY` as gateway fallback rendered-config preflight while
  keeping the broker's writeable Docker socket residual risk open.
- `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, `mission_status.md`,
  `docs/docker.md`, `docs/arclink/data-safety.md`, and
  `docs/arclink/operations-runbook.md`: recorded the local hardening without
  claiming `GAP-019` closure or live proof.

Pre-repair reproduction:

- A focused local probe against `_build_gateway_exec_command` showed symlinked
  fallback `config/arclink.env` and `config/compose.yaml` under the deployment
  state root reached `docker compose exec` command construction and printed
  `UNSAFE_ALLOWED`.

Validation:

- `python3 -m pytest -q tests/test_arclink_notification_delivery.py -k 'gateway_exec_broker_rejects_symlinked_compose_fallback_config_before_docker' --maxfail=1`
- `python3 -m pytest -q tests/test_arclink_notification_delivery.py -k 'gateway_exec_broker or public_agent_bridge_command_validator' --maxfail=10`
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'gateway_exec_broker or docker_authority_inventory' --maxfail=10`
- `python3 -m py_compile python/arclink_gateway_exec_broker.py python/arclink_notification_delivery.py`
- `python3 -m pytest -q tests/test_arclink_notification_delivery.py tests/test_arclink_docker.py tests/test_arclink_public_bots.py tests/test_arclink_telegram.py tests/test_arclink_discord.py --maxfail=20`
  passed: 143 passed.
- `python3 tests/test_documentation_truths.py`
- `python3 tests/test_public_repo_hygiene.py`
- `git diff --check`
- `python3 -m pytest -q tests` passed: 1300 passed, 6 skipped, 81 warnings in
  63.86s.

Residual risk:

- `GAP-019` remains open. The gateway exec broker still intentionally carries
  the writeable Docker socket for allowlisted public Agent Hermes gateway exec;
  remaining closure requires stronger helper/broker isolation, live alert
  integration, or an operator residual-risk decision.

## 2026-05-23 GAP-019-AX Deployment Exec Broker Config-File Preflight

Scope: reduced the `GAP-019` Docker/root trusted-host boundary locally by
making `deployment-exec-broker` treat rendered deployment config paths as
untrusted until the exact request paths are proven to be non-symlink
directories/files. This is local hardening only and does not close the
deployment broker residual-risk decision.

Changed:

- `python/arclink_deployment_exec_broker.py`: added broker-local request path
  preflight for the rendered deployment root, config root, `config/arclink.env`,
  and `config/compose.yaml`. Symlinked roots, symlinked config files, missing
  files, non-regular files, and unreadable config files fail before Docker CLI
  lookup, `SubprocessDockerComposeRunner` construction, or Compose subprocess
  dispatch.
- `tests/test_arclink_executor.py`: added the failing symlinked rendered-config
  regression and wired it into the script-style test runner.
- `tests/test_arclink_docker.py` and `config/docker-authority-inventory.json`:
  recorded `GAP-019-AX` as config-file preflight hardening while keeping the
  broker's writeable Docker socket residual risk open.
- `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, `mission_status.md`,
  `docs/docker.md`, `docs/arclink/data-safety.md`, and
  `docs/arclink/operations-runbook.md`: recorded the local hardening without
  claiming `GAP-019` closure or live proof.

Pre-repair reproduction:

- The focused selector initially had no coverage: 39 deselected.
- After adding the regression, symlinked `dep-one/config/arclink.env` and
  `dep-one/config/compose.yaml` pointing at `dep-one-steered/config` reached
  Docker CLI lookup, failing with `Docker CLI lookup must not run for symlinked
  deployment config files`.

Validation:

- `python3 -m pytest -q tests/test_arclink_executor.py -k 'deployment_exec_broker_rejects_symlinked_compose_config_files_before_docker' --maxfail=1`
- `python3 -m pytest -q tests/test_arclink_executor.py -k 'deployment_exec_broker' --maxfail=10`
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'deployment_exec_broker or docker_authority_inventory' --maxfail=10`
- `python3 -m py_compile python/arclink_deployment_exec_broker.py python/arclink_executor.py`
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
- `python3 -m pytest -q tests/test_arclink_executor.py tests/test_arclink_docker.py tests/test_arclink_provisioning.py tests/test_arclink_sovereign_worker.py --maxfail=20`
  passed: 133 passed.
- `python3 tests/test_documentation_truths.py`
- `python3 tests/test_public_repo_hygiene.py`
- `git diff --check`
- `python3 -m pytest -q tests` passed: 1299 passed, 6 skipped, 81 warnings in
  63.66s.

Residual risk:

- `GAP-019` remains open. The deployment exec broker still intentionally
  carries the writeable Docker socket for allowlisted deployment Compose
  operations; remaining closure requires stronger helper/broker isolation, live
  alert integration, or an operator residual-risk decision.

## 2026-05-23 GAP-019-AW Operator Upgrade Broker Upstream Deploy-Key Path Confinement

Scope: reduced the `GAP-019` Docker/root trusted-host boundary locally by
making `operator-upgrade-broker` treat request-supplied upstream deploy-key
metadata as untrusted path data. This is local hardening only and does not close
the operator-upgrade broker residual-risk decision.

Changed:

- `python/arclink_operator_upgrade_broker.py`: added upstream path validation
  for non-empty `ARCLINK_UPSTREAM_DEPLOY_KEY_PATH` and
  `ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE` values. Relative, out-of-private-state,
  and symlink-steered paths now fail closed before child env construction,
  private operator logs, `_run_logged_command`, or `subprocess.run`.
- `tests/test_arclink_docker.py`: added the failing upstream deploy-key path
  regression, preserved valid private-state upstream path pass-through, and
  extended the authority inventory/docs guard for `GAP-019-AW`.
- `config/docker-authority-inventory.json`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, `mission_status.md`, `docs/docker.md`,
  `docs/arclink/data-safety.md`, and `docs/arclink/operations-runbook.md`:
  recorded `GAP-019-AW` as interim hardening while keeping `GAP-019` open.

Pre-repair reproduction:

- The focused selector initially had no coverage: 59 deselected.
- After adding the regression, a temp queued upgrade request with an outside
  `ARCLINK_UPSTREAM_DEPLOY_KEY_PATH` returned success and reached the mocked
  subprocess path, failing with
  `outside upstream deploy key: {'returncode': 0}`.

Validation:

- `python3 -m pytest -q tests/test_arclink_docker.py -k 'operator_upgrade_broker_rejects_unscoped_upstream_deploy_key_paths_before_log_or_subprocess' --maxfail=1`
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'operator_upgrade_broker and not live' --maxfail=10`
- `python3 -m py_compile python/arclink_operator_upgrade_broker.py`
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'operator_upgrade_broker or docker_authority_inventory_matches_compose_boundary' --maxfail=10`
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_deploy_regressions.py tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
- `python3 tests/test_documentation_truths.py`
- `python3 tests/test_public_repo_hygiene.py`
- `git diff --check`
- `python3 -m pytest -q tests` passed: 1298 passed, 6 skipped, 81 warnings in
  64.39s.

Residual risk:

- `GAP-019` remains open. The operator-upgrade broker still carries the
  writeable Docker socket and writable host repo exception for allowlisted
  queued upgrades; remaining closure requires stronger helper/broker isolation,
  live alert integration, or an operator residual-risk decision.

## 2026-05-23 GAP-019-AV Operator Upgrade Broker Fixed Script Target Preflight

Scope: reduced the `GAP-019` Docker/root trusted-host boundary locally by
making `operator-upgrade-broker` preflight fixed repo script targets before
private operator logs or upgrade subprocess execution. This is local hardening
only and does not close the operator-upgrade broker residual-risk decision.

Changed:

- `python/arclink_operator_upgrade_broker.py`: added fixed repo script target
  validation for `deploy.sh` and `bin/component-upgrade.sh`. Missing,
  symlinked, non-regular, unreadable, or non-executable targets fail closed
  before private operator logs, `_run_logged_command`, or `subprocess.run`.
  `run_pin_upgrade` now builds validated component-upgrade command forms before
  opening the operator log.
- `tests/test_arclink_docker.py`: added the failing operator-upgrade broker
  fixed-script regression and extended the authority inventory/docs guard for
  `GAP-019-AV`.
- `config/docker-authority-inventory.json`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, `mission_status.md`, `docs/docker.md`,
  `docs/arclink/data-safety.md`, and `docs/arclink/operations-runbook.md`:
  recorded `GAP-019-AV` as interim hardening while keeping `GAP-019` open.

Pre-repair reproduction:

- A temp repo with `deploy.sh` symlinked to `real-deploy.sh` returned success,
  reached the mocked `subprocess.run` path with the resolved target, and
  created the private operator log.
- The focused regression then failed before the repair with
  `symlinked deploy.sh: {'returncode': 0}`.

Validation:

- `python3 -m pytest -q tests/test_arclink_docker.py -k 'operator_upgrade_broker_rejects_symlinked_or_non_executable_repo_scripts_before_subprocess' --maxfail=1`
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'operator_upgrade_broker and not live' --maxfail=10`
- `python3 -m py_compile python/arclink_operator_upgrade_broker.py`
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'operator_upgrade_broker or docker_authority_inventory_matches_compose_boundary' --maxfail=10`
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
- `python3 tests/test_documentation_truths.py`
- `python3 tests/test_public_repo_hygiene.py`
- `git diff --check`
- `python3 -m pytest -q tests` passed: 1297 passed, 6 skipped, 81 warnings in
  63.76s.

Residual risk:

- `GAP-019` remains open. The operator-upgrade broker still carries the
  writeable Docker socket and writable host repo exception for allowlisted
  queued upgrades; remaining closure requires stronger helper/broker isolation,
  live alert integration, or an operator residual-risk decision.

## 2026-05-23 GAP-019-AU Process Helper Fixed Command Target Preflight

Scope: reduced the `GAP-019` Docker/root trusted-host boundary locally by
making `agent-process-helper` preflight fixed repo command targets before
helper logs or subprocess execution. This is local hardening only and does not
close the root helper residual-risk decision.

Changed:

- `python/arclink_agent_process_helper.py`: added fixed repo command target
  validation for install, identity, refresh, cron, gateway, and dashboard
  operations. Missing, symlinked, non-regular, unreadable, or non-executable
  shell targets fail closed before helper logs or subprocess dispatch; the
  identity setup script must be a readable canonical repo child.
- `tests/test_arclink_docker.py`: added the failing target-preflight
  regression, updated helper fixtures to create valid fake repo targets, and
  extended authority inventory/docs guards for `GAP-019-AU`.
- `config/docker-authority-inventory.json`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, `mission_status.md`, `docs/docker.md`,
  `docs/arclink/data-safety.md`, and `docs/arclink/operations-runbook.md`:
  recorded `GAP-019-AU` as interim hardening while keeping `GAP-019` open.

Pre-repair reproduction:

- A temp repo with missing `bin/user-agent-refresh.sh` returned success,
  reached the mocked `subprocess.run`, and created a helper log.
- The focused regression then failed before the repair with a successful
  `refresh` payload instead of a fail-closed command-target error.

Validation:

- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper_rejects_symlinked_or_missing_repo_command_targets_before_subprocess' --maxfail=1`
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper and not live' --maxfail=10`
- `python3 -m py_compile python/arclink_agent_process_helper.py`
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20`
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
- `python3 tests/test_documentation_truths.py`
- `python3 tests/test_public_repo_hygiene.py`
- `git diff --check`
- `python3 -m pytest -q tests` passed: 1296 passed, 6 skipped, 81 warnings in
  63.38s.

Residual risk:

- `GAP-019` remains open. The helper still carries bounded root authority for
  allowlisted Docker agent process execution; remaining closure requires
  stronger helper/broker isolation, live alert integration, or an operator
  residual-risk decision.

## 2026-05-23 GAP-014-C Hosted Request Share Broker

Scope: reduced `GAP-014` locally by adding a hosted
`/api/v1/user/share-grants/broker` adapter for Drive/Code `Request Share`.
No direct public share-link generation, live bot delivery, Nextcloud/OCS
sharing, deploy, Docker lifecycle, systemd, credentialed services,
private-state reads, or host mutation was run or claimed.

Files changed:

- `python/arclink_api_auth.py` and `python/arclink_hosted_api.py`: added
  deployment-scoped broker token hashing/validation, recipient resolution,
  broker share-grant creation, OpenAPI route metadata, and a distinct broker
  route that does not weaken the browser session/CSRF route.
- `plugins/hermes-agent/drive/dashboard/plugin_api.py` and
  `plugins/hermes-agent/code/dashboard/plugin_api.py`: normalized broker
  payloads with `owner_deployment_id`, ArcLink `resource_kind`, file/directory
  `item_kind`, and token-header-only auth.
- `python/arclink_provisioning.py`, `python/arclink_sovereign_worker.py`, and
  `bin/install-deployment-hermes-home.sh`: wired the broker URL, runtime token
  secret file path, deployment access metadata, and deployment metadata hash
  sync.
- `tests/test_arclink_hosted_api.py`, `tests/test_arclink_plugins.py`,
  `tests/test_arclink_provisioning.py`, and
  `tests/test_arclink_sovereign_worker.py`: covered valid, missing, invalid,
  and cross-deployment broker tokens; browser route CSRF preservation; plugin
  payload shape; compose secret wiring; and metadata hash sync.
- `docs/API_REFERENCE.md`, `docs/openapi/arclink-v1.openapi.json`,
  `docs/arclink/operations-runbook.md`, plugin READMEs, `GAPS.md`,
  `USER_JOURNEY.md`, `research/COVERAGE_MATRIX.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: recorded the local broker
  repair and remaining live/policy gates.

Validation:

- Pre-repair focused regression failed because
  `/api/v1/user/share-grants/broker` returned `404`.
- `python3 -m pytest -q tests/test_arclink_hosted_api.py -k 'share_grant_broker or share_grants' --maxfail=10`
  passed: 3 passed, 84 deselected.
- `python3 -m pytest -q tests/test_arclink_plugins.py -k 'share_request_broker_auth or drive_code_share_request_broker_contract or share_link_creation or linked_root' --maxfail=10`
  passed: 2 passed, 33 deselected.
- `python3 -m pytest -q tests/test_arclink_provisioning.py tests/test_arclink_sovereign_worker.py -k 'dry_run_renders_full_service_dns_access_intent or fake_sovereign_worker_applies_ready_deployment' --maxfail=10`
  passed: 2 passed, 31 deselected.
- `python3 -m pytest -q tests/test_arclink_hosted_api.py tests/test_arclink_plugins.py tests/test_arclink_provisioning.py tests/test_arclink_sovereign_worker.py --maxfail=20`
  passed: 155 passed.
- `python3 tests/test_documentation_truths.py`, `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1295 passed, 6 skipped, 81 warnings in
  63.99s.

Residual risk:

- `GAP-014` remains open for production workspace/browser proof, live
  Telegram/Discord prompt delivery and callbacks, live audit/revoke proof from
  the browser path, and any operator decision to add or replace the native
  broker with a Nextcloud-backed adapter. This pass does not claim live sharing
  or direct public share links.

## 2026-05-23 GAP-014-B Authenticated Drive/Code Request Share Handoff

Scope: reduced `GAP-014` locally by making the Drive/Code browser
`Request Share` broker handoff explicitly authenticated. No direct public
share-link generation, live bot delivery, Nextcloud/OCS sharing, deploy,
Docker lifecycle, systemd, credentialed services, private-state reads, or host
mutation was run or claimed.

Files changed:

- `plugins/hermes-agent/drive/dashboard/plugin_api.py` and
  `plugins/hermes-agent/code/dashboard/plugin_api.py`: `share_request` status
  now enables only when a broker URL and broker-token file are configured. The
  route rejects URL-only broker configuration before dispatch and sends the
  token only as `X-ArcLink-Share-Request-Broker-Token`.
- `tests/test_arclink_plugins.py`: extended the Drive/Code share-request
  contract to prove URL-only broker configuration stays disabled, does not
  dispatch, and token-file-backed dispatch sends an auth header without
  returning auth material in status, response, or broker payloads.
- `plugins/hermes-agent/drive/README.md`,
  `plugins/hermes-agent/code/README.md`,
  `docs/arclink/operations-runbook.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `research/COVERAGE_MATRIX.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded that `GAP-014` is reduced by the authenticated
  local handoff while production browser broker/adapter proof remains open.

Validation:

- Pre-repair focused regression failed because Drive reported
  `share_request.enabled=true` with only `ARCLINK_SHARE_REQUEST_BROKER_URL`
  configured.
- `python3 -m pytest -q tests/test_arclink_plugins.py -k 'share_request_broker_auth or drive_code_share_request_broker_contract or share_link_creation or linked_root' --maxfail=10`
  passed: 2 passed, 33 deselected.
- `python3 -m pytest -q tests/test_arclink_plugins.py --maxfail=20` passed:
  35 passed.
- `python3 -m py_compile plugins/hermes-agent/drive/dashboard/plugin_api.py plugins/hermes-agent/code/dashboard/plugin_api.py`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1294 passed, 6 skipped, 81 warnings in
  63.55s.

Residual risk:

- `GAP-014` remains open for the production browser broker/adapter
  implementation, live Telegram/Discord prompt delivery and callbacks,
  audit/revoke proof from the browser path, and the operator decision between a
  native ArcLink broker and approved Nextcloud-backed adapter. This pass does
  not claim live sharing or direct public share links.

## 2026-05-23 GAP-014-A Drive/Code Request Share Contract

Scope: reduced `GAP-014` locally by adding a fail-closed Drive/Code browser
`Request Share` contract without enabling direct public share-link generation,
live bot delivery, Nextcloud/OCS sharing, deploy, Docker lifecycle, systemd,
credentialed services, private-state reads, or host mutation.

Files changed:

- `plugins/hermes-agent/drive/dashboard/plugin_api.py` and
  `plugins/hermes-agent/code/dashboard/plugin_api.py`: added `share_request`
  capability state plus `POST /share/request`. The route validates root, path,
  recipient identity, sensitive paths, and `Linked` non-reshare before sending a
  bounded ArcLink share-grants payload to an explicitly configured broker URL.
  With no broker URL, it returns 503 before any external call.
- `plugins/hermes-agent/drive/dashboard/dist/index.js` and
  `plugins/hermes-agent/code/dashboard/dist/index.js`: added a conditional
  `Request Share` context-menu action that is visible only for writable roots
  whose status capabilities enable `share_request`.
- `tests/test_arclink_plugins.py`: added
  `test_arclink_drive_code_share_request_broker_contract`, covering disabled
  defaults, direct share-link copy absence, linked-root rejection, sensitive
  path rejection, missing-recipient rejection, unconfigured-broker rejection,
  and enabled-broker payload semantics.
- `plugins/hermes-agent/drive/README.md`,
  `plugins/hermes-agent/code/README.md`,
  `docs/arclink/operations-runbook.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `research/COVERAGE_MATRIX.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded that `GAP-014` is reduced, not closed.

Validation:

- Pre-repair module probe failed because Drive roots had no `share_request`
  capability; the focused pytest regression failed on missing
  `share_request` status state.
- `python3 -m pytest -q tests/test_arclink_plugins.py -k 'drive_code_share_request_broker_contract or share_link_creation or linked_root' --maxfail=10`
  passed: 2 passed, 33 deselected.
- `python3 -m pytest -q tests/test_arclink_hosted_api.py -k 'share_grant' --maxfail=10`
  passed: 4 passed, 82 deselected.
- `python3 -m pytest -q tests/test_arclink_plugins.py tests/test_arclink_hosted_api.py tests/test_arclink_dashboard.py tests/test_arclink_mcp_schemas.py --maxfail=20`
  passed: 143 passed.
- `node --test web/tests/test_api_client.mjs --test-name-pattern 'share'`
  passed: 49 tests.
- `node --test web/tests/test_page_smoke.mjs --test-name-pattern 'share|Linked'`
  passed: 26 tests.
- `python3 -m py_compile plugins/hermes-agent/drive/dashboard/plugin_api.py plugins/hermes-agent/code/dashboard/plugin_api.py`,
  `node --check` for both dashboard bundles, `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1294 passed, 6 skipped, 81 warnings in
  63.93s.

Residual risk:

- `GAP-014` remains open for authenticated browser broker/adapter work, live
  Telegram/Discord prompt delivery and callbacks, audit/revoke proof from the
  browser path, and the operator decision between a native ArcLink broker and
  approved Nextcloud-backed adapter. This pass does not claim live sharing or
  direct public share links.

## 2026-05-23 GAP-019-AT Process Helper Configured-Root Symlink Rejection

Scope: repaired the next local `GAP-019` trusted-host slice by making the root
Docker `agent-process-helper` reject symlinked configured or requested repo,
private-state, state, and runtime roots before helper log creation,
cwd/command/runtime lookup, or subprocess execution. No deploy, Docker
lifecycle, systemd, live provider, bot, payment, SSH/fleet, private-state read,
or host-mutating command was run.

Files changed:

- `python/arclink_agent_process_helper.py`: applies
  `_require_no_symlink_components` to configured/requested repo, private,
  state, and runtime roots via `_configured_paths`, `_require_configured_path`,
  and `_require_state_dir`.
- `tests/test_arclink_docker.py`: added
  `test_agent_process_helper_rejects_symlinked_configured_roots_before_work`
  for `run_once`, `ensure_processes`, and valid non-symlink requests, and
  extended authority inventory/docs assertions for `GAP-019-AT`.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/data-safety.md`, `docs/arclink/operations-runbook.md`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded `GAP-019-AT` while keeping `GAP-019` open.

Validation:

- Pre-repair temp-dir probe reproduced the bug:
  `process_helper_ok=True`, `calls=1`, `log_under_escaped=True`.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper_rejects_symlinked_configured_roots_before_work or docker_authority_inventory' --maxfail=5`
  passed: 2 passed, 55 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper_rejects_symlinked_configured_roots_before_work or agent_helpers_reject_symlinked_home_root or agent_helpers_reject_symlink_escaped_agent_paths or agent_process_helper_rejects_symlink_escaped_log_directory or configured_root_mismatch or docker_authority_inventory' --maxfail=10`
  passed: 6 passed, 51 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  57 passed in 0.84s.
- `python3 -m py_compile python/arclink_agent_process_helper.py`,
  `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1293 passed, 6 skipped, 81 warnings in
  63.81s.

Residual risk:

- `GAP-019` is reduced, not closed. `agent-process-helper` still carries
  bounded root authority for allowlisted process execution, and the
  socket-bearing brokers remain trusted-host boundaries until stronger
  isolation, live alert integration, or an operator residual-risk decision
  replaces the current posture.

## 2026-05-23 GAP-019-AS Agent Home Root Symlink Rejection

Scope: repaired the next local `GAP-019` trusted-host slice by making both
root Docker agent helpers reject symlinked configured or requested Docker
agent-home roots, including `ARCLINK_DOCKER_AGENT_HOME_ROOT`, before root
filesystem work, helper log creation, or subprocess execution. No deploy,
Docker lifecycle, systemd, live provider, bot, payment, SSH/fleet,
private-state read, or host-mutating command was run.

Files changed:

- `python/arclink_agent_user_helper.py`: added `_require_no_symlink_components`
  and applies it to configured/requested agent-home root validation before
  uid/gid assignment, trusted executable preflight, account commands,
  directory creation, or recursive chown.
- `python/arclink_agent_process_helper.py`: added the same configured
  agent-home root guard before helper log creation, `subprocess.run`, or
  `subprocess.Popen`.
- `tests/test_arclink_docker.py`: added focused regression coverage for a
  symlinked home root reaching root-helper work and updated the authority
  inventory/docs assertions for `GAP-019-AS`.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/data-safety.md`, `docs/arclink/operations-runbook.md`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded `GAP-019-AS` while keeping `GAP-019` open.

Validation:

- Pre-repair temp-dir probe reproduced the bug:
  `user_helper_ok=True`, `commands=3`, `escaped_assignment=True`;
  `process_helper_ok=True`, `run_calls=1`, `logs=True`.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'symlinked_home_root or docker_authority_inventory' --maxfail=5`
  passed: 2 passed, 54 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_helpers_reject_symlinked_home_root or agent_helpers_reject_symlink_escaped_agent_paths or agent_process_helper_rejects_symlink_escaped_log_directory or configured_root_mismatch or docker_authority_inventory' --maxfail=10`
  passed: 5 passed, 51 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  56 passed in 0.87s.
- `python3 -m py_compile python/arclink_agent_user_helper.py python/arclink_agent_process_helper.py`,
  `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `bash -n deploy.sh bin/*.sh test.sh`, `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1292 passed, 6 skipped, 81 warnings in
  63.10s.

Residual risk:

- `GAP-019` is reduced, not closed. `agent-user-helper` and
  `agent-process-helper` still carry bounded root authority in their scopes,
  and the socket-bearing brokers remain trusted-host boundaries until stronger
  isolation, live alert integration, or an operator residual-risk decision
  replaces the current posture.

## 2026-05-23 GAP-019-AR Dashboard Backend Host Confinement

Scope: repaired the next local `GAP-019` trusted-host slice by making both the
root `agent-process-helper` and dashboard `agent-supervisor-broker` reject
unsafe dashboard backend host values before dashboard process or proxy
subprocess construction. Accepted values are loopback or
Docker-internal/private/link-local IPs; wildcard, globally routable, multicast,
malformed, and non-IP values fail closed. No deploy, Docker lifecycle, systemd,
live provider, bot, payment, SSH/fleet, private-state read, or host-mutating
command was run.

Changed:

- `python/arclink_agent_process_helper.py`: added IP-literal dashboard backend
  host validation before dashboard command construction and `subprocess.Popen`.
- `python/arclink_agent_supervisor_broker.py`: aligned dashboard proxy target
  backend-host validation with the same fail-closed policy before sidecar
  subprocess construction.
- `tests/test_arclink_docker.py`: added helper and broker negative/positive
  regressions and extended the Docker authority inventory/doc truth checks.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/operations-runbook.md`, `docs/arclink/data-safety.md`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded `GAP-019-AR` and the remaining trusted-host
  risk.

Evidence:

- Pre-repair source inspection showed the process helper accepted dashboard
  backend host as a single line before dashboard `Popen`, while the broker
  accepted any parsable IP before dashboard proxy sidecar construction.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper_rejects_unsafe_dashboard_backend_host_before_subprocess or agent_supervisor_broker_rejects_unsafe_dashboard_backend_host' --maxfail=1`
  passed: 2 passed, 53 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'dashboard_backend_host or agent_process_helper or agent_supervisor_broker or docker_authority_inventory' --maxfail=10`
  passed: 13 passed, 42 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py tests/test_deploy_regressions.py`
  passed: 198 passed in 6.68s.
- `python3 -m py_compile python/arclink_agent_process_helper.py python/arclink_agent_supervisor_broker.py`,
  `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  and `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1291 passed, 6 skipped, and
  81 warnings in 63.48s.

Remaining:

- `GAP-019` remains open. This slice narrows one dashboard backend host
  authority path but does not make writeable Docker socket brokers or root
  helpers tenant-safe.
- Live proof, host mutation, Docker lifecycle, bot/provider/payment checks, and
  residual-risk acceptance remain out of scope for this local pass.

## 2026-05-23 GAP-019-AQ Provisioner Child Env Allowlist

Scope: repaired the next local `GAP-019` trusted-host slice by replacing
`agent-supervisor` enrollment-provisioner child `os.environ.copy()` inheritance
with an explicit env allowlist. The child keeps Docker mode/path config,
runtime roots, service URLs, and helper/broker values needed for Docker
enrollment and queued operator actions; unrelated payment, provider, bot,
ingress, memory-synthesis, session, fleet, Python path, and Git/SSH steering
env keys are not forwarded. No deploy, Docker lifecycle, systemd, live
provider, bot, payment, SSH/fleet, private-state read, or host-mutating command
was run.

Changed:

- `python/arclink_docker_agent_supervisor.py`: added
  `provisioner_child_env` and changed `run_provisioner` to use it instead of
  starting from the supervisor's full process environment.
- `tests/test_arclink_docker.py`: added
  `test_agent_supervisor_provisioner_child_env_is_allowlisted` and extended
  the Docker authority inventory/doc truth checks.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/operations-runbook.md`, `docs/arclink/data-safety.md`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded `GAP-019-AQ` and the remaining trusted-host
  risk.

Evidence:

- Pre-repair focused selector returned `52 deselected`, and source inspection
  showed `run_provisioner` building the child env from `os.environ.copy()`.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_supervisor_provisioner_child_env_is_allowlisted' --maxfail=1`
  passed: 1 passed, 52 deselected.
- `python3 -m py_compile python/arclink_docker_agent_supervisor.py`,
  `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  and `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_supervisor_provisioner_child_env_is_allowlisted or docker_authority_inventory_matches_compose_boundary' --maxfail=1`
  passed: 2 passed, 51 deselected.
- `python3 tests/test_arclink_docker.py` passed all 53 Docker regression tests.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py tests/test_deploy_regressions.py`
  passed: 196 passed in 6.64s.
- `bash -n deploy.sh bin/*.sh test.sh` and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1289 passed, 6 skipped, and
  81 warnings in 63.99s.

Remaining:

- `GAP-019` remains open. This slice narrows one child-process env exposure path
  but does not make writeable Docker socket brokers, root helpers, or
  `agent-supervisor` private config/state/vault mounts tenant-safe.
- Live proof, host mutation, Docker lifecycle, bot/provider/payment checks, and
  residual-risk acceptance remain out of scope for this local pass.

## 2026-05-23 GAP-019-AP Direct-Run Listener Defaults

Scope: repaired the next local `GAP-019` trusted-host slice by making the seven
high-authority Docker broker/helper modules bind `127.0.0.1` by default when
run directly. Compose remains the explicit source-owned `0.0.0.0` opt-in for
internal request-network reachability. No deploy, Docker lifecycle, systemd,
live provider, bot, payment, SSH/fleet, private-state read, or host-mutating
command was run.

Changed:

- `python/arclink_deployment_exec_broker.py`,
  `python/arclink_gateway_exec_broker.py`,
  `python/arclink_agent_supervisor_broker.py`,
  `python/arclink_operator_upgrade_broker.py`,
  `python/arclink_migration_capture_helper.py`,
  `python/arclink_agent_user_helper.py`, and
  `python/arclink_agent_process_helper.py`: changed direct-run `DEFAULT_HOST`
  from `0.0.0.0` to `127.0.0.1` while preserving `--host` and
  service-specific `ARCLINK_*_HOST` overrides.
- `tests/test_arclink_docker.py`: added
  `test_high_authority_helpers_default_to_loopback_outside_compose`, covering
  direct defaults, env/CLI overrides, Compose `0.0.0.0` host env, and
  loopback healthchecks.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/operations-runbook.md`, `docs/arclink/data-safety.md`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded `GAP-019-AP` and the remaining trusted-host
  risk.

Evidence:

- Pre-repair focused selector returned `51 deselected`, and a direct module
  probe showed all seven high-authority modules reported
  `DEFAULT_HOST == "0.0.0.0"` outside Compose.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'high_authority_helpers_default_to_loopback_outside_compose' --maxfail=1`
  passed: 1 passed, 51 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'high_authority_helpers_default_to_loopback_outside_compose or docker_authority_inventory_matches_compose_boundary' --maxfail=1`
  passed: 2 passed, 50 deselected.
- `python3 -m py_compile` for the seven broker/helper modules,
  `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_arclink_docker.py`, `bash -n deploy.sh bin/*.sh test.sh`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_deploy_regressions.py tests/test_health_regressions.py`
  passed: 189 passed in 6.63s.
- `python3 -m pytest -q tests` passed: 1288 passed, 6 skipped, and
  81 warnings in 63.51s.

Residual risk: this is listener-default hardening only. `GAP-019` remains open
for writeable Docker socket broker authority, root helper authority, stronger
isolation, live alert integration, or operator residual-risk acceptance.

## 2026-05-22 GAP-019-AO Process Helper Log Directory Symlink Paths

Scope: repaired the next local `GAP-019` trusted-host slice by preventing the
tokened root `agent-process-helper` from following symlink-escaped helper log
directories or helper log files before log open or root-reconstructed agent
subprocess execution. No deploy, Docker lifecycle, systemd, live provider, bot,
payment, SSH/fleet, private-state read, or host-mutating command was run.

Changed:

- `python/arclink_agent_process_helper.py`: added canonical helper log
  directory validation before `mkdir`, log open, `subprocess.run`, or
  `subprocess.Popen`; helper log files must resolve to their exact canonical
  child path.
- `tests/test_arclink_docker.py`: added the focused regression covering
  `run_once`, `ensure_processes`, and valid non-symlink helper log directories,
  and extended the Docker authority inventory guard for `GAP-019-AO`.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/operations-runbook.md`, `docs/arclink/data-safety.md`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded the new local control and remaining
  trusted-host risk.

Evidence:

- Pre-repair temp-dir probe showed
  `state/docker/agent-process-helper -> <tmp>/escaped-logs`; `run_once` wrote
  `agent-test-refresh.log` under the escaped directory and reached mocked
  `subprocess.run`, while `ensure_processes` wrote `agent-test-gateway.log`
  under the escaped directory and reached mocked `subprocess.Popen`.
- Pre-repair focused pytest failed because
  `test_agent_process_helper_rejects_symlink_escaped_log_directory` saw a
  successful helper response pointing at the escaped log path.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper_rejects_symlink_escaped_log_directory' --maxfail=1`
  passed: 1 passed, 50 deselected.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 -m py_compile python/arclink_agent_process_helper.py`, and
  `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper_rejects_symlink_escaped_log_directory or docker_authority_inventory' --maxfail=1`
  passed: 2 passed, 49 deselected.
- `python3 tests/test_arclink_docker.py` passed all 51 Docker regression tests.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py tests/test_arclink_action_worker.py`
  passed: 114 passed in 2.57s.
- `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, `bash -n deploy.sh bin/*.sh test.sh`,
  and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1287 passed, 6 skipped, and
  81 warnings in 63.35s.

Residual risk:

- `GAP-019` is reduced, not closed. `agent-process-helper` still has bounded
  root process-runner authority, other root helpers and writeable Docker socket
  brokers remain trusted-host boundaries, and closure still needs stronger
  isolation, live alert integration, or an operator residual-risk decision.

## 2026-05-22 GAP-019-AN Root Agent Helper Symlink Paths

Scope: repaired the next local `GAP-019` trusted-host slice by preventing
tokened root Docker agent helpers from following symlink-escaped agent home,
Hermes home, or workspace paths before root filesystem work, helper log
creation, or root-reconstructed agent subprocess execution. No deploy, Docker
lifecycle, systemd, live provider, bot, payment, SSH/fleet, private-state read,
or host-mutating command was run.

Changed:

- `python/arclink_agent_user_helper.py`: switched request path normalization to
  lexical canonical paths and added resolved canonical-child validation before
  uid/gid assignment writes, directory creation, account commands, or recursive
  chown.
- `python/arclink_agent_process_helper.py`: applied the same canonical-child
  symlink escape rejection before helper log creation, `subprocess.run`, or
  `subprocess.Popen`.
- `tests/test_arclink_docker.py`: added the focused regression covering agent
  home, nested Hermes-home, and workspace symlink escapes plus valid canonical
  non-symlink paths, and extended the authority inventory guard for
  `GAP-019-AN`.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/operations-runbook.md`, `docs/arclink/data-safety.md`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded the new local control and remaining
  trusted-host risk.

Evidence:

- Pre-repair temp-dir probe showed `agent-user-helper` accepted
  `state/docker/users/alex -> <tmp>/escaped/alex`, returned the escaped home,
  and targeted it for chown; `agent-process-helper` accepted the same escaped
  agent context and reached mocked `subprocess.run`.
- Pre-repair focused pytest failed because
  `test_agent_helpers_reject_symlink_escaped_agent_paths` saw a successful
  helper response for the escaped path.
- `python3 -m py_compile python/arclink_agent_user_helper.py python/arclink_agent_process_helper.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_helpers_reject_symlink_escaped_agent_paths' --maxfail=1`
  passed: 1 passed, 49 deselected.
- `python3 tests/test_arclink_docker.py` passed all 50 Docker regression tests.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_helpers_reject_symlink_escaped_agent_paths or docker_authority_inventory' --maxfail=1`
  passed: 2 passed, 48 deselected.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, `bash -n deploy.sh bin/*.sh test.sh`,
  and `git diff --check` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py tests/test_arclink_action_worker.py`
  passed: 113 passed in 2.51s.
- `python3 -m pytest -q tests` passed: 1286 passed, 6 skipped, and
  81 warnings in 63.69s.

Residual risk:

- `GAP-019` is reduced, not closed. `agent-user-helper` still has bounded root
  authority over Docker agent homes, `agent-process-helper` still has bounded
  root process-runner authority, writeable Docker socket brokers remain
  trusted-host boundaries, and closure still needs stronger isolation, live
  alert integration, or an operator residual-risk decision.

## 2026-05-22 GAP-019-AM Process Helper Env Boundary

Scope: repaired the next local `GAP-019` trusted-host slice by preventing
tokened `agent-process-helper` requests from injecting dynamic-loader,
Python path/startup, shell startup, Git/SSH command-steering, or secret-looking
process env keys into root-reconstructed Docker agent subprocesses. No deploy,
Docker lifecycle, systemd, live provider, bot, payment, SSH/fleet,
private-state read, or host-mutating command was run.

Changed:

- `python/arclink_agent_process_helper.py`: added unapproved env key validation
  for `LD_*`, Python path/startup, shell startup, Git/SSH command-steering, and
  secret-looking `*_TOKEN`, `*_SECRET`, `*_PASSWORD`, or `*_KEY` names before
  log creation, `subprocess.run`, or `subprocess.Popen`.
- `python/arclink_docker_agent_supervisor.py`: kept existing ArcLink helper
  token stripping and added fail-closed validation for the same unapproved
  non-token key family before helper payload construction.
- `tests/test_arclink_docker.py`: added focused helper and supervisor
  regressions and extended the Docker authority inventory guard for
  `GAP-019-AM`.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/operations-runbook.md`, `docs/arclink/data-safety.md`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded the new local control and remaining
  trusted-host risk.

Evidence:

- Pre-repair local probe showed `LD_PRELOAD` was accepted, reached mocked
  `Popen`, and was forwarded in the process env.
- Pre-repair focused pytest failed with
  `LD_PRELOAD was not rejected before run_once subprocess`.
- `python3 -m py_compile python/arclink_agent_process_helper.py python/arclink_docker_agent_supervisor.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper_rejects_unapproved_agent_env or docker_agent_supervisor_rejects_unapproved_agent_process_env or docker_authority_inventory' --maxfail=1`
  passed: 3 passed, 46 deselected.
- `python3 tests/test_arclink_docker.py` passed all 49 Docker regression tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  49 passed.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and
  `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 -m pytest -q tests` passed: 1285 passed, 6 skipped, and
  81 warnings in 63.57s.

Residual risk:

- `GAP-019` is reduced, not closed. `agent-process-helper` still has bounded
  root process-runner authority, other root helpers and writeable Docker socket
  brokers remain trusted-host boundaries, and closure still needs stronger
  isolation, live alert integration, or an operator residual-risk decision.

## 2026-05-22 GAP-012 Product Matrix Truth Guard

Scope: closed the local product-matrix documentation/test gap after confirming
`GAP-025` was the broad gate and reproducing that no `product_matrix` truth
test was selected. No deploy, Docker lifecycle, systemd, live provider, bot,
payment, Notion, SSH fleet, private-state read, or host-mutating command was
run.

Changed:

- `tests/test_documentation_truths.py`: added product-matrix parsing, status
  total verification, unknown-status rejection, `real` row source/proof anchor
  enforcement, and proof/policy boundary checks.
- `research/PRODUCT_REALITY_MATRIX.md`: recorded the local truth guard and
  tightened a small set of `real` rows so they carry explicit local test/proof
  anchors.
- `GAPS.md`: moved `GAP-012` to locally `real` while preserving all live proof
  and policy gates.
- `research/COVERAGE_MATRIX.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded the local guard and remaining proof/policy
  boundaries.

Evidence:

- Pre-repair reproduction:
  `python3 -m pytest -q tests/test_documentation_truths.py -k product_matrix --maxfail=1`
  returned `7 deselected`.
- `python3 -m pytest -q tests/test_documentation_truths.py -k product_matrix --maxfail=1`
  passed: 3 passed, 7 deselected.
- `python3 tests/test_documentation_truths.py` passed all 10 documentation
  truth checks.
- `python3 -m pytest -q tests/test_documentation_truths.py` passed: 10 passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1283 passed, 6 skipped, and
  81 warnings in 63.69s.

Residual risk:

- The matrix is locally guarded, not live-certified. Production E2E, Stripe,
  bots, provisioning/ingress/fleet, provider inference/account behavior,
  Hermes browser workspace proof, Notion, backup/restore, upgrade proof, and
  operator policy gates remain open until explicitly authorized proof or
  decision windows.

## 2026-05-22 GAP-021-A Local Cloud Fleet Lifecycle Harness

Scope: repaired the next local provisioning/fleet slice after confirming
`GAP-025` was the broad gate and reproducing the missing Linode lifecycle test
selector. No deploy, Docker lifecycle, systemd, live provider, bot, payment,
Notion, SSH fleet, private-state read, or host-mutating command was run.

Changed:

- `python/arclink_inventory.py`: exact cloud-create idempotency replays now
  return the stored operation result before the duplicate-host fast path, while
  different idempotency keys still fail closed to the existing-machine path.
- `tests/test_arclink_inventory.py`: added provider-parity lifecycle coverage
  for Hetzner and Linode fake clients across create replay, duplicate-host
  handling, drain-before-destroy, provider delete, destroy replay, and stored
  idempotency result shape.
- `tests/test_arclink_inventory_linode.py`: added the missing Linode lifecycle
  test for create replay, fake fleet probe handoff to ready/active state,
  explicit destroy requirement, drain guard, provider delete, destroy replay,
  and token-leak checks.
- `tests/test_arclink_inventory_hetzner.py`: tightened the existing create
  replay assertion to require the original stored result status.
- `docs/arclink/fleet-operator-runbook.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `research/COVERAGE_MATRIX.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded `GAP-021-A` as locally reduced while keeping
  `GAP-021` under `PG-FLEET` for real provider APIs, SSH wait, worker join,
  health, drain/remove, and destroy proof.

Evidence:

- Pre-repair reproduction:
  `python3 -m pytest -q tests/test_arclink_inventory_linode.py -k 'remove or destroy or lifecycle' --maxfail=1`
  returned `3 deselected`.
- `python3 -m py_compile python/arclink_inventory.py python/arclink_inventory_hetzner.py python/arclink_inventory_linode.py python/arclink_fleet_inventory_worker.py python/arclink_fleet.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_inventory_linode.py -k 'remove or destroy or lifecycle' --maxfail=1`
  passed: 1 passed, 3 deselected.
- `python3 -m pytest -q tests/test_arclink_inventory_hetzner.py tests/test_arclink_inventory_linode.py tests/test_arclink_fleet_inventory_worker.py -k 'cloud or lifecycle or probe or drain or remove or destroy' --maxfail=20`
  passed: 7 passed, 5 deselected.
- `python3 -m pytest -q tests/test_arclink_inventory_hetzner.py tests/test_arclink_inventory_linode.py tests/test_arclink_inventory.py tests/test_arclink_fleet_inventory_worker.py --maxfail=20`
  passed: 14 passed.
- `python3 tests/test_documentation_truths.py`, `python3 tests/test_public_repo_hygiene.py`,
  and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1280 passed, 6 skipped, and
  81 warnings in 63.38s.

Residual risk:

- `GAP-021` remains live-proof-gated. The local harness does not prove real
  Hetzner/Linode worker creation, provider-side delete, SSH wait, join,
  production health, or provider cleanup evidence.

## 2026-05-22 GAP-019-AL Trusted-Host Acceptance Gate

Scope: repaired the next local `GAP-019` trusted-host slice by adding an
explicit fail-closed residual-risk acknowledgement gate to the seven remaining
high-authority Docker/root broker and helper services. No deploy, Docker
lifecycle, systemd, live provider, bot, payment, SSH/fleet, private-state read,
or host-mutating command was run.

Changed:

- `python/arclink_boundary.py`: added the shared
  `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted` guard.
- `python/arclink_deployment_exec_broker.py`,
  `python/arclink_gateway_exec_broker.py`,
  `python/arclink_agent_supervisor_broker.py`,
  `python/arclink_operator_upgrade_broker.py`,
  `python/arclink_migration_capture_helper.py`,
  `python/arclink_agent_user_helper.py`, and
  `python/arclink_agent_process_helper.py`: require the guard before HTTP
  listener bind and before direct helper/broker request work.
- `compose.yaml`, `bin/docker-entrypoint.sh`, `bin/arclink-docker.sh`, and
  `bin/deploy.sh`: pass/preserve the env var while keeping the generated
  default blank so acceptance is not silently granted.
- `tests/test_arclink_docker.py`, `tests/test_arclink_executor.py`,
  `tests/test_arclink_pod_migration.py`, and
  `tests/test_arclink_notification_delivery.py`: added/updated coverage for
  missing/false acceptance failures, exact accepted value pass-through, Compose
  wiring, inventory rows, and existing direct broker/helper contracts.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/operations-runbook.md`, `docs/arclink/data-safety.md`,
  `GAPS.md`, `USER_JOURNEY.md`, `research/COVERAGE_MATRIX.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: recorded `GAP-019-AL`
  while keeping `GAP-019` and live proof gates open.

Evidence:

- Pre-repair reproduction returned `acceptance_gate=missing` for
  `deployment-exec-broker`, `migration-capture-helper`, `agent-user-helper`,
  `agent-process-helper`, `agent-supervisor-broker`,
  `operator-upgrade-broker`, and `gateway-exec-broker`.
- Post-repair reproduction returned `acceptance_gate=present` for all seven.
- `python3 -m py_compile python/arclink_boundary.py python/arclink_agent_supervisor_broker.py python/arclink_deployment_exec_broker.py python/arclink_gateway_exec_broker.py python/arclink_operator_upgrade_broker.py python/arclink_agent_user_helper.py python/arclink_agent_process_helper.py python/arclink_migration_capture_helper.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'trusted_host or authority_inventory or compose or docker_config or docker_docs' --maxfail=10`
  passed: 14 passed, 33 deselected.
- `python3 -m pytest -q tests/test_arclink_executor.py -k deployment_exec_broker --maxfail=5`,
  `python3 -m pytest -q tests/test_arclink_pod_migration.py -k migration_capture_helper --maxfail=5`,
  and `python3 -m pytest -q tests/test_arclink_notification_delivery.py -k gateway_exec_broker --maxfail=5`
  passed.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  47 passed.
- `python3 -m pytest -q tests` passed: 1278 passed, 6 skipped, 81 warnings in
  63.01s.

Remaining:

- `GAP-019` is reduced, not closed. The acknowledgement gate makes the
  residual trusted-host boundary explicit and fail-closed by default, but
  writeable Docker socket brokers and root helpers remain trusted-host
  authority until stronger isolation lands or the operator accepts residual
  risk.
- Live production, Stripe, bot, provider, provisioning/ingress, Notion,
  workspace, backup/restore, and upgrade proof gates remain open until an
  authorized credentialed proof window.

## 2026-05-22 GAP-019-AK Broker/Helper Compose Network Scoping

Scope: repaired the next local `GAP-019` trusted-host slice by moving tokened
Docker/root broker and helper request APIs off the shared default Compose
network. No deploy, Docker lifecycle, systemd, live provider, bot, payment,
SSH/fleet, private-state read, or host-mutating command was run.

Changed:

- `compose.yaml`: added internal request networks for
  `deployment-exec-broker`, `migration-capture-helper`, `agent-user-helper`,
  `agent-process-helper`, `agent-supervisor-broker`,
  `operator-upgrade-broker`, and `gateway-exec-broker`, attached only their
  legitimate callers, and preserved single-service egress networks for
  `agent-process-helper` and `operator-upgrade-broker`.
- `tests/test_arclink_docker.py`: added static Compose network topology checks,
  advanced the Docker authority inventory schema guard, and compared inventory
  network boundaries against Compose.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/operations-runbook.md`, `docs/arclink/data-safety.md`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded `GAP-019-AK` while keeping `GAP-019` open.

Evidence:

- Pre-repair reproduction returned `networks=default-only` for all seven
  high-authority broker/helper services.
- Post-repair reproduction returned `networks=scoped` for all seven services.
- `python3 -m py_compile python/arclink_agent_supervisor_broker.py python/arclink_deployment_exec_broker.py python/arclink_gateway_exec_broker.py python/arclink_operator_upgrade_broker.py python/arclink_agent_user_helper.py python/arclink_agent_process_helper.py python/arclink_migration_capture_helper.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'compose or authority_inventory or broker_network or helper_network or docker_docs' --maxfail=10`
  passed: 11 passed, 34 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  45 passed.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1276 passed, 6 skipped, 81 warnings in
  63.47s.

Remaining:

- `GAP-019` is reduced, not closed. The scoped networks reduce in-stack HTTP
  request reachability, but writeable Docker socket brokers and root helpers
  remain trusted-host boundaries until stronger isolation lands or the operator
  accepts residual risk.
- Live production, Stripe, bot, provider, provisioning/ingress, Notion,
  workspace, backup/restore, and upgrade proof gates remain open until an
  authorized credentialed proof window.

## 2026-05-22 GAP-019-AJ Agent Process Helper Desired-Signature Restart

Scope: repaired the next local `GAP-019` trusted-host slice by preventing
`agent-process-helper` from silently keeping stale Docker-mode gateway or
dashboard processes when a validated desired command, cwd, or env contract
changes under the same `agent_id:kind` key. No deploy, Docker lifecycle,
systemd, live provider, bot, payment, SSH/fleet, private-state read, or
host-mutating command was run.

Changed:

- `python/arclink_agent_process_helper.py`: added hashed desired-process
  signatures for long-running gateway/dashboard handles, compared signatures
  during reconciliation, and replaced one-shot terminate/pop with bounded
  process-group SIGTERM/SIGKILL shutdown before replacement.
- `tests/test_arclink_docker.py`: added regression coverage for unchanged
  desired specs, dashboard backend port drift, validated env signature drift,
  and `terminate_all` using the bounded stop path; advanced the authority
  inventory schema guard.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/operations-runbook.md`, `docs/arclink/data-safety.md`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded `GAP-019-AJ` while keeping `GAP-019` open.

Evidence:

- Pre-repair reproduction returned `second_started=[]`, `popen_count=1`,
  `terminated_count=0`, and `last_command_port=8100`.
- Post-repair reproduction returned `second_started=["agent-test:dashboard"]`,
  `second_stopped=["agent-test:dashboard"]`, `popen_count=2`,
  `terminated_count=1`, and `last_command_port=8200`.
- `python3 -m py_compile python/arclink_agent_process_helper.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper or authority_inventory or compose or docker_docs' --maxfail=10`
  passed: 14 passed, 30 deselected.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`, and
  `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1275 passed, 6 skipped, 81 warnings in
  63.38s.

Remaining:

- `GAP-019` is reduced, not closed. `agent-process-helper` still has bounded
  root process-runner authority for allowlisted Docker agent commands, and the
  writeable Docker socket brokers plus other root helpers remain trusted-host
  boundaries until stronger isolation lands or the operator accepts residual
  risk.
- Live production, Stripe, bot, provider, provisioning/ingress, Notion,
  workspace, backup/restore, and upgrade proof gates remain open until an
  authorized credentialed proof window.

## 2026-05-22 GAP-019-AI Operator Upgrade Broker Docker CLI Lookup Hardening

Scope: repaired the next local `GAP-019` trusted-host slice by preventing the
writeable-socket `operator-upgrade-broker` from passing unsafe
`ARCLINK_DOCKER_BINARY` values into queued Docker-mode operator upgrade and
pin-upgrade child subprocesses. No deploy, Docker lifecycle, systemd, live
provider, bot, payment, SSH/fleet, private-state read, or host-mutating command
was run.

Changed:

- `python/arclink_operator_upgrade_broker.py`: added trusted Docker CLI path
  resolution for preserved child env, requiring `docker` or a trusted absolute
  Docker executable before `_run_logged_command`.
- `tests/test_arclink_docker.py`: updated the valid operator-upgrade test to
  preserve a trusted absolute Docker path and added fail-closed coverage for
  `/bin/bash`, shell-like strings, relative values, PATH-injected fake Docker,
  missing Docker, non-executable Docker, and both `run_operator_upgrade` and
  `run_pin_upgrade` flows.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/operations-runbook.md`, `docs/arclink/data-safety.md`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded `GAP-019-AI` while keeping `GAP-019` open.

Evidence:

- Pre-repair reproduction returned `ok=True`, command `deploy.sh docker
  upgrade`, and child `ARCLINK_DOCKER_BINARY=/bin/bash`.
- Post-repair reproduction returned `ok=False`, no captured command, no child
  `ARCLINK_DOCKER_BINARY`, and `operator upgrade broker Docker CLI must point
  to the docker executable`.
- `python3 -m py_compile python/arclink_operator_upgrade_broker.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'operator_upgrade_broker or authority_inventory or compose' --maxfail=10`
  passed: 12 passed, 31 deselected.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`, and
  `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1274 passed, 6 skipped, 81 warnings in
  63.24s.

Remaining:

- `GAP-019` is reduced, not closed. `operator-upgrade-broker` still has
  writeable Docker socket authority and the writable host repo exception for
  allowlisted queued upgrades; other socket brokers and root helpers remain
  trusted-host boundaries until stronger isolation lands or the operator
  accepts residual risk.
- Live production, Stripe, bot, provider, provisioning/ingress, Notion,
  workspace, backup/restore, and upgrade proof gates remain open until an
  authorized credentialed proof window.

## 2026-05-22 GAP-019-AH Gateway Exec Broker Docker CLI Lookup Hardening

Scope: repaired the next local `GAP-019` trusted-host slice by preventing the
writeable-socket `gateway-exec-broker` from resolving public Agent gateway
container discovery or exec through a PATH-injected fake `docker` or unsafe
`ARCLINK_DOCKER_BINARY`. No deploy, Docker lifecycle, systemd, live provider,
bot, payment, SSH/fleet, or host-mutating commands were run.

Changed:

- `python/arclink_gateway_exec_broker.py`: resolves Docker to `docker` or a
  trusted absolute Docker CLI path before running-container discovery or public
  Agent gateway exec, validates the semantic allowlisted `docker` command
  before substituting the trusted executable, and fails closed on unsafe,
  missing, non-executable, or non-Docker values.
- `python/arclink_notification_delivery.py`: lets broker callers inject the
  trusted Docker CLI path into deployment service discovery while preserving the
  existing default for legacy command validation.
- `compose.yaml`: passes the optional `ARCLINK_DOCKER_BINARY` setting into
  `gateway-exec-broker` without reintroducing broad app env.
- `tests/test_arclink_docker.py` and
  `tests/test_arclink_notification_delivery.py`: added fail-closed coverage for
  unsafe Docker binary configuration, a PATH-injected fake `docker`, missing
  Docker discovery, and trusted-path discovery plus exec.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/operations-runbook.md`, `docs/arclink/data-safety.md`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded `GAP-019-AH` while keeping `GAP-019` open.

Evidence:

- Pre-repair reproduction returned `ok=True` and two fake `docker` calls.
- Post-repair reproduction returned `ok=False`, `fake_docker_calls=[]`, and
  `gateway exec broker Docker CLI path is not trusted`.
- `python3 -m py_compile python/arclink_gateway_exec_broker.py python/arclink_notification_delivery.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'gateway_exec_broker or authority_inventory or compose' --maxfail=5`
  passed: 10 passed, 32 deselected.
- `python3 -m pytest -q tests/test_arclink_notification_delivery.py -k 'gateway_exec_broker or public_agent_bridge' --maxfail=10`
  passed: 8 passed, 14 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  42 tests.
- `python3 -m pytest -q tests/test_arclink_notification_delivery.py --maxfail=20`
  passed: 22 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`, and
  `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1273 passed, 6 skipped, 81 warnings in
  63.24s.

Remaining:

- `GAP-019` is reduced, not closed. `gateway-exec-broker` still has writeable
  Docker socket authority for allowlisted public Agent gateway exec, other
  socket brokers remain trusted-host boundaries, and root helpers retain
  bounded root authority until stronger isolation lands or the operator accepts
  residual risk.
- Live production, Stripe, bot, provider, provisioning/ingress, Notion,
  workspace, backup/restore, and upgrade proof gates remain open until an
  authorized credentialed proof window.

## 2026-05-22 GAP-019-AG Deployment Exec Broker Docker CLI Lookup Hardening

Scope: repaired the next local `GAP-019` trusted-host slice by preventing the
writeable-socket `deployment-exec-broker` from resolving deployment Compose
execution through an unsafe `ARCLINK_DOCKER_BINARY`. No deploy, Docker
lifecycle, systemd, live provider, bot, payment, SSH/fleet, or host-mutating
commands were run.

Changed:

- `python/arclink_deployment_exec_broker.py`: resolves `ARCLINK_DOCKER_BINARY`
  to `docker` or a trusted absolute Docker CLI path and fails closed before
  `subprocess.run` when the value is missing, unsafe, non-executable, or not a
  Docker CLI path.
- `tests/test_arclink_docker.py` and `tests/test_arclink_executor.py`: added
  fail-closed coverage for `ARCLINK_DOCKER_BINARY=bash`, preserved trusted
  fake-Docker command construction, and updated the broker contract around the
  new resolver.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/operations-runbook.md`, `docs/arclink/data-safety.md`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded `GAP-019-AG` while keeping `GAP-019` open.

Evidence:

- Pre-repair reproduction returned `executables=['bash']`.
- Post-repair reproduction returned `ok=False` and `executables=[]`.
- `python3 -m py_compile python/arclink_deployment_exec_broker.py python/arclink_executor.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'deployment_exec_broker or authority_inventory or compose' --maxfail=5`
  passed: 10 passed, 31 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  41 tests.
- `python3 -m pytest -q tests/test_arclink_executor.py --maxfail=20` passed:
  39 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1272 passed, 6 skipped, 81 warnings in
  63.92s.

Remaining:

- `GAP-019` is reduced, not closed. `deployment-exec-broker` still has
  writeable Docker socket authority for allowlisted deployment Compose
  operations, other socket brokers remain trusted-host boundaries, and root
  helpers retain bounded root authority until stronger isolation lands or the
  operator accepts residual risk.
- Live production, Stripe, bot, provider, provisioning/ingress, Notion,
  workspace, backup/restore, and upgrade proof gates remain open until an
  authorized credentialed proof window.

## 2026-05-22 GAP-019-AE Agent User Helper Root Executable Lookup Hardening

Scope: repaired the next local `GAP-019` trusted-host slice by preventing the
tokened root `agent-user-helper` from resolving account and ownership tools
through ambient helper `PATH`. No deploy, Docker lifecycle, systemd, live
provider, bot, payment, SSH/fleet, or host-mutating commands were run.

Changed:

- `python/arclink_agent_user_helper.py`: pins `groupadd`, `useradd`, and
  `chown` to `/usr/sbin/groupadd`, `/usr/sbin/useradd`, and `/usr/bin/chown`,
  and preflights those trusted executables before uid/gid assignment writes,
  directory creation, account commands, or recursive ownership repair.
- `tests/test_arclink_docker.py`: updated the helper contract to require
  absolute executable dispatch and added fail-closed coverage for a missing
  trusted executable before helper mutation.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/operations-runbook.md`, `docs/arclink/data-safety.md`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded `GAP-019-AE` while keeping `GAP-019` open.

Evidence:

- Pre-repair reproduction returned `['groupadd', 'useradd', 'chown']`.
- Post-repair reproduction returned
  `['/usr/sbin/groupadd', '/usr/sbin/useradd', '/usr/bin/chown']`.
- `python3 -m py_compile python/arclink_agent_user_helper.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_user_helper or authority_inventory or compose' --maxfail=5`
  passed: 13 passed, 26 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  39 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1270 passed, 6 skipped, 81 warnings in
  63.07s.

Remaining:

- `GAP-019` is reduced, not closed. `agent-user-helper` still has bounded root
  authority over Docker agent homes, `agent-process-helper` still has bounded
  root authority for allowlisted process execution, and writeable Docker socket
  brokers remain trusted-host boundaries until stronger isolation lands or the
  operator accepts residual risk.
- Live production, Stripe, bot, provider, provisioning/ingress, Notion,
  workspace, backup/restore, and upgrade proof gates remain open until an
  authorized credentialed proof window.

## 2026-05-22 GAP-019-AD Agent Process Helper Pre-Drop Lookup Hardening

Scope: repaired the next local `GAP-019` trusted-host slice by preventing a
tokened `agent-process-helper` request from influencing root executable lookup
before `setpriv` drops privileges. No deploy, Docker lifecycle, systemd, live
provider, bot, payment, SSH/fleet, or host-mutating commands were run.

Changed:

- `python/arclink_agent_process_helper.py`: rejects request env `PATH` values
  that differ from `SAFE_PATH`, invokes `/usr/bin/setpriv` by absolute path,
  and fails `identity` setup closed unless the pinned runtime venv Python
  exists under `RUNTIME_DIR`.
- `tests/test_arclink_docker.py`: added fail-closed coverage for malicious
  `PATH` on both `run_once` and `ensure_processes`, absolute `setpriv`
  dispatch, and removal of the bare `python3` identity fallback.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/operations-runbook.md`, `docs/arclink/data-safety.md`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded `GAP-019-AD` while keeping `GAP-019` open.

Evidence:

- Pre-repair reproduction returned `accepted_caller_path=True`, first
  executable `setpriv`, and child `PATH=/tmp/.../malicious-bin`.
- Post-repair reproduction returned `accepted_caller_path=False`, no
  subprocess executable, and
  `agent process helper env PATH must match the safe helper PATH`.
- `python3 -m py_compile python/arclink_agent_process_helper.py python/arclink_docker_agent_supervisor.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper or authority_inventory or compose'`
  passed: 12 passed, 26 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  38 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1269 passed, 6 skipped, 81 warnings in
  62.86s.

Remaining:

- `GAP-019` is reduced, not closed. `agent-process-helper` still has bounded
  root authority to execute allowlisted Docker agent process operations, and
  writeable Docker socket brokers remain trusted-host boundaries until stronger
  isolation lands or the operator accepts residual risk.
- Live production, Stripe, bot, provider, provisioning/ingress, Notion,
  workspace, backup/restore, and upgrade proof gates remain open until an
  authorized credentialed proof window.

## 2026-05-22 GAP-019-AC Migration Capture Helper Env And State-Root Confinement

Scope: repaired the next local `GAP-019` trusted-host slice by narrowing the
root `migration-capture-helper` service environment and adding configured
state-root confinement before root file work. No deploy, Docker lifecycle,
systemd, live provider, bot, payment, SSH/fleet, or host-mutating commands were
run.

Changed:

- `compose.yaml`: removed broad `*arclink-env` inheritance from
  `migration-capture-helper`; preserved only `ARCLINK_STATE_ROOT_BASE` and
  helper token/listener env, with root user, `cap_drop: ALL`, no Docker socket,
  and the deployment state-root bind.
- `python/arclink_migration_capture_helper.py`: added
  `ARCLINK_STATE_ROOT_BASE` parsing and required source, target, and capture
  paths to resolve under that configured base before `_copy_capture` or
  `_materialize_capture` can run.
- `tests/test_arclink_pod_migration.py`: added fail-closed coverage for
  outside-base source, target, and staging paths, including proof that file
  work does not start.
- `tests/test_arclink_docker.py` and `config/docker-authority-inventory.json`:
  updated the Compose/inventory contract to schema 27 and recorded
  `GAP-019-AC` service-env/state-root controls.
- `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`,
  `mission_status.md`, `docs/docker.md`,
  `docs/arclink/operations-runbook.md`, and `docs/arclink/data-safety.md`:
  recorded the local hardening while keeping `GAP-019` open.

Evidence:

- Pre-repair local probes reproduced broad env inheritance and an accepted
  outside-base source root:
  `{'outside_source_accepted': True, 'payload': {'file_count': 1}}`.
- Post-repair probe failed closed:
  `{'outside_source_accepted': False, 'payload': 'migration capture helper source root must stay under the configured state-root base'}`.
- `python3 -m py_compile python/arclink_migration_capture_helper.py python/arclink_pod_migration.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_pod_migration.py -k 'migration_capture_helper or capture_requires_helper or unscoped_source_root'`
  passed: 4 passed, 7 deselected.
- `python3 -m pytest -q tests/test_arclink_action_worker.py -k 'migration_capture_helper or reprovision_non_dry_run'`
  passed: 2 passed, 35 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'migration_capture_helper or authority_inventory or compose' --maxfail=5`
  passed: 9 passed, 29 deselected.
- `python3 -m pytest -q tests/test_arclink_pod_migration.py --maxfail=20`
  passed: 11 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  38 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1269 passed, 6 skipped, 81 warnings in
  63.45s.

Remaining:

- `GAP-019` is reduced, not closed. `migration-capture-helper` still has root
  authority over deployment bind mounts during an operator-controlled migration
  window, and writeable Docker socket brokers remain trusted-host boundaries
  until stronger isolation lands or the operator accepts residual risk.
- Live production, Stripe, bot, provider, provisioning/ingress, Notion,
  workspace, backup/restore, and upgrade proof gates remain open until an
  authorized credentialed proof window.

## 2026-05-22 GAP-019-Z Agent Supervisor Broker Service Env And Private Mount Narrowing

Scope: repaired the next local `GAP-019` trusted-host slice by narrowing the
`agent-supervisor-broker` Compose service boundary used for Docker-mode
dashboard network/proxy sidecars. No deploy, Docker mutation, systemd, SSH
fleet, provider, payment, bot, Notion, credentialed proof, or host mutation ran.

What changed:

- `compose.yaml`: replaced `agent-supervisor-broker` broad `*arclink-env`
  inheritance with an explicit minimal service env for Docker binary/image, repo
  path, host/container private path metadata, and broker token/listener settings;
  removed broad `arclink-priv/config`, `arclink-priv/state`, and
  `arclink-priv/secrets/container` mounts from that socket broker while keeping
  the Docker socket.
- `tests/test_arclink_docker.py`: added regression coverage that fails if the
  broker regains broad app env inheritance, broad private config/state/secrets
  mounts, or loses the minimal env needed for dashboard proxy sidecar
  reconstruction; updated the direct script summary count.
- `config/docker-authority-inventory.json`: upgraded the Docker authority
  inventory to the `GAP-019-Z` schema and recorded the removed env/mount
  authority plus the remaining writeable Docker socket residual risk.
- `docs/docker.md`, `docs/arclink/operations-runbook.md`,
  `docs/arclink/data-safety.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: recorded `GAP-019-Z` as
  local hardening while keeping `GAP-019` open for writeable socket brokers,
  root helpers, alert integration, and operator residual-risk acceptance.

Validation:

- Pre-repair Compose probe failed with broad env plus private config/state and
  global container-secrets mounts present.
- Post-repair Compose probe returned
  `{'inherits_broad_arclink_env': False, 'mounts_global_container_secrets': False, 'mounts_private_config': False, 'mounts_private_state': False, 'has_docker_socket': True, 'has_cap_drop_all': True}`.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_supervisor_broker or authority_inventory or compose'`
  passed: 7 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  35 tests.
- `python3 tests/test_arclink_docker.py` passed: 35 script tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
  passed.
- `python3 tests/test_documentation_truths.py` passed: 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1265 passed, 6 skipped, 81 warnings in
  62.94s.

Remaining:

- `GAP-019` is reduced, not closed. `agent-supervisor-broker` no longer receives
  broad app env values or broad private config/state/secrets mounts at service
  startup, but it still has writeable Docker socket authority for allowlisted
  dashboard network/proxy sidecar work. Other socket brokers and root helpers
  remain trusted-host boundaries until stronger isolation or an operator
  residual-risk decision.

## 2026-05-22 GAP-019-Y Gateway Exec Broker Service Env And Private Mount Narrowing

Scope: repaired the next local `GAP-019` trusted-host slice by narrowing the
`gateway-exec-broker` Compose service boundary used for Raven-mediated
public-Agent gateway exec. No deploy, Docker mutation, systemd, SSH fleet,
provider, payment, bot, Notion, credentialed proof, or host mutation ran.

What changed:

- `compose.yaml`: replaced `gateway-exec-broker` broad `*arclink-env`
  inheritance with an explicit minimal service env for
  `ARCLINK_STATE_ROOT_BASE` plus broker token/listener settings; removed broad
  `arclink-priv/config`, `arclink-priv/state`, and
  `arclink-priv/secrets/container` mounts from that socket broker while keeping
  the deployment state-root bind and Docker socket.
- `tests/test_arclink_docker.py`: added regression coverage that fails if the
  broker regains broad app env inheritance, broad private config/state/secrets
  mounts, or loses the minimal env/state-root bind required for Compose
  fallback.
- `config/docker-authority-inventory.json`: upgraded the Docker authority
  inventory to the `GAP-019-Y` schema and recorded the removed env/mount
  authority plus the remaining writeable Docker socket residual risk.
- `docs/docker.md`, `docs/arclink/operations-runbook.md`,
  `docs/arclink/data-safety.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: recorded `GAP-019-Y` as
  local hardening while keeping `GAP-019` open for writeable socket brokers,
  root helpers, alert integration, and operator residual-risk acceptance.

Validation:

- Pre-repair Compose probe failed with broad env plus private config/state and
  global container-secrets mounts present.
- Post-repair Compose probe returned
  `{'inherits_broad_arclink_env': False, 'mounts_global_container_secrets': False, 'mounts_private_config': False, 'mounts_private_state': False, 'mounts_state_root_base': True, 'has_docker_socket': True}`.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'gateway_exec_broker or authority_inventory or compose'`
  passed: 5 tests.
- `python3 -m pytest -q tests/test_arclink_notification_delivery.py -k 'gateway_exec_broker or public_agent_bridge'`
  passed: 8 tests.
- `python3 tests/test_arclink_docker.py` passed: 33 script tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  34 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
  passed.
- `python3 tests/test_documentation_truths.py` passed: 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1264 passed, 6 skipped, 81 warnings in
  62.92s.

Remaining:

- `GAP-019` is reduced, not closed. `gateway-exec-broker` no longer receives
  broad app env values or broad private config/state/secrets mounts at service
  startup, but it still has writeable Docker socket authority for allowlisted
  public-Agent gateway exec. Other socket brokers and root helpers remain
  trusted-host boundaries until stronger isolation or an operator residual-risk
  decision.

## 2026-05-22 GAP-019-X Process Helper Service Env And Secret Mount Narrowing

Scope: repaired the next local `GAP-019` trusted-host slice by narrowing the
root `agent-process-helper` Compose service boundary. No deploy, Docker
mutation, systemd, SSH fleet, provider, payment, bot, Notion, credentialed
proof, or host mutation ran.

What changed:

- `compose.yaml`: replaced `agent-process-helper` broad `*arclink-env`
  inheritance with an explicit minimal service env for Docker mode markers,
  non-secret configured path validation, and helper token/listener settings;
  removed the global `arclink-priv/secrets/container` mount from that root
  helper.
- `tests/test_arclink_docker.py`: added regression coverage that fails if the
  helper regains broad app env inheritance, a control-secret env anchor, the
  global container secrets mount, or loses required non-secret path env and
  read-only repo access.
- `config/docker-authority-inventory.json`: upgraded the Docker authority
  inventory to the `GAP-019-X` schema and recorded the removed env/mount
  authority plus the remaining root-helper residual risk.
- `docs/docker.md`, `docs/arclink/operations-runbook.md`,
  `docs/arclink/data-safety.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: recorded `GAP-019-X` as
  local hardening while keeping `GAP-019` open for root-helper authority,
  writeable socket brokers, alert integration, and operator residual-risk
  acceptance.

Validation:

- Pre-repair Compose probe returned
  `{'inherits_broad_arclink_env': True, 'mounts_global_container_secrets': True, 'has_read_only_repo_mount': True}`.
- Post-repair Compose probe returned
  `{'inherits_broad_arclink_env': False, 'mounts_global_container_secrets': False, 'has_read_only_repo_mount': True}`.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'authority_inventory or compose or agent_process_helper'`
  passed: 7 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  33 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
  passed.
- `python3 tests/test_documentation_truths.py` passed: 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1263 passed, 6 skipped, 81 warnings in
  63.01s.

Remaining:

- `GAP-019` is reduced, not closed. `agent-process-helper` no longer receives
  broad app env values or the global container secrets mount at service
  startup, but it still has bounded root process-runner authority for
  allowlisted Docker agent commands. Writeable Docker socket brokers and the
  other root helpers remain trusted-host boundaries until stronger isolation or
  an operator residual-risk decision.

## 2026-05-22 GAP-019-W Process Helper Control-Token Env Rejection

Scope: repaired the next local `GAP-019` trusted-host slice by making
`agent-process-helper` reject ArcLink broker/helper/control token env keys at
the helper boundary. No deploy, Docker mutation, systemd, SSH fleet, provider,
payment, bot, Notion, credentialed proof, or host mutation ran.

What changed:

- `python/arclink_agent_process_helper.py`: added a helper-side denylist for
  known ArcLink broker/helper tokens plus future `ARCLINK_*_TOKEN` env keys, so
  invalid env fails during validation before one-shot or long-running agent
  subprocess execution.
- `python/arclink_docker_agent_supervisor.py`: aligned the supervisor
  process-env filter with the helper-side denylist while preserving non-secret
  agent context env such as `ARCLINK_AGENT_UID` and `ARCLINK_AGENT_GID`.
- `tests/test_arclink_docker.py`: added regression coverage for injected
  control-token env in `run_once` and `ensure_processes`, kept the
  argv/startup-log env redaction check, and broadened supervisor token-filter
  coverage.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/operations-runbook.md`, `docs/arclink/data-safety.md`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded `GAP-019-W` as local hardening while keeping
  `GAP-019` open for root-helper authority, writeable socket brokers, alert
  integration, and operator residual-risk acceptance.

Validation:

- Pre-repair reproduction confirmed `agent-process-helper` accepted
  `ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN` in a request env and forwarded it to
  a fake gateway `Popen` env.
- Post-repair reproduction returned `ok: False`, `popen_called: False`, and
  `agent process helper env must not include ArcLink control token keys`.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper or process_helper or docker_agent_supervisor_does_not_forward_helper_tokens'`
  passed: 5 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  32 tests.
- `python3 -m py_compile python/arclink_agent_process_helper.py python/arclink_docker_agent_supervisor.py`
  passed.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
  passed.
- `python3 tests/test_documentation_truths.py` passed: 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1262 passed, 6 skipped, 81 warnings in
  63.36s.

Remaining:

- `GAP-019` is reduced, not closed. The process helper no longer accepts
  ArcLink control-token env injection, but it still has bounded root
  process-runner authority for allowlisted Docker agent commands. Writeable
  Docker socket brokers and the other root helpers remain trusted-host
  boundaries until stronger isolation or an operator residual-risk decision.

## 2026-05-22 GAP-019-V Static Control Ingress Routes

Scope: repaired the next local `GAP-019` trusted-host slice by removing the
remaining read-only Docker socket discovery boundary from `control-ingress`.
No deploy, Docker mutation, systemd, SSH fleet, provider, payment, bot, Notion,
or host mutation ran.

What changed:

- `compose.yaml`: removed Traefik Docker provider discovery, removed the
  `/var/run/docker.sock:ro` mount from `control-ingress`, mounted the checked-in
  Traefik route config read-only, and kept the loopback published web port.
- `config/traefik-control.yaml`: added static Traefik file-provider routers and
  services for `/notion/webhook`, `/v1`, `/api`, and `/`, preserving the prior
  priorities and backend ports.
- `tests/test_arclink_docker.py`: added focused regression coverage for
  socket-free `control-ingress`, static route coverage, Compose socket counts,
  and authority inventory drift.
- `config/docker-authority-inventory.json`: upgraded the authority inventory to
  the `GAP-019-V` schema and removed `control-ingress` from the socket/root
  service inventory.
- `docs/docker.md`, `docs/arclink/operations-runbook.md`,
  `docs/arclink/data-safety.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: recorded `GAP-019-V` as
  local hardening while keeping `GAP-019` open for the remaining writeable
  socket brokers, root helpers, alert integration, and operator residual-risk
  decision.

Validation:

- Pre-repair reproduction confirmed `control-ingress` enabled Traefik Docker
  provider discovery and mounted `/var/run/docker.sock:ro`.
- Post-repair probe showed `control-ingress` uses the static Traefik
  file-provider route config and has no Docker socket mount.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_compose_defines_full_stack_services tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary --maxfail=1`
  passed: 2 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_control_ingress_uses_static_traefik_config_without_docker_socket tests/test_arclink_docker.py::test_control_ingress_static_routes_cover_control_api_web_llm_and_notion --maxfail=1`
  passed: 2 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  32 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
  passed.
- `python3 tests/test_documentation_truths.py` passed: 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1262 passed, 6 skipped, 81 warnings in
  63.09s.

Remaining:

- `GAP-019` is reduced, not closed. `control-ingress` no longer carries even a
  read-only Docker socket, but `deployment-exec-broker`,
  `agent-supervisor-broker`, `operator-upgrade-broker`, and
  `gateway-exec-broker` still carry writeable Docker socket residual risk, and
  `migration-capture-helper`, `agent-user-helper`, and `agent-process-helper`
  still carry root-helper authority.

## 2026-05-22 GAP-019-U Operator Upgrade Broker Split

Scope: repaired the next local `GAP-019` trusted-host slice by moving queued
Docker-mode operator upgrade execution out of the dashboard sidecar broker and
into a dedicated `operator-upgrade-broker`. No deploy, Docker mutation,
systemd, SSH fleet, provider, payment, bot, Notion, or host mutation ran.

What changed:

- `python/arclink_operator_upgrade_broker.py`: added a tokened HTTP broker for
  allowlisted `run_operator_upgrade` and `run_pin_upgrade` requests, with
  explicit path checks, raw command rejection, log confinement, and bounded
  timeout handling.
- `python/arclink_agent_supervisor_broker.py`: reduced the existing broker to
  dashboard network/proxy operations and removed queued upgrade execution.
- `python/arclink_enrollment_provisioner.py`: routed Docker-mode host upgrade
  and pin-upgrade actions through `operator-upgrade-broker`, failing closed
  when the broker URL or token is missing.
- `compose.yaml`, `bin/arclink-docker.sh`, `bin/deploy.sh`, and
  `bin/docker-entrypoint.sh`: added the new broker service and token bootstrap,
  removed the writable host repo bind from `agent-supervisor-broker`, and
  passed the operator-upgrade broker URL/token only to the supervisor path that
  needs it.
- `python/arclink_docker_agent_supervisor.py`: blocked the operator-upgrade
  broker token from per-agent process environments.
- `tests/test_arclink_docker.py`,
  `tests/test_arclink_enrollment_provisioner_regressions.py`, and
  `tests/test_deploy_regressions.py`: added focused coverage for the new broker
  boundary, Compose/inventory authority contract, Docker-mode routing, fail
  closed missing-token behavior, and token bootstrap.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/operations-runbook.md`, `docs/arclink/data-safety.md`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded `GAP-019-U` as a local hardening slice while
  keeping full `GAP-019` closure blocked on residual root/socket authority or
  an explicit operator decision.

Validation:

- Pre-repair reproduction confirmed `agent-supervisor-broker` owned both
  dashboard sidecar Docker operations and queued operator upgrades while
  mounting the host repo writable.
- Post-repair probe showed `agent-supervisor-broker` has no upgrade functions
  and no `ARCLINK_DOCKER_HOST_REPO_DIR` bind, while
  `operator-upgrade-broker` owns the upgrade functions and writable host repo
  exception.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_compose_defines_full_stack_services tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary --maxfail=1`
  passed: 2 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_operator_upgrade_broker_runs_allowlisted_operator_upgrade tests/test_arclink_docker.py::test_operator_upgrade_broker_rejects_raw_or_unsafe_requests tests/test_arclink_docker.py::test_agent_supervisor_broker_rejects_raw_commands_and_builds_dashboard_proxy --maxfail=1`
  passed: 3 tests.
- `python3 -m pytest -q tests/test_arclink_enrollment_provisioner_regressions.py::test_run_host_upgrade_routes_to_operator_upgrade_broker_in_docker_mode tests/test_arclink_enrollment_provisioner_regressions.py::test_run_host_upgrade_fails_closed_without_operator_upgrade_broker_token_in_docker_mode tests/test_arclink_enrollment_provisioner_regressions.py::test_run_pin_upgrade_action_uses_operator_upgrade_broker_in_docker_mode --maxfail=1`
  passed: 3 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
  passed: 56 tests.
- `python3 -m py_compile python/arclink_agent_supervisor_broker.py python/arclink_enrollment_provisioner.py python/arclink_operator_upgrade_broker.py python/arclink_docker_agent_supervisor.py`
  passed.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
  passed.
- `python3 tests/test_documentation_truths.py` passed: 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1260 passed, 6 skipped, 81 warnings in
  63.74s.

Remaining:

- `GAP-019` is reduced, not closed. `operator-upgrade-broker` now owns the
  explicit writable host repo exception for queued upgrades, and the dashboard
  broker is dashboard-only, but the Docker deployment/gateway/operator brokers
  still carry writeable Docker socket residual risk and root/helper authority
  still needs stronger isolation or an explicit operator residual-risk
  decision.

## 2026-05-22 GAP-019-T Read-Only Agent Host Repo Binds

Scope: repaired the next local `GAP-019` trusted-host slice by removing
unnecessary writable live-checkout access from Docker non-broker services.
No deploy, Docker mutation, systemd, SSH fleet, provider, payment, bot,
Notion, or host mutation ran.

What changed:

- `compose.yaml`: `agent-process-helper`, `agent-supervisor`, and
  `curator-refresh` now mount `ARCLINK_DOCKER_HOST_REPO_DIR` read-only while
  preserving the same host-path shape for script reads.
- `tests/test_arclink_docker.py`: added regression coverage requiring the two
  non-broker services to use `:ro`, preserving `agent-supervisor-broker` as the
  explicit writable host repo exception, and advanced the Docker authority
  inventory schema guard.
- `config/docker-authority-inventory.json`: advanced schema version 19 and
  recorded `GAP-019-T` as read-only host repo bind hardening for
  `agent-process-helper`, `agent-supervisor`, and `curator-refresh`, not full
  `GAP-019` closure.
- `docs/docker.md`, `docs/arclink/operations-runbook.md`,
  `docs/arclink/data-safety.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: recorded the narrower
  checkout-write boundary while keeping root-helper and writeable-socket broker
  residual risk open.

Validation:

- Pre-repair reproduction confirmed `agent-process-helper` and
  `agent-supervisor` mounted the host repo writable.
- Post-repair probe showed `agent-process-helper`, `agent-supervisor`, and
  `curator-refresh` ending the host repo bind in `:ro`, while
  `agent-supervisor-broker` remains writable for allowlisted queued Docker-mode
  operator upgrades.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_compose_defines_full_stack_services tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary --maxfail=1`
  passed: 2 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_process_helper_rejects_raw_commands_and_runs_allowlisted_agent_ops tests/test_arclink_docker.py::test_docker_agent_supervisor_delegates_process_launch_to_process_helper --maxfail=1`
  passed: 2 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  30 tests.
- `python3 tests/test_documentation_truths.py` passed: 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1260 passed, 6 skipped, 81 warnings in
  63.26s.

Remaining:

- `GAP-019` is reduced, not closed. `agent-user-helper`,
  `agent-process-helper`, and `migration-capture-helper` still carry bounded
  root authority in their scopes, and the deployment/gateway/agent-supervisor
  brokers still carry writeable Docker socket residual risk. The
  `agent-supervisor-broker` writable host repo exception also remains
  trusted-host authority for queued upgrades. Closure still needs stronger
  isolation or an explicit operator residual-risk decision.

## 2026-05-22 GAP-019-S Helper Configured-Root Confinement

Scope: repaired the next local `GAP-019` trusted-host slice by making
`agent-user-helper` and `agent-process-helper` reject request-scoped roots that
do not match their configured Docker roots. No deploy, Docker mutation,
systemd, SSH fleet, provider, payment, bot, Notion, or host mutation ran.

What changed:

- `python/arclink_agent_user_helper.py`: added configured
  `ARCLINK_DOCKER_AGENT_HOME_ROOT` enforcement before uid/gid assignment
  writes, directory creation, account commands, or recursive ownership repair.
- `python/arclink_agent_process_helper.py`: added configured Docker
  agent-home, repo, private-state, state, and runtime root enforcement before
  helper log creation, `subprocess.run`, or `subprocess.Popen`.
- `tests/test_arclink_docker.py`: added focused fail-closed regression tests
  for both helpers and advanced the Docker authority inventory schema guard.
- `config/docker-authority-inventory.json`: advanced schema version 18 and
  recorded `GAP-019-S` as configured-root confinement, not full `GAP-019`
  closure.
- `docs/docker.md`, `docs/arclink/operations-runbook.md`,
  `docs/arclink/data-safety.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: recorded the narrower
  helper request-path boundary while keeping root-helper and writeable-socket
  residual risk open.

Validation:

- Pre-repair reproduction confirmed both root helpers accepted request-scoped
  roots that differed from the configured Docker roots.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_user_helper_rejects_configured_home_root_mismatch tests/test_arclink_docker.py::test_agent_process_helper_rejects_configured_root_mismatch --maxfail=1`
  passed: 2 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_user_helper_rejects_configured_home_root_mismatch tests/test_arclink_docker.py::test_agent_process_helper_rejects_configured_root_mismatch tests/test_arclink_docker.py::test_agent_user_helper_rejects_raw_commands_and_unscoped_paths tests/test_arclink_docker.py::test_agent_process_helper_rejects_raw_commands_and_runs_allowlisted_agent_ops tests/test_arclink_docker.py::test_docker_agent_supervisor_delegates_process_launch_to_process_helper tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary --maxfail=1`
  passed: 6 tests.
- `python3 -m py_compile python/arclink_agent_user_helper.py python/arclink_agent_process_helper.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  30 tests.
- `python3 tests/test_documentation_truths.py` passed: 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1260 passed, 6 skipped, 81 warnings in
  63.01s.

Remaining:

- `GAP-019` is reduced, not closed. `agent-user-helper`,
  `agent-process-helper`, and `migration-capture-helper` still carry bounded
  root authority in their scopes, and the deployment/gateway/agent-supervisor
  brokers still carry writeable Docker socket residual risk. Closure still
  needs stronger isolation or an explicit operator residual-risk decision.

## 2026-05-22 GAP-019-R Agent Process Helper Env Exposure Hardening

Scope: repaired the next local `GAP-019` trusted-host slice by keeping
validated Docker agent process env values out of setpriv argv and
`agent-process-helper` startup command logs. No deploy, Docker mutation,
systemd, SSH fleet, provider, payment, bot, Notion, or host mutation ran.

What changed:

- `python/arclink_agent_process_helper.py`: `_setpriv_cmd` now reconstructs
  only the allowlisted command and privilege-drop argv. `_run_once` and
  `_ensure_processes` pass the validated env through subprocess `env=`, so env
  assignments are not written into process argv or startup command lines.
- `python/arclink_docker_agent_supervisor.py`: added a per-agent process env
  blocklist for the supervisor broker token and helper tokens before process
  specs are sent to `agent-process-helper`, while preserving those tokens for
  the caller paths that need them.
- `config/docker-authority-inventory.json`: advanced schema version 17 and
  recorded `GAP-019-R` as env exposure hardening for `agent-process-helper`,
  not full `GAP-019` closure.
- `tests/test_arclink_docker.py`: added focused redaction/filtering coverage
  and tightened the existing helper contract to prove required non-secret env
  reaches subprocesses through `env=`.
- `docs/docker.md`, `docs/arclink/operations-runbook.md`,
  `docs/arclink/data-safety.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: recorded the narrower
  boundary while keeping root-helper and writeable-socket residual risk open.

Validation:

- Pre-repair reproduction confirmed a fake token-like env value appeared in
  `state/docker/agent-process-helper/*.log` startup output through the
  reconstructed setpriv command.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_process_helper_does_not_log_or_argv_env_values tests/test_arclink_docker.py::test_docker_agent_supervisor_does_not_forward_helper_tokens_to_agent_processes --maxfail=1` passed: 2 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_process_helper_does_not_log_or_argv_env_values tests/test_arclink_docker.py::test_docker_agent_supervisor_does_not_forward_helper_tokens_to_agent_processes tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary --maxfail=1` passed: 3 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_process_helper_rejects_raw_commands_and_runs_allowlisted_agent_ops tests/test_arclink_docker.py::test_docker_agent_supervisor_delegates_process_launch_to_process_helper tests/test_arclink_docker.py::test_docker_agent_supervisor_replaces_user_systemd_units --maxfail=1` passed: 3 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  28 tests.
- `python3 -m py_compile python/arclink_agent_process_helper.py python/arclink_docker_agent_supervisor.py` passed.
- `python3 tests/test_documentation_truths.py` passed: 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1258 passed, 6 skipped, 81 warnings in
  62.66s.

Remaining:

- `GAP-019` is reduced, not closed. `agent-process-helper` still has bounded
  root authority for allowlisted setpriv agent process execution,
  `agent-user-helper` and `migration-capture-helper` still carry root authority
  in their scopes, and the deployment/gateway/agent-supervisor brokers still
  carry writeable Docker socket residual risk. Closure still needs stronger
  isolation or an explicit operator residual-risk decision.

## 2026-05-22 GAP-019-Q Agent User Helper Capability Narrowing

Scope: repaired the next local `GAP-019` trusted-host slice by replacing
`agent-user-helper` default Linux capabilities with an explicit Compose
capability boundary. No deploy, Docker mutation, systemd, SSH fleet, provider,
payment, bot, Notion, or host mutation ran.

What changed:

- `compose.yaml`: kept `agent-user-helper` as explicit root with no Docker
  socket and only the Docker agent-home bind mount, but added `cap_drop: ALL`
  plus `CHOWN`, `DAC_OVERRIDE`, and `FOWNER`.
- `config/docker-authority-inventory.json`: advanced schema version 16,
  recorded `GAP-019-Q`, and changed the helper's capability boundary to the
  exact `drop_all_add_CHOWN_DAC_OVERRIDE_FOWNER` state.
- `tests/test_arclink_docker.py`: added exact capability parsing so
  `cap_drop: ALL` with `cap_add` is not overclaimed as `all_dropped`, and added
  a focused `agent-user-helper` capability drift test.
- `docs/docker.md`, `docs/arclink/operations-runbook.md`,
  `docs/arclink/data-safety.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: recorded this as
  least-capability hardening while keeping `GAP-019` open.

Validation:

- Pre-repair reproduction confirmed `agent-user-helper` was an explicit-root
  helper with no Docker socket but default Linux capabilities in Compose and
  the authority inventory.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_user_helper_root_boundary_uses_explicit_minimum_capabilities tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary --maxfail=1` passed: 2 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_user_helper_rejects_raw_commands_and_unscoped_paths tests/test_arclink_docker.py::test_docker_agent_supervisor_requires_user_helper_before_root_user_ops tests/test_arclink_docker.py::test_compose_defines_full_stack_services --maxfail=1` passed: 3 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed: 26 tests.
- `python3 -m py_compile python/arclink_agent_user_helper.py python/arclink_docker_agent_supervisor.py`, `python3 tests/test_documentation_truths.py`, `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1256 passed, 6 skipped, 81 warnings in
  63.05s.

Remaining:

- `GAP-019` is reduced, not closed. `agent-user-helper` still has bounded root
  authority over Docker agent homes, `migration-capture-helper` and
  `agent-process-helper` still carry root authority in their scopes, and the
  deployment/gateway/agent-supervisor brokers still carry writeable Docker
  socket residual risk. Closure still needs stronger isolation or an explicit
  operator residual-risk decision.

## 2026-05-22 GAP-019-P Agent Process Helper Split

Scope: repaired the next local `GAP-019` trusted-host slice by moving
Docker-mode setpriv agent process execution and long-running gateway/dashboard
process handles out of `agent-supervisor` and into a narrow root helper. No
deploy, Docker mutation, systemd, SSH fleet, provider, payment, bot, Notion, or
host mutation ran.

What changed:

- `python/arclink_agent_process_helper.py`: added a tokened HTTP helper that
  rejects raw command fields, accepts only `run_once`, `ensure_processes`, and
  `terminate_all`, validates typed Docker agent context, reconstructs
  allowlisted install, identity, refresh, cron, gateway, and dashboard
  commands, and owns gateway/dashboard process handles.
- `python/arclink_docker_agent_supervisor.py`: removed supervisor-side
  `setpriv` command construction and `subprocess.Popen` gateway/dashboard
  lifecycle ownership; the supervisor now validates metadata, repairs MCP
  bootstrap tokens, and delegates process work to `agent-process-helper`.
- `compose.yaml`, `bin/arclink-docker.sh`, `bin/docker-entrypoint.sh`, and
  `bin/deploy.sh`: added the helper service/token wiring and removed explicit
  root from `agent-supervisor`.
- `config/docker-authority-inventory.json`, Docker/security docs, `GAPS.md`,
  `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and `mission_status.md`:
  recorded `GAP-019-P` as local hardening while keeping `GAP-019` open for the
  helper's residual root authority, remaining socket brokers, and operator risk
  acceptance.
- `tests/test_arclink_docker.py` and `tests/test_deploy_regressions.py`: added
  helper raw-command/allowlist coverage, supervisor delegation coverage,
  Compose/inventory/docs drift guards, and bootstrap token assertions.

Validation:

- Pre-repair reproduction confirmed `agent-supervisor` still declared
  `user: "0:0"`, still owned `setpriv` plus `subprocess.Popen` process launch,
  and no `agent-process-helper` existed.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_process_helper_rejects_raw_commands_and_runs_allowlisted_agent_ops tests/test_arclink_docker.py::test_docker_agent_supervisor_delegates_process_launch_to_process_helper --maxfail=1` passed: 2 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed: 25 tests.
- `python3 -m pytest -q tests/test_deploy_regressions.py::test_control_docker_bootstrap_seeds_session_hash_pepper_and_gateway_broker_token --maxfail=1` passed: 1 test.
- `python3 -m py_compile python/arclink_docker_agent_supervisor.py python/arclink_agent_process_helper.py`, `bash -n deploy.sh bin/*.sh test.sh`, `python3 tests/test_documentation_truths.py`, `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1255 passed, 6 skipped, 81 warnings in
  62.87s.

Remaining:

- `GAP-019` is reduced, not closed. The new helper still has bounded root
  authority for setpriv agent process execution, `agent-user-helper` and
  `migration-capture-helper` still carry root authority in their scopes, and
  the deployment/gateway/agent-supervisor brokers still carry writeable Docker
  socket residual risk. Closure still needs stronger isolation or an explicit
  operator residual-risk decision.

## 2026-05-21 GAP-019-N Migration Capture Helper Split

Scope: repaired the next local `GAP-019` trusted-host slice by moving
Docker-mode Pod migration file capture/materialization out of the root
`control-action-worker` and into a narrow root helper. No deploy, Docker
mutation, systemd, SSH fleet, provider, payment, bot, Notion, or host mutation
ran.

What changed:

- `python/arclink_migration_capture_helper.py`: added a tokened HTTP helper
  that rejects raw command fields, accepts only `capture` and `materialize`,
  validates deployment id, prefix, migration id, source root, target root, and
  `.migrations/<migration_id>` staging path, then performs the file copy as the
  only root boundary.
- `python/arclink_pod_migration.py`: Docker-mode non-dry-run migration capture
  now still requires `ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE=1` and
  additionally fails closed without `ARCLINK_MIGRATION_CAPTURE_HELPER_URL` and
  `ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN`.
- `compose.yaml`, `bin/arclink-docker.sh`, `bin/docker-entrypoint.sh`, and
  `bin/deploy.sh`: added the helper service/token and removed `user: "0:0"`
  from `control-action-worker`.
- `config/docker-authority-inventory.json`, Docker/security docs, `GAPS.md`,
  `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and `mission_status.md`:
  recorded `GAP-019-N` as local hardening while keeping `GAP-019` open for the
  helper's residual root authority, remaining socket brokers, root
  `agent-supervisor`, live alerting, and operator risk acceptance.
- `tests/test_arclink_pod_migration.py`, `tests/test_arclink_action_worker.py`,
  and `tests/test_arclink_docker.py`: added helper routing, fail-closed helper
  config, raw-command/path rejection, Compose, inventory, and docs coverage.

Validation:

- Pre-repair reproduction confirmed `control-action-worker` still declared
  `user: "0:0"` and no `migration-capture-helper` existed in Compose or the
  authority inventory.
- `python3 -m pytest -q tests/test_arclink_pod_migration.py::test_migration_capture_requires_helper_in_docker_mode tests/test_arclink_pod_migration.py::test_migration_capture_uses_helper_when_configured tests/test_arclink_pod_migration.py::test_migration_capture_helper_rejects_raw_commands_and_unscoped_paths tests/test_arclink_action_worker.py::test_reprovision_non_dry_run_requires_migration_capture_helper_in_docker_mode --maxfail=1` passed: 4 tests.
- `python3 -m pytest -q tests/test_arclink_action_worker.py tests/test_arclink_pod_migration.py tests/test_arclink_docker.py --maxfail=20` passed: 68 tests.
- `python3 -m py_compile python/arclink_pod_migration.py python/arclink_migration_capture_helper.py python/arclink_action_worker.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 tests/test_documentation_truths.py` passed.
- `python3 -m pytest -q tests` passed: 1251 passed, 6 skipped, 81 warnings in
  63.42s.

Remaining:

- `GAP-019` is reduced, not closed. The new helper still has root authority
  over deployment bind mounts during an approved migration window, the
  deployment/gateway/agent-supervisor brokers still carry writeable Docker
  socket residual risk, and `agent-supervisor` still owns root user-management
  authority. Closure still needs stronger isolation or an explicit operator
  residual-risk decision.

## 2026-05-21 GAP-015-B Share Notification Retry

Scope: repaired the local retry-notification slice for stalled share approvals
and recipient acceptance prompts. No Telegram/Discord network calls, live bot
proof, deploy, Docker, systemd, SSH, provider, payment, or host mutation ran.

What changed:

- `python/arclink_api_auth.py`: added
  `retry_user_share_grant_notification_api`, which authenticates the user
  session, requires CSRF, scopes retry to grant participants, rejects
  caller-supplied channel targets, returns safe no-op responses for terminal
  share states, and only queues the current waiting owner/recipient prompt.
- `python/arclink_hosted_api.py`, `docs/openapi/arclink-v1.openapi.json`, and
  `docs/API_REFERENCE.md`: added
  `POST /api/v1/user/share-grants/retry-notification` to the hosted route and
  public API contract.
- `web/src/lib/api.ts` and `web/src/app/dashboard/page.tsx`: added the web
  client method and dashboard retry action, with copy that distinguishes local
  queueing from live bot delivery proof.
- `tests/test_arclink_hosted_api.py`, `web/tests/test_api_client.mjs`, and
  `web/tests/test_page_smoke.mjs`: added coverage for auth/CSRF, participant
  scoping, no-channel fail-closed recovery, local outbox queueing after channel
  link, stale terminal no-op behavior, route parity, and dashboard action copy.
- `docs/arclink/operations-runbook.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: recorded `GAP-015-B` as
  locally repaired while keeping live Telegram/Discord delivery under
  `PG-BOTS`.

Validation:

- Pre-repair `GAP-015-B` static assertion reproduced the missing scoped retry
  API, hosted route, web client method, and dashboard retry action.
- `python3 -m pytest -q tests/test_arclink_hosted_api.py::test_user_share_grant_retry_notification_requires_session_csrf_and_scopes_participants tests/test_arclink_hosted_api.py::test_user_share_grant_retry_notification_queues_after_public_channel_link --maxfail=1` passed.
- `python3 -m pytest -q tests/test_arclink_hosted_api.py::test_user_share_grants_create_approved_accepted_linked_resources tests/test_arclink_hosted_api.py::test_user_share_grants_inbox_requires_session_and_scopes_owner_recipient tests/test_arclink_hosted_api.py::test_openapi_spec_matches_static_copy --maxfail=1` passed.
- `cd web && node --test tests/test_api_client.mjs tests/test_page_smoke.mjs`
  passed: 75 tests.
- `python3 -m pytest -q tests/test_arclink_hosted_api.py tests/test_arclink_dashboard.py --maxfail=20` passed: 97 tests.
- `cd web && npm run lint` passed.
- `python3 -m pytest -q tests` passed: 1247 passed, 6 skipped, 81 warnings in
  63.12s.

Known risks:

- Live Telegram/Discord delivery, callbacks, and retry-after-channel-link proof
  remain under `PG-BOTS`.
- `GAP-014` browser share creation policy remains unchanged.

## 2026-05-21 GAP-015-A Share Approval Inbox

Scope: reduced `GAP-015` locally without Telegram/Discord delivery proof,
browser share-link policy decisions, live bot calls, deploy, Docker, systemd,
SSH, or host mutation. Live public-bot delivery and retry behavior remain
proof/follow-up gated.

What changed:

- `python/arclink_api_auth.py` and `python/arclink_hosted_api.py`: added
  authenticated `GET /user/share-grants` with owner/recipient-scoped buckets
  for pending owner approval, waiting on owner approval, and recipient
  acceptance. No-channel notification recovery is now durable in the read
  response instead of only appearing in the create response.
- `python/arclink_dashboard.py`: added a user dashboard share-inbox summary so
  the local dashboard read model exposes pending share attention counts.
- `web/src/lib/api.ts` and `web/src/app/dashboard/page.tsx`: added the
  dashboard share approval inbox and wired existing approve, deny, accept, and
  revoke calls without making Linked resources writable or resharable.
- `tests/test_arclink_hosted_api.py`, `tests/test_arclink_dashboard.py`,
  `web/tests/test_api_client.mjs`, and `web/tests/test_page_smoke.mjs`: added
  contract coverage for auth scoping, no-channel recovery, dashboard counts,
  web client routing, and visible dashboard fallback.
- `docs/API_REFERENCE.md`, `docs/openapi/arclink-v1.openapi.json`,
  `docs/arclink/operations-runbook.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: recorded the local source
  truth while keeping live chat delivery and retry proof open.

Validation:

- Pre-repair `GAP-015-A` static assertion reproduced the missing read API,
  hosted GET route, web fetcher, dashboard inbox, and durable no-channel
  recovery.
- `python3 -m pytest -q tests/test_arclink_hosted_api.py::test_user_share_grants_inbox_requires_session_and_scopes_owner_recipient tests/test_arclink_dashboard.py::test_user_dashboard_share_inbox_counts_pending_owner_and_recipient_grants --maxfail=1` passed.
- `python3 -m pytest -q tests/test_arclink_hosted_api.py tests/test_arclink_dashboard.py --maxfail=20` passed: 95 tests.
- `cd web && npm test`, `cd web && npm run lint`, and `cd web && npm run build`
  passed.
- `python3 -m pytest -q tests` passed: 1245 passed, 6 skipped, 81 warnings in
  63.11s.

Known risks:

- Live Telegram/Discord delivery, button callbacks, and retry-after-channel-link
  behavior remain proof/follow-up gated.
- `GAP-014` browser share creation policy is unchanged.

## 2026-05-21 GAP-020 Local Restore Smoke

Scope: reduced `GAP-020` locally without reading private state, running live
GitHub, deploy, Docker, systemd, SSH, bot, provider, or host-mutating
commands. Backup recoverability is still not live-proven; this slice adds a
repeatable no-secret artifact smoke only.

What changed:

- `bin/arclink-restore-smoke.sh`: new local restore-smoke helper for
  `shared` and `agent-home` artifacts. It accepts only local sources, restores
  into a temp/provided directory, rejects remote GitHub/SSH sources, avoids
  Docker/systemd/deploy/live services, validates shared layout/SQLite artifacts,
  and rejects agent-home artifacts containing `secrets/` or `logs/`.
- `tests/test_backup_git_regressions.py`: added shared restore-smoke coverage
  for a committed local `arclink-priv` fixture with SQLite quick-check coverage
  and remote-source rejection.
- `tests/test_agent_backup_regressions.py`: now runs restore-smoke against the
  curated artifact produced by `bin/backup-agent-home.sh`.
- `docs/arclink/backup-restore.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: record the local artifact
  contract while keeping live restore proof under `PG-BACKUP`.

Validation:

- Pre-repair `GAP-020` static assertion reproduced the missing runbook command,
  shared backup restore-smoke test, and agent backup restore-smoke test.
- `bash -n bin/arclink-restore-smoke.sh` passed.
- Post-repair static assertion passed for the runbook command and both
  restore-smoke test anchors.
- `python3 tests/test_backup_git_regressions.py && python3 tests/test_agent_backup_regressions.py`
  passed.
- `python3 tests/test_documentation_truths.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1243 passed, 6 skipped, 81 warnings in
  62.56s.

Known risks:

- Live GitHub backup reads, backup activation, control DB restore,
  per-deployment volume restore, dashboard health, and ArcPod stack health
  remain `PG-BACKUP`.
- This helper proves local artifact shape only; it is not a disaster-recovery
  drill.

## 2026-05-21 GAP-013-C Backup Dashboard UX

Scope: closed the bounded local `GAP-013-C` slice without live GitHub, deploy,
Docker, systemd, SSH, bot, provider, or host-mutating commands. The dashboard
now exposes the existing backup deploy-key and write-check API rails while
keeping backup activation and restore proof gated.

What changed:

- `web/src/lib/api.ts`: added user-session/CSRF-backed client wrappers for
  `POST /api/v1/user/backup-deploy-key` and
  `POST /api/v1/user/backup-write-check`.
- `web/src/app/dashboard/page.tsx`: added backup action state, dashboard
  handlers, staged public-key display, GitHub deploy-key settings link,
  write-check status, fail-closed reason display, and guarded buttons that do
  not claim live backup activation.
- `web/src/components/ui.tsx`: treats staged/failed-closed backup states as
  visible pending states instead of unknown errors.
- `web/tests/test_page_smoke.mjs` and `web/tests/test_api_client.mjs`: prove
  the dashboard and API client expose the backup key/write-check routes,
  staged public key, settings link, and fail-closed action copy.
- `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: record the repaired local UX rail and leave
  `PG-BACKUP` open.

Validation:

- Pre-repair `GAP-013-C` static assertion reproduced the missing web API
  client routes, staged public-key display, write-check action, and web test
  coverage.
- `cd web && npm test` passed: 73 tests.
- `cd web && npm run lint` passed.
- `cd web && npm run build` passed.
- `cd web && npm run test:browser` passed: 55 passed, 3 skipped.
- `python3 -m pytest -q tests/test_arclink_dashboard.py::test_user_dashboard_backup_deploy_key_request_exposes_public_key_without_activation tests/test_arclink_dashboard.py::test_backup_verification_state_records_failed_closed_without_activation tests/test_arclink_hosted_api.py::test_user_backup_deploy_key_request_requires_session_and_csrf tests/test_arclink_hosted_api.py::test_user_backup_write_check_route_requires_session_csrf_and_never_activates --maxfail=1`
  passed: 4 tests.
- `git diff --check`, `python3 tests/test_public_repo_hygiene.py`, and
  `python3 tests/test_documentation_truths.py` passed.
- `python3 -m pytest -q tests` passed after the patch: 1241 passed, 6 skipped,
  81 warnings in 62.82s.

Known risks:

- Live GitHub deploy-key installation and write verification remain
  `PG-BACKUP`.
- Backup activation and restore proof remain `PG-BACKUP`.
- The next local slice is `GAP-020`: add a no-secret restore-smoke harness so
  backup artifacts have local recoverability coverage without claiming a live
  disaster-recovery drill.

## 2026-05-21 GAP-013-B Backup Write-Check Boundary

Scope: closed the bounded local `GAP-013-B` slice without live GitHub, deploy,
Docker, systemd, SSH, bot, provider, or host-mutating commands. The repair
keeps backup verification honest: local dashboard/API/action-worker paths can
record the GitHub write-check boundary, but unattended runs fail closed and do
not activate backup.

What changed:

- `python/arclink_dashboard.py`: added backup write-check state normalization
  and a fail-closed recorder that stores `github_write_check: failed_closed`,
  a redacted reason, `backup_activation: not_active`, and `restore_proof:
  proof_gated`.
- `python/arclink_api_auth.py` and `python/arclink_hosted_api.py`: added a
  user-session plus CSRF-gated `POST /api/v1/user/backup-write-check` route
  that returns only `backup_setup`.
- `python/arclink_action_worker.py`: added a queued `backup_write_check`
  action boundary. Without an authorized `PG-BACKUP` runner it records
  failed-closed state instead of running `git ls-remote`, `git push`, SSH, or
  backup activation.
- `tests/test_arclink_action_worker.py`, `tests/test_arclink_dashboard.py`,
  and `tests/test_arclink_hosted_api.py`: prove the fail-closed write-check
  state is durable, auth/CSRF-gated, and never marks backup active.
- `docs/API_REFERENCE.md`, `docs/openapi/arclink-v1.openapi.json`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: record the repaired local rail and remaining
  `PG-BACKUP` proof gates.

Validation:

- Pre-repair `GAP-013-B` static assertion reproduced the missing
  action-worker write-check/activation boundary.
- `python3 -m pytest -q tests/test_arclink_action_worker.py::test_backup_write_check_fails_closed_without_authorized_runner tests/test_arclink_dashboard.py::test_backup_verification_state_records_failed_closed_without_activation tests/test_arclink_hosted_api.py::test_user_backup_write_check_route_requires_session_csrf_and_never_activates --maxfail=1`
  passed: 3 tests.
- `python3 -m pytest -q tests/test_arclink_action_worker.py::test_backup_write_check_fails_closed_without_authorized_runner tests/test_arclink_dashboard.py::test_backup_verification_state_records_failed_closed_without_activation tests/test_arclink_hosted_api.py::test_user_backup_write_check_route_requires_session_csrf_and_never_activates tests/test_agent_backup_regressions.py --maxfail=20`
  passed: 10 tests.
- `python3 -m pytest -q tests/test_arclink_hosted_api.py::test_openapi_spec_route_serves_valid_contract tests/test_arclink_hosted_api.py::test_openapi_spec_matches_static_copy tests/test_arclink_hosted_api.py::test_user_backup_deploy_key_request_requires_session_and_csrf tests/test_arclink_hosted_api.py::test_user_backup_write_check_route_requires_session_csrf_and_never_activates tests/test_arclink_dashboard.py::test_user_dashboard_backup_deploy_key_request_exposes_public_key_without_activation tests/test_arclink_dashboard.py::test_backup_verification_state_records_failed_closed_without_activation tests/test_arclink_action_worker.py::test_backup_write_check_fails_closed_without_authorized_runner --maxfail=1`
  passed: 7 tests.
- `git diff --check`, `python3 tests/test_public_repo_hygiene.py`, and
  `python3 tests/test_documentation_truths.py` passed.
- `python3 -m pytest -q tests` passed after the patch: 1241 passed, 6 skipped,
  81 warnings in 62.78s.

Known risks:

- Live GitHub deploy-key installation and write verification remain
  `PG-BACKUP`.
- Backup activation and restore proof remain `PG-BACKUP`.
- Superseded by the `GAP-013-C` entry above; the next local slice is now
  `GAP-020` no-secret restore-smoke coverage.

## 2026-05-21 GAP-013-A Backup Deploy-Key Request Rail

Scope: closed the bounded local `GAP-013-A` slice without live GitHub, deploy,
Docker, systemd, SSH, bot, provider, or host-mutating commands. The repair
starts from Raven's recorded private repo and gives the authenticated dashboard
API a local staged public-key/status rail while keeping private key material
server-side and all live proof gates open.

What changed:

- `python/arclink_dashboard.py`: added server-side backup deploy-key staging
  under a configured `ARCLINK_BACKUP_KEY_STAGING_DIR`, stores only public
  key/status metadata in the control DB, and keeps GitHub write check
  `not_run`, activation `not_active`, and restore `proof_gated`.
- `python/arclink_api_auth.py` and `python/arclink_hosted_api.py`: added a
  user-session plus CSRF-gated `POST /api/v1/user/backup-deploy-key` route that
  returns only `backup_setup`.
- `tests/test_arclink_dashboard.py` and `tests/test_arclink_hosted_api.py`:
  prove the staged public key is visible, the private key/path is not returned,
  auth and CSRF are required, and the dashboard read model preserves the
  fail-closed verification state.
- `docs/API_REFERENCE.md`, `docs/openapi/arclink-v1.openapi.json`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: record the repaired local rail and the remaining
  `PG-BACKUP` boundaries.

Validation:

- `python3 -m pytest -q tests` passed before the patch: 1236 passed, 6 skipped,
  81 warnings in 62.71s.
- Pre-repair `GAP-013` static assertion reproduced the missing deploy-key rail.
- `python3 -m pytest -q tests/test_arclink_dashboard.py::test_user_dashboard_backup_deploy_key_request_exposes_public_key_without_activation tests/test_arclink_hosted_api.py::test_user_backup_deploy_key_request_requires_session_and_csrf --maxfail=1`
  passed: 2 tests.
- `python3 -m pytest -q tests/test_arclink_dashboard.py tests/test_arclink_hosted_api.py --maxfail=20`
  passed: 91 tests.
- `python3 -m pytest -q tests/test_arclink_public_bots.py tests/test_arclink_dashboard.py tests/test_arclink_hosted_api.py --maxfail=20`
  passed: 126 tests.
- `git diff --check`, `python3 tests/test_public_repo_hygiene.py`, and
  `python3 tests/test_documentation_truths.py` passed.
- `python3 -m pytest -q tests` passed after the patch: 1238 passed, 6 skipped,
  81 warnings in 62.85s.

Known risks:

- GitHub repo key installation and write verification are not live-proven.
- Backup activation and restore proof remain `PG-BACKUP`.
- This handoff's next local slice, `GAP-013-B`, is now addressed by the
  fail-closed write-check boundary above.

## 2026-05-21 GAP-013 Local Backup Status Handoff

Scope: implemented the bounded `GAP-013` local handoff repair without live
GitHub, deploy-key, restore, Docker, deploy, systemd, SSH, bot, provider, or
host-mutating commands. Raven's `/config_backup` lane already recorded
`repo_recorded_pending_key_setup`; the user dashboard now projects that same
state instead of leaving the Captain at a silent operator-only cliff.

What changed:

- `python/arclink_dashboard.py`: added a no-secret `backup_setup` read model
  for each deployment. It reads Raven backup metadata, sanitizes the
  `owner/repo`, exposes the deploy-key settings URL, marks deploy-key setup
  `pending_operator_setup`, keeps activation `not_active`, and keeps restore
  proof `proof_gated`.
- `web/src/app/dashboard/page.tsx` and `web/src/components/ui.tsx`: added
  backup status to recovery/readiness signals and the Security tab without
  claiming backup is active or recoverable.
- `tests/test_arclink_public_bots.py`, `tests/test_arclink_dashboard.py`,
  `tests/test_arclink_hosted_api.py`, and `web/tests/test_page_smoke.mjs`:
  tied Raven prep, the dashboard read model, the hosted user dashboard route,
  and the web status surface to the same pending-key-setup contract.
- `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: record `GAP-013` as locally reduced. Deploy-key
  generation/installation, GitHub write verification, activation, and restore
  proof remain `PG-BACKUP`.

Validation:

- Pre-repair `GAP-013` static assertion reproduced the split: Raven recorded
  `config_backup_public_status` while the dashboard had no matching status
  surface.
- `python3 -m pytest -q tests/test_arclink_public_bots.py::test_public_bot_config_backup_collects_private_repo_without_secret_leakage tests/test_arclink_dashboard.py::test_user_dashboard_projects_raven_backup_pending_key_setup tests/test_arclink_hosted_api.py::test_user_dashboard_requires_session_auth --maxfail=1`
  passed: 3 tests.
- `python3 -m pytest -q tests/test_arclink_public_bots.py tests/test_arclink_dashboard.py tests/test_arclink_hosted_api.py --maxfail=20`
  passed: 124 tests.
- `cd web && npm test` passed: 71 tests.
- `cd web && npm run lint` passed.
- Post-repair `GAP-013` source assertion passed: dashboard source now exposes
  pending backup setup and the restore proof guard.
- `python3 -m pytest -q tests` passed: 1236 passed, 6 skipped, 81 warnings in
  63.45s.

Known risks:

- Backup is not active locally. This pass only closes the Raven/dashboard
  pending-status split.
- The next local repair is the deploy-key generation and GitHub write
  verification rail. Restore proof remains `PG-BACKUP` and requires an
  authorized live/staging proof window.
- No live deploy, install, upgrade, Docker mutation, Stripe, Telegram, Discord,
  Notion, provider, Cloudflare, Tailscale, SSH fleet, private state, or secret
  material was used.

## 2026-05-21 GAP-010 Local Repair And GAP-013 Plan

Scope: after the requested PLAN refresh and `GAP-025` reconfirmation, build
consent was present, so this pass implemented the bounded `GAP-010` local web
copy/request-boundary repair without live or host-mutating commands.
`?channel=telegram|discord` now remains a web-scoped onboarding preference
until a real platform identity is linked.

What changed:

- `web/src/app/onboarding/page.tsx`: removed the stale promise that Raven would
  continue in Telegram/Discord after checkout from a web-only session. The hero
  now says Raven shows the next setup handoff, and the preferred-channel notice
  explicitly says the browser session is not linked to Telegram/Discord yet.
- `web/tests/test_page_smoke.mjs`: added a static guard that keeps
  `startOnboarding` web-scoped and rejects stale platform-continuation copy.
- `web/tests/browser/product-checks.spec.ts`: added desktop/mobile fake-API
  coverage for `?channel=telegram` and `?channel=discord`, including the
  visible unlinked-channel notice and the `channel: "web"` request payload.
- `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: record `GAP-010` as locally closed while keeping live
  public bot delivery under `PG-BOTS`. The next local slice is `GAP-013`, the
  Raven backup-prep/dashboard backup-status handoff.

Validation:

- `python3 -m pytest -q tests` before the web patch passed with 1235 passed,
  6 skipped, and 81 warnings in 62.60s.
- Pre-repair source assertion confirmed the mismatch: preferred-channel copy
  promised platform continuation while onboarding still started as web-only.
- Post-repair source assertion passed: stale continuation copy is gone, the
  unlinked-channel notice exists, and `startOnboarding` stays web-scoped.
- `cd web && npm test` passed: 71 tests.
- `cd web && npm run lint` passed.
- `cd web && npx playwright test tests/browser/product-checks.spec.ts --grep "Onboarding flow"`
  passed: 8 desktop/mobile fake-API checks.
- `git diff --check`, `python3 tests/test_documentation_truths.py`, and
  `python3 tests/test_public_repo_hygiene.py` passed.
- `GAP-013` reproduction passed: Raven records pending backup status while the
  dashboard lacks a matching status surface.
- `python3 -m pytest -q tests` passed after the `GAP-010` source/test/doc edits
  with 1235 passed, 6 skipped, and 81 warnings in 62.66s.
- `python3 -m pytest -q tests` passed again after final evidence-doc updates
  with 1235 passed, 6 skipped, and 81 warnings in 62.56s.

Known risks:

- `GAP-010` is locally closed for web copy/request behavior only. Live
  Telegram/Discord delivery, callbacks, command registration, and selected-agent
  bridge delivery remain `PG-BOTS`.
- `GAP-025` remains locally closed after this pass, but must be rerun after the
  next source/test slice.
- No live deploy, install, upgrade, Docker mutation, Stripe, Telegram, Discord,
  Notion, provider, Cloudflare, Tailscale, SSH fleet, private state, or secret
  material was used.

## 2026-05-21 GAP-009 Local Repair And GAP-010 Plan

Scope: implemented the bounded `GAP-009` local web storage repair without live
Stripe, provider, bot, Docker, deploy, systemd, SSH, or host-mutating commands.
`GAP-025` was rechecked with the broad no-secret Python suite after the web
patch. Browser claim/cancel proof tokens no longer persist in durable
`localStorage`.

What changed:

- `web/src/app/onboarding/page.tsx`: split durable resume state from proof
  state. The `localStorage` resume snapshot now contains only non-proof form
  and session context; `claimToken` and `cancelToken` are stored under
  session-scoped proof storage.
- `web/src/app/checkout/success/page.tsx`: reads the claim proof from
  session-scoped storage and clears proof plus resume state after a successful
  browser claim.
- `web/src/app/checkout/cancel/page.tsx`: reads cancel proof from
  session-scoped storage, clears proof material after the cancel attempt, and
  rewrites successful-cancel resume state without stale checkout/session proof.
- `web/tests/test_page_smoke.mjs`: added static assertions that durable resume
  state does not include browser proof tokens and that success/cancel cleanup
  paths use the proof storage key.
- `web/tests/browser/product-checks.spec.ts`: added fake-API desktop/mobile
  checks for token placement, checkout-success cleanup, and checkout-cancel
  cleanup.
- `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded `GAP-009` as locally closed and selected
  `GAP-010` as the next local slice.

Validation:

- Reproduction before source patch: a focused `node` source assertion failed
  because `claimToken`/`cancelToken` touched the `localStorage` resume restore
  and persist paths.
- `cd web && npm test` passed: 70 tests.
- `cd web && npm run lint` passed.
- `cd web && npx playwright test tests/browser/product-checks.spec.ts --grep "Onboarding flow"`
  passed: 6 desktop/mobile fake-API checks.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed with 1235 passed, 6 skipped, and
  81 warnings in 62.54s.

Known risks:

- `GAP-009` is locally closed for long-lived browser persistence. A future
  product/security design may still replace session-scoped proof storage with
  HttpOnly server-bound handoff or a different cross-tab recovery model.
- The next local slice is `GAP-010`: preferred-channel web onboarding copy
  still must stop implying Telegram/Discord continuation when the web session
  has no real platform identity. Live public bot delivery remains `PG-BOTS`.

## 2026-05-21 GAP-016 Local Repair And GAP-009 Plan

Scope: after the requested PLAN refresh, build consent was present, so this
pass implemented the bounded `GAP-016` local repair without live or
host-mutating commands. `GAP-025` was checked first, the MCP/plugin mismatch was
reproduced with a failing assertion, then source, tests, and handoff docs were
aligned. The active next slice is now `GAP-009`.

What changed:

- `python/arclink_mcp_server.py`: `shares.request` now returns a concrete
  `copy_duplicate_policy`, destination roots `vault`/`workspace`, and a
  human-readable policy detail instead of `policy_question`.
- `plugins/hermes-agent/arclink-managed-context/__init__.py`: the
  `shares.request` recipe now states that accepted Linked resources can be
  copied/duplicated only into the recipient's owned Vault or Workspace roots.
- `tests/test_arclink_mcp_schemas.py` and `tests/test_arclink_plugins.py`:
  added MCP response/description and managed-context recipe assertions to keep
  the copy/duplicate rule aligned with the existing Drive/Code Linked-root
  behavior proof.
- `GAPS.md` and `USER_JOURNEY.md`: recorded `GAP-016` as locally closed while
  leaving live bot delivery and browser share UI in their separate gates.
- `IMPLEMENTATION_PLAN.md` and `mission_status.md`: moved the active plan to
  `GAP-009`, the browser proof-token persistence slice.

Validation:

- Reproduction before source patch:
  `python3 -m pytest -q tests/test_arclink_mcp_schemas.py::test_agent_share_request_tool_creates_scoped_pending_grant --maxfail=1`
  failed on `copy_duplicate_policy: policy_question`.
- `python3 -m pytest -q tests/test_arclink_mcp_schemas.py::test_agent_share_request_tool_creates_scoped_pending_grant tests/test_arclink_plugins.py::test_arclink_drive_and_code_expose_read_only_linked_root --maxfail=20`
  passed with 2 tests in 0.40s.
- `python3 -m pytest -q tests/test_arclink_plugins.py::test_arclink_managed_context_injects_tool_recipe_cards_on_intent_triggers tests/test_arclink_mcp_schemas.py::test_hot_tool_descriptions_carry_when_to_call_guidance --maxfail=20`
  passed with 2 tests in 0.12s.
- `python3 -m pytest -q tests/test_arclink_plugins.py tests/test_arclink_mcp_schemas.py --maxfail=20`
  passed with 45 tests in 4.12s.
- `git diff --check`, `python3 tests/test_public_repo_hygiene.py`, and
  `python3 tests/test_documentation_truths.py` passed.
- `python3 -m pytest -q tests` passed with 1235 passed, 6 skipped, and
  81 warnings in 63.01s.

Known risks:

- `GAP-016` is locally closed only for the repository contract. Live public bot
  delivery remains `PG-BOTS`, and browser share-link UX remains tracked by
  `GAP-014`/`GAP-015`.
- The next `GAP-009` slice must avoid live Stripe or external checkout and keep
  any browser proof local/fake-API only.

## 2026-05-21 GAP-016 Plan Refresh Attempt 8

Scope: reran the ArcLink Dream Buildout PLAN phase after retry guidance said
the previous attempt passed review but failed post-plan handoff validation.
This pass preserved existing source work, checked `GAP-025` first with the
broad local Python suite, kept `GAP-016` as the bounded next build slice, and
refreshed stale Attempt 7 handoff wording without claiming a product-code
repair.

What changed:

- `IMPLEMENTATION_PLAN.md`: updated the active repair plan to Attempt 8
  evidence, keeping checked-off atlas work, the unchecked `GAP-016` current
  task, exact focused tests, local/live/policy boundaries, owner surface,
  files, reproduction command, and success criteria.
- `mission_status.md`: recorded the Attempt 8 GAP-025 and GAP-016 baseline
  evidence at the top-level handoff.
- `research/RESEARCH_SUMMARY.md` and `research/STACK_SNAPSHOT.md`: refreshed
  the PLAN-phase posture and stack timestamp for this rerun.
- `research/BUILD_COMPLETION_NOTES.md`: added this completion entry.

Validation:

- `python3 -m pytest -q tests` passed with 1235 passed, 6 skipped, and
  81 warnings in 63.06s.
- `python3 -m pytest -q tests/test_arclink_mcp_schemas.py::test_agent_share_request_tool_creates_scoped_pending_grant tests/test_arclink_plugins.py::test_arclink_drive_and_code_expose_read_only_linked_root --maxfail=20`
  passed with 2 tests in 0.35s.
- `python3 -m pytest -q tests/test_arclink_plugins.py tests/test_arclink_mcp_schemas.py --maxfail=20`
  passed with 45 tests in 4.09s.
- `git diff --check`, `python3 tests/test_public_repo_hygiene.py`, and
  `python3 tests/test_documentation_truths.py` passed.

Known risks:

- This was a planning and handoff-artifact repair only. `GAP-016` remains
  unchecked for BUILD until the MCP response, managed-context guidance, tests,
  and any stale runbook wording are aligned.
- `GAP-025` remains locally closed only while `python3 -m pytest -q tests`
  stays green after future source/test edits.
- No live deploy, install, upgrade, Docker mutation, Stripe, Telegram, Discord,
  Notion, provider, Cloudflare, Tailscale, SSH fleet, private state, or secret
  material was used.

## 2026-05-21 GAP-016 Plan Refresh Attempt 7

Scope: reran the ArcLink Dream Buildout PLAN phase after the retry guidance
reported post-plan handoff/intelligence validation failure. This pass preserved
existing source work, checked `GAP-025` first by source/test evidence, selected
the current bounded local next slice (`GAP-016`), and repaired stale handoff
artifacts without claiming a product-code repair.

What changed:

- `IMPLEMENTATION_PLAN.md`: refreshed the active repair plan around `GAP-016`
  with the owner surface, files to inspect/change, local/live/policy boundary,
  exact focused tests, reproduction command, and success criteria.
- `mission_status.md`: updated the top-level status from the completed
  `GAP-019-L` build posture to the current `GAP-016` plan-ready handoff.
- `research/RESEARCH_SUMMARY.md`: replaced the completed `GAP-019-L` handoff
  with the current PLAN evidence and `GAP-016` build target.
- `research/STACK_SNAPSHOT.md`: replaced the stale low-confidence Node-only
  snapshot with the actual Bash/Python/Next.js/Hermes-plugin stack for this
  mission.

Validation:

- `python3 -m pytest -q tests/test_arclink_mcp_schemas.py::test_agent_share_request_tool_creates_scoped_pending_grant tests/test_arclink_plugins.py::test_arclink_drive_and_code_expose_read_only_linked_root --maxfail=20`
  passed with 2 tests.
- `python3 -m pytest -q tests/test_arclink_plugins.py tests/test_arclink_mcp_schemas.py --maxfail=20`
  passed with 45 tests in 4.08s.
- `git diff --check`, `python3 tests/test_public_repo_hygiene.py`, and
  `python3 tests/test_documentation_truths.py` passed after the handoff
  artifact edits.
- `python3 -m pytest -q tests` passed with 1235 passed, 6 skipped, and
  81 warnings in 62.91s.

Known risks:

- This was a planning and handoff-artifact repair only. `GAP-016` remains
  unchecked for BUILD until the MCP response, managed-context guidance, tests,
  and any stale runbook wording are aligned.
- `GAP-025` remains locally closed only while `python3 -m pytest -q tests`
  stays green after future source/test edits.
- No live deploy, install, upgrade, Docker mutation, Stripe, Telegram, Discord,
  Notion, provider, Cloudflare, Tailscale, SSH fleet, private state, or secret
  material was used.

## 2026-05-21 GAP-019-M Docker/Root Incident Controls

Scope: locally repaired the next `GAP-019` residual trusted-host slice by
turning the remaining Docker socket/root response path into source-owned
inventory, docs, and tests. No deploy, Docker up/down/reconcile, systemd,
Stripe, Telegram, Discord, live Notion, provider, Cloudflare, Tailscale, SSH
fleet, private state, or secret material was used.

What changed:

- `config/docker-authority-inventory.json`: bumped the schema to 12, added a
  `GAP-019-M` summary, and added incident controls for
  `deployment-exec-broker`, `gateway-exec-broker`,
  `agent-supervisor-broker`, `control-action-worker`, and `agent-supervisor`.
- `tests/test_arclink_docker.py`: Docker authority tests now fail if a
  remaining writeable socket writer or explicit root helper lacks monitored
  signals, status/log/audit locations, triage steps, fail-closed action, and a
  `GAP-019` escalation boundary.
- `docs/docker.md`, `docs/arclink/data-safety.md`,
  `docs/arclink/operations-runbook.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: record the incident
  controls while keeping the P0 trusted-host boundary open.

Validation:

- `python3 -m pytest -q tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary tests/test_arclink_docker.py::test_docker_docs_cover_socket_and_private_state_boundaries --maxfail=20`
  passed with 2 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed with
  21 tests.
- `python3 -m pytest -q tests/test_arclink_plugins.py tests/test_arclink_mcp_schemas.py --maxfail=20`
  passed with 45 tests as the next `GAP-016` baseline.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and touched-file
  `git diff --check` passed.
- `python3 -m pytest -q tests` passed with 1235 passed and 6 skipped.

Known risks:

- `GAP-019` is reduced, not closed. The deployment, gateway, and agent
  supervisor brokers still carry writeable Docker socket residual risk, and the
  action worker plus agent supervisor still have root helper boundaries pending
  stronger isolation or an operator residual-risk decision.

## 2026-05-21 GAP-019-L Agent Supervisor Metadata Guard

Scope: repaired the next local `GAP-019` root `agent-supervisor`
user-management slice after rechecking the focused owner family. No live
deploy, install, upgrade, Docker up/down/reconcile, Stripe, Telegram, Discord,
live Notion, provider, Cloudflare, Tailscale, SSH fleet, private state, or
secret material was used.

What changed:

- `python/arclink_docker_agent_supervisor.py`: active-agent metadata now fails
  closed before root user-management, broker requests, or subprocess launch
  when `agent_id`, `unix_user`, `hermes_home`, Docker agent home, workspace,
  supervisor log/process key, runuser env key, or command argument is unsafe.
- `tests/test_arclink_docker.py`: added a focused guard test that proves unsafe
  metadata is rejected before monkeypatched root operations are reached.
- `config/docker-authority-inventory.json`, Docker/security docs, `GAPS.md`,
  `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: record
  the guard as local hardening while keeping `GAP-019` open for helper splits,
  incident controls, or operator residual-risk acceptance.

Validation:

- Pre-edit focused probe failed as expected: unsafe `unix_user` reached
  monkeypatched `id`, `useradd`, and recursive `chown` command construction.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_docker_agent_supervisor_rejects_unsafe_metadata_before_root_ops`
  passed with 1 test.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_agent_user_services.py tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
  passed with 51 tests.
- `python3 tests/test_documentation_truths.py`, `python3 tests/test_public_repo_hygiene.py`,
  `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 -m py_compile python/arclink_docker_agent_supervisor.py`, and
  `git diff --check` passed.
- `python3 -m pytest -q tests` passed with 1235 passed and 6 skipped.

Known risks:

- `GAP-019` is reduced, not closed. The root supervisor still performs
  validated useradd/chown/runuser work, and the deployment, gateway, and agent
  supervisor brokers still carry writeable Docker socket residual risk.

## 2026-05-21 GAP-019-L Plan Refresh (Attempt 6)

Scope: reran the ArcLink Dream Buildout PLAN phase for Attempt 6 after the
prior pass still failed post-plan machine validation. This pass preserved the
selected bounded local next slice (`GAP-019-L`), rechecked `GAP-025` first, and
refreshed the handoff wording without claiming a source repair.

What changed:

- `IMPLEMENTATION_PLAN.md`: refreshed broad-suite and owner-family evidence for
  Attempt 6, kept `GAP-019-L` as the unchecked build slice, and retained the
  concrete owner surface, files, reproduction command, safety boundary, first
  fail-closed proof, and success criteria.
- `mission_status.md`: updated the plan-ready status from Attempt 5 evidence to
  Attempt 6 evidence.

Attempt 6 validation run:

- `python3 -m pytest -q tests` passed with 1234 passed and 6 skipped.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_agent_user_services.py tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
  passed with 50 tests.
- `git diff --check` passed.
- `python3 tests/test_documentation_truths.py` passed with 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.

Known risks:

- This was a planning and handoff-artifact repair only. No source behavior was
  changed, and `GAP-019-L` remains unchecked for BUILD.
- No live deploy, install, upgrade, Docker mutation, Stripe, Telegram, Discord,
  Notion, provider, Cloudflare, Tailscale, SSH fleet, private state, or secret
  material was used.

## 2026-05-21 GAP-019-L Plan Refresh (Attempt 5)

Scope: reran the ArcLink Dream Buildout PLAN phase for Attempt 5 after the
previous attempt failed post-plan handoff/intelligence validation despite GO
reviews. This pass preserved existing work, rechecked `GAP-025` first, selected
the same bounded local next slice (`GAP-019-L`), and refreshed the handoff text
so the next BUILD step is concrete without claiming a source repair.

What changed:

- `IMPLEMENTATION_PLAN.md`: refreshed the Attempt 5 broad-suite evidence,
  recorded the current `GAP-019-L` owner-family baseline, and made the next
  build step explicit about owner surface, files, focused reproduction command,
  first fail-closed proof to add, local/live/policy boundary, and success
  criteria.
- `research/RESEARCH_SUMMARY.md`: replaced the stale LLM Router summary with
  the current ArcLink Dream Buildout posture and `GAP-019-L` handoff.
- `research/STACK_SNAPSHOT.md`: replaced the stale low-confidence Node-only
  stack guess with the actual hybrid Bash/Python/Next.js ArcLink control-plane
  stack relevant to this mission.
- `mission_status.md`: recorded that the next local slice is now
  `GAP-019-L`, with live and policy gates still open.

Attempt 5 validation run:

- `python3 -m pytest -q tests` passed with 1234 passed and 6 skipped.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_agent_user_services.py tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
  passed with 50 tests.
- `git diff --check` passed after the plan/handoff edits.
- `python3 tests/test_documentation_truths.py` passed with 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.

Known risks:

- This was a planning and handoff-artifact repair only. No source behavior was
  changed, and `GAP-019` remains open until `GAP-019-L` or a later helper/root
  split actually lands.
- No live deploy, install, upgrade, Docker mutation, Stripe, Telegram, Discord,
  Notion, provider, Cloudflare, Tailscale, SSH fleet, private state, or secret
  material was used.

## 2026-05-21 GAP-019-K Root Capture Opt-In Guard

Scope: repaired the next local `GAP-019` action-worker root migration-capture
surface after confirming `GAP-025` was locally closed by source/test evidence.
No live deploy, install, upgrade, Docker up/down/reconcile, Stripe, Telegram,
Discord, live Notion, provider, Cloudflare, Tailscale, SSH fleet, private
state, or secret material was used.

What changed:

- `python/arclink_pod_migration.py`: non-dry-run Pod migration capture now
  fails closed unless `ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE=1` is
  set for an operator-controlled migration window. Dry-run planning still works
  without that root-capture opt-in. Capture source, target, and staging paths
  are validated as deployment-scoped ArcLink state roots before any root file
  copy starts.
- `compose.yaml`: `control-action-worker` exposes the root-capture opt-in as an
  explicit default-off environment control while continuing to delegate local
  Docker lifecycle/apply calls to `deployment-exec-broker`.
- `tests/test_arclink_pod_migration.py`,
  `tests/test_arclink_action_worker.py`, and `tests/test_arclink_docker.py`:
  added fail-closed coverage for missing opt-in, unscoped capture paths,
  action-worker reprovision failure, and authority inventory drift.
- `config/docker-authority-inventory.json`, Docker/security docs, `GAPS.md`,
  `USER_JOURNEY.md`, `mission_status.md`, and `IMPLEMENTATION_PLAN.md`: record
  `GAP-019-K` as a local guard while keeping the action-worker root boundary
  open for a dedicated helper or explicit residual-risk decision.

Validation run:

- Focused pre-repair probe failed with:
  `MISSING: non-dry-run Pod migration capture ran without explicit root-capture opt-in`.
- `python3 -m pytest -q tests/test_arclink_pod_migration.py tests/test_arclink_action_worker.py tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary --maxfail=20`
  passed with 43 tests.
- `python3 -m py_compile python/arclink_pod_migration.py python/arclink_action_worker.py`
  passed.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
  passed.
- `python3 tests/test_documentation_truths.py` passed with 7 tests.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed with 1234 passed and 6 skipped.

Known risks:

- `GAP-019` is still open. The root action worker cannot run non-dry-run
  migration capture accidentally, but an operator-enabled capture window still
  gives the worker root read/write access to deployment bind mounts.
- The next local slice is either the `agent-supervisor` user-management
  root helper/no-go or incident-response controls for the remaining Docker
  brokers.

## 2026-05-21 GAP-019-J Operator Upgrade Broker Routing

Scope: repaired the next local `GAP-019` Docker-mode operator upgrade authority
surface after confirming `GAP-025` was locally closed by source/test evidence.
No live deploy, install, upgrade, Docker up/down/reconcile, Stripe, Telegram,
Discord, live Notion, provider, Cloudflare, Tailscale, SSH fleet, private
state, or secret material was used.

What changed:

- `python/arclink_enrollment_provisioner.py`: Docker-mode queued host upgrades
  and pinned-component upgrade apply/final-upgrade calls now require
  `ARCLINK_AGENT_SUPERVISOR_BROKER_URL` and token. Missing broker config fails
  closed before any host-mutating command is run.
- `python/arclink_agent_supervisor_broker.py`: added allowlisted
  `run_operator_upgrade` and `run_pin_upgrade` operations, raw command
  rejection, host repo/private path validation, pin component/kind/target
  validation, and private `state/operator-actions` log confinement.
- `compose.yaml`: keeps `agent-supervisor` socket-free and gives
  `agent-supervisor-broker` the live host checkout mount needed for allowlisted
  Docker-mode upgrade execution without overlaying the image repo.
- `config/docker-authority-inventory.json`, Docker/security docs, `GAPS.md`,
  `USER_JOURNEY.md`, `mission_status.md`, and `IMPLEMENTATION_PLAN.md`: record
  `GAP-019-J` as a local authority reduction while keeping the broker's
  writeable Docker socket and host checkout mount residual risk open.

Validation run:

- `python3 -m pytest -q tests/test_arclink_enrollment_provisioner_regressions.py::test_run_host_upgrade_routes_to_docker_upgrade_in_docker_mode tests/test_arclink_enrollment_provisioner_regressions.py::test_run_host_upgrade_fails_closed_without_broker_token_in_docker_mode tests/test_arclink_enrollment_provisioner_regressions.py::test_run_pin_upgrade_action_uses_agent_supervisor_broker_in_docker_mode tests/test_arclink_docker.py::test_compose_defines_full_stack_services tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary tests/test_arclink_docker.py::test_agent_supervisor_broker_runs_allowlisted_operator_upgrade tests/test_arclink_docker.py::test_agent_supervisor_broker_rejects_raw_or_unsafe_operator_upgrade_requests --maxfail=20`
  passed with 7 tests.
- `python3 -m py_compile python/arclink_enrollment_provisioner.py python/arclink_agent_supervisor_broker.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_enrollment_provisioner_regressions.py tests/test_arclink_docker.py --maxfail=20`
  passed with 46 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
  passed.
- `python3 tests/test_documentation_truths.py` passed with 7 tests.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed with 1231 passed and 6 skipped.
- `python3 -m pytest -q tests/test_arclink_action_worker.py tests/test_arclink_pod_migration.py tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary --maxfail=20`
  passed with 40 tests as the `GAP-019-K` baseline.

Known risks:

- `GAP-019` is still open. The root supervisor no longer runs raw Docker-mode
  operator upgrade subprocesses, but `agent-supervisor-broker` still carries
  direct Docker socket authority and now mounts the live host checkout for
  allowlisted upgrade execution.
- The next local slice is `GAP-019-K`: inspect the `control-action-worker` Pod
  migration capture root boundary and either split it behind a narrow helper or
  record an explicit no-go/residual-risk contract, without running live Docker
  mutation.

## 2026-05-21 GAP-019-I Agent Supervisor Broker Split

Scope: repaired the next local `GAP-019` Docker-mode agent supervisor authority
surface after confirming `GAP-025` was locally closed by source/test evidence.
No live deploy, install, upgrade, Docker up/down/reconcile, Stripe, Telegram,
Discord, live Notion, provider, Cloudflare, Tailscale, SSH fleet, private
state, or secret material was used.

What changed:

- `compose.yaml`: removed the Docker socket mount and socket group from
  `agent-supervisor`, added `agent-supervisor-broker` as the dedicated
  non-root socket owner for dashboard network/proxy sidecar operations, and
  wired broker URL/token dependencies into the supervisor.
- `python/arclink_docker_agent_supervisor.py`: dashboard network creation,
  supervisor network attachment, dashboard proxy start, and proxy removal now
  go through a tokened broker request instead of direct Docker subprocess
  calls from the root supervisor.
- `python/arclink_agent_supervisor_broker.py`: added the bounded broker
  contract for `ensure_dashboard_network`, `ensure_dashboard_proxy`, and
  `remove_dashboard_proxy`, rejecting raw commands and validating agent ids,
  deterministic network/container names, backend IPs, ports, and access-file
  confinement under `ARCLINK_DOCKER_CONTAINER_PRIV_DIR`.
- `bin/docker-entrypoint.sh`, `bin/arclink-docker.sh`, `bin/deploy.sh`, and
  `tests/test_deploy_regressions.py`: generate and require a durable
  `ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN`.
- `config/docker-authority-inventory.json`, Docker/security docs, `GAPS.md`,
  `USER_JOURNEY.md`, `mission_status.md`, and `IMPLEMENTATION_PLAN.md`: record
  `GAP-019-I` as a local authority reduction while keeping the broker socket
  and supervisor root user-management residual risks open.

Validation run:

- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed with
  18 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_agent_user_services.py tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
  passed with 46 tests.
- `python3 -m pytest -q tests/test_deploy_regressions.py::test_control_docker_bootstrap_seeds_session_hash_pepper_and_gateway_broker_token`
  passed.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
  passed.
- `python3 tests/test_documentation_truths.py` passed with 7 tests.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed with 1227 passed and 6 skipped.
- `python3 -m pytest -q tests/test_arclink_enrollment_provisioner_regressions.py::test_run_host_upgrade_routes_to_docker_upgrade_in_docker_mode tests/test_arclink_docker.py::test_docker_component_upgrade_apply_loads_upstream_env_from_docker_config tests/test_arclink_docker.py::test_compose_defines_full_stack_services --maxfail=20`
  passed with 3 tests as the `GAP-019-J` baseline.

Known risks:

- `GAP-019` is still open. `agent-supervisor` no longer owns the Docker socket
  in Docker mode, but it still runs as root for container-local Unix user
  creation, chown, and runuser-based agent refresh/install. The new
  `agent-supervisor-broker`, plus `deployment-exec-broker` and
  `gateway-exec-broker`, still carry direct Docker socket residual risk.
- The next local slice is `GAP-019-J`: inspect the Docker-mode operator upgrade
  path from the enrollment provisioner and either move the control-stack
  upgrade operation behind a helper/broker or record an exact no-go split,
  without running live Docker mutation.

## 2026-05-21 GAP-019-H Action Worker Socket Removal

Scope: repaired the next local `GAP-019` Control Node admin-action authority
surface after confirming `GAP-025` was locally closed by source/test evidence.
No live deploy, install, upgrade, Docker up/down/reconcile, Stripe, Telegram,
Discord, live Notion, provider, Cloudflare, Tailscale, SSH fleet, private
state, or secret material was used.

What changed:

- `compose.yaml`: removed the Docker socket mount and socket group from
  `control-action-worker`, wired the deployment exec broker URL/token into the
  worker, and made the worker depend on `deployment-exec-broker`.
- `python/arclink_executor.py`: Docker-mode local executors now fail closed
  unless `ARCLINK_DEPLOYMENT_EXEC_BROKER_URL` and
  `ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN` are configured.
- `tests/test_arclink_action_worker.py`, `tests/test_arclink_executor.py`, and
  `tests/test_arclink_docker.py`: added regression coverage for the broker
  requirement, Compose socket removal, and authority inventory drift guard.
- `config/docker-authority-inventory.json`, Docker/security docs, `GAPS.md`,
  `USER_JOURNEY.md`, `mission_status.md`, and `IMPLEMENTATION_PLAN.md`: record
  `GAP-019-H` as a local authority reduction while keeping the root Pod
  migration capture boundary and remaining broker/socket risks open.

Validation run:

- `python3 -m pytest -q tests/test_arclink_action_worker.py tests/test_arclink_pod_migration.py tests/test_arclink_docker.py tests/test_arclink_executor.py --maxfail=20`
  passed with 95 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
  passed.
- `python3 tests/test_documentation_truths.py` passed with 7 tests.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed with 1226 passed and 6 skipped.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_agent_user_services.py tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
  passed with 45 tests as the `GAP-019-I` baseline.

Known risks:

- `GAP-019` is still open. `control-action-worker` no longer owns the Docker
  socket in Docker mode, but it still runs as root for Pod migration capture
  until a migration helper split lands or the operator accepts that residual
  boundary. At this point in the sequence, `deployment-exec-broker`,
  `gateway-exec-broker`, and `agent-supervisor` still carried direct Docker
  socket residual risk; `GAP-019-I` later removed the supervisor socket.
- The then-next local slice was `GAP-019-I`: inspect the `agent-supervisor`
  dashboard Docker boundary and either move one bounded operation behind a
  helper or record an exact no-go split, without running live Docker mutation.

## 2026-05-21 GAP-019-G Deployment Exec Broker Split

Scope: repaired the next local `GAP-019` Control Node provisioning authority
surface after confirming `GAP-025` was locally closed by source/test evidence.
No live deploy, install, upgrade, Docker up/down/reconcile, Stripe, Telegram,
Discord, live Notion, provider, Cloudflare, Tailscale, SSH fleet, private
state, or secret material was used.

What changed:

- `python/arclink_executor.py`: added `BrokeredDockerComposeRunner` for local
  executor requests when `ARCLINK_DEPLOYMENT_EXEC_BROKER_URL` and token are
  configured. It maps known Compose args to operation kinds and never sends raw
  command args to the broker.
- `python/arclink_deployment_exec_broker.py`: added a dedicated broker that
  rejects raw commands, validates deployment id, generated project name, and
  `ARCLINK_STATE_ROOT_BASE` config paths, then reconstructs allowlisted Compose
  `up`, `ps`, and `down` operations locally.
- `python/arclink_sovereign_worker.py`: direct service-health `ps` calls now
  pass deployment id through the Docker runner contract.
- `compose.yaml`: removed the Docker socket and socket group from
  `control-provisioner`, added `deployment-exec-broker` as the dedicated socket
  owner, and wired the generated broker token into the broker/client pair.
- `bin/docker-entrypoint.sh`, `bin/arclink-docker.sh`, and `bin/deploy.sh`:
  generate and preserve `ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN` in private
  Docker runtime config.
- `config/docker-authority-inventory.json`, Docker/security docs, `GAPS.md`,
  `USER_JOURNEY.md`, `mission_status.md`, and `IMPLEMENTATION_PLAN.md`: record
  `GAP-019-G` as a local broker split while keeping the broker's direct Docker
  socket authority open as trusted-host residual risk.

Validation run:

- `python3 -m pytest -q tests/test_arclink_executor.py` passed with 39 tests.
- `python3 -m pytest -q tests/test_arclink_executor.py tests/test_arclink_sovereign_worker.py tests/test_arclink_docker.py --maxfail=20`
  passed with 75 tests.
- `python3 -m pytest -q tests/test_deploy_regressions.py --maxfail=20`
  passed with 117 tests.
- `python3 tests/test_documentation_truths.py` passed with 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_executor.py python/arclink_deployment_exec_broker.py python/arclink_sovereign_worker.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_action_worker.py tests/test_arclink_pod_migration.py tests/test_arclink_docker.py --maxfail=20`
  passed with 55 tests as the next-slice baseline.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed with 1225 passed and 6 skipped.

Known risks:

- `GAP-019` is still open. `control-provisioner` no longer owns the Docker
  socket in Docker mode, but `deployment-exec-broker` still has
  host-root-equivalent writeable socket access until the operator accepts that
  residual boundary or replaces it with stronger helper/isolation.
- The next local slice is `GAP-019-H`: narrow or explicitly no-go the
  `control-action-worker` lifecycle/migration helper split, without running
  live Docker mutation.

## 2026-05-21 GAP-019-F Gateway Exec Broker Split

Scope: repaired the next local `GAP-019` public-bot delivery authority surface
after confirming `GAP-025` was already locally closed by source/test evidence.
No live deploy, install, upgrade, Docker up/down/reconcile, Stripe, Telegram,
Discord, live Notion, provider, Cloudflare, Tailscale, SSH fleet, private
state, or secret material was used.

What changed:

- `python/arclink_gateway_exec_broker.py`: added a dedicated broker that rejects
  raw commands, accepts only a bounded deployment-scoped gateway exec request,
  validates deployment id/prefix as safe path segments, reconstructs the
  `hermes-gateway` Docker exec command, and validates it before subprocess
  execution.
- `python/arclink_notification_delivery.py`: `notification-delivery` now sends
  brokered public-Agent gateway exec requests when the broker URL is configured;
  detached bridge jobs can carry broker requests without storing Docker command
  authority in the notification worker.
- `compose.yaml`: removed the Docker socket and socket group from
  `notification-delivery`, added `gateway-exec-broker` as the dedicated socket
  owner, and wired the generated broker token into the broker/client pair.
- `bin/docker-entrypoint.sh`, `bin/arclink-docker.sh`, and `bin/deploy.sh`:
  generate and preserve `ARCLINK_GATEWAY_EXEC_BROKER_TOKEN` in private Docker
  runtime config.
- `config/docker-authority-inventory.json`, Docker/security docs, `GAPS.md`,
  `USER_JOURNEY.md`, `mission_status.md`, and `IMPLEMENTATION_PLAN.md`: record
  `GAP-019-F` as a local broker split while keeping the broker's direct Docker
  socket authority open as trusted-host residual risk.

Validation run:

- `python3 -m pytest -q tests/test_arclink_notification_delivery.py tests/test_arclink_docker.py --maxfail=20`
  passed with 39 tests.
- `python3 -m pytest -q tests/test_deploy_regressions.py --maxfail=20`
  passed with 117 tests.
- `python3 tests/test_documentation_truths.py` passed with 7 tests.
- `python3 -m py_compile python/arclink_notification_delivery.py python/arclink_gateway_exec_broker.py`
  passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed with 1223 passed and 6 skipped.

Known risks:

- `GAP-019` is still open. `notification-delivery` no longer owns the Docker
  socket, but `gateway-exec-broker` still has host-root-equivalent writeable
  socket access until the operator accepts that residual boundary or replaces
  it with a stronger helper/isolation design.
- The next local slice is `GAP-019-G`: narrow the `control-provisioner` local
  executor path with a deployment-scoped executor broker, without running live
  Docker mutation.

## 2026-05-20 GAP-019-E Control-Provisioner Executor Preflight

Scope: repaired the next local `GAP-019` authority surface after confirming
`GAP-025` remained locally closed by source/test evidence. No live deploy,
install, upgrade, Docker up/down/reconcile, Stripe, Telegram, Discord, live
Notion, provider, Cloudflare, Tailscale, SSH fleet, private state, or secret
material was used.

What changed:

- `python/arclink_executor.py`: live Docker apply/lifecycle requests now
  validate deployment ids, apply project names, deployment roots, config roots,
  env files, and compose files before `DockerRunner.run`.
- `tests/test_arclink_executor.py` and `tests/test_arclink_sovereign_worker.py`:
  added fake-runner coverage for rejected malformed values and kept valid
  generated executor paths working under configured state roots.
- `config/docker-authority-inventory.json` and `tests/test_arclink_docker.py`:
  upgraded the inventory to schema version 4 and recorded the
  `control-provisioner` preflight as `GAP-019-E`, not a socket-broker closure.
- `docs/docker.md`, `docs/arclink/data-safety.md`,
  `docs/arclink/operations-runbook.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `mission_status.md`, and `IMPLEMENTATION_PLAN.md`: record the local guard
  while keeping direct writeable Docker socket access host-root-equivalent and
  policy-gated.

Validation run:

- `python3 -m pytest -q tests/test_arclink_executor.py tests/test_arclink_sovereign_worker.py tests/test_arclink_docker.py --maxfail=20`
  passed with 73 tests.
- `python3 -m pytest -q tests/test_arclink_action_worker.py tests/test_arclink_pod_migration.py --maxfail=20`
  passed with 38 tests.
- `python3 -m pytest -q tests` passed with 1220 passed and 6 skipped.

Known risks:

- `GAP-019` is still open. The preflight blocks malformed local executor
  project/path requests before Docker runner dispatch, but `control-provisioner`
  still mounts the writeable Docker socket until a deployment-scoped executor
  broker replaces it or the operator accepts the residual risk.
- The next local slice is `GAP-019-F`: narrow or explicitly no-go the
  `notification-delivery` gateway exec broker path for public selected-Agent
  replies.

## 2026-05-20 GAP-019-C Public-Agent Bridge Command Guard

Scope: repaired one local `GAP-019` authority surface after confirming
`GAP-025` had current broad-suite evidence in the active plan. No live deploy,
install, upgrade, Docker up/down/reconcile, Stripe, Telegram, Discord, live
Notion, provider, Cloudflare, Tailscale, SSH fleet, private state, or secret
material was used.

What changed:

- `python/arclink_notification_delivery.py`: detached public-Agent bridge jobs
  now validate the generated `hermes-gateway` Docker command before writing or
  running a job. The validator rejects arbitrary Docker commands, requires the
  bridge script path, matches the deployment project for direct `docker exec`,
  and confines Compose fallback files under `ARCLINK_STATE_ROOT_BASE`.
- `tests/test_arclink_notification_delivery.py`: added regressions for
  rejected/tampered bridge jobs and Compose path confinement.
- `config/docker-authority-inventory.json` and `tests/test_arclink_docker.py`:
  upgraded the inventory to schema version 3 and recorded `GAP-019-C` as a
  local command guard for `notification-delivery`, not a socket-broker closure.
- `docs/docker.md`, `docs/arclink/data-safety.md`,
  `docs/arclink/operations-runbook.md`, `GAPS.md`, `USER_JOURNEY.md`, and
  `IMPLEMENTATION_PLAN.md`: record the local guard while keeping direct
  writeable Docker socket access host-root-equivalent and policy-gated.

Validation run:

- `python3 tests/test_arclink_notification_delivery.py` passed with 18
  notification-delivery regressions.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_notification_delivery.py --maxfail=20`
  passed with 36 tests.
- `python3 -m pytest -q tests` passed with 1217 passed and 6 skipped.

Known risks:

- `GAP-019` is still open. The guard blocks one detached-job command escape,
  but `notification-delivery` still mounts the writeable Docker socket until a
  deployment-scoped gateway exec broker replaces it or the operator accepts the
  residual risk.
- Remaining socket/root services still need their own `GAP-019-D+` command
  narrowing, helper splits, incident controls, or operator residual-risk
  decisions.

## 2026-05-20 GAP-018-A Admin Action Readiness Matrix

Scope: repaired the next local P1 readiness-truth slice after confirming
`GAP-025` remained green. No live deploy, install, upgrade, Docker
up/down/reconcile, Stripe, Telegram, Discord, live Notion, provider,
Cloudflare, Tailscale, SSH fleet, private state, or secret material was used.

What changed:

- `python/arclink_dashboard.py`: added a source-owned admin action support
  matrix covering restart, reprovision, DNS repair, Chutes key rotation,
  refund, cancel, comp, and pending actions. Each row now carries readiness,
  queueability, worker support, operation kind, target kinds, required adapter,
  live proof boundary, local contract, and fail-closed reason.
- `python/arclink_product_surface.py` and `web/src/app/admin/page.tsx`: render
  the matrix so admin surfaces label local/fake readiness separately from live
  side-effect proof.
- `tests/test_arclink_admin_actions.py`, `tests/test_arclink_product_surface.py`,
  `web/tests/test_page_smoke.mjs`, and
  `web/tests/browser/product-checks.spec.ts`: assert the matrix exists and is
  visible.
- `docs/arclink/control-node-production-runbook.md`,
  `docs/arclink/operations-runbook.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: record the local repair
  while keeping `GAP-018` live-proof-gated for real worker/executor side
  effects.

Validation run:

- Baseline before edits:
  `python3 -m pytest -q tests/test_arclink_admin_actions.py tests/test_arclink_action_worker.py tests/test_arclink_dashboard.py tests/test_arclink_executor.py --maxfail=20`
  passed with 81 tests.
- Focused missing-contract repro before implementation showed
  `admin_action_execution_readiness()` had no `action_support` or
  `action_matrix` keys.
- After adding the regression, `python3 -m pytest -q tests/test_arclink_admin_actions.py --maxfail=1`
  failed on missing `action_support`, then passed after implementation with
  8 tests.
- `python3 -m pytest -q tests/test_arclink_admin_actions.py tests/test_arclink_product_surface.py tests/test_arclink_dashboard.py tests/test_arclink_action_worker.py tests/test_arclink_executor.py --maxfail=20`
  passed with 87 tests.
- `cd web && npm test` passed with 69 tests.
- `cd web && npm run lint` passed.
- `python3 -m pytest -q tests` passed with 1215 passed and 6 skipped.

Known risks:

- `GAP-018` is not closed. Live Docker, DNS, Stripe, and provider side effects
  still require an authorized proof window with recorded live successful
  worker/executor results.
- `GAP-019` remains the next highest-priority local P0 boundary for Docker
  socket/root authority reduction.

## 2026-05-20 GAP-019-B2 Broker Review And Action-Worker Guard

Scope: repaired the next local `GAP-019` slice after rechecking `GAP-025`.
No live deploy, install, upgrade, Docker up/down/reconcile, Stripe, Telegram,
Discord, live Notion, provider, Cloudflare, Tailscale, SSH fleet, private
state, or secret material was used.

What changed:

- `python/arclink_action_worker.py`: restart lifecycle metadata can no longer
  override Docker Compose project/env/compose paths by default. The only escape
  hatch is the explicit operator emergency flag
  `ARCLINK_ACTION_WORKER_ALLOW_LIFECYCLE_PATH_OVERRIDES=1`.
- `config/docker-authority-inventory.json`: upgraded the authority inventory to
  schema version 2 with a `GAP-019-B2` review for every socket/root service:
  broker/no-go decision, operation allowlist, runtime enforcement paths,
  monitoring controls, root split review, and remaining gate.
- `tests/test_arclink_action_worker.py` and `tests/test_arclink_docker.py`:
  assert the lifecycle override guard and fail closed when the authority
  inventory lacks B2 review fields.
- `docs/docker.md`, `docs/arclink/data-safety.md`,
  `docs/arclink/operations-runbook.md`, `GAPS.md`, `USER_JOURNEY.md`, and
  `IMPLEMENTATION_PLAN.md`: record the local repair while keeping `GAP-019`
  open for real brokers/helper splits or operator residual-risk acceptance.

Validation run:

- `python3 -m pytest -q tests` passed before the patch with 1212 passed and 6
  skipped, confirming `GAP-025` was not the active failure.
- Baseline focused reproduction before the patch:
  `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_action_worker.py tests/test_arclink_executor.py --maxfail=20`
  passed with 82 tests.
- After the repair, the same focused command passed with 84 tests.
- Final broad recheck after the repair:
  `python3 -m pytest -q tests` passed with 1214 passed and 6 skipped.

Known risks:

- `GAP-019` is not closed. The B2 record rejects a generic Docker socket proxy
  as a closure claim; actual command-specific brokers/helper splits, an
  incident response runbook, and an operator residual-risk decision are still
  required.

## 2026-05-20 GAP-019-B1 Docker Authority Inventory

Scope: repaired the next local `GAP-019` slice by adding a source-owned
authority inventory and a drift guard for every Compose service that mounts the
Docker socket or declares an explicit root user. No live deploy, install,
upgrade, Docker up/down/reconcile, Stripe, Telegram, Discord, live Notion,
provider, Cloudflare, Tailscale, SSH fleet, private state, or secret material
was used.

What changed:

- `config/docker-authority-inventory.json`: records each socket/root service
  with authority class, read/write socket mode, explicit-root status, why the
  authority exists, proxy/broker candidate status, monitoring/runbook anchor,
  and residual `GAP-019` policy state.
- `tests/test_arclink_docker.py`: now derives the Compose socket/root authority
  surface and fails closed when it drifts from the inventory or when docs stop
  pointing at the inventory.
- `docs/docker.md`, `docs/arclink/data-safety.md`,
  `docs/arclink/operations-runbook.md`, `USER_JOURNEY.md`, `GAPS.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: record the local repair and
  keep the residual P0 trusted-host risk open.

Validation run:

- Initial focused reproduction before the patch:
  `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed with
  16 tests, proving the missing behavior was a coverage/contract gap rather
  than an existing red assertion.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed after
  the repair with 17 tests.
- `python3 tests/test_documentation_truths.py` passed.
- `git diff --check` passed.

Known risks:

- `GAP-019` is not closed. `GAP-019-B2` still needs a Docker socket proxy,
  command-specific broker, or explicit no-go/residual-risk decision for each
  writeable socket service, with deeper review of `control-action-worker` and
  `agent-supervisor` root boundaries.

## 2026-05-20 GAP-019 Docker Socket Static Hardening

Scope: repaired the first local `GAP-019` slice after verifying `GAP-025`.
No live deploy, install, upgrade, Docker up/down/reconcile, Stripe, Telegram,
Discord, live Notion, provider, Cloudflare, Tailscale, SSH fleet, private state,
or secret material was used.

What changed:

- `compose.yaml`: non-root Docker-socket services now set `cap_drop: [ALL]`;
  the root/socket services remain explicit for migration capture and per-agent
  runtime reconciliation.
- `tests/test_arclink_docker.py`: the Docker regression now asserts socket
  mount count, supplemental socket group, capability drop for non-root socket
  services, explicit root boundaries, and docs coverage.
- `docs/docker.md`, `docs/arclink/data-safety.md`, and
  `docs/arclink/operations-runbook.md`: document the capability-drop mitigation
  while keeping writeable Docker socket access labeled host-root-equivalent.
- `GAPS.md`, `USER_JOURNEY.md`, and `IMPLEMENTATION_PLAN.md`: record the local
  hardening slice and leave the residual P0 trusted-host risk open.

Validation run:

- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed: 16
  tests.
- `python3 tests/test_documentation_truths.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1211 passed, 6 skipped.

Known risks:

- `GAP-019` is not closed. A Docker socket proxy or command-specific broker,
  root-service narrowing, monitoring/incident controls, and an operator
  residual-risk decision are still required before this P0 boundary can move
  out of the active queue.

## 2026-05-20 GAP-007 Notion Verification State Repair

Scope: repaired the local Notion setup truth boundary after `GAP-025` was
already broad-suite green. No live deploy, install, upgrade, Docker mutation,
Stripe, Telegram, Discord, live Notion, provider, Cloudflare, Tailscale, SSH
fleet, private state, or secret material was used.

What changed:

- `python/arclink_dashboard.py`: changed the dashboard Notion read model so the
  strongest no-secret state is `local_metadata_verified`, not bare `verified`,
  while shared-root read, brokered write preflight, user-owned OAuth, and live
  workspace proof remain gated.
- `web/src/app/dashboard/page.tsx`, `web/src/components/ui.tsx`, and
  `web/tests/browser/product-checks.spec.ts`: updated the dashboard type,
  status badges, copy, and fixture to keep local metadata readiness separate
  from live proof.
- `tests/test_arclink_dashboard.py` and `tests/test_documentation_truths.py`:
  assert that local Notion setup no longer reports top-level `verified` while
  `PG-NOTION` is still open, and guard stale Creative Brief wording.
- `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`,
  `mission_status.md`, and `docs/arclink/CREATIVE_BRIEF.md`: recorded the local
  fail-closed repair and left authorized live Notion proof open.

Validation run:

- Focused repro before the fix failed with top-level Notion status `verified`
  while `verification.live_workspace` was `proof_gated`.
- `python3 -m pytest -q tests/test_arclink_onboarding_notion.py tests/test_arclink_ctl_notion.py tests/test_notion_ssot.py tests/test_arclink_notion_knowledge.py tests/test_arclink_notion_webhook.py tests/test_arclink_ssot_batcher.py tests/test_arclink_notion_skill_text.py tests/test_arclink_dashboard.py --maxfail=20` passed.
- `python3 tests/test_documentation_truths.py` passed.
- `cd web && npm test` passed.
- `cd web && npm run lint` passed.
- `git diff --check` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m pytest -q tests` passed: 1211 passed, 6 skipped.

Known risks:

- `PG-NOTION` remains open until an operator-authorized proof window supplies
  real Notion credentials and records shared-root read, brokered write
  preflight, webhook, and dashboard evidence.
- `GAP-019` is the next local P0 slice: Docker socket/root trusted-host
  hardening and residual-risk controls.

## 2026-05-20 GAP-025 Broad Suite And GAP-011 Truth Repair

Scope: completed the no-secret broad local Python validation repair and closed
`GAP-011` documentation truth drift. No live deploy, install, upgrade, Docker
mutation, Stripe, Telegram, Discord, Notion, provider, Cloudflare, Tailscale,
SSH fleet, private state, or secret material was used.

What changed:

- `docs/arclink/foundation.md` and `docs/arclink/foundation-runbook.md`: aligned
  foundation wording with the current Control Node boundary while keeping live
  proof gates explicit.
- `tests/test_documentation_truths.py`: added a guard that rejects the stale
  foundation/prototype phrases that contradicted Control Node docs.
- `tests/test_arclink_auto_provision.py`, `tests/test_nextcloud_user_access.py`,
  `tests/test_arclink_notification_delivery.py`,
  `tests/test_arclink_pin_upgrade_detector.py`, and
  `tests/test_arclink_enrollment_provisioner_regressions.py`: restored shared
  `subprocess` and `pwd` monkeypatches so broad-suite order no longer poisons
  later subprocess and passwd lookups.
- `tests/test_arclink_sovereign_worker.py`: updated stale handoff-message
  assertions to the current Raven/Helm copy.
- `GAPS.md`, `IMPLEMENTATION_PLAN.md`, `mission_status.md`, and
  `research/COVERAGE_MATRIX.md`: recorded `GAP-011` and `GAP-025` as locally
  closed and selected `GAP-007` as the next local slice.

Validation run:

- `python3 tests/test_documentation_truths.py` passed.
- `python3 -m pytest -q tests/test_arclink_auto_provision.py tests/test_arclink_context_telemetry.py tests/test_arclink_ctl_notion.py tests/test_arclink_memory_sync.py tests/test_arclink_onboarding_notion.py --maxfail=20` passed.
- `python3 -m pytest -q tests/test_nextcloud_user_access.py tests/test_arclink_notification_delivery.py tests/test_arclink_pin_upgrade_detector.py --maxfail=20` passed.
- `python3 -m pytest -q tests/test_arclink_notification_delivery.py tests/test_arclink_pins.py tests/test_arclink_plugins.py --maxfail=20` passed.
- `python3 -m pytest -q tests/test_arclink_sovereign_worker.py --maxfail=20`
  passed.
- `python3 -m pytest -q tests` passed: 1211 passed, 6 skipped.

Known risks:

- Live gates remain open: `PG-PROD`, `PG-STRIPE`, `PG-BOTS`,
  `PG-PROVISION`, `PG-FLEET`, `PG-INGRESS`, `PG-PROVIDER`, `PG-NOTION`,
  `PG-HERMES`, `PG-BACKUP`, and `PG-UPGRADE`.
- Web/Node validation was not rerun in this pass.
- Next local repair slice is `GAP-007`: Notion setup verification truth.

## 2026-05-20 GAP-025 Clusters And GAP-008 OpenAPI Repair

Scope: continued the no-secret `GAP-025` triage after the public-bot adapter
repair. Confirmed the Notion, plugins/workspace, deploy/health, and
vault/repo/backup local clusters with focused commands, repaired a stale
deploy-regression vocabulary expectation, and closed the local `GAP-008`
OpenAPI proof-token schema gap. No live deploy, install, upgrade, Docker
mutation, Stripe, Telegram, Discord, Notion, provider, Cloudflare, Tailscale,
SSH fleet, private state, or secret material was used.

What changed:

- `tests/test_deploy_regressions.py`: updated the Notion SSOT setup prompt
  assertion to expect the current Raven integration-name guidance rather than
  stale `ArcLink Curator` vocabulary.
- `python/arclink_hosted_api.py`: added `claim_token` and `cancel_token` to the
  dynamic OpenAPI request schemas for onboarding claim/cancel.
- `docs/openapi/arclink-v1.openapi.json`: regenerated the static OpenAPI copy
  from the canonical hosted API builder.
- `tests/test_arclink_hosted_api.py`: added semantic assertions that dynamic
  and static OpenAPI both require the onboarding proof tokens.
- `GAPS.md`, `research/COVERAGE_MATRIX.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded `GAP-008` as locally closed, updated
  `GAP-025` cluster status, and selected `GAP-011` as the next local slice.

Validation run:

- `python3 -m pytest -q tests/test_arclink_onboarding_notion.py tests/test_arclink_ctl_notion.py tests/test_notion_ssot.py tests/test_arclink_notion_knowledge.py tests/test_arclink_notion_webhook.py tests/test_arclink_ssot_batcher.py tests/test_arclink_notion_skill_text.py --maxfail=20` passed.
- `python3 -m pytest -q tests/test_arclink_plugins.py --maxfail=20` passed.
- `python3 -m pytest -q tests/test_deploy_regressions.py tests/test_health_regressions.py --maxfail=20` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 -m pytest -q tests/test_arclink_repo_sync.py tests/test_backup_git_regressions.py tests/test_agent_backup_regressions.py tests/test_vault_bootstrap_layout.py tests/test_vault_watch_regressions.py tests/test_vault_symlink_regressions.py --maxfail=20` passed.
- `python3 -m pytest -q tests/test_arclink_hosted_api.py --maxfail=20` passed.
- `python3 tests/test_documentation_truths.py` passed.

Known risks:

- Historical at this point in the log, `GAP-025` still required a fresh broad
  `python3 -m pytest -q tests` run or a release-approved quarantine ledger.
  Later entries supersede this with a green broad suite.
- Live gates remain open: `PG-NOTION`, `PG-HERMES`, `PG-BACKUP`, `PG-UPGRADE`,
  and the broader production proof gates were not run.

## 2026-05-20 GAP-025 Public Bot Adapter Test Repair

Scope: started the `GAP-025` full-suite triage with the user-facing
Telegram/Discord public-bot onboarding contract cluster. No live bot,
webhook, Stripe, provider, Docker, deploy, host mutation, private state, or
secret material was used.

What changed:

- `tests/test_arclink_telegram.py`: updated the fake Telegram contract checks
  to assert Raven's current direct package checkout flow, including Founders
  and Scale package buttons.
- `tests/test_arclink_discord.py`: updated the fake Discord interaction checks
  to match the same direct package flow and keep `/name`,
  `/agent-identity`, and plan selection on one onboarding session.
- `IMPLEMENTATION_PLAN.md`: replaced the document-phase atlas checklist with
  an active repair queue keyed to `GAP-025` and local P0/P1 repairable gaps,
  including exact focused tests and local/live/policy boundaries.
- `GAPS.md`: recorded that the Discord/Telegram adapter cluster is repaired
  while the broader `GAP-025` suite remains open.

Validation run:

- `python3 -m pytest -q tests/test_arclink_public_bots.py tests/test_arclink_telegram.py tests/test_arclink_discord.py --maxfail=20` passed.

Known risks:

- Historical at this point in the log, remaining `GAP-025` full-suite clusters
  still needed local triage, repair, or explicit quarantine. Later entries
  supersede this with a green broad suite.
- Live Telegram/Discord delivery remains `PG-BOTS`; this pass only repaired
  local fake-adapter contract tests.

## 2026-05-20 Ralphie Public Documentation Handoff Finalization

Scope: finalized the public documentation handoff around the two root documents.
Inspected `USER_JOURNEY.md`, `GAPS.md`, `research/COVERAGE_MATRIX.md`,
`research/RALPHIE_ARCLINK_USER_JOURNEY_AND_GAPS_STEERING.md`, the Ralphie
document-phase retry feedback, the current documentation truth test, the public
repo hygiene test, the phase handoff/scoring guard, and the existing completion
log. No live deploy, install, upgrade, Docker mutation, Stripe, Telegram,
Discord, Notion, provider, Cloudflare, Tailscale, SSH fleet, or production-host
mutation was run.

Follow-up audit correction: after Ralphie completed, a broad no-secret Python
suite run of `python3 -m pytest -q tests` on 2026-05-20 reported 197 failed,
1012 passed, and 6 skipped. This does not invalidate the root docs as
source-grounded planning artifacts, but it does invalidate any broad
"local validation is green" reading of the earlier focused 582-test result.
`GAPS.md` now records this as `GAP-025`, and future release planning must triage
the full-suite failures before claiming broad regression cleanliness.

Produced:

- `USER_JOURNEY.md`: kept as the complete ArcLink experience story, added a
  one-page journey synopsis, added an explicit fast handoff and document-phase
  closeout rule for future agents, added a reviewer acceptance checklist, and
  kept launch certification separated from intended experience.
- `GAPS.md`: kept as the implementation-planning register, added operator
  decision summary material, added an ordered planning ladder, added a P0/P1
  launch decision ledger, added a document-phase closeout rule, and preserved
  closure rules so future work does not close proof, policy, validation, or code
  gaps with copy alone. A follow-up audit added `GAP-025` for the full-suite
  failure boundary.
- `research/BUILD_COMPLETION_NOTES.md`: recorded this handoff note with the
  validation boundary.
- `mission_status.md`: recorded the current public documentation handoff status
  for phase tooling that reads a root mission artifact.

Validation:

- `git diff --check` passed.
- `python3 tests/test_documentation_truths.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- A targeted scan of the latest handoff section, `USER_JOURNEY.md`, `GAPS.md`,
  and `mission_status.md` found no absolute local path, private-key marker,
  obvious token prefix, or live-proof-passed overclaim.
- Ralphie's selected no-secret validation reported 582 tests passed plus shell
  syntax and web checks, but the then-later broad Python suite exposed
  `GAP-025` as described above. Treat the 582-test result as focused
  validation only.
- A later retry repair targeted the remaining machine-check weakness from the
  prior document attempt: reviewers had GO/no-gap outcomes, but handoff and
  consensus averages were below the configured 92-point threshold. The root docs
  now make terminal document-phase intent, reviewer acceptance criteria,
  implementation-planning order, operator decision points, and out-of-scope
  proof/policy gates explicit.

Remaining gates:

- No credentialed live proof was run in this document pass.
- Historical at this point in the log, broad Python regression validation was
  still unresolved; later entries supersede this with `GAP-025` locally closed
  by the broad suite.
- `PG-PROD`, `PG-STRIPE`, `PG-BOTS`, `PG-PROVISION`, `PG-FLEET`, `PG-INGRESS`,
  `PG-PROVIDER`, `PG-NOTION`, `PG-HERMES`, `PG-BACKUP`, and `PG-UPGRADE` remain
  governed by `GAPS.md`.
- Provider self-service, Captain migration, browser share-link broker,
  backup automation, linked copy/duplicate wording, and destructive teardown
  authority remain policy decisions until the operator resolves them.

## 2026-05-16 LLM Router Model Catalog And Promotion

Scope: upgraded the Control Node LLM router so model pricing and lifecycle
resolution are catalog-driven instead of frozen to a single default estimate.
No live Chutes request, deployment, provider mutation, or private-state read was
performed.

What changed:

- `python/arclink_chutes.py`: Chutes catalog parsing now extracts per-million
  input/output prices from common Chutes/OpenAI-compatible shapes, including
  string prices such as `$0.95 / 1M tokens`.
- `python/arclink_control.py`: `arclink_model_catalog` now stores pricing,
  status, replacement model id, inferred family, version sort key, first/last
  seen timestamps, and raw provider metadata. New helpers upsert model catalog
  rows, preserve deliberate deprecation replacements across refreshes, mark
  missing rows unavailable after successful refreshes, and find the latest
  active model in a family.
- `python/arclink_llm_router.py`: router startup refreshes Chutes `/models`
  into the catalog, health exposes sanitized refresh status, reservations and
  settlement use catalog pricing when available, and requests are resolved to a
  replacement/latest upstream model before forwarding. This supports both
  Kimi-K2.6 -> Kimi-K2.7 while 2.6 remains active and the case where 2.6 has
  disappeared from a fresh catalog.
- `compose.yaml`: surfaced the router model-promotion and startup catalog
  refresh env vars.
- `docs/arclink/llm-router.md`, `docs/API_REFERENCE.md`,
  `docs/arclink/architecture.md`, and `docs/arclink/operations-runbook.md`:
  documented catalog pricing, startup refresh, auto-promotion, emergency
  replacements, and fallback estimator values.
- `tests/test_arclink_llm_router.py` and
  `tests/test_arclink_chutes_and_adapters.py`: added regression coverage for
  pricing parse, lifecycle rows, explicit deprecation replacement, startup
  catalog refresh, newer same-family auto-promotion, and disappeared old-model
  promotion.

Validation run:

- `python3 -m py_compile python/arclink_chutes.py python/arclink_control.py python/arclink_llm_router.py` passed.
- `python3 tests/test_arclink_llm_router.py` passed (14/14).
- `python3 tests/test_arclink_chutes_and_adapters.py` passed (23/23).
- `python3 tests/test_arclink_schema.py` passed (10/10).
- `python3 tests/test_arclink_provisioning.py` passed (13/13).
- `python3 tests/test_arclink_docker.py` passed (16/16).
- `python3 tests/test_arclink_hosted_api.py` passed (75/75).
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `git diff --check` passed.

Known risks:

- Live Chutes catalog and inference proof remain operator-gated. The source
  path is locally tested with fixture transports only.
- The inferred model-family heuristic handles conventional version strings such
  as `Kimi-K2.6-TEE` -> `Kimi-K2.7-TEE`; unusual provider renames may still
  require `ARCLINK_LLM_ROUTER_MODEL_REPLACEMENTS`.

## 2026-05-16 Sovereign LLM Router Review Button-Up

Scope: reviewed the completed LLM Router work against the follow-up audit and
closed the remaining local testing-rigor and isolation gaps without touching
`arclink-priv`, live secrets, production services, deploy/upgrade flows, or
Hermes core.

Files changed:

- `tests/test_arclink_llm_router.py`: strengthened budget, billing, rate-limit,
  and concurrency tests to assert blocked requests do not reach the upstream
  Chutes transport; added coverage that legacy `CHUTES_API_KEY` alone does not
  configure the router.
- `python/arclink_llm_router.py`: removed the legacy `CHUTES_API_KEY` fallback;
  the router now requires `ARCLINK_LLM_ROUTER_CHUTES_API_KEY` explicitly.
- `compose.yaml` and `tests/test_arclink_docker.py`: kept
  `control-llm-router` off the broad control-secret environment anchor so the
  central router Chutes credential is isolated to the router service.
- `python/arclink_secrets_regex.py`, `python/arclink_evidence.py`, and
  `tests/test_arclink_secrets_regex.py`: added redaction coverage for
  `acpod_live_...` ArcPod router keys and the
  `ARCLINK_LLM_ROUTER_CHUTES_API_KEY` env name.
- `docs/arclink/llm-router.md`: documented the explicit router credential
  requirement with no `CHUTES_API_KEY` fallback.

Validation run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_llm_router.py python/arclink_chutes.py
  python/arclink_control.py python/arclink_provisioning.py
  python/arclink_sovereign_worker.py python/arclink_secrets_regex.py
  python/arclink_evidence.py` passed.
- `python3 tests/test_arclink_llm_router.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_arclink_secrets_regex.py` passed.
- `python3 tests/test_arclink_evidence.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.

Known risks:

- No live Chutes proof, production deploy, or provider mutation was run; those
  remain explicit operator-gated steps.

## 2026-05-16 Sovereign LLM Router Phase 6 Slice

Scope: completed the remaining local router provider-state/docs slice without
touching `arclink-priv`, live secrets, production services, payment/provider
mutations, deploy/upgrade flows, or Hermes core.

Files changed:

- `python/arclink_api_auth.py`: added sanitized ArcLink LLM Router usage,
  reservation, credential-count, and quota summaries to provider-state payloads.
- `tests/test_arclink_hosted_api.py`: added user/admin provider-state coverage
  proving router usage is visible and raw keys/secret refs are not returned.
- `python/arclink_hosted_api.py` and `docs/openapi/arclink-v1.openapi.json`:
  documented `/v1/models` and `/v1/chat/completions` in the OpenAPI catalog.
- `docs/API_REFERENCE.md`, `docs/arclink/llm-router.md`,
  `docs/arclink/operations-runbook.md`, and
  `docs/arclink/sovereign-control-node.md`: updated router topology,
  ArcPod defaults, compatibility flag, live-proof gate, and provider-state
  consumption notes.
- `IMPLEMENTATION_PLAN.md`: marked the local router acceptance criteria that
  this pass completed.

Implementation rationale:

- Kept router key storage on the existing SHA-256 token digest because ArcLink
  router keys are generated high-entropy API keys; a keyed-HMAC migration is
  useful defense-in-depth but is better handled with the broader token hash
  migration rail.
- Exposed only aggregate usage/quota data through provider-state. Raw router
  keys, central Chutes credentials, secret refs, prompts, and completions remain
  outside the payload.

Validation run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_llm_router.py python/arclink_chutes.py
  python/arclink_control.py python/arclink_provisioning.py
  python/arclink_sovereign_worker.py python/arclink_api_auth.py
  python/arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_llm_router.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.

Known risks:

- No live Chutes proof, production deploy, or provider mutation was run; those
  remain explicit operator-gated steps.

## 2026-05-16 Sovereign Fleet Handoff Artifact Repair

Scope: repaired missing handoff artifacts after the prior BUILD validation
handoff failure. This pass preserved the existing fleet/provider worktree,
did not touch `arclink-priv`, live secrets, production services, payment or
provider state, remote SSH, deploy/upgrade flows, or Hermes core, and did not
claim live fleet readiness.

Files changed:

- `mission_status.md`: added an honest mission status showing local/fake
  validation complete while Phase 7 live two-host proof remains
  operator-gated.
- `research/SOVEREIGN_FLEET_TWO_HOST_LIVE_PROOF_CHECKLIST_20260516.md`: added
  the Phase 7 authorization, preflight, live-step, evidence, and completion
  checklist required before any live proof can run.
- `research/BUILD_COMPLETION_NOTES.md`: recorded this artifact repair pass.

Validation run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_fleet.py
  python/arclink_inventory.py python/arclink_executor.py
  python/arclink_sovereign_worker.py python/arclink_action_worker.py
  python/arclink_fleet_enrollment.py python/arclink_fleet_inventory_worker.py
  python/arclink_hosted_api.py python/arclink_secrets_regex.py` passed.
- `bash -n deploy.sh bin/*.sh bin/lib/*.sh bin/arclink-fleet-probe-wrapper
  test.sh` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_fleet_enrollment.py`
  passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_fleet_inventory_worker.py`
  passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_fleet_join.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_inventory.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_inventory_hetzner.py`
  passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_inventory_linode.py`
  passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_fleet.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_action_worker.py`
  passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_executor.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_sovereign_worker.py`
  passed.
- `PYTHONPATH=python:tests python3 tests/test_deploy_regressions.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_schema.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_telegram.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_discord.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_hosted_api.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_api_auth.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_secrets_regex.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_docker.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_documentation_truths.py` passed.
- `npm --prefix web test` passed.
- `npm --prefix web run lint` passed.
- `npm --prefix web run build` passed.
- `npm --prefix web run test:browser` passed with 45 passed and 3 skipped.

Known risks before terminal fleet readiness:

- No live clean-host prerequisite install, worker join, non-loopback SSH probe,
  real provider creation/deletion, production deploy, or two-host proof was
  run. Those remain explicit Operator-authorized gates.
- `shellcheck` is not installed in this environment, so shellcheck validation
  was not run.

## 2026-05-16 Sovereign Fleet Validation Retry

Scope: reran the local BUILD validation floor after the prior handoff
validation failure. This pass preserved the existing fleet/provider worktree,
did not touch `arclink-priv`, live secrets, production services, payment or
provider state, remote SSH, deploy/upgrade flows, or Hermes core, and found no
additional source repair needed before the live/operator gates.

Files changed:

- `research/BUILD_COMPLETION_NOTES.md`: recorded the validation-only retry,
  outcomes, and residual live-proof risks.

Validation run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_fleet.py
  python/arclink_inventory.py python/arclink_executor.py
  python/arclink_sovereign_worker.py python/arclink_action_worker.py
  python/arclink_fleet_enrollment.py python/arclink_fleet_inventory_worker.py
  python/arclink_hosted_api.py python/arclink_secrets_regex.py` passed.
- `bash -n deploy.sh bin/*.sh bin/lib/*.sh bin/arclink-fleet-probe-wrapper
  test.sh` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_fleet_enrollment.py`
  passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_fleet_inventory_worker.py`
  passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_fleet_join.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_inventory.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_inventory_hetzner.py`
  passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_inventory_linode.py`
  passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_fleet.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_action_worker.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_executor.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_sovereign_worker.py`
  passed.
- `PYTHONPATH=python:tests python3 tests/test_deploy_regressions.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_schema.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_telegram.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_discord.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_hosted_api.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_api_auth.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_secrets_regex.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_docker.py` passed.
- `npm --prefix web test` passed.
- `npm --prefix web run lint` passed.
- `npm --prefix web run build` passed.
- `npm --prefix web run test:browser` passed with 45 passed and 3 skipped.

Known risks:

- `shellcheck` is not installed in this environment, so shellcheck validation
  was not run.
- No live clean-host prerequisite install, worker join, non-loopback SSH probe,
  provider creation, production deploy, or two-host proof was run. Those remain
  explicit Operator-authorized gates, and fleet readiness is not claimed.
- At the time of that validation-only retry, this checkout did not contain
  `mission_status.md`; the handoff artifact repair entry above supersedes that
  gap with an honest status file.

## 2026-05-16 Sovereign Fleet Provider Inventory Phase 6 Slice

Scope: implemented the next local Phase 6 provider-inventory slice without
touching `arclink-priv`, live secrets, production services, live provider
accounts, payment/provider mutations, remote SSH, deploy/upgrade flows, or
Hermes core.

Files changed:

- `python/arclink_inventory.py`: added idempotent Hetzner/Linode
  create/register/remove orchestration, duplicate-hostname prevention,
  provider delete guardrails, bootstrap metadata tied to
  `bin/arclink-fleet-join.sh` and `bin/lib/ensure-prereqs.sh`, provider
  billing-ref persistence, and CLI flags for provider create/remove.
- `python/arclink_control.py`: added additive
  `arclink_inventory_machines.metadata_json` migration support.
- `bin/deploy.sh`: forwards `control inventory add hetzner|linode` arguments
  into the inventory CLI.
- `tests/test_arclink_inventory_hetzner.py` and
  `tests/test_arclink_inventory_linode.py`: added fake-provider coverage for
  create replay, duplicate prevention, bootstrap failure redaction, and
  guarded provider destroy replay.
- `docs/arclink/fleet-cli.md`,
  `docs/arclink/fleet-operator-runbook.md`, and `IMPLEMENTATION_PLAN.md`:
  documented the provider slice and kept live proof/operator gates explicit.

Implementation rationale:

- Reused `arclink_operation_idempotency` instead of adding a provider-specific
  replay table.
- Stored provider bootstrap state as inventory metadata while leaving worker
  admission dependent on enrollment callback and probe health.
- Kept live SSH wait/join execution out of this local pass; the code exposes a
  bootstrap hook for fake proof and future authorized live proof without
  passing enrollment tokens through argv.

Validation run:

- `PYTHONPATH=python:tests python3 tests/test_arclink_inventory_hetzner.py`
  passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_inventory_linode.py`
  passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_inventory.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_schema.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_deploy_regressions.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_fleet.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_fleet_enrollment.py`
  passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_inventory.py
  python/arclink_inventory_hetzner.py python/arclink_inventory_linode.py`
  passed.
- `bash -n deploy.sh bin/*.sh bin/lib/*.sh test.sh` passed.
- `git diff --check` passed.

Known risks:

- No real Hetzner/Linode API call, remote SSH wait, worker join, clean-host
  prereq install, or two-host proof was run. Those remain
  Operator-authorized live gates.
- `shellcheck` is not installed in this environment, so shellcheck validation
  was not run.

## 2026-05-16 Sovereign Fleet CLI Hardening Phase 5 Slice

Scope: implemented the next open `IMPLEMENTATION_PLAN.md` Phase 5 operator CLI
surface without touching `arclink-priv`, live secrets, deploy keys,
production services, Docker install/upgrade, remote SSH proof, providers,
payment systems, or Hermes core.

Files changed:

- `bin/deploy.sh`: added `fleet-key --rotate --json`, `inventory rotate-key`,
  non-interactive `control register-worker --hostname --ssh-host --ssh-user`
  with JSON output, JSON-safe default smoke behavior, probe argument forwarding,
  and JSON `inventory set-strategy`.
- `python/arclink_inventory.py`: added scriptable inventory list filters and
  JSON support for strategy/provider subcommands while preserving existing
  table output.
- `docs/arclink/fleet-cli.md` and
  `docs/arclink/fleet-operator-runbook.md`: documented command contracts,
  exit codes, JSON examples, key rotation, re-attestation, health, drain/remove,
  and recovery.
- `tests/test_arclink_inventory.py` and `tests/test_deploy_regressions.py`:
  added regression coverage for filters, non-interactive registration, key
  rotation aliases, JSON contracts, and docs.
- `IMPLEMENTATION_PLAN.md`: marked the Phase 5 CLI slice as implemented
  locally and left live proof/provider work gated.

Implementation rationale:

- Kept the canonical surface in `deploy.sh control` instead of introducing a
  new binary.
- Made JSON worker registration skip live SSH smoke by default so stdout stays
  parseable; `--smoke-test` opts into operator-authorized live proof.

Validation run:

- `bash -n deploy.sh bin/*.sh bin/lib/*.sh bin/arclink-fleet-probe-wrapper test.sh` passed.
- `python3 -m py_compile python/arclink_inventory.py python/arclink_fleet_enrollment.py python/arclink_fleet_inventory_worker.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_inventory.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_deploy_regressions.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_fleet_enrollment.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_fleet_inventory_worker.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_fleet_join.py` passed.
- `PYTHONPATH=python:tests python3 tests/test_arclink_fleet.py` passed.
- `./deploy.sh control register-worker --help` passed.
- `./deploy.sh control fleet-key --help` passed.
- `PYTHONPATH=python python3 python/arclink_inventory.py set-strategy headroom --json` passed.

Known risks:

- No live key rotation, non-loopback SSH registration, clean-host worker join,
  provider provisioning, or two-host proof was run. Phase 6 and Phase 7 remain
  open/operator-gated, and fleet readiness is not claimed.
- `shellcheck` is not installed in this environment, so shellcheck validation
  was not run.

## 2026-05-16 Sovereign Fleet Enrollment HMAC Rotation Follow-Through

Scope: closed the remaining Phase 2 enrollment HMAC-root rotation UX from
`IMPLEMENTATION_PLAN.md`. This pass stayed local and did not touch
`arclink-priv`, live secrets, deploy keys, production services, Docker
install/upgrade, remote SSH, providers, payment systems, or Hermes core.

Files changed:

- `python/arclink_fleet_enrollment.py`: added `rotate-secret` support that
  records an audit event and revokes pending enrollment tokens without
  rendering token or root material.
- `bin/deploy.sh`: exposed `deploy.sh control enrollment rotate-secret` and
  shortcut alias `control-enrollment-rotate-secret`, generating and persisting a
  fresh private HMAC root through the existing runtime-config writer.
- `python/arclink_secrets_regex.py`: redacts `arcfleet_v1...` enrollment
  tokens at shared boundaries.
- `tests/test_arclink_fleet_enrollment.py` and
  `tests/test_deploy_regressions.py`: added coverage for pending-token
  revocation, audit redaction, and control command routing.
- `IMPLEMENTATION_PLAN.md`: marked Phase 2 HMAC rotation follow-through as
  implemented.

Implementation rationale:

- Chose rotation plus pending-token revocation instead of dual-root token
  validation. Pending enrollments are one-time bootstrap credentials; after a
  root rotation, accepting old pending tokens would weaken the operator's trust
  boundary.

Validation run:

- `python3 tests/test_arclink_fleet_enrollment.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_arclink_secrets_regex.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 -m py_compile python/arclink_fleet_enrollment.py python/arclink_secrets_regex.py` passed.
- `bash -n deploy.sh bin/*.sh bin/lib/*.sh test.sh` passed.
- `git diff --check` passed.

Known risks:

- Phase 3 worker join/probe wrapper, Phase 4 periodic inventory worker, Phase 6
  provider provisioning, and Phase 7 live two-host proof remain open or
  operator-gated. Fleet readiness is not claimed by this pass.

## 2026-05-16 Sovereign Fleet Enrollment Phase 2 Slice

Scope: implemented the highest-priority open `IMPLEMENTATION_PLAN.md` Phase 2
surface for worker enrollment and audit-chain trust, while treating the
historical Wave 1 audit report as a regression gate. This pass stayed local:
no `arclink-priv`, live secrets, deploy keys, production services,
provider/payment mutation, remote SSH, Docker install/upgrade, deploy/upgrade,
or Hermes core path was touched.

Files changed:

- `python/arclink_fleet_enrollment.py`: added HMAC-bound single-use enrollment
  token mint/list/revoke/expiry/consume helpers and JSON CLI commands, worker
  attestation into the existing inventory and fleet-host registries, immutable
  fingerprint mismatch rejection, audit-chain append/verify, and P0 operator
  notification on chain tampering.
- `python/arclink_hosted_api.py`: added public
  `POST /api/v1/fleet/enrollment/callback` with bearer enrollment-token
  validation, existing hosted JSON/body posture, and non-secret response shape.
- `bin/deploy.sh`, `bin/arclink-docker.sh`, `bin/docker-entrypoint.sh`, and
  `compose.yaml`: wired `deploy.sh control enrollment mint|list|revoke`,
  generated a dedicated `ARCLINK_FLEET_ENROLLMENT_SECRET`, and passed it into
  control services without relying on the session hash pepper.
- `tests/test_arclink_fleet_enrollment.py`: added focused regression coverage
  for stored-token hashing, fail-closed token states, hosted callback
  attestation, fingerprint mismatch, audit-chain tamper detection, and
  non-secret CLI/list/revoke output.
- `tests/test_deploy_regressions.py`: added source-level coverage for the
  first-class control enrollment command and Docker secret seeding.
- `docs/API_REFERENCE.md` and `docs/openapi/arclink-v1.openapi.json`: recorded
  the callback route and `ARCLINK_FLEET_ENROLLMENT_SECRET` contract.

Implementation rationale:

- Chose HMAC-bound bearer enrollment tokens over SSH-only registration because
  SSH key possession does not attest machine identity or one-time enrollment
  intent. Client certificates remain deferred because the current bootstrap
  path can satisfy the Phase 2 trust boundary with less operational ceremony.
- Stored only HMAC token hashes in SQLite and returned the cleartext token only
  from mint. Callback responses intentionally expose IDs/status only, not token
  material or machine fingerprints.
- Reused `arclink_inventory_machines` plus `arclink_fleet_hosts` rather than
  introducing another registry, preserving the formal inventory/placement split.

Validation run:

- `python3 -m py_compile python/arclink_fleet_enrollment.py python/arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_fleet_enrollment.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_fleet.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_secrets_regex.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_inventory_hetzner.py` passed.
- `python3 tests/test_arclink_inventory_linode.py` passed.
- `python3 -m py_compile python/arclink_fleet_enrollment.py python/arclink_hosted_api.py python/arclink_inventory.py python/arclink_fleet.py python/arclink_control.py python/arclink_executor.py python/arclink_sovereign_worker.py python/arclink_action_worker.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `git diff --check` passed.
- Manual temp-DB smoke for `python/arclink_fleet_enrollment.py --db ... mint`
  and `list` JSON parsing passed.
- `python3 tests/test_arclink_inventory.py` was not run because this checkout
  does not contain that file; current inventory coverage lives in the fleet and
  provider-specific inventory tests listed above.

Known risks and deferrals:

- Worker join script, probe wrapper, inventory daemon, cloud-provider
  bootstrap, and live two-host proof remain open in Phases 3-7.
- Enrollment secret rotation was left for follow-through in this slice and is
  closed by the later 2026-05-16 HMAC rotation entry above.
- No live callback, remote host, provider, or deploy proof was run.

## 2026-05-14 ArcPod Captain Console Mission Closeout

Scope: final closeout for the ArcPod Captain Console mission. This entry
reconciles the six waves landed between commits `b32e1da` and the current Wave
6 worktree, verifies the original onboarding Agent Name / Agent Title bug is
closed across web and public bots, records the vocabulary and route/document
sweep, and states the live gates that remain operator-authorized work. No
private state, live secrets, user Hermes homes, deploy keys, production
services, payment/provider mutation, public bot command registration, deploy,
upgrade, Docker install/upgrade, or Hermes core path was touched.

Landing map:

- Wave 0: vocabulary canon, schema foundations, SOUL overlay variables, and
  drift checks landed in `b32e1da`.
- Wave 1: web / Telegram / Discord Agent Name and Agent Title onboarding,
  post-onboarding rename/retitle, dashboard identity controls, Stripe metadata,
  deployment rows, and SOUL identity projection landed in `b32e1da`.
- Wave 2: `./deploy.sh control inventory`, manual / Hetzner / Linode inventory
  providers, ArcPod Standard Unit calculation, and ASU-aware placement landed
  in `b32e1da`.
- Wave 3: 1:1 Pod migration and executable `reprovision` admin action landed
  in `aec064e`.
- Wave 4: Pod-to-Pod Comms, share-grant-gated cross-Captain comms, MCP tools,
  and Captain/Operator Comms Console landed in `faf33dc`.
- Wave 5: Crew Training, Crew Recipes, deterministic fallback generation,
  `/train-crew`, `/whats-changed`, and additive SOUL overlay application landed
  in `5fd4aff`.
- Wave 6: ArcLink Wrapped report generation, scheduler, delivery, dashboard
  history, admin aggregate view, and `/wrapped-frequency` are complete in the
  current Wave 6 worktree and ready for the final Wave 6 commit.

Original onboarding bug verification:

- Web onboarding now renders real `Agent Name` and `Agent Title` inputs under
  the `Name The Agent` step (`web/src/app/onboarding/page.tsx`) and persists
  both fields through resume state. Browser coverage asserts both labels and
  the `Name The Agent` step in `web/tests/browser/product-checks.spec.ts`.
- Hosted onboarding stores `agent_name` and `agent_title`, writes Stripe
  metadata keys `arclink_agent_name` and `arclink_agent_title`, creates
  deployment rows with per-Pod Agent names (`Atlas`, `Atlas (Chief)`, `Atlas
  (Bosun)` for Scale), and writes `arclink_users.agent_title`; regression
  coverage lives in `tests/test_arclink_onboarding.py`.
- Telegram and Discord public bot command metadata includes `agent_name` and
  `agent_title`; the public bot flow prompts `prompt_agent_name` and
  `prompt_agent_title` before package selection and supports `/agent-name`,
  `/agent-title`, `/agent-identity`, `/rename-agent`, and `/retitle-agent`.
  `tests/test_arclink_public_bots.py` verifies capture into
  `arclink_onboarding_sessions`, post-onboarding rename/retitle updates
  `arclink_deployments`, and the identity projection contains the new Agent
  label/title.
- Provisioning consumes the stored identity via `python/arclink_provisioning.py`
  and writes `ARCLINK_AGENT_NAME`, `ARCLINK_AGENT_TITLE`, and
  `state/arclink-identity-context.json` so managed-context can inject the new
  name/title without rewriting memories or sessions.

Closeout sweep:

- Vocabulary sweep: Captain-facing surfaces were checked for stale
  `Sovereign Pod` / `Sovereign deployment` copy and migrated to the canon in
  `docs/arclink/vocabulary.md` where applicable. Operator/backend surfaces keep
  technical terms such as `deployment`, `user`, and `operator`.
- Cross-wave schema coherence: all five Wave-0 tables are now owned by runtime
  code: `arclink_inventory_machines` (inventory/ASU), `arclink_pod_messages`
  (Comms), `arclink_pod_migrations` (migration), `arclink_crew_recipes` (Crew
  Training), and `arclink_wrapped_reports` (Wrapped). No Wave-0 table remains
  purely decorative schema.
- Route/document reconciliation: `docs/API_REFERENCE.md`,
  `docs/openapi/arclink-v1.openapi.json`, `docs/arclink/architecture.md`,
  `docs/DOC_STATUS.md`, `docs/arclink/operations-runbook.md`,
  `docs/arclink/control-node-production-runbook.md`, and
  `docs/arclink/wrapped.md` were updated for the final Waves 0-6 surface.
- Steering reconciliation: `research/RALPHIE_ARCPOD_CAPTAIN_CONSOLE_STEERING.md`
  now carries a closeout status map tying each wave to the landing commit or
  final Wave 6 worktree.

Validation recorded across the wave entries above:

- Focused Python suites for schema, onboarding, public bots, Telegram, Discord,
  hosted API, API auth, provisioning, plugins, fleet, ASU, inventory providers,
  pod migration, action worker, admin actions, pod comms, MCP surfaces, crew
  recipes, Wrapped, dashboard, Docker, deploy regressions, evidence,
  notification delivery, sovereign worker, and audit trust-boundary regression
  checks passed in their respective wave validation entries.
- Web validation was recorded with `npm test`, `npm run lint`, `npm run build`,
  and `npm run test:browser`; browser proof reported 45 passed and 3 skipped
  desktop-only mobile-layout cases in the local environment.
- Shell validation recorded `bash -n deploy.sh bin/*.sh test.sh`; diff hygiene
  recorded `git diff --check`.

Skipped live gates and residual risks:

- No live Stripe, Chutes, Cloudflare, Tailscale, Hetzner, Linode, Telegram,
  Discord, Notion, Docker install/upgrade, deploy/upgrade, production service
  restart, remote SSH migration, real bot delivery, or live ArcPod Wrapped
  delivery proof was run. Those remain operator-authorized live proof work.
- The persistent trust-boundary residuals outside this mission remain as
  previously recorded: Docker socket blast radius, control upgrade upstream
  pull policy, generated secret cleanup, Cloudflare token env handling,
  idempotency surface joins, Curator approval hardening, and the
  plan-aware additional-agent price alias.
- `ralphie.sh` was intentionally kept out of ArcLink product commits. Its local
  YOLO default/config change is an operator tooling choice, not part of the
  ArcLink product surface.

## 2026-05-14 Wrapped API, Dashboard, And Bot Slice

Scope: completed the next highest-priority Phase 3 Wrapped surfaces from
`IMPLEMENTATION_PLAN.md` while preserving the existing audit gate,
core/scheduler, and delivery work. This pass stayed local: no private state,
live secrets, user Hermes homes, provider/payment mutation, public bot command
registration, deploy, upgrade, Docker install/upgrade, or Hermes core path was
touched.

Files changed:

- `python/arclink_wrapped.py`: added the Captain-visible Wrapped history read
  model that returns redacted rendered text/Markdown and excludes raw scoped
  ledger snippets.
- `python/arclink_api_auth.py` and `python/arclink_hosted_api.py`: added
  authenticated `GET /user/wrapped`, CSRF-gated `POST
  /user/wrapped-frequency`, and aggregate-only `GET /admin/wrapped`.
- `python/arclink_dashboard.py`: added Wrapped history/frequency to the
  Captain dashboard snapshot and aggregate-only Wrapped state to the admin
  dashboard snapshot.
- `python/arclink_public_bots.py`: added pure `/wrapped-frequency
  daily|weekly|monthly` handling plus Telegram underscore and Discord hyphen
  command metadata without live command registration.
- `web/src/lib/api.ts`, `web/src/app/dashboard/page.tsx`, and
  `web/src/app/admin/page.tsx`: added API client helpers, Captain Wrapped tab
  with cadence selector and report history, and Operator Wrapped tab with
  aggregate status/score only.
- `docs/API_REFERENCE.md`, `docs/openapi/arclink-v1.openapi.json`, and
  `docs/arclink/wrapped.md`: documented the new routes and privacy boundary.
- `tests/test_arclink_dashboard.py`, `tests/test_arclink_hosted_api.py`, and
  `tests/test_arclink_public_bots.py`: added regression coverage for user
  scoping, CSRF, redaction, aggregate-only admin output, dashboard snapshots,
  web API route parity, and the Raven command handler.

Validation run:

- `python3 -m py_compile python/arclink_wrapped.py python/arclink_api_auth.py python/arclink_hosted_api.py python/arclink_dashboard.py python/arclink_public_bots.py` passed.
- `python3 tests/test_arclink_wrapped.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `npm --prefix web run lint` passed.
- `npm --prefix web test` passed.
- `npm --prefix web run build` passed.
- `npm --prefix web run test:browser` passed with 45 passed and 3 skipped.
- `python3 tests/test_arclink_notification_delivery.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `git diff --check` passed.

Known risks and deferrals:

- This slice does not claim full Mission Closeout completion. Vocabulary sweep,
  original onboarding end-to-end verification, cross-wave orphan-schema
  reconciliation, full doc reconciliation, steering-doc reconciliation, and
  comprehensive six-wave closeout notes remain open in `IMPLEMENTATION_PLAN.md`.
- The bot command path is covered as a pure handler; live Telegram/Discord
  command registration remains operator-gated.
- Live delivery, production deploy/upgrade, Docker install/upgrade,
  payment/provider flows, and external credential-dependent proof were not run.

## 2026-05-14 Build Phase Verification Addendum

Scope: preserved the existing Wrapped scheduler/delivery implementation work,
re-ran the highest-priority audit gate and focused Wrapped validation, and
confirmed no additional source repair was needed in this pass. No private
state, live secrets, user Hermes homes, live provider/payment flows, public bot
mutation, deploy, upgrade, Docker install/upgrade, or Hermes core path was
touched.

Files changed in this pass:

- `research/BUILD_COMPLETION_NOTES.md`: recorded the expanded local validation
  outcome and residual risks for the current BUILD phase.

Validation run:

- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_secrets_regex.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_arclink_wrapped.py` passed.
- `python3 tests/test_arclink_notification_delivery.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 -m py_compile python/arclink_wrapped.py python/arclink_api_auth.py python/arclink_hosted_api.py python/arclink_dashboard.py python/arclink_public_bots.py python/arclink_notification_delivery.py python/arclink_provisioning.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `git diff --check` passed.

Known risks and deferrals:

- This addendum still does not claim terminal Wave 6 or Mission Closeout
  completion. Hosted API Wrapped routes, dashboard Wrapped surfaces,
  `/wrapped-frequency` bot command wiring, OpenAPI/API-reference
  reconciliation, and the full closeout sweep remain open in
  `IMPLEMENTATION_PLAN.md`.
- The local audit gate continues to treat `ME-11` and `ME-25` as
  fiction/outdated regression-awareness items only.
- Web validation was not rerun in this addendum because this pass did not touch
  `web/src/**`; the broader closeout web floor remains required before final
  mission `done`.

## 2026-05-14 Wrapped Scheduler And Delivery Slice

Scope: continued the highest-priority `IMPLEMENTATION_PLAN.md` Wave 6 tasks
after the audit gate and Wrapped core were green. This slice stayed local:
no `arclink-priv`, live secrets, user Hermes homes, production deploys,
provider/payment mutations, public bot command registration, Docker
install/upgrade, or Hermes core edits were touched.

Files changed:

- `python/arclink_wrapped.py`: added audited cadence mutation,
  quiet-hours-aware `next_attempt_at` calculation, Captain channel resolution,
  `captain-wrapped` notification enqueue, a one-cycle scheduler, failed-report
  retry recording, and persistent-failure Operator notifications without
  Captain narrative.
- `python/arclink_notification_delivery.py`: added `captain-wrapped` delivery
  through the existing public-channel delivery rail and marks matching Wrapped
  reports delivered after successful outbox delivery.
- `bin/arclink-wrapped.sh`: added the thin canonical runner for the Wrapped
  scheduler.
- `compose.yaml` and `python/arclink_provisioning.py`: added the named
  `arclink-wrapped` Docker job-loop service with no Docker socket mount.
- `tests/test_arclink_wrapped.py`: extended coverage for cadence auditing,
  quiet-hours delay, outbox shape/privacy, failed retry, and persistent
  Operator notification behavior.
- `tests/test_arclink_notification_delivery.py`: added `captain-wrapped`
  delivery coverage and report delivered-state update coverage.
- `tests/test_arclink_docker.py` and `tests/test_arclink_provisioning.py`:
  asserted the named scheduler service/runner exists and remains outside the
  Docker socket boundary.
- `docs/arclink/wrapped.md` and `research/CODEBASE_MAP.md`: reconciled the
  implemented scheduler/delivery state.

Validation run:

- `python3 -m py_compile python/arclink_wrapped.py python/arclink_notification_delivery.py python/arclink_provisioning.py` passed.
- `python3 tests/test_arclink_wrapped.py` passed.
- `python3 tests/test_arclink_notification_delivery.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `git diff --check` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.

Known risks and deferrals:

- This still does not claim full Wave 6 completion. Hosted API routes,
  dashboard Wrapped tab, `/wrapped-frequency` public bot command,
  OpenAPI/API-reference reconciliation, and the full Mission Closeout sweep
  remain open.
- Quiet-hours support intentionally parses the existing supported
  `HH:MM-HH:MM` window format and treats unsupported free-form text as no
  delay rather than inventing a new per-Captain scheduling schema.
- Live Telegram/Discord delivery, production deploy/upgrade, Docker
  install/upgrade, payment/provider flows, and public bot command registration
  remain operator-gated and were not run.

## 2026-05-14 Audit Gate And Wrapped Core Slice

Scope: executed the highest-priority current `IMPLEMENTATION_PLAN.md` tasks:
Wave 1 trust-boundary regression gate, then the first ArcLink Wrapped core
slice. No `arclink-priv`, live secrets, user Hermes homes, production deploys,
provider/payment mutations, public bot command registration, or Hermes core
edits were touched.

Files changed:

- `IMPLEMENTATION_PLAN.md`: restored the explicit domain-or-Tailscale ingress
  constraint required by the Docker documentation regression gate.
- `python/arclink_wrapped.py`: added scoped Wrapped report generation,
  frequency/period helpers, due-Captain selection, deterministic novelty
  scoring, redacted plain-text/Markdown rendering, report persistence in
  `arclink_wrapped_reports.ledger_json`, and aggregate-only admin status.
- `tests/test_arclink_wrapped.py`: added regression coverage for Captain
  scoping, redaction, deterministic score output, report persistence,
  invalid more-than-daily cadence rejection, failed-report retry eligibility,
  and admin privacy.
- `docs/arclink/wrapped.md`: documented the `wrapped_novelty_v1` formula and
  aggregate-only Operator boundary.

Validation run:

- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_secrets_regex.py` passed.
- `python3 tests/test_arclink_docker.py` initially failed because the plan no
  longer mentioned domain-or-Tailscale ingress; after the plan repair it
  passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `git diff --check` passed.
- `python3 -m py_compile python/arclink_wrapped.py` passed.
- `python3 tests/test_arclink_wrapped.py` passed.
- `python3 tests/test_arclink_schema.py` passed.

Known risks and deferrals:

- This slice does not claim full Wave 6 completion. Scheduler service,
  notification delivery enqueue/quiet-hours handling, hosted API routes,
  dashboard Wrapped tab, `/wrapped-frequency` public bot command, OpenAPI/API
  reference reconciliation, and the full Mission Closeout sweep remain open.
- `ME-11` and `ME-25` from the May 11 audit remain fiction/outdated regression
  awareness items only, not open implementation backlog.
- Live Stripe, Chutes, Cloudflare, Tailscale, Telegram, Discord, Notion,
  remote Docker host, deploy/upgrade, Docker install/upgrade, public-bot
  mutation, and payment-flow proof remain operator-gated and were not run.

## 2026-05-14 ArcPod Captain Console Wave 0/1 Build Slice

Scope: executed the highest-priority current ArcPod Captain Console plan slice:
Wave 0 vocabulary/schema/SOUL foundations and Wave 1 onboarding Agent Name +
Agent Title flow. Existing dirty-tree work was preserved. No `arclink-priv`,
live secrets, production deploys, live providers, payment mutation, public bot
mutation, or Hermes core edits were touched.

Changed behavior:

- Added the canonical vocabulary reference and marked it in the docs status
  map; kept Operator/backend terminology on operator/admin surfaces.
- Added Wave 0 schema columns/tables/status drift checks for Agent titles,
  Crew Training, inventory, pod messages, pod migrations, and Wrapped reports.
- Added web onboarding Agent Name and Agent Title inputs, resume persistence,
  API payload fields, Stripe metadata propagation, Scale naming suffixes, and
  deployment/user identity persistence.
- Added Telegram/Discord public-bot Agent identity prompts and commands,
  plus dashboard/API/public-bot rename and retitle surfaces with CSRF/audit/DB
  updates.
- Added post-launch local identity projection for rename/retitle: when a
  provisioned Pod's local Hermes home is present in deployment state roots,
  ArcLink updates `state/arclink-identity-context.json` without a gateway
  restart so managed-context can inject the new Agent name/title on the next
  turn.
- Repaired the provisioning/SOUL path so captured `agent_name` and
  `agent_title` reach `ARCLINK_AGENT_NAME`, `ARCLINK_AGENT_TITLE`,
  `SOUL.md`, `arclink-identity-context.json`, and the managed-context
  `[local:identity]` projection.

Validation run:

- `python3 -m py_compile python/arclink_control.py python/arclink_public_bots.py python/arclink_onboarding.py python/arclink_api_auth.py python/arclink_hosted_api.py python/arclink_telegram.py python/arclink_discord.py python/arclink_headless_hermes_setup.py python/arclink_dashboard.py` passed.
- `python3 -m py_compile python/arclink_provisioning.py python/arclink_headless_hermes_setup.py` passed.
- `python3 -m py_compile plugins/hermes-agent/arclink-managed-context/__init__.py` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_control_db.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_headless_hermes_setup.py` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `npm --prefix web test` passed.
- `npm --prefix web run lint` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `git diff --check` passed.

Known risks and deferrals:

- Post-launch rename/retitle now refreshes a local provisioned Pod's
  managed-context identity file when its Hermes home exists on the control
  node. Remote fleet projection remains proof-gated until the Wave 2/3 worker
  transport path lands; the helper skips missing local Hermes homes rather than
  creating control-node lookalike paths.
- Wave 2 and later surfaces remain unimplemented in this slice.
- Live Stripe, Chutes, Cloudflare, Tailscale, Telegram, Discord, Notion, remote
  Docker host, deploy/upgrade, Docker install/upgrade, public-bot mutation, and
  real payment-flow proof remain explicit operator-authorized live gates.

## 2026-05-12 Three-Pass Sovereign Revisit

Scope: performed three additional local passes over the Sovereign control-node
surface: public API/auth/webhook contracts, browser user journeys, and
deployment/runtime packaging. No private state, live providers, production
deploys, public bot mutations, Docker install/upgrade, remote Docker hosts, or
payment-flow live proof were touched.

Findings and fixes:

- Admin action UI still merged disabled actions with `pending_not_implemented`
  using fallback semantics in the action form. Fixed it to display the union of
  unavailable/proof-gated actions and restored `comp` to the default executable
  fallback list.
- The web API client tests still modeled legacy header-supplied session
  credentials instead of the current HttpOnly-cookie plus CSRF browser contract.
  Updated the client test harness, added missing share-grant client methods,
  and expanded route parity coverage across onboarding claim/cancel/status,
  share grants, provider/admin snapshots, health, and adapter-mode.
- Hosted API preflight 405 responses could serialize as `405 OK` through the
  WSGI status-text helper. Added the correct status text and regression
  coverage.
- Browser CORS still allowed ArcLink session-id/session-token headers even
  though browser transport is cookie-only. Tightened allowed headers to
  `Content-Type`, `X-ArcLink-CSRF-Token`, and `X-ArcLink-Request-Id`.
- `detect_github_repo` still defaulted generated GitHub branch references to
  `main`. Switched the default to `${ARCLINK_UPSTREAM_BRANCH:-arclink}` and
  added a deploy regression.
- `.dockerignore` excluded private state but not common generated/build/runtime
  state such as `node_modules`, `.next`, and SQLite files. Added those excludes
  and expanded Docker regression coverage.
- The fake E2E journey still queued admin mutations with header credentials.
  Updated it to exercise browser cookies plus CSRF for admin actions and user
  portal mutations, matching the hardened hosted API contract.
- One hosted API test function existed but was not invoked by the manual test
  runner; wired it into the runner and updated the printed count.

Validation run:

- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `cd web && npm test` passed.
- `python3 tests/test_arclink_e2e_fake.py` passed.
- Sovereign focused Python sweep passed:
  `test_arclink_api_auth.py`, `test_arclink_admin_actions.py`,
  `test_arclink_action_worker.py`, `test_arclink_executor.py`,
  `test_arclink_sovereign_worker.py`, `test_arclink_control_db.py`,
  `test_arclink_provisioning.py`, `test_arclink_entitlements.py`,
  `test_arclink_telegram.py`, `test_arclink_discord.py`,
  `test_arclink_live_runner.py`, `test_arclink_fleet.py`,
  `test_arclink_ingress.py`, `test_arclink_secrets_regex.py`,
  `test_arclink_product_surface.py`, and `test_arclink_live_journey.py`.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.
- `cd web && npm run lint` passed.
- `cd web && npm run build` passed.
- `cd web && npm run test:browser` passed.
- `./bin/ci-preflight.sh` passed.
- `git diff --check` passed.

Remaining boundary:

- Live Stripe, Chutes, Cloudflare, Tailscale, Telegram, Discord, Notion, remote
  Docker host, deploy/upgrade, Docker install/upgrade, public-bot mutation, and
  real payment-flow proof remain explicit operator-authorized live gates.

## 2026-05-12 Audit Closure Revisit

Scope: revisited the full
`research/RALPHIE_SOVEREIGN_AUDIT_VERIFICATION_20260511.md` report against the
current committed tree after the audit hardening checkpoint. No private state,
live secrets, production services, external providers, payment flows, public bot
mutations, Docker install/upgrade flows, deploys, upgrades, or
credential-dependent checks were touched.

Findings:

- Source scans and prior focused coverage show the FACT and actionable PARTIAL
  findings have local source-level remediations or corrected/outdated
  verification, with regression coverage across the remediated risk surfaces.
- `IMPLEMENTATION_PLAN.md` still had all phase checklist boxes open even though
  source and completion notes showed Phases 0-5 were locally closed; updated the
  plan to reflect current source reality and the still-gated live proof posture.
- `research/RALPHIE_SOVEREIGN_AUDIT_VERIFICATION_20260511.md` lacked a closure
  addendum; added one clarifying that no source gaps remain and live proof was
  not run.
- `research/COVERAGE_MATRIX.md` still described terminal completion as future
  tense; updated it with the local closure state and live/operator proof
  boundary.
- `web/tests/browser/product-checks.spec.ts` still mocked `comp` as pending even
  though backend action readiness exposes `comp` as executable when probes pass;
  aligned the fixture with backend behavior.

Validation run:

- `git diff --check` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_secrets_regex.py` passed.
- `cd web && npm test` passed.
- `./bin/ci-preflight.sh` passed.

Remaining live/operator gates:

- No live Stripe, Chutes, Cloudflare, Tailscale, Telegram, Discord, Notion,
  remote Docker host, ingress, deploy, upgrade, Docker install/upgrade,
  payment-flow, or public-bot mutation proof was run. Those require explicit
  operator authorization and real credentials.

## 2026-05-12 Ralphie Attempt 2 Phase 2 Artifact Repair

Scope: re-attempted the highest-priority open `IMPLEMENTATION_PLAN.md` slice
after Wave 1: Phase 2 side effects, idempotency, and race controls. Existing
dirty-tree implementation work was preserved. No private state, live secrets,
production services, external providers, payment flows, public bot mutations,
Docker install/upgrade flows, deploys, upgrades, or credential-dependent
checks were touched.

- Re-ran the Wave 1 validation floor first because the retry note referenced
  prior machine-check failure.
- Re-ran Phase 2 focused validation and marked the Phase 2 checklist complete
  only after the current tests passed.
- Left later open phases, broad release validation, and live/operator proof
  gates open.

Verification run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_hosted_api.py python/arclink_api_auth.py python/arclink_telegram.py python/arclink_discord.py python/arclink_secrets_regex.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_secrets_regex.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_loopback_service_hardening.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_fleet.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_live_runner.py` passed.
- `python3 tests/test_arclink_control_db.py` passed.

Known risks:

- This is local non-live proof only. Live Stripe/Chutes/payment effects,
  public bot mutations, remote Docker host behavior, ingress, deploy, upgrade,
  and Docker install/upgrade proof remain authorization/credential gated.
- Phase 3 and later checklist items remain open in `IMPLEMENTATION_PLAN.md`;
  terminal BUILD completion is not claimed in this slice.

## 2026-05-12 Ralphie Wave 1 Plan Reconciliation

Scope: executed the active highest-priority `IMPLEMENTATION_PLAN.md` slice:
Phase 0 inventory and Phase 1 Wave 1 trust-boundary proof. The current source
already contained the required Wave 1 behavior, so this pass changed only
planning/completion notes. Existing dirty-tree implementation edits were
preserved, and no private state, live secrets, production services, external
providers, payment flows, public bot mutations, Docker install/upgrade flows,
deploys, upgrades, or credential-dependent checks were touched.

- Marked Phase 0 and Phase 1 Wave 1 checklist items complete in
  `IMPLEMENTATION_PLAN.md` after direct source/test verification.
- Verified `ME-11` and `ME-25` remained FICTION/outdated awareness items only.
- Left later implementation phases and live/operator-authorization gates open.

Verification run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_hosted_api.py python/arclink_api_auth.py python/arclink_telegram.py python/arclink_discord.py python/arclink_secrets_regex.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_secrets_regex.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_loopback_service_hardening.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.

Known risks:

- This is local non-live proof only. Live provider, payment, public bot,
  remote Docker host, ingress, deploy, upgrade, and Docker install/upgrade
  behavior remain gated by explicit operator authorization and real
  credentials.
- Later plan phases remain unchecked in `IMPLEMENTATION_PLAN.md`; terminal
  BUILD completion is not claimed in this slice.

## 2026-05-12 Ralphie Wave 1 Active Checklist Execution

Scope: executed the highest-priority active `IMPLEMENTATION_PLAN.md` slice:
Phase 0 inventory plus Phase 1 Wave 1 trust-boundary validation. The current
source already contained the Wave 1 repairs, so this pass made no runtime code
changes. No private state, live secrets, production services, external
providers, payment flows, public bot mutations, Docker install/upgrade flows,
deploys, upgrades, or credential-dependent checks were touched.

- Confirmed the dirty worktree before patching and preserved unrelated
  existing edits.
- Re-read the active audit verification entries for Wave 1 and kept `ME-11`
  and `ME-25` as FICTION/outdated regression-awareness items only.
- Marked Phase 0, Phase 1, and focused-validation note tasks complete in
  `IMPLEMENTATION_PLAN.md` after local proof.

Verification run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_hosted_api.py python/arclink_api_auth.py python/arclink_telegram.py python/arclink_discord.py python/arclink_secrets_regex.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_secrets_regex.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_loopback_service_hardening.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.

Known risks:

- This was local non-live proof only. Live provider, payment, public bot,
  remote Docker host, ingress, deploy, upgrade, and Docker install/upgrade
  behavior remain gated by explicit operator authorization and real
  credentials.
- Later plan phases remain unchecked in `IMPLEMENTATION_PLAN.md`; terminal
  BUILD completion is not claimed in this slice.

## 2026-05-12 Ralphie Broad Non-Live Validation Reconciliation

Scope: after focused Phase 2-5 validation passed, ran the broad non-live
preflight gate. No private state, live provider, payment, bot mutation, Docker
host mutation, deploy, upgrade, Docker install/upgrade, production ingress
proof, or credential-dependent check was performed.

Verification run:

- `./bin/ci-preflight.sh` passed.

Skipped gates:

- `./test.sh` was not run because it invokes the sudo install smoke and can
  mutate host state.
- Browser Playwright proof was not run.
- No live Stripe, Chutes, Cloudflare, Tailscale, Notion, Telegram, Discord,
  Docker host, ingress, deploy, upgrade, Docker install/upgrade, payment flow,
  or public bot proof was run.

Known risks:

- `IMPLEMENTATION_PLAN.md` still keeps the live/operator authorization gate
  unchecked. Terminal BUILD completion should not be claimed until any desired
  live proof is explicitly authorized and run, or deferred with operator-facing
  risk.

## 2026-05-12 Ralphie Phase 5 Active Checklist Reconciliation

Scope: executed the next active plan slice after Phase 4: web/API response
shape contracts, hosted API connection behavior, 404 provisioning status,
action readiness and rate limits, action-worker initialization, CORS/cookie
posture, checkout cancel/admin fetch gating, deploy branch/systemd quoting,
SSH executor boundaries, Notion/qmd hardening, and remaining operational
honesty cleanup. The current source already contained the implementation
repairs, so this slice made no runtime code changes. No private state, live
provider, payment, bot mutation, Docker host mutation, deploy, upgrade, or
Docker install/upgrade activity was performed.

- Verified source behavior for canonical backend/web response shapes, per-
  request WSGI connection support, clean missing-provisioning 404s, action
  readiness/admin rate limits, one-time action-worker connection/schema setup,
  narrowed CORS and local cookie behavior, checkout cancel backend wiring,
  admin secondary-fetch gating, `arclink` upstream branch defaults, quoted
  systemd environment values, SSH executor allowlisting, Notion conflict and
  parent-walk behavior, qmd loopback binding, hardened git protocol flags,
  valid UI action reset behavior, and explicit live-proof env opt-ins.
- Marked Phase 5 complete in `IMPLEMENTATION_PLAN.md` after focused local
  validation.

Verification run:

- `python3 tests/test_arclink_hosted_api.py` passed in the Phase 4 run.
- `python3 tests/test_arclink_dashboard.py` passed in the Phase 3 run.
- `python3 tests/test_arclink_action_worker.py` passed in the Phase 2 run.
- `python3 tests/test_arclink_live_runner.py` passed in the Phase 2 run.
- `python3 tests/test_loopback_service_hardening.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_notion_ssot.py` passed.
- `python3 tests/test_arclink_repo_sync.py` passed.
- `python3 tests/test_arclink_notification_delivery.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.
- `cd web && npm test` passed.
- `cd web && npm run lint` passed.
- `cd web && npm run build` passed.

Known risks:

- Broad release validation remains separate from this focused implementation
  block.
- Live provider, payment, public bot, remote Docker host, ingress, deploy, and
  upgrade behavior remain credential/authorization gated.

## 2026-05-12 Ralphie Phase 4 Active Checklist Reconciliation

Scope: executed the next active plan slice after Phase 3: schema, TTL,
identity, stale onboarding, duplicate-email handling, protected status,
memory-synthesis framing, timestamp normalization, evidence timestamp output,
and drift hygiene. The current source already contained the implementation
repairs, so this slice made no runtime code changes. No private state, live
provider, payment, bot mutation, Docker host mutation, deploy, upgrade, or
Docker install/upgrade activity was performed.

- Verified source behavior for deterministic email merge, high-value
  schema/status checks, subscription drift classification, explicit staged
  revoke transaction assertions, TTL/one-time reveal behavior for handoffs and
  shares, stale onboarding expiry, protected user status preservation,
  duplicate-email onboarding reuse/fail-loud behavior by corrected scope,
  memory-synthesis source framing, cached handoff recovery metadata, indexes,
  active-factor uniqueness, evidence timestamp null semantics, and grouped
  migration safety.
- Marked Phase 4 complete in `IMPLEMENTATION_PLAN.md` after focused local
  validation.

Verification run:

- `python3 tests/test_arclink_control_db.py` passed in the Phase 2 run.
- `python3 tests/test_arclink_entitlements.py` passed in the Phase 2 run.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_evidence.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.

Known risks:

- This is local proof only. Existing live databases may still require
  operator-planned migration/drift review before production rollout.
- Later active plan phases remain unchecked in `IMPLEMENTATION_PLAN.md`, so
  this is not terminal BUILD completion.

## 2026-05-12 Ralphie Phase 3 Active Checklist Reconciliation

Scope: executed the next active plan slice after Phase 2: cancellation,
teardown, cleanup, port release, DNS drift, compose/DNS status honesty,
identifier safety, and DNS status preservation. The current source already
contained the implementation repairs, so this slice made no runtime code
changes. No private state, live provider, payment, bot mutation, Docker host
mutation, deploy, upgrade, or Docker install/upgrade activity was performed.

- Verified source behavior for teardown lifecycle, local and remote secret
  material cleanup, inactive deployment port filtering, cancelled/torn-down DNS
  drift suppression, safe deployment-derived database names, project-aware
  compose status, provider/transport failure reporting, private secret file
  materialization, and unchanged DNS row status preservation.
- Marked Phase 3 complete in `IMPLEMENTATION_PLAN.md` after focused local
  validation.

Verification run:

- `python3 tests/test_arclink_executor.py` passed in the Phase 2 run.
- `python3 tests/test_arclink_sovereign_worker.py` passed in the Phase 2 run.
- `python3 tests/test_arclink_ingress.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.

Known risks:

- This is local proof only. Live DNS provider behavior, remote Docker hosts,
  and production teardown remain unproven without explicit operator
  authorization.
- Later active plan phases remain unchecked in `IMPLEMENTATION_PLAN.md`, so
  this is not terminal BUILD completion.

## 2026-05-12 Ralphie Phase 2 Active Checklist Reconciliation

Scope: executed the next highest-priority active plan slice after Wave 1:
Phase 2 side effects, idempotency, and race controls. The current source
already contained the implementation repairs, so this slice made no runtime
code changes. No private state, live provider, payment, bot mutation, Docker
host mutation, deploy, upgrade, or Docker install/upgrade activity was
performed.

- Verified source behavior for live Stripe/Chutes adapter execution or
  fail-closed behavior, atomic action claims with hardened DB connections,
  guarded refuel spending, durable operation idempotency, atomic placement,
  entitlement/user rechecks, audit-before-side-effect ordering,
  server-derived DNS/Stripe metadata, honest live-proof failure status,
  Stripe webhook duplicate handling, dashboard password hash stability, and
  safe action-worker error codes.
- Marked Phase 2 complete in `IMPLEMENTATION_PLAN.md` after focused local
  validation.

Verification run:

- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_fleet.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_live_runner.py` passed.
- `python3 tests/test_arclink_control_db.py` passed.

Known risks:

- This is local proof only; live provider calls, payment effects, Docker host
  behavior, ingress, and production deploy paths remain unproven without
  explicit operator authorization.
- Later active plan phases remain unchecked in `IMPLEMENTATION_PLAN.md`, so
  this is not terminal BUILD completion.

## 2026-05-12 Ralphie Wave 1 Checklist Reconciliation

Scope: executed the active highest-priority checklist slice from
`IMPLEMENTATION_PLAN.md`: Phase 0 inventory plus Phase 1 Wave 1 trust-boundary
validation. No private state, live secrets, production services, external
providers, payment flows, public bot mutations, Docker install/upgrade flows,
deploys, or upgrades were touched.

- Verified the current source still contains the Wave 1 security repairs for
  Telegram webhook secrets, non-root/scoped Docker runtime policy,
  auth-before-CSRF mutation ordering, Discord timestamp/replay protection,
  hosted API body caps and `invalid_json`, CORS/preflight behavior, backend
  CIDR enforcement, peppered session hashes, centralized secret redaction,
  webhook rate limits, browser/API auth separation, generic auth failures, and
  session-kind enforcement.
- Marked Phase 0 and Phase 1 checklist items complete in
  `IMPLEMENTATION_PLAN.md`.
- Restored the required `domain-or-Tailscale ingress` proof-gate wording in
  `IMPLEMENTATION_PLAN.md` after the Docker regression caught it missing.

Verification run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_hosted_api.py python/arclink_api_auth.py python/arclink_telegram.py python/arclink_discord.py python/arclink_secrets_regex.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_secrets_regex.py` passed.
- `python3 tests/test_loopback_service_hardening.py` passed.
- `python3 tests/test_arclink_docker.py` initially failed on the missing plan
  ingress wording and passed after the plan repair.

Known risks:

- This slice proves Wave 1 locally only. Later unchecked plan phases still need
  focused validation in this active checklist before terminal BUILD completion
  is declared.
- Live provider, payment, public bot, remote Docker host, ingress, deploy, and
  upgrade proof remain credential/authorization gated.

## 2026-05-12 Ralphie Broad Non-Live Preflight

Scope: after focused Phase 1-5 validation passed, ran the broad non-live
preflight gate that does not require live credentials or sudo install smoke.

Verification run:

- `./bin/ci-preflight.sh` passed.

Skipped gates:

- `./test.sh` was not run because it invokes `sudo bin/ci-install-smoke.sh` and
  can mutate host state.
- Browser Playwright proof was not run.
- No live provider, payment, public bot, remote Docker host, ingress, deploy,
  or upgrade proof was run.

## 2026-05-12 Ralphie Phase 5 Local Validation Reconciliation

Scope: executed the final implementation checklist block before broad release
validation: web/API shape contracts, action readiness and rate limits,
action-worker initialization, CORS/cookie posture, checkout cancel/admin fetch
gating, deploy branch/systemd quoting, Notion/qmd runtime hardening, and
remaining low operational-honesty cleanup. No private state, live provider,
payment, bot mutation, Docker host mutation, deploy, upgrade, or Docker
install/upgrade activity was performed.

- Confirmed current source/tests cover canonical reconciliation/audit shapes,
  action readiness and admin action rate limits, one-time action-worker
  connection/schema setup, narrowed CORS and local cookie behavior,
  checkout-cancel backend wiring, admin secondary-fetch gating, `arclink`
  upstream branch defaults, quoted systemd environment values, Notion conflict
  and parent-walk behavior, qmd loopback binding, hardened git protocol flags,
  valid action reset behavior, and explicit live-proof env opt-ins.
- Marked Phase 5 complete in `IMPLEMENTATION_PLAN.md` after focused local
  validation.

Verification run:

- `python3 tests/test_arclink_hosted_api.py` passed in the Wave 1 run.
- `python3 tests/test_arclink_dashboard.py` passed in the Phase 3 run.
- `python3 tests/test_arclink_action_worker.py` passed in the Phase 2 run.
- `python3 tests/test_arclink_live_runner.py` passed in the Phase 2 run.
- `python3 tests/test_loopback_service_hardening.py` passed in the Wave 1 run.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_notion_ssot.py` passed.
- `python3 tests/test_arclink_repo_sync.py` passed.
- `python3 tests/test_arclink_notification_delivery.py` passed.
- `cd web && npm test` passed.
- `cd web && npm run lint` passed.
- `cd web && npm run build` passed.

Known risks:

- Broad release validation (`./bin/ci-preflight.sh`, `./test.sh`, and browser
  Playwright proof) was not run in this slice.
- Live provider, payment, public bot, remote Docker host, ingress, deploy, and
  upgrade behavior remain credential/authorization gated.

## 2026-05-12 Ralphie Phase 4 Local Validation Reconciliation

Scope: executed the next unchecked plan slice after Phase 3: schema, TTL,
identity, stale onboarding, duplicate-email, status, and drift hygiene. No
private state, live provider, payment, bot mutation, Docker host mutation,
deploy, upgrade, or Docker install/upgrade activity was performed.

- Confirmed current source/tests cover deterministic email merge, high-value
  schema/status checks, subscription drift classification, explicit staged
  revoke transaction assertions, TTL/one-time reveal behavior for handoffs and
  shares, stale onboarding expiry, protected user status preservation,
  duplicate-email onboarding reuse/fail-loud behavior by corrected scope,
  indexes, active-factor uniqueness, evidence timestamp null semantics, and
  grouped migration safety.
- Marked Phase 4 complete in `IMPLEMENTATION_PLAN.md` after focused local
  validation.

Verification run:

- `python3 tests/test_arclink_control_db.py` passed in the Phase 2 run and
  covers operation idempotency plus Wave 4 schema/status/index checks.
- `python3 tests/test_arclink_api_auth.py` passed in the Wave 1 run and covers
  staged revoke transaction assertions plus handoff/share behavior.
- `python3 tests/test_arclink_hosted_api.py` passed in the Wave 1 run and
  covers handoff/share API behavior and past-due provider-state handling.
- `python3 tests/test_arclink_entitlements.py` passed in the Phase 2 run and
  covers subscription state/drift behavior.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_evidence.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.

Known risks:

- This is local proof only. Existing live databases may still require
  operator-planned migration/drift review before production rollout.

## 2026-05-12 Ralphie Phase 3 Local Validation Reconciliation

Scope: executed the next unchecked plan slice after Phase 2: cancellation,
teardown, cleanup, port release, DNS drift, compose/DNS status honesty, and DNS
status preservation. No private state, live provider, payment, bot mutation,
Docker host mutation, deploy, upgrade, or Docker install/upgrade activity was
performed.

- Confirmed current source/tests cover teardown from requested/cancelled to
  torn down, local and remote materialized-secret cleanup, inactive deployment
  port release/filtering, cancelled/torn-down DNS drift suppression,
  project-aware compose status with transport failure surfacing, and preserving
  provisioned DNS row status for unchanged desired records.
- Marked Phase 3 complete in `IMPLEMENTATION_PLAN.md` after focused local
  validation.

Verification run:

- `python3 tests/test_arclink_executor.py` passed in the Phase 2 run and covers
  compose secret cleanup plus lifecycle transport failure behavior.
- `python3 tests/test_arclink_sovereign_worker.py` passed in the Phase 2 run
  and covers teardown lifecycle, port release, compose status, and DNS teardown.
- `python3 tests/test_arclink_ingress.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.

Known risks:

- This is local proof only. Live DNS provider behavior, remote Docker hosts,
  and production teardown remain unproven without explicit operator
  authorization.

## 2026-05-12 Ralphie Phase 2 Local Validation Reconciliation

Scope: executed the next highest-priority unchecked plan slice after Wave 1:
Phase 2 side effects, idempotency, and race controls. No private state, live
provider, payment, bot mutation, Docker host mutation, deploy, upgrade, or
Docker install/upgrade activity was performed.

- Confirmed current source/tests cover live Stripe/Chutes adapter execution or
  fail-closed behavior, atomic action claims, guarded refuel spending, durable
  operation idempotency, active placement uniqueness, entitlement/user rechecks,
  audit-before-side-effect recording, server-derived DNS/Stripe metadata, and
  honest live-proof non-success behavior.
- Marked Phase 2 complete in `IMPLEMENTATION_PLAN.md` after focused local
  validation.

Verification run:

- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_fleet.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_live_runner.py` passed.
- `python3 tests/test_arclink_control_db.py` passed.

Known risks:

- This is local proof only; live provider calls, payment effects, Docker host
  behavior, ingress, and production deploy paths remain unproven without
  explicit operator authorization.

## 2026-05-12 Ralphie Wave 1 Plan Reconciliation

Scope: executed the highest-priority active plan slice against the current
dirty public worktree: Phase 0 inventory plus Wave 1 trust-boundary source
inspection and validation. No private state, live secrets, production service,
provider, payment, public bot, Docker install/upgrade, deploy, or upgrade
activity was performed.

- Verified the active audit wording for Wave 1 before editing.
- Confirmed the current source and tests already close the Wave 1 trust-boundary
  IDs: CR-1, CR-2, CR-6, CR-7, CR-8, CR-9, CR-11, HI-1, HI-4, HI-7, ME-2,
  ME-3, ME-4, ME-12, ME-13, LOW-1, LOW-8, and LOW-9.
- Marked Phase 0 and Phase 1 complete in `IMPLEMENTATION_PLAN.md` after local
  focused proof.
- Restored the Sovereign domain-or-Tailscale ingress proof-gate wording in the
  active plan so the Docker documentation regression remains covered.

Verification run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_hosted_api.py python/arclink_api_auth.py python/arclink_telegram.py python/arclink_discord.py python/arclink_secrets_regex.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_secrets_regex.py` passed.
- `python3 tests/test_loopback_service_hardening.py` passed.
- `python3 tests/test_arclink_docker.py` initially failed on missing plan
  ingress wording and passed after the plan repair.

Skipped live/broad gates:

- No live Stripe, Chutes, Cloudflare, Tailscale, Notion, Telegram, Discord,
  Docker host mutation, deploy, upgrade, Docker install/upgrade, payment flow,
  public bot mutation, production ingress proof, `./bin/ci-preflight.sh`,
  `./test.sh`, or browser Playwright proof was run.

Known risks:

- This proves Wave 1 locally only. Terminal BUILD completion still requires
  later FACT/actionable PARTIAL items to be fixed or explicitly deferred, plus
  operator-authorized live proof for provider/host/ingress behavior.

## 2026-05-12 Ralphie Plan Reconciliation And Local Validation

Scope: executed the highest-priority active plan tasks against the current
dirty public worktree: Phase 0 inventory, Wave 1 validation, then focused
later-wave local validation for already-modified implementation surfaces. No
private state, live provider, payment, bot mutation, Docker host mutation,
deploy, upgrade, or Docker install/upgrade activity was performed.

- Verified the active audit file and current dirty-tree state before changing
  code.
- Re-ran the Wave 1 validation floor. Runtime/security surfaces passed; the
  only failure was the Docker documentation regression test requiring the active
  plan to retain the Sovereign domain-or-Tailscale ingress wording.
- Restored that plan contract wording in `IMPLEMENTATION_PLAN.md` and marked
  Phase 0 plus Phase 1 Wave 1 trust-boundary tasks complete after focused
  validation.
- Ran the later-wave focused validation floor and marked locally implemented
  Phase 2 through Phase 5 tasks complete in `IMPLEMENTATION_PLAN.md`; broad
  release validation remains open.
- `ME-11` and `ME-25` remain FICTION/outdated regression-awareness items only.

Verification run:

- `git diff --check` passed before and after the plan patch.
- `python3 -m py_compile python/arclink_hosted_api.py python/arclink_api_auth.py python/arclink_telegram.py python/arclink_discord.py python/arclink_secrets_regex.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_secrets_regex.py` passed.
- `python3 tests/test_loopback_service_hardening.py` passed.
- `python3 tests/test_arclink_docker.py` initially failed on missing plan
  wording, then passed after the plan repair.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_fleet.py` passed.
- `python3 tests/test_arclink_ingress.py` passed.
- `python3 tests/test_arclink_live_runner.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_arclink_control_db.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_evidence.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_memory_synthesizer.py` passed.
- `python3 tests/test_arclink_agent_user_services.py` passed.
- `python3 tests/test_arclink_notification_delivery.py` passed.
- `python3 tests/test_arclink_notion_knowledge.py` passed.
- `python3 tests/test_notion_ssot.py` passed.
- `python3 tests/test_arclink_repo_sync.py` passed.
- `cd web && npm test` passed.
- `cd web && npm run lint` passed.
- `cd web && npm run build` passed.

Skipped live/broad gates:

- No live Stripe, Chutes, Cloudflare, Tailscale, Notion, Telegram, Discord,
  Docker host mutation, deploy, upgrade, Docker install/upgrade, payment flow,
  public bot mutation, production ingress proof, `./bin/ci-preflight.sh`,
  `./test.sh`, or browser Playwright proof was run.

Known risks:

- This pass proves focused local validation only. Broad release validation
  remains separate: `./bin/ci-preflight.sh`, `./test.sh`, and browser
  Playwright proof were not run.
- Local validation does not prove production provider credentials, public bot
  mutation, Docker host behavior, or live ingress.

## 2026-05-12 Ralphie Plan Recheck And Fleet Schema Repair

Scope: executed the highest-priority remaining local BUILD task against the
current dirty public worktree: reconcile stale plan status with source/tests,
then fix the first validation regression found. No private state, live
provider, payment, bot mutation, Docker host mutation, deploy, upgrade, or
Docker install/upgrade activity was performed.

- Fixed a fresh-schema regression in `python/arclink_control.py`: fleet host
  status `CHECK` constraints and drift status constants now match the existing
  fleet writer contract of `active`, `degraded`, and `offline`.
- Rationale: changed the control-plane schema contract instead of the fleet
  writer/tests because `python/arclink_fleet.py` already treats draining as a
  separate boolean and uses `offline` for unhealthy hosts.
- Updated `IMPLEMENTATION_PLAN.md` to mark locally implemented/verified Wave
  1-5 items complete, while leaving broad release validation as a remaining
  non-live gate.

Verification run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_hosted_api.py python/arclink_api_auth.py python/arclink_telegram.py python/arclink_discord.py python/arclink_secrets_regex.py python/arclink_executor.py python/arclink_action_worker.py python/arclink_control.py python/arclink_sovereign_worker.py python/arclink_fleet.py python/arclink_ingress.py python/arclink_dashboard.py python/arclink_evidence.py python/arclink_live_runner.py python/arclink_notion_ssot.py python/arclink_memory_synthesizer.py python/arclink_provisioning.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_secrets_regex.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_fleet.py` initially failed on the stale fleet
  host status constraint, then passed after the schema repair.
- `python3 tests/test_arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_control_db.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_live_runner.py` passed.
- `python3 tests/test_arclink_evidence.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_loopback_service_hardening.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_arclink_agent_user_services.py` passed.
- `python3 tests/test_arclink_repo_sync.py` passed.

Skipped live/broad gates:

- No live Stripe, Chutes, Cloudflare, Tailscale, Notion, Telegram, Discord,
  Docker host mutation, deploy, upgrade, Docker install/upgrade, payment flow,
  public bot mutation, or production ingress proof was run.
- `./bin/ci-preflight.sh`, `./test.sh`, and web lint/test/build/browser proof
  were not rerun in this slice.

Known risks:

- The local BUILD checklist is now source/test aligned, but production
  completion still requires operator-authorized live provider/host proof.
- Existing databases created with earlier local schema drafts may still need
  operator-planned drift remediation if they contain `draining` or `disabled`
  as fleet host statuses; current fleet writer paths do not create those
  values.

## 2026-05-11 Ralphie Build Recheck: Wave 1 Validation Floor

Scope: executed the current Wave 1 validation floor from
`IMPLEMENTATION_PLAN.md` against the dirty public worktree only. No private
state, live secrets, production service, provider, payment, public bot, Docker
install/upgrade, deploy, or upgrade activity was performed.

- Fixed plan/test regression: restored the Sovereign Control Node
  domain-or-Tailscale ingress contract wording in `IMPLEMENTATION_PLAN.md` so
  the Docker documentation regression remains covered.
- Marked Phase 0 and Phase 1 checklist items complete after source-grounded
  inspection and focused validation.
- Proved Wave 1 audit IDs locally: CR-1, CR-2, CR-6, CR-7, CR-8, CR-9,
  CR-11, HI-1, HI-4, HI-7, ME-2, ME-3, ME-4, ME-12, ME-13, LOW-1, LOW-8, and
  LOW-9.
- Confirmed ME-11 and ME-25 remain FICTION/outdated regression-awareness items
  per the audit ground truth.

Verification run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_hosted_api.py python/arclink_api_auth.py python/arclink_telegram.py python/arclink_discord.py python/arclink_secrets_regex.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_secrets_regex.py` passed.
- `python3 tests/test_arclink_docker.py` passed after the plan wording fix.
- `python3 tests/test_loopback_service_hardening.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.

Skipped live checks:

- No live Stripe, Chutes, Cloudflare, Tailscale, Notion mutation, Docker host
  mutation, deploy, upgrade, Docker install/upgrade, payment flow, public bot
  mutation, or production ingress proof was run.

Known risks:

- Local validation does not prove production provider credentials, public bot
  mutation, Docker host behavior, or live ingress.
- Later plan phases remain outside this recheck unless covered by prior local
  completion notes or a future focused validation pass.

## 2026-05-11 Ralphie Residual Closure: Final Local Proof

Scope: closed the remaining residual closure checklist from
`IMPLEMENTATION_PLAN.md` using local source inspection and focused tests only.
No private state, live host, provider, payment, bot mutation, Docker
install/upgrade, deploy, or upgrade activity was performed. Existing dirty-tree
Wave 1-5 and residual implementation work was preserved.

- Fixed/proved audit IDs: HI-8, ME-14, ME-15, ME-18, LOW-11, LOW-12, LOW-14,
  and LOW-15.
- Wave 1 checkpoint re-verification: source still shows Telegram webhook
  secret enforcement, Discord timestamp validation plus interaction
  reservation, provider-scoped webhook rate limits, hosted API body caps and
  CIDR protection, auth-before-CSRF logout ordering, peppered session/CSRF
  token hashing, and shared redaction through `arclink_secrets_regex`.
- HI-8: `tests/test_arclink_executor.py` now proves materialized Compose
  secret copies are cleaned after local runner failure and SSH compose failure
  after remote sync.
- ME-14: `tests/test_memory_synthesizer.py` proves source-content hashing,
  secret redaction, and unsafe model-output rejection on untrusted synthesis
  input.
- ME-15: executor/worker tests prove SSH Docker execution is explicit
  machine-mode work and requires a host allowlist.
- ME-18 and LOW-11: action worker tests prove one-time schema/connection reuse,
  action claim behavior, and safe executor-error codes.
- LOW-12: evidence tests prove unset timestamps serialize as `null`, not
  `0.0`, and zero durations remain explicit.
- LOW-14: dashboard tests prove operator evidence-template readiness is
  computed from the actual template file state.
- LOW-15: focused dashboard/action/evidence tests cover the normalized
  timestamp paths touched by this residual pass.
- No explicit deferrals were recorded for the residual IDs in this slice.

Verification run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_executor.py python/arclink_action_worker.py python/arclink_dashboard.py python/arclink_evidence.py python/arclink_memory_synthesizer.py python/arclink_telegram.py python/arclink_discord.py python/arclink_hosted_api.py python/arclink_api_auth.py python/arclink_secrets_regex.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_memory_synthesizer.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_evidence.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_secrets_regex.py` passed.

Skipped live checks:

- No live Stripe, Chutes, Cloudflare, Tailscale, Notion mutation, Docker host
  mutation, deploy, upgrade, Docker install/upgrade, payment flow, public bot
  mutation, or production ingress proof was run.

Known risks:

- Broad release validation remains later work: `./bin/ci-preflight.sh`,
  `./test.sh`, web lint/test/build/browser proof, and any operator-authorized
  live provider/host proof were intentionally not run in this local residual
  closure pass.
- The repository remains a large pre-existing dirty worktree. This pass only
  updated the plan and completion notes after proving the already-recorded
  implementation/test slices.

## 2026-05-11 Ralphie Residual Closure: Provisioning, Secret Materialization, Recovery

Scope: closed the provisioning/materializer/recovery residual audit slice from
`IMPLEMENTATION_PLAN.md` without live host, provider, payment, bot mutation,
Docker install/upgrade, deploy, or upgrade activity. Existing dirty-tree Wave
1-5, HI-12, and hosted API/auth work was preserved.

- Fixed audit IDs: ME-7, ME-8, LOW-6, LOW-7, and LOW-10.
- ME-7: Nextcloud Postgres database names now use a DB-identifier-safe
  deployment-derived name for both Postgres and Nextcloud service env.
- ME-8: Sovereign dashboard password hash sync now records the generated
  password only when the dashboard secret did not already exist before apply,
  avoiding per-apply rehash churn.
- LOW-6 and LOW-7: file-backed secret materialization now chmods secret
  directories to `0700`, writes secret files `0600`, and uses per-file locking
  plus temp-file rename instead of direct basename writes. Sovereign generated
  secret storage uses the same private/atomic pattern.
- LOW-10: succeeded-job handoff recovery now prefers cached deployment
  `access_urls` metadata before recomputing and persists recomputed URLs when
  no cache exists.

Verification run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_provisioning.py python/arclink_executor.py python/arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed.

Skipped live checks:

- No live Stripe, Chutes, Cloudflare, Tailscale, Notion mutation, Docker host
  mutation, deploy, upgrade, Docker install/upgrade, payment flow, public bot
  mutation, or production ingress proof was run.

Known risks:

- Residual closure is not complete. Executor/memory/worker/evidence/dashboard
  and timestamp residuals (`ME-14`, `ME-15`, `ME-18`, `LOW-11`, `LOW-12`,
  `LOW-14`, `LOW-15`) still need their own source pass or explicit deferral
  before terminal audit completion.
- Local tests cover SQLite/fake/injected executor behavior and filesystem
  permission semantics only; live Docker/SSH/provider behavior remains gated.

## 2026-05-11 Ralphie Residual Closure: Hosted API And Auth

Scope: closed the hosted API/auth residual audit closure slice from
`IMPLEMENTATION_PLAN.md` without live host, provider, payment, bot mutation,
Docker install/upgrade, deploy, or upgrade activity. Existing dirty-tree Wave
1-5 and HI-12 work was preserved.

- Fixed audit IDs: ME-2, ME-3, ME-5, ME-6, LOW-2, and LOW-3.
- Inventory note: CR-1, CR-7, and HI-7 remain recorded as fixed by the local
  Wave 1C source/tests; ME-11 and ME-25 remain FICTION/outdated regression
  awareness only.
- Auth error cleanup: direct login helpers now collapse password-not-configured
  into the same invalid-credentials path, and session lookup/token/status
  failures share a generic authentication-failed detail while hosted responses
  continue returning only `unauthorized`.
- Session-kind enforcement remains in the shared auth helpers through
  `usess_`/`asess_` prefix checks on creation, authentication, and CSRF.
- Hosted API connection model: the WSGI app can now create and close a fresh
  DB connection per request when no test/shared connection is injected; the
  executable entrypoint uses that path instead of one process-wide SQLite
  connection.
- Stripe webhook duplicate handling: an already-recorded `received` event is
  acknowledged as a replay/pending duplicate without applying entitlement side
  effects again.
- User provisioning status: an authenticated request for a missing explicit
  deployment id now returns a clean 404 payload instead of falling through to a
  broad user deployment list.

Verification run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_api_auth.py python/arclink_hosted_api.py python/arclink_entitlements.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_evidence.py` passed.

Skipped live checks:

- No live Stripe, Chutes, Cloudflare, Tailscale, Notion mutation, Docker host
  mutation, deploy, upgrade, Docker install/upgrade, payment flow, public bot
  mutation, or production ingress proof was run.

Known risks:

- Residual closure is not complete. Provisioning/materializer/recovery
  residuals (`ME-7`, `ME-8`, `LOW-6`, `LOW-7`, `LOW-10`) and the
  executor/memory/worker/evidence/dashboard/timestamp residuals (`ME-14`,
  `ME-15`, `ME-18`, `LOW-11`, `LOW-12`, `LOW-14`, `LOW-15`) still need their
  own source pass or explicit deferral before terminal audit completion.
- Per-request DB connections are now available to the WSGI entrypoint, but
  alternate embedding code can still inject a shared connection for tests or
  controlled single-thread use.

## 2026-05-11 Ralphie Residual Closure: Admin Action Queueability

Scope: closed the first residual audit closure implementation slice from
`IMPLEMENTATION_PLAN.md` without live host, provider, payment, bot mutation,
Docker install/upgrade, deploy, or upgrade activity. Existing dirty-tree Wave
1-5 work was preserved.

- Fixed audit IDs: HI-12. Backend admin action queueing now rejects modeled but
  unwired action types (`reprovision`, `rollout`, `suspend`, `unsuspend`,
  `force_resynth`, and `rotate_bot_key`) before creating action intents. Legacy
  queued rows for those types fail safely as unsupported instead of remaining
  in a `pending_not_implemented` backend path.
- Inventory note: source still matches the Wave 1C trust-boundary fixes for
  CR-1, CR-7, and HI-7: Telegram webhooks require
  `TELEGRAM_WEBHOOK_SECRET` and `X-Telegram-Bot-Api-Secret-Token`, Discord
  webhook handling enforces timestamp tolerance plus interaction reservation,
  and hosted webhook routes call provider/IP rate limiting before JSON
  dispatch.
- ME-11 and ME-25 remain FICTION/outdated regression-awareness items only.
- Rationale: removed backend queueability for unsupported actions instead of
  adding placeholder implementations, because no real reprovision, rollout, or
  agent-side integration contract exists yet.

Verification run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_dashboard.py python/arclink_action_worker.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.

Skipped live checks:

- No live Stripe, Chutes, Cloudflare, Tailscale, Notion mutation, Docker host
  mutation, deploy, upgrade, Docker install/upgrade, payment flow, public bot
  mutation, or production ingress proof was run.

Known risks:

- Residual closure is not complete. Hosted API/auth, provisioning/materializer,
  executor, memory, evidence, worker, dashboard, and timestamp residual IDs
  still need their own source pass or explicit deferral before terminal audit
  completion.
- Existing databases can still contain older queued unsupported action rows;
  this pass makes those rows fail safely when processed.

## 2026-05-11 Ralphie Wave 5 Follow-Up: Browser Boundary, Live Proof Opt-Ins, Teardown Revocation

Scope: closed the remaining Wave 5 follow-up items from
`IMPLEMENTATION_PLAN.md` without live host, provider, payment, bot mutation,
Docker install/upgrade, deploy, or upgrade activity. Existing Wave 1-5 partial
dirty-tree work was preserved.

- Fixed audit IDs: HI-5 early unknown-route 404 CORS coverage, HI-6 route-aware
  CORS preflight `Allow` handling, LOW-5 SameSite Strict cookie default with an
  explicit `ARCLINK_COOKIE_SAMESITE=Lax` compatibility override, LOW-24
  per-step external proof opt-in semantics in the live runner, and the CR-4
  provider-artifact revocation follow-up for Sovereign teardown.
- Inventory result: local notes already covered ME-1, ME-16, ME-17, ME-19,
  ME-20, ME-21, ME-22, ME-23, ME-24, ME-27, ME-28, LOW-1, LOW-4, LOW-20,
  LOW-21, LOW-22, and LOW-23. ME-11 and ME-25 remain FICTION/outdated
  regression-awareness items per the audit plan.
- Browser/API boundary rationale: defaulting ArcLink session/CSRF cookies to
  SameSite Strict is compatible with the current first-party app/API flows and
  public checkout cancel/status token paths. The `Lax` override remains for a
  future external redirect route that demonstrably requires it.
- Live-runner rationale: external proof rows now use the step's own
  `ARCLINK_PROOF_*` flag once any external proof is selected; unselected proof
  rows are marked skipped with an explicit opt-in reason rather than inheriting
  global missing-env behavior.
- Teardown rationale: Sovereign teardown now calls the existing Chutes key
  executor with a deterministic revoke idempotency key and records
  `chutes_status` alongside compose/DNS teardown status. Fake-client coverage
  proves an existing provider key is revoked; real live Chutes deletion remains
  fail-closed behind the existing live executor/client authorization boundary.

Verification run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_hosted_api.py python/arclink_api_auth.py python/arclink_dashboard.py python/arclink_control.py python/arclink_notion_ssot.py python/arclink_live_runner.py python/arclink_live_journey.py python/arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_live_runner.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed.
- `python3 tests/test_notion_ssot.py` passed.

Skipped live checks:

- No live Stripe, Chutes, Cloudflare, Tailscale, Notion mutation, Docker host
  mutation, deploy, upgrade, Docker install/upgrade, payment flow, public bot
  mutation, or production ingress proof was run.

Known risks:

- Full production audit completion still requires operator-authorized live
  provider and host proof. Local tests prove SQLite, fake/injected provider,
  and static API behavior only.
- Live Chutes teardown revocation now has a fail-closed call site, but actual
  provider deletion depends on the live Chutes key client/authorization lane
  being configured for the executor.

## 2026-05-11 Ralphie Wave 5 Partial: Web/API, Readiness, Runtime Hardening

Scope: completed a focused Wave 5 BUILD slice from `IMPLEMENTATION_PLAN.md`
without live host, provider, payment, public-bot mutation, Docker install,
deploy, or upgrade activity. Existing Wave 1-4B dirty-tree work was preserved.

- Fixed audit IDs: ME-1 and LOW-23 canonical web/API response-shape cleanup,
  ME-16 fail-closed admin action readiness probes, ME-17 admin action
  rate-limiting by admin and target, ME-19 browser CORS header reduction,
  ME-20 explicit localhost HTTP cookie behavior, ME-21 checkout cancel backend
  cancellation, ME-22 admin secondary fetch gating, ME-24 generated agent
  systemd `Environment=` quoting, ME-28 qmd loopback binding, LOW-1 auth then
  CSRF portal ordering coverage, LOW-4 normalized misconfigured webhook error
  envelopes, LOW-20 Notion 409 conflict non-retry classification, LOW-21 git
  protocol hardening for vault repo sync, LOW-22 action UI reset to a valid
  executable action, and ME-27 parent-walk cache/bounds for live Notion scope
  checks.
- Confirmed/proved ME-23 branch default hardening remained in place through
  deploy regressions.
- Backend/admin response shapes are now canonical in the web admin surface:
  audit rows read `action`, reconciliation reads `{reconciliation,
  drift_count}`, and browser fixtures no longer mock inverse fields.
- Admin readiness now reports no executable actions when the executor adapter
  is disabled or required probes fail. The UI no longer falls back to hard-coded
  executable actions once readiness is known.
- Queueing admin actions now records rate-limit rows for both admin and target
  scopes before creating more durable action-intent churn.
- Runtime script hardening now forces qmd HTTP MCP to `127.0.0.1`, quotes
  generated enrolled-agent user unit environment values, and adds git
  `protocol.ext.allow=never` / `protocol.file.allow=never` defense by default.
  Local filesystem remotes remain explicitly allowed only for local repo-sync
  operations so existing local/operator checkouts and regression fixtures still
  work.
- Notion parent-walk scope decisions are cached in SQLite and the existing
  bounded walk depth remains in force. Notion HTTP 409 conflicts now fail
  without retry unless a future concrete retryable conflict case is proven.
- Rationale: stayed within the existing hosted API, dashboard, control-plane
  SQLite, shell wrapper, and Next.js surfaces instead of adding a new queue,
  service discovery layer, or UI-only bypass.

Verification run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_hosted_api.py python/arclink_api_auth.py python/arclink_dashboard.py python/arclink_control.py python/arclink_notion_ssot.py python/arclink_live_runner.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_live_runner.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_arclink_agent_user_services.py` passed.
- `python3 tests/test_loopback_service_hardening.py` passed.
- `python3 tests/test_arclink_repo_sync.py` passed.
- `python3 tests/test_notion_ssot.py` passed.
- `python3 tests/test_arclink_notion_knowledge.py` passed.
- `python3 tests/test_arclink_product_surface.py` passed.
- `python3 tests/test_arclink_e2e_fake.py` passed.
- `cd web && npm test` passed.
- `cd web && npm run lint` passed.
- `cd web && npm run build` passed.

Skipped live checks:

- No live Stripe, Chutes, Cloudflare, Tailscale, Notion mutation, Docker host
  mutation, deploy, upgrade, Docker install/upgrade, payment flow, public bot
  mutation, or production ingress proof was run.

Known risks:

- Full audit completion is not claimed. LOW-5 SameSite Strict migration and
  LOW-24 live-runner opt-in semantics remain explicit Wave 5 follow-up unless
  another local pass closes them.
- Admin readiness probes are intentionally conservative first-pass checks:
  executor adapter and required SSH key presence. A durable worker heartbeat or
  socket probe would further improve operator fidelity.
- Local tests prove SQLite, fake/injected behavior, and static/browser build
  behavior only. Operator-authorized live provider and host proof remains
  required before production completion claims.

## 2026-05-11 Ralphie Wave 4B: Schema, Onboarding Expiry, Evidence, And Migration Hygiene

Scope: completed the remaining Wave 4B implementation slice from
`IMPLEMENTATION_PLAN.md` without live host, provider, payment, public-bot
mutation, or deploy activity.

- Fixed audit IDs: HI-18 first-pass high-value schema/status constraints and
  drift checks, HI-19 centralized status validation expansion, HI-23 stale
  public onboarding expiry, HI-25 duplicate active web onboarding by email,
  LOW-18 evidence timestamp state semantics, and LOW-19 compatible migration
  grouping hygiene for additive column migrations.
- Added fresh-database SQL `CHECK` constraints for high-value public-control
  statuses where the contract is already centralized: users, deployments,
  subscriptions, refuel credits, credential handoffs, share grants,
  provisioning jobs, user/admin sessions, TOTP factors, channel pairing,
  action intents/attempts, operation idempotency, placements, rollouts, and
  evidence runs. Existing databases avoid unsafe table rebuild churn.
- Expanded centralized status constants and writer validation for action
  intents/attempts while reusing central handoff/share/session status sets in
  API auth.
- Expanded `arclink_drift_checks` across high-risk relationships and invalid
  status values for public owning/session/action/evidence rows.
- Added `expires_at` for public onboarding sessions, a 24-hour default TTL,
  stale active-session terminalization to `expired`, and deterministic active
  web session reuse by email across duplicate browser identities.
- Replaced evidence `0.0` persisted timestamp sentinels with blank-compatible
  timestamp text plus explicit `started_at_state` / `finished_at_state`.
- Rationale: kept fixes in the existing SQLite schema and writer paths. Full
  table rebuilds and FK retrofits remain deferred because additive columns,
  fresh-schema checks, writer validation, and drift reports reduce current risk
  without forcing live public DB rewrite churn.

Verification run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_api_auth.py python/arclink_onboarding.py python/arclink_hosted_api.py python/arclink_entitlements.py python/arclink_dashboard.py python/arclink_evidence.py python/arclink_live_runner.py python/arclink_action_worker.py` passed.
- `python3 tests/test_arclink_control_db.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_evidence.py` passed.
- `python3 tests/test_arclink_live_runner.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.

Skipped live checks:

- No live Stripe, Chutes, Cloudflare, Tailscale, Docker host mutation, deploy,
  upgrade, Docker install/upgrade, payment flow, public bot mutation, or
  production ingress proof was run.

Known risks:

- Full audit completion is not claimed. Wave 5 web/API cleanup, readiness
  probes, admin action rate limits, CORS/dev-cookie/deploy-branch cleanup,
  Notion/qmd loopback hardening, and remaining low cleanup remain backlog.
- SQL `CHECK` constraints protect fresh databases; migrated existing databases
  rely on writer validation plus drift reports until an operator-approved
  rebuild migration is planned.
- Local tests prove SQLite and fake/injected behavior only. Operator-authorized
  live provider and host proof remains required before production completion
  claims.

## 2026-05-11 Ralphie Wave 4 Partial: Identity, Status, TTL, And Drift Hygiene

Scope: completed the highest-priority Wave 4 implementation slice from
`IMPLEMENTATION_PLAN.md` without live host, provider, payment, public-bot
mutation, or deploy activity.

- Fixed audit IDs: HI-3, HI-20, HI-21, HI-22/ME-26 first-pass handoff/share
  TTL and one-time reveal semantics, HI-24, LOW-16, and LOW-17.
- Added centralized first-pass status constants and writer validation for
  touched user, deployment, and subscription status writers.
- Replaced the Stripe-local email merge with a control-plane merge helper that
  deterministically chooses a canonical email owner, repoints user-owned rows,
  marks loser user rows as `merged`, clears loser email to preserve uniqueness,
  and records event plus audit rows.
- Changed `upsert_arclink_user` so `suspended` and `merged` statuses are not
  overwritten by ordinary profile or entitlement upserts unless a privileged
  `force_status_transition` is requested.
- Added targeted indexes for Stripe customer lookups, webhook status, audit
  action, provisioning requested time, and active TOTP uniqueness, with
  migration cleanup for duplicate active TOTP factors.
- Made staged session revocation (`commit=False`) require an existing explicit
  transaction.
- Added expiry columns and 7-day TTL defaults for credential handoffs and share
  grants. Credential reveal is one-time for user API and public bot paths; later
  reads require explicit rotation/reissue instead of returning raw material.
- Split `past_due`/`unpaid` subscriptions into owed-service reconciliation
  drift instead of deployment-without-subscription orphan drift.
- Rationale: kept the repairs inside the existing SQLite control plane and API
  writers rather than introducing a separate migration service, queue, or
  UI-only state. SQL `CHECK`/FK rebuilds remain deferred because the public DB
  already has many live tables without constraints and unsafe table rebuild
  churn is not needed for this slice.

Verification run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_api_auth.py python/arclink_onboarding.py python/arclink_hosted_api.py python/arclink_entitlements.py python/arclink_dashboard.py python/arclink_evidence.py python/arclink_live_runner.py python/arclink_public_bots.py` passed.
- `python3 tests/test_arclink_control_db.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.

Skipped live checks:

- No live Stripe, Chutes, Cloudflare, Tailscale, Docker host mutation, deploy,
  upgrade, Docker install/upgrade, payment flow, public bot mutation, or
  production ingress proof was run.

Known risks:

- Wave 4 is not fully complete. HI-18 high-value SQL FK/CHECK rebuilds, HI-19
  full status coverage, HI-23 stale onboarding expiry, HI-25 duplicate-email
  onboarding UX, LOW-18 evidence timestamp cleanup, and LOW-19 broader
  transaction grouping remain backlog.
- TTL cleanup currently runs from API/public-bot touch paths for these
  resources; a broader periodic cleanup remains a later hardening step.
- Local tests prove SQLite and fake/injected behavior only. Operator-authorized
  live provider and host proof remains required before production completion
  claims.

## 2026-05-11 Ralphie Wave 2E Server-Derived Metadata And Honest Live Proof

Scope: completed Wave 2E from `IMPLEMENTATION_PLAN.md` for server-derived
admin action metadata and requested-live proof blocked status without live host
or provider mutations.

- Fixed audit IDs: HI-15, HI-16, and HI-17.
- Changed `dns_repair` execution to resolve the deployment target server-side,
  derive desired DNS records from existing `arclink_dns_records` rows when
  present, and fall back to deployment prefix/domain/metadata when DNS rows are
  absent. Explicit DNS metadata is still accepted but must be structurally
  valid and bound to the target deployment.
- Changed refund and cancel action execution to resolve user, deployment,
  subscription, Stripe customer, and Stripe subscription targets from control
  DB rows. Executor idempotency now receives the queued action idempotency key,
  and missing Stripe targets fail closed before provider dispatch.
- Made comp actions target-idempotent by replaying an existing comp audit for
  the same user/deployment target instead of writing duplicate entitlement
  audit churn.
- Changed requested live proof so missing credentials or missing registered
  runners return non-zero, write blocked evidence artifacts, and persist
  blocked evidence status through the evidence ledger. Dry-run blocked
  readiness remains a zero-exit planning result.
- Rationale: kept authority in the existing SQLite control rows and executor
  request contracts instead of adding UI-only required metadata, a separate
  reconciliation service, or synthetic live-proof success. This preserves the
  current action-worker/executor split while making server state the source of
  truth for side-effect targets.

Verification run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_action_worker.py python/arclink_dashboard.py python/arclink_executor.py python/arclink_control.py python/arclink_live_runner.py python/arclink_evidence.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_control_db.py` passed.
- `python3 tests/test_arclink_live_runner.py` passed.
- `python3 tests/test_arclink_evidence.py` passed.

Skipped live checks:

- No live Stripe refund/cancel, Cloudflare DNS mutation, Chutes call, Docker
  host mutation, deploy, upgrade, Docker install/upgrade, payment flow, public
  bot mutation, or production ingress proof was run.

Known risks:

- Wave 3 cancellation/teardown lifecycle, DNS/fleet/port release, secret
  cleanup, and honest compose/DNS status remain backlog.
- Later schema/status, onboarding/session expiry, web/API cleanup, readiness,
  rate-limit, CORS, deploy-branch, Notion/qmd, and lower-priority cleanup waves
  remain unresolved.
- This pass proves local SQLite and fake/injected execution behavior only;
  operator-authorized live provider and host proof is still required before
  claiming production end-to-end completion.

## 2026-05-11 Ralphie Wave 2D Credits, Placement, And Entitlement Rechecks

Scope: completed Wave 2D from `IMPLEMENTATION_PLAN.md` for refuel credit
atomicity, active placement uniqueness, and Sovereign deployment-apply
rechecks without live host or provider mutations.

- Fixed audit IDs: CR-10, HI-10, and HI-11.
- Wrapped refuel credit application in an immediate transaction covering credit
  selection, guarded credit row updates, deployment metadata update, and audit
  insertion. Each credit spend now predicates on the expected remaining
  balance, active status, user, and applicable deployment scope.
- Added migration cleanup plus a partial unique index so only one active
  placement can exist per deployment.
- Changed fleet placement to run as transactional place-or-existing logic,
  returning an existing active placement under duplicate/concurrent attempts
  without inflating host load.
- Added Sovereign worker rechecks of deployment row, user row, status, and
  entitlement readiness before placement, DNS persistence/apply, compose apply,
  dashboard secret sync, and service-status side effects. Changed-status
  failures no longer overwrite a non-provisioning deployment status with
  `provisioning_failed`.
- Rationale: kept concurrency control inside SQLite immediate transactions,
  guarded writes, and schema constraints instead of introducing a new queue,
  lock service, or host-level mutex. This matches the existing control-plane
  substrate and gives local tests deterministic proof of the invariants.

Verification run:

- `python3 -m py_compile python/arclink_control.py python/arclink_fleet.py python/arclink_sovereign_worker.py python/arclink_provisioning.py` passed.
- `python3 tests/test_arclink_fleet.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_control_db.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `git diff --check` passed.

Skipped live checks:

- No live Stripe, Chutes, Cloudflare, Tailscale, Docker host mutation, deploy,
  upgrade, Docker install/upgrade, payment flow, public bot mutation, or
  production ingress proof was run.

Known risks:

- Wave 2E server-derived metadata and honest blocked live proof remain open.
- Later cancellation/teardown lifecycle, DNS/fleet/port release, schema/status
  cleanup, and web/API cleanup waves remain backlog.
- This pass proves local SQLite serialization and fake/local executor behavior;
  operator-authorized live provider and host proof is still required before
  claiming production end-to-end completion.

## 2026-05-11 Ralphie Wave 2C Action Queue And Audit Ordering

Scope: completed Wave 2C from `IMPLEMENTATION_PLAN.md` for action-worker DB
access, atomic claims, and audit-before-side-effect ordering without live
external calls.

- Fixed audit IDs: CR-5 and the action-worker ordering portion of HI-13.
- Added `worker_id` and `claimed_at` metadata to `arclink_action_intents`, plus
  a queued-action claim index.
- Changed the worker to claim one queued action inside `BEGIN IMMEDIATE` with a
  compare-and-swap update from `queued` to `running`; workers skip processing
  if the CAS update does not affect a row.
- Changed the CLI worker path to use control-plane `connect_db` and keep one
  initialized DB connection for the worker lifecycle where feasible.
- Persisted action attempt, event, and audit metadata before executor dispatch;
  result/failure rows are updated after provider response.
- Rationale: kept concurrency control in SQLite transactions instead of adding
  an external queue or lock service. This matches the current control-plane DB
  substrate, preserves no-new-infrastructure deployment, and gives tests a
  deterministic CAS boundary.

Verification run:

- `python3 -m py_compile python/arclink_action_worker.py python/arclink_control.py tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_control_db.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_fleet.py` passed.
- `python3 tests/test_arclink_live_runner.py` passed.
- `git diff --check` passed.

Skipped live checks:

- No live Stripe, Chutes, Cloudflare, Tailscale, Docker host mutation, deploy,
  upgrade, Docker install/upgrade, payment flow, public bot mutation, or
  production ingress proof was run.

Known risks:

- Wave 2D credit/placement/entitlement rechecks and Wave 2E server-derived
  metadata plus honest blocked live proof remain open.
- Live adapter side effects are now preceded by durable worker attempt/audit
  rows, but concrete production Chutes/Stripe client wiring still requires an
  operator-authorized live adapter pass.

## 2026-05-11 Ralphie Wave 2B Live Provider Action Honesty

Scope: completed Wave 2B from `IMPLEMENTATION_PLAN.md` for the executor
provider-action surface without making live external calls.

- Fixed audit IDs: CR-3 and the provider-action portion of HI-13.
- Replaced non-fake Chutes key and Stripe admin action synthetic `applied`
  responses with injected `ChutesKeyClient` and `StripeActionClient` calls.
- Forwarded operation idempotency keys to provider clients and, when the
  executor is given a control DB connection, reserve/complete/fail
  `arclink_operation_idempotency` rows with provider refs and replay terminal
  rows without repeating provider side effects.
- Preserved the fake adapter as `live=False` with deterministic provider refs
  for no-secret tests.
- Rationale: used narrow injected client protocols instead of importing SDKs or
  live Chutes/Stripe adapters directly into the executor. This keeps the
  executor testable, fail-closed by default, and compatible with future
  operator-provided live clients.

Verification run:

- `python3 -m py_compile python/arclink_executor.py tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_fleet.py` passed.
- `python3 tests/test_arclink_live_runner.py` passed.
- `git diff --check` passed.
- `python3 -m py_compile python/arclink_action_worker.py python/arclink_executor.py python/arclink_control.py tests/test_arclink_executor.py` passed.

Skipped live checks:

- No live Stripe refund/cancel/portal action, Chutes key mutation, deploy,
  upgrade, Docker install/upgrade, payment flow, public bot mutation,
  Cloudflare/Tailscale proof, or production ingress proof was run.

Known risks:

- Wave 2C action-worker CAS claims and audit-before-side-effect ordering remain
  open.
- Wave 2D credit/placement/entitlement rechecks and Wave 2E server-derived
  metadata plus honest blocked live proof remain open.
- The live Chutes/Stripe clients are now required injection points; concrete
  production wiring still needs an operator-authorized live adapter pass.

## 2026-05-11 Ralphie Wave 1 Validation And Wave 2A Operation Idempotency

Scope: reran the Wave 1 validation floor for the current worktree, repaired one
Docker documentation contract regression, and completed Wave 2A from
`IMPLEMENTATION_PLAN.md`.

- Fixed audit IDs: HI-2.
- Added `arclink_operation_idempotency` to the control-plane schema, keyed by
  `(operation_kind, idempotency_key)` with canonical intent digests, status,
  provider refs, result/error fields, and terminal timestamps.
- Added reserve, replay, complete, and fail helpers in
  `python/arclink_control.py`; same-key changed-intent reuse fails closed, and
  succeeded/failed terminal rows replay after process restart.
- Restored the Sovereign `domain-or-Tailscale ingress` wording expected by the
  Docker regression contract.
- Rationale: kept idempotency durable in SQLite beside the existing control
  state instead of adding Redis, provider-only idempotency, or private-state
  sidecars. That preserves the no-new-infrastructure path and lets later
  Stripe/Chutes/action-worker slices bind provider refs to the same durable
  row before and after side effects.

Verification run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_hosted_api.py python/arclink_api_auth.py python/arclink_discord.py python/arclink_telegram.py python/arclink_public_bot_commands.py python/arclink_boundary.py python/arclink_provisioning.py python/arclink_memory_synthesizer.py python/arclink_secrets_regex.py python/arclink_action_worker.py python/arclink_executor.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_public_bot_commands.py` passed.
- `python3 tests/test_arclink_docker.py` passed after the wording repair.
- `python3 tests/test_arclink_secrets_regex.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_memory_synthesizer.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 -m py_compile python/arclink_control.py tests/test_arclink_control_db.py` passed.
- `python3 tests/test_arclink_control_db.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_fleet.py` passed.
- `python3 tests/test_arclink_live_runner.py` passed.

Skipped live checks:

- No live deploy, upgrade, Docker install/upgrade, payment flow, public bot
  mutation, external provider call, Cloudflare/Tailscale proof, or production
  ingress proof was run; those remain gated by explicit operator authorization
  and live credentials.

Known risks:

- Wave 2A only adds the durable idempotency substrate. Stripe/Chutes live
  adapter calls, action-worker CAS claims, refuel credit atomicity, placement
  uniqueness, entitlement rechecks, server-derived metadata, and honest blocked
  live proof remain unresolved Wave 2 backlog.

## 2026-05-11 Ralphie Wave 1D/1E Secret Redaction And Container Boundary Build

Scope: completed Wave 1D and Wave 1E from `IMPLEMENTATION_PLAN.md`.

- Fixed audit IDs: CR-2, HI-1, ME-12, ME-13, LOW-8, and LOW-9.
- Added `python/arclink_secrets_regex.py` for shared detection/redaction of
  OpenAI, Anthropic, AWS, PEM private key, JWT, Chutes, Discord, GitLab, and
  existing token families, while allowing safe `secret://` and
  `/run/secrets/*` references.
- Replaced duplicated secret regex paths in boundary validation,
  provisioning validation, action-worker errors, executor command/API errors,
  memory synthesis snippets/cards/errors, and hosted webhook logging.
- Changed redaction call sites to redact before truncation and replaced broad
  path substring checks with structured path-segment/key checks.
- Switched the shared Docker app image to `USER arclink`, moved fleet SSH
  mounts under `/home/arclink/.ssh`, recorded `ARCLINK_DOCKER_SOCKET_GID`
  during Docker bootstrap, and added explicit `group_add` only to writeable
  Docker-socket lifecycle services. `control-ingress` remains read-only.
- Updated Docker trust-boundary docs and static Docker tests for the socket
  allowlist, read-only mount, socket gid, non-root user, SSH mount target, and
  trusted write-mount comments.

Verification run:

- `python3 -m py_compile python/arclink_secrets_regex.py python/arclink_boundary.py python/arclink_provisioning.py python/arclink_action_worker.py python/arclink_executor.py python/arclink_memory_synthesizer.py python/arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_secrets_regex.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_memory_synthesizer.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_public_bot_commands.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.
- `docker compose --env-file arclink-priv/config/docker.env config --quiet` passed.
- `git diff --check` passed.

Skipped live checks:

- No live deploy, upgrade, Docker install/upgrade, public bot mutation,
  provider call, payment flow, or production ingress proof was run; those
  remain gated by explicit operator authorization and live credentials.

Known risks:

- Non-root Docker socket access now depends on the host socket gid recorded in
  `ARCLINK_DOCKER_SOCKET_GID`; hosts that change Docker socket ownership after
  bootstrap must refresh or set that value.
- Writeable Docker socket services remain trusted-host boundaries with
  host-root-equivalent capability by design.
- Later Wave 2+ audit items remain unresolved.

## 2026-05-11 Ralphie Wave 1B Session And Browser Auth Boundary

Scope: completed the Wave 1B hosted API/session boundary from
`IMPLEMENTATION_PLAN.md`.

- Fixed audit IDs: CR-6, CR-11, and HI-4.
- Added cookie-only browser session extraction and moved hosted user/admin
  logout onto that path; logout now authenticates the session token before CSRF
  validation or revocation.
- Enforced `usess_` and `asess_` session-id prefixes for user/admin session
  creation, authentication, CSRF validation, and revocation.
- Changed new session and CSRF token storage to versioned
  `hmac_sha256_v1$...` hashes using `ARCLINK_SESSION_HASH_PEPPER`, while
  retaining successful legacy SHA-256 verification long enough to upgrade rows
  in place.
- User-facing hosted auth failures now return generic `unauthorized` responses
  while private structured logs retain the specific failure reason.
- Added Compose/config example pass-through for `ARCLINK_SESSION_HASH_PEPPER`
  and `ARCLINK_SESSION_HASH_PEPPER_REQUIRED`; production-domain session
  creation fails closed when the pepper is missing.

Verification run:

- `python3 -m py_compile python/arclink_api_auth.py python/arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `git diff --check` passed.

Known risks:

- Existing legacy SHA-256 session rows remain accepted only after successful
  token proof and are upgraded immediately; compromised sessions still require
  normal revocation/expiry. No live deploy, browser, Stripe, Telegram, Discord,
  or production ingress proof was run because this slice is local and
  no-secret.
- Wave 1C-1E remain unresolved.

## 2026-05-11 Ralphie Wave 1A Hosted API Request Boundary

Scope: completed the Wave 1A hosted API ingress boundary from
`IMPLEMENTATION_PLAN.md`.

- Fixed audit IDs: CR-8, CR-9, and ME-4.
- Added configurable hosted API body caps before JSON parsing, plus WSGI
  rejection before `wsgi.input` reads for oversized requests.
- Malformed JSON and non-object JSON on JSON-object routes now return
  `400 invalid_json` instead of silently becoming `{}`.
- Early 404, 413, and body/CIDR boundary responses now preserve configured
  CORS headers.
- Added CIDR enforcement for admin/control hosted API routes using the shared
  control-plane IP/CIDR helpers. Forwarded client IPs are only trusted when the
  direct peer is loopback or an allowed backend proxy; direct spoofed
  `X-Forwarded-For` requests remain denied.
- Public onboarding routes intentionally remain outside the admin/control CIDR
  gate so customer-facing entrypoints continue to work.

Verification run:

- `python3 -m py_compile python/arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.

Known risks:

- Wave 1B-1E remain unresolved; no live deploy, Docker, Stripe, Telegram, or
  Discord proof was run because those are outside this local Wave 1A slice and
  require explicit operator authorization for live side effects.

## 2026-05-11 Public Agent Gateway Backpressure

Scope: tightened the Raven selected-agent live-trigger path so public
Telegram/Discord webhook ingress stays fast under load.

- Follow-up repair: API ingress no longer attempts selected-agent delivery
  from Dockerized Control Node containers that do not mount
  `/var/run/docker.sock`. In that mode, it acknowledges the webhook and leaves
  the durable turn for the Docker-capable notification-delivery worker.
- Lowered the Control Node notification-delivery poll interval from 5 seconds
  to 1 second so selected-agent public-channel turns still start quickly
  without giving API ingress direct Docker authority.
- Replaced the unbounded per-message thread start in `arclink_hosted_api.py`
  with a bounded process-local executor.
- Added `ARCLINK_PUBLIC_AGENT_LIVE_TRIGGER_WORKERS` and
  `ARCLINK_PUBLIC_AGENT_LIVE_TRIGGER_MAX_PENDING` controls. When live-trigger
  capacity is saturated, the webhook still acknowledges the platform and the
  durable `notification_outbox` row remains for `notification-delivery`.
- Kept the durable claim/lease notification worker as the recovery path and
  documented the next high-scale move: a warm internal public-agent bridge
  service per deployment, so ArcLink can stop paying the per-turn `docker exec`
  and Python import cost.
- Added `research/PUBLIC_AGENT_GATEWAY_PERFORMANCE_PLAN.md` to separate the
  immediate safe behavior from the final load-balanced gateway target.

Verification run:

- `python3 -m py_compile python/arclink_hosted_api.py python/arclink_notification_delivery.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_notification_delivery.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `git diff --check` passed.

## 2026-05-11 Conflict-Free Raven Active-Agent Command Scope

Scope: made the active Telegram slash surface conflict-free by giving the
active agent the bare slash namespace and moving Raven controls behind a
dedicated Raven command that is selected after the active agent command
inventory is known.

- Active Telegram command scopes now contain one Raven control command,
  normally `/raven`, plus the active agent's current Hermes command menu.
  If an upgraded plugin, skill, or Hermes runtime introduces `/raven`,
  ArcLink falls back to `/arclink`, then `/arclink_control`, then a visible
  `arclink_ops*` escape hatch.
- Bare `/agents`, `/status`, `/help`, `/model`, `/provider`, and similar
  active-agent commands route to the active agent after Telegram command-scope
  refresh records the active command inventory. Raven controls stay reachable
  as `/raven agents`, `/raven status`, `/raven credentials`, `/raven
  connect_notion`, `/raven config_backup`, `/raven link_channel`, `/raven
  upgrade_hermes`, and `/raven cancel`.
- Public bot command registration now refreshes every active Telegram chat
  scope after control install/upgrade, records the command source and
  conflict diagnostics in onboarding session metadata, and queues an operator
  alert when a legacy Raven-name collision, hard Raven control collision, or
  policy-suppressed command such as `/update` appears.
- The same alert path records and reports hidden active-agent command counts
  when Telegram's 100-command menu cap prevents the entire Hermes command
  inventory from being visible.
- Active Telegram inline buttons are rewritten to the Raven namespace so
  button taps keep reaching Raven even when the visible bare slash command
  belongs to the selected agent.
- Telegram share approval buttons now use `/raven approve {grant_id}` and
  `/raven deny {grant_id}` while keeping the older `/share-approve` and
  `/share-deny` forms owner-scoped for compatibility.

Verification run:

- `python3 tests/test_arclink_public_bot_commands.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed.
- `python3 tests/test_documentation_truths.py` passed.
- `python3 -m py_compile python/arclink_telegram.py python/arclink_public_bots.py python/arclink_public_bot_commands.py python/arclink_api_auth.py python/arclink_hosted_api.py python/arclink_sovereign_worker.py tests/test_arclink_telegram.py tests/test_arclink_public_bots.py tests/test_arclink_public_bot_commands.py tests/test_arclink_sovereign_worker.py` passed.
- `git diff --check` passed.

## 2026-05-11 Telegram Active-Agent Command Scope

Scope: repaired the mismatch where Raven routed non-Raven slash commands to the
active agent, but Telegram's slash menu still displayed only Raven's global
public command catalog.

- Added per-chat Telegram command scope refresh for chats with an active
  ArcLink deployment. The scoped menu merges Raven controls with
  non-conflicting active-agent Hermes commands from the pinned Hermes command
  registry, falling back to a bundled safe core list when the registry is not
  present.
- Kept Raven-owned public controls reserved in that chat menu and suppressed
  direct `/update`; `/update`, `/upgrade_hermes`, and `/upgrade-hermes` now
  all route to ArcLink's pinned upgrade guidance instead of unmanaged
  `hermes update`.
- Documented that Discord remains global-command constrained, so `/agent
  <message-or-command>` is still the public bridge for Discord and for any
  Telegram command-name conflict such as Hermes `/status`.

Verification run:

- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_documentation_truths.py` passed.
- `python3 -m py_compile python/arclink_telegram.py python/arclink_public_bots.py python/arclink_hosted_api.py tests/test_arclink_telegram.py tests/test_arclink_public_bots.py` passed.
- `git diff --check` passed.

## 2026-05-10 Raven Selected-Agent Bridge Contract Alignment

Scope: reconciled the product-reality contract after Raven freeform public
messages were changed from a control-only handoff into selected-agent chat
turns for onboarded users.

Rationale:

- Raven remains the slash-command control conduit for `/help`, `/agents`,
  `/status`, credentials, Notion, backup, channel linking, shares, and upgrade
  guidance.
- Onboarded-user freeform Telegram/Discord messages now queue
  `public-agent-turn` notifications, execute the selected deployment's
  `hermes-gateway` container through `notification-delivery`, and return the
  agent reply to the same linked public channel.
- The product matrix, coverage matrix, research summary, and document phase
  status were updated so future agents do not preserve the older control-only
  assumption.

Verification run:

- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_notification_delivery.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `docker compose --env-file arclink-priv/config/docker.env config --quiet` passed.
- `python3 -m py_compile python/arclink_public_bots.py python/arclink_notification_delivery.py` passed.
- `git diff --check` passed.
- `./deploy.sh control health` passed with `32 ok`, `2 warn`, and `0 fail`.
- Live no-message-sending bridge proof from inside the upgraded
  `notification-delivery` container reached the `sirouk | TuDudes`
  `hermes-gateway` runtime and returned `deployed bridge ok`.

Known risks:

- Live Telegram/Discord delivery proof was not forced by this note; the bridge
  was proven at the notification-worker-to-agent-runtime joint without sending
  another user-visible public bot message.
- The memory-synth health row is still warn because the current model returned
  non-JSON for several vault lanes; the job loop itself exits successfully.
- Browser right-click sharing, Chutes provider-path policy, threshold
  continuation copy, self-service provider changes, and scoped peer-awareness
  remain policy-gated.

## 2026-05-09 Ralphie OAuth Callback State Hardening

Scope: tightened the Chutes OAuth/connect fake callback boundary while keeping
live provider calls and provider mutation proof-gated.

Rationale:

- Updated `complete_chutes_oauth_callback` so a wrong user/session or CSRF
  callback cannot consume an otherwise valid pending connect state. Expired
  states and validated callbacks still consume state to preserve one-time
  callback semantics.
- Extended `tests/test_arclink_chutes_oauth.py` to prove a rejected
  cross-user or bad-CSRF callback does not burn the legitimate user's pending
  Chutes connect attempt.

Verification run:

- `python3 -m py_compile python/arclink_chutes.py python/arclink_chutes_live.py python/arclink_chutes_oauth.py python/arclink_evidence.py python/arclink_live_journey.py python/arclink_live_runner.py python/arclink_notion_ssot.py tests/test_arclink_chutes_and_adapters.py tests/test_arclink_chutes_live_adapter.py tests/test_arclink_chutes_oauth.py tests/test_arclink_live_journey.py tests/test_arclink_live_runner.py tests/test_notion_ssot.py tests/test_public_repo_hygiene.py` passed.
- `python3 tests/test_arclink_chutes_oauth.py` passed.
- `python3 tests/test_arclink_chutes_live_adapter.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_arclink_live_journey.py` passed.
- `python3 tests/test_arclink_live_runner.py` passed.
- `python3 tests/test_notion_ssot.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `git diff --check` passed.

Known risks:

- No live Chutes OAuth, Notion, public bot, Stripe, ingress, Docker, or host
  proof was run; those remain gated on explicit operator authorization and
  secret references.
- At the time of this build, the active product-policy rows included Raven
  direct-agent public chat, browser right-click sharing, canonical Chutes
  provider path, threshold continuation copy, self-service provider changes,
  and scoped peer-awareness. Raven direct-agent public chat was later resolved
  and implemented in the 2026-05-10 bridge update above.

## 2026-05-09 Ralphie Notion Harness And Policy-Gate Preservation Build

Scope: closed the remaining local P1 Raven/browser-share/Notion proof-harness
handoff tasks without live Notion, bot, provider, payment, Docker, or host
mutation.

Rationale:

- Added `run_notion_ssot_no_secret_proof` to `python/arclink_notion_ssot.py`.
  The harness validates callback URL shape, proves shared-root page readability
  through an injected transport, can exercise the brokered create-and-trash
  write preflight against fake or explicitly authorized live transport, and
  returns only redacted evidence. Raw Notion tokens and secret refs are not
  included in the response payload.
- Chose an injected no-secret Notion harness instead of user-owned OAuth,
  email-share-only checks, or live workspace mutation. Shared-root membership
  remains the canonical model; user OAuth/token and live workspace mutation
  remain proof-gated until explicit operator authorization.
- Preserved the then-current Raven public-bot policy gate. This historical
  note is superseded by the 2026-05-10 Raven selected-agent bridge update:
  onboarded-user freeform messages now route to the selected agent through
  Raven, while slash commands remain Raven controls.
- Preserved disabled browser right-click share-link UI while keeping
  `shares.request`, read-only living `Linked` projections, revoke behavior, and
  recipient copy/duplicate into owned roots covered by existing plugin/API
  behavior.

Verification run:

- `python3 -m py_compile python/arclink_chutes.py python/arclink_chutes_live.py python/arclink_chutes_oauth.py python/arclink_evidence.py python/arclink_live_journey.py python/arclink_live_runner.py python/arclink_notion_ssot.py tests/test_arclink_chutes_and_adapters.py tests/test_arclink_chutes_live_adapter.py tests/test_arclink_chutes_oauth.py tests/test_arclink_live_journey.py tests/test_arclink_live_runner.py tests/test_notion_ssot.py tests/test_public_repo_hygiene.py` passed.
- `python3 tests/test_notion_ssot.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `python3 tests/test_arclink_chutes_oauth.py` passed.
- `python3 tests/test_arclink_chutes_live_adapter.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_arclink_live_journey.py` passed.
- `python3 tests/test_arclink_live_runner.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `git diff --check` passed.

Known risks:

- No live Notion shared-root, `ssot.write`, OAuth, or workspace mutation proof
  was run. Those remain proof-gated until the operator authorizes a named live
  proof flow and supplies secret references.
- Browser right-click share-link enablement, canonical Chutes provider/OAuth
  selection, threshold continuation copy, self-service provider changes, and
  scoped peer-awareness remain explicit policy questions. Raven direct-agent
  public chat was later resolved and implemented in the 2026-05-10 bridge
  update.
- Live Stripe, Telegram, Discord, Chutes, Nextcloud, Cloudflare, Tailscale,
  Docker install/upgrade, and host deploy/upgrade proof were not run.

## 2026-05-09 Ralphie Chutes OAuth And External Proof Build

Scope: advanced the remaining P0 Chutes continuation tasks without live
provider calls, secret reads, browser bypass tooling, or provider mutations.

Rationale:

- Added `python/arclink_chutes_oauth.py` as the no-secret Chutes OAuth/connect
  boundary. It builds a PKCE authorize plan, binds callback state to user and
  session, validates CSRF, models scope display, stores exchanged fake tokens
  only behind generated `secret://` refs, and exposes disconnect/revoke
  readiness without returning raw tokens to browser/API-shaped payloads.
- Added fake Chutes OAuth callback coverage in
  `tests/test_arclink_chutes_oauth.py` for state mismatch, CSRF mismatch,
  cross-user callback isolation, scope display, disconnect readiness, TLS
  redirect validation, and raw-secret rejection.
- Extended `python/arclink_live_journey.py` and
  `python/arclink_live_runner.py` with an `external` live-proof journey. The
  provider rows are opt-in through explicit `ARCLINK_PROOF_*` flags and cover
  Chutes OAuth, Chutes usage/billing, Chutes key CRUD, Chutes account
  registration, Chutes balance transfer, Notion SSOT, public bot delivery,
  Stripe, Cloudflare, Tailscale, and Hermes dashboard landing.
- Updated the product matrix and build gate to keep the same proof-gated
  counts while pointing future live provider runs at
  `bin/arclink-live-proof --journey external --live --json`.

Verification run:

- `python3 -m py_compile python/arclink_chutes_oauth.py python/arclink_chutes_live.py python/arclink_live_journey.py python/arclink_live_runner.py python/arclink_evidence.py tests/test_arclink_chutes_oauth.py tests/test_arclink_chutes_live_adapter.py tests/test_arclink_live_journey.py tests/test_arclink_live_runner.py` passed.
- `python3 tests/test_arclink_chutes_oauth.py` passed.
- `python3 tests/test_arclink_chutes_live_adapter.py` passed.
- `python3 tests/test_arclink_live_journey.py` passed.
- `python3 tests/test_arclink_live_runner.py` passed.

Known risks:

- No live Chutes OAuth, delegated inference, usage sync, account registration,
  key CRUD, token revoke, or balance transfer was run. These remain
  proof-gated until explicit operator authorization and secret references
  exist.
- The external journey is orchestration and redacted evidence planning; it does
  not replace provider-specific live runners or manual proof procedures.
- Chutes canonical provider-path choice remains a policy question until the
  operator chooses OAuth, operator-metered keys, assisted account creation, or
  another lane.

## 2026-05-09 Ralphie Chutes Live Adapter Boundary Build

Scope: advanced the P0 Chutes continuation tasks without live provider calls,
secret reads, browser bypass tooling, or provider mutations.

Rationale:

- Added a secret-reference Chutes live adapter boundary in
  `python/arclink_chutes_live.py` for model listing, current user,
  subscription usage, user usage, quota usage, quotas, discounts, price
  overrides, API-key list/create/delete, OAuth scopes, token introspection, and
  balance-transfer planning.
- Kept live mutation paths explicit: API-key create/delete and balance transfer
  require `allow_live_mutation`, and balance transfer remains fake/not executed
  in local proof until operator-authorized live proof succeeds.
- Preserved the no-browser-bypass Chutes registration posture from
  `python/arclink_chutes.py`: official registration-token/hotkey modeling is
  represented, and `curl_cffi`/browser-challenge bypass-style requests are
  rejected.
- Added the new provider files to public hygiene's allowed provider-context
  paths so future scans keep Chutes references intentional.

Verification run:

- `python3 -m py_compile python/arclink_chutes.py python/arclink_chutes_live.py tests/test_arclink_chutes_and_adapters.py tests/test_arclink_chutes_live_adapter.py tests/test_public_repo_hygiene.py` passed.
- `python3 tests/test_arclink_chutes_live_adapter.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.

Known risks:

- No live Chutes OAuth, account registration, key CRUD, usage sync, token
  introspection, or balance transfer was run; those remain proof-gated until
  explicit operator authorization and secret references exist.
- Chutes OAuth/connect UI and callback-state tests remain open BUILD work.
- Live Refuel Pod purchase and direct Chutes balance application remain
  proof-gated; local meaning is still ArcLink internal provider-budget credit.

## 2026-05-08 Ralphie Documentation Gate Retry Repair

Scope: repaired document-phase handoff clarity only. No implementation behavior
changed in this retry.

Rationale:

- Rechecked the active plan, product matrix, build notes, closest README/AGENTS
  guidance, API reference, architecture doc, operations runbook, user guide,
  Notion guide, Raven guide, and plugin READMEs.
- Confirmed the current project-facing docs already describe the final
  no-secret product-reality behavior: single active owner, linked-resource
  copy/duplicate into owned roots, disabled browser right-click sharing,
  sanitized provider state, local provider-budget credit accounting, failed
  renewal lifecycle metadata, shared-root Notion SSOT membership, and
  managed-context memory boundaries.
- Added explicit transition-readiness language to
  `docs/arclink/document-phase-status.md` so the remaining live-proof and
  product-policy rows are recorded as external/product gates rather than
  document-phase blockers.

Verification run:

- `git diff --check` passed.
- `python3 tests/test_documentation_truths.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- Stale-copy sweeps passed for old sharing-model wording, deferred dashboard
  data wiring, recipient-copy policy-question wording, live-proof overclaims,
  and shipped speculative add-on copy.

Known risks:

- Live Stripe, Chutes, Telegram, Discord, Notion, Cloudflare, Tailscale, Docker
  install/upgrade, and production host proof remain credential-gated.
- Browser right-click Drive/Code share creation remains disabled until a live
  ArcLink broker or approved Nextcloud-backed adapter exists and is proven.
- Chutes threshold continuation copy, self-service provider changes, and scoped
  peer-awareness cards remain product-policy gates.

## 2026-05-08 Ralphie Raven Identity Build

Scope: closed the approved Raven per-user/per-channel bot-name customization
task from `IMPLEMENTATION_PLAN.md` without claiming platform profile mutation.

Rationale:

- Added `arclink_public_bot_identity` for local Raven display-name preferences.
- Added `/raven_name` and `/raven-name` so users can set a channel override or,
  after account linking, an account default. Channel overrides win over account
  defaults, and selected-agent labels remain separate.
- Kept the implementation truthful: ArcLink message rendering uses the
  effective Raven name, while Telegram and Discord bot profile names remain
  governed by platform bot registration until live platform proof is
  authorized.
- Reclassified the product matrix from 88 `real` / 17 `policy-question` rows
  to 89 `real` / 16 `policy-question` rows.

Verification run:

- `python3 -m py_compile python/arclink_public_bots.py python/arclink_control.py python/arclink_discord.py python/arclink_telegram.py tests/test_arclink_public_bots.py tests/test_arclink_discord.py tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_documentation_truths.py` passed.
- `git diff --check` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.

Known risks:

- This is local message-level display customization only. Live Telegram or
  Discord profile mutation remains proof-gated and is not claimed.

## 2026-05-08 Operator Policy Decision Intake

Scope: captured the operator's answers to the remaining product-policy
questions after the no-secret build gate completed.

Rationale:

- Added `research/OPERATOR_POLICY_DECISIONS_20260508.md` as the canonical
  policy addendum for Raven per-channel identity, SSOT shared-root membership,
  failed-renewal warnings/purge, living Drive/Code shares, recipient
  copy/duplicate, one-operator behavior, Chutes per-user-account fallback, and
  Refuel Pod credits.
- Updated the Ralphie steering and build gate so the next pass reclassifies
  former `policy-question` rows into buildable local work, proof-gated live
  work, or remaining product questions.
- Chutes research was public/no-secret only. Public sources show scoped key
  create/list/delete, user/account usage endpoints, and current model pricing;
  per-key usage metering remains unproven from public code and should stay
  proof-gated until authorized account proof.
- Nextcloud research was public/no-secret only. ArcLink already has optional
  Nextcloud plumbing, and official Nextcloud docs expose OCS share and WebDAV
  shared-mount capabilities; Ralphie should evaluate this as the preferred
  living-share adapter where enabled.

Verification run:

- No code tests were run for this intake-only update.
- Public sources consulted:
  `https://llm.chutes.ai/v1/models`, `https://api.chutes.ai/pricing`,
  `https://github.com/chutesai/chutes`,
  `https://github.com/chutesai/chutes-api`,
  `https://github.com/Veightor/chutes-agent-toolkit`, and official Nextcloud
  OCS/WebDAV developer docs.

Known risks:

- The product matrix count is intentionally marked stale/pending
  reclassification because the operator decisions arrived after the prior
  terminal build reconciliation.
- Live Chutes, Stripe, Notion, Nextcloud, Cloudflare, Tailscale, bot, Docker,
  and host proof remain gated until explicitly authorized.

## 2026-05-08 Ralphie Final Matrix Reconciliation Build

Scope: completed the highest-priority P0/P1 reconciliation tasks from
`IMPLEMENTATION_PLAN.md` after validating that the product matrix has no
remaining `partial` or `gap` rows.

Rationale:

- Reconciled the active plan and product-reality steering checkboxes to the
  current matrix outcome: 88 `real`, 0 `partial`, 0 `gap`, 9 `proof-gated`,
  and 17 `policy-question` rows.
- Kept product-owned choices as explicit policy questions rather than
  inventing behavior: Raven identity beyond selected-agent labels,
  cross-agent peer-awareness, SSOT sharing, linked-resource copy/duplicate,
  Refuel Pod SKU/crediting, failed-renewal warning/purge cadence, and
  one-operator versus multi-admin behavior.
- Kept live/external proof rows gated without running live Stripe, Chutes,
  Notion, Cloudflare, Tailscale, Docker install/upgrade, host deploy/upgrade,
  public bot mutation, or deployed Hermes dashboard proof.

Verification run:

- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_documentation_truths.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `python3 tests/test_arclink_mcp_schemas.py` passed.
- `python3 tests/test_memory_synthesizer.py` passed.
- `python3 tests/test_notion_ssot.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_arclink_product_config.py` passed.
- `python3 tests/test_arclink_ingress.py` passed.
- `python3 tests/test_deploy_regressions.py` passed with two environment
  skips for root-readable breadcrumb cases.
- `python3 tests/test_arclink_pin_upgrade_detector.py` passed.
- `python3 tests/test_arclink_upgrade_notifications.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `git diff --check` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 -m py_compile` over changed Python and Python test files passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `cd web && npm test` passed.
- `cd web && npm run lint` passed.
- `cd web && npm run test:browser` passed with 45 passed and 3 expected
  desktop skips for mobile-only layout checks.

Known risks:

- Live proof rows remain unrun because this BUILD gate does not authorize
  live deploys, Docker install/upgrade, production payment flows, public bot
  mutation, external provider proof, private-state inspection, or
  host-mutating operations.
- Policy-question rows remain product decisions; local surfaces are disabled,
  fail-closed, or labeled until the operator chooses those behaviors.

## 2026-05-08 Ralphie Threshold Continuation Policy Gate Build

Scope: resolved the final `partial` product-reality row,
`Raven/dashboard advises safe continuation paths near threshold`, by making the
surface an explicit policy question instead of inventing fallback, refill, or
Raven warning behavior.

Rationale:

- Added a sanitized Chutes `threshold_continuation` public state object for
  warning/exhausted deployments and the provider boundary.
- Rendered the dashboard policy gate in the Model tab while keeping Raven
  notifications, provider fallback, and overage refill disabled until operator
  policy exists.
- Reconciled the matrix/gate counts from 88 `real`, 1 `partial`, 0 `gap`, 9
  `proof-gated`, 16 `policy-question` to 88 `real`, 0 `partial`, 0 `gap`, 9
  `proof-gated`, 17 `policy-question`.

Verification run:

- `python3 -m py_compile python/arclink_chutes.py python/arclink_api_auth.py python/arclink_dashboard.py tests/test_arclink_chutes_and_adapters.py tests/test_arclink_hosted_api.py tests/test_arclink_dashboard.py` passed.
- `python3 -m py_compile python/arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `cd web && npm test` passed.
- `cd web && npm run lint` passed.
- `cd web && npm run test:browser -- tests/browser/product-checks.spec.ts --project=desktop` passed.
- `cd web && npm run test:browser -- tests/browser/product-checks.spec.ts --project=mobile` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 tests/test_documentation_truths.py` passed.
- `git diff --check` passed.

Known risks:

- Live Chutes utilization/key management, provider fallback, refill credit
  accounting, and Raven warning cadence remain gated by operator authorization
  or product policy.
- No live provider, billing, bot, Docker, host, Cloudflare, Tailscale, Notion,
  or deployed dashboard proof was run.

## 2026-05-08 Ralphie Dashboard UX Completion Build

Scope: closed the user/admin dashboard UX partial rows from
`IMPLEMENTATION_PLAN.md` without changing backend route contracts or exposing
new live/provider actions.

Rationale:

- Improved the user dashboard with `Recovery Actions` and `Workspace
  Readiness` panels that group service health, billing, bot handoff,
  credential handoff, linked resources, Notion/SSOT readiness, and provider
  state into tab-linked operational signals.
- Improved the admin dashboard with `Operations Triage` over the existing
  read models, surfacing section readiness, recent failures, queued actions,
  disabled/proof-gated operations, and billing posture without presenting
  unsupported worker actions as executable.
- Kept Chutes threshold/refuel continuation guidance policy-gated: the
  dashboard may show sanitized warning/exhausted state, but does not invent
  fallback, overage, or Refuel Pod paths.
- Reconciled the matrix/gate counts from 86 `real`, 3 `partial`, 0 `gap`, 9
  `proof-gated`, 16 `policy-question` to 88 `real`, 1 `partial`, 0 `gap`, 9
  `proof-gated`, 16 `policy-question`.

Verification run:

- `cd web && npm test` passed.
- `cd web && npm run lint` passed.
- `cd web && npm run build` passed.
- `cd web && npm run test:browser -- tests/browser/product-checks.spec.ts --project=desktop` passed.
- `cd web && npm run test:browser -- tests/browser/product-checks.spec.ts --project=mobile` passed.

Known risks:

- Raven threshold notifications, provider fallback, overage/refuel, and failed
  renewal cadence remain product-policy questions or proof-gated live work.
- Live dashboard landing in a deployed Hermes runtime was not run; that still
  requires explicit operator authorization and credentials.

## 2026-05-08 Ralphie Linked Resource Projection Build

Scope: closed the read-only `Linked` resource projection task from
`IMPLEMENTATION_PLAN.md` without enabling browser right-click share-link
creation.

Rationale:

- Chose system-managed ArcLink projections over public browser share links.
  Accepted grants materialize a sanitized read-only projection under the
  recipient deployment's `linked-resources` root, while the owner/recipient API
  flow remains the source of truth.
- Kept recipient copy/duplicate policy separate: the projection is a managed
  read-only cache for Drive/Code browsing, not permission to copy into a
  recipient Vault or Workspace.
- Preserved secret hygiene by skipping secret-like files during directory
  projection, exposing only sanitized `linked` paths/status in API/UI payloads,
  and keeping Drive/Code `sharing: false`.
- Reconciled the matrix/gate counts from 85 `real`, 4 `partial`, 0 `gap`, 9
  `proof-gated`, 16 `policy-question` to 86 `real`, 3 `partial`, 0 `gap`, 9
  `proof-gated`, 16 `policy-question`.

Verification run:

- `python3 -m py_compile python/arclink_api_auth.py python/arclink_provisioning.py python/arclink_executor.py tests/test_arclink_hosted_api.py tests/test_arclink_plugins.py tests/test_arclink_provisioning.py tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_product_config.py` passed.
- `cd web && npm test -- --runInBand` passed.
- `cd web && npm run lint` passed.
- `cd web && npm run test:browser -- tests/browser/product-checks.spec.ts --project=desktop` passed.
- `cd web && npm run test:browser -- tests/browser/product-checks.spec.ts --project=mobile` passed.
- `python3 tests/test_documentation_truths.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.

Known risks:

- Projection materialization is local/static proof. Live cross-deployment
  content projection still depends on an authorized deployed Control Node run.
- Recipient copy/duplicate behavior remains an explicit operator-policy
  question.

## 2026-05-08 Ralphie Drive/Code Share-Link Policy Gate Build

Scope: closed the Drive/Code right-click share-link task from
`IMPLEMENTATION_PLAN.md` by keeping the browser-plugin surface disabled and
recording the operator-policy gate.

Rationale:

- Evaluated the available local alternatives: revocable ArcLink share grants,
  Nextcloud links, copied files, or leaving browser share-link creation
  disabled. The repository already has governed API/MCP share grants, but the
  product model for browser right-click share links is still an explicit
  operator-policy question.
- Kept Drive and Code right-click share-link creation hidden instead of
  inventing link semantics. Agent-facing `shares.request` remains the
  implemented governed path for named Vault/Workspace resources.
- Made Code root capabilities mirror Drive's fail-closed posture by
  advertising `sharing: false` for Workspace, Vault, and Linked roots. Linked
  resources remain read-only and non-reshareable.
- Reconciled the matrix/gate counts from 85 `real`, 5 `partial`, 0 `gap`, 9
  `proof-gated`, 15 `policy-question` to 85 `real`, 4 `partial`, 0 `gap`, 9
  `proof-gated`, 16 `policy-question`.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/code/dashboard/plugin_api.py tests/test_arclink_plugins.py` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `python3 tests/test_documentation_truths.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.

Known risks:

- This does not implement browser right-click share links. Exposing that UI
  still requires the operator to choose ArcLink grants, Nextcloud links, copied
  files, or a disabled model.
- Live Raven delivery of share approval prompts and full share projection
  browser proof remain gated/follow-up work.

## 2026-05-08 Ralphie Control Node Deployment Style Build

Scope: closed the operator setup deployment-style row from
`IMPLEMENTATION_PLAN.md` and reconciled the already-implemented Raven
`/link-channel` alias checklist item after focused bot verification.

Rationale:

- Added a Control Node install selector for `single-machine`, `hetzner`, and
  `akamai-linode` instead of leaving the operator to infer the worker topology
  from ingress and executor prompts.
- Persisted the normalized choice as `ARCLINK_CONTROL_DEPLOYMENT_STYLE` in the
  generated Docker/control config, with aliases such as `single_machine`,
  `hcloud`, and `linode` normalized to the canonical values.
- Aligned no-secret defaults with executable rails: `single-machine` defaults
  toward local executor plus starter host registration, while `hetzner` and
  `akamai-linode` default toward SSH worker placement.
- Kept live fleet, provider, ingress, and worker proof gated; this slice records
  and documents setup intent without mutating external hosts.
- Verified the canonical `/link-channel` and `/link_channel` commands remain
  registered and compatible with `/pair-channel` and `/pair_channel`; no live
  bot mutation was run.

Verification run:

- `python3 -m py_compile tests/test_deploy_regressions.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_product_config.py` passed.
- `python3 tests/test_documentation_truths.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `git diff --check` passed.

Known risks:

- This does not prove live Hetzner, Akamai Linode, Cloudflare, Tailscale, SSH
  worker, Docker, provider, or host deployment behavior. Those remain gated by
  explicit operator authorization and credentials.

## 2026-05-08 Ralphie Local Chutes Usage Ingestion Build

Scope: closed the local Chutes usage-ingestion and threshold-boundary task from
`IMPLEMENTATION_PLAN.md`.

Rationale:

- Added a local `record_chutes_usage_event` path instead of claiming live
  Chutes metering. The helper applies sanitized metered events to deployment
  metadata and immediately re-evaluates the existing fail-closed Chutes budget
  boundary.
- Usage audit events store only safe identifiers, token counts, and cents.
  Raw provider payloads, headers, secret refs, and key material are not
  persisted.
- Live Chutes per-key utilization and live key/account management remain
  proof-gated until an authorized account/API proof is available.

Verification run:

- `python3 -m py_compile python/arclink_chutes.py tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 -m py_compile python/arclink_chutes.py python/arclink_api_auth.py python/arclink_dashboard.py python/arclink_hosted_api.py tests/test_arclink_chutes_and_adapters.py tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `git diff --check` passed.

Known risks:

- This is local metered-event ingestion. It does not call a live Chutes
  utilization API.
- Raven threshold notifications and Refuel/overage behavior remain blocked on
  the existing product-policy decisions.

## 2026-05-08 Ralphie Chutes Credential Lifecycle Build

Scope: closed the Chutes credential-lifecycle definition task from
`IMPLEMENTATION_PLAN.md`.

Rationale:

- Chose the local fail-closed lifecycle instead of claiming live provider key
  creation. Chutes inference is enabled only for a scoped per-user or
  per-deployment `secret://` reference with a configured budget.
- Operator-shared keys remain rejected as user isolation, plaintext and
  unscoped references fail closed, and provider-state exposes only sanitized
  lifecycle metadata.
- Live Chutes key/account creation and live utilization proof remain
  proof-gated until an authorized account/API proof is available.

Verification run:

- `python3 -m py_compile
  python/arclink_chutes.py python/arclink_api_auth.py python/arclink_dashboard.py
  python/arclink_hosted_api.py tests/test_arclink_chutes_and_adapters.py
  tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `git diff --check` passed.

Known risks:

- This does not create live Chutes keys or ingest live Chutes utilization.
- Refuel/overage behavior and threshold Raven notifications remain
  policy-owned follow-up tasks.

## 2026-05-08 Ralphie Agent Drive Sharing MCP Build

Scope: closed the agent-facing Drive Sharing tool row from
`IMPLEMENTATION_PLAN.md`.

Rationale:

- Added `shares.request` to the existing ArcLink MCP rail instead of creating a
  separate browser-session or secret-bearing agent path. The managed-context
  plugin already injects the caller's bootstrap token into ArcLink MCP calls,
  so the tool can stay scoped to the caller's linked deployment.
- Reused the existing read-only share-grant model. Agent requests create
  `pending_owner_approval`; owner approval and recipient acceptance remain on
  the existing Raven/dashboard rails.
- Kept Linked-root resharing disabled and left recipient copy/duplicate policy
  as an explicit policy question.

Verification run:

- `python3 -m py_compile python/arclink_api_auth.py python/arclink_mcp_server.py plugins/hermes-agent/arclink-managed-context/__init__.py tests/test_arclink_mcp_schemas.py tests/test_arclink_plugins.py` passed.
- `python3 tests/test_arclink_mcp_schemas.py` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `git diff --check` passed.

Known risks:

- This does not add Drive/Code right-click share-link UI or materialized share
  projection browser proof.
- Live Raven delivery of owner approval prompts remains proof-gated.

## 2026-05-08 Ralphie Setup SSOT Dashboard Verification Build

Scope: closed the local Setup SSOT verification story from
`IMPLEMENTATION_PLAN.md`.

Rationale:

- Kept Raven's `/connect_notion` lane as preparation-only and put local
  verification truth in the authenticated dashboard read model.
- Added a no-secret Notion SSOT setup status that combines Raven setup
  metadata, the deployment callback URL, stored webhook verification state, and
  local Notion index presence without returning the webhook token.
- Rendered the status in the user dashboard Memory/QMD tab and kept live
  workspace/page permission proof explicitly proof-gated.

Verification run:

- `python3 -m py_compile python/arclink_dashboard.py tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `cd web && npm test` passed.
- `cd web && npm run lint` passed.
- `cd web && npm run build` passed.
- `cd web && npm run test:browser` passed with 43 passed and 3 expected
  desktop-skipped mobile-layout checks.

Known risks:

- Live Notion workspace/page permission proof was not run and still requires
  explicit operator authorization and credentials.
- Multi-agent SSOT sharing policy remains an operator product decision.

## 2026-05-08 Ralphie Local Payment Gate Reconciliation Build

Scope: reconciled the local payment-before-deployment product row from
`IMPLEMENTATION_PLAN.md`.

Rationale:

- Verified the existing local entitlement gate with onboarding, provisioning,
  and hosted API tests. Unpaid sessions remain blocked, webhook entitlement
  transition is covered locally, and paid claim-session creation is separated
  from live Stripe account proof.
- Kept live Stripe checkout/webhook proof on the existing proof-gated rows
  because it requires external credentials and authorization.

Verification run:

- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.

Known risks:

- Live Stripe price objects, checkout sessions, and webhook delivery were not
  run.

## 2026-05-08 Ralphie Conversational Memory Sibling Guardrail Build

Scope: closed the optional conversational-memory sibling extension contract
from `IMPLEMENTATION_PLAN.md`.

Rationale:

- Documented `arclink-managed-context` as ArcLink's governed retrieval-routing
  layer, with optional conversational-memory plugins allowed only as sibling
  Hermes plugins.
- Guarded the important boundaries: same-user Hermes home only, no cross-user
  vault/private-state reads, no direct shared Notion/SSOT writes, no broad
  auto-capture into governed memory, and retrieval-first evidence rules.

Verification run:

- `python3 -m py_compile tests/test_arclink_plugins.py` passed.
- `python3 tests/test_arclink_plugins.py` passed.

Known risks:

- This adds the supported extension contract only. It does not install or
  certify any third-party conversational-memory plugin.

## 2026-05-08 Ralphie Linked Channel Handoff Proof Build

Scope: closed the local Raven channel-handoff verification row from
`IMPLEMENTATION_PLAN.md`.

Rationale:

- Reused the existing public bot pairing model instead of adding a live bot
  mutation. The regression pairs Telegram to Discord, runs the fake Sovereign
  worker, and proves the ready handoff queues to the sanitized explicit channel
  targets from both linked sessions.
- Kept live Telegram/Discord delivery as proof-gated. This slice proves the
  local routing data path and queue target selection only.

Verification run:

- `python3 -m py_compile tests/test_arclink_sovereign_worker.py python/arclink_sovereign_worker.py python/arclink_public_bots.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.

Known risks:

- Live Telegram/Discord delivery was not run and still requires explicit
  operator authorization.

## 2026-05-08 Ralphie Ready Dashboard And Raven Conduit Build

Scope: closed the local deployment-ready notification, Raven post-onboarding
control-conduit, direct dashboard-link rendering, and share-test coverage tasks
from `IMPLEMENTATION_PLAN.md`.

Rationale:

- Changed Raven's live-user freeform reply from "onboarding only" to a truthful
  control-conduit message: public slash commands still route to Raven, while
  direct private-agent chat belongs in Helm.
- Strengthened Sovereign worker ready-notification coverage so the queued
  `public-bot-user` ping proves the Helm/dashboard link, `/agents`, and
  `/link-channel` actions are included after deployment activation.
- Strengthened browser dashboard coverage for read-only accepted shares, absent
  share-link creation copy, and scoped Hermes/Drive/Code/Terminal links.
- Reconciled the 114-row matrix to 75 `real`, 16 `partial`, 0 `gap`, 9
  `proof-gated`, and 14 `policy-question` rows. Live Hermes dashboard landing
  remains proof-gated instead of overclaimed.

Verification run:

- `python3 -m py_compile python/arclink_public_bots.py tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 -m py_compile python/arclink_sovereign_worker.py tests/test_arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `cd web && npx playwright test tests/browser/product-checks.spec.ts -g "/dashboard renders with mocked data"` passed on desktop and mobile.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `git diff --check` passed.

Known risks:

- Live Telegram/Discord delivery, live Hermes dashboard landing, and production
  host/browser proof remain gated by explicit operator authorization.
- Drive/Code right-click share-link creation and agent-facing share tooling
  remain partial/disabled; this slice added fail-closed browser coverage rather
  than enabling those UI actions.

## 2026-05-08 Ralphie Shipped-Language Truth Gate Build

Scope: closed the P0 shipped-language overclaim gate from
`IMPLEMENTATION_PLAN.md`.

Rationale:

- Demoted the creative brief's broad "implemented" status note to the current
  local public-repo contract and named the live external proof gate for Stripe,
  Telegram, Discord, Notion, Chutes, Cloudflare, Tailscale, Docker, and
  production host paths.
- Tightened partial-surface wording for Notion workspace verification, live
  Hermes runtime access, and provider key creation/utilization so the brief no
  longer reads as live-proofed production behavior.
- Added documentation truth regressions that keep the creative brief labeled
  with the proof gates and fail on shipped docs that claim live external proof
  has passed without an authorized run.

Verification run:

- `python3 -m py_compile tests/test_documentation_truths.py tests/test_public_repo_hygiene.py` passed.
- `python3 tests/test_documentation_truths.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.

Known risks:

- This was a static shipped-copy truth pass. Live Stripe, Telegram, Discord,
  Notion, Chutes, Cloudflare, Tailscale, Docker, and host proof remain gated by
  explicit operator authorization.

## 2026-05-08 Ralphie Local Memory Fallback Build

Scope: closed the local-only/non-LLM memory synthesis fallback row from
`IMPLEMENTATION_PLAN.md` and reclassified the speculative Refuel Pod rows as
policy questions with a shipped-copy guard. It also reclassified the SSOT
share-grant row as a policy question with user-facing fail-closed Notion copy.

Rationale:

- Added a deterministic `local-non-llm-fallback` model that runs only when
  memory synthesis is explicitly enabled without complete LLM credentials.
- Preserved the existing auto-disabled default when no synthesis provider is
  configured, so routine installs do not start generating cards unexpectedly.
- Kept fallback cards low-confidence, low-trust, no-network routing hints based
  on bounded source metadata/snippets; they still tell agents to use retrieval
  tools for evidence before answering or changing state.
- Added a public hygiene regression that fails if speculative `ArcLink Refuel
  Pod` copy appears outside planning/consensus artifacts before SKU, credit
  accounting, and Chutes proof policy exist.
- Added Notion guide wording and a regression that explicitly keep
  self-service SSOT share/accept grants unavailable until the operator chooses
  a shared-root, per-agent/page grant, or operator-approved-only policy.

Verification run:

- `python3 -m py_compile python/arclink_memory_synthesizer.py python/arclink_control.py tests/test_memory_synthesizer.py` passed.
- `python3 tests/test_memory_synthesizer.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 tests/test_arclink_notion_skill_text.py` passed.

Known risks:

- The fallback is intentionally lower fidelity than an LLM synthesis pass. Live
  LLM behavior and production memory-synth service proof remain credential/live
  environment gated.
- Refuel Pod remains disabled/policy-question; no SKU, checkout, or provider
  credit application path was implemented in this slice.
- SSOT sharing remains policy-question; no Notion share grant workflow was
  implemented in this slice.

## 2026-05-08 Ralphie Memory Trust Signals Build

Scope: closed the local memory-card trust/contradiction P1 from
`IMPLEMENTATION_PLAN.md`.

Rationale:

- Extended the memory synthesis prompt and prompt version to request a bounded
  `trust_score` plus explicit contradiction and disagreement signals.
- Normalized the fields into existing `card_json` and rendered them into
  recall-stub card text as retrieval hints, keeping confidence rendering and
  the existing memory table schema intact.
- Preserved the managed-context guardrail that synthesis cards are awareness
  hints only and require MCP retrieval before answering or changing state.

Verification run:

- `python3 -m py_compile python/arclink_memory_synthesizer.py tests/test_memory_synthesizer.py` passed.
- `python3 tests/test_memory_synthesizer.py` passed.

Known risks:

- Live memory synthesis model behavior was not exercised; this remains local
  no-secret proof through the fake model client.

## 2026-05-08 Ralphie Health Visibility Build

Scope: closed the user/admin health visibility P0, policy-classified the
one-operator P0, and verified the Hermes/component upgrade-rail P0 from
`IMPLEMENTATION_PLAN.md`.

Rationale:

- Kept the existing session boundary: user dashboard/provisioning routes remain
  caller-scoped, while the admin service-health route remains admin-session
  only.
- Added focused hosted API assertions proving a user's dashboard does not render
  another user's service-health signal, and proving the admin health route sees
  health rows across multiple deployments with deployment filtering.
- Classified the one-operator versus multi-admin behavior as an operator-policy
  question instead of enforcing a singleton admin rule without product approval.
  Current shipped surfaces do not claim exactly one operator; admin roles and
  active admin sessions remain explicit.
- Verified the component upgrade rails without mutating the host: pin-upgrade
  detection, upgrade notification fanout, deploy-key handling, main-branch
  refusal, deploy operation windows, health ordering, live smoke ordering, and
  active-agent runtime realignment are covered by the focused regression suites.

Verification run:

- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 -m py_compile tests/test_arclink_hosted_api.py` passed.
- `git diff --check` passed.
- Public-copy sweep for exact one-operator claims found no shipped UI/docs
  overclaim outside the plan/research policy question.
- `python3 tests/test_arclink_pin_upgrade_detector.py` passed.
- `python3 tests/test_arclink_upgrade_notifications.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.

Known risks:

- This is local no-secret proof only. Live host health, Docker upgrade, and
  production deploy/upgrade proof remain gated by explicit operator
  authorization.

## 2026-05-08 Ralphie Hermes Upgrade Route Build

Scope: closed the public Hermes-upgrade command gap from
`IMPLEMENTATION_PLAN.md`.

Rationale:

- Added `/upgrade-hermes` and platform-safe `/upgrade_hermes` handling in Raven
  as a non-mutating route. The reply explicitly refuses direct `hermes update`
  behavior and points users to ArcLink-managed component pin, deploy, health,
  and smoke rails.
- Registered Telegram as `upgrade_hermes` and Discord as `upgrade-hermes`
  rather than exposing a Telegram-invalid hyphenated command.

Verification run:

- `python3 -m py_compile python/arclink_public_bots.py tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_telegram.py && python3 tests/test_arclink_discord.py` passed.
- `git diff --check` passed.

Known risks:

- This route does not execute upgrades. Live component upgrades, deploy
  upgrades, and post-upgrade health/smoke proof remain on the operator
  deploy/control rails.

## 2026-05-08 Ralphie Drive Share Revoke Build

Scope: closed the local Drive/Code share-grant lifecycle gap from
`IMPLEMENTATION_PLAN.md`.

Rationale:

- Added owner-scoped `POST /user/share-grants/revoke` on the existing hosted
  API and control-DB share grant model instead of introducing a new Drive/Code
  projection path without browser proof. Accepted shares now leave
  `/user/linked-resources` as soon as the owner revokes the grant.
- Kept linked resources read-only, non-reshareable, CSRF-protected, and
  user-scoped. Recipients cannot revoke or mutate another user's grant through
  this route; denied grants remain closed.

Verification run:

- `python3 -m py_compile python/arclink_api_auth.py python/arclink_hosted_api.py tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `cd web && npm test -- --runTestsByPath tests/test_api_client.mjs` passed.
- `git diff --check` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.

Known risks:

- Drive/Code projection materialization, right-click share UI, full share
  browser proof, and live Raven notification delivery remain future or
  credential-gated work.

## 2026-05-08 Ralphie Retry 2 Dashboard And Raven Share Approval Build

Scope: closed the repairable retry blockers for dashboard auxiliary-load
feedback and Raven share approval buttons from `IMPLEMENTATION_PLAN.md`.

Rationale:

- Kept raw credential values out of the browser and continued using masked
  `secret://` refs plus acknowledgement/removal. The dashboard now shows an
  explicit credential-handoff unavailable state when the credentials endpoint
  fails instead of silently showing an empty panel.
- Kept linked resources read-only and account scoped. The dashboard now shows
  an explicit linked-resource unavailable state when the linked-resource
  endpoint fails instead of silently implying there are no shares.
- Added the missing Raven owner approval surface for Drive/Code shares:
  creating a share grant queues a `public-bot-user` notification with
  Telegram/Discord `Approve` and `Deny` buttons; Raven processes
  `/share-approve {grant_id}` and `/share-deny {grant_id}` only from a public
  channel linked to the grant owner. The hosted API also exposes
  `POST /user/share-grants/deny`.

Verification run:

- `python3 -m py_compile python/arclink_api_auth.py python/arclink_hosted_api.py python/arclink_public_bots.py tests/test_arclink_hosted_api.py tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_telegram.py && python3 tests/test_arclink_discord.py` passed.
- Web checks passed: `npm test`, `npm run lint`, `npm run build`, and
  `npm run test:browser` with 43 passed and 3 desktop-skipped mobile-layout
  checks. The first browser run failed because it was started concurrently with
  `npm run build` while `.next` was being written; rerunning it by itself
  passed.
- `git diff --check` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.

Known risks:

- Live backend browser proof, live Telegram/Discord delivery, live provider
  credential smoke, Stripe, Notion, Cloudflare, Tailscale, Docker
  install/upgrade, and host deploy/upgrade proof remain credential-gated.
- Drive/Code right-click share creation, agent-facing share tooling, revoke
  and projection materialization, and full linked-resource browser proof remain
  BUILD work.
- Raw credential reveal remains intentionally unsupported in the dashboard; use
  the secure completion bundle and acknowledgement/removal contract.

## 2026-05-08 Ralphie Dashboard Credential And Linked Resource Build

Scope: advanced the product-reality credential handoff and linked-resource
dashboard tasks from `IMPLEMENTATION_PLAN.md`.

Rationale:

- Used the existing secure completion bundle and masked `secret://` handoff
  contract instead of introducing browser raw-secret reveal. The dashboard now
  gives users storage guidance and an acknowledgement control while preserving
  the no-raw-secret API boundary.
- Reused the accepted share-grant read model for the Drive tab rather than
  adding a separate sharing UI. The dashboard now shows accepted resources as
  read-only Linked resources and keeps reshare unavailable.

Verification run:

- `npm test` passed.
- `npm run lint` passed.
- `npm run build` passed.
- `npm run test:browser` passed with 41 passed and 3 desktop-skipped
  mobile-layout tests.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `git diff --check` passed.

Known risks:

- Raw credential reveal, live provider credential smoke, Raven share approval
  buttons, and browser proof against a live backend remain proof-gated or
  future lifecycle work.

## 2026-05-08 Ralphie BUILD Verification Pass

Scope: executed the active `IMPLEMENTATION_PLAN.md` BUILD verification tasks
after confirming no unchecked backlog items remained in the plan or steering
file.

Rationale:

- Fixed the web validation failures found during verification instead of
  weakening release checks. Next.js 15 requires `useSearchParams()` users to be
  under `Suspense` during static prerender, so checkout success/cancel now keep
  their existing client behavior inside small Suspense-wrapped content
  components.
- Kept fake-adapter copy truthful by showing it only when the backend reports
  fake mode, and made Playwright deterministic by mocking `adapter-mode` only
  in tests that assert fake-mode UI. Live-mode pages still avoid unconditional
  fake-adapter claims.
- Updated the mocked browser onboarding flow to provide the email now required
  for post-checkout login/status identity.
- Closed the post-review documentation hold by removing stale language that
  described Stripe webhook handling as a no-secret skip. Canonical docs now
  consistently say that an unset `STRIPE_WEBHOOK_SECRET` returns
  `stripe_webhook_secret_unset` with status 503 so Stripe retries.

Documentation surface accounted for:

- `AGENTS.md`, `README.md`, and `docs/DOC_STATUS.md` now frame Shared Host,
  Shared Host Docker, Sovereign Control Node, and canonical/historical/proof-
  gated documentation status.
- `docs/arclink/foundation.md`, `foundation-runbook.md`,
  `operations-runbook.md`, and `control-node-production-runbook.md` now align
  hosted API, action-worker, Stripe webhook, executor, and proof-gated
  production claims.
- `docs/arclink/data-safety.md`, `docs/docker.md`,
  `docs/arclink/local-validation.md`, `docs/arclink/live-e2e-secrets-needed.md`,
  and the live evidence template now describe trust boundaries, Docker socket
  and private-state exposure, validation setup, and credential-gated proof
  limits.
- `docs/arclink/first-day-user-guide.md` and
  `docs/arclink/notion-human-guide.md` cover the customer/operator first-day
  journey, dashboard expectations, Notion SSOT boundaries, and recovery paths.
- `docs/arclink/architecture.md`, `docs/openapi/arclink-v1.openapi.json`,
  `docs/API_REFERENCE.md`, `docs/arclink/CHANGELOG.md`, and the research maps
  were updated to reflect the repaired web/API, Docker, onboarding, knowledge,
  and control-plane surfaces.

Verification run:

- `git diff --check` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 -m py_compile` for touched Python files passed.
- Focused Python suites from the plan passed:
  `test_arclink_plugins.py`, `test_arclink_agent_user_services.py`,
  `test_loopback_service_hardening.py`, `test_arclink_hosted_api.py`,
  `test_arclink_api_auth.py`, `test_arclink_dashboard.py`,
  `test_arclink_action_worker.py`, `test_arclink_admin_actions.py`,
  `test_arclink_provisioning.py`, `test_arclink_sovereign_worker.py`,
  `test_arclink_fleet.py`, `test_arclink_rollout.py`,
  `test_arclink_evidence.py`, `test_arclink_live_runner.py`,
  `test_arclink_docker.py`, `test_deploy_regressions.py`,
  `test_health_regressions.py`,
  `test_arclink_curator_onboarding_regressions.py`,
  `test_arclink_public_bots.py`, `test_pdf_ingest_env.py`,
  `test_memory_synthesizer.py`, `test_arclink_ssot_batcher.py`, and
  `test_documentation_truths.py`.
- Web checks passed: `npm test`, `npm run lint`, `npm run build`, and
  `npm run test:browser` with 41 passed and 3 desktop-skipped mobile-layout
  tests.

Known risks:

- Heavy/live checks were not run: `./test.sh`, live deploy/install/upgrade,
  Docker install/upgrade, Stripe, Cloudflare, Tailscale, Telegram, Discord,
  Notion, provider credential smoke, and public bot mutation flows remain
  proof-gated unless the operator explicitly authorizes them.
- The worktree is intentionally broad from the Ralphie repair mission and still
  needs commit curation before deployment.

## 2026-05-08 Ralphie Slice 5 Onboarding Recovery Build

Scope: closed the remaining Slice 5 onboarding recovery items from
`IMPLEMENTATION_PLAN.md`.

Rationale:

- Used the existing completion receipt and Discord contact retry rails rather
  than adding another handoff channel. `/retry-contact` now gives users and
  operators a visible recovery path that reuses the stored confirmation code.
- Labeled public `/connect_notion` and `/config_backup` as preparation lanes
  because the public bot does not perform Curator-grade Notion verification or
  deploy-key setup. The commands now record pending status and point to the
  dashboard/operator rail for completion.
- For API-key providers, recorded `runtime_pending` validation after checking
  that a credential is present. A live smoke call was not added because the
  onboarding path has no existing side-effect-free provider check and live
  calls may be quota/network dependent.

Verification run:

- `python3 tests/test_arclink_curator_onboarding_regressions.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_onboarding_prompts.py` passed.
- `python3 -m py_compile` for touched onboarding/public-bot modules and tests
  passed.

Known risks:

- This pass did not run live Discord, Telegram, GitHub deploy-key, Notion, or
  provider credential smoke checks. Those remain credential-gated live proof
  surfaces.
- Full BUILD is not complete; Slice 6 knowledge freshness and Slice 7 docs and
  validation items remain open.

## 2026-05-08 Ralphie Shared Host Nextcloud Effective Enablement Build

Scope: advanced Slice 4 / Priority 3 by closing the Nextcloud effective
enablement gap from `IMPLEMENTATION_PLAN.md`.

Rationale:

- Added a shared `nextcloud_effectively_enabled` predicate instead of letting
  install, restart, wait, rotation, and health each interpret raw
  `ENABLE_NEXTCLOUD` differently.
- Treated Docker mode as compose-only, while bare-metal can use either Podman
  or Compose. This matches the existing `nextcloud-up.sh` runtime split and
  avoids starting or waiting on a disabled service when no runtime is present.
- Kept `ENABLE_NEXTCLOUD=1` in persisted config as the operator's intent rather
  than silently rewriting config when the runtime is temporarily unavailable.

Verification run:

- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 tests/test_install_user_services_regressions.py` passed.
- `python3 tests/test_nextcloud_regressions.py` passed.
- `python3 tests/test_health_regressions.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 -m py_compile tests/test_install_user_services_regressions.py
  tests/test_health_regressions.py tests/test_deploy_regressions.py` passed.
- `git diff --check` passed.

Known risks:

- This pass did not run live install/upgrade, mutate systemd units, or start a
  real Nextcloud runtime. Remaining Slice 4 Docker operation items are still
  open.

## 2026-05-08 Priority 0 Security Boundary Repair Slice

Scope: closed the remaining local Priority 0 security boundary items from the
Ralphie ecosystem gap plan.

Rationale:

- Isolated Docker dashboard backends with per-agent internal Docker networks
  instead of trying to rely on the default Compose network plus a public-facing
  auth proxy. The proxy remains the only host-loopback published surface.
- Staged auto-provision bootstrap tokens into the per-agent bootstrap-token file
  before invoking `init.sh`, avoiding raw token handoff through the
  provisioning subprocess environment while preserving `init.sh` compatibility.
- Added generated-root guards before PDF and Notion index cleanup unlinks so a
  corrupted DB path cannot delete outside generated markdown roots.
- Rejected unsafe team-resource slugs before any checkout path construction or
  destructive git reset path can be reached.

Files changed:

- `python/arclink_docker_agent_supervisor.py` and `docs/docker.md`
- `python/arclink_enrollment_provisioner.py` and `bin/init.sh`
- `bin/pdf-ingest.py` and `python/arclink_control.py`
- `bin/clone-team-resources.sh`
- Focused tests under `tests/`

Verification run:

- `python3 tests/test_pdf_ingest_env.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_arclink_auto_provision.py` passed.
- `python3 tests/test_arclink_repo_sync.py` passed.
- `python3 tests/test_arclink_notion_knowledge.py` passed.
- `git diff --check` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 -m py_compile` for touched Python modules and tests passed.

Known risks:

- This slice did not address the hosted web/API identity and checkout backlog;
  those remain the next unchecked Priority 1 items.

## 2026-05-06 Workspace Proof Screenshot And Documentation Handoff

Scope: completed the portable proof-note and documentation handoff tasks for
the native Drive, Code, and Terminal Hermes dashboard plugins.

Rationale:

- Added sanitized screenshot capture to the repeatable
  `bin/arclink-live-proof --journey workspace --live` path instead of keeping
  one-off manual screenshots outside the evidence contract.
- Kept screenshot artifacts under ignored `evidence/workspace-screenshots/`
  and recorded only relative paths in redacted evidence. The screenshot
  sanitizer masks file names, paths, editor text, terminal scrollback, facts,
  and free-form inputs before capture.
- Updated docs to claim only shipped behavior: Drive and Code are
  first-generation native plugins; Code is not Monaco/VS Code parity; Terminal
  is managed-pty with bounded polling, not tmux or true streaming; workspace
  Docker/TLS proof is complete and separate from the broader hosted customer
  live journey.

Files changed:

- `python/arclink_live_runner.py` - records sanitized screenshot references in
  browser proof evidence, masks sensitive UI regions before screenshot capture,
  and reopens Terminal after reload so the screenshot proves the native plugin
  route.
- `tests/test_arclink_live_runner.py` - covers screenshot evidence and runner
  script generation.
- `docs/arclink/architecture.md`, `docs/arclink/foundation.md`,
  `docs/arclink/foundation-runbook.md`,
  `docs/arclink/document-phase-status.md`,
  `docs/arclink/CHANGELOG.md`, and
  `docs/arclink/live-e2e-evidence-template.md` - aligned workspace plugin
  claims with shipped behavior and completed workspace Docker/TLS proof.
- `IMPLEMENTATION_PLAN.md` and
  `research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md` - marked proof-note
  and documentation handoff items complete while leaving commit curation and
  optional deploy handoff open.

Verification run:

- `PYTHONDONTWRITEBYTECODE=1 python3 tests/test_arclink_live_runner.py`
  passed.
- `python3 -m py_compile python/arclink_live_runner.py tests/test_arclink_live_runner.py`
  passed.
- Generated workspace Playwright proof script passed `node --check` via a
  temporary file.
- `./bin/arclink-live-proof --journey workspace --live --json` passed with
  `passed=8`; evidence: `evidence/run_82ace4c10b45.json`.
- The passing live proof covered `deploy.sh docker upgrade`, `deploy.sh docker
  health`, Drive desktop/mobile TLS proof, Code desktop/mobile TLS proof, and
  Terminal desktop/mobile TLS proof.
- Sanitized screenshot references from the passing proof:
  `../evidence/workspace-screenshots/drive-desktop-1778044624358.png`,
  `../evidence/workspace-screenshots/drive-mobile-1778044625589.png`,
  `../evidence/workspace-screenshots/code-desktop-1778044627199.png`,
  `../evidence/workspace-screenshots/code-mobile-1778044628422.png`,
  `../evidence/workspace-screenshots/terminal-desktop-1778044632221.png`,
  `../evidence/workspace-screenshots/terminal-mobile-1778044635510.png`.

Known risks:

- BUILD handoff is still not fully complete because the broad dirty worktree
  has not been curated into scoped commits.
- Production 12 hosted customer proof remains blocked on separate hosted
  credentials; the workspace Docker/TLS proof does not prove Stripe,
  Cloudflare, Chutes, Telegram, or Discord live paths.
- Host readiness in the workspace proof result still reports missing hosted
  provider env vars. Those are unrelated to the completed `workspace` journey
  but remain blockers for the broader hosted journey.

## 2026-05-06 Workspace TLS Proof Bring-Home Pass

Scope: completed the credentialed Docker/TLS proof loop for the native Drive,
Code, and Terminal Hermes dashboard plugins on the target Docker deployment.

Rationale:

- Kept proof execution in `bin/arclink-live-proof --journey workspace --live`
  instead of a one-off transcript so the result remains repeatable and
  redacted.
- Activated Hermes dashboard plugins through their native dashboard links
  instead of assuming direct `/drive`, `/code`, or `/terminal` navigation will
  bypass the dashboard shell. The live Hermes build redirects direct plugin
  routes back through `/sessions` until the native sidebar route is selected.
- Kept the Terminal root guard intact for baremetal/host use and set the
  explicit Docker dashboard allowance only in generated deployment
  `hermes-dashboard` compose repair, where the terminal process is confined to
  the deployment container and `/workspace` mount.

Files changed:

- `python/arclink_live_runner.py` - fixed workspace browser proof script
  placement for Node module resolution, added native dashboard plugin
  navigation for desktop/mobile, and waited for plugin-specific controls before
  running API assertions.
- `plugins/hermes-agent/arclink-terminal/dashboard/dist/index.js` - registered
  Terminal through the same Hermes plugin registry used by Drive and Code.
- `bin/arclink-docker.sh` - repaired generated deployment dashboard compose
  files with `ARCLINK_TERMINAL_ALLOW_ROOT=1` for the Docker container boundary.
- `tests/test_arclink_live_runner.py`, `tests/test_arclink_plugins.py`, and
  `tests/test_arclink_docker.py` - covered the runner script location,
  dashboard navigation contract, Terminal registration API, and Docker
  dashboard env repair.
- `.gitignore` - ignored interrupted local workspace-proof temp directories.
- `IMPLEMENTATION_PLAN.md` and
  `research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md` - marked the
  completed Docker/TLS proof items.

Verification run:

- `./bin/arclink-live-proof --journey workspace --live --json` passed with
  `passed=8`; evidence: `evidence/run_d4513a2ba89b.json`.
- The passing live proof covered `deploy.sh docker upgrade`, `deploy.sh docker
  health`, Drive desktop/mobile TLS proof, Code desktop/mobile TLS proof, and
  Terminal desktop/mobile TLS proof.
- `PYTHONDONTWRITEBYTECODE=1 python3 tests/test_arclink_live_runner.py`
  passed.
- `PYTHONDONTWRITEBYTECODE=1 python3 tests/test_arclink_plugins.py` passed.
- `PYTHONDONTWRITEBYTECODE=1 python3 tests/test_arclink_docker.py` passed.
- `node --check plugins/hermes-agent/arclink-terminal/dashboard/dist/index.js`
  passed.
- `bash -n bin/arclink-docker.sh` passed.
- `git diff --check` passed.

Known risks:

- BUILD handoff is still not fully complete because screenshot capture, commit
  curation, and final deploy-ready documentation/hygiene remain open plan
  items.
- The live runner host-readiness section still reports missing hosted-provider
  env vars for the broader hosted journey; those are unrelated to the
  completed `workspace` journey but should not be mistaken for hosted journey
  proof.

## 2026-05-06 Workspace TLS Proof Executor Slice

Scope: advanced the credential-gated live-proof journey for the native Hermes
workspace plugins from a canonical runner target to default live executors for
Docker upgrade/reconcile, Docker health, and Drive/Code/Terminal desktop/mobile
TLS browser proof.

Rationale:

- Extended the existing `arclink-live-proof` runner instead of creating a
  one-off browser transcript because the current mission needs repeatable,
  redacted proof artifacts before checkboxes can be closed.
- Kept the hosted onboarding/provider journey as the default and added
  `--journey workspace` so workspace proof can be planned without requiring
  Stripe, Chutes, Telegram, or Discord credentials.
- Required `ARCLINK_WORKSPACE_PROOF_TLS_URL` and
  `ARCLINK_WORKSPACE_PROOF_AUTH` by name only; the live runner still does not
  print or persist auth material.
- Added real default runners only for `--journey workspace --live`, keeping the
  broader hosted journey pending until its separate provider runners exist.
- Used Playwright through the existing web dependency set instead of a one-off
  HTTP-only probe, because the plan requires browser proof over the real TLS
  dashboard routes.

Files changed:

- `python/arclink_live_journey.py` - split hosted and workspace proof journeys,
  adding Docker health/reconcile plus Drive, Code, and Terminal desktop/mobile
  TLS proof steps.
- `python/arclink_live_runner.py` - added the `--journey hosted|workspace|all`
  selector, selected default workspace live runners when no fake runners are
  injected, ran the Docker commands, and executed redacted Playwright proof
  steps for `/drive`, `/code`, and `/terminal`.
- `python/arclink_evidence.py` - added workspace proof auth to the explicit
  redaction set.
- `tests/test_arclink_live_journey.py` and
  `tests/test_arclink_live_runner.py` - covered workspace journey structure,
  missing-env reporting, dry-run behavior, fake live runners, and proof auth
  redaction.
- `docs/arclink/live-e2e-secrets-needed.md` and
  `docs/arclink/live-e2e-evidence-template.md` - documented the workspace proof
  env vars, auth formats, execution commands, timeouts, and evidence rows.

Verification run:

- `python3 -m py_compile python/arclink_live_runner.py tests/test_arclink_live_runner.py` passed.
- `python3 tests/test_arclink_live_runner.py` passed.
- `python3 tests/test_arclink_live_journey.py` passed.
- `python3 -m py_compile plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py plugins/hermes-agent/arclink-code/dashboard/plugin_api.py plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py` passed.
- `node --check` passed for the Drive, Code, and Terminal dashboard bundles.
- `python3 tests/test_arclink_plugins.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `bin/arclink-live-proof --journey workspace --json` passed with
  `blocked_missing_credentials` and missing env names only.
- `node --check` passed for the generated workspace Playwright proof script.
- `git diff --check` passed.

Known risks:

- BUILD remains incomplete: the executor path is implemented and locally
  tested, but the actual live Docker upgrade/reconcile, Docker health, and
  Drive/Code/Terminal desktop/mobile TLS browser proof still need a target
  deployment and credentials.

## 2026-05-06 Integration Validation Pass

Scope: executed the deterministic integration checks available without a
credentialed live TLS dashboard or deployment upgrade target.

Rationale:

- Kept live Docker upgrade, Docker health, and TLS browser proof open because
  those require an explicit target deployment and credentialed dashboard access.
- Used the existing validation floor and web browser checks rather than adding
  a new proof harness for native Hermes plugins.

Files changed:

- `IMPLEMENTATION_PLAN.md` - marked the focused integration-check item complete.
- `research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md` - mirrored the
  focused integration-check completion.
- `research/BUILD_COMPLETION_NOTES.md` - recorded this validation pass and the
  remaining live-proof blocker.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py plugins/hermes-agent/arclink-code/dashboard/plugin_api.py plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py` passed.
- `node --check` passed for Drive, Code, and Terminal dashboard bundles.
- `python3 tests/test_arclink_plugins.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.
- `python3 tests/test_arclink_agent_user_services.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 tests/test_health_regressions.py` passed.
- `git diff --check` passed.
- `npm --prefix web test` passed.
- `npm --prefix web run lint` passed.
- `npm --prefix web run build` passed.
- `npm --prefix web run test:browser` passed with 41 passing and 3 skipped
  desktop-inapplicable mobile-layout cases.

Known risks:

- BUILD is not complete: Docker upgrade/reconcile, Docker health, and real TLS
  browser proof for Drive, Code, and Terminal remain open.
- The current proof did not exercise a live Hermes dashboard plugin host.

## 2026-05-06 Code Nested Explorer Slice

Scope: advanced the Code VS Code foundation by replacing the flat Explorer
surface with a bounded nested tree contract, context-menu file operations, and
tab dirty markers while keeping existing confined backend operations.

Rationale:

- Added a native `/tree` plugin API instead of introducing a separate workspace
  app because the Hermes dashboard plugin already owns the Code surface.
- Kept the tree bounded and symlink-pruned so Explorer navigation stays within
  the configured workspace root and does not surface out-of-root symlink
  targets.

Files changed:

- `plugins/hermes-agent/arclink-code/dashboard/plugin_api.py` - added bounded
  `/tree`, advertised nested Explorer capability, and skipped symlink entries
  in workspace listings.
- `plugins/hermes-agent/arclink-code/dashboard/dist/index.js` - added nested
  Explorer rendering, right-click context menu actions, drag/drop move
  confirmation on tree folders, and tab dirty marker updates.
- `plugins/hermes-agent/arclink-code/dashboard/dist/style.css` - styled nested
  Explorer nodes and the context menu.
- `tests/test_arclink_plugins.py` - covered `/tree`, symlink pruning, nested
  Explorer bundle controls, context menus, and dirty-tab markers.
- `IMPLEMENTATION_PLAN.md` and
  `research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md` - marked only the
  validated nested Explorer task complete while leaving TLS proof open.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/arclink-code/dashboard/plugin_api.py` passed.
- `node --check plugins/hermes-agent/arclink-code/dashboard/dist/index.js` passed.
- `python3 tests/test_arclink_plugins.py` passed.

Known risks:

- Code desktop/mobile TLS browser proof remains open.
- The nested tree is intentionally bounded to depth 3 in the UI and depth 4 in
  the backend; deeper folders remain reachable through folder navigation and
  search.

## 2026-05-06 Terminal Managed Pty Slice

Scope: advanced the Terminal persistent-session slice by replacing the scaffold
with a documented ArcLink-managed pty backend, bounded polling dashboard UI, and
focused lifecycle tests.

Rationale:

- Chose the managed-pty fallback instead of requiring tmux in this slice because
  the Docker and baremetal runtime paths do not yet install and validate tmux as
  a shared dependency.
- Used bounded polling rather than WebSockets/SSE because the current Hermes
  plugin host path already supports simple dashboard API calls and this keeps
  reconnect behavior testable without a new transport rail.
- Added an unrestricted-root startup guard so terminal sessions run only inside
  the deployment/user runtime boundary unless an explicit diagnostics override
  is set.

Files changed:

- `plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py` - added
  managed-pty session create/list/read/input/rename/close endpoints, atomic
  session state, bounded scrollback, root guard, and redacted backend errors.
- `plugins/hermes-agent/arclink-terminal/dashboard/dist/index.js` - added the
  Terminal session list, new session, input, polling refresh, rename, folder,
  reorder, and close confirmation UI.
- `plugins/hermes-agent/arclink-terminal/dashboard/dist/style.css` - added
  responsive session, terminal pane, input, error, and confirmation styles.
- `plugins/hermes-agent/arclink-terminal/README.md` - documented the
  managed-pty backend, polling limitation, root guard, and future tmux path.
- `tests/test_arclink_plugins.py` - covered Terminal create/revisit/input,
  rename/folder/reorder, close confirmation, scrollback bounds, traversal
  rejection, redaction, root guard, and browser bundle controls.
- `IMPLEMENTATION_PLAN.md` and
  `research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md` - marked only the
  validated Terminal managed-pty tasks complete while leaving TLS proof open.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py plugins/hermes-agent/arclink-code/dashboard/plugin_api.py plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py` passed.
- `node --check plugins/hermes-agent/arclink-terminal/dashboard/dist/index.js`
  passed.
- `python3 tests/test_arclink_plugins.py` passed.

Known risks:

- Terminal desktop/mobile TLS browser proof remains open.
- The current transport is bounded polling, not true streaming.
- tmux is still a future backend option; Docker/baremetal install validation
  has not been added for tmux.

## 2026-05-05 Code Source Control Diff Slice

Scope: advanced the Code VS Code foundation by adding a bounded backend diff
contract and a browser diff view for Source Control changed-file clicks.

Rationale:

- Kept the diff implementation inside the native ArcLink Code plugin API and
  dashboard bundle instead of introducing a separate app or Hermes core patch.
- Used allowlisted `git diff`/`git show` reads plus existing workspace/repo path
  confinement so Source Control can inspect staged, unstaged, and untracked
  text changes without shelling out through an unrestricted terminal surface.
- Left Monaco evaluation for the dedicated editor task; this slice only needed
  a source-control diff view.

Files changed:

- `plugins/hermes-agent/arclink-code/dashboard/plugin_api.py` - added
  `/git/diff` with size bounds, text-file guards, and repo-confined file
  resolution.
- `plugins/hermes-agent/arclink-code/dashboard/dist/index.js` - changed Source
  Control changed-file clicks to fetch and render a before/after diff view.
- `plugins/hermes-agent/arclink-code/dashboard/dist/style.css` - added
  responsive diff-pane styling.
- `tests/test_arclink_plugins.py` - covered working-tree, staged, untracked,
  and traversal-rejected diff behavior plus the browser bundle contract.
- `IMPLEMENTATION_PLAN.md` and
  `research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md` - marked only the
  validated diff-view task complete.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py plugins/hermes-agent/arclink-code/dashboard/plugin_api.py plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py` passed.
- `node --check plugins/hermes-agent/arclink-code/dashboard/dist/index.js` passed.
- `python3 tests/test_arclink_plugins.py` passed.

Known risks:

- Drive TLS proof remains externally blocked by lack of a credentialed TLS
  dashboard target in this environment.
- Code still needs nested Explorer operations, Search/status bar, richer git
  actions, theme/auto-save controls, Monaco decision, and live browser proof.

## 2026-05-05 Deploy Baseline And Drive Trash UX Slice

Scope: executed the highest-priority deploy-readiness validation from the
native workspace plugin plan, repaired the README canonical shared-host layout
contract, and advanced Drive browser UX with root-aware breadcrumbs plus a
Trash/Restore view backed by the existing Drive APIs.

Rationale:

- Restored `/home/arclink/` in the README shared-host layout blocks instead of
  weakening the Docker regression that protects operator documentation.
- Kept Drive work in the native Hermes plugin's plain JavaScript bundle and
  existing Python API boundary; no Hermes core or separate Next.js workspace app
  changes were needed for this slice.
- Left sharing disabled because there is still no real Nextcloud/WebDAV share
  adapter with tests.

Files changed:

- `README.md` - restored the canonical `/home/arclink/` root in Shared Host
  layout examples.
- `plugins/hermes-agent/arclink-drive/dashboard/dist/index.js` - added
  root-labeled `Drive / Vault|Workspace` breadcrumbs, a Trash mode, restore
  actions, selected trash restore, and disabled upload/drop affordances while
  viewing trash.
- `tests/test_arclink_plugins.py` - added a focused browser bundle contract
  check for Drive roots, breadcrumbs, Trash, and Restore controls.
- `IMPLEMENTATION_PLAN.md` and
  `research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md` - marked only the
  validated deploy-readiness and Drive root/sharing checklist items complete.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py plugins/hermes-agent/arclink-code/dashboard/plugin_api.py plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py` passed.
- `node --check plugins/hermes-agent/arclink-drive/dashboard/dist/index.js && node --check plugins/hermes-agent/arclink-code/dashboard/dist/index.js && node --check plugins/hermes-agent/arclink-terminal/dashboard/dist/index.js` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `python3 tests/test_arclink_agent_user_services.py` passed.
- `python3 tests/test_arclink_docker.py` failed first on the README layout root, then passed after the README repair.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 tests/test_health_regressions.py` passed.
- `git diff --check` passed.

Known risks:

- Drive still needs full desktop/mobile TLS browser proof before Slice 2B is
  complete.
- The new Trash/Restore coverage is a static bundle contract plus existing
  backend tests, not a real browser interaction test.
- Code VS Code foundation, Terminal persistent sessions, Docker/TLS integration
  proof, commit curation, and deploy handoff remain open.

## 2026-05-05 Native Workspace Plugin Slice 1

Scope: completed the first build slice for native Hermes dashboard workspaces
by adding the `arclink-terminal` plugin scaffold, enabling it by default, and
standardizing sanitized `/status` contracts across Drive, Code, and Terminal.

Rationale:

- Kept the implementation inside ArcLink dashboard plugins and the existing
  installer instead of patching Hermes core.
- Shipped Terminal as an honest scaffold: it reserves the dashboard tab and
  reports backend capability discovery, but leaves persistent sessions disabled
  until the Slice 4 tmux or managed-pty backend is implemented.
- Exposed capability flags through status payloads so the UI and tests can
  distinguish available file/code surfaces from deferred terminal persistence
  without leaking tokens, passwords, credentials, or private keys.

Files changed:

- `plugins/hermes-agent/arclink-terminal/` - new dashboard plugin scaffold.
- `plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py` - status
  contract metadata.
- `plugins/hermes-agent/arclink-code/dashboard/plugin_api.py` - status
  contract metadata.
- `bin/install-arclink-plugins.sh` - default Terminal plugin install/enable.
- `tests/test_arclink_plugins.py` - install and sanitized status coverage.
- `README.md` and `AGENTS.md` - default plugin surface documentation.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py plugins/hermes-agent/arclink-code/dashboard/plugin_api.py plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py` passed.
- `node --check` passed for Drive, Code, and Terminal dashboard `dist/index.js`.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `python3 tests/test_arclink_agent_user_services.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `git diff --check` passed.

Known risks:

- Terminal persistence, streaming, scrollback, reload reconnect, grouping, and
  confirmation-gated close/kill remain Slice 4 implementation work.
- Live TLS browser proof remains dependent on an accessible deployed dashboard.

## 2026-05-02 Build Attempt 2 Handoff Repair

Scope: repaired the Attempt 2 BUILD handoff artifacts so machine checks can
distinguish the completed no-secret build slice from the remaining external
P12 live-proof gate.

Files changed:

- `IMPLEMENTATION_PLAN.md` -- clarified that the scale-operations spine and
  live-proof runner already satisfy the current no-secret BUILD scope, and that
  credentialed P12 proof is not a repairable implementation gap without the
  named external credentials.
- `research/BUILD_COMPLETION_NOTES.md` -- added this retry record so the build
  phase has an explicit tracked mutation and a current verification trail.

Rationale:

- Preserved the existing implementation modules and tests because the codebase
  already contains `arclink_fleet.py`, `arclink_action_worker.py`,
  `arclink_rollout.py`, `arclink_live_runner.py`, and their focused tests.
- Recorded the external blocker as Stripe, Cloudflare, Chutes, Telegram,
  Discord, and production host credentials rather than weakening the live gate
  or claiming live proof from fake/no-secret tests.
- Kept the retry to status artifacts because no failing acceptance test or
  missing product-code artifact was identified.

Verification run:

- `git diff --check` passed.
- Exact uppercase fallback-sentinel search across plan, research, docs, Python,
  tests, and config returned no matches.
- `PYTHONPATH=python python3 tests/test_arclink_live_runner.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_e2e_live.py` passed with the
  expected six credential/live-gated skips.
- `PYTHONPATH=python python3 tests/test_arclink_evidence.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_live_journey.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_host_readiness.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_diagnostics.py` passed.
- `PYTHONPATH=python python3 tests/test_public_repo_hygiene.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_fleet.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_action_worker.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_rollout.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_hosted_api.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_dashboard.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py`
  passed.

Known risks:

- Production 12 remains unproven against live providers until the explicit
  credentialed live run is supplied and executed.

## 2026-05-02 Build Retry Validation Closure

Scope: re-ran the active BUILD gate from `IMPLEMENTATION_PLAN.md` after the
Attempt 2 retry guidance. No implementation repair was required: the plan's
remaining actionable BUILD work is limited to externally credentialed live
proof, and the no-secret validation floor passes.

Rationale:

- Preserved the existing scale-operations, operator snapshot, and live-proof
  orchestration work instead of rebuilding completed slices without a failing
  acceptance check.
- Kept the phase artifact to implementation notes only because the retry found
  no missing product-code artifact and no regression in the required no-secret
  checks.
- Continued to treat credentialed P12 live execution as blocked by named
  external accounts and secrets.

Verification run:

- `git diff --check` passed.
- `PYTHONPATH=python python3 tests/test_arclink_live_runner.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_e2e_live.py` passed with the
  expected six credential/live-gated skips.
- `PYTHONPATH=python python3 tests/test_arclink_evidence.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_live_journey.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_host_readiness.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_diagnostics.py` passed.
- `PYTHONPATH=python python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py`
  passed.

Known risks:

- Credentialed live proof still requires real Stripe, Cloudflare, Chutes,
  Telegram, Discord, and production host credentials before P12 can be declared
  proven live.

## 2026-05-02 Hosted API Contract Expansion

Scope: expanded the hosted API boundary and API/auth layer with health,
provider state, reconciliation, billing portal, and Telegram/Discord webhook
routes, plus corresponding test coverage.

Rationale:

- Added `GET /health` as a public liveness check (DB reachable = ok/degraded)
  so load balancers and monitoring can probe the API without auth.
- Added `GET /user/provider-state` and `GET /admin/provider-state` to surface
  current provider, default model, and per-deployment model assignments through
  the session-authenticated API boundary.
- Added `GET /admin/reconciliation` to expose Stripe-vs-local entitlement drift
  through the admin session gate, consuming the existing
  `detect_stripe_reconciliation_drift` helper.
- Added `POST /webhooks/telegram` and `POST /webhooks/discord` routes to the
  hosted router, delegating to the existing runtime adapter handlers with
  proper error shaping.
- Removed redundant `_rowdict` wrappers from `arclink_api_auth.py` and
  `arclink_dashboard.py`, using the shared `rowdict` from `arclink_boundary`.

Files changed:

- `python/arclink_hosted_api.py` (733 -> 777 lines) -- new routes and handlers.
- `python/arclink_api_auth.py` (813 -> 862 lines) -- `read_provider_state_api`,
  `read_admin_reconciliation_api`, removed `_rowdict`.
- `python/arclink_dashboard.py` -- removed `_rowdict`.
- `tests/test_arclink_hosted_api.py` (26 -> 30 test functions) -- health,
  provider state, reconciliation, billing portal tests.
- Research docs updated to reflect new line counts, test counts, and P1 gap
  narrowing.

Known risks:

- Hosted API is still not deployed behind a production reverse proxy or
  identity provider.
- Provider state read exposes deployment model assignments; access control is
  session-scoped but not deployment-scoped.
- Reconciliation drift detection depends on local DB state; live Stripe API
  comparison remains E2E-gated.

## 2026-05-02 Remove Redundant _rowdict Wrappers

Scope: removed private `_rowdict` wrapper functions from `arclink_api_auth.py`
and `arclink_dashboard.py`, replacing all call sites with the shared `rowdict`
helper already imported from `arclink_boundary`.

Rationale:

- Both modules had identical `_rowdict(row)` one-liners that delegated to the
  shared `rowdict` from `arclink_boundary`. The indirection added no value and
  obscured the actual dependency.
- The shared `rowdict` is the canonical row-to-dict helper across the codebase;
  using it directly makes the ownership and contract clearer.

Files changed:

- `python/arclink_api_auth.py` - removed `_rowdict` definition (3 lines),
  replaced 5 call sites with `rowdict`.
- `python/arclink_dashboard.py` - removed `_rowdict` definition (3 lines),
  replaced 6 call sites with `rowdict`.

Known risks:

- None. Pure rename with no behavioral change; `rowdict` was already the
  underlying implementation.

## 2026-05-01 Active Lint-Repair Gate Build

Scope: completed the current BUILD gate from `IMPLEMENTATION_PLAN.md` and
`research/RALPHIE_LINT_BLOCKER_REPAIR_STEERING.md` without adding hosted
request signing, production frontend work, live bot clients, or provider/host
mutation.

Rationale:

- Validated public onboarding channel and identity through the shared
  onboarding validator before rate limiting so invalid channels fail without
  writing `rate_limits`.
- Kept the repair inside the existing Python dashboard, API/auth, product
  surface, and public-bot helper boundaries because those are the accepted
  no-secret contracts for this build slice.
- Preserved domain-specific `ArcLinkApiAuthError` and
  `ArcLinkDashboardError` responses while keeping the generic product-surface
  exception path user-safe.
- Reused the shared onboarding rate-limit helper for public bot turns instead
  of adding Telegram or Discord client behavior in this pass.

Verification run:

- The invalid-channel acceptance probe printed
  `ArcLinkOnboardingError unsupported ArcLink onboarding channel: email` and
  `0`.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_product_surface.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py`
  passed.
- `python3 -m ruff check python/arclink_dashboard.py python/arclink_api_auth.py python/arclink_product_surface.py python/arclink_public_bots.py tests/test_arclink_dashboard.py tests/test_arclink_api_auth.py tests/test_arclink_product_surface.py tests/test_arclink_public_bots.py`
  passed.
- `git diff --check` passed.

Known risks:

- The API/auth/RBAC layer is still a no-secret helper contract, not hosted
  production identity.
- The product surface remains a stdlib WSGI prototype.
- Live Stripe, Cloudflare, Chutes, Telegram, Discord, Notion, OAuth, and host
  execution remain E2E-gated.

## 2026-05-01 Production Dashboard Contract Build

Scope: advanced the Production Dashboard plan without introducing a frontend
toolchain by making the user/admin dashboard read models explicitly enumerate
the production sections the future web app must render.

Rationale:

- Extended the existing Python dashboard/API contracts instead of adding
  Next.js/Tailwind in this slice, because this checkout has no frontend
  toolchain yet and the implementation plan says the production web app should
  follow stable API/auth contracts.
- Added user dashboard section contracts for deployment health, access links,
  bot setup, files, code, Hermes, qmd/memory freshness, skills, model, billing,
  security, and support.
- Added admin dashboard section contracts for onboarding, users, deployments,
  payments, infrastructure, bots, security/abuse, releases/maintenance,
  logs/events, audit, and queued actions.
- Kept the local WSGI product surface as a no-secret prototype that displays
  those sections, with live provider mutation still gated.

Verification run:

- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_product_surface.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py`
  passed.
- `python3 -m ruff check python/arclink_dashboard.py python/arclink_product_surface.py tests/test_arclink_dashboard.py tests/test_arclink_product_surface.py`
  passed.
- `git diff --check` passed.

Known risks:

- This is still not the production Next.js/Tailwind dashboard.
- Browser workflow coverage for the final frontend remains a follow-up.
- Live Stripe, Cloudflare, Chutes, Telegram, Discord, Notion, and host
  execution paths remain E2E-gated.

## 2026-05-01 Product Surface Lint-Blocker Repair

Scope: closed the immediate BUILD gate for the local no-secret ArcLink product
surface without expanding production dashboard, RBAC, live adapter, or host
mutation work.

Rationale:

- Added a tiny inline SVG favicon response in the existing stdlib WSGI surface
  instead of introducing static asset plumbing or a frontend framework, because
  the route only needs to stop browser smoke from reporting a harmless 404.
- Reconciled coverage notes with the accepted responsive browser-smoke evidence:
  narrow mobile around 390px and desktop around 1440px for `/`,
  `/onboarding/onb_surface_fixture`, `/user`, and `/admin`, with no page-level
  horizontal overflow.
- Kept the WSGI product surface documented as a replaceable prototype.

Verification run:

- `python3 tests/test_arclink_product_surface.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py`
  passed.
- `python3 -m ruff check python/arclink_product_surface.py python/arclink_public_bots.py tests/test_arclink_product_surface.py tests/test_arclink_public_bots.py`
  passed.
- Favicon smoke returned `200 image/svg+xml`.
- `git diff --check` passed.

Known risks:

- Production browser automation still belongs with the future production
  frontend.
- Production API/auth/RBAC, live provider adapters, and host execution remain
  gated follow-up work.

## 2026-05-01 API/Auth Boundary Build

Scope: completed the next no-secret ArcLink API/auth boundary slice without
introducing a production web framework or live provider mutation.

Rationale:

- Added Python helper APIs instead of introducing FastAPI/Next.js routing in
  this pass, because the current repo patterns already expose ArcLink behavior
  through tested Python boundaries and the plan calls for API/auth contracts to
  stabilize before the production dashboard.
- Stored user/admin session tokens and CSRF tokens only as hashes, with
  explicit rate-limit hooks for public onboarding and MFA-ready admin mutation
  gating.
- Kept TOTP enrollment secret material as `secret://` references and masked
  those references in read output, leaving real TOTP code verification for the
  production auth provider/E2E phase.

Verification run:

- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_product_surface.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py` passed.
- `git diff --check` passed.

Known risks:

- This is still a helper/API contract layer, not hosted production browser
  authentication, OAuth, or a deployed HTTP API.
- TOTP is schema- and gate-ready, but real one-time-code validation remains a
  production auth/E2E follow-up.
- Live Stripe, Cloudflare, Chutes, Telegram, Discord, Notion, and host
  execution paths remain gated.

## 2026-05-01 Product Surface Foundation Build

Scope: completed the first Phase 9 no-secret ArcLink product-surface slice
without enabling real Docker, Cloudflare, Chutes, Stripe, Telegram, Discord, or
host mutation.

Rationale:

- Added a small stdlib Python WSGI surface instead of introducing Next.js now,
  because the current acceptance criteria need a runnable no-secret product
  workflow and clean API/read-model boundaries before production auth, RBAC,
  routing, and frontend build tooling are selected.
- Rendered the first screen as the usable onboarding workflow rather than a
  marketing-only page, with fake checkout, user dashboard, admin dashboard, and
  queued admin-action routes backed by existing `arclink_*` helpers.
- Added deterministic Telegram/Discord public bot adapter skeletons that share
  the same onboarding session semantics as web onboarding and keep public bot
  state separate from private user-agent bot tokens.

Verification run:

- `python3 tests/test_arclink_product_surface.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py` passed.
- `python3 -m ruff check python/arclink_product_surface.py python/arclink_public_bots.py tests/test_arclink_product_surface.py tests/test_arclink_public_bots.py` passed.
- `git diff --check` passed.

Known risks:

- The local WSGI product surface is a replaceable prototype, not the production
  Next.js/Tailwind dashboard.
- Browser session auth, RBAC, CSRF/rate limits, hosted routes, real Telegram
  and Discord clients, live Stripe checkout/webhooks, live provider/edge
  adapters, and action executors remain E2E-gated follow-ups.

## 2026-05-01 Executor Replay/Dependency Consistency Repair Build

Scope: completed the active `IMPLEMENTATION_PLAN.md` executor
replay/dependency consistency repair without enabling real Docker, Cloudflare,
Chutes, Stripe, or host mutation.

Rationale:

- Added stable operation-digest checks for fake Cloudflare DNS, Cloudflare
  Access, Chutes key lifecycle, and rollback idempotency keys so key reuse with
  changed inputs is rejected before stored results are returned.
- Kept Chutes replay strict by returning stored action and stored secret
  reference only for identical replay, and rejecting action or secret-ref drift.
- Made fake Docker Compose planning reject `depends_on` references to missing
  rendered services, matching the dependency validation real Compose would
  enforce.

Verification run:

- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_executor.py python/arclink_provisioning.py` passed.
- `python3 -m ruff check python/arclink_executor.py tests/test_arclink_executor.py` passed.
- `git diff --check` passed.

Known risks:

- Real Docker Compose execution, Cloudflare mutation, Chutes key lifecycle,
  Stripe live actions, dashboard/API wiring, and public bot onboarding remain
  E2E-gated follow-ups.

## 2026-05-01 Executor Lint-Risk Repair Build

Scope: completed the active `IMPLEMENTATION_PLAN.md` executor lint-risk repair
without enabling real Docker, Cloudflare, Chutes, Stripe, or host mutation.

Rationale:

- Returned stored fake Docker Compose `applied` replay state before resolving
  current secret material, while keeping rendered-intent digest checks ahead
  of replay.
- Rejected `fake_fail_after_services <= 0` with `ArcLinkExecutorError` so the
  fake adapter cannot accidentally apply a service for a zero limit.
- Replaced rollback destructive-delete detection with an explicit helper and
  covered state-root and vault-delete action variants.
- Added a Cloudflare DNS record type allowlist for `A`, `AAAA`, `CNAME`, and
  `TXT` before fake/live apply.

Verification run:

- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_executor.py python/arclink_provisioning.py` passed.
- `git diff --check` passed.

Known risks:

- Real Docker Compose execution, Cloudflare mutation, Chutes key lifecycle,
  Stripe live actions, dashboard/API wiring, and public bot onboarding remain
  E2E-gated follow-ups.

## 2026-05-01 Executor Idempotency Digest Repair Build

Scope: completed the `IMPLEMENTATION_PLAN.md` executor digest repair without
enabling real Docker, Cloudflare, Chutes, Stripe, or host mutation.

Rationale:

- Stored the rendered `intent_digest` in fake Docker Compose run state so
  explicit idempotency keys are bound to the provisioning intent they first
  applied or partially applied.
- Rejected explicit Docker Compose idempotency-key reuse when the rendered
  intent digest changes, instead of treating the request as a replay or stale
  partial resume.
- Kept implicit idempotency based on the digest unchanged, so callers that do
  not provide an explicit key still get digest-scoped fake runs.

Verification run:

- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_executor.py python/arclink_provisioning.py` passed.
- `git diff --check` passed.

Known risks:

- Real Docker Compose execution, Cloudflare mutation, Chutes key lifecycle,
  Stripe live actions, dashboard/API wiring, and public bot onboarding remain
  E2E-gated follow-ups.

## 2026-05-01 Provider, Edge, And Rollback Fake Executor Build

Scope: completed Tasks 4 and 5 from `IMPLEMENTATION_PLAN.md` without enabling
real Cloudflare, Chutes, Stripe, Docker, or host mutation.

Rationale:

- Extended the existing `arclink_executor` module instead of introducing a
  second provider executor package, so all mutating boundaries still share the
  same explicit live/E2E gate and secret-free result objects.
- Kept Cloudflare DNS/Access and Chutes lifecycle behavior fake and stateful by
  idempotency key, which lets unit tests prove create/rotate/revoke, replay,
  and access-policy planning without live provider credentials.
- Made rollback execution consume a plan, stop rendered services, remove only
  unhealthy service markers, preserve customer state roots, and leave
  `secret://` references for review. The fake result exposes appendable audit
  event names but does not mutate the control-plane database from the adapter.

Verification run:

- `python3 tests/test_arclink_product_config.py` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_ingress.py` passed.
- `python3 tests/test_arclink_access.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py` passed.
- `python3 -m ruff check python/arclink_executor.py tests/test_arclink_executor.py` passed.
- `git diff --check` passed.

Known risks:

- Real Cloudflare DNS/tunnel/access mutation, Chutes key lifecycle, Docker
  rollback effects, Stripe live admin actions, and hosted dashboard/API action
  wiring remain E2E-only follow-ups.

## 2026-05-01 Docker Compose Fake Executor Build

Scope: completed Task 3 from `IMPLEMENTATION_PLAN.md` without enabling real
Docker Compose mutation.

Rationale:

- Extended the existing `arclink_executor` boundary instead of adding a second
  compose runner, so execution continues to consume the dry-run provisioning
  intent as the single source of service, volume, label, and secret semantics.
- Kept the fake adapter stateful by idempotency key, which lets tests exercise
  partial failure, resume, and replay behavior without writing compose files or
  starting containers.
- Planned env file, compose file, project name, volumes, labels, and service
  start order from rendered intent, while secret materialization still returns
  only `/run/secrets/*` targets.

Verification run:

- `python3 tests/test_arclink_product_config.py` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_ingress.py` passed.
- `python3 tests/test_arclink_access.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py` passed.
- `python3 -m ruff check python/arclink_executor.py tests/test_arclink_executor.py` passed.
- `git diff --check` passed.

Known risks:

- Real `docker compose` invocation remains an E2E-only follow-up. Provider and
  edge mutation adapters, rollback execution, and hosted dashboard/API flows
  remain pending.

## 2026-05-01 Live Executor Boundary Build

Scope: completed the first live-executor boundary slice from
`IMPLEMENTATION_PLAN.md` without enabling live host or provider mutation.

Rationale:

- Added a dedicated `arclink_executor` module instead of putting execution
  state into the dry-run provisioning renderer. The renderer remains the
  source of service/DNS/access intent; the executor consumes that intent.
- Made every mutating executor operation fail closed unless an explicit
  live/E2E flag is present. Unit tests can still exercise the boundary with a
  fake adapter name and fake secret resolver.
- Added resolver contracts that materialize `secret://` references to
  `/run/secrets/*` paths while keeping plaintext secret values inside resolver
  internals and out of returned results.

Verification run:

- `python3 tests/test_arclink_product_config.py` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_ingress.py` passed.
- `python3 tests/test_arclink_access.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py` passed.
- `git diff --check` passed.

Known risks:

- Docker Compose execution, Cloudflare mutation, Chutes key lifecycle, Stripe
  actions, and rollback execution are still fakeable contracts only; real
  mutation remains an E2E-only follow-up.

## 2026-05-01 Entitlement Preservation Repair Build

Scope: completed the active entitlement preservation repair from
`IMPLEMENTATION_PLAN.md` without requiring live secrets.

Rationale:

- Made `upsert_arclink_user()` treat omitted `entitlement_state` as a
  profile-only update instead of an implicit write to `none`. This preserves
  the existing helper API for profile fields while keeping
  `set_arclink_user_entitlement()`, Stripe webhooks, and admin comp helpers as
  explicit entitlement writers.
- Kept new users defaulting to `none` on insert, with an empty
  `entitlement_updated_at` when no entitlement mutation was requested.
- Updated public onboarding deployment preparation to avoid passing an
  implicit `none`, so returning paid or comped users keep entitlement state and
  timestamp while onboarding resumes.

Verification run:

- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_onboarding.py python/arclink_entitlements.py` passed.
- `git diff --check` passed.

Known risks:

- Live Stripe checkout/webhook delivery, Cloudflare, Chutes key lifecycle,
  public bot credentials, Notion, dashboards, and deployment-host execution
  remain E2E prerequisites.

## 2026-05-01 Public Onboarding Contract Build

Scope: completed the Phase 7 no-secret public onboarding contract from
`IMPLEMENTATION_PLAN.md`.

Rationale:

- Added durable `arclink_onboarding_sessions` and
  `arclink_onboarding_events` rows instead of binding website/bot state to the
  private ArcLink user-agent onboarding tables. Public Telegram and Discord ids
  are channel hints, not private deployment bot credentials.
- Kept Stripe checkout behind the existing fake adapter boundary with
  deterministic idempotency-key session ids, instead of adding a live Stripe SDK
  dependency before E2E secrets and hosted callback URLs exist.
- Connected checkout success through the existing signed entitlement webhook
  and deployment gate. Onboarding observes the lifted gate and records funnel
  events; it does not grant provisioning directly.

Verification run:

- `python3 -m py_compile python/arclink_control.py python/arclink_adapters.py python/arclink_entitlements.py python/arclink_onboarding.py python/arclink_provisioning.py` passed.
- `python3 tests/test_arclink_product_config.py` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_ingress.py` passed.
- `python3 tests/test_arclink_access.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_model_providers.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.

Known risks:

- Live Stripe checkout creation, hosted success/cancel URLs, public Telegram
  and Discord bot delivery, Cloudflare, Chutes key lifecycle, and deployment
  execution remain E2E prerequisites.

## 2026-05-01 Stripe Webhook Transaction Ownership Guard Build

Scope: completed the Stripe webhook transaction ownership guard from
`IMPLEMENTATION_PLAN.md` without requiring live secrets.

Rationale:

- Rejected caller-owned active SQLite transactions before starting the Stripe
  webhook transaction instead of attempting nested transaction/savepoint
  ownership. The handler's existing atomicity contract is simpler when it owns
  the whole webhook transaction.
- Kept replayable failure marking unchanged for handler-owned transactions, so
  supported webhook failures still roll back entitlement side effects and can
  be replayed.

Verification run:

- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 -m py_compile python/arclink_entitlements.py python/arclink_control.py tests/test_arclink_entitlements.py` passed.
- `python3 -m ruff check python/arclink_entitlements.py python/arclink_control.py tests/test_arclink_entitlements.py` passed.
- `python3 -m pyflakes python/arclink_entitlements.py python/arclink_control.py tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.

Known risks:

- Live Stripe delivery, checkout orchestration, Cloudflare, Chutes key
  lifecycle, bot credentials, Notion, and deployment-host execution remain E2E
  prerequisites.

## 2026-05-01 Stripe Invoice Parent Compatibility Build

Scope: completed the current Stripe invoice compatibility repair from
`IMPLEMENTATION_PLAN.md` without live secrets.

Rationale:

- Extended the existing Stripe payload extraction helpers instead of adding a
  Stripe SDK dependency or a second invoice parser. The current code only needs
  stable, no-secret extraction from verified webhook JSON.
- Preserved legacy top-level metadata, top-level subscription id, and
  `parent.subscription` behavior while adding the current
  `parent.subscription_details` shape.

Verification run:

- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 -m py_compile python/arclink_entitlements.py python/arclink_control.py tests/test_arclink_entitlements.py` passed.
- `python3 -m ruff check python/arclink_entitlements.py python/arclink_control.py tests/test_arclink_entitlements.py` passed.
- `python3 -m pyflakes python/arclink_entitlements.py python/arclink_control.py tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.

Known risks:

- Live Stripe delivery, checkout orchestration, Cloudflare, Chutes key
  lifecycle, bot credentials, Notion, and deployment-host execution remain E2E
  prerequisites.

## 2026-05-01 Stripe Webhook Atomicity Build

Scope: completed the Stripe webhook atomicity repair from
`IMPLEMENTATION_PLAN.md` without requiring live secrets.

Rationale:

- Kept the existing SQLite/Python control-plane helpers and added opt-in
  `commit=False` paths instead of introducing a new transaction abstraction.
  This preserves public helper auto-commit behavior while letting Stripe
  webhook handling defer all entitlement side effects to one transaction.
- Kept failed webhook attempts replayable by rolling back partial entitlement
  work first, then recording the webhook row as `failed` in a separate minimal
  marker write.

Verification run:

- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_ingress.py` passed.
- `python3 tests/test_arclink_access.py` passed.
- `python3 -m py_compile python/arclink_entitlements.py python/arclink_control.py tests/test_arclink_entitlements.py` passed.
- `python3 -m ruff check python/arclink_entitlements.py python/arclink_control.py tests/test_arclink_entitlements.py` passed.
- `python3 -m pyflakes python/arclink_entitlements.py python/arclink_control.py tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.

Known risks:

- Live Stripe delivery, checkout orchestration, Cloudflare, Chutes key
  lifecycle, bot credentials, Notion, and deployment-host execution remain E2E
  prerequisites.

## 2026-05-01 Build Retry

Scope: completed the lint-held entitlement, Tailscale timeout, and provisioning
secret-resolution build slice from `IMPLEMENTATION_PLAN.md` without requiring
live secrets.

Rationale:

- Kept the existing Docker/Python control-plane path instead of adding a new
  SaaS shell because the current plan prioritizes no-secret provisioning
  contracts and regression coverage.
- Preserved global manual comp behavior as a support override, and added
  regression coverage proving it advances all entitlement-gated deployments for
  the user.
- Kept targeted deployment comp as a deployment-scoped override that does not
  mutate the user's global entitlement state or unblock unrelated deployments.
- Kept Compose `_FILE` secrets for stock images where supported, with explicit
  resolver-required fallbacks for application tokens before live execution.

Verification run:

- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.

Known risks:

- Live Stripe, Cloudflare, Chutes key lifecycle, bot credentials, Notion, and
  deployment-host execution remain E2E prerequisites.
- The current build validates rendered provisioning intent only; it does not
  start live per-deployment containers.

## 2026-05-05 Drive Slice 2 Hardening Build

Scope: advanced the Slice 2 ArcLink Drive Google Drive foundation tasks from
`IMPLEMENTATION_PLAN.md`, focused on root safety, upload conflict policy, batch
partial-failure surfacing, and focused plugin regression coverage.

Rationale:

- Kept uploads reject-by-default for existing local filenames so drag/drop and
  file-picker uploads cannot silently overwrite user files.
- Added explicit `keep-both` as the only local upload conflict alternative,
  reusing the existing copy/duplicate conflict naming behavior instead of
  adding a replace path without overwrite confirmation UI.
- Rejected WebDAV `keep-both` because there is no tested adapter that can prove
  a non-overwriting remote destination name; WebDAV reject mode uses
  `If-None-Match: *` to avoid silent remote overwrite.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `node --check plugins/hermes-agent/arclink-drive/dashboard/dist/index.js` passed.
- `git diff --check` passed.

Known risks:

- Browser runtime proof against a live Hermes dashboard was not available in
  this build pass, so mobile layout and interactive Drive proof remain runtime
  verification items.
- The repository already contained broad unrelated dirty and untracked changes;
  this pass stayed scoped to Drive API/UI, focused plugin tests, and these
  implementation notes.

## 2026-05-05 Drive Slice 2 Attempt 2 Root Boundary Repair

Scope: repaired the consensus-held Drive Slice 2 blocker by enforcing root
boundary checks while constructing local list and search items.

Rationale:

- Kept direct symlink-escape requests as explicit 403 errors, preserving the
  existing path safety contract.
- Pruned symlink-escaped children from list and search traversal before item
  metadata is built, so local Drive views do not expose size, modified time, or
  type information for files outside the selected root.
- Added focused regression coverage for both symlinked files and symlinked
  folders that point outside the vault.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `node --check plugins/hermes-agent/arclink-drive/dashboard/dist/index.js` passed.
- `git diff --check` passed.

Known risks:

- Browser runtime proof against a live Hermes dashboard remains a test-phase
  item; this retry only repaired the local API boundary blocker.

## 2026-05-05 Drive Slice 2 Browser Batch And Confirmation Build

Scope: advanced the remaining Drive browser UX tasks from
`IMPLEMENTATION_PLAN.md`, focused on selected-item batch operations, partial
failure surfacing, and deliberate confirmation gates.

Rationale:

- Kept the work inside the native Hermes dashboard plugin bundle instead of
  introducing an external Drive app or Hermes core changes.
- Added a small Drive-local confirmation dialog rather than a broad shared UI
  framework detour; the immediate blocker was risky Drive actions, not a full
  cross-plugin component system.
- Used the existing `/batch` API contract for restore, copy, and move so the UI
  can report per-item failures without implying all-or-nothing success.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py plugins/hermes-agent/arclink-code/dashboard/plugin_api.py plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `node --check plugins/hermes-agent/arclink-drive/dashboard/dist/index.js` passed.
- `node --check plugins/hermes-agent/arclink-code/dashboard/dist/index.js` passed.
- `node --check plugins/hermes-agent/arclink-terminal/dashboard/dist/index.js` passed.
- `git diff --check` passed.

Known risks:

- Live TLS desktop/mobile browser proof was not available in this build pass.
- Rename, new-file, and folder-path entry still use native prompt dialogs; the
  deliberate in-app confirmation work in this slice covers overwrite conflict,
  move, trash, and selected trash flows.

## 2026-05-06 Workspace Plugin Handoff Validation

Scope: completed the final handoff lane for the native ArcLink Drive, Code, and
Terminal workspace plugin mission without running a live deploy.

Rationale:

- Kept the native workspace suite in Hermes dashboard plugins and ArcLink
  wrappers rather than adding a separate workspace application or patching
  Hermes core.
- Preserved managed-pty terminal persistence as the tested backend and kept
  streaming transport documented as future work because the proven dashboard
  host path uses bounded polling.
- Treated deployment as an operator-owned next step; this pass curated commits
  and validation without pushing or running `./deploy.sh upgrade`.

Verification run:

- Plugin Python compile, plugin JavaScript syntax checks, shell syntax checks,
  and `git diff --check` passed.
- Focused Python suites for plugins, deploy, Docker, provisioning, dashboards,
  live runner/journey, health, bot delivery, public bots, sovereign worker,
  Chutes/adapters, run-agent-code-server, and agent user services passed.
- Web unit smoke, lint, production build, and Playwright browser tests passed;
  the browser run reported 41 passing checks with 3 expected desktop skips for
  mobile-only layout assertions.

Known risks:

- This handoff did not push commits or run the canonical live host upgrade.
- Live release state and Docker health remain the previously recorded proof
  status until an operator requests deployment.

## 2026-05-08 Ralphie P0 Notion And SSOT Boundary Build

Scope: advanced the highest-priority unchecked security boundary items from
`IMPLEMENTATION_PLAN.md`: exact live Notion reads and destructive SSOT update
payloads.

Rationale:

- Scoped `notion.fetch` and `notion.query` inside the existing Notion index
  root model instead of adding a separate privileged-read mode. Exact reads now
  allow configured roots, active indexed pages, and parent-walk-proven children;
  out-of-root live reads are denied and audited.
- Rejected destructive SSOT fields at payload validation time rather than
  inventing an approval rail in this pass. The public broker already rejects
  archive/delete/trash operations, and no explicit destructive approval model
  exists yet.

Verification run:

- `python3 -m py_compile python/arclink_control.py` passed.
- `python3 tests/test_arclink_notion_knowledge.py` passed.
- `python3 tests/test_ssot_broker.py` passed.

Known risks:

- A future operator-approved destructive Notion rail would need a distinct
  policy, audit, and UI flow; this build intentionally fails closed.

## 2026-05-08 Ralphie Shared Host Health Probe Build

Scope: advanced Slice 4 / Priority 3 by closing the health DB probe failure
gap from `IMPLEMENTATION_PLAN.md`.

Rationale:

- Kept health behavior in `bin/health.sh` instead of adding a separate
  diagnostic runner. The existing shell health surface is what install,
  upgrade, and operators already use.
- Treated Python probe command failures as hard health failures even outside
  strict mode, while preserving structured `WARN`, `FAIL`, and `OK` output for
  expected degraded states.

Verification run:

- `bash -n bin/health.sh tests/test_health_regressions.py` passed.
- `python3 tests/test_health_regressions.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.

Known risks:

- This pass did not run live `./deploy.sh health` or mutate the host. Remaining
  Slice 4 Docker/operations tasks still need dedicated implementation or
  validation before BUILD can be declared complete.

## 2026-05-08 Ralphie Shared Host Root Unit Build

Scope: advanced Slice 4 / Priority 3 Shared Host operations by verifying the
completed upstream-branch and bare-metal dependency fixes, then repairing root
systemd unit path rendering for custom config/repo paths.

Rationale:

- Kept the production upstream contract on `main`, matching the existing
  upgrade guard, config examples, and deploy regressions instead of widening
  production upgrades to arbitrary branches.
- Added/verified `jq` and `iproute2` in bare-metal bootstrap because existing
  pins and health commands depend on those host tools.
- Rendered root units with systemd-native quoting and specifier escaping rather
  than shell wrapping. Newline/carriage-return and dollar-sign paths are
  rejected because they cannot be made legible or portable in generated unit
  files.

Verification run:

- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_arclink_enrollment_provisioner_regressions.py` passed.
- `git diff --check` passed.

Known risks:

- This pass did not run live install/upgrade or touch `/etc/systemd/system`.
- Remaining Slice 4 items around Nextcloud enablement, Docker health, Docker
  release state, and Docker trust boundaries are still open.

## 2026-05-08 Ralphie Onboarding Recovery Build

Scope: advanced Slice 5 / Priority 4 by closing local no-secret onboarding
recovery gaps for Curator auto-provision, operator notifications, denied
sessions, backup skip, and public bot cancel.

Rationale:

- Surfaced auto-provision failures through the existing Curator session state
  instead of introducing a second retry tracker. `onboarding_sessions` already
  drives `/status`, so durable `provision_error` plus one user notification is
  the narrowest recoverable path.
- Redacted generated dashboard passwords from operator notifications by
  default and kept user credential delivery in the existing completion bundle,
  with an explicit opt-in env for credential-bearing operator channels.
- Treated backup `skip` as durable user intent for the completed-session
  backfill, while preserving `/setup-backup` as the user-initiated recovery
  path.
- Made public `/cancel` close active onboarding/checkout state instead of only
  sub-workflow metadata; live deployments are not cancelled from public chat.

Verification run:

- `python3 -m py_compile python/arclink_control.py python/arclink_enrollment_provisioner.py python/arclink_onboarding.py python/arclink_public_bots.py python/arclink_onboarding_flow.py` passed.
- `python3 tests/test_arclink_enrollment_provisioner_regressions.py` passed.
- `python3 tests/test_arclink_onboarding_prompts.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.

Known risks:

- Completion acknowledgement retry/recovery and public Notion/backup command
  depth remain open Slice 5 work.
- This pass did not run live bot, Stripe, host provisioning, or deployment
  flows.

## 2026-05-08 Ralphie Knowledge Freshness Build

Scope: completed Slice 6 / Priority 5 knowledge freshness and generated
content safety gaps for PDF ingest, memory synthesis, SSOT event batching, and
the ArcLink resources skill.

Rationale:

- Hashed the resolved PDF vision endpoint inside the pipeline signature instead
  of writing the URL into generated markdown. This preserves change detection
  without leaking endpoint userinfo, query values, or private hostnames.
- Moved PDF ingest fast-path checks behind source SHA-256 comparison so
  same-size, same-second PDF rewrites regenerate sidecars.
- Replaced memory synthesis file freshness fingerprints with content hashes for
  scanned source files while keeping raw hashes out of model prompts.
- Added DB row claims for Notion webhook batch processing. Pending events move
  to `processing` with a claim id before work starts; stale processing claims
  can be reclaimed after a lease.
- Removed the unsafe GitHub raw fallback installer URL from the resources skill
  and replaced stale Raven wording with current ArcLink/Curator wording.

Verification run:

- `python3 tests/test_pdf_ingest_env.py` passed.
- `python3 tests/test_memory_synthesizer.py` passed.
- `python3 tests/test_arclink_ssot_batcher.py` passed.
- `python3 tests/test_arclink_resources_skill.py` passed.
- `python3 -m py_compile bin/pdf-ingest.py python/arclink_memory_synthesizer.py python/arclink_control.py python/arclink_ssot_batcher.py` passed.
- `bash -n skills/arclink-resources/scripts/show-resources.sh deploy.sh bin/*.sh test.sh` passed.
- `git diff --check` passed.

Known risks:

- This pass did not run live Notion webhook ingestion, live qmd reindexing,
  PDF vision model calls, or live memory synthesis LLM calls.
- Slice 7 documentation and validation coverage remains open before the full
  Ralphie BUILD can be declared complete.

## 2026-05-08 Ralphie Product Isolation Floor Build

Scope: advanced the highest-priority product-reality isolation floor by
tightening public Raven channel-linking and active-agent selection boundaries
after the hosted API user-route isolation checks were added.

Rationale:

- Refused channel-pair claims when the target channel already belongs to a
  different ArcLink account instead of overwriting that channel's session. This
  keeps pairing as a same-user/same-account bridge and fails closed when account
  ownership is ambiguous.
- Honored `active_deployment_id` only when the deployment belongs to the
  session's user. This preserves same-account agent switching while preventing
  stale or malformed session metadata from selecting another user's pod.
- Kept `/link-channel` and `/link_channel` as canonical user-facing commands
  while preserving `/pair-channel` and `/pair_channel` compatibility.

Verification run:

- `python3 -m py_compile python/arclink_public_bots.py python/arclink_api_auth.py python/arclink_discord.py python/arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `git diff --check` passed.

Known risks:

- Full BUILD is not complete. Credential acknowledgement/removal and the first
  linked-resource grant core are now covered by the next note below; right-click
  sharing UI, Raven approval notifications, live Stripe/bot/Notion proof,
  billing renewal policy, and remaining product matrix gaps still need
  dedicated passes or operator-policy decisions.

## 2026-05-08 Ralphie Credential And Linked Resource Build

Scope: closed the next highest-priority local product-reality gaps for
credential acknowledgement/removal and the first read-only linked-resource share
model.

Rationale:

- Added a credential-handoff state machine in the hosted API. Users can read
  pending handoff metadata with masked secret refs only, acknowledge storage
  with CSRF, and the handoff is removed from future user API reads while
  audit/event rows record the transition.
- Added a read-only share-grant lifecycle: owner request, owner approval,
  recipient acceptance, and recipient-only linked-resource reads. Share
  creation refuses `linked` roots so accepted shares cannot be reshared.
- Exposed a third `Linked` root in Drive and Code when a linked-resource
  projection is present. The root is read-only and unavailable by default so
  standalone plugin installs still degrade cleanly.
- Kept Drive/Code right-click sharing and Raven approve/deny notifications
  disabled instead of implying UI behavior that is not yet wired.

Verification run:

- `python3 -m py_compile python/arclink_control.py python/arclink_api_auth.py python/arclink_hosted_api.py plugins/hermes-agent/drive/dashboard/plugin_api.py plugins/hermes-agent/code/dashboard/plugin_api.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_plugins.py` passed.

Known risks:

- Full BUILD is still incomplete. Right-click share UI, Raven share
  approve/deny notification buttons, share revoke/projector materialization,
  live Stripe/bot/Notion proof, billing renewal policy, and remaining product
  matrix rows still need follow-up passes or operator-policy decisions.

## 2026-05-08 Ralphie Linked Root Git Guard Follow-up

Scope: closed the Attempt 3 linked-root Code Git mutation guard gap without
changing the read-only linked-resource product boundary.

Rationale:

- Routed Code Git write endpoints through the same linked-root read-only guard
  already used by normal Code file mutations. Repo discovery, open, status, and
  diff stay readable for accepted linked resources.
- Added a regression fixture with a real Git repository under the `Linked`
  root. The test proves status/diff reads work while stage, unstage, discard,
  commit, gitignore, pull, and push all fail with the linked-resource guard
  before changing the index, worktree, or `.gitignore`.
- Normalized root-level repo display paths from `/.` to `/` so linked root
  source-control entries are represented consistently with other root views.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/code/dashboard/plugin_api.py plugins/hermes-agent/drive/dashboard/plugin_api.py` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `git diff --check` passed.

Known risks:

- Full BUILD is still incomplete. Dashboard credential UI wiring, Drive/Code
  right-click sharing, Raven share approve/deny buttons, share revoke/projector
  materialization, live Stripe/bot/Notion proof, billing renewal policy, and
  remaining product matrix rows still need follow-up passes or operator-policy
  decisions.

## 2026-05-08 Ralphie Chutes Boundary Build

Scope: advanced the Section 6 P0 Chutes provider gap by adding a local,
fail-closed per-user/per-deployment credential and budget boundary with
sanitized user/admin visibility.

Rationale:

- Used scoped `secret://` references plus deployment metadata budgets as the
  local adapter contract instead of reading live keys or inventing a live
  Chutes account API. Operator-shared `CHUTES_API_KEY` presence is explicitly
  rejected as user isolation.
- Kept usage enforcement fail-closed: missing scoped secret, missing budget,
  suspended/revoked state, and hard-limit exhaustion block inference in the
  adapter boundary. Warning thresholds remain allowed but visible.
- Exposed only sanitized state through provider-state and dashboard model data:
  credential state, isolation mode, budget counters, allowance, and reason. Raw
  env values and `secret://` refs are not returned by provider-state.
- Left live Chutes key creation and live usage ingestion proof-gated because
  those require external account capability proof and operator authorization.

Verification run:

- `python3 -m py_compile python/arclink_chutes.py python/arclink_api_auth.py python/arclink_hosted_api.py python/arclink_dashboard.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `git diff --check` passed.

Known risks:

- Runtime usage metering still needs to feed real Chutes spend into the local
  boundary before live budget enforcement can be claimed end to end.
- Raven threshold/refuel notifications and failed-renewal policy remain open.
- Live Chutes account/key creation and API proof were not run.

## 2026-05-08 Ralphie Pricing And Entitlement Consistency Build

Scope: closed the Section 6 P0 local pricing and entitlement-count checks for
Founders, Sovereign, Scale, and Agentic Expansion.

Rationale:

- Added static consistency coverage tying together Compose price defaults,
  `config/env.example`, API/operations docs, public bot dollar constants, and
  web onboarding price labels.
- Kept the public hygiene provider-name gate current by recognizing the
  Chutes-specific provider-state API/test surfaces as model-provider context.
- Documented monthly-cent defaults beside the existing Stripe price-id defaults
  so operator-facing config surfaces match the public `$149/$199/$275` and
  `$99/$79` labels.
- Added onboarding coverage proving Founders and Sovereign reserve one
  entitlement-gated deployment slot, while Scale reserves three, before any
  provisioning can execute.

Verification run:

- `python3 -m py_compile tests/test_arclink_product_config.py tests/test_arclink_onboarding.py tests/test_public_repo_hygiene.py` passed.
- `python3 tests/test_arclink_product_config.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `git diff --check` passed.

Known risks:

- Live Stripe price objects and checkout/webhook proof remain credential-gated
  and were not run.
- Failed-renewal reminder cadence, grace period, retention, and purge policy
  remain open.

## 2026-05-08 Ralphie Knowledge And Linked-Root Verification Build

Scope: closed the locally provable Section 4 P0 knowledge/retrieval checks and
the Section 5 linked-root preservation check without live credentials or host
mutation.

Rationale:

- Used existing qmd, Notion index, managed-context, MCP schema, hosted API, and
  plugin regression suites as no-secret proof rather than adding duplicate
  harnesses. These suites cover vault/PDF/Notion collections, webhook-driven
  indexing queues, recall-stub guardrails, preferred MCP retrieval recipes,
  user-scoped daily plate context, and read-only Linked roots.
- Left Setup SSOT policy/model work open because the canonical Notion ownership
  model and credential-confirmation sequencing still need product decisions or a
  scoped implementation pass.
- Kept Drive/Code share-link UI and projection/browser proof classified as
  partial instead of claiming a full visible sharing lifecycle.

Verification run:

- `python3 tests/test_arclink_plugins.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_notion_knowledge.py` passed.
- `python3 tests/test_memory_synthesizer.py` passed.
- `python3 tests/test_arclink_memory_sync.py` passed.
- `python3 tests/test_arclink_mcp_schemas.py` passed.
- `python3 tests/test_arclink_mcp_http_compat.py` passed.

Known risks:

- Full BUILD is still incomplete. Setup SSOT sequencing/model, shipped-language
  copy demotion, Raven direct-agent-chat semantics, billing renewal policy,
  one-operator policy, live Stripe/bot/Notion/Chutes proof, and broader browser
  validation remain open.

## 2026-05-08 Ralphie Setup SSOT Sequencing Build

Scope: closed the Section 4 P0 Setup SSOT sequencing/model slice for Raven's
public Notion setup lane.

Rationale:

- Kept the current Notion integration model on ArcLink's brokered shared-root
  SSOT rail. User-owned OAuth and email-share-only API access were not presented
  as real because the repository does not prove those paths.
- Added a Raven gate that blocks `/connect_notion` until the deployment's
  credential handoff rows are acknowledged/removed through the existing
  dashboard flow. The gate reads only public control-plane handoff status, not
  secret material.
- Preserved live Notion verification as dashboard/operator work and kept chat
  copy explicit that tokens and API keys do not belong in Raven messages.

Verification run:

- `python3 -m py_compile python/arclink_public_bots.py tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.

Known risks:

- Live Notion workspace verification remains proof-gated.
- Multi-agent SSOT sharing policy remains an operator product decision.
- The full BUILD backlog still has unrelated open P0/P1 tasks.

## 2026-05-08 Ralphie Managed-Context Cadence And Almanac Truth Build

Scope: closed the Section 4 P1 managed-context cheap-layer versus
expensive-layer cadence slice and the Almanac copy-truth slice.

Rationale:

- Kept the existing injection gates intact: full managed context still appears
  only for first turns, revision/runtime changes, relevant turns, relevant
  follow-ups, or recipes that require full context.
- Labeled compact resource and tool-recipe injections as cheap cadence layers,
  and full refreshed managed-context injection as the expensive cadence layer.
- Added telemetry fields for `cadence_layer`, `cadence_layers`, and
  `cadence_reasons` so operators can see why each layer injected without
  recording user messages or secrets.
- Confirmed shipped docs, web, Python, plugins, templates, config, and tests do
  not present Almanac as a top-level product identity; research artifacts now
  classify it as planning vocabulary only.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/arclink-managed-context/__init__.py tests/test_arclink_plugins.py` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `rg -n "Almanac|almanac" README.md docs web python plugins tests config templates` returned no matches.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.

Known risks:

- This is a local plugin cadence contract; live token-spend measurement was not
  run and remains external operational proof.
- The memory synthesis local-only fallback and optional conversational-memory
  extension-point tasks remain open.

## 2026-05-08 Ralphie Failed-Renewal Lifecycle Build

Scope: closed the Section 6 P1 billing renewal slice by implementing local
provider suspension and truthfully modeling the remaining policy-owned renewal
steps.

Rationale:

- Chose fail-closed provider suspension for non-current billing states because
  it is directly enforceable from local entitlement state and preserves the
  existing Chutes credential/budget boundary.
- Left reminder cadence, grace period, data retention, and purge timing as
  `policy_question` fields instead of inventing destructive account-removal
  behavior without an operator decision.
- Exposed the same sanitized lifecycle in user billing, provider-state, the
  dashboard read model, and the Next.js billing tab without returning provider
  secrets.

Verification run:

- `python3 -m py_compile python/arclink_chutes.py python/arclink_api_auth.py python/arclink_dashboard.py tests/test_arclink_chutes_and_adapters.py tests/test_arclink_hosted_api.py tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `cd web && npm test` passed.
- `cd web && npm run lint` passed.
- `cd web && npm run build` passed.
- `cd web && npm run test:browser` passed with 43 passed and 3 expected desktop mobile-layout skips.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.

Known risks:

- Raven daily reminders, grace-period copy, data retention, and purge/removal
  policy remain blocked on the operator-policy question recorded in
  `consensus/build_gate.md`.
- Live Stripe and Chutes behavior were not run; those remain credential-gated.

## 2026-05-08 Ralphie Admin Action Truth Build

Scope: closed the P1 admin-action truthfulness slice without running live host
or provider mutations.

Rationale:

- Reused the existing action worker boundary instead of widening admin
  mutations: `restart`, `dns_repair`, `rotate_chutes_key`, `refund`, and
  `cancel` are modeled worker actions; not-yet-wired actions remain visible as
  disabled/pending rather than pretending to execute.
- Published the same execution-readiness contract in the admin read model,
  scale-operations snapshot, Next.js admin action form, and lightweight product
  surface.
- Kept action queuing reason-required, CSRF-protected, audited, and
  secret-safe.

Verification run:

- `python3 -m py_compile python/arclink_dashboard.py python/arclink_product_surface.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_product_surface.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `cd web && npm test` passed.
- `cd web && npm run lint` passed.
- `cd web && npm run test:browser` passed with 45 passed and 3 expected desktop mobile-layout skips.
- `git diff --check` passed.

Known risks:

- Live executor/provider effects were not run; live deploy, DNS, Stripe, and
  Chutes mutations remain gated by explicit operator authorization.
- Broader operator setup choices, admin dashboard hierarchy, and sharing
  projection work remain open BUILD tasks.

## 2026-05-08 Ralphie Provider Settings Truth Build

Scope: moved the provider-add/settings journey out of `partial` by making the
current no-secret product posture explicit in API and dashboard surfaces.

Rationale:

- Chose a disabled, policy-question settings posture instead of adding a live
  provider mutation path, because self-service provider changes and `/provider`
  semantics are product decisions and raw provider token collection would touch
  credential handoff policy.
- Published the posture in `/user/provider-state` as sanitized
  `provider_settings` metadata, with dashboard mutation disabled, raw provider
  token collection forbidden, and live provider mutation proof-gated.
- Rendered the same state on the user dashboard Model tab so users see current
  provider/model/budget status without being invited to paste secrets or assume
  live key changes are available.

Verification run:

- `python3 -m py_compile python/arclink_api_auth.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `cd web && node --test web/tests/test_api_client.mjs` passed.
- `cd web && npm run lint` passed.
- `cd web && npm test` passed.
- `cd web && npm run test:browser` passed with 45 passed and 3 expected
  desktop mobile-layout skips.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 tests/test_documentation_truths.py` passed.
- `git diff --check` passed.

Known risks:

- User self-service provider changes remain a policy question in
  `consensus/build_gate.md`; no Hermes `/provider` mutation, raw provider-key
  intake, or live Chutes key change was implemented.
- Live Chutes key/account proof remains gated by explicit operator
  authorization and credentials.

## 2026-05-09 End-To-End Gap Repair Pass

Scope: repaired the highest-risk gaps from the repository-wide ArcLink audit
without touching private state, live credentials, user homes, or live provider
accounts.

Rationale:

- Website checkout now carries one-time browser proof material for dashboard
  claim/cancel instead of treating onboarding session ids as bearer secrets.
  Stripe Checkout receives the known email hint, success/cancel pages verify
  backend state, and cancel stays resume-aware instead of writing a stale
  noncanonical status.
- User dashboard Drive/Code/Terminal now preserves broad user-owned
  Vault/Workspace access, including ordinary user `.env` files, while blocking
  ArcLink control-plane env files, Hermes secrets/state, bootstrap tokens, and
  private SSH material. Terminal sessions start with a scrubbed allowlist env.
- ArcLink MCP/qmd rails now keep vault tools to vault collections, scrub PDF
  generated host paths, restore Notion indexed fallback for
  `knowledge.search-and-fetch`, and restrict memory synthesis Notion reads to
  the Notion markdown index root.
- Control Node now deploys a real `control-action-worker`, keeps the
  provisioner enabled by default, records disabled executor state cleanly when
  live mutation credentials are absent, and invokes real Docker Compose
  lifecycle runners for non-fake restart/stop/inspect/teardown actions.
- Branch defaults and upgrade guardrails now align to `arclink`, Docker health
  proves the action worker job, bootstrap/runtime dependency declarations were
  tightened, and CI installs Python deps plus runs web lint/test/build.
- Documentation now states the user-home vs control-plane boundary, active
  knowledge/memory rails, brokered SSOT destructive-write posture, enabled
  Control Node worker contract, and sanitized founder/cohort creative guidance.

Verification run:

- `python3 -m py_compile python/arclink_api_auth.py python/arclink_hosted_api.py python/arclink_onboarding.py python/arclink_adapters.py python/arclink_mcp_server.py python/arclink_memory_synthesizer.py python/arclink_executor.py python/arclink_action_worker.py python/arclink_sovereign_worker.py python/arclink_dashboard_auth_proxy.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 tests/test_arclink_api_auth.py`, `test_arclink_hosted_api.py`,
  `test_arclink_dashboard_auth_proxy.py`, `test_arclink_mcp_schemas.py`,
  `test_memory_synthesizer.py`, `test_arclink_executor.py`,
  `test_arclink_action_worker.py`, `test_arclink_docker.py`,
  `test_deploy_regressions.py`, `test_arclink_plugins.py`,
  `test_health_regressions.py`, `test_hermes_runtime_pin_regressions.py`,
  `test_arclink_agent_user_services.py`, `test_arclink_public_bots.py`,
  `test_arclink_onboarding_prompts.py`,
  `test_arclink_enrollment_provisioner_regressions.py`,
  `test_documentation_truths.py`, `test_arclink_dashboard.py`,
  `test_arclink_admin_actions.py`, `test_arclink_chutes_oauth.py`,
  `test_arclink_pins.py`, and `test_arclink_upgrade_notifications.py` passed.
- `cd web && npm run lint`, `npm test`, and `npm run build` passed.
- `git diff --check` passed.

Known risks:

- Live Stripe, Chutes, Cloudflare, Tailscale, Notion, Telegram, Discord, Docker
  host mutation, and real user-dashboard browser proof remain gated by explicit
  operator authorization and real credentials.
- SSOT destructive writes remain intentionally brokered rather than fully
  unrestricted; approval/undo policy can be relaxed later, but raw destructive
  Notion writes should not bypass ArcLink scope/audit rails.
- Nextcloud/WebDAV direct delete remains a legacy backend path; the native
  Drive/Code roots use local trash semantics and linked ArcLink resources use
  scoped read-only projections.

## 2026-05-11 Ralphie Wave 1C Webhook Trust Boundary Build

Scope: completed Wave 1C webhook trust-boundary repairs from
`IMPLEMENTATION_PLAN.md`.

Rationale:

- Added `TELEGRAM_WEBHOOK_SECRET` as the public Telegram webhook secret-token
  lane in config templates, Compose, deploy config rendering, Telegram config,
  and Telegram `setWebhook` registration.
- Hosted Telegram webhook handling now fails closed when the secret is absent
  and uses constant-time comparison for `X-Telegram-Bot-Api-Secret-Token`
  before update dispatch.
- Discord interaction webhooks now enforce timestamp freshness and reserve
  interaction IDs in `arclink_webhook_events`, rejecting duplicates as replay.
- Stripe, Telegram, and Discord hosted webhook routes now share a provider-
  scoped remote-subject rate-limit gate before expensive verification or
  dispatch. Limits are configurable with `ARCLINK_WEBHOOK_RATE_LIMIT_*`.

Verification run:

- `python3 -m py_compile python/arclink_hosted_api.py python/arclink_api_auth.py python/arclink_discord.py python/arclink_telegram.py python/arclink_public_bot_commands.py python/arclink_boundary.py python/arclink_provisioning.py python/arclink_memory_synthesizer.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_public_bot_commands.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_memory_synthesizer.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.
- `git diff --check` passed.

Skipped live checks:

- No live Telegram webhook registration, Discord interaction delivery, Stripe
  webhook delivery, deploy, upgrade, Docker install/upgrade, or external
  provider mutation was run; those remain gated by explicit operator
  authorization and real credentials.

Known risks:

- Existing deployed Control Node configs must set `TELEGRAM_WEBHOOK_SECRET`
  before Telegram webhooks will process; this is intentional fail-closed
  behavior.
- Discord replay protection reserves valid interaction IDs before dispatch;
  an internal processing failure marks the row failed and still blocks a later
  duplicate interaction ID.
- Wave 1D unified secret redaction and Wave 1E container privilege/socket
  scope remain open.

## 2026-05-11 Ralphie Wave 3 Teardown Lifecycle Build

Scope: completed the Wave 3 teardown lifecycle and cleanup slice from
`IMPLEMENTATION_PLAN.md` without live host/provider mutation.

Rationale:

- Added an idempotent Sovereign teardown job path for `teardown_requested`,
  retryable `teardown_failed`, and resource-bearing `cancelled` deployments.
  The path runs Compose teardown, tears down persisted DNS, releases active
  placement, reconciles fleet load, clears tailnet service ports, records
  service health, writes events/audit, and transitions the deployment to
  `torn_down`.
- Kept destructive volume removal opt-in only through explicit
  `metadata.teardown.remove_volumes: true`; the default Compose teardown uses
  `down --remove-orphans` and preserves stateful volumes.
- Added executor DNS teardown and Compose lifecycle replay metadata, propagated
  lifecycle transport failures instead of hiding them, cleaned materialized
  local and SSH runtime secret copies after successful Compose operations, and
  validated SSH key paths as regular non-symlink files with private modes.
- Made Compose health reconciliation project-scoped and records transport or
  malformed status failures as failed service health instead of `starting`.
- Preserved provisioned DNS status for unchanged desired tuples, records
  provider DNS ids by hostname when available, and marks DNS rows torn down
  only after provider teardown success.
- Excluded cancelled/torn-down deployments from tailnet port allocation scans
  and suppressed cancelled/torn-down DNS drift rows in the admin dashboard.

Fixed audit IDs:

- `CR-4`, `HI-8`, `HI-9`, `HI-14`, `ME-9`, `ME-10`, `LOW-13`.

Verification run:

- `python3 -m py_compile python/arclink_sovereign_worker.py python/arclink_executor.py python/arclink_ingress.py python/arclink_fleet.py python/arclink_provisioning.py python/arclink_control.py python/arclink_dashboard.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_ingress.py` passed.
- `python3 tests/test_arclink_fleet.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_control_db.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `git diff --check` passed.

Skipped live checks:

- No live Docker host teardown, Cloudflare DNS deletion, Tailscale mutation,
  Stripe/Chutes action, deploy, upgrade, Docker install/upgrade, or production
  service restart was run. Those remain gated by explicit operator
  authorization and real credentials.

Known risks:

- Remote SSH secret cleanup is implemented for the materialized Compose
  `config/secrets` root after successful SSH `up`/`down`, but it has only local
  fake-runner coverage in this pass; live SSH behavior still needs an operator-
  authorized proof window.
- Teardown intentionally does not revoke Chutes/provider credentials yet;
  provider artifact revocation remains a later lifecycle hardening task unless
  the operator explicitly scopes it into the next build slice.
- The full audit is not complete. Wave 4, Wave 5, and any remaining actionable
  FACT/PARTIAL findings remain backlog.

## 2026-05-11 Ralphie Residual Closure Build

Scope: closed the remaining residual closure items from `IMPLEMENTATION_PLAN.md`
without private-state access, live deploys, provider mutations, public bot
mutations, or Hermes core edits.

Fixed and verified:

- `HI-8`: local Docker Compose apply now cleans materialized secret copies in a
  `finally` path after runner failure, and SSH Compose runners clean the remote
  `config/secrets` root after failed sync/compose paths as well as success.
- `ME-14`: memory synthesis prompts now wrap source inventories in explicit
  untrusted-data sentinels, and model outputs containing URLs or executable
  imperatives are rejected from managed recall injection.
- `ME-15`: SSH executor mode now requires explicit machine-mode opt-in plus a
  host allowlist in action-worker and Sovereign provisioning paths.
- `ME-18`: the worker main loop continues to initialize/connect once per worker
  run and reuse that connection for the batch loop; regression coverage locks
  that behavior.
- `LOW-11`: action-worker failures now return and persist safe error codes
  (`executor_error`, `action_validation_error`, etc.) while preserving redacted
  human-readable messages.
- `LOW-12`: evidence ledgers serialize unset record and run timestamps as JSON
  `null` instead of `0.0`, while DB rows keep explicit `not_recorded` state.
- `LOW-14`: operator evidence template readiness is computed from the template
  file and required markers instead of hard-coded `True`.
- `LOW-15`: UTC parsing now normalizes `Z` and offset forms before comparisons;
  Notion claim expiry and notification retry due checks no longer compare mixed
  timestamp strings directly.
- `ME-11` and `ME-25`: left as FICTION/outdated regression awareness per the
  current plan; no active remediation was taken.

Verification run:

- `python3 -m py_compile python/arclink_executor.py python/arclink_memory_synthesizer.py python/arclink_action_worker.py python/arclink_evidence.py python/arclink_dashboard.py python/arclink_control.py python/arclink_notification_delivery.py python/arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_memory_synthesizer.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_evidence.py` passed.
- `python3 tests/test_arclink_control_db.py` passed.
- `python3 tests/test_arclink_notification_delivery.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `git diff --check` passed.

Skipped live gates:

- No live Docker apply/teardown, SSH host mutation, Cloudflare DNS change,
  Tailscale change, Stripe or Chutes mutation, Notion live proof, Telegram or
  Discord webhook mutation, deploy, upgrade, Docker install/upgrade, or
  production service restart was run.

Known risks:

- SSH cleanup and machine-mode allowlisting have local fake-runner and unit
  coverage only; real remote proof still requires an operator-authorized
  maintenance window with disposable credentials/hosts.
- The residual closure is local-code complete. Broad release validation and
  live provider/host proof remain later, explicitly authorized work.

## 2026-05-14 ArcPod Captain Console Waves 0-2 Build Validation

Scope: validated the candidate Wave 0 vocabulary/schema/SOUL foundation, Wave 1
Agent Name and Agent Title onboarding/rename flow, and Wave 2 inventory/ASU
placement work already present in the dirty tree. No private state, live
provider account, payment flow, public bot mutation, deploy, upgrade, or Hermes
core path was touched.

Files changed in this pass:

- `IMPLEMENTATION_PLAN.md`: marked Waves 0-2 locally validated and recorded
  that `python/arclink_users.py` is a stale compile target because the module
  does not exist in this repo.
- `research/BUILD_COMPLETION_NOTES.md`: added this validation record.

Verification run:

- `python3 -m py_compile python/arclink_control.py python/arclink_public_bots.py python/arclink_onboarding.py python/arclink_provisioning.py python/arclink_fleet.py python/arclink_asu.py python/arclink_inventory.py python/arclink_inventory_hetzner.py python/arclink_inventory_linode.py` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_control_db.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_fleet.py` passed.
- `python3 tests/test_arclink_asu.py` passed.
- `python3 tests/test_arclink_inventory_hetzner.py` passed.
- `python3 tests/test_arclink_inventory_linode.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `cd web && npm test` passed.
- `cd web && npm run lint` passed.
- `cd web && npm run test:browser` passed with 45 passing and 3 skipped
  desktop-only-mobile-layout cases.

Skipped live gates:

- No `./deploy.sh install`, `./deploy.sh upgrade`, Docker install/upgrade,
  production restart, live Stripe, Chutes, Hetzner, Linode, Cloudflare,
  Tailscale, Telegram, Discord, or Notion proof was run.

Known risks:

- Waves 0-2 are locally source-validated but remain unproven against live
  infrastructure and real provider credentials.
- Wave 3 Pod migration remains the next implementation wave. The current tree
  has schema foundations, but reprovision/migration execution is not closed by
  this validation pass.

## 2026-05-15 End-To-End Release Readiness Sweep

Scope: exercised the committed ArcPod Captain Console Waves 0-6 work plus the
install/upgrade/runtime hardening discovered during full local smoke. No private
provider credentials, live payment mutation, public bot mutation, remote fleet
host, production deploy, or production upgrade was used.

Corrections made during the sweep:

- Deferred root-side enrollment and Notion-claim provisioning jobs during
  install/upgrade until shared-state ownership and user services are in place.
- Repaired auto-provision token directory ownership before running headless
  `init.sh` as the target user.
- Made dashboard readiness probes use the auth proxy root login path for
  mounted subpaths and report the last observed status/error on timeout.
- Forced UTF-8 locale/Python stdio in generated user-agent service units so
  Hermes dashboard startup is not locale-fragile.
- Hardened the install smoke around `autoprovbot` cleanup, Notion webhook
  install-window arming, loopback source-IP policy, MCP rate-limit semantics,
  synthetic control-plane agent cleanup, and CPU-only qmd embedding backlog.
- Treated stale deleted-user `user@UID.service` failures as resettable health
  noise only when the failed units are exclusively deleted-user managers.

Validation run:

- `git diff --check` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 -m compileall -q python tests` passed.
- `python3 tests/test_arclink_wrapped.py` passed.
- `python3 tests/test_arclink_pod_comms.py` passed.
- `python3 tests/test_arclink_crew_recipes.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_vault_watch_regressions.py` passed.
- `python3 tests/test_arclink_agent_access.py` passed.
- `python3 tests/test_arclink_enrollment_provisioner_regressions.py` passed.
- `python3 tests/test_arclink_agent_user_services.py` passed.
- `python3 tests/test_onboarding_completion_messages.py` passed.
- Full Python sweep passed: `110 Python test files; failures=0`
  (`completion_log/end_to_end_20260515_python_sweep_final.log`).
- `./bin/ci-preflight.sh` passed.
- `cd web && npm test && npm run lint && npm run build && npm run test:browser`
  passed; browser suite reported 45 passed and 3 expected desktop-only skips.
- `./test.sh` passed end-to-end
  (`completion_log/end_to_end_20260515_test_sh_final20.log`): install smoke
  completed successfully, health ended at 68 ok / 5 warn / 0 fail, and teardown
  removed both `arclink` and `autoprovbot`.

Expected non-blocking warnings observed:

- The smoke install intentionally leaves `BACKUP_GIT_REMOTE` empty.
- Shared Notion SSOT live write proof is skipped when Notion is not configured.
- The upgrade-check notification dedup path skips the network-dependent branch
  when upstream lookup is unavailable.
- qmd reports CPU-only embedding warnings on hosts without GPU acceleration;
  text indexing and MCP search were proven, and embedding retry is deferred.
- The smoke deliberately creates malformed `.vault` fixtures to prove warning
  paths; teardown removes the smoke state.

Residual gates:

- Live external/provider proof remains operator-gated: real Stripe checkout and
  webhooks, Chutes provider mutation, Cloudflare DNS, Tailscale publication,
  Telegram/Discord webhook delivery, Notion SSOT writes, remote SSH fleet
  placement/migration, and production deploy/upgrade still require explicit
  live credentials and an authorized maintenance window.

## 2026-05-16 Sovereign Fleet Phase 0/1 Build Pass

Scope:

- Implemented the first Wave 1 fleet plan tasks from `IMPLEMENTATION_PLAN.md`:
  Phase 0 additive fleet schema foundations and orphan reporting, plus Phase 1
  placement-aware action-worker routing.
- Did not touch private state, live secrets, provider/payment mutations,
  production deploys, public bot command registration, Docker install/upgrade,
  or Hermes core.

Files changed:

- `python/arclink_control.py`: added fleet enrollment/probe/audit-chain tables,
  additive inventory/host columns, indexes, and drift/status checks.
- `python/arclink_fleet.py`: added non-destructive inventory/host orphan
  reconciler with operator audit entries.
- `python/arclink_executor.py`: added shared per-host executor construction and
  SSH key validation for fleet workers.
- `python/arclink_sovereign_worker.py`: routed provisioning host executor
  construction through the shared helper.
- `python/arclink_action_worker.py`: resolved deployment active placement
  before dispatch, cached per-host executors by `(host_id, adapter)`, preserved
  injected/static fallback behavior, and wrote routing metadata to attempt
  audit/event records.
- Tests updated in `tests/test_arclink_schema.py`, `tests/test_arclink_fleet.py`,
  `tests/test_arclink_executor.py`, `tests/test_arclink_action_worker.py`, and
  `tests/test_arclink_discord.py`.
- `IMPLEMENTATION_PLAN.md`: restored the domain-or-Tailscale ingress live-gate
  wording expected by Docker regression coverage.

Validation run:

- `python3 -m py_compile python/arclink_control.py python/arclink_fleet.py python/arclink_inventory.py python/arclink_executor.py python/arclink_sovereign_worker.py python/arclink_action_worker.py` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_fleet.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed.
- Audit regression gate passed:
  `python3 tests/test_arclink_telegram.py`,
  `python3 tests/test_arclink_discord.py`,
  `python3 tests/test_arclink_hosted_api.py`,
  `python3 tests/test_arclink_api_auth.py`,
  `python3 tests/test_arclink_secrets_regex.py`, and
  `python3 tests/test_arclink_docker.py`.
- `git diff --check` passed.

Skipped live gates:

- No live non-loopback SSH, cloud-provider provisioning, payment/provider
  mutation, public bot mutation, Docker install/upgrade, production deploy,
  production upgrade, Notion, Cloudflare, or Tailscale proof was run.

Known risks:

- Phase 2 enrollment mint/callback/audit-chain write helpers are not implemented
  yet; this pass only lands their additive schema and drift foundations.
- Phase 4 periodic probing and fleet health summary remain pending, so the new
  probe table is not populated by a daemon yet.
- Phase 7 two-host live proof remains operator-gated; fleet readiness is not
  claimed by this pass.

## 2026-05-16 Sovereign Fleet Phase 2 Follow-Through Build Pass

Scope:

- Extended the existing fleet enrollment/audit-chain slice with operator-facing
  health verification, expiry notification, and explicit re-attestation.
- Preserved the existing `deploy.sh control ...` surface and did not touch
  private state, live secrets, provider/payment mutations, production deploys,
  Docker install/upgrade, or Hermes core.
- Rationale: this pass kept health verification in the existing inventory CLI
  instead of adding a separate binary or daemon, because Phase 4 owns periodic
  probing and the canonical operator surface remains `deploy.sh control ...`.

Files changed:

- `python/arclink_fleet_enrollment.py`: added notification-aware pending-token
  expiry and explicit inventory-machine re-attestation that updates the stored
  fingerprint, appends a `re-attested` chain event, and avoids rendering
  fingerprint material in command output or audit metadata.
- `python/arclink_inventory.py`: added `fleet_inventory_health()` with
  audit-chain verification, enrollment expiry cleanup, host/inventory counts,
  capacity, probe SLI fields, and JSON CLI support for `health`; added
  `re-attest` CLI dispatch.
- `bin/deploy.sh`: exposed `deploy.sh control inventory health --json` and
  `deploy.sh control inventory re-attest ...` plus shortcut aliases.
- `tests/test_arclink_fleet_enrollment.py` and
  `tests/test_deploy_regressions.py`: covered health expiry notification,
  audit-chain verification, re-attestation, and deploy command routing.
- `IMPLEMENTATION_PLAN.md`: updated Phase 2 status to leave only enrollment
  HMAC-root rotation UX as remaining follow-through.

Validation run:

- `python3 tests/test_arclink_fleet_enrollment.py` passed.
- `python3 tests/test_arclink_fleet.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 -m py_compile python/arclink_fleet_enrollment.py python/arclink_inventory.py python/arclink_hosted_api.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `git diff --check` passed.

Skipped live gates:

- No live non-loopback SSH, cloud-provider provisioning, payment/provider
  mutation, public bot mutation, Docker install/upgrade, production deploy,
  production upgrade, Notion, Cloudflare, Tailscale, or two-host proof was run.

Known risks:

- Enrollment HMAC-root rotation UX is closed by the later 2026-05-16 HMAC
  rotation entry above.
- Phase 3 worker join/probe wrapper, Phase 4 periodic inventory worker, Phase 6
  provider provisioning, and Phase 7 live two-host proof remain unimplemented or
  operator-gated, so fleet readiness is not claimed by this pass.

## 2026-05-16 Sovereign Fleet Phase 8 Control-Prereq Build Slice

Scope:

- Added the shared prerequisite auto-installation library and wired it into
  `deploy.sh control install|upgrade` before Docker Compose bootstrap/build.
- Preserved the existing Shared Host Docker install/upgrade flows and did not
  run live Docker installation, production deploys, remote SSH, provider calls,
  or private-state mutations.
- Rationale: the prereq behavior lives in `bin/lib/ensure-prereqs.sh` instead
  of inline `deploy.sh` snippets so the future worker join script and
  provider-bootstrap paths can reuse the same apt/dnf/Docker/check-only logic.

Files changed:

- `bin/lib/ensure-prereqs.sh`: added apt/dnf prerequisite detection and
  installation, Docker Engine/Compose installation via `https://get.docker.com`,
  `--skip-prereq-install`/verify-only behavior, JSON output, optional Python
  package checks, and JSONL audit entries.
- `bin/deploy.sh`: routed Control Node install/upgrade through the prereq
  library and documented `deploy.sh control install --skip-prereq-install`.
- `tests/test_deploy_regressions.py`: added fake-system tests for no-op ready
  hosts, verify-only missing-prereq planning, fake apt/get.docker.com install
  flow, audit output, and deploy wiring.
- `IMPLEMENTATION_PLAN.md`: marked Phase 8 as partially landed for the Control
  Node path while keeping worker/provider follow-through pending.

Validation run:

- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_arclink_fleet_enrollment.py` passed.
- `bash -n deploy.sh bin/*.sh bin/lib/*.sh test.sh` passed.
- `git diff --check` passed.

Skipped validation:

- `shellcheck bin/lib/ensure-prereqs.sh` was not run because `shellcheck` is
  not installed in this environment.
- No live prerequisite installation, Docker install/upgrade, non-loopback SSH,
  cloud-provider provisioning, payment/provider mutation, public bot mutation,
  production deploy, production upgrade, Notion, Cloudflare, Tailscale, or
  two-host proof was run.

Known risks:

- Phase 8 worker join wiring and provider-bootstrap reuse remain pending.
- The Control Node prereq installer is fake-tested only; live clean-host proof
  remains operator-gated.
- Phase 3 worker join/probe wrapper, Phase 4 periodic inventory worker, Phase 6
  provider provisioning, and Phase 7 live two-host proof remain open, so fleet
  readiness is not claimed by this pass.

## 2026-05-16 Sovereign Fleet Phase 3 Worker-Join Build Slice

Scope:

- Added a manual worker bootstrap script and a pull-probe wrapper for the
  Sovereign fleet path.
- Preserved existing enrollment callback semantics and did not run live
  non-loopback SSH, production deploys, Docker install/upgrade, provider calls,
  payment/provider mutations, public bot mutations, or private-state reads.
- Rationale: token input is limited to file/stdin and callback posting is done
  inside Python with the token read from stdin, so enrollment token material is
  not placed in command argv or persisted by ArcLink.

Files changed:

- `bin/arclink-fleet-join.sh`: added idempotent worker-local setup for the
  service/SSH user, authorized key, state root, probe wrapper, Docker-group
  membership, machine fingerprint, prereq audit summary, and enrollment
  callback; failures leave `admission.state` disabled.
- `bin/arclink-fleet-probe-wrapper`: added strict allowlisted
  `liveness`, `capacity`, and `inventory` JSON probes.
- `tests/test_arclink_fleet_join.py`: added fake-root regression coverage for
  token boundary rejection, idempotency/no token persistence, callback-failure
  non-admission, and probe allowlisting.
- `IMPLEMENTATION_PLAN.md`: recorded the Phase 3 local slice as implemented
  while keeping live proof and later daemon/provider work open.

Validation run:

- `python3 tests/test_arclink_fleet_join.py` passed.
- `python3 tests/test_arclink_fleet_enrollment.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_secrets_regex.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_arclink_fleet.py` passed.
- `python3 tests/test_arclink_action_worker.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed.
- `python3 -m py_compile python/arclink_fleet_enrollment.py python/arclink_inventory.py python/arclink_hosted_api.py` passed.
- `bash -n deploy.sh bin/*.sh bin/lib/*.sh bin/arclink-fleet-probe-wrapper test.sh` passed.
- `git diff --check` passed.

Skipped validation:

- `shellcheck bin/arclink-fleet-join.sh bin/arclink-fleet-probe-wrapper bin/lib/ensure-prereqs.sh` was not run because `shellcheck` is not installed in this environment.

Known risks:

- The worker join path is fake-root tested only; clean-host live bootstrap is
  still Phase 7 operator-gated.
- The installed SSH key is not forced to the probe wrapper because current
  day-2 SSH executor paths still share the worker SSH lane; a separate probe
  key remains a deferred hardening item.
- Phase 4 inventory daemon, Phase 6 provider provisioning, and Phase 7 live
  two-host proof remain open, so fleet readiness is not claimed.

## 2026-05-16 Sovereign Fleet Phase 4 Inventory Worker Build Slice

Scope:

- Added the pull-based inventory worker daemon slice for the Sovereign fleet
  path and kept all proof local/fake-runner only.
- Did not run live non-loopback SSH, production deploys, Docker
  install/upgrade, provider calls, payment/provider mutations, public bot
  mutations, private-state reads, or two-host proof.
- Rationale: the worker keeps the existing control-plane pull model over SSH
  and uses the worker-local allowlisted probe wrapper instead of introducing a
  worker-pushed heartbeat service.

Files changed:

- `python/arclink_fleet_inventory_worker.py`: added due-probe scheduling,
  SSH probe runner, redacted probe persistence, liveness thresholds
  (3 failures degraded, 10 failures unreachable/offline), recovery handling,
  linked inventory capacity/health updates, operator notifications, and probe
  retention pruning.
- `python/arclink_inventory.py`: surfaced fleet host health states in
  `inventory health` and added `probe-all` to force a worker probe pass.
- `bin/deploy.sh`: exposed `deploy.sh control inventory probe-all --json` and
  the matching shortcut alias.
- `compose.yaml`: added a `fleet-inventory-worker` job-loop service without a
  Docker socket mount.
- `tests/test_arclink_fleet_inventory_worker.py`: added fake-runner coverage
  for cadences, capacity updates, thresholds, recovery, redaction, and pruning.
- `tests/test_arclink_docker.py`: asserted the new service exists and does not
  broaden Docker socket access.
- `IMPLEMENTATION_PLAN.md`: recorded the Phase 4 local slice and the remaining
  live/dashboard follow-through.

Validation run:

- `python3 tests/test_arclink_fleet_inventory_worker.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_arclink_fleet.py` passed.
- `python3 tests/test_arclink_fleet_enrollment.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_secrets_regex.py` passed.
- `python3 tests/test_arclink_telegram.py` passed.
- `python3 tests/test_arclink_discord.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 -m py_compile python/arclink_fleet_inventory_worker.py python/arclink_inventory.py python/arclink_control.py python/arclink_fleet.py python/arclink_fleet_enrollment.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `git diff --check` passed.

Skipped validation:

- `shellcheck bin/arclink-fleet-join.sh bin/arclink-fleet-probe-wrapper bin/lib/ensure-prereqs.sh` was not run because `shellcheck` is not installed in this environment.

Known risks:

- The worker's SSH path is fake-tested only; live remote probe proof remains
  Phase 7 operator-gated.
- Dashboard-specific fleet health aggregation beyond the CLI health summary is
  still pending.
- Phase 6 provider provisioning and Phase 7 live two-host proof remain open,
  so fleet readiness is not claimed.

## 2026-05-16 ArcLink LLM Router Phase 3 Preflight Enforcement Build Slice

Scope:

- Implemented the router policy gate before upstream forwarding: JSON/body
  caps, model allowlist, billing and budget boundary evaluation, per-key /
  deployment / Captain rate limits, deployment concurrency checks, and budget
  reservations with release on handled responses.
- Kept the relay boundary intentionally preflight-only. Non-streaming and
  streaming Chutes forwarding remain Phase 4 so live/provider behavior is not
  mixed into the policy slice.
- Rationale: reusing `evaluate_chutes_deployment_boundary`,
  `rate_limits`, and SQLite reservation rows keeps the trust boundary local to
  the Control Node without introducing Redis/Postgres or a new gateway layer.

Files changed:

- `python/arclink_llm_router.py`: added Phase 3 router config, request parsing,
  policy/budget/rate/concurrency preflight, reservation creation, and release.
- `tests/test_arclink_llm_router.py`: added focused regression coverage for
  invalid model, request limits, missing/exhausted budget, past-due billing,
  rate limiting, concurrency limiting, and reservation cleanup.
- `IMPLEMENTATION_PLAN.md`: marked Phase 3 policy enforcement tasks and
  validation criteria complete.

Validation run:

- `git diff --check` passed.
- `python3 -m py_compile python/arclink_llm_router.py python/arclink_chutes.py python/arclink_control.py python/arclink_provisioning.py python/arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_llm_router.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed.
- `python3 tests/test_arclink_hosted_api.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.

Known risks:

- Phase 4 forwarding, streaming passthrough, usage settlement, Chutes metadata
  ingestion, and upstream error redaction are still open.
- The current reservation is released around the placeholder `501` response;
  actual settlement must replace that path when upstream relay lands.

## 2026-05-17 LLM Router Hardening And Production Validation Prep

Scope: closed the remaining local hardening gaps from the LLM Router/refueling
audit before production deploy. No private state was read, no live provider
mutation was run during source validation, and the unrelated `mission_status.md`
worktree file was left untouched.

Files changed:

- `python/arclink_control.py`: router key rows now store
  `hmac-sha256$...` keyed digests using `ARCLINK_LLM_ROUTER_KEY_HASH_PEPPER`
  or the session pepper fallback. Legacy SHA-256 router-key rows are accepted
  only on successful verification and are migrated to HMAC immediately.
- `python/arclink_llm_router.py`: low-fuel Raven notices no longer write the
  `llm_router:arc_pod_fuel_notice_queued` dedupe event when no public Captain
  channel exists, so a later channel repair can still queue the real warning.
- `tests/test_arclink_llm_router.py`: added regression coverage for
  no-channel notice recovery and router-key HMAC storage/legacy migration.
- `compose.yaml` and `docs/arclink/llm-router.md`: documented and exposed the
  optional router-key pepper.
- `IMPLEMENTATION_PLAN.md` and `research/PRODUCT_REALITY_MATRIX.md`: removed
  current drift around dirty-tree wording, deferred HMAC language, and old
  Refuel Pod naming in favor of ArcPod Refueling / ArcPod fuel.

Validation run:

- `python3 tests/test_arclink_llm_router.py` passed, 16/16.
- `python3 tests/test_arclink_control_db.py` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_sovereign_worker.py` passed, 17/17.
- `python3 tests/test_arclink_docker.py` passed, 16/16.
- `python3 tests/test_arclink_entitlements.py` passed, 25/25.
- `python3 tests/test_arclink_hosted_api.py` passed, 76/76.
- `python3 tests/test_arclink_public_bots.py` passed, 31/31.
- `python3 tests/test_arclink_notification_delivery.py` passed, 14/14.
- `python3 tests/test_documentation_truths.py` passed, 6/6.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_llm_router.py`
  passed.
- `bash -n deploy.sh bin/*.sh bin/lib/*.sh test.sh` passed.
- `git diff --check` passed.
- `./bin/ci-preflight.sh` passed.
- `cd web && npm test && npm run lint && npm run build && npm run test:browser`
  passed, including 69 Node tests and 45 Playwright tests with 3 documented
  desktop-only mobile-layout skips.

Skipped live gates:

- No live Chutes inference, Stripe purchase, provider-balance transfer,
  production deploy, or agent-message proof was run in this source-validation
  pass. Those are the next operator-authorized steps after commit/push/deploy.

## 2026-05-17 LLM Router Production Cutover Repair

Scope: closed the production cutover gap found during live deploy verification.
The `control-llm-router` service came up but reported `configured=false`
because the existing central Chutes credential was present as `CHUTES_API_KEY`
while the router-specific key was absent. Existing active ArcPods also still
had direct Chutes env because they predated the router cutover.

Files changed:

- `bin/deploy.sh` and `bin/docker-entrypoint.sh`: preserve/write
  `ARCLINK_LLM_ROUTER_CHUTES_API_KEY`, defaulting it from the already collected
  central `CHUTES_API_KEY` when the router-specific value is absent.
- `python/arclink_action_worker.py`: deployment-target action executors now use
  deployment-scoped secret stores instead of host-scoped stores, and
  reprovision passes the worker env through to Pod migration.
- `python/arclink_pod_migration.py`: live reprovision now registers the
  rendered ArcPod router key before applying the refreshed Compose intent, using
  the same generated-secret store layout as the Sovereign worker.
- `tests/test_arclink_action_worker.py`: reprovision coverage asserts the
  router key row is registered with a keyed HMAC digest.

Validation run:

- `python3 tests/test_arclink_action_worker.py` passed, 32/32.
- `python3 tests/test_arclink_llm_router.py` passed, 16/16.
- `python3 tests/test_arclink_sovereign_worker.py` passed, 17/17.
- `python3 tests/test_arclink_provisioning.py` passed, 13/13.
- `python3 tests/test_arclink_docker.py` passed, 16/16.
- `python3 tests/test_deploy_regressions.py` passed, 115/115 with 2 documented
  root-environment skips.
- `python3 tests/test_documentation_truths.py` passed, 6/6.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_action_worker.py python/arclink_pod_migration.py python/arclink_control.py python/arclink_llm_router.py` passed.
- `bash -n deploy.sh bin/*.sh bin/lib/*.sh test.sh` passed.
- `git diff --check` passed.

Live follow-up required after deploy:

- Re-run Control Node upgrade/recreate so the router-specific env reaches the
  router service.
- Reprovision or migrate pre-router active ArcPods so their Hermes gateway env
  moves from direct Chutes to the central router.

## 2026-05-17 Pod Migration Root-Owned State Repair

Scope: live reprovision of the two existing ArcPods exposed that
`control-action-worker` could stop the source stack but could not stage
root-owned Nextcloud/Redis bind-mount files while running as the unprivileged
`arclink` user. The worker already has writeable Docker socket access and is
therefore a trusted-host service; this pass makes that root boundary explicit
instead of letting migrations fail midway on service-owned state.

Files changed:

- `compose.yaml`: `control-action-worker` now runs as `user: "0:0"` with a
  comment explaining the Docker-socket plus migration-capture trust boundary.
- `docs/docker.md` and `docs/arclink/data-safety.md`: document that
  `control-action-worker` is root inside the container for Pod migration
  capture of root-owned bind mounts.

Validation:

- Pending in this pass: focused Compose/docs regression tests, shell syntax,
  redeploy, and live reprovision retry of the two active ArcPods.

## 2026-05-17 Compose Secret Materialization Host-Path Repair

Scope: the root-owned state repair allowed live reprovision to stage the source
tree, but Compose apply then failed because the action-worker resolver had
materialized secrets under the container-local `/tmp/arclink-action-worker`
path. Docker Compose evaluates secret file paths from the host daemon, so that
path was not visible to the daemon.

Files changed:

- `python/arclink_executor.py`: live Compose apply now copies every resolved
  secret into the deployment config's durable `config/secrets/` directory and
  writes the Compose secret file path to that host-visible location. On runner
  failure it cleans both the compose-visible copy and the resolver's temporary
  materialization path.
- `tests/test_arclink_executor.py`: live secret persistence coverage now
  asserts the host-visible `config/secrets/<name>` copy exists, has `0600`
  permissions, and is the path written into the Compose file.

Validation:

- `python3 tests/test_arclink_executor.py` passed, 34/34.
- `python3 tests/test_arclink_action_worker.py` passed, 32/32.
- `python3 tests/test_arclink_provisioning.py` passed, 13/13.
- `python3 -m py_compile python/arclink_executor.py python/arclink_action_worker.py python/arclink_pod_migration.py python/arclink_control.py python/arclink_llm_router.py` passed.
- `bash -n deploy.sh bin/*.sh bin/lib/*.sh test.sh` passed.
- `git diff --check` passed.

Live follow-up required after deploy:

- Re-run Control Node upgrade/recreate so the host-visible Compose secret
  materialization reaches `control-action-worker`.
- Retry live reprovision of the two active ArcPods and confirm their Hermes
  gateway env now points at the central LLM router.

## 2026-05-17 Rolled-Back Pod Migration Capture Cleanup

Scope: live router cutover retries produced rolled-back migration captures
while exercising failure paths. Successful migrations intentionally retain their
captures until the retention window expires, but rolled-back attempts do not
need to keep copied service state after source restart/target teardown has
completed.

Files changed:

- `python/arclink_pod_migration.py`: `_mark_rollback` now removes safe
  `.migrations/<migration_id>` capture directories, records
  `capture_cleanup` metadata, and marks `source_garbage_collected_at` when the
  cleanup succeeds or the directory is already gone.
- `tests/test_arclink_pod_migration.py`: rollback coverage now asserts capture
  cleanup for both cross-host migration rollback and in-place reprovision
  rollback.

Validation:

- `python3 tests/test_arclink_pod_migration.py` passed, 5/5.
- `python3 tests/test_arclink_action_worker.py` passed, 32/32.
- `python3 -m py_compile python/arclink_pod_migration.py python/arclink_action_worker.py python/arclink_executor.py` passed.
- `bash -n deploy.sh bin/*.sh bin/lib/*.sh test.sh` passed.
- `git diff --check` passed.

Live follow-up required after deploy:

- Re-run Control Node upgrade/recreate if this cleanup behavior is promoted
  immediately.
- Remove old rolled-back capture directories from the live router-cutover
  attempts and mark those rows collected.

## 2026-05-20 GAP-019-D Curator Refresh Socket Removal

Scope: local Docker authority hardening. Source review showed
`curator-refresh` performs refresh/detection work, while queued Docker-mode
operator upgrade execution is routed through the enrollment provisioner path.
The repair removes unnecessary host Docker socket authority from the refresh
loop instead of adding a softer command guard.

Files changed:

- `compose.yaml`: removed the Docker socket mount and socket group from
  `curator-refresh`.
- `config/docker-authority-inventory.json` and `tests/test_arclink_docker.py`:
  recorded `GAP-019-D`, removed `curator-refresh` from the socket/root authority
  set, and asserted it stays socket-free.
- `docs/docker.md`, `docs/arclink/data-safety.md`,
  `docs/arclink/operations-runbook.md`, `GAPS.md`, `USER_JOURNEY.md`, and
  `IMPLEMENTATION_PLAN.md`: documented the reduced authority and kept the
  remaining trusted-host Docker socket boundary open.

Validation:

- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed: 17 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20` passed: 41 tests.
- `python3 tests/test_documentation_truths.py` passed: 7 tests.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1217 passed, 6 skipped.

Residual risk:

- `GAP-019` remains open for `control-provisioner`,
  `control-action-worker`, `agent-supervisor`, and `notification-delivery`
  direct Docker socket authority until broker/helper splits land or the
  operator accepts the residual risk.

## 2026-05-21 GAP-019-O Agent User Helper Split

Scope: local Docker authority hardening. Source review showed
`agent-supervisor` still directly owned Docker-mode container-local user/home
setup. The repair moves that root operation into a tokened
`agent-user-helper` while keeping `GAP-019` open for helper/process-runner and
socket-broker residual risk.

Files changed:

- `python/arclink_agent_user_helper.py`: added a root helper that rejects raw
  command fields, accepts only `ensure_user_home`, validates agent id, Unix
  user, Docker agent-home root, agent home, Hermes home, and workspace path,
  then performs container-local user creation, persistent numeric uid/gid
  assignment, and ownership repair.
- `python/arclink_docker_agent_supervisor.py`: user/home setup now fails closed
  without `ARCLINK_AGENT_USER_HELPER_URL` and token, and the supervisor no
  longer contains direct `useradd`, recursive `chown`, or workspace `os.chown`
  calls. Agent process launch now uses `setpriv` with the helper-assigned
  numeric uid/gid so it does not depend on cross-container passwd entries.
- `compose.yaml`, `bin/arclink-docker.sh`, `bin/docker-entrypoint.sh`, and
  `bin/deploy.sh`: added `agent-user-helper` and its Docker runtime token
  wiring without adding Docker socket access.
- `config/docker-authority-inventory.json`, `docs/docker.md`,
  `docs/arclink/data-safety.md`, `docs/arclink/operations-runbook.md`,
  `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md`: recorded `GAP-019-O` as local hardening, not P0
  closure.
- `tests/test_arclink_docker.py` and `tests/test_deploy_regressions.py`:
  added helper contract, supervisor fail-closed, Compose/inventory, and token
  bootstrap assertions.

Validation:

- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_user_helper_rejects_raw_commands_and_unscoped_paths tests/test_arclink_docker.py::test_docker_agent_supervisor_rejects_unsafe_metadata_before_root_ops tests/test_arclink_docker.py::test_docker_agent_supervisor_requires_user_helper_before_root_user_ops tests/test_arclink_docker.py::test_docker_agent_supervisor_replaces_user_systemd_units tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary --maxfail=1`
  passed: 5 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed: 23 tests.
- `python3 -m pytest -q tests/test_deploy_regressions.py::test_control_docker_bootstrap_seeds_session_hash_pepper_and_gateway_broker_token --maxfail=1`
  passed: 1 test.
- `python3 -m py_compile python/arclink_docker_agent_supervisor.py python/arclink_agent_user_helper.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 tests/test_documentation_truths.py` passed: 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1253 passed, 6 skipped, 81 warnings in
  63.00s.

Residual risk:

- `GAP-019` remains open for `agent-user-helper` root authority over Docker
  agent homes, `agent-supervisor` setpriv process-runner root authority, the
  migration-capture helper root boundary, writeable socket brokers, stronger
  isolation, and operator residual-risk acceptance.

## 2026-05-22 GAP-019-AA Deployment Exec Broker Env Narrowing

Scope: local Docker authority hardening. The focused repro showed
`deployment-exec-broker` still inherited broad `*arclink-env` values even
though the broker only needs token/listener settings, `ARCLINK_STATE_ROOT_BASE`,
optional Docker binary selection, the deployment state-root bind, and the
writeable Docker socket to reconstruct allowlisted deployment Compose
operations.

Files changed:

- `compose.yaml`: removed broad `*arclink-env` inheritance from
  `deployment-exec-broker` and left an explicit minimal environment.
- `tests/test_arclink_docker.py` and
  `config/docker-authority-inventory.json`: added `GAP-019-AA` service-boundary
  coverage and inventory metadata for the deployment broker.
- `docs/docker.md`, `docs/arclink/data-safety.md`,
  `docs/arclink/operations-runbook.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: recorded the local
  hardening while keeping `GAP-019` open for writeable Docker socket residual
  risk and operator policy.

Validation:

- Focused repro passed post-repair:
  `inherits_broad_arclink_env=False`, `inherits_control_secret_env=False`,
  `has_deployment_state_root_bind=True`, `mounts_global_container_secrets=False`,
  `has_docker_socket=True`, `has_cap_drop_all=True`.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'deployment_exec_broker or authority_inventory or compose'`
  passed: 7 passed, 29 deselected.
- `python3 -m pytest -q tests/test_arclink_executor.py -k 'deployment_exec_broker or local_executor_uses_deployment_exec_broker'`
  passed: 2 passed, 37 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  36 tests.
- `python3 -m pytest -q tests/test_arclink_executor.py --maxfail=20` passed:
  39 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1266 passed, 6 skipped, 81 warnings in
  63.58s.

Residual risk:

- `deployment-exec-broker` still intentionally mounts the writeable Docker
  socket for local deployment Compose operations. `GAP-019` remains open until
  the operator accepts that trusted-host residual risk or replaces it with
  stronger isolation.

## 2026-05-22 GAP-019-AB Operator Upgrade Broker Env And Mount Narrowing

Scope: local Docker authority hardening. The focused repro showed
`operator-upgrade-broker` still inherited broad `*arclink-env`, mounted broad
canonical private config/state plus `arclink-priv/secrets/container`, and used
`os.environ.copy()` when building env for allowlisted upgrade subprocesses.

Files changed:

- `compose.yaml`: removed broad env inheritance and broad canonical private
  config/state/secrets mounts from `operator-upgrade-broker`, while preserving
  the explicit writeable Docker socket and writable host repo exception.
- `python/arclink_operator_upgrade_broker.py`: replaced child-process full-env
  inheritance with an explicit allowlist and mapped canonical operator log
  paths to the host private bind used by real Docker-mode upgrades.
- `tests/test_arclink_docker.py` and
  `config/docker-authority-inventory.json`: added `GAP-019-AB` Compose,
  inventory, child-env, and residual-risk coverage.
- `docs/docker.md`, `docs/arclink/data-safety.md`,
  `docs/arclink/operations-runbook.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: recorded the local
  hardening while keeping `GAP-019` open.

Validation:

- Focused repro passed post-repair:
  `inherits_broad_arclink_env=False`, `mounts_private_config=False`,
  `mounts_private_state=False`, `mounts_global_container_secrets=False`,
  `has_writable_host_repo_bind=True`, `has_docker_socket=True`,
  `has_cap_drop_all=True`, `operator_env_copies_process_env=False`, and
  `operator_env_has_child_allowlist=True`.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'operator_upgrade_broker or authority_inventory or compose' --maxfail=5`
  passed: 10 passed, 27 deselected.
- `python3 -m pytest -q tests/test_arclink_enrollment_provisioner_regressions.py -k 'operator_upgrade_broker or host_upgrade or pin_upgrade' --maxfail=5`
  passed: 6 passed, 20 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  37 tests.
- `python3 -m pytest -q tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
  passed: 26 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1267 passed, 6 skipped, 81 warnings in
  63.35s.

Residual risk:

- `operator-upgrade-broker` still intentionally mounts the writeable Docker
  socket and writable host repo bind for queued Docker-mode upgrades. That host
  repo bind can reach nested private state needed for real upgrades, so
  `GAP-019` remains open until the operator accepts the trusted-host residual
  risk or replaces it with stronger isolation.

## 2026-05-22 GAP-019-AF Agent Supervisor Broker Docker CLI Lookup Hardening

Scope: local Docker authority hardening. The focused repro showed
`agent-supervisor-broker` accepted `ARCLINK_DOCKER_BINARY=bash`, then
reconstructed dashboard network operations using `bash` as the executable while
returning success.

Files changed:

- `python/arclink_agent_supervisor_broker.py`: added trusted Docker CLI path
  resolution for dashboard sidecar operations. The broker now accepts only
  `docker` resolved to a trusted executable path or a trusted absolute Docker
  CLI path, and fails before `subprocess.run` for unsafe, missing,
  non-executable, or non-Docker values.
- `tests/test_arclink_docker.py`: added fail-closed coverage for unsafe/missing
  Docker CLI configuration and updated the trusted-path dashboard proxy
  contract.
- `config/docker-authority-inventory.json`: recorded `GAP-019-AF` as an
  executable-lookup hardening slice while keeping the broker's writeable Docker
  socket residual risk open.
- `docs/docker.md`, `docs/arclink/data-safety.md`,
  `docs/arclink/operations-runbook.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `mission_status.md`: recorded the local
  hardening without claiming `GAP-019` closure or live proof.

Validation:

- Pre-repair repro returned `ok=True` with `executables=['bash', 'bash']`.
- Post-repair repro returned `ok=False` with `executables=[]`.
- `python3 -m py_compile python/arclink_agent_supervisor_broker.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_supervisor_broker or authority_inventory or compose' --maxfail=5`
  passed: 11 passed, 29 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  40 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1271 passed, 6 skipped, 81 warnings in
  63.26s.

Residual risk:

- `agent-supervisor-broker` still intentionally mounts the writeable Docker
  socket for dashboard network/proxy sidecar operations. `GAP-019` remains
  open until the operator accepts that trusted-host residual risk or replaces
  it with stronger isolation.

## 2026-05-27 Sovereign Control Node Symphony And Operator Prompt Repair

Scope: source-grounded product traversal and bounded deploy prompt repair for
the Sovereign Control Node path. The sweep treated Shared Host and Shared Host
Docker as maintained substrates, but focused the product trajectory on the
paid Control Node path.

Files changed:

- `docs/arclink/sovereign-control-node-symphony.md`: added the long-form
  Control Node target score covering install, Operator Raven, Captains,
  sharing, experience, inference, Pods/isolation, slash menus, dashboard
  plugins, skills, knowledge/memory, updates, billing, fleet, recovery, and
  governance.
- `bin/deploy.sh`: Control Node install now asks for operator Raven enabled
  channels, primary response channel, primary operator chat/channel ID, and
  Telegram operator allowlist hints, with warnings when selected chat lanes are
  missing bot credentials. It also collects and persists router model policy,
  encourages provider-side fallback CSV strings, prevents workerless installs
  from looking product-ready, and re-enables the provisioner only after remote
  worker registration smoke passes. Install, reconfigure, and worker
  registration now print a provisioning readiness summary.
- `python/arclink_llm_router.py`: added non-streaming chat fallback retries for
  configured retryable provider statuses and fallback models, while preserving
  prompt/secret non-storage and recording the final fallback model in usage.
- `tests/test_deploy_regressions.py`: added source assertions that the
  Sovereign install flow exposes the operator Raven channel prompts.
- `README.md` and `USER_JOURNEY.md`: linked the Control Node symphony from the
  front-door docs.
- `GAPS.md`, `research/COVERAGE_MATRIX.md`, and `IMPLEMENTATION_PLAN.md`:
  added and mapped `GAP-029` through `GAP-033` for the remaining Control Node
  dream gaps: full-service Operator Raven, worker-capacity readiness, router
  fallback cascade, rolling ArcPod/Hermes updates, and cross-surface experience
  proof.

Validation:

- `bash -n deploy.sh bin/deploy.sh` passed.
- `python3 -m py_compile python/arclink_llm_router.py` passed.
- `python3 tests/test_arclink_llm_router.py` passed: 18 tests.
- `python3 tests/test_deploy_regressions.py` passed: 115 tests.
- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.

Residual risk:

- The new document is a target score, not launch certification. `GAP-029`
  through `GAP-033` stay open until their product, policy, local-test, and live
  proof requirements are implemented. The prompt/guard repairs make operator
  channel intent, router model policy, and workerless provisioning state
  explicit during install; they do not create the full Operator Raven control
  plane, streaming fallback semantics, live provider fallback proof, or rolling
  ArcPod updates.
