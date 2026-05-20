# ArcLink Gap Register

This register was regenerated from source evidence, not from the prior root
stub or the product matrix. `research/PRODUCT_REALITY_MATRIX.md` claims
101 `real`, 0 `partial`, and 0 `gap` rows (`research/PRODUCT_REALITY_MATRIX.md:19-20`).
This audit treats that as disproven where local source evidence is thin,
contradicted, partial, policy-question, or proof-gated.

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
  proof-gated, `GAP-019` marks Docker socket/root access as a P0 trusted-host
  boundary requiring security hardening and monitoring decisions, and
  `GAP-025` blocks any claim that the current checkout has a green broad local
  release suite.
- Core journey blockers: `GAP-002` through `GAP-008`, `GAP-011`, and `GAP-018`
  affect payment, bots, provisioning, Hermes workspace proof, provider policy,
  Notion setup truth, public API contract, current-status docs, and admin live
  side effects.
- Planning backlog: P2/P3 rows cover browser token storage, web channel copy,
  backup setup, share UI and no-channel waits, linked copy policy, migration,
  restore proof, cloud fleet proof, Crew Training generation, selected-agent
  streaming, and provider self-service clarity.
- Policy gates: provider self-service, provider account lifecycle, threshold
  behavior, Captain migration, browser share-link broker, linked copy behavior,
  backup automation, and destructive teardown authority need operator decisions
  before code should pretend the behavior is settled.
- Proof gates: no live gate in the Proof Gates table is closed by this document
  handoff. Move a row to `real` only after the named proof runs and redacted
  evidence exists outside tracked public docs.

## How To Plan From This Register

Use the register as an ordered work queue, not as a loose list of concerns.

1. Start with P0 trust and launch gates: production E2E proof (`GAP-001`) and
   Docker/root trusted-host hardening (`GAP-019`), while treating the broad
   local suite failure (`GAP-025`) as a release-readiness blocker.
2. Then schedule P1 user-journey blockers: live billing, bot delivery,
   provisioning/ingress, Hermes workspace proof, provider policy/proof, Notion
   verification truth, OpenAPI token contracts, stale status docs, admin live
   action proof, and full-suite regression triage.
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
| `GAP-019` | Docker/root authority is a trusted-host P0 boundary | Security hardening and operator risk decision | Reduce socket/root exposure where practical, add monitoring/runbook controls, and record accepted residual risk. |
| `GAP-002` | Payment and entitlement cannot be called live-ready | Authorized live proof | Run Stripe checkout, webhook, portal, failure, cancellation, and refuel proof rows with redacted evidence. |
| `GAP-003` | Chat-first Raven and selected-agent delivery may strand users | Authorized live proof | Prove Telegram and Discord independently, including commands, buttons, callbacks, and handoff delivery. |
| `GAP-004` | Paid ArcPod provisioning may not create a reachable deployment | Authorized live proof | Prove one domain-mode and one Tailscale-mode deployment, health check, rollback, and teardown. |
| `GAP-005` | Dashboard-to-Hermes workspace promise is not browser-proven | Authorized workspace proof | Run desktop/mobile workspace proof against a real TLS Hermes dashboard and plugin surface. |
| `GAP-006` | Agents may deploy without settled provider/inference behavior | Policy decision plus authorized provider proof | Decide provider self-service/account policy, then prove router inference, key lifecycle, usage, and budget behavior. |
| `GAP-007` | Notion setup can be mistaken for verified integration | Code repair plus live Notion proof | Add explicit verification state and prove shared-root read/write/webhook behavior before saying setup is complete. |
| `GAP-008` | Public API docs omit checkout proof-token requirements | Documentation/schema repair plus test | Update dynamic/static OpenAPI and assert required token fields in tests. |
| `GAP-011` | Operator docs can send future agents to stale Control Node assumptions | Documentation repair plus truth test | Mark foundation wording historical or align it with current Control Node boundaries. |
| `GAP-018` | Admin buttons may be confused with live side effects | Live proof plus support matrix | Publish action readiness by adapter and prove the smallest safe live action subset. |
| `GAP-025` | Broad local Python suite is not green | Regression triage and repair | Triage the 2026-05-20 full-suite failures into environment, stale-test, and true-regression buckets, then repair or quarantine intentionally skipped live/env-dependent cases. |

