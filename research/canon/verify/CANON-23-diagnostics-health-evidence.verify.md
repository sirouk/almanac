# CANON-23 Adversarial Verification — Diagnostics / Health / Evidence / Notifications / Live Proof

Adversarial skeptic pass. Method: re-opened every target file and the cited producer/consumer
ends; re-derived each load-bearing claim at path:line; executed the redaction engines to test
the secret-coverage claim. Code wins over comment/name/prior-doc.

## VERDICT (one line)
**TRUSTWORTHY WITH CORRECTIONS.** The five load-bearing strengths and all four MEDIUM risks
are independently re-confirmed in code (two with executed proof). But the record carries several
factual/precision errors — a wrong key-count (`_REDACT_ENV_KEYS` is 15, not 18), an overstated
"re-redacts every field" claim (only 5 of 10 fields are redacted), an incomplete systemd-timer
read (it omits `OnActiveSec=5m`), and a mis-described bridge argv (`/opt/.../python3`, not bare
`python3`). None of these reverse the verdict; the core "provably does its job, secret-safe on the
happy path" holds. I also found 3 gaps neither the record nor prior docs name.

---

## A. CROSS-PIECE CONTRACTS RE-ATTACKED

### -> CANON-08 host_readiness — CONFIRMED (record correct)
`ReadinessResult.to_dict` emits exactly `{"ready":bool,"checks":[{name,ok,detail}...]}`
(arclink_host_readiness.py:57-61; `ReadinessCheck` fields at :46-49). Consumer reads `.to_dict()`
at arclink_live_runner.py:670,762. Both ends match. record both-ends=yes is correct.

### -> CANON-01 control schema/helpers — CONFIRMED (record correct)
- `queue_notification(conn,*,target_kind,target_id,channel_kind,message,extra=None)->int`,
  INSERT into notification_outbox(target_kind,target_id,channel_kind,message,extra_json,created_at)
  (arclink_control.py:8055-8072). Health-watch consumer calls with exactly those keys
  (arclink_health_watch.py:248-254). Match.
- `arclink_evidence_runs` 13-col schema + `CHECK (status IN ('pending','skipped','passed','failed','blocked'))`
  (arclink_control.py:2523-2537). `store_evidence_run` INSERT lists the same 13 columns in order
  (arclink_evidence.py:292-296). `_evidence_status_from_ledger` collapses `blocked_*`->`blocked`
  before write (arclink_evidence.py:255), so it can never violate the CHECK. `EVIDENCE_STATUSES`
  (arclink_evidence.py:248) == `ARCLINK_EVIDENCE_RUN_STATUSES` (arclink_control.py:3212). Match.
- `fetch_undelivered_notifications` SELECTs attempt_count/last_attempt_at/next_attempt_at
  (arclink_control.py:9423-9426); `run_once` consumes the rows (arclink_notification_delivery.py:1890-1898).
  Match.

### -> CANON-19 dashboard — CONFIRMED, but record MISSED a consumer-side inconsistency
Producers consumed at arclink_dashboard.py:541-548 exactly as the record says.
NEW: the dashboard's own blocker computation at :548 does a PLAIN `env_source.get(key,"")` check
and does NOT honor the `CLOUDFLARE_API_TOKEN_REF` alternate that the runner/journey honor
(`_required_env_present` arclink_live_runner.py:88-90; `_env_present` arclink_live_journey.py:59-61).
So the same `step.required_env` contract is interpreted two different ways across consumers: a
deployment using `CLOUDFLARE_API_TOKEN_REF` is "ready" to the runner but shows a blocker on the
dashboard. Low severity (cosmetic/operator-confusion), but it is a real seam interpretation drift
the record did not flag.

### -> CANON-02 hosted API webhook fast path — CONFIRMED (record correct)
`run_public_agent_turns_once(Config.from_env(), channel_kind=, target_id=, limit=1)` called at
arclink_hosted_api.py:2828-2833; consumer reads `summary.get("delivered"/"errors")` which exist in
the returned dict (arclink_notification_delivery.py:1666-1673). Match.

