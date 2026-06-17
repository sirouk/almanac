# CANON-23 — Diagnostics / Health / Evidence / Notifications / Live Proof — RECONCILED

**Piece:** CANON-23 (seven modules: `arclink_secrets_regex`, `arclink_diagnostics`, `arclink_health_watch`,
`arclink_evidence`, `arclink_live_journey`, `arclink_live_runner`, `arclink_notification_delivery`)

**Codex (GPT-5.5 xhigh) sign-off:** OBJECT(6) — "Core record is trustworthy, but the broker seam can now be
closed and several delivery/proof edge failures need to be added to CANON."

**Claude adversarial verify:** TRUSTWORTHY WITH CORRECTIONS (4 corrections, 3 new gaps).

**Final adjudicator federation sign-off:** **BOTH-MODEL-AGREED.** Every material point reconciles to one
code-grounded truth. No standing disagreements remain. The reconciliation closes the one cross-piece
seam the original record left open (gateway-exec broker, §5B-40), folds in the four record corrections
(both models concur, two execution-proven), and adopts five Codex net-new findings (all re-verified true
in code by the adjudicator) plus two seam observations.

Method: I re-opened every disputed cite myself (Read / grep) and executed both redaction engines. Code
won over name/comment/prior claim throughout.

---

## RESOLUTION TABLE (point | winner | deciding cite)

