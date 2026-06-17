# CANON-22 — Backup / Restore / Lifecycle / Wrapped — ADVERSARIAL VERIFY

Verifier: independent adversarial skeptic. Method: re-opened every target file and every
cited consumer/producer/schema end; did not trust the record's citations.

Files re-read in full: `python/arclink_wrapped.py` (1179 lines, confirmed by `wc -l`),
`bin/backup-agent-home.sh`, `bin/backup-to-github.sh`, `bin/configure-agent-backup.sh`,
`bin/arclink-restore-smoke.sh`, `bin/arclink-wrapped.sh`. Adjacent ends re-read:
`python/arclink_notification_delivery.py` (1733-1944), `python/arclink_control.py`
(schema 745-758, 970, 1738-1750; `fetch_undelivered_notifications` 9411-9440),
`bin/common.sh` (218-232, 318-321, 454-455, 1296-1483), `bin/install-agent-cron-jobs.sh`,
`systemd/user/arclink-github-backup.{service,timer}`, `python/arclink_provisioning.py:1315`,
`bin/docker-job-loop.sh:9-11`, plus callers in api_auth/dashboard/public_bots.

## VERDICT: TRUSTWORTHY WITH MATERIAL ADDITIONS

The record's load-bearing claims hold up under independent re-verification. Every seam it
marked both-ends-verified is genuinely wired, and its citations land where it says. BUT the
record under-scopes two of its own MEDIUM risks (the 404 fail-open is NOT confined to the
agent-home lane), misses a HIGH-impact perpetual-regeneration defect on the
generate→enqueue boundary, and never mentions the TOFU host-key trust gap. The record is a
reliable map; it is not complete on the unhappy paths.

---

## A. CLAIMS RE-CONFIRMED (refuted=false, independently re-verified in code)

1. **Seam 1 — captain-wrapped outbox round-trip is fully wired.** Producer
   `arclink_wrapped.py:921-936` inserts `notification_outbox(target_kind='captain-wrapped',
   target_id, channel_kind, message, extra_json={report_id,user_id,period,period_start,
   period_end,novelty_score,render_kind})`. Consumer `arclink_notification_delivery.py:1803-1825`
   reads `row.channel_kind`/`row.target_id`/`row.message`/`extra.user_id`; `_mark_wrapped_report_delivered`
   (`:1833-1855`) reads `extra.report_id` and flips status to `delivered` guarded by
   `status IN ('generated','delivered')`. Rows ARE actually fetched: `fetch_undelivered_notifications`
   (`arclink_control.py:9411-9440`) only excludes `user-agent`/`curator`, NOT `captain-wrapped`,
   and `deliver_row`→`_mark_wrapped_report_delivered` is reached on the success path
   (`arclink_notification_delivery.py:1939-1940`). Keys match; consumer uses `.get()` defaults
   for keys the producer omits, so no break. CONFIRMED.

2. **target_id prefix contract (telegram).** Producer emits `tg:<id>`
   (`arclink_wrapped.py:830-832`); consumer strips `tg:` via `_strip_public_channel_prefix(target_id,"tg")`
   (`arclink_notification_delivery.py:1281,287-292`). Match. CONFIRMED.

3. **Seam 2 — operator persistent-failure routing.** Producer `arclink_wrapped.py:988-1010`
   (`target_kind='operator', channel_kind='tui-only'`); consumer `arclink_notification_delivery.py:1742`
   handles `operator`, and the tui-only branch returns `None` (`:1773-1774`) → row marked
   delivered, no external send. CONFIRMED (including the tui-only body the record marked "partial").

4. **Seams 3/4/5 producers.** `systemd/user/arclink-github-backup.service` ExecStart is
   `%h/arclink/bin/backup-to-github.sh` (no args); timer `OnUnitActiveSec=1h`. Cron installer
   `bin/install-agent-cron-jobs.sh:194` runs `[backup_script, hermes_home]` with
   `env["HERMES_HOME"]` (`:192`), `SCHEDULE_MINUTES=240` (`:45`), `acquire_lock` (`:132,:177`).
   Provisioning `arclink_provisioning.py:1315` =
   `["./bin/docker-job-loop.sh","arclink-wrapped","300","./bin/arclink-wrapped.sh","--json"]`;
   loop shifts 2 (`docker-job-loop.sh:9-11`); `arclink-wrapped.sh:13` execs python with `"$@"`;
   `main()` honors `--json` (`arclink_wrapped.py:1165,1170`). CONFIRMED.

