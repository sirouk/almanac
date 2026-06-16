# CANON-08 — Provisioning & Enrollment — ADVERSARIAL VERIFY

Verifier: independent Opus 4.8 skeptic. Method: re-opened all seven tracked files + the two
named adjacent ends (`arclink_operator_upgrade_broker.py`, `arclink_hosted_api.py`,
`arclink_control.py`) and re-checked every load-bearing citation at path:line. Default to
refuted-when-uncertain; refuted=false only where I independently re-confirmed in code.

## VERDICT
**The record is largely TRUSTWORTHY and unusually careful** — its citations land, its cross-piece
HMAC contract is genuinely byte-verified at both ends, and its two headline weaknesses (non-Docker
pin-upgrade allowlist gap, UnicodeDecodeError escape) are real and correctly located. I confirmed
~all of its load-bearing claims. HOWEVER the record's VERDICT **overstates the fleet audit chain as
"cryptographically sound … queues a P0 on tamper"** — I found a real unkeyed-SHA256 downgrade in
`verify_fleet_audit_chain` that lets a DB-write attacker re-forge an entire inventory's chain with
zero errors and no P0. That is a NEW MEDIUM gap neither the record nor prior docs mention. I also
found two new LOW/INFO silent-no-op gaps (chown swallow in agent_access; always-pass ingress check
in host_readiness). Net: the piece does its job, but the audit-chain "soundness" claim must be
demoted from MEDIUM-confidence to a known downgrade weakness.

---

## A. CROSS-PIECE CONTRACTS RE-ATTACKED

### Contract #1 — Dispatcher → operator-upgrade-broker (HMAC POST). CONFIRMED both ends.
- Signed string client `f"{timestamp}\n{nonce}\n{body_hash}"` (enrollment:318) == broker rebuild
  `f"{timestamp}\n{nonce}\n{body_hash}"` over `sha256(raw_body)` (broker:707-712). MATCH.
- Token header `X-ArcLink-Operator-Upgrade-Broker-Token` (broker:41) both read same env
  `ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN` (enrollment:294, broker `_broker_token`/:687). MATCH.
- TTL 300s (broker:37,:701); nonce regex `[A-Za-z0-9_.~+/=-]{16,160}` (broker:703). I executed
  `secrets.token_urlsafe(18)` → 24 chars, alphabet ⊂ regex. MATCH.
- Single-use nonce (broker:705,:715), MAX_REQUEST_BYTES 16384 (broker:36,:742), operation allowlist
  `{run_operator_upgrade,run_pin_upgrade}` (broker:642-650). Response `{"ok":true,"result":dict}`
  (broker:759) == client gate (enrollment:344-348). MATCH.
- EXTRA verified by me: broker returns `{"returncode": int(...)}` on ALL success branches
  (broker:360 host-runner, :510 upgrade, :552/:557/:565 pin), so the client's
  `int(result.get("returncode"))` default-2 coercion (enrollment:384) never silently mis-fires.
  NOT refuted.

### Contract #2 — Pin install_items: control.py → dispatcher → broker. CONFIRMED + RECORD UNDERSTATES.
- Producer `get_pin_upgrade_action_payload` (control:9550-9576) re-normalizes via
  `_normalize_pin_upgrade_item` and returns None on bad items. Dispatcher forwards only
  `payload.get("install_items")` verbatim (enrollment:458,:462-463). Broker
  `_normalized_pin_upgrade_item` (broker:265-273) re-validates `component ∈ ALLOWED_PIN_COMPONENTS`
  (broker:267-268) AND drops field/current/throttle_target (returns only component/kind/target,
  broker:273). MATCH for the Docker path.
- **NEW EVIDENCE strengthening the record's MEDIUM risk:** the PRODUCER
  `_normalize_pin_upgrade_item` (control:9502-9515) enforces NO component allowlist — it accepts any
  non-empty `component`+`target`. So on the bare-metal path neither producer NOR
  `_pin_upgrade_command_args` (enrollment:429-448) gates the component; `ALLOWED_PIN_COMPONENTS`
  lives ONLY in the Docker broker (broker:48,:267). The record's MEDIUM is correctly calibrated,
  arguably conservative. NOT refuted.

