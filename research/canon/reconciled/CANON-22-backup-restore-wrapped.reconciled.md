# CANON-22 — Backup / Restore / Lifecycle / Wrapped — RECONCILED (both-model-signed)

**Codex (GPT-5.5 xhigh) SIGN-OFF:** OBJECT(3) — "CANON-22 is mostly ratified; the verifier's HIGH/MEDIUM risks are real, and I add two backup proof gaps plus resolve the open §B39 questions."

**Claude Opus 4.8 FEDERATION SIGN-OFF:** BOTH-MODEL-AGREED.

Adjudicator method: every REFUTE/REFINE/new-finding/residual below was decided by re-opening the
cited code (Read/sed/grep) in /root/arclink on branch `arclink`. Code wins over comment/name/prior claim.
Codex's CONFIRM items where both models already agreed are ratified in one line and not deep-re-checked.

---

## 1. RESOLUTION TABLE (disputed / refined / new — point | winner | deciding cite)

| # | Point | Winner | Deciding cite (re-opened by adjudicator) |
|---|-------|--------|------------------------------------------|
| R1 | GAP-1: generate-succeeds-then-enqueue-throws → committed `generated` row shadowed by later `failed` row; `failed_retry` bypasses `_has_wrapped_signal`; unbounded duplicate generated rows every 300s | both (claude-verify raised, codex confirmed) | `arclink_wrapped.py:728` (generated row committed), `:1043-1056` (enqueue inside try → except writes failure), `:1079-1088` (`ORDER BY created_at DESC, report_id DESC LIMIT 1`), `:1091` (`failed`→`failed_retry`), `:1095` (gate only `if reason == "missing"`) |
| R1b | Adjudicator escalation: failure is *worse* than verifier stated — `_record_wrapped_failure` sets `attempt = prior_failures+1` (`:968`) with PK including attempt (`:138`), so failed rows accumulate AND once `attempt>=3` an operator outbox row fires EVERY subsequent tick (`:987-1010`), not once | claude-verify (confirmed + extended) | `arclink_wrapped.py:138,968,987` |
| R2 | GAP-2: 404 fail-open spans BOTH lanes — control-plane lane (`backup-to-github.sh`) shares it via `require_private_github_backup_remote` falling through `non-public-or-missing` to implicit `return 0` | both | `common.sh:1360-1362` (404→`non-public-or-missing`), `:1390-1397` (only `public`/`error:*`/`unsupported` return 1), `backup-to-github.sh:131` (control lane calls helper) |
| R3 | GAP-3: TOFU host-key trust — `StrictHostKeyChecking=yes` but known_hosts auto-populated by unverified `ssh-keyscan -H`; fail-closed on connectivity, fail-open on key authenticity | claude-verify | `common.sh:1450-1455` (`ssh-keyscan -H "$host"`, exit unchecked), `:1482` (`StrictHostKeyChecking=yes` against that file) |
| R4 | GAP-4: `extra_json.render_kind` is dead metadata (producer-only) | both (claude-verify + codex re-ran rg) | `arclink_wrapped.py:919` sole occurrence; no `python/` or `web/` consumer |
| R5 | Codex new MEDIUM: control-lane visibility check trusts overrideable `GITHUB_API_BASE`/`BACKUP_GIT_GITHUB_API_BASE` with NO test guard (agent-home lane HAS the `ARCLINK_AGENT_BACKUP_ALLOW_TEST_GITHUB_API_BASE` refusal; control lane does not) — spoofed API base can defeat the public-repo refusal | codex | `common.sh:1331-1333` (reads env, no guard), contrast `backup-agent-home.sh:22` + `configure-agent-backup.sh:44` (refusal present) |
| R6 | Codex new LOW: agent-home secret-exclusion proof does not screen symlink targets inside curated dirs; restore-smoke rejects only top-level `secrets`/`logs` and `validate_tar_members` runs only on archive sources | both (codex + claude-verify C) | `arclink-restore-smoke.sh:104-114` (name-only, archive-only), `:119,:125` (git-archive/dir paths unscreened), `:221-222` (top-level `secrets`/`logs` only) |
| R7 | REFINE: quiet-hours math is UTC-only, not local/DST-correct — docstring says "local quiet-hours" but `_parse_dt` normalizes to UTC before `current.replace(hour=...)` applies the window | codex (refines record OPEN #3 / VERDICT) | `arclink_wrapped.py:80` (`.astimezone(timezone.utc)`), `:802` (docstring "local"), `:808-809` (`current.replace(hour=...)` on UTC `current`) |
| R8 | Cross-piece: `captain-wrapped` outbox rows have NO claim/lease path — delivery loop claims only `public-agent-turn`; two workers could double-send | both (raised as cross-piece) — route to CANON-23 | `arclink_notification_delivery.py:1902-1909` (claim gated on `public-agent-turn`); producer chose `captain-wrapped` `arclink_wrapped.py:921` |
| R9 | Force-with-lease duplicate location cite correction: actual lines are `backup-to-github.sh:51` and `backup-agent-home.sh:139` (record's range conflated the two) | codex (cite correction) | `backup-to-github.sh:52` (`push --force-with-lease`), `backup-agent-home.sh:140`; reconcile fns at `:13`/`:101` |
| R10 | Cron seam cite refinement: actual subprocess argv at `install-agent-cron-jobs.sh:193`; `:45` proves only 240-min cadence | codex (cite refinement) | `install-agent-cron-jobs.sh:193-194` (argv `[backup_script, hermes_home]`), `:45` (`SCHEDULE_MINUTES=240`) |
| R11 | Seam 5 line cite: docker-job-loop shift is at `:9-11` (record) — codex cited `:141`; adjudicator confirms record's `:9-11` is the shift; both describe same behavior | both (record cite stands) | `docker-job-loop.sh:9-11` (JOB_NAME/INTERVAL read + `shift 2`) |
| R12 | CI seam: restore-smoke IS exercised in CI with both `--kind` values via the all-`tests/test_*.py` workflow | codex (resolves record OPEN #5) | `.github/workflows/install-smoke.yml:33-41` (runs every `tests/test_*.py`); `tests/test_backup_git_regressions.py` + `tests/test_agent_backup_regressions.py` drive shared+agent-home |
| R13 | Codex REFUTE of an unrelated open seam: no CANON-22 backup script consumes `backup_deploy_key_private_ref` (only dashboard metadata); agent backup uses `AGENT_BACKUP_KEY_PATH` state | codex | `backup-agent-home.sh:39` (`AGENT_BACKUP_KEY_PATH`); `dashboard.py:1237` metadata only |
| R14 | OUT OF PIECE: Codex "CONFIRM HIGH" operator pin-upgrade auto-push (`--skip-upgrade` sent without `--skip-push`) | neither (re: CANON-22) — code-true but route to CANON-15 | `arclink_operator_upgrade_host_runner.py:276` (`--skip-upgrade` only), `component-upgrade.sh:648-660` (push unless `skip_push==1`); files owned by CANON-15, not CANON-22 |
| R15 | OUT OF PIECE: Codex §B39 REFINE Stripe `received`-row stranding + onboarding-expiry default commit | neither (re: CANON-22) — route to CANON-07/CANON-04 | `arclink_entitlements.py:544-552`, `arclink_onboarding.py:324,337`; files owned by CANON-07/CANON-04; CANON-22 only reads `arclink_onboarding_sessions` read-only |

### Ratified CONFIRM items (both models already agreed — one-line ratification, no deep re-check)
- Seam 1 captain-wrapped producer/consumer key match — ratified.
- Seam 2 operator/tui-only persistent-failure routing (no external send) — ratified.
- Seams 3/4/5 backup service/timer, agent cron, docker Wrapped loop wiring — ratified (with cite refinements R9/R10/R11).
- Schema/CHECK seam (notification_outbox PK, wrapped_frequency CHECK, wrapped_reports status CHECK) — ratified.
- Redaction-first (ledger `:726`, scoped_ledger `:710`, render `:618`) — ratified.
- Two-phase verify is a real fail-closed gate (`configure-agent-backup.sh:287-323`) — ratified.
- restore-smoke local-only / no executor seam (asserted absence) — ratified.
- Line count 1179, all files tracked — ratified.

---

## 2. CONFIRMED net-new federation risks (re-verified true in code)

| Severity | Risk | Cite |
|----------|------|------|
| HIGH | **Perpetual duplicate-report storm.** generate commits a `generated` row, then enqueue can throw (`float(novelty_score)` coercion `:918`, `_captain_delivery_channel`, any sqlite outbox error); the later `failed` row shadows the valid generated row in the due query; `failed_retry` bypasses the signal gate; every 300s tick mints a fresh random-PK `generated` row + an accumulating `failed` row, with NO backoff. Once attempt≥3 an operator outbox row also fires every tick thereafter. | `arclink_wrapped.py:728,918,1043-1056,1079-1088,1091,1095,968,987` |
| MEDIUM | **404 fail-open on BOTH backup lanes.** A repo returning 404 (deploy key lacks read scope, or typo'd owner/repo) maps to `non-public-or-missing` and passes the visibility gate on the control-plane lane too, not just agent-home. | `common.sh:1360-1362,1390-1397`; `backup-to-github.sh:131` |
| MEDIUM | **Control-lane API-base spoof.** `github_repo_visibility` on the control lane reads `GITHUB_API_BASE`/`BACKUP_GIT_GITHUB_API_BASE` with no test guard; a spoofed base returning `{"private":true}` defeats the public-repo refusal. Asymmetric with the agent-home lane, which refuses non-default bases. | `common.sh:1331-1333`; contrast `backup-agent-home.sh:22` |
| LOW/MEDIUM | **TOFU host-key trust.** known_hosts auto-populated by unverified `ssh-keyscan -H` (exit unchecked); `StrictHostKeyChecking=yes` is fail-closed on connectivity but fail-open on key authenticity — a MITM at first keyscan pins permanently. | `common.sh:1450-1455,1482` |
| LOW | **restore-smoke does not screen symlink targets.** `validate_tar_members` is name-only and archive-only; git-archive/dir-snapshot paths and curated-dir symlinks are unscreened. Containment still holds (default GNU tar refuses symlink traversal), so this weakens the *proof*, not the *containment*. | `arclink-restore-smoke.sh:104-114,119,125,221-222` |
| INFO | **`extra_json.render_kind` is dead metadata** (producer-only). | `arclink_wrapped.py:919` |

These are net-new beyond the original record's RISKS section. The record's pre-existing MEDIUMs
(eligibility ignores session_counter `:365-421,1095`; no-backoff retry `:1091`) remain valid and are
subsumed/sharpened by HIGH R1.

## 3. REJECTED Codex new-findings (do not hold as CANON-22 risks)

| Codex finding | Why rejected for CANON-22 | Cite |
|---------------|---------------------------|------|
| "CONFIRM HIGH operator pin-upgrade auto-commits/pushes" | Code-TRUE but the files (`arclink_operator_upgrade_host_runner.py`, `bin/component-upgrade.sh`) are owned by CANON-15, not CANON-22. Not a CANON-22 record claim by either model. Route to CANON-15. | `arclink_operator_upgrade_host_runner.py:276`, `component-upgrade.sh:648-660` — referenced in CANON-15 section |
| "REFINE §B39 Stripe received-row stranding / onboarding-expiry commit" | Out of CANON-22 scope (owned by CANON-07/CANON-04). CANON-22 only reads `arclink_onboarding_sessions` read-only for delivery channel. Route to CANON-07/CANON-04. | `arclink_entitlements.py:544-552`, `arclink_onboarding.py:324,337` |

(Both are "rejected as CANON-22 risks" only because of piece ownership — the underlying code claims
are not refuted; they are routed to their owning pieces.)

## 4. SEVERITY CHANGES (applied only where code supports it)

| Risk | From | To | Cite |
|------|------|----|------|
| Failed-report retry / generate-then-enqueue-throw variant | MEDIUM (record "no backoff") | HIGH | `arclink_wrapped.py:1043-1056,1079-1088,1091,1095` — duplicate generated rows + accumulating failures, code-proven |
| 404 visibility fail-open | MEDIUM (record: agent-home lane only) | MEDIUM (re-scoped to BOTH lanes) | `common.sh:1390-1397`; `backup-to-github.sh:131` — scope widened, severity unchanged |

No other severity changes are code-supported. The record's self-check #2 ("failure rows cannot
clobber a generated row — different PK") is literally TRUE but is corrected in framing: the failure
row does not *clobber*, it *shadows* in the `created_at DESC` due query (R1).

## 5. STANDING DISAGREEMENTS

None. Every material point reconciled to a single code-grounded truth. The two out-of-piece Codex
findings (R14, R15) are not disagreements — both models would agree the code is true; they are routed
to their owning pieces (CANON-15, CANON-07/CANON-04) rather than booked as CANON-22 risks.

## 6. FINAL BOTH-MODEL VERDICT

CANON-22 provably does its declared, proof-gated job: redaction-first Wrapped, both-ends-verified
captain-wrapped → outbox → delivered round-trip, hard-refusal of public repos / non-default API bases
(agent-home lane), deploy-key/secrets exclusion from commits, and honest local-only restore-smoke that
never touches Docker/systemd/executor. The reconciled unhappy-path truth adds ONE HIGH defect (the
generate-then-enqueue-throw duplicate-report storm with no backoff), tightens the 404 fail-open to BOTH
backup lanes, and books the control-lane API-base spoof (MEDIUM), TOFU host-key trust (LOW/MEDIUM), and
the restore-smoke symlink-screening gap (LOW). The deeper boundary stands: this piece proves artifact
*shape* and *backup mechanics*, not end-to-end *recoverability*; live GitHub write/activation remains
operator-gated. Within that boundary, with the HIGH storm defect flagged, the code is sound.

**FEDERATION SIGN-OFF: BOTH-MODEL-AGREED.**
