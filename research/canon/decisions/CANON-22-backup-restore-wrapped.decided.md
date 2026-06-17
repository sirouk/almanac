# CANON-22 — Backup / Restore / Lifecycle / Wrapped — DECIDED (final adjudication)

**Adjudicator:** Claude Opus 4.8 (1M) — Federation DECISION mode.
**Counterpart proposal:** `research/canon/decisions/CANON-22-backup-restore-wrapped.codex.md` (Codex GPT-5.5 xhigh).
**Method:** Formed an independent view per decision by re-opening the cited code in `/root/arclink`
on branch `arclink` (Read/rg/sed), then converged with Codex. Symphony is intent; code is reality;
the plan moves code toward the symphony while failing closed.

Both deferred items are *real* and *worth doing*. Neither is a blocking defect — the repair campaign
already landed the HIGH duplicate-report-storm fix, the 404 visibility fix, and the Hermes-session
eligibility fix (`research/canon/reconciled/...` Repair status block: `bf7e201`). These two are the
remaining "needs operator state-path / config-contract decision" items. Both converge to **agree /
refine** — no genuine product fork survives scrutiny.

---

## DECISION 1 — Quiet-hours local/DST semantics need a timezone/config contract

**[VERDICT: refine]** (Codex's direction is correct; I tighten the fail-closed posture and scope.)

### The question
`next_attempt_after_quiet_hours` (`python/arclink_wrapped.py:880`) computes the next safe delivery time
for a `captain-wrapped` notification. Its docstring says "the first supported **local** quiet-hours
boundary after now," and the deploy prompt literally asks for "Organization quiet hours **in local
time**" (`bin/deploy.sh:4729`). But the implementation is UTC-only: `_parse_dt` normalizes `now` to UTC
(`arclink_wrapped.py:86`, `.astimezone(timezone.utc)`), then `current.replace(hour=start_hour, ...)`
(`:884-885`) stamps the configured wall-clock window onto the **UTC** clock. So a `22:00-08:00` quiet
window configured by an operator in `America/New_York` is actually applied as 22:00-08:00 **UTC** — off
by 4–5 hours, and DST-unaware. The code does not read `ARCLINK_ORG_TIMEZONE` at all (`:881` reads only
`ARCLINK_ORG_QUIET_HOURS`).

### My independent reasoning (grounded in re-opened code)
The config contract Codex points to is **already fully built on the operator side** — I verified it end
to end:
- `ARCLINK_ORG_TIMEZONE` defaults to `Etc/UTC`, is **IANA-validated** at deploy time via
  `zoneinfo.available_timezones()` (`bin/deploy.sh:878-890`, `validate_org_timezone`), and is
  **persisted** into the runtime config by `emit_runtime_config()` (`bin/deploy.sh:2346`, `write_kv`).
- `ARCLINK_ORG_QUIET_HOURS` is collected with an "in local time" prompt and a strict `HH:MM-HH:MM`
  validator (`bin/deploy.sh:892-906`, `:4729`) and persisted at `:2347`.
- Both land in the control-plane runtime env that the Wrapped container inherits: the `arclink-wrapped`
  docker job runs with `environment=env` (`python/arclink_provisioning.py:1316`), and `env` is the
  control-plane runtime env sourced from `emit_runtime_config`'s output. So `ARCLINK_ORG_TIMEZONE` is
  **reachable at runtime today** — the only missing link is the consumer reading it.
- `zoneinfo` is present (Python 3.10.12 in-repo; `ZoneInfo("America/New_York")` resolves).

So this is not a new config knob — it is wiring an **existing, operator-owned, already-validated,
already-persisted** value into the one runtime function that silently ignores it. That is squarely
"surfaces stay in lock-step / same truth across surfaces": the operator was promised local-time quiet
hours by the prompt and the docstring, and the runtime quietly does UTC. Closing that gap is correct.

**Where I diverge from Codex — the fail-closed posture.** Codex says "If quiet hours are configured but
malformed, **or the timezone is invalid**, fail closed by raising `ArcLinkWrappedError` instead of
delivering immediately." I split that:
- **Malformed quiet-hours** must NOT raise. Today `_parse_quiet_hours` (`:875`) returns `None` on a
  non-matching string, and the function returns "send now." Quiet-hours is an *optional* policy
  (deploy default is empty). A garbled note appended after the window (the validator explicitly allows
  `22:00-08:00 weekdays`) must degrade to "no window," not block delivery. Raising here would convert an
  optional-policy typo into a Wrapped outage. Keep the current `None → send now` behavior.
- **Invalid timezone *when quiet-hours is configured*** is the real fail-closed case, and here I agree
  with Codex but for a sharper reason: deploy already IANA-validates the TZ, so an invalid
  `ARCLINK_ORG_TIMEZONE` at *runtime* means the persisted config drifted or was hand-edited — a
  degraded-config signal. For a *quiet-hours evaluator*, "fail closed" means **never send into a window
  you cannot evaluate**. Raising `ArcLinkWrappedError` is the correct fail-closed move because the
  enqueue is wrapped in the scheduler's try/except (`run_wrapped_scheduler_once` → `_record_wrapped_failure`
  with the now-landed backoff `_FAILED_RETRY_BACKOFFS`, `arclink_wrapped.py:47-52`): the report is
  **preserved** (the `generated` row stays), a `failed` row is booked, the operator gets the
  persistent-failure notice after 3 attempts, and **nothing is delivered during a possibly-quiet
  window**. That is "preserve state by default + leave redacted evidence + FAILS CLOSED" exactly.
