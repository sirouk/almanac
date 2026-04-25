# Almanac Curator Onboarding Notes

Source: working transcription from a live Almanac Curator onboarding test.

## Purpose

Turn the Curator onboarding flow into a low-friction, catered experience where a user's agent feels prepared before first contact. The agent should already understand the person, the team, the company context, the source of truth, and its own directives.

The ideal experience is: "This was made for you." A user should not have to explain basic identity, role, team, repo, communication context, or how the company works if the operator already provided that information.

## Current Observations

- Vince tested the Almanac Curator onboarding through `/start`.
- Users who share a server with the Curator bot can DM it. The rest of the world likely cannot.
- The current opening question asks what the user should be called.
- After the name question, the current flow asks the user for context about themselves.
- That context question makes sense for a generic install, but for a team rollout it should usually be preloaded.
- The onboarding process already has a "first contact" stage where the new agent can be introduced to its tools, user, purpose, and operating context.
- Almanac already has strong bones for Notion, QMD, managed memory, hourly digestion, background refresh, dashboard access, Nextcloud, code workspace, remote Hermes access, and user-agent lanes.
- Hermes and vault documentation are version-pinned together; preserve that lockstep so vault docs match the running Hermes version.

## Product Direction

### Preloaded Team Context

The operator should be able to provide a preconfigured team or company knowledge source before users onboard.

Supported input shapes should include:

- A short text blurb.
- A single Markdown or text document.
- A folder or repo of team/company context.
- A richer knowledge base containing people, roles, accounts, repos, products, clients, team dynamics, and working doctrine.

When a user says "I'm Vince," the system should be able to resolve that to the known person profile:

- Preferred name.
- Role and position.
- Team responsibilities.
- GitHub/repo references.
- Twitter or other public account references when available.
- Social/account references when available.
- Product/domain ownership.
- Known collaborators.
- Relevant company/client context.
- White-glove onboarding context for clients.

### Agent Soul And Directives

Each agent should be born with a clear "soul" or doctrine document. This can remain a Markdown document, but it should behave like durable identity and purpose context for the agent.

The soul should include:

- The agent's purpose.
- The user it serves.
- The team it belongs to.
- The product and company context.
- The source of truth rules.
- Prime directives or behavioral directives.
- How it should help with focus and communication.
- How it should use skills, plugins, Notion, QMD, dashboard resources, and vault content.

The soul should make the agent feel like a helpful member of the Shoots team in agentic form.

### Core Bottlenecks To Solve

The agent should be oriented around solving two primary bottlenecks:

- Focus.
- Inter-team communication.

Expected behavior:

- Help the user stay focused.
- Keep the user aware of what other team members are doing.
- Perform morning check-ins.
- Check what other Almanac agents are reporting.
- Surface relevant team updates without being asked.
- Use background memory digestion and refreshed context so it arrives already informed.
- Couple the doctrine/soul to the existing morning check-in and background memory "drip" behavior; do not rebuild those mechanisms.

### Source Of Truth

Notion should be treated as the source of truth.

The agent should know:

- Notion is the primary SSOT.
- Local QMD/Notion mirrors can be used for fast local lookup.
- Before taking action, it should know where to check.
- It should derive decisions and updates from the canonical source when possible.

## Action Items

### Operator Setup

- [ ] Add an operator-side prompt for preloaded team/company context.
- [ ] Accept context as a blurb, single file, folder, or repo.
- [ ] Ingest that context before user onboarding begins.
- [ ] Use similarity search to match onboarding users to known people/profiles.
- [ ] Load matched person/team/company memories into the user's agent during birth.
- [ ] Add an operator interview flow that can prepare company context, crawl/collect public materials, and build the initial knowledge base.
- [ ] Treat Ian as the likely owner for the operator interview experience.
- [ ] Include a Marchetto-style front-loading path for company/business context.
- [ ] Consider a client-ready version for demos where company data is ingested ahead of time.

### First Contact

