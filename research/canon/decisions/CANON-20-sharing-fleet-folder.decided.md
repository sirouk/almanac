# CANON-20 — Sharing & Fleet Folder — DECIDED (operator-facing final plan)

Adjudicator: Claude Opus 4.8 (1M) FINAL ADJUDICATOR, ArcLink two-model Federation, DECISION mode.
Method: formed an independent view per deferred decision by re-opening the *current* code
(rg/sed), then converged with Codex (GPT-5.5 xhigh). Every plan is anchored to the symphony
north star and fails closed. Where the live code has advanced past the reconciled doc's cited
state, the **current code wins** and the plan is scoped to the genuine residual gap.

Inputs:
- Deferred items: `research/canon/NEEDS_DECISION.md` (## CANON-20)
- Codex proposal: `research/canon/decisions/CANON-20-sharing-fleet-folder.codex.md`
- North Star: `docs/arclink/sovereign-control-node-symphony.md` (North Star, Whole-System Traversal, Sharing, Config/Schema/Migration, Governance And Proof)
- Code reality: `research/canon/reconciled/CANON-20-sharing-fleet-folder.reconciled.md`, `research/canon/sections/CANON-20-sharing-fleet-folder.md`, re-opened against `python/arclink_fleet_share.py`, `python/arclink_provisioning.py`, `python/arclink_control.py`.

## IMPORTANT CODE-DRIFT NOTE (current code > reconciled cite)
The reconciled doc and Codex's proposal both describe an earlier state. Re-opening the live
code shows three of the cited weaknesses are **already remediated**, which narrows every
decision:
- `ensure_hub_repo` now verifies remote reachability with `git ls-remote` and fails closed if
  unreachable (`python/arclink_fleet_share.py:224-242`) — the "returns True without proof" cite is stale.
- `_assert_safe_git_arg` now rejects git remote-helper syntax via
  `_GIT_REMOTE_HELPER_RE = ^[A-Za-z][A-Za-z0-9+.-]*::` (`python/arclink_fleet_share.py:48,138`),
  so `ext::sh -c ...` is blocked (test at `tests/test_arclink_fleet_share.py:363-364`).
- A working-path containment allowlist exists: `_assert_safe_local_working_path` +
  `_safe_local_fleet_roots` (`python/arclink_fleet_share.py:445-471`) closes the `git add -A`
  whole-tree-exfiltration MEDIUM for the env-driven in-pod path.
- The `.corrupt` quarantine now **reintegrates** orphaned files via
  `_restore_quarantined_working_files` (`python/arclink_fleet_share.py:171-189,300-305`) — the
  MEDIUM data-availability facet is addressed.
- Provisioning already renders remote hubs as `ssh://{user}@{host}{root}/.../fleet-shared.git`
  and wires a known_hosts-backed `GIT_SSH_COMMAND` (`python/arclink_provisioning.py:581-611,1059-1093`).

What is **still genuinely open** maps cleanly onto the three deferred decisions below.

---

## DECISION 1 — Full hub URL host/scheme allowlist for remote fleet-share hubs

**[VERDICT: refine]** (Codex is right in direction; scope it to the true residual gap and
de-duplicate validators rather than re-implementing what already ships.)

### Question
Production supports operator-provided remote SSH hubs. The hub-URL guard only blocks
option-injection / remote-helper syntax and (now) checks reachability; it does **not** constrain
which host/scheme a hub ref may use. Should ArcLink add a host/scheme allowlist, and how strict?

### My independent reasoning (code-grounded)
Two validators guard hub refs and they have **drifted apart**:
- `_assert_safe_git_arg` (`arclink_fleet_share.py:123-141`): blocks empty / leading-`-` /
  control chars / remote-helper `scheme::`. No host or scheme allowlist.
- `_clean_git_ref` (`arclink_provisioning.py:105-111`): blocks empty / leading-`-` / control
  chars **only** — it does **not** block remote-helper syntax and has no allowlist.

So a rendered remote ref in provisioning is validated *more weakly* than the same ref at
in-pod sync time. Neither path bounds the host: any reachable `ssh://attacker/...`,
`https://...`, or `file://...` ref that `ls-remote` can reach is accepted, and a wrong/hostile
runtime env value silently redirects a Captain's entire Fleet folder to an unapproved host.
The symphony is explicit that **operators own the fleet and policy** and that remote hub
transport is an operator-gated concern (Sharing section ties remote `ssh`/`https` hub transport
to `GAP-014/015/016`). The right move is exactly Codex's: one shared validator, operator-owned
host allowlist, ssh-only for now (https deferred — it needs a separate token storage/redaction/
rotation story), fail closed on drift, with a named live gate. The only refinement is scope:
do **not** re-add reachability, remote-helper blocking, known_hosts `GIT_SSH_COMMAND`, or
working-path containment — those already ship. Build the missing allowlist and collapse the two
divergent validators into one.

### Agree / differ from Codex
- AGREE: keep operator remote SSH hubs; explicit operator allowlist from private config; ssh-only
  (reject https/file/git/unknown for now); known_hosts-backed fail-closed host checking; keep
  rejecting remote-helper syntax; named live gate `PG-FLEET-SHARE-HUB`.
- DIFFER (refine): Codex's rationale cites the pre-remediation state (`ensure_hub_repo` "accepts
  remote refs without proof", `_assert_safe_git_arg` "only blocks option/control/remote-helper").
  Reachability and remote-helper blocking already exist; known_hosts `GIT_SSH_COMMAND` already
  exists in provisioning. So the plan is narrower than "add a validator": **promote the
  stricter `_assert_safe_git_arg` to be the single shared validator** (provisioning's weaker
  `_clean_git_ref` is the actual hole — it doesn't even block `ext::`), then **layer the host
  allowlist on top of it**.

### FINAL PLAN
1. **Single shared validator.** Add `validate_fleet_share_hub_ref(ref, *, allow_remote, allowlist)`
   in `arclink_fleet_share.py` that subsumes `_assert_safe_git_arg` (empty / leading-`-` /
   control-char / remote-helper) **and** the new host/scheme allowlist. Have
   `arclink_provisioning._clean_git_ref` for fleet-share refs delegate to it (or import it) so
   provisioning stops being the weaker gate. Keep the existing `ls-remote` reachability check in
   `ensure_hub_repo` after validation.
2. **Scheme policy (fail closed).** Local refs must resolve under `ARCLINK_FLEET_SHARE_HUB_ROOT`
   (consistent with `_assert_safe_local_working_path`'s containment style). Remote refs must be
   `ssh://...` or scp-style `user@host:path`. Reject `https`, `http`, `file`, `git`, and unknown
   schemes (https explicitly deferred to a later credential design).
3. **Host allowlist.** New operator config `ARCLINK_FLEET_SHARE_HUB_ALLOWED_HOSTS` (private config,
   comma/`os.pathsep`-separated), defaulting to deny-remote-unless-set. Extract host from
   `ssh://user@host[:port]/path` and scp-style `user@host:path`; require an exact (case-folded)
   match. On miss, raise `ArcLinkFleetShareError`/`ArcLinkProvisioningError` with an operator
   repair hint — never silently proceed. Provisioning already seeds the natural default
   (`ARCLINK_FLEET_SHARE_HUB_SSH_HOST` / `ARCLINK_WIREGUARD_CONTROL_IP`,
   `arclink_provisioning.py:595-600`); the allowlist should accept those by default so the
   shipped single-host path keeps working.
4. **Local regression proof.** Unit tests around the new validator: reject `https://`, `file://`,
   `git://`, `ext::`, an off-allowlist `ssh://attacker/...`; accept an on-allowlist ssh ref and a
   local-root ref. Add a provisioning test that an off-allowlist `ARCLINK_FLEET_SHARE_HUB_URL`
   fails rendering closed.
5. **Named live gate.** `PG-FLEET-SHARE-HUB`: prove `ls-remote` + a redacted
   write/read/delete sentinel against the configured operator hub, evidence redacted. Track it
   alongside the existing `GAP-016` remote-hub-transport line so docs stay in lock-step.

### Symphony anchor (quoted)
North Star — "Operators own the universe: hosts, secrets, fleet, policy, upgrades, backups,
live proof, emergency repair, and product rollout." And Whole-System Traversal — "If any step
cannot say what surface owns it, what state it reads, what state it writes, and how it fails
closed, the symphony is not complete." The operator must own *which hub host is valid*, and a
ref that drifts off-allowlist must fail closed.

### Effort / blast-radius
**med.** Touches the new shared validator + allowlist in `arclink_fleet_share.py`, the
`_clean_git_ref` delegation in `arclink_provisioning.py`, one new private-config env var,
fleet-share + provisioning tests, and the `PG-FLEET-SHARE-HUB` live-proof/GAP tracking. No
schema change. Blast radius is bounded to fleet-share rendering/validation; the default single-
host local-hub path is unaffected because local refs and the provisioning-seeded host stay valid.

---

## DECISION 2 — Distributed fleet-share sync locking and bounded retry policy

**[VERDICT: agree-codex]** (with one small concretization of the surfacing requirement.)

### Question
`sync_member` runs add → commit → fetch → rebase → push inside a fixed `range(2)` loop and
returns terminal `status="error"` after two attempts (`arclink_fleet_share.py:340-409`). Under
contention this can report failure on a healthy hub. Should ArcLink add a distributed
cross-machine lock, and/or change the retry policy?

### My independent reasoning (code-grounded)
The convergence engine is correct and *fails safe by design*: it never force-pushes (push is
plain `HEAD:main`, `:393`), and an unresolvable rebase is surfaced as `conflict` with the local
edit preserved (`rebase --abort`, `:373-381`) rather than clobbered. The only defect is the
fixed 2-attempt bound: under N concurrent writers the loser of each non-fast-forward push race
can exhaust two retries and return `error` even though the hub is healthy — a *spurious failure*,
not a lost write. A true cross-machine distributed lock would require a hub-side lease/broker,
stale-lock recovery, and its own live proof; worse, that broker becomes a new single point of
failure that can block **all** sharing — the opposite of "boringly reliable underneath." Git is
already the convergence authority; the right fix is a bounded, named retry policy with backoff/
jitter (still no force-push, still preserve local commits), plus a per-working-copy nonblocking
lock to prevent same-pod overlap, and one-truth surfacing of exhaustion. This is exactly Codex's
plan and it is symphony-faithful: the Sharing section demands "multi-writer convergence and
conflict surfacing rather than silent loss," and the Whole-System / Notifications standard
demands the same state across surfaces.

### Agree / differ from Codex
- AGREE in full: no distributed lock for this piece; replace `range(2)` with a named bounded
  policy `ARCLINK_FLEET_SHARE_SYNC_MAX_ATTEMPTS` (default 4) + short capped backoff/jitter; no
  force-push; terminal `error` only after preserving local commits; per-working-copy nonblocking
  lock; surface exhaustion through `last_sync_status`/`last_sync_detail` + local status JSON;
  `PG-FLEET-SHARE-SYNC` two-ArcPod convergence/conflict live gate.
- CONCRETIZE (not a disagreement): the public result states **must stay** `synced|conflict|error`
  so no schema/OpenAPI/fixture churn (the member-row `last_sync_*` fields already exist,
  `arclink_fleet_share.py` member writes). "Same truth across surfaces" is satisfied by writing
  the exhaustion reason into `last_sync_detail` so Drive/Code/Raven/dashboard all read it. Keep
  backoff bounded (e.g. cap total added latency to a few seconds) so a 120s `fleet-share-sync`
  interval is never overrun.

### FINAL PLAN
1. Replace the `for _attempt in range(2)` loop bound (`arclink_fleet_share.py:340`) with
   `ARCLINK_FLEET_SHARE_SYNC_MAX_ATTEMPTS` (default 4, clamped to a sane max), adding short
   capped exponential backoff + jitter between attempts. Preserve: plain `HEAD:main` push (no
   `--force`), `rebase --abort` → `conflict` on unresolvable rebase, committed-local-edits
   guarantee before any terminal `error`.
2. Add a per-working-copy **nonblocking** advisory lock (e.g. `flock` on a lockfile under the
   working path) around `sync_member` so two in-pod passes for the same copy don't overlap; if
   the lock is held, return cleanly (skip this pass) rather than racing.
3. Write retry-exhaustion reason into `last_sync_detail` (and keep `last_sync_status="error"`)
   via the existing member-row sync recorder so dashboard/Raven/Drive/Code show one truth.
4. Local proof: a fake-runner test that simulates K consecutive non-fast-forward pushes and
   asserts convergence within `MAX_ATTEMPTS`, plus a test that a genuinely unresolvable rebase
   still returns `conflict` (never clobbers).
5. Named live gate `PG-FLEET-SHARE-SYNC`: two ArcPods writing the same Fleet folder converge,
   and a real conflict surfaces (not silent loss), with redacted evidence.

### Symphony anchor (quoted)
Sharing — "A Captain's own fleet shares one writable **Fleet** folder across every Agent, with
multi-writer convergence and conflict surfacing rather than silent loss." And North Star —
"The system should be boringly reliable underneath and mythic on top" (a sync broker that can
block all sharing violates this; bounded git-native retry preserves it).

### Effort / blast-radius
**med.** Touches `sync_member`, the env-policy plumbing, the per-copy lock, member-row
status/detail recording, and tests/live tooling. **No schema change** — public result states
stay `synced|conflict|error`, so no OpenAPI/status-fixture churn.

---

## DECISION 3 — Dead `paused` share and member `pending` statuses

**[VERDICT: agree-codex]** (remove from the active contract; do not activate now.)

### Question
Schema allows `paused` for shares and `pending` for members
(`arclink_control.py:1174,1187`; validators `ARCLINK_FLEET_SHARE_STATUSES` /
`ARCLINK_FLEET_SHARE_MEMBER_STATUSES` at `:3255-3256`; integrity checks at `:5164-5165`), but
**no code path ever sets them** — `ensure_fleet_share` writes only `active`/(`removed`→`active`)
and `add_fleet_share_member` always inserts `active`. Should ArcLink remove these dead statuses
or activate a pause/pending lifecycle?

### My independent reasoning (code-grounded)
Verified independently: `grep` for `'paused'`/`'pending'` setters in
`python/arclink_fleet_share.py` returns **NONE**; the only repo references to the two validator
constants are in `arclink_control.py` itself (schema + integrity check) — **no test, doc, web,
or OpenAPI surface depends on them**. An unenforced status is a *false system truth*: a surface
could claim a share is `paused` while the in-pod `fleet-share-sync` job keeps pushing, because
sync runs from env and never consults the DB status. The symphony's same-truth-across-surfaces
and fail-closed principles say the contract must not advertise a state the engine ignores.
Activating a real pause lifecycle is strictly worse right now: it needs new API/action-worker/
plugin semantics **and** an enforcement path that actually stops the in-pod sync (a key
revocation or pod-service control path) — none of which exists. So the smallest move to
same-truth is to **remove** the dead statuses from the active contract, gated by an upgrade
preflight that fails closed if legacy rows exist. This is exactly Codex.

### Agree / differ from Codex
- AGREE in full: narrow to `active|removed` for both shares and members; upgrade preflight
  confirms no legacy `paused`/`pending` rows and **fails closed with an operator repair command**
  if any exist (never silently map); do not add a pause lifecycle until there is enforceable
  sync-stop (broker lease / key revocation / pod-service control).
- One caution I add: because schema is a single idempotent `ensure_schema()` with **no version
  ledger / numbered migrations** (symphony Config/Schema/Migration: "no version ledger and no
  numbered/reversible migration history yet"), tightening a `CHECK` constraint requires a
  `*__new` table copy + `RENAME` rebuild (the existing in-place-rebuild pattern). The preflight
  **must** run *before* the rebuild and abort if legacy rows exist, so we never drop a row that
  violates the new constraint. This keeps "preserve state by default" intact.

### FINAL PLAN
1. Change the two `CHECK` constraints to `('active','removed')` for `arclink_fleet_shares`
   (`arclink_control.py:1174`) and `arclink_fleet_share_members` (`:1187`), and the validator
   constants `ARCLINK_FLEET_SHARE_STATUSES` / `ARCLINK_FLEET_SHARE_MEMBER_STATUSES`
   (`:3255-3256`) to `{"active","removed"}`.
2. Add an **upgrade preflight** (before the `*__new` rebuild) that counts rows with status
   `paused`/`pending` in both tables. If any exist, **fail closed** with a clear operator repair
   command (e.g. an `arclink_ctl` subcommand to inspect/resolve them) rather than silently
   coercing — preserves state by default and leaves the operator the decision.
3. Update the two integrity-check rows (`arclink_control.py:5164-5165`) to the new allowed sets
   and update any fleet-share status fixtures/tests accordingly (verified: only
   `tests/test_arclink_fleet_share.py` exercises these tables; no OpenAPI/web dependency).
4. Local regression proof: a schema test that the tightened constraint rejects `paused`/`pending`
   inserts, and a preflight test that legacy rows trigger the fail-closed repair path on an
   old-state fixture.

### Symphony anchor (quoted)
Whole-System Traversal — "Upgrades, backups, restore, incident repair, share revocation,
provider failover, and teardown all preserve state by default and leave redacted evidence of
what happened." And Governance And Proof — "A residual risk stays visible until removed or
explicitly accepted." (Removing the dead, unenforced statuses removes the residual false-truth
risk; the fail-closed preflight preserves state.)

### Effort / blast-radius
**med.** Touches two schema `CHECK` constraints + a `*__new` rebuild, two validator constants,
the integrity-check rows, a new upgrade preflight + operator repair command, and fleet-share
schema/status tests. No web/OpenAPI churn (verified no surface depends on the dead statuses).
Blast radius is contained to the fleet-share tables; the fail-closed preflight prevents any
silent state loss on upgrade.

---

## STANDING DISAGREEMENTS (genuine operator product forks)
None. All three decisions converge to a single code-grounded, symphony-anchored plan; there is
no inter-model conflict and no fork the operator must arbitrate. (Decision 1's "https hub
transport" is intentionally *deferred*, not forked — it is a future credential-design item under
`GAP-016`, not a now-choice. Decision 3's "activate a pause lifecycle later" is contingent on an
enforcement mechanism that does not yet exist, so it is a future-feature gate, not a present
fork.)
