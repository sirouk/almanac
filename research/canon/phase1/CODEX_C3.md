<<<CODEX-C3-START>>>
SIGN-OFF: OBJECT(2)

### A consecutive terminal counter
STILL-BROKEN. Direct non-racy paths are fixed: terminal credit is centralized in `_maybe_report_public_agent_bridge_hiccup` via `_bump...` at `python/arclink_notification_delivery.py:580`, D5 unconfirmed resets at `python/arclink_notification_delivery.py:1641`, `:1821`, `:1940`, and deferred resets at `python/arclink_notification_delivery.py:2570`, `:2796`.

But detached workers can still make a maybe-delivered turn contribute. `_spawn_public_agent_gateway_bridge` starts the child before recording worker metadata at `python/arclink_notification_delivery.py:2018` and `:2026`; `_record_public_agent_bridge_worker` then does a whole-`extra_json` read/write at `python/arclink_notification_delivery.py:1659` and `:1676`. If it read counter=7, the child can reset on unconfirmed at `python/arclink_notification_delivery.py:1622` and `:1645`, then the parent can write stale `extra_json` back, reintroducing 7. The next genuine terminal bumps to 8 and pages at `python/arclink_notification_delivery.py:580` and `:595`. That is a false-alarm path.

Also, delivery does not literally reset the counter. Success sites call `_resolve_public_agent_bridge_hiccup` at `python/arclink_notification_delivery.py:1810`, `:1925`, `:2587`, `:2817`; delivered rows are protected by the delivered short-circuit at `python/arclink_notification_delivery.py:571`, not by `_reset`.

### B tri-state runtime
CONFIRM-FIXED for the stated ps-inspection false alarm: missing docker runner records `unknown` at `python/arclink_sovereign_worker.py:2239`, ps exceptions record `unknown` at `python/arclink_sovereign_worker.py:2264`, `_deployment_has_durable_runtime` returns `None` for `unknown` at `python/arclink_sovereign_worker.py:948`, and the release gate retains/no-pages on `None` at `python/arclink_sovereign_worker.py:989`.

NEW-ISSUE: serving-runtime post-health failures are not cross-pass stable. The exception path snapshots serving=True at `python/arclink_sovereign_worker.py:858`, but then overwrites health to `failed` for all non-`None` snapshots at `python/arclink_sovereign_worker.py:875` and `:883`. First pass retains via the snapshot at `python/arclink_sovereign_worker.py:980`, but the failed-job re-entry path at `python/arclink_sovereign_worker.py:784` calls the gate with no snapshot; it reads the overwritten `failed` health and can release/page at `python/arclink_sovereign_worker.py:1002` and `:1041`. That can page/release a serving pod on the second pass.

Genuine-dead still pages once when inspection succeeds and rows are actually failed/missing: parsed statuses are recorded at `python/arclink_sovereign_worker.py:2284`, dead states map at `python/arclink_sovereign_worker.py:2453`, and `remove_placement` single-success dedups at `python/arclink_sovereign_worker.py:1002`.

### C new false-alarm/regression
NEW-ISSUE: the stale `extra_json` writer can resurrect a pre-reset terminal counter after a D5 unconfirmed outcome, so a maybe-delivered attempt can still help reach the page threshold.

NEW-ISSUE: serving runtime plus post-health failure can page on re-entry because the first pass preserves only the snapshot, not the recorded serving health.

No deploy-blocking over-suppression found beyond accepted false silence: persistent `unknown` can mask a real dead pod while inspection remains unavailable, but that is explicitly the chosen no-false-alarm behavior.

### D tests
Tests are mostly non-tautological: the 7-unconfirmed-plus-1-terminal no-page case is in `tests/test_arclink_operator_hiccup.py:375`, real bridge worker delivery success resolves through the worker path at `tests/test_arclink_operator_hiccup.py:533`, ps-fail indeterminate is driven through worker batch with re-entry at `tests/test_arclink_sovereign_worker.py:841`, and main runs include them at `tests/test_arclink_operator_hiccup.py:739` and `tests/test_arclink_sovereign_worker.py:1912`.

Coverage gaps match the blockers: no detached stale-`extra_json` race test, and `test_provisioning_post_health_error_on_serving_pod_does_not_page` only checks the first pass at `tests/test_arclink_sovereign_worker.py:714`.

### E other
Block deploy until the stale `extra_json` metadata write is made merge-safe/CAS-safe, and until serving-runtime post-health failures preserve a serving verdict across re-entry or re-inspect before release/page.
<<<CODEX-C3-END>>>