- [ ] Ensure first contact runs across Discord, Telegram, and remote CLI/TUI access.
- [ ] Do not ask for the user's name again if onboarding already collected or resolved it.
- [ ] Use first contact to introduce the agent to its user, tools, source of truth, and purpose.
- [ ] Load the preconfigured soul/directives before or during first contact.
- [ ] Add a Curator handoff at the end of onboarding so the user can immediately talk to the newly created bot/agent.
- [ ] If possible, have the user's bot initiate the first message or join the conversation automatically.

### Provider And Model Configuration

- [ ] Default to a centralized team-provided provider key.
- [ ] Keep bring-your-own-provider/key as an override only.
- [ ] Use one Shoots default provider/model setting unless the user explicitly overrides it.
- [ ] Change the prompt to something like: "Your team already provided a key. Press Enter to use it, or paste a different key/provider if you prefer."
- [ ] Track the shared-account funding plan separately; the session discussed Chris funding a shared account with an approximate $10k budget.
- [ ] Make sure provider credentials are not written into managed memory or long-lived visible messages.
- [ ] At the end of onboarding, remind users to scroll up and edit or delete messages that contained keys, since the bot cannot delete the user's own messages.

### Search

- [ ] Evaluate SearXNG as a local/standalone web search option.
- [ ] Test Docker installation.
- [ ] Confirm whether it can run without an external API service.
- [ ] Validate the expected 25-search-engine setup.
- [ ] Configure desired search engines by file if needed.
- [ ] Review country/locale and safe-search settings.
- [ ] Decide whether SearXNG should become the default team search backend.
- [ ] Use one Shoots search preset by default.

### Discord Onboarding Instructions

- [ ] Update Discord Developer Portal instructions to match the real UI order.
- [ ] Mention that Public Bot appears to be on by default and should remain on.
- [ ] Keep Require OAuth2 Code Grant off.
- [ ] Keep Presence Intent off unless specifically needed.
- [ ] Enable Server Members Intent before Message Content Intent in the instructions, matching the portal layout.
- [ ] Enable Message Content Intent.
- [ ] Explicitly tell the user to save changes before resetting or copying the bot token.
- [ ] Clarify the bot token step: use the reset-token action if needed, then copy the token. The portal may not initially show literal "Reset Token" copy.
- [ ] Do not use the top-left Installation link as the primary install path; it did not work reliably during the session.
- [ ] Put the basic bot/app setup and DM-oriented instructions in the top section.
- [ ] Move server installation steps into a separate optional section.
- [ ] Add a separate "run this bot in a server" section:
  - Go to OAuth2 -> URL Generator.
  - Generate/copy the Guild Install URL.
  - Open the URL and add the bot to the chosen server.
- [ ] Add a final instruction telling the user how to start talking to their bot after setup.

### Discord OAuth2 And Permissions

Working guild/server install path observed during the test:

- OAuth2 page.
- URL Generator.
- Scopes:
  - `bot`
  - `applications.commands`
- Integration type:
  - Guild Install.
- Bot permissions:
  - Send Messages.
  - Manage Messages.
  - Read Message History.
  - Use External Emojis.
  - Add Reactions.
  - Send Voice Messages.

Follow-up work:

- [ ] Verify the exact minimal guild/server permissions.
- [ ] Verify whether Manage Messages is truly needed.
- [ ] Find and document the correct user-install or DM-only flow.
- [ ] Keep the Guild Install URL as the confirmed working server path until DM-only user install is solved.
- [ ] Document that User Install still returned `Invalid scopes` during the session.
- [ ] Make newly created bots easy to find and message.
- [ ] Test whether user install with only `applications.commands` is enough for DMs.
- [ ] Test whether the bot can initiate a DM after user authorization.
- [ ] Make the flow seamless enough that users do not have to troubleshoot Discord app discovery.

### Telegram

