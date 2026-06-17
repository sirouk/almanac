# CANON-18 — Knowledge / Memory / Notion / MCP

## PIECE
This piece is ArcLink's agent-facing knowledge plane: it (a) **synthesizes
compact "memory cards"** from vault/Notion/Academy/shared sources on a timer, (b)
provides the **low-level Notion API client + SSOT handshake + no-secret proof
harness**, (c) **receives Notion webhooks** with an operator-armed verification-token
state machine, (d) runs the **loopback JSON-RPC MCP server** that brokers every
agent tool (vault/knowledge/notion/ssot/bootstrap/academy/pod_comms), and (e) the
**thin SSOT batcher** that drains the webhook queue. Owned files (all tracked):
`python/arclink_memory_synthesizer.py` (1927 lines, the synth job),
`python/arclink_notion_ssot.py` (1206 lines, Notion HTTP client + proof),
`python/arclink_notion_webhook.py` (380 lines, webhook receiver + token policy),
`python/arclink_mcp_server.py` (2715 lines, MCP server), and
`python/arclink_ssot_batcher.py` (24 lines, the batcher entrypoint). Crucially,
**almost all stateful logic these files invoke is implemented in
`arclink_control.py` (CANON-01)** — the tables, `store_notion_event`,
`process_pending_notion_events`, `consume_notion_reindex_queue`,
`notion_verify_signature`, `notion_search/fetch/query`, `read_ssot`,
`enqueue_ssot_write`, the broker scope checks, and the schema all live there. This
piece is mostly a thin set of **entrypoints, HTTP transports, and the Notion REST
client**; the prior ground-truth doc (`research/ground-truth/13-...`) over-scopes
CANON-18 by attributing `arclink_control.py`/`arclink_org_profile*`/`arclink_resource_map`
behavior to it — those are adjacent pieces (CANON-01/CANON-21) here.

## INPUT CONTRACT (code-verified)

### arclink_memory_synthesizer.py
- **`run_once(cfg: Config | None = None, *, model_client: ModelClient | None = None) -> dict`**
  (`arclink_memory_synthesizer.py:1682`). Entry from `main()` (`:1920`) via
  `bin/memory-synth.sh` -> systemd `arclink-memory-synth.service`. No external caller
  args; reads `Config.from_env()` and env. `model_client` is dependency-injected for
  tests, else chosen by `_settings_has_llm_config` (`:1691`).
- **`load_settings(cfg)`** (`:184`) reads env: `ARCLINK_MEMORY_SYNTH_ENABLED`
  (default `auto`, `:192`), `ARCLINK_MEMORY_SYNTH_ENDPOINT/MODEL/API_KEY` (`:186-188`),
  with **fallback to `PDF_VISION_ENDPOINT/MODEL/API_KEY`** (`:189-191`). Numeric bounds
  clamp via `_int_env` (`:163`): `MAX_SOURCES_PER_RUN` 1-100, `MAX_SOURCE_CHARS`
  500-50000, `MAX_OUTPUT_TOKENS` 100-4000, `TIMEOUT_SECONDS` 5-600,
  `FAILURE_RETRY_SECONDS` 60-86400, `CARDS_IN_CONTEXT` 1-30 (`:212-222`). `enabled` is
  `auto` => on iff full LLM config present; explicit value parsed by `_boolish` (`:201`).
- **Validation is fail-safe-by-bounding, not rejecting**: `_bounded_walk_files`
  (limit 800, skips dotdirs/symlinks/`SKIP_DIR_NAMES`, `:277`), `_safe_iterdir`
  (rejects symlinked dirs, `:252`), `_safe_notion_markdown_path` (traversal guard
  confining reads to `ARCLINK_NOTION_INDEX_MARKDOWN_DIR`, `:939`). Snippets are
  `redact_secret_material`-scrubbed (`_clean_space`, `:229`).
- Who may call: the timer user only; no network ingress.

