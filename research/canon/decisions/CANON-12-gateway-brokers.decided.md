# CANON-12 — Public Agent Gateway & Brokers — DECIDED (federation final)

- **Adjudicator:** Claude Opus 4.8 (1M) — DECISION mode final adjudicator.
- **Codex proposal under review:** `research/canon/decisions/CANON-12-gateway-brokers.codex.md` (GPT-5.5 xhigh).
- **Grounding:** every decision re-opened at path:line; symphony anchored to
  `docs/arclink/sovereign-control-node-symphony.md`. The repair campaign already
  landed the 4 fixed items (incl. pod_comms single-transaction at
  `pod_comms.py:307-322` and `extra_json` consumption). These 5 are the genuine
  operator calls.
- **Method:** form independent view from code + symphony FIRST, then converge
  with Codex. Code wins over comment/name. Plan moves code toward the symphony
  while failing closed and preserving state.

Symphony spine these all serve (North Star + Whole-System Traversal):
> "Operators own the universe: hosts, secrets, fleet, policy, upgrades..."
> "Every step should have a local source owner, a local regression or dry-run
> proof where possible, and a named live proof gate... If any step cannot say
> what surface owns it, what state it reads, what state it writes, and **how it
> fails closed**, the symphony is not complete."

---

## DECISION 1 — agent-process-helper arbitrary uppercase non-secret env pass-through

**[VERDICT: refine]**

**Question.** `_require_env` (`agent_process_helper.py:334-370`) rejects control
tokens, secret-suffix keys, `LD_*`, and a fixed unapproved set, but passes
through any *other* `^[A-Z][A-Z0-9_]*$` key the request body carries beyond the
~10 pinned keys. Should this be narrowed to an owned contract?

**Independent reasoning.** The helper is a root→uid-drop `setpriv` boundary
(`:444-457`), so its env is ambient policy injected into a process that briefly
holds root. Today the *only* producer is the supervisor's `_agent_process_env`
(`docker_agent_supervisor.py:291-300`), which itself re-filters — defense in
depth, confirmed both-ends-verified. But the helper independently trusts the
request's env *shape*: a compromised-but-tokened producer (or a future second
client) can set arbitrary non-secret env on a root-spawned process. The
reconciled record holds this at **MEDIUM**. The symphony says terminal/process
execution must be "a brokered capability, never as ambient trust" — an
open-ended env shape is exactly ambient trust at the most privileged seam.

Two real concerns I weigh against Codex's plan: (a) the env constants are
**duplicated** in both files (`agent_process_helper.py:47-69` and
`docker_agent_supervisor.py:72-85`) — a maintenance smell that a shared module
fixes and that keeps the two sides in release lock-step; (b) a *pure* hardcoded
allowlist is brittle for legitimate operator extensions (Hermes/plugin envs
evolve per release), so an escape hatch is warranted — but the escape hatch must
be operator-owned config, never the request body.

**Agree / differ from Codex.** I agree with the *direction and shape* entirely:
shared versioned contract module, default-deny to the keys ArcLink generates,
operator-owned allowlist env, never trust allowlist entries from the request
body, fail before `setpriv`. I **refine** two things: (1) scope-control — make
the shared module the single source for the existing block/unapproved/secret
sets too (removing the duplication), not just the new allowlist; (2) sequencing
— gate the default-deny behind the existing fail-closed validation so unknown
keys raise a `ValueError` that already routes to a rejection incident + HTTP 400
(`agent_process_helper.py:886`), giving free observability without new plumbing.
I keep effort at med (Codex agrees).

**FINAL PLAN.**
1. New `python/arclink_agent_process_env_contract.py`: owns `SAFE_ENV_KEY_RE`,
   the block/unapproved/secret-suffix sets, the pinned expected-key set, and a
   new `operator_extra_env_allowlist()` reading
   `ARCLINK_AGENT_PROCESS_EXTRA_ENV_ALLOWLIST` (CSV of `^[A-Z][A-Z0-9_]*$`).
   Import it from both `agent_process_helper.py` and `docker_agent_supervisor.py`;
   delete the duplicated constants.
2. In `_require_env`, after the existing rejects, require every non-pinned key to
   be in `operator_extra_env_allowlist()`; otherwise raise
   `ValueError("agent process helper env key is not in the operator allowlist")`.
   Never read an allowlist from the request body.
