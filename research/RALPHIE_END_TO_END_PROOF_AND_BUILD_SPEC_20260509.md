# Ralphie End-To-End Proof And Build Spec - 2026-05-09

This document is the next steering packet for `ralphie.sh`. It records the
new Chutes proof work, the remaining operator decisions, and the build details
needed to move ArcLink from local truth to end-to-end production readiness.

Ralphie must read this together with:

- `AGENTS.md`
- `IMPLEMENTATION_PLAN.md`
- `research/PRODUCT_REALITY_MATRIX.md`
- `research/OPERATOR_POLICY_DECISIONS_20260508.md`
- `research/RALPHIE_MEMORY_SYSTEM_CHERRYPICK_STUDY.md`

Do not read secrets, `arclink-priv/`, user homes, live token files, deploy
keys, `.env` values, OAuth credentials, bot tokens, or private state. Do not
run live provider mutations without explicit operator authorization.

## Chutes Research Proved This Pass

Sources inspected:

- `https://llm.chutes.ai/v1/models`
- `https://api.chutes.ai/openapi.json`
- `https://github.com/chutesai/chutes-api`
- `https://github.com/Veightor/chutes-agent-toolkit`

Temporary read-only clones of the public Chutes repositories were used during
research. Their local checkout paths are intentionally omitted so this artifact
stays portable.

### Current Model Pricing

The public model endpoint returns OpenAI-style model records with per-million
token pricing, `chute_id`, context limits, supported features, and confidential
compute flags.

Captured samples:

| Model | Input / 1M | Output / 1M | Cache read / 1M | Notes |
|---|---:|---:|---:|---|
| `Qwen/Qwen3-32B-TEE` | `$0.08` | `$0.24` | `$0.04` | TEE, tools/json/structured/reasoning, 40,960 ctx |
| `deepseek-ai/DeepSeek-V3.2-TEE` | `$0.28` | `$0.42` | `$0.14` | TEE, tools/json/structured/reasoning, 131,072 ctx |
| `moonshotai/Kimi-K2.6-TEE` | `$0.95` | `$4.00` | `$0.475` | TEE, tools/json/structured/reasoning, 262,144 ctx |

ArcLink must not hard-code these prices as permanent truth. Add a model-price
refresh/cache path and test with fixtures.

### Account Creation Reality

Chutes account creation is real in public code, but it is not a simple,
silent operator-server call:

- `POST /users/register` exists.
- Registration requires a registration token.
- The token path is tied to browser/Cloudflare/hCaptcha style proof:
  `/users/registration_token`.
- Registration requires hotkey/coldkey context and enforces a minimum TAO
  balance on the registering coldkey.
- The response returns a 32-character fingerprint shown once.
- The toolkit's Chutes prompt notes practical registration may need
  human-in-the-loop browser verification and funding.

There is also an agent-oriented path in public `chutes-api`:

- `POST /users/agent_registration`
- `GET /users/agent_registration/{hotkey}`
- `POST /users/{user_id}/agent_setup`

That path creates a payment address, waits for funding, then returns a one-time
API key/config after hotkey-signature proof. It still depends on hotkey
ownership and payment; it is not a generic SaaS "create account for user with
operator API key" flow.

Product implication:

- Programmatic per-user Chutes account creation is possible only as an
  assisted/proof-gated flow unless the operator supplies and authorizes the
  hotkey/funding/registration-token mechanics.
- The safer ArcLink default is "Connect your Chutes account" through Chutes
  OAuth / delegated account lanes, with operator-managed bootstrap keys used
  only as a local-metered fallback.

### API Key Lifecycle Reality

Public `chutes-api` exposes key management for the current authenticated user:

- `GET /api_keys/`
- `GET /api_keys/{api_key_id}`
- `POST /api_keys/`
- `DELETE /api_keys/{api_key_id}`

The key model includes:

- `api_key_id`
- `user_id`
- `name`
- `admin`
- scopes
- `created_at`
- `last_used_at`