- **Empty/unset TZ** must behave as today: `Etc/UTC` (the deploy default), i.e. current UTC math is the
  correct answer when no local TZ is configured. No raise.

### Final plan (code-level)
1. In `next_attempt_after_quiet_hours` (`python/arclink_wrapped.py:880`):
   - After parsing `quiet_hours` (keep the existing `None → _iso(current)` early return — malformed/empty
     stays "send now"),
   - Read `tz_name = os.environ.get("ARCLINK_ORG_TIMEZONE", "").strip() or "Etc/UTC"`.
   - Resolve `from zoneinfo import ZoneInfo, ZoneInfoNotFoundError`; `tz = ZoneInfo(tz_name)`. On
     `ZoneInfoNotFoundError`/`ValueError` **and quiet_hours is configured**, raise `ArcLinkWrappedError`
     (fail closed — do not fall back to UTC, do not send). (Tz failure with no quiet window is
     unreachable because we already returned.)
   - Convert: `local = current.astimezone(tz)`; compute `start`/`end` via `local.replace(hour=..., ...)`
     (DST-correct because `ZoneInfo` recomputes the offset for that wall time); keep the existing
     same-time / `start<end` / overnight branch logic but in **local** terms; then convert the chosen
     boundary back with `.astimezone(timezone.utc)` before `_iso(...)`. **Storage stays UTC** —
     `notification_outbox.next_attempt_at` remains an ISO-UTC string, so the downstream delivery claim
     (CANON-23) is unchanged.
   - Note the DST-fold/gap edge: an overnight boundary that lands in a spring-forward gap should resolve
     via `ZoneInfo`'s default (`fold=0`) — acceptable; document it, do not over-engineer.
2. Fix the stale framing in the existing test name/comment if needed; the function's UTC-storage contract
   is unchanged so `test_wrapped_delivery_queue_respects_quiet_hours_and_marks_cadence`
   (`tests/test_arclink_wrapped.py:406`) still asserts a UTC `next_attempt_at` — that test uses no
   `ARCLINK_ORG_TIMEZONE`, so it must keep passing unchanged (proves the `Etc/UTC` default path).
3. Add local regression tests (no live send — delivery remains downstream `PG-BOTS`):
   - `Etc/UTC` default == current behavior (unchanged window).
   - `America/New_York` **summer (EDT)** and **winter (EST)** — same `22:00-08:00` string yields
     different UTC boundaries, proving DST-correctness.
   - An overnight window crossing a DST transition night.
   - **Invalid `ARCLINK_ORG_TIMEZONE` with quiet-hours set → raises `ArcLinkWrappedError`** (fail closed).
   - Malformed/garbled quiet-hours string → returns "send now" (no raise).
