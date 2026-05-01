# Ralphie Steering: Executor Idempotency Digest Repair

The current BUILD slice must not proceed as complete until the fake Docker
Compose executor closes the lint blocker from the previous gate.

Required repair:

- Bind every fake Docker Compose run state to the rendered `intent_digest`.
- When an explicit `idempotency_key` is reused with a different intent digest,
  raise `ArcLinkExecutorError` instead of returning an idempotent replay.
- Cover both cases with regression tests:
  - changed intent after a fully applied run
  - changed intent after a partial failed run
- Keep `services` deterministic and stable for summaries; use
  `service_start_order` for dependency-aware apply order.
- Do not claim the provider/edge/rollback fake executor slice is complete until
  the digest mismatch tests fail before the fix and pass after it.

Do not enable real Docker, Cloudflare, Chutes, Stripe, or host mutation in this
repair. Keep the no-secret/fake-adapter boundary intact.
