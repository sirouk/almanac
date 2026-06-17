# CANON-01 — Control Plane & Schema — RECONCILED (both-model truth)

- **Codex (GPT-5.5 xhigh) SIGN-OFF:** OBJECT(5) — "Core CANON-01 risks are real, but the record
  overstates schema centrality and helper exclusivity."
- **Claude Opus 4.8 FINAL ADJUDICATOR FEDERATION SIGN-OFF:** **BOTH-MODEL-AGREED**
- **Method:** every DISPUTED / REFUTE / REFINE / NEW-FINDING point below was re-opened in the
  cited code by the adjudicator (Read + rg + an in-`:memory:` schema rebuild). Code wins over any
  name, comment, or prior claim. CONFIRM items where both models already agreed are ratified in one
  line.

---

## RESOLUTION TABLE (disputed + adjudicated points)

| # | Point | Winner | Deciding cite (adjudicator-opened) |
|---|-------|--------|-------------------------------------|
| 1 | Unguarded `int()` casts hard-fail config load (MEDIUM) | both | `arclink_control.py:413` (`int(env.get("ARCLINK_MCP_PORT","8282"))`), `:415`, `:492` — all bare `int()`, no try-guard. Codex's extra cites (413/415) are more complete than the record's lone :492. |
| 2 | event/notification JSON paths do NOT reject secrets (MEDIUM) | both | `_arclink_json` `arclink_control.py:3234-3243` validates/dumps only, no `reject_secret_material`; `queue_notification` plain `json_dumps` `:8069`. Contrast `json_dumps_safe` `arclink_boundary.py:65`. |
| 3 | Config-file value silently truncated to first shlex token (MEDIUM) | both (G1≡Codex) | `arclink_control.py:330-331` keeps `parsed[0]` only; CIDR consumer `is_ip_in_cidrs` splits on commas only `:7616`. Space-separated allowlist in config file silently narrows. |
| 4 | `connect_db` is a WRITE path on open (REFINE → MEDIUM) | both (G3≡Codex) | `arclink_control.py:589-591`: `ensure_schema` + `_migrate_onboarding_bot_tokens` + `expire_stale_ssot_pending_writes`; expiry UPDATE+commit `:6020-6046`; token migration writes secret file + commit `:7087,7101`. Record's contract said "mkdir + journal + ensure_schema" only. |
| 5 | rowdict importer count: record "26" vs actual | codex/verify | AST/grep: modules importing `rowdict` specifically = **6**; 26 = modules importing *anything* from boundary. Producer passthrough `arclink_boundary.py:76`. Record's "26 importers of rowdict" cite is defective; the `def _rowdict`=0 convention claim still holds. |
| 6 | TRACE step-8 event-reader cites are the wrong tables | codex/verify | `arclink_dashboard.py:673-676` reads `arclink_rollouts` (not events); `arclink_api_auth.py:985-991` (`_public_session`) reads a user-session row (not events). Real `arclink_events` readers: `arclink_dashboard.py:1545-1560` (`_deployment_events`), `arclink_hosted_api.py:961-968`. Concept valid, cite wrong. |
| 7 | "80 tables / 25 substrate" headline | codex/verify (REFINE) | In-`:memory:` rebuild: 80 runtime tables = **79 source-owned `CREATE TABLE IF NOT EXISTS`** (counted in `ensure_schema` body :595-2560 = 79) + SQLite-internal `sqlite_sequence` (AUTOINCREMENT, e.g. `rate_limits` `:652`). Substrate is **24 owned + sqlite_sequence**, not 25 owned. 45 arclink_/10 academy_ correct. |
| 8 | "entire SQLite schema" / `ensure_schema` is the SOLE control-DB schema authority | codex (REFUTE) | `org_profile_apply` runs on the SAME `connect_db` conn (`arclink_ctl.py:2090`) and creates 5 extra `org_profile_*` tables via `ensure_org_profile_schema` `arclink_org_profile.py:1910-1957` (called at `:2093`). After apply, control DB = 80+5 = **85** tables. The record's "entire schema in a single ensure_schema" is scope-overstated. |
| 9 | "external callers consume the notification/event APIs rather than raw SQL" | codex (REFUTE) | Raw `INSERT INTO notification_outbox` `arclink_llm_router.py:1024-1041`, `arclink_wrapped.py:921-932`; raw `INSERT INTO arclink_events` `arclink_llm_router.py:1043-1051`, `arclink_chutes.py:917-925`. Helper contracts are NOT exclusive. |
| 10 | Seam #1 `append_arclink_event` kwargs both-ends | both (CONFIRM) | producer `arclink_control.py:3870`; consumer `arclink_api_auth.py:2189-2196` — exact kwargs match. Ratified. |
| 11 | Seam #2 `is_ip_in_cidrs`/`is_loopback_ip` both-ends | both (CONFIRM) | producer `arclink_control.py:7611,7604` `(value,cidrs)`; consumers `arclink_hosted_api.py:644-648` AND intra-piece `backend_client_allowed` `arclink_control.py:7628`. Fail-closed via `ipaddress` ValueError. Ratified. |
| 12 | Seam #3 Docker trust guards both-ends, fail-closed | both (CONFIRM) | producer `arclink_boundary.py:85-97,107`; consumer `arclink_gateway_exec_broker.py:22-25,66-70,289,378`. Exact-match `== "accepted"`. Ratified. |
| 13 | Process-env-wins-over-config-file precedence | both (CONFIRM) | `_load_config_env` `arclink_control.py:305` (`dict(os.environ)`) + `:334` `merged.setdefault`. Empirically re-proven. Ratified. |
| 14 | No `PRAGMA user_version` writer; `user_version=0`; no `__new`/`__legacy` leftovers | both (CONFIRM) | repo-wide grep `user_version` = 0 writers; in-`:memory:` rebuild `user_version=0`, no leftovers. Ratified. |
| 15 | ALMANAC_* aliases dead repo-wide | both (CONFIRM) | repo-wide `grep -rl ALMANAC python/` = 0 files. MEMORY.md "ALMANAC_* aliases preserved" is stale. Ratified. |
| 16 | `org_provider_secret` read-but-not-stored in Config | both (CONFIRM) | `arclink_control.py:427-430` read; not in dataclass field list. Good hygiene. Ratified. |
| 17 | `_discover_config_file` degenerate ternary; explicit-but-missing config silent no-op | both (CONFIRM, LOW) | `arclink_control.py:248-249` returns `path` in both branches; `:310-312` setdefault + env-only proceed. Ratified. |
| 18 | `export KEY=value` ignored as literal key `"export KEY"` (LOW, G2) | both | `arclink_control.py:324-325` splits on first `=` without stripping `export `. Ratified. |
| 19 | journal_mode lock-swallow + effective-mode never read (LOW/INFO, G4) | both | `arclink_control.py:573` issues PRAGMA, never reads back; `:576-577` swallows "database is locked". Ratified. |
| 20 | `frozen=True` Config shallow-immutable (`model_presets` dict) | both (INFO) | `arclink_control.py:398` mutable dict field. Ratified. |

