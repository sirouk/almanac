<<<CODEX-FIX-START CANON-24>>>
## CANON-24 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: AGENTS.md, init.sh, bin/deploy.sh, bin/component-upgrade.sh, bin/docker-entrypoint.sh, bin/install-operator-hermes-home.sh, python/arclink_operator_upgrade_host_runner.py, python/arclink_operator_upgrade_broker.py, tests/test_arclink_docker.py, tests/test_deploy_regressions.py
TESTS: PASS: bash -n touched shell + bin/*.sh; py_compile broker/runner; tests/test_arclink_docker.py; tests/test_arclink_operator_raven.py; tests/test_docker_health_regressions.py; 5 CANON-24 deploy tests invoked directly. NEEDS-REVIEW: full tests/test_deploy_regressions.py stops early on unrelated Discord onboarding assertion before CANON-24 tests.
### Fixed (severity — what — path:line)
- HIGH — queued pin upgrades no longer auto-push to upstream; host-runner and broker fallback pass `--skip-push` and mark changed-pin deploys as explicit local dirty builds — python/arclink_operator_upgrade_host_runner.py:306, python/arclink_operator_upgrade_broker.py:526
- MEDIUM — live control upgrade now uses deploy-key SSH config for fetch and refuses detached, wrong-branch, no-upstream, local-ahead, and diverged checkouts by default — bin/deploy.sh:11535, bin/deploy.sh:11563, bin/deploy.sh:11614, bin/deploy.sh:11658
- MEDIUM — non-docker component-upgrade reexec reads the operator breadcrumb’s actual `_CONFIG_FILE/_REPO_DIR` keys — bin/component-upgrade.sh:514
- MEDIUM — top-level init no longer defaults to `github.com/example`; it clones the canonical repo/branch and raw URL — init.sh:13, init.sh:126
- MEDIUM/LOW — docker entrypoint quotes shell-sourced generated config values and fails closed on missing/unrepairable placeholder secrets, including persisted `change-me` — bin/docker-entrypoint.sh:270, bin/docker-entrypoint.sh:330, bin/docker-entrypoint.sh:715, bin/docker-entrypoint.sh:724
- LOW — fixed `printf "$TARGET_USER"` format-string fallback — init.sh:200
- LOW — removed spurious empty iteration from `CONTROL_DEPLOY_ARGS` expansion — bin/deploy.sh:11634
- INFO — operator Hermes-home install lock now has a bounded timeout — bin/install-operator-hermes-home.sh:10, bin/install-operator-hermes-home.sh:24
- MEDIUM — AGENTS upgrade instructions now describe the live Dockerized Control Node path, not retired `run_root_upgrade` — AGENTS.md:182
### Skipped (risk-accepted / standing / out-of-scope — why)
- P7 producer/consumer component sets remain a safe subset, not a code defect requiring expansion.
- `run_upgrade_flow` dead code was not removed; removal is broad cleanup outside the requested repair surface.
- GAP-019 trusted-host/root-equivalence properties were not changed; queued pin deploys now avoid upstream mutation but still intentionally run on the trusted host.
- `bootstrap.handshake` producer shape divergence was not changed because the consumer contract is owned outside CANON-24.
### NEEDS-DECISION (ambiguous; left for human)
- Whether to unify `init.sh` remote `auto_provision` and `bin/init.sh` host-side `source_ip` payloads for `bootstrap.handshake`; left unchanged pending CANON-18 consumer decision.
### Cross-piece edits made (if any) + tests added
- Cross-piece: python/arclink_operator_upgrade_broker.py aligned direct broker fallback with host-runner no-push behavior.
- Cross-piece/doc: AGENTS.md corrected live upgrade guidance.
- Tests added/updated: pin no-push host-runner proof, entrypoint quote/source proof, component breadcrumb proof, init canonical URL/safe printf proof, operator install lock timeout proof, stricter control-upgrade sync assertions.
<<<CODEX-FIX-END CANON-24>>>