The secret key is returned only during creation. List/get calls do not return
the secret. This maps well to ArcLink's existing credential handoff/ack/remove
pattern.

Important unknown:

- Public code does not show authoritative per-API-key spend accounting.
  `last_used_at` exists, but usage endpoints are account/user/chute/time
  oriented. If ArcLink uses one operator Chutes account with one API key per
  ArcLink user, provider-side per-key budget enforcement is not proven.

### Usage, Billing, Quota, And Balance Reality

The toolkit's `chutes-usage-and-billing` skill is now a strong proof guide. It
is marked verified live by that repo and includes read-only scripts:

- `spend_summary.py`
- `cost_breakdown.py`
- `quota_guard.py`
- `download_export.py`

Public Chutes OpenAPI/source confirms these useful user/account endpoints:

- `GET /users/me/subscription_usage`
- `GET /users/me/quota_usage/{chute_id}`
- `GET /users/{user_id}/usage`
- `GET /users/me/quotas`
- `GET /users/me/discounts`
- `GET /users/me/price_overrides`
- `GET /users/{user_id_or_username}/subscription_usage` for billing admins
- `POST /users/balance_transfer`

The toolkit warns that several endpoints are platform-wide, not personal spend:

- `/invocations/usage`
- `/invocations/stats/llm`
- `/invocations/exports/*`
- `/payments`
- `/payments/summary/tao`

ArcLink must label those carefully and must prefer personal/account endpoints
for user billing views.

### OAuth / Sign In With Chutes Reality

The toolkit and public API expose a real OAuth/OIDC/PKCE surface:

- `GET /idp/scopes`
- `POST /idp/apps`
- `GET/PATCH/DELETE /idp/apps/{app_id}`
- `POST /idp/apps/{app_id}/regenerate-secret`
- `GET /idp/authorize`
- `POST /idp/token`
- `POST /idp/token/introspect`
- `POST /idp/token/revoke`
- `GET /idp/userinfo`

Useful scopes from public `idp` code/toolkit docs:

- `openid`
- `profile`
- `chutes:invoke`
- `account:read`
- `billing:read`
- `quota:read`
- `usage:read`

Scope rule:

- Request `billing:read` only when ArcLink actually shows Chutes usage/billing.
- `chutes:invoke` delegates inference to the user's Chutes account, but it does
  not grant management CRUD. For Chutes app/admin management, use API-key
  authentication.

Live proof still needed:

- Whether ArcLink's server can use a Chutes OAuth access token directly for
  `https://llm.chutes.ai/v1` inference in the exact header shape ArcLink needs.
- Whether token refresh/revocation semantics are stable enough for production
  provider failover.

## Recommended Chutes Product Decision

Recommended canonical model:

1. **Primary:** per-user Chutes account connected through Sign in with Chutes.
   Use `openid profile chutes:invoke account:read billing:read` only after the
   ArcLink UI actually presents account/billing usage. The user's Chutes
   account pays for provider usage; ArcLink still monitors plan-level ArcLink
   entitlement and can require Refuel/upgrade when ArcLink-covered limits are
   exceeded.
2. **Fallback:** operator-managed scoped Chutes API key per deployment only
   when ArcLink local metering is authoritative for that deployment. Label this
   as local ArcLink budget enforcement, not provider-side per-key billing proof.
3. **Account-creation assist:** guide a user through Chutes account creation
   only when no account exists. Do not promise silent creation because
   registration token, hCaptcha/Cloudflare, hotkey, and funding constraints are
   real.
4. **Refuel Pod:** local ArcLink budget credits first. Direct Chutes balance
   transfer/top-up is a later live-proof feature using `POST /users/balance_transfer`
   or user-directed Chutes dashboard top-up.

## Remaining Operator Decisions

Ralphie must not guess these. Keep unresolved surfaces disabled or truthfully
labeled until the operator answers.

### Decision 1 - Raven Chat Scope

Current code: Raven is a public control conduit. Freeform messages in Telegram
or Discord do not become private-agent chat.