Operator decision rule: if the closure type is live proof or policy, a local
fake test can reduce implementation risk but cannot close the row. If the
closure type is documentation/schema repair, it can close only after the
corresponding truth or contract test passes.

## Gap Register

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
- Status: partial, proof-gated
- Journey joints: `J-22`
- Proof gates: `PG-NOTION`
- Joint: Raven `/connect_notion`, SSOT verification, shared Notion workspace
- Expected: after secure credential handoff, the user can connect Notion and see
  verified shared-root SSOT status.
- Actual evidence: Raven blocks Notion setup until credential handoff closes
  (`python/arclink_public_bots.py:3291-3358`) and then records setup intent and a
  callback. The command explicitly does not verify the integration, install
  secrets, support user-owned OAuth, or bypass verification
  (`python/arclink_public_bots.py:3759-3835`). The dashboard labels live proof as
  gated (`web/src/app/dashboard/page.tsx:1541-1580`). Notion proof code marks
  live mutation and user-owned OAuth as proof-gated
  (`python/arclink_notion_ssot.py:1120-1205`).
- Missing proof/tests: live shared root readability, brokered write preflight,
  webhook verification, and user-facing completion copy.
- Impact: users may think `/connect_notion` completes Notion setup when it only
  records intent.
- Owner/surface: Notion SSOT, public bot, dashboard.
- Next repair: add a dashboard/operator verification state machine and change
  copy where needed so "ready" never means "verified" until proof passes.

### GAP-008 - OpenAPI omits required onboarding proof tokens

- Severity: P1
- Status: doc-gap, test-gap
- Journey joints: `J-02`
- Joint: public API contract for checkout success/cancel
- Expected: OpenAPI says `claim_token` is required for
  `/onboarding/claim-session` and `cancel_token` is required for
  `/onboarding/cancel`.
- Actual evidence: actual API requires `claim_token` and `cancel_token`
  (`python/arclink_api_auth.py:3485-3608`), and the web client sends them
  (`web/src/lib/api.ts:56-60`). Dynamic OpenAPI only documents `session_id`
  (`python/arclink_hosted_api.py:2602-2620`), and the static copy has the same
  omission (`docs/openapi/arclink-v1.openapi.json:985-1017`,
  `docs/openapi/arclink-v1.openapi.json:1061-1097`). Tests only check route
  coverage/static equality, not semantic required fields
  (`tests/test_arclink_hosted_api.py:3821-3858`).
- Missing proof/tests: schema assertions for required request bodies and example
  contract tests that a generated client can call success/cancel.
- Impact: generated clients fail, docs understate the anti-enumeration proof,
  and external implementers may build insecure or broken checkout flows.
- Owner/surface: hosted API OpenAPI, docs, tests.
- Next repair: update dynamic and static OpenAPI, then add focused tests for
  required token fields.

### GAP-009 - Browser proof tokens persist in localStorage

- Severity: P2
- Status: security-risk, ux-gap
- Journey joints: `J-02`, `J-28`
- Joint: web onboarding resume and checkout success/cancel proof
- Expected: claim/cancel proof tokens should be recoverable enough for checkout
  resume without creating unnecessary persistent browser exposure.
- Actual evidence: web onboarding restores and persists `claimToken` and
  `cancelToken` in `localStorage` (`web/src/app/onboarding/page.tsx:85-122`);
  success/cancel pages read those tokens from the same storage
  (`web/src/app/checkout/success/page.tsx:72-99`,
  `web/src/app/checkout/cancel/page.tsx:35-58`).
