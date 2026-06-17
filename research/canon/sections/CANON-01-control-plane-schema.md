# CANON-01 — Control Plane & Schema

## PIECE
This piece is the **data spine** of ArcLink: it owns `python/arclink_control.py`
(19,391 lines) and `python/arclink_boundary.py` (133 lines). `arclink_control.py`
defines the entire SQLite schema in a single idempotent `ensure_schema(conn, cfg)`
(`python/arclink_control.py:595`), the frozen `Config` dataclass + its env loader
(`Config.from_env`, `python/arclink_control.py:405`; `_load_config_env`,
`python/arclink_control.py:302`), the DB connector `connect_db`
(`python/arclink_control.py:563`), the `settings` key/value store helpers
(`upsert_setting`/`get_setting`, `python/arclink_control.py:2971`/`2983`), and the
two cross-piece producer helpers `append_arclink_event`
(`python/arclink_control.py:3870`) and `queue_notification`
(`python/arclink_control.py:8055`), plus network helpers `is_loopback_ip` /
`is_ip_in_cidrs` (`python/arclink_control.py:7604`/`7611`). `arclink_boundary.py`
is the shared boundary-safety toolkit: `rowdict` (`python/arclink_boundary.py:76`),
JSON helpers `json_loads_safe` / `json_dumps_safe`
(`python/arclink_boundary.py:29`/`65`), `reject_secret_material`
(`python/arclink_boundary.py:39`), and the Docker-trust guards
`require_docker_trusted_host_risk_accepted` / `require_trusted_docker_binary`
(`python/arclink_boundary.py:85`/`107`). Note: `arclink_control.py` is far larger
than its schema/config role — it also carries onboarding, notion, billing,
provisioning and notification-delivery logic; this section claims only the
SCHEMA + CONFIG + the shared-helper surface; HTTP routing/auth is CANON-02.

## INPUT CONTRACT (code-verified)
- **`Config.from_env() -> Config`** (`python/arclink_control.py:405`): zero args
  (classmethod). Reads the merged env from `_load_config_env()`
  (`python/arclink_control.py:406`). Coerces ~40 `ARCLINK_*`/`OPERATOR_*` keys via
  `int(...)`, `bool_env(...)` (`python/arclink_control.py:427,467,499`), and CSV
  splits (`python/arclink_control.py:451,462`). **No validation/try-guard around
  the `int(...)` casts** (e.g. `int(env.get("ARCLINK_BOOTSTRAP_WINDOW_SECONDS","3600"))`,
  `python/arclink_control.py:492`) — a non-numeric override raises `ValueError`
  unhandled. Callers: nearly every `arclink_*` module + `bin/` entrypoints.
- **`_load_config_env() -> dict[str,str]`** (`python/arclink_control.py:302`): no
  args. Starts from `dict(os.environ)` (`python/arclink_control.py:305`), discovers
  a config file via `_discover_config_file()` (`python/arclink_control.py:245`),
  parses `KEY=value` lines (shlex-split first token, `python/arclink_control.py:330`),
  and applies each with `merged.setdefault(...)` (`python/arclink_control.py:334`)
  — **process env wins; the file only fills gaps** (proven empirically, see TRACE).
- **`config_env_value(name, default="") -> str`** (`python/arclink_control.py:340`):
  thin wrapper re-invoking `_load_config_env()` on every call (re-reads the file
  each time — see RISKS).
- **`connect_db(cfg) -> sqlite3.Connection`** (`python/arclink_control.py:563`):
  arg `cfg: Config`. Side-effects: mkdir runtime paths, open SQLite with
  `timeout=15.0`, set `busy_timeout`, `journal_mode`, `foreign_keys=ON`,
  `synchronous=NORMAL`, then call `ensure_schema`. Caller universe: all DB-touching
  modules.
- **`ensure_schema(conn, cfg=None) -> None`** (`python/arclink_control.py:595`):
  args `conn: sqlite3.Connection`, optional `cfg`. Runs one big `executescript`
  of `CREATE TABLE IF NOT EXISTS` (`python/arclink_control.py:596`) then procedural
  `_ensure_column`/index/`__new`-rebuild migrations, ending in `conn.commit()`
  (`python/arclink_control.py:2548`). Idempotent (re-run proven OK).
