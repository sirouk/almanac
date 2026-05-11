# Build Completion Notes

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