- Missing proof/tests: browser tests for token lifetime, replay, cleanup,
  multi-tab behavior, and XSS-resistant storage choice.
- Impact: the tokens are random and hashed server-side, but persistence extends
  exposure to scripts/extensions and can confuse recovery on shared browsers.
- Owner/surface: web onboarding, hosted auth.
- Next repair: move proof material to shorter-lived `sessionStorage`,
  HttpOnly-bound server state, or an explicit short TTL design; add browser
  tests for cleanup after claim/cancel.

### GAP-010 - Web "preferred channel" copy does not create a Telegram/Discord identity

- Severity: P2
- Status: ux-gap
- Journey joints: `J-01`, `J-02`, `J-03`
- Joint: website entry from `?channel=telegram` or `?channel=discord`
- Expected: if the page says Raven will continue in Telegram/Discord, the
  session should be linked to that real channel identity or the copy should say
  web-only.
- Actual evidence: onboarding reads a query channel and displays "Raven will
  continue there after checkout" (`web/src/app/onboarding/page.tsx:72-82`,
  `web/src/app/onboarding/page.tsx:294-297`), but `handleStart` always sends
  `channel: "web"` with a generated web contact id
  (`web/src/app/onboarding/page.tsx:124-144`).
- Missing proof/tests: UI test for channel query behavior and a product decision
  on whether web can start a public channel handoff without platform identity.
- Impact: users may expect a Telegram/Discord handoff that cannot happen from
  that web-only session.
- Owner/surface: web onboarding, public bot linking.
- Next repair: remove the promise, require a real channel-link action, or route
  the user into the platform before checkout.

### GAP-011 - Foundation docs contradict current Control Node status

- Severity: P1
- Status: doc-gap
- Journey joints: `J-15`, `J-17`
- Joint: operator understanding of live adapters and product surface
- Expected: root and operations docs agree on what Control Node currently ships
  and what remains proof-gated.
- Actual evidence: the current Control Node docs say hosted API, web, provisioner
  loop, action worker, LLM router, and live executor boundaries exist with live
  mutation gated by config (`docs/arclink/sovereign-control-node.md:21-36`,
  `docs/arclink/sovereign-control-node.md:121-155`). The older foundation
  runbook still says ArcLink does not ship production adapters that execute
  customer containers, create live DNS, mint provider keys, run live public bots,
  authenticate dashboards, or run live admin-action worker
  (`docs/arclink/foundation-runbook.md:14-25`). `foundation.md` also says public
  bot adapters do not run live clients yet (`docs/arclink/foundation.md:172-177`,
  `docs/arclink/foundation.md:275-279`).
- Missing proof/tests: documentation truth check that stale prototype wording
  cannot coexist with current Control Node runbooks.
- Impact: an operator or future agent may call the wrong deploy path or
  understate/overstate current capability.
- Owner/surface: docs, operations.
- Next repair: mark foundation docs historical or rewrite the status section to
  match current Control Node boundaries.

### GAP-012 - Product matrix "0 gap / 0 partial" is not a reliable control

- Severity: P2
- Status: doc-gap, test-gap
- Journey joints: `J-27`
- Joint: source-of-truth claims for product readiness
- Expected: a matrix row marked `real` should have enough local source and test
  evidence, and proof-gated rows should not be hidden by aggregate optimism.
- Actual evidence: matrix totals claim 101 `real`, 0 `partial`, and 0 `gap`
  (`research/PRODUCT_REALITY_MATRIX.md:19-20`), while current docs explicitly
  state no live E2E proof (`README.md:26-31`,
  `docs/arclink/live-e2e-secrets-needed.md:3-22`) and this register identifies
  multiple partial/proof/doc/test gaps from fresh evidence.
- Missing proof/tests: automated doc/status consistency check or evidence
  requirement for each `real` row.
