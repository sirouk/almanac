# ArcLink Product And Admin Brief

## Product Promise

ArcLink turns ArcLink into a self-serve private AI workforce deployment. A user can start from a website form, Telegram conversation, or Discord conversation; pay; pick a model lane; connect a bot; and receive a fully isolated agentic workspace with Hermes, qmd-powered vault retrieval, hot memory stubs, files, code workspace, dashboard, and optional Notion/backup/SSH rails.

It should feel premium and potent, not like a devops checklist. The interface should surface the underlying technology with confidence: Hermes, qmd, Chutes, memory stubs, skills, vault, Notion rails, code workspace, and agentic harness are part of the value.

## Brand System

Canonical source: `docs/arclink/brand-system.md`. Original brand kit PDF is tracked at `docs/arclink/brand/ArcLink Brandkit.pdf`.

ArcLink is private AI infrastructure for operators. The product language is clear, direct, confident, minimal, operational, and quietly powerful. Use operator language, not marketer language.

Visual rules:

- Primary palette: jet black `#080808`, carbon `#0F0F0E`, soft white `#E7E6E6`, signal orange `#FB5005`.
- Secondary accents: electric blue `#2075FE` and neon green `#1AC153` for system states and feedback.
- Typography: Space Grotesk for display/headlines; Satoshi or Inter for UI/body.
- Imagery: dark, abstract, minimal, purpose-driven private infrastructure. No stock photos, generic AI imagery, cliches, or decorative gradient overload.
- UI tone: premium control room, dense but calm. Orange means action/energy. Blue and green support state, not decoration.

## User Entry Points

- Website form/workflow in Next.js + Tailwind.
- Public Telegram onboarding bot.
- Public Discord onboarding bot.

All three should write the same onboarding/session/event state. Website users can continue in bot chat. Bot users can open the web dashboard. No duplicate business logic.

## Core User Workflow

1. User lands on ArcLink site and chooses `Start`.
2. User can continue by web, Telegram, or Discord.
3. ArcLink collects minimal context: name, use case, desired bot platform, bot name, model lane, optional BYOK preference, optional Notion/backup interest.
4. ArcLink opens Stripe Checkout or validates an existing entitlement.
5. Stripe webhook marks entitlement active.
6. Provisioning job reserves obscure prefix and creates deployment records.
7. DNS/routing is prepared.
8. ArcLink creates/allocates per-deployment Chutes key by default or initiates BYOK auth flow.
9. ArcLink renders per-deployment config and starts/reconciles Docker services.
10. ArcLink validates health, dashboard, qmd, memory payload, bot gateway, Nextcloud/code-server/Hermes access.
11. User receives a launch card with links and first instructions.
12. Dashboard teaches skills/memory/vault growth naturally after first success.

## Domain And Routing Strategy

Base domain: `arclink.online`.

Prefer wildcard DNS to avoid per-user Cloudflare API churn:

- HTTP/S: wildcard `*.arclink.online` points to the active ArcLink ingress node. Proxied through Cloudflare where compatible.
- SSH: use `ssh.arclink.online` as DNS-only bastion, or Cloudflare Tunnel/Access later. Do not assume orange-cloud HTTP proxy can route raw SSH.

Per-deployment hostnames:

- `u-<prefix>.arclink.online`: unified ArcLink dashboard.
- `files-<prefix>.arclink.online`: Nextcloud/files.
- `code-<prefix>.arclink.online`: code-server.
- `hermes-<prefix>.arclink.online`: Hermes dashboard/API.
- Optional future: `mcp-<prefix>.arclink.online` for authenticated MCP/debug endpoints.

Prefix generation:

- Use partially obscure, pronounceable but non-enumerable prefixes such as `arc-7k9m2p` or `<word>-<base32>`.
- Store prefix reservation in DB with unique index.
- Never expose incremental deployment ids in hostnames.

Ingress:

- Use Traefik initially because Docker labels and Cloudflare DNS-01 are mature for Compose-based routing.
- Avoid path-prefix routing for Nextcloud and code-server unless tests prove it; host-per-service is safer.
- Use Cloudflare DNS-01 wildcard certificate or per-host certs.

## SSH/TUI Strategy

The previous idea of raw SSH through Traefik `HostSNI(*)` is not valid for per-subdomain routing because raw SSH is not TLS and has no SNI. ArcLink should implement one of:

- Preferred MVP: SSH bastion at `ssh.arclink.online`; users connect with a deployment-scoped username/key; bastion maps them to the right TUI/container and logs/audits access.
- Later: TLS-wrapped SSH via stunnel/sslh with SNI if subdomain-specific SSH is truly needed.
- Later: Cloudflare Access/Tunnel for browser terminal or SSH if product/account supports it.

Do not ship a fake per-subdomain SSH promise.

## Per-Deployment Services

Required per deployment or per deployment lane:

- Hermes agent runtime and Hermes dashboard.
- qmd index/retrieval over the user's vault.
- Vault watcher.
- Memory synthesis, preferably moved toward shared worker pool over time because it is bursty.
- Managed-context plugin and hot memory stub publication.
- Bot gateway for Telegram/Discord private agent lane.
- Nextcloud or equivalent file UI for vault/files.
- code-server browser IDE.
- Unified dashboard that wraps/links files, code, Hermes, stats, settings, billing, skills, memory, and activity.

Shared/global services:

- ArcLink API/control plane.
- Next.js marketing/user/admin app.
- Postgres for ArcLink SaaS state.
- Redis for jobs/pubsub/rate limits.
- Traefik ingress.
- Prometheus metrics.
- Loki logs.
- Grafana deep-dive panels embedded in admin only.
- Provisioning workers.
- Model catalog worker.
- Payment webhook worker.
- Cloudflare DNS/drift worker.
- Chutes key management worker.

## User Dashboard

Design direction: follow `docs/arclink/brand-system.md`: premium, dark, precise, technical, high contrast, minimal, operational, and system-first. It must be excellent on mobile.

Dashboard sections:

- Home: deployment health, agent status, model, last activity, quick launch buttons.
- Chat setup: Telegram/Discord private bot status, retry handoff, token regeneration workflow.
- Files: embedded or deep-linked Nextcloud; upload guidance; vault structure recommendations.
- Code: embedded or deep-linked code-server; open workspace button; mobile fallback to launch card.
- Hermes: embedded or deep-linked Hermes dashboard; session health; model runtime.
- Memory: memory stub count, last synth, vault landmarks, Notion landmarks, manual resynth.
- Skills: explain current skills, how users can grow them, skill install/upgrade surface later.
- Model: Chutes default, current model, reasoning level, BYOK Codex/Claude setup.
- Billing: Stripe portal, plan, usage, payment state.
- Security: active sessions, bot tokens masked/reveal with warnings, SSH keys, backup status.
- Support: export diagnostics bundle, request help, incident status.

Embedding rules:

- Wrap code-server/Nextcloud/Hermes with iframe tabs only where headers/CSP/proxy compatibility is tested.
- If embedding is fragile on mobile, use polished cards and full-screen deep links instead of clunky iframes.
- Dashboard should feel like a command center, not a pile of vendor tabs.

## Admin Dashboard

Purpose: owner/operator control plane for global ArcLink operations. Grafana alone is not enough because admins need actions.

Architecture:

- Next.js admin route gated by role-based auth and TOTP.
- FastAPI admin endpoints with `require_admin` dependency.
- Postgres for ArcLink state.
- Redis streams/pubsub for live events and jobs.
- Prometheus for metrics.
- Loki for logs.
- Optional embedded Grafana panels for deep dives.
- Append-only audit log for every mutation.

Admin sections:

- Overview: active users, MRR, signups, churn, failed payments, unhealthy deployments, host CPU/RAM/disk, Stripe webhook lag, provisioning queue depth, Cloudflare status, Chutes usage/cost, average onboarding completion time.
- Onboarding funnel: DM/form started, questions answered, checkout opened, payment success, provisioning started, health passed, first agent message. Filter by web/Telegram/Discord, plan, week.
- Users/deployments table: account, deployment prefix, plan, MRR, status, last agent activity, service health, signup source, lifetime value.
- Per-user detail: profile/subscription, containers/services, vault/memory, DNS, bot, model/provider, logs, audit trail.
- Payments: Stripe-synced MRR/ARR, failed payments, dunning, refunds, disputes, reconciliation alerts.
- Infrastructure: nodes, Docker daemon, deployment density, disk usage, Traefik routes/certs/5xx, Cloudflare drift, DB pool/slow queries/backups, job queues.
- Bots: public Telegram/Discord bot health, webhook delivery, rate limit, active onboarding conversations, stuck-state tools.
- Security/abuse: failed admin logins, anomaly flags, bandwidth spikes, CPU pegging, suspicious files, SSH attempts, suspended users, Falco/auditd alerts later.
- Releases/maintenance: image versions across deployments, canary rollout, maintenance-mode toggle, announcement broadcaster, rollback.

Required admin actions:

- Restart service.
- Restart deployment stack.
- Reprovision with confirm/reason.
- Suspend/unsuspend deployment.
- Pull latest image/canary rollout.
- Force memory resynth.
- Recreate DNS/routing.
- Rotate/revoke bot token.
- Rotate/revoke Chutes key.
- Open Stripe customer/subscription/invoices.
- Grant comp/cancel/refund through guarded Stripe flows.
- Download diagnostics bundle.

Audit rules:

- Admin identities live in `arclink_admins`, not product user table.
- TOTP required for mutating admin roles.
- Short JWT TTL with refresh.
- Every mutating endpoint writes `arclink_audit_log` with admin id, action, target, before/after JSON where safe, reason, IP, user agent, timestamp.
- Sensitive reveal actions require a reason and audit event.

## Security Baseline

- Stripe webhooks verify signatures and idempotency keys.
- Cloudflare token scoped to Zone DNS edit/read only.
- Chutes owner key never enters user runtime; per-deployment keys do.
- Per-deployment secrets are encrypted/secret-managed, never plaintext in Git or logs.
- Docker containers unprivileged wherever possible; no broad `--privileged`.
- Docker socket access is a trusted-host boundary; restrict to control/supervisor components only.
- Per-deployment networks isolate user services.
- Resource limits for CPU/RAM/disk and quotas by plan.
- Health checks and rollback on partial provisioning.
- Direct host IP exposure minimized; HTTP through ingress; SSH through explicit bastion.

## Scaling Path

MVP: one Hetzner node with Docker Compose, Traefik, Postgres, Redis, and per-deployment stacks. Good for proving product and user experience.

Next: multiple Hetzner nodes, central control plane assigns deployments to nodes, wildcard DNS per node or global load balancer, remote Docker contexts or node agents.

Later: Nomad or Kubernetes only when Docker Compose/node agents become the bottleneck. Do not introduce Kubernetes before product-market validation unless a specific scaling problem demands it.