3. Mirror the same default-deny in the supervisor's `_agent_process_env` so both
   sides agree (lock-step).
4. Tests (in an existing runnable file per CANON-29 writability constraint):
   `FOO=bar` rejected by default; accepted only when
   `ARCLINK_AGENT_PROCESS_EXTRA_ENV_ALLOWLIST=FOO`; rejection emits an incident.
5. Doc the new env in `docs/arclink/public-agent-gateway.md` /
   operations-runbook trust-boundary rows.

**Symphony anchor.** Abuse, Safety, And Platform Boundaries:
> "Terminal/process/root-helper restrictions that treat shell execution as a
> brokered capability, never as ambient trust."
Also Pods, Isolation, And SOUL: "Terminal and process execution stay behind
bounded broker/helper contracts."

**Effort:** med. **Blast-radius:** agent-process-helper, docker-agent-supervisor,
new shared module, tests, broker/helper docs; any deployment relying on an
undocumented env key must now name it in the operator allowlist (a deliberate,
visible break that fails closed rather than drifting).

---

## DECISION 2 — Pod Comms same-Captain bypass + user-pair-scoped cross-Captain grants

**[VERDICT: refine]**

**Question.** Same-Captain sends skip the grant entirely
(`pod_comms.py:133`: `if sender_user == recipient_user: return None`), and
cross-Captain grants with no deployment metadata authorize ALL deployment pairs
between the two users (`_grant_matches_deployments` returns `True` when both ids
are absent, `:77-78`). Should this be tightened?

**Independent reasoning.** Two distinct sub-questions, and they should not get
the same verdict:

