# CANON-15 — Operator Upgrade Pipeline — ADVERSARIAL VERIFY

Verifier: independent Opus 4.8 skeptic. Method: re-opened all four in-scope files plus
adjacent consumers/producers (`arclink_control.py`, `arclink_enrollment_provisioner.py`,
`bin/component-upgrade.sh`, `compose.yaml`, `bin/deploy.sh`) and re-derived every load-bearing
claim at path:line against the working tree (branch `arclink`). Default disposition: refute unless
re-confirmed in code.

## OVERALL VERDICT

**The record is substantially trustworthy and well-calibrated.** Every cross-piece seam I attacked
verifies at both ends in code; the four carried risks H1/M1/M2/M3/M4/M5/M6 reproduce on the working
tree; the working-tree-edit and policy-name-drift drift notes are accurate. I found **no refutation
of a load-bearing claim.** I did find **two genuine gaps neither the record nor DISSECT names**
(unbounded queue-dir growth; stale/ghost re-execution of a request the broker already timed out on),
and I down-rate **M3** by one notch (it is a state/UX inconsistency on a trusted boundary, not a
MEDIUM-class defect). The record's own ADVERSARIAL SELF-CHECK already honestly flags the soft spots.

## CITATION SPOT-CHECKS (re-confirmed in code)

- Broker `_is_authorized` 686-716; `do_POST` 734; size gate 739-744; auth-before-parse 746; JSON+dict
  400 at 749-756. CONFIRMED.
- Broker `run_operator_upgrade_request` 636; trusted-host gate first 638; operation allowlist
  642/646/650; catch tuple `(OSError, RuntimeError, ValueError, subprocess.SubprocessError)` 651 +
  rejection incident 652 + `(False, str)` 653. CONFIRMED.
- Broker pin allowlist `ALLOWED_PIN_COMPONENTS` 48, `SAFE_COMPONENT_RE` 47, `PIN_UPGRADE_FLAGS` 49-56;
  `_normalized_pin_upgrade_item` regex-AND-set check 267, kind-keys-map 271, target ≤240 270.
  CONFIRMED.
- Broker schema-v1 payload 316-337; `_atomic_write_json` tmp `.{name}.{pid}.tmp` + `os.replace`
  295-299; poll loop 340-365; `float(...)` poll-seconds with no try/except 341. CONFIRMED.
- Runner `_validate_request` 279-330; `int(schema_version or 0)==1` lax 282; `REQUEST_ID_RE` 25,
  285; operation allowlist 287-289; repo/priv resolve-equality 290-295; log confinement via
  `_require_child_path(mkdir_parent=True)` 296-302; pin items validated before any command 321-329.
  CONFIRMED.
- Runner `_queue_root` only `is_absolute()` — NO containment 87-92. CONFIRMED (M1 asymmetry real).
- Runner `_process_request_file` pre-`try` lstat/symlink 367-370, JSON/dict 371-373, id 374-376;
  `try:` at 380; result write 382/384-390; move-or-unlink 392-396; non-zero child returncode is
  `ok:True`. CONFIRMED.
- Runner `process_once` glob sort-key `item.stat().st_mtime` 412; no try/except around loop;
  `main` 417-423 no wrap. CONFIRMED (H1 real).
- Detector `register_pin_upgrade_action(...)` 710-715; `_pin_upgrade_action_items` filter `if r.target`
  626; `_pin_upgrade_install_items` parent-collapse 643-646; `_read_pins` unguarded `json.loads`
  99-100; GitHub raw fail-soft `except (HTTPError, URLError, TimeoutError, OSError, UnicodeError)`
  135. CONFIRMED.
- Policy module `mutation_performed: False` always (283-302); `PIN_UPGRADE_COMPONENTS` lists
  `"hermes"` (10) vs allowlist `"hermes-agent"`. CONFIRMED (benign name drift).

### Control-plane / provisioner line-number drift (NOT a refutation, but flag)

The record's CROSS-PIECE/RISKS cites for `arclink_control.py` are slightly off against the current
tree (the code is correct; the cites are stale by a few lines):
- "register at 9502-9534" — `_normalize_pin_upgrade_item` is **9502-9515**, `register_pin_upgrade_action`
  is **9518-9547**; the six-key normalize + blank-component(9512)/blank-target(9514) raise is real.
- token formula cited "9540" — exact: `arclink_control.py:9540`. MATCH.
- M3 cites `dismiss_pin_upgrade_action` "9683-9703" — actual def **9675-9711**; the `silenced=1`
  UPDATE is **9686**, no `applied_at` write anywhere in it. Mechanism intact.
- M3 cites `_active_pin_upgrade_targets ... applied_at IS NULL` "9601" — actual filter line **9601**
  inside def at **9596**. MATCH.
The substance survives; the spans are imprecise. Recorded as INFO drift, not a refutation.