### arclink_notion_ssot.py (pure client, no DB, no env)
- `handshake_notion_space(*, space_url, token, api_version=..., urlopen_fn=...) -> dict`
  (`:1002`): requires non-empty url+token (`:1013-1016`); extracts id, GETs `/users/me`,
  resolves target, resolves stable root page.
- `run_notion_ssot_no_secret_proof(*, callback_url, root_page_id, token, token_ref="",
  api_version=..., urlopen_fn=None, run_write_preflight=False, proof_mode="fake",
  allow_live_mutation=False) -> dict` (`:1074`): `proof_mode` validated to
  {`fake`,`authorized_live`} (`:1096`); **`fake` mode REQUIRES an injected `urlopen_fn`**
  (`:1099-1100`); token required (`:1102-1104`). The raw token is never returned.
- The ~30 `retrieve_*/create_*/update_*/query_*/append_*` functions all take
  keyword-only `token`, optional `api_version` (default `2026-03-11`, `:11`), and an
  injectable `urlopen_fn`; ids are normalized by `extract_notion_space_id` (`:47`) which
  raises `ValueError` on a missing/short id (`:30-31`).

### arclink_notion_webhook.py (HTTP + operator state machine)
- `do_POST` (`:311`): loopback-only (`_require_loopback_transport`, `:289`); only
  `/notion/webhook` (`:314`); `Content-Length` parsed (`:318`), rejects `<0` or
  `> MAX_WEBHOOK_BODY_BYTES` (256 KiB, `:31`/`:322`); body must be JSON (`:327`).
- `handle_verification_token_post(conn, candidate_token) -> (int, dict)` (`:197`):
  candidate required (`:206-208`); **refuses overwrite if a token is already stored
  -> 409 CONFLICT** (`:210`); **requires the operator-armed window or 412
  PRECONDITION_FAILED** (`:220-230`).
- `arm_verification_token_install(conn, *, ttl_seconds, actor)` (`:109`): `ttl` floored
  to 60s (`:110`). `reset_verification_token` (`:134`), `mark_verification_token_verified`
  (`:251`, raises if no token stored). Callers are `arclink_ctl.py` (CANON-14),
  cites `arclink_ctl.py:26-29,2697-2748`.
- `do_GET` (`:303`): `/health` is **public** (returned before the loopback check,
  `:304-305`); everything else requires loopback then 404.

### arclink_mcp_server.py (JSON-RPC over loopback)
- `do_POST` (`:1744`): loopback-only (`:1745`), `/mcp` only (`:1747`), body bounded by
  `ARCLINK_MCP_MAX_REQUEST_BYTES` (default 1 MiB, capped 16 MiB, `:1650`). Dispatch on
  `method` in {`initialize`,`notifications/initialized`,`tools/list`,`tools/call`}.
- Auth model: per-tool. Enrolled tools read `token` (harness-injected `AGENT_TOKEN_PROP`,
  `:163`) and call `validate_token` (e.g. `:2667`); operator tools call `_require_operator`
  (`:1882`, reads `operator_token` or legacy `token` -> `validate_operator_token`);
  `bootstrap.*` gate on tailnet/loopback source (`_ensure_bootstrap_source_allowed`,
  `:1858`) + optional Tailscale-Serve identity headers (`_tailscale_identity`, `:1863`,
  gated by `ARCLINK_TRUST_TAILSCALE_PROXY_HEADERS`).

### arclink_ssot_batcher.py
- `main()` (`:10`): no args; `Config.from_env()`, one DB connection, calls
  `process_pending_notion_events(conn)` then `consume_notion_reindex_queue(conn, cfg,
  actor="ssot-batcher")`, prints `{"events":..., "reindex":...}` JSON.