- **`append_arclink_event(conn, *, subject_kind, subject_id, event_type, metadata=None, event_id="", commit=True) -> str`**
  (`python/arclink_control.py:3870`): keyword-only after conn. Returns the event id.
- **`queue_notification(conn, *, target_kind, target_id, channel_kind, message, extra=None) -> int`**
  (`python/arclink_control.py:8055`): keyword-only after conn. Returns
  `cursor.lastrowid`.
- **`rowdict(row) -> dict`** (`python/arclink_boundary.py:76`): `dict(row)` or `{}`
  for `None`. **No secret filtering** (pure passthrough).
- **`json_dumps_safe(value, *, label, error_cls=ValueError) -> str`**
  (`python/arclink_boundary.py:65`): rejects plaintext secret material recursively
  (`reject_secret_material`, `python/arclink_boundary.py:39`) before `json.dumps(...,
  sort_keys=True)`.
- **`require_docker_trusted_host_risk_accepted(*, service, env=None, error_cls=RuntimeError)`**
  (`python/arclink_boundary.py:85`): fail-closed unless
  `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED == "accepted"`
  (`python/arclink_boundary.py:82`).
- **`require_trusted_docker_binary(configured, *, service, ...) -> str`**
  (`python/arclink_boundary.py:107`): validates the docker CLI path against an
  allowlist `TRUSTED_DOCKER_BINARY_PATHS` (`python/arclink_boundary.py:21`).

## OUTPUT CONTRACT (code-verified)
- **DB schema (DDL):** `ensure_schema` creates **80 tables** on a fresh build
  (empirically counted): **45 `arclink_*`**, **10 `academy_*`**, **25 unprefixed
  substrate** tables. (See TOUCH POINTS for the enumerated CREATE cites.) Schema is
  create-if-absent; `PRAGMA user_version` stays **0** (no version ledger, proven).
- **`Config`**: a `@dataclass(frozen=True)` (`python/arclink_control.py:344`) with
  ~45 fields (`python/arclink_control.py:346-402`). `org_provider_secret` is read
  (`python/arclink_control.py:429`) but **deliberately NOT a Config field** — the
  secret never enters the persisted config object (good hygiene). `model_presets`
  is a `dict` field, so the "frozen" object is not deeply immutable.
- **`append_arclink_event`** INSERT → `arclink_events(event_id, subject_kind,
  subject_id, event_type, metadata_json, created_at)`
  (`python/arclink_control.py:3881-3887`); `metadata` JSON-encoded via `_arclink_json`
  (`python/arclink_control.py:3234`) which **only validates JSON, does NOT reject
  secrets** (contrast `json_dumps_safe`).
- **`queue_notification`** INSERT → `notification_outbox(target_kind, target_id,
  channel_kind, message, extra_json, created_at)`
  (`python/arclink_control.py:8064-8070`); `extra` via `json_dumps` (plain, no secret
  reject).
- **`upsert_setting`** UPSERT → `settings(key,value,updated_at)`
  (`python/arclink_control.py:2972`); commits.
- **`connect_db`** side-effects: `mkdir -p` of state/runtime/agents/curator/archived/
  db-parent dirs (`ensure_runtime_paths`, `python/arclink_control.py:551`); WAL or
  DELETE journal file; `ensure_schema` run.
- **`require_*` guards** raise on failure (fail-closed), else return/None.

## TOUCH POINTS
**Env vars (read in this piece):**
- Config discovery: `ARCLINK_CONFIG_FILE` (`python/arclink_control.py:246`),
  `ARCLINK_REPO_DIR` (`:251`), `ARCLINK_OPERATOR_ARTIFACT_FILE` (`:253`).
- DB/runtime: `ARCLINK_DB_PATH` (`:481`), `STATE_DIR`/`RUNTIME_DIR`/`VAULT_DIR`
  (`:410-412`), `ARCLINK_PRIV_DIR` (`:409`), `ARCLINK_USER` (`:407`),
  `ARCLINK_HOME` (`:475`).
