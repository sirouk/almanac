# CANON-26 — Systemd Services & Timers — DECIDED (final adjudication)

- Piece: CANON-26 (systemd unit semantics + 5 installer scripts)
- Adjudicator: Claude Opus 4.8 (1M), DECISION mode, two-model Federation.
- Codex proposal: `research/canon/decisions/CANON-26-systemd-units.codex.md` — "No deferred operator decisions remain."
- Method: re-opened the repaired code (not just the reconciled record) and **proved** the fix scope before converging. Symphony = intent; code = reality; the plan moves code toward the symphony while failing closed.

## Bottom line

`research/canon/NEEDS_DECISION.md` lists CANON-26 as **NONE**, and the reconciled record reports `7 fixed / 3 skipped / 0 needs-decision`. I independently re-verified the repaired source and **agree**: there is no residual operator *policy* call for this piece. The campaign's net-new HIGH/MEDIUM findings (access-state fail-open, agent-renderer injection guard, SSH-key newline injection, unvalidated `from=`) were all **landed in code** and each fix moves the piece toward the symphony's fail-closed / secret-hygiene contract. The only items that cannot be settled here are two genuinely cross-repo CANON-30 Hermes-CLI seams — not CANON-26 operator decisions.

There is exactly one place worth an operator's explicit eyes (the access-state schema overload between two writers). I traced it to ground and it is **not** a live regression — see Decision 1. I record it as a decision (not a standing disagreement) because the right call is "ratify the fix as-is + one cheap follow-up," not "operator must pick a product fork."

---

## [VERDICT: agree-codex] Decision 1 — Access-state parse is now fail-closed; ratify, with one cheap consistency follow-up

**Question.** The repair changed the per-agent dashboard/proxy access-state parse from a hard dict subscript (record: "fail-closed KeyError"; Codex execution: "silent fail-open into broken/half-enabled units") to a validating parser that `exit 1`s on a malformed object, missing key, or out-of-range port (`bin/install-agent-user-services.sh:305-362`, gated at `:344-352`). A second writer, `bin/install-deployment-hermes-home.sh`, writes the SAME `arclink-web-access.json` filename but OMITS `dashboard_backend_port`/`dashboard_proxy_port`. Does failing closed on that divergent payload now block a previously-working install path — i.e., is there an operator product call hidden here?

**Independent reasoning.** I proved the two writers do not meet on a port-rendering path:
- Docker/deployment mode invokes `install-agent-user-services.sh` with `ARCLINK_AGENT_SERVICE_MANAGER=docker-supervisor` (`python/arclink_enrollment_provisioner.py:1071`, `python/arclink_docker_agent_supervisor.py:101`). The script **short-circuits with `exit 0` at `bin/install-agent-user-services.sh:275-276`** — before the access-state parse at `:344` and before any systemd render. So the deployment-mode file (the one missing the port keys, `bin/install-deployment-hermes-home.sh` payload has **zero** `dashboard_*_port` keys — verified `grep -c` = 0) never reaches the parse.
- Systemd mode (native enrollment, `bin/init.sh:585`) reads the file written by `python/arclink_agent_access.py:529-530`, which DOES emit both port keys.

So the fail-closed change is correctly scoped: it only fails closed in the lane where the producer is contractually obligated to emit the keys, and it never hard-aborts the docker-supervisor lane. The original "this is a cross-boundary KeyError waiting to fire" worry is now a clean, validated, fail-closed boundary. This is squarely what the symphony wants.

**Agree/differ from Codex.** Full agree with Codex's conclusion (no operator decision). I add the proof Codex's terse note did not show: the schema-overloaded second writer is harmless because the docker-supervisor `exit 0` precedes the parse. The one thing I'd add beyond "ship it": the divergent filename is a latent footgun if a future refactor ever lets the docker writer's file reach a systemd render. Cheap belt-and-suspenders: have `bin/install-deployment-hermes-home.sh` either (a) not reuse the `arclink-web-access.json` name for its port-less payload, or (b) include the two port keys it already knows from config. This is hygiene, not a gate.

**FINAL PLAN.** Ratify the landed fail-closed parser as-is (no operator action required). Optional low-effort follow-up (engineering hygiene, not an operator call): make the two `arclink-web-access.json` writers schema-consistent — either rename the deployment writer's port-less artifact or have it emit `dashboard_backend_port`/`dashboard_proxy_port`. Add a one-line comment at `bin/install-agent-user-services.sh:275` noting the docker-supervisor short-circuit is what keeps the port-less deployment payload off this parse path, so the invariant survives refactors.

**Symphony anchor.** *Installation And Machine Admission*: "Workerless interactive installs now stop or continue only as control-plane-only ... the same local readiness state" — and the global North Star principle (Ground Truth Boundary) that every step "FAILS CLOSED." A render that cannot prove valid ports must refuse, not emit `--port ` into a live unit. *Configuration, Schema, And Migration*: "Generated config includes enough version/release context to detect stale, missing, deprecated, or incompatible values before services start." The validated parse is exactly that detector at the unit boundary.

**Effort:** low. **Blast radius:** the optional follow-up touches one writer's JSON payload (docker/operator-home seam, CANON-19/CANON-25 adjacent); the ratified fix is already shipped and scoped to the systemd lane only.

