<<<CODEX-VERDICT-START CANON-24>>>
## CANON-24 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(6)
ONE-LINE VERDICT: Central live-lane thesis is correct, but the record needs verifier refinements plus one extra control-upgrade branch/upstream defect.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM: public `install|upgrade|health` routes to Control Node, not `run_root_upgrade`: `bin/deploy.sh:13012-13016`, `bin/deploy.sh:12832-12836`; `run_root_upgrade` is only privileged `--apply-upgrade`: `bin/deploy.sh:779-782`, `bin/deploy.sh:12982-13000`.
- REFINE: `run_upgrade_flow` is dead from dispatch, not retired-reachable; retired modes just return 2: `bin/deploy.sh:631-644`, `bin/deploy.sh:8224-8261`, `bin/deploy.sh:13023-13028`.
- CONFIRM: `bin/init.sh` is the agent enrollment flow, not a 5-line wrapper; wrapper is `bin/install-arclink.sh`: `bin/init.sh:4-7`, `bin/init.sh:380-456`, `bin/install-arclink.sh:5`.
- REFINE: P7 seam is safe-subset, not matching sets. Runner allows 7 components/3 emitted flags: `python/arclink_operator_upgrade_host_runner.py:26-34`; consumer accepts any pins component and `--branch` too: `bin/component-upgrade.sh:680-699`, `config/pins.json:7-97`.
- CONFIRM: HIGH auto-push risk. Host-runner passes `--skip-upgrade` only: `python/arclink_operator_upgrade_host_runner.py:274-276`; changed pins commit+push: `bin/component-upgrade.sh:658-662`; value-noop can still push: `bin/component-upgrade.sh:618-637`; runner deploys on `changed|pushed`: `python/arclink_operator_upgrade_host_runner.py:248-259`, `python/arclink_operator_upgrade_host_runner.py:363`.
- CONFIRM: deploy-key env is inert on live control-upgrade path. Component-upgrade forwards it: `bin/component-upgrade.sh:497-504`; control sync uses current git upstream and plain `git fetch`, no `GIT_SSH_COMMAND`: `bin/deploy.sh:11555-11567`.
- CONFIRM: AGENTS upgrade doc describes retired root flow, not live code: `AGENTS.md:182-195` vs `bin/deploy.sh:11623-11646`, `bin/deploy.sh:13012-13016`.
- REFINE: placeholder URL risk is real for top-level `init.sh` clone defaults: `init.sh:13-14`, `init.sh:117-125`; bootstrap-userland’s personal URL is generated-note metadata, not a clone in that path: `bin/bootstrap-userland.sh:14-18`, `bin/reconcile-vault-layout.py:331-332`, `bin/reconcile-vault-layout.py:416-417`.
- CONFIRM: docker-entrypoint fails open on unwritable config/repair: `bin/docker-entrypoint.sh:655-660`, `bin/docker-entrypoint.sh:663-698`; DB/admin password repair can preserve literal `change-me` after init markers: `bin/docker-entrypoint.sh:323-341`.
- CONFIRM: operator breadcrumb is mis-keyed only in component-upgrade non-docker reexec: producer writes `_CONFIG_FILE/_REPO_DIR`: `bin/deploy.sh:2855-2858`; consumer reads `_CONFIG/_REPO`: `bin/component-upgrade.sh:514-520`, then falls back hardcoded: `bin/component-upgrade.sh:524-538`. Common/deploy readers use the correct keys: `bin/common.sh:41-51`.
- REFUTE: operator SOUL output filename claim; rendered target is `SOUL.md`, not `SOUL.operator.md`: `bin/install-operator-hermes-home.sh:112-115`.
- CONFIRM: no CANON-24 item exists in residual severity disputes §C; no tiebreak needed there.

### New findings both Claude passes missed (severity + path:line)
- MEDIUM: live control upgrade has no `ARCLINK_UPSTREAM_BRANCH=arclink` guard and deploys the current checkout branch/upstream; branch guard exists only in retired/root paths: `bin/deploy.sh:11550-11567`, `bin/deploy.sh:11623-11625`, `bin/deploy.sh:5647`, `bin/deploy.sh:8257`.
- MEDIUM: live control upgrade can deploy clean local commits that are ahead of upstream, contradicting “remote, not unpushed local commits”: `bin/deploy.sh:11574-11582` vs `AGENTS.md:197-199`.
- LOW: initial `docker-entrypoint` config writes env-provided secret values unquoted into a file later sourced by shell helpers; generated secrets are safe, but operator-supplied values with shell syntax can break/execute on source: `bin/docker-entrypoint.sh:391-470`, `bin/docker-entrypoint.sh:549-551`, `bin/common.sh:211-214`, `bin/deploy.sh:8428-8433`.

### Claude citations re-confirmed or corrected
- Reconfirmed: stable-copy self reexec: `bin/deploy.sh:11-23`; Dockerfile pin reads: `Dockerfile:74-86`; status marker parser/producer: `bin/component-upgrade.sh:46`, `python/arclink_operator_upgrade_host_runner.py:236-259`; Docker entrypoint runtime-env early exec: `bin/docker-entrypoint.sh:177-185`.
- Corrected: component-upgrade “noop skips deploy” is false when pins diff exists or HEAD is absent upstream: `bin/component-upgrade.sh:611-637`.
- Corrected: `bootstrap-userland.sh` URL claim should be “wrong generated repo metadata,” not “wrong clone”: `bin/bootstrap-userland.sh:17`, `bin/reconcile-vault-layout.py:505-605`.
- Corrected: consolidated HIGH auto-push risk is a CANON-24 code risk even if the table row labels it CANON-22: `bin/component-upgrade.sh:658-662`.

### Residual disagreement with the Claude half (for final reconciliation)
- Keep the record’s core live-lane verdict, but amend CANON-24 with: dead `run_upgrade_flow`, safe-subset P7 gates, value-noop push/deploy, scoped breadcrumb breakage, bootstrap-userland URL severity reduction, and the new control-upgrade branch/local-ahead deployment risk.
<<<CODEX-VERDICT-END CANON-24>>>
