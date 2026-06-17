# CANON-12 — Public Agent Gateway & Brokers — RECONCILED (both-model truth)

- **Adjudicator:** Claude Opus 4.8 (1M) final federation arbiter.
- **Codex (GPT-5.5 xhigh) sign-off:** `OBJECT(6)` — boundary thesis code-proven; six material contract corrections required.
- **Federation sign-off:** **AGREED-WITH-STANDING-DISAGREEMENTS** — all logic points reconciled to one code-grounded truth; two items genuinely cannot be settled from a read-only audit (live-container EPERM proof; whether production state roots are ever symlinked). They are enumerated below with why.
- **Method:** every disputed point re-opened at path:line by the arbiter. Code wins over comment/name/prior claim. Codex CONFIRM items where both models already agreed are ratified one-line.

---

## RESOLUTION TABLE (disputed points + Codex REFUTE/REFINE + new findings)

| # | Point | Winner | Deciding cite (arbiter re-opened) |
|---|-------|--------|-----------------------------------|
| 1 | GAP-019 gate enforced in code (start + per-request) | both | `arclink_boundary.py:85-97` raises unless env=="accepted"; per-file main()+request cites ratified |
| 2 | Constant-time token auth, fail-closed on blank | both | `gateway_exec_broker.py:51-54`; `hmac.compare_digest` with `bool(expected and supplied ...)` |
| 3 | Raw-command rejection before reconstruction | both | `gateway_exec_broker.py:197-198`; `migration_capture_helper.py:116-117`; `agent_process_helper.py:876` |
| 4 | docker.sock split (3 of 6) + supervisor holds none | both | `compose.yaml:666,832,1017`; helpers 908-918 carry no socket |
| 5 | All seven inbound seams: producer/consumer key + header match | both | seam cites re-spot-checked; `_validate_public_agent_bridge_cmd` container from Docker labels `notification_delivery.py:536-538` |
| 6 | **G1/S8: "stdin-only, never on disk" is FALSE — detached path writes bot_token to 0600 job file** | both (Codex+Claude agree; arbiter confirms) | `notification_delivery.py:973-977` (`gateway_exec_request` incl `payload.bot_token`) `json.dump` to `job_path` mode 0600 `:997-1001`; built from `payload` carrying `bot_token` `:676,729-735` |
| 7 | **G2: agent-process-helper cap_drop ALL + no cap_add vs setpriv --reuid/--regid** | both (compose/code mismatch proven; EPERM not executed) | `compose.yaml:908-918` (cap_drop ALL, no cap_add, user 0:0) vs `agent_process_helper.py:444-457` (setpriv --reuid/--regid); contrast agent-user-helper cap_add CHOWN/DAC_OVERRIDE/FOWNER `compose.yaml:888-891` |
| 8 | **G3: gateway-exec-broker-net co-attachment is CURRENT topology, not "future"** | both (Claude G3 + Codex refine) | operator gateway `compose.yaml:388-391` + dashboard `:428-431` both on `gateway-exec-broker-net`; co-tenants get URL `:174` but NOT token (token only `:1006,1032`) |
| 9 | **G4: agent-process-helper "leaks a log FD per started process (MEDIUM/LOW)"** | codex (REFUTE) | `agent_process_helper.py:843` `log` is a local; `PROCESSES`/`PROCESS_SIGNATURES` retain only the `Popen` + signature `:72-73,846,855`; local `log` is rebound each loop iter → CPython refcount-GC closes the parent FD. No indefinite leak. |
| 10 | env pass-through beyond 10 pinned keys (MEDIUM) | both | `agent_process_helper.py:334-370` accepts arbitrary safe `^[A-Z][A-Z0-9_]*$` non-secret keys; supervisor producer pre-filters `docker_agent_supervisor.py:291-300` — risk needs compromised tokened producer/alt client. Stays MEDIUM. |
| 11 | R2/S2: pod_comms is two transactions, not one | both | `pod_comms.py:306` commits message/audit/event/rate-limit, then `queue_notification` commits separately `arclink_control.py:8071`. Record's "single commit at :306" understated. |
| 12 | R1: INFO risk rationale ("later validation failure rolls back rate-limit") | claude-verifier | `pod_comms.py:243-246` — all validation runs BEFORE `check_arclink_rate_limit(... commit=False)`; no post-insert validation step exists. Conclusion accidentally right, rationale wrong. |
| 13 | G5: chown -R TOCTOU "symlink-traversal" wording | codex (softened) | `agent_user_helper.py:446` plain `chown -R` (no `-L`); GNU `chown -R` defaults to `-P` (no symlink dereference). Validate-then-act gap real (LOW); symlink-tree-traversal blast radius overstated. |
| 14 | G6: cross-Captain grant is user-pair scoped, not deployment-pair | both | `pod_comms.py:77-78` returns True when grant metadata pins neither deployment id → one grant authorizes all deployment pairs between the two users. |
| 15 | G7: bridge reports delivered on absence-of-exception | both | `public_agent_bridge.main()` prints `{"ok":true,"delivered":true}` when `_run` returns without raising; broker accepts on `ok is True`. Delivery semantics optimistic. INFO. |
| 16 | S1: migration-capture producer sends raw paths, consumer resolves | both (narrow, deferred to CANON-13) | `migration_capture_helper.py:81` `path.resolve(strict=False)`; all containment/name checks + copy run on resolved path. Bounded under state-root base; identity mismatch only if a state-root component is symlinked. |
| 17 | B29: gateway-exec command-shape audit | both | `notification_delivery.py:490-527` allows only len-6 docker-exec / len-13 compose-exec; container resolved from Docker project/service labels `:536-538`, not raw deployment_id. Validator load-bearing on detached job-file reload. |

