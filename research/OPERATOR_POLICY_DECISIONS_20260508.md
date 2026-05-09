# Operator Policy Decisions - 2026-05-08

These decisions answer the remaining ArcLink product-policy questions from the
product-reality matrix. They are operator intent, not proof that the current
code already implements every behavior.

## Canonical Decisions

- Raven identity: support per-user and per-channel Raven bot-name
  customization. Selected-agent labels remain required, but they are not the
  whole promise.
- SSOT sharing: use shared-root membership as the canonical Notion SSOT sharing
  model. User-owned Notion OAuth/token and email-share-only models are not the
  default product path unless later proof/policy changes this.
- Failed renewal: suspend provider/API access immediately when renewal fails.
  Notify through Raven immediately and once daily while unpaid. Days 1-6 are
  payment reminders. Day 7 and later warnings must explicitly say the account
  and agent data are scheduled for deletion. On day 14 unpaid, queue
  irreversible purge only after the day-14 warning is delivered or delivery is
  durably attempted and audited.
- Drive sharing: accepted shared resources remain living linked files or
  directories rooted in an approved shared backend, not copy snapshots. The
  recipient may copy or duplicate accepted content into their own Vault or
  Workspace, but the `Linked` root itself stays non-reshareable.
- Browser right-click sharing: canonical browser behavior is ArcLink share
  grants backed by living shared roots. Use Nextcloud/WebDAV/OCS when the
  ArcLink deployment has Nextcloud enabled and the share can be represented
  safely there; otherwise keep the browser share UI disabled or build a live
  ArcLink broker. Do not claim copied projections satisfy the product promise.
- Operator model: exactly one operator. Any current multi-admin mechanics must
  be constrained, hidden as internal-only, or made subordinate to the single
  operator policy.
- Chutes/refuel: prefer isolated per-user Chutes credentials. If per-key usage
  cannot be metered from the operator account, use a separate Chutes
  account/OAuth session per ArcLink user. Refuel Pod credits are a real product
  direction and should be priced from current Chutes token pricing with margin
  that protects ArcLink without gouging users.

## Chutes Research Snapshot

Verified 2026-05-08 from public sources and temporary read-only clones of
public Chutes repositories:

- `https://llm.chutes.ai/v1/models` returns per-model token pricing. Sample
  prices at capture time:
  - `Qwen/Qwen3-32B-TEE`: `$0.08/M` input, `$0.24/M` output.
  - `deepseek-ai/DeepSeek-V3.2-TEE`: `$0.28/M` input, `$0.42/M` output.
  - `moonshotai/Kimi-K2.6-TEE`: `$0.95/M` input, `$4.00/M` output.
- `https://api.chutes.ai/pricing` returns GPU/compute pricing, not the LLM
  token-price table.
- `chutesai/chutes` documents scoped API-key creation through
  `chutes keys create`, including admin, image, and chute-scoped keys.
- `chutesai/chutes-api` exposes API-key list/get/create/delete for the current
  user. The key model exposes `api_key_id`, `user_id`, `name`, scopes, and
  `last_used_at`, but the open usage tables and endpoints inspected are
  user/chute/time-bucket based rather than per-api-key based.
- `chutes-api` usage surfaces include platform-wide invocation exports and
  aggregate usage. The `chutes-agent-toolkit` research warns those exports are
  not personal spend data.
- `Veightor/chutes-agent-toolkit` documents user/account usage through
  `/users/me/subscription_usage`, `/users/{user_id}/usage`,
  `/users/me/quota_usage/{chute_id}`, and Sign in with Chutes OAuth scopes.
  Treat it as an integration candidate and proof guide, not shipped ArcLink
  behavior.

## Refuel Pod Working Model

Use current token pricing to set conservative refill credits:

- `Refuel Pod S`: `$25`, grants `$17.50` provider budget credit.
- `Refuel Pod M`: `$75`, grants `$55.00` provider budget credit.
- `Refuel Pod L`: `$150`, grants `$115.00` provider budget credit.

Budget credits are internal ArcLink provider-budget credits, not a promise that
Chutes itself has applied balance. Credit application, Stripe SKU IDs, live
purchase proof, and Chutes account top-up mechanics remain implementation and
live-proof work.

## Nextcloud Sharing Decision

ArcLink already has optional Nextcloud service/user-access plumbing. Nextcloud
has a documented OCS Share API for file/folder shares and WebDAV exposes shared
mount metadata and permissions. Ralphie should evaluate a Nextcloud-backed
living share adapter for Drive/Code right-click sharing where enabled, while
preserving ArcLink's owner approval, recipient login, no-reshare, audit,
revoke, and cross-user isolation rules.
