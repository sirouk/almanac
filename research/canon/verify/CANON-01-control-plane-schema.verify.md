# CANON-01 — Control Plane & Schema — ADVERSARIAL VERIFICATION

Verifier: independent adversarial skeptic. Method: re-opened every load-bearing line,
re-built the schema in `:memory:`, re-ran the loader, and traced both ends of each
cross-piece seam. Code wins over comments/names/prior docs.

## VERDICT (overall)
The record is **largely trustworthy on its core structural claims** (schema count,
env precedence, fail-closed Docker gate, secret-leak surface, unguarded int casts —
all independently re-confirmed in code). BUT it contains **two demonstrable citation
defects** (one in a "both-ends-verified" cross-piece contract, one in the round-trip
TRACE) and **misses three real undocumented gaps** in the config-file parser and the
`connect_db` side-effect surface. Net: trust the conclusions, distrust two specific
evidentiary cites, and add the missed gaps.

---

## REFUTATIONS / RE-CONFIRMATIONS

### R1 — REFUTED (citation defect): "rowdict imported in 26 modules"
CROSS-PIECE CONTRACT #4 states `rowdict` is "imported in 26 modules
(`grep \"from arclink_boundary import\"`)". The grep counts modules importing ANYTHING
from `arclink_boundary` (= 26). Modules importing **`rowdict` specifically = 6**
(AST-checked). The cited evidence does NOT prove the claim it is attached to.
The *broader* convention claim (no surviving `def _rowdict`, =0) is still TRUE, so the
conclusion survives, but the "26" adoption figure for `rowdict` is wrong.
Cite: python/arclink_boundary.py:76 (producer); importer count by AST = 6, not 26.

### R2 — REFUTED (citation defect): TRACE step 8 reader cites are the wrong table
TRACE step 8 claims the `arclink_events.metadata_json` written by `append_arclink_event`
is read back via `json_loads_safe`/`_json_loads` at `arclink_dashboard.py:676` and
`arclink_api_auth.py:991`. Reality:
- `arclink_dashboard.py:676` reads `metadata_json` from **arclink_rollouts**, not arclink_events.
- `arclink_api_auth.py:991` (`_public_session`) reads `metadata_json` from **arclink_user_sessions**, not arclink_events.
The round-trip *concept* is valid — real `arclink_events` readers exist
(arclink_dashboard.py:1549/2017/2044, arclink_hosted_api.py:964) — but the SPECIFIC
both-ends citation is wrong. A citation that does not say what the record claims.

### R3 — PARTIAL REFUTE (mis-attribution): "80 tables / 25 substrate" headline
Re-built schema in `:memory:` (with `row_factory=sqlite3.Row`, required — bare cursor
crashes `_table_columns` at :2553): `sqlite_master` = 80 tables (45 arclink_/10 academy_/
25 other), user_version=0, no `__new`/`__legacy` leftovers, idempotent on re-run. The
COUNT is correct, BUT the "25 unprefixed substrate tables" with CREATE cites is wrong by
one: the record enumerates only **24** substrate CREATEs; the 25th is `sqlite_sequence`,
an SQLite-internal table auto-created by AUTOINCREMENT — NOT a `CREATE` owned by this
piece. So `ensure_schema` CREATEs **79** tables; the 80th is engine bookkeeping. Minor,
but the record presents all 25 as owned substrate.

### R4 — CONFIRMED: process-env-wins precedence
Re-ran loader: `ARCLINK_PROBE_KEY` present in both env (`from_process_env`) and config
file (`from_config_file`) -> merged = `from_process_env`; file-only key surfaces as
`file_value`. `merged.setdefault(...)` at arclink_control.py:334. TRUE.

### R5 — CONFIRMED: unguarded int casts (MEDIUM)
`ARCLINK_BOOTSTRAP_WINDOW_SECONDS=abc` -> unhandled `ValueError` at
`Config.from_env` (arclink_control.py:492). Hard-fails config load. TRUE.

### R6 — CONFIRMED: secret-leak surface (MEDIUM)
Empirically persisted a plaintext `sk-ant-...` token through BOTH
`append_arclink_event(metadata=...)` (-> `_arclink_json`, arclink_control.py:3234, only
validates JSON, no `reject_secret_material`) and `queue_notification(extra=...)` (->
`json_dumps`, arclink_control.py:8069). Both rows stored the secret verbatim. TRUE.
Severity MEDIUM is defensible (latent, caller-conditional, but high-traffic rows).

### R7 — CONFIRMED: cross-piece contract #1 (append_arclink_event kwargs)
Producer arclink_control.py:3870-3879 keyword-only `(subject_kind, subject_id,
event_type, metadata, event_id, commit)`; consumer arclink_api_auth.py:2189-2196 passes
exactly `subject_kind=/subject_id=/event_type=/metadata=/commit=`. Both ends match. TRUE.

### R8 — CONFIRMED w/ caveat: cross-piece contract #2 (is_ip_in_cidrs / is_loopback_ip)
Producer arclink_control.py:7611 `(value:str, cidrs:str)`; consumer
`_backend_client_allowed` at arclink_hosted_api.py:644-648 calls
`is_ip_in_cidrs(normalized, config.backend_allowed_cidrs)` — shape matches. I verified
the consumer end the record left as a "handoff". CAVEAT: the record missed that an
INTRA-piece consumer `backend_client_allowed` also exists at arclink_control.py:7628
(no leading underscore) — same file, not CANON-02. Both-ends now fully verified.

