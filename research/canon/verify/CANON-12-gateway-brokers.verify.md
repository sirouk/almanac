# CANON-12 — Public Agent Gateway & Brokers — ADVERSARIAL VERIFICATION

Verifier: independent Opus 4.8 skeptic. Method: re-opened every cited file at
path:line; verified producer/consumer both ends in code; hunted unhappy paths,
fail-open, TOCTOU, concurrency, and disk-secret exposure. Code wins over the
record's prose.

## OVERALL VERDICT
**TRUSTWORTHY WITH MATERIAL OMISSIONS.** The record's core thesis is correct and
independently re-confirmed: these are genuine, code-enforced privilege boundaries
(GAP-019 gate at start + per-request, constant-time token auth, raw-command
rejection, local command reconstruction, strict regex/path/IP validation,
redacted incident logs). All seven inbound seams have matching producer/consumer
keys and shared header symbols — re-verified. BUT the record overstates two
load-bearing safety claims and misses three real defects:

1. **Bot-token "stdin-only, never on disk" is FALSE on the detached path** — the
   detached job-file path persists the bot token to disk (mode 0600). The record's
   secret-handling section and adversarial self-check #1 never mention this.
2. **agent-process-helper capability posture is unverified and likely broken** —
   container drops ALL caps with no `cap_add`, yet relies on `setpriv --reuid/
   --regid` which needs CAP_SETUID/CAP_SETGID. Neither record nor prior docs note
   this. Potential fail-to-function for every agent process.
3. **gateway-exec-broker-net already has multiple co-attached operator
   containers** — the record frames co-attachment as a hypothetical "future"
   risk; it is the current topology.

Plus an FD leak, a chown -R TOCTOU, a pod_comms grant-scope looseness, a
mis-stated transaction boundary, and a mis-reasoned INFO risk.

---

## REFUTATIONS / CONFIRMATIONS OF RECORD CLAIMS

### R1 — REFUTED (rationale): pod_comms INFO risk "later validation failure rolls back the rate-limit row"
Record RISKS INFO (lines 421-424): "rate-limit row is inserted (commit=False)
before the message INSERT in the same transaction; a later validation failure
rolls back the rate-limit row too (correct)."
Code `arclink_pod_comms.py:243-253`: ALL validation
(`_require_send_allowed` 243, `_clean_body` 244, `_validate_attachment_refs` 245)
runs BEFORE `check_arclink_rate_limit(... commit=False)` at 246. There is no
validation step after the rate-limit insert; the subsequent INSERT (274) does not
reject. So the described "later validation failure" path does not exist. The
record's conclusion (limit consumed only on valid sends) is accidentally correct
but for the opposite reason. Rationale refuted.

### R2 — REFUTED (precision): OUTPUT CONTRACT "single conn.commit() at :306"
Record lines 168-171 lumps `queue_notification` into the pod_comms write set
"single conn.commit() at :306". Code: `arclink_pod_comms.py:306` commits the
message/audit/event/rate-limit, but `queue_notification` is called AFTER the
commit (308) and does its OWN commit (`arclink_control.py:8071`). So the
notification is a SEPARATE transaction. If `queue_notification` raised before
8071, the message would be committed with no notification — a real (if narrow)
non-atomic seam the record presents as atomic.

### R3 — CONFIRMED: GAP-019 gate enforced in code, both start and per-request
`require_docker_trusted_host_risk_accepted` raises unless env == "accepted"
(`arclink_boundary.py:85-97`). Verified per file at main() (SystemExit) and per
request (ValueError): gateway-exec 289/378; deployment-exec 233/312;
agent-supervisor 434/523; migration-capture 224/295; agent-user 529/603;
agent-process 873/945. Record TOUCH POINTS accurate.

### R4 — CONFIRMED: constant-time token auth, all six
`hmac.compare_digest` with `bool(expected and supplied and ...)` so blank token
fails closed: gateway-exec :54; deployment-exec :99; agent-supervisor :462;
migration-capture :57; agent-user :66; agent-process :95. Confirmed.

### R5 — CONFIRMED: raw-command rejection on every broker/helper
`("args","cmd","command")` (or `("cmd","command")` for gateway-exec :197) rejected
before any reconstruction. Confirmed at each cited site.

### R6 — CONFIRMED: docker.sock split (3 of 6) and supervisor holds none
compose.yaml: deployment-exec :666, agent-supervisor-broker :832, gateway-exec
:1017 mount /var/run/docker.sock. migration-capture, agent-user, agent-process do
NOT (and say so in comments). agent-supervisor (965-992) mounts no socket. Record
correct.