## OUTPUT CONTRACT (code-verified)
- **memory-synth -> `memory_synthesis_cards`** (schema `arclink_control.py:944-960`;
  UNIQUE index on `(source_kind, source_key)` at `:1848`). `_upsert_card` (`:1543`)
  writes `card_id`, `source_signature` (=`sha256(json_dumps(payload))`, `:141`),
  `prompt_version="memory-synth-v3"` (`:34`), `model`, `status` in
  {ok,failed,stale}, `card_json`, `card_text`. Returns `bool` "changed". `_mark_stale_cards`
  (`:1626`) blanks `card_text` and sets `status='stale'` when source disappears.
- **memory-synth side effects**: atomic redacted `status.json` via `_write_status`
  (`:1673`, strips `api_key/authorization/token/secret/password`); `note_refresh_job`
  job `memory-synth` (`:1853`); on `changed>0` a `queue_notification(target_kind=
  "curator", channel_kind="brief-fanout", ...)` (`:1826`) and an immediate
  `consume_curator_brief_fanout` unless `ARCLINK_MEMORY_SYNTH_CONSUME_FANOUT=0` (`:1844`);
  consumes Academy refresh markers (`:1871`). Holds `fcntl.LOCK_EX` on `synth.lock`
  for the whole run (`:1695-1696`).
- **notion_ssot client**: pure dicts; `run_notion_ssot_no_secret_proof` returns
  `{ok, model:"brokered_shared_root", proof_mode, token_ref_status, api_version,
  checks:[...]}` (`:1198-1205`) — public urls/ids only.
- **webhook -> `notion_webhook_events`** via `store_notion_event` (INSERT OR IGNORE,
  `arclink_control.py:12151`). On accept it responds HTTP 200
  `{"status":"accepted","event_id":...}` (`:360`) THEN fires `_kick_ssot_batcher()`
  (`:361`) which **debounces 1.0s** (`:62-81`) and `subprocess.Popen`s
  `systemctl --user --no-block start arclink-ssot-batcher.service` (`:42-55`).
  Token POST returns 200/400/409/412. Token state mutates `settings` keys
  (`:83-91`) and `note_refresh_job` job `notion-webhook-token`.
- **MCP**: JSON-RPC results returned as `{"content":[{"type":"text","text":json}],
  "structuredContent":result}` (`:1835-1838`). **JSON-RPC errors return HTTP 200**
  with `X-ArcLink-MCP-Error-Status` header (`:1718-1721`) to avoid client teardown.
  `ssot.write` calls `enqueue_ssot_write` and normalizes via
  `_normalize_ssot_write_result` (`:2670`). vault/knowledge tools emit
  `_mcp_tool_call(cfg.qmd_url, "query"/"get", ...)` to the qmd MCP.
- **batcher -> stdout** JSON `{events, reindex}` (`:15-20`); all DB writes happen
  inside the two control functions.

## TOUCH POINTS
- **Env vars (read in CANON-18 files)**: `ARCLINK_MEMORY_SYNTH_ENABLED/ENDPOINT/MODEL/
  API_KEY/MAX_SOURCES_PER_RUN/MAX_SOURCE_CHARS/MAX_OUTPUT_TOKENS/TIMEOUT_SECONDS/
  FAILURE_RETRY_SECONDS/CARDS_IN_CONTEXT/STATE_DIR/STATUS_FILE/LOCK_FILE`
  (`memory_synthesizer.py:186-225`), `PDF_VISION_ENDPOINT/MODEL/API_KEY` (`:189-191`),
  `ARCLINK_MEMORY_SYNTH_CONSUME_FANOUT` (`:1844`), `ARCLINK_NOTION_INDEX_MARKDOWN_DIR`
  (`:943`); `ARCLINK_MCP_MAX_REQUEST_BYTES` (`mcp_server.py:1652`),
  `ARCLINK_ALLOW_LOOPBACK_SOURCE_IP_OVERRIDE` (`:1853`),
  `ARCLINK_TRUST_TAILSCALE_PROXY_HEADERS` (`:1873`), `ARCLINK_FLEET_SHARED_ROOT/
  ARCLINK_FLEET_SHARED_COLLECTION_NAME/ARCLINK_LINKED_RESOURCES_ROOT/
  ARCLINK_LINKED_COLLECTION_NAME` (`:665-668`). Webhook/batcher read no env directly
  (they use `Config.from_env`). NOTE: `bin/memory-synth.sh` also exports
  `ARCLINK_MEMORY_SYNTH_MAX_CONTENT_HASH_BYTES`, but the Python only defines the
  constant `DEFAULT_MAX_CONTENT_HASH_BYTES` (`:42`) and never reads that env var
  (see DRIFT).
