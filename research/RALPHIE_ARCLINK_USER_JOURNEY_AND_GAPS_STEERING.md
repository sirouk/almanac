# Ralphie Steering: ArcLink User Journey And Gap Atlas

## Mission

Create the full ArcLink user-journey atlas and the corresponding gap register.

Primary deliverables:

- `USER_JOURNEY.md`: the complete first-sweep story of ArcLink as the product
  should feel when every intended rail is in place. It may describe the ideal
  product contract, but it must avoid pretending unproven live behavior is
  already verified.
- `GAPS.md`: the rigorous source-grounded register of every actual missing,
  partial, proof-gated, policy-gated, risky, underspecified, or under-tested
  joint discovered while comparing that story against code, tests, docs,
  service units, configuration, and scripts.

Use both engines. Codex should drive the main pass when healthy, while Claude
must participate through mixed consensus review. If either engine is unhealthy,
stop rather than silently reducing this mission to a single-engine pass.

## Audit Independence (disprove, do not confirm)

This is an adversarial gap hunt, not a reformat of prior optimism.

- Treat `research/PRODUCT_REALITY_MATRIX.md` counts (eg. "0 gap, 0 partial",
  "N real") as an UNVERIFIED CLAIM TO DISPROVE, never a starting truth. Do not
  copy its rows. Independently re-confirm or knock down each claim against
  source, and actively hunt for net-new gaps the matrix missed.
- A `real` claim with thin, missing, or absent local evidence is itself a gap.
  Demote it and record why.
- The root `USER_JOURNEY.md` and `GAPS.md` start as intentional stubs. Generate
  them from fresh source evidence; do not merely polish the stub text.
- The seed drafts `research/seed-user-journey-draft.md` and
  `research/seed-gaps-draft.md` are INPUT ONLY — prior v0 material, not a
  baseline to preserve. Improve on, contradict, or discard them as evidence
  dictates.

## Guardrails

- Read `AGENTS.md` first.
- Do not read `arclink-priv/`, user homes, secret files, deploy keys, `.env`
  values, OAuth stores, bot tokens, or live credentials.
- Do not run live deploy/install/upgrade, Stripe, Chutes, Telegram, Discord,
  Notion, Cloudflare, Tailscale, SSH fleet mutation, Docker mutation, or host
  mutation unless the operator explicitly authorizes that later.
- Prefer `rg` and focused file reads.
- Keep public docs free of secrets, local absolute paths, and tool transcripts.
- Do not edit Hermes core to close ArcLink gaps.
- Do not overclaim. Mark live/external behavior as proof-gated when local code
  cannot prove it.

## Required User-Journey Coverage

`USER_JOURNEY.md` must cover at least these surfaces, including happy paths,
choice points, alternate paths, error paths, retry paths, access boundaries,
and handoffs:

- Public entry: website, Telegram, Discord, returning visitor, linked channel,
  mobile and desktop.
- Public Raven: first contact, identity, channel safety, onboarding answers,
  checkout opening, post-onboarding control commands, agent selection, channel
  linking, status, upgrade guidance, Notion prep, backup prep, share approvals,
  selected-agent chat, and command namespace conflicts.
- Billing: plan selection, Limited 100 Founders, Sovereign, Scale, additional
  agents, failed renewal, suspension, daily warnings, day-7 removal warning,
  day-14 audited purge queue, cancellation, refuel credits, and proof-gated
  live payment rails.
- Deployment: entitlement gate, provisioning-ready transition, fleet placement,
  single-machine, remote fleet, domain ingress, Tailscale ingress, DNS/Traefik,
  worker execution, rollback, teardown, health, notification, and handoff.
- Credentials: generation, one-time handoff, copy/store instruction,
  acknowledgement, post-ack hiding, reissue/rotation/recovery, and dashboard
  entry.
- User dashboard: account, deployment, service health, billing, provider state,
  communications, credential handoff, workspace readiness, recovery actions,
  dashboard-to-Hermes links, and unavailable states.
- Hermes and agents: user-agent homes, Curator, ArcPod Hermes homes, gateway
  run mode, private chat channels, Telegram `/start`, Discord handoff retry,
  dashboard plugins, skills, provider/model choice, and safe refresh.
