<<<CODEX-C4-START>>>
SIGN-OFF: RATIFY

### A merge-safe extra_json
CONFIRM-FIXED. The public-agent-turn `extra_json` writers are now per-key SQL writes: bump at `python/arclink_notification_delivery.py:451`, reset at `python/arclink_notification_delivery.py:505`, worker metadata at `python/arclink_notification_delivery.py:1706`, and reaper `reclaimed_at` at `python/arclink_notification_delivery.py:1792`. The bump re-reads persisted state at `python/arclink_notification_delivery.py:471`. The only remaining whole `notification_outbox.extra_json` assignment I found is curator/notion-reindex, not this row class, at `python/arclink_control.py:15484`.

### B serving cross-pass
CONFIRM-FIXED in code. The except path snapshots runtime at `python/arclink_sovereign_worker.py:858`, writes `unknown` only for `None` at `python/arclink_sovereign_worker.py:887`, writes `failed` only for `False` at `python/arclink_sovereign_worker.py:894`, and intentionally leaves `True` untouched. Snapshot-less re-entry uses the tri-state read at `python/arclink_sovereign_worker.py:989`; `True` and `None` retain at `python/arclink_sovereign_worker.py:994` and `python/arclink_sovereign_worker.py:1003`, while `False` releases/pages at `python/arclink_sovereign_worker.py:1016` and `python/arclink_sovereign_worker.py:1055`.

### C new false-alarm/regression
No new false-alarm path found. Reaper still reads worker pid/lease metadata before acting at `python/arclink_notification_delivery.py:1768`, then only stamps the nested `reclaimed_at` key at `python/arclink_notification_delivery.py:1792`. Real bridge terminal failures still gate/page via `python/arclink_notification_delivery.py:605`; real dead provisioning failures still release/page via `python/arclink_sovereign_worker.py:1016`. Stale serving health can still bias toward retention, but that is false silence, not a false alarm.

### D tests
Race test is non-tautological: it fires the reset during real metadata recording at `tests/test_arclink_operator_hiccup.py:770`, asserts counter not resurrected at `tests/test_arclink_operator_hiccup.py:793`, asserts worker key survives at `tests/test_arclink_operator_hiccup.py:801`, and asserts no page at `tests/test_arclink_operator_hiccup.py:819`.

Provisioning serving test verifies pass 1, but its claimed second worker pass is mostly tautological: it sets `max_attempts=1` at `tests/test_arclink_sovereign_worker.py:698`, calls the second batch at `tests/test_arclink_sovereign_worker.py:773`, but batch selection excludes failed jobs at max attempts at `python/arclink_sovereign_worker.py:565`. `main()` includes the new tests at `tests/test_arclink_operator_hiccup.py:884` and `tests/test_arclink_sovereign_worker.py:1954`. I could not execute them in this read-only sandbox: Python reported no usable temporary directory.

### E other
No deploy-blocking false-alarm issue found. Test coverage should be tightened for the serving re-entry branch, but code wins.
<<<CODEX-C4-END>>>