5. **Schema/CHECK seam (CANON-01).** `notification_outbox` PK `id INTEGER AUTOINCREMENT`
   (`arclink_control.py:745-758`); `arclink_users.wrapped_frequency CHECK IN (daily,weekly,monthly)`
   (`:970`); `arclink_wrapped_reports` status `CHECK IN (pending,generated,delivered,failed)`
   (`:1744`). Producer `INSERT` column/placeholder counts balance (verified `set_wrapped_frequency`
   audit insert: 8 columns, 2 literals, 6 placeholders, 6 values). CONFIRMED.

6. **Redaction-first.** Persisted ledger is `_redact_any`'d at write (`arclink_wrapped.py:726`);
   `scoped_ledger` is also pre-redacted at `:710`; rendered text redacted in `_render_report`
   (`:618`). Double-redaction is idempotent. CONFIRMED (completeness still depends on the
   CANON-23 regex library, not fuzzed — record acknowledges this).

7. **Two-phase verify is a real gate, fail-closed.** `verify_backup_git_access`
   (`configure-agent-backup.sh:287-323`) does a real `git ls-remote ... HEAD` (read) and
   `git push --dry-run` (write) and `return 1` on either failure; under `set -e` the bare call
   at `:326` aborts before `write_backup_state`. CONFIRMED fail-closed.

8. **restore-smoke is honestly local-only.** Remote sources refused (`:74-78`); no
   import/call of `arclink_executor`, no Docker/systemd; shells `tar`/`git archive`/`sqlite3`
   only; SQLite path runs `PRAGMA quick_check` read-only (`:153-171`). CONFIRMED — seam 8
   (asserted absence) holds.

9. **Line count / tracking.** `wc -l` = 1179 (record's "1179" exact; prior-doc "~1180" is the
   stale one). All six files tracked; both systemd units tracked. CONFIRMED.

---

## B. NEW GAPS BOTH THE RECORD AND PRIOR DOCS MISSED

