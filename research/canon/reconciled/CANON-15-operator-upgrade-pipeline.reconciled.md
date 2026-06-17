# CANON-15 — Operator Upgrade Pipeline — RECONCILED (both-model truth)

- **Piece:** CANON-15 (operator/pin upgrade pipeline: detector → policy → broker → host runner)
- **Codex (GPT-5.5 xhigh) sign-off:** `OBJECT(6)` — core broker/runner/detector proof holds; objections on
  policy-consumer characterization, M1 wording, M3/M5 severity, timeout semantics, and detector overlap.
- **Claude adjudicator (Opus 4.8) federation sign-off:** **BOTH-MODEL-AGREED.**
  Every material point reconciled to a single code-grounded truth. The two severity moves Codex asked for
  (M3↓, M5↓) are supported by the code/compose/structured fields and are adopted. The one substantive
  characterization dispute (policy "display-only") resolves to **both**: Codex is right that the policy
  module gates a *mutating* command, and the Claude record is right that the literal `"hermes"` never crosses
  into broker `install_items`. No standing disagreements remain.
- **Method:** every disputed point below was re-opened in the working tree (branch `arclink`, HEAD `63a42c8`,
  with the two in-scope files carrying uncommitted edits — verified via `git diff --stat HEAD`). Code wins over
  any comment, name, or prior claim. Citations re-confirmed at path:line by this adjudicator.

---

## RESOLUTION TABLE (point | winner | deciding cite)

