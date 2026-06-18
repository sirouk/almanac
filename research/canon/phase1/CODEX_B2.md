<<<CODEX-B2-START>>>
SIGN-OFF: OBJECT(3)

### A #1 operator notice
STILL-BROKEN in the deployed service path. The row shape is correct only if `env` already contains the operator vars: `_operator_target` reads `OPERATOR_NOTIFY_CHANNEL_*` at `python/arclink_llm_model_sync.py:136`, and queueing uses `target_kind="operator"`, real `target_id`, and platform `channel_kind` at `python/arclink_llm_model_sync.py:180`.

But `main()` passes raw `os.environ` at `python/arclink_llm_model_sync.py:319`. The compose service runs Python directly at `compose.yaml:1116` and only adds LLM-specific env over `*arclink-env` at `compose.yaml:1107`; the entrypoint only exports `ARCLINK_CONFIG_FILE` at `bin/docker-entrypoint.sh:781`. Unlike health-watch’s shell path, which sources config through `bin/health-watch.sh:5` and `bin/common.sh:211`, the sync worker does not load docker.env before `_operator_target`. Result: a real Telegram/Discord operator configured only in docker.env gets queued as `tui-only`, and delivery treats row `channel_kind` as authoritative at `python/arclink_notification_delivery.py:314`, then marks tui-only delivered/no external at `python/arclink_notification_delivery.py:2340`.

### B #2 re-arm
CONFIRM-FIXED. Dedup is now audit-state based, not undelivered-row based: `_failure_already_notified` reads the latest ok/failed action at `python/arclink_llm_model_sync.py:152` and returns true only when the latest is failed at `python/arclink_llm_model_sync.py:164`. Failures append `llm_router:model_sync_failed` at `python/arclink_llm_model_sync.py:231`; successes append `llm_router:model_sync_ok` at `python/arclink_llm_model_sync.py:283`. `ORDER BY created_at DESC, rowid DESC` at `python/arclink_llm_model_sync.py:157` is deterministic for this rowid table.

### C #3 partial shrink
CONFIRM-FIXED for the claimed floor/proportional guard. The floor is forced to at least 2 at `python/arclink_llm_model_sync.py:223`; below-floor responses fail before upsert at `python/arclink_llm_model_sync.py:257`. Last-known active count is TEE-scoped at `python/arclink_llm_model_sync.py:195`, suspicious drops fail before upsert at `python/arclink_llm_model_sync.py:267`, and `mark_missing_unavailable=True` is reached only on the success path at `python/arclink_llm_model_sync.py:277`. Residual policy note: a partial response above the 50% threshold can still shrink the list by design.

### D #4 startup refresh
STILL-BROKEN for non-empty bad responses. Empty is fixed: `fetched < _STARTUP_REFRESH_MIN_MODELS` skips before upsert at `python/arclink_llm_router.py:377`. Startup exceptions are caught without catalog writes at `python/arclink_llm_router.py:2003`.

The remaining hole is that startup refresh counts and upserts all Chutes models, not filtered `-TEE` models: `catalog.list_models` feeds raw `models` at `python/arclink_llm_router.py:366`, `fetched = len(models)` at `python/arclink_llm_router.py:376`, and upsert uses that raw set with `mark_missing_unavailable=mark_missing` at `python/arclink_llm_router.py:403`. A partial response containing enough non-TEE models but zero TEE models passes the floor/proportional guard and then `upsert_model_catalog` marks every active TEE row missing/unavailable at `python/arclink_control.py:6731`. The router’s synced allow-list then sees no active TEE rows because it only reads `model_id LIKE '%-TEE'` at `python/arclink_llm_router.py:706`.

### E regressions
NEW-ISSUE: the new tests do not reliably prove the fixes. `test_startup_refresh_empty_response_does_not_empty_catalog` is defined at `tests/test_arclink_llm_router.py:986` but is never called from `main()`; the nearby new global allow-list test is called at `tests/test_arclink_llm_router.py:2081`, proving the omission. The new `tests/test_arclink_llm_model_sync.py` file has no `main()` / `if __name__ == "__main__"` runner and ends after the last assertion at `tests/test_arclink_llm_model_sync.py:333`, so the repo’s documented `python3 tests/...py` style executes zero tests for that file.

Success-path code itself looks intact: sync success upserts and marks missing unavailable at `python/arclink_llm_model_sync.py:277`, and per-key allow-lists still override global DB allow resolution at `python/arclink_llm_router.py:1209`.

### F other
No additional deploy blocker beyond A, D, and E. I would not deploy until operator target resolution reads the same config source as health-watch, startup refresh guards TEE count or disables mark-missing on that path, and the regression tests are actually executable by the repo’s normal test style.
<<<CODEX-B2-END>>>
