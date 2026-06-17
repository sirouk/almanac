# CANON-24 — Deployment & Install Lane — ADVERSARIAL VERIFICATION

Verifier: independent adversarial skeptic. Method: re-opened every load-bearing
file at its cited path:line; verified both ends of cross-piece seams in code.

## VERDICT (summary)
The record is **largely trustworthy on its central thesis** (the public
`./deploy.sh {install,upgrade,health}` lane routes to `run_control_install_flow`,
NOT `run_root_upgrade`; the P7 host-runner↔component-upgrade.sh status-marker seam
is mechanically real; Dockerfile pin reads match pins.json; entrypoint writes 600
config). BUT it contains **one flat factual error in its file inventory**, **two
overstated "both-ends-verified" seam claims**, **one genuinely broken seam neither
the record nor prior docs caught (mis-keyed operator breadcrumb)**, and **an
under-described HIGH-risk behavior (a value-"noop" pin can still push + deploy).**

---

## REFUTATIONS (record claim → code reality)

### R1 [REFUTED] Inventory says `bin/init.sh` is a 5-line wrapper. It is 752 lines.
Record line 13: "`bin/init.sh` (5) — wrapper that `exec`s `../deploy.sh`
(`bin/init.sh:5`)." FALSE. `wc -l bin/init.sh` = 752. `bin/init.sh:5` is
`if [[ $# -gt 0 ]]; then` — not an exec. `bin/init.sh` is the in-repo agent
enrollment flow (`run_agent_flow`, bin/init.sh:380-716). The record confused
`bin/init.sh` (agent flow) with `bin/install-arclink.sh` (the actual 5-line
wrapper, install-arclink.sh:5). Note the record is internally inconsistent: its
deeper citations (lines 32-33, contract #6/#7) DO cite `bin/init.sh` correctly as
the 752-line agent flow (require_linux_host at :68-85, preseed env at :386-393,
handshake at :444-456 all verified accurate). Only the inventory line is wrong.
Severity: the inventory misdescribes the single largest non-deploy.sh file in the
piece — a reader trusting line 13 would skip 747 lines of enrollment logic.

### R2 [REFUTED] "flag/component sets ... match on both sides" (contract #1).
Record line 81 marks the P7 seam "BOTH ENDS VERIFIED: yes — flag/component sets
and the status string literals match on both sides." The **component sets do NOT
match**. Producer `ALLOWED_PIN_COMPONENTS` (host_runner.py:26) = 7 names
{hermes-agent,qmd,nextcloud,postgres,redis,nvm,node}. Consumer
(component-upgrade.sh:697-699) accepts ANY component present in config/pins.json —
which has 12 (hermes-agent, hermes-docs, nextcloud, node, nvm, postgres, python,
qmd, quarto, redis, tailscale, uv). These are two *independent* gates, not a
matched contract; the producer set is a subset, so it is *safe*, but the record's
"match on both sides" is false as stated. Flags are likewise subset (producer can
emit --ref/--tag/--version; consumer also accepts --branch) — not equality.

### R3 [REFUTED] Self-check #2: "a noop with clean returncode skips deploy."
Record line 100 frames a pin "noop" as deploy-skipping. Code refutes: in
`do_apply` the value-unchanged branch (component-upgrade.sh:611-639), when
`skip_push != 1` and pins.json has an uncommitted diff (`:618`) OR local HEAD is
absent from upstream (`:628`), it sets `upgrade_status="pushed"`, runs
`commit_and_push_pins`/`push_current_head`, and emits `status_marker "pushed"`
(:637). The host-runner's `_pin_upgrade_log_requires_deploy` then returns True on
`pushed` (host_runner.py:257-259) → runs `deploy.sh upgrade`. So a *requested pin
already at target* can STILL push to the production branch and trigger a full
Control Node rebuild whenever the local checkout has drifted. The record's
self-check undersells this; it should amplify the HIGH risk, not bound it.

### R4 [REFUTED-as-imprecise] "`run_upgrade_flow` is only invoked from retired paths."
Record lines 91/121 say `run_upgrade_flow` (deploy.sh:8224) "is only invoked from
retired paths." `grep -n run_upgrade_flow bin/deploy.sh` shows it at the
definition (8224) and NOWHERE ELSE — it has ZERO callers. The retired-mode
functions (retired_shared_host_mode :631, retired_shared_host_docker_mode :646)
just print a message and `return 2`; they do not call it. So it is *fully dead
code*, not "reachable via retired paths." This SHARPENS (does not break) the
central thesis: public `upgrade` cannot reach `run_root_upgrade`.

### R5 [REFUTED-as-naming] Operator home output file is `SOUL.md`, not `SOUL.operator.md`.
Record line 54: "renders `SOUL.operator.md` from `templates/SOUL.operator.md.tmpl`".
The template is correct, but the rendered target is `$HERMES_HOME_TARGET/SOUL.md`
(install-operator-hermes-home.sh:115 passes `"$HERMES_HOME_TARGET/SOUL.md"`).
Minor, but the output filename in the record is wrong.

---

## CONFIRMATIONS (independently re-verified true)

- C1. Public MODE routing: `install|upgrade|health` → CONTROL_DEPLOY_COMMAND,
  MODE=control, run_control_deploy_flow (deploy.sh:13012-13016). `--apply-upgrade`
  → PRIVILEGED_MODE=upgrade (deploy.sh:779-782), EUID==0 required (:12991-12994),
  run_root_upgrade (:12998). install→run_control_install_flow 1 (:12833),
  upgrade→run_control_install_flow 0 (:12836). CENTRAL DRIFT CLAIM CONFIRMED.
- C2. deploy.sh self-reexec stable copy (deploy.sh:11-20): mktemp 0700, exports
  ARCLINK_DEPLOY_STABLE_COPY=1 + owner PID, execs the copy. Cleanup trap (:21-23).
  Accurate.
- C3. Dirty-tree guard + ff-only sync only on upgrade (run_interactive!=1):
  verify_control_upgrade_checkout_clean (:11515-11533, refuses dirty unless
  ARCLINK_CONTROL_UPGRADE_ALLOW_DIRTY=1) and sync_control_upgrade_checkout_from_upstream
  (:11535-11587, ff-only or refuse on divergence) gated at :11623-11626. Install
  (run_interactive=1) does NOT verify clean. Accurate.
- C4. Dockerfile pin reads (Dockerfile:74-86) read
  ["components"][name][field] for uv.version, qmd.version, hermes-agent.repo/ref;
  pins.json declares uv=installer-url(+version), qmd=npm(+version),
  hermes-agent=git-commit(+repo/ref). Contract #3 holds.
- C5. P7 producer argv (host_runner.py:276) = [component_upgrade, component,
  "apply", flag, target, "--skip-upgrade"]; consumer parser accepts apply +
  --ref/--tag/--version/--branch (component-upgrade.sh:680-687). status_marker
  printf 'ARCLINK_COMPONENT_UPGRADE_STATUS=%s' (:46) is ANSI-free; subprocess
  stdout→log (host_runner.py:222-223, stderr=STDOUT), re-parsed by
  _component_upgrade_statuses_from_text (:236-245). Mechanically sound.
- C6. component-upgrade docker-mode reexec `deploy.sh upgrade` (:497-504);
  non-docker sudo `deploy.sh --apply-upgrade` (:530-538). do_apply re-exec gated by
  `skip_upgrade!=1 && skip_push!=1` (:664) — with host-runner's --skip-upgrade it
  does NOT re-exec, emits status_marker changed (:668). Accurate.
- C7. docker-entrypoint: runtime-env mode early `exec "$@"` (:177-185); else state
  dirs (:187-248), template rsync --ignore-existing (:252-260), default docker.env
  600 only if config_file_can_write (:655-661), secret repair only if
  config_file_can_repair else warn+continue (:663-698). Self-check #3 ("always"
  wrong; conditional) is correct.
