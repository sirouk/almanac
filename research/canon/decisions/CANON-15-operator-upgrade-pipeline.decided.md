# CANON-15 — Operator Upgrade Pipeline — DECIDED (final adjudication)

> Final adjudicator: Claude Opus 4.8 (1M), DECISION mode, ArcLink two-model Federation.
> Inputs weighed: `research/canon/NEEDS_DECISION.md` (§CANON-15), Codex's proposal
> (`CANON-15-operator-upgrade-pipeline.codex.md`), the North Star
> (`docs/arclink/sovereign-control-node-symphony.md`), and the code reality
> (`reconciled` + `sections` records, re-grounded against the working tree at HEAD `7931b04`).
> Method: every carried-forward risk was re-opened in committed code (`rg`/`sed`) before ruling.
> Code wins over any comment, name, or prior claim.

---

## Bottom line

**CANON-15 carries ZERO genuine deferred operator decisions.** `NEEDS_DECISION.md` §CANON-15
says `NONE`; Codex recommends closing the piece as `0 needs-decision` with no runtime/schema/
contract/threat-model change. **I independently re-verified the code and AGREE.** The repair
campaign (`14 fixed / 3 skipped / 0 needs-decision`) genuinely landed all 14 fixes at HEAD
`7931b04` — the two in-scope files no longer carry an uncommitted diff (`git diff --stat HEAD`
is empty), so the audited fail-closed behavior is what ships. The three "skipped" items are
standing risk-accepted / out-of-scope notes, **not** operator calls, and only one of them is
even a candidate for an operator's optional cosmetic preference.