### GAP-1 (HIGH) — generate-succeeds-then-enqueue-throws causes UNBOUNDED duplicate generated reports
`run_wrapped_scheduler_once` (`arclink_wrapped.py:1030-1056`) does, inside one try block:
`generate_wrapped_report` (commits a `generated` row, `:719-728`) → `summary["generated"]++`
→ `enqueue_wrapped_report_notification` (`:1043`). If `enqueue` raises AFTER the generated
row is committed (e.g. an sqlite error on the outbox INSERT, a `float(row["novelty_score"])`
coercion failure `:918`, or any exception in `_captain_delivery_channel`), the `except` at
`:1046` writes a `failed` row via `_record_wrapped_failure` with a LATER `created_at`.
On the next tick, `list_due_wrapped_captains` selects the single latest row per period by
`created_at DESC, report_id DESC LIMIT 1` (`:1079-1088`); the later `failed` row SHADOWS the
valid `generated` row → `reason="failed_retry"` (`:1091`). `failed_retry` BYPASSES the
`_has_wrapped_signal` gate (gate only runs `if reason == "missing"`, `:1095`). So every tick:
a brand-new `generated` report (`wrap_<random hex>` PK, `:132`) is created and committed, then
enqueue throws again, appending another `failed` row. Result: monotonic growth of duplicate
`generated` reports + `failed` rows for the period, every 300s, forever, with NO backoff.
The record's "No backoff on failed-report retry" MEDIUM (`:1091`) only contemplated a report
that NEVER generates; it explicitly asserts (self-check #2) that failure rows "cannot clobber a
generated row (different primary key)" — TRUE but irrelevant: the failure row does not clobber,
it SHADOWS in the due query, and the system keeps minting fresh generated rows. This is a
strictly worse failure mode than the record describes.
Cite: `arclink_wrapped.py:1043-1056,1079-1094,1095`.

### GAP-2 (MEDIUM) — 404 fail-open is NOT confined to the agent-home lane; the control-plane lane shares it
The record scopes its "404→proceed" MEDIUM to `backup-agent-home.sh:88-90` /
`configure-agent-backup.sh:165-167` and implies the arclink-priv lane is protected by
`require_private_github_backup_remote`. It is NOT. `require_private_github_backup_remote`
(`common.sh:1377-1398`) only `return 1`s on `public`, `error:*`, and `unsupported`; the
404 result `non-public-or-missing` (`common.sh:1360-1362`) falls through to the implicit
`return 0` (success). `backup-to-github.sh:131` calls this helper before pushing, so a repo
that 404s because the deploy key lacks read scope, or a typo'd owner/repo that does not exist,
is NOT blocked at the control-plane visibility gate either. Both lanes share the identical
fail-open-on-404 branch. The record's MEDIUM should be re-cited to `common.sh:1390-1397` in
addition to the agent-home scripts.
Cite: `common.sh:1360-1362,1390-1397`; `backup-to-github.sh:131`.

### GAP-3 (LOW/MEDIUM) — TOFU host-key trust undermines StrictHostKeyChecking on BOTH lanes
`prepare_backup_git_transport` exports `GIT_SSH_COMMAND` with
`StrictHostKeyChecking=yes` (`common.sh:1482`) but the known_hosts file it points at is
auto-populated by `ensure_backup_git_known_hosts` via `ssh-keyscan -H "$host"`
(`common.sh:1455`) with NO verification against GitHub's published key fingerprints — pure
trust-on-first-use. A MITM present at first keyscan gets their host key pinned permanently.
`ssh-keyscan`'s exit status is also unchecked (`:1455`, no `|| return 1`); if it writes nothing
the later push fails closed (StrictHostKeyChecking), so the net is fail-closed on connectivity
but fail-open on key authenticity. Affects `backup-agent-home.sh:252` and `backup-to-github.sh:133`.
The record's security-posture section never mentions host-key trust.
Cite: `common.sh:1450-1456,1482`.

### GAP-4 (INFO) — `extra_json.render_kind` is CONFIRMED dead metadata
The record left this OPEN (open question #1, self-check #1). Repo-wide `rg "render_kind"` over
`python/` and `web/` returns the producer `arclink_wrapped.py:919` and NOTHING ELSE. No
consumer reads it. Resolved: dead metadata, harmless.
Cite: `arclink_wrapped.py:919` (sole occurrence).

---

## C. SEVERITY RE-CALIBRATION

- Record's "No backoff on failed-report retry" (MEDIUM) is correct for pure-generation
  failures but UNDER-states the generate-then-enqueue-throw variant, which is HIGH-impact
  (unbounded duplicate generated rows). See GAP-1.
- Record's "Visibility check 404→proceed" (MEDIUM) is correctly rated but MIS-SCOPED — it
  applies to the control-plane lane too. See GAP-2.
- Record's "tar path validation only covers archive sources" (LOW) is accurate; I add that
  `validate_tar_members` inspects member NAMES only (`arclink-restore-smoke.sh:104-113`), never
  link targets, but default GNU tar refuses traversal through symlinks and stores symlinks
  in-place, so containment holds. LOW is correctly calibrated.

---

## D. CLAIMS ATTACKED BUT NOT REFUTED

- "Wrapped never deletes/over-writes a generated report" (self-check #2): TRUE as stated
  (distinct PK). Not refuted — but see GAP-1 for the shadowing issue it misses.
- "backup-to-github excludes the deploy key" (self-check #3): TRUE. Default key path
  `$ARCLINK_HOME/.ssh/...` is the PARENT-of-repo (`common.sh:219`), outside
  `$ARCLINK_PRIV_DIR` (`:220`), so it is never staged; the in-tree exclusion loop
  (`backup-to-github.sh:69-76,116`) is a correct belt-and-suspenders. Not refuted.
- "restore-smoke cannot write outside restore-dir" (self-check #4): overlap guard uses
  `realpath` both directions (`:93-102`); tar member validation on archive sources
  (`:104-114`). Holds. Not refuted.
- Seam 1 "keys match exactly": consumer `_deliver_public_bot_user` (`:1276-1326`) reads many
  optional `extra.*` keys the producer omits, but all via `.get()` defaults — tolerant, no
  break. Not refuted.

---

## E. RESIDUAL DISAGREEMENTS / DEFERRED TO CODEX FEDERATION

1. GAP-1 is the strongest finding; it should be promoted into the record's RISKS at HIGH and
   the adversarial self-check #2 corrected (failure rows shadow, not clobber).
2. The captain-wrapped delivery row carries NO lease/claim — `run_once` only claims
   `public-agent-turn` rows (`arclink_notification_delivery.py:1902`). Two concurrent delivery
   workers could double-send a captain-wrapped notification. This is CANON-23's delivery loop,
   not strictly this piece, but the producer chose `target_kind='captain-wrapped'` without a
   claim path; flagged for cross-piece review.
3. GAP-2/GAP-3 live in `common.sh` (CANON-24 helpers) but are consumed by this piece's scripts;
   confirm whether CANON-24's record captures the 404 fail-open and TOFU gaps.