### Contract #3 — hosted_api → consume_fleet_enrollment. CONFIRMED both ends.
- Producer `_handle_fleet_enrollment_callback` reads Bearer (hosted_api:2035-2037), passes
  `token=token.strip()` (:2042), `payload=body` (:2043), `secret=config.fleet_enrollment_secret`
  (:2044), `source_ip` from `x-real-ip`/`x-forwarded-for` (:2046). Error → 401 (:2048-2049),
  success → 201 `{"worker": result}` (:2050). Consumer reads `body["machine_fingerprint"]`/
  `["hostname"]` (fleet:536-537). OpenAPI `required=["hostname","machine_fingerprint"]`
  (hosted_api:3185). MATCH.
- **NEW INFO gap (record omits):** `source_ip` derives from client-controllable headers and is
  stored into `metadata["source_ip"]` (fleet:632-633). It is audit-only (not used for auth), but
  it is attacker-spoofable audit data — worth a TOUCH-POINTS note.

### Contract #4 — Intent renderer → executor. CONFIRMED producer side; executor request construction verified.
- `render_arclink_provisioning_intent` called at worker:1149 and :1169; `intent["dns"]` fed into
  `CloudflareDnsApplyRequest(...dns=intent["dns"]...)` (worker:1210-1214). `_reload_apply_ready_deployment`
  re-checked at :1181,:1198,:1205,:1209 (the "×8 re-check" claim holds in spirit). NOT refuted.

### Contract #5 — build_arclink_ssh_access_record → intent. CONFIRMED (self-contained).
- access:28-57 rejects raw_http/ssh_over_http (:37-38), http(s) hostnames (:39-40), unknown strategy
  (:41-42), empty user/host (:43-44). NOT refuted.

### Contract #6 — operator_actions confirmed-source. CONFIRMED consumer; producer NOT re-opened.
- `_operator_action_has_confirmed_source` requires `request_source.lower() in {"operator-raven"}`
  (enrollment:2292,:2295-2297). Gate enforced in both `_run_pending_operator_actions` (:2334) and
  `_run_pending_pin_upgrade_actions` (:2451). Consumer end solid. The record itself flags (Open
  item) that EVERY writer of `request_source='operator-raven'` (CANON-14) must be audited — I did
  NOT enumerate them, so the gate's strength remains contingent. NOT refuted, but contingent.

---

## B. FAIL-CLOSED / VALIDATED / SAFE CLAIMS RE-ATTACKED

### "validate_no_plaintext_secrets is the final gate." CONFIRMED (with the record's own caveat).
- Runs at provisioning:1781 before return. Logic (provisioning:1398-1421): for secret-ref paths,
  passes on run-secret path / compose-secret-source / valid secret-ref, raises otherwise; for ALL
  paths, raises if `contains_secret_material`. So non-secret-ref paths are gated ONLY by the CANON-23
  regex `contains_secret_material`. Record self-check #1 already concedes this. NOT refuted; the
  dependency on CANON-23 regexes is real (INFO in record, accurate).

### "Enrollment consume is TOCTOU-safe via rowcount==1." CONFIRMED — and I PROVED the open question.
- Guard: `UPDATE … WHERE status='pending'` then `rowcount != 1 → raise` (fleet:689-698).
- I PROVED the record's unproven self-check #2: each hosted_api request opens its OWN connection
  (`connect_db_fn`, hosted_api:4319) and ALWAYS closes it in `finally` (hosted_api:4332-4334). On
  the losing race, the consume UPDATE finds status `consumed` → rowcount 0 → raise (fleet:698);
  `ArcLinkFleetEnrollmentError` is caught (hosted_api:2048) WITHOUT an explicit rollback, but the
  loser's earlier `register_inventory_machine` INSERTs are uncommitted (commit only at fleet:759)
  and are rolled back when `request_conn.close()` runs. SQLite serializes the two writers via
  `busy_timeout=15000` (control:567). Net: clean single-winner, no orphan inventory row. **TOCTOU
  claim HOLDS — NOT refuted.**

