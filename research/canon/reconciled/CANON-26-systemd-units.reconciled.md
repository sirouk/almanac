# CANON-26 — Systemd Services & Timers — RECONCILED (both-model-signed)

- Piece: CANON-26 (Systemd Services & Timers)
- Codex (GPT-5.5 xhigh) SIGN-OFF: **OBJECT(3)** — three material corrections to the Claude record (inventory split, fail-open access-state, agent-renderer injection-guard "strength") plus one new HIGH (SSH-key newline injection).
- Final adjudicator: Claude Opus 4.8 (1M). Method: every disputed point re-opened in source and, where behavior was the dispute, **executed** the exact bash/python path. Code wins over comment/name/prior claim.
- FEDERATION SIGN-OFF: **AGREED-WITH-STANDING-DISAGREEMENTS** — every material code-level point reconciled to one truth; the only items that cannot be settled from THIS repo are two genuinely cross-repo CANON-30 Hermes-CLI contract questions (enumerated below). All in-repo safety/severity claims are settled.

The architectural map in the Claude record (29 thin `%h/arclink/bin/*` wrappers; full unit→script→module trace; clean CANON-24 boundary) is ratified by both models and survived re-verification. The disputes were entirely in the SAFETY/severity layer, and the code resolves them decisively against the original record.

---

## RESOLUTION TABLE (disputed points only; point | winner | deciding cite)

| Point | Winner | Deciding cite (re-opened / executed) |
|---|---|---|
| Inventory split "18 .service + 11 .timer" | **codex+claude-verifier** (record wrong) | `ls systemd/user/` = **19 .service / 10 .timer**; unpaired = `systemd/user/arclink-pdf-ingest-watch.service:6`, always disabled `bin/install-user-services.sh:72` |
| Access-state parse = "fail-closed, aborts with KeyError" | **codex+claude-verifier** (record REFUTED) | Executed `bin/install-agent-user-services.sh:276-294`: malformed JSON AND missing-key both → `exit=0`, `enable_access_surfaces=1`, ports EMPTY. NOT fail-closed. |
| Downstream of fail-open = broken units enabled/restarted | **codex+claude-verifier** | empty `$dashboard_backend_port`/`$dashboard_proxy_port` render `--port `/`--listen-port ` `:416,:434`; units gated by `=="1"` at `:394`, enabled+restarted `:475-478` |
| Agent renderer injection guard = "a strength" | **codex+claude-verifier** (record REFUTED for agent path) | `reject_systemd_unit_value` called ONLY from `systemd_env_line` `:49`; `Description=$AGENT_ID` raw `:298,313,326,342,371,397,426`, `WorkingDirectory=$HERMES_HOME` raw `:380,415,433`, `PathChanged/Modified` raw `:345-348`, `ExecStart` raw `:308,333,383,416,434` |
| Guard `exit 1` aborts the render | **codex+claude-verifier** (inert) | Executed heredoc repro: injected `ExecStart=/bin/touch /tmp/pwned` via raw `Description` newline; guard printed "Refusing" but parent `cat >file <<EOF` still wrote file, parent exit 0 |
| End-to-end agent-id injection exploitable? | **both** (defect real in-piece; producer mitigates normal path) | `safe_slug` restricts to `[a-z0-9-_]` `arclink_control.py:171-175`; `make_agent_id` `:7599-7601`. So normal AGENT_ID is safe — mitigation is PRODUCER-side, not this piece's guard. |
| System renderer guard sound | **codex+claude-verifier** (ratify) | `reject_systemd_unit_value` at MODULE level `bin/install-system-services.sh:45-46` (aborts in main shell, not subshell), static Descriptions, root-gated `:8`, guard def `:18-30` |
| access-state PRODUCER emits exact port keys | **codex REFINE wins over verifier C3** | enrolled-user writer DOES emit both keys `arclink_agent_access.py:524-525,551`; BUT `bin/install-deployment-hermes-home.sh:163-175` overloads the SAME filename with a payload that OMITS backend/proxy ports → real drift source feeding the fail-open |
| `--claims-only` accepted by provisioner | **both** (ratify) | `arclink_enrollment_provisioner.py:145` + branch `:3336` |
| Cross-piece exec seams (memory/notif/health/dash-proxy/qmd/curator/backup) | **both** (ratify) | exec lines + consumer argparse all read; `arclink_dashboard_auth_proxy.py:1367-1371`, `arclink_memory_synthesizer.py:1920`, `arclink_notification_delivery.py:1955`, `bin/backup-agent-home.sh:8-17` |
| ssot-batcher wake seam (CANON-18→26) | **codex** (ratify, new corroboration) | `arclink_notion_webhook.py:42-49` `systemctl --user --no-block start arclink-ssot-batcher.service` |
| `set -e` half-enable = restart block only | **codex+claude-verifier** (record under-scoped) | ENABLE block also unguarded: `enable_user_units`→`systemctl --user enable` `:32`, called `:49-59`, no `|| true` |
| Hermes cron installer is not systemd | **both** (ratify) | `bin/install-agent-cron-jobs.sh:406-433` writes `cron/jobs.json`; no systemctl |
| TOCTOU `start_system_service_if_idle` | **both** (ratify) | `bin/install-system-services.sh:110-119` |
| Dead/legacy units (pdf-ingest-watch, user-agent-code) | **both** (ratify) | `bin/install-user-services.sh:72`, `bin/install-agent-user-services.sh:442,479` |

