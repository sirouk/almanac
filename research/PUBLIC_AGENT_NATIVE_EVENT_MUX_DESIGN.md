# Public Agent Native Event Mux Design

Status: 2026-05-11 design and first implementation slice.

## Problem

Raven and an active Hermes agent share the same public Telegram or Discord
conversation. Telegram only allows one active webhook or polling consumer for a
bot token, and Discord slash commands, message events, attachments, and voice
all belong to one bot application identity. Running Raven and Hermes as two
independent platform adapters would either conflict at the provider or require
ArcLink to re-implement Hermes' platform code.

The maintainable target is therefore not two bots and not an ArcLink clone of
Hermes adapters. The target is a native-event mux:

1. A platform edge owns the public bot token and receives the real provider
   events.
2. Hermes' own Telegram and Discord adapter code parses those events into
   Hermes event semantics.
3. ArcLink routes Raven-owned controls to Raven and active-agent events to the
   selected deployment.
4. The selected deployment runs a warm Hermes gateway runner and consumes the
   event envelope without a per-message import/exec cycle.
5. Platform egress operations such as send, edit, typing, reactions, files,
   callbacks, and voice remain implemented by Hermes adapters or by narrow
   proxy objects that call the platform edge.

## First Slice Now Implemented

Telegram active-agent turns now preserve the original Telegram update JSON from
public ingress into `public-agent-turn` metadata. The deployment bridge rebuilds
the PTB `Update` and dispatches it to Hermes' own Telegram adapter handlers:

- `_handle_text_message` for normal text,
- `_handle_command` for slash commands,
- `_handle_location_message` for location and venue pins,
- `_handle_media_message` for photos, video, audio, voice, documents, and
  stickers,
- `_handle_callback_query` for non-Raven inline callbacks.

This keeps ArcLink out of Telegram media download, caption, document, sticker,
callback, batching, and reaction details. As Hermes updates those handlers,
ArcLink follows them.

Raven callbacks remain under the `arclink:` callback namespace. Non-Raven
callbacks are active-agent events.

## Remaining Native Mux Build

### Warm Deployment Bridge

Replace per-turn `docker exec python arclink_public_agent_bridge.py` with a
warm internal service inside each deployment:

- import Hermes once,
- keep `GatewayRunner`, adapters, session store, and model/client cache warm,
- accept authorized events over an internal-only Unix socket, HTTP, or gRPC
  endpoint,
- enforce per-chat ordering and deployment-level backpressure,
- expose health, queue depth, and adapter ABI fingerprints.

The current durable outbox and lease/claim worker stay. Only the delivery
target changes from "start a process" to "post an event to the warm bridge."

### Discord Native Edge

Discord cannot reach full parity through interaction webhooks alone. A
long-lived Discord gateway client is required for:

- message attachments and CDN-backed file/image objects,
- full guild/member/channel/thread object context,
- voice state events,
- voice listening and playback,
- native slash defer/edit-original behavior,
- durable adapter state.

The edge should run Hermes' Discord adapter with a router handler rather than a
normal agent handler. The router handler decides:

- `/raven` and other Raven namespace controls go to Raven,
- bare Hermes slash commands and normal messages go to the active deployment,
- unsupported or unauthorized events fail closed.

For active-agent delivery, either:

- forward a serialized Hermes `MessageEvent` plus cached media blobs to the
  deployment warm bridge, or
- forward a provider-native event plus an edge media fetch token when Hermes
  can safely reconstruct the event in the deployment.

Use an opaque raw-message proxy for Discord reactions and edits when the
deployment does not hold the original `discord.py` message object. The proxy
should call the edge service, not reimplement Discord behavior in the
deployment.

### Telegram Edge

Telegram can continue to use the control API webhook, but the native-event mux
version should still route through a Hermes Telegram adapter instance with an
ArcLink router handler. The current raw-update replay is the bridge-compatible
form of the same idea.

### Reasoning Display

Reasoning display is a product policy switch, not a parity bug. The bridge now
forces Hermes streaming on for public-agent turns, but it deliberately does not
force `show_reasoning`. If the operator wants public channels to show thinking,
add an explicit ArcLink setting and surface it in user/admin controls.

## ABI Guardrails

Add tests that load the pinned Hermes runtime and assert that:

- `gateway.platforms.base.MessageEvent` still has the fields ArcLink serializes,
- Telegram adapter still exposes the native handlers ArcLink calls,
- Discord adapter still exposes the message, slash, send, edit, typing,
  reaction, media, and voice hooks needed by the edge,
- ArcLink fails closed and alerts the operator after a Hermes upgrade if any
  required surface changes.

This gives ArcLink a small compatibility contract with Hermes instead of a fork.