- SQLite: `ARCLINK_DOCKER_MODE` (`:568`, selects DELETE vs WAL),
  `ARCLINK_SQLITE_JOURNAL_MODE` (`:569`).
- Network helper: `ARCLINK_BACKEND_ALLOWED_CIDRS` (`:7632`).
- Boundary Docker trust: `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED`
  (`python/arclink_boundary.py:19`).
- Plus ~40 tunables in `from_env` (`python/arclink_control.py:413-547`):
  `ARCLINK_MCP_PORT/HOST`, `ARCLINK_NOTION_WEBHOOK_PORT/HOST`, `ARCLINK_QMD_URL`,
  `QMD_MCP_PORT`, `ARCLINK_BOOTSTRAP_*`, `ARCLINK_AUTO_PROVISION_*`,
  `ARCLINK_ONBOARDING_*`, `ARCLINK_SSOT_PENDING_WRITE_TTL_SECONDS`,
  `ARCLINK_CURATOR_*`, `OPERATOR_NOTIFY_*`, `OPERATOR_GENERAL_*`,
  `ARCLINK_OPERATOR_TELEGRAM_USER_IDS`, `ARCLINK_MODEL_PRESET_*`,
  `ARCLINK_ORG_PROVIDER_*`, `ARCLINK_UPSTREAM_*`, `ARCLINK_AGENT_*PORT*`,
  `ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE`, `ENABLE_TAILSCALE_SERVE`.
- **`ALMANAC_*` aliases: NONE** in this piece — `grep -c ALMANAC` over
  `arclink_control.py` = 0 (drift vs MEMORY.md "ALMANAC_* aliases preserved").

**DB tables created (CREATE cites):** 45 `arclink_*` —
`arclink_users` (`:962`), `arclink_webhook_events` (`:980`), `arclink_deployments`
(`:991`), `arclink_subscriptions` (`:1008`), `arclink_refuel_credits` (`:1020`),
`arclink_credential_handoffs` (`:1034`), `arclink_share_grants` (`:1052`),
`arclink_share_claim_nonces` (`:1071`), `arclink_fleet_shares` (`:1092`),
`arclink_fleet_share_members` (`:1104`), `arclink_provisioning_jobs` (`:1124`),
`arclink_dns_records` (`:1138`), `arclink_admins` (`:1151`),
`arclink_user_sessions` (`:1165`), `arclink_admin_sessions` (`:1178`),
`arclink_admin_roles` (`:1193`), `arclink_admin_totp_factors` (`:1203`),
`arclink_audit_log` (`:1213`), `arclink_service_health` (`:1224`),
`arclink_events` (`:1233`), `arclink_model_catalog` (`:1242`),
`arclink_llm_router_keys` (`:1261`), `arclink_llm_usage_events` (`:1275`),
`arclink_llm_budget_reservations` (`:1296`), `arclink_onboarding_sessions`
(`:1309`), `arclink_onboarding_events` (`:1334`), `arclink_public_bot_identity`
(`:1344`), `arclink_channel_pairing_codes` (`:1355`), `arclink_action_intents`
(`:1371`), `arclink_operation_idempotency` (`:1388`), `arclink_action_operation_links`
(`:1403`), `arclink_inventory_machines` (`:1413`), `arclink_pod_messages` (`:1437`),
`arclink_pod_migrations` (`:1451`), `arclink_crew_recipes` (`:1476`),
`arclink_agent_skill_enablement` (`:1718`, **NEW since prior doc**),
`arclink_wrapped_reports` (`:1738`), `arclink_fleet_hosts` (`:2349`),
`arclink_deployment_placements` (`:2369`), `arclink_action_attempts` (`:2381`),
`arclink_rollouts` (`:2395`), `arclink_fleet_enrollments` (`:2429`),
`arclink_fleet_host_probes` (`:2440`), `arclink_fleet_audit_chain` (`:2450`),
`arclink_evidence_runs` (`:2523`).
10 `academy_*` — `academy_programs` (`:1493`), `academy_trainees` (`:1512`),
`academy_mode_sessions` (`:1536`), `academy_resource_proposals` (`:1560`),
`academy_sources` (`:1597`, **NEW**), `academy_corpus_specialists` (`:1624`, **NEW**),
`academy_specialist_sources` (`:1643`, **NEW**), `academy_source_provenance`
(`:1654`, **NEW**), `academy_specialist_subscriptions` (`:1670`, **NEW**),
`academy_source_crawl_observations` (`:1686`, **NEW**).
25 unprefixed substrate — `settings` (`:598`), `bootstrap_requests` (`:604`),
`bootstrap_tokens` (`:636`), `rate_limits` (`:652`), `agents` (`:659`),
`agent_identity` (`:679`), `vaults` (`:698`), `vault_definitions` (`:708`),
`agent_vault_subscriptions` (`:723`), `pin_upgrade_notifications` (`:732`),
`notification_outbox` (`:745`), `operator_actions` (`:760`),
`notion_webhook_events` (`:774`), `refresh_jobs` (`:789`), `onboarding_sessions`
(`:799`), `onboarding_update_failures` (`:827`), `ssot_access_audit` (`:836`),
`ssot_pending_writes` (`:850`), `notion_identity_claims` (`:874`),
`notion_identity_overrides` (`:892`), `notion_index_documents` (`:902`),
`notion_retrieval_audit` (`:920`), `notion_parent_scope_cache` (`:934`),
`memory_synthesis_cards` (`:944`).
**`__new`/`__legacy` rebuild migrations** (table-rebuild, column-add via rebuild):
`arclink_fleet_enrollments__new` (`:2613`), `arclink_fleet_host_probes__new`
(`:2673`), `arclink_fleet_audit_chain__new` (`:2822`), `arclink_rollouts__new`
(`:2860`), `notion_identity_claims__new` (`:2908`).

