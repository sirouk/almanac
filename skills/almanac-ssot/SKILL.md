---
name: almanac-ssot
description: Use to connect an enrolled user agent to a shared Notion SSOT workspace with read, insert, and update rails while refusing archive/delete by default.
---

# Almanac SSOT

Use this skill for Notion-backed SSOT tasks.

## Default Rails

- allow read / insert / update
- do not archive
- do not delete
- if ownership is unclear, require approval before writing

## Ownership Resolution

1. explicit `Owner` property
2. `created_by`
3. otherwise ask for approval

## Refresh Model

- prefer webhook-driven refreshes
- tolerate delayed webhook delivery by using the hourly backstop state maintained by Almanac

## Guardrails

- write only on behalf of the user who owns the agent
- do not silently cross-edit records owned by another user
- if a requested action would archive or delete content, stop and ask first