Options:

- A. Keep Raven control-only; update product copy to say direct agent chat
  happens in Helm/Hermes or the private agent bot.
- B. Add explicit public bot command `/ask` or `/agent <message>` that proxies
  one message to the selected agent and labels the answer with the active
  agent. Keep raw freeform routed to Raven.
- C. Make all public freeform chat proxy to the selected agent after onboarding.
  This is highest risk because it expands public-channel data exposure.

Recommended: B. Explicit proxy command, not raw freeform.

### Decision 2 - Browser Share-Link Backend

Current code: share grants, owner approve/deny, recipient accept, `Linked`
roots, no-reshare, copy/duplicate, and living symlink projections are real.
Browser right-click share-link UI remains intentionally hidden.

Options:

- A. ArcLink broker first: create claim-link tokens in ArcLink, require logged
  in recipient, then owner approve/deny, then materialize `Linked`.
- B. Nextcloud/WebDAV/OCS adapter where Nextcloud is enabled, wrapped by the
  same ArcLink approval/audit policy.
- C. Keep browser share-link disabled and only allow agent/MCP share requests.

Recommended: A first, B optional adapter later. Do not expose raw Nextcloud
shares as the product contract unless ArcLink approval/no-reshare/revoke rules
wrap them.

### Decision 3 - Share Recipient Discovery

Options:

- A. Recipient email/account handle lookup in ArcLink dashboard.
- B. Recipient paste/link claim only; owner approves after the recipient claims.
- C. Both.

Recommended: C, but implement B first because it best matches "generate a link
and recipient accepts while logged in."

### Decision 4 - Chutes Provider Path

Options:

- A. Per-user Chutes OAuth/delegated account as canonical.
- B. Operator account with per-user API keys plus ArcLink local metering.
- C. Chutes agent-registration/account-creation assist.

Recommended: A canonical, B fallback, C guided assist only.

### Decision 5 - Refuel Pod Semantics

Options:

- A. ArcLink internal provider-budget credit only.
- B. ArcLink also transfers Chutes balance to the user's Chutes account.
- C. User receives instructions/link to top up Chutes directly, while ArcLink
  credits only its own local provider budget.

Recommended: A now, B only after live balance-transfer proof, C as user-facing
copy for connected per-user Chutes accounts.

### Decision 6 - Renewal Purge Execution

Options:

- A. Day 14 queues purge for operator approval.
- B. Day 14 automatically purges after audited notice attempts.

Recommended: A. Queue purge review; require operator confirmation for the
irreversible delete.

### Decision 7 - Notion SSOT Account Model

Current canonical policy: shared-root membership. Email sharing alone is not
proof of API read/write.

Options:

- A. Shared-root membership only for first production cut.
- B. Also support user-owned Notion OAuth/token lanes.
- C. Email-share-only as a convenience flow.

Recommended: A. Keep B proof-gated and C explicitly not proof.

## Ralphie Build Plan

### Phase 0 - Truth And Messaging Repair

- Update `research/PRODUCT_REALITY_MATRIX.md` with the new Chutes proof:
  account creation is assisted/proof-gated; usage/billing endpoints are real;
  per-api-key provider spend remains unproven; OAuth/delegated account is the
  preferred path.
- Update `research/OPERATOR_POLICY_DECISIONS_20260508.md` or supersede it
  with this Chutes proof.
- Scrub explicit lore/franchise framing from `docs/arclink/CREATIVE_BRIEF.md`.
  Product term `Limited 100 Founders` may remain; explanatory "The 100" lore
  should not.
- Update Raven docs to distinguish control conduit vs direct private-agent
  chat. If Decision 1 is not answered, keep control-only truth.

Validation:

- `rg -n "The 100|franchise|The 100 is|Founder-tier mythology" docs research web python plugins`
- `python3 tests/test_documentation_truths.py`
- `git diff --check`

### Phase 1 - Chutes Live Adapter Boundary