### -> CANON-16 llm_router — CONFIRMED (record correct)
`load_router_config` (arclink_llm_router.py:157), `create_app(config, upstream_transport=)` (:1801).
The `arclink_router` response metadata with `primary_model/upstream_model/fallback_used` is built at
:702-704; proof runner reads `router_meta.get("fallback_used"/"upstream_model"/"primary_model")`
(arclink_live_runner.py:606-628). Producer keys match consumer reads. record both-ends=yes correct.

### -> CANON-05 telegram/discord adapters — record said "both-ends NOT verified"; I VERIFIED BOTH ENDS, contract HOLDS
The record flagged this for Codex as unverified. I re-read producers:
- Telegram `telegram_send_message` -> `_request_json` UNWRAPS `result` and returns it
  (arclink_telegram.py:208-209). So the returned dict has `message_id` at top level. Consumer
  `sent.get("message_id")` (arclink_notification_delivery.py:1335) is CORRECT.
- Discord `discord_send_message`/`discord_create_dm_channel` -> `_request_json` returns the raw
  message/channel object (arclink_discord.py:70,105-112). Discord top-level field is `id`. Consumer
  `sent.get("id") or sent.get("message_id")` (:1380) and `dm.get("id")` (:1371) are CORRECT.
This is a CONFIRMATION that resolves the record's open item — the record's caution was unnecessary
but not wrong.

### -> CANON-12 gateway exec broker — genuinely cross-piece, correctly left "no"
Consumer side re-verified (`_gateway_exec_broker_request` body keys deployment_id/prefix/project_name/
payload/timeout_seconds at arclink_notification_delivery.py:342-348; operator variant operator_stack/
project_name/payload/timeout_seconds at :357-362; header `X-ArcLink-Gateway-Exec-Token` at :385,301).
Broker endpoint is owned by CANON-12 and not re-read here. record's both-ends=no is honest.

---

## B. FAIL-CLOSED / VALIDATED / SAFE CLAIMS RE-ATTACKED

### "Diagnostics never leak secret values" — CONFIRMED
`_credential_check` only emits `"present"`/`"missing: <ENVVAR>"` (arclink_diagnostics.py:44-51);
qmd check emits counts/ages/path only (:151-188). No branch returns a value. Holds.

### "Bridge secrets via stdin/header, never argv; exact-shape allowlist" — CONFIRMED, with defense-in-depth
`_validate_public_agent_bridge_cmd` pins len 6 or 13 and exact positional tokens
(arclink_notification_delivery.py:490-509), regex-checks container/project (:299-300), and runs the
symlink/dir/path-within preflight for the 13-shape (:459-476). Validation is enforced THREE times:
at request build (:781), at job write (:981), and re-validated at exec time (:1078) — the on-disk job
file is treated as data, not authority. Payload (incl `bot_token`) travels via `input=`/stdin
(:1107,1235) and broker token via header (:385). Holds.

### Substring container allowlist — record LOW is correctly calibrated
`"hermes-gateway" in container_name` (:494) is a substring test, but the container name is NOT
operator-free-text: it comes from a `docker ps` label query (`_deployment_service_container` :530-552)
and must also pass `PUBLIC_AGENT_BRIDGE_CONTAINER_RE.fullmatch` (:492) and the `{expected_project}-/_`
prefix gate (:496-499) where `expected_project` is module-derived from deployment_id
(`_compose_project_name` :321-323). Practical exploitability is low. record LOW is right.

### Health-watch fingerprint de-dup + deploy-window suppression — CONFIRMED
Skip when `active_deploy_operation` (arclink_health_watch.py:179-192); edge-trigger only when
status in {fail,warn} AND fingerprint changed, or recovery ok-after-fail (:246-267);
sha256[:16] fingerprint (:118-120). Holds.

---

## C. CONFIRMED RISKS (re-derived, some with executed proof)

### MEDIUM — No retry backoff on delivery failures — CONFIRMED
`mark_notification_error` updates ONLY `delivery_error` (truncated to error[:500]); it does NOT touch
`attempt_count` or `next_attempt_at` (arclink_control.py:9403-9408). The main loop DOES gate on
`_notification_due_now(row)` (arclink_notification_delivery.py:1899) and that helper reads
`next_attempt_at` (:313-318) — but since the error path never sets it, the gate is a permanent no-op
for operator/public-bot-user rows. Only public-agent-turn rows get a lease via
`_claim_notification_for_delivery` (:1641, the sole writer of next_attempt_at). With the delivery
timer at OnBootSec=5s + OnUnitActiveSec=5s (systemd/user/arclink-notification-delivery.timer), a
persistently failing operator row hot-loops the external API every 5s. record framing is correct;
I add the precise mechanism: the due-now gate exists but is toothless on the error path.

