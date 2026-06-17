# CANON-24 — Deployment & Install Lane — RECONCILED (both-model truth)

Adjudicator: Claude Opus 4.8 (1M) — FINAL. Method: re-opened every disputed cite
in code (Read/sed/grep); code wins over any name, comment, or prior claim.

- Codex (GPT-5.5 xhigh) SIGN-OFF: **OBJECT(6)** — central live-lane thesis correct,
  but the record needs the verifier refinements plus extra control-upgrade defects.
- Claude record verdict: live lane provably routes to `run_control_install_flow`;
  HIGH auto-push; doc drift; placeholder URLs; entrypoint fail-open.
- Claude adversarial verify: 5 refutations (R1–R5), 4 new gaps (G1–G4).

## FEDERATION SIGN-OFF: **BOTH-MODEL-AGREED**
Every material point reconciled to one code-grounded truth. Codex and both Claude
passes converge once the record absorbs the verifier's R1–R5 and Codex's three new
control-upgrade findings. No standing disagreement survives a direct read of code.

---

## RESOLUTION TABLE (disputed/refined points → winner + deciding cite)

| # | Point | Winner | Deciding cite (re-opened) |
|---|-------|--------|---------------------------|
| 1 | Public `install\|upgrade\|health` routes to Control Node, NOT `run_root_upgrade`; `run_root_upgrade` only via privileged `--apply-upgrade` (EUID 0) | both | `bin/deploy.sh:13012-13016`, `:12982-13000`, `:779-782` |
| 2 | `bin/init.sh` (752 lines) is the agent-enrollment flow; the 5-line wrapper is `bin/install-arclink.sh`. Record inventory line 13 is a flat error. | claude-verify / codex | `bin/init.sh:1-7` (`:5`=`if [[ $# -gt 0 ]]`), `wc -l`=752; `bin/install-arclink.sh:5` (`exec ../deploy.sh`) |
| 3 | P7 seam is a SAFE SUBSET, not "matching sets." Producer allowlist = 7 names; consumer accepts ANY pins.json component (12) + also `--branch`. | claude-verify / codex | `arclink_operator_upgrade_host_runner.py:26` (7-name set), `PIN_UPGRADE_FLAGS` emit `--ref/--tag/--version` only (`:27-34`); `bin/component-upgrade.sh:680-699` (accepts `--branch` + any pins component); `config/pins.json`=12 components |
| 4 | `run_upgrade_flow` is DEAD CODE (zero callers), not "reachable via retired paths." Retired modes just `return 2`. | claude-verify / codex | `grep run_upgrade_flow bin/deploy.sh` → only def at `:8224`; `retired_shared_host_mode`/`_docker_mode` `return 2` (`:631-644`) |
| 5 | "noop skips deploy" is FALSE when pins.json has uncommitted diff OR HEAD absent upstream → sets `pushed`, pushes, and (without `--skip-upgrade`) reexecs. Strengthens the HIGH. | claude-verify / codex | `bin/component-upgrade.sh:611-637` (value-unchanged branch sets `upgrade_status="pushed"`, `commit_and_push_pins`/`push_current_head`); runner deploys on `pushed`: `host_runner.py:257-259` |
| 6 | Operator SOUL output filename is `SOUL.md`, NOT `SOUL.operator.md` (template name is correct). | claude-verify / codex | `bin/install-operator-hermes-home.sh:115` (`"$HERMES_HOME_TARGET/SOUL.md"`) |
| 7 | Operator breadcrumb mis-keyed ONLY in component-upgrade non-docker reexec; common.sh/deploy.sh read the correct keys. | claude-verify / codex | producer `bin/deploy.sh:2856,2858` (`_REPO_DIR`,`_CONFIG_FILE`); wrong consumer `bin/component-upgrade.sh:515,517,520` (`_REPO`,`_CONFIG`) → empty → hardcoded fallback `:525-526`; correct readers `bin/common.sh:43,45,51`, `bin/deploy.sh:355,357,363` |
| 8 | Deploy-key env forwarded to control-upgrade is INERT: plain `git fetch --prune`, no `GIT_SSH_COMMAND`. | both / codex | `bin/component-upgrade.sh:498-504` (forwards `ARCLINK_UPSTREAM_DEPLOY_KEY_*`); `bin/deploy.sh:11567` (`git fetch --prune "$remote"`, no SSH env) |
| 9 | HIGH auto-push to live upstream branch on host-runner-triggered pin bumps. | both | `bin/component-upgrade.sh:658-662`; host-runner passes only `--skip-upgrade`: `host_runner.py:274-276` |
| 10 | AGENTS.md `./deploy.sh upgrade` 12-step doc describes retired `run_root_upgrade`, not live code. | both | `AGENTS.md:182-195` vs `bin/deploy.sh:11623-11646`, `:13012-13016` |
| 11 | `init.sh` placeholder `example` URL → real clone failure on Linux agent w/o `ARCLINK_INIT_REPO_URL`; `bootstrap-userland.sh:17` personal URL is reconcile metadata, NOT a clone. (Record's MEDIUM on the fork URL is slightly overstated.) | claude-verify / codex | `init.sh:13-14`, `ensure_repo_cache` clone `:124-125`, `should_remote_public_bootstrap`=false on Linux `:162-168`; bootstrap-userland URL feeds reconcile metadata not a git clone |
| 12 | docker-entrypoint fails open (warn+continue) on unwritable config/repair. | both | `bin/docker-entrypoint.sh:655-660`, `:663-698` |

## CONFIRMED Codex NEW FINDINGS (re-verified true → net-new federation risks)

- **[MEDIUM] Live control-upgrade has NO branch guard.** `sync_control_upgrade_checkout_from_upstream`
  builds whatever branch is checked out (`symbolic-ref HEAD` + its `@{u}`), with no
  `ARCLINK_UPSTREAM_BRANCH=arclink` enforcement. The guard
  `require_main_upstream_branch_for_upgrade` is called ONLY at `bin/deploy.sh:5647`
  (run_root_upgrade) and `:8257` (run_upgrade_flow) — both retired/dead — and is
  absent from `run_control_install_flow` (`:11589-11650`, verified not present).
  Cite: `bin/deploy.sh:11550-11567`, `:11623-11625`; guard def `:2823`, callers `:5647`,`:8257`.

- **[MEDIUM] Live control-upgrade deploys local-ahead (unpushed) commits.** When the
  checkout is ahead of upstream, it prints "building local ahead commit" and
  `return 0` (builds it), contradicting AGENTS.md "consumes the remote, not unpushed
  local commits." Cite: `bin/deploy.sh:11581-11583` vs `AGENTS.md:197-199`.

- **[LOW] Entrypoint writes secret VALUES unquoted into a shell-sourced env file.**
  `cat >"$CONFIG_FILE"` emits e.g. `POSTGRES_PASSWORD=$postgres_password` (no quotes,
  `bin/docker-entrypoint.sh:391-470`,`:549-551`); `bin/common.sh:213-214` later
  `source`s that file. Generated secrets are `token_urlsafe` (safe), but an
  operator-supplied split-mount value containing shell syntax could break/execute on
  source. Cite: `bin/docker-entrypoint.sh:391-470`,`:549-551`; `bin/common.sh:211-214`.

## CONFIRMED Claude-verify NEW GAPS (re-verified true)

- **[MEDIUM] Mis-keyed operator breadcrumb (G1).** Scoped to the non-docker
  `--apply-upgrade` reexec in component-upgrade.sh; host-runner uses docker mode
  (reexecs `deploy.sh upgrade`, `bin/component-upgrade.sh:497-504`) so live blast
  radius is low. Real undocumented defect. Cite per row 7 above.
- **[LOW/INFO] `change-me` can persist as live DB/Nextcloud admin password (G2).**
  `repair_placeholder_secret` is used ONLY for POSTGRES_PASSWORD / NEXTCLOUD_ADMIN_PASSWORD;
  when the init marker exists it writes/keeps literal `change-me` (`bin/docker-entrypoint.sh:332-338`).
  By design (cannot rotate an initialized DB by editing env), but undisclosed in the
  record's "idempotent secret repair" strength. Broker/helper tokens are NOT affected
  (regenerated unconditionally when empty/`change-me`, `:666-695`).
- **[INFO] Divergent `bootstrap.handshake` producer payloads (G3).** init.sh (remote)
  sends `auto_provision` (no `source_ip`); bin/init.sh (host) sends `source_ip`
  (no `auto_provision`). Consumer is CANON-18 (not verified here); producer divergence
  is real. Cite: `init.sh:264-272`, `bin/init.sh:450-454`.
- **[INFO] `flock 9` operator-install.lock blocks with no timeout (G4).**
  Cite: `bin/install-operator-hermes-home.sh:23` (bare `flock 9`, no `-n`/`-w`).

## REJECTED new-findings
None. Every Codex and Claude-verify new finding re-verified true in code.

## SEVERITY CHANGES (code-supported only)
- MEDIUM → LOW on the `bootstrap-userland.sh` fork-URL risk: `bin/bootstrap-userland.sh:17`
  feeds reconcile-vault-layout metadata, NOT a git clone in that path; it does not
  "clone the wrong repo." The init.sh `example`-URL risk stays the real clone failure.
  Cite: `bin/bootstrap-userland.sh:14-18` + reconcile metadata; vs `init.sh:124-125`.
- HIGH (host-runner pin push) BROADENED (not re-leveled): a value-"noop" can also
  push + deploy when the local checkout drifted. Cite: `bin/component-upgrade.sh:618-637`.
- The record's MEDIUM "placeholder upstream URLs" splits: init.sh stays MEDIUM
  (real failure), bootstrap-userland drops to LOW per above.

## STANDING DISAGREEMENTS
None. All material points settled from code.

## FINAL BOTH-MODEL VERDICT
CANON-24's central thesis is correct and stands: `./deploy.sh {install,upgrade,health}`
deterministically routes to the Dockerized Control Node flow (`run_control_install_flow`),
dirty-tree-guarded and ff-only-synced; `run_root_upgrade`/`run_root_install` are
reachable only via privileged `--apply-*`, and `run_upgrade_flow` is fully dead code.
The P7 host-runner ↔ component-upgrade.sh seam is mechanically sound but is a SAFE
SUBSET (independent allowlist gates), not a matched contract. The Dockerfile reads
pins.json correctly; the entrypoint materializes 600-perm config with atomic writes.
Reconciled risks: **HIGH** operator/Raven pin bumps auto-push to the production branch
(and a value-noop can push+deploy on local drift); **MEDIUM** the live control-upgrade
has no branch guard and will deploy whatever branch / local-ahead commit is checked out;
**MEDIUM** AGENTS.md documents a retired flow; **MEDIUM** mis-keyed operator breadcrumb
(scoped, low blast radius); **MEDIUM** init.sh `example` placeholder URL is a real clone
failure absent `ARCLINK_INIT_REPO_URL`; **LOW/INFO** entrypoint fail-open + persistent
`change-me` DB password + unquoted-secret source risk. Record corrections to apply:
bin/init.sh inventory (R1), P7 "match" → safe-subset (R2/R3), SOUL.md filename (R5),
bootstrap-userland URL severity (MEDIUM→LOW).