There is exactly one decision section below (Codex's DECISION 1), plus a short "what was
actually fixed" ledger I re-proved so the operator can trust the closeout, and one optional
non-blocking cosmetic flagged as a standing item.

---

## DECISION 1 — Close CANON-15 as 0 needs-decision; make no runtime/schema/contract change

**[VERDICT: agree-codex]**

### Question
Does any operator-facing decision remain open for the operator/pin upgrade pipeline
(detector → policy → broker → host runner), or can the piece be closed with no change?

### My independent reasoning (code re-grounded at HEAD `7931b04`)
I did not take the repair status block on faith. I re-opened the committed code for every
carried-forward HIGH/MEDIUM/LOW risk the reconciled record flagged, and each is closed
**fail-closed**, in the source-owned broker/runner, with the mutation still fenced behind the
trusted-host gate:

- **H1 (HIGH) — poison/dangling-symlink wedge — FIXED.** `process_once` sorts pending files by
  `item.lstat().st_mtime` (no symlink-following `stat()`), and per-file handling is now wrapped
  in `try/except BaseException` inside `_process_request_file`
  (`python/arclink_operator_upgrade_host_runner.py:407-443,478-495`). A bad file is
  result-recorded when possible and quarantined; the drain no longer aborts the whole pass.
- **M1 (MED) — queue-root containment asymmetry — FIXED.** `_queue_root` now enforces
  `root.relative_to(state_root)` (`host_runner.py:90-101`), matching the broker's
  `relative_to(<priv>/state)`. Config drift can no longer silently desync the queue root.
- **M2 (MED) — nonce replay TOCTOU + non-persistent store — FIXED.** Check-and-record is now
  atomic under one lock (`_record_nonce_if_unseen`, `broker.py:737-739,783`) and the store is
  persisted across restarts (`_load_persisted_nonces_locked` / `_persist_seen_nonces_locked`,
  `broker.py:696-755`).
- **M4 (MED) — provisioner had no component allowlist — FIXED.** The non-Docker provisioner now
  declares and enforces the 7-name set (`arclink_enrollment_provisioner.py:104`, and
  `:449-450` raises `pin upgrade action component is not allowlisted`). The reconciled record's
  "provisioner has no allowlist" finding is now stale-by-fix.
- **Stale/ghost re-execution after broker timeout — FIXED.** The runner now reads `created_at`
  and raises `request expired before execution` (`host_runner.py:177-187,339`), so a result
  landing after the requester timed out cannot host-mutate later.
- **Provisioner↔broker 30 s timeout mismatch — addressed via signed timeout alignment**
  (request-body timeout drives both ends; broker waits `timeout + grace`, `broker.py:328-330`).
- **Poll-seconds parsed after the queue write — FIXED.** Poll interval is computed by
  `_host_runner_poll_interval()` with its own `try/except` (`broker.py:304-310`) **before**
  `_atomic_write_json` — a malformed env can no longer reject a request that already drained.
- **Unbounded results/processed growth — FIXED.** `_prune_queue_dir` adds age+count retention
  (`host_runner.py:445-475`) and the broker now unlinks the consumed result file
  (`broker.py:363-366`).
- **Detector concurrency (INFO→LOW), unguarded pins.json, constants triplication** — the
  remaining LOWs are entropy/cosmetic on a single trusted host; none is an operator decision.

The three "skipped" items are correctly classified as standing notes, not deferred calls:
1. **GAP-019 trusted-host / root-equivalence.** The broker intentionally owns a writable live
   host repo + private-state queue (`compose.yaml:843-872` — `user: "0:0"`,
   `cap_drop: ALL` + only `DAC_OVERRIDE`, repo bind only, **no `docker.sock`**;
   inventory confirms "removes the operator-upgrade-broker Docker socket… the broker still has
   trusted write access to the live host repo/private-state bind",
   `config/docker-authority-inventory.json:65`). This is the design's deliberate Docker-mode
   boundary and belongs to the broader GAP-019 risk-acceptance track, not CANON-15.
2. **Broker `0.0.0.0:8917` bind inside `internal: true`** (`compose.yaml:866-868,1174`) — the
   network has no egress and only the two enrolled callers attach; the bind breadth is contained
   by compose isolation. Not a CANON-15 decision.
3. **`upgrade_policy` `"hermes"` vs allowlist `"hermes-agent"` label drift** — non-load-bearing:
   `PIN_UPGRADE_COMPONENTS` (`python/arclink_upgrade_policy.py:9-10`) gates the *display* router
   and the *mutating* `/pin_upgrade` command, but the literal `"hermes"` is mapped to
   `{hermes-agent, hermes-docs}` for **filtering** detector payloads only; what is queued is the
   opaque detector token whose `install_items` carry `hermes-agent`, never literal `"hermes"`
   (resolution #10). The two name sets never meet in the broker path.

### Where I agree / differ from Codex
- **Agree on the core call:** no runtime/schema/contract/threat-model change; close as
  `0 needs-decision`; keep the three skipped items as standing risk-accepted/out-of-scope notes.
- **One refinement (does not change the verdict):** Codex's writeup repeats two framings from
  the *original* record that the re-grounding corrects, and the operator should not inherit them
  as if still-open:
  - The M5 "broker writeable Docker socket" framing was a **citation error** — the
    operator-upgrade-broker has **no socket** (`compose.yaml:843-872`;
    `docker-authority-inventory.json:65`). The real residual is the writable repo/private-state
    queue (point 1 above), not a socket. The federation already moved M5 MEDIUM→LOW as pure
    prose drift; I uphold that.
  - M4 is now **fixed in the provisioner** (`:104,:449-450`), so it should not be listed as a
    live "code already moved toward fail-closed" gap that still lacks an allowlist — it now has
    one.
  - These are precision fixes to the closeout narrative, not a disagreement on the decision.

### FINAL PLAN
1. **Close CANON-15 as `0 needs-decision`.** No code, schema, contract, or threat-model change.
   The pipeline is provably fail-closed for the proven scope and contained by the trusted-host
   boundary; the campaign's 14 fixes are committed and re-verified at HEAD `7931b04`.
2. **Record the three skipped items as standing notes**, not operator calls:
   GAP-019 trusted-host/root-equivalence (writable repo/private-state queue; broker has no
   socket); `0.0.0.0` bind contained by `internal: true`; `hermes`/`hermes-agent` label drift
   (non-load-bearing).
3. **Optional, non-blocking cosmetic (operator's taste, not required):** if the operator wants
   one vocabulary across surfaces, align the `upgrade_policy` display label `"hermes"` →
   `"hermes-agent"` (`python/arclink_upgrade_policy.py:9-10,69` + `_ALIASES` so existing
   `/upgrade_policy hermes` input still resolves). This is a low-effort surface-vocabulary tidy
   with no execution-path effect; it is recorded in standing items, not as a blocking fork.
4. **No artifact beyond this decision ledger** is needed unless the operator wants an explicit
   closeout note in `GAPS.md`/runbook; the campaign report already says `NEEDS-DECISION — NONE`.

### Symphony anchor (quoted)
- North Star — *"Operators own the universe: hosts, secrets, fleet, policy, upgrades, backups,
  live proof, emergency repair, and product rollout."* — the upgrade pipeline keeps mutation
  inside operator-owned, audited broker/runner rails; nothing here transfers authority.
- Whole-System Traversal §10 — *"Upgrades, backups, restore, incident repair … all preserve
  state by default and leave redacted evidence of what happened."* — the pipeline now preserves
  state on malformed/expired/replayed requests (fails closed, quarantines, records rejection
  incidents) and the broker queue carries only secret PATHS, never key content.
- Whole-System Traversal — *"every step should have a local source owner, a local regression or
  dry-run proof where possible, and a named live proof gate … and how it fails closed."* — the
  detector, broker, and runner each have a local source owner and tests; the only remaining
  open work is the named live gate (`GAP-032` real multi-Pod apply proof), which is a campaign
  gap, not a CANON-15 operator decision.
- Cross-Surface Experience Standard (the optional cosmetic): *Raven, dashboard, and CLI should
  "use the same language and never force the Operator to translate between three vocabularies"*
  — the only reason to touch the `hermes` label at all, and even then it is operator-optional
  because the drift is display-only.

### Effort / blast-radius
- **Decision itself: low.** No code change; only this ledger (and optionally a one-line
  GAPS/runbook closeout). Runtime surfaces affected: none.
- **Optional cosmetic (if the operator opts in): low**, blast-radius confined to the
  `/upgrade_policy` display router (CANON-14 consumer); zero execution-path impact because the
  literal `"hermes"` never reaches the broker.

---

## Standing items (not blocking, recorded for the operator)
1. **GAP-019 trusted-host / root-equivalence** — the operator-upgrade-broker's writable host
   repo + private-state queue (root container, `DAC_OVERRIDE`, **no docker.sock**) is the
   intentional Docker-mode boundary. Belongs to the GAP-019 acceptance track, not CANON-15.
2. **Optional vocabulary tidy** — align `upgrade_policy` display label `"hermes"` →
   `"hermes-agent"` (with alias) for one-vocabulary surfaces. Operator's taste; non-load-bearing.
3. **Named live-proof gate `GAP-032`** — real multi-Pod refresh/apply proof remains the
   campaign-level live gate for the upgrade dream; tracked outside CANON-15.