## CROSS-PIECE CONTRACTS — re-attacked, all hold at both ends

1. **Detector → control plane (§1).** Producer emits `{component,kind,field,current,target,
   throttle_target}` only when `r.target` truthy (pin_upgrade_check.py:626,647); consumer raises on
   blank target (arclink_control.py:9513). Blank-target raise unreachable from this producer.
   BOTH ENDS CONFIRMED.
2. **Provisioner → broker HMAC (§3).** Producer signs `HMAC-SHA256(token, f"{ts}\n{nonce}\n
   sha256hex(body_bytes)")` over `json.dumps(body, sort_keys=True)` (enrollment_provisioner.py:312-320)
   and sends `data=body_bytes` (323); consumer recomputes `sha256(raw_body)` over the exact wire bytes
   it read (broker.py:707-713). Header constant byte-identical (broker.py:41 == provisioner.py:99).
   Nonce `secrets.token_urlsafe(18)` (24 chars, charset ⊂ broker regex). No parser-differential: the
   broker hashes raw bytes, then parses the same bytes (broker.py:745,750). BOTH ENDS CONFIRMED.
3. **Broker → runner schema (§5).** Broker writes `install_items:[{component,kind,target}]`
   normalized (broker.py:336/265-273); runner re-validates each via `_validated_pin_upgrade`
   (host_runner.py:262-271) plus schema_version/request_id/operation/repo/priv/log. Result: runner
   `{ok,returncode|error,...}` (host_runner.py:382-391); broker requires `ok is True` + int
   returncode (broker.py:352-360). `created_at` ignored by runner — benign. BOTH ENDS CONFIRMED.
4. **hermes-docs collapse (§4).** `config/pins.json:30` declares `inherits_from: hermes-agent`;
   `_pin_upgrade_install_items` drops the child when parent co-included (643-646). BOTH ENDS CONFIRMED.
   Residual LOW (hermes-docs-only digest) is real and honestly flagged.
5. **Policy → Operator Raven (§6).** Policy module is read-only and out of the broker path; sole
   consumer is the display router. CONFIRMED.
6. **Runner → component-upgrade.sh status markers (§7).** Re-read `do_apply` 543-669. Under
   `--skip-upgrade` (skip_upgrade=1, dry_run=0): noop path emits exactly ONE terminal marker at
   `:637` (`noop` or `pushed`; the `:625/:633` markers are guarded by `skip_upgrade!=1`); changed
   path emits exactly ONE at `:668` (the `:665` marker guarded). Single-marker-per-apply holds, so the
   broker/runner tail-N slice (`_pin_upgrade_log_requires_deploy`, host_runner.py:248-259,
   broker.py:481-492) is sound. BOTH ENDS CONFIRMED.

## RISKS — re-attacked

- **H1 (HIGH) — CONFIRMED, severity correct.** Dangling-symlink `*.json`: `item.stat()` in the glob
  sort key (412) follows the link → `FileNotFoundError`, raised before `_process_request_file` runs;
  neither `process_once` (399-414) nor `main` (417-423) wraps the loop → whole drain aborts; file
  never moves to `processed/`, re-globbed every timer tick → permanent wedge. A regular poison file
  trips the pre-`try` checks (368-376) with the same propagation. No test covers this
  (grep of tests/test_arclink_docker.py finds only GAP-019 symlink-authority assertions, none on the
  drain). HIGH is correct; trusted-host-only is the right scoping.
- **M1 (MEDIUM) — CONFIRMED, with a precision correction.** Broker enforces queue dir
  `relative_to(<host_priv>/state)` (broker.py:284); runner only `is_absolute()` (host_runner.py:90).
  Both read the SAME explicit override env `ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR` (broker.py:277,
  host_runner.py:88), and compose (compose.yaml:862) + deploy.sh (8397) wire both to the same
  `<priv>/state/operator-upgrade-host-runner`. The "different env var" in the record refers to the
  **fallback** priv source (broker defaults from `ARCLINK_DOCKER_HOST_PRIV_DIR`; runner from
  `ARCLINK_OPERATOR_UPGRADE_HOST_PRIV_DIR`) — accurate but the headline could be misread as the queue
  env differing, which it does not. Mechanism (asymmetric containment) is real. MEDIUM stands.
- **M2 (MEDIUM) — CONFIRMED.** Lock released between `_nonce_seen` (665-671) and `_record_nonce`
  (674-683); HMAC work done lock-free in between on per-request threads (ThreadingHTTPServer, 765).
  Two concurrent identical signed requests can both pass. Store is in-memory (45), wiped on restart →
  one post-restart replay inside ±300 s. CONFIRMED.