### "Host preflight is no-mutation." CONFIRMED, but record MISSED a tautology.
- `run_readiness` ready roll-up excludes `secret_*` checks (host_readiness:183) — confirmed; record's
  INFO is accurate.
- **NEW INFO gap:** `check_ingress_strategy` returns `ok=True` on BOTH branches (host_readiness:159
  cloudflare, :161 traefik_local). It can never fail the roll-up — it is a tautological check, not a
  gate. The record lists ingress as part of preflight without flagging it always passes.

### "plan_arclink_provisioning_rollback performs NO host mutation." CONFIRMED.
- Requires job exist AND status=='failed' (provisioning:1922-1925); only writes a job + plan dict +
  `rollback_requested` event (provisioning:1934-1953). No executor / subprocess. NOT refuted.

### Double handoff gates. CONFIRMED + record's DRIFT call is right.
- Healthy-services gate blockers include "starting" (worker:1264) — prior-doc understatement is a
  real DRIFT, record correct. Hermes-home gate raises on not-ready (worker:1271-1293). NOT refuted.

---

## C. AUTH / REPLAY / CONCURRENCY

- Broker replay: single-use nonce + 300s TTL + signature over body-hash (broker:701-716). Sound.
- Fleet token: HMAC sig `compare_digest` (fleet:101) AND stored `token_hash` `compare_digest`
  (fleet:110); lazy expire flip (fleet:115-121); reject non-pending (fleet:122-123). Sound.
- Stale-running reaper: `_fail_stale_running_operator_actions` flips `running` rows older than
  30 min to `failed` (enrollment:622-647). This MITIGATES the UnicodeDecodeError strand (see D).
- `_docker_mode` truthy-set divergence CONFIRMED: agent_access:143 `{1,true,yes,on}` vs
  enrollment:764 `{1,true,yes}`. Record LOW is accurate.

---

## D. UnicodeDecodeError ESCAPE — CONFIRMED, but record OVER-states "strands".
- I executed the hierarchy check: `UnicodeDecodeError` is a subclass of `ValueError` but NOT of
  `OSError`/`TimeoutError`/`URLError`/`json.JSONDecodeError`. The except tuple at enrollment:342 does
  NOT catch it. So a non-UTF-8 success body at enrollment:335 (`.decode("utf-8")`) propagates out of
  `_operator_upgrade_broker_request`, past `_run_brokered_host_upgrade` (only catches RuntimeError,
  :381), out of `main()` (no try/except, enrollment:3348). Row was marked `running` at :2342.
  CLAIM CONFIRMED.
- **CORRECTION to the record:** it says the action is "stranded in running". It IS recoverable: the
  next `main()` invocation runs `_fail_stale_running_operator_actions(stale_seconds=1800)` first
  (enrollment:2323-2329) which flips it to `failed` after 30 min (enrollment:633-647). So "strand"
  is transient (≤30 min + dependent on the cron/loop surviving the crash), not permanent. LOW
  severity stands; the "strands the row" phrasing should read "strands until the 30-min reaper".
- In-repo broker always emits UTF-8 (broker:657 `json.dumps(...).encode("utf-8")`), so unreachable
  from the in-repo broker; reachable only via a non-UTF-8 responder on the broker URL.

---

## E. NEW GAPS NEITHER RECORD NOR PRIOR DOCS MENTION