| # | Point | Winner | Deciding cite (re-opened here) |
|---|-------|--------|--------------------------------|
| 1 | H1 — poison/dangling-symlink file wedges the drain | both (CONFIRM) | `host_runner.py:412` (`item.stat()` in glob sort key follows symlink → raises before per-file handling), `:367-376` (pre-`try` rejects regular poison), `:399-414,417-423` (no try/except around loop). Ratified. |
| 2 | M1 — queue-root agreement deploy-enforced, not code-enforced | both, with Codex/verifier wording precision | Broker confines `relative_to(host_priv/state)` at `broker.py:283-287`; runner only `is_absolute()` at `host_runner.py:90`. SAME explicit override env `ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR` both sides (`broker.py:277`, `host_runner.py:88`); only the *fallback* priv source differs (broker `ARCLINK_DOCKER_HOST_PRIV_DIR` `:278`; runner `ARCLINK_OPERATOR_UPGRADE_HOST_PRIV_DIR` `host_runner.py:80`). Mechanism real; MEDIUM stands. Headline must say "fallback priv source," not "queue env." |
| 3 | M2 — nonce replay TOCTOU + non-persistent store | both (CONFIRM) | `broker.py:665-671` (`_nonce_seen` lock A) and `:674-683` (`_record_nonce` lock B) are separate locked regions; HMAC work `:707-713` is lock-free between them; `ThreadingHTTPServer` `:765`; store in-memory `_SEEN_SIGNATURE_NONCES`. MEDIUM stands. |
| 4 | M3 — dismissed pin upgrade stays "active"/listable | mechanism both; **severity codex** | `dismiss_pin_upgrade_action` sets `silenced=1`, never `applied_at` (`control.py:9686`); `_active_pin_upgrade_targets` filters only `applied_at IS NULL`, ignores `silenced` (`:9601`); detector only resets `applied_at`→NULL (`pin_upgrade_check.py:487`); `list_pin_upgrade_action_payloads(active_only=True)` still returns it. BUT execution still requires an explicit operator confirm (`operator_raven.py:1627-1637`) and the digest IS silenced. → severity MEDIUM→LOW. |
| 5 | M4 — component allowlist enforced only on Docker broker/runner | both (CONFIRM) | `control.register_pin_upgrade_action`/`_normalize_pin_upgrade_item` accept any non-empty component (`control.py:9502-9515`); provisioner `_pin_upgrade_command_args` validates component-nonempty/target-nonempty/kind-flag only, NO allowlist (`enrollment_provisioner.py:429-448`); only broker `:267` and runner `:264` enforce the 7-name set. "byte-identical across three modules" is false for the provisioner. MEDIUM stands. |
| 6 | M5 — authority-inventory prose contradicts real boundary | **severity codex; cite codex** | Real boundary clean: `compose.yaml:866-868` mounts only the repo (no docker.sock), `:1173-1174` `internal: true` (no egress); structured `compose_boundary.docker_socket:"none"` (`docker-authority-inventory.json:2229`), `egress_networks:[]` (`:2245`), `why_socket_needed:"No Docker socket is needed"` (`:2247`). Only `remaining_gate` *prose* still says "writeable Docker socket authority" (e.g. `:205`). Pure doc/audit drift. → MEDIUM→LOW. Record cite `broker.py:866` is INVALID (file is 786 lines) — replace with the compose/inventory anchors. |
| 7 | M6 — provisioner decode/HTTP error escapes handler | both (CONFIRM) | Success path `json.loads(response.read().decode("utf-8"))` (`enrollment_provisioner.py:335`) can raise `UnicodeDecodeError` (a `ValueError`); catch tuple `(OSError, TimeoutError, URLError, json.JSONDecodeError)` (`:342`) does not include it. MEDIUM stands (bounded by stale-row reaping). |
| 8 | hermes-docs-only `install_items` reachable → broker rejects | both (REFINE confirmed) | Collapse drops child only when `inherits_from` parent co-included (`pin_upgrade_check.py:643-646`); `config/pins.json:30` `inherits_from: hermes-agent`; broker allowlist has no `hermes-docs` (`broker.py:48`). Divergence reachable via `subdir`/docs-preview override; otherwise docs track agent. LOW stands. |
| 9 | Detector concurrency — SELECT→INSERT has no lock | codex (confirmed as a real risk) | `_upsert_state` SELECT `pin_upgrade_check.py:405-409` then bare INSERT `:431-443` with no `BEGIN IMMEDIATE`/row lock; `component TEXT PRIMARY KEY` (`control.py` schema `:732`+) → concurrent runs (hourly timer + `arclink_ctl` `internal pin-upgrade-check` `:2685-2687`) can `IntegrityError` on 2nd INSERT or double-notify. Real, but narrow (two concurrent runs, trusted single host). Promote from INFO → **LOW**. |
| 10 | `upgrade_policy` is "display-only" / out of execution path | **both** | Codex right: `PIN_UPGRADE_COMPONENTS` gates the *mutating* `/pin_upgrade` (`operator_raven.py:1597`, `pin_upgrade` ∈ `MUTATING_COMMANDS` `:225`). Claude right: the literal `"hermes"` only FILTERS detector payloads (`control._pin_upgrade_operator_component_names` maps `hermes`→`{hermes-agent,hermes-docs}` `:9579-9585`; matches via `_pin_upgrade_payload_matches_component` `:9588-9593`), and what is queued is the opaque detector token (`operator_raven.py:1304-1313`) whose `install_items` carry `hermes-agent`, never literal `"hermes"`. No name-drift bug reaches the broker. Record's "display-only" wording is corrected; its security conclusion is upheld. |
| 11 | Provisioner urlopen timeout 30s < broker poll deadline | codex (new, CONFIRMED) | Provisioner calls `_operator_upgrade_broker_request(...)` with no timeout arg → urlopen `timeout=max(30,7200)=7200` (`enrollment_provisioner.py:334,377-379,465`); body carries no `timeout_seconds` (`_brokered_operator_payload:352-356`) → broker `_operator_timeout`→7200, wait `=max(30,min(21630,7230))=7230` (`broker.py:340`). Provisioner times out 30 s before broker would return. Real seam defect. MEDIUM. |
| 12 | Stale/ghost re-execution after broker timeout | both (verifier+codex, CONFIRMED) | Broker times out `broker.py:362` but leaves the pending file; runner `_validate_request` reads `timeout_seconds` only to clamp subprocess (`host_runner.py:307`) and never reads `created_at` for any age/expiry test (`:279-330`) → host-mutating `deploy.sh upgrade`/per-pin apply can run later after the requester got a timeout. MEDIUM. |
| 13 | Poll-seconds parse ordered AFTER the queue write | codex (new, CONFIRMED) | `_atomic_write_json(request_path,...)` at `broker.py:339`, THEN `float(...POLL_SECONDS)` at `:341`; malformed value raises ValueError caught at `:651-653` → broker returns `(False,str)` rejection while the already-queued mutation still drains. Sharpens the record's existing LOW (which missed that the file is already queued). LOW. |
| 14 | HMAC seam byte-for-byte | both (CONFIRM) | Producer signs `ts\nnonce\nsha256(body_bytes)` over `json.dumps(body,sort_keys=True)` (`enrollment_provisioner.py:312-330`); consumer hashes raw received bytes (`broker.py:707-713`); header constants identical. Ratified. |
| 15 | Broker→runner request/result schema seam | both (CONFIRM) | `broker.py:316-337` producer; runner re-validates `schema_version==1`, request_id regex, operation allowlist, repo/priv equality, log confinement, pin items (`host_runner.py:279-330`); result `ok`+int returncode (`broker.py:352-360`). Ratified. |
| 16 | Runner→component-upgrade.sh status-marker seam (single emission) | both (CONFIRM) | Under `--skip-upgrade` one terminal marker per apply: `noop`/`pushed` at `bin/component-upgrade.sh:637`, `changed` at `:668`; `:665` and reexec guarded by `skip_upgrade!=1`; tail-N slice `_pin_upgrade_log_requires_deploy` `host_runner.py:248-259`. Ratified. |
| 17 | Control-plane line-number spans (register/dismiss) | codex/verifier (cite correction) | `register_pin_upgrade_action` is `control.py:9518-9547`; `_normalize_pin_upgrade_item` `:9502-9515`; `dismiss_pin_upgrade_action` `:9675-9711`. Record spans were stale by a few lines; code substance intact. |

