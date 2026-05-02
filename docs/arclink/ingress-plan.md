# ArcLink Ingress Plan

## Overview

ArcLink uses Cloudflare DNS for public hostname resolution and Traefik as the
reverse proxy for per-deployment service routing within Docker Compose stacks.

## DNS Layout

Each deployment gets a unique prefix derived from its deployment ID. Hostnames
follow the pattern `{service}.{prefix}.{base_domain}`:

| Hostname | Service |
|----------|---------|
| `dashboard.{prefix}.arclink.online` | User dashboard |
| `files.{prefix}.arclink.online` | Nextcloud file access |
| `code.{prefix}.arclink.online` | code-server workspace |
| `hermes.{prefix}.arclink.online` | Hermes agent gateway |

The base domain is configured via `ARCLINK_BASE_DOMAIN` (default: `arclink.online`).

## Cloudflare DNS Management

**Module:** `python/arclink_ingress.py`

- `desired_arclink_dns_records()` computes the expected DNS shape for a deployment.
- `provision_arclink_dns()` creates or updates records (fake by default).
- `reconcile_arclink_dns()` detects drift between desired and actual state.
- `teardown_arclink_dns()` removes records for a decommissioned deployment.

**Required credentials:**
- `CLOUDFLARE_API_TOKEN` with `Zone:DNS:Edit` scope
- `CLOUDFLARE_ZONE_ID` for the target zone

**Fake mode (default):** Records are persisted to SQLite only. No Cloudflare API
calls are made. Drift reconciliation reports local-only state.

## Traefik Reverse Proxy

**Label generation:** `render_traefik_dynamic_labels()` produces Docker labels
for Traefik routing per service.

**Deployment topology:**
```
Internet -> Cloudflare DNS -> Host IP -> Traefik (443/80) -> Docker service
```

Traefik runs as a shared container on the host with:
- Automatic TLS via Let's Encrypt or Cloudflare origin certificates
- Host-based routing rules from Docker labels
- Health check forwarding to per-deployment services

**Traefik configuration requirements:**
- Docker provider enabled (watches container labels)
- Entrypoints for HTTP (80) and HTTPS (443)
- TLS certificate resolver configured
- Network shared with per-deployment Compose stacks

## SSH Access

SSH access uses Cloudflare Access TCP-style tunnels, not raw SSH over HTTP or
path-prefix routing. This is enforced by `arclink_access.py` which rejects
any SSH strategy other than `cloudflare_access_tcp`.

## Drift Detection

The admin dashboard surfaces DNS drift via `GET /api/v1/admin/reconciliation`.
Drift items include:
- **Missing:** expected records not present in Cloudflare
- **Extra:** records in Cloudflare not expected by ArcLink
- **Mismatched:** records with wrong target or type

## Teardown

DNS teardown is a destructive operation that:
1. Requires explicit admin action with reason and audit log
2. Removes Cloudflare DNS records for the deployment
3. Preserves local state records for audit trail