---

## CODEX NEW FINDINGS — CONFIRMED vs REJECTED

### CONFIRMED (re-verified true → net-new federation risks)

- **CONFIRMED / HIGH — SSH-key newline injection bypasses `from=`/no-forwarding restrictions.**
  Executed both regexes. Bash installer regex `bin/install-agent-ssh-key.sh:56` and upstream Python validator `arclink_onboarding_flow.py:76-77` (called via `.fullmatch` at `:956`) BOTH admit a value with an internal newline **after a no-comment first key**. Mechanism (proven): in this build `[[:space:]]`/`\s` match newline and `.` matches newline, so the optional trailing group `([[:space:]].*)?`/`(?:\s+.*)?` swallows `\n<second key>`. A first key WITH a comment is correctly rejected; no-comment + newline passes. The whole multiline value is then appended at `:115` (`printf '%s\n' "$AUTHORIZED_KEY_LINE"`), so the `from="$ALLOWED_FROM",no-agent-forwarding,...` options apply ONLY to the first physical line; the injected second line lands as an **unrestricted** `authorized_keys` entry. Net-new HIGH (neither Claude pass found it). Cite `bin/install-agent-ssh-key.sh:54-56,73-74,115`, `python/arclink_onboarding_flow.py:76-77,955-956`.

- **CONFIRMED / LOW — `ARCLINK_AGENT_REMOTE_SSH_FROM` interpolated into `from="..."` unvalidated.**
  `bin/install-agent-ssh-key.sh:72-74`: `KEY_OPTIONS="from=\"$ALLOWED_FROM\",..."` with no quote/control-char check, so an operator-set value containing `"` can inject additional authorized_keys options. Operator-side (lower reach than the remote-supplied pubkey), hence LOW. Cite `bin/install-agent-ssh-key.sh:72-74`.

- **CONFIRMED / REFINE → folds into HIGH(G1) — access-state filename schema-overload.**
  `bin/install-deployment-hermes-home.sh:163-175` writes the SAME `arclink-web-access.json` filename with a payload lacking `dashboard_backend_port`/`dashboard_proxy_port`, while the enrolled-user writer `arclink_agent_access.py:524-525` includes them. This is a concrete drift source that triggers the fail-open at `install-agent-user-services.sh:287`. Corrects the Claude verifier's C3 ("over-cautious"): the seam is NOT uniformly happy-path — a second, schema-divergent writer exists.

### REJECTED
- None. All Codex new findings hold in code.

---

## SEVERITY CHANGES (only where code supports; from → to + cite)

