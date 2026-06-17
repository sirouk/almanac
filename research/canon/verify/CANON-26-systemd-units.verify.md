# CANON-26 — Systemd Services & Timers — ADVERSARIAL VERIFICATION

Verifier: independent Opus 4.8 adversarial skeptic. Method: re-opened every load-bearing
file, re-counted units, and *executed* the two suspect bash/heredoc/eval paths to confirm
runtime behavior (not just read them). Citations are path:line verified against the real files.

## VERDICT (one line)
**PARTIALLY TRUSTWORTHY — the unit→script→module map and cross-piece exec seams are accurate,
but TWO load-bearing claims are REFUTED by execution: (1) the headline MEDIUM "fail-closed,
aborts with KeyError" risk is actually a silent FAIL-OPEN that renders broken units; (2) the
"unit-injection guard is a strength" claim is overstated — the guard does not cover
Description/WorkingDirectory/Path/ExecStart fields and its `exit 1` is inert inside heredoc
command substitution. Plus a factual inventory error (service/timer split inverted).**

---

## REFUTATIONS (claim → finding)

### R1 — REFUTED: inventory split "18 .service + 11 .timer" is wrong
Record PIECE (line 4) and VERDICT (line 95) state "29 static unit files under `systemd/user/`
(18 `.service` + 11 `.timer`)". Actual: `ls systemd/user/*.service` = **19**, `*.timer` = **10**.
Total 29 is correct; the split is INVERTED. The 19th service with no timer pairing is the dead
`arclink-pdf-ingest-watch.service` plus the always-on long-runners. Load-bearing because the
record uses the split to reason about "timer-driven oneshots." Cite: `systemd/user/` (19 .service,
10 .timer; verified `ls`).

### R2 — REFUTED: MEDIUM risk "fail-closed... aborts with KeyError" (the headline risk)
Record RISKS (line 86) + OPEN (line 79) + SELF-CHECK #4 (line 75): "reads
`state["dashboard_backend_port"]` as a hard dict subscript; if the access-state JSON is malformed
or schema-renamed, the whole per-agent install **aborts with KeyError** ... **Fail-closed but
brittle**."
I executed the exact parse path (`install-agent-user-services.sh:276-294`) with (a) malformed
JSON and (b) JSON missing the key. **In BOTH cases the install does NOT abort.** The `python3 - ...`
runs inside `eval "$(...)"`; under `set -euo pipefail` a non-zero command-substitution used as an
argument does not propagate. Result: `enable_access_surfaces` stays `"1"` (set at :277 BEFORE the
parse), `dashboard_backend_port`/`dashboard_proxy_port` stay EMPTY, and the installer proceeds to
render dashboard + proxy units with empty `--port`/`--listen-port`/`--target http://127.0.0.1:`
(`:416`,`:434`), enable them, and only then fail at `systemctl --user restart` (:476) with a
misleading error. So the behavior is **silent FAIL-OPEN into a broken-unit state**, not
"fail-closed / aborts with KeyError." Both the stated mechanism AND the safety property are wrong.
Cite: `install-agent-user-services.sh:276-294,394,416,434,474-478` (executed).

