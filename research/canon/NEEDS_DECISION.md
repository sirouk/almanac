# NEEDS-DECISION Ledger — operator calls deferred by the repair campaign

> The Codex (GPT-5.5) repair campaign fixed genuine defects across all 32 pieces but
> **deferred** the items below: schema/contract changes with wide blast radius,
> threat-model severity calls, and design decisions that are the operator's to make,
> not Codex's to guess. Each is quoted from the per-piece fix report
> (`research/canon/fixes/CANON-NN-*.fix.md`). Risk-accepted designs (GAP-019, etc.) were
> documented-and-skipped separately and are NOT relisted here.

## CANON-01 — control plane schema (1)
- NONE

## CANON-02 — hosted api transport (2)
- MEDIUM — `ARCLINK_BASE_DOMAIN` unset still permits the documented dev pepper fallback unless `ARCLINK_SESSION_HASH_PEPPER_REQUIRED=1`; making unset domain fail closed changes local/dev direct-use behavior, while canonical deploy lanes already set/generate the pepper and required flag.
- MEDIUM — trusted proxy without `X-Forwarded-For` still collapses to the proxy IP; fixing this cleanly needs a separate proxy-vs-admin-CIDR contract because current `ARCLINK_BACKEND_ALLOWED_CIDRS` represents both direct allowed clients and trusted peers.

## CANON-03 — web product surface (2)
- Admin CIDR allowlist XFF dependency remains: fixing it likely requires replacing the Next rewrite with a controlled proxy or proving Next standalone forwarding in live deployment. That is a transport-contract change wider than CANON-03 page code.
- Host-level allowlisting for dynamic ArcPod/fleet dashboard URLs remains policy-sensitive. This patch blocks non-http schemes; constraining arbitrary `https://` hosts needs deployment/domain policy for custom domains, worker URLs, and Tailscale/WireGuard lanes.

## CANON-04 — onboarding provider auth (3)
- NEW onboarding never transitions to `completed`: changing `first_contacted` to terminal `completed` is a public state-contract/index behavior change.
- OLD completion plaintext shared password in chat: current scrub-on-ack handoff is a deliberate UX/security tradeoff; replacing it needs product flow decision.
- `prepare_arclink_onboarding_deployment` committing deployment rows before Stripe checkout: safe fix requires checkout/reservation ordering redesign, not a surgical patch.

## CANON-05 — public bots (1)
- None.

## CANON-06 — curator onboarding (1)
- LOW — Discord operator DM allowed without explicit allowlist when the configured operator channel is a DM. This may be intentional DM-channel-as-operator identity behavior, so I left it unchanged.

## CANON-07 — billing entitlements (1)
- Full forged-metadata policy when neither Stripe customer nor subscription is locally bound. This patch blocks known local ownership conflicts without changing the wider first-binding contract for signed Stripe checkout/subscription events.

## CANON-08 — provisioning enrollment (3)
- `operator_actions.request_source == "operator-raven"` remains a string convention, not a hard capability boundary; hardening requires a cross-piece queue/auth contract decision.
- `host_readiness.check_ingress_strategy` still always returns ok; unclear whether it is intended as a status marker with local fallback or a hard preflight gate.
- Hosted API `source_ip` spoofability is audit-only and owned by the CANON-02 proxy/header trust model, so I did not patch it from CANON-08.

## CANON-09 — ingress dns (4)
- Torn-down-row/global DNS unique-index collision: left unchanged because the normal path is gated by CANON-08 prefix reservation, and changing the index/delete semantics is a schema/contract decision. `python/arclink_control.py:2077`
- Persisted `proxied` drift: left unchanged because fixing it needs a DB schema and live drift contract change, not a surgical CANON-09 patch. `python/arclink_ingress.py:74`
- Public unused `tailscale_dns_name` / `tailscale_host_strategy` args on `desired_arclink_ingress_records`: left unchanged because removing or repurposing them is a public signature decision. `python/arclink_ingress.py:46`
- Non-empty internal commits in DNS helpers remain; removing them would change caller transaction semantics outside the narrow empty-record no-op.

