# Ralphie Public Onboarding Steering

## Mission

Continue the ArcLink plan with the Phase 7 no-secret build slice: durable
public onboarding contracts for website, Telegram, and Discord.

This is not a UI build and not a live Stripe/bot integration. It should create
the shared backend contract that all public entrypoints will use later.

## Scope

- Add or extend `arclink_*` schema/helpers for public onboarding sessions and
  funnel events.
- Keep website, Telegram, and Discord flows unified through the same session
  state machine.
- Keep public onboarding state separate from private user-agent bot state.
- Add fake/live adapter boundaries for Stripe checkout session creation.
- Use deterministic fake checkout ids and URLs in no-secret tests.
- Connect successful checkout completion to the existing entitlement/provisioning
  gate contract without executing live containers.

## Explicit Non-Goals

- Do not build Next.js dashboard pages yet.
- Do not call live Stripe, Telegram, Discord, Cloudflare, Chutes, Notion, Codex,
  or Claude services.
- Do not create live containers, DNS records, or Chutes API keys.
- Do not store private bot tokens, provider API keys, or checkout secrets in
  public onboarding session rows.
- Do not rework mature ArcLink onboarding logic beyond the ArcLink contract
  boundary needed for this slice.

## Expected Tests

- Duplicate web/Telegram/Discord session creation resumes or rejects correctly.
- Cancelled checkout blocks provisioning and records a funnel event.
- Expired checkout blocks provisioning and records a funnel event.
- Successful fake checkout advances only through the existing entitlement gate.
- Public onboarding rows do not contain private bot tokens or live provider
  secrets.
- Existing ArcLink foundation tests continue to pass.

## Documentation

Update the ArcLink foundation/runbook docs only where the new public onboarding
contract changes operator assumptions. Keep docs honest that live public bot
delivery and website UI are still future work.