### R3 — REFUTED (strength overstated): "Both inline renderers guard against unit injection"
Record RISKS line 92 (INFO strength) and INPUT/OUTPUT contracts (lines 13,24): claims
`reject_systemd_unit_value` makes the agent-user renderer injection-safe.
Findings:
  (a) In `install-agent-user-services.sh` the guard is invoked ONLY from `systemd_env_line`
      (`:47-51`, called at `:49`), i.e. ONLY for `Environment=` lines. The `Description=` lines
      interpolate `$AGENT_ID` RAW at :298,:313,:326,:342,:371,:397,:426; `WorkingDirectory=$HERMES_HOME`
      RAW at :380,:415,:433; `PathChanged=$ACTIVATION_TRIGGER_PATH`/`$ACTIVATION_TRIGGER_DIR` RAW at
      :345-348; `ExecStart` interpolates `$HERMES_BIN`/`$SHARED_REPO_DIR`/`$HERMES_HOME` RAW
      (:308,:333,:383,:416,:434). None of these positional-arg fields are guarded.
  (b) EVEN where the guard runs (`Environment=ARCLINK_AGENT_ID` at :302), its `exit 1` is INERT.
      I executed a heredoc reproduction: a `$(systemd_env_line ...)` that hits `exit 1` runs in a
      command-substitution subshell, so it only exits the subshell — the parent `cat >file <<EOF`
      still writes the file, and the RAW `Description=...$AGENT_ID` line above it injects a
      newline-borne `ExecStart=/bin/touch /tmp/pwned` into the rendered unit. Test output: rendered
      unit contained the injected `ExecStart`, parent exit 0.
This makes the renderer's injection guard a near-no-op for the agent-user path. (The SYSTEM
renderer `install-system-services.sh:45-46` DOES guard before interpolation and uses static
Descriptions, so it is sound — the strength claim is true ONLY for system-services.) Upstream
slugging (`make_agent_id`→`safe_slug`, `arclink_control.py:171-175,7599-7601`) usually strips
newlines/`$`, so end-to-end exploitability is mitigated by the PRODUCER, not by this piece's guard;
but `linked_agent_id` can also be set from `payload.get("linked_agent_id")` with only `.strip()`
(`arclink_ctl.py:777`), and the installer is a trust boundary that does not enforce its own claim.
Cite: `install-agent-user-services.sh:47-51,298,302,345-348,380,383,416,434` (executed repro).

---

## CONFIRMED (independently re-verified true)

- C1 ExecStart uniformity: `grep ExecStart systemd/user/ | grep -v %h` returns nothing; every
  static unit ExecStart is `%h/arclink/bin/<script>`. `ls systemd/` shows only `user/` (no
  `systemd/system/`). TRUE. Cite verified.