Implement a secret-safe Chutes adapter layer behind ArcLink's existing
`python/arclink_chutes.py` boundary. Suggested module split:

- `python/arclink_chutes_live.py`
- `python/arclink_chutes_oauth.py`
- `tests/test_arclink_chutes_live_adapter.py`

Required client methods:

- `list_models()`
- `get_me()`
- `get_subscription_usage()`
- `get_user_usage(user_id, page, limit, per_chute=False, chute_id=None)`
- `get_quota_usage(chute_id)`
- `get_quotas()`
- `get_discounts()`
- `get_price_overrides()`
- `list_api_keys()`
- `create_api_key(name, admin, scopes)`
- `delete_api_key(api_key_id)`
- `transfer_balance(recipient_user_id, amount)`
- `list_scopes()`
- `introspect_oauth_token(token_ref)` via secret ref only

Hard rules:

- No raw `cpk_`, `cak_`, `crt_`, `csc_`, fingerprint, hotkey seed, or OAuth
  token may appear in logs, tests, docs, API responses, or exceptions.
- All live methods accept secret references, not raw secrets.
- Fake tests must use fixtures shaped like public OpenAPI responses.
- Live tests must be skipped unless explicit env flags and secret refs are set.

Recommended DB/state additions if existing rows are insufficient:

- `arclink_provider_accounts`
  - `provider_account_id`
  - `provider`
  - `user_id`
  - `mode` (`chutes_oauth`, `chutes_api_key`, `operator_metered_key`)
  - `external_user_id`
  - `external_username`
  - `secret_ref`
  - `status`
  - `metadata_json`
  - timestamps
- `arclink_provider_usage_snapshots`
  - `snapshot_id`
  - `provider`
  - `user_id`
  - `deployment_id`
  - `provider_account_id`
  - `source_endpoint`
  - `period_start`
  - `period_end`
  - `usage_cents`
  - `input_tokens`
  - `output_tokens`
  - `request_count`
  - `metadata_json`
  - timestamps

### Phase 2 - Chutes User Connect Flow

Add a user-facing provider connect journey:

- Dashboard "Connect Chutes" action.
- Server route to start Chutes OAuth.
- Callback route stores token by secret ref.
- Provider state shows connected account, scopes, and billing-read readiness.
- User can disconnect/revoke ArcLink's Chutes access.
- Provider state never accepts raw provider tokens in the browser.

If OAuth live proof is not authorized:

- Implement local fake OAuth callback tests.
- Keep UI labeled "proof-gated" or "operator setup required".

Validation:

- Hosted API tests for CSRF, user scoping, no raw tokens, state mismatch.
- Dashboard tests for connect/disconnect states.
- Provider-state tests proving one user cannot see another user's Chutes account
  metadata or usage.

### Phase 3 - Chutes Usage Monitoring And Refuel

Implement monitored budget behavior:

- Periodic usage sync from Chutes personal endpoints when a user Chutes account
  is connected.
- Local fallback metering from ArcLink inference usage events when using
  operator-scoped keys.
- Warning threshold state visible in user dashboard, admin dashboard, and Raven.
- Hard-limit state blocks inference or routes to the configured fallback policy.
- Refuel Pod checkout creates ArcLink internal budget credit first.
- Optional later: if Chutes balance transfer is live-proven, apply part of a
  Refuel Pod to the user's Chutes account via `POST /users/balance_transfer`.

Public copy must say:

- "ArcLink budget credit" when it is internal only.
- "Chutes balance transferred" only after a live provider transfer succeeds.

Validation:

- Local fake tests for usage sync, warning, exhaustion, Refuel credit,
  billing-suspended state, and no cross-user usage leakage.
- Live tests skipped unless `ARCLINK_LIVE_CHUTES_PROOF=1` and secret refs exist.

### Phase 4 - Raven Direct-Agent Decision

If operator chooses explicit proxy command:

- Add `/ask`, `/agent`, or `/agent <message>` command.
- Require an active deployment selected by `/agents`.
- Prefix replies with the selected agent label.
- Keep raw freeform public messages routed to Raven/control copy.
- Add tests proving account/channel scoping and that another user's selected
  agent cannot be reached.

