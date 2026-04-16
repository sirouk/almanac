---
name: almanac-vaults
description: Use to inspect the active Almanac vault catalog, show subscribed vs default vaults, and opt in or out of ambient-awareness subscriptions without changing qmd retrieval access.
---

# Almanac Vaults

Use this skill when an enrolled user wants to manage Almanac vault subscriptions.

## Contract

- all approved users may retrieve from any active vault through qmd
- subscriptions only affect managed-memory awareness and Curator push behavior
- active vaults come from valid `.vault` files in the shared vault tree
- missing or malformed `.vault` files fail safe and should be surfaced as warnings

## Operations

- list the vault catalog with:
  - vault name
  - description
  - owner
  - default subscription state
  - current subscription state
- opt into a vault
- opt out of a vault
- trigger a refresh after a subscription change

## Guardrails

- do not edit `.vault` files unless the user explicitly asks
- do not treat qmd access as revoked when a user unsubscribes from a vault
- if a vault listed in memory no longer exists in the catalog, treat that as drift and refresh before answering