| Risk | From | To | Deciding cite |
|---|---|---|---|
| Access-state parse failure (record's "MEDIUM, fail-closed KeyError") | MEDIUM (fail-closed) | **HIGH (silent fail-open → broken/half-enabled dashboard+proxy units)** | executed `bin/install-agent-user-services.sh:276-294` (exit 0, empty ports), render `:416,434`, enable/restart `:475-478` |
| Agent-renderer unit injection guard (record's "INFO strength") | INFO (strength) | **MEDIUM (defect: guard covers only `Environment=`; abort inert; positional fields raw)** | guard caller `:49`; raw fields `:298,345-348,380,416,434`; inert-exit repro executed |
| SSH-key remote pubkey validation | (absent in record) | **HIGH (net-new)** | `bin/install-agent-ssh-key.sh:56,115` + `arclink_onboarding_flow.py:956` (both regexes executed) |
| `ARCLINK_AGENT_REMOTE_SSH_FROM` interpolation | (absent in record) | **LOW (net-new)** | `bin/install-agent-ssh-key.sh:72-74` |
| `set -e` half-enable scope | LOW (restart block only) | **LOW (unchanged severity; scope corrected to also include enable block `:49-59`)** | `bin/install-user-services.sh:32,49-59` |

Ratified-as-is (no change): MEDIUM→effectively-folded hard-subscript brittleness (now the HIGH above); LOW TOCTOU `install-system-services.sh:110-119`; INFO dead units; INFO `HOME=/root` hardcode `install-system-services.sh:58`; system-renderer guard remains a genuine INFO strength.

---

## STANDING DISAGREEMENTS (cannot be settled from THIS repo)

1. **Hermes gateway CLI contract — two invocation styles.** Per-agent + Docker helper emit `gateway run --replace` (`bin/install-agent-user-services.sh:383`, `python/arclink_agent_process_helper.py:705-707`); Curator emits bare `gateway` (`bin/curator-gateway.sh:162`); `bin/hermes-shell.sh:12` only forwards `"$@"` to the runtime Hermes binary.
   - claudeView: both invocation styles are real in-repo; whether they are CLI-compatible cannot be proven here because the Hermes runtime lives in CANON-30 / external `hermes-agent`.
   - codexView: same — "the Hermes CLI contract remains not both-ends-verified from this repo."
   - whyUnresolved: the consumer (Hermes `gateway` argparse) is not in this repository; this is a true cross-repo seam, not a code disagreement.

2. **`disable_native_hermes_gateway_units` naming completeness.** Enumerates only the `hermes-gateway*` glob (`bin/install-agent-user-services.sh:256`).
   - claudeView / codexView: agree the enumeration is correct for that glob; agree completeness (does CANON-30 ever name a native gateway unit outside `hermes-gateway*`?) cannot be proven from public-repo evidence.
   - whyUnresolved: depends on CANON-30 / Hermes-native unit naming, out of this repo.

No standing disagreement between the two models on any IN-REPO point — Codex explicitly states "no residual disagreement with the Claude verifier on CANON-26 HIGH/MEDIUM findings," and the adjudicator's executions confirm both the verifier's REFUTATIONS (R1/R2/R3) and Codex's new HIGH.

---

## FINAL BOTH-MODEL VERDICT

The CANON-26 unit map, cadence/Type/Restart semantics, install-time gating, and every cross-piece exec seam are **provably correct** and ratified by both models. The original Claude RECORD must NOT be signed as written: its three load-bearing safety claims are wrong in code —
1. inventory split is 19/10, not 18/11;
2. the access-state parse is a **silent FAIL-OPEN into broken/half-enabled dashboard+proxy units (HIGH)**, not a fail-closed KeyError; and
3. the agent-user renderer injection guard is **NOT a strength (MEDIUM defect)** — it guards only `Environment=` lines and its abort is inert inside `$(...)`; only the SYSTEM renderer is genuinely guarded.
Plus the federation net-new **HIGH SSH-key newline injection** (unrestricted `authorized_keys` line) and a **LOW** unvalidated `from=` interpolation. The agent-id injection is mitigated end-to-end by the PRODUCER's `safe_slug`, not by this piece — so the in-piece guard defect stands as a trust-boundary weakness. Net: architecture YES, safety record CORRECTED. Federation sign-off: AGREED-WITH-STANDING-DISAGREEMENTS (two cross-repo CANON-30 CLI seams only).

---

<!-- CANON-REPAIR-STATUS:START -->
## Repair status

> Refreshed from [`research/canon/fixes/CANON-26-systemd-units.fix.md`](../fixes/CANON-26-systemd-units.fix.md) (tracked). The audit findings above remain the adjudicated spec; this block records the repair campaign state for this piece.

- Status: `bf7e201` committed.
- Summary: 7 fixed / 3 skipped / 0 needs-decision.
- Tests: 5 Python test files run, all pass; bash -n on 4 touched shell scripts passed; py_compile for python/arclink_onboarding_flow.py passed
- Representative fixes:
  - HIGH — access-state parsing now fails closed before dashboard/proxy render: validates JSON object plus 1-65535 backend/proxy ports, sets `enable_access_surfaces=1` only after successful parse. `bin/install-agent-user-services.sh:305`
  - MEDIUM — agent unit directive injection now rejects raw unit fields in the parent shell before heredocs render, including `AGENT_ID`, paths, activation triggers, ports, and dashboard env values. `bin/install-agent-user-services.sh:39`, `bin/install-agent-user-services.sh:66`, `bin/install-agent-user-services.sh:369`
  - HIGH — SSH public key newline injection is blocked in the root installer with explicit multiline rejection and `[[:blank:]]` separators instead of `[[:space:]]`. `bin/install-agent-ssh-key.sh:56`, `bin/install-agent-ssh-key.sh:61`
<!-- CANON-REPAIR-STATUS:END -->
