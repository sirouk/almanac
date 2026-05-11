# Public Agent Gateway Parity And Scale Audit

Status: 2026-05-11 code audit after Raven active-agent bridge repair and
Telegram native-update replay.

## Current Truth

ArcLink no longer treats public Telegram/Discord agent chat as a simple Raven
text relay. Once a user is aboard, Raven queues normal messages and non-Raven
slash commands as durable `public-agent-turn` rows
(`python/arclink_public_bots.py:1717`). The delivery worker then tries to run
the selected deployment through Hermes' gateway event pipeline
(`python/arclink_notification_delivery.py:348`), using
`python/arclink_public_agent_bridge.py`.

This gives current public-channel chat these real Hermes properties:

- Hermes session handling, plugin hooks, MCP/bootstrap context, model runtime,
  command parsing, and selected-agent state.
- Telegram text and slash turns carry the original update JSON and are replayed
  through Hermes' own Telegram adapter handlers when available.
- Telegram media, location/venue, and non-Raven callback queries now follow the
  same native Hermes Telegram handler path in the bridge.
- Discord text turns are passed as `MessageType.TEXT`.
- Discord slash turns are passed as `MessageType.COMMAND`.
- Gateway streaming is enabled for public bridge turns unless explicitly
  disabled (`python/arclink_public_agent_bridge.py:78`).
- Discord reactions are available through a raw-message shim with
  `add_reaction` and `remove_reaction`
  (`python/arclink_public_agent_bridge.py:227`).
- Discord typing and message edits are wired through REST shims
  (`python/arclink_public_agent_bridge.py:293`).
- Telegram uses Hermes' Telegram adapter with a real Telegram `Bot`
  (`python/arclink_public_agent_bridge.py:157`), so normal sends, edits,
  typing, and reactions use the native adapter path.

The degraded `hermes chat -Q` path is now fail-closed by default. It can only
run when an operator explicitly sets `ARCLINK_PUBLIC_AGENT_QUIET_FALLBACK=1`,
because that path severs native platform behavior
(`python/arclink_notification_delivery.py:464`).

## Parity Gap

This is not full native Telegram/Discord parity yet. Telegram is now much
closer because raw updates replay through Hermes' adapter. Discord still creates
synthetic per-turn events and only carries text, slash command text, source ids,
and basic reply/message ids into Hermes:

- Discord bridge event: `python/arclink_public_agent_bridge.py:354`.
- Telegram public ingress preserves raw update JSON for active-agent delivery.
  Direct Hermes appears to handle location/venue plus media/sticker/callbacks;
  contact and poll remain product-extension territory unless upstream Hermes
  adds native handlers.
- Discord public ingress currently parses slash commands, components, and plain
  content; it does not carry attachments/voice/thread/member objects into the
  bridge payload (`python/arclink_discord.py:241`).

Hermes itself supports richer native events. In the deployed Hermes runtime,
`MessageEvent` carries `raw_message`, `media_urls`, `media_types`,
`reply_to_*`, `auto_skill`, and `channel_prompt`
(`/opt/arclink/runtime/hermes-agent-src/gateway/platforms/base.py:869`).
Native Telegram registers media and callback handlers, including photo, video,
audio, voice, documents, stickers, and callback queries
(`/opt/arclink/runtime/hermes-agent-src/gateway/platforms/telegram.py:980`).
Native Discord has a long-lived `discord.py` adapter with `on_message`, voice
state handlers, voice receivers, slash sync, file/image/document send helpers,
and reaction methods
(`/opt/arclink/runtime/hermes-agent-src/gateway/platforms/discord.py:128`).

## Features Currently Severed Or Degraded By The Substrate

These are the functions that do not yet have full "as if Hermes were directly
connected" parity:

- Telegram contact and poll updates are still not full parity unless Hermes
  itself grows native handlers for them. ArcLink surfaces them as active-agent
  update placeholders today, not rich structured native events.
- Discord inbound attachments/files/images are not passed into Hermes as
  attachment-backed media/document events.
- Discord voice channel/listening features cannot work through the current
  webhook-plus-per-turn bridge, because Hermes' native Discord voice support is
  tied to a long-lived gateway connection and `VoiceReceiver`.
- Discord native interaction objects and full guild/member/channel/thread
  objects are not available to Hermes; the bridge supplies a minimal source and
  REST send/edit/reaction shim.
- Long-lived adapter state is rebuilt per turn. That works for text and
  commands, but is too expensive for massive scale and cannot preserve every
  live adapter feature.

## Scale Gap

The current control-node shape is durable and bounded:

- Public webhook ingress writes a durable queue row and returns quickly.
- Live triggers are bounded and only run where Docker access actually exists.
- The Docker-capable `notification-delivery` worker claims rows with leases and
  polls once per second.

The non-final part is the per-turn bridge process. For every public agent turn,
the worker currently shells into the deployment's `hermes-gateway` container and
starts `arclink_public_agent_bridge.py`. That preserves the Hermes turn path,
but it is not the massive-scale shape.

The target production shape remains a warm internal bridge service per
deployment or per deployment pool:

- Import Hermes once and keep adapters/session stores warm.
- Accept authorized synthetic Telegram/Discord events over an internal-only
  Unix socket, HTTP, or gRPC endpoint.
- Preserve ordered per-chat/session processing.
- Carry full event envelopes: text, commands, reply context, media descriptors,
  attachments, callback/query ids, thread/channel metadata, and platform
  identity.
- Expose platform send/edit/reaction/typing/media operations through the same
  adapter surface Hermes expects.
- Keep Raven controls namespaced, but let active-agent messages and active-agent
  slash commands behave like direct Hermes chat.

## Non-Negotiable Next Build

Do not optimize by routing around Hermes. The next build should replace the
per-turn `docker exec` helper with a warm public-agent gateway service and
extend the ingress payloads to carry media/attachment/callback metadata. Until
that exists, ArcLink should be honest that text, slash commands, typing,
reactions, and streaming are supported, while native media and Discord voice are
not full-parity yet.
