<<<CODEX-VERDICT-START CANON-08>>>
## CANON-08 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(3)
ONE-LINE VERDICT: CANON-08 mostly holds, but fleet audit-chain soundness is overstated, fleet consume has committed pre-guard side effects, and the operator-source gate is a current-writer convention, not a hard capability boundary.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM: Non-Docker pin-upgrade has no component allowlist; `_pin_upgrade_command_args` only requires nonempty `component`, nonempty `target`, and a valid kind flag before argv execution. `python/arclink_enrollment_provisioner.py:429-448`, `python/arclink_enrollment_provisioner.py:483-500`
- CONFIRM: Docker broker does enforce the allowlist the non-Docker path lacks. `python/arclink_operator_upgrade_broker.py:47-48`, `python/arclink_operator_upgrade_broker.py:265-273`
- CONFIRM: Fleet audit-chain “cryptographically sound / P0 on tamper” is false for legacy hashes; verifier accepts unprefixed SHA-256 by recomputing with `secret=""`, and P0 only queues when `errors` exist. `python/arclink_fleet_enrollment.py:469-472`, `python/arclink_fleet_enrollment.py:884-912`
- REFINE: `operator-raven` source is currently emitted only by Operator Raven queue paths I found, and those paths require actor + confirmation/nonce, but `request_operator_action` blindly persists caller-supplied `request_source`; the gate is source-string based. `python/arclink_operator_raven.py:1293-1314`, `python/arclink_operator_raven.py:1545-1564`, `python/arclink_operator_raven.py:1624-1639`, `python/arclink_control.py:8260-8306`
- REFINE: UnicodeDecodeError still escapes the RuntimeError/rc=2 contract, but the row is not permanent; stale-running recovery marks it failed after 30 minutes on a later run. `python/arclink_enrollment_provisioner.py:334-343`, `python/arclink_enrollment_provisioner.py:613-647`, `python/arclink_enrollment_provisioner.py:2322-2329`
- CONFIRM: HMAC broker seam byte-matches: client signs `timestamp\nnonce\nbody_hash`; broker hashes raw body and verifies the same preimage with TTL + nonce replay check. `python/arclink_enrollment_provisioner.py:310-330`, `python/arclink_operator_upgrade_broker.py:686-716`
- CONFIRM: Intent renderer returns only after recursive plaintext-secret validation. `python/arclink_provisioning.py:1398-1421`, `python/arclink_provisioning.py:1701-1782`
- CONFIRM: SSO seam is live, not dead: provisioning emits `dashboard_sso_secret`, install writes SSO fields, proxy loads them and emits an SSO cookie. `python/arclink_provisioning.py:666-669`, `bin/install-deployment-hermes-home.sh:163-170`, `python/arclink_dashboard_auth_proxy.py:180-186`, `python/arclink_dashboard_auth_proxy.py:729-735`
- CONFIRM: `secret_refs.llm_router_api_key` is absent in `direct_chutes` mode and migration silently skips when absent. `python/arclink_provisioning.py:657-665`, `python/arclink_pod_migration.py:736-739`

### New findings both Claude passes missed (severity + path:line)
- MEDIUM: Fleet enrollment consume is not transaction-clean. `consume_fleet_enrollment()` calls `register_inventory_machine()` before the single-use token `UPDATE ... status='pending'` guard; that registration commits, and `register_fleet_host()` can also commit, so a replay race or post-register failure can leave inventory/fleet-host side effects even when token consumption later fails. `python/arclink_fleet_enrollment.py:651-698`, `python/arclink_inventory.py:173-182`, `python/arclink_inventory.py:253-263`, `python/arclink_fleet.py:238-248`

### Claude citations re-confirmed or corrected
- Re-confirmed: Hosted API passes Bearer token + JSON body to `consume_fleet_enrollment`; failures become 401. `python/arclink_hosted_api.py:2035-2050`
- Re-confirmed: Fleet token checks compare both token signature and stored token hash, then reject non-`pending`. `python/arclink_fleet_enrollment.py:92-123`
- Re-confirmed: Host readiness excludes `secret_*` checks from `ready`, and ingress check is tautological `ok=True`. `python/arclink_host_readiness.py:154-183`
- Re-confirmed: `agent_access` ownership guarantee is overstated because `chown/chmod` `OSError` is swallowed. `python/arclink_agent_access.py:69-75`
- Corrected: The verifier’s “TOCTOU clean single-winner, no orphan inventory row” conclusion misses the committed side effects above. `python/arclink_inventory.py:262`, `python/arclink_fleet_enrollment.py:689-698`

### Residual disagreement with the Claude half (for final reconciliation)
- Disagree with the original record’s fleet-audit verdict: HMAC entries are checked, but legacy unkeyed entries are still accepted and can be fully re-forged by a DB writer. `python/arclink_fleet_enrollment.py:886-902`
- Disagree with the verifier’s concurrency proof: losing consumes do not necessarily roll back all earlier side effects because registration helpers commit before the consume guard. `python/arclink_inventory.py:253-263`, `python/arclink_fleet_enrollment.py:689-698`
- Keep the `operator-raven` seam as “current code-path confirmed, helper spoofable by design,” not as a cryptographic authorization boundary. `python/arclink_enrollment_provisioner.py:2292-2297`, `python/arclink_control.py:8294-8303`
<<<CODEX-VERDICT-END CANON-08>>>
