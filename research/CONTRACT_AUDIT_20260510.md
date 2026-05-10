# Contract Audit 2026-05-10

Scope: end-to-end no-secret contract pass after the Raven selected-agent bridge
repair. This audit checked public repo contracts, focused regression suites,
web/browser surfaces, live control-node health, live deployment state, and the
Raven-to-agent runtime bridge without printing secrets or forcing a
user-visible Telegram/Discord message.

## Current Contract Counts

`research/PRODUCT_REALITY_MATRIX.md` now classifies 121 rows:

| Status | Count |
| --- | ---: |
| `real` | 101 |
| `partial` | 0 |
| `gap` | 0 |
| `proof-gated` | 15 |
| `policy-question` | 5 |

Raven direct-agent public chat scope moved from `policy-question` to `real`:
slash commands remain Raven controls, and onboarded-user freeform public
messages queue selected-agent turns through `notification-delivery`.

## Verified Contract Path

1. Website, Telegram, and Discord share the public onboarding/bot contract.
2. Stripe entitlement tests prove deployment remains gated until paid state.
3. Sovereign worker tests prove paid deployment handoff, ready notifications,
   and service-health refresh.
4. User/admin API tests prove scoped sessions, CSRF, credential acknowledgement,
   share grants, provider state, billing state, and cross-user denial.
5. Raven bot tests prove command routing, channel linking, selected-agent
   switching, share approval scoping, Raven display-name scoping, and freeform
   selected-agent queueing.
6. Notification delivery tests prove public-agent-turn execution and same
   Telegram/Discord channel return delivery.
7. Docker/Compose tests prove the control stack, trusted socket boundaries,
   deployment runtime assets, and health contracts.
8. Plugin/MCP/memory tests prove Drive, Code, Terminal, Linked roots, managed
   context, qmd retrieval, shares.request, recall stubs, and fallback memory
   synthesis boundaries.
9. Notion/SSOT tests prove shared-root indexing, webhook batching, brokered
   read/write preflight, and no-secret live-proof harnesses.
10. Web tests prove API route parity, dashboard/admin/onboarding pages, mobile
    layouts, disabled fake/live claims, and browser tab surfaces.
11. Live control health reports `32 ok`, `2 warn`, `0 fail`.
12. Live deployed bridge proof from inside `arclink-notification-delivery-1`
    reached the `sirouk | TuDudes` Hermes gateway and returned
    `contract bridge ok`.

## Live State Snapshot

- Deployed commit: `7dc5a511f9513054db9fd47a0fd68111481c8fee`.
- Tracked upstream branch: `arclink`.
- Active deployments: 1.
- Provisioning jobs: 1 succeeded.
- Pending notification outbox rows: 0.
- Latest deployment service-health rows for dashboard, Hermes gateway,
  Hermes dashboard, qmd, vault-watch, memory-synth, Nextcloud, Notion webhook,
  notification delivery, and health-watch are healthy.
- Public web returns HTTP 200 on the local ingress.
- Hosted API `/health` returns `{"db": true, "status": "ok"}`.
- Hermes dashboard path returns HTTP 401, which proves the protected dashboard
  endpoint is alive and requires authentication.

## Remaining Gates

These are intentionally not closed by local/no-secret proof:

- Live Stripe checkout/webhook proof.
- Live Telegram and Discord user-visible delivery proof.
- Live Chutes OAuth, usage, key CRUD, account registration, balance transfer,
  and provider-balance application proof.
- Live Notion shared-root mutation proof.
- Live Cloudflare zone and Tailscale certificate/serve proof.
- Browser right-click Drive/Code share-link enablement.
- Canonical Chutes provider path policy.
- Threshold/refuel continuation copy and self-service provider-change policy.
- Scoped agent self-model or peer-awareness policy.

## Warnings To Track

- `memory-synth` health is warn because the current configured model returned
  non-JSON for several vault lanes. Local memory synthesis and fallback tests
  pass, and deployment service-health marks the memory-synth container healthy.
- The internal Docker health check warns that Traefik HTTPS is unreachable at
  `control-ingress:443`. Current public HTTPS is published through the
  Tailscale/Funnel path, while the container exposes local HTTP on port 8080.

## Validation Run

- `python3 tests/test_arclink_public_bots.py`
- `python3 tests/test_arclink_notification_delivery.py`
- `python3 tests/test_arclink_hosted_api.py`
- `python3 tests/test_arclink_api_auth.py`
- `python3 tests/test_arclink_telegram.py`
- `python3 tests/test_arclink_discord.py`
- `python3 tests/test_arclink_sovereign_worker.py`
- `python3 tests/test_arclink_docker.py`
- `python3 tests/test_arclink_plugins.py`
- `python3 tests/test_arclink_mcp_schemas.py`
- `python3 tests/test_memory_synthesizer.py`
- `python3 tests/test_arclink_memory_sync.py`
- `python3 tests/test_arclink_notion_knowledge.py`
- `python3 tests/test_notion_ssot.py`
- `python3 tests/test_arclink_notion_webhook.py`
- `python3 tests/test_arclink_ssot_batcher.py`
- `python3 tests/test_arclink_entitlements.py`
- `python3 tests/test_arclink_chutes_and_adapters.py`
- `python3 tests/test_arclink_chutes_oauth.py`
- `python3 tests/test_arclink_chutes_live_adapter.py`
- `python3 tests/test_arclink_dashboard.py`
- `python3 tests/test_deploy_regressions.py`
- `python3 tests/test_health_regressions.py`
- `python3 tests/test_arclink_product_config.py`
- `python3 tests/test_documentation_truths.py`
- `python3 tests/test_public_repo_hygiene.py`
- `bash -n deploy.sh bin/*.sh test.sh`
- `python3 -m py_compile` for the touched/high-risk Python modules
- `docker compose --env-file arclink-priv/config/docker.env config --quiet`
- `git diff --check`
- `cd web && npm test`
- `cd web && npm run lint`
- `cd web && npm run build`
- `cd web && npm run test:browser`
- `bin/arclink-live-proof --json`
- `bin/arclink-live-proof --journey external --json`
- `./deploy.sh control health`

All local/static/browser checks passed. Both live-proof commands correctly
reported `blocked_missing_credentials` for gated external proof instead of
pretending live provider proof had run.