## CANON-10 — inventory capacity (2)
- Hostname-collision capacity clobber across reused fleet hostnames — fixing safely needs a public contract decision on whether re-registering an existing hostname is allowed to update fleet-host capacity.
- `compute_asu` zero RAM/disk global behavior and stale unlinked `asu_consumed` — left unchanged because current contracts explicitly allow zero-capacity summaries and placement-critical rows use linked hosts.

## CANON-11 — executor (3)
- Live Chutes/Stripe admin clients are still not production-implemented/wired. Executor now requires durable DB before any injected client can run, but real Chutes key management and Stripe refund/cancel semantics need provider/product decisions.
- Generic ArcLink replay ledger for compose/lifecycle/DNS beyond the DNS lock needs a contract decision; current compose apply keys can be reused across legitimate deployment updates, so naive replay would break re-apply flows.
- SSH TOFU default (`StrictHostKeyChecking=accept-new`) left unchanged; tightening it would affect first-contact fleet bootstrap policy.

## CANON-12 — gateway brokers (5)
- agent-process-helper arbitrary uppercase non-secret env pass-through: real surface, but narrowing it is a public process-env contract change.
- Pod Comms same-Captain grant bypass and user-pair-scoped cross-Captain grants: changing this would alter sharing semantics/backward compatibility.
- agent-user-helper `chown -R` validate-then-act gap: narrow safe fix is not obvious without deciding whether to replace recursive chown with a pinned/fd-based ownership walk.
- `record_rejection_incident` silent no-op on unsafe/OSError paths: raising could break rejection handling; needs observability-vs-availability decision.
- public_agent_bridge `delivered:true` on absence-of-exception: needs a platform delivery contract, not just local code inference.

## CANON-13 — pod migration (3)
- True target-host-scoped health verification needs a DB/wire contract change because `arclink_service_health` has no host/migration column. I fixed empty/stale fail-open by requiring fresh post-start health, but did not alter schema.
- Dry-run-to-live reuse of the same `migration_id` still needs a contract decision; fixing it cleanly changes idempotency-key semantics and dry-run planned-row promotion.
- Rollback lifecycle best-effort semantics left unchanged; changing `rolled_back` vs `failed` behavior on teardown/restart failure is a public status contract decision.

## CANON-14 — operator admin control (1)
- tests/test_arclink_action_worker.py still fails at `test_academy_apply_action_materializes_local_hermes_home_when_authorized`: current code fails closed because PG-PROVIDER live review is not complete. I did not rewrite that CANON-17/Academy expectation in this CANON-14 repair.

## CANON-15 — operator upgrade pipeline (1)
- NONE

## CANON-16 — llm router providers (2)
- Budget fail-open provenance for `observe_only_unlimited` — lane is deliberate for the Operator Pod; changing router acceptance requires a product/provenance rule for configurable operator identities.
- Mid-stream error SSE after valid chunks — changing partial-stream wire shape could break clients; needs an explicit contract decision.

## CANON-17 — academy crew soul (1)
- NONE

## CANON-18 — knowledge memory notion mcp (2)
- Initial Notion verification-token first-caller authenticity under public Funnel is still a workflow contract problem. The race is fixed, but fully preventing arbitrary first POSTs requires a product decision such as a nonce-bearing webhook URL or gating signed events on operator confirmation.
- Webhook `/health` remains pre-auth because `tests/test_loopback_service_hardening.py` explicitly asserts that contract; changing it would affect health/monitoring behavior.

## CANON-19 — workspace dashboard (4)
- Backup deploy-key staging persists a private key and the `backup_deploy_key_private_ref` rail has no consumer; changing/removing it would alter the public backup setup contract.
- Silent SSO secret generation/default enablement in Docker/domain mode needs a product decision on whether SSO should be opt-in.
- Process-local auth-proxy login throttle needs a shared-store design if it should survive restarts/multiple proxy processes.
- Env-derived dashboard host validation needs allowed-host policy before tightening operator env URL formats.

