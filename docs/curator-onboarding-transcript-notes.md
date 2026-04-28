# Almanac Curator Onboarding Design Notes

This public note captures generic product lessons from onboarding tests. Do not
store live operator names, org rosters, budgets, transcript excerpts, repo
inventories, or role-specific context here. Session-derived notes belong in the
private state repo or vault and should be summarized into generic behavior
before they are promoted to public docs.

## Status

This file is a design backlog, not the source of shipped behavior. Use
`README.md`, `AGENTS.md`, and the implementation/tests for the current operating
contract.

Several ideas captured through onboarding work have shipped in some form:
org-provided model credentials, per-agent `SOUL.md` seeding, managed context
injection, Discord completion handoff with a confirmation code, Telegram
`/start` handoff, private agent backup setup, Notion identity verification,
dashboard/code/vault resource messages, Nextcloud vault access, and the
`~/Almanac` workspace alias.

Still not shipped as a complete pipeline: automatic ingestion of an operator
profile into control-plane rows, profile-driven SOUL/managed-memory
distribution, profile-sourced resource manifests, web-search backend setup, and
demo data generation for local proof runs.

## Purpose

Turn Curator onboarding into a low-friction, catered experience where each
agent feels prepared before first contact. The agent should already understand
the person it serves, the operating context, the source-of-truth rules, and its
own boundaries when the operator has provided that information.

The ideal first impression is: "This was made for this context." A user should
not have to explain basic identity, role, household/team/project context, repo
locations, communication handles, or source-of-truth rules if the operator
already provided them through the private profile ingestion path.

## Product Direction

### Preloaded Operating Context

The operator should be able to provide a preconfigured knowledge source before
users onboard.

Supported input shapes should include:

- A short text blurb.
- A single Markdown or text document.
- A folder or repo of operating context.
- A richer profile containing people, roles, accounts, repos, projects,
  recurring workflows, boundaries, source pointers, and working doctrine.

When a user identifies themself, the system should be able to resolve that to a
known private person/profile record when one exists:

- Preferred name.
- Role and responsibilities.
- Relevant GitHub/repo references.
- Discord handle and optional platform identifiers.
- Public or social context when the operator has provided it.
- Known collaborators.
- Relevant project, family, client, or organization context.

### Agent Soul And Directives

Each agent should be born with a clear doctrine document. This can remain
Markdown, but it should behave like durable identity and purpose context for the
agent.

The doctrine should include:

- The agent's purpose.
- The person or operating unit it serves.
- The broader project, family, team, or organization context.
- Source-of-truth rules.
- Prime directives and boundaries.
- Communication and focus preferences.
- How it should use skills, plugins, Notion, qmd, dashboard resources, and
  vault content.

### Core Bottlenecks To Solve

The agent should be oriented around the bottlenecks named by the operator in the
private profile. Common examples:

- Focus.
- Cross-person communication.
- Remembering recurring workflows.
- Retrieving source-backed context.
- Turning meeting notes and decisions into governed source-of-truth updates.

Expected behavior:

- Help the user stay focused.
- Keep the user aware of relevant updates.
- Perform check-ins when configured.
- Use background memory digestion and refreshed context.
- Couple doctrine to the existing check-in and background memory paths instead
  of rebuilding those mechanisms.

## Action Items

### Operator Setup

- [ ] Keep org, family, solo, and project profile data in private state.
- [ ] Accept context as a blurb, single file, folder, or repo.
- [ ] Ingest that context before user onboarding begins.
- [ ] Use profile matching to resolve onboarding users to known people.
- [ ] Load matched person and context modules into the user's agent during
      birth.
- [ ] Generate private resource manifests from the profile ingestion document.
- [ ] Keep public docs limited to generic behavior and fictional examples.

### First Contact

- [ ] Ensure first contact runs across Discord, Telegram, and remote CLI/TUI
      access.
- [ ] Do not ask for the user's name again if onboarding already collected or
      resolved it.
- [ ] Use first contact to introduce the agent to its user, tools, source of
      truth, purpose, and boundaries.
- [ ] Load doctrine before or during first contact.
- [ ] Add a Curator handoff at the end of onboarding so the user can
      immediately talk to the newly created bot/agent.

### Provider And Model Configuration

- [ ] Support a centralized operator-provided provider key.
- [ ] Keep bring-your-own-provider/key as an override.
- [ ] Track shared-account or budget plans privately, never in public docs.
- [ ] Keep provider credentials out of managed memory and long-lived visible
      messages.
- [ ] Remind users to edit or delete chat messages that contained keys when a
      chat platform does not allow the bot to delete user messages.

### Discord Onboarding Instructions

- [ ] Keep the Discord Developer Portal instructions current.
- [ ] Make DM-oriented setup the primary path when supported.
- [ ] Put guild/server installation steps in a separate optional section.
- [ ] State the minimal required intents and permissions.
- [ ] Tell the user how to start talking to their bot after setup.

### Notion Access

- [ ] Verify the user can open the shared Almanac page in the configured
      workspace.
- [ ] Route access requests to the operator/admin.
- [ ] Use Discord relative timestamps for claim/access expiry messages when
      available.
- [ ] Make clear that Notion is the canonical source of truth when configured.

### Dashboard, Vault, And Workspace

- [ ] Keep dashboard and workspace links HTTPS when exposed through a tailnet.
- [ ] Make clear which password unlocks the Almanac dashboard.
- [ ] Keep credentials out of managed memory.
- [ ] Ensure the vault is visible in the code workspace and file-drop surface.
- [ ] Keep Nextcloud available for bulk file uploads when enabled.

### Remote Hermes Helper

- [ ] Confirm the home-route setup command works on macOS, Linux, and Windows
      WSL2 clients.
- [ ] Present the public-key reply path clearly.
- [ ] Verify the generated wrapper works after key acceptance.
- [ ] Keep remote helper URLs configurable instead of tied to a public repo
      default.