### R7 — CONFIRMED: all seven inbound seams both-ends key/header match
Seam #1 producer `_public_agent_gateway_payload` emits
platform/bot_token/chat_id/channel_id/user_id/text/message_id/display_name/
chat_type/streaming_enabled (`arclink_notification_delivery.py:674-685`); consumer
`_validate_payload` validates the 5 security-relevant keys and passes the rest
through (`gateway_exec_broker.py:176-188`). Seam #3 executor body
(`arclink_executor.py` BrokeredDockerComposeRunner) ↔ `_validate_request`
(deployment_exec_broker.py:117-156). Seam #4 `_migration_capture_helper_payload`
(`arclink_pod_migration.py:469-478` + operation 498) ↔ migration_capture_helper
:115-158. Seam #5 `ensure_dashboard_proxy` (`docker_agent_supervisor.py:484-491`)
↔ broker :267-281. Seam #6 `ensure_container_user` (:585-592) ↔ agent_user_helper
:414-421. Seam #7 `agent_process_context` (:659-673) ↔ `_validate_common`
:385-434. Header symbols verified identical in both ends for each. Confirmed.

### R8 — CONFIRMED-WITH-CAVEAT: seam #1 "consumer reads exactly those"
True for the 5 validated keys, but the producer emits ~13 keys and the broker
forwards ALL of them to the bridge stdin via `clean = dict(payload)`
(`gateway_exec_broker.py:176`). The bridge re-requires its own keys via
`_required` (public_agent_bridge.py:71-75), so safe, but "reads exactly those"
understates the passthrough surface.

### R9 — CONFIRMED: DRIFT note on agent-process-helper do_POST non-dict ordering
agent_process_helper `do_POST` (905-928) does NOT check `isinstance(body,dict)`
before dispatch; the inner `run_agent_process_helper_request` does (874-875).
Record DRIFT note correct.

### R10 — CONFIRMED: 0.0.0.0 bind drift vs loopback docstring
Code default `DEFAULT_HOST="127.0.0.1"` everywhere; compose forces 0.0.0.0
(656,686,825,897,930,1007). Record correct. See G3 for under-calibration.

---

## NEW GAPS BOTH THE RECORD AND PRIOR DOCS MISSED

### G1 — HIGH: bot token persisted to disk on the detached gateway-exec path
Record secret-handling (212-215) and self-check #1 (350-357) assert bot tokens
reach only stdin / container env, never argv, and present "stdin-only secret path"
as a VERIFIED STRENGTH (VERDICT, 435-436). But the detached delivery path writes
the entire `gateway_exec_request` — which contains `payload.bot_token` — to a JSON
job file: `_write_public_agent_bridge_job` builds `body={... "gateway_exec_request":
gateway_exec_request ...}` and `json.dump(body, handle)` to `job_path`
(`arclink_notification_delivery.py:973-1001`); reloaded via `read_text`
(`:1007`). File mode is 0600 (`:997`), so it is protected, but it is a cleartext
secret on the control-node filesystem — directly contradicting the record's
stdin-only framing. Producer is CANON-23, but the claim it refutes is made in
CANON-12.

### G2 — HIGH (needs runtime confirm): agent-process-helper drops ALL caps but needs CAP_SETUID/SETGID for setpriv
compose.yaml agent-process-helper (908-947): `security_opt: no-new-privileges:true`
(911-912), `cap_drop: ALL` (913-914), `user: "0:0"` (918), NO `cap_add`. The helper
drops privilege via `setpriv --reuid <uid> --regid <gid>` (agent_process_helper.py
:444-457). A uid-0→non-zero setresuid/setresgid generally requires CAP_SETUID/
CAP_SETGID; with all caps dropped this likely fails EPERM, breaking every
`run_once`/`ensure_processes`. Contrast agent-user-helper, which DOES add the caps
it needs (`cap_add: [CHOWN, DAC_OVERRIDE, FOWNER]`, 888-891). Neither the record's
TOUCH POINTS (205-209, lists the setpriv argv as a strength) nor prior docs note
the missing setuid/setgid caps. Either a latent deployment defect or an undocumented
runtime grant — must be verified live.

### G3 — MEDIUM: gateway-exec-broker-net already has multiple co-attached operator containers (record says "future")
Record MEDIUM risk (403-406) and OPEN #3 frame co-attachment as a hypothetical
future mis-wire. Actual compose: `control-operator-hermes-gateway` (390-391) and
`control-operator-hermes-dashboard` (428-431) are BOTH attached to
`gateway-exec-broker-net`, plus the delivery client (1052) and the broker (1020).
These run Hermes agent code and can already reach the broker (token-gated). The
"any future co-attached container" wording understates current exposure; the risk
is live, not prospective.

### G4 — MEDIUM/LOW: agent-process-helper leaks a log file descriptor per started process
`_ensure_processes` opens `log = log_path.open("a", ...)` (843), passes it to
`subprocess.Popen(... stdout=log ...)` (846-852), and never closes it in the
parent. The helper is long-lived (ThreadingHTTPServer) and reconciles repeatedly;
each (re)start leaks one FD. Over many cycles this exhausts FDs in a root-held
boundary process. Not mentioned anywhere.