| Point | Winner | Deciding cite (adjudicator-opened) |
|---|---|---|
| Gateway-exec broker contract end-to-end (record left "both-ends: no"; Codex REFINE closes it) | **codex** | Broker reads `deployment_id,prefix,project_name,payload,timeout_seconds` (`python/arclink_gateway_exec_broker.py:227-238`), operator variant `operator_stack,project_name,payload,timeout_seconds` (`:199-209`), routes POST only to `/v1/public-agent-bridge` (`:336`), auths `X-ArcLink-Gateway-Exec-Token` via `hmac.compare_digest` (`:51-54,339`), rejects raw `cmd`/`command` (`:197-198`). Exactly matches consumer send-side. Both-ends now = YES. |
| Album-leader concurrency: double-leader race? (Claude self-check #3 hypothesis; Codex REFINE) | **codex** | No double-leader race: each worker only processes a row it exclusively leased via `_claim_notification_for_delivery` (`python/arclink_notification_delivery.py:1702-1708,1902-1907`); leader = deterministic `min(undelivered id)` re-queried under `connect_db` (`:1527`). Real behavior: non-leader returns `PUBLIC_AGENT_BRIDGE_DEFERRED` (`:1529`) and the DEFERRED handler (`:1719-1721,1927-1928`) does NOT clear the lease — a deferred sibling stays not-due until lease expiry. INFO behavioral note, not a race. |
| `_REDACT_ENV_KEYS` is 15, not 18 (record error) | **both** (codex+claude) | Executed `len(arclink_evidence._REDACT_ENV_KEYS) == 15` (`python/arclink_evidence.py:44-53`). |
| "`EvidenceRecord.to_dict()` re-redacts every field" overstated | **both** (codex+claude) | `to_dict` redacts only 5 of 10 fields: provider_id, url, health_summary, detail, error (`python/arclink_evidence.py:118-126`); step_name/status/timestamp/commit_hash/hostname pass through. |
| Health-watch timer wording incomplete (record: "only OnUnitActiveSec=15m") | **both** (codex+claude) | File has BOTH `OnActiveSec=5m` AND `OnUnitActiveSec=15m` + `AccuracySec=1m` (`systemd/user/arclink-health-watch.timer:5-7`). "No OnBootSec" is technically true (it is OnActiveSec). |
| Bridge argv `python3` vs absolute paths (record shorthand) | **both** (codex+claude) | `PUBLIC_AGENT_BRIDGE_PYTHON="/opt/arclink/runtime/hermes-venv/bin/python3"`, `PUBLIC_AGENT_BRIDGE_SCRIPT="/home/arclink/arclink/python/arclink_public_agent_bridge.py"` (`python/arclink_notification_delivery.py:297-298`). Cosmetic. |
| CANON-05 adapter shapes (record: "both-ends: no"; verify+Codex CONFIRM hold) | **both** | Telegram `_request_json` unwraps `result` so `message_id` is top-level (`python/arclink_telegram.py:208-209`); Discord returns raw object, top-level `id` (`python/arclink_discord.py:70`). Consumer reads (`python/arclink_notification_delivery.py:1335,1380`) correct. Both-ends now = YES. |
| MEDIUM no-backoff on delivery failure (Codex CONFIRM) | **both** | `mark_notification_error` updates ONLY `delivery_error=error[:500]`, never `attempt_count`/`next_attempt_at` (`python/arclink_control.py:9403-9408`); due gate reads `next_attempt_at` (`python/arclink_notification_delivery.py:313-318`) → permanent no-op on error path; delivery timer 5s (`systemd/user/arclink-notification-delivery.timer:5`). |
| MEDIUM evidence DB unwired (Codex CONFIRM) | **both** | Zero callers of `store_evidence_run`/`get_evidence_run`/`list_evidence_runs`/`latest_evidence_status` in python/bin/web outside the module/tests (grep empty); `run_live_proof` writes only local JSON (`python/arclink_live_runner.py:743-748`). |
| MEDIUM divergent redaction engines (Codex CONFIRM, execution-proven) | **both** | Executed both engines: `arclink_evidence.redact_text` leaks anthropic/telegram/discord/jwt/chutes/github/openai/pem (catches only stripe_live); shared `redact_secret_material` catches all but bare-header PEM. Error/detail strings route to weak `redact_text` because key not sensitive (`python/arclink_evidence.py:84-88`). |
| MEDIUM Phase-4 global `os.environ` mutation (Codex CONFIRM) | **both** | `run_live_proof` does `os.environ.update(source)` then restores in finally (`python/arclink_live_runner.py:705-711`) because journey checks read process globals (`python/arclink_live_journey.py:58-61`). Not thread-safe. |
| LOW qmd clock-skew swallow (Codex CONFIRM) | **both** | `age = max(0, int(current) - pending_since)` clamps future epoch to 0 → reports ok (`python/arclink_diagnostics.py:176`). |
| INFO `run_diagnostics(live=)` dead param (Codex CONFIRM) | **both** | Body never branches on `live` (`python/arclink_diagnostics.py:202-213`). |
| S8 bot-token disk persistence (Codex CONFIRM) | **codex** | Detached job body serializes `"payload": payload` incl `"bot_token"` (`python/arclink_notification_delivery.py:676,989`) / `gateway_exec_request` (`:976`) to a 0600 O_EXCL file, unlinked on worker read (`:1010`). Record's "secrets never in argv" holds; nuance: transient 0600 disk file in detached path. INFO/LOW. |
| Pod-message nonatomic seam (Codex CONFIRM) | **codex** | `arclink_pod_comms.py` commits message+event at `:306`, then `queue_notification` commits separately at `python/arclink_control.py:8071`; crash between loses the notification. Cross-piece (pod_comms producer); LOW durability edge on the shared notification helper CANON-23 consumes. |
| Dashboard vs runner `CLOUDFLARE_API_TOKEN_REF` divergence (Codex CONFIRM + Claude verify NEW) | **both** | Dashboard blocker does plain `env_source.get(key,"")` (`python/arclink_dashboard.py:548`); runner honors `_REF` alternate (`python/arclink_live_runner.py:85-90`). Same `required_env` contract, two interpretations. Net-new LOW. |

---

## CONFIRMED CODEX NEW FINDINGS (re-verified true in code → net-new federation risks)

1. **MEDIUM — Notification due-filtering happens AFTER `LIMIT`, causing head-of-line blocking.**
   Both the fast path (`run_public_agent_turns_once`) and the periodic path select
   `... WHERE delivered_at IS NULL AND target_kind=... ORDER BY id ASC LIMIT ?` with NO `next_attempt_at`
   predicate in SQL, then filter `_notification_due_now(row)` in Python and `continue` on not-due
   (`python/arclink_notification_delivery.py:1686-1701`; periodic `python/arclink_control.py:9423-9439`
   + `python/arclink_notification_delivery.py:1898-1900`). The hosted-API webhook fast path calls with
   `limit=1` (`python/arclink_hosted_api.py:2832`), so a single not-due (leased) lowest-id
   public-agent-turn row occupies the only slot and hides ALL newer due turns for that channel/target.
   **CONFIRMED.**

2. **MEDIUM — `run_live_proof` returns `dry_run_ready`/exit 0 even when readiness or diagnostics failed.**
   The status ladder branches only on journey `all_missing`, `live_requested`, `effective_runners`
   (`python/arclink_live_runner.py:692-699`); it never reads `readiness.ready` or `diagnostics.all_ok`
   (computed at `:670,678` but only carried into the result dict). Exit code is 0 for `dry_run_ready`
   (`:753-754`). So with Docker down / providers missing but journey `required_env` present, the CLI
   exits 0 and reports `dry_run_ready`. A CI gate on exit code gets a false green. **CONFIRMED.**
   (Severity note: `dry_run_ready` honestly means "creds present, ready to run live"; the defect is the
   exit-0 signal-loss for gating, which is the MEDIUM.)

3. **LOW — Default evidence artifact write is unguarded; an unwritable `evidence/` crashes the CLI
   before it prints.** `out_dir.mkdir(...)` + `artifact_file.write_text(...)` have no try/except
   (`python/arclink_live_runner.py:743-748`) and run inside `run_live_proof`, which `main` calls
   (`:804`) BEFORE any print (`:811-825`). For `dry_run_ready` the write happens even with no
   `--artifact-dir` (`:743`). An OSError aborts before result/JSON is emitted. **CONFIRMED.**

4. **LOW — Health-watch forwards raw `[fail]`/`[warn]`/stderr/command-error lines to operator
   notifications without shared redaction.** `_health_lines` extracts raw stdout lines (`:88-98`),
   raw stderr appended (`:220-222`), `command_error` embeds `str(exc)` (`:210`) → `problem_lines` →
   `_clip_lines` (whitespace/length only, no redaction, `:101-115`) → `_format_problem_message` →
   `queue_notification(target_kind="operator")` (`:248-253`). No `redact_secret_material` anywhere on
   this path; a secret printed by `bin/health.sh` reaches an operator Telegram/Discord verbatim.
   Defense-in-depth gap (the evidence/diagnostics paths have the backstop; this one doesn't).
   **CONFIRMED.**

5. **LOW — Token-bearing detached bridge job file is not unlinked on the spawn/log-open error path.**
   After `_write_public_agent_bridge_job` writes the 0600 file (`python/arclink_notification_delivery.py:1185`),
   if `log_path.parent.mkdir`/`log_path.open` or `Popen` raises, the handler returns an error WITHOUT
   unlinking (`:1213-1214`); an immediate-nonzero worker exit also returns without unlink (`:1210-1212`).
   The job file is only unlinked when the worker reads it (`:1005-1012`). So a token-bearing 0600 file
   can persist if the worker never starts/reads. **CONFIRMED.**

(Codex S8 bot-token-disk and the pod-message nonatomic seam are recorded as confirmed INFO/LOW
observations in the resolution table above; they are durability/defense-in-depth notes, not net-new
elevated risks. Codex's two REFINEs — broker contract closed, album non-race — are adopted as shown.)

## REJECTED CODEX NEW FINDINGS

None. Every Codex finding and refinement re-verified true in code.

---

## SEVERITY CHANGES (applied only where code supports it)

| Risk | From | To | Cite |
|---|---|---|---|
| Notification head-of-line blocking (Codex new #1) | (absent in record) | **MEDIUM** | `python/arclink_notification_delivery.py:1686-1701`, `python/arclink_hosted_api.py:2832` |
| Live-proof exit-0 ignores readiness/diagnostics (Codex new #2) | (absent in record) | **MEDIUM** | `python/arclink_live_runner.py:692-699,751-754` |
| Unguarded default evidence write crashes CLI (Codex new #3) | (absent) | **LOW** | `python/arclink_live_runner.py:743-748,804` |
| Health-watch unredacted operator forwarding (Codex new #4) | (absent) | **LOW** | `python/arclink_health_watch.py:88-98,220-222,248-253` |
| Detached bridge job not unlinked on error path (Codex new #5) | (absent) | **LOW** | `python/arclink_notification_delivery.py:1185,1213-1214` |
| Dashboard/runner `_REF` divergence | (absent) | **LOW** | `python/arclink_dashboard.py:548`, `python/arclink_live_runner.py:85-90` |
| Pod-message non-atomic notification queue | (absent) | **LOW** | `python/arclink_pod_comms.py:306`, `python/arclink_control.py:8071` |

No EXISTING record severity was raised or lowered — the four MEDIUMs, two LOWs, and INFO in the original
record all re-confirmed at their stated severity. The above are net-new additions.

Record FACTUAL corrections folded in (not severity changes): `_REDACT_ENV_KEYS`=15 (not 18); `to_dict`
redacts 5/10 fields (not "every field"); health-watch timer = `OnActiveSec=5m`+`OnUnitActiveSec=15m`;
bridge argv uses absolute Hermes-venv python + script paths; CANON-05 and CANON-12 both-ends now = YES.

---

## STANDING DISAGREEMENTS

None. Every material point was settled from code by the adjudicator.

---

## FINAL BOTH-MODEL VERDICT

CANON-23 provably does its core job — dry-run live proof, presence-only diagnostics that emit credential
NAMES never values, edge-triggered de-duplicated health alerting, and outbox delivery — and it is
secret-safe on the happy path (bridge secrets travel via stdin/header behind an exact-shape allowlist +
symlink/path-within preflight, validated three times). Both models agree on the four standing MEDIUM
weaknesses: evidence-ledger DB persistence is built but entirely unwired (largest delta vs the
"operator-visible evidence" vision); delivery failures have no backoff and hot-loop external APIs every 5s;
redaction is split across two engines of unequal coverage (execution-proven leak via error/detail
strings); and the runner mutates process-global `os.environ` mid-run. Reconciliation closes the
gateway-exec broker seam (now both-ends-verified) and resolves the album-leader race hypothesis (no race;
a deferred sibling's lease merely persists until expiry). It adds five net-new federation risks from
Codex — two MEDIUM (notification head-of-line blocking under `limit=1`; live-proof exit-0 that ignores
host readiness and diagnostics) and three LOW (unguarded evidence write, unredacted health-watch operator
forwarding, token-bearing job file un-unlinked on error path) — plus two LOW seam/durability notes
(dashboard/runner `_REF` divergence; pod-message non-atomic notification queue). The `external` journey
remains a catalog with no runners and `run_diagnostics(live=)` is a dead parameter; neither may be read as
"live provider proof exists." **FEDERATION SIGN-OFF: BOTH-MODEL-AGREED.**