---

## CODEX NEW FINDINGS — CONFIRMED vs REJECTED

### CONFIRMED (become net-new federation risks)

1. **[MEDIUM] Provisioner↔broker timeout mismatch (30 s grace gap).** Provisioner urlopen timeout = 7200 s
   (function default, no arg passed at `enrollment_provisioner.py:377-379,465`; `:334`); broker poll wait = 7230 s
   (`broker.py:340`, body carries no `timeout_seconds` so both default to 7200). A host result landing in the final
   30 s window is reported as failed to the action worker → invites retry/double-execution (compounds M2 and
   finding #12). Cite: `enrollment_provisioner.py:334,377-379,465`; `broker.py:340-365`.
2. **[LOW] Poll-seconds parsed after the queue write.** Malformed `ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_POLL_SECONDS`
   raises at `broker.py:341` *after* `_atomic_write_json` at `:339`; caught at `:651-653` → broker returns rejection
   while the already-queued host mutation still executes. Sharpens the record's existing poll-seconds LOW. Cite:
   `broker.py:339,341,651-653`; `host_runner.py:412-413`.

### Also CONFIRMED from the federation set (verifier-originated, Codex-ratified)

3. **[MEDIUM] Stale/ghost re-execution after broker timeout** (resolution #12) — runner enforces no `created_at`
   staleness. Cite: `host_runner.py:279-330,381`; `broker.py:362-365`.
4. **[LOW] Unbounded `results/`+`processed/` growth** — broker reads `results/<id>.json` once and never deletes;
   runner writes results and moves processed files with no retention (`host_runner.py:377,391-396`;
   `broker.py:314-315`). Trusted-host disk growth. Confirmed by Codex; no pruning exists in either module.
5. **[LOW] Detector concurrency race** (resolution #9) — promote INFO→LOW. Cite: `pin_upgrade_check.py:405-443`;
   `control.py:732` (PRIMARY KEY); `arclink_ctl.py:2685-2687`.

### REJECTED

- *None.* Every Codex finding and adjudication re-verified true in the working-tree code.

---

## SEVERITY CHANGES (only where code supports it)

| Risk | From | To | Deciding cite |
|------|------|----|---------------|
| M3 (dismissed pin upgrade stays listable) | MEDIUM | LOW | Execution still gated by explicit operator confirm (`operator_raven.py:1627-1637`); digest is silenced (`control.py:9686`); pure state/UX inconsistency on a trusted boundary. |
| M5 (authority-inventory prose drift) | MEDIUM | LOW | Real runtime boundary has no socket / no egress (`compose.yaml:866-868,1173-1174`; `docker-authority-inventory.json:2229,2245,2247`); only `remaining_gate` prose is stale (`:205`). Doc/audit-class. |
| Detector concurrency race | INFO | LOW | Concurrent SELECT→INSERT with `component` PRIMARY KEY can IntegrityError/double-notify across timer+ctl runs (`pin_upgrade_check.py:405-443`; `control.py:732`; `arclink_ctl.py:2685-2687`). |

> H1, M1, M2, M4, M6, the provisioner-timeout MEDIUM, stale/ghost MEDIUM, and queue-growth LOW retain their
> record/finding severities — code supports each as stated.

---

## CITATION CORRECTIONS (code correct, cite fixed)

- M5 anchor `broker.py:866` → **INVALID** (file is 786 lines). Use `compose.yaml:842-872,1173-1174` +
  `config/docker-authority-inventory.json:2225-2247`.
- `register_pin_upgrade_action` `9502-9534` → `control.py:9518-9547`; `_normalize_pin_upgrade_item` →
  `:9502-9515`; `dismiss_pin_upgrade_action` `9683-9703` → `:9675-9711`. Substance intact.

---

## STANDING DISAGREEMENTS

**None.** Every material point reconciled to a single code-grounded truth. The policy "display-only" framing
(resolution #10) resolved cleanly to **both** by re-reading `operator_raven.py:1581-1602` + `_handle_pin_upgrade`
queueing and `control._pin_upgrade_operator_component_names` — Codex's refinement is adopted as a wording
correction; the record's security-relevant conclusion (no `"hermes"` leaks into broker `install_items`) is upheld.
M3 and M5 severities were code-decided in Codex's favor.

---

## FINAL BOTH-MODEL VERDICT

**Provably YES for the proven scope — well-guarded against an adversary, under-guarded against entropy and
liveness.** The detector is a deterministic fail-soft state machine throttling per release-version; the broker and
host runner authenticate every request (HMAC over `ts\nnonce\nsha256(body)`, TTL+nonce protected), fence behind the
trusted-host gate, allowlist exactly two operations and seven pin components, and execute only two hard-coded,
symlink-checked scripts. All cross-piece seams verify at both ends. The `upgrade_policy` module gates the mutating
`/pin_upgrade` command (corrected from "display-only") but never injects the literal `"hermes"` into the broker
payload — the opaque detector token carries `hermes-agent`.

The federation's residual weaknesses are liveness/entropy, not authority:
- **HIGH H1** — one poison/dangling-symlink pending file permanently wedges the drain (no try/except around the loop).
- **MEDIUM** — M1 (queue-root containment asymmetry via mismatched *fallback* priv-env), M2 (nonce-replay TOCTOU +
  in-memory store), M4 (component allowlist enforced only on the Docker path), M6 (provisioner decode escape),
  **provisioner↔broker 30 s timeout mismatch** (new), **stale/ghost re-execution after broker timeout** (new).
- **LOW** — M3↓ (dismissed-but-listable), M5↓ (inventory prose drift), detector concurrency↑, poll-seconds
  ordering (new), unbounded results/processed growth, hermes-docs-only rejection, unguarded pins.json read,
  constants triplication.

All defects are contained by the trusted-host boundary (not remotely exploitable). The two in-scope execution files
carry uncommitted working-tree edits vs HEAD `63a42c8` — the audited behavior is what runs now.

**Federation sign-off: BOTH-MODEL-AGREED.**

---

<!-- CANON-REPAIR-STATUS:START -->
## Repair status

> Refreshed from [`research/canon/fixes/CANON-15-operator-upgrade-pipeline.fix.md`](../fixes/CANON-15-operator-upgrade-pipeline.fix.md) (tracked). The audit findings above remain the adjudicated spec; this block records the repair campaign state for this piece.

- Status: `bf7e201` committed.
- Summary: 14 fixed / 3 skipped / 0 needs-decision.
- Tests: 5 test files run, all pass; py_compile/json/diff checks pass
- Representative fixes:
  - HIGH — poison/dangling symlink/invalid pending file no longer wedges the host runner; bad files are result-recorded when possible and quarantined. `python/arclink_operator_upgrade_host_runner.py:403`
  - MEDIUM — queue root override is confined under private state. `python/arclink_operator_upgrade_host_runner.py:90`
  - MEDIUM — nonce replay TOCTOU and cross-restart replay closed with locked check-record plus persistent nonce store. `python/arclink_operator_upgrade_broker.py:678`, `python/arclink_operator_upgrade_broker.py:779`
<!-- CANON-REPAIR-STATUS:END -->
