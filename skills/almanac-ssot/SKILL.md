---
name: almanac-ssot
description: Use to connect an enrolled user agent to a shared Notion SSOT workspace with read, insert, and update rails while refusing archive/delete by default.
---

# Almanac SSOT

Use this skill when the task is about the shared organizational source of truth
that Almanac agents converge around.

The SSOT in Almanac is a shared Notion workspace. Curator and the enrolled
user agents operate from one common deployment, but each user agent still acts
on behalf of one user. Use this skill to stay aware of the organization,
current work, and user-scoped responsibilities without treating the SSOT as a
free-for-all edit surface.

## Default Rails

- allow read / insert / update
- do not archive
- do not delete
- if ownership is unclear, require approval before writing
- treat SSOT awareness as on-by-default for enrolled user agents
- prefer converging on current organizational state over inventing local shadow state

## Ownership Resolution

1. explicit `Owner` property
2. `created_by`
3. otherwise ask for approval

## Orientation

- you are operating inside a Curator-managed Almanac deployment shared by the organization
- the user attached to this agent is your primary working principal
- use SSOT to understand what is happening across the organization, then help your user orient, plan, and act inside that context
- do not assume you should write everywhere just because you can read broadly
- when SSOT and vault material overlap, use SSOT for live organizational state and qmd/vault retrieval for deeper background context

## Refresh Model

- prefer webhook-driven refreshes
- tolerate delayed webhook delivery by using the hourly backstop state maintained by Almanac
- expect Almanac to batch and de-duplicate webhook-driven refresh work

## Guardrails

- write only on behalf of the user who owns the agent
- do not silently cross-edit records owned by another user
- do not inspect other users' home directories or central deployment config to
  infer ownership; use the SSOT metadata and Almanac rails already exposed to
  this agent
- if a requested action would archive or delete content, stop and ask first
- if the requested change appears to touch another user's records, ask for approval instead of guessing
