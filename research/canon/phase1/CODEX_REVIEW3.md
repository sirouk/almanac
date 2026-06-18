<<<CODEX-REVIEW3-START>>>
SIGN-OFF: RATIFY
### Stale-positive
CLOSED. `_gateway_has_public_agent_bridge_root_wrapper` now trusts only cached `False` within TTL (`python/arclink_notification_delivery.py:713-721`). Cached `True` falls through to a fresh `docker exec ... test -e` probe (`python/arclink_notification_delivery.py:722-727`), then overwrites the cache with the new result (`python/arclink_notification_delivery.py:730-731`). Callers route `False` to legacy bridge commands (`python/arclink_notification_delivery.py:734-744`, `python/arclink_notification_delivery.py:757-769`). The regression captures positive re-probe and negative caching (`tests/test_arclink_notification_delivery.py:3584-3625`).

### New issues from the fix
No sign-off-changing issue. The positive path does add one bounded probe per L2-enabled turn, but it is not an unbounded loop: the probe has `timeout=15` and no retry loop (`python/arclink_notification_delivery.py:725-727`). Probe timeout/error/nonzero becomes `present=False`, so the command builder falls back to legacy (`python/arclink_notification_delivery.py:728-731`, `python/arclink_notification_delivery.py:742-744`, `python/arclink_notification_delivery.py:763-769`). Cached negatives still suppress probe churn for 300s (`python/arclink_notification_delivery.py:700-721`).

A flapping wrapper can toggle L2 wrapper vs legacy per turn. That is acceptable: L2 is only the Telegram `getMe` cache, while legacy is the normal bridge path. A wrapper disappearing after a successful probe can still fail that single invocation, but the stale-positive TTL hole is gone; the next turn/retry re-probes.

### Final verdict on the public-bridge effort
No change to my broader sign-off. Replay remains guarded against duplicate generic dispatch (`python/arclink_public_agent_bridge.py:907-934`). D5 still requires confirmed message ids before delivery (`python/arclink_public_agent_bridge.py:102-119`, `python/arclink_notification_delivery.py:415-455`). Broker responses preserve bridge delivery evidence (`python/arclink_gateway_exec_broker.py:292-299`). The broker flag is wired into the broker service (`compose.yaml:1023-1028`). The reaper records and re-arms dead detached workers (`python/arclink_notification_delivery.py:1376-1496`). The root wrapper preloads as root, then drops the child to the runtime uid/gid (`python/arclink_public_agent_bridge_root.py:55-64`, `python/arclink_public_agent_bridge_root.py:114-127`). L2 cache isolation remains HMAC-keyed, root-owned/outside agent roots, and fail-open (`python/arclink_public_agent_bridge.py:401-405`, `python/arclink_public_agent_bridge.py:423-480`, `python/arclink_public_agent_bridge.py:595-619`).

RATIFY for the whole public-bridge effort.
<<<CODEX-REVIEW3-END>>>
