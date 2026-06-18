<<<CODEX-REVIEW2-START>>>
SIGN-OFF: OBJECT(1)
### A. Replay
CONFIRM-FIXED. `adapter.handle_message(event)` is now inside `if not replayed`, and `event` is only bound in that block: `python/arclink_public_agent_bridge.py:921-933`. The replayed path still drains pending adapter work, persists Telegram bridge state, and returns evidence: `python/arclink_public_agent_bridge.py:934-936`. I found no remaining replay-only unbound reference in `_run_telegram`.

### B. Preflight
CONFIRM-FIXED for cold flag-on + missing-wrapper skew. The builder only uses the root wrapper when the L2 flag is enabled and `_gateway_has_public_agent_bridge_root_wrapper(...)` returns true: `python/arclink_notification_delivery.py:728-733`. Missing wrapper/nonzero probe, timeout, or any exception falls back to legacy because `present` defaults false and exceptions are swallowed: `python/arclink_notification_delivery.py:716-725`. Both direct and Compose builders use that gate: `python/arclink_notification_delivery.py:736-748`, `python/arclink_notification_delivery.py:751-780`. The probe uses the resolved `ARCLINK_DOCKER_BINARY`: `python/arclink_notification_delivery.py:716-720`. It is TTL-cached, not per-turn in a long-lived process: `python/arclink_notification_delivery.py:700-715`.

NEW-ISSUE: stale-positive cache can still hard-fail for up to 300s after a target gateway is recreated/rolled back without the wrapper under the same container/Compose prefix. The cache key is only `tuple(exec_prefix)`, and cached true returns before probing: `python/arclink_notification_delivery.py:711-715`; the root-wrapper command is then emitted unconditionally from that cached true: `python/arclink_notification_delivery.py:736-748`, `python/arclink_notification_delivery.py:751-780`. That is worse than acceptable L2-off flapping: it can reintroduce wrapper-missing hard failures until TTL expiry.

The preflight is outside `_validate_public_agent_bridge_cmd`, but the prefix is generated locally, not request-supplied. Broker request validation/preflight happens before command construction for Compose fallback: `python/arclink_gateway_exec_broker.py:245-263`; final bridge commands are still allowlisted: `python/arclink_gateway_exec_broker.py:264-267`.

### C. Broker flag
CONFIRM-FIXED. `gateway-exec-broker` now receives `ARCLINK_BRIDGE_SINGLE_PLATFORM_CONFIG` and `ARCLINK_BRIDGE_GETME_CACHE`: `compose.yaml:1023-1028`. The broker reconstructs commands through the same gated builders: `python/arclink_gateway_exec_broker.py:218-222`, `python/arclink_gateway_exec_broker.py:241-264`, so enabling the flag is protected by the preflight, subject to the stale-positive cache objection above.

### D. Regression check
No weakening found in the previously confirmed surfaces. Root wrapper still preloads only as root and runs the bridge child through `preexec_fn` privilege drop: `python/arclink_public_agent_bridge_root.py:114-128`. D5 evidence still requires confirmed platform ids before delivered: `python/arclink_public_agent_bridge.py:102-120`, `python/arclink_notification_delivery.py:415-455`. The reaper still only reclaims dead detached workers: `python/arclink_notification_delivery.py:1450-1490`. L2 cache isolation remains root-owned, mode `0700`, outside agent roots, and fail-open to live `getMe`: `python/arclink_public_agent_bridge.py:423-480`, `python/arclink_public_agent_bridge.py:595-619`.

### E. Residual
Still acknowledged and not made worse. The irreducible at-least-once duplicate remains: a detached worker can send successfully and die before marking delivered; delivered is written only after confirmed bridge output: `python/arclink_notification_delivery.py:1631-1645`. Unknown outcomes are held for reconciliation: `python/arclink_notification_delivery.py:1646-1660`; hard timeout/failed-no-id paths still become retryable errors, so a real send with no id before failure can duplicate later: `python/arclink_notification_delivery.py:1600-1606`, `python/arclink_notification_delivery.py:465-469`.
<<<CODEX-REVIEW2-END>>>