**Files/paths:** SQLite DB at `cfg.db_path`
(default `<state>/arclink-control.sqlite3`, `python/arclink_control.py:481`);
config file `arclink.env` discovered across ~13 candidate paths
(`python/arclink_control.py:262-298`); operator artifact `.arclink-operator.env`
(`python/arclink_control.py:253`).
**Subprocess/sockets/ports:** none directly in this piece (ports are merely values
in Config). **Locks:** SQLite `busy_timeout=15000` + `PRAGMA journal_mode`
(`python/arclink_control.py:567,573`) — concurrency is delegated to SQLite, no
app-level lock.
**Secrets handling:** `reject_secret_material` (`python/arclink_boundary.py:39`)
recursively scans Mapping/list/str; trusted-docker-path allowlist
(`python/arclink_boundary.py:21`); `org_provider_secret` read-but-not-stored
(`python/arclink_control.py:429`).
**External services:** none called directly here (this piece is the substrate).

## CODE-PATH TRACE
Empirically executed (probe built schema in `:memory:` and exercised the loader):
1. Caller invokes `Config.from_env()` (`python/arclink_control.py:405`).
2. → `_load_config_env()` (`:302`): `merged = dict(os.environ)` (`:305`).
3. → `_discover_config_file()` (`:245`): honors explicit `ARCLINK_CONFIG_FILE`
   (`:246`), else walks artifact/repo/home candidates, returns first existing file
   (`:299`).
4. Back in `_load_config_env`: each `KEY=value` line applied with
   `merged.setdefault(key, value)` (`:334`) — **process env wins**. Proven:
   with both `ARCLINK_PROBE_KEY` in env (`from_process_env`) and config file
   (`from_config_file`), the merged value was `from_process_env`; a file-only key
   surfaced as `file_value`.
5. `from_env` coerces fields and returns the frozen `Config`
   (`python/arclink_control.py:473-547`).
6. Caller invokes `connect_db(cfg)` (`:563`): `ensure_runtime_paths` mkdirs (`:564`),
   `sqlite3.connect(cfg.db_path, timeout=15.0)` (`:565`), journal mode resolved from
   `ARCLINK_DOCKER_MODE`/`ARCLINK_SQLITE_JOURNAL_MODE` (`:568-573`), then
   `ensure_schema(conn, cfg)` (`:589`).