- **DB tables (r/w)**: `memory_synthesis_cards` (rw), `notion_index_documents` (r,
  `memory_synthesizer.py:954`; schema `control.py:902`), `notion_webhook_events`
  (rw via store/claim; schema `control.py:774`), `notification_outbox` (the reindex
  queue, read by `consume_notion_reindex_queue` `control.py:14828`), `settings`
  (webhook token keys; `refresh_jobs` via `note_refresh_job`).
- **Sockets/ports**: MCP `127.0.0.1:8282` (`ARCLINK_MCP_PORT`, `control.py:413`);
  webhook `127.0.0.1:8283` (`ARCLINK_NOTION_WEBHOOK_PORT`, `:415`); qmd MCP client
  target `cfg.qmd_url` default `http://127.0.0.1:8181/mcp` (`:417`); Notion API
  `https://api.notion.com/v1` (`notion_ssot.py:10`).
- **Subprocess**: `systemctl --user --no-block start arclink-ssot-batcher.service`
  (`notion_webhook.py:43-49`); `_git_output` runs `git` in MCP vault-source enrichment
  (`mcp_server.py:864`).
- **Locks**: `fcntl.flock(LOCK_EX)` on `synth.lock` (`memory_synthesizer.py:1696`);
  `threading.Lock` + `threading.Timer` debounce in the webhook (`notion_webhook.py:28-30`);
  DB write-claim lease on webhook events (`_claim_pending_notion_webhook_events`,
  `control.py:19154`).
- **External services**: Notion REST (client), qmd MCP (vault retrieval bridge),
  systemd user manager (batcher kick). **Secrets**: Notion `token` passed only as a
  keyword arg to the client and never logged; status.json redaction; LLM `api_key`
  sent only as a Bearer header (`memory_synthesizer.py:1136`).

## CODE-PATH TRACE — Notion webhook -> reindex (end to end)
1. Notion POSTs to `127.0.0.1:8283/notion/webhook`; `Handler.do_POST`
   (`notion_webhook.py:311`) enforces loopback (`:312`), path (`:314`), body bounds
   (`:318-323`), JSON parse (`:327`).
2. If `payload.verification_token` present (`:339`) -> `handle_verification_token_post`
   (`:197`): 409 if already stored / 412 if not armed / 200 + store on success.
3. Else read stored token (`:344`); 412 if absent; verify signature via
   `notion_verify_signature(raw_body, X-Notion-Signature, stored_token)`
   (`control.py:12135`, HMAC-SHA256 `compare_digest`); 403 on mismatch (`:349`).
4. Derive `event_id` from `id`/`event_id`/`entity.id` (`:352`); 400 if none (`:355`);
   `store_notion_event` INSERT OR IGNORE into `notion_webhook_events` (`control.py:12151`).
5. Respond HTTP 200 `{status:"accepted",event_id}` (`:360`), THEN `_kick_ssot_batcher()`
   (`:361`) -> debounce 1.0s (`:62-81`) -> `_spawn_batcher_now` Popen systemctl (`:42`).
6. systemd `arclink-ssot-batcher.service` runs `bin/arclink-ssot-batcher.sh` ->
   `arclink_ssot_batcher.main` (`:10`).
