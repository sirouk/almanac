<<<CODEX-B3-START>>>
SIGN-OFF: RATIFY
### A operator notice
CONFIRM-FIXED. `Config.from_env()` loads `_load_config_env()` at `python/arclink_control.py:463-465`; `_discover_config_file()` honors `ARCLINK_CONFIG_FILE` at `python/arclink_control.py:291-294`, then parses that file into config values at `python/arclink_control.py:366-395`. Operator fields are populated from that merged config at `python/arclink_control.py:514-579`.

The service still only injects `ARCLINK_CONFIG_FILE` plus LLM-specific env, not `OPERATOR_NOTIFY_*`, at `compose.yaml:1107-1116`. The worker now loads cfg once at `python/arclink_llm_model_sync.py:319-323`, passes it into `sync_llm_models()` at `python/arclink_llm_model_sync.py:333-340`, and `_operator_target(cfg)` reads `cfg.operator_notify_platform/channel_id` at `python/arclink_llm_model_sync.py:124-147`. Queueing stamps `target_kind="operator"`, real `target_id`, and real `channel_kind` at `python/arclink_llm_model_sync.py:182-195`; delivery uses row `channel_kind` and row `target_id` at `python/arclink_notification_delivery.py:314-320` and `python/arclink_notification_delivery.py:2326-2339`. I found no `main()` path still resolving the operator target from raw env; raw `os.environ` is only passed for Chutes/min-model settings at `python/arclink_llm_model_sync.py:340`.

### D startup refresh
CONFIRM-FIXED. Startup refresh hard-sets `mark_missing = False` at `python/arclink_llm_router.py:385-407`, so no startup path calls `upsert_model_catalog(..., mark_missing_unavailable=True)`. Empty startup responses skip before upsert at `python/arclink_llm_router.py:376-384`; TEE-light but nonempty responses can only add/update rows.

GLM/Kimi survival is directly asserted in router tests: seed at `tests/test_arclink_llm_router.py:1057-1076`, TEE-light startup at `tests/test_arclink_llm_router.py:1088-1094`, and active `-TEE` list equality at `tests/test_arclink_llm_router.py:1096-1108`. Genuinely removed models can remain stale-active until the hourly worker, which is the intended split.

### E tests executable + real
CONFIRM-FIXED. `tests/test_arclink_llm_model_sync.py` now has 14 `def test_` functions and `main()` invokes all 14 at `tests/test_arclink_llm_model_sync.py:507-522`, with `raise SystemExit(main())` at `tests/test_arclink_llm_model_sync.py:526-527`. `tests/test_arclink_llm_router.py` has 31 `def test_` functions and `main()` invokes all 31 at `tests/test_arclink_llm_router.py:2136-2168`, with `raise SystemExit(main())` at `tests/test_arclink_llm_router.py:2172-2173`.

The new tests are substantive: operator target checks assert non-`tui-only` Config-derived Telegram/Discord targets and queued row fields at `tests/test_arclink_llm_model_sync.py:126-160`; startup allow-list checks assert `mark_missing_unavailable is False` and GLM/Kimi remain active at `tests/test_arclink_llm_router.py:1043-1108`. I attempted to execute both files, but this read-only sandbox has no writable temp dir; they began running and then failed in `tempfile`, not in the assertions.

### F regressions/other
No deploy-blocking regression found. The hourly worker still owns destructive removal: success upserts filtered `-TEE` models with `mark_missing_unavailable=True` at `python/arclink_llm_model_sync.py:268-299`, and `upsert_model_catalog()` marks omitted active rows unavailable at `python/arclink_control.py:6731-6746`. I spot-checked a 13-model then 12-model worker sync in-memory; the omitted `-TEE` row became `unavailable`.

Per-request allow resolution is intact: active synced `-TEE` rows are read at `python/arclink_llm_router.py:693-719`, fallback to static env happens at `python/arclink_llm_router.py:722-732`, and per-key allowlists still win at `python/arclink_llm_router.py:1209-1215`.

Non-blocking drift: `ARCLINK_LLM_ROUTER_MARK_MISSING_MODELS_UNAVAILABLE` is now parsed but unused by startup (`python/arclink_llm_router.py:207-210` versus `python/arclink_llm_router.py:400-407`), while docs still describe startup marking omitted rows unavailable at `docs/arclink/llm-router.md:204-205` and `docs/arclink/llm-router.md:300-302`.
<<<CODEX-B3-END>>>