7. `ensure_schema` runs the big `executescript` of `CREATE TABLE IF NOT EXISTS`
   (`:596`), then `_ensure_column`/index/`__new` migrations, `conn.commit()`
   (`:2548`). Proven: fresh build → 80 tables (45 arclink_/10 academy_/25 other),
   `user_version=0`, idempotent on re-run, no `__new`/`__legacy` leftovers.
8. A downstream writer (e.g. CANON-02 api_auth) calls `append_arclink_event(conn,
   subject_kind="deployment", subject_id=..., event_type="credential_handoff_removed",
   metadata={...}, commit=False)` (`python/arclink_api_auth.py:2189`) which INSERTs
   into `arclink_events` (`python/arclink_control.py:3881`); a downstream reader
   (CANON-19 dashboard / CANON-02 admin_events) projects `metadata_json` back via
   `json_loads_safe`/`_json_loads` (`python/arclink_dashboard.py:676`,
   `python/arclink_api_auth.py:991`).

## CROSS-PIECE CONTRACTS (both ends verified)
1. **CANON-02 (Hosted API/Auth) — `append_arclink_event` kwargs.** Producer
   declares `(conn, *, subject_kind, subject_id, event_type, metadata, event_id,
   commit)` (`python/arclink_control.py:3870`); consumer/caller passes exactly
   `subject_kind=`, `subject_id=`, `event_type=`, `metadata=`, `commit=`
   (`python/arclink_api_auth.py:2189-2196`). `metadata` (dict) → `metadata_json`
   TEXT. **BOTH ENDS VERIFIED: yes.**
