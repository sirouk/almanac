<<<CODEX-VERDICT-START CANON-01>>>
## CANON-01 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(5)
ONE-LINE VERDICT: Core CANON-01 risks are real, but the record overstates schema centrality and helper exclusivity.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM MEDIUM: unguarded `int(...)` casts hard-fail config load (`python/arclink_control.py:413`, `:415`, `:492-546`).
- CONFIRM MEDIUM: event/notification JSON paths do not reject secrets: `_arclink_json` only validates/dumps (`python/arclink_control.py:3234-3243`), then `append_arclink_event` stores it (`:3881-3887`); `queue_notification` uses plain `json_dumps` (`:8064-8070`) unlike `json_dumps_safe` (`python/arclink_boundary.py:65-73`).
- CONFIRM MEDIUM: config-file parser keeps only first shlex token (`python/arclink_control.py:324-334`); CIDR consumers later split only commas (`:7616-7624`), so unquoted space-separated allowlists silently narrow.
- REFINE MEDIUM: `connect_db` is a write path on open: it calls `ensure_schema`, token migration, and stale SSOT expiry (`python/arclink_control.py:589-591`); expiry commits an UPDATE (`:6020-6046`), and token migration can write secret files then commit (`:7068-7101`).
- CONFIRM A1 rowdict correction: producer is passthrough (`python/arclink_boundary.py:76-77`); actual `rowdict` importers are 6, e.g. `python/arclink_pod_comms.py:9`, `python/arclink_dashboard.py:16`, `python/arclink_fleet_share.py:28`, `python/arclink_action_worker.py:29`, `python/arclink_api_auth.py:32`, `python/arclink_fleet.py:11`.
- CONFIRM A1 event-trace correction: cited readers were wrong tables (`python/arclink_dashboard.py:673-676` rollouts; `python/arclink_api_auth.py:985-991` sessions). Real `arclink_events` readers exist at `python/arclink_dashboard.py:1545-1560` and `python/arclink_hosted_api.py:961-968`.
- REFINE A1 table count: `ensure_schema` has 79 source-owned `CREATE TABLE IF NOT EXISTS` statements from `settings` to `arclink_evidence_runs` (`python/arclink_control.py:598`, `:2523`); runtime count 80 includes SQLite’s `sqlite_sequence`, caused by AUTOINCREMENT tables such as `rate_limits` (`:652`).
- REFUTE/REFINE B23: `ensure_schema` is not the sole control-DB schema authority. `arclink_ctl` opens the control DB (`python/arclink_ctl.py:2075`) and org-profile apply creates 5 extra tables outside `arclink_control.py` (`python/arclink_ctl.py:2089-2090`; `python/arclink_org_profile.py:1910-1957`, `:2093`). No `PRAGMA user_version` writer found; in-memory rebuilds under Docker/non-Docker left 80 tables, no `__new`/`__legacy`, `user_version=0`.
- CONFIRM seam: IP predicates fail closed on malformed values via `ipaddress` (`python/arclink_control.py:7604-7625`) and hosted API consumes them at `python/arclink_hosted_api.py:644-648`.
- CONFIRM seam: Docker trust guards fail closed (`python/arclink_boundary.py:80-97`, `:107-132`) and gateway broker imports/calls them (`python/arclink_gateway_exec_broker.py:22-25`, `:66-70`, `:287-290`, `:378`).
- CONFIRM LOW set: config re-read/TOCTOU (`python/arclink_control.py:340-341`), missing explicit config silent no-op (`:246-249`, `:310-312`), journal-mode lock swallow/effective-mode not read (`:573-577`), `export KEY=value` ignored as key `"export KEY"` (`:324-325`).

### New findings both Claude passes missed (severity + path:line)
- MEDIUM: control-DB schema total is not captured by CANON-01: org-profile creates `org_profile_*` tables on the same `connect_db` connection (`python/arclink_ctl.py:2075`, `:2089-2090`; `python/arclink_org_profile.py:1910-1957`).
- MEDIUM: helper contracts are not exclusive. Raw `notification_outbox` INSERTs bypass `queue_notification` in LLM router and Wrapped (`python/arclink_llm_router.py:1024-1027`; `python/arclink_wrapped.py:921-927`, `:988-994`), and raw `arclink_events` INSERTs bypass `append_arclink_event` (`python/arclink_llm_router.py:753-761`, `:1043-1051`; `python/arclink_chutes.py:917-925`). These paths also use plain JSON helpers (`python/arclink_llm_router.py:672-673`; `python/arclink_chutes.py:459-460`; `python/arclink_wrapped.py:117-118`).
- LOW: legacy onboarding token migration trusts stored `pending_bot_token_path` and writes there without containment when opening the DB (`python/arclink_control.py:590`, `:7086-7090`), using `_write_private_text` (`:6973-6981`).

### Claude citations re-confirmed or corrected
- Reconfirmed: env-file values are fallback only because `_load_config_env` starts from `os.environ` and uses `setdefault` (`python/arclink_control.py:305`, `:334`).
- Reconfirmed: `org_provider_secret` is read but not stored in `Config` fields (`python/arclink_control.py:427-430`, `:539-547`).
- Corrected: “80 tables / 25 substrate” should read “79 CANON-01-owned CREATEs + SQLite internal `sqlite_sequence`”; after org-profile apply, same control DB reaches 85 tables.
- Corrected: `queue_notification` schema/delivery shape is valid (`python/arclink_control.py:745-757`, `:8055-8072`, `:9910-9914`), but not all producers use that API.

### Residual disagreement with the Claude half (for final reconciliation)
- I reject “entire SQLite schema / sole schema authority” as written.
- I reject “external callers consume notification/event APIs rather than raw SQL” as written.
- I accept the four CANON-01 MEDIUM severities; `connect_db` should explicitly include token migration and SSOT expiry in its contract.
<<<CODEX-VERDICT-END CANON-01>>>