- Impact: future work may use the matrix as a launch checklist and miss
  unresolved proof gates.
- Owner/surface: research docs, release process.
- Next repair: rebuild the matrix from this register with row-level evidence and
  require matrix rows marked `real` to cite code plus test/proof before this
  atlas treats them as `real`.

### GAP-013 - Raven backup prep stops before key setup and verification

- Severity: P2
- Status: partial, ux-gap, ops-gap
- Journey joints: `J-03`, `J-13`, `J-26`
- Proof gates: `PG-BACKUP`
- Joint: public `/config_backup` lane
- Expected: user chooses a private repo, ArcLink creates/verifies a per-pod
  deploy key, activates backup, and reports status.
- Actual evidence: public bot backup prep records the intended private repo and
  explicitly says it does not mint, install, or verify the deploy key; dashboard
  or operator backup rail completes that step
  (`python/arclink_public_bots.py:3838-3912`). First-day docs say private
  Hermes-home backup may be offered, public repos are refused, and deploy keys
  must not be pasted in chat (`docs/arclink/first-day-user-guide.md:72-79`).
- Missing proof/tests: Control Node dashboard backup rail, public status
  handoff, deploy-key verification proof, and restore proof.
- Impact: a user can start backup setup in chat and then hit an operator-only
  cliff.
- Owner/surface: backup, public bot, dashboard.
- Next repair: add backup status and key-verification UI, or change Raven copy
  to explicitly hand off to an operator.

### GAP-014 - Browser share-link UI is disabled pending a broker/adapter

- Severity: P2
- Status: partial, policy-question
- Journey joints: `J-19`, `J-20`
- Joint: Drive/Code share creation from user workspace
- Expected: users can create a share link or share request from the browser
  where they find the file.
- Actual evidence: backend share grants, Raven approvals, and Linked roots are
  present, but the operations runbook says right-click browser share-link UI
  remains disabled until a live ArcLink browser broker or approved
  Nextcloud-backed adapter exists (`docs/arclink/operations-runbook.md:131-148`).
- Missing proof/tests: browser UI flow, broker auth, recipient notification,
  audit, revoke, and no-reshare tests.
- Impact: sharing exists through API/MCP/Raven but not through the expected file
  browser affordance.
- Owner/surface: Drive/Code UI, share broker, Nextcloud adapter policy.
- Next repair: decide broker vs Nextcloud-backed adapter and implement a single
  browser share path with tests.

### GAP-015 - Share approval can silently wait if the owner has no linked public channel

- Severity: P2
- Status: ux-gap, ops-gap
- Journey joints: `J-13`, `J-20`, `J-24`
- Joint: cross-user share request notification
- Expected: if a share requires owner approval, the owner reliably sees the
  approval request or the requester gets a clear next step.
- Actual evidence: operations docs say share creation persists the grant as
  `pending_owner_approval`, but no Raven notification is queued if the owner has
  no linked Telegram/Discord channel. The response reports
  `owner_notification.queued=false` with a reason
  (`docs/arclink/operations-runbook.md:150-158`).
- Missing proof/tests: requester UI that surfaces this waiting state, dashboard
  approval inbox, and retry notification path.
- Impact: the requester can think sharing failed or the owner can miss the
  approval entirely.
- Owner/surface: sharing UX, dashboard, public bot.
- Next repair: expose pending approvals in both user dashboards and provide a
  "send/link channel" recovery action.

### GAP-016 - Copy/duplicate policy is inconsistent across MCP, docs, and tests

- Severity: P2
- Status: policy-question, doc-gap
- Journey joints: `J-20`
- Joint: recipient copying an accepted Linked resource into owned space
- Expected: the policy is one clear product rule.
- Actual evidence: docs say Drive/Code allow copy/duplicate from Linked into the
  recipient's own Vault/Workspace (`docs/arclink/operations-runbook.md:131-148`);
  tests prove copy/duplicate works (`tests/test_arclink_plugins.py:640-686`).
  But `shares.request` returns `"copy_duplicate_policy": "policy_question"`
  (`python/arclink_mcp_server.py:1022-1031`).