7. `process_pending_notion_events(conn)` (`control.py:19206`):
   `_claim_pending_notion_webhook_events` leases pending/stale-processing rows
   (`:19154`, claim_id, 600s lease, `batch_status='processing'`), dedupes on event_id,
   maps `(entity_type, entity_id)` into `reindex_entities` (page/database -> incremental,
   data_source/file_upload -> `("full","full")`, `:19269-19277`), routes per-user nudges,
   marks rows `processed`. (Reindex enqueue into `notification_outbox` happens inside
   the mapping helpers in CANON-01.)
8. `consume_notion_reindex_queue(conn, cfg, actor="ssot-batcher")` (`control.py:14821`)
   drains `notification_outbox WHERE target_kind='curator' AND channel_kind='notion-reindex'`,
   computes page/database ids + full-sweep, calls `sync_shared_notion_index` (re-fetches
   page markdown -> `notion_index_documents` -> qmd reindex of `notion-shared`),
   retries unresolved entities up to a max, records `note_refresh_job`.
9. Batcher prints `{events, reindex}` to stdout (`ssot_batcher.py:15-20`).

## CODE-PATH TRACE — memory-synth cycle (end to end)
1. `bin/memory-synth.sh` exports env, runs `arclink_memory_synthesizer.main` -> `run_once`
   (`:1682`).
2. `load_settings` resolves enable + LLM config (`:184`); `model_client` chosen (`:1691`).
3. Acquire `LOCK_EX` on `synth.lock` (`:1695`); open DB (`:1697`). If disabled, write
   `note_refresh_job(status="disabled")` + status.json and return (`:1698-1724`).
4. `build_candidates` (`:1052`) = vault (`:508`) + academy seeds (`:652`) + shared docs
   (`:868`) + notion (`:954`). Each `SourceCandidate.source_signature` = full-content
   sha256 fingerprint digest (`:141`, payload includes `_file_content_hash`, `:324`).
5. `_mark_stale_cards` blanks vanished sources (`:1728`). For each candidate, skip if a
   prior `status='ok'` card matches `source_signature`+`prompt_version`+`model` (`:1734-1742`);
   skip failed cards within backoff only when source unchanged (`:1743-1754`).
6. Top `max_sources_per_run` by source_count synthesized via `model_client` -> LLM
   `call_openai_compatible_model` (`:1104`, temp 0.1, bounded tokens) OR
   `local_non_llm_fallback_model` (`:1314`, deterministic, no network).
7. `_normalize_card_payload` (`:1393`) clamps fields + runs `_card_has_unsafe_output`
   (`:1436`) against `UNSAFE_OUTPUT_PATTERNS` (`:95`); on hit blanks summary, sets
   `inject=false`, `unsafe_output_rejected=true`.
8. `render_card_text` (`:1474`) then `_upsert_card` (`:1543`). On any model exception,
   tries local fallback (if LLM-configured), else writes a `failed` card preserving prior
   text (`:1780-1822`).
9. If `changed>0`: `queue_notification(brief-fanout)` + immediate
   `consume_curator_brief_fanout` (`:1826-1850`). Write `note_refresh_job` + redacted
   `status.json` (`:1853,1916`); return result dict.

## CROSS-PIECE CONTRACTS (both ends verified)

1. **webhook -> systemd batcher (CANON-26)** — producer
   `notion_webhook.py:42-49` spawns argv `["systemctl","--user","--no-block","start",
   "arclink-ssot-batcher.service"]`; consumer unit
   `systemd/user/arclink-ssot-batcher.service` `ExecStart=%h/arclink/bin/arclink-ssot-batcher.sh`.
   The unit name string matches exactly. **BOTH-ENDS-VERIFIED: yes.**

2. **batcher -> control-plane batch funcs (CANON-01)** — producer
   `ssot_batcher.py:13-14` calls `process_pending_notion_events(conn)` then
   `consume_notion_reindex_queue(conn, cfg, actor="ssot-batcher")`; consumer signatures
   `control.py:19206` (positional conn) and `control.py:14821` (conn, cfg, kw `actor`).
   Arg shapes match. **BOTH-ENDS-VERIFIED: yes.**

