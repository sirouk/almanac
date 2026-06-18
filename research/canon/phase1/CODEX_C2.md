<<<CODEX-C2-START>>>
SIGN-OFF: OBJECT(2)
### A bridge resolve-on-delivery
CONFIRM-FIXED for the stated success-site wiring: broker success resolves at `python/arclink_notification_delivery.py:1696`, bridge worker success at `python/arclink_notification_delivery.py:1811`, album absorption at `python/arclink_notification_delivery.py:2273`, public-agent loop success at `python/arclink_notification_delivery.py:2469`, and generic loop success at `python/arclink_notification_delivery.py:2695`. Report/resolve share the same per-row key at `python/arclink_notification_delivery.py:398`, `python/arclink_notification_delivery.py:425`, so `resolve_operator_hiccup` re-arms via the resolved audit row at `python/arclink_control.py:8419`.

NEW-ISSUE: the threshold is not actually “8 terminal attempts.” `_mark_public_agent_bridge_unconfirmed` increments `attempt_count` for explicitly non-terminal held/unknown outcomes at `python/arclink_notification_delivery.py:1500`, `python/arclink_notification_delivery.py:1516`, `python/arclink_notification_delivery.py:1526`; `_maybe_report_public_agent_bridge_hiccup` then pages only from total `attempt_count` at `python/arclink_notification_delivery.py:478`. After 7 unconfirmed/possibly-delivered D5 outcomes, one terminal error can page as “8 terminal attempts” at `python/arclink_notification_delivery.py:486`. That is a remaining false-alarm path.

### B bridge scope
CONFIRM-FIXED. The bridge hiccup gate now reads the outbox row and returns unless `target_kind == "public-agent-turn"` at `python/arclink_notification_delivery.py:459` and `python/arclink_notification_delivery.py:473`. Generic `public-bot-user` delivery errors can still call the helper from the generic loop at `python/arclink_notification_delivery.py:2689`, but they return before paging.

### C provisioning durable-runtime
CONFIRM-FIXED for the original overwrite bug: the snapshot is taken before `_record_service_status(... failed ...)` at `python/arclink_sovereign_worker.py:858`, passed into the exhausted gate at `python/arclink_sovereign_worker.py:867`, and treated authoritatively at `python/arclink_sovereign_worker.py:909`.

NEW-ISSUE: the snapshot can still be false when the pod is actually running if `docker compose up -d` succeeds, but the subsequent `docker compose ps` reconciliation fails. `_record_service_status_after_compose` catches that inspection failure and records all services as `failed` at `python/arclink_sovereign_worker.py:2171`; the outer handler snapshots that synthetic failed table at `python/arclink_sovereign_worker.py:858`, then can release/page at `python/arclink_sovereign_worker.py:914` and `python/arclink_sovereign_worker.py:962`. That can page/release a serving pod on a post-apply inspection/transport hiccup.

The exhausted+no-runtime real failure still pages once: no durable runtime falls through to `remove_placement` at `python/arclink_sovereign_worker.py:923`, re-entry returns before paging at `python/arclink_sovereign_worker.py:924`, and the report is queued at `python/arclink_sovereign_worker.py:998`.

### D new false-alarm/regression
BLOCKING false-alarm paths:
1. Bridge count mixes non-terminal unconfirmed attempts into the terminal threshold: `python/arclink_notification_delivery.py:1500` plus `python/arclink_notification_delivery.py:478`.
2. Provisioning treats post-apply compose-ps transport failure as proof of no runtime: `python/arclink_sovereign_worker.py:2171` plus `python/arclink_sovereign_worker.py:914`.

I did not find scope narrowing breaking normal retry/lease behavior; deferred/unconfirmed branches still continue before error reporting at `python/arclink_notification_delivery.py:2456` and `python/arclink_notification_delivery.py:2678`.

### E tests
Provisioning tests now drive the real worker batch and placement predicates: `tests/test_arclink_sovereign_worker.py:714` and `tests/test_arclink_sovereign_worker.py:784`, included in the file main at `tests/test_arclink_sovereign_worker.py:1831`.

Bridge page-then-deliver is still helper-level/tautological for wiring: it directly calls `_maybe_report_public_agent_bridge_hiccup`, then `mark_notification_delivered`, then `_resolve_public_agent_bridge_hiccup` at `tests/test_arclink_operator_hiccup.py:357` and `tests/test_arclink_operator_hiccup.py:370`. It does not prove the real broker/bridge/album/public-loop/generic-loop success sites. The D5 test only covers below-threshold held rows at `tests/test_arclink_operator_hiccup.py:421`, so it misses the unconfirmed-count false-alarm path.

Could not run tests in this read-only workspace: Python reported no usable temporary directory for `tempfile`.

### F other
I would block deploy on the two false-alarm paths above.
<<<CODEX-C2-END>>>
