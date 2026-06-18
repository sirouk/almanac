<<<CODEX-B-START>>>
SIGN-OFF: OBJECT(4)

### 1 Router safety
CONFIRM: effective global list is DB-backed and nonempty under normal config: active Chutes `%-TEE` rows are read in `python/arclink_llm_router.py:655`, env fallback is returned in `python/arclink_llm_router.py:693`, and `load_router_config` forces `allowed_models=(default_model,)` when env is blank at `python/arclink_llm_router.py:173`.
CONFIRM: nonempty per-key lists still win in chat and `/v1/models`: `python/arclink_llm_router.py:1171` and `python/arclink_llm_router.py:2000`.
RISK: global DB allow-list is not the sole source when a key has no per-key list. `_router_model_allowed` still admits `config.default_model` even when synced DB rows exist and do not include it (`python/arclink_llm_router.py:707`, `python/arclink_llm_router.py:712`). That preserves prior behavior, but weakens the new “DB is source of truth” claim.

### 2 Never-empty
CONFIRM: the new sync worker does not wipe on fetch error, empty, or below-min results: fetch exceptions return before upsert at `python/arclink_llm_model_sync.py:198`, and too-few returns before upsert at `python/arclink_llm_model_sync.py:203`.
BUG: the router’s existing startup catalog refresh is still enabled by compose default (`compose.yaml:588`) and bypasses this LKG guard. `_refresh_model_catalog_once` writes whatever `/models` returns with `mark_missing_unavailable` at `python/arclink_llm_router.py:350` and `python/arclink_llm_router.py:365`; an empty successful `data: []` reaches `upsert_model_catalog`, whose missing pass marks all active rows unavailable at `python/arclink_control.py:6731`. That can empty the DB-backed list with no Operator notice.
RISK: env fallback itself is nonempty, but if fallback models are configured outside that env allow-list, `_disallowed_router_model` can still 403 otherwise allowed requests (`python/arclink_llm_router.py:1180`, `python/arclink_llm_router.py:728`).

### 3 mark_missing_unavailable
BUG: partial/garbage Chutes responses can silently shrink the allow-list. The production min defaults to 1 (`compose.yaml:1112`, `python/arclink_llm_model_sync.py:173`), so any one `*-TEE` entry is treated as success (`python/arclink_llm_model_sync.py:203`) and then `mark_missing_unavailable=True` marks every active model not in that partial `seen` set unavailable (`python/arclink_llm_model_sync.py:212`, `python/arclink_control.py:6731`). No failure notice is emitted on this path.

### 4 Operator notice
BUG: Telegram delivery target is wrong. The notice is queued with `target_kind="operator"`, `target_id="llm-router:model-sync"`, `channel_kind="operator"` at `python/arclink_llm_model_sync.py:151`. Delivery falls back to configured platform because `operator` is not a real channel kind (`python/arclink_notification_delivery.py:314`), but Telegram then uses the row `target_id` as `chat_id` before config fallback (`python/arclink_notification_delivery.py:2326`). Result: it tries to send to `llm-router:model-sync`, not the Operator chat.
BUG: re-arm is incomplete if the notice never delivers. Dedup suppresses on any undelivered row for that target (`python/arclink_llm_model_sync.py:112`), so a later success audit does not re-enable a new notice while the old undelivered/error row remains.

### 5 Scheduling/security
CONFIRM: scheduling is hourly and immediate-on-start: compose runs `docker-job-loop ... 3600 ... --once --json` at `compose.yaml:1116`, and the loop runs then sleeps at `bin/docker-job-loop.sh:177`.
RISK: the Chutes key is now present in a second long-running container (`compose.yaml:1110`) beyond the router (`compose.yaml:580`). It is somewhat constrained by `cap_drop: ALL` and only config/state mounts (`compose.yaml:1105`, `compose.yaml:1113`), but it still expands the credential exposure surface and has write access to the control DB state.

### 6 Race/cost
CONFIRM: per-chat cost is one extra indexed-ish catalog read on the existing preflight DB connection (`python/arclink_llm_router.py:655`, `python/arclink_llm_router.py:2040`); `/v1/models` opens a second connection after auth (`python/arclink_llm_router.py:2004`). Catalog size should make this cheap.
CONFIRM: readers should see old-or-new, not partial, because `upsert_model_catalog` commits after the full missing-mark pass (`python/arclink_control.py:6731`, `python/arclink_control.py:6747`) and router connections use a busy timeout (`python/arclink_llm_router.py:341`).
<<<CODEX-B-END>>>