---

## [VERDICT: agree-codex] Decision 2 — Agent-renderer unit-injection guard now covers positional fields; ratify

**Question.** The record originally scored the agent-user renderer's injection guard an INFO "strength." Codex/adjudicator proved it was a MEDIUM defect: `reject_systemd_unit_value` was called only from `systemd_env_line` (`Environment=` lines), while `Description=`, `WorkingDirectory=`, `ExecStart=`, and `PathChanged/Modified` interpolated `$AGENT_ID`/`$HERMES_HOME`/paths raw, and the guard's `exit 1` was inert inside `$(...)` command substitution. Is there an operator call in how the repair closed this?

**Independent reasoning.** The repair added `reject_systemd_unit_raw_value` (rejects newline/CR/`$`/`"`/`%`) and two parent-shell validators, `validate_common_render_inputs` (`bin/install-agent-user-services.sh:66-75+`) and `validate_systemd_render_inputs` (`:369-388`), called in the **main shell** before the heredocs render — so the abort is no longer inert. They cover `AGENT_ID`, `SHARED_REPO_DIR`, `HERMES_HOME`, `HERMES_BIN`, bundled-skills, activation-trigger path/dir, `PYTHON3_BIN`, access-state file, workspace/linked dirs, both ports, and dashboard label/title/theme/accent envs. End-to-end the producer already restricts `AGENT_ID` to `[a-z0-9-_]` via `safe_slug` (`arclink_control.py:171-175`), so the realistic attack surface was already narrow; the fix now makes the renderer itself fail closed regardless of producer, which is the correct defense-in-depth posture. No product fork here — there is exactly one right answer (guard positional fields in the parent shell), and it is implemented.

**Agree/differ from Codex.** Full agree. Nothing for the operator to decide.

**FINAL PLAN.** Ratify as landed. No operator action.

**Symphony anchor.** *Identity, Access, And Session Governance*: "Admin and Operator actions should never trust client-asserted privilege ... or natural-language intent without server-side authorization." Rendering operator/agent-derived strings into privileged systemd units is the same trust boundary; the parent-shell guard enforces it server-side and fails closed.

**Effort:** low (already done). **Blast radius:** none beyond the repaired installer.

---

## [VERDICT: agree-codex] Decision 3 — SSH-key newline injection + unvalidated `from=` are closed; ratify

**Question.** Net-new federation HIGH: a no-comment first pubkey followed by `\n<second key>` previously passed both the bash regex and the upstream Python validator, landing an **unrestricted** `authorized_keys` line below the `from="..."`,no-forwarding options. Plus a LOW: `ARCLINK_AGENT_REMOTE_SSH_FROM` interpolated into `from="..."` unvalidated. Any operator policy call in the fix?

**Independent reasoning.** Verified the repaired installer: explicit multiline rejection at `bin/install-agent-ssh-key.sh:55-58` (`*$'\n'* → exit 1`), key-body regex now uses `[[:blank:]]` instead of `[[:space:]]` so the separator class can no longer match a newline (`:61`), and `ALLOWED_FROM` is rejected if it contains newline/CR/`"` at `:73-76` before being interpolated into `KEY_OPTIONS`. The whole value is still appended as one physical line (`:118`-area), so the `from=`/no-forwarding restrictions now provably bind the only key on that line. The upstream Python validator (`arclink_onboarding_flow.py`) is a second gate; the installer is now self-sufficiently fail-closed at the root-write boundary, which is the correct place for a HIGH (it's the last hop before the privileged file). No operator fork — there is one correct answer (refuse multiline + control-char `from=`), and it is implemented.

**Agree/differ from Codex.** Full agree. This is a security fix with a single correct shape, not an operator preference.

**FINAL PLAN.** Ratify as landed. No operator action. (If anything, this is a candidate for the named live-proof gate around remote-Hermes SSH bootstrap — but that is a proof-evidence task under the existing fleet/SSH gate, not a deferred CANON-26 decision.)

**Symphony anchor.** *Secrets, Keys, And Rotation*: "Any helper that requires a token should prefer a file, secret reference, or private env over argv ... and should fail closed if validation cannot run." A remote-supplied pubkey is exactly such untrusted material; the installer must refuse anything it cannot bind to the tailnet `from=` restriction.

**Effort:** low (already done). **Blast radius:** none beyond the repaired installer; the tailnet-only `from=` default is unchanged so legitimate remote-Hermes bootstrap is unaffected.

---

## Cross-repo seams (NOT operator decisions — recorded for completeness)

Both models agree the only unsettled CANON-26 items are two Hermes-CLI contract questions whose consumer (`hermes gateway` argparse) lives in CANON-30 / the external `hermes-agent` runtime, not this repo:
1. Two `gateway` invocation styles in-repo (`gateway run --replace` per-agent/docker vs bare `gateway` for the Curator) — CLI-compatibility unprovable here.
2. `disable_native_hermes_gateway_units` enumerates only the `hermes-gateway*` glob — completeness depends on CANON-30 native-unit naming.

These are verification seams to close when the CANON-30 repair confirms the Hermes `gateway` contract, not operator product calls. They carry forward as standing items on CANON-30, not deferred decisions on CANON-26.