### R9 — CONFIRMED: cross-piece contract #3 (Docker trust guard)
Producer arclink_boundary.py:85/107; consumer arclink_gateway_exec_broker.py:24-25 imports
both, calls `require_trusted_docker_binary(os.environ.get("ARCLINK_DOCKER_BINARY"),
service=..., trusted_paths=..., which=shutil.which)` (:66) and
`require_docker_trusted_host_risk_accepted(service=SERVICE_NAME, error_cls=ValueError/
SystemExit)` (:289/:378). Both ends match. Fail-closed re-tested: untrusted
which()-result and untrusted absolute path both rejected. TRUE.

### R10 — CONFIRMED: drift #3 ALMANAC aliases dead (record under-claimed scope)
`grep -c ALMANAC` over control AND boundary = 0; AND repo-wide `grep -rl ALMANAC python/`
= ZERO files. The record's Codex open item ("confirm ALMANAC dead repo-wide") is hereby
RESOLVED: dead across all of python/.

### R11 — CONFIRMED: no PRAGMA user_version writes anywhere (record self-check #3 resolved)
`grep -rn user_version python/ bin/` = zero hits. The "no version ledger, user_version=0"
claim is solid repo-wide, not just one empirical run. Self-check #3 falsifier eliminated.

### R12 — CONFIRMED: _ensure_managed_database_schema / ensure_notion_verification_database
do NOT add control-DB tables (self-check #1 resolved). Read :5768 — operates on Notion
HTTP payloads, no SQLite CREATE. The 79-CREATE count is authoritative for the control DB.

### R13 — CONFIRMED: drift #6 degenerate ternary
`_discover_config_file` arclink_control.py:248-249 is `return path if
_safe_path_is_file(path) else path` — returns `path` in BOTH branches (pointless ternary);
explicit-but-missing config file silently proceeds env-only. TRUE.

---

## NEW GAPS (missed by BOTH the record and prior docs)

### G1 — MEDIUM: config-file value silent truncation to first shlex token
`_load_config_env` at arclink_control.py:330-331 does `shlex.split(raw_value, posix=True)`
and keeps ONLY `parsed[0]`. An unquoted multi-token value is SILENTLY TRUNCATED:
- `ARCLINK_BACKEND_ALLOWED_CIDRS=10.0.0.0/8 192.168.0.0/16` -> `10.0.0.0/8` (second CIDR dropped)
- `ARCLINK_CURATOR_CHANNELS=telegram, discord` -> `telegram,` (mangled)
This is a security-adjacent footgun: an operator who writes a two-CIDR backend allowlist
unquoted in the config file silently gets a one-CIDR allowlist. Affects only
config-FILE-sourced values (process env is taken verbatim). Neither record nor prior docs
flag it, despite the record citing the very line (`shlex-split first token`, :330).
Reproduced empirically.

### G2 — LOW: config-file parser does not handle `export KEY=value`
Same parser (arclink_control.py:324-325) splits on the first `=` without stripping a
leading `export `. A `.env`-style line `export ARCLINK_MCP_PORT=9999` is stored under the
literal key `"export ARCLINK_MCP_PORT"`, which never matches `env.get("ARCLINK_MCP_PORT")`
-> the setting is silently ignored and the default used. Reproduced empirically.
Common `.env` convention -> silent misconfiguration.

### G3 — LOW/MEDIUM: connect_db OUTPUT CONTRACT omits two mutating side-effects
The record's OUTPUT CONTRACT for `connect_db` lists only "mkdir + journal file +
ensure_schema run". But `connect_db` (arclink_control.py:563) ALSO runs, on EVERY
connection open:
- `_migrate_onboarding_bot_tokens(conn, cfg)` (:590)
- `expire_stale_ssot_pending_writes(conn)` (:591) -> runs `UPDATE ssot_pending_writes SET
  status='expired' ... WHERE status='pending' AND expires_at < now` AND `conn.commit()`
  (:6020-6046).
So opening a connection is NOT data-side-effect-free: it mutates rows and commits a write
on every connect. This matters for the record's CONCURRENCY section ("no app-level lock,
delegated to SQLite") — connection-open is itself a write path that can contend the
write lock / hit `database is locked`. Under-specified contract + missed concurrency
surface.

### G4 — INFO: connect_db ignores the actual journal_mode returned by the PRAGMA
arclink_control.py:573 issues `PRAGMA journal_mode = {mode}` but never reads back the
result row. SQLite's `PRAGMA journal_mode` returns the mode actually set (e.g. WAL is
silently downgraded to non-WAL on `:memory:`/some network FS). A requested-vs-effective
mismatch is invisible. Broader than the record's LOW (which only covers the locked
exception swallow at :576-577).

---

## SEAM MISMATCHES (summary)
- Contract #4 (rowdict): evidence figure wrong (26 vs 6 actual rowdict importers). See R1.
- TRACE step 8 (events round-trip): reader cites point at wrong tables (rollouts/sessions,
  not arclink_events). See R2.
- Contract #2 (is_ip_in_cidrs): consumer end was deferred by the record; now verified, and
  an intra-piece second consumer (backend_client_allowed, :7628) was missed. See R8.

## RESIDUAL DISAGREEMENTS
- The "80 tables" headline conflates 79 owned CREATEs + 1 engine table (sqlite_sequence).
  Not load-bearing, but the substrate enumeration should say 24 owned + sqlite_sequence.
- Severities for R5/R6 (MEDIUM) accepted as defensible; G1 raised to MEDIUM because it
  touches a backend access-control allowlist.

## TRUSTWORTHINESS
Core claims (schema determinism, env precedence, fail-closed Docker gate, secret bypass,
unguarded casts, dead ALMANAC, no user_version) independently RE-CONFIRMED in code.
Two cite defects (R1, R2) and three missed gaps (G1-G3) mean the record is **trustworthy
in conclusion but imperfect in evidence** — use with the corrections above.