- Knowledge: vault, qmd, PDF sidecars, Notion indexed markdown, SSOT broker,
  webhook/batcher, memory synthesis, recall stubs, daily plate, governed
  managed context, retrieval tools, and Almanac lineage terminology.
- Workspace: Drive, Code, Terminal, root guards, linked resources, read-only
  projections, accepted shares, no reshare, copy/duplicate into owned space,
  audit, revoke, and disabled browser share-link UI where unimplemented.
- Admin/operator: exactly one operator, admin dashboard, action worker,
  shared-host install/upgrade, Docker shared-host mode, Sovereign Control Node,
  service units, health checks, release state, deploy keys, component pins,
  component upgrades, live proof, backups, enrollment reset, org profile, and
  notification delivery.
- Security and isolation: one user cannot read, infer, mutate, route to, or
  share another user's private deployment, channels, dashboard, provider state,
  Notion/SSOT data, files, Stripe state, or Hermes resources.

## Required Gap Register Coverage

`GAPS.md` must include:

- A status taxonomy: `gap`, `partial`, `proof-gated`, `policy-question`,
  `test-gap`, `doc-gap`, `ux-gap`, `ops-gap`, `security-risk`, and `real`.
- A severity taxonomy: P0 blocks trust/security/payment/provisioning; P1 blocks
  a core journey; P2 causes degraded or confusing behavior; P3 is polish or
  future scale.
- A row for each gap or non-real item with: id, severity, journey joint,
  expected behavior, actual evidence, source references, missing proof/tests,
  user impact, likely owner/surface, and recommended next repair.
- A separate "Not Gaps / Already Real" section for important surfaces that were
  checked and found covered, so future readers know the audit looked there.
- A "Proof Gates" section listing exact live credentials or authorized proof
  runs required before claims can move to `real`.
- A "Policy Questions" section listing choices code cannot decide.
- A "Test Plan" section with focused local checks for every code-owned gap.

## Must-Inspect Sources

At minimum inspect:

- `AGENTS.md`, `README.md`, `deploy.sh`, `bin/deploy.sh`, `compose.yaml`.
- `docs/arclink/sovereign-control-node.md`,
  `docs/arclink/control-node-production-runbook.md`,
  `docs/arclink/fleet-operator-runbook.md`,
  `docs/arclink/operations-runbook.md`,
  `docs/arclink/foundation-runbook.md`,
  `docs/arclink/first-day-user-guide.md`,
  `docs/arclink/raven-public-bot.md`,
  `docs/arclink/data-safety.md`,
  `docs/arclink/llm-router.md`.
- `research/PRODUCT_REALITY_MATRIX.md`,
  `research/RALPHIE_ARCLINK_PRODUCT_REALITY_AND_JOURNEY_STEERING.md`,
  and relevant newer Ralphie steering/completion notes.
- `python/arclink_hosted_api.py`, `python/arclink_api_auth.py`,
  `python/arclink_dashboard.py`, `python/arclink_public_bots.py`,
  `python/arclink_telegram.py`, `python/arclink_discord.py`,
  `python/arclink_onboarding.py`, `python/arclink_onboarding_flow.py`,
  `python/arclink_provisioning.py`, `python/arclink_executor.py`,
  `python/arclink_sovereign_worker.py`, `python/arclink_action_worker.py`,
  `python/arclink_entitlements.py`, `python/arclink_fleet.py`,
  `python/arclink_chutes*.py`, `python/arclink_llm_router.py`,
  `python/arclink_mcp_server.py`, `python/arclink_memory_synthesizer.py`,
  `python/arclink_notion_*.py`, and `python/arclink_ssot_batcher.py`.
- `web/src/**`, `web/tests/**`.
- `plugins/hermes-agent/arclink-managed-context/**`,
  `plugins/hermes-agent/drive/**`, `plugins/hermes-agent/code/**`,
  `plugins/hermes-agent/terminal/**`.
- `tests/test_arclink_*.py`, `tests/test_*notion*.py`, `tests/test_*memory*.py`,
  `tests/test_deploy_regressions.py`, and browser tests under `web/tests`.

## Output Bar

The final documents should be dense, navigable, and honest. The story should
feel simple and mind-blowing at the human layer while the gap register is
unsentimental about every missing proof, missing code path, weak test, unclear
policy choice, or confusing surface.
