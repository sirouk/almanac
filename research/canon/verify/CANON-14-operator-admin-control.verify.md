# CANON-14 — Operator & Admin Control — ADVERSARIAL VERIFICATION

Verifier: independent Opus 4.8 skeptic. Method: re-opened every load-bearing
file and both ends of every cross-piece contract; did not trust the record's
own citations. Code wins over comments/docstrings/names/prior docs.

Bottom line: the record is **substantially trustworthy** on its core
contract (fail-closed/identity-gated/audited control plane, atomic claim,
record-only rollout, provisioner re-check). I CONFIRMED the spine. But two of
its three MEDIUM risks are **mis-framed or mis-mechanized**, its top
"load-bearing security uncertainty" is **largely resolvable and partly false**,
and I found **two defects neither the record nor the prior docs mention**
(infinite stale-action re-queue with no failed/retry cap; `_redact_text` only
redacts `key=value` lines). Net: keep the record but correct risk #1 and #3
framing and add the two new gaps.

---

## A. REFUTATIONS / CONFIRMATIONS OF LOAD-BEARING CLAIMS

### A1. CONFIRMED — atomic claim is race-safe (worker)
`_claim_next_queued_action` (`python/arclink_action_worker.py:453-496`):
`BEGIN IMMEDIATE` (`:456`) → SELECT oldest queued (`:458-466`) →
`UPDATE ... WHERE action_id=? AND status='queued'` (`:472-483`) → guard
`cursor.rowcount != 1 → return None` (`:484-486`). Record's claim holds.
refuted=false.

### A2. CONFIRMED — rollout is record-only everywhere
`execute_arcpod_update_rollout_batch` (`python/arclink_rollout.py:623-834`):
every result/metadata carries `live_mutation_performed=False`
(`:732, :830`), `commands_run=[]` (`:678, :721, :824`), and the executor
contract validator forces `adapter∈{fake,local}` + `record_only` truthy
(`:837-852`). `materialize_*` requires `plan_kind=="arcpod_update_rollout"` /
`status=="ready"` / `mode=="dry_run"` (`:452-457`) and raises on mismatched
shape under the same idempotency key (`:494-497`). Worker forces
`record_only:True` regardless of intent metadata (`:1236`). Record's OUTPUT
CONTRACT and contracts #6 hold. refuted=false.

### A3. CONFIRMED — provisioner re-validates request_source (defense in depth)
`_operator_action_has_confirmed_source` requires
`request_source∈{"operator-raven"}` (`python/arclink_enrollment_provisioner.py:2292-2297`);
both upgrade (`:2334-2337`) and pin-upgrade (`:2451`) lanes
`_fail_unconfirmed_operator_action` (`:2300-2319`) else. Trace step 9's
`_run_brokered_host_upgrade` is reached via `_run_host_upgrade` →
`if _docker_mode(): return _run_brokered_host_upgrade(...)` (`:390-392`).
Record's contract #3 + trace hold. refuted=false.

### A4. CONFIRMED — producer-side queue validation (contract #2)
`queue_arclink_admin_action` enforces action-type allowlist (`dashboard:2341`),
worker-support gating (`:2343-2344`), target validity (`:2345-2352`), and
idempotency-key re-binding (`:2363-2372`) before INSERT `status='queued'`
(`:2376-2395`). Consumer reads `action_id/action_type/target_kind/target_id/
metadata_json` (`worker:688-692`). Both ends match. refuted=false.

### A5. CONFIRMED — `silenced` dismissed pin upgrades stay queueable (risk #2)
`_active_pin_upgrade_targets` filters **only** `applied_at IS NULL`
(`python/arclink_control.py:9596-9608`); it never inspects `silenced`, which
`dismiss_pin_upgrade_action` sets to 1 on `pin_upgrade_notifications`
(`:9686`). So `list_pin_upgrade_action_payloads(active_only=True)` still
surfaces a dismissed release; `_pending_pin_payloads*`
(`raven:1281-1290`) re-queue it via `/pin_upgrade`//`upgrade_sweep`. Risk #2
is CONFIRMED, correctly MEDIUM, correctly cited. refuted=false.

### A6. CONFIRMED — button nonce double-consume race (risk #4)
`consume_operator_button_nonce` is a non-transactional read-check-write:
SELECT (`raven:1381`), `if used_at: return ""` (`:1388`), then
`upsert_setting` (`:1394`) which is its own `INSERT…ON CONFLICT`+commit
(`control:2971-2980`). No `BEGIN IMMEDIATE` / `WHERE used_at=''` guard. Two
concurrent taps can both read empty. Correctly LOW (queue-layer idempotency
bounds impact). refuted=false.