1. **[MEDIUM] Fleet audit chain accepts UNKEYED SHA-256 entries → full re-forge undetected.**
   `verify_fleet_audit_chain` (fleet:886-902): if a stored `entry_hash` lacks the `hmac_sha256_v1$`
   prefix it is treated as "legacy" and re-verified with `secret=""` (fleet:892-901). A DB-write
   attacker can replace an inventory's entire chain with consistent UNKEYED sha256 entries (no
   prefix) and pass verification with ZERO errors — no P0 fires (fleet:904-912). The chain-link
   check (`actual_prev != expected_prev`, fleet:884) only catches PARTIAL edits that break linkage,
   not a wholesale unkeyed re-forge. `_chain_hash` itself silently falls back to unkeyed sha256 when
   no secret is present (fleet:469-472). This DIRECTLY contradicts the record VERDICT's
   "cryptographically sound … HMAC prev-hash audit chain that queues a P0 on tamper". Gated behind
   DB-write access (already high-privilege), hence MEDIUM not HIGH.
   `[python/arclink_fleet_enrollment.py:469-472,884,886-902]`

2. **[LOW] agent_access state-file ownership is a silent no-op on failure.** `_write_access_state`
   wraps `os.chown(uid,gid)` + `chmod(0o600)` in `try/except OSError: pass`
   (agent_access:71-75). If chown fails (e.g. EPERM when not root), the exception is swallowed and
   the state file stays owned by the writer, NOT the agent uid/gid — silently violating the record's
   "owned by the agent uid/gid" claim. (Perms stay 0600 via mkstemp default, so the perms half is
   safe; only ownership silently degrades.) `[python/arclink_agent_access.py:69-75]`

3. **[INFO] host_readiness `check_ingress_strategy` is a tautology.** Returns `ok=True` on both the
   cloudflare and traefik_local branches (host_readiness:159,:161); it can never fail the readiness
   roll-up. The record lists ingress as a preflight check without noting it always passes.
   `[python/arclink_host_readiness.py:154-161]`

4. **[INFO] enrollment `source_ip` is attacker-spoofable audit data.** Sourced from
   `x-real-ip`/`x-forwarded-for` (hosted_api:2046) and persisted to `metadata["source_ip"]`
   (fleet:632-633). Audit-only (not auth), so low impact, but the audit record's source IP is
   client-forgeable. `[python/arclink_hosted_api.py:2046; python/arclink_fleet_enrollment.py:632-633]`

5. **[INFO] operator-agent exclusion is a fragile substring match.**
   `metadata_json … NOT LIKE '%"operator_agent"%'` (worker:565) is a raw substring test; a metadata
   value (not the flag) containing that literal would wrongly exclude a deployment, and a flag stored
   with different key-casing/whitespace would slip through. Convention reused elsewhere; low risk.
   `[python/arclink_sovereign_worker.py:565]`

---

## F. REFUTATIONS ATTEMPTED — NONE SUCCEEDED (record's load-bearing claims hold)
- Cross-piece HMAC seam #1: re-opened broker, byte-matched — HOLDS.
- TOCTOU-safe consume (#2 self-check): PROVEN safe via per-request connection close — HOLDS.
- UnicodeDecodeError escape: CONFIRMED (record correct) — refines "strand" to transient.
- Non-Docker pin allowlist gap: CONFIRMED + producer also lacks allowlist — record correct.
- validate_no_plaintext_secrets final gate: CONFIRMED at :1781 — HOLDS.
- Rollback no-mutation, handoff gates, ssh-record rejects, ingress/strategy cleaners: all HOLD.

## RESIDUAL DISAGREEMENTS WITH THE RECORD
1. VERDICT calls the fleet audit chain "cryptographically sound … queues a P0 on tamper" — this is
   too strong; the unkeyed-legacy verify branch (fleet:891-902) allows an undetected full re-forge.
   Demote to "tamper-evident against partial linkage edits; downgradeable to unkeyed sha256".
2. The UnicodeDecodeError risk text "strands a running row" should read "strands until the 30-min
   stale reaper recovers it" (enrollment:2323-2329,:633-647).
3. The record under-documents that `check_ingress_strategy` can never fail readiness.