### MEDIUM — Evidence ledger DB layer is unwired — CONFIRMED by zero-caller grep
`store_evidence_run`/`get_evidence_run`/`list_evidence_runs`/`latest_evidence_status` have ZERO
callers in python/, bin/, web/ outside tests/test_arclink_evidence.py. `run_live_proof` writes only a
local JSON file (arclink_live_runner.py:743-748) and never imports/calls the DAL (its only
`import arclink_control` is local to the router proof at :510). The "operator-visible evidence state"
is not real. Holds.

### MEDIUM — Two divergent redaction engines — CONFIRMED WITH EXECUTED PROOF
`arclink_evidence` has its OWN `_SECRET_PATTERNS` (arclink_evidence.py:26-31) and does NOT import
arclink_secrets_regex. I executed both engines on 9 secret families. `arclink_evidence.redact_text`
(the engine applied to non-sensitive-keyed text values such as `error`, `url`, `health_summary`, and
`detail` inner strings) LEAKS: anthropic sk-ant, telegram bot token, JWT, discord bot token, PEM
private key, chutes cpk_, github ghp_, openai sk-proj. Only Stripe `sk_live_` is caught by both. The
shared `redact_secret_material` catches all 9. Concrete escape path the record under-specified: a
journey runner exception whose message embeds one of those families -> `step.error=str(exc)`
(arclink_live_journey.py:387) -> `EvidenceRecord.error` -> `redact_any(error,key="error")` routes to
`redact_text` (the weak engine, because "error" is not a sensitive key per `_is_sensitive_key`
:63-65) -> survives into `evidence/<run_id>.json`. MEDIUM is defensible (requires a secret in an
error/detail string), but the leak is real and demonstrable, not hypothetical.

### MEDIUM — Phase 4 mutates global os.environ — CONFIRMED
`evaluate_journey`/`missing_credentials` read `os.environ` directly (arclink_live_journey.py:58-71),
NOT the passed env, so `run_live_proof` does `os.environ.update(source)` then restores in finally
(arclink_live_runner.py:705-711). Not thread-safe; a concurrent thread observes injected creds during
a live run. Holds.

### LOW — qmd clock-skew swallow — CONFIRMED
`age = max(0, int(current) - pending_since)` (arclink_diagnostics.py:176); a future `pending_since`
epoch clamps age to 0 -> `stale=False` -> reports ok=True (:177-185). Holds.

### INFO — run_diagnostics(live=) dead param — CONFIRMED
Body never branches on `live` (arclink_diagnostics.py:202-213); docstring admits "future" (:200);
CLI `--live` only passes it through (:221,224). Holds.

---

## D. REFUTATIONS / CORRECTIONS OF THE RECORD (record is wrong or imprecise here)

1. **`_REDACT_ENV_KEYS` count is 15, not 18.** Record TOUCH POINTS line 38 says "18 keys".
   Executed `len(arclink_evidence._REDACT_ENV_KEYS) == 15` (arclink_evidence.py:44-53). Factual error.

2. **"`EvidenceRecord.to_dict()` re-redacts every field at serialize time" is OVERSTATED.**
   Record OUTPUT CONTRACT line 32 and CODE-PATH TRACE step 9 ("re-redacts every field"). Actual
   `to_dict` redacts only 5 of 10 fields: provider_id, url, health_summary, detail, error
   (arclink_evidence.py:121-125). NOT redacted: step_name, status, timestamp, commit_hash, hostname.
   No active leak today (hostname always "", commit_hash is a short git hash, step_name is a fixed
   catalog name), but the blanket claim is false and could mask a future leak if hostname/step_name
   ever carry user data.

