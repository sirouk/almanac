# Public Agent Gateway Performance Plan

Status: 2026-05-11 implementation note after live-trigger repair.

## Current Truth

ArcLink public Telegram and Discord webhooks are now a fast ingress path:

- The webhook handler acknowledges the platform after Raven/public-bot routing.
- Selected-agent messages are persisted as `notification_outbox` rows with
  `target_kind=public-agent-turn`.
- The API process only runs a bounded in-process live trigger when it can
  actually reach the local Docker API. In Dockerized Control Node mode, the
  API container deliberately does not mount `/var/run/docker.sock`, so it
  leaves the turn on the durable queue.
- The Docker-capable `arclink-notification-delivery` worker polls once per
  second, claims the row, and delivers through the selected deployment's
  Hermes gateway container.
- If the live trigger is disabled, unavailable, saturated, or fails to submit,
  the durable `arclink-notification-delivery` worker still owns delivery.
- Claim/lease logic prevents live triggers and polling workers from delivering
  the same row twice.
- The legacy quiet CLI fallback is fail-closed by default. Operators must set
  `ARCLINK_PUBLIC_AGENT_QUIET_FALLBACK=1` before ArcLink will knowingly deliver
  a degraded text-only response instead of surfacing a gateway-bridge failure.

This is good enough for responsive single-node text/command operation, but it
is not the final high-throughput gateway architecture. The current
selected-agent bridge still shells into the target deployment's
`hermes-gateway` container and starts `arclink_public_agent_bridge.py` for each
delivered turn. That preserves the Hermes message pipeline for text, slash
commands, typing, reactions, and streaming, but it is too expensive to treat as
the final load-balanced design and does not yet carry every native Telegram or
Discord event type. See `research/PUBLIC_AGENT_GATEWAY_PARITY_AND_SCALE_AUDIT.md`.

## Immediate Backpressure Contract

`python/arclink_hosted_api.py` uses these controls:

- `ARCLINK_PUBLIC_AGENT_LIVE_TRIGGER=1`
- `ARCLINK_PUBLIC_AGENT_LIVE_TRIGGER_RUNNER=auto`
- `ARCLINK_PUBLIC_AGENT_LIVE_TRIGGER_WORKERS=4`
- `ARCLINK_PUBLIC_AGENT_LIVE_TRIGGER_MAX_PENDING=64`

The live trigger must never block webhook ingress and must never spawn
unbounded threads. It must also never force Docker access into API ingress.
Saturation or local-runner unavailability is acceptable because the
notification row is already durable; the delivery worker owns the real
trusted-host execution path.

## Target Load-Balanced Shape

The production gateway should move toward this shape:

1. Stateless ingress replicas receive Telegram and Discord webhooks behind the
   operator's chosen load balancer or ingress layer.
2. Ingress validates the platform request, resolves Raven/account/deployment
   state, writes a durable queue row, and returns quickly.
3. Dispatcher replicas claim queued rows with leases. On a single node, SQLite
   claims are acceptable. For multi-node operation, move the queue/lease state
   to Postgres or another shared durable queue with equivalent compare-and-set
   claims.
4. Dispatcher concurrency is bounded globally and per deployment/session so a
   chat gets Hermes turns in order.
5. Each deployment exposes an internal-only warm bridge endpoint, such as an
   HTTP, gRPC, or Unix-socket service inside the deployment network.
6. The warm bridge imports Hermes gateway code once, keeps platform adapters
   warm, and accepts synthetic platform events for Telegram/Discord without a
   per-message `docker exec` and Python import cycle.
7. The event envelope preserves full native parity where the platform allows it:
   text, slash commands, reply context, message ids, attachments/media,
   callback/query ids, thread/channel metadata, typing/reaction hooks, and
   platform send/edit/media operations.
8. Raven controls remain namespaced. Active-agent commands and normal messages
   route through the selected deployment only after user/deployment/linkage
   authorization is verified.
9. Observability records queue depth, live-trigger saturation, claim latency,
   turn duration, bridge failures, platform send failures, and per-deployment
   backpressure.

## Non-Negotiables

- Do not bypass Hermes gateway semantics just to reduce latency. Reactions,
  typing, command handling, session behavior, and platform formatting are part
  of the user contract.
- Do not allow direct public access to deployment bridge endpoints.
- Do not process more than one turn for the same public chat/session at the
  same time unless Hermes explicitly supports that conversation model.
- Do not let API ingress own long-running model work without a bound and a
  durable recovery path.

## Next Build Task

Replace the per-turn container bridge with a warm internal public-agent bridge
service. Keep the current durable outbox and claim/lease semantics, but make
the delivery worker call the warm bridge endpoint instead of starting a fresh
process for every turn.