- [ ] Add an onboarding option to configure another message channel after the first one is complete.
- [ ] Support Discord and Telegram through the same reusable loop.
- [ ] Consider making Telegram the recommended path if Discord remains too cumbersome.
- [ ] Explore whether the Curator can guide or automate more of the BotFather setup.

### Notion Access

- [ ] Verify the user can open the shared Almanac page in the organization's Notion workspace.
- [ ] Ensure the operator shares the Almanac Notion page with the user's Notion email in the organization workspace.
- [ ] If Notion says "request access," prompt the user to provide their Notion email.
- [ ] Route access requests to the operator/admin.
- [ ] Use Discord relative timestamp formatting for claim/access expiry messages instead of only a static printed time.
- [ ] Include a readable absolute time as a fallback if useful.
- [ ] Make it clear that Notion is the canonical source of truth for the agent.

### Dashboard And Web Access Messages

- [ ] Ensure dashboard and workspace links use HTTPS.
- [ ] Make clear that the generated password unlocks the Almanac dashboard.
- [ ] After the password message is deleted, visually separate the follow-up "web access" message.
- [ ] Add a horizontal rule or clear divider above the second message.
- [ ] Include dashboard URL, username, code workspace URL, Nextcloud username, workspace root, and Almanac vault path.
- [ ] Tell the user to save the generated password.
- [ ] Keep credentials out of managed memory.

### Code Workspace

- [ ] Verify code-server works after onboarding.
- [ ] Preserve or improve dark mode.
- [ ] Investigate browser/plugin freezes, but note that incognito worked during the test.
- [ ] Investigate the possible self-referential vault loop that may have contributed to the freeze.
- [ ] Root-cause the Vince-session bug where the Almanac vault symlink did not appear in the workspace sidebar.
- [ ] Make sure the Almanac vault appears in the workspace sidebar.
- [ ] Add a symbolic link to the Almanac vault so users can drag in documents, research, and repos.
- [ ] Prefer opening directly into the useful files/folder view instead of templates.
- [ ] Confirm integrated terminal workflows work, including cloning repos into the vault/workspace.

### Nextcloud

- [ ] Keep Nextcloud available for bulk file uploads and vault file management.
- [ ] Make the correct vault location obvious.
- [ ] Treat Nextcloud as complementary to the code workspace: easier for file drops, while code-server is better for editing, terminal work, and repo operations.

### Remote Hermes Helper

- [ ] Confirm the home-route `curl` command sets up macOS, Linux, and Windows WSL2 clients.
- [ ] Simplify the remote helper output.
- [ ] Present only the ED25519 `/ssh-key ssh-ed25519 ...` reply variant as the obvious copy/paste path.
- [ ] Avoid making the raw public key look like the primary thing to send.
- [ ] Strip extra verbosity from the remote-helper TUI output.
- [ ] After key acceptance, verify `hermes-<tab>` completion exposes the generated wrapper binary in a new terminal.
- [ ] Investigate the `No such file or directory` error seen when running the generated `hermes-*` wrapper after `remote_agent_key_installed`.
- [ ] Root-cause whether the failure is related to invoking the wrapper without the full `chat` segment.
- [ ] Confirm the repair path that fixed the live agent is captured in code/tests.
- [ ] Verify the wrapper works from macOS, Linux, and Windows WSL.
- [ ] Verify `hermes-<agent> chat` or the equivalent starts the correct remote Hermes session.
- [ ] Explore a branded TUI onboarding experience, potentially using an animation library similar to Codex's terminal UI.

### Error Handling

- [ ] When onboarding errors happen, have the Curator inspect logs, state, and database records where available.
- [ ] Give the user a useful diagnosis or story instead of a dead end.
- [ ] Reuse the pattern from the one-to-one event work where the agent pieces together user-specific issues from records.

### Skills And Vault Content