### A7. REFUTED (framing) — "load-bearing security uncertainty" about
non-Telegram callers is largely resolvable and partly false.
The record (Adversarial Self-Check #1, OPEN-FOR-CODEX #1, RISK MEDIUM #1)
presents as an open question whether Discord/curator/web callers enforce the
approval code, and frames the risk as "any other caller that supplies a
forged/loose actor_id and the literal confirm queues real mutations." Reading
the actual call sites refutes the framing:
- There are exactly THREE external transports that call
  `dispatch_operator_raven_command` plus Raven's own recursion. NO web/API/
  hosted-api caller exists (`rg` over python/: only `arclink_telegram.py`,
  `arclink_curator_onboarding.py`, `arclink_curator_discord_onboarding.py`,
  `arclink_operator_raven.py`).
- ALL THREE enforce the code on typed `is_mutating` paths via the identical
  `operator_raven_command_is_mutating → strip_operator_approval_code` pattern:
  Telegram `arclink_telegram.py:1305-1322`; Telegram-curator
  `arclink_curator_onboarding.py:345-359`; Discord-curator
  `arclink_curator_discord_onboarding.py:310-324`.
- The `actor_id` is NOT forgeable by an arbitrary caller: every transport
  first passes a sender allowlist —
  `_operator_telegram_sender_allowed` (telegram:1293),
  `_operator_sender_allowed` (curator-onboarding:809-821),
  `_operator_discord_subject_allowed` (discord:298-304).
Conclusion: the "audit gap" the record left open is closed and the risk is
narrower than stated. CODE WINS over the record's open-uncertainty framing.

### A7b. NEW seam the record never named — the BUTTON-callback path is the
*actual* code-skipping path (and it is allowlist-gated, not code-gated).
Callback/`custom_id` handlers dispatch `arclink:/...` commands WITHOUT
`operator_raven_command_is_mutating`/`strip_operator_approval_code`:
`arclink_curator_onboarding.py:822-838` and
`arclink_curator_discord_onboarding.py:955-967` and
Telegram (`/upgrade_apply <nonce>` is not in MUTATING_COMMANDS so
`is_mutating` returns False at `arclink_telegram.py:1305`). For the designed
nonce buttons this is correct (nonce = second factor). BUT a *code-configured*
operator who is already on the allowlist could hand-craft
`callback_data="arclink:/upgrade confirm"` and skip the approval code, because
these paths only gate on `_operator_sender_allowed`/`_ensure_operator_channel`,
not on the code. This is the real (narrow) residual — the operator's OWN code
is bypassable by that operator via a crafted callback. The record gestured at
"non-Telegram callers" but never identified the callback dispatch as the
mechanism. NEW seam mismatch (severity LOW: requires an already-allowlisted
operator; no privilege escalation beyond what they can already type).

### A8. REFUTED (mechanism) — risk #3 says academy_apply is "gated by one env
var, not the executor adapter." FALSE: it IS gated by the executor adapter.
`stage_academy_apply` sets `writes_enabled=True` ONLY when FOUR conditions all
hold (`python/arclink_academy_programs.py:2938-2940`):
`live_adapter` (adapter∈{local,ssh,live}, i.e. NOT fake/disabled — `:2863-2864`)
AND `live_authorized` (`ARCLINK_ACADEMY_APPLY_LIVE` — worker:1085) AND
`review_ready` AND `trainer_review_ready`. `_materialize_academy_apply`
early-returns unless `writes_enabled` (`worker:2077-2078`). So the executor
adapter is part of the gate, contradicting the record's stated rationale. The
risk itself (a real on-disk write at `worker:2089-2206`) is genuine, but its
severity is OVER-stated and its cited mechanism ("one env var, not the executor
adapter") is wrong. CODE WINS. Down-calibrate to LOW/INFO with corrected
mechanism.

### A9. PARTIALLY REFUTED (cite) — one-agent invariant.
Record INPUT CONTRACT says the invariant is enforced by
`ensure_operator_agent_deployment:112-117`. That refusal is CONDITIONAL: it
only raises when the SETTING `operator_agent_deployment_id` is already pinned to
a *different, still-resolvable* deployment (`agent:111-117`). The real global
guarantee is the post-hoc `assert_single_operator_agent(conn)` called at the
public entry `ensure_operator_agent:378` (`agent:198-215`), which COUNTS
`operator_agent`-stamped rows and raises if `>1` — AFTER the second row was
already created/committed (it is detection, not prevention; no lock; TOCTOU on
the pinned-setting read at `:111` vs writes at `:153/171`). Invariant holds at
the public boundary but the record under-cited and over-claimed "refuses to
create." refuted=false on existence, but cite/strength is imprecise.

### A10. CONFIRMED — read handlers are allowlisted, no SQL injection.
Despite `f"…FROM {table}…"` interpolation, every count helper gates on a static
allowlist BEFORE interpolating and every call site passes a string literal:
`_count_by_status` (`raven:2030`), `_group_counts` (`:2053`),
`_count_rows` (`:2065`, plus a where-clause allowlist `:2067-2074`),
`_sum_int` (`:2090`), `_service_status_counts` (`:2108`). Record's
"allowlisted table set" claim holds. refuted=false.

### A11. CONFIRMED — ctl destructive ops + upgrade_check notify.
Typed `--yes==target` for `user purge-enrollment` (`ctl:2047-2048`) and
`agent deenroll` (`ctl:2065-2066`). `upgrade_check` writes
`arclink_upgrade_last_seen_sha`/`_relation` (`ctl:1818-1819`), gates operator +
user-agent notifications on `update_available`+new sha+no active deploy op
(`:1821-1827`), sets `_last_notified_sha` (`:1878`), always
`note_refresh_job("arclink-upgrade-check")` (`:1881-1889`). refuted=false.

### A12. CONFIRMED — executor seam (#5) and fleet seam (#4) both ends.
Executor result dataclasses expose `live/status/action/records/key_id`
(`arclink_executor.py:226-358`) matching the worker reads
(`worker:856,880,900,927`). `fleet_capacity_summary` emits
`total_hosts`/`active_hosts` ints (`arclink_fleet.py:356-357`) read by
`_handle_status` (`raven:468`). `admin_action_execution_readiness` emits
`queueable`/`executor_adapter`/`live_proof_gate` (`dashboard:243,250,248`)
read by status/pod_repair/rollout gates. refuted=false.

---

## B. NEW GAPS (neither record nor prior docs flagged)

### B1. MEDIUM — `recover_stale_actions` has NO failed-path and NO retry/attempt
cap; it re-queues forever (fail-open-ish infinite retry).
`python/arclink_action_worker.py:2242-2283`: the docstring says
"running actions older than threshold to queued **or failed**" (`:2247`) but
the code ALWAYS sets `_update_intent_status(... status="queued")` (`:2262`).
There is no max-attempt check, no transition to `failed`, no backoff. A stale
action whose executor consistently hangs >1h (e.g. a `restart`/`reprovision`
that wedges the adapter) is recovered to `queued`, re-claimed, hangs again,
recovered again — unbounded, accreting `arclink_action_attempts` rows forever
and never surfacing as a terminal failure to `/action_status`. Docstring drift
("or failed") + missing terminal/cap is a real defect. NOT mentioned anywhere.

### B2. LOW/INFO — `_redact_text` only redacts `key=value` secret lines.
`python/arclink_operator_raven.py:2415-2423`: redaction fires only when
`_SECRETISH_RE.search(line)` AND `"=" in line`. A secret on a line without `=`
(e.g. `Authorization: Bearer abc`, a bare token, or a JSON `"token": "abc"`
rendered with `:` not `=`) passes through unredacted. Operator Raven outputs
are structured count/status strings so live exposure is small, but the record
asserts outputs are "scrubbed" without this caveat. Minor over-claim.

### B3. INFO — host-upgrade dedupe ignores request_source.
`request_operator_action(action_kind="upgrade", ...)` non-`dedupe_by_target`
path dedupes via `get_active_operator_action(action_kind)` on
`(action_kind, status∈{pending,running})` ONLY (`control:8200-8216, 8288`). If a
NON-operator-raven caller had already queued an `upgrade` action, an
operator-raven `/upgrade confirm` would dedupe against it and return
`created=False` (so `mutation_performed=False`) — the operator's confirmed
request silently no-ops onto a possibly-unconfirmed pre-existing row. The
provisioner's `request_source` re-check then FAILS that pre-existing row closed,
so the net effect is safe, but the Raven-side "already queued" message is
misleading. Edge case, not a break.

---

## C. RISK RE-CALIBRATION VERDICT
- RISK MEDIUM #1 (approval code in transport): keep the OBSERVATION (code lives
  in transports, not Raven) but DOWNGRADE the framing — the caller set is closed
  (3 transports, all allowlist+code gated; no web route). True residual is the
  narrow callback-path-skips-code-for-an-already-allowlisted-operator (A7b),
  which is LOW.
- RISK MEDIUM #2 (dismissed pin upgrades queueable): CONFIRMED as written.
- RISK MEDIUM #3 (academy_apply live write): mechanism is WRONG ("one env var,
  not the executor adapter"); it IS adapter-gated + 3 more gates → recalibrate
  to LOW with corrected mechanism (A8).
- RISK LOW #4 (nonce double-consume): CONFIRMED.
- NEW: B1 stale-action infinite re-queue → MEDIUM.

## D. OVERALL VERDICT
TRUSTWORTHY WITH CORRECTIONS. The record's spine — clean
dry-run/actorless/confirm/queue contract, never-inline mutation, atomic claim,
record-only rollout, one-agent invariant, provisioner request_source re-check —
is independently re-confirmed in code. Corrections required: (1) risk #1 is
over-framed as an open uncertainty that is actually closed and largely false;
the real residual is the callback path (A7b); (2) risk #3's mechanism is
factually wrong (it IS executor-adapter gated); (3) add B1 (infinite stale
re-queue, no failed/cap) as a MEDIUM the record missed; (4) note B2/B3 minor
over-claims. None of these break the core contract.
