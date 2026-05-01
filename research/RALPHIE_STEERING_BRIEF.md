# Ralphie Steering Brief: Build ArcLink From Almanac

You are Ralphie running inside the cloned Almanac repository that must become ArcLink. You write the code. The human/operator has asked the supervising Codex instance to prep and babysit you, not to hand-write the product transformation.

## Mission

Transform Almanac into ArcLink: a polished, self-serve, single-user AI deployment product that preserves Almanac's robust Hermes/qmd/memory/health/provisioning system while adding SaaS onboarding, payment, DNS, dashboard, admin control plane, and Chutes-first inference.

## Non-Negotiables

- Rebrand must reign throughout the codebase. Do not leave public product UI/docs/messages as Almanac unless intentionally marked as legacy compatibility.
- Preserve operational robustness. Do not delete services or tests just to make a simpler demo.
- Chutes is the primary inference provider. Default model is `moonshotai/Kimi-K2.6-TEE`, but model catalog must be refreshable and validated.
- Website form, Telegram bot, and Discord bot must converge into one workflow/state machine.
- Stripe payment state gates self-serve provisioning.
- Cloudflare/domain orchestration must be real and testable, with wildcard DNS preferred to per-user record churn.
- Nextcloud and code-server should use host-per-service routing, not fragile path prefixes, unless tests prove otherwise.
- SSH/TUI must use a bastion or TLS-wrapped strategy. Do not fake raw SSH subdomain routing through HTTP/Traefik.
- Admin dashboard must be a true control plane with audit logs and actions, not only read-only charts.
- Mobile responsiveness matters for user and admin dashboard critical paths.
- Surface the technology tastefully. Hermes, qmd, Chutes, skills, managed memory, and agentic harness are product strengths.

## Existing Code Surfaces To Respect

Read these before major changes:

- `README.md`, `AGENTS.md`, `docs/docker.md`
- `compose.yaml`
- `bin/almanac-docker.sh`
- `bin/deploy.sh`
- `python/almanac_control.py`
- `python/almanac_onboarding_flow.py`
- `python/almanac_enrollment_provisioner.py`
- `python/almanac_docker_agent_supervisor.py`
- `python/almanac_agent_access.py`
- `python/almanac_onboarding_provider_auth.py`
- `python/almanac_memory_synthesizer.py`
- `plugins/hermes-agent/almanac-managed-context/`
- `config/model-providers.yaml`
- `tests/test_almanac_docker.py`, `tests/test_almanac_auto_provision.py`, `tests/test_almanac_onboarding_prompts.py`, `tests/test_memory_synthesizer.py`, `tests/test_almanac_plugins.py`

Prep docs created for you:

- `research/ALMANAC_ARCHITECTURE_MAP.md`
- `research/CHUTES_ARCLINK_NOTES.md`
- `research/ARCLINK_PRODUCT_AND_ADMIN_BRIEF.md`
- `docs/arclink/brand-system.md`
- `IMPLEMENTATION_PLAN.md`

## First Build Direction

Do not try to finish the entire SaaS in one sweep. Build a coherent foundation that tests can execute:

1. Establish ArcLink product identity/config while preserving compatibility aliases for existing `ALMANAC_*` runtime settings.
2. Add ArcLink SaaS/control-plane data model scaffolding and tests: deployments, subscriptions, DNS, provisioning jobs, audit log, admin users/events.
3. Add Cloudflare routing planner code that can generate wildcard/service-host plans without requiring live credentials in tests.
4. Add Chutes model catalog validation code and tests using fixture data; include auth caveat in docs/config.
5. Add Stripe webhook/provisioning gate scaffold with signature/idempotency tests; do not require real Stripe keys for tests.
6. Add dashboard/admin app scaffold only when the backend contract is in place; prefer small vertical slices over empty UI shell.
7. Update docs and tests with ArcLink language as implementation becomes real.

## Validation Expectations

- Run focused tests for changed Python surfaces.
- Add tests for any new control-plane logic.
- Keep existing regression tests meaningful; update them for ArcLink names only when behavior is intentionally rebranded.
- Do not print or commit secrets.
- If live credentials are missing, build fakeable adapters and mark live E2E as pending in docs/tests.

## Keys That Will Be Needed Later

Initial work must proceed without these. When live deploy/E2E starts, request:

- Cloudflare API token scoped to `arclink.online` DNS edit/read and zone id if not discoverable.
- Hetzner API token or server SSH access.
- Stripe secret key, webhook signing secret, price ids, and customer portal config.
- Chutes owner/admin API key or account credentials for per-deployment key creation.
- Telegram public onboarding bot token.
- Discord public onboarding bot token/application credentials.
- OAuth credentials/config for OpenAI Codex and Anthropic/Claude flows if not already supported by existing auth.
- Notion integration token/webhook verification if shared Notion remains enabled.

## Tone/UX

ArcLink copy and UI must follow `docs/arclink/brand-system.md`: jet black/carbon surfaces, signal orange `#FB5005`, soft white `#E7E6E6`, restrained blue/green for system state, Space Grotesk display type, Satoshi or Inter for UI/body, minimal system-first visuals, and direct operator language.

ArcLink copy should be clear, premium, and technically proud. Avoid generic AI SaaS language, hype, stock imagery, and overused gradients. Teach users that skills and managed memory are their growth path: they are buying an agentic harness now and growing high-power tools over time.