- C2 Cross-piece exec seams (record contracts #1-#5,#9,#10) — all consumer entrypoints confirmed:
  memory_synthesizer `main()`@1920/`__main__`@1926; notification_delivery `--limit default=50`@1949,
  `main()`@1955; health_watch `main()`@297; enrollment_provisioner `--claims-only`@145, branch
  `args.claims_only`@3336; dashboard_auth_proxy argparse @1367-1371 (`--listen-host` default
  127.0.0.1, `--listen-port` required, `--target` required, `--access-file`, `--realm` default
  Hermes); mcp-server.sh:30, notion-webhook.sh:30, ssot-batcher.sh:13, qmd-daemon.sh:20 exec lines
  all match. Self-check #1 RESOLVED is correct.
- C3 access-state PRODUCER seam (record left this OPEN/unverified, line 79): I verified it.
  `arclink_agent_access.py:24` `ACCESS_STATE_FILENAME="arclink-web-access.json"`, `:517-526` emits
  payload with EXACT keys `dashboard_backend_port`/`dashboard_proxy_port`, `:551` writes it. So the
  seam is both-ends-verifiable and correct on the happy path — the record was over-cautious calling
  it unverified. (The DRIFT failure mode is R2, not a key mismatch.)
- C4 timer cadences: all match record (memory-synth 6m/30m, notification-delivery 5s/5s,
  ssot-batcher 30s/1m, qmd-update 2m/15m, curator-refresh 2m/1h, github-backup 5m/1h,
  hermes-docs-sync 10m/4h, pdf-ingest 4m/5m, quarto-render 10m/30m, health-watch OnActiveSec=5m /
  OnUnitActiveSec=15m). TRUE.
- C5 `[Install]`-less oneshots: curator-refresh, github-backup, health-watch, hermes-docs-sync,
  memory-synth, notification-delivery, pdf-ingest, qmd-update, quarto-render, ssot-batcher have NO
  `[Install]`; only their `.timer` is enabled. DRIFT #2 TRUE.
- C6 `set_user_systemd_bus_env` returns the `[[ -n XDG_RUNTIME_DIR && -n DBUS_SESSION_BUS_ADDRESS ]]`
  test (common.sh:1237). Self-check #5 falsifier (socket exists but uid mismatch) is plausible since
  export is gated on `-S "$bus_path"` only. TRUE.
- C7 DRIFT #3 (install-agent-cron-jobs.sh is a Hermes-native cron installer, not systemd) — TRUE;
  no systemd touch; writes `$HERMES_HOME/cron/jobs.json` (:406-433), pre-run script (:348-363, 0700),
  config.yaml timeout (:366-403). Lock `fcntl.flock(LOCK_EX|LOCK_NB)` @138. atomic_write @260-279.
- C8 install-system-services injection guard IS sound (R3 caveat): `reject_systemd_unit_value`
  called on CONFIG_PATH+ARCLINK_REPO_DIR @45-46 before interpolation; static Descriptions; root-gated
  @8; DEFER_START stops units @124-129; `start_system_service_if_idle` TOCTOU @110-119. TRUE.
- C9 SSH installer: regex-validates key @56, requires user @61, hardened options @73, de-dup by key
  body via inline python @86-113, chmod 700/600 @80-82, chown @82/118. TRUE.

---

## NEW GAPS (neither record nor prior docs mention)

- G1 (HIGH) Silent FAIL-OPEN on bad/renamed access-state JSON — the `eval "$(python3 ...)"` swallows
  both JSONDecodeError and KeyError; install renders + enables dashboard/proxy units with EMPTY
  `--port`/`--listen-port`, then aborts mid-`systemctl restart` leaving half-enabled broken units.
  Worse than the record's "fail-closed KeyError" framing. Cite install-agent-user-services.sh:276-294,476.
- G2 (MEDIUM) Unit-directive injection via unguarded interpolation of positional args into
  `Description=`/`WorkingDirectory=`/`PathChanged=`/`ExecStart=`; guard's `exit 1` is inert inside
  heredoc `$(...)`. Mitigated end-to-end only because the PRODUCER slugs agent_id
  (safe_slug, arclink_control.py:171-175), not by this piece. Cite install-agent-user-services.sh:298,345-348,380.
- G3 (LOW) `install-user-services.sh` enable block (:49-59) is ALSO unguarded under set -e (record
  only flagged the restart block :109-120). A failing `systemctl --user enable` aborts equally,
  leaving an even-earlier half-enabled state. Cite install-user-services.sh:30-34,49-59.
- G4 (INFO) health-watch.timer uses `OnActiveSec=5m` (not `OnBootSec`); record never surfaces the
  key, only "15m" — harmless but the trace (line 48 "health-watch.timer:4-7") under-specifies.

---

## SEAM MISMATCHES
None of the verified cross-piece exec contracts mismatched (producer emits exactly what consumer
reads for memory-synth, notification-delivery, health-watch, enrollment `--claims-only`,
dashboard-proxy flags, access-state JSON keys). The single seam DEFECT is intra-piece-to-CANON-19
robustness (R2/G1): the consumer (`install-agent-user-services.sh`) does not defensively handle a
producer (`arclink_agent_access.py`) that fails to write valid JSON — it fails open, not closed.

## RESIDUAL DISAGREEMENTS WITH THE RECORD
1. Record's headline MEDIUM ("fail-closed, aborts with KeyError") is REFUTED — it is silent
   fail-open; correct severity should be HIGH for the broken-unit/half-enable outcome.
2. Record's INFO "strength" (injection guards) must be DOWNGRADED — guard covers only Environment
   lines on the agent path and its abort is inert; only the SYSTEM renderer is genuinely guarded.
3. Inventory "18 service + 11 timer" must be corrected to 19 service + 10 timer.

Overall: the architectural mapping is trustworthy; the SAFETY/severity claims are not, and were
refuted by executing the actual code paths.