- **M3 (MEDIUM → recommend LOW/MEDIUM) — mechanism CONFIRMED, severity slightly high.**
  `dismiss_pin_upgrade_action` sets `silenced=1` (arclink_control.py:9686), never `applied_at`;
  `_active_pin_upgrade_targets` filters only `applied_at IS NULL` (9601) ignoring `silenced`; detector
  only ever resets `applied_at` to NULL (pin_upgrade_check.py:487). So a dismissed-but-unapplied row
  keeps satisfying the "active" filter that `list_pin_upgrade_action_payloads(active_only=True)`
  queues from. Real. But the digest IS silenced (no re-notify), so the surface is "Raven /list still
  shows a dismissed item as queueable" — a state/UX inconsistency on a trusted boundary, not a
  security or correctness-of-execution defect. I lean LOW–MEDIUM. Recorded as residual disagreement.
- **M4 (MEDIUM) — CONFIRMED.** `register_pin_upgrade_action`/`_normalize_pin_upgrade_item` accept any
  non-empty component (arclink_control.py:9511); provisioner `_pin_upgrade_command_args` validates
  only component-nonempty/target-nonempty/kind-has-flag (enrollment_provisioner.py:433-438) — NO
  `ALLOWED_PIN_COMPONENTS` check. Only broker (267) and runner (264) enforce the 7-name set. The
  "byte-identical across three modules" framing IS false for the provisioner. CONFIRMED.
- **M5 (MEDIUM) — CONFIRMED structurally.** `operator-upgrade-broker-net: internal: true`
  (compose.yaml:1173-1174) → no egress; broker has no docker.sock mount (compose.yaml:866-869 mounts
  only the repo). Broker runs `user: 0:0` with `cap_add: DAC_OVERRIDE` and mounts the repo
  **read-write** (compose.yaml:847-851,869) — this is by design (it writes typed requests into private
  state) and is consistent with the record's "trusted-host queue boundary" framing; not a new
  contradiction. Prose-vs-structured drift in the authority inventory is the documented M5.
- **M6 (MEDIUM) — CONFIRMED.** Provisioner success path `json.loads(response.read().decode("utf-8"))`
  (335) can raise `UnicodeDecodeError`/`JSONDecodeError`; the catch tuple is `(OSError, TimeoutError,
  URLError, json.JSONDecodeError)` (342) — `UnicodeDecodeError` (a `ValueError`) is NOT in it and
  escapes. Bounded by stale-row reaping. CONFIRMED.
- **LOW poll-seconds (341), LOW pins.json unguarded read (99-100), LOW hermes-docs-only,
  LOW constants triplication, INFO laxity** — all re-confirmed at the cited lines.

## NEW GAPS (neither record nor DISSECT names these)

1. **[MEDIUM] Stale/ghost re-execution after a broker timeout.** The broker poll loop times out
   (broker.py:362) but the pending request file is LEFT in `pending/`. The runner's `_validate_request`
   and `_process_request_file` never check `created_at`/`timeout_seconds` for staleness
   (host_runner.py:279-330 reads `created_at` only as passthrough; no age/expiry test). If the runner
   timer was down or backlogged past the broker deadline, the host-mutating `deploy.sh upgrade` (or
   per-pin `component-upgrade.sh ... apply`) runs LATER, after the requester already received a
   timeout error and (per M2) may have retried with a fresh nonce → a second pending file → the same
   logical upgrade can execute twice with no result consumer. Cite:
   `python/arclink_operator_upgrade_host_runner.py:279-330,381`;
   `python/arclink_operator_upgrade_broker.py:362-365`.
2. **[LOW] Unbounded `results/` and `processed/` growth.** The broker reads `results/<id>.json` once
   and never deletes it; the runner writes every result there and moves every request into
   `processed/` (host_runner.py:391-394) with NO pruning/retention anywhere in either module (grep
   confirms only mkdir/write/move, no unlink-of-results, no rmtree, no max-age). Both dirs grow one
   file per upgrade forever. Trusted-host disk-growth, not exploitable, but unbounded. Cite:
   `python/arclink_operator_upgrade_host_runner.py:377,391-394`;
   `python/arclink_operator_upgrade_broker.py:314-315`.

## SEAM MISMATCHES

None that refute the record. All seven cross-piece seams verify at both ends. The only seam-adjacent
weakness is NEW GAP #1 (broker-timeout ↔ runner-staleness): the broker's deadline and the runner's
drain have no shared liveness contract — the request's `created_at`/`timeout_seconds` are written but
never honored by the consumer.

## RESIDUAL DISAGREEMENTS

- M3 severity: record says MEDIUM; I lean LOW–MEDIUM (state/UX inconsistency, digest is silenced).
- M1 headline wording: technically accurate but the "defaults from a different env var" phrasing risks
  being read as the queue-dir env differing (it does not — only the fallback priv source differs).
- Stale-control-plane line cites (register/dismiss spans off by a few lines); code is correct.