3. **webhook signature check (CANON-01)** — producer passes `raw_body` (bytes),
   `X-Notion-Signature` header, `stored_token` (`notion_webhook.py:348`); consumer
   `notion_verify_signature(raw_body, header_value, verification_token)`
   (`control.py:12135`) computes `"sha256="+HMAC` and `compare_digest`. Byte/arg order
   matches. **BOTH-ENDS-VERIFIED: yes.**

4. **webhook token state -> ctl (CANON-14)** — producer functions
   `arm_verification_token_install/reset_verification_token/mark_verification_token_verified/
   get_verification_token_state` (`notion_webhook.py:109,134,251,178`); consumer
   `arclink_ctl.py:26-29` imports them and calls at `:2697-2748`. Same names/kwargs
   (`ttl_seconds/actor/rearm_ttl_seconds`). **BOTH-ENDS-VERIFIED: yes.**

5. **MCP ssot.write -> broker (CANON-01)** — producer `mcp_server.py:2670` calls
   `enqueue_ssot_write(conn, cfg, agent_id=, operation=, target_id=, payload=,
   requested_by_actor=)`; result fed to `_normalize_ssot_write_result` (`:1605`).
   Consumer is `enqueue_ssot_write` in control (imported `:41`). The forbidden ops
   (archive/delete/trash) are rejected inside the broker (CANON-01), not here.
   **BOTH-ENDS-VERIFIED: partial** — producer args verified against the import; the
   broker's internal rejection of destructive ops and the exact returned keys consumed
   by `_normalize_ssot_write_result` (`final_state`,`target_id`,`url`,`id`) were read
   from the consumer side only; I did not open `enqueue_ssot_write`'s body. Flag for Codex.

6. **MCP vault/knowledge -> qmd MCP (CANON-31/external qmd)** — producer
   `_mcp_tool_call(cfg.qmd_url, "query"|"get", args)` (`mcp_server.py:676`) speaks MCP
   `2025-03-26` (`:75`) and posts `{searches:[{type:lex|vec,query}], collections, intent,
   rerank:false}` (`_qmd_query_arguments`, `:731`). Consumer is the external qmd binary
   (pinned `config/pins.json`), not in this repo. **BOTH-ENDS-VERIFIED: no** — qmd is an
   external service; only the producer end is in-tree. Protocol-version coupling is a
   comment claim (`:71-75`), not verified against qmd source.

7. **notion_ssot client -> control broker (CANON-01)** — producer: the 20+ client
   functions (`notion_ssot.py`); consumer `control.py:33-54` imports
   `retrieve_notion_page/database/data_source`, `query_notion_collection[_all]`,
   `create_notion_page/database`, `update_notion_*`, `append_notion_block_children`,
   `retrieve_notion_page_markdown`, etc. Names + keyword-only signatures match the
   imports. **BOTH-ENDS-VERIFIED: yes** (import-list vs def-list); the higher broker
   logic that calls them was not fully traced.

8. **notion_ssot handshake/preflight -> ctl (CANON-14)** — producer
   `handshake_notion_space`/`preflight_notion_root_children` (`:1002,924`); consumer
   `arclink_ctl.py:2753,2773` passes `space_url/token/api_version` and `root_page_id/
   token/api_version`. **BOTH-ENDS-VERIFIED: yes.**