- Missing proof/tests: assertion that MCP response policy matches the accepted
  product decision.
- Impact: agents may describe the policy as undecided even though UI/plugin
  behavior allows recipient copies.
- Owner/surface: MCP share tool, docs, plugin policy.
- Next repair: change the MCP response to the decided policy or deliberately
  revert the copy/duplicate behavior and docs.

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
- Proof gates: `PG-PROVISION`, `PG-INGRESS`
- Joint: restart, DNS repair, key rotation, refund/cancel/comp, rollout,
  reprovision, rollback
- Expected: admin actions mutate real services/providers only when the worker and
  executor are live and record evidence.
- Actual evidence: readiness probes fail closed when executor/worker are not
  ready (`python/arclink_dashboard.py:57-92`), and queuing rejects unsupported or
  pending action types (`python/arclink_dashboard.py:1428-1512`). Production docs
  say an action only proves live mutation when the recorded executor result is
  live and succeeded (`docs/arclink/control-node-production-runbook.md:72-86`).
- Missing proof/tests: live action-worker run for each supported action class,
  plus negative tests for wrong idempotency reuse against live adapters.
- Impact: operators may see an action in UI and assume it has production effect
  when only local queueing is proven.
- Owner/surface: admin dashboard, action worker, executor.
- Next repair: publish action support matrix from worker readiness and add live
  proof rows for the smallest safe subset.

### GAP-019 - Docker socket/root services are a P0 trusted-host boundary

- Severity: P0
- Status: security-risk, ops-gap
- Journey joints: `J-16`, `J-17`, `J-28`
- Joint: Control Node and Docker shared-host authority boundary
- Expected: services with Docker socket/root access are explicitly hardened and
  monitored because compromise means host/container control.
- Actual evidence: Compose mounts the host Docker socket into control ingress,
  control provisioner, control action worker, agent supervisor, notification
  delivery, and curator refresh; action-worker and agent-supervisor run as root
  (`compose.yaml:323-340`, `compose.yaml:349-408`,
  `compose.yaml:420-473`, `compose.yaml:499-518`). Data safety documents these
  as trusted-host services (`docs/arclink/data-safety.md:67-80`).
- Missing proof/tests: hardening checklist, least-privilege review, socket proxy
  evaluation, container escape monitoring, and incident runbook.
- Impact: a bug in public bot delivery or admin/action worker could become host
  compromise in local-adapter deployments.
- Owner/surface: platform security, Docker deployment.
- Next repair: make the P0-grade mitigation code-level where practical:
  minimize socket exposure, consider a Docker socket proxy, drop capabilities,
  and narrow writer containers. Treat threat-model docs and health/audit alerts
  as interim controls, not the whole fix.

### GAP-020 - Backup and disaster recovery are documented but not proofed

- Severity: P2
- Status: proof-gated, ops-gap
- Journey joints: `J-26`, `J-27`
- Proof gates: `PG-BACKUP`
- Joint: restore confidence after data loss or migration
- Expected: backup docs map to automated or periodically executed restore
  evidence.
- Actual evidence: backup docs list backup targets, restore steps, retention,
  and a periodic staging restore expectation (`docs/arclink/backup-restore.md:3-77`).
  The audit found docs and scripts, but no source-level evidence of an executed
  restore drill for Control Node plus one ArcPod.
- Missing proof/tests: staging restore ledger, restored health output, restored
  dashboard load, restored deployment stack health.
- Impact: backup existence does not prove recoverability.
- Owner/surface: operations, backup/restore.
- Next repair: add a no-secret restore-smoke harness and require a dated staging
  restore evidence artifact before production launch.

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
  (`docs/arclink/control-node-production-runbook.md:133-158`).
