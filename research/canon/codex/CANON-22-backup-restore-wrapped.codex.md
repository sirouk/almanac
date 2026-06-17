<<<CODEX-VERDICT-START CANON-22>>>
## CANON-22 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(3)
ONE-LINE VERDICT: CANON-22 is mostly ratified; the verifier’s HIGH/MEDIUM risks are real, and I add two backup proof gaps plus resolve the open §B39 questions.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM seams: `captain-wrapped` producer/consumer keys match, but no claim path covers it (`python/arclink_wrapped.py:921`, `python/arclink_notification_delivery.py:1803`, `python/arclink_notification_delivery.py:1902`).
- CONFIRM seams: persistent failure emits `operator`/`tui-only` and delivery treats tui-only as no external send (`python/arclink_wrapped.py:987`, `python/arclink_wrapped.py:990`, `python/arclink_notification_delivery.py:1742`, `python/arclink_notification_delivery.py:1773`).
- CONFIRM seams: shared backup service/timer and agent cron are wired; record cite should split cadence vs argv (`systemd/user/arclink-github-backup.service:6`, `systemd/user/arclink-github-backup.timer:6`, `bin/install-agent-cron-jobs.sh:45`, `bin/install-agent-cron-jobs.sh:193`, `bin/backup-agent-home.sh:17`).
- CONFIRM seams: Docker Wrapped loop runs every 300s and wrapper passes `--json` into Python (`python/arclink_provisioning.py:1313`, `python/arclink_provisioning.py:1315`, `bin/docker-job-loop.sh:141`, `bin/arclink-wrapped.sh:13`, `python/arclink_wrapped.py:1165`).
- CONFIRM seams: schema/check/redaction/local-only restore claims hold (`python/arclink_control.py:745`, `python/arclink_control.py:970`, `python/arclink_control.py:1738`, `python/arclink_wrapped.py:37`, `python/arclink_wrapped.py:710`, `bin/arclink-restore-smoke.sh:74`).
- CONFIRM HIGH: operator pin upgrade auto-commits/pushes because host-runner sends `--skip-upgrade` only, while component-upgrade commits and pushes unless `--skip-push` is present (`python/arclink_operator_upgrade_host_runner.py:274`, `python/arclink_operator_upgrade_host_runner.py:276`, `bin/component-upgrade.sh:652`, `bin/component-upgrade.sh:658`, `bin/component-upgrade.sh:475`, `bin/component-upgrade.sh:491`).
- CONFIRM HIGH / §A16: generate-then-enqueue failure creates a committed generated row, then a later failed row shadows it and `failed_retry` bypasses the missing-signal gate (`python/arclink_wrapped.py:719`, `python/arclink_wrapped.py:728`, `python/arclink_wrapped.py:1043`, `python/arclink_wrapped.py:1046`, `python/arclink_wrapped.py:1079`, `python/arclink_wrapped.py:1091`, `python/arclink_wrapped.py:1095`).
- CONFIRM MEDIUM / §A16: 404 fail-open spans both backup lanes, not just agent-home (`bin/backup-agent-home.sh:87`, `bin/backup-agent-home.sh:180`, `common.sh:1360`, `common.sh:1390`, `bin/backup-to-github.sh:130`).
- CONFIRM MEDIUM: failed Wrapped periods retry every scheduler tick with no time/backoff field (`python/arclink_wrapped.py:1079`, `python/arclink_wrapped.py:1091`, `python/arclink_provisioning.py:1315`).
- CONFIRM MEDIUM: eligibility ignores `session_counter`; session counts affect generated stats only after the missing gate has passed (`python/arclink_wrapped.py:365`, `python/arclink_wrapped.py:404`, `python/arclink_wrapped.py:646`, `python/arclink_wrapped.py:684`, `python/arclink_wrapped.py:1095`).
- REFINE §B39: a durable Stripe `received` row is stranded on replay because duplicate `received` returns replayed without processing; a shipped path can commit inside this flow through onboarding expiry’s default commit before later processing (`python/arclink_entitlements.py:544`, `python/arclink_entitlements.py:552`, `python/arclink_onboarding.py:337`, `python/arclink_onboarding.py:324`).
- REFINE §B39: quiet-hours math is UTC-only, not proven correct for local/DST semantics; `_parse_dt` normalizes to UTC before `replace(hour=...)` applies the quiet window (`python/arclink_wrapped.py:70`, `python/arclink_wrapped.py:80`, `python/arclink_wrapped.py:801`, `python/arclink_wrapped.py:808`).
- CONFIRM §B39: restore-smoke is run in CI with both `shared` and `agent-home` via the all-`tests/test_*.py` workflow (`.github/workflows/install-smoke.yml:33`, `.github/workflows/install-smoke.yml:40`, `tests/test_backup_git_regressions.py:388`, `tests/test_agent_backup_regressions.py:347`).

### New findings both Claude passes missed (severity + path:line)
- MEDIUM: control-plane backup visibility checks trust overrideable `GITHUB_API_BASE`/`BACKUP_GIT_GITHUB_API_BASE` with no agent-home-style test guard, so the public-repo refusal can be bypassed by config/env spoofing before `require_private_github_backup_remote` evaluates visibility (`common.sh:1331`, `common.sh:1389`, `common.sh:1394`; contrast guard `bin/backup-agent-home.sh:22`).
- LOW: agent-home “no secrets/logs” restore proof does not screen symlink targets inside curated dirs; backup copies allowlisted dirs with `rsync -a`/`cp -R`, while restore-smoke only rejects top-level `secrets`/`logs` and accepts any curated path (`bin/backup-agent-home.sh:150`, `bin/backup-agent-home.sh:204`, `bin/arclink-restore-smoke.sh:221`, `bin/arclink-restore-smoke.sh:226`).

### Claude citations re-confirmed or corrected
- RECONFIRMED: `render_kind` is producer-only dead metadata in the repo search I ran (`python/arclink_wrapped.py:919`).
- CORRECTED: CANON seam cite for cron should include actual subprocess argv at `bin/install-agent-cron-jobs.sh:193`; `:45` proves only the 240-minute cadence.
- CORRECTED: force-with-lease duplicate locations are `bin/backup-to-github.sh:51` and `bin/backup-agent-home.sh:139`; the line range in the record conflates the two scripts.
- REFUTE related open seam: no CANON-22 backup script consumes `backup_deploy_key_private_ref`; the only code occurrence is dashboard metadata, while action-worker backup verification is fail-closed and agent backup uses `AGENT_BACKUP_KEY_PATH` state (`python/arclink_dashboard.py:1237`, `python/arclink_action_worker.py:954`, `python/arclink_action_worker.py:973`, `bin/backup-agent-home.sh:39`).

### Residual disagreement with the Claude half (for final reconciliation)
- No material rejection. I agree with the verifier’s promotion of duplicate-report storm and 404 fail-open scope, but CANON-22 should add the control-lane API-base spoof gap and weaken any “local quiet hours” claim to “UTC quiet hours only” (`common.sh:1331`, `python/arclink_wrapped.py:801`).
<<<CODEX-VERDICT-END CANON-22>>>