- [ ] Flesh out the shared skills folder.
- [ ] Add reusable Shoots skills for management, marketing, blog/content generation, LinkedIn posts, onboarding, and Curator behavior.
- [ ] Store team skills in the vault so agents can discover and use them.
- [ ] Keep the model simple: skills are recipes/instructions, plugins are durable code/tools.
- [ ] Keep capability additions in skills or plugins; do not modify Hermes core for these features.
- [ ] Consider an Almanac-specific skill bundle and Curator-specific skill bundle.

### Client/Company Demo Path

- [ ] Prototype a company ingestion flow using a real client dataset.
- [ ] Build the Probrutes SQL-to-Almanac demo path before the Thursday `:30` meeting.
- [ ] Hook the Probrutes SQL database up to Almanac rather than directly to Hermes.
- [ ] Build skills that interpret the company database and expose useful business answers.
- [ ] Consider connecting Hermes/Almanac to a company SQL database through a secure local path.
- [ ] Design a secure deployment shape where a small on-prem box connects to internal systems over a controlled wired/VPN connection.
- [ ] Explore the "AI in a box" appliance idea:
  - Small local machine.
  - 3D-printed or branded shell.
  - Internal hardware can change while external form factor stays consistent.
  - Server-rack or cable-box style deployment.
  - Ship the box to the customer and have them return it on cancellation, similar to a cable-company hardware model.

## Informational Notes

### Curator As Shared Bot Versus Separate Bots

One option is to make the Curator act as each user's bot and isolate behavior by user. That may work technically because conversations can be locked to user lanes, but it could hit rate limits or become operationally messy.

The preferred path for the current scale appears to be separate bots per agent/user.

### Managed Memory And Background Context

The system already has pieces for:

- Hot-reloaded managed memories.
- Background context refresh.
- Hourly digestion.
- Per-agent context relative to the user and their agent.
- Curator brief fanout.

The directive/soul layer should pair with these existing mechanisms instead of replacing them.

### Version Lockstep

Almanac should preserve the current version-pinning behavior where vault documentation stays aligned with the actual Hermes version running for the user.

### Vault Vision

The vault should become the user's practical workspace for:

- Documents.
- Research.
- Repos.
- Skills.
- Company and team context.
- Agent-specific working material.

Users should be able to put things in the vault through either Nextcloud or the code workspace.

### Desired User Experience

The goal is a sci-fi-grade first experience: the agent already knows the user's role, team, context, and tools, then immediately starts helping.

The experience should be useful enough that skeptical team members see value without needing to configure much themselves.

### Implementation Boundary

Almanac should harness Hermes through skills, plugins, vault context, and onboarding scaffolding. Do not touch Hermes core for these capability additions unless a future task explicitly requires it.

## Open Questions

- What is the exact minimal Discord permission set for guild/server installs?
- What is the correct Discord user-install or DM-only flow for a brand-new bot?
- Can a newly created Discord bot initiate a DM after authorization, or does the user need to message it first?
- Should Telegram become the default recommended messaging path?
- Where should the operator-provided team/company document live by default?
- Should the soul/directives be stored in the vault, generated into Hermes memory, or both?
- How much of the company ingestion flow should happen during operator onboarding versus after install?
- What is the default centralized provider account/key strategy for the Shoots team?
- Which SearXNG engines and safe-search defaults should be used?
- Who owns the shared provider account budget and key rotation policy?
- What exact time zone applies to the Thursday `:30` Probrutes demo target?

## Suggested Implementation Order

1. Update Discord onboarding instructions and tests around the known guild install path.
2. Fix first contact so it does not re-ask known identity and works across Discord and remote CLI/TUI.
3. Add the operator-provided team/company context input.
4. Load matched person profiles and soul/directives during agent birth.
5. Improve web access, password, and remote helper messages.
6. Add vault symlink visibility in code-server.
7. Add centralized provider-key support.
8. Investigate Discord DM-only/user-install and Telegram as a simpler channel.
9. Add Curator error diagnosis from logs/state/database records.
10. Prototype the Probrutes SQL-to-Almanac demo flow and company ingestion path.
