# ArcLink Ingress Plan

## Overview

ArcLink Sovereign pods support two first-class ingress modes:

- `ARCLINK_INGRESS_MODE=domain`: public DNS is managed through Cloudflare and
  routed by Traefik to per-pod Docker services.
- `ARCLINK_INGRESS_MODE=tailscale`: public/control exposure is published through
  the host Tailscale edge, while per-pod service URLs are rendered under a
  Tailscale node name. Cloudflare DNS is not required in this mode.

Both modes use the same provisioning intent model. The control node renders
hostnames, access URLs, Traefik labels, DNS intent, SSH strategy, health checks,
and audit state before any live executor is allowed to mutate infrastructure.

## Domain Mode

Domain mode is the public SaaS shape for a root domain such as
`arclink.online`. Each deployment gets an obscure prefix derived from its
deployment ID. Hostnames follow the current code shape:

| Hostname | Service |
|----------|---------|
| `u-{prefix}.{base_domain}` | User dashboard |
| `files-{prefix}.{base_domain}` | Nextcloud file access |
| `code-{prefix}.{base_domain}` | code-server workspace |
| `hermes-{prefix}.{base_domain}` | Hermes agent gateway |

`ARCLINK_BASE_DOMAIN` sets the base domain. `ARCLINK_EDGE_TARGET` sets the
Cloudflare CNAME target, usually the control edge or worker edge host.

## Tailscale Mode

Tailscale mode is the safe starter path when the control node or worker nodes
are reached through a Tailscale DNS name. `deploy.sh control install` asks for:

- `ARCLINK_TAILSCALE_DNS_NAME`, for example `s1396.tailnet.ts.net`.
- `ARCLINK_TAILSCALE_HTTPS_PORT`, default `443`.
- `ARCLINK_TAILSCALE_NOTION_PATH`, default `/notion/webhook`.
- `ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY`, default `path`.

The default `path` strategy avoids assuming that sub-subdomains under a
Tailscale name can be resolved and certificated. Access URLs are rendered as:

| URL | Service |
|-----|---------|
| `https://{tailscale_dns_name}/u/{prefix}` | User dashboard |
| `https://{tailscale_dns_name}/u/{prefix}/files` | Nextcloud file access |
| `https://{tailscale_dns_name}/u/{prefix}/code` | code-server workspace |
| `https://{tailscale_dns_name}/u/{prefix}/hermes` | Hermes agent gateway |
| `https://{tailscale_dns_name}/u/{prefix}/notion/webhook` | Per-deployment Notion callback |

The optional `subdomain` strategy renders `u-{prefix}.{tailscale_dns_name}`,
`files-{prefix}.{tailscale_dns_name}`, `code-{prefix}.{tailscale_dns_name}`,
and `hermes-{prefix}.{tailscale_dns_name}`. Use it only when the operator has
confirmed that DNS and certificates for that shape actually work in the
tailnet.

## DNS Management

**Module:** `python/arclink_ingress.py`

- `desired_arclink_ingress_records()` returns Cloudflare CNAME records in
  `domain` mode and an empty record set in `tailscale` mode.
- `provision_arclink_dns()` creates or updates domain-mode records.
- `reconcile_arclink_dns()` detects drift between desired and actual DNS state.
- `teardown_arclink_dns()` removes domain-mode records for a decommissioned
  deployment.

**Domain-mode credentials:**

- `CLOUDFLARE_API_TOKEN` with `Zone:DNS:Edit` scope.
- `CLOUDFLARE_ZONE_ID` for the target zone.

**Tailscale-mode requirements:**

- The host Tailscale CLI must be installed and logged in for live publication.
- Tailscale Funnel/Serve approval must be handled by the tailnet operator when
  Tailscale prompts for it.
- No Cloudflare token or zone is required for Sovereign pod routing.

Fake mode remains the default for tests and dry runs. Records are persisted to
SQLite only and no provider API call is made.

## Traefik Reverse Proxy

**Label generation:** `render_traefik_dynamic_labels()` produces Docker labels
for Traefik routing per service.

Domain mode uses host-based routing:

```text
Internet -> Cloudflare DNS -> edge host -> Traefik (443/80) -> Docker service
```

Tailscale path mode uses host plus path-prefix routing:

```text
Tailscale/Funnel host -> Traefik -> Host(`node.ts.net`) && PathPrefix(`/u/{prefix}/...`) -> Docker service
```

The generated path-mode labels include a StripPrefix middleware so the wrapped
service receives the route shape it expects.

## SSH Access

SSH is never routed through HTTP path prefixes.

- Domain mode advertises `cloudflare_access_tcp` hints such as
  `cloudflared access ssh --hostname ssh-{prefix}.{base_domain} ...`.
- Tailscale mode advertises `tailscale_direct_ssh` hints such as
  `ssh arc-{prefix}@{tailscale_dns_name}`.

`python/arclink_access.py` rejects raw SSH-over-HTTP strategies and rejects HTTP
URLs for SSH hostnames.

## Per-Deployment Notion Callback

Sovereign pods reserve a customer-specific Notion callback endpoint in the
rendered provisioning intent. This is separate from the operator-led shared-host
Notion webhook used by Shared Host and Shared Host Docker modes.

- Domain mode: `https://u-{prefix}.{base_domain}/notion/webhook`
- Tailscale path mode:
  `https://{tailscale_dns_name}/u/{prefix}/notion/webhook`

The intent includes the callback URL, callback path, Notion token reference, and
webhook secret reference under `integrations.notion`. Live creation of the
customer's Notion integration/subscription remains credential-gated E2E work.

## Drift Detection

The admin dashboard surfaces DNS and provisioning drift via
`GET /api/v1/admin/reconciliation`.

Domain-mode drift items include:

- **Missing:** expected records not present in Cloudflare.
- **Extra:** records in Cloudflare not expected by ArcLink.
- **Mismatched:** records with the wrong target or type.

Tailscale mode has no Cloudflare DNS drift. Its live validation should instead
check Tailscale login state, Funnel/Serve publication, Traefik path routes,
service health, and SSH reachability.

## Teardown

Teardown is a destructive operation that:

1. Requires explicit admin action with a reason and audit log.
2. Removes Cloudflare DNS records in domain mode.
3. Clears Tailscale publication intent in Tailscale mode when that executor is
   enabled.
4. Preserves local state records for audit and rollback analysis.