3. **Health-watch timer description is INCOMPLETE.** Record CODE-vs-DOC line 71 says the timer "has
   only `OnUnitActiveSec=15m`, no `OnBootSec`." The actual file
   (systemd/user/arclink-health-watch.timer) has BOTH `OnActiveSec=5m` AND `OnUnitActiveSec=15m`
   (plus AccuracySec=1m). The "no OnBootSec" sub-claim is technically true (it is OnActiveSec), but
   "only OnUnitActiveSec=15m" omits the 5-minute initial trigger. Refuted as incomplete.

4. **Bridge argv described as `python3`; actual is an absolute interpreter path.** Record TOUCH POINTS
   line 42 writes the allowlisted shapes as `docker exec -i <ctr> python3 bridge`. Actual constants:
   `PUBLIC_AGENT_BRIDGE_PYTHON = "/opt/arclink/runtime/hermes-venv/bin/python3"` and
   `PUBLIC_AGENT_BRIDGE_SCRIPT = "/home/arclink/arclink/python/arclink_public_agent_bridge.py"`
   (arclink_notification_delivery.py:297-298). Cosmetic, but the description is not the real argv.

5. **CANON-05 "both-ends-verified: no" is over-conservative.** See section A — I verified both ends;
   the contract holds. Not a defect in the code; a defect in the record's confidence rating.

---

## E. NEW GAPS (neither the record nor prior docs mention)

1. **LOW/INFO — Detached public-agent-turn lease is ~2h, so a transient bridge error locks a user's
   agent turn for up to 2 hours.** `_public_agent_turn_lease_seconds` returns
   `_public_agent_bridge_max_seconds()+300` = 7500s when detached (default)
   (arclink_notification_delivery.py:943-946,939-940). On bridge error the detached worker calls
   `mark_notification_error` (:1064,1128) which does NOT clear `next_attempt_at`, so the row stays
   un-due until the 7500s lease expires. Net: operator rows hot-loop every 5s (no backoff) while
   public-agent-turn rows are effectively rate-limited to once per ~2h even for a transient failure.
   The asymmetry is the opposite extreme on each side and neither is a tuned backoff.

2. **LOW — Dashboard vs runner disagree on `CLOUDFLARE_API_TOKEN` presence** (detailed in section A,
   CANON-19): two consumers of the same `step.required_env` contract apply different alternate-env
   logic; the `_REF` form is honored by the runner/journey but not by the dashboard blocker check
   (arclink_dashboard.py:548).

3. **INFO — `mark_notification_delivered` then `mark_notification_error` on absorbed album siblings.**
   In `_absorb_telegram_album_siblings` the leader calls `mark_notification_delivered(absorbed_id)`
   immediately followed by `mark_notification_error(absorbed_id, "absorbed_into_album_leader:...")`
   (arclink_notification_delivery.py:1546-1547). `mark_delivered` sets delivery_error=NULL,
   `mark_error` then re-populates delivery_error on an already-delivered row. Harmless (delivered_at
   wins for due/undelivered filters) but the row ends up "delivered with an error string" — a
   confusing audit artifact, not a correctness bug.

---

## F. CLAIMS RE-CONFIRMED TRUE (record correct, no change)
- argparse `--journey` choices reject bad values with exit 2 (arclink_live_runner.py:798);
  `--public-agent-bridge-worker` is argparse.SUPPRESS (:1951) and re-enters as the bridge worker (:1957).
- Phase 6 write condition (artifact_dir given OR dry_run_ready/live_executed OR blocked-while-live)
  at :743; status decision ladder at :692-699; exit-code ladder at :751-756. All correct.
- bridge job files O_EXCL+0o600, atomic os.replace, nonce filename (:994-1001); job dir
  `<STATE_DIR>/docker/jobs/public-agent-bridge-jobs/` (:949-957). Correct.
- Runner never persists to arclink_evidence_runs; only local JSON. Correct.

## Overall trust assessment
The record's verdict and all five load-bearing strengths survive adversarial re-verification, and its
four MEDIUM risks are real (two now proven by execution / zero-caller grep). Deduct trust only for the
factual slips in section D (the 15-vs-18 count, the "every field redacted" overstatement, the timer
omission, and the python3-vs-abspath argv). None alter the security posture or the verdict. The record
is a reliable basis for the canon, conditional on those four corrections being folded in.