4. Doc touch: confirm `docs/arclink/` quiet-hours/backup-restore copy states the TZ contract
   (`ARCLINK_ORG_TIMEZONE` is the canonical zone for `ARCLINK_ORG_QUIET_HOURS`, storage is UTC).

### Symphony anchor
- Primary — **Configuration, Schema, And Migration**: "Generated config includes enough version/release
  context to detect stale, missing, deprecated, or incompatible values before services start." The
  operator-validated `ARCLINK_ORG_TIMEZONE` is the canonical, already-persisted value; the runtime must
  honor it, and a runtime-invalid value (config drift) must be detected and fail closed.
- Reinforcing — **Cross-Surface Experience Standard** / North Star "same truth across surfaces": the
  deploy prompt and the docstring both promise *local* quiet hours; the runtime must match the surface.
- Reinforcing — North Star step 10: background paths "preserve state by default and leave redacted
  evidence" and the Whole-System Traversal close: "how it fails closed." Raising on un-evaluatable TZ
  preserves the generated report, books a failure with backoff, and never delivers into a quiet window.

### Effort / blast-radius
**Effort: med.** Touches one function in `python/arclink_wrapped.py`, its tests, and a doc line. **No DB
migration, no schema change, no new config knob, no compose change** (env already flows). Blast radius is
contained to Wrapped scheduling; UTC storage contract and the CANON-23 delivery seam are untouched.
Residual: actual Telegram/Discord send timing remains `PG-BOTS`; this fixes only local scheduling.

---

## DECISION 2 — Backup reconcile needs script-owned single-writer locks

**[VERDICT: refine]** (Codex's "make the mutating script the lock owner" is right; I refine the mechanism
to the codebase's existing `flock` idiom and tighten which lock moves where to keep blast radius low.)

### The question
Neither backup lane enforces single-writer at the point of mutation:
- **Shared/control lane** (`bin/backup-to-github.sh`): the archive-then-`--force-with-lease` reconcile
  (`:51-52`) and the steady-state push (`:138`) rely entirely on a **comment** asserting "a single-writer
  timer on this host" (`:135-137`). The script can also be run manually / by a repair path concurrently
  with the systemd timer, and two writers can both archive + force-align unrelated history.
- **Agent-home lane** (`bin/backup-agent-home.sh`): the only lock lives in the **Python cron wrapper**
  `bin/install-agent-cron-jobs.sh` (`acquire_lock` at `:132`, taken in `main()` at `:177` on
  `hermes_home/state/agent-home-backup/.backup.lock`, emitting a `busy` status when held). A **direct
  `backup-agent-home.sh` run bypasses that lock entirely** — the script itself, which is the true owner
  of the local repo + remote branch mutation, holds nothing.

So today the single-writer guarantee is owned by the *scheduler* (timer/cron), not the *script*, and
every non-scheduler entrypoint (manual op, repair, direct invocation) defeats it.

### My independent reasoning (grounded in re-opened code)
The symphony is explicit: backups are **operator-owned** ("Operators own ... backups") and "Backup cannot
mean 'files were copied once'" — it must be *provably* safe state, and North Star step 10 requires these
paths "preserve state by default and leave redacted evidence." A force-with-lease race that double-archives
or aligns the remote against a stale lease is exactly the "destroying state / surprising the Captain"
failure the Backup section warns against. The script is the local source owner of the local repo and the
remote branch; the **owner must serialize all entrypoints**, not delegate that to whichever scheduler
happens to call it. Codex's framing is correct.

I verified the codebase already has a **canonical `flock` idiom** for exactly this — non-blocking, with
graceful degradation when `flock` is unavailable: `bin/deploy.sh:2711-2723` (`flock -n` on an FD, warn-and-
continue if `flock` missing), and the same pattern in `bin/pins.sh:63-69`,
`bin/install-operator-hermes-home.sh:28`, `bin/pdf-ingest.sh:37`. So this is **not new infrastructure** —
it is applying an existing, proven shell pattern to two scripts that lack it. That keeps the change boring-
and-reliable-underneath.

**Where I refine Codex:**
- **Mechanism — use `flock(1)` on an FD, the bin/ idiom**, not a hand-rolled lockfile, and **match
  `deploy.sh`'s graceful-degradation**: if `flock` is unavailable, warn and proceed (do not hard-fail a
  backup just because `flock` is missing) — the timer/cron single-writer remains the fallback exactly as
  today, so we never *regress* availability. Codex's prose says "non-blocking `flock`" which I endorse;
  I'm pinning it to the established `flock -n 9` + `command -v flock` guard so it reads like the rest of
  the tree.