- Missing proof/tests: authorized provider create/join/probe/drain/remove proof
  for each supported provider.
- Impact: Scale/Federation claims that depend on remote capacity remain
  source-level only.
- Owner/surface: fleet inventory, provider adapters.
- Next repair: run one scratch-worker lifecycle per provider and preserve
  redacted evidence.

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

### GAP-025 - Broad local Python suite is not green

- Severity: P1
- Status: test-gap, ops-gap
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
  access tests.
- Missing proof/tests: a triage ledger that separates environment-coupled
  failures from stale tests and true regressions, followed by a green broad
  no-secret suite or an explicit release-approved quarantine list.
- Impact: the journey and gap docs can still be useful as source-grounded
  planning artifacts, but the checkout must not be described as broadly
  regression-clean. Some failing clusters touch surfaces the atlas documents as
  locally `real`, so they must be rechecked before those claims are used for
  release readiness.
- Owner/surface: release validation, CI/preflight, affected owners from each
  failure cluster.
- Next repair: run a dedicated full-suite triage pass, start with the failures
  in public bot onboarding, deploy/health shell paths, plugins, repo sync,
  backup, vault, and Notion onboarding, then update this row with closed,
  quarantined, or newly split gap IDs.

## Not Gaps / Already Real

These surfaces were checked and found covered at the source/local level. They
still may have separate live proof gates above. After `GAP-025`, do not treat
this section as a broad release-green claim; it records source/local evidence
that must be reconciled with the current full-suite failures before launch.

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
  (`tests/test_arclink_hosted_api.py:3861-3908`).

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
- Browser share-link broker: native ArcLink broker or approved Nextcloud-backed
  adapter?
- Linked copy/duplicate policy: align MCP response with the currently allowed
  copy/duplicate into owned roots, or change behavior.
- Backup automation: how much of per-pod backup key setup should be user-facing
  versus operator-only?
- Destructive teardown: define who may request volume deletion and what
  confirmation/evidence is required.

## Test Plan

Focused local checks for code-owned gaps:

- GAP-008: update dynamic and static OpenAPI, then extend
  `tests/test_arclink_hosted_api.py` to assert `claim_token` and `cancel_token`
  are required in schema and behavior.
- GAP-009: add browser/unit coverage for onboarding token storage, cleanup after
  claim/cancel, replay window, refresh, and multi-tab behavior.
- GAP-010: add a web test for `?channel=telegram|discord` copy and request body,
  then either remove the continuation promise or implement a real platform link.
- GAP-011/GAP-012: add a documentation truth check that rejects stale prototype
  phrases and requires matrix rows marked `real` to cite current code plus
  test/proof before they are treated as `real` in this atlas.
- GAP-013: add a dashboard/public-bot test that backup prep exposes pending
  status and does not imply deploy-key verification.
- GAP-014/GAP-015: add share UI/API tests for pending-owner-no-channel,
  dashboard approval inbox, recipient accept, revoke, and no-reshare.
- GAP-016: update MCP `copy_duplicate_policy` and add an assertion that docs,
  MCP response, and plugin behavior agree.
- GAP-018: add fake/local action-worker integration tests per supported action
  type, including idempotency mismatch rejection and disabled worker readiness.
- GAP-019: add a security review checklist and a CI/static assertion that any new
  Docker socket mount has a trusted-boundary comment and runbook entry.
- GAP-020/GAP-021: add no-secret dry-run/fixture restore and fleet provider
  lifecycle harnesses; live variants stay skipped unless proof env gates are set.
- GAP-025: rerun the broad no-secret Python suite, preserve the failure log,
  classify each failing file as environment-coupled, stale expectation, or true
  regression, and require a green rerun or an explicit quarantine file before a
  future handoff says broad local validation passed.

Live proof checks must not run by default in CI and must skip cleanly without
credentials.
