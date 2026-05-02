# Ralphie Steering: ArcLink Final Form Gap Closure

This file supersedes the older unchecked gap list. The current branch has a
substantial no-secret foundation, but ArcLink is not final until live deployment
and the full customer journey are proven with real credentials.

## Current Checkpoint

Latest accepted commits on branch `arclink`:

- `2e6fa98` - live journey model, deployment evidence ledger, evidence
  template, live E2E harness wiring, and no-secret tests.
- `a9ea651` - host readiness CLI, provider diagnostics CLI, injectable Docker
  runner, and no-secret tests.
- `9e50eeb` - operations/deployment documentation assets.
- `211bea7` - fake E2E journey harness and live E2E scaffold.
- `adde1ff` - browser product proof.
- `8cd17a4` - hosted-API-backed user/admin dashboard wiring and bot readiness.

Landed no-secret foundation:

- Website, Telegram, and Discord onboarding share a backend contract.
- Stripe, Cloudflare, Docker executor, Chutes, Telegram, and Discord all have
  fake/no-secret boundaries and tests.
- User/admin dashboards are wired to hosted API read/action contracts.
- Playwright browser product proof exists for desktop/mobile.
- Fake full journey E2E exists.
- Live E2E scaffold exists and skips cleanly without secrets.
- Host readiness, provider diagnostics, and injectable Docker runner no-secret
  surfaces exist.
- Live journey/evidence no-secret scaffolding exists and has focused tests.
- Deployment, ingress, secret, backup/restore, operations, observability, data
  safety, and documentation-truth assets exist.

## Remaining Final Form Work

Do not declare final form while any non-external item below is unfinished.

- [x] Gap A: Add executable host deployment assets, not only docs. Produce a
  no-secret host bootstrap/check script or compose wrapper that validates
  required binaries, env shape, state directories, Traefik/Cloudflare strategy,
  and API health without mutating live providers by default.
- [x] Gap B: Deepen the live-gated Docker executor from intent/fake coverage
  toward a real operator path. It must refuse to run unless explicit live flags,
  a state root, and a secret resolver are present. Dry-run tests must remain the
  default.
- [x] Gap C: Add live-readiness diagnostics for Stripe, Cloudflare, Chutes,
  Telegram, Discord, and host Docker. Diagnostics should say exactly which
  env/account is missing and must never print secret values.
- [ ] Gap D: Expand the live E2E harness from provider smoke checks toward the
  full signup-to-agent journey. No-secret journey modeling and skip behavior
  must be built now; credentialed execution stays skipped until credentials
  exist.
- [ ] Gap E: Record real deployment evidence once credentials are supplied:
  website onboarding, checkout, provisioning, DNS, dashboard, Nextcloud,
  code-server, Hermes/qmd/memory, bot handoff, Chutes inference, and admin
  operations. No-secret evidence schema/template work must be built now.

## External Live Blockers

These are blocked until the operator supplies credentials or account setup:

- [ ] [external] Stripe test/prod keys, webhook secret, product/price IDs.
- [ ] [external] Cloudflare zone id and scoped DNS/edit token for `arclink.online`.
- [ ] [external] Chutes owner/admin key for live inference/key lifecycle.
- [ ] [external] Telegram onboarding bot token.
- [ ] [external] Discord app id, public key, bot token, guild/channel.
- [ ] [external] Production host/Hertzner decision and any provider API token
  beyond existing SSH access.

## Next Ralphie Objective

Start with Gap D/E scaffolding because Gaps A-C are now landed. The scaffolding
is not externally blocked; only the credentialed live run is blocked. Do not
rebuild P1-11, P13-P16, or Gaps A-C unless a failing test proves a regression.
Do not mark P12 or final form complete until credential-backed E2E evidence
exists.