- **Agent lane — collapse to ONE authoritative lock, don't nest.** Move the single-writer guarantee into
  `backup-agent-home.sh` itself (lock taken inside the script before any local-repo mutation/reconcile/
  push), and have the cron wrapper **delegate** rather than hold its own competing lock. I prefer
  **keeping the existing lock path** `${HERMES_HOME}/state/agent-home-backup/.backup.lock` (already the
  cron wrapper's path) so the wrapper and the script contend on the **same** lock — that way a direct
  script run and a cron run mutually exclude. Concretely: the script acquires `flock -n` on that path; the
  wrapper either (a) stops taking its own `fcntl` lock and lets the script own it, or (b) keeps taking it
  but on the **same** path so they nest harmlessly on one file. Option (a) is cleaner (one owner). Codex's
  env-overridable `AGENT_BACKUP_LOCK_FILE` default is fine but **default it to the existing path**, not a
  new `.backup.lock` location, to avoid two-locks-different-files.
- **Shared lane — add `flock -n` around the mutation+reconcile+push critical section** in
  `backup-to-github.sh`, default lock at `${ARCLINK_BACKUP_LOCK_FILE:-$STATE_DIR/locks/arclink-priv-backup.lock}`
  (`STATE_DIR` is `common.sh:223`). `mkdir -p "$(dirname "$lock")"` first. This is the lane with **zero**
  current serialization, so it is the higher-value half of this decision.
- **Held-lock behavior — scheduled no-op, not error.** If the lock is held: make **no** git/local/remote
  mutation, write a redacted `busy`/`skipped` status line, and exit 0 (success, did-nothing). This
  matches the cron wrapper's existing `busy` semantics (`install-agent-cron-jobs.sh:184-189`) and
  preserves "fail closed" correctly — a held lock means *another writer owns it*, so the safe action is to
  decline, not to force. Blocking locks are rejected (a hung backup must not stall the timer/cron
  indefinitely) — agree with Codex.
- **Lock files must never enter a backup.** The shared lock under `$STATE_DIR` must be excluded from the
  `backup-to-github.sh` commit tree (it already excludes deploy key/known-hosts and gitignored entries,
  `:60-120`; add the lock path / ensure `$STATE_DIR/locks` is excluded). The agent lock lives under
  `state/agent-home-backup/` (the backup *repo* dir, not the curated source set), so it is already outside
  the curated allowlist — verify, don't assume.
- **Scope guard — host-local only.** No distributed/remote lock now. Cross-host use of the same backup
  remote stays operator-disallowed; a future brokered lease is out of scope. Agree with Codex.

### Final plan (code-level)
1. **`bin/backup-to-github.sh`**: wrap the local-repo staging + `reconcile_backup_git_remote_branch` +
   push block (currently `:60-140`) in a `flock -n` critical section using the `deploy.sh:2711-2723`
   pattern; lock path `${ARCLINK_BACKUP_LOCK_FILE:-$STATE_DIR/locks/arclink-priv-backup.lock}`;
   `mkdir -p` its dir; if not acquired → emit redacted `busy` line, exit 0; if `flock` missing → warn +
   proceed. Exclude `$STATE_DIR/locks` from the commit tree.
2. **`bin/backup-agent-home.sh`**: acquire `flock -n` on
   `${AGENT_BACKUP_LOCK_FILE:-$HERMES_HOME_TARGET/state/agent-home-backup/.backup.lock}` (the existing
   cron-wrapper path) before any mutation; held → redacted `busy`, exit 0; `flock` missing → warn +
   proceed.
3. **`bin/install-agent-cron-jobs.sh`**: stop holding its own `fcntl` lock (`:132,:177`) OR point it at
   the **same** lock file as the script. Preferred: remove the wrapper's lock and let the script own it
   (single authoritative owner); keep the wrapper's `busy`-status emission by reading the script's exit/
   status. One lock, not nested competing locks.
4. **Optional cleanup (low priority, not required):** `reconcile_backup_git_remote_branch` is duplicated
   verbatim in both scripts (`backup-to-github.sh:13-54`, `backup-agent-home.sh:101-142`) — record LOW
   R-dup. If a shared `common.sh` helper is cheap, factor it; otherwise leave it and note the drift risk.
   Not gating this decision.
5. **Tests:** extend the existing backup regressions (`tests/test_backup_git_regressions.py`,
   `tests/test_agent_backup_regressions.py`) with a **lock-held → no-mutation, busy-status, exit-0**
   case per lane (hold the lock from a helper process, run the script, assert no commit/push and a `busy`
   line). Add a shell-syntax / dry-run check. These run in CI via the all-`tests/test_*.py` workflow
   (`.github/workflows/install-smoke.yml`).

### Symphony anchor
- Primary — **Backup, Restore, And Data Lifecycle**: "Backup cannot mean 'files were copied once.' It must
  mean the Operator can prove recoverability without surprising the Captain or destroying state." A
  script-owned single-writer lock is what makes the force-with-lease reconcile safe under manual/repair
  concurrency, so the remote is never raced into a double-archive / stale-lease align.
- Reinforcing — North Star: "Operators own the universe: hosts, secrets, fleet, policy, upgrades,
  backups..." and step 10 "Upgrades, backups, restore ... preserve state by default and leave redacted
  evidence." The held-lock `busy` no-op + redacted status is the evidence; declining-not-forcing is the
  fail-closed.
- Reinforcing — North Star "boringly reliable underneath": reuse the existing `flock` idiom
  (`deploy.sh`/`pins.sh`/`pdf-ingest.sh`), not a new locking scheme.

### Effort / blast-radius
**Effort: med.** Touches `bin/backup-to-github.sh`, `bin/backup-agent-home.sh`,
`bin/install-agent-cron-jobs.sh`, and two backup regression tests; reuses the `flock` idiom already in
the tree. **No DB, no schema, no config knob** (lock paths derive from existing `STATE_DIR` /
`HERMES_HOME` with optional `*_LOCK_FILE` overrides). Blast radius: the change is a *guard* — when no
contention exists (the steady-state timer/cron case) behavior is byte-identical to today; it only changes
behavior under concurrent entrypoints, which is the bug. The graceful-degrade-on-missing-`flock` path
prevents any availability regression. Live recoverability remains `PG-BACKUP`.

---

## STANDING DISAGREEMENTS (genuine operator product forks)

**None.** Both decisions converge to a single recommended plan. There is no product fork the operator
must arbitrate — these are reliability/correctness fixes to existing, operator-owned config and backup
ownership, not a choice between two valid product behaviors.

Two micro-choices exist inside Decision 2 that are *implementation taste*, not product forks, and I have
already picked the recommended option (so they are not booked as standing disagreements):
- Agent-lane lock ownership: remove the wrapper's lock and let the script own it (recommended) vs. keep
  both on the same lock file. **Recommended: script owns it (one authoritative lock).**
- Shared-lane lock path env var name `ARCLINK_BACKUP_LOCK_FILE` (recommended, namespaced) — operator may
  rename; cosmetic.