## CODE vs COMMENT/DOC/NAME DRIFT
1. **`ARCLINK_MEMORY_SYNTH_MAX_CONTENT_HASH_BYTES` is exported but never read.**
   `bin/memory-synth.sh` exports it, and `_file_content_hash` uses the constant
   `DEFAULT_MAX_CONTENT_HASH_BYTES` (8 MiB, `memory_synthesizer.py:42`,324`), but
   `load_settings` never calls `_int_env` for that env var. Setting it has no effect.
   Code wins: the cap is hardcoded.
2. **Prior ground-truth doc over-scopes CANON-18.** `research/ground-truth/13-...:13-14`
   attributes `arclink_control.py` tables/SSOT-broker/today-plate and
   `arclink_org_profile*`/`arclink_resource_map` to this subsystem. In the CANON
   decomposition those are CANON-01/CANON-21. The memory/Notion *logic* (store/process/
   consume/search/broker) is in `arclink_control.py`, which CANON-18 only **calls**.
3. **Prior doc: "webhook ... 1s debounce ... 1-min timer".** Verified: debounce is
   `_BATCHER_KICK_DEBOUNCE_SECONDS = 1.0` (`notion_webhook.py:30`) and the timer is
   `OnUnitActiveSec=1m` (`systemd/user/arclink-ssot-batcher.timer`). Accurate.
4. **Prior doc: notion candidate snippet reads "path-confined ... traversal guard".**
   Verified at `memory_synthesizer.py:939-951` (`_safe_notion_markdown_path` resolves and
   `relative_to(markdown_root)`); accurate.
5. **`_spawn_batcher_now` docstring claims the auto-reaper handles the zombie via the
   "discarded Popen object's destructor"** (`notion_webhook.py:38-41`). The Popen object
   is created in an expression statement and immediately discarded; CPython's Popen has
   no `__del__`-based reaper that waits — zombies are reaped lazily on the next Popen
   construction/`_cleanup`. The comment overstates determinism; in practice systemctl
   exits fast so the window is tiny. Behavioral, low risk, but the comment is not
   strictly accurate.
6. **MCP `_ensure_mcp_session` docstring**: "The MCP session id is transport bookkeeping,
   not authorization" — verified true: it only gates protocol methods, and tools
   re-validate tokens (`:2667` etc.). No drift; called out because it is a security claim.

## ADVERSARIAL SELF-CHECK
1. **Claim: webhook batcher kick cannot lose events.** Least sure. If
   `_spawn_batcher_now` raises (caught and swallowed, `:56-59`) AND the systemd timer is
   disabled, events sit in `notion_webhook_events` forever. The 1-min timer is the only
   guaranteed drain. Falsifier: a host without the `.timer` enabled. The webhook never
   retries the kick itself.
2. **Claim: `process_pending_notion_events` claim is concurrency-safe.** Medium. The
   SELECT-then-UPDATE-then-reSELECT in `_claim_pending_notion_webhook_events`
   (`control.py:19154`) relies on sqlite serializing writes at commit; two concurrent
   batchers could both SELECT the same ids, but the guarded UPDATE `WHERE batch_status=
   'pending' OR (...stale...)` plus per-claim re-SELECT by `batch_claim_id` should make
   only one win. I did not test two concurrent processes; falsifier would be a race where
   both re-SELECTs return the same row under WAL. (This is CANON-01 code, flagged for
   completeness.)
3. **Claim: ssot.write rejects destructive ops.** Medium. I verified the producer call
   and the doc string (`mcp_server.py:107` "Archive/delete are rejected"), and the const
   `SSOT_FORBIDDEN_OPERATIONS` (`control.py:12164`), but I did NOT read the body of
   `enqueue_ssot_write` to confirm it enforces them. Falsifier: a code path in the broker
   that accepts `operation="trash"`.
4. **Claim: fake-mode proof requires injected transport.** High confidence —
   `notion_ssot.py:1099-1100` raises without `urlopen_fn` in fake mode. But
   `authorized_live` defaults to `request.urlopen` (`:1101`), so a caller passing
   `proof_mode="authorized_live"` with no urlopen hits the live network even with
   `allow_live_mutation=False` (reads only, since write preflight is separately gated).
   Falsifier: none found; this is by design but worth noting.
5. **Claim: `/health` on the webhook is intentionally pre-auth.** High. `do_GET` returns
   health before `_require_loopback_transport` (`notion_webhook.py:304-307`). If the
   webhook is ever exposed beyond loopback (e.g. via Tailscale Funnel) `/health` leaks
   service presence. The funnel scripts exist (`bin/tailscale-notion-webhook-funnel.sh`).

## OPEN FOR CODEX FEDERATION
1. Read `enqueue_ssot_write` (control.py) and confirm: (a) it rejects
   `SSOT_FORBIDDEN_OPERATIONS`, (b) the exact return keys consumed by
   `_normalize_ssot_write_result` (`mcp_server.py:1605-1626`) — does the broker always
   emit `final_state`/`target_id`/`url`/`id`?
2. Confirm the reindex enqueue producer: `process_pending_notion_events` builds
   `reindex_entities` but the actual `notification_outbox` rows with
   `channel_kind='notion-reindex'` are written elsewhere — find that producer and verify
   `source_kind`/`target_id` shape matches what `consume_notion_reindex_queue` reads
   (`control.py:14850-14863`).
3. Verify the qmd MCP protocol-version coupling: does the pinned qmd in
   `config/pins.json` actually speak `2025-03-26`? The comment at `mcp_server.py:71-75`
   asserts it; this crosses into CANON-27/CANON-31.
4. Concurrency: prove that two `arclink-ssot-batcher.service` invocations (timer +
   webhook kick firing together) cannot double-process an event under WAL.

## RISKS (severity-ranked, code-cited)
- **MEDIUM — Event drain depends entirely on the 1-min timer if the kick fails.**
  `_spawn_batcher_now` swallows all exceptions (`notion_webhook.py:56-59`) and there is
  no in-process retry; if systemd timer is not enabled, stored events are never
  processed. Fail-safe only because the timer normally exists.
- **MEDIUM — `authorized_live` proof mode uses real `request.urlopen` by default**
  (`notion_ssot.py:1101`). A caller selecting live mode without injecting a transport
  performs real Notion reads of the root page (`:1120`) even with
  `allow_live_mutation=False`. Reads only, but it is live network egress with the real
  token.
- **LOW — `/health` GET answered before loopback auth** (`notion_webhook.py:304-307`)
  and on the MCP side health is behind loopback (`mcp_server.py:1727-1742`), so the
  webhook is the asymmetric one; under a Funnel it leaks presence.
- **LOW — MCP returns all JSON-RPC errors as HTTP 200** (`mcp_server.py:1718`). Correct
  for the streamable-http client, but means transport-layer monitors see only 200s;
  error signal is in a custom header `X-ArcLink-MCP-Error-Status`.
- **LOW — exported env `ARCLINK_MEMORY_SYNTH_MAX_CONTENT_HASH_BYTES` is dead** (DRIFT 1);
  operators may believe they can raise the 8 MiB hash cap but cannot.
- **INFO — memory cards are explicitly "awareness hints, not evidence"** and
  unsafe-output-filtered (`memory_synthesizer.py:1108-1110,1429-1433`); the synth path is
  off the chat critical path (timer-only) and fully bounded/redacted.

## VERDICT
This piece **provably does its job** within its real (narrow) scope. Load-bearing
strengths verified in code: (1) the memory-synth cycle is bounded, content-hash-based
for freshness, prompt-injection-wrapped, unsafe-output-filtered, secret-redacted, and
single-flighted under `flock` — and it never sits on the chat path. (2) The Notion
client is a clean, retry/backoff-correct, dependency-injectable REST layer with a
no-secret proof harness that is fail-closed on live mutation. (3) The webhook enforces
loopback, body bounds, HMAC signature verification, and a genuine operator-armed
verification-token install state machine (409/412) that resists secret overwrite on a
shared host. (4) The MCP server is loopback-only with per-tool token auth and
restart-safe sessions. Real weaknesses: the webhook->batcher kick is best-effort and
leans on the 1-min timer as the only guarantee; the heavy lifting (broker scope checks,
reindex queue writes, destructive-op rejection) lives in CANON-01 and was only verified
from the consumer side here; and one exported env var is dead. The prior ground-truth
doc is materially accurate on behavior but over-attributes adjacent-piece code to
CANON-18.
