# Research Summary

<confidence>92</confidence>

## Goal

Transform Almanac into ArcLink: a Chutes-first, self-serve, paid,
single-user AI deployment SaaS with website, Telegram, and Discord onboarding;
Stripe entitlement gates; Cloudflare and Traefik host routing; responsive
user/admin dashboards; and preserved Hermes, qmd, vault, managed memory,
Notion, Nextcloud, code-server, bot, and health robustness.

## Current Finding

ArcLink should continue as a staged evolution of the existing Almanac
Docker/Python control plane. The repository already has a mature operational
substrate: Docker Compose, Python control-plane modules, Bash deploy and
health scripts, Hermes/qmd/vault/memory rails, Nextcloud, code-server,
Telegram and Discord onboarding foundations, Notion SSOT, service health, and
focused no-secret regression tests.

The ArcLink foundation is additive and contract-first. Product config, SaaS
schema helpers, Chutes catalog validation, fakeable Stripe/Cloudflare/Traefik/
Chutes adapters, entitlement handling, ingress/access decisions, dry-run
provisioning intent, public onboarding session contracts, dashboard read
models, queued admin action contracts, and fake executor/secret resolver
boundaries are present. The current code records, validates, and fake-applies
intent. It does not execute live customer containers, create live DNS records,
mint live Chutes keys, serve a Next.js frontend, or execute queued admin
actions against live providers.

## Implemented Foundation

| Surface | Evidence | Status |
| --- | --- | --- |
| Product identity/config | `python/arclink_product.py`, `tests/test_arclink_product_config.py` | Present. |
| SaaS schema/helpers | `arclink_*` tables and helpers in `python/almanac_control.py`, `tests/test_arclink_schema.py` | Present. |
| Chutes-first provider | `python/arclink_chutes.py`, `config/model-providers.yaml` | Catalog/fake-key scaffold present; live key lifecycle deferred. |
| Stripe entitlement gate | `python/arclink_entitlements.py`, `tests/test_arclink_entitlements.py` | No-secret webhook/entitlement contract present. |
| Public onboarding contract | `python/arclink_onboarding.py`, `tests/test_arclink_onboarding.py` | Web/Telegram/Discord session and fake checkout contract present. |
| Cloudflare/Traefik ingress | `python/arclink_adapters.py`, `python/arclink_ingress.py`, Traefik golden fixture | Render/drift scaffold present; live adapter deferred. |
| Access strategy | `python/arclink_access.py`, `tests/test_arclink_access.py` | Dedicated Nextcloud and Cloudflare Access TCP decisions are test-pinned. |
| Provisioning dry run | `python/arclink_provisioning.py`, `tests/test_arclink_provisioning.py` | Intent renderer, no-secret service plan, health placeholders, timeline events, and rollback planning present. |
| Dashboard/admin backend contracts | `python/arclink_dashboard.py`, `tests/test_arclink_dashboard.py`, `tests/test_arclink_admin_actions.py` | User/admin read models and queued, audited action intents present. |
| Executor boundary | `python/arclink_executor.py`, `tests/test_arclink_executor.py` | Fail-closed executor types, secret resolver contracts, fake Docker/provider/edge/rollback behavior, digest and operation replay guards, DNS type validation, and Compose dependency validation present. |
| E2E truth docs | `docs/arclink/live-e2e-secrets-needed.md` | Present; must stay current as live paths land. |

## Path Comparison

Path A: evolve the Docker/Python control plane.

This remains selected. It preserves working Hermes/qmd/memory/health/bot
behavior, keeps no-secret tests practical, and lets ArcLink prove onboarding,
payment, provisioning, access, dashboard, and admin contracts before executing
live infrastructure changes.

Path B: build a clean SaaS shell that treats Almanac as a black-box
provisioner.

This is viable later if ArcLink needs a separate web/API boundary, but it is
too early. It would duplicate state, audit, billing, health, and provisioning
semantics before the backend contract is stable.

Path C: rewrite around Kubernetes or Nomad.

This is not justified for the MVP. Docker Compose plus per-node supervision is
enough until real multi-host scheduling pressure appears.

## Key Assumptions

- Docker mode is the first ArcLink provisioning target.
- Baremetal/systemd behavior remains a compatibility/operator lane.
- New SaaS state belongs in `arclink_*` tables with stable text ids and
  Postgres-compatible shapes.
- `ARCLINK_*` values should take precedence over non-empty `ALMANAC_*`
  aliases; blank ArcLink values should be treated as unset.
- Unit tests must not require live Stripe, Cloudflare, Chutes, Telegram,
  Discord, Notion, OAuth, or server credentials.
- Public website, Telegram, and Discord onboarding should share one durable
  backend session contract.
- User/admin dashboards should consume backend read/action contracts; the
  frontend should not invent separate business logic.

## Build Readiness

The no-secret executor lint-risk and replay/dependency repairs are complete.
The next phase should reconcile documentation and handoff artifacts, then
proceed only to E2E-gated live adapter planning: Docker Compose materialization,
Cloudflare DNS/Tunnel/Access, Chutes key lifecycle, Stripe actions, hosted
dashboard/API action wiring, and public bot/website delivery.

## Remaining Risks

- Real Docker Compose execution and live provider mutation remain disabled by
  default and must stay behind explicit E2E/operator gates.
- Live Chutes key lifecycle and auth-header behavior still need account-backed
  verification.
- Stripe, Cloudflare, public bot, Notion, OAuth, and deployment-host E2E are
  blocked on real credentials/infrastructure but must not block unit tests.
- Public onboarding has a no-secret contract, but live Stripe checkout,
  hosted success/cancel URLs, and real bot handoff are not implemented.
- Dedicated Nextcloud per deployment is safer for isolation but heavier; shared
  Nextcloud remains deferred until measured resource pressure justifies it.
- The provisioning renderer records intent and timeline data, not live
  containers.
- Broad rebrand work could destabilize legacy Almanac paths if done before
  backend contracts and execution boundaries settle.

## External Research Notes

- Chutes is the primary inference target for ArcLink; keep the base URL and
  default model centralized and treat live per-deployment key lifecycle as an
  E2E prerequisite until the production account flow is verified:
  https://docs.chutes.ai/
- Stripe webhook processing must verify the raw payload, signature header, and
  endpoint secret; blank secrets must fail closed:
  https://docs.stripe.com/webhooks/signature
- Cloudflare Tunnel/Access is the correct direction for SSH/TCP-style access;
  do not present raw SSH as HTTP routing:
  https://developers.cloudflare.com/tunnel/
- Docker Compose secrets and image-supported `_FILE` environment variables
  match the no-plaintext provisioning intent:
  https://docs.docker.com/reference/compose-file/secrets/
- Traefik Docker labels support host rules and explicit service ports, matching
  the host-per-service routing plan:
  https://doc.traefik.io/traefik/reference/routing-configuration/other-providers/docker/
- Next.js App Router and Tailwind remain suitable for the later dashboard
  phase, but no dashboard app exists yet:
  https://nextjs.org/docs/app