---

## CODEX NEW FINDINGS — CONFIRMED vs REJECTED

**CONFIRMED (net-new federation risks):**

1. **MEDIUM — control-DB schema is larger than CANON-01 captures: org-profile adds 5 tables on the
   same connection.** `org_profile_apply(conn, ...)` (`arclink_ctl.py:2090`, conn from `connect_db`)
   → `_replace_profile_rows` `arclink_org_profile.py:1962` → `ensure_org_profile_schema`
   `:1910-1957` creates `org_profile_revisions/roles/people/teams/relationships`. Control DB reaches
   **85** tables after apply. **CONFIRMED.**
2. **MEDIUM — helper contracts are NOT exclusive (raw-SQL bypass of the producer APIs, with plain
   JSON encoders).** Raw `notification_outbox` INSERT `arclink_llm_router.py:1024-1041`,
   `arclink_wrapped.py:921-932`; raw `arclink_events` INSERT `arclink_llm_router.py:1043-1051`,
   `arclink_chutes.py:917-925` — all using plain `json.dumps`/`_json_dumps`/`_json_dumps_object`,
   not `json_dumps_safe`. Widens the secret-leak surface beyond the two producer helpers.
   **CONFIRMED.**
3. **LOW — legacy onboarding token migration trusts a stored path and writes there without
   containment on EVERY DB open.** `_migrate_onboarding_bot_tokens` `arclink_control.py:590` →
   `:7086-7090` writes the token to the row-stored `pending_bot_token_path` via `_write_private_text`
   `:6973-6981`, which `mkdir -p`s the parent and writes — no allowlist/containment of the target
   path. **CONFIRMED.**

