<<<CODEX-FIX-START CANON-12>>>
## CANON-12 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: python/arclink_notification_delivery.py, python/arclink_control.py, python/arclink_pod_comms.py, python/arclink_gateway_exec_broker.py, tests/test_arclink_notification_delivery.py, tests/test_arclink_pod_comms.py
TESTS: 7 test files run, all pass; py_compile and git diff --check pass
### Fixed (severity — what — path:line)
- HIGH — detached public Agent bridge jobs no longer persist `payload.bot_token`; job files strip runtime secrets and worker rehydrates from platform env before broker/bridge execution — python/arclink_notification_delivery.py:960
- MEDIUM/LOW — Pod Comms message write and notification enqueue are now one transaction via `queue_notification(commit=False)`; enqueue failure rolls back message/audit/event/rate rows — python/arclink_pod_comms.py:307, python/arclink_control.py:8073
- MEDIUM — agent notification consumption now reads `extra_json`, returns parsed `extra`, and marks linked `pod-message` rows delivered with audit/event rows — python/arclink_control.py:9891
- LOW — gateway-exec broker no longer returns raw subprocess stderr/stdout tail to its HTTP caller; it returns only exit status — python/arclink_gateway_exec_broker.py:307
### Skipped (risk-accepted / standing / out-of-scope — why)
- GAP-019 trusted-host/root-equivalence behavior: explicitly risk-accepted by policy.
- Broker `0.0.0.0` binds contained by compose `internal:true`: explicitly skipped by policy.
- agent-process-helper `cap_drop: ALL` vs `setpriv`: standing disagreement requiring live container proof.
- migration-capture raw-vs-resolved state-root symlink reality: deferred to CANON-13 standing/out-of-piece invariant.
- FD-leak finding: reconciled canon rejects it as not a defect.
### NEEDS-DECISION (ambiguous; left for human)
- agent-process-helper arbitrary uppercase non-secret env pass-through: real surface, but narrowing it is a public process-env contract change.
- Pod Comms same-Captain grant bypass and user-pair-scoped cross-Captain grants: changing this would alter sharing semantics/backward compatibility.
- agent-user-helper `chown -R` validate-then-act gap: narrow safe fix is not obvious without deciding whether to replace recursive chown with a pinned/fd-based ownership walk.
- `record_rejection_incident` silent no-op on unsafe/OSError paths: raising could break rejection handling; needs observability-vs-availability decision.
- public_agent_bridge `delivered:true` on absence-of-exception: needs a platform delivery contract, not just local code inference.
### Cross-piece edits made (if any) + tests added
- Cross-piece: python/arclink_notification_delivery.py (CANON-23-adjacent detached job producer/worker) for the CANON-12 bot-token boundary defect.
- Cross-piece: python/arclink_control.py shared notification helper, with additive defaulted `commit` parameter and richer consume payload.
- Tests added/updated: `test_pod_message_enqueue_is_atomic_with_notification`, `test_agent_notification_consumption_preserves_pod_message_metadata_and_status`, detached job secret assertions, and `test_gateway_exec_broker_sanitizes_subprocess_failure_tail`.
<<<CODEX-FIX-END CANON-12>>>