- C8. Operator-install flock 9 on operator-install.lock (install-operator-hermes-home.sh:23,155);
  bootstrap-system EUID!=0 → exit 1 (:21-24); refresh-agent-install --unix-user
  required else exit 2 (:66-69), must run as user/root (:109-112);
  migrate-hermes-config <1 arg → exit 2 (:4-7); activate-agent no state → exit 0
  (:61-63), missing token → exit 1 (:65-68), 600 args file (:83-84), agents.register
  with {token,unix_user,display_name,role,hermes_home,model_preset,model_string,channels}
  (:97-106), reads agent_id/manifest_path/subscriptions/home_channel (:119-127).
  All accurate.
- C9. .dockerignore excludes /config/arclink.env (:3), .env* (:6-7), /arclink-priv +
  arclink-priv/** (:9-10), *.sqlite* (:22-25), plus /.arclink-operator.env (:5),
  /config/install.answers.env (:4). Accurate (record under-enumerated but correct).
- C10. AGENTS.md drift: AGENTS.md:182-195 describes the 12-step run_root_upgrade flow
  (fetch upstream, deploy key, sync public repo, bootstrap system+userland, curator,
  realign, restart, release.json, strict health, live-smoke) that the public
  `./deploy.sh upgrade` does NOT run. AGENTS.md:114 "thin wrapper" is true. Drift
  claim CONFIRMED.
- C11. Deploy-key inertness on control upgrade (record OPEN): confirmed
  sync_control_upgrade_checkout_from_upstream uses git `@{u}` + plain
  `git fetch --prune "$remote"` (:11567) with NO GIT_SSH_COMMAND / deploy-key env.
  The ARCLINK_UPSTREAM_DEPLOY_KEY_* env forwarded by component-upgrade.sh:498-504
  is genuinely inert in control mode. This means contract #2 ("both ends verified:
  yes for env-var names") describes a *forwarded-but-unconsumed* seam — honest in
  the record's own "partial for behavior" caveat, but worth flagging as effectively
  a no-op seam.
- C12. init.sh placeholder URLs (record risk): top-level init.sh:13-14 default
  REPO_URL=github.com/example/arclink.git, RAW_INIT_URL=.../example/...; on Linux
  agent mode with no target-host, should_remote_public_bootstrap=false (:162-168) →
  ensure_repo_cache clones $REPO_URL (:124-125) when LOCAL_REPO_DIR empty. A
  curl-piped `init.sh agent` with no ARCLINK_INIT_REPO_URL clones the nonexistent
  example repo. CONFIRMED.
- C13. printf-as-format-string init.sh:199 `printf "$TARGET_USER"` — confirmed; LOW
  (only the unlikely `id -un` failure fallback path; usernames rarely contain %).

---

## NEW GAPS (neither record nor prior docs mention)

### G1 [MEDIUM] Mis-keyed operator breadcrumb → dead config discovery (BROKEN SEAM).
Producer `write_operator_checkout_artifact` writes
`ARCLINK_OPERATOR_DEPLOYED_CONFIG_FILE=...` (deploy.sh:2858) and
`ARCLINK_OPERATOR_DEPLOYED_REPO_DIR=...` (:2856). Consumer in
`reexec_upgrade` sources the breadcrumb and reads
`${ARCLINK_OPERATOR_DEPLOYED_CONFIG:-}` (component-upgrade.sh:520) — a DIFFERENT
key (`_CONFIG`, not `_CONFIG_FILE`); it also pre-defaults `..._REPO=""` (:515) vs
producer `..._REPO_DIR`. Result: breadcrumb-based config discovery on the
non-docker `--apply-upgrade` path ALWAYS yields empty and falls through to the
hardcoded `/home/arclink/arclink/arclink-priv/config/arclink.env` (:525). The
breadcrumb is effectively dead. Both ends read in code; impact bounded to the
non-docker apply path (host-runner uses docker mode → reexecs `deploy.sh upgrade`,
:497-504, bypassing this), so live blast radius is low — but it is a real,
undocumented defect the record's TOUCH-POINTS breadcrumb mention (line 60) glosses.

### G2 [LOW/INFO] DB-password secret-repair can PERSIST literal `change-me`.
`repair_placeholder_secret` (docker-entrypoint.sh:323-341) is used ONLY for
POSTGRES_PASSWORD and NEXTCLOUD_ADMIN_PASSWORD (:664-665). When the init marker
exists (PG_VERSION / config.php) it deliberately does NOT regenerate: if the value
is empty-with-marker it WRITES the literal string `change-me` (:332-335), and if
the value is already `change-me` with marker it keeps it (:336-338). This is
by-design (you cannot rotate an already-initialized DB password by editing env),
but the record's "idempotent secret repair" strength (verdict, line 121) and
secrets touch-point (line 65) do not disclose that `change-me` can remain the live
DB/Nextcloud admin password value. Broker/helper tokens (:675-695) are NOT
affected (regenerated unconditionally when empty/change-me).

### G3 [INFO] Two different handshake payload shapes to one MCP tool (seam gap).
Contract #6 lists both producers but does not flag that they send DIFFERENT
arguments to `bootstrap.handshake`: top-level init.sh (remote) sends
`{requester_identity,unix_user,auto_provision:true(,model_preset,channels)}`
(init.sh:264-272) with NO source_ip; host-side bin/init.sh sends
`{requester_identity,unix_user,source_ip}` (bin/init.sh:450-454) with NO
auto_provision. A reader assumes a uniform shape. Consumer is CANON-18 (unverified
here), so I cannot confirm both are accepted — but the producer divergence is
real and undocumented.

### G4 [INFO] flock 9 on operator-install.lock is blocking with no timeout.
install-operator-hermes-home.sh:23 uses bare `flock 9` (no -n, no -w). A stale
holder blocks the operator-home install indefinitely. Low practical risk (single
control-node operator install), noted for completeness.

---

## SEAM MISMATCHES (consolidated)
1. operator breadcrumb: producer key `_CONFIG_FILE`/`_REPO_DIR` (deploy.sh:2856,2858)
   vs consumer read `_CONFIG`/`_REPO` (component-upgrade.sh:515,517,520). BROKEN.
2. P7 component set: producer 7-name allowlist (host_runner.py:26) vs consumer
   pins.json-membership (component-upgrade.sh:697) — independent gates, not the
   "match" the record claims (safe subset, but mis-described).
3. handshake payload: auto_provision (init.sh:267) vs source_ip (bin/init.sh:453)
   to the same tool — divergent producer shapes, undocumented.
4. deploy-key env (component-upgrade.sh:498-504) forwarded to control upgrade but
   NOT consumed (deploy.sh:11567 plain fetch) — forwarded-but-inert no-op seam.

## RISK RE-CALIBRATION
- HIGH (host-runner pin push to upstream): CONFIRMED and should be BROADENED — a
  value-"noop" can also push + deploy when the local checkout drifted (R3).
- MEDIUM (bootstrap-userland fork URL, record line 114): SLIGHTLY OVERSTATED — the
  github.com/sirouk/arclink.git default (bootstrap-userland.sh:17) feeds
  reconcile-vault-layout.py --repo-url (metadata), NOT a git clone in that path; it
  does not "clone the wrong repo" there. The *init.sh* example-URL risk (C12) IS a
  real clone failure.

## OVERALL
Trust the record's central routing/seam thesis and its main risks. Distrust its
file inventory for bin/init.sh (R1), its "both-ends match" wording on the P7
component set (R2) and the noop framing (R3). Add the mis-keyed breadcrumb (G1) as
a confirmed new defect and the change-me DB-password persistence (G2) as an
undisclosed secret-repair nuance.