**REJECTED:** none. All three Codex new findings re-verify true in code.

---

## SEVERITY CHANGES (code-supported only)

| Risk | From | To | Cite |
|------|------|----|------|
| `connect_db` write-on-open / side-effect surface (was LOW/MEDIUM "G3" in Claude verify; Claude record omitted it from the contract) | record: omitted | **MEDIUM** | `arclink_control.py:589-591`, `:6020-6046`, `:7087,7101` — UPDATE+commit and secret-file write on every open; contends the SQLite write lock, relevant to the record's "no app-level lock" concurrency claim. |
| Config-file shlex truncation (G1) | Claude record: not raised | **MEDIUM** | `arclink_control.py:330-331` + comma-only CIDR split `:7616` — touches a backend access-control allowlist. |

No other severities changed: the four original MEDIUMs (unguarded int casts, secret-leak surface)
are ratified at MEDIUM; LOW/INFO items unchanged.

---

## STANDING DISAGREEMENTS

None. Every material point reconciled to a single code-grounded truth. The only two phrasings Codex
"rejected" ("entire SQLite schema / sole authority" and "external callers consume the APIs rather
than raw SQL") are settled decisively against the record's wording by code (rows 8 & 9) — these are
resolved, not standing.

---

## FINAL BOTH-MODEL VERDICT

CANON-01 **provably does its core job**: `connect_db` → `ensure_schema` builds a deterministic,
idempotent control schema (79 source-owned CREATEs + `sqlite_sequence` = 80 runtime; 45 arclink_/10
academy_/24 owned substrate; `user_version=0`; no `__new` leftovers; no version ledger), with proven
process-env-wins config precedence and clean fail-closed Docker-trust / secret-rejection boundary
helpers. The reconciliation corrects four record imperfections (all evidentiary/scope, none
conclusion-breaking): (a) `ensure_schema` is the **primary but not sole** control-DB schema author —
org-profile adds 5 tables on the same connection (→85); (b) the producer helpers
`append_arclink_event`/`queue_notification` are **not exclusive** — raw-SQL inserts in
llm_router/wrapped/chutes bypass them with plain JSON, widening the secret-leak surface; (c)
`connect_db` is a **write path on open** (SSOT expiry UPDATE+commit, token-file migration), which the
contract must state and which bears on the "no app-level lock" concurrency story; (d) two record
cites were wrong (rowdict "26"→6 actual importers; TRACE-8 event readers pointed at
rollouts/sessions, real readers are dashboard:1545 / hosted_api:961). Both highest-traffic write
helpers plus their raw-SQL siblings bypass the boundary secret rejector, so secret hygiene depends on
each caller. Config-file values are silently shlex-truncated (a real access-control footgun for
space-separated CIDR allowlists). Net: **BOTH-MODEL-AGREED.**

---

<!-- CANON-REPAIR-STATUS:START -->
## Repair status

> Refreshed from [`research/canon/fixes/CANON-01-control-plane-schema.fix.md`](../fixes/CANON-01-control-plane-schema.fix.md) (active untracked). The audit findings above remain the adjudicated spec; this block records the repair campaign state for this piece.

- Status: completed, active uncommitted repair workspace.
- Summary: 9 fixed / 3 skipped / 0 needs-decision.
- Tests: 16 files run, all pass; py_compile pass; git diff --check pass
- Representative fixes:
  - MEDIUM — unguarded `Config.from_env` integer casts now default with warnings instead of crashing — `python/arclink_control.py:161`, `python/arclink_control.py:471`
  - MEDIUM — config-file parser now preserves multi-token values, handles `export KEY=value`, caches env-file reads, and fails loudly for missing explicit configs while preserving `/dev/null` sentinel — `python/arclink_control.py:347`
  - MEDIUM — event and notification helper JSON now rejects plaintext secret material before persistence — `python/arclink_control.py:3310`, `python/arclink_control.py:8179`
<!-- CANON-REPAIR-STATUS:END -->
