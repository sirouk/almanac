# CANON-21 — Org Profile — FINAL ADJUDICATED DECISIONS

- **Adjudicator:** Claude Opus 4.8 (FINAL ADJUDICATOR, DECISION mode)
- **Codex proposal:** `research/canon/decisions/CANON-21-org-profile.codex.md`
- **Method:** Each deferred item was re-opened in the live code (not the reconciled snapshot). Code wins. The symphony is intent; the code is reality; the plan moves code toward the symphony while failing closed.

## Code-reality note (the module advanced past the reconciled snapshot)

Two facts changed since `CANON-21-org-profile.reconciled.md` was written, and both strengthen the direction of these decisions:

1. **Stale SOUL/identity overlay is now reaped.** `clear_materialized_agent_context` is no longer dead — it has a real caller at `python/arclink_control.py:18938-18940`: when the managed payload's `org_profile_agent_context` is empty/missing, control.py calls `clear_materialized_agent_context(hermes_home)`. So an unmatched active user agent now has its SOUL overlay block cleared, not left stale. The reconciled MEDIUM "stale overlay on teardown" is largely closed.
2. **Apply now locks + rolls back.** `apply_profile` runs inside `_profile_apply_lock(cfg)` (an `fcntl.LOCK_EX` file lock at `python/arclink_org_profile.py:135-143`, taken at `:2228`) and wraps the DB+file fan-out in `try/except BaseException: conn.rollback(); raise` with `conn.commit()` only on success (`:2304-2307`). The reconciled "no concurrency control" and "post-commit DB/file divergence" risks are materially mitigated.

Neither deferred decision is invalidated by this — both become cleaner to land.

---

## DECISION 1 — Should org-profile fan-out include non-`role='user'` or inactive agents?

**[VERDICT: agree-codex]**

### The question
`apply_profile`'s context fan-out, the refresh signal, the SOUL/identity materialization, and stale-slice deletion are all gated to `role='user' AND status='active'`. Is that an intentional contract boundary, or a gap that silently starves operator/curator/inactive agents of org-profile context?

### Independent reasoning (from code + symphony)
The gate is real and consistent, not accidental:
- `_active_agent_rows()` SELECTs `FROM agents a LEFT JOIN agent_identity i ... WHERE a.role = 'user' AND a.status = 'active'` (`python/arclink_org_profile.py:2191-2207`); the fan-out loop iterates exactly those rows (`:2253`).
- The downstream refresh signal repeats the identical gate and fails closed otherwise: `signal_agent_refresh_from_curator()` returns `None` unless `role == "user" and status == "active"` and a non-empty `unix_user` (`python/arclink_control.py:19178-19199`).

This maps cleanly onto the symphony's ownership split. `role='user'` is precisely the enrolled Captain/Crew lane that the symphony says SOUL/context fan-out is for. Operators do not get their host/fleet/policy authority through a Crew SOUL overlay; they own those surfaces directly. Widening fan-out to operator/curator/non-user agents would blur Captain Crew context with operator runtime context — a boundary violation, not a feature. Widening to inactive agents would mutate preserved/retired state, violating "preserve state by default." Excluded agents getting *no new* org-profile material (rather than accidental authority/privacy/host-policy material) is the fail-closed posture. The now-live `clear_materialized_agent_context` reap (`:18940`) further confirms the design intent: when an agent is out of scope, its overlay is cleared, not left to drift.

### Agreement / divergence with Codex
Full agreement. Codex correctly anchors to "Pods, Isolation, And SOUL" and reads the boundary as intentional, fail-closed ownership. The optional helper/report-field rename to make the boundary self-documenting is a positive low-cost clarity move. I add one citation Codex's anchor implies but didn't quote: the refresh-signal gate at `arclink_control.py:19184` is the *second* enforcement point, so a regression must pin both to prevent silent drift between fan-out and refresh.

