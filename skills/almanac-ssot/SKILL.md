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
- shared reads are filtered to the current user's owned / assigned records
- shared writes require a verified Notion identity before they can apply
- when the shared database exposes `Changed By`, Almanac stamps the verified
  human there automatically on every shared write
- Curator's self-serve verification claims live in a shared workspace database,
  so treat the claim metadata there as operator-visible workspace scaffolding,
  not as a secret channel
- if ownership is unclear, require approval before writing
- treat SSOT awareness as on-by-default for enrolled user agents
- prefer converging on current organizational state over inventing local shadow state

## Ownership Resolution

1. explicit `Owner` or `Assignee`
2. `created_by`
3. for plain pages, the user's own last human edit or this same agent's prior brokered write history
4. otherwise ask for approval

## Orientation

- you are operating inside a Curator-managed Almanac deployment shared by the organization
- the user attached to this agent is your primary working principal
- use SSOT to understand what is happening across the organization, then help your user orient, plan, and act inside that context
- do not assume you should write everywhere just because you can read broadly
- when SSOT and vault material overlap, use SSOT for live organizational state and qmd/vault retrieval for deeper background context

## Refresh Model

- Curator pushes a shared Notion digest into managed memory on the normal
  fanout cycle
- prefer webhook-driven refreshes
- tolerate delayed webhook delivery by using the hourly backstop state maintained by Almanac
- expect Almanac to batch and de-duplicate webhook-driven refresh work
- treat managed-memory SSOT summaries as ambient orientation and `ssot.read`
  as the depth rail when the user needs specifics

## Guardrails

- use the brokered `ssot.read` rail for shared Notion lookups rather than
  trying to reach the shared workspace directly
- write only on behalf of the user who owns the agent
- do not silently cross-edit records owned by another user
- do not fall back to "please touch the page again" when the page is already in the user's edit lane or this agent has already written there through the broker
- prefer append-only page notes when the user wants to add context to a shared
  page without taking ownership of existing text
- do not claim that native Notion history will show the human directly; it
  shows the Almanac integration while the row-level attribution lives in
  `Changed By` plus Almanac's local audit
- do not inspect other users' home directories or central deployment config to
  infer ownership; use the SSOT metadata and Almanac rails already exposed to
  this agent
- if a requested action would archive or delete content, stop and ask first
- if the requested change appears to touch another user's records, ask for approval instead of guessing; Almanac can now queue that approval instead of dropping the request