### G5 — LOW: chown -R TOCTOU in agent-user-helper
`_ensure_user_home` validates paths with `resolve(strict=False)` at request time
(`_require_canonical_child_path`, agent_user_helper.py:129-148) but then runs
`subprocess.run([chown, "-R", f"{uid}:{gid}", str(home)])` (446) on the unpinned
path tree. Between validation and the recursive chown, a path component under the
agent home could be swapped to a symlink (chown -R follows directory tree). Only
the trusted token-holding supervisor drives this, lowering practical risk, but the
validate-then-act gap is real and unflagged.

### G6 — LOW: pod_comms cross-Captain grant is user-pair scoped, not deployment-pair scoped
`_grant_matches_deployments` returns True when the grant metadata carries neither
`owner_deployment_id` nor `recipient_deployment_id` (`arclink_pod_comms.py:77-78`).
So a single `pod_comms` grant between two Captains authorizes messaging across ALL
of their deployment pairs, not just the granted pair, unless the grant explicitly
pins deployment ids in metadata. The record's input contract ("cross-Captain
requires active pod_comms grant") presents the gate as tighter than it is.

### G7 — INFO: bridge reports delivered:true on absence-of-exception, not confirmed send
`public_agent_bridge.main()` prints `{"ok":true,"delivered":true}` whenever `_run`
returns without raising (`:799`); the broker accepts on `ok is True`
(gateway_exec_broker.py:315) and delivery marks the notification delivered. A
gateway pipeline that completes without actually emitting a platform message would
still report delivered. The record's CODE-PATH TRACE step 7 presents delivery as
definitive.

---

## SEAM MISMATCHES

### S1 — migration-capture: producer sends RAW DB paths, consumer validates RESOLVED paths
Producer `_migration_capture_helper_payload` emits raw `str(row["source_state_root"])`
etc. (`arclink_pod_migration.py:475-477`). Consumer `_absolute_path` calls
`path.resolve(strict=False)` (migration_capture_helper.py:81), so name-equality
and base-containment checks run on the SYMLINK-RESOLVED path, and `_copy_capture`/
`_materialize_capture` operate on the resolved location. If any state-root
component is a symlink, the helper reads/writes a different concrete path than the
action worker recorded. Blast radius is bounded under the state-root base by the
post-resolution checks, but producer and consumer disagree on path identity. Not
noted in the record's both-ends-verified seam #4.

### S2 — pod_comms producer/consumer notification transaction split (see R2)
`send_pod_message` commits the message at `pod_comms.py:306` then calls
`queue_notification` which commits separately at `arclink_control.py:8071`. The
record's seam #9 ("partial") flags the delivery-worker read as untraced but treats
the producer write as a single transaction; it is two.

---

## CLAIMS RE-CONFIRMED (record was right)
- uid/gid range [20000,60000): AGENT_UID_MIN=20000 + SPAN=40000, enforced at
  agent_user_helper.py:197-198. Correct.
- backend_host IP class gate (no wildcard/multicast/global; loopback/private/
  link-local only): agent_supervisor_broker.py:96-110 and agent_process_helper.py
  :130-144. Correct, fail-closed.
- env block/allow logic: control-token reject (raise) + unapproved set + LD_*
  prefix + _TOKEN/_SECRET/_PASSWORD/_KEY suffix + exact 10 pinned keys + pinned
  SAFE_PATH (agent_process_helper.py:322-370). Confirmed. Supervisor pre-filter
  is strictly narrower (strips control tokens, rejects unapproved) so helper is
  the stricter end — genuine defense-in-depth (seam #7).
- rejection incidents never carry payload/token/text: top-level row fields are
  fixed constants from `_rejection_message`; metadata re-filtered by
  `safe_metadata` (SAFE_METADATA_RE, <=160 chars) at rejection_incidents.py:111-125,
  149-150. O_APPEND|O_CREAT|O_NOFOLLOW|O_CLOEXEC 0600 at :152-159. Correct.
- record_rejection_incident silent no-op on unsafe/unset path (138-139,160-161):
  confirmed (record LOW risk accurate).
- schema cites: arclink_pod_messages CREATE at arclink_control.py:1437 with status
  CHECK queued/delivered/failed/redacted; arclink_share_grants at :1052. Correct.
- PROCESS_LOCK guards all PROCESSES mutation (826,863); run_once does not touch
  PROCESSES. No TOCTOU on the registry itself (record OPEN #5 can be closed).

## RESIDUAL DISAGREEMENTS / OPEN FOR FEDERATION
- G2 (setpriv cap requirement) needs a live container check: run the helper and
  invoke run_once; confirm whether setpriv --reuid succeeds with cap_drop ALL.
- G1 detached-path token-on-disk is owned by CANON-23 producer but refutes a
  CANON-12 verdict claim; both pieces should reconcile.
- S1 raw-vs-resolved path identity needs CANON-13 sign-off on whether state roots
  are ever symlinked in production.