2. **CANON-02 (Auth) — `is_ip_in_cidrs` / `is_loopback_ip` contract.** Producer
   (`python/arclink_control.py:7604,7611`) takes `(value:str, cidrs:str)`; the
   CIDR gate logic in api_auth/hosted_api relies on these booleans. (Producer
   verified here; consumer side is CANON-02's `_backend_client_allowed`.)
   **BOTH ENDS VERIFIED: producer yes, consumer = CANON-02 (cite handoff).**
3. **CANON-12 (Brokers) — Docker trust guard.** Producer
   `require_docker_trusted_host_risk_accepted(*, service, env, error_cls)` +
   `require_trusted_docker_binary(configured, *, service, ...)`
   (`python/arclink_boundary.py:85,107`); consumer imports both and calls with
   `service=SERVICE_NAME, error_cls=ValueError/SystemExit`
   (`python/arclink_gateway_exec_broker.py:24-25,66,289,378`). **BOTH ENDS
   VERIFIED: yes.**
4. **CANON-23/14/19 (many) — `rowdict` passthrough.** Producer
   (`python/arclink_boundary.py:76`) returns `dict(row)`; imported in 26 modules
   (`grep "from arclink_boundary import"`). No per-module `_rowdict` survives
   (`grep "def _rowdict"` = 0), so the MEMORY.md convention holds. Exact contract:
   sqlite3.Row → plain dict (no filtering). **BOTH ENDS VERIFIED: yes (shape) /
   per-consumer behavior delegated.**
5. **CANON-14/23 — `queue_notification` → `notification_outbox`.** Producer INSERT
   columns (`python/arclink_control.py:8064`) are a subset of the table schema
   (`python/arclink_control.py:745`); the delivery reader (intra-piece,
   `python/arclink_control.py:9910` `SELECT * FROM notification_outbox`) and
   external callers (`arclink_action_worker`, `arclink_ctl`, etc.) consume via the
   `queue_notification` API, not raw SQL. **BOTH ENDS VERIFIED: yes (schema
   superset; delivery reader intra-piece).**

## CODE vs COMMENT/DOC/NAME DRIFT
1. **Prior doc `01-control-core-api.md` says "44 arclink_* tables" and lists 4
   academy tables.** Reality: **45 arclink_** (adds `arclink_agent_skill_enablement`,
   `python/arclink_control.py:1718`) and **10 academy_** (adds `academy_sources`
   `:1597`, `academy_corpus_specialists` `:1624`, `academy_specialist_sources`
   `:1643`, `academy_source_provenance` `:1654`, `academy_specialist_subscriptions`
   `:1670`, `academy_source_crawl_observations` `:1686`). Prior doc's "72 total" is
   now **80 total**. Schema grew (commits `4e1bb47`, `9fdc844`).
2. **MEMORY.md: "44 arclink_* tables + 4 academy_* tables".** Same drift — now
   45 + 10.
3. **MEMORY.md: "ALMANAC_* aliases preserved" + "ARCLINK_* env vars take
   precedence; ALMANAC_* aliases preserved".** In THIS piece there are **zero**
   `ALMANAC` references (`grep -c ALMANAC python/arclink_control.py` = 0). If
   aliases exist they are not in the config-loader; the config loader knows only
   `ARCLINK_*`/`OPERATOR_*`/`STATE_DIR`/etc.
4. **Naming: `json_dumps_safe` (boundary, rejects secrets) vs `_arclink_json`
   (control:3234) and `json_dumps` (control).** The two control-side helpers do
   NOT reject secrets — `append_arclink_event` (`metadata_json`) and
   `queue_notification` (`extra_json`) use the non-rejecting encoders, so a caller
   that smuggles a plaintext secret into `metadata`/`extra` will persist it. Name
   `_arclink_json` does not imply "safe"; behavior confirmed at `:3234-3243`.
5. **`@dataclass(frozen=True)` Config (`:344`) "immutability" is shallow.** Field
   `model_presets: dict[str,str]` (`:398`) is mutable in place; "frozen" only blocks
   attribute reassignment, not dict mutation.
6. **`_discover_config_file` comment-free fallthrough.** When `explicit` is set but
   the file is missing, it returns the (nonexistent) path anyway (`:248-249`);
   `_load_config_env` then `setdefault`s `ARCLINK_CONFIG_FILE` to it (`:311`) and
   returns env unchanged. Silent no-op (not an error) — caller never learns the
   configured file was absent.

## ADVERSARIAL SELF-CHECK
1. **"45 arclink_/10 academy_/80 total is the canonical live count."** Proven by
   building the schema in `:memory:` and counting `sqlite_master`. Falsifier: a
   second `ensure_*` path elsewhere creating more `arclink_*` tables NOT under
   `ensure_schema` (e.g. `_ensure_managed_database_schema` at `:5768`,
   `ensure_notion_verification_database` at `:5867`) — those build SEPARATE
   databases, not this control DB, but I did not exhaustively confirm none add
   control-DB tables. Worth a Codex check.
2. **"Process env always wins over config file."** Proven for one key via probe.
   Falsifier: any caller that mutates `os.environ` FROM the file before
   `_load_config_env` runs, or a code path using `config_env_value` to seed env.
   I saw `:14455-14457` re-inject `ARCLINK_CONFIG_FILE` into a child env — that is
   a child-process env build, not the in-process precedence, but it shows env gets
   rewritten in places.
3. **"No version ledger / migrations are create-if-absent + rebuild."**
   `PRAGMA user_version` = 0 proven. Falsifier: a migration runner outside
   `ensure_schema`/`connect_db` (e.g. in `bin/` or a separate module) that sets
   `user_version`. I did not grep the whole repo for `PRAGMA user_version` writes.
4. **"`append_arclink_event`/`queue_notification` do not reject secrets."** Proven
   by reading `_arclink_json` (`:3234`) and `json_dumps`. Falsifier: callers
   pre-sanitize via `json_dumps_safe` before passing — true for SOME callers, so
   the leak is conditional on the caller, not guaranteed.
5. **"`rowdict` has no per-module shadow."** `grep "def _rowdict"` = 0 today.
   Falsifier: a differently-named local row→dict wrapper still in use (I only
   checked `_rowdict`).

## OPEN FOR CODEX FEDERATION
- Confirm no OTHER function in `arclink_control.py` (e.g. `_ensure_managed_database_schema`
  `:5768`, `ensure_notion_verification_database` `:5867`,
  `ensure_request_expiry` `:6930`, `ensure_llm_router_key` `:6731`) adds tables to
  the **control** DB outside `ensure_schema` — and whether any writes
  `PRAGMA user_version`.
- Independently rebuild the schema and re-count: is 45/10/80 stable across
  `ARCLINK_DOCKER_MODE=1` (DELETE journal) vs WAL, and across a pre-existing DB
  that triggers the `__new` rebuild paths (`:2613,2673,2822,2860,2908`)?
- Verify the secret-leak surface: enumerate callers of `append_arclink_event`/
  `queue_notification` that pass user-controlled `metadata`/`extra` WITHOUT prior
  `reject_secret_material`/`json_dumps_safe`.
- Confirm the `ALMANAC_*` alias claim is fully dead repo-wide (not just this
  piece) or lives in an adjacent module.

## RISKS (severity-ranked, code-cited)
- **MEDIUM — `from_env` int casts are unguarded.** Any non-numeric override (e.g.
  `ARCLINK_BOOTSTRAP_WINDOW_SECONDS=abc`) raises an unhandled `ValueError` at
  config load, hard-failing every consumer (`python/arclink_control.py:492-546`).
  No clamp/validation/default-on-error.
- **MEDIUM — secret material can reach event/notification rows.**
  `append_arclink_event.metadata` → `_arclink_json` (`python/arclink_control.py:3234`)
  and `queue_notification.extra` → `json_dumps` (`:8069`) do NOT call
  `reject_secret_material`; a caller passing plaintext secrets persists them
  unredacted, unlike the boundary `json_dumps_safe` path.
- **LOW — `config_env_value` re-reads the config file on every call**
  (`python/arclink_control.py:340` → `_load_config_env` → `read_text`,
  `python/arclink_control.py:315`). Repeated hot-path use is wasteful and is a mild
  TOCTOU surface (file can change between reads); also no caching.
- **LOW — silent missing-config-file no-op.** Explicit-but-absent
  `ARCLINK_CONFIG_FILE` returns the bogus path and proceeds with env-only config
  (`python/arclink_control.py:248-249`, `:310-312`) — misconfiguration is invisible.
- **LOW — `journal_mode` fallback can leave WAL request unmet silently.** On a
  locked DB the `PRAGMA journal_mode` failure is swallowed (`pass`,
  `python/arclink_control.py:576-577`), so the DB may run in an unexpected journal
  mode without surfacing.
- **INFO — `frozen=True` Config is shallow-immutable** (`model_presets` dict
  mutable, `python/arclink_control.py:398`).
- **INFO — GAP-019 trusted-host gate is fail-closed by design**
  (`python/arclink_boundary.py:85`); a deliberate operator-acceptance control, not a
  defect.

## VERDICT
This piece **provably does its core job**: a single idempotent `ensure_schema`
builds the full 80-table control schema deterministically (empirically verified —
45 `arclink_*`, 10 `academy_*`, 25 substrate; idempotent re-run; no `__new`
leftovers; `user_version=0`), and `_load_config_env` implements a clear,
proven **process-env-wins-over-config-file** precedence via `setdefault`. The
shared `rowdict`/`json_*`/Docker-trust helpers in `arclink_boundary.py` are clean,
single-responsibility, and consumed consistently (26 importers, zero surviving
`_rowdict` shadows; broker trust guard verified at both ends). Load-bearing
strengths: deterministic schema, correct env precedence, fail-closed Docker-trust
gate, secret-rejection at the boundary, no version-ledger complexity. Real
weaknesses: (1) the schema is "idempotent create-if-absent" with NO version ledger
and only ad-hoc `__new` rebuilds — reversibility/ordered migrations are NOT
provided despite aspirational docs; (2) the two highest-traffic write helpers
(`append_arclink_event`, `queue_notification`) bypass the boundary's secret
rejector, so secret hygiene depends on each caller; (3) `from_env` int casts are
unguarded; (4) prior ground-truth doc and MEMORY.md table counts are stale (44→45,
4→10 academy) and the "ALMANAC_* aliases" claim is absent from this piece's code.