---

## CONFIRMED Codex NEW FINDINGS (re-verified true → net-new federation risks)

- **MEDIUM — pod-message notification `extra` is queued but never read at agent consumption.**
  `queue_notification(... extra={message_id, sender_deployment_id, recipient_deployment_id, sender_agent_name, attachments})` writes `extra_json` (`pod_comms.py:308-321`; persisted `arclink_control.py:8066,8069`), but `consume_agent_notifications` SELECTs only `id,target_kind,target_id,channel_kind,message,created_at` — no `extra_json` (`arclink_control.py:9871-9882`). The recipient agent receives the flattened body only; message_id/sender/attachments are dropped on the read path.

- **LOW/MEDIUM — `mark_pod_message_delivered` has no production caller (pod-message status unwired).**
  Definition `pod_comms.py:398-437` updates `arclink_pod_messages.status='delivered'`; the only callers repo-wide are the unit test. The agent consume path marks `notification_outbox.delivered_at` only (`arclink_control.py:9883-9890`), never the pod-message row. (Already acknowledged in `docs/arclink/architecture.md` and `ARCLINK_GROUND_TRUTH_BRIEF.md` — net-new to the CANON-12 record, not net-new to the project.)

## REJECTED Codex new-findings
- (none — Codex offered no new finding that failed re-verification.)

## Codex REFUTATION of a CLAUDE-VERIFIER finding — UPHELD
- **G4 FD-leak (Claude verifier MEDIUM/LOW) → REJECTED.** Re-verified: `log` (`agent_process_helper.py:843`) is a per-iteration local, not retained in any global; only `Popen`+signature persist (`:72-73,846,855`). CPython refcount GC closes the parent FD when `log` is rebound. No FD exhaustion. Codex's REFUTE wins.

---

## SEVERITY CHANGES (only where code supports)

| Risk | From | To | Cite |
|------|------|----|------|
| agent-process-helper log FD leak | MEDIUM/LOW (verifier) | **DROPPED (not a risk)** | `agent_process_helper.py:72-73,843` — handle not retained; GC-closed |
| Bot-token stdin-only "verified strength" | (record VERDICT strength) | **HIGH defect** | `notification_delivery.py:973-1001` — token on 0600 disk on detached path |
| agent-process-helper cap-drop vs setpriv | (unflagged) | **HIGH pending live proof** | `compose.yaml:908-918` vs `agent_process_helper.py:444-457` |
| pod-message notification metadata | (unflagged) | **MEDIUM (new)** | `pod_comms.py:308-321` vs `arclink_control.py:9871-9882` |
| pod-message status wiring | (unflagged) | **LOW/MEDIUM (new)** | `pod_comms.py:398-437`, no prod caller |
| chown -R TOCTOU | LOW (symlink-traversal) | **LOW (validate-then-act only; traversal wording removed)** | `agent_user_helper.py:446` plain `chown -R`, default `-P` |
| pod_comms INFO rate-limit (rationale) | INFO (wrong rationale) | **INFO (corrected rationale)** | `pod_comms.py:243-246` |
| pod_comms write atomicity | (record: single commit) | **clarified: two transactions** | `pod_comms.py:306` + `arclink_control.py:8071` |

---

## STANDING DISAGREEMENTS (cannot be settled from code alone)

1. **agent-process-helper setpriv EPERM under cap_drop ALL (G2).**
   Claude view: with `cap_drop: ALL` and no `cap_add`, `setpriv --reuid/--regid` from uid 0 should fail EPERM, breaking every run_once/ensure_processes. Codex view: same — but this read-only audit proved the compose/code mismatch, not an executed EPERM. **Why unresolved:** requires running the container and invoking run_once to observe whether the kernel grants the setresuid (e.g. via a residual capability or undocumented runtime grant). Severity held at **HIGH pending live proof**.

