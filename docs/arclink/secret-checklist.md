# ArcLink Secret Checklist

Secrets required for live deployment. Never commit these to version control.
Store in `.env` files, a secret manager, or interactive deploy prompts.

## Required for Production

| Secret | Purpose | Where Used |
|--------|---------|------------|
| `STRIPE_SECRET_KEY` | Billing API, portal links, subscription reads | `arclink_adapters.py`, `arclink_entitlements.py` |
| `STRIPE_WEBHOOK_SECRET` | Webhook signature verification | `arclink_hosted_api.py`, `arclink_entitlements.py` |
| `CLOUDFLARE_API_TOKEN` | DNS record create/update/delete | `arclink_ingress.py` |
| `CLOUDFLARE_ZONE_ID` | Target DNS zone | `arclink_ingress.py` |
| `CHUTES_API_KEY` | Model catalog, per-deployment key lifecycle | `arclink_chutes.py`, `arclink_executor.py` |
| `TELEGRAM_BOT_TOKEN` | Public onboarding bot | `arclink_telegram.py` |
| `DISCORD_BOT_TOKEN` | Public onboarding bot | `arclink_discord.py` |
| `DISCORD_APP_ID` | Interaction signature verification | `arclink_discord.py` |

## Per-Deployment Secrets (Provisioned at Runtime)

These are generated or resolved during provisioning and stored as
`secret://...` references, never as plaintext in database rows or logs.

| Secret | Purpose |
|--------|---------|
| Postgres password | Per-deployment Nextcloud DB |
| Nextcloud admin password | Per-deployment Nextcloud admin |
| Chutes per-deployment API key | Per-deployment model inference |
| App/provider tokens | Per-deployment service auth |

## Secret Handling Rules

1. **No plaintext in database rows.** Use `secret://...` references.
2. **No secrets in logs.** Structured events redact sensitive fields.
3. **No secrets in test fixtures.** All tests run with fake adapters.
4. **No secrets in Compose intent.** Use Compose secret mounts or `_FILE` env vars.
5. **No secrets in admin action metadata.** Rejected before write.
6. **Executor results never include secret values.** Only references and target paths.

## Verification

```bash
# Scan for potential secret leaks in tracked files
git grep -iE '(sk_live|whsec_|Bearer [a-zA-Z0-9]{20,})' -- ':!*.example' ':!*.md'
```

See `docs/arclink/live-e2e-secrets-needed.md` for the full credential checklist
required to run the live E2E harness.