### FINAL PLAN
1. **Keep the scope as-is.** Do not widen fan-out, SOUL writes, slice writes, stale-slice deletion, or the refresh trigger beyond `role='user' AND status='active'`.
2. **Codify the contract with a regression** in the org-profile test corpus: assert that a seeded non-user agent (e.g. operator/curator) and an `status!='active'` user agent receive (a) no context slice, (b) no stale-slice deletion, (c) no SOUL/identity materialization, and (d) no refresh trigger. Pin both enforcement points (`_active_agent_rows` and `signal_agent_refresh_from_curator`).
3. **Document the boundary** in `docs/org-profile.md` as an explicit, intentional contract: "org-profile context fans out only to active enrolled (`role='user'`) Crew agents; operator/curator/inactive agents are out of scope by design."
4. **Optional (cosmetic-positive):** rename the report field / helper to surface the boundary (e.g. `active_user_agent_fanout`) in the `apply`/`doctor` report so the scope is visible to an operator reading the receipt.
5. **Any operator-org-profile orientation surface is a separate future work item**, not a change to Crew fan-out — it would carry its own RBAC/audit contract backed by `applied.json`. Not in scope here.

### Symphony anchor
"Pods, Isolation, And SOUL" (`docs/arclink/sovereign-control-node-symphony.md:558-563`): "Crew Training should be offered but not mandatory... If a Captain uses Crew Training, ArcLink should project an **additive SOUL overlay and role/context slices without rewriting historical memory**. Agents should receive hot injected, versioned, grounded context from SOUL, organization profile..." The fan-out is the Captain/Crew projection lane; operators own host/fleet/policy elsewhere. This keeps the boundary fail-closed.

### Effort / blast-radius
**Low.** Touches `python/arclink_org_profile.py` (optional field rename), `docs/org-profile.md`, and the org-profile regression tests. Zero behavior change to the shipped fan-out scope; the regression locks the current truth. Medium only if the optional separate operator-orientation surface is ever built — out of scope.

---

## DECISION 2 — Does unmatched slice deletion need an audit/event rail beyond the apply report?

**[VERDICT: refine]** — agree with adding operator-visible evidence; refine the placement and fail-closed wiring.

### The question
On apply, an active user agent that no longer matches a person loses its context slice via `stale_path.unlink()` (`python/arclink_org_profile.py:2260`), recorded only as `stale_context_removed: true` inside the file-local `last-apply.json` report. Does this silent identity/context-state mutation need a shared audit/event rail, and does that cross reporting/notification ownership?

### Independent reasoning (from code + symphony)
The deletion is generated-state cleanup, not user-authored data loss — but it still mutates an agent's identity/context surface, and today the only trace is a `0o600` file on the host (`last-apply.json` at `:2303`). That is a private local receipt, not a shared evidence rail. The symphony's "Notifications, Incidents, And Evidence" section is explicit that this is exactly the kind of background path that must not fail silently and must produce redacted, cross-surface evidence.

The mechanics are already in place to do this cheaply and correctly:
- The unmatched rows are already collected with the exact flag needed: `unmatched_agents.append({... "stale_context_removed": stale_removed})` (`:2262-2269`).
- The ctl apply path `org_profile_apply` already holds the `conn` and already re-iterates `report["unmatched_active_agents"]` to fire refreshes (`python/arclink_ctl.py:963-989`) — so an audit emit per removed slice slots in with no new plumbing.
- The evidence helpers exist on the same connection: `append_arclink_audit(conn, action=..., actor_id=..., target_kind=..., target_id=..., reason=..., metadata=...)` (`python/arclink_control.py:4745-4767`) and `append_arclink_event(conn, subject_kind=..., subject_id=..., event_type=..., metadata=...)` (`:3948-3967`).

Owner is **Operator** — the profile is operator-authored policy, the apply is an operator action, and unmatched-status can disclose roster/policy churn, so it must not be a Captain notification. No external live-proof gate is required; this is local control-plane evidence.

### Agreement / divergence with Codex
Agreement on the core call: add operator-visible audit/event evidence for stale-slice removals; keep `last-apply.json` as the detailed local receipt; no Captain notification by default; redact metadata to `revision`, `agent_id`, reason `org_profile_person_unmatched`, and counts — never private paths or profile body.