2. **migration-capture raw-vs-resolved path identity (S1).**
   Claude view: producer sends raw DB paths, consumer resolves symlinks, so they can disagree on the concrete path. Codex view: did not separately dispute; checks are post-resolution and base-bounded. **Why unresolved:** whether this is ever exploitable depends on whether production state roots under `ARCLINK_STATE_ROOT_BASE` are ever symlinked — a CANON-13 invariant not provable from CANON-12 code. Bounded blast radius; held at **INFO/LOW, deferred to CANON-13**.

---

## FINAL BOTH-MODEL VERDICT

The CANON-12 core thesis stands and is independently re-proven by both models: these are genuine, code-enforced privilege boundaries — GAP-019 gate at start and per-request, constant-time token auth that fails closed on blank, raw-command rejection with local allowlisted reconstruction, strict regex/path/IP/env validation with canonical-child checks, redacted incident logs that carry no secrets, and a real docker.sock split (3 of 6; root supervisor holds none). All seven inbound seams have matching producer/consumer keys and shared header symbols.

Reconciled corrections to the record (both models agree):
1. The "stdin-only, never on disk" bot-token claim is **false on the detached path** — the token is written cleartext to a 0600 job file (HIGH).
2. agent-process-helper drops ALL caps with no cap_add yet relies on `setpriv --reuid/--regid` — a proven compose/code mismatch (**HIGH pending live EPERM proof**).
3. gateway-exec-broker-net co-attachment of the operator gateway/dashboard is **current** topology (token-gated; co-tenants hold URL but not token) — MEDIUM.
4. pod-message notification `extra` metadata is written but never read at agent consumption (MEDIUM, net-new).
5. `mark_pod_message_delivered` has no production caller; pod-message status is unwired (LOW/MEDIUM, net-new).
6. pod_comms is two transactions (message commit, then a separate `queue_notification` commit), not one.
7. The verifier's FD-leak (G4) is **rejected** — the log handle is GC-closed, not retained.
8. chown -R TOCTOU is a validate-then-act concern only; the symlink-traversal framing is overstated (plain `chown -R` defaults to `-P`).

Net: the boundary **provably does its job**; the open exposure is operational/contractual (a disk-resident secret on the detached path, a likely-broken cap posture for one helper, an unwired pod-message delivery/status path) rather than a defeat of the privilege boundary itself. Two points (live setpriv EPERM; state-root symlink reality) remain standing disagreements resolvable only outside a read-only audit.

---

<!-- CANON-REPAIR-STATUS:START -->
## Repair status

> Refreshed from [`research/canon/fixes/CANON-12-gateway-brokers.fix.md`](../fixes/CANON-12-gateway-brokers.fix.md) (tracked). The audit findings above remain the adjudicated spec; this block records the repair campaign state for this piece.

- Status: `c5cec97` committed.
- Summary: 4 fixed / 5 skipped / 5 needs-decision.
- Tests: 7 test files run, all pass; py_compile and git diff --check pass
- Representative fixes:
  - HIGH — detached public Agent bridge jobs no longer persist `payload.bot_token`; job files strip runtime secrets and worker rehydrates from platform env before broker/bridge execution — python/arclink_notification_delivery.py:960
  - MEDIUM/LOW — Pod Comms message write and notification enqueue are now one transaction via `queue_notification(commit=False)`; enqueue failure rolls back message/audit/event/rate rows — python/arclink_pod_comms.py:307, python/arclink_control.py:8073
  - MEDIUM — agent notification consumption now reads `extra_json`, returns parsed `extra`, and marks linked `pod-message` rows delivered with audit/event rows — python/arclink_control.py:9891
- Needs decision:
  - agent-process-helper arbitrary uppercase non-secret env pass-through: real surface, but narrowing it is a public process-env contract change.
  - Pod Comms same-Captain grant bypass and user-pair-scoped cross-Captain grants: changing this would alter sharing semantics/backward compatibility.
  - agent-user-helper `chown -R` validate-then-act gap: narrow safe fix is not obvious without deciding whether to replace recursive chown with a pinned/fd-based ownership walk.
  - `record_rejection_incident` silent no-op on unsafe/OSError paths: raising could break rejection handling; needs observability-vs-availability decision.
  - public_agent_bridge `delivered:true` on absence-of-exception: needs a platform delivery contract, not just local code inference.
<!-- CANON-REPAIR-STATUS:END -->