If operator chooses control-only:

- Update docs and UI copy to stop implying Raven is direct chat with agents.

### Phase 5 - Browser Share Links

Implement ArcLink broker share links:

- Owner right-clicks file/dir under Vault or Workspace in Drive/Code.
- Browser calls a new CSRF-protected share-link create endpoint.
- Endpoint returns a claim URL/token, not raw filesystem paths.
- Recipient must be logged into ArcLink to claim.
- Claim creates or binds a pending share grant to recipient.
- Owner receives Raven and dashboard approve/deny.
- Approval materializes `Linked` as current code already does.
- Recipient cannot reshare from `Linked`, but can copy/duplicate into own Vault
  or Workspace.
- Revoke removes projection and manifest entry.

If Nextcloud is enabled:

- Add a capability probe for OCS/WebDAV share support.
- Never expose raw Nextcloud share semantics directly to users.
- ArcLink remains the policy broker and audit source.

Validation:

- Hosted API tests for claim token expiry, recipient auth, owner approval,
  deny, revoke, path traversal, symlink/source-outside-root blocks, and
  cross-user denial.
- Drive and Code browser tests for context menu visibility only when capability
  is enabled.

### Phase 6 - Notion SSOT Live Proof Harness

Keep shared-root membership as canonical. Build proof harnesses, not guesses:

- Verify callback URL configured.
- Verify the shared root/page is readable through the configured integration.
- Verify write rail uses `ssot.write`.
- Verify email-share-only is not treated as proof.
- Store proof result as scoped metadata visible to the user and admin.

### Phase 7 - Live Proof Orchestration

Extend the existing live proof/evidence tooling so each external row can be
proven independently:

- Stripe checkout/webhook.
- Telegram Raven delivery and buttons.
- Discord Raven delivery and buttons.
- Hermes dashboard landing.
- Chutes OAuth connect.
- Chutes usage/billing sync.
- Chutes API key create/delete, if authorized.
- Chutes balance transfer, if authorized.
- Notion shared-root SSOT.
- Cloudflare zone verification.
- Tailscale serve/cert verification.

Live proof command must:

- Require explicit env flags per provider.
- Redact all secrets.
- Write evidence records with provider, target, timestamp, request id, status,
  and redacted result summary.
- Never mutate production user data without a dry-run or dedicated scratch
  account.

## Ralphie Done Criteria

Ralphie is not done until:

- The matrix is updated with every new Chutes proof/gate.
- The explicit lore/messaging violation is removed.
- Every unresolved operator decision is represented as disabled UI/copy or a
  clear policy question.
- Chutes adapters have fake tests and live-proof gates.
- Browser share links are either implemented behind capability flags or remain
  disabled with truthful docs.
- Raven direct-agent behavior matches the operator's chosen policy.
- User isolation tests cover dashboard, provider state, usage, shares, channels,
  credentials, billing, and health after any route changes.
- `research/BUILD_COMPLETION_NOTES.md` records what was run, what was skipped,
  and why.

## Suggested Ralphie Session Objective

Use this as the next `ralphie.sh` goal text:

```text
Continue ArcLink end-to-end production readiness from
research/RALPHIE_END_TO_END_PROOF_AND_BUILD_SPEC_20260509.md.

First update the truth matrix and docs with the new Chutes proof trail.
Then implement the highest-impact local build tasks that do not require live
secrets: Chutes live-adapter boundary with fake tests, Chutes usage/refuel
state plumbing, explicit Raven policy copy or command scaffolding depending on
operator decision, and ArcLink broker share-link design/tests behind disabled
capability flags. Keep live Chutes, Stripe, Notion, Telegram, Discord,
Cloudflare, Tailscale, and Hermes runtime proof gated unless explicit env flags
and secret refs are supplied.

Do not claim live proof without evidence. Preserve all user isolation and
secret redaction invariants.
```