I **refine** two things:
1. **Placement.** Codex says "`python/arclink_ctl.py` or the apply wrapper." Make it definite: emit from `org_profile_apply` in `python/arclink_ctl.py`, inside the loop that already walks `unmatched_active_agents` (`:966-967`), not from inside `apply_profile`. Rationale: `apply_profile` is the pure model writer (it takes `conn` but its job is the deterministic fan-out under the file lock); the ctl wrapper is already the orchestration layer that owns refresh side-effects on the same `conn`. Keeping audit emission in the wrapper preserves `apply_profile` as a testable pure transform and keeps all control-plane side-effects (refresh + evidence) in one place. Emit one audit row per `unmatched_active_agents[]` entry where `stale_context_removed` is true.
2. **Fail-closed wiring (Codex flagged this as residual risk — promote it to the plan).** The audit write must not be swallowed. Either (a) write it on the same `conn` and let any failure raise into the apply/refresh failure path (surfaced via `report["refresh_failures"]`), or (b) wrap it like the existing refresh block and append to `refresh_failures` on exception. Do **not** silently `except: pass`. The whole point of this decision is "never fail silently"; a swallowed evidence write would reintroduce the exact gap.

I also keep Codex's correct scoping: evidence is for *removals*, not for ordinary matched re-writes. The matched case overwrites context (now also idempotent + reaped on unmatch), but the silent **deletion** of an identity surface is the action that warrants a shared evidence row.

### FINAL PLAN
1. In `python/arclink_ctl.py` `org_profile_apply`, after `apply_profile` returns, iterate `report["unmatched_active_agents"]`; for each entry with `stale_context_removed == True`, call `append_arclink_audit(conn, action="org_profile_context_unlinked", actor_id=actor, target_kind="agent", target_id=agent_id, reason="org_profile_person_unmatched", metadata={"revision": report["revision"], "stale_context_removed": True})`. Optionally also `append_arclink_event(conn, subject_kind="agent", subject_id=agent_id, event_type="org_profile_context_unlinked", metadata={"revision": ...})` so Raven/dashboard evidence readers see the same state as the CLI.
2. **Redaction:** metadata carries `revision`, `agent_id` (as `target_id`), the fixed reason, and counts only — never `context_path`, never profile body. (The `unmatched_active_agents[]` row contains `context_path`; do NOT forward it into audit metadata.)
3. **Fail-closed:** if the audit/event write raises, surface it as an apply/refresh failure (append to `report["refresh_failures"]` or let it raise) — never swallow.
4. **No Captain notification.** Operator-only evidence rail. Roster/policy churn stays operator-scoped.
5. **No new table.** Reuse `arclink_audit_log` / `arclink_events`.
6. Add a regression: apply a profile that unmatches a previously-matched active user agent; assert exactly one `arclink_audit_log` row with `action='org_profile_context_unlinked'`, `target_id=<agent_id>`, no path/body in metadata; and assert a forced audit-write failure propagates rather than being silently dropped.

### Symphony anchor
"Notifications, Incidents, And Evidence" (`docs/arclink/sovereign-control-node-symphony.md:979-999`): "ArcLink should never fail silently. Every important background path should have an owner-visible state... **Dashboard and Raven views of the same incident state**... **Redacted evidence records**... No raw stack traces, secrets, private file paths, or prompt/completion payloads in public artifacts." The audit/event row makes the silent unlink owner-visible and cross-surface; the redaction constraint forbids carrying `context_path`/profile body.

### Effort / blast-radius
**Medium.** Touches `python/arclink_ctl.py` (the emit + fail-closed wiring), reuses existing helpers in `python/arclink_control.py` (no schema change), and org-profile tests. Optional, additive read-side wiring in any dashboard/Raven evidence reader that chooses to display the new `event_type`. No change to `apply_profile`'s pure transform or to fan-out scope. Blast radius is confined to the apply orchestration path; the worst regression mode (a swallowed evidence write) is exactly what the fail-closed requirement prevents.

---

## Standing disagreements / operator product forks
None. Both decisions are clear engineering calls grounded in symphony + code, not product forks. Codex's recommendations are directionally correct on both; Decision 1 is ratified as-is plus a codifying regression, Decision 2 is ratified with tightened placement and a promoted fail-closed requirement.
