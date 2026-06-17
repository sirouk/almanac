<<<CODEX-VERDICT-START CANON-09>>>
## CANON-09 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(2)
ONE-LINE VERDICT: Core CANON-09 is sound; refine the prefix-collision risk and add one live DNS-repair tracking gap.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM — Desired DNS is exactly dashboard/hermes CNAMEs with `proxied=True`; files/code are filtered out. `python/arclink_ingress.py:35-43`, `python/arclink_adapters.py:228-238`
- CONFIRM — Live provisioning seam matches: intent calls `desired_arclink_ingress_records`, projects four `DnsRecord` fields, sovereign worker rebuilds `DnsRecord`s and persists. `python/arclink_provisioning.py:1487-1494`, `python/arclink_provisioning.py:1744-1752`, `python/arclink_sovereign_worker.py:1981-1992`
- CONFIRM — MEDIUM dead/divergent API surface is real as a doc-trust hazard: wrappers exist, but production imports only desired/render/persist/read/mark helpers. `python/arclink_ingress.py:114`, `python/arclink_ingress.py:192`, `python/arclink_ingress.py:207`, `python/arclink_provisioning.py:25`, `python/arclink_action_worker.py:31`, `python/arclink_sovereign_worker.py:67`
- REFINE — §5C#49 severity: operational risk is LOW because the wrappers are not on the live path; MEDIUM is defensible only for documentation/test-trust drift. `tests/test_arclink_ingress.py:49`, `tests/test_arclink_ingress.py:86`, `tests/test_arclink_ingress.py:122`
- CONFIRM — MEDIUM bulk status clobber: `_mark_dns_status` updates every row for the deployment, and teardown calls it after provider teardown/skips. `python/arclink_ingress.py:145-148`, `python/arclink_sovereign_worker.py:1365-1377`
- REFINE — Torn-down-row UNIQUE-index crash is not normally reachable through the reservation path: DNS rows persist and the DNS index is global, but deployment prefix reuse is blocked by `idx_arclink_deployments_prefix` and the single production reserve insert path. Risk remains for DB bypass/manual corruption, not ordinary onboarding. `python/arclink_control.py:1947-1948`, `python/arclink_control.py:3591-3616`, `python/arclink_control.py:2077-2078`, `python/arclink_ingress.py:78`
- CONFIRM — `provider_record_id` is out-of-piece state: ingress reads it for teardown but never writes it; sovereign `_mark_dns_provisioned` backfills from executor metadata. `python/arclink_ingress.py:74-77`, `python/arclink_ingress.py:174-186`, `python/arclink_sovereign_worker.py:2011-2023`, `python/arclink_executor.py:1174`
- CONFIRM — Live teardown over-reports attempted hostnames as removed when Cloudflare find/delete is a silent no-op. `python/arclink_executor.py:1041-1050`, `python/arclink_executor.py:2584-2589`, `python/arclink_ingress.py:166-168`
- CONFIRM — `proxied` is applied live from intent but not persisted; live code has no persisted proxied drift detector. `python/arclink_executor.py:2515`, `python/arclink_executor.py:2555`, `python/arclink_ingress.py:74-77`, `python/arclink_adapters.py:202-210`
- CONFIRM — Test-only retry catches all `Exception`s. `python/arclink_ingress.py:221-231`

### New findings both Claude passes missed (severity + path:line)
- MEDIUM — `dns_repair` can apply DNS with no DB tracking when rows are absent or explicit DNS is supplied: `_resolve_dns_repair` returns computed/explicit DNS, the action worker calls `executor.cloudflare_dns_apply`, then returns without `persist_arclink_dns_records` or provider-id/status backfill; later teardown only reads `arclink_dns_records`. `python/arclink_action_worker.py:168-179`, `python/arclink_action_worker.py:209-231`, `python/arclink_action_worker.py:858-880`, `python/arclink_ingress.py:171-189`
- INFO — Dead `teardown_arclink_dns` passes all four hostnames to the fake cloudflare client even though provisioning creates only dashboard/hermes records; harmless only because the wrapper is non-production. `python/arclink_ingress.py:201-203`, `python/arclink_adapters.py:233-238`

### Claude citations re-confirmed or corrected
- Reconfirmed: sole tracked code member is `python/arclink_ingress.py`; it has 284 lines.
- Reconfirmed: schema, event append, teardown record shape, and executor consumer shape match. `python/arclink_control.py:1138-1149`, `python/arclink_control.py:3870-3889`, `python/arclink_ingress.py:182-188`, `python/arclink_executor.py:2521-2530`
- Corrected: the intent DNS dict projection is `python/arclink_provisioning.py:1744-1752`; the earlier `~1505` citation is stale/loose.
- Corrected: `created_at` is written on INSERT only; the conflict update changes `last_checked_at` and `updated_at`, not `created_at`. `python/arclink_ingress.py:74-91`

### Residual disagreement with the Claude half (for final reconciliation)
- Prefix-collision risk should be downgraded or caveated: normal code proves prefix uniqueness before DNS persistence, so the unhandled DNS-index `IntegrityError` is a bypass/corruption scenario, not a normal torn-down redeploy path. `python/arclink_control.py:1947-1948`, `python/arclink_control.py:3585-3616`
- Add the action-worker `dns_repair` untracked-apply gap to CANON-09 seams/risk register. `python/arclink_action_worker.py:858-880`, `python/arclink_ingress.py:171-189`
<<<CODEX-VERDICT-END CANON-09>>>