- *Same-Captain bypass:* This matches the symphony's Crew ownership model — a
  Captain owns all their Pods/Crew, so intra-fleet Agent-to-Agent Comms needs no
  share grant. The only falsifier (record's adversarial self-check #5) is two
  distinct Captains sharing a `user_id`, which is a CANON-01/CANON-08 uniqueness
  invariant, not a CANON-12 defect. **Keep grantless.** I agree with Codex.

- *Cross-Captain user-pair scope:* This is the real issue. One accepted grant
  with empty metadata silently authorizes every current and future Pod pair
  between two users. The symphony's Sharing section is emphatic that a share
  "records owner, recipient, path, mode, **scope**, expiration" and that grants
  are "scoped by deployment/user identity" — an all-pair default is broader than
  the visible grant boundary the operator/Captain approved. So new grants should
  default to deployment-pair scope.

Where I diverge from Codex: the legacy-rescope mechanic. Codex proposes a new
`legacy_unscoped_requires_rescope` status that **stops authorizing sends** until
upgraded. I judge that too aggressive for a read-only-audited contract: it is a
**breaking change to live, already-accepted grants** with no evidence any such
grants are mis-scoped in practice — it trades a LOW-severity over-broad-default
for a guaranteed outage of existing cross-Captain Comms, which violates "preserve
state by default." The symphony wants fail-closed on *ambiguity*, but an existing
accepted user-pair grant is not ambiguous — it was, under the old contract, a
deliberate all-pair grant. The right move is to fail closed on *new* grants while
honoring legacy ones, and to surface them for operator review rather than
silently disarm them.

**Agree / differ from Codex.** Agree: keep same-Captain grantless; new grants
default to `deployment_pair` requiring owner+recipient deployment ids; keep an
explicit `captain_pair` (all-Crew) scope as an honest product opt-in; preserve
rows. **Differ:** do NOT auto-disarm legacy unscoped grants. Instead, treat a
legacy grant with no scope metadata as `legacy_captain_pair` (it keeps
authorizing, matching its original intent) AND emit a one-time redacted evidence
record + operator/Captain notification recommending re-scope. Optionally gate
hard-disarm behind an operator policy flag
(`ARCLINK_POD_COMMS_REQUIRE_SCOPED_GRANTS=1`) for operators who want the strict
posture — that makes the strict behavior the operator's call, not ours. This is
the one place I record a standing product fork (see below).

**FINAL PLAN.**
1. `create_user_share_grant_for_owner` (and the pod_comms grant write path):
   stamp `metadata.pod_comms_scope` = `deployment_pair` (default, requires
   `owner_deployment_id`+`recipient_deployment_id`) or `captain_pair` (explicit,
   with approval copy "this links every Pod you both run"). Reject a
   `deployment_pair` grant missing either id.
2. `_grant_matches_deployments`: when `pod_comms_scope` is absent (legacy),
   treat as `captain_pair` (return True) but flag `legacy_unscoped=True` on the
   returned grant so the caller can emit the advisory.
3. `find_active_pod_comms_grant`/`_require_send_allowed`: on a legacy-unscoped
   match, emit a redacted evidence row + queue an operator/Captain notification
   (once per grant) recommending re-scope. Honor the send.
4. Operator policy flag `ARCLINK_POD_COMMS_REQUIRE_SCOPED_GRANTS=1`: when set,
   legacy-unscoped grants do NOT authorize (fail closed with a clear
   "grant requires re-scope" PermissionError + advisory). Default unset = honor.
5. Surface parity: dashboard + Raven share copy, OpenAPI/MCP `_create_agent_share_request`
   schema gain the `pod_comms_scope` field, same truth across surfaces.
6. Tests: same-Captain still grantless; new deployment_pair grant rejects
   cross-pair sends; captain_pair authorizes all pairs; legacy honored + advisory
   emitted; legacy disarmed under the policy flag.

**Symphony anchor.** Pods, Isolation, And SOUL:
> "Pods cannot read or write another Captain's state... Dashboard, Drive, Code,
> Terminal, MCP, Notion, SSOT, and share routes are **scoped by deployment/user
> identity**."
Sharing: a share "records owner, recipient, path, mode, **scope**, expiration."

**Effort:** high. **Blast-radius:** pod_comms, share-grant API/OpenAPI, MCP
schema, dashboard/Raven copy, evidence/notifications, compatibility tests.
Preserves all existing rows; only the *default scope of new grants* changes
behavior, and legacy grants keep working unless the operator opts into strict.

---

## DECISION 3 — agent-user-helper `chown -R` validate-then-act gap

**[VERDICT: refine]**

**Question.** `_ensure_user_home` validates the canonical home, then shells
`chown -R <uid>:<gid> <home>` (`agent_user_helper.py:446`). Replace the shell
recursive chown with an in-process fd-anchored ownership walk?

**Independent reasoning.** Recursive chown is root authority, and the reconciled
record is precise about the *actual* residual risk: GNU `chown -R` defaults to
`-P` (no symlink dereference on the walk), so the originally-feared
"symlink-tree-traversal" framing is **overstated** — the record explicitly
softened this to **LOW, validate-then-act only**. The genuine gap is a TOCTOU
between the canonical-home validation and the recursive walk: a concurrent actor
who can swap a subtree of `home` between validate and chown could redirect
ownership changes. The home is under `ARCLINK_DOCKER_AGENT_HOME_ROOT`, the helper
runs as root inside its own container, and the only mutator of that tree is the
helper itself under `ASSIGNMENTS_LOCK` (`:41,342`) — so the practical exploit
window requires an already-present hostile writer inside the agent home root,
which is a narrow precondition.

So I weigh: the fd-walk is the *correct* shape for a root boundary and matches
the symphony's "brokered capability, never ambient trust," but it is **more code
on a LOW-severity, narrow-window gap**, and a hand-rolled recursive fd walk is
itself a source of new bugs (symlink races on the walk, fchownat flag mistakes,
performance on large homes). The proportionate move is the fd-anchored walk
*because* this is a root seam (the symphony holds root helpers to a higher bar
than severity alone), but I refine the urgency to reflect LOW severity and add a
cheaper interim hardening so the gap is not left fully open if the full walk
slips.

**Agree / differ from Codex.** Agree with the target: in-process no-follow
ownership walk, fd-relative (`O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC`,
`os.chown(..., dir_fd=, follow_symlinks=False)` / `fchown`), fail with a
rejection incident on any race/escape, never recreate files. **Refine:** (1) mark
this LOW-severity / med-effort and schedule it *after* the HIGH/MEDIUM items
(decisions 4, 1, 5), not as a blocker; (2) interim one-line hardening shippable
immediately: add `-h` (`chown -R -h`, already-default `-P`) and `--` argument
terminator, and re-`lstat` the home root immediately before the chown to confirm
it is still the same non-symlink dir/inode validated earlier — closing most of
the window cheaply while the full fd-walk lands.

**FINAL PLAN.**
1. Interim (low effort, ship now): re-`lstat` `home` immediately before the chown
   and assert it is the same `(st_dev, st_ino)` non-symlink directory the
   validation pinned; pass `--` and keep recursion no-dereference. Reject →
   incident if the inode changed.
2. Target (med effort): replace `subprocess.run([chown,-R,...])` with
   `_chown_tree_fd(home, uid, gid)`: open the validated home with
   `O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC`, `fstat`-verify it matches the validated
   inode, then walk with descriptor-relative `os.open(dir_fd=, O_NOFOLLOW)` /
   `os.scandir` + `os.chown(name, uid, gid, dir_fd=fd, follow_symlinks=False)`,
   skipping symlinks (chown the link itself, never the target), failing closed on
   any path-escape/race with a `RejectionIncidentWriteError`-routed incident.
3. Keep state: never delete/recreate user files; identical final ownership.
4. Tests (existing runnable file): symlink under home is not followed; a
   mid-walk inode swap is rejected; normal home gets correct recursive ownership.

**Symphony anchor.** Abuse, Safety, And Platform Boundaries:
> "Terminal/process/root-helper restrictions that treat shell execution as a
> brokered capability, never as ambient trust."

**Effort:** med (interim low). **Blast-radius:** agent-user-helper, trusted
executable expectations (the `chown` pin can stay for the interim, then becomes
unused for the recursive path once the fd-walk lands), tests, root-helper docs.

---

## DECISION 4 — `record_rejection_incident` silent no-op on unsafe/OSError paths

**[VERDICT: refine]**

**Question.** `record_rejection_incident` returns silently when `path is None`
(`rejection_incidents.py:138-139`) or on any `OSError` writing the JSONL
(`:160-161`). For GAP-019 broker/helper rejections, should an unwritable
incident sink fail the request instead of dropping the evidence?

**Independent reasoning.** These incident rows are the *evidence trail* for the
root/Docker privilege boundary — they are precisely what "leave redacted evidence
of what happened" means for the highest-trust seam. The symphony is unambiguous:
"ArcLink should never fail silently. Every important background path should have
an owner-visible state... and evidence that can be shared without secrets." A
silently-dropped rejection on the GAP-019 family is a same-truth violation: the
operator running blind cannot distinguish "no attacks" from "incident sink
broken." So I agree the silent no-op is wrong *for the broker/helper family*.

But I weigh the symmetric danger Codex also flags: making *recording* failure
turn a request into a hard failure can itself create availability problems, and —
more subtly — the current callers invoke `record_rejection_incident` **inside the
except block that is already handling a rejection** (e.g.
`gateway_exec_broker.py:292`). If recording raises there, the original rejection
reason could be masked by a secondary exception, and care is needed that the
last-ditch evidence (stderr line) never carries the raw request body/token. The
symphony's own guidance ("A clear split between local dry-run proof, authorized
live proof, policy decision, and residual-risk acceptance") supports a typed,
strict result rather than a bare raise.

**Agree / differ from Codex.** Agree: strict mode for the trusted-host family —
a typed result / dedicated redacted `RejectionIncidentWriteError`, callers pass
`required=True`, mutating endpoints return 503 *before* privileged work when the
sink is unavailable, health reports the sink down, a sanitized stderr line is the
last-ditch evidence, never leak request bodies. **Refine** two precision points:
(1) the 503-before-privileged-work check must be a *preflight* sink probe at
request entry (or at `main()` startup, like the GAP-019 gate already does), NOT a
raise from inside the rejection except-block — raising from the except path would
corrupt the rejection response and risk leaking the in-flight exception text.
Probe writability up front; if the sink is unwritable, refuse the request with
503 and a generic message and never reach the privileged operation. (2) Keep the
*existing* best-effort no-op for non-trusted-host / low-risk telemetry callers
(`required=False` default) so this does not ripple into unrelated logging.

**FINAL PLAN.**
1. `record_rejection_incident(..., required: bool = False)`: on `required=True`,
   if `path is None` or the write raises `OSError`, raise
   `RejectionIncidentWriteError` (carrying only `service`/`reason`, no payload)
   AND emit one sanitized stderr line. On `required=False`, keep today's silent
   no-op.
2. Add `incident_sink_writable(path) -> bool` (probe: resolve safe path + attempt
   an `O_APPEND|O_CREAT|O_NOFOLLOW` open of a `.probe` sibling, or stat the
   parent). Each trusted-host broker/helper calls it as a **preflight** at
   `do_POST` entry (before auth-gated privileged dispatch) and at `main()`
   startup; on failure → HTTP 503 `{"ok":false,"error":"incident sink
   unavailable"}` and `/health` reports the sink degraded.
3. The existing in-except `_record_rejection_incident(...)` wrappers keep using
   the strict mode but are wrapped so a write failure there logs the sanitized
   stderr line and still returns the original rejection HTTP code — never a 200,
   never the raw exception text to the client.
4. Tests (existing runnable file): unwritable sink → request 503 before any
   privileged work; `/health` degraded; rejection path on a writable sink still
   logs redacted; no request body/token in the stderr fallback.

**Symphony anchor.** Notifications, Incidents, And Evidence:
> "ArcLink should never fail silently. Every important background path should
> have an owner-visible state, a retry or repair path, and evidence that can be
> shared without secrets."

**Effort:** med. **Blast-radius:** rejection_incidents, all six broker/helper
rejection wrappers + their `do_POST`/`main()`, health tests, operations docs.
Fails closed on a broken evidence sink (the symphony's intent) while preserving
best-effort behavior for non-boundary telemetry.

---

## DECISION 5 — public_agent_bridge `delivered:true` on absence-of-exception

**[VERDICT: refine]**

**Question.** The bridge prints `{"ok":true,"delivered":true}` whenever `_run`
returns without raising (`public_agent_bridge.py:799`); the broker accepts on
`ok is True` (`gateway_exec_broker.py:313`) and delivery marks the notification
delivered. Should `delivered:true` require observed platform acknowledgment?

**Independent reasoning.** This is a same-truth problem: absence of a Python
exception in the bridge is not proof that Telegram/Discord accepted the send.
The symphony requires "Redacted evidence records for... bot delivery" and lists
"bot delivery problems" among the operator notifications — i.e. delivery is a
first-class, operator-visible truth, and a false "delivered" corrupts the
dashboard/Raven same-truth contract and suppresses legitimate retries. So I agree
with the *thesis*: bridge completion is processing, not delivery.

The critical reality I verified against the code (and that tempers the plan): the
bridge replays the public turn through **Hermes' native gateway pipeline**
(`adapter.handle_message` → Hermes' own send/edit logic, `:455`,
`_run_telegram:372-462`). The actual Telegram/Discord API send happens deep
inside Hermes' adapter, which the bridge does **not** own. The bridge only
captures a `result_message_id` on its *own* direct send path (the approval-card
send at `:286`, `getattr(result,"message_id","")`), proving send-results ARE
observable where the bridge itself calls the API — but the native-replay path
gives the bridge no structured ack handle today. That is why Codex correctly
rates this **high** and ties it to a live gate: full ack capture needs a hook out
of Hermes' native send path (upstream cooperation), not just local bridge code.

So the honest, fail-closed, *shippable* move splits cleanly into two layers:
(a) immediately stop lying — rename the unconditional flag to `processed:true`
and only assert `delivered:true` where the bridge actually observed an ack;
(b) the full per-send ack capture + outbox delivery-state + `PG-PUBLIC-AGENT-
DELIVERY` live gate is the larger contract change. Critically, (a) must not
silently regress today's behavior into "never delivered" — that would break the
notification-delivery worker's `delivered_at` marking and trigger infinite
retries. So the worker contract must move in lock-step: treat `processed:true`
(no observed ack) as a distinct, non-error "processed, delivery unconfirmed"
state that does NOT mark `delivered_at` but also does NOT hard-retry indefinitely
— bounded by policy.

**Agree / differ from Codex.** Agree with the whole shape: split
`processed` vs `delivered`, require observed Telegram/Discord ack (with redacted
message ids) for `delivered:true`, mark `delivered_at` only on `delivered:true`,
store `delivery_error`/evidence + retry by policy otherwise, add fake-platform
ack/failure tests + a named `PG-PUBLIC-AGENT-DELIVERY` live gate, handle
partial-send as a `partial_platform_ack` incident with no blind retry. **Refine:**
sequence it as two landable steps and protect the retry contract: step 1 (med)
renames to `processed:true` + adds a `delivered:true` ONLY for bridge-owned send
paths that already capture a message id (`:286`), and updates the worker +
`notification_outbox` to record `processed`/`unconfirmed` without false
`delivered_at` and without infinite retry (bounded `processed_unconfirmed`
state); step 2 (high) plumbs an ack hook out of Hermes' native adapter send/edit
to populate `delivered` on the replay path, then wires the live gate. This keeps
us from shipping a flag rename that breaks retry/outbox semantics.

**FINAL PLAN.**
1. Bridge: replace the unconditional `{"ok":true,"delivered":true}` with
   `{"ok":true,"processed":true,"delivered":<bool>,"platform_message_ids":[...]}`
   where `delivered`/ids are populated only from observed send/edit acks the
   bridge captures (today: its own send paths e.g. `:286`). No observed ack →
   `delivered:false` (not an error).
2. Broker `run_gateway_exec_request`: keep accepting on `ok is True` but pass
   `processed`/`delivered`/`platform_message_ids` back to the caller instead of
   collapsing to a bare `(True,"")`.
3. notification_delivery: mark `notification_outbox.delivered_at` ONLY on
   `delivered:true`; on `processed:true && delivered:false` set a
   `processed_unconfirmed` state (redacted `delivery_evidence`), retry per a
   bounded policy (not infinite); a platform send failure → `delivery_error` +
   operator-visible "bot delivery problem" incident. Treat partial multi-send as
   `partial_platform_ack` with recorded ids and no blind retry.
4. Step 2: add an ack callback/return-value hook on the Hermes native adapter
   send/edit used by the replay path so `_run_telegram`/`_run_discord` can
   populate `platform_message_ids` on the replay path too (upstream-coordinated).
5. Named live gate `PG-PUBLIC-AGENT-DELIVERY`: real Telegram + Discord send/edit
   proof that `delivered_at` is set only on true platform ack. Fake-adapter
   ack/failure/partial tests locally.

**Symphony anchor.** Notifications, Incidents, And Evidence:
> "Redacted evidence records for live proof, health runs, upgrade runs, backup
> restore, Stripe events, provider fallback, **bot delivery**, fleet lifecycle..."
> and operator notifications for "**bot delivery problems**."
Also Cross-Surface: dashboard and Raven must show "the same incident state, so a
chat retry and a browser retry do not create competing truths."

**Effort:** high (step 1 med, step 2 high). **Blast-radius:** public bridge,
gateway-exec broker, notification delivery, outbox evidence shape, tests, docs,
and a live Telegram/Discord proof gate. Step 1 fails closed against false
"delivered" without breaking retry/outbox; step 2 + the live gate close the loop.

---

## STANDING DISAGREEMENTS (genuine operator product forks)

1. **Legacy unscoped cross-Captain pod_comms grants: honor-with-advisory vs
   hard-disarm (Decision 2).** Codex would set existing unscoped grants to
   `legacy_unscoped_requires_rescope` and stop them authorizing sends until
   upgraded (fail-closed on the existing grant). I recommend honoring them as
   `legacy_captain_pair` with a re-scope advisory + evidence, and gating
   hard-disarm behind `ARCLINK_POD_COMMS_REQUIRE_SCOPED_GRANTS=1`. This is a
   genuine policy fork: strict-immediately (operator accepts breaking live
   cross-Captain Comms to guarantee scoped grants) vs preserve-state-by-default
   (honor existing intent, tighten only new grants, let the operator opt into
   strict). My default recommendation is preserve-state + opt-in strict; the
   operator owns the call.

2. **Live-only items inherited from the reconciled record (not new here, noted
   for completeness):** the agent-process-helper `setpriv` EPERM-under-cap_drop-ALL
   posture (HIGH pending live proof) and the migration-capture state-root symlink
   reality are CANON-12/CANON-13 live-container questions, not decided by these
   five contract calls; they remain for the named live-proof gates, not operator
   product forks.