## CANON-20 — sharing fleet folder (3)
- Full hub URL host/scheme allowlist: production supports operator-provided remote SSH hubs; I only blocked git remote-helper command syntax.
- Distributed fleet-share sync locking / bounded retry policy: a true cross-machine lock requires hub/broker design, not a local retry tweak.
- Dead `paused` / member `pending` statuses: removing or activating them changes schema/API contract.

## CANON-21 — org profile (2)
- Whether org-profile fan-out should include non-`role='user'` or inactive agents; current scope looks like an intentional contract boundary.
- Whether unmatched slice deletion needs a separate audit/event rail beyond the existing apply report; that crosses reporting/notification ownership.

## CANON-22 — backup restore wrapped (2)
- Quiet-hours local/DST semantics: current code is UTC-only; a real local-time fix needs a timezone/config contract.
- Backup reconcile single-writer locking: adding in-script flock/state locks would change the current timer/cron ownership model and needs an operator state-path decision.

## CANON-23 — diagnostics health evidence (1)
- `run_diagnostics(live=...)` still documents future real provider connectivity; implementing actual live provider checks would change external-provider semantics and needs product/threat-model decision.

## CANON-24 — deploy install lane (1)
- Whether to unify `init.sh` remote `auto_provision` and `bin/init.sh` host-side `source_ip` payloads for `bootstrap.handshake`; left unchanged pending CANON-18 consumer decision.

## CANON-25 — compose containers (4)
- `agent-process-helper-egress-net` remains non-internal: current tests require it for “outbound-only runtime work”; safely fixing listener exposure likely needs a design change, not a one-line compose edit.
- `docker-job-loop.sh` still does not exit on child failure: making recurring jobs crash on poll failure changes restart cadence across many services.
- `health()` still repairs Nextcloud data permissions as a side effect; removing that mutating repair could change live recovery behavior.
- Embedded and standalone Nextcloud still share default host port `18080`; changing the standalone default is a public/default contract decision.

## CANON-26 — systemd units (1)
- NONE

## CANON-27 — config environment (2)
- `config/team-resources.example.tsv` remains pipe-delimited despite `.tsv`; renaming is a public/operator contract change.
- Expanding docker-authority inventory tests to derive every structured field from Compose crosses CANON-12/25 boundaries and needs owner agreement.

## CANON-28 — ci smoke gates (3)
- Orphaned test functions: enforcing a repository-wide self-executing test call-graph from CANON-28 would be a broad CANON-29 test-corpus contract change.
- Provider-auth/provider-unavailable live-smoke skip still exits 0: this is deliberate best-effort deploy behavior; making it fail closed could block upgrades on provider outages.
- Full ruff/pyflakes style enforcement: I added a passing fatal lint gate; strict full pyflakes/ruff currently flags existing cross-piece warnings and needs a broader cleanup decision.

## CANON-29 — test corpus (1)
- Literal dedicated new `tests/test_arclink_upgrade_policy.py` / `tests/test_arclink_rejection_incidents.py` files could not be created because the `tests/` directory is not writable in this workspace. I added direct behavioral coverage inside existing runnable files instead.

## CANON-30 — hermes plugins (2)
- Full replacement of installer regex/indentation YAML edits with a comment-preserving YAML parser. I added backups, but parser replacement needs dependency/formatting policy because current tests intentionally preserve comments and future nested config.
- Full Drive denylist/TOCTOU redesign. I fixed the empty-root guard, but complete mitigation likely needs fd-anchored file operations or an allowlist policy that changes file-manager behavior.

## CANON-31 — ops scripts skills templates (1)
- Whether to fully remove/rename ENABLE_TAILSCALE_SERVE and the related install prompts/agent tailnet URL assumptions. I stopped the active teardown path, but broader config-contract migration has wider blast radius.

## CANON-32 — docs corpus provenance (1)
- `python3 tests/test_public_repo_hygiene.py` currently fails on provider-name hits in immutable/current spec text (`CANON.md`) and unrelated `tests/test_arclink_evidence.py`. Fixing that requires a hygiene policy/allowlist decision outside CANON-32’s repair scope.

---

**Total: ~66 deferred operator decisions across the 32 pieces.**
